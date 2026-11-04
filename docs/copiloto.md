# Copiloto RUANA — asistente del aliado

Asistente que vive dentro del panel del aliado (`/aliado`). Explica la app, dice
qué conviene hacer con el score, ayuda a invitar al oficio que falta y guía el
cierre de encargos. Habla con datos de la cuenta, no con generalidades.

| Campo | Valor |
|-------|-------|
| Punto de entrada | Botón flotante «Copiloto», en `/aliado` (encima del de soporte) y en `/admin` |
| Backend | `core/services/copiloto_*.py` + `web/blueprints/copiloto_bp.py` |
| Frontend | `web/static/js/aliado-copiloto.js` y `admin-copiloto.js` + `web/static/css/aliado-copiloto.css` |
| Tests | `RUANA/tests/test_copiloto.py` |
| Estado | Operativo. La IA generativa es opcional y está apagada por defecto |

## Dos capas, un producto

1. **Motor determinista** (siempre activo). Construye el contexto real del
   aliado desde la BD (score, banda, movimientos, grupo, oficios que faltan,
   recompensas restantes, contactos abiertos, perfil, demanda de la zona),
   clasifica la intención del mensaje y responde. Gratis, instantáneo y exacto.
2. **Modelo de lenguaje** (opcional). Recibe ese contexto y las reglas del
   score, y reescribe la respuesta con lenguaje natural. **Solo redacta.**

Si el modelo falla, tarda o escribe una cifra que no está en el contexto, se
devuelve la respuesta determinista. El aliado nunca ve un error ni un número
inventado.

## Qué hace

| Capacidad | Cómo se nota |
|-----------|--------------|
| Guía de la app | Responde cómo funciona y lleva al sitio: abre el perfil, el código de invitación o el centro de comunicación |
| Mentor de score | Traduce las reglas a «esto te suma, esto te resta», con la distancia real al siguiente estado |
| Captador | Detecta el oficio que falta en el grupo y que la zona está pidiendo, y redacta la invitación para esa persona |
| Cierre de encargos | Dice qué falta para cerrar (campos de la negociación, importe, comprobante) |
| Jugadas del día | 1-3 tarjetas ordenadas por urgencia, cada una con un botón que ejecuta la acción |

## Endpoints

| Ruta | Uso |
|------|-----|
| `GET /api/aliado/copiloto/estado` | Saludo, jugadas, sugerencias y si hay IA |
| `GET /api/aliado/copiloto/jugadas` | Solo las jugadas |
| `POST /api/aliado/copiloto/mensaje` | Un turno de conversación |
| `POST /api/aliado/copiloto/redactar` | Invitación o derivación lista para copiar |
| `GET /api/aliado/copiloto/capacidades` | Modo IA o asistente para la sesión |
| `GET /api/admin/copiloto/estado` | Red: saludo, jugadas del admin y modo IA |
| `POST /api/admin/copiloto/mensaje` | Un turno de conversación con el administrador |

Todas exigen sesión de aliado (`@require_aliado`). El código sale de la sesión,
nunca del cuerpo de la petición.

## Activar la IA

Sin configurar nada, el copiloto ya funciona en modo determinista. Para que el
modelo reescriba las respuestas:

```bash
RUANA_AI_ENABLED=1
RUANA_AI_PROVIDER=deepseek        # o openai, groq, openrouter, anthropic, ollama
RUANA_AI_API_KEY=...
RUANA_AI_MODEL=deepseek-chat
```

`RUANA_AI_PROVIDER=openai_compatible` + `RUANA_AI_BASE_URL` sirve para cualquier
servidor compatible con la API de chat de OpenAI (Ollama, LM Studio, vLLM).

Cuando el modelo está activo, la cabecera del panel lo muestra («IA conectada ·
modelo») y aparece el contador de mensajes del día.

### DeepSeek en producción (Cloud Run)

La clave **no va en el repositorio ni en el workflow**. Se guarda en Secret
Manager y el servicio la recibe como secreto:

```bash
# 1. Crear el secreto (una sola vez)
printf '%s' 'sk-...' | gcloud secrets create ruana-deepseek-api-key \
  --data-file=- --replication-policy=automatic

# 2. Dar acceso a la cuenta de servicio de Cloud Run
gcloud secrets add-iam-policy-binding ruana-deepseek-api-key \
  --member="serviceAccount:<SERVICE_ACCOUNT_DE_CLOUD_RUN>" \
  --role="roles/secretmanager.secretAccessor"
```

Después, en `.github/workflows/deploy-firebase.yml`:

- añadir a `--set-env-vars`:
  `RUANA_AI_ENABLED=1,RUANA_AI_PROVIDER=deepseek,RUANA_AI_MODEL=deepseek-chat`
- añadir a `--set-secrets`:
  `RUANA_AI_API_KEY=ruana-deepseek-api-key:latest`

Sin los dos cambios el despliegue sigue funcionando igual, en modo
determinista. **Si se añade la referencia al secreto antes de crearlo, el
despliegue falla**, así que primero el secreto y luego el workflow.

> Recomendación: usar una clave propia del proyecto RUANA, no una compartida con
> otro producto. Así el gasto y la revocación quedan aislados.

### Coste

El modelo solo se llama en `POST /api/aliado/copiloto/mensaje` y en
`POST /api/aliado/copiloto/redactar`. El resto del copiloto (saludo, jugadas,
abrir la invitación) no gasta tokens. `RUANA_AI_CUOTA_DIARIA` limita los
mensajes por aliado y día; el contador vive en el proceso, así que con N workers
de gunicorn el tope efectivo es N × la cuota. Sirve para proteger la factura,
no como contabilidad exacta.

## Guardarraíles

- **El LLM no calcula nada.** Todas las cifras vienen del contexto que arma
  `copiloto_contexto.py` a partir de la BD.
- **Validador de cifras.** `copiloto_service.validar_cifras` compara los números
  del texto con los del contexto y de la tabla de reglas. Si aparece uno que no
  está, la respuesta se descarta y se usa la determinista.
- **No promete trabajo, ingresos ni puntos.** Solo describe la regla («según las
  reglas, +5»).
- **No revela datos de otros aliados.** Al modelo se le pasa oficio y CP, no
  nombres, teléfonos ni códigos de terceros.
- **No ejecuta escrituras.** Abre modales y prerrellena; confirmar es del aliado.
- **Cuota por aliado y día** (`RUANA_AI_CUOTA_DIARIA`) con contador en proceso.
  Es aproximada con varios workers de gunicorn: protege la factura, no es
  contabilidad.
- **Fail-open.** Timeout de `RUANA_AI_TIMEOUT` segundos y caída al motor
  determinista.

## Añadir una respuesta nueva

1. Añade la intención y sus patrones en `copiloto_conocimiento.py` (`_INTENCIONES`).
2. Añade su respuesta en `copiloto_service._respuesta_determinista`.
3. Si lleva acción, devuélvela en el segundo elemento de la tupla (`nav`,
   `invitar`, `soporte`, `copiar`).
4. Añade el caso a `RUANA/tests/test_copiloto.py`.

Las respuestas deterministas son la red de seguridad del producto: el copiloto
tiene que ser útil con el modelo apagado.


---

# Copiloto del administrador

El mismo panel, con otro contexto. En `/admin` las preguntas son sobre la red,
no sobre el score de una persona.

## Qué mira

| Bloque | Fuente |
|--------|--------|
| Red | `admin_dashboard_service.build_dashboard_summary` (aliados, grupos, riesgo, espera) |
| Tráfico 24 h | `admin_service.obtener_stats_24h_panel` (solicitudes, invitaciones, top invitadores) |
| Salud | `admin_service.obtener_metricas_salud` (ratios, retención, zona con más demanda) |
| Encargos | `admin_service.obtener_metricas_contactos` (abiertos, en disputa) |
| Altas | `aliado_service.listar_aliados_pendiente_validacion` |
| Soporte | `admin_service.listar_conversaciones_soporte_admin` (sin leer / abiertas) |
| Conflictos | `pago_service.listar_payment_conflicts_admin` |

Cada bloque va en su propio `try`. Si uno falla (por ejemplo, una métrica escrita
contra SQLite que no corre en Postgres), ese bloque queda en `None` y **no se
muestra un 0**: el copiloto dice que no tiene el dato. Un cero inventado es peor
que un «no lo sé».

## Qué ofrece

- **Jugadas del admin**: soporte sin responder, conflictos de pago abiertos,
  altas por validar, aliados en riesgo, red parada 24 h, plazas en espera.
- **Navegación**: cada jugada lleva a la sección real del panel
  (`data-nav-target`, p. ej. `centro-comunicacion`, `pendientes`, `conflictos`).
- **Respuestas** sobre resumen, soporte, conflictos, altas, riesgo, encargos,
  crecimiento, territorio y salud.

## Añadir una respuesta

Igual que en el del aliado: intención en `_INTENCIONES`, texto en
`responder_determinista`, acción `{"tipo": "nav_admin", "destino": "<sección>"}`
y su test en `RUANA/tests/test_copiloto.py`.
