# Centro de Actividad (RUANA Pulse)

> **Autoridad:** frontend `ruana-pulse.js` + backend `actividad_cinta_service`.  
> Verificado 2026-09-04. Feature reciente (PRs #206, #208, #209 en `main`).

## Qué es

Panel flotante en `aliado.html` («Actividad») que muestra la cinta de novedades del aliado. No es un blueprint HTTP propio.

## Evidencia

| Pieza | Ubicación |
|-------|-----------|
| UI | `RUANA/web/static/js/ruana-pulse.js`, `static/css/ruana-pulse.css` |
| Host | `aliado.html` (trigger `#ruana-pulse-trigger`) + `PrivatePanel` |
| Preview | `RUANA/web/ruana-pulse-preview.html` (ruta HTML **no** registrada en `app.py` — preview estático) |
| Datos | `actividad_cinta_service` (`MAX_ACTIVIDAD_CINTA = 10`) vía `notificacion_service.preparar_actividad_cinta*` |
| Transporte | Campo `actividad_cinta` en `GET/POST /api/aliado/datos` y en notificaciones (`aliado_bp.py`) |
| Persistencia | `actividad_repo.py` |
| Tests | `test_actividad_cinta_*.py` (service, frontend contract, nombres, postgres) |

La cinta excluye tipos de notificación de pago/soporte/competencia personal (`_CINTA_TIPOS_EXCLUIDOS` en `actividad_cinta_service.py`).

## Relación con alertas

El módulo `aliado-alertas-module.js` también consume `actividad_cinta`. Pulse es la UI premium que envuelve la misma cinta.

## PRs abiertos relevantes (2026-09-04)

| PR | Título | Nota |
|----|--------|------|
| #207 | fix(pulse): detalle de Apoyo RUANA con la firma correcta del panel | Abierto; `main` ya incluye #208/#209 |

Estado de adopción en producción: **NO VERIFICADO** (la UI está en `aliado.html` del repo; el despliegue efectivo depende del último deploy).
