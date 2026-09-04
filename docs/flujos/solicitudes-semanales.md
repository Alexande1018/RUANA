# Solicitudes semanales

> **Autoridad:** código en `solicitud_semanal_service.py`, `solicitudes_semanales_bp.py`, migración `20260819000200_solicitudes_semanales.sql`.  
> Verificado 2026-09-04. No confundir con las **solicitudes de grupo** (`solicitudes_bp` / tabla `solicitudes`).

## Qué es

Tablero semanal (semana = lunes–domingo) donde un aliado publica una necesidad y el resto del grupo responde: *puedo ayudar*, *no puedo ayudar* o *conozco a alguien*.

## Evidencia

| Pieza | Ubicación |
|-------|-----------|
| Blueprint | `RUANA/web/blueprints/solicitudes_semanales_bp.py` (9 rutas) |
| Service | `RUANA/core/services/solicitud_semanal_service.py` |
| Repo | `RUANA/core/repositories/solicitud_semanal_repo.py` |
| Tests | `RUANA/tests/test_solicitudes_semanales.py` |
| Migración PG | `supabase/migrations/20260819000200_solicitudes_semanales.sql` |
| Panel admin | `GET /api/admin/solicitudes-semanales` (commit `1e77b32`) |

## Rutas verificadas

| Método | Ruta |
|--------|------|
| GET | `/api/solicitudes-semanales/bp-health` |
| GET, POST | `/api/solicitudes-semanales` |
| PATCH | `/api/solicitudes-semanales/<id>` |
| POST | `/api/solicitudes-semanales/<id>/puedo-ayudar` |
| POST | `/api/solicitudes-semanales/<id>/no-puedo-ayudar` |
| POST | `/api/solicitudes-semanales/<id>/conozco-alguien` |
| GET | `/api/solicitudes-semanales/<id>/interesados` |
| GET | `/api/admin/solicitudes-semanales` |
| POST | `/api/solicitudes-semanales/expirar` |

## RLS

La migración **activa RLS** en `solicitudes_semanales` y `solicitudes_semanales_respuestas` **sin `CREATE POLICY`**. Acceso PostgREST/anon queda denegado por defecto. El backend Flask usa service role y **elude RLS**. Autorización efectiva = decorators Flask.

## Relación con solicitudes de grupo

Las solicitudes de plaza/grupo (`/api/solicitudes`) son otro dominio (`solicitud_service`). Este módulo no las reemplaza.
