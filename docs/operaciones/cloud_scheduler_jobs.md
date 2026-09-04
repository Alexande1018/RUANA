# Cloud Scheduler — jobs operativos RUANA

Despliegue objetivo: **Google Cloud Run** (servicio Flask). Los cron jobs **no** corren dentro del contenedor; Cloud Scheduler invoca endpoints HTTP protegidos.

## Autenticación

Configura en el servicio Cloud Run (y en `.env` local si pruebas):

```bash
RUANA_CRON_SECRET=<valor-aleatorio-largo>
```

Cada petición del scheduler debe autenticarse de **una** de estas formas (verificado en `auth_decorators._cron_secret_valid()`):

1. Header `X-Ruana-Cron-Secret: <valor-aleatorio-largo>`
2. **OIDC Bearer** de Google: `Authorization: Bearer <id_token>` cuyo `email` coincide con `RUANA_SCHEDULER_SA` y `email_verified` es verdadero. Deploy fija `RUANA_SCHEDULER_SA=ruana-scheduler-invoker@ruana-4293f.iam.gserviceaccount.com`.

Los endpoints aceptan **sesión admin con escritura** **o** cron válido (secreto u OIDC).

Despliegue real de los jobs en GCP: **NO VERIFICADO** en esta auditoría (el script de provisionamiento existe; no se ha listado Scheduler).

Base URL de producción: sustituye `https://<tu-servicio>-<hash>-ew.a.run.app` por la URL real del servicio Cloud Run.

---

## Job 1 — Finalizar competencias vencidas

| Campo | Valor |
| --- | --- |
| Nombre sugerido | `ruana-finalizar-competencias-vencidas` |
| Frecuencia | `0 6 * * *` (diario 06:00 UTC) o cada 6 h: `0 */6 * * *` |
| URL | `https://<CLOUD_RUN_URL>/api/competencia/finalizar-vencidas` |
| Método | `POST` |
| Headers | `X-Ruana-Cron-Secret: <RUANA_CRON_SECRET>` |
| Body | vacío o `{}` |

---

## Job 2 — Purga mensual de calidad

| Campo | Valor |
| --- | --- |
| Nombre sugerido | `ruana-purga-mensual` |
| Frecuencia | `0 5 1 * *` (día 1 de cada mes, 05:00 UTC) |
| URL | `https://<CLOUD_RUN_URL>/api/purga/mensual` |
| Método | `POST` |
| Headers | `X-Ruana-Cron-Secret: <RUANA_CRON_SECRET>` |
| Body | vacío o `{}` |

---

## Job 3 — Motor de evaluación periódico

| Campo | Valor |
| --- | --- |
| Nombre sugerido | `ruana-motor-evaluacion-periodico` |
| Frecuencia | `0 4 * * 1` (lunes 04:00 UTC) o diario si se prefiere |
| URL | `https://<CLOUD_RUN_URL>/api/admin/motor/evaluar-periodico` |
| Método | `POST` |
| Headers | `X-Ruana-Cron-Secret: <RUANA_CRON_SECRET>` |
| Body | vacío o `{}` |

---

## Job 4 — Automatización financiera (FASE 11)

| Campo | Valor |
| --- | --- |
| Nombre sugerido | `ruana-financial-automation-cycle` |
| Frecuencia | `0 */6 * * *` (cada 6 h) o `0 7 * * *` (diario 07:00 UTC) |
| URL | `https://<CLOUD_RUN_URL>/api/admin/financial-automation/ejecutar-ciclo` |
| Método | `POST` |
| Headers | `X-Ruana-Cron-Secret: <RUANA_CRON_SECRET>` |
| Body | vacío o `{"incluir_reconciliacion": true}` |

Ejecuta el ciclo de monitorización financiera (`financial_monitoring_cycle`): detección de webhooks atascados/fallidos, alertas, reconciliación opcional. Requiere `RUANA_CRON_SECRET` en Cloud Run (sincronizado por el workflow de deploy).

---

## Provisionamiento idempotente (script)

Tras desplegar Cloud Run y configurar `RUANA_CRON_SECRET`:

```bash
export PROJECT_ID=ruana-4293f
export CLOUD_RUN_URL=https://<tu-servicio>.run.app
export RUANA_CRON_SECRET=<mismo-valor-que-GitHub-Secret>
# Opcional (recomendado si Cloud Run exige IAM):
export SCHEDULER_OIDC_SERVICE_ACCOUNT=ruana-runner@ruana-4293f.iam.gserviceaccount.com

bash .github/scripts/provision-cloud-scheduler-jobs.sh
```

El script crea o actualiza los **cuatro** jobs anteriores.

---

## Creación en GCP (ejemplo gcloud)

```bash
gcloud scheduler jobs create http ruana-purga-mensual \
  --location=europe-west1 \
  --schedule="0 5 1 * *" \
  --uri="https://<CLOUD_RUN_URL>/api/purga/mensual" \
  --http-method=POST \
  --headers="X-Ruana-Cron-Secret=<RUANA_CRON_SECRET>" \
  --oidc-service-account-email=<SA>@<PROJECT>.iam.gserviceaccount.com \
  --oidc-token-audience="https://<CLOUD_RUN_URL>"
```

Nota: si el servicio Cloud Run exige autenticación IAM además del secreto RUANA, usa cuenta de servicio con permiso `roles/run.invoker` y OIDC como en el ejemplo.

## Verificación manual

```bash
curl -sS -X POST "https://<CLOUD_RUN_URL>/api/purga/mensual" \
  -H "X-Ruana-Cron-Secret: $RUANA_CRON_SECRET"
```

Respuesta esperada: JSON con `status: success` o detalle de error; sin sesión admin ni secreto → 401.
