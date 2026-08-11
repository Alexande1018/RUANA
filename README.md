# RUANA

**RUANA** (*Red Unida de Apoyo entre Negocios Aliados*) es un sistema de control, coordinación y reputación profesional para redes locales de profesionales y pequeños negocios. Organiza a los profesionales por territorio (código postal), limita la competencia dentro de cada zona mediante plazas de oficio, y registra el comportamiento (score, encargos, Apoyo económico a la red) con consecuencias reales.

> **Principio de autoridad de este documento:** describe únicamente lo verificado en el código y la documentación del repositorio en la fecha de auditoría. Si hay conflicto entre este README y el código, prevalece el **código**. Lo no confirmado se marca como `NO VERIFICADO`, `PENDIENTE` o `PLANIFICADO`.

| Campo | Valor |
|-------|-------|
| Fecha de auditoría | 2026-08-11 |
| Fase declarada en roadmap | pre-MVP avanzada (v0.9) |
| Código fuente principal | `RUANA/` |
| Hosting público verificado | Firebase Hosting → Cloud Run (`https://ruana-4293f.web.app`) |

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
| **Aliado** | Registro, login por código, panel (`aliado.html`), directorio, solicitudes, conexiones, perfil, pagos, notificaciones |
| **Administrador** | Panel (`admin.html`): activar/rechazar aliados, campañas, pagos, competencia, reglas, métricas |
| **Visitante** | Páginas de acceso (`index.html`, `invite.html`) e inicio de registro |

### Propuesta de valor (deducible del producto)

Orden profesional territorial: un oficio principal por plaza en cada grupo, reputación con consecuencias, y un flujo de encargo con cierre económico trazable.

### Qué lo hace diferente (según código)

- Territorio por **código postal** con tope de grupos.
- **Exclusividad de plaza** por oficio principal (las especializaciones no ocupan plaza).
- Score como fuente del estado del aliado (“el panel no piensa”).
- Apoyo económico a la red calculado sobre el importe cerrado (configurables).

---

## 2. Principios y reglas fundamentales

Reglas estructurales verificadas en código/config:

| Principio | Evidencia | Notas |
|-----------|-----------|-------|
| Score define el estado | `DBManager.score_a_estado` | Bandas en código: ÉLITE / DESTACADO / ESTABLE / EN RIESGO / COMPETENCIA |
| Login aliado por código | `POST /api/aliado/login` | Sin contraseña de aliado |
| Sesión por pestaña | JWT + `sessionStorage` + header `X-Ruana-Session-Id` | Evita cruce de sesiones entre pestañas |
| Territorio = código postal | Campo `codigo_postal` en grupos/aliados | |
| Máx. 5 grupos activos por CP | `MAX_GRUPOS_POR_CP = 5` | |
| Una plaza = un oficio principal por grupo | Docs de flujo + lógica de registro | Especializaciones no ocupan plaza |
| Score inicial al registrarse = 50 | Flujo registro documentado y código | |
| Umbral de competencia = 15 | `ruana_reglas_v1.json` | Reinicio tras derrota: 50 |
| Apoyo RUANA = % sobre importe | `apoyo_pct` (12.0 en config) | |
| Backend-first | Flask sirve UI y API | Firebase Hosting solo reescribe a Cloud Run |

### ⚠️ INCONSISTENCIAS DETECTADAS

1. **Rango de score:** documentación antigua / Manual previo hablaba de score 0–100; el código y la migración `20260729000100_score_max_500.sql` usan **0–500** con banda ÉLITE (≥350). **Prevalece el código (0–500).**
2. **Chat libre vs negociación:** docs (`docs/flujos/chat-y-alerta.md`) y partes del Manual previo describen chat libre (p. ej. límite 30 mensajes). En `app.py`, los POST de chat libre responden **410**; el flujo vigente es **negociación guiada** (`negociacion_manager.py`, UI en `aliado.html`). Tests E2E aún buscan selectores de chat antiguo (`#modal-chat-ruana`).
3. **Esquema competencia `suplente_*` vs `retador_*`:** hay lógica de compatibilidad/migración entre nombres legacy y nuevos en `db_manager.py`.
4. **`README_RUANA_COMPLETO.md`:** el índice de docs lo presenta como copia idéntica del Manual; tras esta reconstrucción puede quedar desfasado respecto a `README.md`.
5. **RLS en Supabase vs backend:** las migraciones definen RLS, pero el backend usa **service role**, que bypasea RLS. La app Flask no depende de RLS para autorización.

---

## 3. Funcionalidades actuales

Leyenda: 🟢 operativo · 🟡 parcial / requiere revisión · 🔴 no implementado · ⚠️ existe pero requiere atención técnica

| Funcionalidad | Estado | Descripción |
| ------------- | ------ | ----------- |
| Registro | 🟢 | `register.html` + `POST /api/aliados/registrar`; validaciones, código 5 dígitos, asignación a grupo/plaza o espera |
| Perfil | 🟢 | Datos, foto, catálogo de servicios; APIs aliado/admin |
| Grupos / territorio | 🟢 | Grupos por CP, plazas por oficio, suplentes `en_espera`, fusión/viabilidad en backend |
| Chat libre | 🔴 | Endpoints legacy → 410; sustituido por negociación |
| Negociación / acuerdos | 🟢 | APIs `negociacion/*`, `acuerdos`, UI modal; E2E desfasado |
| Captación (invitaciones / referidos / campañas) | 🟢 | No hay módulo llamado “captación”; sí hay invitaciones, linaje/referidos y campañas admin |
| Aliados | 🟢 | CRUD operativo, estados, directorio, pausa, foto |
| Pagos / Apoyo RUANA | 🟡 | Comprobantes, métodos de pago (Bizum/IBAN/QR), impugnación y revisión admin; **sin pasarela automática** (PayPal/Stripe API no integradas) |
| Notificaciones | 🟢 | Inbox aliado + centro de comunicación / soporte |
| Administración | 🟢 | Panel amplio: aliados, pagos, competencia, reglas, métricas, campañas |
| Competencia por score | 🟢 | Automática por umbral; forzar desde admin; UI/E2E parcial |
| Purga mensual | 🟡 | Endpoint/lógica en backend; operación/UI completa `NO VERIFICADO` en E2E |
| Auth admin Firebase | 🔴 | `PLANIFICADO` (plan en archive); vigente: credenciales hasheadas (“puente temporal”) |
| Supabase Auth / `profiles` | 🟡 | Tabla y roles en migración; login Flask actual **no** usa `auth.users` |

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
        ├── Postgres (Supabase) vía DATABASE_URL
        ├── Supabase Storage (fotos, comprobantes, QR)
        ├── SMTP (correo de bienvenida)
        └── Fallback local: SQLite (RUANA_DB_PATH / ruana.db)
```

| Capa | Tecnología verificada |
|------|----------------------|
| Frontend | HTML, CSS, JS vanilla en `RUANA/web/` (sin React/Vue) |
| Backend | Flask 2.3.3, Flask-Cors, PyJWT, Werkzeug |
| Servidor WSGI | gunicorn |
| Base de datos | Postgres (psycopg) o SQLite fallback |
| Storage | Supabase Storage (`storage_manager.py`) |
| Auth app | JWT propio (aliado por código; admin por credenciales hasheadas) |
| Hosting | Firebase Hosting → Cloud Run |
| Secretos prod | Google Secret Manager (scripts/workflows) |
| QA | pytest + Playwright |

Piezas internas relevantes:

- `RUANA/core/db_manager.py` — persistencia y reglas (~13 223 líneas, monolito).
- `RUANA/core/negociacion_manager.py` — negociación guiada.
- `RUANA/core/admin_auth.py` — autenticación admin (puente temporal).
- `RUANA/engines/motor_evaluacion.py` + `orquestador.py` — motor de evaluación/métricas (el semáforo de panel sale del score en `aliados`, no del motor como fuente UI).
- No existen carpetas `services/` ni `repositories/` en el código actual.

---

## 5. Estructura del proyecto

```text
/
├── README.md                 # Este documento (Manual Maestro)
├── README_RUANA_COMPLETO.md  # Copia histórica del manual (puede divergir)
├── ROADMAP.md                # Puntero al roadmap operativo
├── Dockerfile                # Imagen Cloud Run
├── firebase.json             # Hosting + rewrite a Cloud Run
├── firebase-public/          # Público Firebase (vacío salvo .gitkeep)
├── package.json              # Scripts deploy/QA (Firebase, Supabase, Playwright)
├── playwright.config.js
├── .env.example              # Variables de entorno (sin secretos reales)
├── .github/workflows/        # Deploy Firebase, preview, QA manual
├── docs/                     # Documentación secundaria + archive
├── e2e/                      # Tests Playwright
├── scripts/                  # Deploy, secretos GCP, verificaciones
├── supabase/migrations/      # DDL Postgres + RLS (init) + migraciones
└── RUANA/                    # Aplicación
    ├── config/               # Reglas, oficios, ejemplos admin
    ├── core/                 # DBManager, auth, storage, email, negociación
    ├── engines/              # Motor de evaluación
    ├── events/               # Event bus (JSONL)
    ├── metrics/              # Colector
    ├── web/                  # Flask app + HTML/JS/CSS
    ├── tests/                # Tests pytest
    ├── scripts/              # Utilidades (credenciales, verify_supabase, …)
    └── docs/                 # Punteros a docs del monorepo
```

Carpetas generadas / menos relevantes para el mapa: `RUANA/logs/`, `__pycache__/`, artefactos QA.

---

## 6. Base de datos

### Dualidad SQLite / Postgres

- **Producción prevista:** Postgres en Supabase (`DATABASE_URL`).
- **Local / QA CI:** SQLite (`RUANA_DB_PATH`).
- Compatibilidad de nombres/tipos vía `postgres_compat.py` y migraciones `sqlite_compat_*`.

### Tablas principales (verificadas en migraciones y/o `ruana.db`)

| Tabla | Propósito |
|-------|-----------|
| `aliados` | Profesionales: código, datos, oficio, score, estado, grupo, foto, linaje |
| `grupos` | Grupos territoriales por `codigo_postal` |
| `solicitudes` | Solicitudes de oficio/atención en grupo |
| `contactos_ruana` | Encargos entre aliados (trabajo, importes, Apoyo, urgencia) |
| `chat_mensajes` | Mensajes asociados a contacto (legado / canal; UI principal = negociación) |
| `confirmaciones_trabajo` | Declaraciones de importe |
| `ingresos_ruana` | Registro de Apoyo cobrado |
| `payment_conflicts` | Disputas / impugnaciones de importe |
| `invitaciones` / `invitaciones_oficio` | Códigos de invitación |
| `referidos` | Relación invitador → referido |
| `competencia` / `competencia_pendiente` | Retos titular/retador |
| `notificaciones_aliado` | Inbox |
| `score_movimientos` | Ledger de cambios de score |
| `evaluaciones` / `evaluaciones_historico` | Persistencia del motor |
| `grupo_oficio_cerrado` | Oficios cerrados en grupo |
| `avisos_grupo` | Avisos |
| `eventos_sistema` / `audit_log` | Trazabilidad |
| `aliados_eliminados` | Histórico de bajas (migración Postgres) |
| `aliado_accesos_dia` | Control de accesos diarios |
| `profiles` | Liga a `auth.users` (migración init); **uso runtime Flask: NO VERIFICADO / no usado en login actual** |

Tablas adicionales creadas en runtime por `DBManager` (pueden no estar en el `.db` commitado): p. ej. `invitacion_campanas`, `catalogo_servicios_aliado`, `ruana_soporte_conversaciones`, `ruana_soporte_mensajes`, `negociacion_eventos`.

### Storage (Supabase)

Buckets en migración: `ruana-public`, `ruana-comprobantes`, `ruana-conflictos`.

### Relaciones relevantes (verificadas)

```text
Usuario/Aliado
  → pertenece a Grupo (codigo_postal + oficio/plaza)
  → genera/recibe Invitaciones y Referidos (linaje)
  → participa en Contactos (encargos)
       → Negociación / mensajes
       → Confirmación de importe → Apoyo RUANA → (opcional) Conflicto
  → Score / score_movimientos → estado operativo
  → puede entrar en Competencia (titular vs retador)
```

### Datos sensibles

- Email, teléfono, nombre de aliados.
- Códigos de aliado (sirven como secreto de acceso).
- Comprobantes de pago e imágenes de conflicto.
- Credenciales admin (hashes; fuera del repo en producción).
- Datos de cobro de la red (Bizum/IBAN/QR) en config — **no reproducir valores aquí**.

### Permisos BD

- RLS definido en migración init para muchas tablas públicas.
- Backend Flask usa **service role** → RLS no es la barrera efectiva de la API.
- Autorización real de la app: decoradores `@require_aliado` / `@require_admin` (+ comprobaciones internas).

---

## 7. Reglas de negocio

Formato: `CONDICIÓN → ACCIÓN → RESULTADO`. Solo reglas verificables.

### Registro

- Datos válidos (nombre ≥3, email con `@` y dominio, teléfono ≥7 dígitos) y únicos → crear aliado con código numérico de 5 dígitos y score **50**.
- Oficio fuera de catálogo → estado `pendiente_validacion` (sin grupo).
- Oficio en catálogo + plaza libre en grupo del CP → asignar grupo, estado `activo`.
- Sin plaza y &lt; 5 grupos en el CP → crear grupo nuevo y asignar.
- 5 grupos y oficio ocupado en todos → estado `en_espera` (suplente; login panel 403 hasta incorporar).
- Invitación aplicable → consumir invitación y aplicar linaje/score según tipo (simple / oficio / campaña).

### Perfil y profesiones

- Catálogo: `RUANA/config/oficios_ruana.json` (**39** oficios).
- Oficio principal obligatorio en registro; especializaciones **no** ocupan plaza.
- Endpoint de especializaciones disponibles marcado como deprecado respecto a la lógica de plaza.

### Territorio y grupos

- `codigo_postal` define el territorio.
- Máximo **5** grupos activos por CP.
- Estados de grupo incluyen `activo`, `en_competencia`, `disuelto` (CHECK en esquema).

### Score y estados del aliado

Según `score_a_estado` en código (rango efectivo 0–500):

| Score | Estado |
|------:|--------|
| 350–500 | ÉLITE |
| 200–349 | DESTACADO |
| 50–199 | ESTABLE |
| 15–49 | EN RIESGO |
| 0–14 | COMPETENCIA |

### Competencia

- Score &lt; `umbral_competencia` (15) → entra lógica de competencia.
- Duración configurable (`duracion_competencia_dias`, default 30).
- Tras derrota, reinicio de score configurable (`score_reinicio_competencia`, default 50).
- Admin puede forzar competencia/suplencia.

### Purga

- Config: meses sin ganar + umbral de score bajo (`purga_mensual_meses_sin_ganar`, `purga_score_bajo_umbral`).
- Endpoint `POST /api/purga/mensual` existe; operación completa en producción `NO VERIFICADO`.

### Invitaciones y captación

- Invitaciones de un uso; invitaciones de oficio; campañas admin con usos.
- Referidos / linaje (`referidos`, campos `invitado_por*`).

### Encargos (contactos) y Apoyo

- Ciclo de contacto: crear → aceptar / estados de trabajo → declarar importe → comprobante Apoyo → posible impugnación.
- Apoyo = `importe × apoyo_pct / 100` (`apoyo_pct` default 12.0).
- Cobro: métodos configurados (Bizum, IBAN, QR PayPal/Revolut) — **manual**, no pasarela API.

### Negociación

- Sustituye al chat libre para el flujo de encargo.
- Eventos de negociación persistidos; UI en panel aliado.

### Administración

- Activar / rechazar / eliminar aliados; suplentes; cerrar oficio / abrir plaza.
- Revisar pagos e impugnaciones; cambiar reglas permitidas del JSON de config.
- Permisos admin en JSON: `leer`, `escribir`, `eliminar`, `configurar` (con fallback amplio si permisos vacíos — ⚠️ atención).

---

## 8. Flujos principales

### Registro

1. Acceso desde `index` / `invite` / `register`.
2. Validación de invitación (si aplica).
3. `POST /api/aliados/registrar` → código + estado según plaza/CP.
4. Correo SMTP de bienvenida con código (si SMTP configurado).

### Creación / completado del perfil

1. Login con código.
2. Panel aliado: datos, foto Storage, catálogo de servicios.

### Incorporación a grupos / sistema territorial

1. Al registrar: búsqueda de plaza en grupos del CP.
2. Crear grupo si cabe bajo el tope de 5.
3. Si no hay plaza: `en_espera`; admin puede incorporar suplente.

### Captación / invitaciones

1. Aliado o admin genera invitación / campaña.
2. Candidato registra con código.
3. Se registra referido/linaje y se consume la invitación.

### Aliados

1. Login → sesión JWT por pestaña.
2. Operación diaria: directorio, solicitudes, conexiones, perfil, notificaciones.

### Acuerdos / negociación

1. Contacto entre aliados.
2. Negociación guiada (propuestas / contraofertas / cierre).
3. Declaración de importe y Apoyo.

### Chat

- Flujo de chat libre: **no operativo** (410). Usar negociación.

### Pagos

1. Cierre de importe → cálculo Apoyo.
2. Subida de comprobante.
3. Admin aprueba / rechaza; aliado puede impugnar; admin resuelve conflictos.

### Notificaciones

1. Eventos generan `notificaciones_aliado`.
2. Lectura/marcado desde panel; centro de comunicación para soporte.

### Administración

1. Login admin (credenciales hasheadas).
2. Dashboard, pendientes, pagos, campañas, competencia, reglas, métricas.

---

## 9. Seguridad

### Autenticación

| Actor | Mecanismo |
|-------|-----------|
| Aliado | Código de aliado → JWT HS256 (`FLASK_SECRET_KEY`), header `X-Ruana-Session-Id` |
| Admin | ID + contraseña hasheada (pbkdf2 Werkzeug) desde JSON/env; sesión JWT análoga |

### Autorización

- Decoradores `@require_aliado`, `@require_admin`, `@require_admin_escritura`.
- Middleware `before_request` en rutas `/api/admin/*` (salvo login/logout).
- Algunas rutas API públicas (health, catálogo, registro, validar invitación, login). Lista completa: revisar `app.py`.

### RLS

- Definido en `supabase/migrations/20260519000100_init_ruana_clean.sql`.
- Helpers `current_aliado_codigo()`, `is_ruana_admin()`.
- **Efecto real sobre la API Flask:** limitado, porque el backend usa service role.
- SQLite: sin RLS.

### Roles

- App: aliado / admin.
- Tabla `profiles.role` ∈ (`aliado`, `admin`) pensada para Supabase Auth — no cableada al login Flask actual.

### Datos sensibles y secretos (solo nombres)

| Variable / artefacto | Finalidad |
|----------------------|-----------|
| `FLASK_SECRET_KEY` | Firma de JWT / sesiones |
| `RUANA_ADMIN_CREDENTIALS_JSON` / `_PATH` | Credenciales admin |
| `SUPABASE_SERVICE_ROLE_KEY` | Cliente admin Supabase (bypassa RLS) |
| `SUPABASE_ANON_KEY` | Clave pública anon |
| `DATABASE_URL` | Conexión Postgres |
| `RUANA_SMTP_PASSWORD` | SMTP |
| Secretos GCP / GitHub Actions | Deploy y credenciales prod |

**Nunca** versionar valores reales de contraseñas, keys, tokens o IBAN/Bizum en documentación.

### Protección detectada

- Sesión por pestaña (mitiga cookie compartida).
- Hashes de admin (no plaintext en el flujo recomendado).
- Cloud Run con secrets inyectados en deploy.
- ⚠️ Login aliado = posesión del código (factor único débil).
- ⚠️ Store de sesiones en memoria (mitigado en parte con `workers 1` en Docker).
- ⚠️ Datos de cobro en `ruana_reglas_v1.json` versionado.
- ⚠️ Rutas de preview/test en la misma app.
- ⚠️ Cloud Run configurado con acceso no autenticado a nivel de red (`--allow-unauthenticated` en scripts de deploy); la auth es de aplicación.

---

## 10. Integraciones externas

| Servicio | Función | Estado |
| -------- | ------- | ------ |
| Supabase Postgres | Base de datos principal | 🟢 Usado (vía `DATABASE_URL`) |
| Supabase Storage | Fotos, comprobantes, QR | 🟢 Usado |
| Supabase Realtime | Publication de tablas en migración | 🟡 DDL existe; uso cliente `NO VERIFICADO` |
| Firebase Hosting | Front door + rewrite a Cloud Run | 🟢 Usado |
| Google Cloud Run | Ejecución Flask | 🟢 Usado |
| Artifact Registry | Imágenes Docker | 🟢 Usado |
| Google Secret Manager | Secretos de runtime | 🟢 Usado en workflows/scripts |
| SMTP (Gmail u otro) | Email de bienvenida | 🟡 Implementado; depende de vars |
| PayPal / Revolut / Bizum | Cobro Apoyo vía QR/datos | 🟡 Manual (sin API de pasarela) |
| Stripe / PayPal REST | Pagos automáticos | 🔴 No integrado |
| Firebase Authentication | Auth admin/usuarios | 🔴 Planificado, no implementado |

---

## 11. Configuración

### Variables de entorno (ver `.env.example`)

| Variable | Uso |
|----------|-----|
| `FLASK_SECRET_KEY` | Secret de sesión/JWT |
| `RUANA_ADMIN_SESSION_EXPIRES` | TTL sesión admin (s) |
| `RUANA_ALIADO_SESSION_EXPIRES` | TTL sesión aliado (s) |
| `RUANA_ADMIN_CREDENTIALS_PATH` | Ruta JSON admin |
| `RUANA_ADMIN_CREDENTIALS_JSON` | JSON inline admin |
| `FIREBASE_PROJECT_ID` | Proyecto Firebase/GCP |
| `GOOGLE_CLOUD_REGION` | Región (p. ej. `europe-west1`) |
| `ARTIFACT_REGISTRY_REPOSITORY` | Repo de imágenes |
| `SUPABASE_URL` | URL proyecto Supabase |
| `SUPABASE_ANON_KEY` | Anon key |
| `SUPABASE_SERVICE_ROLE_KEY` | Service role |
| `DATABASE_URL` | Postgres (pooler recomendado en Cloud Run) |
| `RUANA_DB_PATH` | Ruta SQLite fallback |
| `RUANA_SMTP_HOST` / `_PORT` / `_USER` / `_PASSWORD` / `_FROM_EMAIL` | Correo |
| `RUANA_PUBLIC_APP_URL` / `PUBLIC_APP_URL` | URL pública (emails/enlaces) |
| `PORT` | Puerto gunicorn (Cloud Run) |

### Config de negocio

- `RUANA/config/ruana_reglas_v1.json` — umbrales, Apoyo %, métodos de pago.
- `RUANA/config/oficios_ruana.json` — catálogo de oficios.
- `RUANA/config/admin_codes.example.json` — ejemplo.
- `RUANA/config/admin_credentials.qa.json` — credenciales QA (hashes).

### Dependencias

- Python: `RUANA/web/requirements.txt` (+ `requirements-dev.txt` para QA).
- Node: `package.json` (Firebase CLI, Supabase CLI, Playwright) — no es el runtime de la app.

---

## 12. Desarrollo local

Esta sección explica cómo levantar RUANA en tu máquina. Los términos técnicos se aclaran la primera vez.

### Requisitos

1. **Python** (lenguaje del backend) — el `Dockerfile` usa 3.13; CI QA usa 3.11. Conviene 3.11+.
2. **pip** (instala librerías Python).
3. Opcional: **Node.js** + **npm** (herramienta que instala dependencias JS) solo para E2E/deploy.
4. Opcional: cuenta Supabase/Postgres; si no, se usa **SQLite** (base de datos en un archivo local).

### Pasos

1. Clonar el repositorio y entrar en la carpeta del proyecto.
2. Copiar variables de entorno:
   ```bash
   cp .env.example .env
   ```
   Editar `.env`: como mínimo `FLASK_SECRET_KEY` y, si usas Postgres, `DATABASE_URL` + claves Supabase. Para local puro, deja vacío `DATABASE_URL` y usa `RUANA_DB_PATH`.
3. Crear entorno virtual (carpeta aislada de dependencias Python):
   ```bash
   cd RUANA/web
   python -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```
4. Credenciales admin locales: seguir `docs/seguridad/credenciales-admin.md` (generar JSON hasheado; no subir secretos).
5. Arrancar la app Flask:
   ```bash
   # Desde el layout del proyecto; el módulo es web.app
   # Ajusta PYTHONPATH para importar RUANA/core
   cd /ruta/al/repo/RUANA
   export PYTHONPATH=.
   python -m flask --app web.app run --host 0.0.0.0 --port 8080
   ```
   Alternativa de producción local: gunicorn como en el `Dockerfile`.
6. Abrir el navegador en `http://localhost:8080/`.

### Tests

```bash
# Backend
pip install -r RUANA/web/requirements-dev.txt
python -m pytest RUANA/tests -q

# E2E (npm = gestor de paquetes JS)
npm ci
npx playwright install chromium
npm run qa:e2e
```

### Nota

Si algo falla por falta de secretos SMTP/Supabase, la app puede seguir en modo SQLite; el correo y el storage remoto quedarán limitados.

---

## 13. Deploy

`Deploy` significa publicar una versión de la aplicación.

### Dónde se despliega (verificado)

| Pieza | Destino |
|-------|---------|
| App | Cloud Run service `ruana`, región `europe-west1`, proyecto `ruana-4293f` |
| Entrada web | Firebase Hosting `https://ruana-4293f.web.app` → rewrite a Cloud Run |
| Imagen | Artifact Registry `europe-west1-docker.pkg.dev/ruana-4293f/ruana/ruana` |
| BD / Storage | Supabase proyecto referenciado en config (`qqlxgwbmtzcfrrobrfzy`) |

### Cómo se realiza

**Producción (automático):** push a `main` dispara `.github/workflows/deploy-firebase.yml` (build imagen, Cloud Run, sync secrets, Firebase Hosting).

**Preview:** workflows `deploy-firebase-preview.yml` / `trigger-preview-deploy.yml` (canales de Hosting; rama `dev`).

**Manual (scripts en `package.json` / `scripts/`):**

- `npm run cloudrun:build` / `cloudrun:deploy`
- `npm run deploy:hosting` / `deploy:preview`
- `npm run supabase:push` (aplicar migraciones; requiere login/link)

### Variables / secretos de deploy

Inyectados vía GitHub Actions + Secret Manager (nombres, no valores): credenciales admin, Supabase keys, `DATABASE_URL`, `FLASK_SECRET_KEY`, SMTP, etc. Ver workflow y `.env.example`.

### Comprobar que funciona

- Abrir `https://ruana-4293f.web.app`.
- `GET /api/health` (sin auth).
- Login aliado/admin de prueba en entorno controlado.

### Detectar un fallo

- Revisar logs del workflow de GitHub Actions.
- Logs de Cloud Run (`gcloud` / consola GCP).
- Respuestas 5xx / health fallido.

### Volver a una versión anterior

- Cloud Run permite traficar a una revisión anterior desde la consola GCP / `gcloud run services update-traffic` — procedimiento exacto operativo **parcialmente documentado en scripts**; detalle UI de rollback en consola: `NO VERIFICADO` en docs del repo más allá de redeploy.

---

## 14. Estado técnico actual

### Funcionando

- Registro, login aliado/admin, panel aliado y admin.
- Grupos/plazas por CP, invitaciones, referidos, campañas.
- Contactos, negociación guiada, Apoyo con comprobantes e impugnación.
- Notificaciones / centro comunicación.
- Deploy Firebase → Cloud Run.
- Tests pytest + Playwright (ejecución CI **manual**).

### Parcial

- Seguridad Hito 2 (endpoints públicos residuales).
- Purga/competencia (backend sí; cobertura E2E/ops variable).
- SMTP / Storage dependen de secretos.
- RLS definido pero no es la barrera de la API.
- Documentación secundaria desfasada (chat, score 0–100).

### Pendiente

- Firebase Authentication para admin.
- Integración de pasarela de pago automática.
- Uso real de Supabase Auth / `profiles` en el login Flask.
- Alineación E2E con negociación (selectores chat legacy).

### Riesgos técnicos detectados

1. Monolitos `db_manager.py` + `app.py` + HTML enormes.
2. Drift SQLite vs Postgres / columnas legacy.
3. `ruana.db` presente en el árbol de trabajo (datos de prueba).
4. Service role bypassea RLS.
5. Código de aliado = único secreto de acceso.
6. Sesiones en memoria.
7. Datos de cobro en repositorio.
8. QA CI solo con `workflow_dispatch` (no en cada push/PR).
9. Rutas preview/test expuestas.
10. Docs/E2E contradicen el flujo de negociación y el score 0–500.

### Deuda técnica

`Deuda técnica` = decisiones o restos que generan más trabajo o riesgo después.

- Ausencia de capa `services/` / `repositories/` pese al tamaño de `DBManager`.
- Chat legacy + tests/contratos rotos respecto a negociación.
- Manual duplicado (`README_RUANA_COMPLETO.md`).
- Stubs/legado en `orquestador.py` (menciones a capital/trading).
- Plan Firebase Auth sin implementar.
- Referencias rotas a paths de docs antiguos (`ADMIN_CREDENTIALS_SETUP.md` citado en UI/issue; vigente: `docs/seguridad/credenciales-admin.md`).

---

## 15. Estado del producto

### Implementado

Registro, perfil, grupos territoriales, plazas/suplentes, aliados, invitaciones/referidos/campañas, solicitudes, contactos, negociación/acuerdos, Apoyo con revisión admin, notificaciones, panel admin, competencia por score, deploy cloud.

### En desarrollo

Endurecimiento de seguridad/permisos (Hito 2); consolidación docs/ops (según roadmap 2026-07-28).

### Planificado

Admin → Firebase Authentication (plan en `docs/archive/superpowers/plans/2026-07-27-admin-firebase-auth-migration.md`).

### No verificado

- Estado exacto del schema/RLS remoto en Supabase en este momento.
- Uso de Realtime en el cliente.
- Cobertura completa de purga en operación real.
- Rollback operativo día a día del equipo.
- Que todos los flujos E2E pasen tras el cambio chat→negociación.

---

## 16. Puntos críticos de RUANA

Tratar con especial cuidado antes de cambiar:

| Área | Por qué |
|------|---------|
| Autenticación / sesiones | JWT, store en memoria, login por código |
| Autorización admin | Permisos y fallback amplio |
| `aliados` / score / estados | Fuente del semáforo y competencia |
| Grupos, CP, plazas | Exclusividad territorial |
| Contactos + Apoyo + conflictos | Dinero y reputación |
| Negociación | Sustituye chat; contratos/tests frágiles |
| Storage comprobantes | Datos sensibles |
| `DATABASE_URL` / dual SQLite-Postgres | Drift de esquema |
| Config `ruana_reglas_v1.json` | Umbrales globales + datos de cobro |
| Deploy secrets | Compromiso = acceso total |

---

## 17. Reglas para futuros cambios

> Antes de modificar una funcionalidad crítica, comprobar sus dependencias, reglas de negocio, seguridad y efectos sobre otras funcionalidades.

Reglas detectadas que un desarrollador debe respetar:

1. **Código > documentación.** Si actualizas comportamiento, actualiza este README y los deep-dives en `docs/`.
2. **No asumir score 0–100;** el código usa 0–500 y bandas ÉLITE/DESTACADO.
3. **No reintroducir chat libre** sin migrar UI, APIs y tests; el contrato vigente es negociación guiada.
4. **Plaza = oficio principal;** no volver a cobrar plaza por especialización sin decisión explícita de producto.
5. **Máximo 5 grupos por CP** (`MAX_GRUPOS_POR_CP`).
6. **Apoyo** se calcula con `apoyo_pct`; cambios afectan importes y admin de pagos.
7. **No subir secretos** ni valores reales de cobro/credenciales a git.
8. **Auth aliado/admin** son puentes propios; cualquier cambio debe preservar el header `X-Ruana-Session-Id` o migrar cliente y servidor juntos.
9. **Service role** implica que la seguridad de datos sensibles debe vivir en la API Flask, no solo en RLS.
10. **Tests:** el workflow `ruana-qa.yml` es manual (`workflow_dispatch`); un “verde local” no equivale a CI automático en cada PR.
11. Si se toca `DBManager`, aplicar la política de modularización del proyecto (**Campamento Base**) solo con tests CI adecuados — hoy la extracción a `services/`/`repositories/` **aún no está hecha** en el árbol.

---

## 18. Roadmap

Fuente verificable: [`docs/operaciones/roadmap.md`](docs/operaciones/roadmap.md) (actualización 2026-07-28). `ROADMAP.md` en la raíz solo apunta ahí.

Resumen factual:

| Hito | Estado documentado |
|------|--------------------|
| 1 — Infra (Docker, Cloud Run, Firebase, Supabase) | Cerrado documentalmente |
| 2 — Seguridad y permisos | Activo / parcial |
| Invitaciones admin + campañas | Hecho en código |
| Métodos de pago + Storage | Hecho en código |
| Impugnación cobros / alertas | Hecho en código |
| Competencia automática por score | Hecho en main |
| Admin → Firebase Auth | Preparado, **no implementado** |

Histórico adicional: `docs/archive/ROADMAP_2026-05.md` (puede citar archivos ausentes).

No se inventan hitos nuevos fuera de esas fuentes.

---

## Documentación secundaria

Índice: [`docs/README.md`](docs/README.md).

Deep-dives útiles:

- [`docs/flujos/registro-aliados.md`](docs/flujos/registro-aliados.md)
- [`docs/seguridad/autenticacion-sesiones.md`](docs/seguridad/autenticacion-sesiones.md)
- [`docs/seguridad/credenciales-admin.md`](docs/seguridad/credenciales-admin.md)
- [`docs/operaciones/roadmap.md`](docs/operaciones/roadmap.md)

`docs/flujos/chat-y-alerta.md` describe el modelo de chat histórico; contrastar con negociación en código.

---

*Auditoría basada en inspección del repositorio. El README describe únicamente funcionalidades y arquitectura verificadas en el proyecto; lo demás está etiquetado explícitamente.*
