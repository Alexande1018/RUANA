"""Repositorio de aprobaciones de acciones financieras (FASE 10)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class FinancialActionApprovalRepo:
    ESTADOS_TERMINALES = frozenset({"REJECTED", "EXPIRED", "EXECUTED", "CANCELED"})

    def select_por_id(self, cursor, action_id: int) -> Optional[Dict[str, Any]]:
        cursor.execute("SELECT * FROM financial_action_approvals WHERE id = ?", (action_id,))
        row = cursor.fetchone()
        return self._row(row, cursor)

    def select_por_action_id(self, cursor, action_key: str) -> Optional[Dict[str, Any]]:
        cursor.execute(
            "SELECT * FROM financial_action_approvals WHERE action_id = ? ORDER BY id DESC LIMIT 1",
            (action_key,),
        )
        row = cursor.fetchone()
        return self._row(row, cursor)

    def insert(
        self,
        cursor,
        *,
        action_id: str,
        action_type: str,
        contacto_id: Optional[int],
        actor_solicitante: str,
        importe_cents: int,
        currency: str,
        motivo: str,
        idempotency_key: str,
        expires_at: str,
        metadata_json: str = "",
        version: int = 1,
    ) -> int:
        cursor.execute(
            """
            INSERT INTO financial_action_approvals (
                action_id, action_type, contacto_id, actor_solicitante,
                importe_cents, currency, motivo, estado, version,
                idempotency_key, expires_at, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'REQUESTED', ?, ?, ?, ?)
            """,
            (
                action_id, action_type, contacto_id, actor_solicitante,
                importe_cents, currency, motivo, version,
                idempotency_key, expires_at, metadata_json,
            ),
        )
        return int(cursor.lastrowid or 0)

    def actualizar_estado_cas(
        self,
        cursor,
        row_id: int,
        *,
        estado_nuevo: str,
        version_esperada: int,
        actor_autorizador: str = "",
        approved_at: Optional[str] = None,
        executed_at: Optional[str] = None,
    ) -> bool:
        cursor.execute(
            """
            UPDATE financial_action_approvals
            SET estado = ?, version = version + 1,
                actor_autorizador = COALESCE(NULLIF(?, ''), actor_autorizador),
                approved_at = COALESCE(?, approved_at),
                executed_at = COALESCE(?, executed_at),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND version = ? AND estado NOT IN ('EXECUTED','REJECTED','EXPIRED','CANCELED')
            """,
            (estado_nuevo, actor_autorizador, approved_at, executed_at, row_id, version_esperada),
        )
        return cursor.rowcount == 1

    def marcar_expiradas(self, cursor) -> int:
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        cursor.execute(
            """
            UPDATE financial_action_approvals
            SET estado = 'EXPIRED', version = version + 1, updated_at = CURRENT_TIMESTAMP
            WHERE estado IN ('REQUESTED', 'APPROVED')
              AND expires_at IS NOT NULL AND expires_at < ?
            """,
            (now,),
        )
        return int(cursor.rowcount or 0)

    def listar_pendientes(self, cursor, *, limit: int = 50) -> List[Dict[str, Any]]:
        cursor.execute(
            """
            SELECT * FROM financial_action_approvals
            WHERE estado IN ('REQUESTED', 'APPROVED')
            ORDER BY id DESC LIMIT ?
            """,
            (max(1, min(limit, 200)),),
        )
        return [self._row(r, cursor) for r in cursor.fetchall() if r]

    def _row(self, row, cursor) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        if hasattr(row, "keys"):
            return dict(row)
        names = [c[0] for c in cursor.description]
        return {names[i]: row[i] for i in range(len(row))}
