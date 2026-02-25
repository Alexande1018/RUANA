# MAPA MENTAL COMPLETO DE RUANA
## Sistema de Gestión de Profesionales y Contactos

```
╔══════════════════════════════════════════════════════════════════════════════════════════╗
║                              RUANA - VISTA GENERAL                                      ║
╚══════════════════════════════════════════════════════════════════════════════════════════╝

                                ┌─────────────┐
                                │   USUARIO    │
                                │  (Browser)   │
                                └──────┬───────┘
                                       │
                    ┌──────────────────┼──────────────────┐
                    ▼                  ▼                  ▼
            ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
            │  index.html  │  │ aliado.html  │  │  admin.html  │
            │  (Entrada)   │  │  (Panel)     │  │  (Panel)     │
            │  375 líneas  │  │ 2822 líneas  │  │ 1828 líneas  │
            └──────┬───────┘  └──────┬───────┘  └──────┬───────┘
                   │                 │                  │
                   ▼                 ▼                  ▼
            ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
            │register.html │  │  JS inline   │  │ dashboard.js │
            │ 1010 líneas  │  │ (en aliado)  │  │  508 líneas  │
            └──────┬───────┘  └──────┬───────┘  └──────┬───────┘
                   │                 │                  │
                   └────────────┬────┴──────────────────┘
                                │
                        ┌───────▼────────┐
                        │   styles.css   │
                        │   config.css   │
                        └────────────────┘


╔══════════════════════════════════════════════════════════════════════════════════════════╗
║                         FLUJO DE DATOS: FRONTEND → BACKEND                              ║
╚══════════════════════════════════════════════════════════════════════════════════════════╝


  ┌──────────────────────────────────────────────────────────────────────────────────┐
  │                         FRONTEND (HTML + JS inline)                              │
  │                                                                                  │
  │  index.html ───fetch()──→ /api/validar-invitacion                               │
  │  register.html ─fetch()──→ /api/aliados/registrar + /api/catalogo/oficios       │
  │  aliado.html ──fetch()──→ /api/aliado/datos + /api/contactos/* + /api/invit*    │
  │  admin.html ───fetch()──→ /api/stats + /api/aliados/listar + /api/metricas-*   │
  │  dashboard.html─fetch()──→ dashboard.js (mezcla API real + datos mock legacy)   │
  │                                                                                  │
  └─────────────────────────────────────┬────────────────────────────────────────────┘
                                        │ HTTP (fetch API)
                                        ▼
  ┌──────────────────────────────────────────────────────────────────────────────────┐
  │                        FLASK SERVER (web/app.py)                                 │
  │                        1959 líneas │ 100+ rutas                                  │
  │                        Puerto 5050 │ Secret key hardcoded                        │
  │                                                                                  │
  │  ┌─────────────────────────────────────────────────────────────────────────┐     │
  │  │                    RUTAS POR CATEGORÍA                                  │     │
  │  │                                                                         │     │
  │  │  PÁGINAS          ALIADOS API        CONTACTOS API     ADMIN API        │     │
  │  │  ─────────        ──────────         ─────────────     ─────────        │     │
  │  │  GET /            POST registrar     POST crear        POST validar     │     │
  │  │  GET /register    GET datos          POST aceptar      GET stats        │     │
  │  │  GET /aliado      GET listar         POST trabajo      GET mov-24h     │     │
  │  │  GET /admin       PUT actualizar     POST declarar     POST suplencia  │     │
  │  │  GET /dashboard   POST pausar        POST no-concret   POST cerrar     │     │
  │  │                   GET verificar      GET metricas      GET salud       │     │
  │  │                                                                         │     │
  │  │  INVITACIONES     EVALUACIONES       SISTEMA                            │     │
  │  │  ─────────────    ─────────────      ──────────                         │     │
  │  │  GET validar      GET por-codigo     GET oficios                        │     │
  │  │  POST crear       GET historico      GET filtros                        │     │
  │  │  POST generar     GET estadisticas   GET health                         │     │
  │  │                                      POST purga                         │     │
  │  └─────────────────────────────────────────────────────────────────────────┘     │
  │                                                                                  │
  └─────────────────────────────────────┬────────────────────────────────────────────┘
                                        │ Llama a...
                    ┌───────────────────┼───────────────────┐
                    ▼                   ▼                   ▼
  ┌──────────────────────┐ ┌──────────────────┐ ┌──────────────────────┐
  │  core/db_manager.py  │ │engines/motor_    │ │  config/*.json       │
  │  1303 líneas         │ │evaluacion.py     │ │                      │
  │  100+ métodos        │ │  254 líneas      │ │ oficios_ruana.json   │
  │  Clase: DBManager    │ │  3 filtros       │ │  (77 oficios)        │
  │  Función: get_db()   │ │                  │ │ admin_codes.json     │
  └──────────┬───────────┘ └────────┬─────────┘ │ ruana_reglas_v1.json │
             │                      │            └──────────────────────┘
             │                      │
             ▼                      │
  ┌──────────────────────┐          │
  │     ruana.db         │◄─────────┘
  │   SQLite 188 KB      │
  │   15 tablas          │
  └──────────────────────┘


╔══════════════════════════════════════════════════════════════════════════════════════════╗
║                          BASE DE DATOS (ruana.db) - 15 TABLAS                           ║
╚══════════════════════════════════════════════════════════════════════════════════════════╝

  ┌─────────────────┐       ┌─────────────────┐       ┌─────────────────────┐
  │    aliados       │──┐    │    grupos        │       │  contactos_ruana    │
  │─────────────────│  │    │─────────────────│       │─────────────────────│
  │ id (PK)         │  │    │ id (PK)         │       │ id (PK)             │
  │ codigo (unique) │  ├───→│ nombre          │       │ solicitante_codigo ─┼──→ aliados
  │ nombre          │  │    │ codigo_postal   │       │ profesional_codigo ─┼──→ aliados
  │ marca           │  │    │ ciudad          │       │ servicio            │
  │ oficio          │  │    │ provincia       │       │ estado (máq.estados)│
  │ codigo_postal   │  │    │ estado          │       │ importe_solicitante │
  │ email           │  │    │ fecha_creacion  │       │ importe_profesional │
  │ telefono        │  │    └────────┬────────┘       │ importe_final       │
  │ estado          │  │             │                │ comision_ruana (5%) │
  │ score (0-100)   │  │             │                │ score_aplicado      │
  │ grupo_id (FK)───┼──┘             │                └─────────────────────┘
  │ especializacion │                │
  │ descripcion_srv │                │
  └────────┬────────┘                │
           │                         │
     ┌─────┴──────┐           ┌──────┴─────────┐
     ▼            ▼           ▼                ▼
┌──────────┐ ┌──────────┐ ┌──────────────┐ ┌──────────────────┐
│evaluacio-│ │score_    │ │solicitudes   │ │competencia       │
│nes       │ │movimient.│ │──────────────│ │──────────────────│
│──────────│ │──────────│ │ id           │ │ id               │
│codigo_al.│ │id        │ │ grupo_id ────┼─┤ grupo_id         │
│estado    │ │codigo_al.│ │ texto        │ │ oficio           │
│score     │ │delta     │ │ creado_por   │ │ aliado_original  │
│intencion │ │motivo    │ │ estado       │ │ aliado_suplente  │
│tasas     │ │timestamp │ │              │ │ duracion         │
│severidad │ │          │ │              │ │ ganador          │
└──────────┘ └──────────┘ └──────────────┘ └──────────────────┘

  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐  ┌──────────────┐
  │ invitaciones │  │  referidos   │  │invitaciones_oficio │  │avisos_grupo  │
  │──────────────│  │──────────────│  │────────────────────│  │──────────────│
  │ codigo       │  │ invitador    │  │ codigo (RUANA-X-X) │  │ grupo_id     │
  │ invitador_id │  │ invitado     │  │ grupo_id           │  │ mensaje      │
  │ usado (bool) │  │ fecha        │  │ oficio             │  │ fecha        │
  └──────────────┘  └──────────────┘  │ usado              │  └──────────────┘
                                      └────────────────────┘

  ┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────────┐
  │ evaluaciones_histor. │  │contacto_penaliz.     │  │grupo_oficio_cerrado  │
  │──────────────────────│  │──────────────────────│  │──────────────────────│
  │ (histórico de eval.) │  │ (7d=-2pts, 21d=-5pts)│  │ (oficios bloqueados) │
  └──────────────────────┘  └──────────────────────┘  └──────────────────────┘

  ┌──────────────────────┐
  │  eventos_sistema     │
  │──────────────────────│
  │ (log de eventos)     │
  └──────────────────────┘


╔══════════════════════════════════════════════════════════════════════════════════════════╗
║                    FLUJO 1: ENTRADA POR CÓDIGO DE INVITACIÓN                            ║
╚══════════════════════════════════════════════════════════════════════════════════════════╝

  ┌──────────┐     ┌──────────────┐     ┌───────────────────┐     ┌──────────────┐
  │ Usuario  │────→│  index.html  │────→│ fetch(/api/validar│────→│   Flask      │
  │ ingresa  │     │  campo código│     │ -invitacion)      │     │   app.py     │
  │ código   │     └──────────────┘     └───────────────────┘     └──────┬───────┘
  └──────────┘                                                           │
                                                              ┌──────────┴──────────┐
                                                              ▼                     ▼
                                                   ┌──────────────────┐  ┌──────────────────┐
                                                   │ Formato 5 dígitos│  │Formato RUANA-X-X │
                                                   │ → Es un código   │  │ → Es invitación  │
                                                   │   de aliado      │  │   de oficio      │
                                                   └────────┬─────────┘  └────────┬─────────┘
                                                            │                     │
                                                            ▼                     ▼
                                                   ┌──────────────────┐  ┌──────────────────┐
                                                   │ db.obtener_aliado│  │ db.validar_invit │
                                                   │ _por_codigo()    │  │ _oficio()        │
                                                   └────────┬─────────┘  └────────┬─────────┘
                                                            │                     │
                                                            ▼                     ▼
                                                   ┌──────────────────┐  ┌──────────────────┐
                                                   │ → aliado.html    │  │ → register.html  │
                                                   │   (Panel aliado) │  │   (Registro)     │
                                                   └──────────────────┘  └──────────────────┘


╔══════════════════════════════════════════════════════════════════════════════════════════╗
║                    FLUJO 2: REGISTRO DE ALIADO                                          ║
╚══════════════════════════════════════════════════════════════════════════════════════════╝

  ┌────────────┐    ┌──────────────────────────────────────────────────────────────┐
  │ register   │    │                   PROCESO DE REGISTRO                        │
  │ .html      │    │                                                              │
  │            │    │  1. Carga catálogo ──→ /api/catalogo/oficios (77 oficios)   │
  │ Formulario:│    │                                                              │
  │ - nombre   │    │  2. Envía datos ────→ /api/aliados/registrar                │
  │ - email    │    │                          │                                   │
  │ - teléfono │    │                          ▼                                   │
  │ - oficio   │    │                   ┌──────────────────┐                       │
  │ - espec.   │    │                   │  db.crear_aliado  │                      │
  │ - C.P.     │    │                   │                  │                       │
  │            │    │                   │ 1. Valida formato│                       │
  │            │    │                   │ 2. Genera código │                       │
  │            │    │                   │    5 dígitos     │                       │
  │            │    │                   │ 3. Busca/crea    │                       │
  │            │    │                   │    grupo por CP  │                       │
  │            │    │                   │ 4. Verifica oficio│                      │
  │            │    │                   │    no duplicado  │                       │
  │            │    │                   │ 5. score = 75    │                       │
  │            │    │                   │ 6. Si oficio no  │                       │
  │            │    │                   │    en catálogo:  │                       │
  │            │    │                   │    estado =      │                       │
  │            │    │                   │    'pendiente'   │                       │
  │            │    │                   └──────────────────┘                       │
  │            │    │                                                              │
  │            │    │  3. Si tenía invitación ─→ db.consumir_invitacion()          │
  │            │    │     (+3 score al invitador)                                   │
  │            │    │                                                              │
  │            │    │  4. Retorna código ──→ Usuario inicia sesión                 │
  └────────────┘    └──────────────────────────────────────────────────────────────┘


╔══════════════════════════════════════════════════════════════════════════════════════════╗
║                    FLUJO 3: MÁQUINA DE ESTADOS DE CONTACTOS                             ║
╚══════════════════════════════════════════════════════════════════════════════════════════╝

                         ┌─────────────────────────┐
                         │     CREAR CONTACTO       │
                         │  POST /api/contactos     │
                         │  solicitante + profesional│
                         └────────────┬─────────────┘
                                      │
                                      ▼
                              ┌───────────────┐
                              │   INICIADO    │
                              │               │
                              └───────┬───────┘
                                      │ POST .../aceptar
                                      ▼
                              ┌───────────────┐
                              │   ACEPTADO    │
                              │               │
                              └───────┬───────┘
                                      │ POST .../trabajo-en-progreso
                                      ▼
                              ┌───────────────┐
                              │   TRABAJO EN  │
                              │   PROGRESO    │
                              └───┬───┬───┬───┘
                                  │   │   │
                    ┌─────────────┘   │   └──────────────┐
                    ▼                 ▼                   ▼
           ┌───────────────┐ ┌───────────────┐  ┌───────────────┐
           │ DECLARAR      │ │ NO CONCRETADO │  │  (sin acción  │
           │ IMPORTE       │ │  POST .../    │  │   por 7 días) │
           │ POST .../     │ │  no-concretado│  │               │
           │ declarar-     │ │               │  │ Penalización  │
           │ importe       │ │  -2 score c/u │  │ automática    │
           └───┬───────┬───┘ └───────────────┘  │ 7d: -2 pts   │
               │       │                         │ 21d: -5 pts  │
               ▼       ▼                         └───────────────┘
    ┌──────────────┐ ┌──────────────┐
    │ Importes     │ │ Importes NO  │
    │ COINCIDEN    │ │ coinciden    │
    │              │ │              │
    │ TRABAJO      │ │ IMPORTE EN   │
    │ CERRADO      │ │ DISPUTA      │
    │              │ │              │
    │ +8 score c/u │ │ -5 score c/u │
    │ comisión 5%  │ │              │
    └──────────────┘ └──────────────┘


╔══════════════════════════════════════════════════════════════════════════════════════════╗
║                    FLUJO 4: MOTOR DE EVALUACIÓN                                         ║
╚══════════════════════════════════════════════════════════════════════════════════════════╝

  ┌─────────────────────┐
  │  core/orquestador.py│
  │  (Batch runner)     │
  └──────────┬──────────┘
             │ 1. Solicita métricas
             ▼
  ┌─────────────────────┐
  │ metrics/collector.py│     ⚠️  FAKE: Solo retorna datos
  │  (Recolector)       │────→ hardcoded para aliado "A1"
  └──────────┬──────────┘
             │ 2. Pasa métricas al motor
             ▼
  ┌───────────────────────────────────────────────────────────────────┐
  │  engines/motor_evaluacion.py  (Motor RUANA v0.2)                 │
  │                                                                   │
  │  ┌─────────────────────────────────────────────────────────────┐ │
  │  │              3 FILTROS DE EVALUACIÓN                         │ │
  │  │                                                             │ │
  │  │  ┌─────────────────┐  ┌────────────────┐  ┌─────────────┐ │ │
  │  │  │ FILTRO 1        │  │ FILTRO 2       │  │ FILTRO 3    │ │ │
  │  │  │ tasa_respuesta  │  │ tasa_confirm.  │  │ meses_sin   │ │ │
  │  │  │ >= 0.70         │  │ >= 0.80        │  │ trabajo <= 6│ │ │
  │  │  └────────┬────────┘  └───────┬────────┘  └──────┬──────┘ │ │
  │  │           │                   │                   │        │ │
  │  │           └───────────────────┼───────────────────┘        │ │
  │  │                               ▼                            │ │
  │  │              ┌─────────────────────────────────┐           │ │
  │  │              │ 3 OK = VERDE (saludable)        │           │ │
  │  │              │ 2 OK = AMARILLO (riesgo)        │           │ │
  │  │              │ ≤1 OK = ROJO (crítico)          │           │ │
  │  │              └─────────────────────────────────┘           │ │
  │  └─────────────────────────────────────────────────────────────┘ │
  │                                                                   │
  │  ┌─────────────────────────────────────────────────────────────┐ │
  │  │              SEVERIDAD (por persistencia)                    │ │
  │  │                                                             │ │
  │  │  ciclos_consecutivos = 0  → NORMAL                         │ │
  │  │  ciclos_consecutivos = 1  → ALERTA                         │ │
  │  │  ciclos_consecutivos >= 2 → CRÍTICO                        │ │
  │  └─────────────────────────────────────────────────────────────┘ │
  └──────────────────────────────┬────────────────────────────────────┘
                                 │ 3. Persiste resultado
                                 ▼
                    ┌─────────────────────────┐
                    │  db.guardar_evaluacion() │
                    │  → tabla evaluaciones    │
                    └─────────────────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │  event_bus.register()    │
                    │  → eventos_ruana.jsonl   │
                    └─────────────────────────┘

         ⚠️ BUG: evaluaciones.score NUNCA se sincroniza con aliados.score


╔══════════════════════════════════════════════════════════════════════════════════════════╗
║                    FLUJO 5: SISTEMA DE SCORE                                            ║
╚══════════════════════════════════════════════════════════════════════════════════════════╝

                              ┌──────────────────┐
                              │   SCORE ALIADO   │
                              │   Rango: 0-100   │
                              │   Inicio: 75     │
                              │   Límite: ±10/día│
                              └────────┬─────────┘
                                       │
                    ┌──────────────────┼──────────────────┐
                    ▼                  ▼                  ▼
          ┌─────────────────┐ ┌───────────────┐ ┌──────────────────┐
          │  SUBE SCORE     │ │ BAJA SCORE    │ │  ESTADOS RUANA   │
          │                 │ │               │ │                  │
          │ Trabajo cerrado │ │ No concretado │ │ 80-100:          │
          │ OK: +8 c/u      │ │ : -2 c/u      │ │  PRIORITARIO     │
          │                 │ │               │ │                  │
          │ Referido        │ │ Disputa       │ │ 50-79:           │
          │ exitoso: +3     │ │ importe: -5   │ │  ESTABLE         │
          │                 │ │               │ │                  │
          │                 │ │ Contacto 7d   │ │ 25-49:           │
          │                 │ │ sin cerrar:-2 │ │  EN RIESGO       │
          │                 │ │               │ │                  │
          │                 │ │ Contacto 21d  │ │ 0-24:            │
          │                 │ │ sin cerrar:-5 │ │  EN COMPETENCIA  │
          └─────────────────┘ └───────────────┘ └──────────────────┘


╔══════════════════════════════════════════════════════════════════════════════════════════╗
║                    FLUJO 6: PANEL ADMIN                                                 ║
╚══════════════════════════════════════════════════════════════════════════════════════════╝

  ┌──────────────┐  bypass solo dev (env)   ┌──────────────────────────────────────────┐
  │    ADMIN     │──────────────────→│            admin.html                     │
  └──────────────┘                   │                                          │
                                     │  Carga en paralelo:                      │
                                     │  ┌────────────────────────────────────┐  │
                                     │  │ /api/stats          → totales     │  │
                                     │  │ /api/aliados/listar → tabla       │  │
                                     │  │ /api/contactos/metricas → KPIs   │  │
                                     │  │ /api/movimiento-24h → actividad  │  │
                                     │  │ /api/metricas-salud → salud      │  │
                                     │  │ /api/eventos-recientes → log     │  │
                                     │  └────────────────────────────────────┘  │
                                     │                                          │
                                     │  Acciones admin:                         │
                                     │  ┌────────────────────────────────────┐  │
                                     │  │ Pausar aliado      (POST)         │  │
                                     │  │ Forzar suplencia   (POST)         │  │
                                     │  │ Cerrar oficio      (POST)         │  │
                                     │  │ Abrir plaza        (POST)         │  │
                                     │  │ Activar pendiente  (POST)         │  │
                                     │  │ Cambiar reglas     (POST)         │  │
                                     │  │ Generar reporte    (POST)         │  │
                                     │  └────────────────────────────────────┘  │
                                     └──────────────────────────────────────────┘


╔══════════════════════════════════════════════════════════════════════════════════════════╗
║                    DEPENDENCIAS ENTRE ARCHIVOS                                          ║
╚══════════════════════════════════════════════════════════════════════════════════════════╝


    ┌───────────────┐
    │  web/app.py   │──────────────────────────────────┐
    │  (Flask)      │                                  │
    │  1959 líneas  │─── importa ──→ core/db_manager   │
    │  100+ rutas   │─── importa ──→ config/*.json     │
    └───────┬───────┘                                  │
            │ sirve                                     │
            ▼                                          │
    ┌───────────────────────────┐                      │
    │  HTML + JS + CSS          │                      │
    │  index / register /       │                      │
    │  aliado / admin /         │                      │
    │  dashboard                │                      │
    └───────────────────────────┘                      │
                                                       │
    ┌────────────────────┐                             │
    │core/orquestador.py │──importa──→ engines/motor   │
    │  (batch runner)    │──importa──→ metrics/collect  │
    │                    │──importa──→ events/event_bus │
    └────────────────────┘              │              │
                                        │              │
    ┌────────────────────┐              │              │
    │engines/motor_      │──importa──→──┼──────────────┘
    │evaluacion.py       │              │    core/db_manager.py
    │  (3 filtros)       │              │         │
    └────────────────────┘              │         ▼
                                        │    ┌──────────┐
    ┌────────────────────┐              │    │ ruana.db  │
    │metrics/collector.py│              │    │ (SQLite)  │
    │  ⚠️ FAKE DATA      │              │    └──────────┘
    └────────────────────┘              │
                                        │
    ┌────────────────────┐              │
    │events/event_bus.py │──escribe──→──┘
    │  (logger JSONL)    │         logs/eventos_ruana.jsonl
    └────────────────────┘


╔══════════════════════════════════════════════════════════════════════════════════════════╗
║                    SISTEMA DE INVITACIONES                                              ║
╚══════════════════════════════════════════════════════════════════════════════════════════╝

    ┌────────────────────────────────────────────────────────────────┐
    │                    DOS TIPOS DE INVITACIÓN                     │
    │                                                                │
    │  TIPO 1: Código genérico (5 dígitos)                          │
    │  ───────────────────────────────────                          │
    │  Aliado genera → código "83921"                               │
    │  Invitado ingresa en index.html                               │
    │  → Si código es de aliado existente → va a aliado.html       │
    │  ⚠️ Almacenado en Flask SESSION (se pierde al reiniciar)     │
    │                                                                │
    │  TIPO 2: Invitación de oficio (RUANA-{grupo}-{OFICIO}-{4ch}) │
    │  ─────────────────────────────────────────────────────────────│
    │  Aliado genera para oficio faltante en su grupo               │
    │  Ejemplo: "RUANA-3-PLOMERO-A7K2"                             │
    │  → Invitado va a register.html con oficio pre-seleccionado   │
    │  ✅ Almacenado en DB (tabla invitaciones_oficio)              │
    │                                                                │
    │  Al completar registro con invitación:                         │
    │  → Invitador recibe +3 score                                  │
    │  → Invitación marcada como usada                              │
    └────────────────────────────────────────────────────────────────┘


╔══════════════════════════════════════════════════════════════════════════════════════════╗
║                    ESTADO ACTUAL: QUÉ FUNCIONA Y QUÉ NO                                 ║
╚══════════════════════════════════════════════════════════════════════════════════════════╝

    ✅ FUNCIONA                          ❌ ROTO / FAKE / FALTANTE
    ──────────────────────               ──────────────────────────────
    ✅ Entrada por código                ❌ MetricsCollector = datos falsos
    ✅ Registro de aliado                ❌ Invitaciones genéricas en SESSION
    ✅ Panel aliado completo             ❌ eval.score ≠ aliados.score (no sync)
    ✅ Máquina de estados contacto       ❌ Secret key hardcoded
    ✅ Importes sellados + 5% comisión   ❌ Suplente activation = no existe
    ✅ Motor evaluación 3 filtros        ❌ Solicitud response/closure = faltan
    ✅ Score con límite ±10/día          ❌ Alertas/notificaciones = no existen
    ✅ Panel admin con APIs reales       ❌ 150+ console.log en frontend
    ✅ Catálogo 77 oficios               ❌ dashboard.js = mezcla mock + real
    ✅ Penalizaciones automáticas        ❌ models/*.py = stubs vacíos
    ✅ Competencia tracking              ❌ ruana_reglas_v1.json = config trading

    🗑️ ARCHIVOS PARA ELIMINAR
    ─────────────────────────
    🗑️ private-panel.html
    🗑️ private-panel-new.html
    🗑️ risk_engine.py / executor.py / calculator.py (stubs de AceroTrade)
    🗑️ models/*.py (stubs vacíos nunca usados)


╔══════════════════════════════════════════════════════════════════════════════════════════╗
║                    ESTRUCTURA DE ARCHIVOS CON TAMAÑOS                                   ║
╚══════════════════════════════════════════════════════════════════════════════════════════╝

    RUANA/
    │
    ├── web/
    │   ├── app.py ················ 1959 líneas  ★ SERVIDOR PRINCIPAL
    │   ├── run.py ················   15 líneas    Lanzador
    │   ├── index.html ············  375 líneas    Pantalla entrada
    │   ├── register.html ·········  1010 líneas   Registro aliado
    │   ├── aliado.html ···········  2822 líneas  ★ PANEL ALIADO (JS inline)
    │   ├── admin.html ············  1828 líneas  ★ PANEL ADMIN (JS inline)
    │   ├── dashboard.html ········   ~200 líneas   Dashboard
    │   ├── invite.html ···········   ~100 líneas   Invitación
    │   ├── private-panel.html ····  🗑️ ELIMINAR
    │   ├── private-panel-new.html   🗑️ ELIMINAR
    │   └── static/
    │       ├── css/styles.css ····   CSS principal
    │       ├── css/config.css ····   CSS config
    │       └── js/dashboard.js ···  508 líneas   (mock + real mezclado)
    │
    ├── core/
    │   ├── db_manager.py ·········  1303 líneas  ★ TODA LA LÓGICA DB
    │   ├── orquestador.py ········   233 líneas    Batch runner
    │   └── preflight_validator.py    ~50 líneas    Validación
    │
    ├── engines/
    │   └── motor_evaluacion.py ···   254 líneas  ★ MOTOR 3 FILTROS
    │
    ├── config/
    │   ├── oficios_ruana.json ····   77 oficios    Catálogo
    │   ├── admin_codes.json ······    ~5 líneas    Códigos admin
    │   └── ruana_reglas_v1.json ··   ⚠️ CONFIG TRADING (reescribir)
    │
    ├── metrics/
    │   └── collector.py ··········    44 líneas   ⚠️ FAKE DATA
    │
    ├── events/
    │   └── event_bus.py ··········    77 líneas    Logger JSONL
    │
    ├── scripts/
    │   ├── seed_aliados.py ·······   132 líneas    Seed de prueba
    │   └── purga_mensual.py ······    34 líneas    Purga calidad
    │
    ├── utils/
    │   └── logger.py ·············   ~30 líneas    Setup logging
    │
    ├── logs/
    │   └── eventos_ruana.jsonl ···   Log eventos
    │
    └── ruana.db ··················   188 KB       ★ BASE DE DATOS
```
