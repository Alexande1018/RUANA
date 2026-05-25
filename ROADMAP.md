# Roadmap unificado RUANA

Fecha de creacion: 2026-05-22  
Fuente de verdad operativa: este documento.  
Registro historico de cierres: `HITOS_PROYECTO.md`.  
Auditoria base: `AUDITORIA_RUANA_2026-05-19.md`.

## 1. Estado actual

RUANA esta en fase pre-MVP avanzada. El Hito 1 dejo hecha la auditoria tecnica, la preparacion de despliegue y la base de migracion progresiva hacia Supabase/Firebase/Cloud Run.

El paso actual es:

**Hito 2 - Cierre de superficie critica de seguridad y permisos.**

Objetivo inmediato: bloquear los riesgos de Prioridad 0 antes de exponer la aplicacion a usuarios reales.

## 2. Metodo de trabajo por hitos

Cada hito se trabaja como un ciclo cerrado:

1. **Abrir hito**
   - Confirmar objetivo, alcance y riesgos.
   - Marcar en este roadmap el hito como `Activo`.
   - Definir una lista corta de entregables y criterios de salida.

2. **Planificar solo el hito activo**
   - No se replanifica todo el proyecto salvo que cambie una decision importante.
   - El plan se limita a los archivos y flujos afectados por el hito.
   - Si el hito supera 5-7 tareas tecnicas, se divide en subhitos.

3. **Ejecutar en cambios pequenos**
   - Una tarea debe poder revisarse y probarse de forma aislada.
   - Se priorizan tests antes de tocar permisos, datos personales o flujos de negocio.
   - Cada cambio debe dejar el sistema en estado ejecutable.

4. **Verificar**
   - Ejecutar pruebas automatizadas si existen.
   - Anadir pruebas cuando el riesgo sea de permisos, datos o dinero.
   - Registrar comandos relevantes y resultado en el cierre del hito.

5. **Cerrar hito**
   - Actualizar `HITOS_PROYECTO.md` con resumen para cliente/equipo.
   - Actualizar este roadmap: hito cerrado, fecha, pendientes que pasan al siguiente.
   - Dejar indicada la siguiente accion operativa.

## 3. Metodo eficiente en coste de tokens

El metodo recomendado es **trabajo por contexto minimo + delta documentado**.

En cada nueva sesion, el asistente solo deberia leer:

1. `ROADMAP.md`
2. La ultima seccion relevante de `HITOS_PROYECTO.md`
3. Los archivos concretos que el hito activo vaya a modificar
4. Salida corta de `git status --short --branch`

Evitar por defecto:

- Releer toda la auditoria en cada sesion.
- Pegar archivos largos en el chat.
- Rehacer resumenes globales del proyecto.
- Mezclar varios hitos en una misma sesion.
- Duplicar la misma informacion en muchos documentos.

Regla practica:

- **Roadmap** = que toca y en que orden.
- **Hitos** = que se ha cerrado y como se explica.
- **Auditoria** = evidencia congelada, se consulta solo cuando haga falta.
- **Codigo/tests** = verdad tecnica actual.

Para ahorrar tokens, al final de cada sesion se debe dejar un bloque muy breve de reanudacion en el cierre o nota de avance:

```text
Estado para reanudar:
- Hito activo:
- Tarea terminada:
- Verificacion ejecutada:
- Siguiente tarea:
- Bloqueos:
```

Ese bloque sustituye a tener que reconstruir el contexto desde cero.

## 4. Hitos

### Hito 1 - Auditoria, base de despliegue y transicion de infraestructura

Estado: `Cerrado documentalmente`  
Fecha de cierre documental: 2026-05-20  
Referencia: `HITOS_PROYECTO.md`

Entregables principales:

- Auditoria tecnica del proyecto existente.
- Priorizacion de riesgos antes de produccion.
- Migraciones iniciales para Supabase/Postgres.
- Preparacion de configuracion Firebase, Cloud Run, Docker y scripts.
- Puente temporal SQLite/Postgres.

Pendientes que arrastra:

- Cerrar riesgos criticos de autoridad y exposicion de datos.
- Consolidar tests y despliegue real.

### Hito 2 - Cierre de superficie critica

Estado: `Activo`  
Prioridad: maxima  
Base: Prioridad 0 de la auditoria.

Objetivo:

Bloquear accesos publicos o mal autorizados que puedan exponer datos personales, modificar negocio o permitir suplantacion.

Orden recomendado:

1. Crear o ajustar pruebas de permisos con base de datos temporal.
2. Proteger o retirar endpoints publicos que modifican estado:
   - `POST /api/invitaciones/crear`
   - `POST /api/competencia/finalizar-vencidas`
   - `POST /api/purga/mensual`
3. Cerrar lectura publica de datos personales en `/api/aliados*`.
4. Eliminar o proteger endpoints legacy de chat:
   - `/api/chat/mensajes`
   - `/api/chat/enviar`
5. Restringir campos editables por aliado:
   - `score`
   - `estado`
   - `grupo_id`
6. Validar pertenencia al contacto en acciones de contacto, chat e importes.
7. Cambiar escrituras admin de `@require_admin` a `@require_admin_escritura` donde corresponda.
8. Ejecutar regresion y documentar cierre.

Criterios de salida:

- Ningun endpoint publico modifica estado de negocio.
- Los endpoints publicos no devuelven PII ni reputacion sensible.
- Un aliado no puede alterar contactos ajenos aunque conozca el ID.
- Un aliado no puede editar su score, estado o grupo mediante API.
- Admin de solo lectura no puede ejecutar escrituras.
- Hay pruebas automatizadas o verificaciones reproducibles para los casos criticos.

Siguiente accion operativa:

Empezar por pruebas de permisos y proteccion de endpoints publicos que modifican estado.

### Hito 3 - Endurecimiento tecnico

Estado: `Pendiente`

Objetivo:

Reducir riesgos tecnicos de produccion que no son puramente funcionales.

Entregables:

- Exigir `FLASK_SECRET_KEY` seguro en produccion.
- Restringir CORS por entorno.
- Activar foreign keys en SQLite por conexion mientras exista SQLite.
- Limitar uploads y validar tipo/tamano.
- Sacar comprobantes de rutas publicas o proteger el acceso.
- Sustituir sesiones en memoria por almacenamiento persistente o estrategia equivalente.
- Proteger cron por token interno o moverlo fuera de HTTP publico.

Criterios de salida:

- Configuracion de produccion sin secretos por defecto.
- CORS, sesiones y uploads con reglas explicitas.
- Jobs internos sin acceso publico accidental.

### Hito 4 - Coherencia funcional y deuda de dominio

Estado: `Pendiente`

Objetivo:

Alinear reglas de negocio, nomenclatura y comportamiento real.

Entregables:

- Resolver competencia vencida de forma controlada.
- Decidir si el motor aplica score operativo o solo genera evaluaciones.
- Unificar estados `no_concretado` y `cerrado_no_concretado`.
- Alinear Apoyo RUANA al porcentaje real configurado.
- Corregir frontend de subida de comprobantes para enviar sesion.
- Marcar o retirar pantallas legacy/demo.

Criterios de salida:

- Reglas de negocio consistentes entre backend, frontend y documentacion.
- No quedan nombres/documentos que contradigan calculos activos.

### Hito 5 - Calidad, pruebas y operaciones

Estado: `Pendiente`

Objetivo:

Dejar una base de pruebas y operacion que permita evolucionar sin romper flujos clave.

Entregables:

- Suite pytest con base de datos temporal.
- Tests de permisos por endpoint.
- Tests transaccionales de contactos, cierres, importes y pagos.
- Migraciones versionadas y menos `ALTER TABLE` dispersos.
- Logs estructurados para purga, competencia, pagos y acciones admin.
- Documentacion del esquema y API reales.

Criterios de salida:

- Se puede validar el backend sin tocar datos reales.
- Los flujos economicos y de permisos quedan cubiertos por tests.

### Hito 6 - Despliegue real y beta controlada

Estado: `Pendiente`

Objetivo:

Publicar RUANA en entorno controlado con infraestructura persistente y validacion de flujos reales.

Entregables:

- Backend desplegado en Cloud Run o alternativa definida.
- Persistencia real en Supabase/Postgres o servicio acordado.
- Hosting conectado a backend.
- Secretos gestionados fuera del repo.
- Checklist manual de flujos principales:
  - registro
  - login aliado
  - panel aliado
  - solicitud
  - contacto
  - chat
  - cierre con importe
  - pago Apoyo RUANA
  - panel admin

Criterios de salida:

- Beta cerrada usable por usuarios reales seleccionados.
- Incidencias documentadas y priorizadas.

### Hito 7 - MVP publico controlado

Estado: `Pendiente`

Objetivo:

Abrir la plataforma con control de riesgos, soporte y capacidad de seguimiento.

Entregables:

- Politica operativa basica de altas, pagos, incidencias y soporte.
- Monitorizacion minima.
- Backups o estrategia de recuperacion.
- Documentacion de uso para administracion.
- Lista de decisiones pendientes para v2.

Criterios de salida:

- RUANA puede operar publicamente de forma limitada y medible.

## 5. Reglas de priorizacion

Orden de decision:

1. Seguridad y datos personales.
2. Integridad de dinero, pagos y score.
3. Flujos principales de usuario.
4. Despliegue y operaciones.
5. Limpieza tecnica y documentacion secundaria.

No se debe avanzar a un hito posterior si queda abierto un riesgo critico del hito activo, salvo que se documente explicitamente como decision aceptada.

## 6. Formato de cierre de hito

Cada cierre en `HITOS_PROYECTO.md` debe incluir:

```text
## Hito N - Nombre

Fecha de cierre:
Estado:
Rama/commit:

Resumen para cliente:

Trabajo realizado:

Verificacion:

Pendientes que pasan al siguiente hito:

Estado para reanudar:
- Hito activo:
- Tarea terminada:
- Verificacion ejecutada:
- Siguiente tarea:
- Bloqueos:
```

## 7. Estado para reanudar

- Hito activo: Hito 2 - Cierre de superficie critica.
- Tarea terminada: Hito 2A protege `POST /api/invitaciones/crear`, `POST /api/competencia/finalizar-vencidas` y `POST /api/purga/mensual` con pruebas pytest de permisos.
- Verificacion ejecutada: `python -m pytest RUANA/tests/test_hito_2a_permissions.py -v` y `python -m pytest RUANA/tests -v` (13 passed en ambos).
- Siguiente tarea: Hito 2B, cerrar lectura publica de datos personales en `/api/aliados*`.
- Bloqueos: ninguno documentado.
