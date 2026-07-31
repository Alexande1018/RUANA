# Hito 2A - Seguridad y permisos iniciales

Fecha: 2026-05-22
Estado: Diseno aprobado para revision

## Contexto

`ROADMAP.md` marca como activo el Hito 2: cierre de superficie critica de seguridad y permisos. La auditoria base identifica como primer riesgo critico varios endpoints publicos que modifican estado de negocio sin autenticacion.

Este subhito acota el primer corte operativo del Hito 2 para reducir riesgo sin mezclar todavia cambios de PII, chat legacy o permisos admin mas amplios.

## Objetivo

Bloquear modificaciones de negocio desde endpoints publicos y dejar pruebas reproducibles que demuestren que las rutas criticas requieren identidad adecuada.

## Alcance

El Hito 2A cubre:

- Crear una suite minima de tests de permisos para Flask.
- Proteger `POST /api/invitaciones/crear` con sesion de aliado.
- Proteger `POST /api/competencia/finalizar-vencidas` con admin de escritura.
- Proteger `POST /api/purga/mensual` con admin de escritura.
- Verificar que las rutas no ejecutan acciones de negocio sin credenciales validas.

Queda fuera de este subhito:

- Lectura publica de PII en endpoints de aliados.
- Endpoints legacy de chat.
- Validacion de pertenencia en contactos, chat e importes.
- Conversion de cron HTTP a token interno o script no HTTP.
- Revision completa de todos los endpoints admin con escritura.

## Enfoque elegido

Se usaran los mecanismos de autenticacion ya existentes en `RUANA/web/app.py`:

- `@require_aliado` para acciones iniciadas por un aliado autenticado.
- `@require_admin_escritura` para acciones administrativas que modifican estado global.
- Store de sesion actual via `X-Ruana-Session-Id`.

Este enfoque minimiza cambios, respeta el diseno actual y permite cerrar el riesgo inmediato. La proteccion especifica de jobs internos por token queda para Hito 3, donde ya esta prevista.

## Cambios funcionales

### Invitaciones

`POST /api/invitaciones/crear` dejara de estar disponible sin sesion. La ruta requerira `@require_aliado`.

Cuando exista sesion de aliado, el backend resolvera el invitador desde `_aliado_codigo()` y solo usara datos de body como apoyo opcional. Esto evita que una llamada anonima cree placeholders o atribuya invitaciones manipulando `aliado_id`.

### Competencia vencida

`POST /api/competencia/finalizar-vencidas` requerira `@require_admin_escritura`.

Un usuario anonimo recibira `401`. Un admin de solo lectura recibira `403`. Un admin con permiso de escritura podra ejecutar el flujo actual.

### Purga mensual

`POST /api/purga/mensual` requerira `@require_admin_escritura`.

La semantica de respuesta actual se mantiene para admin con permiso valido. El cambio solo afecta a autorizacion.

## Diseno de pruebas

Se agregaran tests pytest en `RUANA/tests` usando el cliente de test de Flask.

Las pruebas deben evitar la base real:

- Usar monkeypatch sobre `get_db()` o sobre el objeto `db` usado por las rutas.
- Usar fakes pequenos que registren si se llamo una operacion sensible.
- Crear sesiones directamente con `_ruana_session_create()` para probar flujos autenticados sin depender de login completo.
- Limpiar `_RUANA_SESSION_STORE` entre tests.

Casos minimos:

- `POST /api/invitaciones/crear` sin sesion devuelve `401` y no llama a DB.
- `POST /api/competencia/finalizar-vencidas` sin admin devuelve `401`.
- `POST /api/purga/mensual` sin admin devuelve `401`.
- Admin solo lectura contra competencia devuelve `403`.
- Admin solo lectura contra purga devuelve `403`.
- Aliado autenticado puede crear invitacion y el resultado conserva la respuesta actual.

Si el coste es bajo, se anadira tambien un caso positivo para admin con escritura en competencia o purga usando DB fake.

## Riesgos y mitigaciones

Riesgo: algun frontend o script llama a los endpoints de cron sin credenciales.

Mitigacion: el roadmap ya considera cron protegido en Hito 3. En Hito 2A se prioriza impedir ejecucion anonima. Si aparece una integracion real, se actualizara para enviar sesion admin de escritura o se movera a token interno en el siguiente hito tecnico.

Riesgo: tests importan `app.py` y crean una DB SQLite por defecto.

Mitigacion: configurar `RUANA_DB_PATH` temporal antes de importar o monkeypatch temprano. La suite no debe escribir en `RUANA/ruana.db`.

Riesgo: proteger `POST /api/invitaciones/crear` puede afectar un flujo legacy anonimo.

Mitigacion: existen rutas de validacion e ingreso publicas para codigos. Crear codigos nuevos es accion de aliado y debe requerir sesion. Si se detecta un flujo frontend roto, se ajustara para enviar `X-Ruana-Session-Id`.

## Criterios de salida

- Las tres rutas criticas rechazan llamadas anonimas.
- Competencia y purga rechazan admin de solo lectura.
- Crear invitacion solo funciona con sesion de aliado.
- Los tests se ejecutan de forma reproducible sin tocar datos reales.
- `ROADMAP.md` o `HITOS_PROYECTO.md` se actualizara al cierre del subhito con verificacion ejecutada y siguiente paso.

## Estado para reanudar

- Hito activo: Hito 2 - Cierre de superficie critica.
- Subhito activo: Hito 2A - endpoints publicos que modifican estado.
- Diseno: proteger invitaciones con aliado; proteger competencia y purga con admin de escritura; cubrir con pytest y DB fake.
- Siguiente tarea: escribir plan de implementacion despues de revision de esta spec.
- Bloqueos: ninguno.
