# RUANA

**RUANA** (*Red Unida de Apoyo entre Negocios Aliados*) es un sistema de control, coordinación y reputación profesional para redes locales de profesionales y pequeños negocios. Organiza a los profesionales por territorio (código postal), limita la competencia dentro de cada zona mediante plazas de oficio, y registra el comportamiento (score, encargos, Apoyo económico a la red) con consecuencias reales.

> **Principio de autoridad:** este documento describe únicamente lo verificado en el código y la documentación del repositorio. Si hay conflicto entre este README y el código, prevalece el **código**. Lo no confirmado se marca como `NO VERIFICADO`, `PENDIENTE` o `PLANIFICADO`.

| Campo | Valor |
|-------|-------|
| Fecha de auditoría | 2026-09-04 (auditoría documental + pytest local) |
| Commit de referencia al auditar | `main` @ `7ea0fa1` (21 blueprints, 37 services, 31 repos, 29 migraciones PG) |
| Pack documentación de cierre | [`docs/HANDOFF.md`](docs/HANDOFF.md) · [`docs/PROJECT_AUDIT.md`](docs/PROJECT_AUDIT.md) |
| Informe auditoría documental | [`docs/exports/AUDITORIA_DOCUMENTAL_2026-09-04.md`](docs/exports/AUDITORIA_DOCUMENTAL_2026-09-04.md) |
| Informe auditoría anterior | [`docs/exports/AUDITORIA_DOCUMENTAL_2026-08-15.md`](docs/exports/AUDITORIA_DOCUMENTAL_2026-08-15.md) |
| Fase declarada en roadmap | pre-MVP avanzada (v0.9) |
| Código fuente principal | `RUANA/` |
| Hosting público verificado | Firebase Hosting → Cloud Run (`https://ruana-4293f.web.app`) |
| Tests backend (verificado 2026-09-04) | **1007 passed**, 11 skipped (`PYTHONPATH=RUANA python3 -m pytest RUANA/tests -q`) |

---

## 1. Visión del producto

### Qué es RUANA

Una plataforma web (Flask + HTML/JS) donde los **aliados** (profesionales) se registran, se agrupan por código postal y oficio, reciben y gestionan encargos entre ellos, conversan mediante una **negociación guiada**, cierran importes y aportan un porcentaje (“Apoyo RUANA”) a la red. Un panel de **administración** gobierna invitaciones, pagos, suplentes, competencia y métricas.

### Problema que intenta resolver

Las recomendaciones entre profesionales locales carecen de memoria, reglas y consecuencias. RUANA introduce:

- memoria persistente (historial de aliados, contactos, pagos, score);
- reglas territoriales (grupos por CP, plazas por oficio);
- reputación medible (score → estado operativo);
- gobernanza (admin, competencia, purga, impugnaciones).

### Quién utiliza RUANA

| Rol | Uso verificado |
|-----|----------------|
| **Aliado** | Registro, login **código + PIN** (4–6 dígitos), panel (`aliado.html`), directorio, solicitudes, solicitudes semanales, conexiones, perfil, pagos, notificaciones |
| **Administrador** | Panel (`admin.html`): activar/rechazar aliados, campañas, pagos, competencia, reglas, métricas |
| **Visitante** | Páginas de acceso (`index.html`, `invite.html`) e inicio de registro |

### Propuesta de valor (deducible del producto)

Orden profesional territorial: un oficio principal por plaza en cada grupo, reputación con consecuencias, y un flujo de encargo con cierre económico trazable.

### Qué lo hace diferente (según código)

- Territorio por **código postal** con tope de grupos.
- **Exclusividad de plaza** por oficio principal (las especializaciones no ocupan plaza).
- Score como fuente del estado del aliado (“el panel no piensa”).
- Apoyo económico a la red calculado sobre el importe cerrado (configurable).

---

## 2. Principios y reglas fundamentales

| Principio | Evidencia | Notas |
|-----------|-----------|-------|
| Score define el estado | `score_service.score_a_estado` (fachada en `DBManager`) | Bandas ÉLITE / DESTACADO / ESTABLE / EN RIESGO / COMPETENCIA |
| Login aliado código + PIN | `POST /api/aliado/login` | Código 5 dígitos + PIN 4–6 dígitos; rate limit (`30/h`, `10/min`); bloqueo tras intentos (`RUANA_PIN_MAX_INTENTOS`); recuperación OTP por email (`aliado_pin_auth.py`, `auth_bp.py`) |
| Sesión por pestaña | JWT + `sessionStorage` + `X-Ruana-Session-Id` | Lógica en `core/auth_session.py` |
| Territorio = código postal | Campo `codigo_postal` | |
| Máx. 5 grupos activos por CP | `MAX_GRUPOS_POR_CP` en `core/db_constants.py` | |
| Una plaza = un oficio principal por grupo | `grupo_service` + docs de flujo | Especializaciones no ocupan plaza |
| Score inicial al registrarse = 50 | `aliado_service` / flujo registro | |
| Umbral de competencia = 15 | `ruana_reglas_v1.json` | Reinicio tras derrota: 50 |
| Apoyo RUANA = % sobre importe | `apoyo_pct` (12.0 en config) | `pago_service` |
| Backend-first | Flask sirve UI y API | Firebase Hosting reescribe a Cloud Run |
| Campamento Base | 37 `services/` + 31 `repositories/` con SQL real + fachada `DBManager` (~1.969 LOC) | Extracción avanzada; `DBManager` sigue como compatibilidad |

### ⚠️ INCONSISTENCIAS / DISCREPANCIAS DETECTADAS

1. **Chat libre vs negociación:** las rutas legacy `/api/chat_enviar`, `/api/chat/enviar` (POST) responden **410** (`negociacion_bp`). El flujo vigente de encargo es **negociación guiada**. El chat de mensajes (`chat_service`, tabla `chat_mensajes`) sigue existiendo para contactos que lo usen vía `/api/contactos/<id>/mensajes`, pero la UI principal no promueve chat libre.
2. **Esquema `comision_porcentaje`:** DDL default `0.05` en `schema_service`; en runtime el cierre usa `apoyo_pct/100` (= **0.12** con config actual). Ver `contacto_service`.
3. **Esquema competencia `suplente_*` vs `retador_*`:** migración renombra; código mantiene compatibilidad.
4. **RLS vs service role:** migraciones definen RLS; el backend usa **service role** y bypasea RLS. La autorización efectiva es la de la API Flask.
5. **Drift SQLite/Postgres:** varias tablas/columnas existen solo en init SQLite o parches runtime Postgres (`schema_service._init_postgres_schema`). No asumir paridad sin verificar migraciones.
6. **`ingresos_ruana.apoyo_ruana_2pct`** (PG migración) vs **`contactos_ruana.apoyo_ruana`** — nombres distintos en tablas relacionadas.
7. **Motor evaluación:** umbrales de filtros (0.70, 0.80, 6 meses) están **hardcodeados** en `motor_evaluacion.py`; no en `ruana_reglas_v1.json` (`reglas: []` vacío).
8. **`RUANA/ruana.db` local:** generado en runtime; **gitignored** (`*.db`). No usar como referencia de schema; usar migraciones + `_init_db()`.

---

## 3. Funcionalidades actuales

Leyenda: 🟢 operativo · 🟡 parcial / requiere revisión · 🔴 no implementado · ⚠️ requiere atención técnica

| Funcionalidad | Estado | Descripción |
| ------------- | ------ | ----------- |
| Registro | 🟢 | `register.html` + `POST /api/aliados/registrar` → `aliado_service` |
| Perfil | 🟢 | Datos, foto, catálogo de servicios |
| Grupos / territorio | 🟢 | Grupos por CP, plazas, suplentes `en_espera` (`grupo_service` / `aliado_service`) |
| Chat libre (encargo) | 🔴 | Rutas globales legacy → 410; sustituido por negociación guiada |
| Mensajes de contacto (chat_mensajes) | 🟡 | `chat_service` + `/api/contactos/<id>/mensajes`; no es el flujo principal de UI |
| Negociación / acuerdos | 🟢 | `negociacion_service` + `negociacion_bp` + UI; E2E alineado |
| Captación (invitaciones / referidos / campañas) | 🟢 | `invitacion_service`, `referido_service`; no hay módulo llamado “captación” |
| Aliados | 🟢 | CRUD, estados, directorio, pausa, foto, Stripe onboarding |
| Pagos / Apoyo RUANA | 🟢 | Manual (Bizum/IBAN/QR) + revisión admin + impugnación |
| Stripe Connect (pagos encargo) | 🟡 | Implementado (`pagos_bp`, webhook); requiere `RUANA_STRIPE_PAYMENTS_ENABLED=1` y secretos |
| Notificaciones | 🟢 | Inbox aliado + centro de comunicación / soporte |
| Administración | 🟢 | Panel amplio vía `admin_service` + rutas admin |
| Competencia por score | 🟢 | `competencia_service`; umbral config; UI/E2E parcial |
| Purga mensual | 🟡 | Lógica/endpoint existen; operación en producción `NO VERIFICADO` |
| Auth admin Firebase | 🔴 | `PLANIFICADO` (plan en archive); vigente: credenciales hasheadas |
| Supabase Auth / `profiles` | 🟡 | Tabla en migración; login Flask **no** usa `auth.users` |
| Módulo financiero admin (FASE 02–13) | 🟢 | 7 blueprints `financial_*` + 14 services/repos financieros; cron automatización FASE 11 |
| Crecimiento orgánico de grupo | 🟢 | `grupo_crecimiento_service` + migración `20260819000100`; invitaciones tipo crecimiento |
| Solicitudes semanales | 🟢 | `solicitud_semanal_service` + `solicitudes_semanales_bp` + migración `20260819000200` |
| Login aliado PIN + recuperación | 🟢 | Código + PIN obligatorio; setup inicial; cambio; recuperación email OTP |
| Modularización Campamento Base | 🟡 | 37 services + 31 repos; `DBManager` (~1.969 LOC) sigue como fachada |

---

## 4. Arquitectura

```text
Navegador (HTML/JS vanilla)
        │
        ▼
Firebase Hosting (proyecto ruana-4293f)
  public: firebase-public/  (vacío a propósito; solo rewrite)
        │ rewrite **
        ▼
Cloud Run service "ruana" (europe-west1)
  Docker: python:3.13-slim + gunicorn → web.app:app
        │
        ├── web/app.py (~546 líneas: HTML, estáticos, auth admin)
        │     └── 21 Blueprints (~315 rutas API únicas + alias EN/ES financiero; ~349 con app.py)
        │           └── core/services/<dominio>_service.py
        │                 └── core/repositories/<dominio>_repo.py
        ├── Postgres (Supabase) vía DATABASE_URL
        ├── Supabase Storage
        ├── SMTP (correo de bienvenida)
        ├── Stripe Connect (opcional, flag)
        └── Fallback local: SQLite (RUANA_DB_PATH)
```

| Capa | Tecnología / pieza verificada |
|------|-------------------------------|
| Frontend | HTML, CSS, JS vanilla en `RUANA/web/` |
| Backend | Flask 2.3.3, Flask-Cors, PyJWT, Werkzeug, gunicorn, stripe |
| Dominio | `RUANA/core/services/` (37 services, incl. financiero, PIN, crecimiento, solicitudes semanales) |
| Persistencia | `DBManager` fachada (~1.969 líneas) + 31 repositories con SQL |
| Constantes BD | `RUANA/core/db_constants.py` |
| Sesiones | `RUANA/core/auth_session.py` |
| Blueprints | 21: core (`admin`, `aliado`, `auth`, `catalogo`, `contactos`, `evaluacion`, `invitacion`, `negociacion`, `pagos`, `referidos`, `solicitudes`, `solicitudes_semanales`, `soporte`, `stripe_webhook`) + financiero (`financial_admin`, `financial_automation`, `financial_conflicts`, `financial_disputes`, `financial_ledger`, `financial_reconciliation`, `financial_refunds`) |
| BD | Postgres (psycopg) o SQLite |
| Storage | Supabase Storage (+ fallback local con `RUANA_ALLOW_LOCAL_UPLOADS`) |
| Hosting | Firebase Hosting → Cloud Run |
| Migraciones PG | `supabase/migrations/` — **29** archivos; **2 con RLS**, **27 sin RLS** |
| QA | pytest **1007 tests** (push/PR) + Playwright E2E (push / manual) |

### Patrón Campamento Base (verificado)

```text
Consumidor (blueprints / tests)
    → DBManager.método()          # fachada / wrapper (~1.969 LOC)
        → <dominio>_service.*     # lógica de negocio
            → <dominio>_repo.*    # SQL (31 repos con consultas reales)
                → SQLite o Postgres
```

No hay herencia de services desde `DBManager`: es **delegación** pasando `self` (o cursor) al service.

### Subsistema financiero (FASE 02–13) — VERIFICADO

Implementado en código y cubierto por tests `test_financial_*` / `test_stripe_*`. Documentación de flujos en `docs/flujos/financial-*.md`.

| Fase / dominio | Migración PG (fecha) | Blueprint API | Service principal |
|----------------|---------------------|---------------|-------------------|
| FASE 02 — Webhooks + reconciliación base | `20260818000100` (2026-08-18) | `stripe_webhook_bp` | `stripe_webhook_service`, `financial_reconciliation_service` |
| FASE 03 — Transferencias Stripe | `20260818000200`–`00400` | (vía `pagos_bp`) | `financial_transfer_service`, `financial_transaction_service` |
| FASE 04 — Conflictos financieros | `20260818000500` | `financial_conflicts_bp` | `financial_conflict_service` |
| FASE 05 — Reembolsos | `20260818000600` | `financial_refunds_bp` | `financial_refund_service` |
| FASE 06 — Disputas Stripe | `20260818000700` | `financial_disputes_bp` | `financial_dispute_service` |
| FASE 07 — Reconciliación avanzada | `20260818000800` | `financial_reconciliation_bp` | `financial_reconciliation_advanced_service` |
| FASE 08 — Ledger (libro mayor) | `20260818000900` | `financial_ledger_bp` | `financial_ledger_service`, `financial_ledger_reconciliation_service` |
| FASE 09 — Panel admin financiero | `20260818001000` | `financial_admin_bp` | `financial_admin_service` |
| FASE 10 — Seguridad financiera | `20260818001100` | (decoradores en blueprints) | permisos granulares `financial_admin_authorization`, `ledger_authorization` |
| FASE 11 — Automatización / alertas | `20260818001200` | `financial_automation_bp` | `financial_automation_service` |
| FASE 13 — P0 endurecimientos | `20260818001300` | — | tests `test_financial_fase13a_p0.py` |
| Serial `financial_transfers.id` | `20260903000100` (2026-09-03) | — | `financial_transfer_repo` |

**Prefijos API financieros (alias EN + ES por blueprint):**

- `/api/admin/financial*` y `/api/admin/finanzas*` — panel admin
- `/api/admin/financial-conflicts*` / `conflictos-financieros`
- `/api/admin/financial-refunds*` / `reembolsos-financieros`
- `/api/admin/financial-disputes*` / `disputas-financieras`
- `/api/admin/financial-reconciliation*` / `reconciliacion-financiera`
- `/api/admin/financial-ledger*` / `libro-mayor-financiero`
- `/api/admin/financial-automation*` / `automatizacion-financiera`

**Permisos admin financieros (deny-by-default):** `financial.dashboard.view`, `financial.payments.view`, `financial.transfers.view`, `financial.refunds.view`, `financial.disputes.view`, `financial.conflicts.view`, `financial.reconciliation.view`, `financial.ledger.view`, `financial.audit.view` — mapeados desde permisos legacy `leer`/`escribir`/`configurar` (`core/financial_admin_authorization.py`).

**Flujos clave:**

- **Reembolso:** admin inicia → aprobación dual opcional (`RUANA_FINANCIAL_REQUIRE_APPROVAL`) → ejecución Stripe → estados `REEMBOLSO_PENDIENTE` / `REEMBOLSADO`.
- **Disputa:** webhook `charge.dispute.created` → `financial_dispute_service` → estado `DISPUTA_STRIPE`.
- **Reconciliación:** comparación RUANA↔Stripe sin corrección automática de estados irreversibles; alertas vía `financial_automation_service`.
- **Cron:** `POST /api/admin/financial-automation/ejecutar-ciclo` — ver [`docs/operaciones/cloud_scheduler_jobs.md`](docs/operaciones/cloud_scheduler_jobs.md).

---

## 5. Estructura del proyecto

```text
/
├── README.md                     # Manual Maestro (única fuente en la raíz)
├── ROADMAP.md                    # Puntero a docs/operaciones/roadmap.md
├── Dockerfile
├── firebase.json
├── firebase-public/              # Vacío salvo .gitkeep
├── package.json                  # Scripts deploy / QA
├── playwright.config.js
├── .env.example
├── .github/workflows/            # Deploy + ruana-qa (push/PR)
├── docs/                         # Docs secundarias + archive
├── e2e/                          # Playwright
├── scripts/                      # Deploy, secretos GCP
├── supabase/migrations/          # 29 DDL Postgres (2 con RLS)
├── dev-tools/code-map/           # Mapa interactivo del código (herramienta local)
└── RUANA/
    ├── config/                   # Reglas, oficios, ejemplos admin
    ├── core/
    │   ├── db_manager.py         # Fachada Campamento Base (~1.969 LOC)
    │   ├── db_constants.py
    │   ├── auth_session.py
    │   ├── admin_auth.py
    │   ├── aliado_pin_auth.py    # Hash PIN aliado, bloqueo, setup token
    │   ├── negociacion_manager.py
    │   ├── services/             # 37 módulos de dominio (+ financiero, PIN, crecimiento)
    │   └── repositories/         # 31 repos con SQL
    ├── engines/                  # Motor de evaluación v0.2
    ├── events/ / metrics/
    ├── web/
    │   ├── app.py                # Setup Flask + HTML (~546 LOC)
    │   ├── blueprints/           # 21 blueprints (~315 rutas API únicas)
    │   ├── *.html
    │   └── static/
    ├── tests/
    └── scripts/
```

---

## 6. Base de datos

### Dualidad SQLite / Postgres

- **Producción prevista:** Postgres Supabase (`DATABASE_URL`).
- **Local / CI pytest:** SQLite (`RUANA_DB_PATH`).
- Compatibilidad vía `postgres_compat.py` y migraciones `sqlite_compat_*`.
- Schema runtime adicional vía `schema_service` / `_init_db`.

### Tablas principales

| Tabla | Propósito |
|-------|-----------|
| `aliados` | Profesionales: código, datos, oficio, score, estado, grupo, foto, linaje |
| `grupos` | Grupos territoriales por `codigo_postal` |
| `solicitudes` | Solicitudes en grupo |
| `contactos_ruana` | Encargos (trabajo, importes, Apoyo) |
| `chat_mensajes` | Mensajes de contacto (legado; UI principal = negociación) |
| `confirmaciones_trabajo` | Declaraciones de importe |
| `ingresos_ruana` | Apoyo cobrado |
| `payment_conflicts` | Impugnaciones |
| `invitaciones` / `invitaciones_oficio` | Códigos de invitación |
| `referidos` | Linaje invitador → referido |
| `competencia` / `competencia_pendiente` | Retos titular/retador |
| `notificaciones_aliado` | Inbox |
| `score_movimientos` | Ledger de score |
| `evaluaciones` / `evaluaciones_historico` | Motor de evaluación |
| `grupo_oficio_cerrado` | Oficios cerrados |
| `avisos_grupo` | Avisos |
| `eventos_sistema` / `audit_log` | Trazabilidad |
| `aliados_eliminados` | Histórico de bajas |
| `aliado_accesos_dia` | Accesos diarios |
| `profiles` | Liga a `auth.users` (migración); **uso en login Flask: no verificado / no usado** |

Tablas adicionales en runtime (p. ej.): `invitacion_campanas`, `catalogo_servicios_aliado`, tablas de soporte, `negociacion_eventos`.

### Storage

Buckets (migración): `ruana-public`, `ruana-comprobantes`, `ruana-conflictos`.

### Relaciones relevantes

```text
Aliado
  → Grupo (codigo_postal + plaza de oficio)
  → Invitaciones / Referidos
  → Contactos
       → Negociación / (mensajes legado)
       → Importe → Apoyo → (opcional) Conflicto
  → Score / score_movimientos → estado
  → Competencia (titular vs retador)
```

### Datos sensibles

Email, teléfono, nombre, **código de aliado** (secreto de acceso), comprobantes, credenciales admin (hashes), datos de cobro de la red en config (**no reproducir valores**).

### Permisos BD

RLS definido solo en **2 de 29** migraciones (`20260519000100_init_ruana_clean.sql` — políticas completas; `20260819000200_solicitudes_semanales.sql` — `ENABLE ROW LEVEL SECURITY` sin políticas `CREATE POLICY` en el archivo). Las **27 restantes no definen RLS**. El backend usa **service role** y bypasea RLS en todos los casos. La autorización efectiva es la de la API Flask.

---

## 7. Reglas de negocio

Formato: `CONDICIÓN → ACCIÓN → RESULTADO`.

### Registro

- Datos F07 válidos y únicos → aliado con código de 5 dígitos y score **50**.
- Oficio fuera de catálogo → `pendiente_validacion` (sin grupo).
- Oficio en catálogo + plaza libre en CP → grupo + `activo`.
- Sin plaza y &lt; 5 grupos en CP → crear grupo + `activo`.
- 5 grupos y oficio ocupado en todos → `en_espera` (login panel 403 hasta incorporar).
- Invitación aplicable → consumir + linaje/score según tipo.

### Profesiones / catálogo

- `RUANA/config/oficios_ruana.json` — **39** oficios.
- Plaza = **oficio principal**; especializaciones no ocupan plaza.

### Territorio

- `MAX_GRUPOS_POR_CP = 5`.
- Estados de grupo: `activo`, `en_competencia`, `disuelto`.

### Score y estados

Fuente: `score_service` (rango **0–500**, tope diario **±10**):

| Score | Estado |
|------:|--------|
| 350–500 | ÉLITE |
| 200–349 | DESTACADO |
| 50–199 | ESTABLE |
| 15–49 | EN RIESGO |
| 0–14 | COMPETENCIA |

### Competencia

- Score &lt; 15 → lógica de competencia (`competencia_service`).
- Duración 30 días (config); reinicio tras derrota 50.
- Admin puede forzar competencia/suplencia.

### Purga

- Config: meses sin ganar + umbral score (`purga_*` en JSON).
- Endpoint/lógica existen; operación productiva `NO VERIFICADO`.

### Invitaciones / captación

- Invitación simple, de oficio (`RUANA-{grupo}-{OFICIO}-…`) y campañas admin.
- Referidos / linaje en `referido_service`.

### Encargos y Apoyo

- Contacto → trabajo → declarar importe → Apoyo = `importe × apoyo_pct/100` (default 12%).
- Comprobante → revisión admin → posible impugnación.
- Cobro manual: Bizum / IBAN / QR (config en `ruana_reglas_v1.json`).
- Cobro Stripe Connect: checkout + transfer al profesional (si `RUANA_STRIPE_PAYMENTS_ENABLED=1`).

### Negociación

- Sustituye chat libre para encargos (`negociacion_service` + UI).

### Administración

- Activar/rechazar/eliminar; suplentes; cerrar/abrir plazas; pagos; reglas; métricas.
- Permisos: `leer`, `escribir`, `eliminar`, `configurar`.
- `require_admin`: cualquier admin autenticado accede a endpoints de lectura del panel.
- `require_admin_escritura`: exige `escribir` o `configurar` en la lista de permisos; si está vacía → **403** en escritura (no hay fallback a permisos completos).

---

## 8. Flujos principales

### Registro

Acceso `index` / `invite` / `register` → validar invitación → `POST /api/aliados/registrar` → código + estado por plaza/CP → email SMTP opcional.

### Perfil

Login por **código + PIN** → panel aliado → datos / foto Storage / catálogo servicios.

### Grupos / sistema territorial

Al registrar: buscar plaza → crear grupo si cabe → o `en_espera` → admin incorpora suplente.

### Captación / invitaciones

Generar invitación o campaña → registro con código → referido/linaje + consumo.

### Aliados

Sesión JWT por pestaña → directorio, solicitudes, conexiones, perfil, notificaciones.

### Acuerdos / negociación

Contacto → negociación guiada → importe → Apoyo.

### Chat

Chat libre de encargo: **no operativo** (410). Vigente: negociación. Canal de **soporte** aliado–admin: activo (distinto del chat de encargo).

### Pagos

Importe → Apoyo → comprobante → admin aprueba/rechaza → impugnación opcional.

### Notificaciones

Eventos → `notificaciones_aliado` + centro de comunicación.

### Administración

Login admin → dashboard, pendientes, pagos, campañas, competencia, reglas, métricas.

---

## 9. Seguridad

### Autenticación

| Actor | Mecanismo |
|-------|-----------|
| Aliado | Código 5 dígitos + PIN 4–6 dígitos → JWT HS256 (`FLASK_SECRET_KEY`), header `X-Ruana-Session-Id` (`auth_session.py`, `aliado_pin_auth.py`, `auth_bp.py`) |
| Admin | ID + contraseña hasheada (`admin_auth.py`) → sesión JWT análoga |

### Autorización

- `@require_aliado`, `@require_admin`, `@require_admin_escritura`.
- Middleware en `/api/admin/*` (salvo login/logout).
- Hito 2A/2B: tests de permisos; PII de listados admin-only; PUT aliado filtra campos (`score`/`estado`/`grupo_id` no editables por self).
- Roadmap: Hito 2 **activo / parcial** (aún hay endurecimientos pendientes).

### RLS

Definido parcialmente (2/29 migraciones); **eludido por service role** en el camino Flask. SQLite sin RLS. Tabla `solicitudes_semanales` tiene `ENABLE ROW LEVEL SECURITY` pero sin políticas en migración — **efecto en producción: NO VERIFICADO**.

### CORS

`CORS(app)` sin restricción de orígenes en `web/app.py` (Flask-Cors con configuración por defecto = todos los orígenes). **PR abierto sin merge:** `cursor/cors-pago-manual-allowlist-2cc1` propone allowlist — **NO VERIFICADO** en `main`.

### Roles

App: aliado / admin. `profiles.role` preparado para Supabase Auth — no cableado al login actual.

### Secretos (solo nombres)

`FLASK_SECRET_KEY`, `RUANA_ADMIN_CREDENTIALS_JSON` / `_PATH`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_ANON_KEY`, `DATABASE_URL`, `RUANA_SMTP_*`, secretos GCP/GitHub Actions.

### Protección y riesgos

- Sesión por pestaña (mitiga cookie compartida).
- JWT validable entre instancias Cloud Run; revoke store en memoria (limitación).
- Login aliado: **dos factores de conocimiento** (código + PIN) con rate limit y bloqueo por intentos — el código sigue siendo secreto de alto valor.
- ⚠️ Datos de cobro en `ruana_reglas_v1.json` versionado **y fallbacks hardcodeados** en `pago_service.py` (requieren migración a secret manager).
- ⚠️ CORS abierto a todos los orígenes (`CORS(app)` sin allowlist).
- ⚠️ Previews/rutas de prueba en la misma app.
- ⚠️ Cloud Run con acceso de red no autenticado; auth es de aplicación.

---

## 10. Integraciones externas

| Servicio | Función | Estado |
| -------- | ------- | ------ |
| Supabase Postgres | BD principal | 🟢 |
| Supabase Storage | Fotos, comprobantes, QR | 🟢 |
| Supabase Realtime | Publication en migración | 🟡 DDL; uso cliente `NO VERIFICADO` |
| Firebase Hosting | Rewrite a Cloud Run | 🟢 |
| Google Cloud Run | Runtime Flask | 🟢 |
| Artifact Registry | Imágenes Docker | 🟢 |
| Google Secret Manager | Secretos runtime | 🟢 |
| SMTP | Email bienvenida | 🟡 Depende de vars |
| PayPal / Revolut / Bizum | Cobro Apoyo manual (QR/datos en config) | 🟡 Manual |
| Stripe Connect | Pagos encargo (checkout, onboarding, webhook) | 🟡 Implementado; flag + secretos |
| Firebase Authentication | Auth admin/usuarios | 🔴 Planificado |

---

## 11. Configuración

### Variables de entorno (ver `.env.example`)

| Variable | Uso |
|----------|-----|
| `FLASK_SECRET_KEY` | Firma JWT / sesiones |
| `RUANA_ADMIN_SESSION_EXPIRES` / `RUANA_ALIADO_SESSION_EXPIRES` | TTL sesiones |
| `RUANA_ADMIN_CREDENTIALS_PATH` / `_JSON` | Credenciales admin |
| `FIREBASE_PROJECT_ID` | Proyecto Firebase/GCP |
| `GOOGLE_CLOUD_REGION` | Región |
| `ARTIFACT_REGISTRY_REPOSITORY` | Repo imágenes |
| `SUPABASE_URL` / `SUPABASE_ANON_KEY` / `SUPABASE_SERVICE_ROLE_KEY` | Supabase |
| `DATABASE_URL` | Postgres |
| `RUANA_DB_PATH` | SQLite fallback |
| `RUANA_SMTP_*` | Correo |
| `RUANA_PUBLIC_APP_URL` / `PUBLIC_APP_URL` | URL pública |
| `RUANA_STRIPE_PAYMENTS_ENABLED` | Activa Stripe Connect (0/1) |
| `STRIPE_SECRET_KEY` / `STRIPE_PUBLISHABLE_KEY` / `STRIPE_WEBHOOK_SECRET` | Stripe |
| `STRIPE_API_VERSION` | Versión API Stripe (default `2024-11-20.acacia`) |
| `RUANA_STRIPE_TRANSFER_TIMEOUT_DAYS` | Timeout transferencias |
| `RUANA_ALLOW_LOCAL_UPLOADS` | Storage local en QA |
| `PORT` | Puerto gunicorn |

### Config de negocio

- `RUANA/config/ruana_reglas_v1.json` — umbrales, Apoyo %, métodos de pago.
- `RUANA/config/oficios_ruana.json` — catálogo.
- Ejemplos / QA admin en `RUANA/config/`.

### Dependencias

- Python: `RUANA/web/requirements.txt` (+ `requirements-dev.txt` para QA).
- Node: solo para Firebase CLI / Playwright / scripts.

---

## 12. Desarrollo local

### Requisitos

1. **Python** 3.11+ (Dockerfile usa 3.13; CI pytest usa 3.11).
2. **pip**.
3. Opcional: **Node.js** + **npm** para E2E/deploy.
4. Opcional: Postgres/Supabase; si no, **SQLite**.

### Pasos

1. Clonar el repo.
2. `cp .env.example .env` y editar al menos `FLASK_SECRET_KEY` (y Postgres si aplica).
3. Entorno virtual e instalación:
   ```bash
   cd RUANA/web
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
4. Credenciales admin: `docs/seguridad/credenciales-admin.md`.
5. Arrancar:
   ```bash
   cd /ruta/al/repo/RUANA
   export PYTHONPATH=.
   python -m flask --app web.app run --host 0.0.0.0 --port 8080
   ```
6. Abrir `http://localhost:8080/`.

### Tests

```bash
pip install -r RUANA/web/requirements-dev.txt
python -m pytest RUANA/tests -q

npm ci
npx playwright install chromium
npm run qa:e2e
```

---

## 13. Deploy

`Deploy` = publicar una versión.

### Dónde

| Pieza | Destino |
|-------|---------|
| App | Cloud Run `ruana`, `europe-west1`, proyecto `ruana-4293f` |
| Entrada | `https://ruana-4293f.web.app` → rewrite Cloud Run |
| Imagen | Artifact Registry `…/ruana/ruana` |
| BD/Storage | Supabase |

### Cómo

- **Producción:** push a `main` → `.github/workflows/deploy-firebase.yml`.
- **Preview:** workflows de preview / rama `dev`.
- **Manual:** scripts `npm run cloudrun:*`, `deploy:hosting`, `supabase:push`.

### Comprobar / fallos / rollback

- Health: `GET /api/health`.
- Fallos: logs GitHub Actions + Cloud Run.
- Rollback: revisar tráfico a revisión anterior en Cloud Run (`NO VERIFICADO` el procedimiento día a día del equipo más allá de redeploy).

---

## 14. Estado técnico actual

### Funcionando

Registro, login (código+PIN), paneles, grupos/plazas, invitaciones/referidos/campañas, contactos, negociación, Apoyo con revisión, notificaciones, competencia por score, módulo financiero admin (FASE 02–13), crecimiento orgánico, solicitudes semanales, deploy cloud, **37 services + 31 repos**, CI automático pytest (**1007 tests** verificados 2026-09-04).

### Parcial

Hito 2 seguridad; purga (lógica sin cron verificado); SMTP/Storage según secretos; RLS no efectivo en API; `DBManager` fachada residual; drift SQLite/Postgres; Stripe dependiente de flag; motor evaluación sin automatización periódica verificada.

### Pendiente

Firebase Auth admin; cablear `profiles`/Supabase Auth al login; sincronización completa migraciones PG; cron purga/motor; retirar o regenerar `ruana.db` commiteado.

### Riesgos técnicos

1. Código de aliado sigue siendo secreto de alto valor (aunque PIN añade segundo factor).
2. CORS sin allowlist (`CORS(app)` por defecto).
3. Service role bypasea RLS (solo 2/29 migraciones con RLS).
4. Drift SQLite/Postgres (tablas/columnas no en todas las migraciones).
5. Datos de cobro en `ruana_reglas_v1.json` **y fallbacks en `pago_service.py`** versionados.
6. Revocación de sesión en memoria (multi-instancia).
7. Admin credenciales JSON puente.
8. `comision_porcentaje` DDL (0.05) vs runtime (`apoyo_pct/100`).

### Deuda técnica

- Completar paridad migraciones Supabase ↔ `schema_service`.
- Plan Firebase Auth sin implementar.
- Orquestador CLI desconectado del servidor web.
- Automatizar purga y motor evaluación (decisión operativa pendiente).

---

## 15. Estado del producto

### Implementado

Registro, perfil, grupos territoriales, plazas/suplentes, aliados, invitaciones/referidos/campañas, solicitudes, contactos, negociación/acuerdos, Apoyo con admin, Stripe Connect (opcional), notificaciones, competencia por score, panel admin, deploy, extracción Campamento Base (services + repos), CI automático pytest.

### En desarrollo

Hito 2 seguridad (parcial); paridad migraciones PG; consolidación docs/ops.

### Planificado

Admin → Firebase Authentication (plan en archive).

### No verificado

Estado exacto schema/RLS remoto en vivo; Realtime en cliente; purga en operación real (cron); Stripe activo en producción; rollback operativo cotidiano.

---

## 16. Puntos críticos de RUANA

| Área | Por qué |
|------|---------|
| Auth / sesiones (`auth_session.py`) | JWT, revoke en memoria, login por código |
| Permisos admin / Hito 2 | Fallback de permisos; PII |
| Score (`score_service` + `ScoreRepo`) | Semáforo, competencia, tope diario |
| Grupos / CP / plazas | Exclusividad territorial |
| Contactos + Apoyo + conflictos | Dinero y reputación |
| Negociación | Contrato vigente de encargo |
| Storage comprobantes | Datos sensibles |
| Dual SQLite/Postgres | Drift |
| `ruana_reglas_v1.json` | Umbrales globales + cobro |
| Deploy secrets | Compromiso = acceso total |
| Fachadas `DBManager` | Compatibilidad durante extracción |

---

## 17. Reglas para futuros cambios

> Antes de modificar una funcionalidad crítica, comprobar sus dependencias, reglas de negocio, seguridad y efectos sobre otras funcionalidades.

1. **Código > documentación.** Actualizar este README al cambiar comportamiento.
2. Score es **0–500** con tope ±10/día; no asumir 0–100.
3. Contrato de encargo = **negociación guiada**, no chat libre.
4. Plaza = oficio principal; máx. **5** grupos por CP.
5. Apoyo usa `apoyo_pct`; impacta pagos y admin.
6. No subir secretos ni datos reales de cobro/credenciales.
7. Cambios de sesión deben respetar `X-Ruana-Session-Id` o migrar cliente y servidor juntos.
8. Seguridad de datos en la **API Flask**, no solo en RLS.
9. **Campamento Base:** al tocar un dominio mapeado (`aliado`, `grupo`, `score`, `pago`, `competencia`, `invitacion`, `solicitud`, `negociacion`, `chat`, `referido`, `catalogo`, `admin`), la lógica nueva va a `services/` (+ `repositories/` para SQL) y `DBManager` conserva la fachada. Extraer solo con **test CI** que proteja el comportamiento.
10. CI: `ruana-qa.yml` corre pytest en **push/PR** a `main`/`dev`; E2E en push o `workflow_dispatch`.

---

## 18. Roadmap

Fuente: [`docs/operaciones/roadmap.md`](docs/operaciones/roadmap.md) (2026-09-04). `ROADMAP.md` solo apunta ahí.

| Hito | Estado documentado |
|------|--------------------|
| 1 — Infra | Cerrado documentalmente |
| 2 — Seguridad y permisos | Activo / parcial |
| Invitaciones admin + campañas | Hecho en código |
| Métodos de pago + Storage | Hecho en código |
| Impugnación cobros | Hecho en código |
| Módulo financiero (FASE 02–13) | Hecho en código |
| Crecimiento orgánico de grupo | Hecho en código (2026-08-19) |
| Solicitudes semanales | Hecho en código (2026-08-19) |
| Login aliado PIN + recuperación | Hecho en código |
| Competencia automática | Hecho en main |
| Stripe Connect (pagos encargo) | FASE 14: Test en prod; **Live bloqueado** |
| Campamento Base (modularización) | **Avanzado** — 37 services + 31 repos; fachada `DBManager` (~1.969 LOC) |
| Pack documentación cierre | Hecho 2026-08-19; auditoría documental 2026-09-04 |
| Admin → Firebase Auth | Preparado, **no implementado** |
| CORS allowlist pagos manuales | **PR abierto** (`cursor/cors-pago-manual-allowlist-2cc1`); no en `main` |

Histórico: `docs/archive/ROADMAP_2026-05.md`.

No se inventan hitos fuera de fuentes del repo + estado verificable del código.

---

## Documentación secundaria

Índice: [`docs/README.md`](docs/README.md).

### Pack de cierre (2026-08-19)

- [`docs/HANDOFF.md`](docs/HANDOFF.md) — transferencia operativa
- [`docs/PROJECT_AUDIT.md`](docs/PROJECT_AUDIT.md) — auditoría técnica del repositorio
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — arquitectura verificada
- [`docs/SETUP.md`](docs/SETUP.md) — instalación y ejecución local
- [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) — despliegue CI/CD
- [`docs/ENVIRONMENT_VARIABLES.md`](docs/ENVIRONMENT_VARIABLES.md) — variables de entorno
- [`docs/KNOWN_ISSUES.md`](docs/KNOWN_ISSUES.md) — problemas conocidos

### Deep-dives y histórico

- [`docs/exports/AUDITORIA_DOCUMENTAL_2026-09-04.md`](docs/exports/AUDITORIA_DOCUMENTAL_2026-09-04.md) — informe de auditoría documental actual
- [`docs/exports/AUDITORIA_DOCUMENTAL_2026-08-15.md`](docs/exports/AUDITORIA_DOCUMENTAL_2026-08-15.md) — informe anterior
- [`docs/flujos/registro-aliados.md`](docs/flujos/registro-aliados.md)
- [`docs/seguridad/autenticacion-sesiones.md`](docs/seguridad/autenticacion-sesiones.md)
- [`docs/seguridad/credenciales-admin.md`](docs/seguridad/credenciales-admin.md)
- [`docs/operaciones/roadmap.md`](docs/operaciones/roadmap.md)
- Herramienta local: [`dev-tools/code-map/`](dev-tools/code-map/)

`docs/flujos/chat-y-alerta.md` documenta mensajes de contacto y alertas; las rutas globales de chat libre devuelven 410 — el flujo de encargo vigente es negociación guiada.

---

## 19. Handoff / mantenimiento

Ver [`docs/HANDOFF.md`](docs/HANDOFF.md) para checklist de recepción, secretos, operación recurrente y deuda priorizada.

## 20. Responsables o puntos de contacto

**No verificado** en el repositorio. Completar en `HANDOFF.md` §11 antes de cierre comercial.

## 21. Licencia

**Ausente.** No existe archivo `LICENSE` en la raíz del repositorio. Tratar como *all rights reserved* hasta publicación explícita de una licencia.

---

*Auditoría basada en inspección del repositorio y pytest local (2026-09-04). El README describe funcionalidades verificadas; lo demás está etiquetado explícitamente.*
