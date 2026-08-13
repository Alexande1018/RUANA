#!/usr/bin/env bash
# RUANA Mapa — regenerar inventario + standalone
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"

echo "[mapa] escaneando territorio real…"
"$PYTHON_BIN" "$HERE/scanner.py"
echo "[mapa] empaquetando standalone…"
"$PYTHON_BIN" "$HERE/build_standalone.py"

echo ""
echo "[mapa] listo."
echo "  Ver con código profundo:"
echo "    python3 $HERE/serve.py"
echo "    http://127.0.0.1:8842"
echo "  O abre en Brave (doble clic):"
echo "    $HERE/ruana-code-map.html"
