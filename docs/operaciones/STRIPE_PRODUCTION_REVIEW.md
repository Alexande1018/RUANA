# Revisión Stripe — ¿listo para el primer cobro Live?

**Audiencia:** Alexander (product owner)  
**Fecha:** 2026-09-09  
**Alcance:** verificación en código y workflows del repo. **No** se ha inspeccionado el Dashboard de Stripe, los valores reales de GitHub Secrets ni el entorno Cloud Run en ejecución.

**Veredicto: go-with-caveats**

El cableado en código **existe y es coherente** (Checkout + Connect + webhook + ledger). **No** hay un `RUANA_STRIPE_MODE=test` hardcodeado en el deploy de producción (K-04 está obsoleto).  
**No pulses Live mañana.** El primer cobro real sigue bloqueado por configuración operativa y por riesgos que hay que comprobar en Test antes de conmutar.

---

## 1. Veredicto en una frase

| Pregunta | Respuesta |
|----------|-----------|
| ¿Stripe está implementado en el repo? | **Sí** — Connect Express + Checkout + Transfer diferida |
| ¿Producción cobra dinero real hoy? | **No** — el deploy **por defecto** deja `RUANA_STRIPE_MODE=test` |
| ¿Se puede activar Live sin reescribir código? | **Sí** — es un flip de secrets + variable + webhook Live |
| ¿El primer cobro Live es seguro ahora? | **No** — checklist de la §2 incompleto; hay riesgos de primer cobro (§5) |

---

## 2. Checklist antes del primer cobro Live

Haz esto **en orden**. No adelantes el paso 7 si falla alguno anterior.

### A. Completar en Stripe Dashboard (Live)

1. [ ] Cuenta plataforma verificada (KYC / business) y **charges + payouts** activos en Live.
2. [ ] Connect activado en Live (mismo modelo que Test: Express, país ES).
3. [ ] En **Connect → Onboarding options** (Live): no forzar `card_payments` si las cuentas Express solo reciben transferencias. Si el onboarding pide capacidades incompatibles con *recipient*, el aliado no termina el alta. Ver §5.1.
4. [ ] Crear endpoint webhook **Live** (no reutilizar el de Test):
   - URL: `https://ruana-4293f.web.app/api/stripe/webhook`  
     (Hosting reescribe todo a Cloud Run; también vale la URL directa de Cloud Run.)
   - Eventos **mínimos** que el código maneja (hay que suscribirlos; Stripe no los envía si no están en el endpoint):

     | Evento | Para qué |
     |--------|----------|
     | `checkout.session.completed` | Confirma cobro del cliente |
     | `checkout.session.expired` | Permite reintentar Checkout |
     | `payment_intent.succeeded` | Respaldo si falta el de Checkout |
     | `payment_intent.payment_failed` | Marca fallo pre-cobro |
     | `account.updated` | Actualiza `charges_enabled` / `payouts_enabled` del aliado |
     | `transfer.created` | Confirma Transfer al profesional |
     | `transfer.updated` | Snapshot / reversión |
     | `transfer.reversed` | Bloquea y marca revertida |
     | `charge.refunded` | Reembolsos |
     | `refund.updated` | Sync de refund existente |
     | `charge.dispute.created` / `.updated` / `.closed` | Disputas |

   - `transfer.paid` y `transfer.failed` son **legacy**; el código los acepta pero Stripe Connect moderno **no los emite**. No dependas de ellos.
5. [ ] Copiar el `whsec_...` **del endpoint Live** (es distinto del de Test).

### B. Completar en GitHub + deploy

6. [ ] Sustituir GitHub Secrets (los mismos nombres; **un solo juego**):
   - `STRIPE_SECRET_KEY` = `sk_live_...`
   - `STRIPE_PUBLISHABLE_KEY` = `pk_live_...`
   - `STRIPE_WEBHOOK_SECRET` = `whsec_...` del endpoint **Live**
7. [ ] **No** hagas push a `main` todavía. El siguiente deploy de preview (`deploy-firebase-preview.yml`) **escribe los mismos secretos GCP** (`ruana-stripe-secret-key`, etc.) y usa la **misma** `DATABASE_URL` de producción. Si metes claves Live y corre un preview, preview opera contra Stripe Live **y** la BD real.
8. [ ] Desplegar producción con Live de forma explícita:
   - Actions → **Deploy to Firebase** → `workflow_dispatch` → `ruana_stripe_mode=live`  
   - **o** `vars.RUANA_STRIPE_MODE=live` + `vars.RUANA_STRIPE_ALLOW_LIVE_PUSH=true` si quieres que los push a `main` también queden en Live.
9. [ ] El workflow **falla** si el modo no coincide con el prefijo de la clave (`sk_test_` ↔ test, `sk_live_` ↔ live). Eso es intencional.

### C. Humo en Test **antes** de Live (obligatorio)

Aún no habéis cerrado un cobro real. Haced **un encargo Test completo** con tarjetas de prueba:

10. [ ] Aliado profesional: onboarding Express → en Dashboard Test, anotar `charges_enabled`, `payouts_enabled` y `capabilities.transfers`. Si `charges_enabled=false` tras onboarding válido, **para**: el código no dejará cerrar el encargo (§5.1).
11. [ ] Contratante: acuerdo de precio → «Pagar ahora» → Checkout → pago OK.
12. [ ] Comprobar en BD / panel: `modo_pago=stripe`, `estado_pago=cobro_confirmado`, Apoyo 12 % calculado, profesional notificado.
13. [ ] Contratante confirma entrega → Transfer al Express → estado `TRANSFERIDO` (o `transfer_pendiente` breve y luego `TRANSFERIDO`).
14. [ ] En Stripe Test: el cobro está en la **cuenta plataforma**; el Transfer, en la cuenta Connect del profesional (no es destination charge).
15. [ ] Forzar un evento webhook (Dashboard → Send test webhook) y ver `stripe_webhook_events` en `completed`.

### D. Primer cobro Live (supervisado)

16. [ ] Un profesional **real** con Connect Live `listo` (cuenta + flags).
17. [ ] Encargo de importe pequeño, vosotros como contratante y profesional.
18. [ ] Tras el pago: no confirmar entrega hasta ver el PaymentIntent `succeeded` y el webhook `completed` en logs / `stripe_webhook_events`.
19. [ ] Confirmar entrega y vigilar el Transfer. Si falla por saldo, ver §5.2 (`source_transaction`).
20. [ ] Anotar fecha, IDs Stripe (`cs_`, `pi_`, `tr_`, `acct_`) y resultado. Actualizar [`fase-14-stripe-live.md`](fase-14-stripe-live.md).

---

## 3. Cómo está cableado (evidencia)

### 3.1 Flags y entorno

| Pieza | Qué hace el código | Evidencia |
|-------|--------------------|-----------|
| `RUANA_STRIPE_PAYMENTS_ENABLED` | El deploy de prod **siempre** pone `1`. Sin esto, Stripe está apagado. | `.github/workflows/deploy-firebase.yml` (`--set-env-vars` … `RUANA_STRIPE_PAYMENTS_ENABLED=1`) |
| `stripe_habilitado_global()` | Exige flag **y** `STRIPE_SECRET_KEY` + `STRIPE_WEBHOOK_SECRET` no vacíos | `pago_service.py` + `stripe_client.stripe_configured()` |
| `RUANA_STRIPE_MODE` | En prod es obligatorio (`test` \| `live`). Arranque falla si falta. | `startup_validation.py`, `stripe_mode_guard.py` |
| Resolución en deploy | 1) input `workflow_dispatch` → 2) `vars.RUANA_STRIPE_MODE` → 3) prefijo de `STRIPE_SECRET_KEY` → 4) `test` | `.github/scripts/resolve-stripe-mode.sh` |
| Coherencia modo ↔ clave | `test` exige `sk_test_`; `live` exige `sk_live_` | `validate-stripe-deploy-mode.sh` + `validate_stripe_key_prefix_at_runtime` |
| Live en push a `main` | Bloqueado salvo `vars.RUANA_STRIPE_ALLOW_LIVE_PUSH=true` **o** la secret ya es `sk_live_` | `resolve-stripe-mode.sh` |
| Modelo de cobro | **Separate charges and transfers**, no destination Checkout | `stripe_client.create_checkout_session` (sin `transfer_data`) + `create_transfer` posterior |

**K-04 (docs/KNOWN_ISSUES.md):** el texto antiguo decía que el workflow fija `RUANA_STRIPE_MODE=test`. **Eso ya no es cierto.** El workflow interpola `${{ steps.stripe_mode.outputs.mode }}`. Lo que **sí** sigue siendo cierto: si no configuráis nada, el default es **test**. Producción puede estar cobrando en Test aunque `RUANA_ENV=production`.

### 3.2 Camino de pago extremo a extremo

```
Negociación (precio aceptado)
    → si Stripe global ON y profesional listo:
         activar_pago_stripe_tras_acuerdo
         modo_pago=stripe, estado_pago=esperando_cobro_cliente
         congela importe + Apoyo 12 % / neto 88 %
    → si profesional NO listo: el acuerdo NO cierra
         (mensaje: «Este profesional está completando la activación…»)

Contratante POST /api/contactos/<id>/stripe/checkout
    → Checkout Session (EUR, metadata contacto_id)
    → redirect a checkout.stripe.com

Cliente paga
    → webhook checkout.session.completed (payment_status=paid)
       y/o payment_intent.succeeded (metadata tipo=encargo_ruana)
    → estado_pago=cobro_confirmado, estado=trabajo_en_progreso
    → ledger on_pago_confirmado + notificaciones

Contratante POST /api/contactos/<id>/stripe/confirmar-trabajo
    → Transfer del neto a la cuenta Express del profesional
    → TRANSFERIDO solo si el snapshot Stripe tiene
       balance_transaction + destination_payment (no basta transfer.created vacío)
```

Archivos: `negociacion_service.py` (`aceptar_negociacion`, `_aplicar_cierre_automatico_tras_acuerdo`), `pagos_bp.py`, `pago_service.py`, `financial_transfer_service.py`, `stripe_webhook_service.py`, `aliado-stripe-pagos-module.js`.

Comisión: `core/financial/money.py` — `COMISION_RUANA_PCT = 12` (céntimos enteros). El cliente paga el bruto; RUANA retiene el 12 % en la plataforma; el Transfer es el 88 %.

### 3.3 Webhook

| Tema | Estado | Evidencia |
|------|--------|-----------|
| Ruta | `POST /api/stripe/webhook` (sin sesión) | `stripe_webhook_bp.py` |
| Hosting | rewrite `**` → Cloud Run `ruana` | `firebase.json` |
| Firma | `Stripe-Signature` + `Webhook.construct_event` | `stripe_client.construct_webhook_event` |
| Sin header | HTTP 400 | `stripe_webhook_bp` |
| Firma inválida | HTTP 400, no reprocesa dinero | `signature_invalid` |
| Livemode ≠ `RUANA_STRIPE_MODE` | HTTP 400, alerta `stripe_livemode_mismatch` | `stripe_mode_guard.py` |
| Idempotencia | `INSERT OR IGNORE` / `ON CONFLICT DO NOTHING` en `stripe_webhook_events` | `stripe_webhook_repo.py`, `postgres_compat.py` |
| Reintento | `failed` se reclama de nuevo; `completed` → 200 duplicate | mismo repo |
| Error de handler | HTTP 500 + `retry: true` (Stripe reintenta) | `stripe_webhook_bp` |
| Rate limit | 60/min, 300/h **en memoria por instancia** | `financial_rate_limit.py`, K-07 |

Eventos no listados en `_HANDLERS` se ignoran con 200 (`ignored_unknown`). Si olvidas suscribir un evento en el Dashboard, RUANA no se entera: el cobro puede existir en Stripe y el encargo quedarse en `esperando_cobro_cliente`.

### 3.4 Secretos: de GitHub a Cloud Run

```
GitHub Secrets (STRIPE_*)
    → sync-stripe-secrets-gcp.sh
    → Secret Manager:
         ruana-stripe-secret-key
         ruana-stripe-publishable-key
         ruana-stripe-webhook-secret
    → Cloud Run --set-secrets …:latest
```

Riesgos:

- **Un solo secreto por nombre.** Test y Live no conviven. Al poner `sk_live_`, el siguiente sync **pisa** el `sk_test_` en GCP.
- Si el GitHub Secret está vacío, el script **avisa y sigue**; Cloud Run puede arrancar con un secreto GCP viejo (test) o vacío. Arranque en prod exige clave + webhook secret no débiles (`startup_validation.py`).
- **Preview usa los mismos secretos GCP y la misma `DATABASE_URL`.** No trates preview como sandbox de Live.
- Este review **no** ha leído los valores actuales. Hay que mirar en GitHub si hoy son `sk_test_` / `pk_test_` / `whsec_` de Test.

### 3.5 Connect (onboarding)

- Alta: `POST /api/aliado/stripe/onboarding` → `Account` Express `country=ES`, capability **solo** `transfers` (no `card_payments`) → Account Link.
- «Listo para cobrar»: `stripe_account_id` **y** `stripe_charges_enabled == 1` (`profesional_stripe_listo`).
- Sync: webhook `account.updated` + `GET /api/aliado/stripe/estado` (`retrieve_account`).
- Transfer: exige cuenta + `charges_enabled`; **no** exige `payouts_enabled` de forma explícita (`financial_transfer_service._validar_precondiciones`).

### 3.6 Pago manual vs Stripe

| Pregunta | Respuesta |
|----------|-----------|
| ¿Puede un encargo nuevo cerrarse en manual si Stripe está ON? | **No.** Tras acuerdo con precio, el único camino es Stripe. |
| ¿Si el profesional no ha terminado Connect? | El precio **no se acepta**. No hay fallback silencioso a Bizum/IBAN. |
| ¿Para qué sirve el pago manual? | Allowlist admin: mostrar IBAN/Bizum/QR a aliados concretos. No cierra encargos. |
| ¿Si faltan secretos Stripe en prod? | `stripe_habilitado_global()` es falso → el cierre automático **falla** (no cae a manual). Encargos nuevos con precio quedan bloqueados. |
| ¿Encargos viejos `modo_pago=manual`? | Siguen el flujo legacy; no se convierten solos. |

Conclusión: producción **no** se queda «solo manual» por accidente si el flag está a `1`. O Stripe funciona, o **no se puede cobrar el encargo**. El riesgo opuesto es más real: creer que hay un plan B manual y no haberlo.

---

## 4. K-04 y docs que mentían

| Doc | Antes | Ahora (verificado) |
|-----|--------|--------------------|
| `KNOWN_ISSUES.md` K-04 | «Cada deploy fija `RUANA_STRIPE_MODE=test`» | **Cerrado.** El modo se resuelve; default test si no hay vars/input. |
| `README.md` roadmap | «deploy fija test» | Alineado con resolución dinámica. |
| `fase-14-stripe-live.md` | Ya describía resolución B5 | Sigue vigente; este informe es el go/no-go de 2026-09-09. |
| `PROJECT_AUDIT.md` | «Stripe en prod = test hardcode» | Corregido a «default test, no hardcode». |

Tests que lo clavan: `tests/test_cicd_stripe_mode_b5.py`, `tests/test_sync_cron_secret_cicd_fase14.py`.

---

## 5. Huecos que pueden tumbar el primer cobro Live

Ordenados por probabilidad de romper el **primer** dinero real. No son refactors grandes; son comprobaciones (y un par de parches pequeños si el humo Test falla).

### 5.1 — Alto. «Profesional listo» usa `charges_enabled` con capability solo `transfers`

`create_connect_account` pide únicamente `transfers`. En Connect, una cuenta Express puede **recibir** Transfers con `charges_enabled=false` y `payouts_enabled=true`.

El código, en cambio, solo da por listo al profesional si `charges_enabled == 1`. Si tras el onboarding Live/Test ese flag queda en false, **ningún encargo con precio cierra**.

**Qué hacer:** en Dashboard, abrir una cuenta Express de prueba ya onboarded. Si `charges_enabled` es false y `payouts_enabled` / `transfers=active` son true, hay que cambiar el criterio (código + UI en `aliado-stripe-pagos-module.js`) **antes** de Live. No lo he cambiado en este PR: depende de vuestra cuenta Stripe.

### 5.2 — Alto. Transfer sin `source_transaction`

`create_transfer` mueve el neto desde el **saldo de la plataforma**, sin ligar el cargo del cliente (`source_transaction`). En una cuenta Live nueva el cobro suele estar *pending*; el Transfer puede fallar por saldo insuficiente.

Stripe documenta asociar el Transfer al charge para no adelantar fondos. El código no lo hace.

**Qué hacer:** en el humo Test, confirmar entrega en cuanto el cobro esté *pending* (no solo *available*). Si el Transfer falla, hay que pasar el `charge` del PaymentIntent a `create_transfer` antes de Live.

### 5.3 — Medio. Idempotency key de Checkout fija (`…-v1`)

`crear_checkout_stripe` usa `checkout-contacto-{id}-v1`. Si la sesión caduca (`checkout.session.expired` resetea BD) y el cliente vuelve a pagar, Stripe puede devolver **la sesión caducada**. Primer cobro en <24 h no suele picar; un abandono + reintento sí.

### 5.4 — Medio. `TRANSFERIDO` no es automático con `transfer.created` vacío

La API moderna no manda `transfer.paid`. La confirmación exige `balance_transaction` **y** `destination_payment` en el objeto Transfer. Si vienen vacíos, el encargo se queda en `TRANSFERENCIA_ENVIADA` hasta `transfer.updated` o el cron de automatización financiera.

Ese cron **no está verificado en GCP** (K-08). Para el primer Live: o el objeto Transfer ya trae esa evidencia (lo habitual), o hay que lanzar a mano `POST /api/admin/financial-automation/ejecutar-ciclo`.

### 5.5 — Medio. Webhook Live distinto + livemode guard

Si Cloud Run está en `live` y el endpoint sigue siendo el de Test (o al revés), cada evento se rechaza (`stripe_livemode_mismatch`) y el dinero **no** se refleja en RUANA. El cliente ya pagó.

### 5.6 — Bajo / operativo

- Rate limit del webhook en memoria (K-07): un burst de Stripe + 3 instancias Cloud Run puede 429; Stripe reintenta.
- Checkout no envía `customer_email` (UX, no bloqueo).
- `STRIPE_PUBLISHABLE_KEY` se sincroniza pero el cobro usa Checkout hosted (clave secreta). Igual hay que poner `pk_live_` al conmutar.
- URLs de retorno: `{RUANA_PUBLIC_APP_URL}/aliado.html?...` — Flask sirve `/aliado.html`; Hosting apunta a Cloud Run. OK en código.
- Preview + prod comparten secretos Stripe y Postgres.

---

## 6. Lista de arreglos (si algo bloquea)

Solo lo que es **objetivamente** necesario para Live. Sin refactors.

| Prioridad | Qué | Tipo | ¿Hecho en este PR? |
|-----------|-----|------|--------------------|
| P0 | Poner secrets Live + webhook Live + deploy `ruana_stripe_mode=live` | Operación (Dashboard + GitHub) | No — no se tocan secretos desde el repo |
| P0 | Humo Test E2E (onboarding → cobro → transfer) | Operación | No |
| P0 | Si Test muestra `charges_enabled=false` con transfers activos: aceptar `payouts_enabled` o `transfers=active` como «listo» | Código pequeño | No — falta evidencia de vuestra cuenta |
| P1 | Añadir `source_transaction` al Transfer si el humo falla por saldo | Código pequeño | No — no confirmar saldo real |
| P1 | Versionar la idempotency key de Checkout tras `session.expired` | Código pequeño | No — no bloquea el primer intento |
| P1 | Verificar Cloud Scheduler job financiero (K-08) | Operación GCP | No |
| Docs | Cerrar K-04 + alinear README / PROJECT_AUDIT | Docs | **Sí** |

**No** hace falta reescribir `pagos_bp`, el webhook ni el ledger para ir a Live.

---

## 7. Qué **no** se ha verificado (fuera de este repo)

- Valores actuales de `STRIPE_*` en GitHub / Secret Manager (test vs live).
- `vars.RUANA_STRIPE_MODE` y `RUANA_STRIPE_ALLOW_LIVE_PUSH` en el repositorio.
- `RUANA_STRIPE_MODE` efectivo en la revisión Cloud Run que está sirviendo ahora.
- Endpoint webhook Live creado y eventos suscritos.
- Ni un PaymentIntent / Transfer Live (confirmado por el encargo: cero cobros reales).
- Jobs de Cloud Scheduler desplegados.
- Compliance / T&C Connect / retención 6 años ([`docs/legal/politica-retencion-datos.md`](../legal/politica-retencion-datos.md) marca decisión fiscal pendiente).

---

## 8. Mensaje corto para el equipo

Stripe **está programado** (Connect Express, Checkout, webhook firmado, Apoyo 12 %, Transfer al profesional). El deploy **ya no fuerza Test**.  
El primer cobro Live **no** es un merge: es secrets Live + webhook Live + un humo Test extremo a extremo. Hasta que ese humo (sobre todo onboarding `charges_enabled` y el Transfer) no esté verde, **no conmutar**.
