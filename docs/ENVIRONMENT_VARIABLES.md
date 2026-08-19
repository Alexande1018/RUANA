# Variables de entorno

Referencia consolidada de variables usadas por RUANA. Origen: grep sobre `RUANA/`, workflows, `playwright.config.js`, `.env.example`.

| Leyenda | Significado |
|---------|-------------|
| **Verificado** | Referenciada en código o CI inspeccionado |
| **Plantilla** | Presente en `.env.example` |
| **Prod** | Inyectada en deploy Cloud Run (workflow o Secret Manager) |

---

## 1. Core / Flask

| Variable | Obligatoria | Default | Descripción |
|----------|-------------|---------|-------------|
| `FLASK_SECRET_KEY` | Prod: sí | `ruana_secret_key_dev` | Firma JWT y sesiones. Mín. 24 chars en prod (`startup_validation.py`) |
| `FLASK_ENV` | No | — | Si `production`, fuerza `RUANA_ENV=production` |
| `RUANA_ENV` | No | `development` | `development` \| `test` \| `production` |
| `PORT` | No | `8080` | Puerto gunicorn / Cloud Run |
| `PYTHONPATH` | Local: sí | — | Debe incluir raíz `RUANA/` para imports |
| `CI` | Auto | — | Si `true`, entorno test |
| `PYTEST_CURRENT_TEST` | Auto | — | Detecta contexto pytest |
| `K_SERVICE` | Auto (Cloud Run) | — | Implica producción si set |

### Gunicorn (Docker)

| Variable | Default | Descripción |
|----------|---------|-------------|
| `WEB_CONCURRENCY` | `(2×CPU)+1` o `2` | Workers gunicorn |
| `GUNICORN_THREADS` | `4` | Threads por worker |
| `GUNICORN_TIMEOUT` | `30` | Timeout worker (seg) |

---

## 2. Sesiones y cookies

| Variable | Default | Descripción |
|----------|---------|-------------|
| `RUANA_ADMIN_SESSION_EXPIRES` | `3600` | TTL sesión admin (seg) |
| `RUANA_ALIADO_SESSION_EXPIRES` | `3600` | TTL sesión aliado (seg) |
| `RUANA_SESSION_COOKIE_SECURE` | `false` local | En prod forzado `true`. Valores: `1`, `true`, `yes` |

Header de sesión (no env): `X-Ruana-Session-Id` — ver [`seguridad/autenticacion-sesiones.md`](seguridad/autenticacion-sesiones.md).

---

## 3. Administrador

| Variable | Obligatoria | Descripción |
|----------|-------------|-------------|
| `RUANA_ADMIN_CREDENTIALS_PATH` | Una de dos | Ruta a JSON con hashes bcrypt |
| `RUANA_ADMIN_CREDENTIALS_JSON` | Una de dos | JSON inline (Cloud Run / CI). En prod es overlay de arranque; fuente de verdad = Secret Manager |
| `RUANA_ADMIN_USE_SECRET_MANAGER` | No | `1` fuerza lectura/escritura GCP; `0` desactiva. Default: activo si `is_production()` |
| `RUANA_ADMIN_GCP_SECRET_NAME` | No | Nombre del secreto GCP (default `ruana-admin-credentials`) |
| `GOOGLE_CLOUD_PROJECT` / `GCLOUD_PROJECT` | Auto Cloud Run | ID de proyecto para API Secret Manager |

Formato JSON: ver `RUANA/scripts/bootstrap_admin_credentials.py` y [`seguridad/credenciales-admin.md`](seguridad/credenciales-admin.md).

**Prod:** secret GCP `ruana-admin-credentials` → env var en deploy.

---

## 4. Base de datos

| Variable | Obligatoria prod | Default | Descripción |
|----------|------------------|---------|-------------|
| `DATABASE_URL` | Sí (prod) | vacío | Postgres connection string. Vacío → SQLite |
| `RUANA_DB_PATH` | No | `RUANA/ruana.db` | Ruta SQLite |
| `RUANA_DB_POOL_MIN` | No | `1` | Pool psycopg mínimo |
| `RUANA_DB_POOL_MAX` | No | `10` | Pool psycopg máximo |

---

## 5. Supabase

| Variable | Obligatoria prod | Descripción |
|----------|------------------|-------------|
| `SUPABASE_URL` | Sí | URL proyecto (ej. `https://qqlxgwbmtzcfrrobrfzy.supabase.co`) |
| `SUPABASE_ANON_KEY` | Sí | Clave pública |
| `SUPABASE_SERVICE_ROLE_KEY` | Sí | Clave service role (backend) |

Project ref CLI: `qqlxgwbmtzcfrrobrfzy` (`package.json` script `supabase:link`).

---

## 6. GCP / Firebase (deploy)

| Variable | Default | Descripción |
|----------|---------|-------------|
| `FIREBASE_PROJECT_ID` | `ruana-4293f` | Proyecto Firebase/GCP |
| `GOOGLE_CLOUD_REGION` | `europe-west1` | Región Cloud Run |
| `ARTIFACT_REGISTRY_REPOSITORY` | `ruana` | Repo imágenes Docker |
| `RUANA_PUBLIC_APP_URL` | `https://{project}.web.app` | URL pública enlaces email |
| `PUBLIC_APP_URL` | — | Alias aceptado por `settings.py` |

---

## 7. SMTP

| Variable | Default | Descripción |
|----------|---------|-------------|
| `RUANA_SMTP_HOST` | `smtp.gmail.com` | Servidor SMTP |
| `RUANA_SMTP_PORT` | `587` | Puerto |
| `RUANA_SMTP_USER` | `team.ruana@gmail.com` | Usuario |
| `RUANA_SMTP_PASSWORD` | vacío | Contraseña / app password |
| `RUANA_SMTP_FROM_EMAIL` | `RUANA_SMTP_USER` | Remitente |

Sin password configurado, el correo de bienvenida no se envía (fallo silencioso inferido — verificar logs).

**Prod:** secret `RUANA_SMTP_PASSWORD` en GitHub → GCP `ruana-smtp-password`.

---

## 8. Stripe Connect

| Variable | Default | Descripción |
|----------|---------|-------------|
| `RUANA_STRIPE_PAYMENTS_ENABLED` | `0` | `1`/`true` activa pagos Stripe |
| `RUANA_STRIPE_MODE` | vacío local | **`test` \| `live`** — obligatorio en prod |
| `STRIPE_SECRET_KEY` | vacío | API secret (`sk_test_` o `sk_live_`) |
| `STRIPE_PUBLISHABLE_KEY` | vacío | Clave publicable |
| `STRIPE_WEBHOOK_SECRET` | vacío | Secreto webhook (`whsec_`) |
| `STRIPE_API_VERSION` | `2024-11-20.acacia` | Versión API Stripe |
| `RUANA_STRIPE_TRANSFER_TIMEOUT_DAYS` | `12` | Timeout transferencias |

Validación: prefijo clave debe coincidir con modo (`startup_validation.py`, `stripe_mode_guard.py`).

**Prod deploy workflow:** fija `RUANA_STRIPE_MODE=test` — revisar antes de live.

---

## 9. Cron y automatización

| Variable | Obligatoria prod | Descripción |
|----------|------------------|-------------|
| `RUANA_CRON_SECRET` | Sí (FASE 11+) | Header `X-Ruana-Cron-Secret` para jobs HTTP |

### Finanzas — automatización (FASE 11)

| Variable | Default | Descripción |
|----------|---------|-------------|
| `RUANA_FIN_AUTOMATION_LEASE_TTL` | `300` | TTL lease automatización (seg) |
| `RUANA_FIN_AUTOMATION_RECON_LIMIT` | `20` | Límite reconciliación por ciclo |
| `RUANA_FIN_ALERT_DISPUTE_HOURS` | `72` | Alerta disputas |
| `RUANA_FIN_ALERT_CONFLICT_DAYS` | `7` | Alerta conflictos antiguos |
| `RUANA_FIN_ALERT_REFUND_STALE_HOURS` | `48` | Reembolsos estancados |
| `RUANA_FIN_ALERT_WEBHOOK_STUCK_HOURS` | `2` | Webhooks atascados |
| `RUANA_FIN_ALERT_TRANSFER_STUCK_HOURS` | `24` | Transferencias atascadas |

### Finanzas — aprobaciones

| Variable | Default | Descripción |
|----------|---------|-------------|
| `RUANA_FINANCIAL_REQUIRE_APPROVAL` | `1` | Exige approval_id en acciones sensibles |
| `RUANA_FINANCIAL_ALLOW_SELF_APPROVAL` | `0` | Permite auto-aprobación |
| `RUANA_FINANCIAL_APPROVAL_TTL_HOURS` | `72` | TTL solicitudes aprobación |

---

## 10. PIN aliado

| Variable | Default | Descripción |
|----------|---------|-------------|
| `RUANA_PIN_MAX_INTENTOS` | `5` | Intentos PIN antes de bloqueo |
| `RUANA_PIN_BLOQUEO_MINUTOS` | `15` | Minutos de bloqueo |
| `RUANA_PIN_SETUP_EXPIRES` | `900` | TTL setup PIN (seg) |
| `RUANA_RECUPERACION_OTP_MINUTOS` | `15` | Validez OTP recuperación |
| `RUANA_RECUPERACION_MAX_INTENTOS` | `5` | Intentos OTP |

---

## 11. Storage / QA

| Variable | Default | Descripción |
|----------|---------|-------------|
| `RUANA_ALLOW_LOCAL_UPLOADS` | `0` | `1` → uploads locales sin Supabase |

---

## 12. Playwright / E2E

| Variable | Default | Descripción |
|----------|---------|-------------|
| `RUANA_BASE_URL` | `http://127.0.0.1:5000` | URL base tests |
| `RUANA_SKIP_WEBSERVER` | — | No arrancar servidor embebido |
| `RUANA_QA_VIDEO_PAUSE_MS` | — | Pausa video QA (CI: 1500) |
| `RUANA_QA_ACTION_PAUSE_MS` | — | Pausa acciones (CI: 800) |
| `RUANA_QA_PUBLISH_PAGES` | — | Mencionado en workflow; publicar Pages |

---

## 13. Archivos de entorno

Orden de carga (`settings.py`):

1. Variables de proceso existentes
2. `.env.local` (raíz repo, no commitear)
3. `.env` (raíz repo, gitignored)

Plantilla commiteada: `.env.example` (solo documentación; valores placeholder).

---

## 14. Variables documentadas pero sin uso directo encontrado

| Variable | Notas |
|----------|-------|
| `RUANA_QA_PUBLISH_PAGES` | Solo en comentario workflow CI |

---

## 15. Checklist prod mínimo

```text
[ ] FLASK_SECRET_KEY (Secret Manager)
[ ] DATABASE_URL
[ ] SUPABASE_URL + keys
[ ] RUANA_ADMIN_CREDENTIALS_JSON
[ ] RUANA_CRON_SECRET
[ ] RUANA_STRIPE_MODE + STRIPE_* (si pagos activos)
[ ] RUANA_SMTP_PASSWORD (si email requerido)
[ ] RUANA_PUBLIC_APP_URL
[ ] RUANA_ENV=production
[ ] RUANA_SESSION_COOKIE_SECURE=true
```

---

*Auditoría cruzada con código 2026-08-19. Reportar discrepancias en [`KNOWN_ISSUES.md`](KNOWN_ISSUES.md).*
