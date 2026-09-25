# Cómo se hacía el grupo general antes del territorial

| | |
|---|---|
| Fecha | 2026-09-25 |
| Para qué sirve | Completar el hueco del informe de funcionamiento: **cómo se creaba el grupo general de ciudad y cómo se convertía después en grupo territorial** |
| Estado en `main` hoy | **Ese camino ya no corre.** Se quitó el 2026-09-09 en el PR [#233](https://github.com/Alexande1018/RUANA/pull/233) (`e7b5f98`). El alta actual crea el grupo territorial en el acto. |
| Dónde estaba el código | Commit `68c4d59` y anteriores. Archivos: `RUANA/core/services/grupo_madre_service.py` y `RUANA/core/repositories/grupo_madre_repo.py` (borrados). |
| Autoridad | El código histórico citado. Si hay conflicto con un recuento de memoria, prevalece el commit. |

---

## 0. Qué es «grupo general» en RUANA

En el equipo se dice **grupo general**. En el programa se llamaba **Grupo Madre**.

No era un grupo de un código postal. Era **un grupo de toda la ciudad**. Ahí entraban los aliados nuevos **mientras su código postal todavía no tenía grupos propios**. Cuando esa zona «maduraba», un administrador pulsaba un botón y **entonces** se creaban los grupos territoriales de ese CP y se movía a la gente.

Eso es exactamente: **primero el grupo general, después el territorial**.

Hoy, en `main`, ese paso intermedio **no existe**. El primer aliado de un CP crea ya el grupo territorial. Este documento describe **la manera en que se hacía** (y cómo se podría volver a hacer si se restaura).

---

## Las reglas antes de crear el grupo del CP

Sí: **antes de abrir el grupo territorial de un código postal** había que cumplir **las dos** a la vez. No valía solo una.

| Regla | Número exacto | Qué contaba |
|-------|---------------|-------------|
| Profesionales distintos en **ese** CP | **10** (`CP_MADUREZ_MIN_ALIADOS`) | Aliados con estado `activo` de ese código postal |
| Encargos de verdad en **ese** CP | **3** (`CP_MADUREZ_MIN_ENCARGOS`) | Encargos en los que el profesional **ya aceptó** (o más adelante: en progreso, acuerdo, pago, cerrado, disputa) |

**«10 profesionales diferentes»** en la práctica eran **10 oficios distintos**. En el grupo general solo cabía **una persona por oficio en cada CP**. Un segundo fontanero del mismo CP no entraba como activo: iba a la lista de espera y **no sumaba**. Por eso no se podía llegar a 10 con diez del mismo oficio.

El programa **no** comprobaba «oficios distintos» con un `DISTINCT`. Contaba personas activas de ese CP. La plaza del Madre (un oficio por CP) hacía que esas 10 personas fueran 10 oficios.

**Qué no contaba como encargo:** abierto pero sin aceptar (`iniciado`, `en_conversacion`), chat agotado, cierres sin encargo.

**Las dos a la vez.** 10 profesionales y 2 encargos → la zona **no** estaba lista. 9 profesionales y 5 encargos → tampoco.

Cumplir las reglas **no creaba el grupo del CP al momento**. El programa solo dejaba una solicitud de independencia. Un administrador tenía que **aprobar**. Sin ese clic, la gente seguía en el grupo general.

Constantes históricas (commit `68c4d59`, `RUANA/core/db_constants.py`):

```
CP_MADUREZ_MIN_ALIADOS = 10
CP_MADUREZ_MIN_ENCARGOS = 3
```

Comprobación: `n_aliados >= 10 and n_encargos >= 3` en `actualizar_madurez_cp`.

---

## 1. Cómo se creaba el grupo general

No lo creaba un administrador a mano. Lo creaba el **alta del primer aliado** de una ciudad que aún no tenía Grupo Madre.

### 1.1 Disparador

Al registrar (`POST /api/aliados/registrar`) el programa miraba el código postal de la persona:

1. Traducía el CP a ciudad (listado fijo; ejemplo: `03001` → Alicante).
2. Preguntaba: **¿este CP ya tiene algún grupo territorial activo?**
3. Si **sí** → no usaba el grupo general. Seguía el flujo territorial de siempre.
4. Si **no** y la ciudad se pudo resolver → **incubación**: entra (o crea) el Grupo Madre de esa ciudad.

Fuente histórica: `grupo_madre_service.resolver_asignacion_registro` y `asignar_aliado_incubacion` (commit `68c4d59`).

### 1.2 Creación (o reutilización) del grupo

Función: `obtener_o_crear_grupo_madre` → `asegurar_grupo_madre`.

Pasos concretos:

1. Normaliza el nombre de la ciudad (mayúsculas, sin rarezas).
2. Busca un grupo **activo** de tipo `madre` con esa ciudad.
3. Si ya existe, **lo reutiliza**. Alicante tenía **un solo** Grupo Madre, no uno por CP.
4. Si no existe:
   - Nombre: `RUANA-{CIUDAD}-MADRE`  
     Ejemplo: `RUANA-ALICANTE-MADRE`.
   - Código postal guardado: **`__MADRE__`** (falso; no es un CP real). Así el grupo no se confunde con un territorial de `03001`.
   - Tipo: `madre`.
   - Estado: `activo`.
   - Ciudad y provincia de la persona.
5. Si ya había una fila con ese nombre pero mal etiquetada, la **reetiquetaba** a tipo `madre` y CP `__MADRE__` en vez de crear otra.

Inserción histórica (`grupo_madre_repo.insertar_grupo_madre`):

```sql
INSERT INTO grupos (nombre, codigo_postal, ciudad, provincia, estado, tipo, fecha_creacion)
VALUES (?, '__MADRE__', ?, ?, 'activo', 'madre', CURRENT_TIMESTAMP)
```

**No hacía falta un número mínimo de gente para crear el grupo general.** El primer aliado de la ciudad lo hacía nacer. No esperaba 10 personas ni 3 encargos.

### 1.3 Quién entraba y quién no

Una vez existía el Madre, cada alta nueva de un CP **sin** grupos territoriales:

| Situación | Resultado |
|-----------|-----------|
| Oficio de catálogo y plaza libre en el Madre | Entra `activo` en el Grupo Madre |
| Oficio ya ocupado **en ese mismo CP** dentro del Madre | `en_espera`, sin grupo |
| Ese oficio ya está en **5 CPs distintos** dentro del mismo Madre | `en_espera`, sin grupo (tope de 5, igual que el tope de grupos por CP) |
| El CP no se puede traducir a ciudad | No crea Madre; caía al flujo territorial / espera |
| El CP **ya** tenía grupos territoriales | No entra al Madre; va a un territorial |

Regla de plaza **dentro del grupo general** (distinta del territorial):

- En un grupo territorial: **un oficio = una persona** en ese grupo.
- En el Madre: **un oficio = una persona por código postal**. Un electricista de `03001` y otro de `03003` **sí** cabían los dos en el mismo Grupo Madre de Alicante. Un segundo electricista de `03001` no.

Eso está en `plaza_disponible_en_madre` y en el test `test_sexto_oficio_mismo_cp_en_madre_va_a_espera` (commit `60a9ce7`).

Al entrar, el programa apuntaba el CP en la tabla `cp_estado` con modo `incubacion` y el `grupo_madre_id`.

### 1.4 Segunda forma de «hacer» el grupo general (migración de arranque)

Hubo un trabajo extra, no del alta diaria: `consolidar_territoriales_en_madre` (commit `68c4d59`, migración `grupo_madre_v2_consolidar`).

Al arrancar la base, **una vez**, el programa:

1. Cogía a los aliados que ya estaban en grupos territoriales.
2. Los pasaba al Grupo Madre de su ciudad (lo creaba si no existía).
3. Disolvía esos grupos pequeños y dejaba el CP en `incubacion`.

Eso iba **al revés** que la independización: no era «Madre → territorial», era «territoriales existentes → Madre». Servía para que, en el piloto, toda la ciudad empezara junta en el grupo general.

Hoy esa consolidación es un no-op: ya no mueve a nadie (`schema_service.py`, comentario de `grupo_madre_v2_consolidar`).

---

## 2. Qué podía hacer quien estaba en el grupo general

El aliado **sí tenía panel** (si quedó `activo`). No era una lista de espera.

| Acción | En el Grupo Madre | En un grupo territorial |
|--------|-------------------|-------------------------|
| Entrar al panel | Sí | Sí |
| Ver el directorio | **Toda la ciudad**: otros CPs del mismo Madre | Solo su grupo / su CP |
| Mandar y recibir solicitudes | Sí, del grupo Madre | Sí, de su grupo |
| Encargos y negociación | Sí | Sí |
| Competencia por plaza | Había reglas propias de incubación | Reglas territoriales actuales |
| Chat libre de encargo | No (el chat libre ya estaba cerrado) | No |

El directorio de incubación **mezclaba códigos postales de la misma ciudad**. Test histórico: `test_directorio_incubacion_incluye_otro_cp_misma_ciudad` (`52001` en `03001` ve a `52002` en `03003`).

La primera vez veía un **aviso de bienvenida** (`aviso_tipo = grupo_madre_bienvenida`) y una **barra de madurez** de su CP: cuántos aliados y cuántos encargos faltaban para independizar la zona.

Quien quedaba `en_espera` **no** entraba al Madre ni al panel. Igual que ahora.

---

## 3. Cuándo se creaba el grupo territorial (después del general)

El grupo territorial **no nacía solo** al llegar a un número. Primero la zona tenía que **madurar**. Luego un administrador **aprobaba**.

### 3.1 Umbrales de madurez (por código postal, no por ciudad)

Son las mismas dos reglas de arriba: **10 profesionales distintos + 3 encargos aceptados**, las dos a la vez, **de ese CP** (no de toda la ciudad).

Constantes históricas en `RUANA/core/db_constants.py` (commit `68c4d59`):

| Constante | Valor | Significado |
|-----------|-------|-------------|
| `CP_MADUREZ_MIN_ALIADOS` | **10** | Aliados **activos** de **ese** CP. En el general equivalían a **10 oficios distintos** (un oficio por CP). |
| `CP_MADUREZ_MIN_ENCARGOS` | **3** | Encargos **válidos** de profesionales de **ese** CP |

Ni 10 aliados sin encargos, ni 3 encargos con 9 aliados.

**Encargo válido:** el profesional ya aceptó el contacto. Contaban: `aceptado`, `trabajo_en_progreso`, `acuerdo_alcanzado`, `pendiente_de_pago`, `trabajo_cerrado`, `importe_en_disputa`. **No** contaban: `iniciado`, `en_conversacion`, chat agotado, cierres sin encargo.

La cuenta se actualizaba en `actualizar_madurez_cp` (cuando se aceptaba un encargo). Si las dos cifras se cumplían y no había ya una solicitud pendiente, el programa **creaba una solicitud de independencia** en `cp_independencia_solicitudes` con estado `pendiente`.

Eso **no** creaba todavía el grupo territorial. Solo avisaba al admin: «esta zona está lista».

### 3.2 El admin crea el territorial (el paso que faltaba en el informe)

Función: `aprobar_independencia_cp`. Endpoint histórico: `POST /api/admin/cp-independencia/aprobar`.

El administrador podía **aprobar** o **posponer**. Sin ese clic, la gente se quedaba en el Grupo Madre aunque ya hubiera 10 aliados y 3 encargos.

Al **aprobar**, para **ese CP** (no para toda la ciudad):

1. Lista los aliados **activos** de ese CP que siguen en el Madre.
2. Para cada uno, usa la lógica territorial de plazas:
   - Si ya hay un grupo territorial de ese CP con el oficio libre → entra ahí.
   - Si **no hay ningún** grupo territorial en el CP → **aquí nace el primer grupo territorial** (`crear_grupo_en_cp` / `asignar_territorial_post_insert`) y entra esa persona.
   - Si hace falta otro grupo y hay menos de 5 → se crea otro y entra.
   - Si los 5 grupos ya tienen ese oficio → esa persona pasa a `en_espera` y se le quita el `grupo_id`.
3. Marca el CP como `territorial` (`cp_estado.modo = territorial`).
4. Limpia competencias de incubación de ese CP.
5. Marca la solicitud como `aprobada`.
6. Avisa a los migrados: *«Tu código postal X ya tiene su propio Grupo RUANA. A partir de ahora formas parte de la red territorial de tu zona.»*

Los aliados de **otros** CPs de la misma ciudad **se quedan** en el Grupo Madre. La independización es **por código postal**, no se vacía Alicante de un golpe.

El admin podía **posponer**: la solicitud pasa a `pospuesta` y nadie se mueve.

### 3.3 Orden y desempates al repartir

No había sorteo.

- Orden de las personas: el listado de aliados activos de ese CP en el Madre (consulta `listar_aliados_activos_madre_por_cp`).
- Al sentar a cada uno: primer grupo territorial del CP con el oficio libre; si no hay grupos, se crea el primero en ese momento.
- Tope: 5 grupos por CP (`MAX_GRUPOS_POR_CP`).
- Quien no cabe: `en_espera`, sin grupo.

**Nadie del Madre se iba a otro CP.** Solo se movía gente **de ese** código postal.

---

## 4. Dibujo del camino

```
Registro con CP (ej. 03001)
        │
        ▼
¿Ese CP ya tiene grupo territorial?
   │                │
  SÍ               NO
   │                │
   ▼                ▼
Grupo territorial   ¿Se conoce la ciudad del CP?
de ese CP              │              │
                      SÍ             NO
                       │              │
                       ▼              ▼
              ¿Existe RUANA-ALICANTE-MADRE?
                 │            │
                SÍ           NO
                 │            │
                 │            ▼
                 │     CREAR grupo general
                 │     nombre: RUANA-ALICANTE-MADRE
                 │     CP falso: __MADRE__
                 │     tipo: madre
                 │            │
                 └─────┬──────┘
                       ▼
              ¿Hay plaza en el Madre?
              (1 oficio por CP; máx. 5 CPs
               con el mismo oficio)
                 │            │
                SÍ           NO
                 │            │
                 ▼            ▼
            Entra activo    en_espera
            al grupo        (sin grupo,
            general          sin panel)

Luego, en el grupo general:
  directorio de toda la ciudad
  solicitudes, encargos, barra de madurez

Cuando ESE CP llega a:
  10 aliados activos  Y  3 encargos aceptados
        │
        ▼
  Solicitud de independencia (pendiente)
        │
        ▼
  Admin aprueba ──────────► se CREAN los grupos
                            territoriales de ese CP
                            y se mueve a esa gente
  Admin pospone ──────────► nadie se mueve
```

---

## 5. Lo que no hay que mezclar

Estos nombres suenan parecidos y **no** son el grupo general:

| Nombre | Qué es de verdad |
|--------|------------------|
| **Grupo Madre / grupo general** | Grupo de **ciudad**, tipo `madre`, CP `__MADRE__`. Sala previa al territorial. **Ya no se crea.** |
| **Grupo territorial** | Grupo de **un CP**. El único que se crea hoy. Hasta 5 por CP. |
| **Grupo en creación** | Un territorial con **10 o menos** aliados. Invitaciones +5. Sigue existiendo. No es sala de ciudad. |
| **Grupo en formación** | Apodo al colocar al perdedor de una competencia: el grupo del CP con menos gente y oficio libre. No es un tipo de grupo. |
| **Frase «red de RUANA Alicante»** | Texto del formulario al resolver el CP. **No crea grupo.** |

---

## 6. Qué hace `main` hoy (para no confundir el informe)

Tras el PR #233:

- El alta **nunca** llama a `obtener_o_crear_grupo_madre` (esa función ya no existe).
- `resolver_asignacion_registro` dice en el propio código: *«Asignación territorial directa por CP. Nunca crea ni usa Grupo Madre.»* (`RUANA/core/services/grupo_service.py`).
- El primer aliado de un CP **crea el territorial al momento**. No hay umbral de 10+3. No hay clic de admin.
- Quedan restos de lectura: columnas `grupos.tipo`, `cp_estado`, migración `territorio_directo_v1` por si quedaran filas `madre`.
- Un segundo grupo territorial vacío puede nacer tras **10 altas con plaza** en un CP **ya** territorial (`CP_NUEVO_GRUPO_MIN_ALIADOS = 10`). Eso **no** es independizar un grupo general: es un extra dentro de un CP que ya era territorial.

Si el equipo explica el producto como «primero el grupo general de Alicante y luego los de cada código postal», **está describiendo el diseño que se implementó en septiembre de 2026 y se retiró el 9 de septiembre**. El programa de hoy no hace ese paso.

---

## 7. Commits para quien quiera ver el código

| Commit | Qué hizo |
|--------|----------|
| `60a9ce7` | Nacimiento del Grupo Madre: incubación, madurez 10+3, independencia admin, directorio de ciudad |
| `06f32e2` / `9238fff` | Cinta de actividad y competencia dentro del Madre |
| `926e40d` | Auto-split: 10 elegibles abren otro territorial **si el CP ya era territorial** |
| `68c4d59` | Consolidación de arranque: pasar territoriales vivos **al** Madre |
| `e7b5f98` / PR #233 | Se elimina el alta en Madre. Territorio directo por CP |

Archivos históricos (ya no están en `main`):

- `RUANA/core/services/grupo_madre_service.py`
- `RUANA/core/repositories/grupo_madre_repo.py`

Esquema que **sí** quedó (sin DROP): `supabase/migrations/20260908000200_grupo_madre_schema.sql`.
