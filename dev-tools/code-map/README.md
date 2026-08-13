# RUANA — Mapa del territorio

Explorador visual tipo **Google Earth** del proyecto real.

> Si existe en RUANA, debe poder encontrarse.

## Ver

```bash
bash dev-tools/code-map/generate.sh
python3 dev-tools/code-map/serve.py
# http://127.0.0.1:8842
```

Standalone (Brave): `dev-tools/code-map/ruana-code-map.html`

## Niveles (zoom semántico)

0 Planeta → 1 Continentes (dominios) → 2–3 Carpetas → 4 Archivos → 5 Símbolos → 6 Código

## Modos

- **Explorar** — recorrido espacial
- **X-Ray** — más relaciones visibles
- **Auditoría / Encuéntrame todo** — huérfanos, señales, no clasificados

## Principios

- Inventario real (no inventa módulos)
- Diferencia Hecho / Detección / Inferencia / Desconocido
- «Sin clasificar» nunca se oculta
- Solo lectura (+ `/api/src` para inspeccionar código)

## Archivos

- `scanner.py` · `serve.py` · `generate.sh` · `build_standalone.py`
- `index.html` · `graph.json` · `ruana-code-map.html`
