# RUANA — Red Unida de Apoyo entre Negocios Aliados

## Documento oficial único

**Este archivo es la única fuente de verdad del proyecto RUANA.** Cualquier otro `.md` en el repositorio es complementario o histórico; la descripción funcional y técnica autorizada está aquí. Para detalle extendido: chat y alerta (`docs/LOGICA_CHAT_Y_ALERTA.md`), autenticación (`docs/AUTENTICACION_SESIONES_SEGURAS.md`), flujo registro (`docs/FLUJO_REGISTRO_ALIADOS_OFICIOS.md`).

---

## 1. ¿Qué es RUANA?

**RUANA** es un **sistema de control, coordinación y reputación profesional** para redes locales de profesionales y pequeños negocios: reglas claras, consecuencias reales y trazabilidad completa.

### Lo que RUANA no es

- No es una red social ni un marketplace.
- No es un CRM tradicional.
- No prioriza crecimiento rápido ni volumen.

### Lo que RUANA sí es

- **Sistema operativo de confianza** para comunidades profesionales.
- **Memoria y consecuencias**: el comportamiento se refleja en score y estado.
- **Presión positiva**: buen comportamiento se recompensa, el malo se degrada.
- **Orden profesional** en un entorno sin control de calidad.

---

## 2. Problema que resuelve

Hoy las recomendaciones no tienen consecuencias, no hay memoria de errores y la confianza es frágil. **RUANA** introduce: memoria (historial en BD), reglas operativas (score, estados, contactos) y presión positiva (recompensas y penalizaciones automáticas).

---

## 3. Principios de diseño

### Principio rector (no negociable)

> **"El panel no piensa. El motor decide. El panel solo refleja estado."**

El frontend presenta y recoge acciones; el backend y el motor RUANA orquestan, aplican reglas y persisten en SQLite.

### Otros principios

1. **Un aliado = una identidad**: código único, historial ligado al código. Perder el código = perder acceso (no “crear otra cuenta”).
2. **Un código = una historia**: cada código tiene memoria completa; no hay anonimato.
3. **Una base de datos = una verdad**: SQLite como fuente única; persistencia real e histórica.
4. **Backend-first**: el frontend no decide; el backend orquesta y aplica reglas.
5. **Compatibilidad legacy controlada**: se aceptan códigos alfanuméricos (A0001, ALFA01, etc.) además de códigos numéricos de 5 dígitos; los nuevos aliados siempre reciben código numérico.

---

## 4. Arquitectura general

### Capas del sistema

```
┌─────────────────────────────────────────────────────────┐
│  Frontend (HTML/CSS/JS)                                 │  Presenta, recoge acciones
├─────────────────────────────────────────────────────────┤
│  Backend (Flask / web/app.py)                            │  Rutas, validación, orquestación
├─────────────────────────────────────────────────────────┤
│  Core + Motor RUANA (core/, engines/, metrics/, events/) │  Reglas, evaluación, eventos
├─────────────────────────────────────────────────────────┤
│  Persistencia (core/db_manager.py → SQLite)             │  Fuente única de verdad
└─────────────────────────────────────────────────────────┘
```

### Componentes por directorio

| Directorio / archivo | Responsabilidad |
|----------------------|------------------|
| **web/** | Aplicación web: Flask (`app.py`), HTML (index, invite, register, aliado, admin, dashboard), estáticos (CSS/JS). |
| **web/app.py** | Rutas HTTP, validación de entrada (F07), generación de código único, delegación a `DBManager`. |
| **web/run.py** | Punto de entrada para levantar el servidor (Flask en `http://127.0.0.1:5000`). |
| **core/db_manager.py** | Gestión de SQLite: aliados, grupos, solicitudes, contactos RUANA, evaluaciones, score, invitaciones, referidos. |
| **core/orquestador.py** | Ciclos de evaluación: preflight, colector de métricas, motor de evaluación. |
| **core/preflight_validator.py** | Validación pre-operativa (estructura, config, directorios). |
| **engines/motor_evaluacion.py** | Motor RUANA v0.2: evalúa aliados (tasa respuesta/confirmación, meses sin trabajo), persistencia en SQLite, severidad (normal/alerta/crítico). |
| **metrics/collector.py** | Recolector de métricas (por ahora datos de ejemplo para el orquestador). |
| **events/event_bus.py** | Registro de eventos del motor en `logs/eventos_ruana.jsonl` (JSONL). |
| **config/ruana_reglas_v1.json** | Configuración del motor: version, capital, risk_per_trade_pct, **umbral_competencia** (35), **duracion_competencia_dias** (30), **purga_mensual_meses_sin_ganar** (3), **purga_score_bajo_umbral** (40), **apoyo_pct** (15.0, % Apoyo RUANA por trabajo cerrado). |
| **config/oficios_ruana.json** | Catálogo oficial de oficios (lista `oficios`); ~77 oficios. |
| **config/admin_codes.json** | Códigos de administrador y permisos (admin_codes). |

---

## 5. Base de datos (SQLite)

- **Archivo**: `ruana.db`.
- **Ruta**: definida en `core/db_manager.py` como constante `DB_PATH` (por defecto ruta absoluta al proyecto; para portabilidad se puede instanciar `DBManager(db_path="ruta/ruana.db")` con otra ruta).
- **Inicialización**: al instanciar `DBManager` se crean todas las tablas y se ejecutan migraciones si no existen.

### Tablas principales

| Tabla | Descripción |
|-------|-------------|
| **aliados** | id, codigo (único), nombre, marca, oficio, codigo_postal, grupo_id, email, telefono, estado, score, especializaciones, derrotas_competencia, descripcion_servicio, **qr_paypal_path**, **bizum_num** (para notificaciones de Apoyo RUANA), creado_en, actualizado_en. |
| **grupos** | id, nombre (único), codigo_postal (varios grupos por CP, máx. 5), ciudad, provincia, estado (activo \| en_competencia \| disuelto), fecha_creacion. Nombre automático: RUANA-&lt;ID_ALFANUM&gt;-&lt;SUFIJO&gt; (sufijos: PUENTE, FARO, NEXO, RAÍZ, PLAZA, RED, HOGAR, IMPULSO, ORIGEN, ENLACE). |
| **solicitudes** | id, grupo_id, texto, creado_por_codigo, estado (pendiente, contestada, etc.), creado_en. |
| **contactos_ruana** | Flujo de contacto: estado (incl. **en_conversacion**, **chat_agotado**), declaraciones de importe, importe_final, **apoyo_ruana**, comision, **estado_pago**, **pendiente_pago**, comprobante_ruta, **posponer_recordatorio**, **fecha_pospuesto_hasta** (ocultar alerta temporalmente), fechas. Índice **idx_contacto_aliado** en (id, profesional_codigo). |
| **chat_mensajes** | id, contacto_id (FK contactos_ruana), emisor_codigo, receptor_codigo (opcional), texto, creado_en. Chat interno entre solicitante y profesional; máximo 5 mensajes por usuario; vigencia 48 h desde última actividad. Índice idx_chat_mensajes_contacto. |
| **contacto_panel_oculto** | contacto_id, codigo_aliado. Contactos que el aliado ha marcado como "Finalizar chat" y ya no se muestran en contactos abiertos. |
| **score_movimientos** | codigo_aliado, delta, motivo, creado_en. Auditoría y límite ±10 puntos/día por aliado. |
| **contacto_penalizaciones_aplicadas** | contacto_id, tipo (7d, 21d). Evita aplicar dos veces la misma penalización por contacto abierto. |
| **evaluaciones** | codigo_aliado, estado (verde/amarillo/rojo), score, intencion, tasa_respuesta, tasa_confirmacion, meses_sin_trabajo, ciclos_consecutivos, razones, severidad (normal/alerta/critico). |
| **evaluaciones_historico** | Historial de cambios de evaluación por aliado. |
| **invitaciones** | codigo (PK), invitador_aliado_id, usado, creado_en. Para recompensa +3 al invitador cuando se usa la invitación. |
| **referidos** | codigo_referido, codigo_invitador, creado_en. Cuenta “aliados referidos por mí”. |
| **invitaciones_oficio** | id, codigo (único), grupo_id, oficio, aliado_id, estado, fecha_creacion. Invitaciones para cubrir oficios faltantes en un grupo (formato RUANA-{grupo_id}-{OFICIO_NORM}-{4chars}). |
| **eventos_sistema** | id, tipo, descripcion, actor_tipo, actor_codigo, metadata, creado_en. Trazabilidad (incl. tipo **apoyo_generado**). |
| **notificaciones_aliado** | id, aliado_codigo, tipo (ej. apoyo_ruana), titulo, mensaje, metadata (JSON: qr_paypal_path, bizum_num, contacto_id, apoyo_ruana), leida, creado_en. |
| **competencia** | id, grupo_id, oficio, aliado_original_codigo, suplente_codigo, suplente_grupo_anterior_id, fecha_inicio, fecha_fin_prevista, estado (activa \| finalizada), ganador_codigo, creado_en. Competencia temporal por bajo score. |
| **avisos_grupo** | id, grupo_id, tipo, texto, creado_en. Avisos al grupo (ej. “Este mes tenemos X en competencia”). |
| **grupo_oficio_cerrado** | grupo_id, oficio, cerrado_en (PK compuesta). Plaza cerrada por admin (Cerrar Oficio / Abrir Plaza). |
| **migraciones** | id, nombre (único), aplicada_en. Control de migraciones aplicadas una sola vez. |

### Asignación automática de grupo al registrarse

Al registrar un aliado con **código postal** y **oficio**:

1. Se buscan **grupos activos** en ese código postal (datos desde BD).
2. Si existe un grupo que **no tiene** ese oficio → se asigna el aliado a ese grupo (nunca se repite oficio dentro del mismo grupo).
3. Si su oficio ya está en todos los grupos del CP:
   - Si hay **menos de 5 grupos** en el CP → se crea un **nuevo grupo** y se asigna al aliado.
   - Si ya hay **5 grupos** → el registro se rechaza y se devuelve **redirect_to_codigo_postal** (CP adyacente sugerido desde la BD, misma zona por dos primeros dígitos).

Límites: máximo **5 grupos por código postal**; **un oficio principal por grupo** (no repetir). Las especializaciones no ocupan plaza.

### Catálogo oficial de oficios

- **Catálogo predefinido**: ~77 oficios en `config/oficios_ruana.json` (lista `oficios`). API: `GET /api/catalogo/oficios`.
- **Cada aliado elige**: 1 **oficio principal** (obligatorio, del catálogo) y **especializaciones** opcionales (solo del catálogo; no ocupan plaza en el grupo).
- **Oficio fuera de catálogo**: si el oficio principal no está en el catálogo (p. ej. "Otro" con texto libre), el aliado queda en estado **pendiente_validacion**; no se asigna grupo y se requiere **validación manual** por administrador para activar.

### Viabilidad mínima y fusión automática

- **Grupo viable** = mínimo **2 aliados activos**.
- Si un grupo **baja a 1 aliado**:
  1. Se intenta **fusión** con otro grupo activo del mismo CP con **&lt;3 aliados**, solo si **no hay oficios repetidos** entre ambos. El **grupo más antiguo absorbe** (se mueven los aliados del otro al más antiguo y se disuelve el otro).
  2. Si no es posible fusionar: se **reasigna** el aliado a un **grupo compatible** del mismo CP (sin ese oficio) o se **crea un nuevo grupo** y se asigna allí; el grupo que quedó con 1 aliado se marca **disuelto**.
- El **nombre** del grupo disuelto **queda retirado permanentemente** (no se reutiliza).
- Se dispara al actualizar un aliado (cambio de `estado` o `grupo_id`). También existe `procesar_grupos_no_viables()` para revisar todos los grupos activos con 1 aliado.

### Sistema de competencia

- **Cuándo**: cuando el **score** del aliado baja **por debajo del umbral** (config `umbral_competencia`, por defecto 35 en `config/ruana_reglas_v1.json`).
- **Proceso**:
  1. **Selección del suplente**: mismo oficio, mayor score, misma ciudad/provincia (o mismo CP si no hay); prioridad a grupos con **&lt;3 aliados**; luego criterio territorial (mismo CP).
  2. El **suplente entra temporalmente** al grupo (mismo grupo que el aliado en riesgo).
  3. **Durante 1 mes** (`duracion_competencia_dias` en config): ambos reciben solicitudes, ambos generan score; se envía **aviso al grupo**: *"Este mes tenemos &lt;OFICIO&gt; en competencia dentro del grupo."*
  4. **Final**: **mayor score permanece** en el grupo; el otro sale (suplente vuelve a su grupo anterior si pierde).
- **Primera derrota** (el aliado original pierde): **no se elimina el perfil**, **no se desactiva el código**. Se **crea o asigna** a un grupo real (RUANA-XXX), **score se reinicia a 75**. Ese grupo funciona como grupo normal (recibe solicitudes, genera score, regla 1 oficio). Solo las **derrotas en competencia** cuentan (cambios involuntarios por disolución o reasignación no cuentan).
- **Segunda derrota en competencia (expulsión definitiva)**: se **elimina el perfil** del acceso (estado = `expulsado`), se **desactiva el código** (el código ya no da acceso al panel ni vale como invitación). Para volver se **requiere nueva invitación** (registro con otro código de invitación).
- El score individual **sigue visible** durante competencia activa; las APIs exponen `competencia_activa: true` como indicador.
- **Finalizar vencidas**: `POST /api/competencia/finalizar-vencidas` (para cron o ejecución periódica).

---

## 6. Score RUANA y estado del aliado

### Score (0–100)

- Almacenado en `aliados.score`.
- **Límite diario**: máximo ±10 puntos por aliado por día (suma de `score_movimientos` del día).
- **Cálculo de estado** (derivado, no almacenado como texto en `aliados`): `DBManager.score_a_estado(score)`:
  - **PRIORITARIO**: score ≥ 85  
  - **ESTABLE**: 60 ≤ score < 85  
  - **EN RIESGO**: 35 ≤ score < 60  
  - **COMPETENCIA**: score < 35  

### Eventos que modifican el score (ejemplos)

- Contacto cerrado con importes coincidentes: +8 (solicitante y profesional).
- Declaración contradictoria (importe en disputa): -5 cada uno.
- Contacto no concretado: -2 cada uno.
- Contacto abierto 7 días: -2 (una vez por contacto).
- Contacto abierto 21 días: -5 (una vez por contacto).
- Aliado referido se registra con código de invitación válido: +3 al invitador.

Las penalizaciones por contactos abiertos se aplican al solicitar datos del aliado (p. ej. `GET /api/aliado/datos`) mediante `aplicar_penalizaciones_contactos_abiertos()`.

---

## 7. Flujo de contactos RUANA

Un **contacto** une a un solicitante (aliado que pide servicio) y un profesional (aliado que lo ofrece).

### Estados del contacto

- **iniciado** → **aceptado** (profesional acepta; se habilita contacto externo).
- **aceptado** o **iniciado** → **trabajo_en_progreso**.
- **trabajo_en_progreso** → **trabajo_cerrado** (cuando ambos declaran el mismo importe) o **no_concretado** o **importe_en_disputa** (importes distintos).

### Chat interno y alerta de contactos abiertos

- **Chat**: entre solicitante y profesional del contacto. Tabla `chat_mensajes`; vigencia **48 h** desde última actividad (último mensaje o aceptación); máximo **5 mensajes por usuario**; al llegar ambos al límite el contacto pasa a `chat_agotado` (solo se permite cerrar). APIs: `GET /api/chat/mensajes`, `POST /api/chat/enviar`; alias legacy `GET /api/chat_mensajes`, `POST /api/chat_enviar`; por contacto `GET/POST /api/contactos/<id>/mensajes`.
- **Alerta en panel**: `GET /api/contactos/abiertos/<codigo>` devuelve contactos que deben mostrarse como aviso. Se excluyen si `posponer_recordatorio = 1` y `fecha_pospuesto_hasta` > now ("Sigue en conversación") o si el aliado usó "Finalizar chat" (`contacto_panel_oculto`). Acciones: `POST /api/contactos/<id>/en-conversacion`, `POST /api/contactos/<id>/finalizar-chat`. Detalle en `docs/LOGICA_CHAT_Y_ALERTA.md`.

### Declaración de importe

- Cada parte declara su importe por separado (`registrar_importe_contacto`).
- Si **ambos importes coinciden**: estado → `trabajo_cerrado`, se guarda `importe_final`, **apoyo_ruana** (porcentaje desde `config/ruana_reglas_v1.json` → **apoyo_pct**, por defecto 15%), `pendiente_pago = 1`, evento **apoyo_generado** y notificación al aliado (profesional) con mensaje y, si existen, QR PayPal (`aliados.qr_paypal_path`) o número Bizum (`aliados.bizum_num`). El aliado puede enviar comprobante desde su panel para validación en admin.
- Si **no coinciden**: estado → `importe_en_disputa`; no se cierra ni se genera apoyo.

### API de contactos (resumen)

- `POST /api/contactos`: crear contacto (solicitante_codigo, profesional_codigo, servicio).
- `POST /api/contactos/<id>/aceptar`: profesional acepta.
- `POST /api/contactos/<id>/trabajo-en-progreso`: marcar trabajo en progreso.
- `POST /api/contactos/<id>/no-concretado`: cerrar sin concretar.
- `POST /api/contactos/<id>/declarar-importe`: declarar importe (parte, importe, moneda, usuario).
- `GET /api/contactos/<id>`: resumen seguro (sin importes individuales de cada parte).
- `GET /api/contactos/abiertos/<codigo_aliado>`: contactos abiertos del aliado (excluye posponer_recordatorio activo y contacto_panel_oculto).
- `GET /api/contactos/metricas`: agregados (abiertos, no resueltos, en disputa, disputa prolongada).
- `POST /api/contactos/<id>/en-conversacion`: marcar "Sigue en conversación" (posponer_recordatorio=1, fecha_pospuesto_hasta; la alerta se oculta hasta esa fecha).
- `POST /api/contactos/<id>/finalizar-chat`: ocultar contacto del panel del aliado (contacto_panel_oculto).

---

## 8. Invitaciones y referidos

### Formatos de código de invitación

1. **Código de aliado** (acceso como invitado por otro aliado): formato 5 dígitos (`12345`), `A0001` o alfanumérico tipo `ALFA01`/`BETA02`. El invitado introduce el código en la pantalla de invitación (`/` o `/invite`) y se registra en `register.html` con `codigo_invitacion`. Debe ser un aliado existente en estado `activo` o `pendiente_completar`; si está `expulsado`, el código se rechaza y se indica que se requiere nueva invitación.
2. **Invitación por oficio** (para cubrir oficios faltantes en un grupo): formato `RUANA-{grupo_id}-{OFICIO_NORM}-{4chars}` (ej. `RUANA-1-ELECTRICIDAD-A1B2`). Se valida contra la tabla `invitaciones_oficio`; cada código es de un solo uso.

### Validación y creación

- **Validación**: `GET /api/invitaciones/validar/<codigo>`, `GET /api/invitaciones/validar?codigo=XXX` o `GET /api/validar-invitacion?codigo=XXX` comprueban el código (aliado o RUANA-oficio) y devuelven `invitacion` con zona, grupo, oficio, etc. según el tipo.
- **Crear invitación (aliado)**: `POST /api/invitaciones/crear` genera un código ligado al invitador; la tabla `invitaciones` vincula código con `invitador_aliado_id`.
- **Generar invitación por oficio**: `POST /api/generar-invitacion` y `POST /api/aliado/generar-invitacion` generan códigos para invitar a un oficio faltante en el grupo (formato RUANA-…).
- **Al registrarse con código de invitación**: si el registro incluye `codigo_invitacion` y existe en `invitaciones` sin usar, se llama a `consumir_invitacion_y_recompensar`: +3 al invitador, se inserta en `referidos` y se marca la invitación como usada.

---

## 9. Motor de evaluación (engines/motor_evaluacion.py)

- **Entrada**: diccionario de métricas por aliado (`tasa_respuesta`, `tasa_confirmacion`, `meses_sin_trabajo`, etc.).
- **Reglas**:
  - tasa_respuesta ≥ 0.70 → 1 filtro OK.
  - tasa_confirmacion ≥ 0.80 → 1 filtro OK.
  - meses_sin_trabajo ≤ 6 → 1 filtro OK.
- **Decisión**:
  - 3 OK → estado **verde**, intención **mantener**.
  - 2 OK → estado **amarillo**, intención **vigilar**.
  - ≤1 OK → estado **rojo**, intención **evaluar_suplencia**.
- **Score del motor**: (filtros_ok / 3) * 100.
- **Persistencia**: se guarda en `evaluaciones` (y histórico) vía `DBManager.guardar_evaluacion`.
- **Severidad**: según ciclos consecutivos en el mismo estado (normal / alerta / crítico). Ej.: rojo ≥2 ciclos o amarillo ≥6 ciclos → crítico.

El orquestador (`core/orquestador.py`) ejecuta preflight, recolecta métricas (`metrics/collector.py`) y llama al motor; los eventos se registran en `events/event_bus.py` (archivo `logs/eventos_ruana.jsonl`). En la implementación actual, el **MetricsCollector** devuelve métricas de ejemplo para un aliado "A1"; la integración con datos reales (tasa respuesta/confirmación, meses sin trabajo desde BD) es futura. Al ejecutar `python core/orquestador.py` se ejecutan 5 ciclos de demo con pausa de 2 s entre ellos.

---

## 10. Referencia de API (Flask)

Base URL: `http://127.0.0.1:5000` (o el host/puerto configurado).

### Páginas (HTML)

| Ruta | Archivo | Descripción |
|------|---------|-------------|
| `/`, `/dashboard` | index.html | Pantalla de invitación (introducir código); misma entrada que dashboard. |
| `/invite`, `/invite.html` | invite.html | Introducir código de invitación (alternativa a `/`). |
| `/register`, `/register.html` | register.html | Registro de aliado (con/sin invitación). |
| `/aliado`, `/aliado.html` | aliado.html | Panel del aliado (?codigo=XXX). |
| `/panel`, `/private-panel`, `/private-panel.html` | aliado.html / private-panel.html | Panel aliado (legacy/alternativo). |
| `/admin` | admin.html | Panel administrador (login por código). Bypass solo en desarrollo vía variables de entorno (S-02). |
| `/dashboard.html` | dashboard.html | Dashboard alternativo. |
| `/test-panel`, `/diagnostico-panel`, `/test-simple`, `/panel-test` | (raíz proyecto) | Páginas de desarrollo/diagnóstico. |
| `/static/<path>` | web/static/ | CSS (styles.css, config.css), JS (dashboard.js). |

### Aliados

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/aliados` | Lista todos los aliados |
| GET | `/api/aliados/<id>` | Aliado por ID numérico |
| GET | `/api/aliados/por-codigo/<codigo>` | Aliado por código |
| GET | `/api/aliados/obtener-por-codigo/<codigo>` | Aliado + solicitudes del grupo (formato código: 5 dígitos, A0001, ALFA01) |
| GET / POST | `/api/aliado/datos` | GET `?codigo=XXX` o POST `{codigo: "XXX"}`: datos completos del aliado para el panel (aplica penalizaciones por contactos abiertos, estado_ruana, referidos, etc.) |
| POST | `/api/aliados/registrar` | Registrar aliado (nombre, email, telefono obligatorios; opcional codigo_invitacion) |
| PUT | `/api/aliados/<codigo>` | Actualizar aliado (incl. qr_paypal_path, bizum_num para Apoyo RUANA) |
| GET | `/api/aliados/<codigo>/notificaciones` | Notificaciones del aliado (Apoyo RUANA: mensaje, QR/Bizum en metadata) |
| POST | `/api/aliados/<codigo>/notificaciones/<id>/leida` | Marcar notificación como leída |
| GET | `/api/aliados/verificar-codigo/<codigo>` | Verificar si existe el código |
| GET | `/api/aliados/listar?codigo_postal=XXX` | Listar aliados (opcional filtro por código postal) |
| POST | `/api/aliado/pausar` | Pausar aliado (body: `codigo`). Requiere admin con permiso escritura. |

### Solicitudes

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/solicitudes/grupo?codigo=XXX` | Solicitudes del grupo del aliado (por código de aliado) |

### Contactos RUANA

Ver sección 7; resumen de endpoints clave:

- **Contactos (núcleo)**: `POST /api/contactos`, `POST /api/contactos/<id>/aceptar`, `POST /api/contactos/<id>/trabajo-en-progreso`, `POST /api/contactos/<id>/no-concretado`, `POST /api/contactos/<id>/declarar-importe`, `GET /api/contactos/<id>`, `GET /api/contactos/abiertos/<codigo>`, `GET /api/contactos/metricas`.
- **Chat entre aliados (contacto activo)**:
  - Aliado/profesional: `GET /api/chat/mensajes`, `POST /api/chat/enviar` (alias simples) y `GET /api/contactos/<id>/mensajes`, `POST /api/contactos/<id>/mensajes`.
  - Alias legacy: `GET /api/chat_mensajes`, `POST /api/chat_enviar` (mantienen mismo modelo de datos).
  - Todas las variantes respetan permisos: solo solicitante y profesional del contacto pueden leer/enviar.
- **Visión admin de conversaciones**:
  - Resumen de contactos con chat: `GET /api/admin/conversations`, `GET /api/admin/contactos-conversaciones`.
  - Chat bruto paginado: `GET /api/admin/chat-messages`.
  - Conversaciones completas agregadas por contacto: `GET /api/admin/chats`.
  - Mensajes de un contacto concreto: `GET /api/admin/contactos/<id>/mensajes`.
- **Conflictos de pago**:
  - Panel admin: `GET /api/admin/payment-conflicts`, `GET /api/admin/payment-conflicts/<id>`, `POST /api/admin/payment-conflicts/<id>/resolver`.
  - Atajo admin por contacto: `POST /api/admin/conflictos-pago/<contacto_id>/resolver`.
  - Aliado: `GET /api/conflictos/por-trabajo/<trabajo_id>?codigo=XXX`, `POST /api/conflictos/<id>/subir-prueba` (subida de archivo de prueba).

### Competencia y purga

- `POST /api/competencia/finalizar-vencidas`: finaliza competencias cuya fecha ha pasado (mayor score permanece). Para cron o ejecución periódica.
- `POST /api/purga/mensual`: purga mensual de calidad (finaliza vencidas + aplica reglas de pool; aliados en pool sin victoria en N meses o score bajo → expulsión temporal). Para cron mensual.

**Cron (primer día de cada mes):** ejecutar sin depender del servidor web con `scripts/purga_mensual.py`. El script usa `get_db()` y por tanto la misma `DB_PATH` definida en `core/db_manager.py`; asegurarse de que la ruta del proyecto (o `DB_PATH`) sea correcta en el entorno del cron. Ejemplo (ajustar RUANA_DIR):
```bash
0 2 1 * * /usr/bin/env python3 /ruta/a/RUANA/scripts/purga_mensual.py >> /ruta/a/RUANA/logs/purga_mensual.log 2>&1
```
Plantilla en `scripts/cron_purga_mensual.txt`; instalar con `crontab -e` y pegar la línea.

### Evaluaciones (motor RUANA)

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/evaluaciones/<codigo_aliado>` | Evaluación actual |
| GET | `/api/evaluaciones?estado=verde` | Listar evaluaciones (filtro opcional) |
| GET | `/api/evaluaciones/<codigo>/historico` | Histórico de evaluaciones del aliado |
| GET | `/api/evaluaciones/estadisticas` | Estadísticas globales |


### Invitaciones (validación y creación)

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/validar-invitacion?codigo=XXX` | Valida código de invitación (query) |
| GET | `/api/invitaciones/validar?codigo=XXX` | Valida código (alias) |
| GET | `/api/invitaciones/validar/<codigo>` | Valida código (path) |
| POST | `/api/invitaciones/crear` | Crear invitación (body según implementación) |
| POST | `/api/generar-invitacion`, `/api/aliado/generar-invitacion` | Generar invitación por oficio (grupo + oficio faltante) |

### Filtros y estadísticas

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/catalogo/oficios` | Catálogo oficial de oficios RUANA (para registro: oficio principal + especializaciones) |
| GET | `/api/filtros` | Zonas, oficios, estados para filtros |
| GET | `/api/stats` | Estadísticas (total aliados, activos, evaluaciones, contactos) |
| GET | `/api/health` | Estado del servidor |
| GET | `/api/movimiento-24h` | Movimiento de score en las últimas 24 h (agregado) |
| GET | `/api/movimiento-24h-horas` | Movimiento de score por hora |
| GET | `/api/metricas-salud` | Métricas de salud del sistema |
| GET | `/api/eventos-recientes` | Últimos eventos del sistema (eventos_sistema) |

### Admin

| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/api/admin/validar` | Validación de código admin (config/admin_codes.json). Body: `{codigo: "ADMIN001"}`. Devuelve `permisos`, `token` (JWT), `expires_at`. La UI puede guardar el token y enviarlo en `Authorization: Bearer <token>` para peticiones posteriores. |
| POST | `/api/admin/logout` | Cierra sesión admin (limpia sesión en servidor). |
| GET | `/api/admin/me` | Devuelve los permisos efectivos del admin actual (sesión o JWT). Útil para inicializar el panel sin revalidar. |
| POST | `/api/admin/forzar-suplencia` | Forzar suplencia (body: grupo_id, oficio, aliado_original_codigo, suplente_codigo). Requiere admin. |
| GET | `/api/admin/aliados-pendientes` | Lista aliados con estado pendiente_validacion. Requiere admin. |
| POST | `/api/admin/activar-aliado` | Activar aliado pendiente (body: codigo). Requiere permiso escritura. |
| POST | `/api/admin/cerrar-oficio` | Cerrar oficio en grupo (body: grupo_id, oficio). Requiere permiso escritura. |
| POST | `/api/admin/abrir-plaza` | Abrir plaza de oficio en grupo (body: grupo_id, oficio). Requiere admin. |
| POST | `/api/admin/generar-reporte` | Genera resumen (aliados, contactos, grupos, competencias, plazas cerradas). Requiere admin. |
| POST | `/api/admin/cambiar-reglas` | Cambiar regla (body: clave, valor). Claves: umbral_competencia, duracion_competencia_dias, purga_mensual_meses_sin_ganar, purga_score_bajo_umbral. Requiere permiso escritura. |
| GET | `/api/admin/stats-24h` | Movimiento del sistema en las últimas 24h (solicitudes, invitaciones, top invitadores) en una sola respuesta. |
| GET | `/api/admin/health-metrics` | Métricas de salud del sistema (ratios solicitud→invitación, invitación→registro, oficios saturados/disponibles, zona de mayor demanda, tasa de retención). |
| GET | `/api/admin/invitaciones-recientes` | Últimas invitaciones generadas para el panel admin (histórico reciente). |
| GET | `/api/admin/dashboard-summary` | Resumen global del dashboard (usuarios totales/activos, suplentes, en riesgo, solicitudes activas, grupos, estado_sistema). |
| GET | `/api/admin/solicitudes` | Lista todas las solicitudes (pendientes y atendidas) para análisis administrativo. |
| GET | `/api/admin/conversations` / `/api/admin/contactos-conversaciones` | Lista contactos recientes con chat y métricas básicas (mensajes, importe, estado, fechas). |
| GET | `/api/admin/chat-messages` | Registro bruto paginado de mensajes de chat (para auditoría). |
| GET | `/api/admin/chats` | Conversaciones agregadas por contacto (mensajes + resumen por conversación). |
| GET | `/api/admin/contactos/<id>/mensajes` | Mensajes de chat completos de un contacto concreto (incluye remitente lógico). |
| GET | `/api/admin/payment-conflicts` / `/api/admin/conflictos-pago` | Lista conflictos de pago abiertos o históricos. |
| GET | `/api/admin/payment-conflicts/<id>` | Detalle ampliado de un conflicto de pago. |
| POST | `/api/admin/payment-conflicts/<id>/resolver` | Resuelve un conflicto de pago (decisión + comentario obligatorio). |
| POST | `/api/admin/conflictos-pago/<contacto_id>/resolver` | Atajo para resolver conflicto de pago asociado a un contacto concreto. |
| GET | `/api/admin/pagos-apoyo` | Lista contactos con trabajo cerrado y Apoyo RUANA generado (para confirmar pagos manuales). |
| GET | `/api/admin/pagos-en-revision` | Lista contactos con estado_pago = en_revision (comprobante subido, pendiente de aprobar/rechazar). |
| POST | `/api/admin/contactos/<id>/estado-pago` | Actualiza estado_pago del contacto (body: `estado_pago`: `en_revision` \| `pagado` \| `rechazado`). Requiere permiso escritura. |

**Permisos (config/admin_codes.json):**
- **Código de prueba solo lectura:** `0000` → `permisos: ["leer"]`: puede ver todo el panel pero las acciones (Pausar, Forzar Suplencia, etc.) devuelven 403 y los botones se deshabilitan.
- **Admin completo:** `ADMIN001` → `permisos: ["leer","escribir","eliminar","configurar"]`: acceso total.

**Autenticación:** Tras `POST /api/admin/validar` el servidor devuelve un JWT en `token` y guarda sesión (cookie). Las rutas protegidas aceptan sesión o cabecera `Authorization: Bearer <token>`. El endpoint `/api/admin/me` permite recuperar los permisos actuales sin reenviar el código de admin (usa sesión o JWT).

**Sesión expirada:** Variable de entorno `RUANA_ADMIN_SESSION_EXPIRES` (segundos; por defecto 3600). Si la sesión supera ese tiempo, las peticiones protegidas devuelven 401 y el panel debe mostrar de nuevo el modal de login.

**Sin bypass por URL (S-02, S-03):** El parámetro `?bypass=` no tiene ningún efecto. El acceso admin es únicamente mediante el formulario de login en `/admin` y validación con códigos definidos en `config/admin_codes.json` (POST `/api/admin/validar`).

---

## 11. Validaciones de negocio (registro F07)

- **nombre**: obligatorio, mínimo 3 caracteres.
- **email**: obligatorio, debe contener `@` y dominio con `.`.
- **telefono**: obligatorio, al menos 7 dígitos (solo dígitos).
- **Unicidad**: email y teléfono únicos en `aliados` (mensajes específicos en español).
- **Código nuevo**: generado por el backend (5 dígitos numéricos). Códigos legacy (A0001, ALFA01, etc.) se aceptan para acceso pero no se generan en registro.

---

## 12. Flujo de usuario (resumido)

1. **Entrada**: Usuario va a `invite.html`, introduce código de invitación (código de un aliado existente o código generado por invitación).
2. **Validación**: Frontend llama `GET /api/invitaciones/validar/<codigo>` y guarda en sessionStorage (ruana_invite_*).
3. **Registro**: En `register.html` envía `POST /api/aliados/registrar` con nombre, email, telefono y opcional codigo_invitacion. Recibe código de 5 dígitos.
4. **Panel**: Redirección a `aliado.html?codigo=XXX`. Si no hay datos en sessionStorage, se llama `GET /api/aliado/datos?codigo=XXX` y se rellenan; el panel muestra perfil, estado RUANA, métricas, solicitudes del grupo, contactos.
5. **Cerrar sesión**: Limpieza de sessionStorage (ruana_*) y redirección a invite.

---

## 13. Cómo ejecutar el sistema

### Requisitos

- Python 3.8+ (recomendado 3.11+).
- Dependencias: `pip install -r web/requirements.txt` (Flask, Flask-Cors, Werkzeug).

### Levantar la web

Desde el directorio `web/`:

```bash
cd web
pip install -r requirements.txt   # si aún no está instalado
python run.py
```

O desde la raíz del proyecto (el path de imports en `app.py` añade el parent al `sys.path`):

```bash
python web/run.py
```

Servidor: `http://127.0.0.1:5000` (host `127.0.0.1`, sin reloader en `run.py`). La primera petición que use `DBManager` creará `ruana.db` en la ruta definida por `DB_PATH` en `core/db_manager.py` si no existe.

### Datos semilla

```bash
python scripts/seed_aliados.py
```

Inserta 4 aliados con códigos **ALFA01**, **BETA02**, **GAMA03**, **DELTA04** (idempotente; si ya existen, no duplica). Usa `DBManager.crear_aliado_seed()` (acepta códigos alfanuméricos).

### Orquestador (motor en ciclo)

```bash
python core/orquestador.py
```

Ejecuta preflight, luego varios ciclos de recolección de métricas y evaluación con el motor (demo). Los logs van a `logs/`.

---

## 14. Estructura del proyecto (resumida)

```
RUANA/
├── README.md                    # Este documento (documento oficial único)
├── ruana.db                    # Base SQLite (creada al usar DBManager; ruta en core/db_manager.py)
├── config/
│   ├── admin_codes.json        # Códigos de admin y permisos
│   ├── oficios_ruana.json      # Catálogo oficial de oficios
│   └── ruana_reglas_v1.json   # Reglas del motor (umbral_competencia, purga, etc.)
├── core/
│   ├── db_manager.py           # Gestor SQLite (fuente única de verdad; get_db() singleton)
│   ├── orquestador.py          # Ciclos de evaluación (preflight + collector + motor)
│   └── preflight_validator.py  # Validación pre-operativa (estructura, config, directorios)
├── engines/
│   └── motor_evaluacion.py     # Motor RUANA v0.2 (verde/amarillo/rojo, severidad)
├── events/
│   └── event_bus.py            # Registro de eventos en logs/eventos_ruana.jsonl (JSONL)
├── logs/                        # Logs (orquestador, preflight) y eventos_ruana.jsonl
├── metrics/
│   └── collector.py            # Recolector de métricas (por ahora datos de ejemplo por aliado)
├── scripts/
│   ├── seed_aliados.py         # Inserta ALFA01, BETA02, GAMA03, DELTA04 (idempotente)
│   ├── purga_mensual.py        # Purga mensual (finalizar competencias + pool); para cron
│   └── cron_purga_mensual.txt  # Plantilla crontab (primer día del mes, 02:00)
├── utils/
│   └── logger.py               # setup_logger(name, log_dir) para orquestador y preflight
└── web/
    ├── app.py                   # Flask: rutas HTML, API (aliados, contactos, admin, etc.)
    ├── run.py                   # Punto de entrada: lanza servidor en 127.0.0.1:5000
    ├── requirements.txt         # Flask, Flask-Cors, Werkzeug, PyJWT
    ├── index.html               # Pantalla de invitación (código de ingreso)
    ├── invite.html              # Invitación (alternativa)
    ├── register.html            # Registro de aliado
    ├── aliado.html              # Panel del aliado
    ├── admin.html               # Panel administrador
    ├── dashboard.html           # Dashboard alternativo
    ├── private-panel.html       # Panel privado (legacy)
    ├── private-panel-new.html
    ├── VERIFICACION_FLUJO.html  # Verificación de flujo
    └── static/
        ├── css/
        │   ├── styles.css
        │   └── config.css
        └── js/
            └── dashboard.js
```

Nota: Otros directorios que pueden existir en el repo (executors, models, risk, state, tests, core/api_server.py) son stubs o legacy; el flujo principal está en `web/`, `core/db_manager.py`, `core/orquestador.py`, `engines/motor_evaluacion.py`, `metrics/collector.py` y `events/event_bus.py`.

---

## 15. Límites y riesgos

- **Seguridad**: Sin SSL ni autenticación fuerte en la configuración por defecto; no usar en producción abierta sin endurecer. Secret key de Flask y JWT en código; en producción usar variables de entorno.
- **Escalado**: SQLite adecuado para comunidades pequeñas/medianas; no para alto concurrencia masiva.
- **Datos**: Historial completo y trazable; considerar cumplimiento (p. ej. GDPR) si se usan datos personales en producción.
- **Motor**: Reglas de evaluación y severidad implementadas; métricas reales (tasa respuesta/confirmación, meses sin trabajo) pueden venir de integraciones futuras; el collector actual devuelve datos de ejemplo.
- **Ruta de la BD**: `DB_PATH` en `core/db_manager.py` está fijada a una ruta absoluta del sistema; para desplegar en otro equipo, cambiar esa constante o instanciar `DBManager(db_path="...")` donde se use.

---

## 16. Versión y estado

- **Proyecto**: RUANA (Red Unida de Apoyo entre Negocios Aliados).
- **Versión**: 0.9 (pre-MVP avanzado).
- **Estado**: Desarrollo activo. Backend con SQLite, API Flask, panel aliado, registro, invitaciones, contactos RUANA, **chat interno** (48 h vigencia, 5 mensajes/usuario) y **alerta de contactos abiertos** (posponer/finalizar chat) operativos. Score y motor de evaluación, dashboard y admin leen de la API real.

---

**Fin del documento oficial.**
