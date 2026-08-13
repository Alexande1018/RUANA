# RUANA Code Map

Mapa visual interactivo del código **real** de RUANA — no es una maqueta ni datos
de ejemplo. `scanner.py` lee el repositorio con `ast` (Python), regex (JS/HTML) y
parseo de migraciones SQL, y `index.html` renderiza el grafo resultante con
Sigma.js (WebGL), pensado para cientos/miles de nodos sin bloquear la interfaz.

Herramienta 100% de desarrollo, aislada en `dev-tools/code-map/`. No importa
nada de `RUANA/`, no se ejecuta como parte de la app, y no toca producción.

## Cómo verlo (forma fácil)

```bash
bash dev-tools/code-map/generate.sh
```

Luego abre en Brave (doble clic, sin servidor):

```text
dev-tools/code-map/ruana-code-map.html
```

Ese HTML es **standalone**: lleva libs + `graph.json` embebidos.

### Alternativa con servidor

```bash
cd dev-tools/code-map && python3 -m http.server 8842
# http://127.0.0.1:8842
```

Cada vez que cambie el código, vuelve a correr `generate.sh` para refrescar
`graph.json` y el HTML standalone.

## Vistas

- **ARCHITECTURE** — el proyecto agregado por área real (core, engines, backend,
  frontend, utils, metrics, events, tests, devops, database, API), con el
  volumen de conexiones entre áreas.
- **FILES** — el grafo de archivos real: imports Python, `<script src>` en
  plantillas, llamadas `fetch()` del JS emparejadas contra las rutas Flask
  reales, y menciones de tablas SQL en consultas crudas.
- **MODULES** — los mismos archivos agrupados por carpeta real del repo.
- **IMPACT** — selecciona cualquier nodo y pulsa "▼ depende de" (todo lo que
  usa, transitivamente) o "▲ le afecta" (todo lo que se rompería si lo tocas).
- **HEALTH** — ciclos de imports, módulos más conectados, archivos sin ninguna
  conexión detectada, y candidatos a código sin uso (heurística sobre el grafo
  de imports — revisar antes de borrar, no es una confirmación).

## Qué detecta hoy

- 90 archivos Python (AST real): imports resueltos dentro del paquete `RUANA`,
  clases + métodos, funciones de módulo, y las 176 rutas Flask (`@app.route`)
  con sus métodos HTTP y función handler.
- 18 archivos JS: funciones top-level y llamadas `fetch('/api/...')`,
  enlazadas automáticamente a la ruta Flask real que golpean.
- 12 plantillas HTML: qué archivos JS cargan vía `<script src>`.
- 12 migraciones SQL de Supabase: tablas creadas (`CREATE TABLE`), y qué
  archivos `.py` las mencionan en SQL crudo (`FROM`, `INTO`, `UPDATE`, `JOIN`).

## Limitaciones conocidas

- Los edges JS→Python son por coincidencia de string de ruta (`fetch('/api/x')`
  ↔ `@app.route('/api/x')`), no por análisis de flujo real — rutas construidas
  dinámicamente con lógica compleja pueden no matchear.
- Las menciones de tablas SQL son regex sobre el código fuente, no un parser
  SQL real — puede haber falsos positivos si un identificador coincide por
  casualidad con un nombre de tabla.
- "Candidatos a código sin uso" es heurística basada solo en el grafo de
  imports estático: no detecta uso dinámico (`importlib`, `getattr`), ni scripts
  que se invocan como entry point standalone (`python script.py`) sin ser
  importados por nadie.
- No hay parser real de JavaScript (no hay import/export ES modules en este
  proyecto — todo son scripts `<script>` con patrón IIFE), así que el grafo JS
  es más superficial que el de Python.
- El layout (ForceAtlas2) corre en el hilo principal en memoria del navegador;
  con miles de nodos puede tardar 1–2s al cargar antes de estabilizarse.

## Archivos

- `scanner.py` — el escáner (solo lectura, no modifica nada del repo).
- `generate.sh` — regenera `graph.json` + `ruana-code-map.html`.
- `build_standalone.py` — empaqueta libs + grafo en un HTML autocontenido.
- `graph.json` — salida generada (se sobreescribe en cada regeneración).
- `ruana-code-map.html` — visor standalone (ábrelo en Brave a doble clic).
- `index.html` — el visor (modo servidor + compatible con JSON embebido).
- `vendor/code-map-libs.js` — bundle local de graphology, layouts y sigma.
