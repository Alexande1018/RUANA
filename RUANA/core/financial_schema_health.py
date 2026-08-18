"""Verificación de esquema financiero completo (FASE 13A P0-5)."""
from __future__ import annotations

from typing import Any, Dict, List

REQUIRED_FINANCIAL_TABLES: tuple[str, ...] = (
    "payment_conflicts",
    "financial_transfers",
    "financial_refunds",
    "financial_disputes",
    "financial_reconciliation_executions",
    "ledger_transactions",
    "ledger_entries",
    "financial_alerts",
    "financial_job_leases",
    "financial_action_approvals",
    "financial_audit_log",
)


def _es_postgres(cursor) -> bool:
    module = type(cursor).__module__ or ""
    if "psycopg" in module:
        return True
    try:
        cursor.execute("SELECT 1 FROM information_schema.tables LIMIT 1")
        cursor.fetchone()
        return True
    except Exception:
        return False


def tabla_existe(cursor, nombre: str) -> bool:
    if _es_postgres(cursor):
        cursor.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = %s LIMIT 1",
            (nombre,),
        )
        return cursor.fetchone() is not None
    cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (nombre,),
    )
    return cursor.fetchone() is not None


def verificar_esquema_financiero(cursor) -> Dict[str, Any]:
    faltantes: List[str] = []
    presentes: List[str] = []
    for t in REQUIRED_FINANCIAL_TABLES:
        if tabla_existe(cursor, t):
            presentes.append(t)
        else:
            faltantes.append(t)
    return {
        "status": "success" if not faltantes else "error",
        "ok": not faltantes,
        "tablas_requeridas": list(REQUIRED_FINANCIAL_TABLES),
        "presentes": presentes,
        "faltantes": faltantes,
    }


def assert_esquema_financiero_completo(cursor) -> None:
    r = verificar_esquema_financiero(cursor)
    if not r.get("ok"):
        raise RuntimeError(
            "Esquema financiero incompleto. Tablas faltantes: "
            + ", ".join(r.get("faltantes") or [])
        )
