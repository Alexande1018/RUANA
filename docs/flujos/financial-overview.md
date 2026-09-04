# Subsistema financiero RUANA (FASE 01–11, 13A, 14)

> **Autoridad:** [Manual Maestro §3 y §10](../../README.md).  
> Este documento describe únicamente lo verificado en el código el **2026-09-04**.  
> Deep-dives: [máquina de estados](financial-transaction-state-machine.md) · [webhooks y reconciliación](financial-webhooks-reconciliation.md) · [transferencias](financial-transfers.md).

**Principio:** el código es la fuente de verdad. Lo no confirmado se marca `NO VERIFICADO`.

---

## 1. Qué es

Capa de administración e integración Stripe sobre `contactos_ruana`. Separa el **estado del encargo** (`estado`) del **estado del dinero** (`estado_financiero`, `estado_transferencia`) y añade excepciones (conflictos internos, reembolsos, disputas Stripe), libro mayor, reconciliación y automatización.

**Conflictos ≠ disputas.** Son dominios distintos (tablas, permisos y flujos distintos) con enlace opcional disputa → conflicto.

---

## 2. Arquitectura verificada

```text
stripe_webhook_bp  ──► pago_service ──► stripe_webhook_service
pagos_bp           ──► pago_service / financial_transfer_service
financial_*_bp     ──► financial_*_service ──► financial_*_repo
                         │
                         ▼
                   core/financial/*  (estados, state machine, money, permisos)
                         │
                         ▼
                   Postgres (migraciones 20260818* + hotfix SERIAL 20260903)
                   SQLite   (schema_service._migrar_financial_fase*)
```

Registro en `RUANA/web/app.py` (L113–127): siete blueprints `financial_*` + `pagos_bp` + `stripe_webhook_bp`.

Todas las rutas financieras admin tienen **alias EN + ES** (p. ej. `/api/admin/financial` y `/api/admin/finanzas`). Cada alias cuenta como ruta distinta.

---

## 3. Mapa de fases (verificado en código y migraciones)

| Fase | ¿Existe? | Alcance | Evidencia principal |
|------|----------|---------|---------------------|
| 01 | Sí | Máquina de estados `estado_financiero`, CAS, invariantes | `core/financial/estados.py`, `state_machine.py`, `financial_transaction_service.py`. **No hay** SQL `20260818*` para esta fase; runtime en `schema_service._migrar_financial_fase01` |
| 02 | Sí | Webhooks, reconciliación básica, columnas Stripe | `stripe_webhook_*`, `20260818000100_financial_fase02.sql` |
| 03 / 03.1 / 03.2 | Sí | Transferencias blindadas + reconciliación explícita | `financial_transfer_*`, `stripe_transfer_events.py`, `20260818000200`–`00400` |
| 04 / 04.1 | Sí | Conflictos formales RUANA + REST | `financial_conflict_*`, `20260818000500` |
| 05 | Sí | Reembolsos | `financial_refund_*`, `20260818000600` |
| 06 | Sí | Disputas / chargebacks Stripe | `financial_dispute_*`, `20260818000700` |
| 07 | Sí | Reconciliación avanzada (cadena Stripe) | `financial_reconciliation_advanced_*`, `20260818000800` |
| 08 | Sí | Ledger doble partida | `financial_ledger_*`, `20260818000900` |
| 09 | Sí | Panel admin | `financial_admin_*`, `20260818001000` |
| 10 | Sí | Aprobaciones, audit, rate limit, permisos | `financial_action_approval_*`, `20260818001100` |
| 11 | Sí | Automatización / cron | `financial_automation_*`, `20260818001200` |
| **12** | **No** | — | Búsqueda `FASE 12` / `fase12` en el repo: **0 coincidencias** |
| 13A | Sí | P0: mode guard, ledger inmutable, legacy 410, schema-health | `startup_validation.py`, `stripe_mode_guard.py`, `20260818001300` |
| 14 | Sí (operativa, sin migración) | Céntimos enteros + rate limit + ops Live | `core/financial/money.py`, `docs/operaciones/fase-14-stripe-live.md` |
| Hotfix 2026-09-03 | Sí | SERIAL/`nextval` en ~24 tablas financieras | `20260903000100_financial_transfers_id_serial.sql` |

**RLS:** ninguna migración financiera (`20260818*` ni `20260903*`) activa RLS ni crea políticas. Las tablas financieras quedan **sin RLS** en el DDL del repo.

---

## 4. Blueprints y rutas (conteo verificado)

| Blueprint | Rutas `@*.route` | Prefijos |
|-----------|----------------:|----------|
| `financial_admin_bp` | 30 | `/api/admin/financial`, `/api/admin/finanzas` |
| `financial_automation_bp` | 14 | `/api/admin/financial-automation`, `/automatizacion-financiera` |
| `financial_conflicts_bp` | 28 | `/api/admin/financial-conflicts`, `/conflictos-financieros` |
| `financial_disputes_bp` | 14 | `/api/admin/financial-disputes`, `/disputas-financieras` |
| `financial_ledger_bp` | 14 | `/api/admin/financial-ledger`, `/libro-mayor-financiero` |
| `financial_reconciliation_bp` | 14 | `/api/admin/financial-reconciliation`, `/reconciliacion-financiera` |
| `financial_refunds_bp` | 16 | `/api/admin/financial-refunds`, `/reembolsos-financieros` (+ acción desde conflicto) |
| `pagos_bp` (Stripe + métodos) | 14 | checkout, onboarding, métodos de pago, **legacy 410** |
| `stripe_webhook_bp` | 1 | `POST /api/stripe/webhook` |

**Legacy 410** (`pagos_bp.py`): `POST /api/admin/payment-conflicts/<id>/resolver` y alias equivalentes. Canónico: `financial-conflicts/.../resolver`.

---

## 5. Permisos

| Mecanismo | Evidencia | Efecto |
|-----------|-----------|--------|
| `require_admin` | `auth_decorators.py` | Sesión admin o JWT `admin_codigo` |
| `require_admin_escritura` | idem | Exige permiso `escribir` o `configurar` |
| `require_admin_escritura_or_cron` | idem | Escritura **o** cron válido |
| Permisos granulares por dominio | `core/*_authorization.py` | `financial.dashboard.view`, `conflict.resolve`, `financial.refund.execute`, etc. |
| Cron | `_cron_secret_valid()` | Header `X-Ruana-Cron-Secret` **o** OIDC Bearer (`RUANA_SCHEDULER_SA`) |
| Webhook Stripe | `stripe_webhook_bp` | Sin sesión; firma `Stripe-Signature` + rate limit |
| Mutaciones financieras | `@limit_financial_mutation` | 60/h + 15/min |

**Fallback verificado:** admin sin lista de permisos explícitos recibe `["leer","escribir","eliminar","configurar"]` en `_admin_permisos_efectivos()` — usado por el panel financiero. Distinto del endurecimiento de `require_admin_escritura` en el resto del panel.

**Excepción verificada:** `GET …/schema-health` en `financial_admin_bp` **no** lleva decorator de auth (cualquiera puede consultar el estado del esquema).

---

## 6. Flujos

### 6.1 Máquina de estados (FASE 01)

Estados canónicos en `core/financial/estados.py`. Transiciones en `state_machine.py`. Persistencia CAS:

```sql
UPDATE contactos_ruana SET estado_financiero = ?
WHERE id = ? AND estado_financiero = ?
```

Invariantes verificadas: conflicto abierto bloquea transferencia; `TRANSFERIDO` no vuelve a `TRANSFERENCIA_PENDIENTE`; estados cancelados no reactivan el flujo.

Tests: `tests/test_financial_state_machine.py`.

### 6.2 Ledger (FASE 08)

Doble partida append-only. Hooks en `financial_ledger_hooks.py` para pago confirmado, transfer (creada/completada/revertida), refund y disputa. Ajuste admin vía API ledger.

Inmutabilidad de asientos `POSTED`: triggers PostgreSQL en `20260818001300_financial_fase13_p0.sql`. Anulación por compensación `VOID_COMPENSATION`.

`financial_ledger_reconciliation_service` comprueba equilibrio y huérfanos; **no autocorrige**.

### 6.3 Reconciliación

| Capa | Servicio | Qué compara | ¿Mueve dinero? |
|------|----------|-------------|----------------|
| FASE 02 | `financial_reconciliation_service` | Contacto RUANA vs snapshot PI/transfer | No |
| FASE 03.2 | `transfer_reconciliation.py` | Transfer Stripe vs obligación | Solo cierra a `TRANSFERIDO` si `confirmed` |
| FASE 07 | `financial_reconciliation_advanced_service` | Cadena Stripe (PI, charge, transfer, refunds, disputes, fees) | No |

`transfer.created` **no** implica `TRANSFERIDO`. `transfer.paid` es camino **legacy** (`procesar_transfer_paid_legacy` en `stripe_transfer_events.py`); el flujo vigente exige reconciliación `confirmed`.

### 6.4 Conflictos internos (FASE 04)

Disputa **RUANA** contratante/profesional. Tabla `payment_conflicts` + evidencia/comentarios/acciones/auditoría.

Workflow: abrir → asignar → investigar → evidencias → resolver / escalar / cerrar.

Estado financiero del contacto: `CONFLICTO_ABIERTO`. Bloquea operaciones financieras mientras el conflicto no es terminal.

### 6.5 Reembolsos (FASE 05 + 10)

```text
GET  …/disponible/<contacto_id>
POST …/solicitar          → financial_action_approval (REFUND_EXECUTE)
POST …/aprobaciones/<id>/autorizar|rechazar
POST …/ejecutar           → Stripe Refund API (exige approval_id si RUANA_FINANCIAL_REQUIRE_APPROVAL=1)
```

Separación de funciones: 403 si el mismo admin autoriza su propia solicitud (`RUANA_FINANCIAL_ALLOW_SELF_APPROVAL` default `0`).

Causa `INDETERMINADO` bloquea la ejecución. También se puede ejecutar reembolso desde un conflicto resuelto.

### 6.6 Disputas Stripe (FASE 06)

Origen: webhooks `charge.dispute.created|updated|closed`. Estados internos en `dispute_estados.py` (`ABIERTO` → investigación/evidencia → `GANADA`/`PERDIDA` → `CERRADA`). Contacto → `DISPUTA_STRIPE`. Vinculación opcional a conflicto RUANA.

### 6.7 Automatización (FASE 11)

`POST /api/admin/financial-automation/ejecutar-ciclo` (también alias ES).

Ciclo: lease → detectores (webhooks atascados/fallidos, refunds, disputas, conflictos, transfers, ledger, discrepancias) → reconciliación opcional → `financial_automation_runs` + `financial_alerts`.

Despliegue Cloud Scheduler: **listo en código**; presencia real en GCP = `NO VERIFICADO`.

### 6.8 Panel admin (FASE 09)

Dashboard KPIs, alertas, listados (pagos, transfers, refunds, disputes, conflicts, reconciliation, ledger, webhooks, audit) y vista 360° `operation/<contacto_id>`. HTML: `/admin/finanzas` redirige al panel.

---

## 7. Integración Stripe Connect (pagos de encargo)

| Pieza | Evidencia |
|-------|-----------|
| Flag | `RUANA_STRIPE_PAYMENTS_ENABLED` (`stripe_client.py`) |
| Modo | `RUANA_STRIPE_MODE` (`test`\|`live`) resuelto en deploy por script; **no** hardcodeado a `test` en el workflow actual |
| Checkout / confirmar / estado | `pagos_bp` |
| Onboarding Connect | `POST /api/aliado/stripe/onboarding` |
| Webhook | `POST /api/stripe/webhook` |
| Reparto | `core/financial/money.py` — céntimos enteros; comisión runtime = `apoyo_pct/100` (12 % con config actual) |

Estado Live vs Test **en el servicio Cloud Run en este momento:** `NO VERIFICADO` (depende de `vars.RUANA_STRIPE_MODE` y del prefijo de `STRIPE_SECRET_KEY` en secretos. Hay commit `9b273d5` que habilita Live en el pipeline; no implica que Live esté activo ahora).

---

## 8. Qué no hace este subsistema (verificado)

- No sustituye el cobro manual Bizum/IBAN/QR (`pago_service` + `ruana_reglas_v1.json`).
- No aplica RLS a sus tablas (DDL sin `ENABLE ROW LEVEL SECURITY`).
- No existe FASE 12.
- No hay evidencia en el repo de que Cloud Scheduler FASE 11 esté desplegado en GCP.

---

*Inventario 2026-09-04. Si este documento diverge del código, prevalece el código.*
