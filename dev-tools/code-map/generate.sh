#!/usr/bin/env bash
# RUANA Code Map — regenerar el grafo a partir del código REAL del repo.
# Uso: bash dev-tools/code-map/generate.sh
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PYTHON_BIN="${PYTHON_BIN:-python3}"

echo "[code-map] escaneando el repositorio real…"
"$PYTHON_BIN" "$HERE/scanner.py"

echo ""
echo "[code-map] listo. graph.json actualizado en $HERE/graph.json"
echo ""
echo "Para verlo:"
echo "  cd $HERE && python3 -m http.server 8842"
echo "  abre http://localhost:8842 en el navegador"
echo ""
echo "(El visor usa fetch() para leer graph.json — no funciona abriendo index.html con doble clic, necesita un servidor local.)"
