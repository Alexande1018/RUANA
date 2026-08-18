"""Repositorio de estado financiero transaccional (FASE 01)."""
from __future__ import annotations

from typing import Any, Dict, Optional


class FinancialTransactionRepo:
    """Acceso a datos para estado_financiero y conflictos."""

    def columnas_contacto(self, cursor) -> set:
        cursor.execute("PRAGMA table_info(contactos_ruana)")
        return {row[1] for row in cursor.fetchall()}

    def select_contacto_financiero(self, cursor, contacto_id: int) -> Optional[Any]:
        columnas = self.columnas_contacto(cursor)
        extra = []
        if "estado_financiero" in columnas:
            extra.append("estado_financiero")
        if "estado_transferencia" in columnas:
            extra.append("estado_transferencia")
        extra_sql = (", " + ", ".join(extra)) if extra else ""
        cursor.execute(
            f"""
            SELECT id, solicitante_codigo, profesional_codigo, servicio, estado,
                   importe_acordado, importe_final, apoyo_ruana, comision, comision_porcentaje,
                   modo_pago, estado_pago, pendiente_pago,
                   stripe_checkout_session_id, stripe_payment_intent_id, stripe_transfer_id,
                   importe_neto_profesional, fecha_cobro_confirmado, fecha_confirmacion_trabajo,
                   stripe_cobro_estado{extra_sql}
            FROM contactos_ruana WHERE id = ?
            """,
            (contacto_id,),
        )
        return cursor.fetchone()

    def tiene_conflicto_abierto(self, cursor, contacto_id: int) -> bool:
        from core.repositories.financial_conflict_repo import FinancialConflictRepo
        return FinancialConflictRepo().tiene_conflicto_bloqueante(cursor, contacto_id)

    def actualizar_estado_financiero_atomico(
        self,
        cursor,
        contacto_id: int,
        estado_esperado: str,
        estado_nuevo: str,
        estado_transferencia: Optional[str] = None,
    ) -> int:
        """UPDATE atómico con guardia de concurrencia (compare-and-swap)."""
        columnas = self.columnas_contacto(cursor)
        if "estado_financiero" not in columnas:
            return 0
        sets = ["estado_financiero = ?", "actualizado_en = CURRENT_TIMESTAMP"]
        params = [estado_nuevo]
        if estado_transferencia and "estado_transferencia" in columnas:
            sets.append("estado_transferencia = ?")
            params.append(estado_transferencia)
        params.extend([contacto_id, estado_esperado])
        cursor.execute(
            f"""
            UPDATE contactos_ruana
            SET {", ".join(sets)}
            WHERE id = ? AND COALESCE(estado_financiero, '') = ?
            """,
            params,
        )
        return cursor.rowcount

    def establecer_estado_financiero(
        self,
        cursor,
        contacto_id: int,
        estado: str,
        estado_transferencia: Optional[str] = None,
    ) -> int:
        columnas = self.columnas_contacto(cursor)
        if "estado_financiero" not in columnas:
            return 0
        sets = ["estado_financiero = ?", "actualizado_en = CURRENT_TIMESTAMP"]
        params = [estado]
        if estado_transferencia and "estado_transferencia" in columnas:
            sets.append("estado_transferencia = ?")
            params.append(estado_transferencia)
        params.append(contacto_id)
        cursor.execute(
            f"UPDATE contactos_ruana SET {', '.join(sets)} WHERE id = ?",
            params,
        )
        return cursor.rowcount

    def backfill_estado_financiero(self, cursor, contacto_id: int, estado: str) -> int:
        columnas = self.columnas_contacto(cursor)
        if "estado_financiero" not in columnas:
            return 0
        cursor.execute(
            """
            UPDATE contactos_ruana
            SET estado_financiero = ?
            WHERE id = ? AND (estado_financiero IS NULL OR estado_financiero = '')
            """,
            (estado, contacto_id),
        )
        return cursor.rowcount

    def listar_contactos_sin_estado_financiero(self, cursor, limit: int = 500) -> list:
        columnas = self.columnas_contacto(cursor)
        if "estado_financiero" not in columnas:
            return []
        cursor.execute(
            """
            SELECT id, modo_pago, estado, estado_pago, stripe_transfer_id,
                   stripe_payment_intent_id, fecha_confirmacion_trabajo
            FROM contactos_ruana
            WHERE estado_financiero IS NULL OR estado_financiero = ''
            LIMIT ?
            """,
            (limit,),
        )
        return cursor.fetchall()

    def actualizar_solo_estado_transferencia(
        self, cursor, contacto_id: int, estado_transferencia: str
    ) -> int:
        columnas = self.columnas_contacto(cursor)
        if "estado_transferencia" not in columnas:
            return 0
        cursor.execute(
            """
            UPDATE contactos_ruana
            SET estado_transferencia = ?, actualizado_en = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (estado_transferencia, contacto_id),
        )
        return cursor.rowcount

    def contacto_dict(self, row) -> Dict[str, Any]:
        if row is None:
            return {}
        if hasattr(row, "keys"):
            return dict(row)
        return {}
