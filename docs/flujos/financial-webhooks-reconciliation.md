# Financial Webhooks & Reconciliation (FASE 02)

## Objetivo

Blindar la comunicación Stripe ↔ RUANA con idempotencia, eventos fuera de orden y reconciliación sin modificar dinero automáticamente de forma peligrosa.

## Arquitectura

| Componente | Rol |
|------------|-----|
| `stripe_webhook_bp.py` | Endpoint HTTP `POST /api/stripe/webhook` |
| `pago_service.procesar_webhook_stripe` | Fachada → `stripe_webhook_service` |
| `stripe_webhook_service.py` | Validación, reclamación atómica, despacho |
| `stripe_webhook_repo.py` | Persistencia eventos + refunds/disputes |
| `financial_reconciliation_service.py` | Detección de discrepancias |
| `financial_reconciliation` (tabla) | Registro de discrepancias abiertas |

## Idempotencia

1. **Reclamación atómica:** `INSERT OR IGNORE` en `stripe_webhook_events` con `estado_procesamiento='processing'`.
2. Solo el proceso que inserta procesa el evento.
3. Duplicados devuelven `duplicate: true` sin efecto financiero adicional.
4. Fallos marcan `estado_procesamiento='failed'` para permitir reintento Stripe.

## Eventos implementados

| Evento | Acción | Estado RUANA |
|--------|--------|--------------|
| `checkout.session.completed` | Confirma cobro + sync financiero | → `ESPERANDO_CONFIRMACION` |
| `payment_intent.succeeded` | Idem si no procesado | → `ESPERANDO_CONFIRMACION` |
| `payment_intent.payment_failed` | Solo si pre-pago | → `PAGO_FALLIDO` |
| `checkout.session.expired` | Reset checkout | legacy `esperando_cobro_cliente` |
| `account.updated` | Flags Connect aliado | N/A |
| `transfer.created` | Guarda `transfer_id`, enviada | → `TRANSFERENCIA_ENVIADA` |
| `transfer.paid` | Confirma transferencia | → `TRANSFERIDO` |
| `transfer.failed` | Marca fallo / discrepancia si terminal | → `TRANSFERENCIA_FALLIDA` |
| `charge.refunded` | Registra refund (total/parcial) | → `REEMBOLSO_PENDIENTE` / `REEMBOLSADO` |
| `charge.dispute.created` | Registra disputa | → `DISPUTA_STRIPE` |

## Eventos fuera de orden

- `transfer.paid` antes de `transfer.created`: recupera cadena de estados hasta `TRANSFERIDO`.
- `transfer.failed` tras `TRANSFERIDO`: **no retrocede**; registra discrepancia `STATUS_MISMATCH`.

## Reconciliación

Servicio: `financial_reconciliation_service.reconciliar_contacto()` / `ejecutar_reconciliacion_lote()`.

Compara RUANA vs snapshot Stripe (PI, transfer, importes, moneda).

**No corrige automáticamente** estados irreversibles; genera alerta vía `eventos_sistema`.

Tipos: `PAYMENT_MISSING_STRIPE`, `AMOUNT_MISMATCH`, `STATUS_MISMATCH`, etc.

## PostgreSQL

Migración: `supabase/migrations/20260818000100_financial_fase02.sql`

SQLite: `schema_service._migrar_financial_fase02`

## Tests

`tests/test_stripe_webhooks_fase02.py` — 26 casos FASE 02.
