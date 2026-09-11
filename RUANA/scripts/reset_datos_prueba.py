#!/usr/bin/env python3
"""Vacía datos de prueba RUANA en Supabase Postgres (TRUNCATE CASCADE).

Modos:
  python RUANA/scripts/reset_datos_prueba.py --dry-run
  python RUANA/scripts/reset_datos_prueba.py --execute --confirm RESET-RUANA-PREPRODUCTION

Por defecto es --dry-run. No usa DELETE ni DROP. No toca la tabla migraciones.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import unquote, urlparse

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

CONFIRM_PHRASE = "RESET-RUANA-PREPRODUCTION"
TRUNCATE_SQL = "TRUNCATE aliados, grupos, cp_estado RESTART IDENTITY CASCADE;"
COUNT_TABLES = (
    "aliados",
    "grupos",
    "cp_estado",
    "contactos_ruana",
    "ruana_metodos_pago_manual",
    "migraciones",
)
WIPE_TABLES = frozenset({"aliados", "grupos", "cp_estado"})
KEEP_TABLES = frozenset({"ruana_metodos_pago_manual", "migraciones"})
FK_SQL = """
SELECT conname, confrelid::regclass
FROM pg_constraint
WHERE conrelid = 'ruana_metodos_pago_manual'::regclass AND contype = 'f';
""".strip()
CASCADE_SQL = """
SELECT DISTINCT conrelid::regclass::text AS tabla, confrelid::regclass::text AS referencia
FROM pg_constraint
WHERE contype = 'f'
  AND confrelid IN ('aliados'::regclass, 'grupos'::regclass, 'cp_estado'::regclass)
ORDER BY 1, 2;
""".strip()
_FORBIDDEN_WRITE = re.compile(r"\b(DELETE|DROP)\b", re.IGNORECASE)


class ResetAborted(RuntimeError):
    """Error controlado: no se modifica la base."""


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def redact_database_url(url: str) -> str:
    """Oculta contraseña/tokens de una URL de conexión."""
    if not url:
        return ""
    return re.sub(r":([^:@/]+)@", r":***@", url)


def parse_database_identity(url: str) -> Dict[str, str]:
    parsed = urlparse(url)
    dbname = unquote((parsed.path or "").lstrip("/") or "")
    return {
        "host": parsed.hostname or "",
        "port": str(parsed.port or ""),
        "database": dbname.split("?")[0],
        "user": unquote(parsed.username or ""),
    }


def database_fingerprint(url: str) -> str:
    ident = parse_database_identity(url)
    payload = "|".join(ident[k] for k in ("host", "port", "database", "user"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def dry_run_flag_path(url: str) -> Path:
    return Path(tempfile.gettempdir()) / f"ruana_reset_datos_prueba_dryrun_{os.getuid()}_{database_fingerprint(url)}"


def write_dry_run_flag(url: str) -> Path:
    path = dry_run_flag_path(url)
    payload = {
        "fingerprint": database_fingerprint(url),
        "host": parse_database_identity(url)["host"],
        "database": parse_database_identity(url)["database"],
        "written_at": datetime.now(timezone.utc).isoformat(),
        "pid": os.getpid(),
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


def require_prior_dry_run(url: str) -> Path:
    path = dry_run_flag_path(url)
    if not path.is_file():
        raise ResetAborted(
            "EXECUTE abortado: no hay --dry-run previo en esta sesión para esta base. "
            "Ejecuta primero: python RUANA/scripts/reset_datos_prueba.py --dry-run"
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResetAborted(f"EXECUTE abortado: flag de dry-run ilegible ({exc}).") from exc
    if payload.get("fingerprint") != database_fingerprint(url):
        raise ResetAborted(
            "EXECUTE abortado: el --dry-run previo apunta a otra base de datos."
        )
    return path


def assert_safe_sql(sql: str) -> None:
    if sql.strip() != TRUNCATE_SQL.strip():
        raise ResetAborted("SQL de escritura no autorizado: solo se permite el TRUNCATE fijo.")
    if _FORBIDDEN_WRITE.search(sql):
        raise ResetAborted("Prohibido DELETE/DROP. Abortando.")


def _regclass_name(value: Any) -> str:
    text = str(value or "").strip().strip('"')
    if "." in text:
        text = text.split(".")[-1]
    return text.strip('"')


def fk_references_aliados(rows: Sequence[Sequence[Any]]) -> List[Tuple[str, str]]:
    hits: List[Tuple[str, str]] = []
    for row in rows:
        conname = str(row[0])
        target = _regclass_name(row[1])
        if target == "aliados":
            hits.append((conname, str(row[1])))
    return hits


def connect(database_url: str, *, autocommit: bool):
    try:
        import psycopg
    except ImportError as exc:
        raise ResetAborted(
            "Falta el paquete psycopg. Instálalo con: pip install 'psycopg[binary]'"
        ) from exc
    return psycopg.connect(database_url, autocommit=autocommit, prepare_threshold=None)


def fetch_fk_rows(cur) -> List[Tuple[Any, ...]]:
    cur.execute(FK_SQL)
    return [tuple(row) for row in cur.fetchall()]


def fetch_cascade_rows(cur) -> List[Tuple[str, str]]:
    cur.execute(CASCADE_SQL)
    return [(_regclass_name(row[0]), _regclass_name(row[1])) for row in cur.fetchall()]


def fetch_counts(cur, tables: Iterable[str] = COUNT_TABLES) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for table in tables:
        if not re.fullmatch(r"[a-z_]+", table):
            raise ResetAborted(f"Nombre de tabla no permitido: {table}")
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        row = cur.fetchone()
        counts[table] = int(row[0])
    return counts


def project_counts_after(
    counts_before: Mapping[str, int],
    cascade_tables: Iterable[str],
) -> Dict[str, int]:
    affected = set(WIPE_TABLES)
    affected.update(cascade_tables)
    projected: Dict[str, int] = {}
    for table, n in counts_before.items():
        if table in KEEP_TABLES:
            projected[table] = n
        elif table in affected:
            projected[table] = 0
        else:
            projected[table] = n
    return projected


def backup_filename(stamp: Optional[str] = None) -> str:
    return f"backup_pre_reset_{stamp or _utc_stamp()}.dump"


def run_pg_dump(database_url: str, dest: Path) -> int:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    pg_dump = os.environ.get("PG_DUMP_BIN") or "pg_dump"
    try:
        completed = subprocess.run(
            [pg_dump, "--format=custom", "-d", database_url, "-f", str(dest)],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise ResetAborted(
            "pg_dump no está instalado. Instala postgresql-client antes de --execute."
        ) from exc
    if completed.returncode != 0:
        err = (completed.stderr or completed.stdout or "").strip()
        err = redact_database_url(err)
        raise ResetAborted(f"pg_dump falló (código {completed.returncode}): {err}")
    if not dest.is_file() or dest.stat().st_size <= 0:
        raise ResetAborted(
            f"Backup inválido: {dest} no existe o pesa 0 bytes. Abortando sin TRUNCATE."
        )
    return dest.stat().st_size


def print_section(title: str) -> None:
    print()
    print(f"== {title} ==")


def print_counts(label: str, counts: Mapping[str, int]) -> None:
    print(f"{label}:")
    for table in COUNT_TABLES:
        print(f"  {table}: {counts.get(table, 0)}")


def print_report(
    *,
    mode: str,
    database_url: str,
    fk_rows: Sequence[Sequence[Any]],
    cascade_rows: Sequence[Sequence[str]],
    counts_before: Mapping[str, int],
    backup_path: str,
    backup_status: str,
    truncate_status: str,
    counts_after: Mapping[str, int],
    commit_status: str,
) -> None:
    ident = parse_database_identity(database_url)
    print("=== RUANA reset datos de prueba ===")
    print(f"modo: {mode}")
    print(f"DATABASE_URL: {redact_database_url(database_url)}")
    print(f"host: {ident['host']}")
    print(f"port: {ident['port'] or '(default)'}")
    print(f"database: {ident['database']}")
    print(f"user: {ident['user']}")
    print()
    print("SQL de comprobación FK:")
    print(FK_SQL)
    print("resultado FK ruana_metodos_pago_manual:")
    if not fk_rows:
        print("  (ninguna FK)")
    else:
        for conname, confrelid in fk_rows:
            print(f"  conname={conname} confrelid={confrelid}")
    print()
    print("tablas que TRUNCATE ... CASCADE vaciaría (FK hacia aliados/grupos/cp_estado):")
    if not cascade_rows:
        print("  (ninguna además de las nombradas)")
    else:
        for tabla, ref in cascade_rows:
            print(f"  {tabla} → {ref}")
    print()
    print_counts("conteos_antes", counts_before)
    print()
    print("[backup]")
    print(f"  ruta: {backup_path}")
    print(f"  estado: {backup_status}")
    print()
    print("[truncate]")
    print(f"  sql: {TRUNCATE_SQL}")
    print(f"  estado: {truncate_status}")
    print()
    print_counts("conteos_despues", counts_after)
    print()
    print(f"transaccion: {commit_status}")
    print("tablas_conservadas_esperadas: migraciones, ruana_metodos_pago_manual")
    print("tablas_objetivo_cero: aliados, grupos, cp_estado")


def load_database_url() -> str:
    from core.settings import get_settings

    url = (get_settings().database_url or os.environ.get("DATABASE_URL") or "").strip()
    if not url:
        raise ResetAborted(
            "DATABASE_URL no está configurada. Define la variable o un .env.local."
        )
    return url


def inspect(database_url: str) -> Tuple[List[Tuple[Any, ...]], List[Tuple[str, str]], Dict[str, int]]:
    with connect(database_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            fk_rows = fetch_fk_rows(cur)
            cascade_rows = fetch_cascade_rows(cur)
            counts = fetch_counts(cur)
    return fk_rows, cascade_rows, counts


def abort_if_metodos_pago_fk_aliados(fk_rows: Sequence[Sequence[Any]]) -> None:
    hits = fk_references_aliados(fk_rows)
    if not hits:
        return
    detalle = ", ".join(f"{name} → {target}" for name, target in hits)
    raise ResetAborted(
        "ABORTADO: ruana_metodos_pago_manual tiene FK hacia aliados "
        f"({detalle}). TRUNCATE aliados ... CASCADE vaciaría "
        "ruana_metodos_pago_manual (IBAN/Bizum). No se continúa. "
        "Quita esa FK o pide confirmación explícita adicional antes de reintentar."
    )


def execute_truncate(database_url: str, counts_before: Mapping[str, int]) -> Dict[str, int]:
    assert_safe_sql(TRUNCATE_SQL)
    with connect(database_url, autocommit=False) as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(TRUNCATE_SQL)
                counts_after = fetch_counts(cur)
                keep_ok = all(
                    counts_after.get(table) == counts_before.get(table)
                    for table in KEEP_TABLES
                )
                wipe_ok = all(counts_after.get(table) == 0 for table in WIPE_TABLES)
                keep_dropped = any(
                    counts_after.get(table, 0) == 0 and (counts_before.get(table, 0) or 0) > 0
                    for table in KEEP_TABLES
                )
                if (not keep_ok) or keep_dropped or (not wipe_ok):
                    conn.rollback()
                    raise ResetAborted(
                        "ROLLBACK: conteos posteriores no cuadran. "
                        f"antes={dict(counts_before)} despues={counts_after}. "
                        "migraciones y ruana_metodos_pago_manual deben permanecer; "
                        "aliados, grupos y cp_estado deben quedar en 0."
                    )
            conn.commit()
            return counts_after
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Vacía datos de prueba RUANA (TRUNCATE aliados/grupos/cp_estado CASCADE)."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="No modifica nada (por defecto).")
    mode.add_argument("--execute", action="store_true", help="Ejecuta TRUNCATE tras backup.")
    parser.add_argument(
        "--confirm",
        default="",
        help=f"Debe ser exactamente {CONFIRM_PHRASE} junto con --execute.",
    )
    parser.add_argument(
        "--backup-dir",
        default="",
        help="Directorio del pg_dump en --execute (default: directorio de trabajo).",
    )
    args = parser.parse_args(argv)
    args.dry_run = bool(args.dry_run) or not args.execute
    return args


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    execute = bool(args.execute)
    if execute and args.confirm != CONFIRM_PHRASE:
        print(
            "EXECUTE abortado: se requiere --confirm "
            f"{CONFIRM_PHRASE} (exacto).",
            file=sys.stderr,
        )
        return 2

    try:
        database_url = load_database_url()
        if execute:
            require_prior_dry_run(database_url)

        fk_rows, cascade_rows, counts_before = inspect(database_url)
        abort_if_metodos_pago_fk_aliados(fk_rows)

        stamp = _utc_stamp()
        backup_dir = Path(args.backup_dir).expanduser() if args.backup_dir else Path.cwd()
        backup_path = backup_dir / backup_filename(stamp)
        cascade_table_names = [row[0] for row in cascade_rows]

        if execute:
            size = run_pg_dump(database_url, backup_path)
            backup_status = f"CREADO ({size} bytes)"
            counts_after = execute_truncate(database_url, counts_before)
            truncate_status = "EJECUTADO"
            commit_status = "COMMIT"
            mode = "EXECUTE"
        else:
            write_dry_run_flag(database_url)
            backup_status = "OMITIDO (dry-run; se crearía en --execute)"
            counts_after = project_counts_after(counts_before, cascade_table_names)
            truncate_status = "OMITIDO (dry-run; no se ejecutó TRUNCATE)"
            commit_status = "OMITIDO (dry-run; no hay transacción de escritura)"
            mode = "DRY-RUN"

        print_report(
            mode=mode,
            database_url=database_url,
            fk_rows=fk_rows,
            cascade_rows=cascade_rows,
            counts_before=counts_before,
            backup_path=str(backup_path.resolve()),
            backup_status=backup_status,
            truncate_status=truncate_status,
            counts_after=counts_after,
            commit_status=commit_status,
        )
        if execute:
            print()
            print("resumen_final:")
            print(f"  truncado: {TRUNCATE_SQL}")
            print(f"  backup: {backup_path.resolve()}")
            print(f"  backup_estado: {backup_status}")
            print_counts("  conteos_antes", counts_before)
            print_counts("  conteos_despues", counts_after)
        else:
            print()
            print("dry-run_ok: flag de sesión guardado. --execute exigirá este dry-run.")
        return 0
    except ResetAborted as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
