#!/usr/bin/env bash
# RUANA Code Map — regenerar el grafo a partir del código REAL del repo.
# Uso: bash dev-tools/code-map/generate.sh
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PYTHON_BIN="${PYTHON_BIN:-python3}"

echo "[code-map] escaneando el repositorio real…"
"$PYTHON_BIN" "$HERE/scanner.py"

echo "[code-map] generando HTML standalone (Brave a doble clic)…"
"$PYTHON_BIN" "$HERE/build_standalone.py"

echo ""
echo "[code-map] listo."
echo "  graph.json  → $HERE/graph.json"
echo "  standalone  → $HERE/ruana-code-map.html"
echo ""
echo "Forma más fácil de verlo:"
echo "  abre $HERE/ruana-code-map.html en Brave (doble clic)"
echo ""
echo "Alternativa con servidor:"
echo "  cd $HERE && python3 -m http.server 8842"
echo "  abre http://127.0.0.1:8842"
