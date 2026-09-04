# Autenticación segura y sesiones por pestaña

> **Autoridad:** [Manual Maestro §11](../../README.md#11-seguridad).  
> Este documento detalla el fallo histórico de sesiones cruzadas y el diseño vigente.  
> Original archivado: [`docs/archive/RUANA/AUTENTICACION_SESIONES_SEGURAS.md`](../archive/RUANA/AUTENTICACION_SESIONES_SEGURAS.md).

## Problema resuelto

Flask guardaba identidad en cookie de sesión compartida entre pestañas del mismo origen. Un login en la pestaña A sobrescribía la cookie y la pestaña B pasaba a operar como el último usuario.

## Solución vigente

1. El servidor emite un **`session_id`** (JWT HS256 firmado con `FLASK_SECRET_KEY`).
2. El cliente lo guarda en **`sessionStorage`** (aislado por pestaña).
3. Cada petición autenticada envía **`X-Ruana-Session-Id`**.
4. El backend valida el JWT / store de sesión y obtiene `aliado_codigo` o admin.

## Login aliado: código + PIN (VERIFICADO)

Desde la implementación en `aliado_pin_auth.py`, `aliado_pin_service.py` y `auth_bp.py`:

| Paso | Endpoint | Comportamiento |
|------|----------|----------------|
| Login | `POST /api/aliado/login` | Body: `{ codigo, pin }`. Valida código 5 dígitos + PIN 4–6 dígitos |
| Sin PIN configurado | misma ruta | Respuesta `pin_setup_required: true` + `setup_token` JWT |
| Crear PIN inicial | `POST /api/aliado/pin/crear` | Requiere `setup_token`; confirma PIN |
| Cambiar PIN | `POST /api/aliado/pin/cambiar` | Sesión aliado activa |
| Recuperación | `POST /api/aliado/recuperacion/solicitar` | Envía OTP por email al aliado |
| Verificar OTP | `POST /api/aliado/recuperacion/verificar` | Valida OTP |
| Reset PIN | `POST /api/aliado/recuperacion/pin` | Establece nuevo PIN tras OTP |

### Protecciones (VERIFICADO)

| Mecanismo | Configuración | Fuente |
|-----------|---------------|--------|
| Rate limit login | `30/hour`, `10/minute` | `auth_bp.py` + `web/limiter.py` |
| Máx. intentos PIN | `RUANA_PIN_MAX_INTENTOS` (default 5) | `aliado_pin_auth.py` |
| Bloqueo temporal | `RUANA_PIN_BLOQUEO_MINUTOS` (default 15) | `aliado_pin_auth.py` |
| Setup token TTL | `RUANA_PIN_SETUP_EXPIRES` (default 900 s) | `aliado_pin_auth.py` |
| OTP recuperación TTL | `RUANA_RECUPERACION_OTP_MINUTOS` (default 15) | `aliado_pin_service.py` |
| Hash PIN | Werkzeug `generate_password_hash` | `aliado_pin_auth.py` |
| Mensaje genérico | `Credenciales incorrectas` (no revela si falló código o PIN) | `aliado_pin_auth.py` |

> **Nota histórica:** la documentación anterior (hasta 2026-08-15) describía login solo por código. Eso ya **no coincide** con el código actual.

## Endpoints clave

| Rol | Login | Sesión | Logout |
|-----|-------|--------|--------|
| Aliado | `POST /api/aliado/login` (código + PIN) | `GET /api/aliado/sesion` | `POST /api/aliado/logout` |
| Admin | `POST /api/admin/validar` | `GET /api/admin/me` | `POST /api/admin/logout` |

## Expiración

- `RUANA_ALIADO_SESSION_EXPIRES` (default 3600)
- `RUANA_ADMIN_SESSION_EXPIRES` (default 3600)

## Admin

Contraseñas hasheadas (`core/admin_auth.py`). Ver [credenciales-admin.md](credenciales-admin.md).  
Migración futura a Firebase Auth: plan en `docs/archive/superpowers/plans/2026-07-27-admin-firebase-auth-migration.md`.

## CORS (relacionado)

`web/app.py` ejecuta `CORS(app)` sin allowlist de orígenes. Ver riesgo en [KNOWN_ISSUES.md](../KNOWN_ISSUES.md) y Manual Maestro §9.
