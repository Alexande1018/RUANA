#!/usr/bin/env python3
"""
Script de demostración del Dashboard RUANA
Genera datos de ejemplo y lanza el servidor web
"""

import sys
import subprocess
from pathlib import Path
from datetime import datetime

# Datos de ejemplo para demostración
DATOS_EJEMPLO = {
    "ultima_actualizacion": datetime.now().isoformat(),
    "aliados": [
        {
            "id": 1,
            "nombre": "Carlos Mendoza",
            "referencia": "CM-001",
            "oficio": "Carpintería",
            "zona": "Centro",
            "score": 92,
            "estado": "recomendado",
            "descripcion": "Excelente desempeño, todas las métricas positivas",
            "especialidades": "Muebles a medida, restauración",
            "contacto": "+57 300 123 4567",
            "suplente": None
        },
        {
            "id": 2,
            "nombre": "Ana García",
            "referencia": "AG-002",
            "oficio": "Plomería",
            "zona": "Norte",
            "score": 78,
            "estado": "observacion",
            "descripcion": "Desempeño aceptable, requiere seguimiento",
            "especialidades": "Instalación, mantenimiento",
            "contacto": "+57 300 234 5678",
            "suplente": {
                "nombre": "Roberto López",
                "referencia": "RL-012",
                "score": 85,
                "estado": "recomendado",
                "razon": "Disponibilidad mejorada"
            }
        },
        {
            "id": 3,
            "nombre": "Miguel Torres",
            "referencia": "MT-003",
            "oficio": "Electricidad",
            "zona": "Sur",
            "score": 45,
            "estado": "riesgo",
            "descripcion": "Incumplimientos recientes, en evaluación",
            "especialidades": "Instalaciones residenciales",
            "contacto": "+57 300 345 6789",
            "suplente": {
                "nombre": "Javier Ruiz",
                "referencia": "JR-018",
                "score": 88,
                "estado": "recomendado",
                "razon": "Reemplazo activo"
            }
        },
        {
            "id": 4,
            "nombre": "Laura Domínguez",
            "referencia": "LD-004",
            "oficio": "Pintura",
            "zona": "Occidente",
            "score": 89,
            "estado": "recomendado",
            "descripcion": "Desempeño consistente y confiable",
            "especialidades": "Pintura interior y exterior, decoración",
            "contacto": "+57 300 456 7890",
            "suplente": None
        },
        {
            "id": 5,
            "nombre": "Francisco Gutiérrez",
            "referencia": "FG-005",
            "oficio": "Carpintería",
            "zona": "Centro",
            "score": 72,
            "estado": "observacion",
            "descripcion": "Rendimiento variable, en seguimiento",
            "especialidades": "Puertas, ventanas",
            "contacto": "+57 300 567 8901",
            "suplente": None
        },
        {
            "id": 6,
            "nombre": "Patricia Morales",
            "referencia": "PM-006",
            "oficio": "Limpieza",
            "zona": "Este",
            "score": 81,
            "estado": "recomendado",
            "descripcion": "Servicio de calidad, cumplimiento total",
            "especialidades": "Limpieza residencial y comercial",
            "contacto": "+57 300 678 9012",
            "suplente": None
        },
        {
            "id": 7,
            "nombre": "Diego Rodríguez",
            "referencia": "DR-007",
            "oficio": "Plomería",
            "zona": "Norte",
            "score": 52,
            "estado": "riesgo",
            "descripcion": "Problemas de puntualidad, en revisión",
            "especialidades": "Reparación de fugas",
            "contacto": "+57 300 789 0123",
            "suplente": {
                "nombre": "Andrés Pérez",
                "referencia": "AP-015",
                "score": 91,
                "estado": "recomendado",
                "razon": "Reemplazo activo"
            }
        },
        {
            "id": 8,
            "nombre": "Mónica Sánchez",
            "referencia": "MS-008",
            "oficio": "Electricidad",
            "zona": "Sur",
            "score": 86,
            "estado": "recomendado",
            "descripcion": "Profesional confiable y experimentada",
            "especialidades": "Instalaciones comerciales, reparaciones",
            "contacto": "+57 300 890 1234",
            "suplente": None
        },
        {
            "id": 9,
            "nombre": "Alberto Vega",
            "referencia": "AV-009",
            "oficio": "Carpintería",
            "zona": "Occidente",
            "score": 77,
            "estado": "observacion",
            "descripcion": "Mejorando, resultados prometedores",
            "especialidades": "Muebles, carpintería general",
            "contacto": "+57 300 901 2345",
            "suplente": None
        },
        {
            "id": 10,
            "nombre": "Verónica Castro",
            "referencia": "VC-010",
            "oficio": "Pintura",
            "zona": "Este",
            "score": 94,
            "estado": "recomendado",
            "descripcion": "Excelencia en ejecución, altamente recomendado",
            "especialidades": "Todo tipo de pintura y acabados",
            "contacto": "+57 300 012 3456",
            "suplente": None
        }
    ]
}


def main():
    """Función principal"""
    print("=" * 70)
    print("🎨 RUANA Dashboard - Demostración")
    print("=" * 70)

    # Instalar dependencias
    print("\n📦 Verificando dependencias...")
    try:
        import flask  # noqa: F401
        print("✅ Flask está instalado")
    except ImportError:
        print("📥 Instalando Flask...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"]
        )
        print("✅ Dependencias instaladas")
    # Lanzar servidor
    print("\n" + "=" * 70)
    print("🚀 Iniciando servidor...")
    print("=" * 70)
    print("\n📍 Dashboard disponible en: http://localhost:5000")
    print("🛑 Presione Ctrl+C para detener el servidor\n")
    
    try:
        # Cambiar a directorio del web
        web_dir = Path(__file__).parent
        import os
        os.chdir(web_dir)
        
        # Importar y ejecutar Flask
        from app import app
        # Importante: desactivar el reloader automático y limitar el host
        # a localhost para evitar conflictos de permisos en este entorno.
        app.run(
            host='127.0.0.1',
            port=5000,
            debug=False,
            use_reloader=False,
        )
    except KeyboardInterrupt:
        print("\n\n✅ Servidor detenido correctamente")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
