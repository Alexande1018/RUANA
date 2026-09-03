#!/usr/bin/env python3
"""Diagnóstico y resync idempotente del encargo #72 (Sandra Castaño Reina)."""
from __future__ import annotations

import json
import os
import sys

import psycopg

CONTACTO_ID = 72
PI_ID = "pi_3UBAKsRtuA6KQmfo1xWbxyAu"
CS_ID = "cs_live_a1Tw1qDozDSc9nHD3J9ocIljViRPtQGLdNdeHMDVfmHygUJm9LrKLw4CWE"
COBRO_TS = "2026-09-02 09:20:04+00"

DIAGNOSTIC_SQL = """
SELECT
  c.id,
  c.solicitante_codigo,
  sol.nombre  AS solicitante_nombre,
  sol.email   AS solicitante_email,
  c.profesional_codigo,
  pro.nombre  AS profesional_nombre,
  pro.email   AS profesional_email,
  pro.stripe_account_id,
  pro.stripe_charges_enabled,
  pro.stripe_payouts_enabled,
  c.estado,
  c.estado_pago,
  c.estado_financiero,
  c.modo_pago,
  c.importe_acordado,
  c.importe_neto_profesional,
  c.apoyo_ruana,
  c.stripe_payment_intent_id,
  c.stripe_checkout_session_id,
  c.stripe_transfer_id,
  c.acuerdo_alcanzado_en,
  c.fecha_cobro_confirmado,
  c.fecha_confirmacion_trabajo,
  c.actualizado_en
FROM contactos_ruana c
JOIN aliados sol ON sol.codigo = c.solicitante_codigo
JOIN aliados pro ON pro.codigo = c.profesional_codigo
WHERE c.id = %s
"""

AUDIT_SQL = """
SELECT accion, actor_tipo, actor_codigo, detalles, creado_en
FROM audit_log
WHERE entidad = 'contacto' AND entidad_id = %s
ORDER BY creado_en DESC
LIMIT 15
"""

FT_SQL = """
SELECT id, contacto_id, estado, stripe_transfer_id, amount_cents,
       destination_account_id, professional_codigo, error_message,
       creado_en, actualizado_en
FROM financial_transfers
WHERE contacto_id = %s
ORDER BY id DESC
LIMIT 5
"""

# Cuenta Connect de prueba (cacero1018@hotmail.com) vinculada por error a Andrea 50009.
DEV_STRIPE_ACCOUNT = "acct_1U4nS02OQ4mXrlA3"

CLEAR_DEV_STRIPE_SQL = """
UPDATE aliados
SET stripe_account_id = NULL,
    stripe_charges_enabled = 0,
    stripe_payouts_enabled = 0
WHERE codigo = %s
  AND stripe_account_id = %s
"""

RESYNC_SQL = """
UPDATE contactos_ruana
SET estado = 'trabajo_en_progreso',
    estado_pago = 'cobro_confirmado',
    pendiente_pago = 0,
    stripe_payment_intent_id = %s,
    stripe_checkout_session_id = COALESCE(stripe_checkout_session_id, %s),
    stripe_cobro_estado = 'confirmado',
    fecha_cobro_confirmado = COALESCE(fecha_cobro_confirmado, %s::timestamptz),
    fecha_trabajo_en_progreso = COALESCE(fecha_trabajo_en_progreso, %s::timestamptz),
    actualizado_en = CURRENT_TIMESTAMP
WHERE id = %s
  AND modo_pago = 'stripe'
  AND estado_pago IN ('esperando_cobro_cliente', 'checkout_activo')
"""


def _row_to_dict(cur, row) -> dict:
    cols = [d[0] for d in cur.description]
    out = {}
    for k, v in zip(cols, row):
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


def main() -> int:
    url = (os.environ.get("DATABASE_URL") or "").strip()
    if not url:
        print("DATABASE_URL no configurada", file=sys.stderr)
        return 1

    dry_run = os.environ.get("ENCARGO_72_DRY_RUN", "0").strip().lower() in ("1", "true", "yes")
    allow_resync = os.environ.get("ENCARGO_72_ALLOW_RESYNC", "1").strip().lower() in ("1", "true", "yes")
    clear_dev_stripe = os.environ.get("ENCARGO_72_CLEAR_DEV_STRIPE", "0").strip().lower() in ("1", "true", "yes")

    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute(DIAGNOSTIC_SQL, (CONTACTO_ID,))
            row = cur.fetchone()
            if not row:
                print(f"ERROR: contacto {CONTACTO_ID} no encontrado", file=sys.stderr)
                return 1
            diag = _row_to_dict(cur, row)
            print("=== DIAGNOSTICO ENCARGO #72 ===")
            print(json.dumps(diag, ensure_ascii=False, indent=2, default=str))

            cur.execute(AUDIT_SQL, (CONTACTO_ID,))
            audit = [_row_to_dict(cur, r) for r in cur.fetchall()]
            print("\n=== AUDIT LOG (ultimos 15) ===")
            print(json.dumps(audit, ensure_ascii=False, indent=2, default=str))

            cur.execute(FT_SQL, (CONTACTO_ID,))
            ft_rows = [_row_to_dict(cur, r) for r in cur.fetchall()]
            print("\n=== FINANCIAL_TRANSFERS ===")
            print(json.dumps(ft_rows, ensure_ascii=False, indent=2, default=str))

            estado_pago = (diag.get("estado_pago") or "").strip()
            prof_codigo = (diag.get("profesional_codigo") or "").strip()
            prof_acct = (diag.get("stripe_account_id") or "").strip()
            prof_charges = int(diag.get("stripe_charges_enabled") or 0)

            print("\n=== ANALISIS ===")
            if estado_pago in ("esperando_cobro_cliente", "checkout_activo"):
                print("COBRO: pendiente de resync en BD")
            elif estado_pago == "cobro_confirmado":
                print("COBRO: ya confirmado en BD")
            else:
                print(f"COBRO: estado_pago={estado_pago!r}")

            if prof_acct == DEV_STRIPE_ACCOUNT:
                print(
                    f"STRIPE PROF: cuenta DEV de prueba vinculada por error ({prof_acct}) "
                    f"— NO es Connect real de {diag.get('profesional_nombre')}"
                )
            elif prof_acct and prof_charges == 1:
                print(f"STRIPE PROF: flags listos en BD ({prof_acct})")
            else:
                print(
                    f"STRIPE PROF: NO listo (account_id={prof_acct!r}, charges_enabled={prof_charges})"
                )

            if diag.get("stripe_transfer_id"):
                print(f"TRANSFER: ya registrado {diag['stripe_transfer_id']}")
            else:
                print("TRANSFER: pendiente (sin stripe_transfer_id en contacto)")

            if clear_dev_stripe and prof_acct == DEV_STRIPE_ACCOUNT and prof_codigo:
                if dry_run:
                    print(f"\n=== CLEAR DEV STRIPE (dry-run): resetearia aliado {prof_codigo} ===")
                else:
                    cur.execute(CLEAR_DEV_STRIPE_SQL, (prof_codigo, DEV_STRIPE_ACCOUNT))
                    cleared = cur.rowcount
                    conn.commit()
                    print(f"\n=== CLEAR DEV STRIPE: {cleared} fila(s) — Andrea debe re-onboardear ===")

            resync_rows = 0
            if allow_resync and estado_pago in ("esperando_cobro_cliente", "checkout_activo"):
                if dry_run:
                    print("\n=== RESYNC (dry-run, no ejecutado) ===")
                    print("Se aplicaria UPDATE de cobro confirmado")
                else:
                    cur.execute(
                        RESYNC_SQL,
                        (PI_ID, CS_ID, COBRO_TS, COBRO_TS, CONTACTO_ID),
                    )
                    resync_rows = cur.rowcount
                    conn.commit()
                    print(f"\n=== RESYNC EJECUTADO: {resync_rows} fila(s) actualizada(s) ===")
                    if resync_rows:
                        cur.execute(DIAGNOSTIC_SQL, (CONTACTO_ID,))
                        post = _row_to_dict(cur, cur.fetchone())
                        print(json.dumps(post, ensure_ascii=False, indent=2, default=str))
            else:
                print("\n=== RESYNC: omitido (no necesario o deshabilitado) ===")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
