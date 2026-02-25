"""
RUANA Dashboard - Ejemplos de Integración
Cómo conectar el dashboard con el motor de evaluación

⚠️ ACTUALIZACIÓN: Todos los datos ahora se persisten en SQLite (ruana.db)
No se utiliza más estado_aliados.json
"""

# ============================================================
# EJEMPLO 1: Usar el motor de evaluación con SQLite
# ============================================================
"""
El motor_evaluacion.py ahora guarda automáticamente en SQLite:
- db.guardar_evaluacion() guarda la evaluación
- db.obtener_evaluacion() recupera el estado actual
- db.obtener_estadisticas_evaluaciones() obtiene estadísticas

Los endpoints de app.py acceden directamente a los datos desde SQLite.
"""

def ejemplo_motor_con_sqlite():
    """
    Ejemplo de cómo el motor_evaluacion.py usa SQLite
    """
    from core.db_manager import get_db
    from engines.motor_evaluacion import MotorEvaluacion
    
    # Inicializar motor (ahora con SQLite)
    motor = MotorEvaluacion()
    
    # Evaluar aliados
    metricas = {
        'A001': {'tasa_respuesta': 0.85, 'tasa_confirmacion': 0.90, 'meses_sin_trabajo': 2},
        'A002': {'tasa_respuesta': 0.65, 'tasa_confirmacion': 0.70, 'meses_sin_trabajo': 8},
    }
    
    decisiones = motor.evaluate_all(metricas)
    
    # Las evaluaciones se guardaron automáticamente en SQLite
    # Ahora puedo recuperarlas:
    db = get_db()
    eval_a001 = db.obtener_evaluacion('A001')
    print(f"Evaluación de A001: {eval_a001['estado']} (score: {eval_a001['score']})")


# ============================================================
# EJEMPLO 2: Consultar datos desde los endpoints
# ============================================================
"""
Los nuevos endpoints en app.py permiten acceder a SQLite:
"""

def ejemplo_endpoints_sqlite():
    """
    Ejemplos de endpoints disponibles
    """
    endpoints_nuevos = {
        'GET /api/aliados': 'Retorna lista de aliados desde SQLite',
        'GET /api/aliados/<id>': 'Detalle de un aliado',
        'GET /api/evaluaciones': 'Lista evaluaciones (filtra por estado)',
        'GET /api/evaluaciones/<codigo_aliado>': 'Evaluación actual de un aliado',
        'GET /api/evaluaciones/<codigo_aliado>/historico': 'Histórico de cambios',
        'GET /api/evaluaciones/estadisticas': 'Estadísticas generales',
        'POST /api/aliados/registrar': 'Registrar nuevo aliado',
    }
    
    for endpoint, descripcion in endpoints_nuevos.items():
        print(f"{endpoint}: {descripcion}")
    return datos


# ============================================================
# EJEMPLO 3: Llamar exportación automáticamente
# ============================================================
"""
Ubicación: core/orquestador.py

En el método principal que ejecuta evaluaciones.
"""

def ejecutar_evaluacion_completa(self):
    """Ejecuta evaluación y exporta para dashboard"""
    
    # ... código existente de evaluación ...
    
    # Exportar para dashboard
    if hasattr(self.motor_evaluacion, 'guardar_para_dashboard'):
        self.motor_evaluacion.guardar_para_dashboard()
        print("✅ Dashboard actualizado con nuevas evaluaciones")
    
    # ... resto del código ...


# ============================================================
# EJEMPLO 4: Endpoint API personalizado
# ============================================================
"""
Ubicación: web/app.py (agregar esta ruta)

Endpoint para ejecutar evaluación desde el dashboard.
"""

@app.route('/api/evaluar', methods=['POST'])
def triguer_evaluation():
    """
    POST /api/evaluar
    Dispara una nueva ronda de evaluación
    
    Requiere:
    - Authorization header (en versión segura)
    
    Response 200:
    {
        "status": "success",
        "message": "Evaluación iniciada",
        "timestamp": "2026-02-05T10:30:00"
    }
    """
    try:
        # Importar orquestador
        from core.orquestador import Orquestador
        
        # Instanciar
        orq = Orquestador()
        
        # Ejecutar
        orq.ejecutar_evaluacion_completa()
        
        return jsonify({
            'status': 'success',
            'message': 'Evaluación completada',
            'timestamp': datetime.now().isoformat()
        }), 200
    
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


# ============================================================
# EJEMPLO 5: Event Bus Integration
# ============================================================
"""
Ubicación: events/event_bus.py (agregar método)

Notificar al dashboard cuando hay cambios.
"""

def on_evaluation_complete(self, evento):
    """Handler cuando evaluación se completa"""
    
    # Datos del evento
    aliado_id = evento.get('aliado_id')
    nuevo_estado = evento.get('nuevo_estado')
    cambio_score = evento.get('cambio_score')
    
    # Loguear para auditoría
    self.logger.info(
        f"Cambio de estado en aliado {aliado_id}: "
        f"{evento.get('estado_anterior')} → {nuevo_estado} "
        f"(Score: {cambio_score:+.1f})"
    )
    
    # En versión futura: enviar WebSocket al dashboard
    # socket.emit('aliado_actualizado', {
    #     'aliado_id': aliado_id,
    #     'nuevo_estado': nuevo_estado
    # })


# ============================================================
# EJEMPLO 6: Importar datos del dashboard a evaluador
# ============================================================
"""
Ubicación: core/motor_evaluacion.py (método nuevo)

Para casos donde se editan evaluaciones desde dashboard.
"""

def actualizar_desde_feedback(self, aliado_id: str, feedback: dict):
    """
    Actualiza evaluación con feedback del usuario
    
    Args:
        aliado_id: ID del aliado
        feedback: {
            'notas': 'Observaciones usuario',
            'score_ajuste': -5,  # Ajuste manual
            'nuevo_estado': 'observacion'
        }
    """
    
    if aliado_id not in self.estado_institucional:
        return False
    
    aliado = self.estado_institucional[aliado_id]
    
    # Aplicar cambios
    if 'notas' in feedback:
        aliado['notas_feedback'] = feedback['notas']
        aliado['fecha_feedback'] = datetime.now().isoformat()
    
    if 'score_ajuste' in feedback:
        original = aliado.get('score_final', 50)
        nuevo = max(0, min(100, original + feedback['score_ajuste']))
        aliado['score_final'] = nuevo
    
    if 'nuevo_estado' in feedback:
        aliado['estado'] = feedback['nuevo_estado']
    
    # Guardar cambios
    self._guardar_estado()
    
    # Registrar evento
    if self.event_bus:
        self.event_bus.emit({
            'tipo': 'evaluacion_actualizada_manualmente',
            'aliado_id': aliado_id,
            'cambios': feedback
        })
    
    return True


# ============================================================
# EJEMPLO 7: Estructura de datos completa (Referencia)
# ============================================================
"""
Esto es lo que espera el dashboard:

estado_aliados.json
{
  "ultima_actualizacion": "2026-02-05T10:30:00",
  "aliados": [
    {
      "id": 1,
      "nombre": "Carlos Mendoza",
      "referencia": "CM-001",
      "oficio": "Carpintería",
      "zona": "Centro",
      "score": 92,                          # 0-100, resultado evaluación
      "estado": "recomendado",              # recomendado|observacion|riesgo
      "descripcion": "Excelente desempeño",  # Resumen evaluación
      "especialidades": "Muebles, restauración",
      "contacto": "+57 300 123 4567",
      "suplente": null  # O { nombre, referencia, score, estado, razon }
    }
  ]
}

Campo por campo:

id (int)
  - ID único del aliado
  - Debe ser consistente entre ejecuciones
  - Usado para referencias internas

nombre (str)
  - Nombre completo del aliado
  - Mostrado en tarjeta y modal
  - Searchable

referencia (str)
  - Código único (ej: CM-001)
  - Identificador humano-legible
  - Searchable

oficio (str)
  - Especialidad principal
  - Usado para filtros
  - Ejemplos: Carpintería, Plomería, Electricidad

zona (str)
  - Ubicación geográfica
  - Usado para filtros
  - Ejemplos: Centro, Norte, Sur, Este, Occidente

score (int, 0-100)
  - Métrica principal de evaluación
  - Resultado del motor_evaluacion
  - Usado para ordenamiento
  - Mostrado prominentemente en tarjeta
  - Determina color parcialmente (junto con estado)

estado (str)
  - "recomendado": 80-100 puntos, confío
  - "observacion": 60-79 puntos, vigilo
  - "riesgo": 0-59 puntos, cuidado

descripcion (str)
  - Resumen textual de la evaluación
  - Síntesis de por qué tiene este score
  - Máximo 200 caracteres para brevedad

especialidades (str)
  - Servicios específicos que ofrece
  - Ejemplos: "Muebles a medida, restauración"
  - Información adicional

contacto (str)
  - Teléfono, email o ambos
  - Usado para contacto directo
  - Mostrado en modal

suplente (dict | null)
  - null: Sin suplente
  - dict: Tiene suplente activo
    - nombre: Nombre suplente
    - referencia: Su código
    - score: Su evaluación
    - estado: Su estado
    - razon: Por qué es suplente
  - Cuando existe, renderiza split card
"""


# ============================================================
# EJEMPLO 8: Testing integración
# ============================================================
"""
Ubicación: tests/test_dashboard_integration.py

Unit tests para verificar integración.
"""

import json
import pytest
from pathlib import Path

def test_export_to_dashboard():
    """Verifica que export genera estructura correcta"""
    from core.motor_evaluacion import MotorEvaluacion
    
    motor = MotorEvaluacion()
    resultado = motor.export_to_dashboard()
    
    assert 'ultima_actualizacion' in resultado
    assert 'aliados' in resultado
    assert isinstance(resultado['aliados'], list)
    
    if resultado['aliados']:
        aliado = resultado['aliados'][0]
        assert 'id' in aliado
        assert 'nombre' in aliado
        assert 'score' in aliado
        assert 'estado' in aliado
        assert 0 <= aliado['score'] <= 100
        assert aliado['estado'] in ['recomendado', 'observacion', 'riesgo']

def test_guardar_para_dashboard():
    """Verifica que archivo se crea correctamente"""
    from core.motor_evaluacion import MotorEvaluacion
    
    motor = MotorEvaluacion()
    datos = motor.guardar_para_dashboard()
    
    # Verificar archivo existe
    state_file = Path('state/estado_aliados.json')
    assert state_file.exists()
    
    # Verificar contenido
    with open(state_file) as f:
        guardado = json.load(f)
    
    assert guardado == datos

def test_mapeo_estado_score():
    """Verifica que scores mapean a estados correctamente"""
    from core.motor_evaluacion import MotorEvaluacion
    
    motor = MotorEvaluacion()
    
    assert motor._mapear_estado(90) == 'recomendado'
    assert motor._mapear_estado(70) == 'observacion'
    assert motor._mapear_estado(40) == 'riesgo'
    assert motor._mapear_estado(80) == 'recomendado'  # Límite inferior
    assert motor._mapear_estado(60) == 'observacion'  # Límite inferior
"""

# ============================================================
# EJEMPLO 9: Deploy script
# ============================================================
"""
Ubicación: scripts/deploy_dashboard.sh

Script para desplegar dashboard en producción.
"""

#!/bin/bash

# RUANA Dashboard - Deploy Script
# Ejecutar en servidor de producción

set -e

echo "🚀 RUANA Dashboard - Deploy"

# Directorio
DASHBOARD_DIR="/var/www/ruana-dashboard"

# 1. Descargar código
cd $DASHBOARD_DIR
git pull origin main

# 2. Instalar dependencias
pip install -r web/requirements.txt

# 3. Recolectar datos
python3 web/run.py

# 4. Reiniciar servicio
systemctl restart ruana-dashboard

# 5. Verificar salud
curl -f http://localhost:5000/api/health || exit 1

echo "✅ Dashboard desplegado exitosamente"


# ============================================================
# EJEMPLO 10: Actualización automática de datos
# ============================================================
"""
Ubicación: core/scheduler.py (nuevo archivo)

Ejecutar evaluaciones periódicamente.
"""

from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime

class EvaluationScheduler:
    def __init__(self, orquestrador):
        self.orquestrador = orquestrador
        self.scheduler = BackgroundScheduler()
    
    def start(self):
        """Inicia scheduler de evaluaciones"""
        # Ejecutar cada día a las 2 AM
        self.scheduler.add_job(
            func=self.ejecutar_evaluacion,
            trigger="cron",
            hour=2,
            minute=0,
            id='evaluacion_diaria'
        )
        self.scheduler.start()
    
    def ejecutar_evaluacion(self):
        """Ejecuta evaluación y actualiza dashboard"""
        try:
            print(f"[{datetime.now()}] Iniciando evaluación automática...")
            self.orquestrador.ejecutar_evaluacion_completa()
            print(f"[{datetime.now()}] ✅ Evaluación completada")
        except Exception as e:
            print(f"[{datetime.now()}] ❌ Error en evaluación: {e}")

# Uso en main:
if __name__ == '__main__':
    from core.orquestador import Orquestador
    
    orq = Orquestador()
    scheduler = EvaluationScheduler(orq)
    scheduler.start()
    
    # Mantener running
    while True:
        pass
"""

# ============================================================
# FIN DE EJEMPLOS
# ============================================================
"""
Estos ejemplos muestran cómo:

1. ✅ Exportar datos del motor al formato dashboard
2. ✅ Guardar en JSON para que lee el servidor
3. ✅ Llamar automáticamente después de evaluación
4. ✅ Crear endpoint para disparar evaluaciones
5. ✅ Integrar con EventBus para notificaciones
6. ✅ Actualizar evaluaciones desde feedback del dashboard
7. ✅ Estructura exacta de datos esperada
8. ✅ Tests para verificar integración
9. ✅ Deploy en producción
10. ✅ Actualizaciones automáticas

Para preguntas o ayuda, revisa TECHNICAL.md
"""
