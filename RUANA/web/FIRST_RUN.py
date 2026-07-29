#!/usr/bin/env python3
"""
RUANA Dashboard - First Run Guide
Guía interactiva para primera ejecución
"""

import sys
import subprocess
from pathlib import Path

def clear_screen():
    """Limpia pantalla"""
    import os
    os.system('clear' if sys.platform != 'win32' else 'cls')

def print_banner():
    """Banner inicial"""
    print("""
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║          🎨 RUANA DASHBOARD - PRIMERA EJECUCIÓN         ║
║                                                           ║
║  Dashboard profesional para la Red Unida de Apoyo        ║
║  para Negocios entre Aliados                             ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
    """)

def check_python():
    """Verifica Python"""
    try:
        version = sys.version_info
        if version.major < 3 or (version.major == 3 and version.minor < 8):
            print("❌ Python 3.8+ es requerido")
            print(f"   Tienes: {version.major}.{version.minor}")
            return False
        print(f"✅ Python {version.major}.{version.minor} detectado")
        return True
    except:
        print("❌ Error verificando Python")
        return False

def check_structure():
    """Verifica estructura de carpetas"""
    web_dir = Path(__file__).parent
    required_files = ['index.html', 'app.py', 'requirements.txt']
    
    for file in required_files:
        if not (web_dir / file).exists():
            print(f"❌ Archivo faltante: {file}")
            return False
    
    print(f"✅ Estructura de carpetas correcta")
    return True

def check_venv():
    """Verifica/crea venv"""
    web_dir = Path(__file__).parent
    venv_dir = web_dir / 'venv'
    
    if venv_dir.exists():
        print(f"✅ Entorno virtual existe: {venv_dir}")
        return True
    
    print("📦 Creando entorno virtual...")
    try:
        subprocess.check_call([sys.executable, '-m', 'venv', str(venv_dir)])
        print(f"✅ Entorno virtual creado: {venv_dir}")
        return True
    except Exception as e:
        print(f"❌ Error creando venv: {e}")
        return False

def get_activate_command():
    """Retorna comando de activación según OS"""
    if sys.platform == 'win32':
        return r'venv\Scripts\activate.bat'
    else:
        return 'source venv/bin/activate'

def install_dependencies():
    """Instala dependencias"""
    web_dir = Path(__file__).parent
    req_file = web_dir / 'requirements.txt'
    
    if sys.platform == 'win32':
        python_cmd = 'python'
        pip_cmd = 'pip'
    else:
        python_cmd = 'python3'
        pip_cmd = 'pip3'
    
    print("📥 Instalando dependencias Flask...")
    try:
        # Intentar con venv primero
        venv_dir = web_dir / 'venv'
        if venv_dir.exists():
            if sys.platform == 'win32':
                pip_exe = venv_dir / 'Scripts' / 'pip.exe'
            else:
                pip_exe = venv_dir / 'bin' / 'pip'
            
            subprocess.check_call([str(pip_exe), 'install', '-q', '-r', str(req_file)])
        else:
            subprocess.check_call([pip_cmd, 'install', '-q', '-r', str(req_file)])
        
        print("✅ Dependencias instaladas")
        return True
    except Exception as e:
        print(f"❌ Error instalando dependencias: {e}")
        print("   Intenta manualmente: pip install -r requirements.txt")
        return False

def create_demo_data():
    """
    Datos de demostración (legacy - ahora se usan datos en SQLite)
    Esta función ya no es necesaria
    """
    print("✅ Los datos se almacenan ahora en SQLite (ruana.db)")
    return True

def print_launch_instructions():
    """Imprime instrucciones para lanzar"""
    print("\n" + "="*60)
    print("🚀 PARA LANZAR EL DASHBOARD")
    print("="*60)
    
    web_dir = Path(__file__).parent
    activate_cmd = get_activate_command()
    
    print(f"\n1️⃣  Abre una terminal en: {web_dir}")
    print(f"\n2️⃣  Activa el entorno virtual:")
    print(f"    $ {activate_cmd}")
    print(f"\n3️⃣  Lanza el servidor:")
    print(f"    $ python3 run.py")
    print(f"\n4️⃣  Abre en navegador:")
    print(f"    http://localhost:5000")
    print("\n" + "="*60)

def print_what_to_do():
    """Qué hacer en el dashboard"""
    print("\n" + "="*60)
    print("🎯 QUÉ HACER EN EL DASHBOARD")
    print("="*60)
    
    print("""
1. VER ALIADOS
   - Observa la "mesa de tarjetas" con aliados
   - Cada tarjeta es un aliado evaluado
   - Score 0-500 es la métrica principal

2. IDENTIFICAR ESTADOS
   🟢 Verde (Recomendado)     = Confío en este aliado
   🟡 Amarillo (Observación)  = Vigilado, pero OK
   🔴 Rojo (En Riesgo)        = Problema, ver suplente

3. USAR FILTROS
   - Zona: Centro, Norte, Sur, Este, Occidente
   - Oficio: Carpintería, Plomería, Electricidad
   - Estado: Recomendado, En Observación, En Riesgo
   - Búsqueda: Por nombre o referencia
   - "Limpiar" resetea todos los filtros

4. ORDENAR
   - Default: Score mayor a menor (mejores primero)
   - Puedes cambiar orden en dropdown "Ordenar por"

5. VER DETALLES
   - Click en una tarjeta abre modal completo
   - Información extendida del aliado
   - Si hay suplente, lo ves lado a lado

6. ENTENDER SPLIT CARDS
   - Si un aliado tiene suplente activo
   - Tarjeta se divide en 2 columnas
   - Izquierda: Titular con su score
   - Derecha: Suplente con su score
   - Compara visualmente

FILOSOFÍA
   Todo está diseñado para que en 5 segundos
   entiendas a quién recomendar.
    """)

def print_troubleshooting():
    """Solución de problemas"""
    print("\n" + "="*60)
    print("🔧 SI ALGO FALLA")
    print("="*60)
    
    print("""
"Python no encontrado"
  → Instala Python 3.8+ desde python.org
  → En terminal: python3 --version (debe ser 3.8+)

"ModuleNotFoundError: Flask"
  → Estás en el venv? Ejecuta: source venv/bin/activate
  → O: pip install -r requirements.txt

"Port 5000 already in use"
  → Otro proceso usa puerto 5000
  → En Mac: lsof -ti:5000 | xargs kill -9
  → O edita run.py y cambia puerto

"No aparecen datos"
  → Mira Console en Developer Tools (F12)
  → Busca errores rojos
  → Verifica que http://localhost:5000/api/aliados retorne JSON

"Dashboard se ve feo"
  → Ctrl+F5 (refresh hard) o Cmd+Shift+R en Mac
  → Limpia cache del navegador
  → Usa navegador moderno (Chrome, Firefox, Safari)
    """)

def print_next_resources():
    """Recursos para aprender"""
    print("\n" + "="*60)
    print("📚 PARA APRENDER MÁS")
    print("="*60)
    
    web_dir = Path(__file__).parent
    
    print(f"\nDirigete a: {web_dir}")
    print("\nLee estos archivos en orden:")
    print("  1. README.md              ← Descripción general")
    print("  2. QUICKSTART.py          ← Guía interactiva")
    print("  3. DESIGN_GUIDE.md        ← Decisiones visuales")
    print("  4. TECHNICAL.md           ← Arquitectura y API")
    print("  5. ROADMAP.md             ← Planes futuros")
    print("  6. INTEGRATION_EXAMPLES.py ← Código para integrar")

def main():
    """Función principal"""
    clear_screen()
    print_banner()
    
    # Verificaciones
    print("\n📋 Verificando sistema...\n")
    
    checks = [
        ("Python", check_python),
        ("Estructura", check_structure),
        ("Entorno virtual", check_venv),
        ("Dependencias", install_dependencies),
        ("Datos demo", create_demo_data),
    ]
    
    for name, check_func in checks:
        try:
            if not check_func():
                print(f"\n⚠️  Problema con {name}")
                print("   Intenta resolver manualmente")
        except Exception as e:
            print(f"❌ Error en {name}: {e}")
    
    # Instrucciones finales
    print_launch_instructions()
    print_what_to_do()
    print_troubleshooting()
    print_next_resources()
    
    print("\n" + "="*60)
    print("✅ LISTO PARA EMPEZAR!")
    print("="*60)
    print("\nSigue los pasos en la sección '🚀 PARA LANZAR EL DASHBOARD'")
    print("\n¡Que disfrutes el dashboard! 🎉\n")

if __name__ == '__main__':
    main()
