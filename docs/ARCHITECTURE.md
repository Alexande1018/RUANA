# Arquitectura RUANA

Documento de referencia técnica para desarrolladores y auditores. Describe la implementación **actual**, no la arquitectura objetivo.

| | |
|---|---|
| Fecha | 2026-09-04 |
| Autoridad | Código en `RUANA/` prevalece sobre este documento |
| Manual Maestro | [`/README.md`](../README.md) |

---

## 1. Vista general

```text
┌─────────────────────────────────────────────────────────────┐
│  Cliente (navegador)                                        │
│  HTML/JS vanilla — RUANA/web/*.html, static/js/*            │
└───────────────────────────┬─────────────────────────────────┘
                            │ HTTPS
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Firebase Hosting (ruana-4293f)                             │
│  public: firebase-public/ (vacío; solo rewrite)             │
└───────────────────────────┬─────────────────────────────────┘
                            │ rewrite ** → Cloud Run
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Google Cloud Run — servicio "ruana" (europe-west1)         │
│  gunicorn → web.app:app (Flask)                             │
│  max-instances: 3 (deploy workflow)                         │
└───────┬─────────────────────────────┬───────────────────────┘
        │                             │
        ▼                             ▼
┌──────────────────┐        ┌─────────────────────────────┐
│ Postgres         │        │ Supabase Storage            │
│ (Supabase)       │        │ buckets: ruana-public,      │
│ DATABASE_URL     │        │ ruana-comprobantes, etc.    │
└──────────────────┘        └─────────────────────────────┘
        │
        │ fallback local / CI
        ▼
┌──────────────────┐
│ SQLite           │
│ RUANA_DB_PATH    │
└──────────────────┘

Integraciones opcionales: SMTP, Stripe Connect, Cloud Scheduler (HTTP cron)
```

**Verificado** en: `firebase.json`, `Dockerfile`, `deploy-firebase.yml`, `storage_manager.py`, `postgres_compat.py`.

---

## 2. Capas de aplicación

### 2.1 Presentación (web)

| Componente | Ubicación | Responsabilidad |
|------------|-----------|-----------------|
| Páginas HTML | `RUANA/web/*.html` | UI aliado, admin, registro, invitación |
| Assets estáticos | `RUANA/web/static/` | CSS, JS modular por dominio aliado |
| Rutas HTML | `web/app.py` | Sirve páginas; incluye rutas legacy y preview |

Paneles principales: `aliado.html`, `admin.html`, `register.html`, `index.html`, `invite.html`.

### 2.2 API HTTP (blueprints)

21 blueprints Flask registrados en `web/app.py`. Agrupación funcional:

| Dominio | Blueprint(s) | Prefijo API típico |
|---------|--------------|-------------------|
| Catálogo / health | `catalogo_bp` | `/api/catalogo/*`, `/api/health` |
| Auth aliado/admin | `auth_bp` + rutas en `app.py` | `/api/aliado/*`, `/api/admin/validar` |
| Aliados | `aliado_bp` | `/api/aliados/*` |
| Grupos / territorio | `aliado_bp`, `solicitudes_bp` | varios |
| Contactos / encargos | `contactos_bp`, `negociacion_bp` | `/api/contactos/*`, negociación |
| Pagos / Apoyo | `pagos_bp`, `stripe_webhook_bp` | `/api/pagos/*`, webhook Stripe |
| Invitaciones / referidos | `invitacion_bp`, `referidos_bp` | `/api/invitaciones/*`, `/api/referidos/*` |
| Solicitudes | `solicitudes_bp`, `solicitudes_semanales_bp` | `/api/solicitudes/*` |
| Admin operativo | `admin_bp` | `/api/admin/*` (~59 rutas) |
| Competencia / evaluación | `admin_bp`, `evaluacion_bp` | motor, purga, competencia |
| Soporte | `soporte_bp` | centro comunicación |
| Finanzas (FASE 04–13) | `financial_*` (7 blueprints) | `/api/admin/financial-*` |

**Verificado:** ~315 endpoints únicos en blueprints + ~34 rutas HTML/auth en `app.py` (~349 total).

### 2.3 Dominio (services)

Patrón **Campamento Base**:

```text
Blueprint / test / legacy
    → DBManager.método()          # fachada (~1.925 LOC)
        → <dominio>_service       # reglas de negocio
            → <dominio>_repo      # SQL
                → SQLite | Postgres
```

37 módulos en `RUANA/core/services/`, incluyendo:

- **Core negocio:** `aliado`, `grupo`, `score`, `contacto`, `negociacion`, `pago`, `competencia`, `invitacion`, `referido`, `solicitud`, `chat`, `notificacion`, `catalogo`, `admin`, `evaluacion`
- **Financiero:** `financial_transaction`, `financial_transfer`, `financial_conflict`, `financial_refund`, `financial_dispute`, `financial_reconciliation`, `financial_ledger`, `financial_admin`, `financial_automation`, `financial_audit`, `financial_action_approval`, etc.
- **Infra dominio:** `schema`, `stripe_webhook`, `grupo_crecimiento`, `solicitud_semanal`, `aliado_pin`, `red_arbol`, `actividad_cinta`, `contacto`

`DBManager` no hereda services; **delega** pasando `self` o cursor.

### 2.4 Persistencia (repositories)

31 repos en `RUANA/core/repositories/` con consultas SQL explícitas.

Adaptadores:

- `postgres_compat.py` — pool psycopg (`RUANA_DB_POOL_MIN/MAX`)
- `schema_service` — DDL runtime y parches compatibilidad

---

## 3. Flujos de datos críticos

### 3.1 Registro aliado

```text
register.html → POST /api/aliados/registrar
  → aliado_service (validación, código 5 dígitos, score inicial 50)
  → grupo_service (plaza CP, max 5 grupos, en_espera)
  → invitacion_service / referido_service (si aplica)
  → email_service (SMTP opcional)
```

### 3.2 Encargo económico

```text
Contacto → negociación guiada (negociacion_service)
  → declaración importe (contacto_service)
  → Apoyo RUANA = importe × apoyo_pct/100 (pago_service; default 12%)
  → comprobante → Storage → revisión admin
  → opcional: Stripe Connect checkout (flag RUANA_STRIPE_PAYMENTS_ENABLED)
  → opcional: impugnación → payment_conflicts / financial_conflicts
```

**Verificado:** rutas legacy chat libre devuelven **410** (`negociacion_bp`).

### 3.3 Score y competencia

```text
Eventos de dominio → score_service (rango 0–500, ±10/día)
  → score_a_estado → bandas ÉLITE…COMPETENCIA
  → umbral < 15 → competencia_service
  → cron POST /api/competencia/finalizar-vencidas (auth cron)
```

Umbrales en `RUANA/config/ruana_reglas_v1.json` (`umbral_competencia: 15`).

### 3.4 Módulo financiero (admin)

Capas adicionales sobre pagos Stripe y conflictos manuales:

```text
financial_admin_bp / financial_*_bp
  → financial_*_service
  → financial_*_repo
  → tablas: payment_conflicts, financial_ledger, disputes, refunds, etc.
  → financial_automation_service (ciclos cron, alertas)
```

Autorización financiera: permisos granulares vía `core/financial_automation_authorization.py` y decoradores en blueprints.

---

## 4. Autenticación y sesiones

| Aspecto | Implementación |
|---------|----------------|
| Token | JWT HS256 firmado con `FLASK_SECRET_KEY` |
| Sesión por pestaña | UUID en `sessionStorage` + header `X-Ruana-Session-Id` |
| Store servidor | Dict en memoria (`auth_session.py`) + set revocados |
| TTL | `RUANA_ALIADO_SESSION_EXPIRES`, `RUANA_ADMIN_SESSION_EXPIRES` (default 3600s) |
| Aliado login | Código 5 dígitos + PIN 4–6 (`POST /api/aliado/login`) |
| PIN aliado | `aliado_pin_auth.py` + `aliado_pin_service.py` — setup, bloqueo, recuperación OTP email |
| Admin login | `POST /api/admin/validar` — hashes en JSON externo |
| Cron | Header `X-Ruana-Cron-Secret` |

**Limitación Verificada:** store de sesiones no compartido entre workers/instancias gunicorn.

---

## 5. Configuración de negocio

| Archivo | Contenido |
|---------|-----------|
| `RUANA/config/ruana_reglas_v1.json` | Umbrales score, competencia, purga, `apoyo_pct`, métodos pago manual |
| `RUANA/config/oficios_ruana.json` | Catálogo oficios (39 oficios — verificar conteo al cambiar) |
| `RUANA/core/db_constants.py` | `MAX_GRUPOS_POR_CP = 5`, estados grupo, regex invitación |

Motor evaluación (`engines/motor_evaluacion.py`): umbrales 0.70, 0.80, 6 meses **hardcodeados**; `reglas: []` vacío en JSON.

---

## 6. Observabilidad

| Mecanismo | Estado |
|-----------|--------|
| Logs aplicación | `print` en boot (`[RUANA][BOOT]`) — sin framework logging estructurado |
| Health HTTP | `/api/health` — no deep check BD |
| Audit financiero | `financial_audit_service`, tablas `audit_log` / eventos |
| Métricas Cloud Run | Infra GCP — **No verificado** en repo |
| Flask-Limiter | Memoria local por IP |

---

## 7. Testing (arquitectura QA)

```text
pytest (RUANA/tests/) — SQLite, mocks, Flask test client — **1007 passed**, 11 skipped (2026-09-04)
    ↑ gate en PR (ruana-qa.yml job pytest)

Playwright (e2e/) — arranca run.py, SQLite temporal, admin_credentials.qa.json
    ↑ push main/dev + workflow_dispatch (job e2e)
```

Fixtures de sesión en `conftest.py` limpian `_RUANA_SESSION_STORE` entre tests.

---

## 8. Decisiones arquitectónicas frágiles

1. **Monolito Flask** con extracción parcial — coherencia depende de fachadas `DBManager`.
2. **Dual BD** — toda feature nueva debe probarse en SQLite (CI) y validarse en Postgres (prod).
3. **RLS Supabase parcial e irrelevante** para API actual — solo 2/29 migraciones con RLS; service role bypasea en todos los casos.
4. **CORS abierto** — `CORS(app)` sin allowlist; PR pendiente.
5. **Firebase Hosting sin assets** — todo el tráfico va a Cloud Run (coste/latencia vs CDN estático).
6. **Financial module acoplado** a mismo proceso — jobs cron son HTTP al mismo servicio.

---

## 9. Referencias cruzadas

- Instalación: [`SETUP.md`](SETUP.md)
- Variables: [`ENVIRONMENT_VARIABLES.md`](ENVIRONMENT_VARIABLES.md)
- Deploy: [`DEPLOYMENT.md`](DEPLOYMENT.md)
- Flujos detallados: [`flujos/`](flujos/)
- Seguridad sesiones: [`seguridad/autenticacion-sesiones.md`](seguridad/autenticacion-sesiones.md)
- Cron: [`operaciones/cloud_scheduler_jobs.md`](operaciones/cloud_scheduler_jobs.md)
