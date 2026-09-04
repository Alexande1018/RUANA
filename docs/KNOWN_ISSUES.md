# Problemas conocidos y limitaciones

Registro de issues **confirmados en código o documentación**, no lista aspiracional de mejoras. Actualizar al corregir cada ítem.

| | |
|---|---|
| Fecha | 2026-09-04 |
| Auditoría | [`PROJECT_AUDIT.md`](PROJECT_AUDIT.md) · [`exports/AUDITORIA_DOCUMENTAL_2026-09-04.md`](exports/AUDITORIA_DOCUMENTAL_2026-09-04.md) |

---

## Críticos (impacto seguridad / dinero / acceso)

### K-01 — Login aliado: código + PIN (ya no es factor único)

**Estado:** Mitigado en código / adopción prod **NO VERIFICADO**  
**Severidad:** Media (era Alta cuando el login era solo código)  
**Verificado:** `auth_bp.py`, `aliado_pin_service.py`, `aliado_pin_auth.py`, tests PIN + rate limit

El login vigente exige **código + PIN** una vez configurado el PIN. Primer acceso: código → `pin_setup_required` + `setup_token`. Hay bloqueo por intentos (`RUANA_PIN_MAX_INTENTOS`, default 5 / 15 min) y recuperación OTP por email.

**Riesgo residual:** compromiso simultáneo de código + PIN, o de email (recuperación). Rate limit en memoria (K-07). Adopción real de `pin_hash` en producción **NO VERIFICADO**.

La documentación anterior a 2026-09-04 que afirma «login por código, sin contraseña / factor único» está **obsoleta**.

---

### K-02 — Service role elude RLS Supabase

**Estado:** Abierto (diseño actual)  
**Severidad:** Alta  
**Verificado:** migraciones RLS + uso `SUPABASE_SERVICE_ROLE_KEY`

Toda autorización debe implementarse en Flask (`@require_aliado`, `@require_admin`). Un bug en un endpoint expone datos sin barrera RLS.

---

### K-03 — Datos de cobro manual en repositorio

**Estado:** Abierto  
**Severidad:** Alta (privacidad / compliance)  
**Verificado:** `RUANA/config/ruana_reglas_v1.json`

Contiene IBAN, número Bizum y URLs de QR en historial git. No rotar automáticamente si se filtran.

---

### K-04 — Modo Stripe de producción no inspeccionable desde el repo

**Estado:** Abierto (incertidumbre operativa)  
**Severidad:** Alta (si se esperan cobros live o si Live está activo sin checklist)  
**Verificado:** `deploy-firebase.yml` resuelve `RUANA_STRIPE_MODE` vía `resolve-stripe-mode.sh` (input / `vars.RUANA_STRIPE_MODE` / default `test`). **Ya no** hardcodea `test`.

El commit `9b273d5` habilita Live en el pipeline. El valor **efectivo** en Cloud Run ahora mismo es **NO VERIFICADO** (depende de GitHub vars + prefijo de `STRIPE_SECRET_KEY`). Salvaguarda: Live en push automático exige `vars.RUANA_STRIPE_ALLOW_LIVE_PUSH=true`.

---

## Altos (operación / consistencia)

### K-05 — Drift SQLite ↔ Postgres

**Estado:** Abierto  
**Verificado:** `schema_service`, migraciones parciales, tests solo SQLite en CI

Tablas/columnas pueden existir en runtime SQLite sin migración Postgres equivalente. Riesgo de error 500 en prod tras feature nueva.

---

### K-06 — Sesiones revocadas en memoria

**Estado:** Abierto  
**Verificado:** `auth_session.py`, gunicorn multi-worker, Cloud Run `max-instances: 3`

Logout/revocación no se propaga entre workers ni instancias. JWT puede seguir válido hasta expiración TTL.

---

### K-07 — Rate limiting en memoria

**Estado:** Abierto  
**Verificado:** `web/limiter.py` — `storage_uri="memory://"`

Límites por IP no compartidos entre instancias; bypass posible distribuyendo requests.

---

### K-08 — Cron jobs no verificados en GCP

**Estado:** Abierto  
**Verificado:** endpoints + docs; **No verificado** despliegue Scheduler

Competencia automática, purga mensual, motor evaluación y automatización financiera dependen de HTTP cron. Sin scheduler activo, la lógica no se ejecuta periódicamente.

---

### K-09 — Health check superficial

**Estado:** Abierto  
**Verificado:** `GET /api/health` no consulta BD

Cloud Run puede marcar instancia sana mientras Postgres está caído.

---

## Medios (producto / UX / deuda)

### K-10 — Chat libre de encargo deshabilitado (410)

**Estado:** Cerrado funcionalmente / documentado  
**Verificado:** `negociacion_bp` devuelve 410 en rutas legacy

UI o docs antiguos que referencien chat libre están obsoletos. Flujo vigente: negociación guiada.

---

### K-11 — Discrepancia `comision_porcentaje` DDL vs runtime

**Estado:** Abierto  
**Verificado:** default DDL 0.05; runtime usa `apoyo_pct/100` (= 0.12)

Puede confundir auditorías de BD; el valor efectivo es el de `ruana_reglas_v1.json`.

---

### K-12 — Motor evaluación: reglas vacías en JSON

**Estado:** Abierto  
**Verificado:** `ruana_reglas_v1.json` → `"reglas": []`; umbrales en `motor_evaluacion.py`

Cambiar reglas requiere editar código, no config.

---

### K-13 — Inconsistencia puertos desarrollo

**Estado:** Abierto  
**Verificado:** 8080 (flask doc), 5000 (`run.py`, Playwright, `app.__main__`)

Provoca confusión en setup local.

---

### K-14 — Rutas preview/test en build producción

**Estado:** Abierto  
**Verificado:** `/test-panel`, `/feedback-preview`, `/aliado-shell-preview`, etc. en `app.py`

Misma app que producción expone páginas de prueba (sin auth adicional documentada).

---

### K-15 — `DBManager` fachada residual (~1.969 LOC)

**Estado:** Deuda técnica  
**Verificado:** `core/db_manager.py` (`wc -l` = 1969)

Extracción Campamento Base incompleta. Cambios amplios tienen radio de impacto difícil de prever.

---

### K-16 — Firebase Auth admin planificado, no implementado

**Estado:** Abierto  
**Verificado:** plan en `docs/archive/superpowers/plans/2026-07-27-admin-firebase-auth-migration.md`

Admin sigue con credenciales JSON hasheadas. El cambio de contraseña desde el panel persiste en Secret Manager (`RUANA/core/admin_auth.py`); no sustituye Firebase Auth.

---

### K-17 — Supabase Auth / tabla `profiles` no cableada

**Estado:** Abierto  
**Verificado:** migración init crea `profiles`; login Flask no usa `auth.users`

---

### K-18 — Documentación desactualizada (conteos)

**Estado:** En corrección (2026-09-04)  
**Verificado:** pack 2026-08-19 citaba 21 blueprints / 36 services / 30 repos / 784 tests / 28 migraciones; login «solo código»

Cifras verificadas 2026-09-04: **21 blueprints, 37 services, 31 repos, 29 migraciones, 326 rutas en blueprints**. Tests: ver informe del día. El archive conserva cifras históricas a propósito.

---

## Bajos / administrativos

### K-19 — Licencia ausente

**Estado:** Abierto  
**Verificado:** no existe `LICENSE` en raíz

Due diligence legal requiere decisión explícita.

---

### K-20 — Referencia rota `docs/ADMIN_CREDENTIALS_SETUP.md`

**Estado:** Abierto  
**Verificado:** `.env.example` línea 29 referencia archivo inexistente

Usar [`seguridad/credenciales-admin.md`](seguridad/credenciales-admin.md).

---

### K-21 — `ruana.db` local ignorado, no snapshot commiteado

**Estado:** Información corregida  
**Verificado:** `.gitignore` → `*.db`

Documentación anterior afirmaba DB commiteada; **incorrecto** en estado actual del repo.

---

### K-22 — Realtime Supabase

**Estado:** No verificado uso cliente  
**Verificado:** publication en migración DDL

No se encontró consumo Realtime en JS frontend durante auditoría.

---

### K-23 — CORS permisivo (`CORS(app)` sin allowlist)

**Estado:** Abierto en `main`  
**Severidad:** Alta (superficie CSRF/cross-origin si el navegador envía sesión)  
**Verificado:** `RUANA/web/app.py` L147–148 — `CORS(app)` sin `origins`. Flask-Cors 4.0.0 por defecto permite cualquier Origin (`r".*"`).

PR abierto #195 (`cursor/cors-pago-manual-allowlist-2cc1`) propone allowlist — **no fusionado** a 2026-09-04.

---

### K-24 — RLS ausente en tablas financieras y parcial en core

**Estado:** Abierto  
**Severidad:** Alta en combinación con K-02 (service role) y si se usara PostgREST/anon  
**Verificado:** 29 migraciones; solo `init_ruana_clean.sql` crea políticas; `solicitudes_semanales` activa RLS **sin** políticas; **0** migraciones financieras definen RLS.

PR abierto #196 (`cursor/rls-public-tables-2cc1`) — título indica «no aplicar en prod aún».

---

### K-25 — `GET /api/admin/financial/schema-health` sin auth

**Estado:** Abierto  
**Severidad:** Media (filtración de estado de esquema)  
**Verificado:** `financial_admin_bp.py` — rutas `schema-health` sin decorator.

---

### K-27 — Tres tests HTTP de firma Stripe fallan en suite completa

**Estado:** Abierto (flaky / orden)  
**Severidad:** Media (CI puede ponerse rojo sin regresión funcional)  
**Verificado:** 2026-09-04 — suite `RUANA/tests` → fallan `test_http_valid_signature_not_400`, `test_http_altered_body_returns_400`, `test_http_processing_error_after_valid_signature_returns_500`. El archivo entero en aislamiento: **4 passed**.

---

### K-26 — Datos de cobro también en frontend/código (además de JSON)

**Estado:** Abierto (amplía K-03)  
**Severidad:** Alta  
**Verificado:** fallbacks `bizum_num`/`iban` en `pago_service.py`; constantes JS en `aliado.html`; default IBAN en `admin-sistema-module.js`. **No se reproducen valores** en esta documentación.

---

## Inconsistencias documentación ↔ código (histórico)

| Tema | Documentación antigua | Código actual (2026-09-04) |
|------|----------------------|----------------------------|
| Nº blueprints | 2 → 13 → 21 | **21** (sin cambio de recuento; sí de rutas) |
| Nº tests | 383 → 784 (2026-08-19) | Recuento del día: ver auditoría 2026-09-04 |
| Nº services/repos | 16/16 → 36/30 | **37 / 31** |
| Migraciones | 12 → 28 | **29** |
| Login aliado | Código de 5 dígitos, sin contraseña | **Código + PIN** + rate limit + bloqueo + email |
| Stripe mode en deploy | Hardcode `test` | Resuelto por script / vars |
| Motor umbrales | Hardcodeados en `motor_evaluacion.py` | Leídos de `ruana_reglas_v1.json` (`motor_umbral_*`) con default 0.70/0.80/6 |
| CI automático | manual | push/PR a `main`/`dev` |

---

## Cómo reportar nuevos issues

1. Confirmar en código (no solo en UI).
2. Añadir entrada con ID `K-XX`, severidad, evidencia (ruta archivo).
3. Enlazar test de regresión si aplica.
4. Actualizar este archivo y [`PROJECT_AUDIT.md`](PROJECT_AUDIT.md) si es riesgo de handoff.

---

*No incluye backlog de features del roadmap — ver [`operaciones/roadmap.md`](operaciones/roadmap.md).*
