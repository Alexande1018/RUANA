# Cloud Scheduler — jobs operativos RUANA

Despliegue objetivo: **Google Cloud Run** (servicio Flask). Los cron jobs **no** corren dentro del contenedor; Cloud Scheduler invoca endpoints HTTP protegidos.

## Autenticación

Configura en el servicio Cloud Run (y en `.env` local si pruebas):

```bash
RUANA_CRON_SECRET=<valor-aleatorio-largo>
```

Cada petición del scheduler debe incluir:

```http
X-Ruana-Cron-Secret: <valor-aleatorio-largo>
```

Los endpoints aceptan **sesión admin con escritura** **o** el header anterior.

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
