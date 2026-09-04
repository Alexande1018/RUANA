# Auditoría completa del sistema de pagos RUANA

| Campo | Valor |
|-------|-------|
| Fecha | 2026-09-04 |
| Rama auditada | `main` @ `7ea0fa1` |
| Alcance | Cobro manual (Apoyo RUANA), Stripe Connect, máquina de estados, transferencias, webhooks, ledger, reembolsos, disputas, conflictos, admin financiero, frontend aliado/admin, tests y CI |
| Método | Lectura estática del código, migraciones, workflows, tests y documentación vigente. El código prevalece sobre la documentación. |
| Runtime / Stripe Live | **No ejecutado.** Análisis estático. Stripe Live sigue bloqueado en despliegue (FASE 14). |
| Tests de esta auditoría | **No reejecutados.** Cobertura inferida por inventario de `RUANA/tests/test_*financ*`, `test_*stripe*`, `test_*pago*` y E2E Playwright. |

**Etiquetas de evidencia**

| Etiqueta | Significado |
|----------|-------------|
| **Verificado** | Comprobado en archivo + línea o en documento vigente del repo |
| **Inferido** | Deducción con alta confianza a partir del código |
| **No verificado** | Requiere ejecución runtime, Stripe real o acceso a producción |

---

## 1. Veredicto ejecutivo

RUANA tiene un **sistema de pagos de dos vías** y un **stack financiero posterior al cobro notablemente maduro** (fases 01–14): máquina de estados, webhooks firmados e idempotentes, transferencias con reclamo atómico, ledger de partida doble, 4-ojos en reembolsos, conflictos, disputas, reconciliación y monitorización.

Eso **no equivale a un sistema de cobro listo para dinero real**.

| Pregunta | Respuesta |
|----------|-----------|
| ¿Se puede cobrar en Test? | **Sí, en código.** Checkout + webhook + retención + transfer. Flag `RUANA_STRIPE_PAYMENTS_ENABLED` activo en Cloud Run. |
| ¿Se cobra dinero real hoy? | **No.** `RUANA_STRIPE_MODE` default `test`; Live bloqueado salvo override explícito. **Verificado** en `docs/operaciones/fase-14-stripe-live.md`. |
| ¿El flujo post-acuerdo es Stripe o manual? | **Stripe es el camino válido.** Si el profesional no tiene Connect listo, el cierre con precio se **bloquea**. El Apoyo manual (Bizum/IBAN) sigue vivo como pipeline admin/E2E y respaldo. |
| ¿Hay doble cobro / doble transfer? | **Mitigado** con `UNIQUE(contacto_id)`, idempotency Stripe y webhook `event_id`. Residual: `STRIPE_EN_PROCESO` sin timeout. |
| ¿El ledger cuadra siempre? | **No garantizado.** Riesgo de doble asiento en refund (claves de idempotencia distintas) y cuentas de disputa que no se cierran. |
| ¿Un admin puede resolver un caso real end-to-end? | **Reembolso: sí** (con 4-ojos). **Liberar profesional tras conflicto: no orquestado.** **Disputa cerrada: no restaura `estado_financiero`.** |

**Conclusión:** el diseño financiero es sólido y está bien testeado a nivel unitario/contrato. Los riesgos que impiden tratarlo como “cerrado para Live” son de **coherencia dual (legacy vs canónico)**, **orquestación incompleta post-excepción**, **huecos contables** y **operación en Test**.

---

## 2. Mapa del sistema

### 2.1 Capas

```text
Aliado / Admin (HTML + JS vanilla)
    │
    ▼
Blueprints Flask
    pagos_bp, stripe_webhook_bp, contactos_bp, negociacion_bp,
    financial_{conflicts,refunds,disputes,reconciliation,ledger,admin,automation}
    │
    ▼
DBManager (fachada Campamento Base)
    │
    ▼
Services          Repos / money / state machine
    pago_service        pago_repo
    financial_*         financial_*_repo
    stripe_webhook      stripe_webhook_repo
    stripe_client       money.py (céntimos)
                        FinancialStateMachine
    │
    ▼
SQLite (CI/local)  |  Postgres Supabase (prod)
         + Stripe API (Checkout, Transfer, Refund, Dispute, Connect)
```

**Verificado** en `docs/ARCHITECTURE.md` y registro de blueprints en `web/app.py`.

### 2.2 Módulos clave

| Dominio | Service | Repo / motor | HTTP |
|---------|---------|--------------|------|
| Cobro / Apoyo / Checkout | `pago_service.py` | `pago_repo.py`, `money.py` | `pagos_bp.py`, `contactos_bp.py` |
| Estados canónicos | `financial_transaction_service.py` | `financial_transaction_repo.py`, `state_machine.py` | (hooks internos) |
| Transferencias | `financial_transfer_service.py` | `financial_transfer_repo.py`, `transfer_reconciliation.py` | `pagos_bp` confirmar-trabajo |
| Webhooks | `stripe_webhook_service.py` | `stripe_webhook_repo.py` | `stripe_webhook_bp.py` |
| Conflictos | `financial_conflict_service.py` | `financial_conflict_repo.py` | `financial_conflicts_bp.py` |
| Reembolsos | `financial_refund_service.py` | `financial_refund_repo.py` | `financial_refunds_bp.py` |
| Disputas | `financial_dispute_service.py` | `financial_dispute_repo.py` | `financial_disputes_bp.py` |
| Ledger | `financial_ledger_service.py` + hooks | `financial_ledger_repo.py` | `financial_ledger_bp.py` |
| Reconciliación | `financial_reconciliation(_advanced)_service.py` | repos FASE 02/07 | `financial_reconciliation_bp.py` |
| Admin / 4-ojos / jobs | `financial_admin/approval/automation/audit` | repos FASE 09–11 | `financial_admin_bp`, `financial_automation_bp` |

### 2.3 Dos verdades de estado

| Campo | Rol | Comentario |
|-------|-----|------------|
| `contactos_ruana.estado` | Encargo operativo | `trabajo_en_progreso`, `trabajo_cerrado`, `importe_en_disputa`… |
| `contactos_ruana.estado_pago` | **Legacy** de cobro | `esperando_cobro_cliente`, `cobro_confirmado`, `pendiente_pago`, `en_revision`, `pagado`… |
| `contactos_ruana.estado_financiero` | **Canónico** FASE 01 | `PAGO_PENDIENTE` … `TRANSFERIDO` + excepciones |
| `contactos_ruana.estado_transferencia` | Sub-estado del dinero | `RETENIDO`, `ENVIADA`, `COMPLETADA`… |
| `financial_transfers.estado` | Slot de transferencia | `RECLAMADA`, `STRIPE_EN_PROCESO`, `STRIPE_CREADA`, `FALLIDA` |

**Regla de diseño (Verificado):** trabajo entregado ≠ dinero transferido. `docs/flujos/financial-transaction-state-machine.md`.

---

## 3. Flujo A — Apoyo RUANA manual (Bizum / IBAN / Revolut)

### 3.1 Secuencia

```text
Importe acordado (o cierre admin deprecado)
        ↓
trabajo_cerrado + apoyo_ruana (12 %)
        ↓
estado_pago = pendiente_pago
        ↓
Profesional paga fuera de la app (Bizum/IBAN/QR)
        ↓
POST /api/contactos/<id>/comprobante-apoyo  →  en_revision
        ↓
Admin POST /api/admin/contactos/<id>/estado-pago
        ↓
pagado (score)  |  rechazado
```

**Verificado:** `contacto_service.registrar_importe_contacto`, `pago_service.subir_comprobante_apoyo_ruana`, `actualizar_estado_pago_contacto`, E2E `e2e/ruana-critical-flows.spec.js` (QA-20/21/22).

### 3.2 Estado de producto

Tras acuerdo bilateral en negociación, **el cobro manual ya no es camino válido** si Stripe no está listo:

```703:710:RUANA/core/services/negociacion_service.py
    # Seguridad: el cobro manual ya no es un camino válido tras acuerdo con precio.
    out['cierre_automatico'] = False
    out['cierre_aviso'] = pago_service.MSG_PROFESIONAL_STRIPE_NO_LISTO
```

`registrar_importe_contacto` queda como respaldo admin y está marcado deprecado. El pipeline manual **sigue operativo** en admin, notificaciones, storage y E2E.

### 3.3 Superficie HTTP (manual)

| Ruta | Auth | Rate limit | Notas |
|------|------|------------|-------|
| `GET /api/metodos-pago` | `@require_aliado` | No | Expone Bizum/IBAN/QR |
| `POST /api/admin/metodos-pago` | `@require_admin_escritura` | No | Persiste JSON en disco |
| `POST /api/admin/metodos-pago/qr-revolut` | admin escritura | No | Bucket `ruana-public` |
| `POST /api/contactos/<id>/comprobante-apoyo` | aliado | **No** | Bucket `ruana-comprobantes` |
| `POST /api/contactos/<id>/impugnar-apoyo` | aliado | **No** | Abre conflicto |
| `POST /api/admin/contactos/<id>/estado-pago` | admin escritura | `@limit_financial_mutation` | Aprueba/rechaza |

### 3.4 Hallazgos de esta vía

- **K-03 vigente:** IBAN y Bizum reales en `pago_service.py` (defaults) y `config/ruana_reglas_v1.json`. **Verificado.**
- Mensajes de notificación aún mencionan “PayPal” (`qr_paypal_path`) mientras el producto usa Revolut. **Verificado.**
- Uploads de comprobante e impugnación **sin rate limit financiero**. **Verificado.**
- E2E cubre este flujo; **no cubre Stripe**. **Verificado** en `e2e/ruana-critical-flows.spec.js`.

---

## 4. Flujo B — Stripe Connect (camino canónico)

Modelo: **separate charges and transfers**. RUANA cobra el bruto al contratante, retiene el 12 %, transfiere el 88 % al profesional Connect cuando el contratante confirma el trabajo.

### 4.1 Secuencia

```text
Acuerdo + profesional Connect listo
        ↓
activar_pago_stripe_tras_acuerdo
  estado=pendiente_de_pago
  estado_pago=esperando_cobro_cliente
  modo_pago=stripe
  precio congelado
        ↓
POST /api/contactos/<id>/stripe/checkout
  importe SOLO desde BD
  idempotency_key = checkout-contacto-{id}-v1
        ↓
Webhook checkout.session.completed / payment_intent.succeeded
        ↓
trabajo_en_progreso + cobro_confirmado
  estado_financiero → ESPERANDO_CONFIRMACION
        ↓
POST /api/contactos/<id>/stripe/confirmar-trabajo
  CAS: ESPERANDO_CONFIRMACION → LIBERACION_AUTORIZADA
  reclamo UNIQUE(contacto_id) en financial_transfers
  Transfer.create (idempotency_key=transfer-contacto-{id})
        ↓
TRANSFERENCIA_ENVIADA  (aún no TRANSFERIDO)
        ↓
Webhook transfer.created + evidencia
  (balance_transaction + destination_payment)
        ↓
TRANSFERIDO + score + notificación (una vez)
```

**Verificado:** `docs/flujos/financial-transfers.md`, `pago_service.py`, `financial_transfer_service.py`.

### 4.2 Dinero: 88 / 12

Fuente canónica Stripe y cierre acordado:

```11:62:RUANA/core/financial/money.py
COMISION_RUANA_PCT = 12
...
def comision_ruana_cents(importe_bruto_cents: int) -> int:
    return (int(importe_bruto_cents) * COMISION_RUANA_PCT) // 100
```

- Comisión por **truncamiento entero**, no `round`. Invariante `apoyo + neto == bruto`.
- Persistencia legacy: euros `REAL` con `Decimal` + `ROUND_HALF_UP`.
- Tests: `test_financial_money_fase14.py`.

**Segunda fuente:** `_get_apoyo_pct()` lee `ruana_reglas_v1.json` y usa `round(imp * pct / 100.0, 2)` en resoluciones admin y fallbacks de listados. Stripe **ignora** ese JSON (`_calcular_importes_stripe` descarta `db`).

Si alguien cambia `apoyo_pct` ≠ 12, los importes **divergen** entre Stripe, listados y resoluciones de conflicto.

### 4.3 Onboarding profesional

- `POST /api/aliado/stripe/onboarding` + `GET /api/aliado/stripe/estado`.
- “Listo” = `stripe_account_id` + `stripe_charges_enabled`.
- Se lee `stripe_payouts_enabled` pero **no se exige** antes de transferir. Una cuenta que cobra y no puede recibir payouts puede llegar a `Transfer.create` y fallar tarde.

### 4.4 Frontend aliado

`aliado-stripe-pagos-module.js`:

- Checkout y confirmación de trabajo.
- Desglose 12 % en HTML.
- `stripePagosActivos()` **siempre retorna `true`** — no consulta el flag de backend. **Verificado** líneas 18–20.
- Contratos estáticos en `test_aliado_payment_frontend_contract.py` (labels, auth headers, no mostrar “pendiente” si `cobro_confirmado`).

El panel aliado **sigue exponiendo** el modal de Apoyo manual (Bizum primero). Convivencia de dos UX.

### 4.5 Timeout sin confirmación

`procesar_timeouts_sin_confirmacion_stripe` (default 12 días, `RUANA_STRIPE_TRANSFER_TIMEOUT_DAYS`). Se dispara como *side-effect* de `GET /api/aliado/datos`, no solo por cron. **Inferido:** carga extra en el hot path del panel; el SQL es idempotente.

---

## 5. Transferencias: idempotencia, concurrencia, huecos

### 5.1 Controles (bien resueltos)

| Capa | Mecanismo | Evidencia |
|------|-----------|-----------|
| Una transfer por encargo | `UNIQUE(contacto_id)` | `financial_transfers` |
| Misma llamada Stripe | `idempotency_key=transfer-contacto-{id}` | `financial_transfer_service.py` |
| Un hilo llama a Stripe | CAS `RECLAMADA → STRIPE_EN_PROCESO` | `financial_transfer_repo.py` |
| API no cierra el dinero | Nunca marca `TRANSFERIDO` | tests FASE 03 |
| Efectos post-pago | `efectos_post_transfer_aplicados` | score/notif una vez |
| Webhook | `UNIQUE(stripe_event_id)` + reclaim failed/stuck | FASE 02 |

### 5.2 `STRIPE_EN_PROCESO` sin reclaim

`intentar_reintentar_stripe` **solo** resetea `FALLIDA`. Si el proceso muere entre el commit de `STRIPE_EN_PROCESO` y `marcar_stripe_creada`, la API responde `transferencia_en_proceso` de forma indefinida.

Hay mitigación parcial: un webhook `transfer.created` posterior puede completar el flujo si Stripe sí creó la transfer. Si Stripe **no** llegó a crear nada, el encargo queda bloqueado hasta intervención.

Ya hubo operación de reparación en `main` (`0e0cbc2` encargo #72: secuencia `financial_transfers.id` + backfill de `estado_pago`). El hueco de timeout **sigue en código**.

### 5.3 Precondiciones vs máquina de estados

`_validar_precondiciones` admite `PAGO_CONFIRMADO` y `TRABAJO_EN_CURSO`, pero `FinancialStateMachine` no permite saltar desde ahí a `TRANSFERENCIA_*`. Validación HTTP puede pasar y fallar después al registrar pendiente/enviada.

### 5.4 Reversión post-`TRANSFERIDO`

Alerta crítica + discrepancia. Score y notificación **no se revierten**. Correcto como política conservadora; exige playbook admin. **Verificado** en `stripe_transfer_events.py` y docs de transferencias.

---

## 6. Webhooks Stripe

Endpoint: `POST /api/stripe/webhook`.

### 6.1 Seguridad (sólida)

1. Sin `Stripe-Signature` → 400.
2. `stripe.Webhook.construct_event` + `STRIPE_WEBHOOK_SECRET`.
3. Guard de `livemode` vs `RUANA_STRIPE_MODE`.
4. Rate limit `300/hour; 60/minute`.
5. Firma inválida → 400; error reprocesable → 500 (Stripe reintenta).

### 6.2 Eventos registrados

| Evento | Rol |
|--------|-----|
| `checkout.session.completed` | Confirma cobro |
| `payment_intent.succeeded` | Idem si no procesado |
| `payment_intent.payment_failed` | `PAGO_FALLIDO` si pre-pago |
| `checkout.session.expired` | Reset checkout |
| `account.updated` | Flags Connect |
| `transfer.created` | **Camino moderno** → snapshot + reconciliación |
| `transfer.updated` | Snapshots / discrepancias |
| `transfer.reversed` | Bloqueo + alerta |
| `transfer.paid` | **Legacy:** confirma sin exigir evidencia |
| `transfer.failed` | **Legacy** |
| `charge.refunded` / `refund.*` | Reembolsos |
| `charge.dispute.*` | Disputas |

### 6.3 Inconsistencia operativa

El código y `docs/flujos/financial-transfers.md` dicen **no configurar** `transfer.paid` / `transfer.failed` en el endpoint moderno. Los handlers **siguen registrados**. Si el Dashboard los envía, `transfer.paid` puede marcar `TRANSFERIDO` **sin** `balance_transaction` + `destination_payment`.

Comentarios obsoletos en `pago_service.py` y `financial_transaction_service.py` aún afirman que `TRANSFERIDO` solo llega por `transfer.paid`.

### 6.4 Reclaim de eventos

- `failed` → se reclama y reprocesa.
- `processing` atascado → reclaim tras `RUANA_WEBHOOK_PROCESSING_STUCK_MINUTES` (default 120).
- `completed` → `duplicate: true`, HTTP 200.

Mejor resuelto que el stuck de transferencias API.

---

## 7. Máquina de estados e invariantes

Estados normales: `PAGO_NO_INICIADO → PAGO_PENDIENTE → PAGO_CONFIRMADO → TRABAJO_EN_CURSO → TRABAJO_ENTREGADO → ESPERANDO_CONFIRMACION → LIBERACION_AUTORIZADA → TRANSFERENCIA_PENDIENTE → TRANSFERENCIA_ENVIADA → TRANSFERIDO`.

Excepciones: `PAGO_FALLIDO`, `PAGO_CANCELADO`, `CONFLICTO_ABIERTO`, `REEMBOLSO_*`, `DISPUTA_STRIPE`, `TRANSFERENCIA_FALLIDA/REVERTIDA`, `CANCELADO`, `MIGRACION_PENDIENTE`.

**Invariantes (Verificado en `modelo.py`):** importes ≥ 0; `comision + profesional == bruto`; reembolsos ≤ bruto; conflicto bloquea transfer; `TRANSFERIDO` no vuelve a pendiente; importe inmutable tras pago confirmado.

**CAS:** `UPDATE ... WHERE estado_financiero = ?` esperado.

### 7.1 Mapeo legacy problemático (manual)

| `estado_pago` | `estado_financiero` inferido | Problema |
|---------------|------------------------------|----------|
| `pendiente_pago` | `PAGO_CONFIRMADO` | El profesional **aún no pagó** a RUANA |
| `en_revision` | `PAGO_CONFIRMADO` | Comprobante sin validar |
| `pagado` | `PAGO_CONFIRMADO` | No distingue de los anteriores |

**Verificado** en `mapeo_legacy.py` 63–71. En contactos sin backfill de `estado_financiero`, la capa canónica **sobreestima** que el dinero está confirmado.

Stripe mapea mejor (`esperando_cobro_cliente` → `PAGO_PENDIENTE`, `cobro_confirmado` → `ESPERANDO_CONFIRMACION`).

---

## 8. Conflictos, reembolsos y disputas

### 8.1 Conflictos (FASE 04)

Apertura idempotente; estados `ABIERTO / EN_INVESTIGACION / PENDIENTE_DE_EVIDENCIA / ESCALADO` bloquean finanzas. Resolución (`LIBERAR_PROFESIONAL`, `REEMBOLSAR_*`, `DIVIDIR_IMPORTE`, …) deja `orden_financiera_pendiente=True` y **no ejecuta** transfer ni refund.

Endpoints legacy `POST /api/admin/payment-conflicts/.../resolver` y `.../conflictos-pago/.../resolver` responden **410**. El segundo **no exige auth admin** (solo rate limit): filtra información de deprecación. **Verificado** `pagos_bp.py` 150–162.

### 8.2 Reembolsos (FASE 05) — 4-ojos

```text
solicitar → autorizar (otro admin) → ejecutar (approval_id)
```

Default `RUANA_FINANCIAL_REQUIRE_APPROVAL=1`. Auto-aprobación off. TTL 72 h.

Bloqueos: disputa abierta, conflicto abierto (salvo ejecución ligada a conflicto resuelto), estados `TRANSFERENCIA_ENVIADA / TRANSFERIDO / TRANSFERENCIA_REVERTIDA`.

**Hueco de importe disponible:** `sum_confirmados` y `sum_pendientes` comparten `STRIPE_PROCESSING` y `PENDING_RECONCILIATION`. La fórmula `disponible = cobrado - confirmados - pendientes` **resta dos veces** esos estados. **Verificado** `financial_refund_repo.py` 77–107.

**Hueco ledger:** la ejecución admin llama `on_refund_succeeded` con `idempotency_key=stripe_idem`; el webhook usa `ledger-{idem}`. Son claves distintas → el ledger **puede asentar el refund dos veces**. **Verificado** `financial_refund_service.py` 452–461 vs 534–542.

### 8.3 Disputas / chargebacks (FASE 06)

Ingesta por webhook. Admin puede investigar, adjuntar evidencia y enviarla a Stripe.

Al crear: `estado_financiero → DISPUTA_STRIPE`, ledger `DISPUTE_OPENED` (DR `DISPUTE_PAYABLE` / CR `FUNDS_HELD`).

Al cerrar:

- `lost`: DR `DISPUTE_LOSS` / CR `STRIPE_BALANCE` — **no cierra** `DISPUTE_PAYABLE` / `FUNDS_HELD` de la apertura.
- `won`: DR `STRIPE_BALANCE` / CR `FUNDS_HELD` — **incrementa** `FUNDS_HELD` en lugar de revertir la apertura.
- **No** restaura `estado_financiero` histórico. El contacto puede quedar en `DISPUTA_STRIPE` para siempre.

**Verificado** `financial_ledger_service.py` 472–551 y `financial_dispute_service.py` cierre.

---

## 9. Ledger (FASE 08)

Partida doble, cuentas explícitas, estados `DRAFT / POSTED / VOIDED`. Publicación exige `debe == haber`, ≥ 2 líneas, moneda uniforme. Corrección por compensación, no edición.

Cadena de cobro: `PAYMENT_RECEIVED → PAYMENT_SETTLED → OBLIGATION_RECOGNIZED` (+ fee Stripe opcional).

Fortalezas: idempotencia por key, hooks con alerta `ledger_hook_fallido`, triggers de inmutabilidad en **Postgres** (FASE 13A). SQLite se apoya en la aplicación.

Debilidades ya citadas (refund doble, disputa abierta sin cierre) más:

- Ajuste y anulación de ledger (`LEDGER_ADJUST` / `LEDGER_VOID`) **sin 4-ojos**. La constante `ACTION_LEDGER_ADJUST` existe y **no está cableada**.
- `anular_transaccion` hace `commit` antes de publicar la compensación → ventana si falla el segundo paso.
- Panel admin de auditoría lee `audit_log` legacy, no `financial_audit_log`.

---

## 10. Admin financiero, permisos y automatización

### 10.1 Panel

`admin-financial-module.js` consume APIs agregadas: pagos, transfers, refunds, disputas, conflictos, reconciliación, ledger, webhooks, auditoría, alertas. Es **lectura + cierre de alertas**, no un workflow único de resolución.

### 10.2 Permisos

Catálogo FASE 10 (`financial.refund.*`, `financial.dispute.*`, `financial.ledger.*`, …). Mutaciones: deny-by-default si la lista de permisos está vacía.

**Asimetría:** el panel usa fallback amplio (`leer/escribir/eliminar/configurar`) si el admin autenticado no tiene permisos explícitos. Un viewer de panel puede ser más potente que el modelo granular. Resolver alertas exige solo `DASHBOARD_VIEW`.

### 10.3 Automatización (FASE 11)

Jobs de **detección**, no de movimiento de dinero: webhooks atascados, refunds stale, deadlines de disputa, conflictos viejos, transfers revertidas, ledger descuadrado, discrepancias.

Auth cron: `X-Ruana-Cron-Secret` o OIDC (`RUANA_SCHEDULER_SA`). Documentado en `cloud_scheduler_jobs.md`. **Despliegue real del Scheduler: No verificado** (K-08).

Rate limits financieros en memoria (`memory://`): no se comparten entre instancias Cloud Run (K-07).

---

## 11. Seguridad (corte pagos)

| Riesgo | Severidad | Estado |
|--------|-----------|--------|
| Webhook sin firma | Crítico si existiera | **Mitigado** |
| Livemode mismatch | Alto | **Mitigado** |
| IDOR checkout / confirmar / conflicto | Alto | **Mitigado** (código de participante) |
| Login aliado factor único (código 5 dígitos) | Alto | **Abierto** (K-01) — compromete Checkout y confirmación |
| IBAN/Bizum en git | Alto | **Abierto** (K-03) |
| Stripe Live no activo | Alto (negocio) | **Diseño actual** (FASE 14) |
| Service role elude RLS | Alto | **Diseño** (K-02) |
| Endpoint 410 sin auth | Bajo | Expone paths canónicos |
| Upload comprobante sin rate limit | Medio | Abierto |
| `except Exception: pass` en score post-pago | Medio | Score puede no aplicarse en silencio (`pago_service.py` ~496, ~951) |
| Health check no toca Stripe/BD | Medio | K-09 |

---

## 12. Frontend y E2E

| Superficie | Qué cubre | Hueco |
|------------|-----------|-------|
| `aliado-stripe-pagos-module.js` | Checkout, confirmar, onboarding, desglose | Flag Stripe hardcodeado a `true` |
| Modal Apoyo (`aliado.html` + alertas) | Bizum / Revolut / IBAN + comprobante | Convive con el bloqueo de cierre Stripe |
| `admin-financial-module.js` | Panel FASE 09 | No orquesta refund/transfer post-conflicto |
| Contratos JS pytest | Auth headers, labels, estados visibles | No ejecutan Stripe |
| Playwright | Encargo → comprobante → aprobar/rechazar admin, impugnación | **Cero escenarios Checkout/Transfer/webhook** |

Para dinero real, la ausencia de E2E Stripe (aunque sea contra stripe-mock) es el mayor hueco de QA.

---

## 13. Tests y CI

CI **automático** en push/PR a `main` y `dev` (`.github/workflows/ruana-qa.yml`). Precondición Campamento Base **cumplida**. Pytest en SQLite; E2E solo en push.

Inventario de tests del dominio (conteo de `def test_` / `class Test`, **Inferido** por grep):

| Área | Archivos representativos | Tests ≈ |
|------|--------------------------|---------|
| Máquina de estados | `test_financial_state_machine.py` | 18 |
| Webhooks | `test_stripe_webhooks_fase02.py` + firma/retry/pg | 48 |
| Transfers 03 / 03.1 / 03.2 | `test_financial_transfers_fase03*.py` | 44 |
| Conflictos | `test_financial_conflicts_fase04*.py` | 40 |
| Refunds | `test_financial_refunds_fase05.py` | 25 |
| Disputas | `test_financial_disputes_fase06.py` + state machine | 24+ |
| Reconciliación | `test_financial_reconciliation_fase07.py` | 29 |
| Ledger | `test_financial_ledger_fase08.py` | 27 |
| Admin / seguridad / automation | fases 09–11, 13A, 14 | ~90 |
| Money / rate limit / Stripe obligatorio | fase 14 + `test_stripe_*` | ~27 |
| Frontend contrato + misión bp | `test_aliado_payment_*`, `test_mision_pagos_*` | ~10 |

**Fortaleza:** el núcleo financiero tiene más tests que la mayoría de dominios RUANA.

**Límites:** CI no habla con Stripe ni Postgres; no hay prueba de doble asiento refund; no hay prueba de reclaim `STRIPE_EN_PROCESO`; no hay E2E Connect.

---

## 14. Configuración y producción

| Variable | Default / prod | Efecto |
|----------|----------------|--------|
| `RUANA_STRIPE_PAYMENTS_ENABLED` | `0` local; **`1` en Cloud Run** | Activa Checkout |
| `RUANA_STRIPE_MODE` | default `test` | Live exige override + `RUANA_STRIPE_ALLOW_LIVE_PUSH` |
| `STRIPE_SECRET_KEY` / `WEBHOOK_SECRET` / `PUBLISHABLE_KEY` | secrets | Obligatorios si Stripe on |
| `STRIPE_API_VERSION` | `2024-11-20.acacia` | |
| `RUANA_STRIPE_TRANSFER_TIMEOUT_DAYS` | 12 | Conflicto por no confirmación |
| `RUANA_WEBHOOK_PROCESSING_STUCK_MINUTES` | 120 | Reclaim webhook |
| `RUANA_FINANCIAL_REQUIRE_APPROVAL` | `1` | 4-ojos refund |
| `RUANA_FINANCIAL_ALLOW_SELF_APPROVAL` | `0` | |
| `RUANA_FINANCIAL_APPROVAL_TTL_HOURS` | 72 | |

Deploy valida coherencia `sk_test_` / `sk_live_` (`validate-stripe-deploy-mode.sh`). **Verificado.**

---

## 15. Catálogo de hallazgos

Severidad: **P0** bloquea dinero seguro en Live · **P1** error financiero o contable probable · **P2** coherencia / operación · **P3** higiene.

### P0 — no activar Live hasta resolver o aceptar explícitamente

| ID | Hallazgo | Evidencia |
|----|----------|-----------|
| P0-1 | Stripe Live bloqueado; no hay transacción real supervisada | `docs/operaciones/fase-14-stripe-live.md` |
| P0-2 | Login aliado = código de 5 dígitos. Quien lo tenga confirma trabajo y dispara transfer | K-01, `pagos_bp` confirmar-trabajo |
| P0-3 | Datos bancarios RUANA en repositorio | `pago_service.py` 59–61, `ruana_reglas_v1.json` |

### P1 — integridad de dinero o libros

| ID | Hallazgo | Evidencia |
|----|----------|-----------|
| P1-1 | Doble asiento ledger en refund (keys distintas API vs webhook) | `financial_refund_service.py` 460 vs 542 |
| P1-2 | `STRIPE_EN_PROCESO` sin timeout/reclaim | `financial_transfer_repo.py` 62–76 |
| P1-3 | Cuentas `DISPUTE_PAYABLE` / `FUNDS_HELD` no se cierran al ganar/perder | `financial_ledger_service.py` 489–547 |
| P1-4 | Tras `charge.dispute.closed` no se restaura `estado_financiero` | `financial_dispute_service.py` ~368–404 |
| P1-5 | Comisión dual: `money.COMISION_RUANA_PCT=12` vs `apoyo_pct` JSON + `round` | `money.py`, `pago_service.py` 30–40, 309–310, 693–696 |
| P1-6 | Disponible de refund resta dos veces estados compartidos | `financial_refund_repo.py` 83 y 99 |
| P1-7 | Ajuste/void de ledger sin 4-ojos | `financial_ledger_bp` + `ACTION_LEDGER_ADJUST` sin uso |
| P1-8 | `LIBERAR_PROFESIONAL` no dispara transfer | `financial_conflict_service.resolver_conflicto` |

### P2 — operación y coherencia

| ID | Hallazgo | Evidencia |
|----|----------|-----------|
| P2-1 | `transfer.paid` legacy activo pese a “no configurar” | `_HANDLERS` en `stripe_webhook_service.py` |
| P2-2 | Manual `pendiente_pago` → `PAGO_CONFIRMADO` | `mapeo_legacy.py` 66–71 |
| P2-3 | Validación transfer admite estados que la SM rechaza | `financial_transfer_service.py` ~535 |
| P2-4 | No se exige `stripe_payouts_enabled` | misma validación ~502–507 |
| P2-5 | `stripePagosActivos()` siempre `true` en frontend | `aliado-stripe-pagos-module.js` 18–20 |
| P2-6 | Timeout Stripe en `GET /api/aliado/datos` | `aliado_bp.py` ~127 |
| P2-7 | Checkout: `reclamar_checkout_stripe` es SELECT, no lock | `pago_repo.py` ~551 |
| P2-8 | Panel audit no lee `financial_audit_log` | `financial_admin_service.py` ~492 |
| P2-9 | Fallback de permisos del panel más laxo que mutaciones | `auth_decorators.py` 57–63 |
| P2-10 | Endpoint 410 de conflictos sin `@require_admin` | `pagos_bp.py` 150–152 |
| P2-11 | Uploads de comprobante/impugnación sin rate limit | `contactos_bp.py` |
| P2-12 | Comentarios “solo transfer.paid” obsoletos | `pago_service.py` ~965 |
| P2-13 | `resumen_stripe_admin` trata cualquier `transfer_id` como “completada” | `pago_service.py` 1248–1249 (y duplicado 1315–1316) |
| P2-14 | Sin E2E Stripe | `e2e/ruana-critical-flows.spec.js` |
| P2-15 | Cron financiero: código sí, Scheduler en GCP **No verificado** | K-08 |
| P2-16 | `tabla_existe` vía `sqlite_master` en repos financieros | refund/dispute/ledger repo — riesgo en Postgres |

### P3 — higiene

| ID | Hallazgo | Evidencia |
|----|----------|-----------|
| P3-1 | `_stripe_onboarding_estado` y `resumen_stripe_admin` definidos **dos veces** | `pago_service.py` 1213–1277 y 1280–1344 |
| P3-2 | Columna `ingresos_ruana.apoyo_ruana_2pct` (nombre 2 %, valor 12 %) | `pago_repo.py` |
| P3-3 | Texto “PayPal” en notificaciones / config | `pago_service.py` 43–49 |
| P3-4 | Resolvers legacy de conflicto siguen en `pago_service` (HTTP 410) | código muerto parcial |
| P3-5 | `importe_bd_a_cents(int)` trata el int como **euros** (`500` → `50000`) | `money.py` 23–24 |
| P3-6 | `conn` sin init en `impugnar_apoyo_ruana` → posible `UnboundLocalError` | `pago_service.py` 583–585 |
| P3-7 | Score envuelto en `except Exception: pass` | `pago_service.py` |
| P3-8 | Docs de flujos existen; comentarios internos a veces desactualizados | `docs/flujos/financial-*.md` |

---

## 16. Completitud operacional (casos reales)

| Caso | ¿Cerrable hoy? | Condición |
|------|----------------|-----------|
| A. Encargo Stripe feliz (Test) | Sí, en código | Connect listo + webhooks `transfer.created/updated/reversed` |
| B. Apoyo manual + aprobación admin | Sí | Cubierto por E2E |
| C. Profesional sin Stripe tras acuerdo | **Bloqueado** | No hay fallback automático |
| D. Reembolso por conflicto (antes de transfer) | Sí | 4-ojos + API |
| E. Reembolso después de transfer | **No** | Bloqueado a propósito |
| F. Liberar profesional tras conflicto | **Manual** | Flag pendiente; hay que usar flujo de transfer aparte |
| G. Chargeback Stripe | Parcial | Ingesta y evidencia sí; estado y ledger incompletos |
| H. Crash a mitad de `Transfer.create` | Parcial | Webhook puede salvar; si no hay transfer, atasco |
| I. Live money | **No** | FASE 14 |

---

## 17. Recomendaciones (prioridad, no calendario)

1. **No conmutar Live** hasta P0-2/P0-3 aceptados por negocio y P1-1/P1-2/P1-3 parcheados o monitorizados.
2. Unificar clave de idempotencia ledger de refunds (misma key en API y webhook).
3. Reclaim de `STRIPE_EN_PROCESO` con TTL (espejo del webhook stuck).
4. Asientos de cierre de disputa que reviertan `DISPUTE_PAYABLE`/`FUNDS_HELD` + restaurar `estado_financiero`.
5. Una sola fuente de comisión (`money.COMISION_RUANA_PCT`); deprecar `apoyo_pct` o hacerlo leer el mismo entero.
6. Configurar en Stripe Dashboard solo `transfer.created`, `transfer.updated`, `transfer.reversed` (+ cobro, refund, dispute, `account.updated`). No `transfer.paid`.
7. Orquestar `orden_financiera_pendiente` (transfer o refund) o documentarlo como paso admin obligatorio en el panel.
8. E2E mínimo contra stripe-mock: checkout → webhook cobro → confirmar → webhook transfer → `TRANSFERIDO`.
9. Quitar IBAN/Bizum del git; secretos + rotación.
10. Eliminar funciones duplicadas al final de `pago_service.py` y ajuste de `sum_*` de refunds.

---

## 18. Campamento Base (esta entrega)

Esta orden es **auditoría documental**, no cambio de comportamiento.

| Casilla | Estado |
|---------|--------|
| Tests existentes en verde en CI | CI automático vigente en `ruana-qa.yml`; esta rama no modifica código de dominio |
| Lógica nueva con test nuevo | No aplica — sin cambio funcional |
| Extracción de dominio | **No extraído.** No se tocó `DBManager` ni se movió método de pago. Extraer en una auditoría aumentaría riesgo sin test nuevo de comportamiento. |
| Fachada DBManager | Intacta |
| Alcance | Solo informe + enlace en índice de docs |

`Campamento Base: no se extrajo porque el comportamiento no estaba siendo modificado y la orden no requería cambio de código de dominio.`

---

## 19. Archivos de referencia rápida

| Ruta | Para qué |
|------|----------|
| `RUANA/core/services/pago_service.py` | Cobro manual + Checkout + fachada webhook |
| `RUANA/core/financial/money.py` | 12 % en céntimos |
| `RUANA/core/financial/state_machine.py` | Transiciones legales |
| `RUANA/core/financial/mapeo_legacy.py` | Dualidad de estados |
| `RUANA/core/services/financial_transfer_service.py` | Liberación |
| `RUANA/core/services/stripe_webhook_service.py` | Despacho eventos |
| `RUANA/core/services/financial_ledger_service.py` | Libros |
| `RUANA/core/services/financial_refund_service.py` | Reembolsos |
| `RUANA/web/blueprints/pagos_bp.py` | API aliado/admin de cobro |
| `docs/flujos/financial-*.md` | Diseño de fases 01–03 |
| `docs/operaciones/fase-14-stripe-live.md` | Live bloqueado |
| `docs/KNOWN_ISSUES.md` | K-01, K-03, K-04/FASE 14, K-07, K-08 |

---

*Informe generado por auditoría estática del 2026-09-04. Cualquier transacción Live, saldo Stripe o job de Cloud Scheduler citado como “No verificado” debe confirmarse en consola GCP/Stripe antes de usarlo como evidencia operativa.*
