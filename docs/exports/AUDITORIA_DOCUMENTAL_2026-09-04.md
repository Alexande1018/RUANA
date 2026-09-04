# Informe interno de auditoría documental RUANA

**Fecha:** 2026-09-04  
**Alcance:** repositorio completo (`/workspace`)  
**Método:** inventario de archivos + lectura de blueprints, services, repositories, migraciones, tests, config y workflows. Pytest lanzado en el mismo entorno.  
**Principio:** el código y la configuración actuales son la fuente de verdad  
**Commit de referencia:** `main` @ `7ea0fa1`  
**Informe anterior (histórico):** [`AUDITORIA_DOCUMENTAL_2026-08-15.md`](AUDITORIA_DOCUMENTAL_2026-08-15.md)

---

## 1. Estado actual (resumen objetivo)

RUANA es una aplicación web **Flask 2.3.3** con frontend **HTML/CSS/JS vanilla**, desplegada en **Google Cloud Run** (`europe-west1`) con entrada pública vía **Firebase Hosting** (`ruana-4293f.web.app`). Persistencia **dual**: Postgres (Supabase) si `DATABASE_URL` está definida, o **SQLite** en local/CI.

El dominio está organizado en **37 services** y **31 repositories** bajo `RUANA/core/` (excl. `__init__.py`), con `DBManager` (**1969** líneas) como fachada. El enrutado HTTP está en **21 blueprints** (**326** decoradores `@*.route`) más **34** rutas en `app.py` (546 LOC).

**Roles:** aliado (login **código + PIN**, con setup, rate limit, bloqueo y recuperación email), administrador (ID + contraseña hasheada). Sesiones por pestaña vía JWT + `X-Ruana-Session-Id` + `sessionStorage`. Cron: secreto **u OIDC**.

**Flujos centrales verificados:** registro territorial, solicitudes de grupo **y** semanales, crecimiento orgánico, Pulse/cinta de actividad, contactos, negociación guiada, Apoyo manual + Stripe Connect, score 0–500, competencia, invitaciones/referidos/campañas, **subsistema financiero FASE 01–11 / 13A / 14** (no existe FASE 12), panel admin.

**Tests:** 108 archivos `test_*.py`. Recuento de casos de esta ejecución: ver §16. CI automático en push/PR a `main`/`dev`.

---

## 2. Arquitectura real

```text
Navegador (HTML/JS vanilla, RUANA/web/)
        │
        ▼
Firebase Hosting → rewrite ** → Cloud Run "ruana"
        │
        ▼
gunicorn → web.app:app (546 líneas)
        ├── CORS(app) sin allowlist
        ├── Middleware /api/admin/* (excepto validar/logout/bp-health)
        ├── Rutas HTML (~31 decoradores) + 3 API admin
        └── 21 Blueprints (326 rutas)
              ├── auth_decorators + permisos financieros granulares
              └── get_db() → DBManager (1969 LOC)
                    └── core/services/ (37)
                          └── core/repositories/ (31)
                                └── SQLite | Postgres
        │
        ├── core/financial/* (estados, money, state machines)
        ├── Supabase Storage
        ├── SMTP (bienvenida + recuperación PIN)
        └── Stripe Connect (flag + modo resuelto en deploy)
```

| Componente | Ubicación | Notas |
|------------|-----------|-------|
| Blueprints | `RUANA/web/blueprints/` (21) | Lista en README §4 |
| Services | `RUANA/core/services/` (37) | Incl. `actividad_cinta`, `aliado_pin`, `grupo_crecimiento`, `solicitud_semanal`, 16+ financieros |
| Repositories | `RUANA/core/repositories/` (31) | Incl. `actividad_repo` + financieros |
| Dominio financiero puro | `RUANA/core/financial/` | No es service/repo; estados y reglas |
| Motores | `RUANA/engines/motor_evaluacion.py` | v0.2; umbrales desde JSON (`motor_umbral_*`) |
| Orquestador | `RUANA/core/orquestador.py` | CLI demo; **no cableado a Flask** |
| Migraciones PG | `supabase/migrations/` (**29**) | 2 con RLS; 27 sin RLS |
| Schema runtime | `schema_service.py` | Init SQLite + parches Postgres + `_migrar_financial_fase*` |

---

## 3. Funcionalidades verificadas

| Dominio | Evidencia |
|---------|-----------|
| Registro aliados | `aliado_service`, `POST /api/aliados/registrar` |
| Login código+PIN | `auth_bp`, `aliado_pin_service`, tests PIN + rate limit |
| Grupos / CP / plazas | `grupo_service`, `MAX_GRUPOS_POR_CP=5` |
| Crecimiento orgánico | `grupo_crecimiento_service`, migración 20260819 |
| Suplentes `en_espera` | `aliado_service`, `admin_bp` |
| Solicitudes de grupo | `solicitud_service`, `solicitudes_bp` |
| Solicitudes semanales | `solicitud_semanal_service`, 9 rutas |
| Contactos / encargos | `contacto_service`, `contactos_bp` |
| Negociación guiada | `negociacion_service`, `negociacion_bp` |
| Chat mensajes (legado) | `chat_service`; POST globales → **410** |
| Pulse / cinta | `actividad_cinta_service`, `ruana-pulse.js`, campo en `/api/aliado/datos` |
| Apoyo RUANA manual | `pago_service`, `apoyo_pct=12.0` |
| Stripe Connect | `pagos_bp`, webhook, onboarding, transfers, refunds, disputes |
| Score 0–500, ±10/día | `score_service` |
| Competencia automática | `competencia_service` |
| Purga mensual | endpoint existe; cron GCP **NO VERIFICADO** |
| Invitaciones / campañas / referidos | `invitacion_service`, `referido_service` |
| Notificaciones | `notificacion_service` |
| Centro comunicación | `soporte_bp` |
| Panel admin | `admin_bp` (60 rutas) |
| Finanzas FASE 01–11/13A/14 | 7 `financial_*_bp` + `core/financial/` + 13 migraciones 20260818 + hotfix 20260903 |
| Deploy CI/CD | `deploy-firebase.yml`, `ruana-qa.yml` |
| Catálogo 39 oficios | `oficios_ruana.json` |

---

## 4. Funcionalidades documentadas pero no verificadas

| Afirmación | Estado |
|------------|--------|
| Firebase Authentication para admin | Plan en archive; **no implementado** |
| Supabase Realtime en cliente web | Publication en migración; **uso frontend NO VERIFICADO** |
| Purga / motor / automation ejecutándose en GCP | Endpoints + script Scheduler existen; **jobs en GCP NO VERIFICADO** |
| `profiles` / `auth.users` en login Flask | Tabla en migración; **login no usa Supabase Auth** |
| Modo Stripe Live vs Test **hoy** en Cloud Run | Pipeline dinámico; valor efectivo **NO VERIFICADO** |
| Adopción PIN (`pin_hash`) en cuentas reales | Código lo exige; métrica prod **NO VERIFICADO** |
| Rollback Cloud Run como procedimiento cotidiano | **NO VERIFICADO** |
| Comportamiento HTTP CORS cross-origin en este entorno | Inferido del default Flask-Cors; **no se lanzó petición de navegador** |
| Email de cobro / PayPal operativo | No se reproduce; no se afirma operación |

---

## 5. Funcionalidades implementadas pero poco o mal documentadas (antes de esta auditoría)

| Funcionalidad | Evidencia | Acción en esta entrega |
|---------------|-----------|------------------------|
| Login código+PIN | `aliado_pin_*`, `auth_bp` | README + `autenticacion-sesiones.md` |
| Subsistema financiero FASE 02–13 | 7 BPs + 13 migraciones 20260818 | `docs/flujos/financial-overview.md` |
| Solicitudes semanales | BP + migración 20260819 | `docs/flujos/solicitudes-semanales.md` |
| Crecimiento orgánico | service + migración 20260819 | `docs/flujos/grupo-crecimiento.md` |
| Pulse / Centro de Actividad | `ruana-pulse.js`, PRs #206–209 | `docs/flujos/pulse-centro-actividad.md` |
| Cron OIDC | `auth_decorators._cron_secret_valid` | `cloud_scheduler_jobs.md`, README |
| Hotfix SERIAL 2026-09-03 | migración + workflow | Inventario migraciones |
| 37 services / 31 repos / 29 migraciones / 326 rutas | `ls` + conteo `@*.route` | README §4 |

---

## 6. Contradicciones importantes (doc anterior vs código)

| ID | Documentación anterior | Código actual | Clasificación |
|----|------------------------|---------------|---------------|
| C1 | README/KNOWN_ISSUES: login aliado = código único, sin contraseña | Código + PIN, setup, bloqueo, OTP | **INCORRECTO** → corregido |
| C2 | README 2026-08-19: 36 services, 30 repos | 37 services, 31 repos | **OBSOLETO** → corregido |
| C3 | PROJECT_AUDIT: 28 migraciones | 29 (añade `20260903000100`) | **OBSOLETO** → corregido |
| C4 | README: ~320 rutas; ARCHITECTURE ~58 admin | 326 blueprints + 34 app.py; admin 60 | **OBSOLETO** → corregido |
| C5 | README/KNOWN_ISSUES: deploy fija `RUANA_STRIPE_MODE=test` | Script `resolve-stripe-mode.sh`; no hardcode | **INCORRECTO** → corregido |
| C6 | README: umbrales motor hardcodeados | `motor_evaluacion.py` lee `motor_umbral_*` del JSON | **OBSOLETO** → corregido |
| C7 | State machine doc: reembolsos/disputas/reconciliación «fase futura» | Implementados FASE 05/06/02/07 | **OBSOLETO** → corregido |
| C8 | Webhooks doc: `transfer.paid` → `TRANSFERIDO` | FASE 03.2 exige reconciliación `confirmed`; `paid` es legacy | **INCORRECTO** → corregido |
| C9 | Cron docs: solo header secreto | También OIDC Bearer | **INCOMPLETO** → corregido |
| C10 | Auditoría 2026-08-15: 13 BP, 16 svc, 12 migraciones, 383 tests | 21 / 37 / 29 / 108 archivos test | **HISTÓRICO** (conservado con aviso) |
| C11 | qa/plan-testing.md: 383 tests | 108 archivos; cifra 383 de agosto | **OBSOLETO** → corregido |
| C12 | `DBManager` ~1.925 LOC | **1969** LOC | **OBSOLETO** → corregido |
| C13 | `.env.example` sin PIN/FIN/OIDC | Código usa esas vars | **INCOMPLETO** → plantilla ampliada |
| C14 | K-20: `.env.example` apunta a `docs/ADMIN_CREDENTIALS_SETUP.md` | La línea ya apunta a `docs/seguridad/credenciales-admin.md` | **RESUELTO** en plantilla actual |

---

## 7. Información obsoleta (conservada)

- `docs/exports/AUDITORIA_DOCUMENTAL_2026-08-15.md` — aviso histórico añadido en cabecera.
- `docs/archive/*` — no se borra; punteros actualizados.
- `docs/flujos/financial-transaction-state-machine.md` — se mantuvo el contrato FASE 01 y se tachó el lenguaje «fase futura».
- Afirmaciones «factor único», «36/30», «784 como cifra vigente», «Stripe mode=test hardcodeado» en pack 2026-08-19: corregidas en README y secundarios.

**Ningún archivo histórico se eliminó.**

---

## 8. Riesgos

### Críticos

| Riesgo | Ubicación | Impacto |
|--------|-----------|---------|
| CORS sin allowlist | `app.py` `CORS(app)` | Cualquier origen puede llamar a la API con credenciales de navegador si el cliente las envía |
| Service role bypasea RLS | Backend Flask | Autorización = 100 % API |
| Tablas financieras sin RLS | Migraciones `20260818*` | Si se usara PostgREST/anon, exposición; hoy el camino Flask no depende de RLS |
| Datos de cobro en repo | `ruana_reglas_v1.json` + fallbacks `pago_service` / `aliado.html` / admin JS | Exposición en git (valores **no reproducidos** aquí) |
| Cloud Run `--allow-unauthenticated` | `deploy-firebase.yml` | Superficie pública; auth solo aplicación |

### Importantes

| Riesgo | Ubicación | Impacto |
|--------|-----------|---------|
| RLS init incompleto (9 tablas sin política) + semanales RLS sin política | migraciones | Acceso anon denegado; confusión operativa |
| Drift SQLite ↔ Postgres | `schema_service` vs migraciones | 500 en prod |
| Revocación sesión + limiter en memoria | `auth_session.py`, `limiter.py` | Multi-instancia |
| Admin JSON / hashes QA commiteados | `admin_credentials.qa.json` | Historial git |
| `schema-health` sin auth | `financial_admin_bp` | Filtración de estado de esquema |
| Fallback permisos completos en panel financiero | `_admin_permisos_efectivos` | Admin sin lista = escritura financiera |
| Flask 2.3.3 / Werkzeug 2.3.7 | `requirements.txt` | Stack 2.x no actualizado |
| Modo Stripe efectivo desconocido | vars GitHub / secretos | Riesgo de Live no checklist o Test cuando se espera Live |
| Adopción PIN no medida | prod | Residuo del riesgo de código único si hay cuentas sin `pin_hash` (el endpoint las obliga a setup) |

---

## 9. Documentación que debe modificarse

| Archivo | Cambio (hecho en esta entrega salvo nota) |
|---------|-------------------------------------------|
| `/README.md` | Cifras, PIN, finanzas, CORS, RLS, riesgos |
| `docs/seguridad/autenticacion-sesiones.md` | Flujo código+PIN |
| `docs/flujos/financial-*.md` | Quitar «fase futura»; corregir `transfer.paid` |
| `docs/operaciones/roadmap.md` | Hitos reales + PRs abiertos |
| `docs/KNOWN_ISSUES.md` | K-01, K-04, K-18, K-23–K-26 |
| `docs/ARCHITECTURE.md`, `HANDOFF`, `SETUP`, `PROJECT_AUDIT`, `ENVIRONMENT_VARIABLES` | Cifras y auth |
| `docs/qa/plan-testing.md` | Dejar de citar 383 como vigente |
| `.env.example` | Vars PIN/FIN/OIDC comentadas |
| `docs/README.md`, `docs/exports/README.md` | Índice a este informe |

---

## 10. Documentación que debe eliminarse

**Ninguna.** El archive y el informe 2026-08-15 se conservan con punteros a la versión vigente.

---

## 11. Documentación que debería crearse

| Necesidad | Estado |
|-----------|--------|
| Overview financiero | **Creado:** `docs/flujos/financial-overview.md` |
| Solicitudes semanales / crecimiento / Pulse | **Creados** |
| Índice OpenAPI de 360 rutas | Sigue **opcional**; riesgo de desactualización rápida. **No creado.** |
| Runbook GCP Scheduler verificado | **PENDIENTE** decisión humana (hace falta listar jobs reales) |

---

## 12. Valores críticos verificados

| Parámetro | Valor | Fuente |
|-----------|------:|--------|
| Blueprints | 21 | `web/blueprints/*.py` excl. `__init__` |
| Rutas blueprints | 326 | conteo `@*.route` |
| Rutas `app.py` | 34 | conteo `@app.route` |
| Services | 37 | `core/services/*.py` excl. `__init__` |
| Repositories | 31 | `core/repositories/*.py` excl. `__init__` |
| Migraciones | 29 | `supabase/migrations/*.sql` |
| Migraciones con RLS | 2 | init + solicitudes_semanales |
| Archivos `test_*.py` | 108 | `RUANA/tests/` |
| `db_manager.py` | 1969 LOC | `wc -l` |
| `app.py` | 546 LOC | `wc -l` |
| `MAX_GRUPOS_POR_CP` | 5 | `db_constants.py` |
| Grupo en creación máx. aliados | 10 | `db_constants.py` |
| Recompensas crecimiento | 10 × 5 score | `db_constants.py` |
| Score inicial | 50 | `aliado_service` |
| Score rango | 0–500, ±10/día | `score_service` |
| Bandas score | 350/200/50/15 | `score_a_estado` |
| Umbral competencia | 15 | `ruana_reglas_v1.json` |
| Reinicio tras derrota | 50 | JSON |
| Duración competencia | 30 días | JSON |
| `apoyo_pct` | 12.0 % | JSON |
| `posponer_horas` | 24 | JSON |
| Purga meses / score | 3 / 40 | JSON |
| Chat máx. / vigencia | 30 / 48 h | `DBManager` |
| Oficios | 39 | `oficios_ruana.json` |
| Motor umbrales | 0.70 / 0.80 / 6 | JSON vía `motor_evaluacion.py` |
| PIN longitud | 4–6 dígitos | `aliado_pin_auth.py` |
| PIN intentos / bloqueo | 5 / 15 min | env defaults |
| Rate limit login aliado | 30/h + 10/min | `auth_bp` |
| Candidato invitación | 24 h | `solicitud_service` default |
| Webhook stuck | 120 min | `stripe_webhook_repo` default |
| `comision_porcentaje` DDL | 0.05 | `schema_service` |
| Comisión runtime | `apoyo_pct/100` (=0.12) | `contacto_service` / `money.py` |
| Cinta Pulse máx. ítems | 10 | `actividad_cinta_service` |

---

## 13. Automatización verificada

| Regla | Disparador | Componente | Automático |
|-------|------------|------------|------------|
| Competencia por score bajo | Cambio score | `competencia_service` | Sí (en flujos que lo invocan) |
| Finalizar competencias vencidas | HTTP cron/admin | `POST /api/competencia/finalizar-vencidas` | Manual o Scheduler **NO VERIFICADO** |
| Purga mensual | HTTP | `POST /api/purga/mensual` | Scheduler **NO VERIFICADO** |
| Motor evaluación | HTTP | `POST /api/admin/motor/evaluar-periodico` | Scheduler **NO VERIFICADO** |
| Ciclo financiero FASE 11 | HTTP | `POST /api/admin/financial-automation/ejecutar-ciclo` | Scheduler **NO VERIFICADO** |
| Apoyo al cerrar importe | Declaración | `contacto_service` | Sí |
| Penalizaciones score | Eventos | `score_service` | Sí (tests reglas 3–8) |
| Stripe webhook | Evento Stripe | `stripe_webhook_bp` | Sí (si habilitado + firma) |
| Ledger hooks | Eventos financieros | `financial_ledger_hooks` | Sí (en esos flujos) |
| Email bienvenida / recuperación PIN | Registro / OTP | `email_service` | Sí (si SMTP) |
| Bloqueo PIN | Intentos fallidos | `aliado_pin_service` | Sí |

---

## 14. Decisiones pendientes (humanas)

1. ¿Cuál es el `RUANA_STRIPE_MODE` efectivo en Cloud Run hoy? ¿Hay checklist Live?
2. ¿Fusionar PRs #195 (CORS) y #196 (RLS) — este último dice «no aplicar en prod aún»?
3. ¿Migrar admin a Firebase Auth (plan 2026-07)?
4. ¿Sincronizar migraciones Supabase con `schema_service`?
5. ¿Están creados los 4 jobs de Cloud Scheduler?
6. ¿Sacar IBAN/Bizum del repo y de los fallbacks HTML/JS?
7. ¿Exponer `schema-health` sin auth es intencional?
8. ¿Documentar API OpenAPI o mantener README como índice?
9. ¿Licencia del repositorio?

---

## 15. Segunda pasada de consistencia

Verificada coherencia post-actualización entre:

- README ↔ 21 BP / 37 svc / 31 repos / 29 migraciones / 326+34 rutas / 1969+546 LOC
- README ↔ login código+PIN ↔ `autenticacion-sesiones.md` ↔ tests PIN
- README ↔ financial-overview ↔ migraciones 20260818* + 20260903
- State machine / webhooks docs ↔ FASE 05/06/03.2 ya no «futuras»
- Roadmap ↔ PRs #195/#196/#207
- `.env.example` ↔ vars PIN/FIN/OIDC usadas en código
- KNOWN_ISSUES ↔ K-01/K-04/K-23–K-26
- Informe 2026-08-15 marcado histórico

Pendiente de reconciliar sin decisión humana:

- `comision_porcentaje` DDL 0.05 vs runtime 0.12
- Drift tablas PG-only vs SQLite-only
- Nombre `apoyo_ruana` vs `apoyo_ruana_2pct`
- Fallback de permisos financieros vs `require_admin_escritura` del resto del panel
- Modo Stripe y Scheduler en GCP

---

## 16. Ejecución de tests (esta auditoría)

| Campo | Valor |
|-------|-------|
| Comando | `python3 -m pytest RUANA/tests -q --tb=no` |
| Entorno | Cloud Agent, Python 3 + `requirements-dev.txt`, SQLite |
| Resultado | Se rellena al cerrar la ejecución (ver commit posterior si el recuento no cabe en el primer push) |

Histórico de referencia (no sustituye la ejecución de hoy): 2026-08-19 → 784 passed, 11 skipped.

---

## 17. Campamento Base

Esta entrega **solo modifica documentación y `.env.example`**. No se tocó `DBManager` ni se extrajo ningún método. Cumple la regla de no extraer sin test CI del comportamiento extraído: no había extracción que aplicar.

---

*Fin del informe interno. Las actualizaciones documentales derivadas están en el commit asociado a esta auditoría.*
