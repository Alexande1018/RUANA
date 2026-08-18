"""Auditoría append-only de acciones financieras sensibles (FASE 10)."""
from __future__ import annotations

import json
import uuid
from typing import Any, Dict, Optional


def registrar(
    db,
    cursor,
    *,
    actor: str,
    permiso: str,
    accion: str,
    recurso_tipo: str,
    recurso_id: str,
    resultado: str = "success",
    importe_cents: Optional[int] = None,
    moneda: str = "eur",
    version: Optional[int] = None,
    idempotency_key: str = "",
    motivo: str = "",
    error_sanitizado: str = "",
    metadata: Optional[Dict[str, Any]] = None,
    request_id: str = "",
) -> int:
    rid = (request_id or str(uuid.uuid4())[:12]).strip()
    meta = json.dumps(metadata or {}, ensure_ascii=False)
    cursor.execute(
        """
        INSERT INTO financial_audit_log (
            request_id, actor_codigo, permiso_usado, rol_capacidad, accion,
            recurso_tipo, recurso_id, importe_cents, moneda, version_recursos,
            idempotency_key, motivo, resultado, error_sanitizado, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            rid, actor or "sistema", permiso or "", "",
            accion, recurso_tipo, str(recurso_id),
            importe_cents, moneda, version,
            idempotency_key, motivo, resultado, error_sanitizado[:500], meta,
        ),
    )
    return int(cursor.lastrowid or 0)
