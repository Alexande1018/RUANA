# Chat interno y alerta de contactos abiertos

> **Autoridad:** [Manual Maestro §5.10–5.11 y §6.4](../../README.md#510-chat).  
> Original histórico (con límite incorrecto de 5 msgs): [`docs/archive/RUANA/LOGICA_CHAT_Y_ALERTA.md`](../archive/RUANA/LOGICA_CHAT_Y_ALERTA.md).

## Constantes de código (`DBManager`)

| Constante | Valor | Significado |
|-----------|------:|-------------|
| `CHAT_MAX_MENSAJES_TOTAL` | **30** | Máximo de mensajes **totales** del contacto |
| `CHAT_HORAS_VIGENCIA` | **48** | Horas desde última actividad |

> Corrección respecto a docs previos: no es «5 mensajes por usuario».

## Modelo

- Tabla `chat_mensajes` ligada a `contactos_ruana`.
- Participan solo `solicitante_codigo` y `profesional_codigo`.
- Al alcanzar 30 mensajes → estado `chat_agotado` + posible penalización a quien envió el mensaje límite.
- Vigencia: si pasan 48 h sin actividad, el chat deja de aceptar mensajes según reglas de `enviar_mensaje_chat`.

## APIs

| Método | Ruta |
|--------|------|
| GET/POST | `/api/contactos/<id>/mensajes` |
| GET | `/api/chat/mensajes`, `/api/chat_mensajes` |
| POST | `/api/chat/enviar`, `/api/chat_enviar` (este último valida sesión en el handler) |

## Alerta de abiertos

- `GET /api/contactos/abiertos/<codigo>`
- Excluye contactos con `posponer_recordatorio` activo hasta `fecha_pospuesto_hasta` (`posponer_horas`, default 24).
- Excluye filas en `contacto_panel_oculto` («Finalizar chat») para ese aliado.
- Acciones: `POST …/en-conversacion`, `POST …/finalizar-chat`.

## Penalizaciones relacionadas

- Sin respuesta ≥48 h → −2 al que no respondió (si el encargo no está en cierre adecuado).
- Chat agotado sin resultado → −2 a quien agotó el cupo.
