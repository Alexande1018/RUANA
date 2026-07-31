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

## Endpoints clave

| Rol | Login | Sesión | Logout |
|-----|-------|--------|--------|
| Aliado | `POST /api/aliado/login` | `GET /api/aliado/sesion` | `POST /api/aliado/logout` |
| Admin | `POST /api/admin/validar` | `GET /api/admin/me` | `POST /api/admin/logout` |

## Expiración

- `RUANA_ALIADO_SESSION_EXPIRES` (default 3600)
- `RUANA_ADMIN_SESSION_EXPIRES` (default 3600)

## Admin

Contraseñas hasheadas (`core/admin_auth.py`). Ver [credenciales-admin.md](credenciales-admin.md).  
Migración futura a Firebase Auth: plan en `docs/archive/superpowers/plans/2026-07-27-admin-firebase-auth-migration.md`.
