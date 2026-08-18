"""Servicio de aprobaciones de acciones financieras sensibles (FASE 10)."""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from core.financial_security_authorization import (
    REFUND_AUTHORIZE,
    REFUND_EXECUTE,
    REFUND_REQUEST,
)
from core.repositories.financial_action_approval_repo import FinancialActionApprovalRepo
from core.services import financial_audit_service as audit

_repo = FinancialActionApprovalRepo()

ACTION_REFUND_EXECUTE = "REFUND_EXECUTE"
ACTION_LEDGER_ADJUST = "LEDGER_ADJUST"

_DEFAULT_TTL_HOURS = int(os.environ.get("RUANA_FINANCIAL_APPROVAL_TTL_HOURS", "72"))


def _allow_self_approval() -> bool:
    return os.environ.get("RUANA_FINANCIAL_ALLOW_SELF_APPROVAL", "0").strip().lower() in ("1", "true", "yes")


def _require_approval() -> bool:
    return os.environ.get("RUANA_FINANCIAL_REQUIRE_APPROVAL", "1").strip().lower() not in ("0", "false", "no")


def _expires_at(hours: int = _DEFAULT_TTL_HOURS) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).replace(microsecond=0).isoformat()


def solicitar_accion(
    db,
    *,
    action_type: str,
    contacto_id: Optional[int],
    actor: str,
    permiso: str,
    importe_cents: int,
    currency: str,
    motivo: str,
    idempotency_key: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    motivo = (motivo or "").strip()
    if len(motivo) < 5:
        return {"status": "error", "message": "motivo obligatorio (mín. 5 caracteres)"}
    key = (idempotency_key or "").strip()
    if not key:
        return {"status": "error", "message": "idempotency_key obligatoria"}
    if importe_cents <= 0 and action_type == ACTION_REFUND_EXECUTE:
        return {"status": "error", "message": "importe_cents debe ser > 0"}

    action_id = f"{action_type.lower()}-{contacto_id or 0}-{key}"

    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            _repo.marcar_expiradas(cursor)
            prev = _repo.select_por_action_id(cursor, action_id)
            if prev and prev.get("estado") in ("REQUESTED", "APPROVED"):
                return {
                    "status": "success",
                    "idempotent": True,
                    "approval_id": prev["id"],
                    "estado": prev["estado"],
                    "action_id": action_id,
                }
            row_id = _repo.insert(
                cursor,
                action_id=action_id,
                action_type=action_type,
                contacto_id=contacto_id,
                actor_solicitante=actor,
                importe_cents=importe_cents,
                currency=currency,
                motivo=motivo,
                idempotency_key=key,
                expires_at=_expires_at(),
                metadata_json=json.dumps(metadata or {}),
            )
            audit.registrar(
                db, cursor,
                actor=actor, permiso=permiso, accion="approval_requested",
                recurso_tipo=action_type, recurso_id=str(row_id),
                importe_cents=importe_cents, moneda=currency,
                idempotency_key=key, motivo=motivo,
            )
            conn.commit()
        finally:
            conn.close()
    return {"status": "success", "approval_id": row_id, "estado": "REQUESTED", "action_id": action_id}


def autorizar_accion(
    db,
    approval_id: int,
    *,
    actor: str,
    permiso: str,
    motivo: str = "",
) -> Dict[str, Any]:
    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            _repo.marcar_expiradas(cursor)
            row = _repo.select_por_id(cursor, approval_id)
            if not row:
                return {"status": "error", "message": "Aprobación no encontrada"}
            if row.get("estado") != "REQUESTED":
                return {"status": "error", "message": f"Estado inválido: {row.get('estado')}"}
            if row.get("actor_solicitante") == actor and not _allow_self_approval():
                return {
                    "status": "error",
                    "message": "El autorizador no puede ser el mismo solicitante",
                    "code": "separation_of_duties",
                }
            now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            ok = _repo.actualizar_estado_cas(
                cursor, int(row["id"]),
                estado_nuevo="APPROVED",
                version_esperada=int(row.get("version") or 1),
                actor_autorizador=actor,
                approved_at=now,
            )
            if not ok:
                return {"status": "error", "message": "Conflicto de versión", "code": "version_conflict"}
            audit.registrar(
                db, cursor,
                actor=actor, permiso=permiso, accion="approval_authorized",
                recurso_tipo=row.get("action_type") or "", recurso_id=str(approval_id),
                importe_cents=int(row.get("importe_cents") or 0),
                moneda=str(row.get("currency") or "eur"),
                motivo=motivo or row.get("motivo") or "",
                version=int(row.get("version") or 1),
            )
            conn.commit()
        finally:
            conn.close()
    return {"status": "success", "approval_id": approval_id, "estado": "APPROVED"}


def rechazar_accion(
    db,
    approval_id: int,
    *,
    actor: str,
    permiso: str,
    motivo: str,
) -> Dict[str, Any]:
    motivo = (motivo or "").strip()
    if len(motivo) < 5:
        return {"status": "error", "message": "motivo de rechazo obligatorio"}
    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            row = _repo.select_por_id(cursor, approval_id)
            if not row:
                return {"status": "error", "message": "Aprobación no encontrada"}
            if row.get("estado") != "REQUESTED":
                return {"status": "error", "message": f"Estado inválido: {row.get('estado')}"}
            ok = _repo.actualizar_estado_cas(
                cursor, int(row["id"]),
                estado_nuevo="REJECTED",
                version_esperada=int(row.get("version") or 1),
                actor_autorizador=actor,
            )
            if not ok:
                return {"status": "error", "code": "version_conflict", "message": "Conflicto de versión"}
            audit.registrar(
                db, cursor,
                actor=actor, permiso=permiso, accion="approval_rejected",
                recurso_tipo=row.get("action_type") or "", recurso_id=str(approval_id),
                motivo=motivo, resultado="rejected",
            )
            conn.commit()
        finally:
            conn.close()
    return {"status": "success", "approval_id": approval_id, "estado": "REJECTED"}


def consumir_aprobacion_para_ejecucion(
    db,
    approval_id: int,
    *,
    actor: str,
    action_type: str,
    contacto_id: Optional[int],
    importe_cents: int,
    currency: str,
) -> Dict[str, Any]:
    """Valida aprobación APPROVED y la marca EXECUTED (uso único)."""
    if not _require_approval():
        return {"status": "success", "skipped": True}

    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            _repo.marcar_expiradas(cursor)
            row = _repo.select_por_id(cursor, approval_id)
            if not row:
                return {"status": "error", "message": "Aprobación no encontrada"}
            if row.get("estado") == "EXECUTED":
                return {"status": "success", "idempotent": True, "approval_id": approval_id}
            if row.get("estado") != "APPROVED":
                return {"status": "error", "message": "Aprobación no autorizada", "estado": row.get("estado")}
            if row.get("action_type") != action_type:
                return {"status": "error", "message": "Tipo de acción no coincide"}
            if contacto_id is not None and int(row.get("contacto_id") or 0) != int(contacto_id):
                return {"status": "error", "message": "Contacto no coincide con aprobación", "code": "idor"}
            if int(row.get("importe_cents") or 0) != int(importe_cents):
                return {"status": "error", "message": "Importe no coincide con aprobación"}
            if str(row.get("currency") or "eur").lower() != str(currency or "eur").lower():
                return {"status": "error", "message": "Moneda no coincide con aprobación"}
            if row.get("actor_solicitante") == actor and not _allow_self_approval():
                return {
                    "status": "error",
                    "message": "Ejecutor no puede ser el solicitante sin excepción registrada",
                    "code": "separation_of_duties",
                }
            now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            ok = _repo.actualizar_estado_cas(
                cursor, int(row["id"]),
                estado_nuevo="EXECUTED",
                version_esperada=int(row.get("version") or 1),
                executed_at=now,
            )
            if not ok:
                return {"status": "error", "code": "version_conflict", "message": "Conflicto de versión"}
            audit.registrar(
                db, cursor,
                actor=actor, permiso=REFUND_EXECUTE, accion="approval_consumed",
                recurso_tipo=action_type, recurso_id=str(approval_id),
                importe_cents=importe_cents, moneda=currency,
            )
            conn.commit()
        finally:
            conn.close()
    return {"status": "success", "approval_id": approval_id}


def listar_pendientes(db, *, limit: int = 50) -> Dict[str, Any]:
    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            _repo.marcar_expiradas(cursor)
            items = _repo.listar_pendientes(cursor, limit=limit)
            conn.commit()
        finally:
            conn.close()
    return {"status": "success", "items": items}
