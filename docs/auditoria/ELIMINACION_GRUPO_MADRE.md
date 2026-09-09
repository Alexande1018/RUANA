# Auditoría: eliminación del Grupo Madre y territorio directo por CP

| | |
|---|---|
| Fecha | 2026-09-09 |
| Rama | `cursor/territorio-directo-cp-b288` |
| Estado | Fase 1 — auditoría previa a implementación |
| Autoridad | El código en `RUANA/` prevalece si hay conflicto |

---

## Decisión arquitectónica (antes de modificar)

**Se conservan varios grupos territoriales independientes dentro del mismo código postal.**

La arquitectura vigente ya contempla hasta **5 grupos activos por CP** (`MAX_GRUPOS_POR_CP` en `core/db_constants.py`). Cada aliado pertenece a **un** grupo territorial asociado a su CP; no se fusionan todos los aliados de un CP en un único grupo.

Motivos para no colapsar a un grupo por CP:

- Las plazas son **un oficio principal por grupo**. Varios grupos en el mismo CP permiten más de un profesional del mismo oficio en la zona, con tope de 5.
- Competencia, crecimiento orgánico y lista de suplentes dependen de esa multiplicidad.
- Unificar a un grupo por CP rompería plazas, suplentes y datos existentes.

Modelo resultante:

- Un aliado solo ve el **directorio de su grupo territorial actual**.
- El administrador consulta todos los grupos y códigos postales.
- La **proximidad** no abre el directorio de otros grupos: solo recomienda un profesional cercano cuando el oficio no está en el grupo local.

---

## 1. Archivos afectados

### Backend / dominio

| Archivo | Rol actual | Acción |
|---------|------------|--------|
| `RUANA/core/services/grupo_madre_service.py` | Incubación, madurez, independencia, consolidación | Eliminar lógica de madre; mover asignación territorial a `grupo_service` |
| `RUANA/core/repositories/grupo_madre_repo.py` | SQL de madre / `cp_estado` | Sustituir por `territorio_repo` + migración |
| `RUANA/core/services/aliado_service.py` | Registro y directorio según modo incubación | Asignación y directorio solo territoriales |
| `RUANA/core/services/grupo_service.py` | Info de panel, viabilidad (excluye madre) | Asignación directa + sin ramas madre |
| `RUANA/core/services/schema_service.py` | `grupo_madre_v1` + consolidar v2 al arrancar | v2 deja de consolidar; nueva `territorio_directo_v1` |
| `RUANA/core/services/competencia_service.py` | Retador/cierre en incubación | Solo reglas territoriales |
| `RUANA/core/repositories/competencia_repo.py` | `buscar_retador_activo_madre` | Dejar de usarse en runtime |
| `RUANA/core/services/solicitud_service.py` | Solicitudes por grupo madre en incubación | Solo grupo/CP territorial |
| `RUANA/core/services/solicitud_semanal_service.py` | `plaza_ocupada_contexto` madre | Plaza territorial |
| `RUANA/core/services/contacto_service.py` | `actualizar_madurez_cp` al aceptar | Quitar madurez |
| `RUANA/core/services/actividad_cinta_service.py` | Métricas e hitos de incubación | Quitar métricas/hitos de madre |
| `RUANA/core/repositories/actividad_repo.py` | Sentinel `__MADRE__` en contexto | Conservar lectura histórica; no crear madre |
| `RUANA/core/db_manager.py` | Fachadas madre / independencia | Quitar fachadas operativas; añadir migración/check |
| `RUANA/core/db_constants.py` | Constantes madre/madurez | Conservar nombres históricos para detectar datos; no usarlos en alta |

### API

| Endpoint | Acción |
|----------|--------|
| `POST /api/aliado/grupo-madre/aviso-visto` | Eliminar |
| `GET /api/admin/grupos-madre` | Eliminar |
| `GET /api/admin/cp-madurez` | Eliminar |
| `GET /api/admin/cp-independencia/pendientes` | Eliminar |
| `POST /api/admin/cp-independencia/aprobar` | Eliminar |
| `POST /api/admin/cp-independencia/posponer` | Eliminar |
| `GET /api/admin/dashboard-summary` (`grupos_madre`, `cp_independencia_pendientes`) | Sustituir por métricas territoriales |
| `GET /api/aliado/proximidad` | **Nuevo** |
| `POST /api/aliado/proximidad/solicitar` | **Nuevo** |
| `GET /api/admin/territorio/migracion-check` | **Nuevo** |
| `GET /api/admin/territorio/estado` | **Nuevo** (aliados por CP/grupo) |

### Frontend

| Archivo | Acción |
|---------|--------|
| `RUANA/web/aliado.html` | Quitar modal y barras de madurez |
| `RUANA/web/static/js/aliado-grupo-module.js` | Quitar aviso/madurez/incubación |
| `RUANA/web/static/js/aliado-directorio-module.js` | Directorio solo del grupo; proximidad puntual |
| `RUANA/web/admin.html` | Sustituir bloque Grupo Madre |
| `RUANA/web/static/js/admin-territorio-module.js` | Estado territorial + check de migración |
| `RUANA/web/static/js/admin-resumen-module.js` | Quitar KPIs de madre |
| `RUANA/web/static/js/admin-command-center-module.js` | Quitar alerta de independización |
| `e2e/utils/qa-narrator.js` | Quitar dismiss del aviso madre |

### Tests a reescribir o sustituir

- `test_grupo_madre.py`, `test_grupo_madre_admin.py`, `test_grupo_madre_consolidar.py`
- `test_grupo_madre_postgres_schema.py`
- `test_cp_auto_split_grupos.py` (bootstrap deja de ir a madre)
- `test_actividad_cinta_madre.py`, `test_competencia_incubacion_madre.py`

### Documentación / despliegue

- `supabase/migrations/20260908000200_grupo_madre_schema.sql` — **no borrar** (histórico; no DROP)
- Nueva migración `20260909000100_territorio_directo.sql` — backup + informe, sin DROP de columnas

---

## 2. Tablas y columnas afectadas

### Se conservan (histórico / reversibilidad)

| Objeto | Motivo |
|--------|--------|
| `grupos.tipo` | Detectar residuales `madre` |
| `grupos.grupo_madre_id` | Trazabilidad; no se usa en alta |
| `cp_estado` | Contador de auto-split territorial (`aliados_desde_ultimo_grupo`); `modo` queda `territorial` |
| `cp_independencia_solicitudes` | Histórico; sin flujo operativo |
| `aliado_avisos_vistos` | Histórico |
| `cp_ciudad` | Resolución CP → ciudad (sigue haciendo falta) |

### Nuevas (migración segura)

| Tabla | Uso |
|-------|-----|
| `migracion_territorio_backup` | `aliado_id`, `grupo_id_anterior`, `grupo_id_nuevo`, `estado_anterior`, instantánea reversible |
| `migracion_territorio_informe` | Casos: `migrado`, `sin_codigo_postal`, `ambiguedad_plaza`, `sin_grupo_destino`, `grupo_madre_vacio` |

**No se eliminan** contratos, mensajes, pagos, invitaciones ni historial. **No se DROP** columnas de madre en esta fase.

---

## 3. Endpoints afectados

Ver sección 1. Los endpoints de independencia y aviso de madre desaparecen. El dashboard admin deja de exponer `grupos_madre` / `cp_independencia_pendientes`.

---

## 4. Riesgos

| Riesgo | Mitigación |
|--------|------------|
| Aliados en madre sin CP | No se mueven; informe `sin_codigo_postal`; check admin |
| Oficio ocupado en todos los grupos del CP (tope 5) | No se inventa plaza; informe `ambiguedad_plaza`; el aliado permanece hasta decisión manual |
| Consolidar v2 ya aplicado en producción | Nueva migración inversa con backup; v2 deja de mutar datos si aún no se había aplicado |
| Varios grupos por CP | Se documenta y se conserva; el directorio no mezcla grupos |
| Competencia / cinta / solicitudes acopladas a incubación | Ramas madre eliminadas; tests de competencia territorial |
| Pagos 12% | Sin cambios de flujo; tests de cierre/apoyo existentes + cobertura en el pack territorial |
| Arranque Postgres | v1 schema se mantiene; consolidar v2 no-op; v3 migración de datos |

---

## 5. Plan de migración

1. **Respaldo:** insertar en `migracion_territorio_backup` el `grupo_id` actual de cada aliado en grupo `tipo=madre` o CP `__MADRE__`.
2. **Asignación:** por cada aliado activo con CP válido, buscar grupo territorial del CP con plaza libre; si no hay grupos, crear el primero; si hay plaza en alguno, asignar; si hay que abrir grupo adicional y hay cupo (&lt;5), crear; si no hay plaza y el cupo está lleno, **no mover** y registrar `ambiguedad_plaza`.
3. **Sin CP:** no inventar CP; registrar y dejar el vínculo hasta decisión manual.
4. **Grupos madre vacíos:** marcar `estado=disuelto` (no DELETE). Los que aún tengan aliados residuales quedan en el informe.
5. **Reverso:** restaurar `aliados.grupo_id` desde `migracion_territorio_backup` y reactivar grupos disueltos en el backup.
6. **Runtime:** el alta nueva nunca crea `tipo=madre`. `grupo_madre_v2_consolidar` no vuelve a empujar aliados a madre.

---

## 6. Casos ambiguos (decisión manual)

1. Aliado activo **sin código postal**.
2. Aliado con CP cuyo oficio está ocupado en los **5 grupos** del CP.
3. Aliado cuyo CP no resuelve ciudad en catálogo (se puede crear grupo territorial igual; ciudad puede quedar vacía).
4. Grupo madre con aliados residuales tras el paso 2 (los del informe).
5. Solicitudes de independencia pendientes: se archivan como histórico; no se aprueban ni se ejecutan.

Estos casos **no se borran**. El panel admin ofrece `GET /api/admin/territorio/migracion-check`.
