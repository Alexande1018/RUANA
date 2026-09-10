# Despliegue RUANA

Procedimientos de publicación basados en workflows y scripts **Verificados** en el repositorio. No sustituyen runbooks internos del equipo GCP si existen.

| | |
|---|---|
| Fecha | 2026-08-19 |
| URL producción | `https://ruana-4293f.web.app` |
| Proyecto GCP/Firebase | `ruana-4293f` |
| Región | `europe-west1` |

---

## 1. Topología de producción

```text
GitHub (push main)
    → workflow deploy-firebase.yml
        → Build Docker → Artifact Registry
        → Deploy Cloud Run (servicio "ruana")
        → Sync secretos → Google Secret Manager
        → firebase deploy --only hosting
        → curl smoke tests (/api/health, /aliado, /)
```

Firebase Hosting **no sirve** la app estática; reescribe todo el tráfico a Cloud Run (`firebase.json`).

---

## 2. Entornos

| Entorno | Servicio Cloud Run | Trigger | Hosting |
|---------|-------------------|---------|---------|
| Producción | `ruana` | push `main` | `ruana-4293f.web.app` |
| Preview | `ruana-preview` | workflow `deploy-firebase-preview.yml`, rama `dev` | canal Firebase `dev` (30 días) |

---

## 3. Pipeline CI/CD producción

Archivo: `.github/workflows/deploy-firebase.yml`

### Prerrequisitos GitHub (No verificado estado actual de secretos)

| Secret / configuración | Uso |
|------------------------|-----|
| WIF provider + SA `ruana-firebase-deployer@...` | Auth GCP |
| `RUANA_ADMIN_CREDENTIALS_JSON` | Sync Secret Manager |
| `RUANA_SMTP_PASSWORD` | Sync SMTP |
| `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET` | Sync Stripe |
| `RUANA_CRON_SECRET` | Sync cron |

Secretos ya en GCP (referenciados en deploy):

- `ruana-database-url`
- `ruana-supabase-service-role-key`
- `ruana-supabase-anon-key`
- `ruana-flask-secret-key`
- `ruana-admin-credentials`
- `ruana-smtp-password`
- `ruana-stripe-*`
- `ruana-cron-secret`

### Variables de entorno fijadas en deploy (Verificado)

El workflow establece explícitamente:

```text
FIREBASE_PROJECT_ID=ruana-4293f
GOOGLE_CLOUD_REGION=europe-west1
SUPABASE_URL=https://qqlxgwbmtzcfrrobrfzy.supabase.co
RUANA_PUBLIC_APP_URL=https://ruana-4293f.web.app
RUANA_STRIPE_PAYMENTS_ENABLED=1
STRIPE_API_VERSION=2024-11-20.acacia
RUANA_ENV=production
RUANA_STRIPE_MODE=<resuelto: vars.RUANA_STRIPE_MODE o default test>
RUANA_SESSION_COOKIE_SECURE=true
```

**Atención:** por defecto el deploy usa `test` si no hay variable de repositorio. Para Live: `workflow_dispatch` con `ruana_stripe_mode=live` y secrets `sk_live_` / `whsec_` de Live.

### Imagen Docker

```bash
# Equivalente manual (desde raíz repo)
npm run cloudrun:build
# Tag: europe-west1-docker.pkg.dev/ruana-4293f/ruana/ruana:<git-sha>
```

Dockerfile: Python 3.13-slim, gunicorn multi-worker, `PORT` default 8080, `GUNICORN_TIMEOUT` default 60s.

### Instancias Cloud Run (producción `ruana`)

El workflow de producción y `scripts/deploy_cloudrun.ps1` fijan:

- `--min-instances 1` — no escala a cero; el contenedor sigue en memoria entre visitas.
- `--max-instances 3` — tope de escala (sin cambio).

No se activa CPU always allocated. El preview (`ruana-preview`) **no** usa min-instances: sigue pudiendo escalar a cero para no duplicar el coste fijo.

**Coste:** 1 instancia mínima en reposo (CPU throttling por defecto) ronda unos 10 USD/mes en `europe-west1`. El panel aliado reintenta `/api/aliado/datos` por si la primera petición aún tarda. No se tocan secretos Stripe ni el modo Live.

**Evidencia ops (Pasarela, 2026-09-10, servicio `ruana` europe-west1):**

| Ruta | 1ª llamada (frío) | Caliente |
|------|-------------------|----------|
| `GET /api/aliado/datos` | ~15 s (sonda: 401 sin sesión) | ~0,32–0,35 s ×3 |
| `GET /api/health` | ~4 s | ~0,3 s |

El login puede ir bien y el bootstrap igual falla con «No pudimos cargar tu panel» si `datos` es lento. Un ping a `/api/health` no sustituye min-instances: `#inicio` espera `datos`, que en frío es ~4× más lento que health.

---

## 4. Despliegue manual

### Cloud Run (PowerShell — entorno Windows documentado)

```bash
npm run cloudrun:deploy
# Ejecuta scripts/deploy_cloudrun.ps1
```

### Solo Firebase Hosting

```bash
npm run deploy:hosting
# scripts/deploy_firebase_hosting.ps1
```

### Preview channel

```bash
npm run deploy:preview
# firebase hosting:channel:deploy dev --expires 30d
```

### Migraciones Supabase

```bash
npm run supabase:push
# supabase db push — project-ref qqlxgwbmtzcfrrobrfzy
```

**Recomendación:** ejecutar migraciones en ventana controlada antes o después del deploy de app, nunca asumir paridad automática.

---

## 5. Verificación post-deploy

### Automática (CI)

```bash
curl --fail https://ruana-4293f.web.app/api/health
curl --fail https://ruana-4293f.web.app/aliado | grep -q "input-foto-perfil"
curl --fail https://ruana-4293f.web.app/ | grep -q "ruana-brand-mark"
```

### Manual recomendada

| Check | Comando / acción |
|-------|------------------|
| Health | `GET /api/health` → `status: healthy` |
| Boot logs | Cloud Run logs → `[RUANA][BOOT] Flask usando backend Postgres/Supabase` |
| Login aliado | Flujo registro/login en entorno staging |
| Admin | Login con credenciales prod |
| Stripe webhook | Dashboard Stripe → eventos entregados |
| Storage | Subir foto perfil / comprobante |

---

## 6. Cron operativo (Cloud Scheduler)

Los jobs **no** se despliegan con el workflow de app. Configuración documentada en [`operaciones/cloud_scheduler_jobs.md`](operaciones/cloud_scheduler_jobs.md).

Endpoints principales:

| Job | Método | Ruta |
|-----|--------|------|
| Competencias vencidas | POST | `/api/competencia/finalizar-vencidas` |
| Purga mensual | POST | `/api/purga/mensual` |
| Motor evaluación | POST | `/api/admin/motor/evaluar-periodico` |
| Automatización financiera | POST | `/api/admin/financial-automation/ejecutar-ciclo` |

Header requerido: `X-Ruana-Cron-Secret: <RUANA_CRON_SECRET>`

**Estado despliegue scheduler:** Código y script `provision-cloud-scheduler-jobs.sh` listos; **creación en GCP no verificada** (ejecutar script manualmente).

---

## 7. Rollback

**No verificado** procedimiento formal en repo. Opciones técnicas inferidas:

1. **Cloud Run:** redirigir tráfico a revisión anterior en consola GCP o redeploy imagen con tag SHA previo.
2. **Firebase Hosting:** redeploy commit anterior (hosting solo rewrite; rollback efectivo = rollback Cloud Run).
3. **BD:** migraciones Supabase no tienen rollback automático en repo — requiere script manual.

Documentar decisión del equipo antes de handoff.

---

## 8. QA en CI (no es deploy)

Workflow `.github/workflows/ruana-qa.yml`:

- **pytest** en push/PR a `main` y `dev`
- **Playwright** en push y `workflow_dispatch` (no en PR como gate)

Artefacto: `ruana-qa-latest` (reporte HTML + videos, retención 1 día).

---

## 9. Scripts npm disponibles

| Script | Acción |
|--------|--------|
| `firebase:deploy` | Hosting only |
| `cloudrun:build` | Build imagen Artifact Registry |
| `cloudrun:deploy` | Deploy Cloud Run (PS1) |
| `gcp:secrets` | Sync secretos (PS1) |
| `gcp:admin-credentials` | Admin creds bash |
| `supabase:push` | Migraciones BD |
| `qa:e2e` | Playwright local |

Ver `package.json` para lista completa.

---

## 10. Huecos operativos

- Confirmar si preview (`ruana-preview`) comparte BD con producción — **No verificado**.
- Confirmar IAM Cloud Run invoker para Scheduler OIDC — ver nota en cloud_scheduler_jobs.md.
- `docs/ADMIN_CREDENTIALS_SETUP.md` referenciado en `.env.example` pero **ausente**.

---

*Ver también [`SETUP.md`](SETUP.md) y [`HANDOFF.md`](HANDOFF.md).*
