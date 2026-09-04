# Crecimiento orgánico de grupos

> **Autoridad:** [Manual Maestro §3](../../README.md#3-funcionalidades-actuales).  
> **Estado:** VERIFICADO en código (2026-09-04).

## Objetivo

Incentivar que aliados de un grupo en fase de creación inviten a otros profesionales, con recompensas de score acotadas.

## Evidencia en código

| Pieza | Ubicación |
|-------|-----------|
| Service | `RUANA/core/services/grupo_crecimiento_service.py` |
| Repository | `RUANA/core/repositories/grupo_crecimiento_repo.py` |
| Integración invitaciones | `invitacion_bp.py` → `puede_crear_invitacion_crecimiento` |
| Migración PG | `supabase/migrations/20260819000100_grupo_crecimiento_organico.sql` |
| Tests | `RUANA/tests/test_grupo_crecimiento_organico.py` |

## Reglas verificadas

| Constante | Valor | Fuente |
|-----------|------:|--------|
| Grupo «en creación» | ≤ 10 aliados activos | `GRUPO_EN_CREACION_MAX_ALIADOS` en `db_constants.py` |
| Máx. recompensas por invitador | 5 | `CRECIMIENTO_GRUPO_MAX_RECOMPENSAS` |
| Delta score por invitado registrado | 5 | `CRECIMIENTO_GRUPO_SCORE_DELTA` |
| Tipo invitación | `crecimiento_grupo` | `INVITACION_TIPO_CRECIMIENTO_GRUPO` |

## Tablas

- `grupo_crecimiento_recompensas` — registro único `(invitador_codigo, invitado_codigo)` con `score_delta`
- `invitaciones.grupo_id`, `invitaciones.tipo` — columnas añadidas en migración

## RLS

Migración `20260819000100` — **NO RLS** (verificado en archivo SQL).
