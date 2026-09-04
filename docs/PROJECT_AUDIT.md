# Auditoría técnica del repositorio RUANA

| Campo | Valor |
|-------|-------|
| Fecha de auditoría | 2026-08-19 (pack de cierre). **Revisión de cifras: 2026-09-04** — ver [`exports/AUDITORIA_DOCUMENTAL_2026-09-04.md`](exports/AUDITORIA_DOCUMENTAL_2026-09-04.md) |
| Rama auditada | `main` (commit de trabajo en rama `cursor/docs-cierre-producto-dccf`) |
| Alcance | Repositorio completo: código, config, CI/CD, migraciones, docs existentes |
| Ejecución de tests | **Verificado** — `784 passed, 11 skipped` en ~9m24s (Python 3.12, SQLite) |
| E2E Playwright | **No ejecutado** en esta auditoría (requiere `npm ci` + servidor; CI lo corre en push) |
| Deploy producción | **No ejecutado** (requiere credenciales GCP/Firebase) |

**Principio:** el código prevalece sobre la documentación. Etiquetas: **Verificado** (comprobado en repo o ejecución local), **Inferido** (deducido con alta confianza), **No verificado** (requiere confirmación manual en entorno remoto).

---

## Resumen ejecutivo

RUANA es una aplicación web monolítica Flask que sirve UI HTML/JS y una API REST extensa. Producción desplegada vía **Firebase Hosting → Cloud Run** (`ruana-4293f`, `europe-west1`), con persistencia prevista en **Postgres (Supabase)** y fallback **SQLite** para desarrollo/CI.

Estado del producto documentado internamente: **pre-MVP avanzada (v0.9)**. El núcleo operativo (registro, grupos territoriales, score, negociación, pagos manuales, panel admin, competencia) está implementado y cubierto por tests automatizados. Existe un **módulo financiero ampliado** (conflictos, reembolsos, disputas, conciliación, ledger, automatización) añadido tras la auditoría documental de agosto 2025.

La modularización **Campamento Base** está avanzada: `DBManager` actúa como fachada (**1969** LOC el 2026-09-04) delegando en **37 services** y **31 repositories**, pero no está completa.

**Riesgos principales para handoff (revisados 2026-09-04):** login aliado es código+PIN (ya no factor único; adopción prod NO VERIFICADO), CORS permisivo, service role Supabase que elude RLS, tablas financieras sin RLS en DDL, drift SQLite/Postgres, sesiones revocadas en memoria, datos de cobro en JSON/frontend versionado, modo Stripe efectivo NO VERIFICADO, cron jobs documentados pero **no verificados** en GCP.

---

## Stack detectado

| Capa | Tecnología | Evidencia | Estado |
|------|------------|-----------|--------|
| Runtime producción | Python 3.13-slim, gunicorn | `Dockerfile` | Verificado |
| Runtime CI pytest | Python 3.11 | `.github/workflows/ruana-qa.yml` | Verificado |
| Backend | Flask 2.3.3, Flask-Cors, Flask-Compress, Flask-Limiter, PyJWT, Werkzeug | `RUANA/web/requirements.txt` | Verificado |
| BD | psycopg3 + SQLite3 | `postgres_compat.py`, `db_manager.py` | Verificado |
| Storage | Supabase Storage (+ fallback local) | `storage_manager.py` | Verificado |
| Pagos | Stripe Connect (opcional, flag) | `stripe_client.py`, `pagos_bp` | Verificado en código |
| Email | SMTP (Gmail documentado) | `email_service.py`, `settings.py` | Verificado |
| Frontend | HTML/CSS/JS vanilla | `RUANA/web/*.html`, `static/` | Verificado |
| Hosting | Firebase Hosting rewrite → Cloud Run | `firebase.json` | Verificado |
| CI/CD | GitHub Actions (WIF → GCP) | `.github/workflows/` | Verificado |
| QA E2E | Playwright 1.44 | `playwright.config.js`, `e2e/` | Verificado (config) |
| Migraciones PG | Supabase CLI SQL | `supabase/migrations/` (**29** archivos el 2026-09-04) | Verificado |
| Node (tooling) | firebase-tools, supabase CLI, Playwright | `package.json` | Verificado |

**No detectado en repo:** licencia (`LICENSE` ausente), Terraform/Pulumi, Kubernetes manifests, Vercel/Netlify, Firebase Auth implementado, Supabase Realtime en cliente.

---

## Entrypoints y ejecución

| Entrypoint | Comando / mecanismo | Puerto | Notas |
|------------|---------------------|--------|-------|
| Producción (Docker) | `gunicorn web.app:app` | `${PORT:-8080}` | Verificado — `Dockerfile` |
| Desarrollo Flask | `python -m flask --app web.app run` desde `RUANA/` con `PYTHONPATH=.` | 8080 (README) / 5000 (`app.py` `__main__`) | Verificado — hay inconsistencia de puerto |
| QA / E2E | `python RUANA/web/run.py` | 5000 | Verificado — `playwright.config.js` |
| CLI orquestador | Scripts en `RUANA/scripts/` | N/A | Inferido — no conectados al servidor web principal |

**Blueprints registrados:** 21 módulos en `RUANA/web/app.py` (**326** decoradores `@*.route` en blueprints + **34** rutas en `app.py`, verificado 2026-09-04).

Lista **Verificada** en `app.py`: `catalogo`, `negociacion`, `referidos`, `admin`, `contactos`, `auth`, `pagos`, `stripe_webhook`, `solicitudes`, `solicitudes_semanales`, `aliado`, `invitacion`, `evaluacion`, `soporte`, `financial_conflicts`, `financial_refunds`, `financial_disputes`, `financial_reconciliation`, `financial_ledger`, `financial_admin`, `financial_automation`.

**Health check:** `GET /api/health` → JSON `{status: healthy}` — **Verificado** en `catalogo_bp.py`. No comprueba conectividad a BD.

**Validación de arranque:** `startup_validation.py` aborta el proceso en producción si faltan secretos débiles (`FLASK_SECRET_KEY`, Stripe, `RUANA_CRON_SECRET`) — **Verificado**.

---

## Configuración y variables de entorno

- Plantilla: `.env.example` (raíz) — **Verificado**.
- Carga runtime: `core/settings.py` lee `.env.local` y `.env` desde raíz del repo — **Verificado**.
- Documentación consolidada: [`ENVIRONMENT_VARIABLES.md`](ENVIRONMENT_VARIABLES.md).

**Discrepancias detectadas:**

| Tema | Código | Documentación previa | Ganador |
|------|--------|----------------------|---------|
| Nº blueprints | 21 | README citaba 13 | Código |
| Nº tests | 784 passed | README citaba 383 | Código (ejecución 2026-08-19) |
| `ruana.db` en git | Ignorado (`*.db` en `.gitignore`) | README decía "commiteado" | Código |
| Stripe en prod | `RUANA_STRIPE_MODE=test` en deploy workflow | No documentado | Código |
| Referencia `docs/ADMIN_CREDENTIALS_SETUP.md` | Archivo **no existe** | `.env.example` línea 29 | Hueco |

---

## Persistencia y datos

### Estrategia dual

| Modo | Activación | Uso |
|------|------------|-----|
| Postgres | `DATABASE_URL` no vacío | Producción Cloud Run — **Inferido** |
| SQLite | Sin `DATABASE_URL` | Local, pytest, E2E CI — **Verificado** |

Ruta SQLite: `RUANA_DB_PATH` o default `RUANA/ruana.db` (`db_constants.py`).

### Schema

- **Postgres:** 28 migraciones en `supabase/migrations/` (init 2026-05-19 + financial fases + linaje + score + solicitudes semanales).
- **SQLite:** inicialización runtime vía `schema_service` / `_init_db()` en `DBManager`.
- **Drift conocido:** tablas/columnas creadas en runtime SQLite o parches Postgres no reflejados en todas las migraciones — **Verificado** en informes previos y código `schema_service`.

### RLS

Migración init define RLS en tablas Supabase. Backend usa **service role** → RLS no protege la API Flask — **Verificado**.

### Archivos sensibles en repo

- `RUANA/config/ruana_reglas_v1.json` contiene IBAN, Bizum y URLs de QR — **Verificado** (datos reales de cobro manual).
- `RUANA/config/admin_credentials.qa.json` — credenciales QA para Playwright — **Verificado**.

---

## Integraciones externas

| Servicio | Función | Estado en código |
|----------|---------|------------------|
| Supabase Postgres | BD principal prod | Implementado |
| Supabase Storage | Fotos, comprobantes | Implementado |
| Firebase Hosting | Proxy a Cloud Run | Implementado |
| Google Cloud Run | Runtime Flask | Implementado |
| Artifact Registry | Imágenes Docker | Implementado |
| Google Secret Manager | Secretos en deploy | Implementado (scripts + workflow) |
| SMTP | Email bienvenida aliado | Implementado (opcional) |
| Stripe Connect | Pagos encargo + webhooks | Implementado (flag + secretos) |
| Cloud Scheduler | Cron HTTP | Endpoints + auth documentados; **despliegue No verificado** |
| Firebase Auth | Login admin | **Planificado** — no implementado |
| Supabase Auth / `profiles` | Tabla en migración | **No cableado** al login Flask |

---

## Seguridad y acceso

| Actor | Mecanismo | Archivos clave |
|-------|-----------|----------------|
| Aliado | Código 5 dígitos → JWT HS256 + `X-Ruana-Session-Id` | `auth_bp.py`, `auth_session.py` |
| Aliado (PIN) | PIN personal opcional/recuperación OTP | `aliado_pin_auth.py`, `aliado_pin_service.py` |
| Admin | ID + contraseña hasheada (JSON fuera de repo) | `admin_auth.py`, `app.py` |
| Cron | Header `X-Ruana-Cron-Secret` o sesión admin escritura | `auth_decorators.py` |

**Autorización:** decoradores `@require_aliado`, `@require_admin`, `@require_admin_escritura`, permisos financieros en módulo admin finanzas.

**Rate limiting:** Flask-Limiter en memoria (`memory://`) — no compartido entre instancias Cloud Run — **Verificado**.

**Producción:** Cloud Run `--allow-unauthenticated`; la seguridad es de aplicación — **Verificado** en `deploy-firebase.yml`.

---

## Testing y calidad

| Suite | Ubicación | CI | Resultado local |
|-------|-----------|-----|-----------------|
| pytest | `RUANA/tests/` (89 archivos `test_*.py`) | push/PR `main`,`dev` | **784 passed, 11 skipped** |
| Playwright E2E | `e2e/ruana-critical-flows.spec.js` | push + manual | No ejecutado aquí |
| Contratos blueprints | `test_campamento_mision_blueprints.py` | incluido en pytest | Verificado en suite |

Workflow: `.github/workflows/ruana-qa.yml` — **Verificado** con triggers `push`, `pull_request`, `workflow_dispatch`.

---

## Deploy e infraestructura

| Entorno | Trigger | Destino |
|---------|---------|---------|
| Producción | push `main` | Cloud Run `ruana` + Firebase Hosting |
| Preview | workflow `deploy-firebase-preview.yml` / rama `dev` | Cloud Run `ruana-preview` |
| Migraciones BD | manual `npm run supabase:push` | Supabase project `qqlxgwbmtzcfrrobrfzy` |

**URL pública documentada:** `https://ruana-4293f.web.app` — **Verificado** en workflows.

**Post-deploy checks en CI:** `curl /api/health`, smoke HTML en `/aliado` y `/` — **Verificado**.

---

## Documentación existente

| Documento | Estado |
|-----------|--------|
| `README.md` (raíz) | Extenso; parcialmente desactualizado (conteos pre-financial) |
| `docs/README.md` | Índice secundario; no incluía docs de cierre |
| `docs/flujos/*`, `docs/seguridad/*` | Deep-dives válidos |
| `docs/operaciones/roadmap.md` | Fecha 2026-08-15; conteos desactualizados |
| `docs/archive/*` | Histórico; no borrar |
| `docs/exports/AUDITORIA_DOCUMENTAL_2026-08-15.md` | Auditoría anterior |

**Nueva documentación de cierre (esta entrega):** `PROJECT_AUDIT.md`, `ARCHITECTURE.md`, `SETUP.md`, `DEPLOYMENT.md`, `ENVIRONMENT_VARIABLES.md`, `KNOWN_ISSUES.md`, `HANDOFF.md`.

---

## Riesgos técnicos

1. **Auth aliado código+PIN** — mitigado vs factor único; adopción prod y rate-limit en memoria pendientes.
2. **Service role Supabase** — bypass RLS; toda autorización depende de Flask.
3. **Drift SQLite/Postgres** — riesgo de fallos silenciosos en prod si migraciones no están al día.
4. **Sesiones en memoria** — revocación no consistente entre réplicas Cloud Run (`max-instances: 3`).
5. **Datos de cobro en git** — `ruana_reglas_v1.json` expone IBAN/Bizum en historial.
6. **Modo Stripe en prod** — el workflow ya no hardcodea `test`; valor efectivo **NO VERIFICADO**.
7. **Cron jobs** — endpoints existen; ejecución programada en GCP **No verificada**.
8. **Rate limit / session store en memoria** — limitación multi-instancia.
9. **`DBManager` fachada residual** — deuda de extracción; riesgo de regresión en cambios amplios.
10. **Rutas preview/test en producción** — `/test-panel`, `/feedback-preview`, etc. servidas por la misma app.

---

## Huecos detectados

| # | Hueco | Acción requerida |
|---|-------|------------------|
| 1 | Estado real schema Supabase remoto vs migraciones locales | Comparar con `supabase db diff` o panel Supabase |
| 2 | Cloud Scheduler jobs creados en GCP | Listar con `gcloud scheduler jobs list` |
| 3 | Stripe activo live vs test en producción | Revisar env vars Cloud Run y dashboard Stripe |
| 4 | Realtime Supabase usado en cliente | Buscar en JS frontend (no encontrado en auditoría) |
| 5 | Procedimiento rollback operativo cotidiano | Confirmar con equipo ops |
| 6 | Responsables / contactos | No definidos en repo |
| 7 | `docs/ADMIN_CREDENTIALS_SETUP.md` referenciado pero ausente | Crear o corregir referencia en `.env.example` |
| 8 | Purga mensual ejecutada en prod | Revisar logs tras cron |
| 9 | Licencia del software | Ausente — decisión legal pendiente |

---

## Recomendaciones prioritarias

1. **Sincronizar migraciones Supabase** con `schema_service` y ejecutar `supabase db push` en entorno controlado antes de handoff.
2. **Confirmar Cloud Scheduler** para competencia, purga y motor evaluación (`docs/operaciones/cloud_scheduler_jobs.md`).
3. **Revisar `RUANA_STRIPE_MODE`** en producción antes de cobros reales.
4. **Externalizar datos de cobro** de `ruana_reglas_v1.json` a secretos o panel admin.
5. **Actualizar roadmap y README** con módulo financiero y conteos actuales (hecho en esta entrega).
6. **Definir licencia** y contactos de mantenimiento en `HANDOFF.md`.
7. **Evaluar store de sesiones** externo (Redis/Firestore) si se escalan instancias Cloud Run.

---

## Anexo de archivos clave revisados

| Ruta | Propósito |
|------|-----------|
| `RUANA/web/app.py` | Setup Flask, blueprints, HTML, auth admin |
| `RUANA/core/db_manager.py` | Fachada persistencia (1969 LOC, 2026-09-04) |
| `RUANA/core/settings.py` | Settings y carga `.env` |
| `RUANA/core/startup_validation.py` | Validación boot producción |
| `RUANA/core/auth_session.py` | Sesiones JWT + store memoria |
| `RUANA/core/admin_auth.py` | Credenciales admin |
| `RUANA/web/blueprints/*.py` | 21 blueprints API |
| `RUANA/core/services/*.py` | 37 services de dominio (2026-09-04) |
| `RUANA/core/repositories/*.py` | 31 repos SQL (2026-09-04) |
| `RUANA/config/ruana_reglas_v1.json` | Reglas negocio + cobro manual |
| `RUANA/config/oficios_ruana.json` | Catálogo oficios |
| `Dockerfile` | Imagen producción |
| `firebase.json` | Hosting rewrite |
| `.github/workflows/deploy-firebase.yml` | Deploy prod |
| `.github/workflows/ruana-qa.yml` | CI pytest + E2E |
| `supabase/migrations/*.sql` | DDL Postgres (29, 2026-09-04) |
| `package.json` | Scripts deploy/QA |
| `.env.example` | Plantilla variables |
| `playwright.config.js` | E2E local/CI |
| `e2e/ruana-critical-flows.spec.js` | Flujos críticos E2E |

---

*Auditoría generada por inspección del repositorio y ejecución local de pytest. Ver [`HANDOFF.md`](HANDOFF.md) para transferencia operativa.*
