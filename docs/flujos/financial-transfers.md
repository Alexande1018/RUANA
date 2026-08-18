# Transferencias Stripe blindadas (FASE 03)

Documentación del flujo de liberación de fondos al profesional tras confirmación del contratante.

## Flujo normal

```
Contratante confirma trabajo
        ↓
Validaciones (pago, conflicto, importe, Connect)
        ↓
CAS: ESPERANDO_CONFIRMACION → LIBERACION_AUTORIZADA
        ↓
Reclamo atómico en financial_transfers (UNIQUE contacto_id)
        ↓
TRANSFERENCIA_PENDIENTE
        ↓
Stripe Transfer.create (idempotency_key=transfer-contacto-{id})
        ↓
TRANSFERENCIA_ENVIADA + stripe_transfer_id registrado
        ↓
Webhook transfer.created (refuerzo idempotente)
        ↓
Webhook transfer.paid
        ↓
TRANSFERIDO + estado_pago=transferido + notificación + score
```

**Importante:** `TRANSFERIDO` solo se alcanza tras `transfer.paid`, no al crear la transferencia en Stripe.

## Estados

| Capa | Estados relevantes |
|------|---------------------|
| Servicio (`estado`) | `trabajo_en_progreso` → `trabajo_cerrado` (en `transfer.paid`) |
| Financiero (`estado_financiero`) | `ESPERANDO_CONFIRMACION` → `LIBERACION_AUTORIZADA` → `TRANSFERENCIA_PENDIENTE` → `TRANSFERENCIA_ENVIADA` → `TRANSFERIDO` |
| Transferencia (`estado_transferencia`) | `RETENIDO` → `PENDIENTE` → `ENVIADA` → `COMPLETADA` |

## Idempotencia

1. **Tabla `financial_transfers`**: `UNIQUE(contacto_id)` garantiza una sola fila por operación RUANA.
2. **Idempotency key Stripe**: `transfer-contacto-{contacto_id}` — reintentos devuelven la misma transferencia.
3. **CAS financiero**: `actualizar_estado_financiero_atomico` evita doble autorización.
4. **Webhooks Fase 02**: reclamación atómica de `event_id`.

## Concurrencia

- `INSERT OR IGNORE` en `financial_transfers` — solo un proceso reclama el slot.
- `intentar_ejecutar_stripe`: `UPDATE ... WHERE estado='RECLAMADA'` — solo un proceso llama a Stripe.
- Segundo proceso concurrente recibe respuesta idempotente `transferencia_en_proceso`.

## Timeout y recuperación

Si Stripe crea la transferencia pero RUANA pierde la respuesta:

1. El registro en `financial_transfers` persiste (`RECLAMADA` o `FALLIDA`).
2. Reintento con la misma `idempotency_key` recupera la transferencia existente en Stripe.
3. `intentar_reintentar_stripe` resetea `FALLIDA` → `RECLAMADA` para reintentos seguros.

## Relación RUANA ↔ Stripe

| RUANA | Stripe |
|-------|--------|
| `contactos_ruana.id` | `metadata.contacto_id` en Transfer |
| `stripe_payment_intent_id` | PaymentIntent |
| `financial_transfers.stripe_transfer_id` | Transfer.id |
| `aliados.stripe_account_id` | Transfer.destination |
| `importe_neto_profesional` | Transfer.amount (céntimos) |

## Webhooks

| Evento | Acción |
|--------|--------|
| `transfer.created` | Registra `transfer_id`, `TRANSFERENCIA_ENVIADA` |
| `transfer.paid` | `TRANSFERIDO`, legacy, notificación, score |
| `transfer.failed` | `TRANSFERENCIA_FALLIDA` o discrepancia si terminal |

### Eventos fuera de orden

- `transfer.paid` antes de `transfer.created`: se recupera la cadena de estados y se marca `TRANSFERIDO`.
- `transfer.paid` + `transfer.failed` posterior: discrepancia, sin retroceder desde `TRANSFERIDO`.

## Bloqueos

La liberación se bloquea si:

- Conflicto abierto (`payment_conflicts` o `estado=importe_en_disputa`)
- PaymentIntent ausente o pago no confirmado
- Importe/profesional/cuenta Connect no coinciden con registro existente
- Estado financiero incompatible
- Operación ya `TRANSFERIDO`

## Auditoría

Tabla `financial_transfer_attempts`: cada intento, bloqueo, transición y referencia Stripe (sin secretos).

## Archivos clave

- `core/services/financial_transfer_service.py` — orquestación
- `core/repositories/financial_transfer_repo.py` — persistencia atómica
- `core/services/stripe_webhook_service.py` — handlers transfer.*
- `supabase/migrations/20260818000200_financial_fase03.sql` — PostgreSQL

## Migración SQLite

`schema_service._migrar_financial_fase03`
