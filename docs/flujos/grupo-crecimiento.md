# Crecimiento orgánico de grupos

> **Autoridad:** `grupo_crecimiento_service.py`, `grupo_crecimiento_repo.py`, `db_constants.py`, migración `20260819000100_grupo_crecimiento_organico.sql`.  
> Verificado 2026-09-04.

## Qué es

Mecanismo para que un grupo **en creación** crezca por invitaciones de sus propios aliados, con tope de recompensas de score.

## Constantes verificadas (`db_constants.py`)

| Constante | Valor | Significado |
|-----------|------:|-------------|
| `GRUPO_EN_CREACION_MAX_ALIADOS` | 10 | Un grupo está «en creación» con 0–10 aliados activos inclusive |
| `CRECIMIENTO_GRUPO_MAX_RECOMPENSAS` | 10 | Tope de recompensas por invitador |
| `CRECIMIENTO_GRUPO_SCORE_DELTA` | 5 | Puntos de score por recompensa |

`es_grupo_en_creacion(n)` → `n <= 10`.

## Persistencia

Migración `20260819000100`:

- columnas `grupo_id`, `tipo` en `invitaciones`;
- tabla `grupo_crecimiento_recompensas`.

**Sin RLS** en esta migración.

## API

No hay blueprint propio. El progreso se expone a través de servicios de invitación/aliado (`info_progreso_invitador`). Tests: `test_grupo_crecimiento_organico.py`.
