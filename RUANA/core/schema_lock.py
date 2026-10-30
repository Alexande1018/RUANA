"""Serializa el init/migración de esquema Postgres entre instancias y workers.

Problema (29 oct 2026): varias instancias de Cloud Run (y varios workers de
gunicorn por instancia) ejecutaban a la vez ``_init_postgres_schema`` y Postgres
abortaba con deadlocks (también en ``payment_conflicts``).

Solución: antes de migrar, cada proceso abre una conexión DEDICADA (fuera del
pool) y toma un advisory lock de clave fija. Se usa el lock de TRANSACCIÓN
(``pg_try_advisory_xact_lock``) y no el de sesión porque la ``DATABASE_URL`` de
producción apunta al pooler de Supabase (puerto 6543, modo transacción): ahí un
lock de sesión puede quedarse “huérfano” en una conexión de servidor ajena. Con
la transacción abierta, pgbouncer fija la conexión de servidor, y el lock se
libera solo al hacer commit/rollback o si el proceso muere (se cae la conexión).

Si el proceso tuvo que ESPERAR y, mientras esperaba, otro proceso con la misma
versión de esquema terminó la migración, se omite (no-op idempotente). Si no
hubo espera, la migración se ejecuta como siempre (mismo comportamiento que
antes en cada arranque en frío).

Si no se puede abrir la conexión del lock o se agota la espera, se registra un
aviso y se ejecuta la migración igualmente (comportamiento anterior): nunca se
deja una instancia sin esquema por culpa del lock.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Callable, Optional

_logger = logging.getLogger("ruana.db.schema_lock")

# Clave fija (bigint) del advisory lock de init de esquema RUANA. No cambiar:
# todas las revisiones desplegadas deben competir por la misma clave.
SCHEMA_INIT_LOCK_KEY = 7_726_002_910_290_001

MARKER_TABLE = "ruana_schema_init_marker"


def _lock_timeout_s() -> float:
    try:
        return max(0.0, float(os.environ.get("RUANA_SCHEMA_LOCK_TIMEOUT_S", "25")))
    except ValueError:
        return 25.0


def _lock_poll_s() -> float:
    try:
        return max(0.05, float(os.environ.get("RUANA_SCHEMA_LOCK_POLL_S", "0.5")))
    except ValueError:
        return 0.5


def _idle_in_tx_timeout() -> str:
    # La conexión del lock queda "idle in transaction" mientras se migra por otra
    # conexión. Tope para que un proceso colgado no retenga el lock para siempre.
    return os.environ.get("RUANA_SCHEMA_LOCK_IDLE_TX_TIMEOUT", "10min")


def schema_version(paths: Optional[list[Path]] = None) -> str:
    """Huella del código de migraciones: cambia si cambia schema_service."""
    if paths is None:
        base = Path(__file__).resolve().parent
        paths = [base / "services" / "schema_service.py"]
    h = hashlib.sha256()
    for p in paths:
        try:
            h.update(Path(p).read_bytes())
        except OSError:
            h.update(str(p).encode())
    return h.hexdigest()[:16]


def _log(event: str, level: int = logging.INFO, **extra: Any) -> None:
    payload = {"component": "postgres_schema_lock", "event": event, "pid": os.getpid(), **extra}
    line = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
    try:
        _logger.log(level, line)
    except Exception:
        pass
    print(f"[RUANA][DB] {line}")


def _default_connect(database_url: str):
    import psycopg

    return psycopg.connect(database_url, autocommit=False, prepare_threshold=None)


def run_with_schema_lock(
    database_url: str,
    migrate: Callable[[], Any],
    *,
    version: Optional[str] = None,
    timeout_s: Optional[float] = None,
    poll_s: Optional[float] = None,
    connect: Optional[Callable[[str], Any]] = None,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> str:
    """Ejecuta ``migrate()`` con el advisory lock de esquema.

    ``migrate`` debe devolver True si la migración terminó bien (solo entonces
    se graba la marca que permite a los que esperaban omitirla).

    Devuelve el resultado: ``"migrated"``, ``"skipped"``,
    ``"migrated_without_lock"`` o ``"failed"``.
    """
    version = version or schema_version()
    timeout_s = _lock_timeout_s() if timeout_s is None else timeout_s
    poll_s = _lock_poll_s() if poll_s is None else poll_s

    connect = connect or _default_connect
    try:
        lock_conn = connect(database_url)
    except Exception as exc:  # sin conexión de lock → comportamiento anterior
        _log("schema_lock_connect_failed", logging.WARNING, error=str(exc)[:300])
        ok = migrate()
        return "migrated_without_lock" if ok else "failed"

    acquired = False
    migrate_called = False
    try:
        cur = lock_conn.cursor()
        try:
            cur.execute(
                "SELECT set_config('idle_in_transaction_session_timeout', %s, true)",
                (_idle_in_tx_timeout(),),
            )
        except Exception as exc:
            _log("schema_lock_set_timeout_failed", logging.WARNING, error=str(exc)[:300])
        cur.execute("SELECT now()")
        tx_start = _first(cur.fetchone())

        start = monotonic()
        waited = False
        while True:
            cur.execute("SELECT pg_try_advisory_xact_lock(%s)", (SCHEMA_INIT_LOCK_KEY,))
            if bool(_first(cur.fetchone())):
                acquired = True
                break
            if not waited:
                _log("schema_lock_waiting", key=SCHEMA_INIT_LOCK_KEY)
            waited = True
            if monotonic() - start >= timeout_s:
                break
            sleep(poll_s)

        waited_s = round(monotonic() - start, 3)
        if not acquired:
            _log("schema_lock_timeout", logging.WARNING, waited_s=waited_s)
            _safe_rollback(lock_conn)
            migrate_called = True
            ok = migrate()
            return "migrated_without_lock" if ok else "failed"

        _log("schema_lock_acquired", waited=waited, waited_s=waited_s, version=version)
        cur.execute(
            f"CREATE TABLE IF NOT EXISTS {MARKER_TABLE} ("
            " id INTEGER PRIMARY KEY,"
            " version TEXT NOT NULL,"
            " completed_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )

        if waited:
            cur.execute(
                f"SELECT 1 FROM {MARKER_TABLE} WHERE id = 1 AND version = %s AND completed_at >= %s",
                (version, tx_start),
            )
            if cur.fetchone() is not None:
                _log("schema_init_skipped", reason="otra_instancia_acaba_de_migrar", version=version)
                lock_conn.commit()  # libera el lock
                return "skipped"

        migrate_called = True
        ok = bool(migrate())
        if ok:
            cur.execute(
                f"INSERT INTO {MARKER_TABLE} (id, version, completed_at) VALUES (1, %s, clock_timestamp()) "
                "ON CONFLICT (id) DO UPDATE SET version = EXCLUDED.version, completed_at = EXCLUDED.completed_at",
                (version,),
            )
        lock_conn.commit()  # libera el lock (xact)
        _log("schema_lock_released", ok=ok)
        return "migrated" if ok else "failed"
    except Exception as exc:
        _log("schema_lock_error", logging.WARNING, error=str(exc)[:300], acquired=acquired)
        _safe_rollback(lock_conn)
        if migrate_called:
            # migrate() ya se ejecutó (falló el marcador/commit): no repetir.
            return "failed"
        ok = migrate()
        return "migrated_without_lock" if ok else "failed"
    finally:
        try:
            lock_conn.close()  # cerrar la conexión también libera el lock
        except Exception:
            pass


def _first(row: Any) -> Any:
    if row is None:
        return None
    if isinstance(row, dict):
        return next(iter(row.values()), None)
    return row[0]


def _safe_rollback(conn: Any) -> None:
    try:
        conn.rollback()
    except Exception:
        pass
