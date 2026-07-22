"""Small sqlite3-style wrapper over psycopg for the current RUANA DBManager.

This is a migration bridge, not a long-term abstraction. It lets the existing
SQLite-oriented code run against Supabase Postgres while we gradually replace
raw SQL with explicit Postgres queries.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Mapping
from typing import Any, Iterable, Optional

import psycopg
from psycopg.rows import dict_row


class CompatRow(Mapping):
    def __init__(self, data: dict[str, Any], order: list[str]):
        self._data = data
        self._order = order

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, int):
            return self._data[self._order[key]]
        return self._data[key]

    def __iter__(self):
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def keys(self):
        return self._data.keys()


def _replace_placeholders(sql: str) -> str:
    out: list[str] = []
    in_single = False
    in_double = False
    i = 0
    while i < len(sql):
        ch = sql[i]
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        if ch == "?" and not in_single and not in_double:
            out.append("%s")
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def _translate_sql(sql: str) -> str:
    translated = sql.strip()

    translated = re.sub(
        r"INSERT\s+OR\s+IGNORE\s+INTO\s+",
        "INSERT INTO ",
        translated,
        flags=re.IGNORECASE,
    )
    if re.match(r"INSERT\s+INTO\s+", translated, flags=re.IGNORECASE) and " OR IGNORE " in sql.upper():
        translated = f"{translated} ON CONFLICT DO NOTHING"

    # INSERT OR REPLACE INTO t (a,b,...) VALUES (...) → upsert on primera columna (PK típica)
    replace_match = re.match(
        r"INSERT\s+OR\s+REPLACE\s+INTO\s+(\w+)\s*\(([^)]+)\)\s*VALUES\s*\(([^)]+)\)\s*;?\s*$",
        translated,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if replace_match:
        table, cols_raw, vals_raw = replace_match.groups()
        cols = [c.strip() for c in cols_raw.split(",") if c.strip()]
        if cols:
            pk = cols[0]
            updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols[1:]) or f"{pk} = EXCLUDED.{pk}"
            translated = (
                f"INSERT INTO {table} ({cols_raw}) VALUES ({vals_raw}) "
                f"ON CONFLICT ({pk}) DO UPDATE SET {updates}"
            )

    translated = re.sub(
        r"datetime\('now',\s*'-([0-9]+)\s+day'\)",
        r"(now() - interval '\1 day')",
        translated,
        flags=re.IGNORECASE,
    )
    translated = re.sub(
        r"datetime\('now',\s*'-([0-9]+)\s+days'\)",
        r"(now() - interval '\1 days')",
        translated,
        flags=re.IGNORECASE,
    )
    translated = re.sub(
        r"datetime\('now',\s*'-([0-9]+)\s+hour'\)",
        r"(now() - interval '\1 hour')",
        translated,
        flags=re.IGNORECASE,
    )
    translated = re.sub(
        r"datetime\('now',\s*'-([0-9]+)\s+hours'\)",
        r"(now() - interval '\1 hours')",
        translated,
        flags=re.IGNORECASE,
    )
    translated = re.sub(r"datetime\('now'\)", "now()", translated, flags=re.IGNORECASE)
    translated = re.sub(r"date\('now'(?:,\s*'localtime')?\)", "current_date", translated, flags=re.IGNORECASE)
    translated = re.sub(r"date\(([^()]+)\)", r"(\1)::date", translated, flags=re.IGNORECASE)
    translated = re.sub(r"datetime\(([^()]+)\)", r"\1", translated, flags=re.IGNORECASE)

    translated = re.sub(
        r"strftime\('%H',\s*([^)]+)\)",
        r"to_char(\1, 'HH24')",
        translated,
        flags=re.IGNORECASE,
    )
    translated = re.sub(
        r"julianday\('now'\)\s*-\s*julianday\(([^)]+)\)",
        r"(extract(epoch from (now() - \1)) / 86400.0)",
        translated,
        flags=re.IGNORECASE,
    )
    translated = re.sub(
        r"julianday\('now',\s*'localtime'\)\s*-\s*julianday\(MAX\(([^)]+)\)\)",
        r"(extract(epoch from (now() - max(\1))) / 86400.0)",
        translated,
        flags=re.IGNORECASE,
    )
    translated = translated.replace("AUTOINCREMENT", "")
    translated = _replace_placeholders(translated)
    return translated


class PostgresCompatCursor:
    def __init__(self, conn: "PostgresCompatConnection"):
        self.conn = conn
        self._cursor = conn._conn.cursor()
        self.lastrowid: Optional[int] = None
        self.description = None
        self._synthetic_rows: Optional[list[tuple[Any, ...]]] = None
        self._synthetic_description = None

    def execute(self, sql: str, params: Optional[Iterable[Any]] = None):
        params = tuple(params or ())
        self._synthetic_rows = None
        self._synthetic_description = None

        pragma_match = re.match(r"\s*PRAGMA\s+table_info\(([^)]+)\)", sql, flags=re.IGNORECASE)
        if pragma_match:
            table = pragma_match.group(1).strip("'\"")
            self._cursor.execute(
                """
                select ordinal_position - 1 as cid,
                       column_name as name,
                       data_type as type,
                       case when is_nullable = 'NO' then 1 else 0 end as notnull,
                       column_default as dflt_value,
                       0 as pk
                from information_schema.columns
                where table_schema = 'public' and table_name = %s
                order by ordinal_position
                """,
                (table,),
            )
            rows = self._cursor.fetchall()
            self._synthetic_rows = [
                (r["cid"], r["name"], r["type"], r["notnull"], r["dflt_value"], r["pk"])
                for r in rows
            ]
            self.description = [("cid",), ("name",), ("type",), ("notnull",), ("dflt_value",), ("pk",)]
            return self

        sqlite_master_match = re.match(
            r"\s*SELECT\s+name\s+FROM\s+sqlite_master\s+WHERE\s+type='table'\s+AND\s+name='([^']+)'",
            sql,
            flags=re.IGNORECASE,
        )
        if sqlite_master_match:
            table = sqlite_master_match.group(1)
            self._cursor.execute(
                """
                select table_name as name
                from information_schema.tables
                where table_schema='public' and table_name=%s
                """,
                (table,),
            )
            rows = self._cursor.fetchall()
            self._synthetic_rows = [(r["name"],) for r in rows]
            self.description = [("name",)]
            return self

        translated = _translate_sql(sql)
        try:
            self._cursor.execute(translated, params)
            self.description = self._cursor.description
            if translated.lstrip().upper().startswith("INSERT"):
                try:
                    with self.conn._conn.cursor() as c:
                        c.execute("savepoint ruana_lastval_probe")
                        c.execute("select lastval()")
                        self.lastrowid = c.fetchone()["lastval"]
                except Exception:
                    try:
                        with self.conn._conn.cursor() as c:
                            c.execute("rollback to savepoint ruana_lastval_probe")
                            c.execute("release savepoint ruana_lastval_probe")
                    except Exception:
                        pass
                    self.lastrowid = None
                else:
                    try:
                        with self.conn._conn.cursor() as c:
                            c.execute("release savepoint ruana_lastval_probe")
                    except Exception:
                        pass
            return self
        except psycopg.IntegrityError as exc:
            raise sqlite3.IntegrityError(str(exc)) from exc

    def fetchone(self):
        if self._synthetic_rows is not None:
            if not self._synthetic_rows:
                return None
            return self._synthetic_rows.pop(0)
        row = self._cursor.fetchone()
        return self._wrap(row)

    def fetchall(self):
        if self._synthetic_rows is not None:
            rows = self._synthetic_rows
            self._synthetic_rows = []
            return rows
        return [self._wrap(row) for row in self._cursor.fetchall()]

    def _wrap(self, row):
        if row is None:
            return None
        if isinstance(row, dict):
            return CompatRow(row, list(row.keys()))
        return row

    def close(self):
        self._cursor.close()

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()


class PostgresCompatConnection:
    def __init__(self, database_url: str):
        self._conn = psycopg.connect(database_url, row_factory=dict_row, prepare_threshold=None)
        self.row_factory = None

    def cursor(self):
        return PostgresCompatCursor(self)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        self.close()


def connect(database_url: str) -> PostgresCompatConnection:
    return PostgresCompatConnection(database_url)
