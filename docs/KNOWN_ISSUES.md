# Problemas conocidos y limitaciones

Registro de issues **confirmados en código o documentación**, no lista aspiracional de mejoras. Actualizar al corregir cada ítem.

| | |
|---|---|
| Fecha | 2026-09-04 |
| Auditoría | [`PROJECT_AUDIT.md`](PROJECT_AUDIT.md) · [`exports/AUDITORIA_DOCUMENTAL_2026-09-04.md`](exports/AUDITORIA_DOCUMENTAL_2026-09-04.md) |

---

## Críticos (impacto seguridad / dinero / acceso)

### K-01 — Login aliado: código + PIN

**Estado:** Mitigado parcialmente (PIN implementado)  
**Severidad:** Media–Alta  
**Verificado:** `auth_bp.py`, `aliado_pin_auth.py`, `aliado_pin_service.py`, `POST /api/aliado/login`

El login exige **código de 5 dígitos + PIN de 4–6 dígitos** (dos factores de conocimiento). Incluye rate limiting (`30/h`, `10/min`), bloqueo tras `RUANA_PIN_MAX_INTENTOS` intentos fallidos y recuperación por OTP email.

**Riesgo residual:** el código de aliado sigue siendo un secreto de alto valor; no hay MFA hardware ni rotación obligatoria del código. Compromiso de código + PIN (o de sesión JWT) = acceso completo.

**Documentación anterior incorrecta:** afirmaba «código único sin contraseña» — obsoleto desde implementación PIN.

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

Contiene IBAN, número Bizum y URLs de QR en historial git. Además, `pago_service.py` define **fallbacks hardcodeados** con los mismos datos si falla la lectura del JSON. No rotar automáticamente si se filtran. Requiere migración a secret manager / variables de entorno.

---

---

### K-04 — Stripe en modo test en deploy producción

**Estado:** Abierto  
**Severidad:** Alta (si se esperan cobros live)  
**Verificado:** `.github/workflows/deploy-firebase.yml` línea `RUANA_STRIPE_MODE=test`

Cada deploy desde `main` fija modo test. Cobros reales requieren cambio explícito a `live` y claves `sk_live_`.

---

### K-04a — CORS sin restricción de orígenes

**Estado:** Abierto  
**Severidad:** Media  
**Verificado:** `web/app.py` — `CORS(app)` sin `origins`

Flask-Cors con configuración por defecto permite peticiones desde cualquier origen. **PR abierto sin merge:** `cursor/cors-pago-manual-allowlist-2cc1`.

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

### K-15 — `DBManager` fachada residual (~1.925 LOC)

**Estado:** Deuda técnica  
**Verificado:** `core/db_manager.py`

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

### K-18 — Documentación desactualizada (conteos pre-financial)

**Estado:** En corrección (2026-08-19)  
**Verificado:** README/roadmap citaban 13 blueprints, 383 tests

Actualizado en entrega de docs de cierre; revisar docs en `archive/` que sigan citando cifras antiguas.

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

## Inconsistencias documentación ↔ código (histórico)

| Tema | Documentación antigua | Código actual |
|------|----------------------|---------------|
| Nº blueprints | 13 | 21 |
| Nº tests | 383 | 784 passed |
| Nº services/repos | 16/16 | 36/30 |
| CI automático | manual (regla Campamento Base antigua) | push/PR activo |

---

## Cómo reportar nuevos issues

1. Confirmar en código (no solo en UI).
2. Añadir entrada con ID `K-XX`, severidad, evidencia (ruta archivo).
3. Enlazar test de regresión si aplica.
4. Actualizar este archivo y [`PROJECT_AUDIT.md`](PROJECT_AUDIT.md) si es riesgo de handoff.

---

*No incluye backlog de features del roadmap — ver [`operaciones/roadmap.md`](operaciones/roadmap.md).*
