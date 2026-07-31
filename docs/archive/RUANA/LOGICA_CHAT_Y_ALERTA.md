# Lógica del sistema de Chat y Alerta RUANA

Este documento describe de punta a punta la lógica del **chat interno RUANA** (entre solicitante y profesional de un contacto) y del **panel de alerta** en el panel del aliado (seguimiento de contactos abiertos).

---

## 1. Modelo de datos del chat

### 1.1 Tabla `chat_mensajes`

- **Ubicación**: Creada por migración en `core/db_manager.py` (`_migrar_chat_mensajes`).
- **Propósito**: Mensajes del chat interno entre los dos aliados de un contacto (solicitante y profesional).

| Columna        | Tipo     | Descripción                                      |
|----------------|----------|--------------------------------------------------|
| `id`           | INTEGER  | PK autoincrement                                 |
| `contacto_id`  | INTEGER  | FK a `contactos_ruana(id)`                        |
| `emisor_codigo`| TEXT     | Código del aliado que envía                      |
| `receptor_codigo` | TEXT  | Opcional; el otro código del contacto            |
| `texto`        | TEXT     | Contenido del mensaje                            |
| `creado_en`    | TIMESTAMP| Fecha/hora de creación                           |

- **Índice**: `idx_chat_mensajes_contacto` sobre `chat_mensajes(contacto_id)`.

**Un solo source of truth**: El panel de administración lee desde `chat_mensajes` con JOIN a `contactos_ruana` y `aliados` (emisor y receptor por código). No existe tabla duplicada `chat_messages`.

### 1.2 Contactos y estados que afectan al chat y a la alerta

- En `contactos_ruana` se usan, entre otros, los estados:
  - `iniciado`, `aceptado`, `trabajo_en_progreso`: contacto abierto; chat y alerta aplican.
  - `importe_en_disputa`: contacto abierto; alerta muestra mensaje de disputa y, si aplica, subida de comprobante.
  - `en_conversacion`: si `posponer_recordatorio = 1` y `fecha_pospuesto_hasta` > now, el backend no incluye el contacto en la alerta; tras esa fecha la alerta reaparece (límite temporal configurable).
  - `chat_agotado`: ambos usuarios han llegado al límite de 5 mensajes; el contacto sigue "abierto" para la alerta pero solo se permite cerrar (Sí hubo trabajo / No se concretó).
- **`posponer_recordatorio`** (INTEGER) y **`fecha_pospuesto_hasta`** (TIMESTAMP): cuando el aliado usa "Sigue en conversación", se pone `posponer_recordatorio = 1` y `fecha_pospuesto_hasta = now + posponer_horas` (config, p. ej. 24 h). El backend excluye de la alerta solo mientras `fecha_pospuesto_hasta` > now; pasado ese tiempo la alerta vuelve a mostrarse.

---

## 2. Reglas de negocio del chat

- **Vigencia**: 48 horas desde **última actividad**, no desde creación del contacto:
  - **A) Si hay mensajes** → 48 h desde el **último mensaje** (`MAX(creado_en)` en `chat_mensajes`).
  - **B) Si no hay mensajes** → 48 h desde **aceptación del profesional** (`fecha_aceptacion`) o, si no existe, desde `creado_en` del contacto.
- Así no se penaliza un contacto activado o con conversación reciente. Constantes en `DBManager`:  
  `CHAT_MAX_MENSAJES_POR_USUARIO = 5`, `CHAT_HORAS_VIGENCIA = 48`.
- **Límite de mensajes**: Máximo **5 mensajes por usuario** en `chat_mensajes`. Cuando **ambos** usuarios alcanzan el límite, el contacto pasa a **`chat_agotado`** (alerta de cierre obligatorio; se oculta «Sigue en conversación»). Si solo uno tiene 5, no puede enviar más; el contacto sigue abierto y la alerta sigue mostrándose hasta que se cierre por “Sí, hubo trabajo”, “No se concretó” o resolución admin.
- **Permisos**: Solo el **solicitante** y el **profesional** del contacto pueden listar y enviar mensajes en ese contacto. Se comprueba que `codigo` (o `emisor_codigo`) sea uno de los dos.

---

## 3. APIs del chat

### 3.1 Listar mensajes y estado del chat

- **GET** `/api/chat_mensajes?contacto_id=<id>&codigo=<codigo_aliado>`
  - Respuesta: `{ status, mensajes[], chat_expirado, mensajes_restantes }`.
  - Backend: `db.listar_mensajes_contacto(contacto_id)` y `db.estado_chat_contacto(contacto_id, codigo)`.
  - `chat_expirado`: true si el contacto está en estado final (`_ESTADOS_FINALES_CONTACTO`) — por ejemplo cuando las dos partes confirman el valor y se envía la alerta de pago (`trabajo_cerrado`) — o si han pasado más de 48 h desde la última actividad.
  - `mensajes_restantes`: 0 si contacto cerrado; si no, `max(0, 5 - mensajes del usuario)`.

### 3.2 Enviar mensaje

- **POST** `/api/chat_enviar`  
  Body: `{ contacto_id, emisor_codigo, texto }`.
- **POST** `/api/chat/enviar`  
  Mismo cuerpo y lógica (alias).
- Backend: `db.enviar_mensaje_chat(contacto_id, emisor_codigo, texto)`:
  - Comprueba que el contacto exista y que `emisor_codigo` sea solicitante o profesional.
  - Comprueba vigencia 48 h desde `creado_en`.
  - Comprueba que el usuario no haya llegado a 5 mensajes; si no, inserta en `chat_mensajes` (admin lee desde aquí con JOIN a aliados).
  - Devuelve error con mensaje amigable si está expirado o al límite.

### 3.3 Rutas alternativas por contacto

- **GET** `/api/contactos/<id>/mensajes?codigo=XXX` → lista mensajes (misma lógica que listar).
- **POST** `/api/contactos/<id>/mensajes` body `{ emisor_codigo, texto }` → envía mensaje (misma lógica que enviar).

---

## 4. APIs relacionadas con la alerta (contactos abiertos)

### 4.1 Contactos abiertos del aliado

- **GET** `/api/contactos/abiertos/<codigo_aliado>`
  - Devuelve solo contactos que deben mostrarse como **alerta activa**: estado en `iniciado`, `aceptado`, `trabajo_en_progreso`, `importe_en_disputa`, `en_conversacion`, `chat_agotado` **y** `posponer_recordatorio = 0`. Si `posponer_recordatorio = 1`, el backend no los incluye (server-driven). **Todo chat expirado** (más de 48 h desde última actividad) se excluye; los contactos que el aliado ha **finalizado** (tabla `contacto_panel_oculto`) tampoco se incluyen.
  - Backend: `db.obtener_contactos_abiertos_por_codigo(codigo_aliado)`.
  - Cada item incluye, entre otros: `id`, `solicitante_codigo`, `profesional_codigo`, `servicio`, `estado`, `num_mensajes`. La respuesta es limitada a propósito (no expone importes declarados en detalle).
- **POST** `/api/contactos/<id>/finalizar-chat`  
  - Oculta este contacto del panel personal del aliado (botón «Finalizar chat» en el modal). Inserta en `contacto_panel_oculto`; el contacto deja de mostrarse en contactos abiertos para ese aliado. Backend: `db.ocultar_contacto_del_panel(contacto_id, codigo_aliado)`.

### 4.2 Marcar “Sigue en conversación”

- **POST** `/api/contactos/<id>/en-conversacion`  
  Body: `{ usuario: "<codigo_aliado>" }`.
  - Backend: `db.marcar_en_conversacion(contacto_id, actor_codigo=usuario)`.
  - Pone `estado = 'en_conversacion'` y `posponer_recordatorio = 1`; no modifica score; no aplica si el contacto ya está en estado final. En la siguiente petición a contactos abiertos, el backend ya no devuelve ese contacto.

---

## 5. Flujo en el panel del aliado (`web/aliado.html`)

### 5.1 Carga inicial y aviso persistente

- Al cargar el panel se llama a `cargarContactosPendientes()`:
  - Pide **GET** `/api/contactos/abiertos/<codigo>`.
  - El backend devuelve contactos que deben mostrarse como alerta: excluye solo si `posponer_recordatorio = 1` y `fecha_pospuesto_hasta` > now (límite temporal).
  - Si hay contactos, se toma el primero como `contactoActual` y se muestra el bloque `#contacto-aviso-persistente` con texto según estado y número de mensajes.

### 5.2 Contenido del aviso según estado

- **Estado normal** (iniciado, aceptado, trabajo_en_progreso, en_conversacion): mensaje tipo “Tienes un contacto activo. Usa **Abrir chat**… Cuando lo consideres oportuno, indícanos el resultado.” Si `num_mensajes > 0`, se añade “Tienes N mensaje(s) pendiente(s) de leer.”
- **Estado `importe_en_disputa`**: mensaje indicando que hay declaración diferente y que debe aclararse; si el aliado es el solicitante y existe conflicto en estado `PENDIENTE_PRUEBA`, se muestra el bloque “Subir comprobante de pago” (input file + botón “Enviar prueba”).

### 5.3 Botones del aviso y acciones

| Botón                  | Acción en frontend / backend |
|------------------------|-----------------------------|
| **Abrir chat**         | `abrirChatDesdeContactoActual()` → abre el modal de chat con `contactoActual.id`, carga mensajes (`cargarMensajesChat()`), llama a `iniciarPollingChat()` (el panel tiene `_chatPollingIntervalId`; la implementación actual no usa `setInterval`; el aviso indica que los mensajes “se actualizan solos” — se puede implementar polling más adelante). |
| **Sí, hubo trabajo**  | `handleAvisoSiHuboTrabajo()` → abre el modal `#modal-contacto-importe` (Confirmación de trabajo realizado). El usuario introduce importe y confirma → `confirmarImporteContacto()` → POST `/api/contactos/<id>/declarar-importe` con `parte` (solicitante/profesional), `importe`, `moneda`, `usuario`. Si el backend devuelve `estado === 'trabajo_cerrado'` se muestra resumen de cierre; si `estado === 'importe_en_disputa'` se actualiza el texto del aviso y se muestra la opción de subir comprobante. Luego se cierra el modal y se recargan contactos pendientes. |
| **No se concretó**     | `handleAvisoNoSeConcreto()` → muestra el modal `#modal-no-concretado`. El modal **solo se cierra** con “Confirmar” o “Cancelar” (listener en el overlay hace `preventDefault`/`stopPropagation` al clic en el overlay para no cerrar al hacer clic fuera). “Confirmar” → `confirmarNoConcretado()` → POST `/api/contactos/<id>/no-concretado` con `motivo`, `usuario`; tras éxito se cierra el modal y se llama a `cargarContactosPendientes()`. |
| **Sigue en conversación** | POST `/api/contactos/<id>/en-conversacion`; backend pone `posponer_recordatorio = 1` y `fecha_pospuesto_hasta = now + posponer_horas` (config). La alerta se oculta solo hasta esa fecha; después reaparece. |

### 5.4 Modal de chat

- Se abre con `abrirChatContacto(contactoId, profesional)` (desde directorio o desde el aviso).
- Carga mensajes con **GET** `/api/chat_mensajes` y actualiza `chatExpirado`, `mensajesRestantes` y la UI; deshabilita input/Enviar si el chat está expirado/cerrado o no quedan mensajes.
- **Polling**: mientras el modal está abierto, `iniciarPollingChat()` arranca un `setInterval` de 5 s que llama a `cargarMensajesChat(true)` (actualización en segundo plano sin mostrar "Cargando..."). Al cerrar el modal, `detenerPollingChat()` hace `clearInterval`.
- Enviar: **POST** `/api/chat_enviar`; si el contacto está cerrado, el backend rechaza con "Contacto cerrado; no se pueden enviar más mensajes."
- **Finalizar chat**: botón en el modal que llama a **POST** `/api/contactos/<id>/finalizar-chat`. El contacto se marca como oculto para ese aliado en `contacto_panel_oculto` y deja de mostrarse en el panel personal (contactos abiertos).

---

## 6. Flujo en administración

- **Conversaciones / Chats**: El panel admin consume listados que usan `db.listar_contactos_recientes_con_chat`, `db.listar_conversaciones_admin` y `db.listar_chat_messages`; todos leen únicamente de `chat_mensajes` (con JOIN a aliados cuando se necesita emisor/receptor).
- **Pendientes de validación**: Son aliados con `estado = 'pendiente_validacion'`; se listan en la sección correspondiente y se pueden Activar o Rechazar. No forman parte directa de la lógica del chat o de la alerta, pero el aliado solo puede usar chat y alerta una vez activado.

---

## 7. Resumen de constantes y claves de sesión

| Constante / clave | Valor / uso |
|------------------|-------------|
| `CHAT_MAX_MENSAJES_POR_USUARIO` | 5 (db_manager) |
| `CHAT_HORAS_VIGENCIA` | 48 (db_manager) |
| Posponer alerta | `posponer_recordatorio = 1` + `fecha_pospuesto_hasta` (config `posponer_horas`, p. ej. 24). La alerta se oculta solo hasta esa fecha. |
| `ruana_codigo_aliado` / `ruana_aliado_data` | sessionStorage para código y datos del aliado en el panel |

---

## 8. Archivos de referencia

- **Backend**: `core/db_manager.py` (tabla `chat_mensajes`, migraciones, `listar_mensajes_contacto`, `estado_chat_contacto`, `enviar_mensaje_chat`, `listar_chat_messages` para admin desde `chat_mensajes`+JOIN, `obtener_contactos_abiertos_por_codigo`, `marcar_en_conversacion`).
- **API**: `web/app.py` (`/api/chat_mensajes`, `/api/chat_enviar`, `/api/chat/enviar`, `/api/contactos/<id>/mensajes`, `/api/contactos/abiertos/<codigo>`, `/api/contactos/<id>/en-conversacion`, `/api/contactos/<id>/no-concretado`, `/api/contactos/<id>/declarar-importe`).
- **Panel aliado**: `web/aliado.html` (bloque `#contacto-aviso-persistente`, `cargarContactosPendientes`, botones Abrir chat / Sí hubo trabajo / No se concretó / Sigue en conversación, modales de importe y no concretado, modal de chat, alerta según lo que devuelve el backend (posponer_recordatorio server-driven)).
- **Admin**: `web/admin.html` (sección de conversaciones/chats y pendientes de validación según corresponda).
