# Autenticación y sesiones por pestaña

> **Autoridad:** [Manual Maestro §9](../../README.md#9-seguridad).  
> Verificado en código el **2026-09-04**.  
> Original histórico (solo cookie): [`docs/archive/RUANA/AUTENTICACION_SESIONES_SEGURAS.md`](../archive/RUANA/AUTENTICACION_SESIONES_SEGURAS.md).

## Problema resuelto (sesiones)

Flask guardaba identidad en cookie compartida entre pestañas. Un login en la pestaña A sobrescribía la cookie y la pestaña B operaba como el último usuario.

## Solución vigente de sesión

1. El servidor emite un **`session_id`** (JWT HS256 firmado con `FLASK_SECRET_KEY`).
2. El cliente lo guarda en **`sessionStorage`** (aislado por pestaña).
3. Cada petición autenticada envía **`X-Ruana-Session-Id`**.
4. El backend valida el JWT / store (`core/auth_session.py`) y obtiene `aliado_codigo` o admin.

Admin también acepta `Authorization: Bearer <JWT>` (`auth_decorators.py`).

**Limitación verificada:** el store de revocación es un dict en memoria. Logout no se propaga entre workers gunicorn ni instancias Cloud Run (`max-instances: 3`). El JWT puede seguir válido hasta el TTL.

---

## Login aliado — código + PIN (vigente)

**El login de aliado ya no es un factor único (código de 5 dígitos).**  
Tras el primer acceso, exige **código + PIN**. Evidencia: `auth_bp.py`, `aliado_pin_service.py`, `aliado_pin_auth.py`, `tests/test_aliado_pin_auth.py`, `tests/test_aliado_login_rate_limit.py`.

### Flujo

```text
POST /api/aliado/login  { codigo, pin? }
        │
        ├─ aliado inexistente / PIN incorrecto / bloqueado → 401 "Credenciales incorrectas"
        ├─ estado expulsado|pendiente|rechazado|suspendido|en_espera → 403
        ├─ sin pin_hash → 200 { pin_setup_required: true, setup_token }
        │       └─ POST /api/aliado/pin/crear  { setup_token, pin } → sesión
        └─ con PIN correcto → 200 { session_id }
```

| Parámetro | Default | Variable |
|-----------|---------|----------|
| Formato PIN | 4–6 dígitos | — (`aliado_pin_auth.py`) |
| Intentos fallidos máx. | 5 | `RUANA_PIN_MAX_INTENTOS` |
| Bloqueo | 15 min | `RUANA_PIN_BLOQUEO_MINUTOS` |
| TTL setup token | 900 s | `RUANA_PIN_SETUP_EXPIRES` |
| Hash | Werkzeug `generate_password_hash` | — |
| Rate limit login | 30/h + 10/min | Flask-Limiter (`auth_bp.py`) |

Tras `PIN_MAX_INTENTOS` fallos se escribe `pin_bloqueado_hasta`. Mientras el bloqueo está activo, incluso el PIN correcto devuelve 401 genérico (anti-enumeración).

### Recuperación por email

OTP de 6 dígitos (`aliado_pin_service.py`):

| Paso | Endpoint |
|------|----------|
| Solicitar | `POST /api/aliado/recuperacion/solicitar` (`tipo`: `pin`, `codigo` o `ambos`) |
| Verificar OTP | `POST /api/aliado/recuperacion/verificar` |
| Nuevo PIN | `POST /api/aliado/recuperacion/pin` |

TTL OTP: `RUANA_RECUPERACION_OTP_MINUTOS` (default 15). Máx. intentos OTP: `RUANA_RECUPERACION_MAX_INTENTOS` (default 5). Mensaje genérico anti-enumeración.

Cambio de PIN autenticado: `POST /api/aliado/pin/cambiar` (`@require_aliado`).

### Endpoints de sesión aliado

| Rol | Login | Sesión | Logout |
|-----|-------|--------|--------|
| Aliado | `POST /api/aliado/login` | `GET /api/aliado/sesion` | `POST /api/aliado/logout` |
| Admin | `POST /api/admin/validar` | `GET /api/admin/me` | `POST /api/admin/logout` |

TTL: `RUANA_ALIADO_SESSION_EXPIRES` / `RUANA_ADMIN_SESSION_EXPIRES` (default 3600).

**Adopción del PIN en producción:** `NO VERIFICADO` (el código lo exige; no hay métrica de aliados con `pin_hash` en este informe).

---

## Admin

Contraseñas hasheadas (`core/admin_auth.py`). Ver [credenciales-admin.md](credenciales-admin.md).

- Dev: `.local-secrets/admin_credentials.json`
- Prod: GCP Secret Manager si `_should_use_secret_manager()`
- Fallback QA commiteado: `config/admin_credentials.qa.json` (**hashes**, no plaintext)

`POST /api/admin/validar` tiene rate limit 10/h + 5/min. Middleware `app.py` bloquea `/api/admin/*` salvo `/validar`, `/logout`, `/bp-health`. Bypass cron: secreto o OIDC.

Migración futura a Firebase Auth: plan en `docs/archive/superpowers/plans/2026-07-27-admin-firebase-auth-migration.md` — **no implementado** en Python.

---

## Rate limit

`web/limiter.py` usa `storage_uri="memory://"`. No se comparte entre instancias. Se desactiva si `TESTING`, `RUANA_DISABLE_RATE_LIMIT`, `CI` o `RUANA_DB_PATH` (diseño para tests/E2E).
