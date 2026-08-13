# RUANA Atlas

Mapa ligero del código **real** de RUANA. Navegas por capas (área → carpeta →
archivo) y el centro solo dibuja el **vecindario** del nodo elegido: qué
conecta con qué, sin renderizar los 400+ nodos a la vez.

## Cómo verlo

```bash
bash dev-tools/code-map/generate.sh
python3 dev-tools/code-map/serve.py
# http://127.0.0.1:8842
```

`serve.py` habilita **Ver código profundo** (`/api/src`).

### Sin servidor (Brave, doble clic)

```text
dev-tools/code-map/ruana-code-map.html
```

## Qué incluye

- Capas: áreas → carpetas → archivos
- Grafo enfocado: nodo + vecinos (ligero)
- Panel de conexiones: sale hacia / entra desde, tipadas
- Modos: Todo · Huérfanos · Sin uso · Calientes
- Símbolos del archivo (clases, métodos, funciones, rutas)
- Código fuente vía `serve.py`

## Archivos

- `scanner.py` — escáner (solo lectura)
- `generate.sh` — regenera `graph.json` + standalone
- `build_standalone.py` — HTML autocontenido
- `serve.py` — servidor + `/api/src`
- `index.html` / `ruana-code-map.html` / `graph.json`
- `vendor/code-map-libs.js`
