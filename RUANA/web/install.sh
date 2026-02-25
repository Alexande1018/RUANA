#!/bin/bash
# RUANA Dashboard - Script de instalación rápida
# macOS / Linux

set -e

echo "=========================================="
echo "🎨 RUANA Dashboard - Instalación"
echo "=========================================="

# Cambiar a directorio web
cd "$(dirname "$0")"

echo ""
echo "📍 Ubicación: $(pwd)"
echo ""

# Verificar Python
echo "🐍 Verificando Python..."
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 no está instalado"
    exit 1
fi
echo "✅ Python 3 encontrado"

# Crear venv si no existe
if [ ! -d "venv" ]; then
    echo ""
    echo "📦 Creando entorno virtual..."
    python3 -m venv venv
    echo "✅ Entorno virtual creado"
fi

# Activar venv
echo ""
echo "🔌 Activando entorno virtual..."
source venv/bin/activate
echo "✅ Entorno virtual activado"

# Instalar dependencias
echo ""
echo "📥 Instalando dependencias..."
pip install -q -r requirements.txt
echo "✅ Dependencias instaladas"

# Crear datos de ejemplo
echo ""
echo "📊 Creando datos de ejemplo..."
python3 run.py &
sleep 2
kill $! 2>/dev/null || true

echo ""
echo "=========================================="
echo "✅ Instalación completada!"
echo "=========================================="
echo ""
echo "Para iniciar el dashboard:"
echo "  cd $(pwd)"
echo "  source venv/bin/activate"
echo "  python3 run.py"
echo ""
echo "Luego abre: http://localhost:5000"
echo ""
