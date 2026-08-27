# Estado Stripe Live — FASE 14

**Fecha de verificación:** 2026-08-19  
**Entorno producción:** Cloud Run `ruana` (europe-west1) + Firebase Hosting `ruana-4293f.web.app`

## Veredicto operativo

| Aspecto | Estado |
|--------|--------|
| Stripe **Test** | Activo en producción (`RUANA_STRIPE_MODE=test`) |
| Stripe **Live** | **BLOQUEADO** — no habilitado en despliegue |
| Transferencias Live reales | **No ejecutadas** en esta fase |
| Reembolsos Live reales | **No ejecutados** en esta fase |

## Configuración de modo (B5 — sin hardcode en workflow)

El despliegue **no** fija `RUANA_STRIPE_MODE=test` en el workflow. Se resuelve así:

| Origen | Prioridad |
|--------|-----------|
| Input `ruana_stripe_mode` en `workflow_dispatch` | 1 |
| Variable de repositorio `vars.RUANA_STRIPE_MODE` | 2 |
| Default `test` | 3 |

Antes de desplegar, `.github/scripts/validate-stripe-deploy-mode.sh` exige coherencia modo ↔ prefijo de `STRIPE_SECRET_KEY`.

**Salvaguarda:** `RUANA_STRIPE_MODE=live` en push automático a `main` falla salvo `vars.RUANA_STRIPE_ALLOW_LIVE_PUSH=true`.

## Cómo activar Live (fuera de alcance FASE 14)

1. Completar checklist de negocio y compliance Stripe.
2. Configurar secrets Live en GitHub (`STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, etc.).
3. Ejecutar deploy con `workflow_dispatch` y `ruana_stripe_mode=live` (o definir `vars.RUANA_STRIPE_MODE=live` + `vars.RUANA_STRIPE_ALLOW_LIVE_PUSH=true` si se desea en push).
4. Registrar endpoint webhook Live en Stripe Dashboard apuntando a `/api/stripe/webhook`.
5. Ejecutar smoke tests en Test antes de conmutar.
6. Documentar fecha de activación y primera transacción Live supervisada.

**No simular operatividad Live hasta completar los pasos anteriores.**

## Health checks post-despliegue (2026-08-19)

| URL | HTTP | Respuesta |
|-----|------|-----------|
| `https://ruana-288784334163.europe-west1.run.app/api/health` | 200 | `{"status":"healthy"}` |
| `https://ruana-4293f.web.app/api/health` | 200 | `{"status":"healthy"}` |

El fallo 429 en verificación automática post-deploy (FASE 13A) fue rate limiting del health check repetido, no fallo del despliegue. Los endpoints responden correctamente con petición única.
