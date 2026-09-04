# Informe interno de auditoría documental RUANA

**Fecha:** 2026-09-04  
**Alcance:** repositorio completo (`/workspace`)  
**Método:** inventario desde cero + inspección de código, configuración, migraciones y tests  
**Commit de referencia:** `main` @ `7ea0fa1`  
**Principio:** el código y la configuración actuales son la fuente de verdad  

---

## 1. Estado actual (resumen objetivo)

RUANA es una aplicación web **Flask 2.3.3** con frontend **HTML/CSS/JS vanilla**, desplegada en **Google Cloud Run** (`europe-west1`) con entrada pública vía **Firebase Hosting** (`ruana-4293f.web.app`). La persistencia es **dual**: Postgres (Supabase) en producción cuando `DATABASE_URL` está definida, o **SQLite** en local/CI.

El dominio de negocio está organizado en **37 services** y **31 repositories** bajo `RUANA/core/`, con `DBManager` (~1.969 líneas) actuando como **fachada de compatibilidad**. El enrutado HTTP está repartido en **21 blueprints** (~315 rutas API únicas; ~349 incluyendo rutas HTML en `app.py`).

**Roles:** aliado (login **código 5 dígitos + PIN 4–6** con rate limit, bloqueo y recuperación OTP email), administrador (ID + contraseña hasheada en JSON/Secret Manager). Sesiones por pestaña vía JWT + `X-Ruana-Session-Id` + `sessionStorage`.

**Subsistema financiero (FASE 02–13):** implementado completo — webhooks, transferencias, conflictos, reembolsos, disputas, reconciliación, ledger, panel admin, automatización, endurecimientos P0. **7 blueprints** `financial_*` con alias EN/ES.

**Funcionalidad nueva desde auditoría 2026-08-15:** grupo crecimiento orgánico, solicitudes semanales, login PIN aliado, migraciones financieras 2026-08-18 a 2026-09-03.

**Tests:** **1007 passed**, 11 skipped (`PYTHONPATH=RUANA python3 -m pytest RUANA/tests -q`, verificado 2026-09-04). CI automático en push/PR a `main`/`dev`.

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
        ├── CORS(app) — sin allowlist (VERIFICADO)
        ├── Middleware /api/admin/* (excepto login/logout/health)
        ├── Rutas HTML (~34) + estáticos
        ├── POST /api/admin/validar|logout|cambiar-contraseña
        └── 21 Blueprints (~315 rutas API únicas)
              ├── auth_decorators (require_aliado / require_admin / require_financial_*)
              └── get_db() → DBManager (fachada)
                    └── core/services/<dominio>_service.py
                          └── core/repositories/<dominio>_repo.py
                                └── SQLite | Postgres (postgres_compat.py)
        │
        ├── Supabase Storage (fotos, comprobantes, QR)
        ├── SMTP (email bienvenida + OTP recuperación PIN)
        └── Stripe Connect (opcional, RUANA_STRIPE_PAYMENTS_ENABLED)
```

### Inventario verificado (2026-09-04)

| Componente | Cantidad | Ubicación |
|------------|----------|-----------|
| Blueprints | **21** | `RUANA/web/blueprints/*.py` (excl. `__init__.py`) |
| Rutas API únicas (blueprints) | **315** | Conteo por decoradores + resolución `_BASE` |
| Rutas `app.py` | **34** | HTML, admin auth, estáticos |
| Services | **37** | `RUANA/core/services/` |
| Repositories | **31** | `RUANA/core/repositories/` |
| Migraciones PG | **29** | `supabase/migrations/` |
| Migraciones con RLS | **2** | `init_ruana_clean`, `solicitudes_semanales` |
| Migraciones sin RLS | **27** | Resto (incl. todas las financieras 2026-08-18) |
| Archivos test | **108** | `RUANA/tests/test_*.py` |
| Tests pytest | **1007 passed**, 11 skipped | Ejecución local 2026-09-04 |
| `db_manager.py` | **1.969** LOC | Fachada Campamento Base |

### Blueprints y rutas (top)

| Blueprint | Rutas únicas |
|-----------|-------------:|
| `admin_bp` | 59 |
| `financial_admin_bp` | 30 |
| `financial_conflicts_bp` | 24 |
| `aliado_bp` | 20 |
| `referidos_bp` | 16 |
| `contactos_bp` | 15 |
| `negociacion_bp` | 15 |
| `financial_*` (6 restantes) | 14 c/u aprox. |
| `pagos_bp` | 14 |
| `auth_bp` | 12 |
| `solicitudes_semanales_bp` | 9 |
| Otros (7 blueprints) | ≤10 c/u |

---

## 3. Funcionalidades verificadas

| Dominio | Evidencia |
|---------|-----------|
| Registro aliados | `aliado_service`, `POST /api/aliados/registrar` |
| Login aliado código + PIN | `auth_bp`, `aliado_pin_auth.py`, `aliado_pin_service.py`, tests `test_aliado_pin_auth.py` |
| Recuperación PIN por email | `POST /api/aliado/recuperacion/*` |
| Grupos / CP / plazas | `grupo_service`, `MAX_GRUPOS_POR_CP=5` |
| Crecimiento orgánico grupo | `grupo_crecimiento_service`, migración `20260819000100` |
| Solicitudes semanales | `solicitud_semanal_service`, `solicitudes_semanales_bp`, migración `20260819000200` |
| Negociación guiada | `negociacion_service`, UI, E2E |
| Módulo financiero FASE 02–13 | 7 `financial_*_bp`, 14 services/repos financieros, tests `test_financial_*` |
| Webhooks Stripe idempotentes | `stripe_webhook_service`, `stripe_webhook_events` |
| Transferencias con reconciliación | `financial_transfer_service`, FASE 03.2 |
| Reembolsos admin | `financial_refund_service`, FASE 05 |
| Disputas Stripe | `financial_dispute_service`, FASE 06 |
| Ledger / libro mayor | `financial_ledger_service`, FASE 08 |
| Panel admin financiero | `financial_admin_service`, permisos granulares FASE 09–10 |
| Automatización financiera | `financial_automation_service`, cron FASE 11 |
| Stripe Connect pagos encargo | `pagos_bp`, flag `RUANA_STRIPE_PAYMENTS_ENABLED` |
| Score 0–500, competencia | `score_service`, `competencia_service` |
| Deploy CI/CD | `deploy-firebase.yml`, `ruana-qa.yml` |

---

## 4. Funcionalidades documentadas pero no verificadas

| Afirmación en docs | Estado |
|--------------------|--------|
| Firebase Authentication para admin | Plan en archive; **no implementado** |
| Supabase Realtime en cliente web | Publication en migración init; **uso frontend no verificado** |
| Purga mensual / motor evaluación en cron GCP | Endpoints + docs; **despliegue Scheduler no verificado** |
| Automatización financiera en cron GCP | Endpoint documentado; **despliegue no verificado** |
| Políticas RLS efectivas en `solicitudes_semanales` | `ENABLE RLS` sin `CREATE POLICY` en migración; backend usa service role |
| CORS allowlist | **PR abierto** (`cursor/cors-pago-manual-allowlist-2cc1`); `main` tiene `CORS(app)` abierto |
| Adopción PIN en producción | Código + tests verdes; **uso real en prod NO VERIFICADO** |
| Stripe Live en producción | Deploy fija `RUANA_STRIPE_MODE=test` |

---

## 5. Funcionalidades implementadas pero poco o mal documentadas (corregidas en esta auditoría)

| Funcionalidad | Evidencia | Acción documental |
|---------------|-----------|-------------------|
| Login PIN aliado (no solo código) | `auth_bp.py` líneas 52–120 | README §2, §9; `autenticacion-sesiones.md` |
| Subsistema financiero FASE 02–13 completo | migraciones `20260818*`, blueprints `financial_*` | README §4.1; `financial-transaction-state-machine.md` actualizado |
| Grupo crecimiento orgánico | migración `20260819000100` | Nuevo `flujos/grupo-crecimiento-organico.md` |
| Solicitudes semanales | migración `20260819000200` | Nuevo `flujos/solicitudes-semanales.md` |
| 37 services / 31 repos (no 36/30) | conteo archivos | README, ARCHITECTURE, roadmap |
| 1007 tests (no 784/383) | pytest 2026-09-04 | README, plan-testing, roadmap |
| RLS 2/29 migraciones | análisis SQL | README §6, este informe |
| CORS sin allowlist | `app.py:147-148` | README §9, KNOWN_ISSUES K-04a |
| Fallbacks cobro en `pago_service.py` | líneas ~59–60 | KNOWN_ISSUES K-03 ampliado |
| Migración `financial_transfers_id_serial` | `20260903000100` | README §4.1, roadmap |

---

## 6. Contradicciones importantes (doc anterior vs código)

| ID | Documentación anterior | Código actual (2026-09-04) | Clasificación |
|----|------------------------|----------------------------|---------------|
| C1 | Login aliado solo por código (AUDITORIA 2026-08-15) | Código + PIN obligatorio | **OBSOLETO** → corregido |
| C2 | README: 784 tests (2026-08-19) | 1007 passed | **OBSOLETO** → corregido |
| C3 | README: 36 services, 30 repos | 37 services, 31 repos | **OBSOLETO** → corregido |
| C4 | AUDITORIA 2026-08-15: 12 migraciones | 29 migraciones | **OBSOLETO** |
| C5 | AUDITORIA 2026-08-15: 13 blueprints | 21 blueprints | **OBSOLETO** |
| C6 | `financial-transaction-state-machine.md`: reembolsos/disputas «fase futura» | FASE 05–06 implementadas | **INCORRECTO** → corregido |
| C7 | KNOWN_ISSUES K-01: factor único | PIN como segundo factor | **INCORRECTO** → corregido |
| C8 | Implícito: RLS en migración init cubre todo | Solo 2/29 migraciones con RLS | **AMBIGUO** → explicitado |
| C9 | `comision_porcentaje` DDL 0.05 vs runtime 0.12 | Sin cambio | **PERSISTE** |
| C10 | Subsistema financiero FASE 04–13 sin detalle en README | FASE 02–13 con tabla completa | **INCOMPLETO** → corregido |
| C11 | Sin documentación grupo_crecimiento / solicitudes_semanales | Implementado con tests | **AUSENTE** → docs nuevos |
| C12 | CORS no mencionado como riesgo | `CORS(app)` abierto | **AUSENTE** → añadido |

---

## 7. Información obsoleta (conservada en archive)

- `docs/archive/RUANA/AUTENTICACION_SESIONES_SEGURAS.md` — no menciona PIN.
- `docs/exports/AUDITORIA_DOCUMENTAL_2026-08-15.md` — cifras y auth desactualizados; **conservar** con puntero a este informe.
- `docs/archive/README_RUANA_COMPLETO.md` — arquitectura pre-blueprints masivos y pre-financiero.
- Afirmaciones «login sin contraseña» en archive — históricas.

---

## 8. Riesgos

### Críticos

| Riesgo | Ubicación | Impacto |
|--------|-----------|---------|
| Service role Supabase bypasea RLS | Backend Flask + 27/29 migraciones sin RLS | Autorización 100% en API Flask |
| Datos de cobro en repo versionado | `ruana_reglas_v1.json` + fallbacks `pago_service.py` | Exposición IBAN/Bizum en historial git |
| Cloud Run acceso público | `deploy-firebase.yml` | Superficie expuesta; auth solo aplicación |
| Código aliado sigue siendo secreto de alto valor | Entrega en email registro | Compromiso código facilita ataques al PIN |

### Importantes

| Riesgo | Ubicación | Impacto |
|--------|-----------|---------|
| CORS sin allowlist | `web/app.py` `CORS(app)` | CSRF cross-origin en endpoints sin protección adicional |
| Drift SQLite ↔ Postgres | `schema_service` vs 29 migraciones | Tablas/columnas pueden faltar en PG |
| Revocación sesión en memoria | `auth_session.py` | Multi-instancia: logout incompleto |
| RLS parcial sin políticas | `solicitudes_semanales` migración | Acceso directo Supabase: **NO VERIFICADO** |
| Stripe modo test en deploy | `deploy-firebase.yml` | Cobros live bloqueados |
| Cron jobs no verificados en GCP | docs vs infra real | Purga, motor, automatización financiera inactivos si no hay Scheduler |
| Rate limit en memoria | `web/limiter.py` | No compartido entre instancias |

---

## 9. Documentación modificada en esta auditoría

| Archivo | Cambio |
|---------|--------|
| `/README.md` | Inventario 2026-09-04, auth PIN, subsistema financiero §4.1, RLS 2/29, CORS, 1007 tests |
| `docs/seguridad/autenticacion-sesiones.md` | Flujo código+PIN completo |
| `docs/flujos/grupo-crecimiento-organico.md` | **Nuevo** |
| `docs/flujos/solicitudes-semanales.md` | **Nuevo** |
| `docs/flujos/financial-transaction-state-machine.md` | Fases 05–06 ya no «futuras» |
| `docs/qa/plan-testing.md` | 1007 tests, dominios financieros/PIN |
| `docs/KNOWN_ISSUES.md` | K-01 PIN, K-03 fallbacks, K-04a CORS |
| `docs/ARCHITECTURE.md` | Cifras y auth actualizados |
| `docs/operaciones/roadmap.md` | Hitos 2026-09-04, PRs abiertos |
| `docs/README.md` | Enlaces nuevos flujos + auditoría |
| `docs/exports/README.md` | Enlace informe 2026-09-04 |

---

## 10. Documentación que debe eliminarse

**Ninguna.** El archive se conserva como evidencia histórica.

---

## 11. Documentación que debería crearse (pendiente)

| Necesidad | Justificación |
|-----------|---------------|
| `docs/referencia/api-endpoints.md` | ~349 rutas; índice machine-readable sigue ausente — **no creado** (riesgo desactualización) |
| Runbook operativo cron GCP verificado | Endpoints existen; falta evidencia de Scheduler desplegado |
| Políticas RLS para tablas post-init | 27 migraciones sin RLS; decisión de seguridad pendiente |

---

## 12. Valores críticos verificados

| Parámetro | Valor | Fuente |
|-----------|------:|--------|
| `MAX_GRUPOS_POR_CP` | 5 | `db_constants.py` |
| Score inicial registro | 50 | `aliado_service` |
| Score rango | 0–500, tope ±10/día | `score_service` |
| Umbral competencia | 15 | `ruana_reglas_v1.json` |
| `apoyo_pct` | 12.0 % | `ruana_reglas_v1.json` |
| PIN longitud | 4–6 dígitos | `aliado_pin_auth.py` `PIN_REGEX` |
| `RUANA_PIN_MAX_INTENTOS` | 5 (default) | `aliado_pin_auth.py` |
| `RUANA_PIN_BLOQUEO_MINUTOS` | 15 (default) | `aliado_pin_auth.py` |
| Login rate limit | 30/h, 10/min | `auth_bp.py` |
| Oficios catálogo | 39 | `oficios_ruana.json` |
| Blueprints | 21 | `web/blueprints/` |
| Services | 37 | `core/services/` |
| Repositories | 31 | `core/repositories/` |
| Migraciones PG | 29 (2 RLS, 27 sin RLS) | `supabase/migrations/` |
| Tests pytest | 1007 passed, 11 skipped | ejecución 2026-09-04 |

---

## 13. Automatización verificada

| Regla | Disparador | Componente | Automático |
|-------|------------|------------|------------|
| Competencia por score bajo | Cambio score | `competencia_service` | Sí (en flujos que lo invocan) |
| Webhooks Stripe | Evento Stripe | `stripe_webhook_service` | Sí (si habilitado) |
| Transferencias + reconciliación | Confirmar trabajo / webhook | `financial_transfer_service` | Sí |
| Reembolsos / disputas | Admin / webhook | `financial_refund_service`, `financial_dispute_service` | Sí |
| Ciclo automatización financiera | `POST …/financial-automation/ejecutar-ciclo` | `financial_automation_service` | Manual/cron — **despliegue GCP NO VERIFICADO** |
| Purga mensual | `POST /api/purga/mensual` | `competencia_service` | Manual/cron — **NO VERIFICADO** |
| Motor evaluación | `POST /api/admin/motor/evaluar-periodico` | `motor_evaluacion.py` | Manual/cron — **NO VERIFICADO** |
| Email bienvenida / OTP PIN | Registro / recuperación | `email_service` | Sí (si SMTP configurado) |

---

## 14. Decisiones pendientes (humanas)

1. ¿Mergear PR CORS allowlist (`cursor/cors-pago-manual-allowlist-2cc1`)?
2. ¿Activar Stripe Live en producción? (ver `docs/operaciones/fase-14-stripe-live.md`)
3. ¿Migrar admin a Firebase Auth (plan 2026-07)?
4. ¿Añadir RLS/políticas a las 27 migraciones sin RLS?
5. ¿Eliminar datos de cobro de `ruana_reglas_v1.json` y fallbacks de `pago_service.py`?
6. ¿Desplegar Cloud Scheduler para purga, motor y automatización financiera?
7. ¿Completar paridad migraciones Supabase ↔ `schema_service`?

---

## 15. Segunda pasada de consistencia

Verificada coherencia post-actualización entre:

- README ↔ conteo blueprints/services/repos/migraciones
- README ↔ auth PIN ↔ `auth_bp.py`
- README ↔ 1007 tests ↔ ejecución pytest local
- README ↔ subsistema financiero ↔ migraciones `20260818*`
- `autenticacion-sesiones.md` ↔ flujo recuperación PIN
- `financial-transaction-state-machine.md` ↔ FASE 05–06 implementadas
- roadmap ↔ PRs abiertos en `git branch -r`
- KNOWN_ISSUES ↔ CORS y fallbacks cobro

Pendiente sin decisión humana:

- `comision_porcentaje` DDL 0.05 vs runtime 0.12
- Drift tablas PG-only vs SQLite-only
- Efectividad RLS `solicitudes_semanales` sin políticas

---

*Fin del informe. Informe anterior: [`AUDITORIA_DOCUMENTAL_2026-08-15.md`](./AUDITORIA_DOCUMENTAL_2026-08-15.md). Manual Maestro vigente: [`/README.md`](../../README.md).*
