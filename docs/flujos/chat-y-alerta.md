# Chat interno, negociación guiada y alerta de contactos abiertos

> **Autoridad:** [Manual Maestro §8](../../README.md#8-flujos-principales).  
> Original histórico (con límite incorrecto de 5 msgs): [`docs/archive/RUANA/LOGICA_CHAT_Y_ALERTA.md`](../archive/RUANA/LOGICA_CHAT_Y_ALERTA.md).

## Flujo principal de encargo (re-verificado 2026-09-04; rutas 410 sin cambio)

El flujo vigente para cerrar un encargo es la **negociación guiada** (`negociacion_service`, UI `negociacion-guiada.js`):

| Método | Ruta |
|--------|------|
| GET | `/api/contactos/<id>/negociacion` |
| POST | `/api/contactos/<id>/negociacion/proponer` |
| POST | `/api/contactos/<id>/negociacion/proponer-completa` |
| POST | `/api/contactos/<id>/negociacion/aceptar` |
| POST | `/api/contactos/<id>/negociacion/contraoferta` |
| POST | `/api/contactos/<id>/negociacion/cerrar` |

Las rutas globales legacy de chat libre devuelven **410 Gone**:

| Método | Ruta | Respuesta |
|--------|------|-----------|
| POST | `/api/chat_enviar`, `/api/chat/enviar` | 410 — usar negociación guiada |
| GET | `/api/admin/chats` (registro chat libre) | 410 — usar `GET /api/admin/negociaciones` |

## Mensajes de contacto (chat_mensajes)

Existe un subsistema de mensajes por contacto (`chat_service`, tabla `chat_mensajes`) accesible vía:

| Método | Ruta |
|--------|------|
| GET/POST | `/api/contactos/<id>/mensajes` |
| GET | `/api/chat/mensajes`, `/api/chat_mensajes` |

Este mecanismo **no es el flujo principal de la UI** de encargo (sustituido por negociación), pero sigue operativo en código para contactos que lo utilicen.

### Constantes de código (`DBManager` / `chat_service`)

| Constante | Valor | Significado |
|-----------|------:|-------------|
| `CHAT_MAX_MENSAJES_TOTAL` | **30** | Máximo de mensajes **totales** del contacto |
| `CHAT_HORAS_VIGENCIA` | **48** | Horas desde última actividad |

> Corrección respecto a docs archivados: no es «5 mensajes por usuario».

### Reglas verificadas

- Participan solo `solicitante_codigo` y `profesional_codigo`.
- Al alcanzar 30 mensajes → estado `chat_agotado` + posible penalización a quien envió el mensaje límite.
- Vigencia: si pasan 48 h sin actividad, el chat deja de aceptar mensajes según `chat_service.enviar_mensaje_chat`.

## Alerta de contactos abiertos

- `GET /api/contactos/abiertos/<codigo>`
- Excluye contactos con `posponer_recordatorio` activo hasta `fecha_pospuesto_hasta` (`posponer_horas`, default **24** en `ruana_reglas_v1.json`).
- Excluye filas en `contacto_panel_oculto` («Finalizar chat») para ese aliado.
- Acciones: `POST …/en-conversacion`, `POST …/finalizar-chat`.

## Penalizaciones relacionadas (verificadas en `score_service`)

- Sin respuesta ≥48 h → −2 al que no respondió (si el encargo no está en cierre adecuado).
- Chat agotado sin resultado → −2 a quien agotó el cupo.

## Canal de soporte (distinto del chat de encargo)

El **centro de comunicación** aliado–admin (`soporte_bp`, tablas `ruana_soporte_*`) es un canal separado para soporte RUANA, no confundir con chat/negociación de encargo.
