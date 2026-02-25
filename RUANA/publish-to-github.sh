#!/bin/bash
# Publicar RUANA en GitHub - ejecutar desde la raíz del proyecto
set -e
REPO_DIR="/Users/alex/Desktop/RUANA"
REMOTE="https://github.com/Alexander8860/RUANA.git"

cd "$REPO_DIR"

echo "=== 1. Git ==="
if ! git rev-parse --git-dir 2>/dev/null; then
  git init -b main
  echo "   OK: repositorio inicializado."
else
  echo "   Git ya inicializado."
fi

echo ""
echo "=== 2. Añadir archivos y commit ==="
git add .
git branch -M main
if ! git diff --cached --quiet 2>/dev/null || ! git rev-parse HEAD 2>/dev/null; then
  git commit -m "Initial commit RUANA"
  echo "   OK: commit creado."
fi

echo ""
echo "=== 3. Remote y push ==="
git remote remove origin 2>/dev/null || true
git remote add origin "$REMOTE"
git push -u origin main

echo ""
echo "=== Listo: publicado en https://github.com/Alexander8860/RUANA ==="
