"""Repositorio de disputas Stripe formales (FASE 06)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


class FinancialDisputeRepo:
    def tabla_existe(self, cursor) -> bool:
        cursor.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='financial_disputes' LIMIT 1"
        )
        return cursor.fetchone() is not None

    def reclamar_disputa(
        self,
        cursor,
        *,
        contacto_id: int,
        stripe_dispute_id: str,
        charge_id: str,
        payment_intent_id: str,
        amount_cents: int,
        currency: str,
        reason: str,
        status_stripe: str,
        evidence_due_by: Optional[str],
        network_reason_code: str = "",
        balance_transaction_id: str = "",
        idempotency_key: str,
        estado_financiero_historico: str = "",
        metadata: Optional[Dict] = None,
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        cursor.execute(
            """
            INSERT OR IGNORE INTO financial_disputes (
                contacto_id, stripe_dispute_id, charge_id, payment_intent_id,
                amount_cents, currency, reason, status_stripe, estado_interno,
                evidence_due_by, network_reason_code, balance_transaction_id,
                idempotency_key, bloqueo_financiero, estado_financiero_historico, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ABIERTO', ?, ?, ?, ?, 1, ?, ?)
            """,
            (
                contacto_id, stripe_dispute_id, charge_id or None, payment_intent_id or None,
                amount_cents, currency, reason or None, status_stripe or None,
                evidence_due_by, network_reason_code or None, balance_transaction_id or None,
                idempotency_key, estado_financiero_historico or None,
                json.dumps(metadata or {}, ensure_ascii=False),
            ),
        )
        if cursor.rowcount > 0:
            return "claimed", self.select_por_stripe_dispute_id(cursor, stripe_dispute_id)
        return "existing", self.select_por_stripe_dispute_id(cursor, stripe_dispute_id)

    def select_por_id(self, cursor, dispute_id: int) -> Optional[Dict[str, Any]]:
        cursor.execute("SELECT * FROM financial_disputes WHERE id = ?", (dispute_id,))
        row = cursor.fetchone()
        return self._row_dict(row, cursor) if row else None

    def select_por_stripe_dispute_id(self, cursor, stripe_dispute_id: str) -> Optional[Dict[str, Any]]:
        cursor.execute(
            "SELECT * FROM financial_disputes WHERE stripe_dispute_id = ?", (stripe_dispute_id,),
        )
        row = cursor.fetchone()
        return self._row_dict(row, cursor) if row else None

    def select_por_idempotency_key(self, cursor, key: str) -> Optional[Dict[str, Any]]:
        cursor.execute("SELECT * FROM financial_disputes WHERE idempotency_key = ?", (key,))
        row = cursor.fetchone()
        return self._row_dict(row, cursor) if row else None

    def tiene_disputa_bloqueante(self, cursor, contacto_id: int) -> bool:
        if not self.tabla_existe(cursor):
            return False
        cursor.execute(
            """
            SELECT 1 FROM financial_disputes
            WHERE contacto_id = ? AND bloqueo_financiero = 1
              AND estado_interno NOT IN ('GANADA', 'PERDIDA', 'CERRADA')
            LIMIT 1
            """,
            (contacto_id,),
        )
        return cursor.fetchone() is not None

    def listar_por_contacto(self, cursor, contacto_id: int) -> List[Dict[str, Any]]:
        cursor.execute(
            "SELECT * FROM financial_disputes WHERE contacto_id = ? ORDER BY id ASC",
            (contacto_id,),
        )
        return [self._row_dict(r, cursor) for r in cursor.fetchall()]

    def actualizar_snapshot_stripe(
        self,
        cursor,
        dispute_id: int,
        *,
        status_stripe: str = "",
        reason: str = "",
        evidence_due_by: Optional[str] = None,
        has_evidence: Optional[bool] = None,
        evidence_submitted: Optional[bool] = None,
        network_reason_code: str = "",
        balance_transaction_id: str = "",
        funds_withdrawn_cents: Optional[int] = None,
        funds_reinstated_cents: Optional[int] = None,
    ) -> bool:
        sets = ["actualizado_en = CURRENT_TIMESTAMP"]
        params: list = []
        if status_stripe:
            sets.append("status_stripe = ?")
            params.append(status_stripe)
        if reason:
            sets.append("reason = ?")
            params.append(reason)
        if evidence_due_by is not None:
            sets.append("evidence_due_by = ?")
            params.append(evidence_due_by)
        if has_evidence is not None:
            sets.append("has_evidence = ?")
            params.append(1 if has_evidence else 0)
        if evidence_submitted is not None:
            sets.append("evidence_submitted = ?")
            params.append(1 if evidence_submitted else 0)
        if network_reason_code:
            sets.append("network_reason_code = ?")
            params.append(network_reason_code)
        if balance_transaction_id:
            sets.append("balance_transaction_id = ?")
            params.append(balance_transaction_id)
        if funds_withdrawn_cents is not None:
            sets.append("funds_withdrawn_cents = ?")
            params.append(funds_withdrawn_cents)
        if funds_reinstated_cents is not None:
            sets.append("funds_reinstated_cents = ?")
            params.append(funds_reinstated_cents)
        params.append(dispute_id)
        cursor.execute(
            f"UPDATE financial_disputes SET {', '.join(sets)} WHERE id = ?",
            tuple(params),
        )
        return cursor.rowcount == 1

    def transicionar_estado(
        self,
        cursor,
        dispute_id: int,
        *,
        estado_nuevo: str,
        estado_actual_esperado: Optional[str] = None,
    ) -> bool:
        if estado_actual_esperado:
            cursor.execute(
                """
                UPDATE financial_disputes
                SET estado_interno = ?, actualizado_en = CURRENT_TIMESTAMP
                WHERE id = ? AND estado_interno = ?
                """,
                (estado_nuevo, dispute_id, estado_actual_esperado),
            )
        else:
            cursor.execute(
                """
                UPDATE financial_disputes
                SET estado_interno = ?, actualizado_en = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (estado_nuevo, dispute_id),
            )
        return cursor.rowcount == 1

    def cerrar_disputa(
        self,
        cursor,
        dispute_id: int,
        *,
        estado_interno: str,
        resolution: str,
        resolution_reason: str = "",
        bloqueo_financiero: bool = False,
    ) -> bool:
        cursor.execute(
            """
            UPDATE financial_disputes
            SET estado_interno = ?, resolution = ?, resolution_reason = ?,
                bloqueo_financiero = ?, cerrado_en = CURRENT_TIMESTAMP,
                actualizado_en = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (estado_interno, resolution or None, resolution_reason or None,
             1 if bloqueo_financiero else 0, dispute_id),
        )
        return cursor.rowcount == 1

    def vincular_conflicto(self, cursor, dispute_id: int, conflicto_id: int) -> bool:
        cursor.execute(
            "UPDATE financial_disputes SET conflicto_id = ?, actualizado_en = CURRENT_TIMESTAMP WHERE id = ?",
            (conflicto_id, dispute_id),
        )
        return cursor.rowcount == 1

    def asignar_responsable(self, cursor, dispute_id: int, codigo: str) -> bool:
        cursor.execute(
            "UPDATE financial_disputes SET responsable_codigo = ?, actualizado_en = CURRENT_TIMESTAMP WHERE id = ?",
            (codigo, dispute_id),
        )
        return cursor.rowcount == 1

    def intentar_envio_evidencia(self, cursor, dispute_id: int) -> bool:
        cursor.execute(
            """
            UPDATE financial_disputes
            SET evidence_submitted = 1, actualizado_en = CURRENT_TIMESTAMP
            WHERE id = ? AND evidence_submitted = 0
            """,
            (dispute_id,),
        )
        return cursor.rowcount == 1

    def insertar_evidencia(
        self,
        cursor,
        *,
        dispute_id: int,
        tipo: str,
        referencia: str,
        content_hash: str,
        autor_codigo: str,
        metadata: Optional[Dict] = None,
    ) -> int:
        cursor.execute(
            """
            INSERT INTO financial_dispute_evidence (
                dispute_id, tipo, referencia, content_hash, autor_codigo, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                dispute_id, tipo, referencia or None, content_hash or None,
                autor_codigo, json.dumps(metadata or {}, ensure_ascii=False),
            ),
        )
        return int(cursor.lastrowid or 0)

    def listar_evidencias(self, cursor, dispute_id: int) -> List[Dict[str, Any]]:
        cursor.execute(
            "SELECT * FROM financial_dispute_evidence WHERE dispute_id = ? ORDER BY id ASC",
            (dispute_id,),
        )
        return [self._row_dict(r, cursor) for r in cursor.fetchall()]

    def marcar_evidencia_enviada(self, cursor, evidence_id: int) -> bool:
        cursor.execute(
            """
            UPDATE financial_dispute_evidence
            SET enviada_a_stripe = 1, fecha_envio = CURRENT_TIMESTAMP, estado = 'ENVIADA'
            WHERE id = ? AND enviada_a_stripe = 0
            """,
            (evidence_id,),
        )
        return cursor.rowcount == 1

    def registrar_intento(
        self,
        cursor,
        dispute_id: int,
        operacion: str,
        actor: str,
        resultado: str,
        *,
        permiso_usado: str = "",
        metadata: Optional[Dict] = None,
    ) -> None:
        cursor.execute(
            """
            INSERT INTO financial_dispute_attempts (
                dispute_id, operacion, actor_codigo, permiso_usado, resultado, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                dispute_id, operacion, actor, permiso_usado or None, resultado,
                json.dumps(metadata or {}, ensure_ascii=False),
            ),
        )

    def vincular_stripe_disputes_audit(self, cursor, stripe_dispute_id: str, financial_dispute_id: int) -> None:
        cols = self._columnas(cursor, "stripe_disputes")
        if "financial_dispute_id" not in cols:
            return
        cursor.execute(
            "UPDATE stripe_disputes SET financial_dispute_id = ? WHERE stripe_dispute_id = ?",
            (financial_dispute_id, stripe_dispute_id),
        )

    def _columnas(self, cursor, tabla: str) -> set:
        cursor.execute(f"PRAGMA table_info({tabla})")
        return {row[1] for row in cursor.fetchall()}

    def _row_dict(self, row, cursor) -> Dict[str, Any]:
        if row is None:
            return {}
        if hasattr(row, "keys"):
            return dict(row)
        names = [c[0] for c in cursor.description]
        return {names[i]: row[i] for i in range(len(row))}

    @staticmethod
    def deadline_expirado(evidence_due_by: Any) -> bool:
        if not evidence_due_by:
            return False
        try:
            if isinstance(evidence_due_by, (int, float)):
                due = datetime.fromtimestamp(int(evidence_due_by), tz=timezone.utc)
            else:
                raw = str(evidence_due_by).replace("Z", "+00:00")
                due = datetime.fromisoformat(raw)
                if due.tzinfo is None:
                    due = due.replace(tzinfo=timezone.utc)
            return datetime.now(timezone.utc) > due
        except (TypeError, ValueError, OSError):
            return False
