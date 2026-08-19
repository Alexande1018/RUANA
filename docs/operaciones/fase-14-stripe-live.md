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

## Evidencia de configuración

En `.github/workflows/deploy-firebase.yml`, el despliegue Cloud Run incluye:

```text
RUANA_STRIPE_MODE=test
```

La barrera `core/stripe_mode_guard.py` rechaza eventos webhook cuyo `livemode` no coincide con `RUANA_STRIPE_MODE`. Con `test`, cualquier evento Live sería rechazado con `stripe_livemode_mismatch`.

## Cómo activar Live (fuera de alcance FASE 14)

1. Completar checklist de negocio y compliance Stripe.
2. Configurar secrets Live en GitHub (`STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, etc.).
3. Cambiar `RUANA_STRIPE_MODE=live` en el workflow de despliegue.
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
