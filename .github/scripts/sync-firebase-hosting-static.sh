#!/usr/bin/env bash
# Copia assets 100% estáticos a firebase-public/static para que Hosting
# los sirva sin pasar por Cloud Run. Excluye /static/uploads (archivos de usuario).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SRC="${ROOT}/RUANA/web/static"
DEST="${ROOT}/firebase-public/static"

if [[ ! -d "$SRC" ]]; then
  echo "No existe ${SRC}" >&2
  exit 1
fi

rm -rf "$DEST"
mkdir -p "$DEST"

# Copia portable (sin rsync): todo excepto uploads de usuario.
while IFS= read -r -d '' rel; do
  rel="${rel#./}"
  mkdir -p "$(dirname "${DEST}/${rel}")"
  cp -p "${SRC}/${rel}" "${DEST}/${rel}"
done < <(cd "$SRC" && find . -type f ! -path './uploads/*' -print0)

mkdir -p "${DEST}/uploads"
if [[ -f "${SRC}/uploads/.gitkeep" ]]; then
  cp "${SRC}/uploads/.gitkeep" "${DEST}/uploads/.gitkeep"
fi

if [[ -d "${DEST}/uploads" ]] && find "${DEST}/uploads" -type f ! -name '.gitkeep' | grep -q .; then
  echo "ERROR: firebase-public/static/uploads contiene archivos de usuario; no se publica." >&2
  exit 1
fi

if [[ ! -f "${DEST}/css/ruana-fonts.css" ]]; then
  echo "ERROR: falta ruana-fonts.css en el paquete de Hosting." >&2
  exit 1
fi
if [[ ! -f "${DEST}/fonts/plus-jakarta-sans-latin-wght-normal.woff2" ]]; then
  echo "ERROR: falta la fuente Plus Jakarta Sans en el paquete de Hosting." >&2
  exit 1
fi

count="$(find "$DEST" -type f | wc -l | tr -d ' ')"
echo "Firebase Hosting static: ${count} archivos copiados a ${DEST} (uploads de usuario excluidos)."
