# Solicitudes semanales

> **Autoridad:** [Manual Maestro §3](../../README.md#3-funcionalidades-actuales).  
> **Estado:** VERIFICADO en código (2026-09-04).

## Objetivo

Permitir que un aliado publique una necesidad profesional semanal para su grupo (distinto de las solicitudes de grupo clásicas en `solicitudes_bp`).

## Evidencia en código

| Pieza | Ubicación |
|-------|-----------|
| Blueprint | `RUANA/web/blueprints/solicitudes_semanales_bp.py` (9 rutas) |
| Service | `RUANA/core/services/solicitud_semanal_service.py` |
| Repository | `RUANA/core/repositories/solicitud_semanal_repo.py` |
| Migración PG | `supabase/migrations/20260819000200_solicitudes_semanales.sql` |
| Tests | `RUANA/tests/test_solicitudes_semanales.py` |

## Endpoints principales

| Método | Ruta | Rol |
|--------|------|-----|
| GET/POST | `/api/solicitudes-semanales` | Aliado (listar / crear) |
| GET | `/api/solicitudes-semanales/<id>` | Aliado |
| POST | `/api/solicitudes-semanales/<id>/puedo-ayudar` | Aliado |
| POST | `/api/solicitudes-semanales/<id>/no-puedo-ayudar` | Aliado |
| POST | `/api/solicitudes-semanales/<id>/conozco-alguien` | Aliado |
| GET | `/api/solicitudes-semanales/<id>/interesados` | Aliado |
| GET | `/api/admin/solicitudes-semanales` | Admin |
| POST | `/api/solicitudes-semanales/expirar` | Cron / admin |

## Reglas verificadas

- Una solicitud activa por aliado y semana (`UNIQUE solicitante_codigo, semana_inicio`).
- Semana inicia en lunes (`_semana_inicio_lunes`).
- Respuestas: `puedo_ayudar`, `no_puedo_ayudar`, `conozco_alguien` — tabla `solicitudes_semanales_respuestas`.
- Notificaciones al grupo vía `notificacion_service` con `origen: solicitud_semanal`.

## RLS

Migración `20260819000200` — `ENABLE ROW LEVEL SECURITY` en `solicitudes_semanales` y `solicitudes_semanales_respuestas`. **Sin políticas `CREATE POLICY` en el archivo.** Efecto en producción con service role Flask: **bypaseado**. Políticas para acceso directo Supabase: **NO VERIFICADO**.
