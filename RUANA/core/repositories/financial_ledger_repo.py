"""Repositorio del ledger financiero (FASE 08)."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple


class FinancialLedgerRepo:
    def tabla_existe(self, cursor, nombre: str) -> bool:
        cursor.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (nombre,),
        )
        return cursor.fetchone() is not None

    def select_por_idempotency(self, cursor, key: str) -> Optional[Dict[str, Any]]:
        cursor.execute(
            "SELECT * FROM ledger_transactions WHERE idempotency_key = ?",
            (key,),
        )
        row = cursor.fetchone()
        return self._row_dict(row, cursor) if row else None

    def select_por_id(self, cursor, tx_id: int) -> Optional[Dict[str, Any]]:
        cursor.execute("SELECT * FROM ledger_transactions WHERE id = ?", (tx_id,))
        row = cursor.fetchone()
        return self._row_dict(row, cursor) if row else None

    def insert_transaction(
        self,
        cursor,
        *,
        transaction_key: str,
        contacto_id: Optional[int],
        tipo: str,
        moneda: str,
        estado: str,
        actor_origen: str,
        evento_origen: str,
        referencia_stripe: str,
        idempotency_key: str,
        reversa_de_id: Optional[int] = None,
        metadata: Optional[Dict] = None,
    ) -> int:
        cursor.execute(
            """
            INSERT OR IGNORE INTO ledger_transactions (
                transaction_key, contacto_id, tipo, moneda, estado,
                actor_origen, evento_origen, referencia_stripe, idempotency_key,
                reversa_de_id, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                transaction_key, contacto_id, tipo, moneda, estado,
                actor_origen or None, evento_origen or None, referencia_stripe or None,
                idempotency_key, reversa_de_id,
                json.dumps(metadata or {}, ensure_ascii=False),
            ),
        )
        row = self.select_por_idempotency(cursor, idempotency_key)
        return int((row or {}).get("id") or 0)

    def insert_entry(
        self,
        cursor,
        *,
        ledger_transaction_id: int,
        account_code: str,
        debit_cents: int,
        credit_cents: int,
        currency: str,
        descripcion: str = "",
        referencia: str = "",
    ) -> int:
        cursor.execute(
            """
            INSERT INTO ledger_entries (
                ledger_transaction_id, account_code, debit_cents, credit_cents,
                currency, descripcion, referencia
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ledger_transaction_id, account_code,
                int(debit_cents), int(credit_cents),
                currency, descripcion or None, referencia or None,
            ),
        )
        return int(cursor.lastrowid or 0)

    def insert_event_link(
        self,
        cursor,
        *,
        ledger_transaction_id: int,
        resource_type: str,
        resource_id: str,
        metadata: Optional[Dict] = None,
    ) -> None:
        cursor.execute(
            """
            INSERT OR IGNORE INTO ledger_event_links (
                ledger_transaction_id, resource_type, resource_id, metadata_json
            ) VALUES (?, ?, ?, ?)
            """,
            (
                ledger_transaction_id, resource_type, resource_id,
                json.dumps(metadata or {}, ensure_ascii=False),
            ),
        )

    def marcar_posted(self, cursor, tx_id: int) -> None:
        cursor.execute(
            """
            UPDATE ledger_transactions
            SET estado = 'POSTED', fecha_publicacion = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND estado = 'DRAFT'
            """,
            (tx_id,),
        )

    def marcar_voided(self, cursor, tx_id: int) -> None:
        cursor.execute(
            """
            UPDATE ledger_transactions
            SET estado = 'VOIDED', updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (tx_id,),
        )

    def listar_entries(self, cursor, tx_id: int) -> List[Dict[str, Any]]:
        cursor.execute(
            "SELECT * FROM ledger_entries WHERE ledger_transaction_id = ? ORDER BY id",
            (tx_id,),
        )
        return [self._row_dict(r, cursor) for r in cursor.fetchall()]

    def sumas_transaction(self, cursor, tx_id: int) -> Tuple[int, int]:
        cursor.execute(
            """
            SELECT COALESCE(SUM(debit_cents), 0), COALESCE(SUM(credit_cents), 0)
            FROM ledger_entries WHERE ledger_transaction_id = ?
            """,
            (tx_id,),
        )
        row = cursor.fetchone()
        if not row:
            return 0, 0
        return int(row[0]), int(row[1])

    def actualizar_balance(
        self,
        cursor,
        *,
        account_code: str,
        contacto_id: Optional[int],
        currency: str,
        debit_delta: int,
        credit_delta: int,
    ) -> None:
        cid = int(contacto_id or 0)
        cursor.execute(
            """
            INSERT INTO ledger_account_balances (
                account_code, contacto_id, currency,
                debit_total_cents, credit_total_cents, saldo_neto_cents
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(account_code, contacto_id, currency) DO UPDATE SET
                debit_total_cents = debit_total_cents + excluded.debit_total_cents,
                credit_total_cents = credit_total_cents + excluded.credit_total_cents,
                saldo_neto_cents = saldo_neto_cents + excluded.saldo_neto_cents,
                actualizado_en = CURRENT_TIMESTAMP
            """,
            (
                account_code, cid, currency,
                int(debit_delta), int(credit_delta),
                int(debit_delta) - int(credit_delta),
            ),
        )

    def saldo_cuenta(
        self, cursor, account_code: str, *, contacto_id: Optional[int] = None, currency: str = "eur",
    ) -> Dict[str, int]:
        cid = int(contacto_id or 0)
        cursor.execute(
            """
            SELECT debit_total_cents, credit_total_cents, saldo_neto_cents
            FROM ledger_account_balances
            WHERE account_code = ? AND contacto_id = ? AND currency = ?
            """,
            (account_code, cid, currency),
        )
        row = cursor.fetchone()
        if not row:
            return {"debit_cents": 0, "credit_cents": 0, "saldo_neto_cents": 0}
        if hasattr(row, "keys"):
            return {
                "debit_cents": int(row["debit_total_cents"] or 0),
                "credit_cents": int(row["credit_total_cents"] or 0),
                "saldo_neto_cents": int(row["saldo_neto_cents"] or 0),
            }
        return {"debit_cents": int(row[0]), "credit_cents": int(row[1]), "saldo_neto_cents": int(row[2])}

    def listar_posted_sin_entries(self, cursor, limit: int = 100) -> List[Dict[str, Any]]:
        cursor.execute(
            """
            SELECT t.* FROM ledger_transactions t
            LEFT JOIN ledger_entries e ON e.ledger_transaction_id = t.id
            WHERE t.estado = 'POSTED'
            GROUP BY t.id
            HAVING COUNT(e.id) < 2
            LIMIT ?
            """,
            (limit,),
        )
        return [self._row_dict(r, cursor) for r in cursor.fetchall()]

    def listar_desequilibrados(self, cursor, limit: int = 100) -> List[Dict[str, Any]]:
        cursor.execute(
            """
            SELECT t.id, t.transaction_key, t.contacto_id,
                   COALESCE(SUM(e.debit_cents), 0) AS debit_sum,
                   COALESCE(SUM(e.credit_cents), 0) AS credit_sum
            FROM ledger_transactions t
            JOIN ledger_entries e ON e.ledger_transaction_id = t.id
            WHERE t.estado = 'POSTED'
            GROUP BY t.id
            HAVING debit_sum != credit_sum
            LIMIT ?
            """,
            (limit,),
        )
        return [self._row_dict(r, cursor) for r in cursor.fetchall()]

    def _row_dict(self, row, cursor) -> Dict[str, Any]:
        if row is None:
            return {}
        if hasattr(row, "keys"):
            return dict(row)
        names = [c[0] for c in cursor.description]
        return {names[i]: row[i] for i in range(len(row))}
