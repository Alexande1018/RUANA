#!/usr/bin/env python3
"""
RUANA Dashboard - Quick Start Guide
Guía ejecutable para comenzar rápidamente
"""

def print_header():
    print("""
╔════════════════════════════════════════════════════════════╗
║                   RUANA DASHBOARD v1.0                    ║
║          Red Unida de Apoyo para Negocios                ║
║                  Quick Start Guide                        ║
╚════════════════════════════════════════════════════════════╝
    """)

def print_intro():
    print("""
🎨 BIENVENIDO AL DASHBOARD RUANA

Este es un dashboard profesional y minimalista para:
  ✓ Evaluar aliados de forma visual
  ✓ Tomar decisiones en 5 segundos
  ✓ Comparar titular vs suplente
  ✓ Filtrar por zona, oficio, estado
  ✓ Ver scores RUANA destacados

NO es:
  ✗ Red social
  ✗ CRM
  ✗ Sistema de messaging
    """)

def print_installation():
    print("""
📦 INSTALACIÓN RÁPIDA

OPCIÓN 1: Script automático (Recomendado)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
macOS/Linux:
  $ cd /Users/alex/Desktop/RUANA/web
  $ chmod +x install.sh
  $ ./install.sh

Windows:
  > cd C:\\Users\\alex\\Desktop\\RUANA\\web
  > install.bat


OPCIÓN 2: Manual
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  $ cd web
  $ python3 -m venv venv
  $ source venv/bin/activate  # o 'venv\\Scripts\\activate' en Windows
  $ pip install -r requirements.txt
  $ python3 run.py


OPCIÓN 3: Con Docker (Próxima versión)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  $ docker build -t ruana-dashboard .
  $ docker run -p 5000:5000 ruana-dashboard
    """)

def print_first_run():
    print("""
🚀 PRIMER USO

1. Ejecuta el script de instalación
2. Abre en navegador: http://localhost:5000
3. Ves una "mesa de aliados" con tarjetas
4. Cada tarjeta es un aliado evaluado
5. Score RUANA: 0-100, prominente
6. Colores = estado:
   🟢 Verde  = Recomendado
   🟡 Amarillo = En Observación  
   🔴 Rojo   = En Riesgo

¡Listo! Ahora explora:
  → Usa filtros para ver solo ciertos aliados
  → Ordena por score (mejor arriba)
  → Clickea una tarjeta para ver detalles
  → Si hay suplente, lo ves lado a lado
    """)

def print_features():
    print("""
✨ CARACTERÍSTICAS PRINCIPALES

FILTROS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  🔍 Zona: Centro, Norte, Sur, Este, Occidente
  🏢 Oficio: Carpintería, Plomería, Electricidad, etc.
  📊 Estado: Recomendado, En Observación, En Riesgo
  🔎 Búsqueda: Nombre o referencia del aliado

ORDENAMIENTO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ⬇️  Score (Mayor a menor) - Default, mejores primero
  ⬆️  Score (Menor a mayor)
  🔤 Nombre (A-Z)

TARJETAS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Nombre y referencia
  Oficio y zona
  Score prominente (barra visual)
  Estado con dot indicador
  Suplente si aplica (split card)

MODAL DETALLES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Click en tarjeta → Ver detalles completos
  Información extendida del aliado
  Comparación con suplente si existe
    """)

def print_ui_guide():
    print("""
🎯 GUÍA RÁPIDA DE UI

SECCIONES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

HEADER (Arriba)
  RUANA | Red Unida...
  Stats: Total | Recomendados | En Riesgo

FILTROS (Debajo header)
  [Zona] [Oficio] [Estado] [Búsqueda] [Limpiar]
  Ordenar: [Score ▼]

GRID DE CARDS (Centro)
  Tarjetas de aliados
  Colores indican estado
  Hover: sube y resalta

MODAL (Popup)
  Detalles completos
  Click X o fuera → Cierra

FOOTER (Abajo)
  © RUANA 2026

COLORES Y SIGNIFICADO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  🟢 Verde (#22c55e)
     Significado: RECOMENDADO - Confío, es bueno
     Dónde: Badges, scores altos, bordes tarjetas
  
  🟡 Amarillo (#eab308)
     Significado: EN OBSERVACIÓN - Vigilado
     Dónde: Badges de estado, bordes amarillas
  
  🔴 Rojo (#ef4444)
     Significado: EN RIESGO - Cuidado, hay suplente
     Dónde: Badges en riesgo, label suplente

INTERACCIONES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Cambiar filtro
    → Grid actualiza al instante
    → Stats se recalculan

  Buscar
    → Filtra por nombre o referencia
    → En tiempo real

  Ordenar
    → Reordena tarjetas
    → Mantiene filtros

  Click tarjeta
    → Abre modal con detalles

  Click X o fuera modal
    → Cierra modal

  Click "Limpiar"
    → Resetea todos los filtros
    """)

def print_filesystem():
    print("""
📁 ESTRUCTURA DE ARCHIVOS

web/
├── 📄 index.html              ← Página principal (abrela en navegador)
├── 🐍 app.py                  ← Servidor Flask (corre con run.py)
├── 🚀 run.py                  ← Script para iniciar todo
├── 📋 requirements.txt        ← Dependencias Python
│
├── 📂 static/
│   ├── 📂 css/
│   │   └── 🎨 styles.css     ← Todos los estilos (dark mode, glassmorphism)
│   │
│   └── 📂 js/
│       └── ⚙️  dashboard.js    ← Lógica JavaScript (filtros, renderizado)
│
├── 📚 README.md               ← Documentación general
├── 🎨 DESIGN_GUIDE.md         ← Guía visual y de diseño
├── 🔧 TECHNICAL.md            ← Documentación técnica avanzada
└── 🗺️  ROADMAP.md             ← Planes futuros y mejoras

ARCHIVOS DE DATOS
state/
└── 📊 estado_aliados.json    ← Datos persistentes de aliados
    (Se crea automáticamente al ejecutar run.py)
    """)

def print_troubleshooting():
    print("""
🔧 SOLUCIÓN DE PROBLEMAS

PROBLEMA: "Python no encontrado"
SOLUCIÓN:
  - Instala Python 3.8+ desde python.org
  - En terminal: python3 --version (debe ser 3.8+)
  - En Windows: python --version

PROBLEMA: "ModuleNotFoundError: No module named 'flask'"
SOLUCIÓN:
  - Asegúrate de estar en el venv activado
  - Corre: pip install -r requirements.txt
  - En Windows: pip.exe install...

PROBLEMA: "Port 5000 already in use"
SOLUCIÓN:
  - Mata otros procesos en 5000: lsof -ti:5000 | xargs kill -9
  - O ejecuta en puerto diferente (edita run.py)

PROBLEMA: "No aparecen datos en el dashboard"
SOLUCIÓN:
  - Abre Console en Developer Tools (F12)
  - Mira si hay errores rojos
  - Verifica que /api/aliados retorne datos
  - Revisa que estado_aliados.json exista

PROBLEMA: "Dashboard se ve feo/mal formateado"
SOLUCIÓN:
  - Actualiza navegador (Ctrl+F5 o Cmd+Shift+R)
  - Limpia cache del navegador
  - Usa navegador moderno (Chrome, Firefox, Safari recientes)

PROBLEMA: "Filtros no funcionan"
SOLUCIÓN:
  - Abre Console (F12), mira errores
  - Recarga página
  - Intenta "Limpiar" filtros primero

PROBLEMA: "¿Cómo cambio los datos de ejemplo?"
SOLUCIÓN:
  - Los datos están en web/run.py (constante DATOS_EJEMPLO)
  - O en state/estado_aliados.json (archivo JSON)
  - Edita, guarda, recarga navegador
    """)

def print_next_steps():
    print("""
🎓 PRÓXIMOS PASOS

PASO 1: Familiarízate con la interfaz
  → Juega con filtros
  → Ordena de diferentes formas
  → Abre modales

PASO 2: Personaliza datos
  → Edita DATOS_EJEMPLO en run.py
  → O edita estado_aliados.json
  → Recarga la página

PASO 3: Integra con tu sistema
  → Lee TECHNICAL.md
  → Conecta tu motor_evaluacion
  → Exporta resultados a JSON

PASO 4: Deploya a producción
  → Lee TECHNICAL.md section "Deployment"
  → Usa Gunicorn + Nginx
  → Configura SSL/TLS

PASO 5: Feedback y mejoras
  → Reporta bugs
  → Sugiere features
  → Lee ROADMAP.md para planes futuros

PARA APRENDER MÁS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  📖 README.md           - Documentación principal
  🎨 DESIGN_GUIDE.md     - Decisiones visuales
  🔧 TECHNICAL.md        - Arquitectura y API
  🗺️  ROADMAP.md         - Qué viene después
    """)

def print_support():
    print("""
💬 SOPORTE Y COMUNIDAD

PROBLEMAS O DUDAS
  → Lee la documentación primero
  → Chequea el archivo TECHNICAL.md
  → Revisa la sección de troubleshooting

SUGERIR FEATURES
  → Abre issue en GitHub
  → O envía email al team

REPORTAR BUGS
  → Describe qué hiciste
  → Qué esperabas que pasara
  → Qué pasó en realidad
  → Tu navegador y OS

QUIERO CUSTOMIZAR EL DISEÑO
  → Lee DESIGN_GUIDE.md
  → Edita colors en styles.css
  → Las fuentes están en Google Fonts
  → ¡Mantel que sea profesional!

QUIERO AGREGAR FEATURES
  → Crea un fork
  → Haz cambios en una rama
  → Envía pull request
  → ¡Contribuciones bienvenidas!
    """)

def print_footer():
    print("""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ✨ RUANA Dashboard v1.0
  📍 Profesional. Minimalista. Decisiones Rápidas.
  📅 Creado: 5 de febrero de 2026
  🔗 Proyecto: RUANA Core
  
  Gracias por usar RUANA Dashboard 🙌

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    """)

def main():
    print_header()
    print_intro()
    print_installation()
    print_first_run()
    print_features()
    print_ui_guide()
    print_filesystem()
    print_troubleshooting()
    print_next_steps()
    print_support()
    print_footer()

if __name__ == '__main__':
    main()
