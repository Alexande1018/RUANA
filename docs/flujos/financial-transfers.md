# Transferencias Stripe blindadas (FASE 03 / 03.1 / 03.2)

**Importes:** el cálculo interno del reparto 88/12 y de las transferencias usa **céntimos enteros** (`core/financial/money.py`). Las columnas REAL de `contactos_ruana` permanecen como borde de persistencia legacy (euros con 2 decimales).

## Flujo normal (FASE 03.2 — reconciliación explícita)

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
Webhook transfer.created
        ↓
Validación firma + idempotencia + coherencia (importe, moneda, destino, metadata)
        ↓
Snapshot Stripe guardado (balance_transaction, destination_payment)
        ↓
Reconciliación explícita (confirmed / pending / reversed / mismatch)
        ↓
Solo si confirmed → TRANSFERIDO + notificación + score (una vez)
```

**Decisión de dominio (FASE 03.2):** `transfer.created` **no** implica automáticamente `TRANSFERIDO`. Confirma que Stripe creó la transferencia y deja la operación en `TRANSFERENCIA_ENVIADA` hasta que la reconciliación devuelva `confirmed`.

## Significado de estados financieros

| Estado | Significado |
|--------|-------------|
| `TRANSFERENCIA_PENDIENTE` | Slot reclamado en RUANA; llamada a Stripe pendiente o en curso |
| `TRANSFERENCIA_ENVIADA` | Transfer aceptada por Stripe (API o webhook); obligación RUANA **no cerrada** |
| `TRANSFERIDO` | Obligación RUANA cerrada tras reconciliación `confirmed` |
| `TRANSFERENCIA_REVERTIDA` | Stripe revirtió la transferencia; operación bloqueada para nuevas liberaciones |

## Reconciliación (`transfer_reconciliation.py`)

Función `evaluar_reconciliacion_transfer` / API `evaluar_reconciliacion_contacto`:

| Decisión | Condición | Acción |
|----------|-----------|--------|
| `confirmed` | Coherencia RUANA↔Stripe + `balance_transaction` + `destination_payment` | `finalizar_transferencia_completada` (score/notif una vez) |
| `pending` | Falta evidencia Stripe o estado pre-confirmación | Permanece `TRANSFERENCIA_ENVIADA` |
| `reversed` | `reversed=true` en snapshot | `TRANSFERENCIA_REVERTIDA` + bloqueo |
| `mismatch` | Importe, moneda, destino, metadata o transfer_id incoherente | Discrepancia; no `TRANSFERIDO` |

No mueve dinero; solo compara y decide.

## Score y notificaciones

- Se ejecutan **solo** en `finalizar_transferencia_completada` tras reconciliación `confirmed`.
- Flag `efectos_post_transfer_aplicados` en `financial_transfers` evita duplicados ante webhooks repetidos.
- Si `transfer.reversed` llega **después** de `TRANSFERIDO`: alerta crítica + discrepancia; score/notificación **no** se revierten automáticamente (revisión administrativa).

## Webhooks Stripe Connect (eventos reales)

| Evento | Acción |
|--------|--------|
| `transfer.created` | Valida, snapshot, `TRANSFERENCIA_ENVIADA`, reconciliación |
| `transfer.updated` | Snapshot, compara cambios, discrepancias tipadas; no marca `TRANSFERIDO` por sí solo |
| `transfer.reversed` | `TRANSFERENCIA_REVERTIDA`, bloqueo, alerta, discrepancia; idempotente |

### Eventos legacy (compatibilidad histórica)

| Evento | Tratamiento |
|--------|-------------|
| `transfer.paid` | Alias de confirmación legacy (`legacy_confirmacion=True` → `confirmed` sin exigir evidencia) |
| `transfer.failed` | Handler legacy; fallos reales son síncronos en `Transfer.create` |

**No configurar** `transfer.paid` ni `transfer.failed` en el endpoint webhook moderno. Cubiertos por tests separados; no fundamentan el diseño actual.

## Idempotencia

1. **`financial_transfers`**: `UNIQUE(contacto_id)` — una operación RUANA → una transferencia.
2. **Stripe**: `idempotency_key=transfer-contacto-{contacto_id}`.
3. **Webhooks**: reclamación atómica de `event_id` (FASE 02).
4. **Efectos post-transfer**: `efectos_post_transfer_aplicados` evita doble score/notificación.

## Concurrencia

- `INSERT OR IGNORE` en `financial_transfers`.
- `intentar_ejecutar_stripe`: solo un proceso llama a Stripe.
- Segundo proceso: respuesta idempotente `transferencia_en_proceso`.

## Bloqueos

- Conflicto abierto, pago no confirmado, incoherencia de datos
- Estado `TRANSFERENCIA_REVERTIDA` o flag `bloqueada=1`
- Operación ya `TRANSFERIDO` (salvo idempotencia de webhooks)

## Auditoría

- `financial_transfer_attempts` — intentos y transiciones
- `financial_transfer_snapshots` — historial de snapshots Stripe por evento
- `financial_reconciliation` — discrepancias tipadas

## Archivos clave

- `core/services/financial_transfer_service.py` — orquestación API
- `core/services/stripe_transfer_events.py` — handlers Connect + reconciliación
- `core/financial/transfer_reconciliation.py` — decisión confirmed/pending/reversed/mismatch
- `core/repositories/financial_transfer_repo.py` — persistencia atómica
- `core/services/stripe_webhook_service.py` — despacho webhooks
- `supabase/migrations/20260818000400_financial_fase03_2.sql` — reconciliación + snapshots

## Migraciones

- FASE 03: tablas `financial_transfers`, `financial_transfer_attempts`
- FASE 03.1: `stripe_balance_transaction_id`, `stripe_destination_payment_id`
- FASE 03.2: `reconciliacion_estado`, `stripe_snapshot_json`, `efectos_post_transfer_aplicados`, `bloqueada`, tabla `financial_transfer_snapshots`

SQLite: `schema_service._migrar_financial_fase03` + `_migrar_financial_fase03_1` + `_migrar_financial_fase03_2`
