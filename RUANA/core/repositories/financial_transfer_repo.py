"""Repositorio de transferencias Stripe blindadas (FASE 03)."""
from __future__ import annotations

import json
from typing import Any, Dict, Optional, Tuple


class FinancialTransferRepo:
    """Persistencia atómica: una operación RUANA → una transferencia Stripe."""

    def tabla_existe(self, cursor) -> bool:
        cursor.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='financial_transfers' LIMIT 1"
        )
        return cursor.fetchone() is not None

    def reclamar_transferencia(
        self,
        cursor,
        contacto_id: int,
        idempotency_key: str,
        amount_cents: int,
        currency: str,
        destination_account_id: str,
        professional_codigo: str,
        stripe_payment_intent_id: str,
        actor_codigo: str,
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        """
        Reclama el slot de transferencia de forma atómica (UNIQUE contacto_id).

        Returns:
            ('claimed', row_dict) — este proceso debe ejecutar Stripe.
            ('existing', row_dict) — ya existe registro para esta operación.
        """
        cursor.execute(
            """
            INSERT OR IGNORE INTO financial_transfers (
                contacto_id, idempotency_key, amount_cents, currency,
                destination_account_id, professional_codigo, stripe_payment_intent_id,
                estado, actor_codigo
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'RECLAMADA', ?)
            """,
            (
                contacto_id,
                idempotency_key,
                amount_cents,
                currency,
                destination_account_id,
                professional_codigo,
                stripe_payment_intent_id or None,
                actor_codigo,
            ),
        )
        if cursor.rowcount > 0:
            row = self.select_por_contacto(cursor, contacto_id)
            return "claimed", self._row_dict(row)

        row = self.select_por_contacto(cursor, contacto_id)
        return "existing", self._row_dict(row)

    def intentar_reintentar_stripe(self, cursor, contacto_id: int) -> bool:
        """Permite reintentar solo tras FALLIDA explícita (p. ej. timeout Stripe).

        No resetea STRIPE_EN_PROCESO: otro hilo puede estar ejecutando Transfer.create.
        """
        cursor.execute(
            """
            UPDATE financial_transfers
            SET estado = 'RECLAMADA', error_message = NULL, actualizado_en = CURRENT_TIMESTAMP
            WHERE contacto_id = ? AND stripe_transfer_id IS NULL
              AND estado = 'FALLIDA'
            """,
            (contacto_id,),
        )
        return cursor.rowcount == 1

    def esta_ejecucion_stripe_en_curso(self, cursor, contacto_id: int) -> bool:
        """True si otro proceso ya reclamó y está llamando a Stripe."""
        cursor.execute(
            """
            SELECT 1 FROM financial_transfers
            WHERE contacto_id = ? AND stripe_transfer_id IS NULL
              AND estado = 'STRIPE_EN_PROCESO'
            LIMIT 1
            """,
            (contacto_id,),
        )
        return cursor.fetchone() is not None

    def intentar_ejecutar_stripe(self, cursor, contacto_id: int) -> bool:
        """Solo un proceso puede pasar de RECLAMADA a STRIPE_EN_PROCESO."""
        cursor.execute(
            """
            UPDATE financial_transfers
            SET estado = 'STRIPE_EN_PROCESO', actualizado_en = CURRENT_TIMESTAMP
            WHERE contacto_id = ? AND stripe_transfer_id IS NULL AND estado = 'RECLAMADA'
            """,
            (contacto_id,),
        )
        return cursor.rowcount == 1

    def select_por_contacto(self, cursor, contacto_id: int) -> Optional[Any]:
        columnas = self._columnas_financial_transfers(cursor)
        extras = []
        for col in (
            "stripe_balance_transaction_id", "stripe_destination_payment_id",
            "reconciliacion_estado", "stripe_snapshot_json",
            "efectos_post_transfer_aplicados", "bloqueada",
        ):
            if col in columnas:
                extras.append(col)
        extra_sql = (", " + ", ".join(extras)) if extras else ""
        cursor.execute(
            f"""
            SELECT id, contacto_id, idempotency_key, stripe_transfer_id,
                   amount_cents, currency, destination_account_id, professional_codigo,
                   stripe_payment_intent_id, estado, actor_codigo, error_message,
                   creado_en, actualizado_en{extra_sql}
            FROM financial_transfers
            WHERE contacto_id = ?
            """,
            (contacto_id,),
        )
        return cursor.fetchone()

    def select_por_idempotency_key(self, cursor, idempotency_key: str) -> Optional[Any]:
        cursor.execute(
            """
            SELECT id, contacto_id, idempotency_key, stripe_transfer_id,
                   amount_cents, currency, destination_account_id, professional_codigo,
                   stripe_payment_intent_id, estado, actor_codigo, error_message
            FROM financial_transfers
            WHERE idempotency_key = ?
            """,
            (idempotency_key,),
        )
        return cursor.fetchone()

    def marcar_stripe_creada(
        self, cursor, contacto_id: int, stripe_transfer_id: str
    ) -> int:
        cursor.execute(
            """
            UPDATE financial_transfers
            SET stripe_transfer_id = ?, estado = 'STRIPE_CREADA',
                actualizado_en = CURRENT_TIMESTAMP
            WHERE contacto_id = ? AND stripe_transfer_id IS NULL
            """,
            (stripe_transfer_id, contacto_id),
        )
        return cursor.rowcount

    def marcar_completada(self, cursor, contacto_id: int) -> int:
        cursor.execute(
            """
            UPDATE financial_transfers
            SET estado = 'COMPLETADA', actualizado_en = CURRENT_TIMESTAMP
            WHERE contacto_id = ?
            """,
            (contacto_id,),
        )
        return cursor.rowcount

    def actualizar_referencias_stripe(
        self,
        cursor,
        contacto_id: int,
        transfer_id: str,
        *,
        balance_transaction_id: str = "",
        destination_payment_id: str = "",
    ) -> int:
        columnas = self._columnas_financial_transfers(cursor)
        sets = ["stripe_transfer_id = COALESCE(stripe_transfer_id, ?)", "actualizado_en = CURRENT_TIMESTAMP"]
        params = [transfer_id]
        if balance_transaction_id and "stripe_balance_transaction_id" in columnas:
            sets.append("stripe_balance_transaction_id = COALESCE(stripe_balance_transaction_id, ?)")
            params.append(balance_transaction_id)
        if destination_payment_id and "stripe_destination_payment_id" in columnas:
            sets.append("stripe_destination_payment_id = COALESCE(stripe_destination_payment_id, ?)")
            params.append(destination_payment_id)
        params.append(contacto_id)
        cursor.execute(
            f"UPDATE financial_transfers SET {', '.join(sets)} WHERE contacto_id = ?",
            params,
        )
        return cursor.rowcount

    def _columnas_financial_transfers(self, cursor) -> set:
        cursor.execute("PRAGMA table_info(financial_transfers)")
        return {row[1] for row in cursor.fetchall()}

    def marcar_reconciliacion(self, cursor, contacto_id: int, estado_recon: str) -> int:
        columnas = self._columnas_financial_transfers(cursor)
        if "reconciliacion_estado" not in columnas:
            return 0
        cursor.execute(
            """
            UPDATE financial_transfers
            SET reconciliacion_estado = ?, actualizado_en = CURRENT_TIMESTAMP
            WHERE contacto_id = ?
            """,
            (estado_recon, contacto_id),
        )
        return cursor.rowcount

    def marcar_efectos_aplicados(self, cursor, contacto_id: int) -> int:
        columnas = self._columnas_financial_transfers(cursor)
        if "efectos_post_transfer_aplicados" not in columnas:
            return 0
        cursor.execute(
            """
            UPDATE financial_transfers
            SET efectos_post_transfer_aplicados = 1, actualizado_en = CURRENT_TIMESTAMP
            WHERE contacto_id = ?
            """,
            (contacto_id,),
        )
        return cursor.rowcount

    def marcar_bloqueada(self, cursor, contacto_id: int) -> int:
        columnas = self._columnas_financial_transfers(cursor)
        if "bloqueada" not in columnas:
            return 0
        cursor.execute(
            """
            UPDATE financial_transfers
            SET bloqueada = 1, actualizado_en = CURRENT_TIMESTAMP
            WHERE contacto_id = ?
            """,
            (contacto_id,),
        )
        return cursor.rowcount

    def guardar_snapshot(
        self,
        cursor,
        contacto_id: int,
        transfer_id: str,
        snapshot: Dict[str, Any],
        event_id: str,
        event_type: str,
    ) -> None:
        snap_json = json.dumps(snapshot, ensure_ascii=False)
        columnas = self._columnas_financial_transfers(cursor)
        if "stripe_snapshot_json" in columnas:
            cursor.execute(
                """
                UPDATE financial_transfers
                SET stripe_snapshot_json = ?, actualizado_en = CURRENT_TIMESTAMP
                WHERE contacto_id = ?
                """,
                (snap_json, contacto_id),
            )
        cursor.execute(
            """
            INSERT INTO financial_transfer_snapshots (
                contacto_id, stripe_transfer_id, stripe_event_id, event_type, snapshot_json
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (contacto_id, transfer_id, event_id, event_type, snap_json),
        )

    def ultimo_snapshot(self, cursor, contacto_id: int) -> Optional[Dict[str, Any]]:
        cursor.execute(
            """
            SELECT snapshot_json FROM financial_transfer_snapshots
            WHERE contacto_id = ?
            ORDER BY id DESC LIMIT 1
            """,
            (contacto_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        raw = row[0] if not hasattr(row, "keys") else row["snapshot_json"]
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None

    def marcar_fallida(self, cursor, contacto_id: int, error_message: str) -> int:
        cursor.execute(
            """
            UPDATE financial_transfers
            SET estado = 'FALLIDA', error_message = ?,
                actualizado_en = CURRENT_TIMESTAMP
            WHERE contacto_id = ?
            """,
            (error_message[:2000], contacto_id),
        )
        return cursor.rowcount

    def registrar_intento(
        self,
        cursor,
        contacto_id: int,
        *,
        financial_transfer_id: Optional[int] = None,
        actor_codigo: str = "",
        resultado: str,
        motivo_bloqueo: str = "",
        estado_anterior: str = "",
        estado_nuevo: str = "",
        stripe_transfer_id: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        cursor.execute(
            """
            INSERT INTO financial_transfer_attempts (
                contacto_id, financial_transfer_id, actor_codigo, resultado,
                motivo_bloqueo, estado_anterior, estado_nuevo, stripe_transfer_id, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                contacto_id,
                financial_transfer_id,
                actor_codigo,
                resultado,
                motivo_bloqueo or None,
                estado_anterior or None,
                estado_nuevo or None,
                stripe_transfer_id or None,
                json.dumps(metadata or {}, ensure_ascii=False),
            ),
        )

    def contar_transferencias_contacto(self, cursor, contacto_id: int) -> int:
        cursor.execute(
            "SELECT COUNT(*) FROM financial_transfers WHERE contacto_id = ?",
            (contacto_id,),
        )
        row = cursor.fetchone()
        return int(row[0] if row else 0)

    def _row_dict(self, row, columnas: Optional[list] = None) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        if hasattr(row, "keys"):
            return dict(row)
        nombres = columnas or [
            "id", "contacto_id", "idempotency_key", "stripe_transfer_id",
            "amount_cents", "currency", "destination_account_id", "professional_codigo",
            "stripe_payment_intent_id", "estado", "actor_codigo", "error_message",
            "creado_en", "actualizado_en",
            "stripe_balance_transaction_id", "stripe_destination_payment_id",
            "reconciliacion_estado", "stripe_snapshot_json",
            "efectos_post_transfer_aplicados", "bloqueada",
        ]
        return {nombres[i]: row[i] for i in range(min(len(row), len(nombres)))}
