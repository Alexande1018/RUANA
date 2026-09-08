"""Regresión: registro de aliado no debe abortar la transacción Postgres.

Al crear el primer grupo del CP se consultaba unicidad con COLLATE NOCASE
(SQLite). En Postgres esa collation no existe: la sentencia falla, la
transacción queda abortada y el INSERT de aliados responde
"current transaction is aborted, commands ignored until end of transaction block".
"""
from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock

import psycopg
import pytest

from core.postgres_compat import PostgresCompatCursor, _translate_sql
from core.repositories.grupo_repo import GrupoRepo


def _compat_cursor():
    conn = MagicMock()
    conn._conn = MagicMock()
    inner = MagicMock()
    conn._conn.cursor.return_value = inner
    return PostgresCompatCursor(conn), inner


def test_translate_sql_strips_collate_nocase_de_existe_nombre():
    sql = "SELECT 1 FROM grupos WHERE TRIM(nombre) = ? COLLATE NOCASE LIMIT 1"
    translated = _translate_sql(sql)
    assert "NOCASE" not in translated.upper()
    assert "COLLATE" not in translated.upper()
    assert "%s" in translated


def test_translate_sql_strips_collate_nocase_en_indice_unico():
    sql = "CREATE UNIQUE INDEX IF NOT EXISTS idx_grupos_nombre_unique ON grupos(nombre COLLATE NOCASE)"
    translated = _translate_sql(sql)
    assert "NOCASE" not in translated.upper()
    assert "COLLATE" not in translated.upper()


def test_grupo_repo_existe_nombre_sql_sin_collate_nocase():
    cur, inner = _compat_cursor()
    inner.fetchone.return_value = None
    assert GrupoRepo().existe_nombre(cur, "RUANA-ABC12345-PUENTE") is False
    sent = inner.execute.call_args[0][0]
    assert "NOCASE" not in sent.upper()
    assert "LOWER" in sent.upper()


def test_sentencia_fallida_hace_rollback_de_savepoint():
    cur, inner = _compat_cursor()
    inner.execute.side_effect = RuntimeError('collation "nocase" for encoding "UTF8" does not exist')

    with pytest.raises(RuntimeError, match="collation"):
        cur.execute(
            "SELECT 1 FROM grupos WHERE TRIM(nombre) = ? COLLATE NOCASE LIMIT 1",
            ("RUANA-X",),
        )

    raw_sqls = [str(c[0][0]) for c in cur.conn._conn.execute.call_args_list]
    assert any(s.upper().startswith("SAVEPOINT ") for s in raw_sqls)
    assert any("ROLLBACK TO SAVEPOINT" in s.upper() for s in raw_sqls)


def test_tras_error_la_siguiente_sentencia_sigue_en_la_transaccion():
    """Emula el flujo registro: falla unicidad de grupo, luego INSERT aliados."""
    cur, inner = _compat_cursor()
    inner.execute.side_effect = [
        RuntimeError('collation "nocase" for encoding "UTF8" does not exist'),
        None,
    ]

    with pytest.raises(RuntimeError):
        cur.execute(
            "SELECT 1 FROM grupos WHERE TRIM(nombre) = ? COLLATE NOCASE LIMIT 1",
            ("RUANA-X",),
        )

    inner.execute.side_effect = None
    inner.execute.return_value = None
    inner.description = None
    # No debe exigir rollback total: el savepoint ya recuperó la transacción.
    result = cur.execute(
        "INSERT INTO aliados (codigo, nombre, marca, oficio, codigo_postal, email, telefono, estado, score, descripcion_servicio) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("12345", "Ana", "", "Electricidad", "03001", "ana@example.com", "600000000", "activo", 50, None),
    )
    assert result is cur
    insert_calls = [
        c[0][0]
        for c in inner.execute.call_args_list
        if "INSERT INTO ALIADOS" in str(c[0][0]).upper()
    ]
    assert insert_calls


def test_integrity_error_se_convierte_a_sqlite_tras_savepoint():
    cur, inner = _compat_cursor()
    inner.execute.side_effect = psycopg.IntegrityError("duplicate key")

    with pytest.raises(sqlite3.IntegrityError, match="duplicate key"):
        cur.execute("INSERT INTO grupos (nombre) VALUES (?)", ("RUANA-DUP",))

    raw_sqls = [str(c[0][0]) for c in cur.conn._conn.execute.call_args_list]
    assert any("ROLLBACK TO SAVEPOINT" in s.upper() for s in raw_sqls)
