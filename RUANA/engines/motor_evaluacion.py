"""
Motor de evaluación del sistema RUANA v0.2
Evalúa aliados contra criterios y mantiene memoria institucional en SQLite
"""

from datetime import datetime
from pathlib import Path
import sys

# Importar gestor de base de datos
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.db_manager import get_db


class MotorEvaluacion:
    """Motor de evaluación RUANA v0.2 con persistencia en SQLite"""
    
    def __init__(self, config=None, logger=None, event_bus=None):
        """Inicializa motor"""
        self.config = config or {}
        self.logger = logger
        self.event_bus = event_bus  # EventBus opcional para registrar eventos
        self.db = get_db()  # Instancia de base de datos
    
    def evaluate_all(self, metricas: dict, reglas: dict = None) -> list:
        """
        Evalúa todos los aliados en las métricas contra los filtros
        
        Args:
            metricas: dict con estructura {"aliado_codigo": {métricas}}
            reglas: dict con reglas (no usado por ahora)
        
        Returns:
            list: Lista de decisiones estructuradas (guardadas en SQLite)
        """
        decisiones = []
        
        # Evaluar cada aliado en las métricas
        for aliado_codigo, aliado_metrics in metricas.items():
            decision = self._evaluar_aliado(aliado_codigo, aliado_metrics)
            
            # Incorporar persistencia desde SQLite
            decision = self._incorporar_persistencia(aliado_codigo, decision)
            
            # Guardar evaluación en SQLite
            self.db.guardar_evaluacion(
                codigo_aliado=aliado_codigo,
                estado=decision["estado"],
                score=decision["score"],
                intencion=decision["intencion"],
                tasa_respuesta=aliado_metrics.get("tasa_respuesta", 0.0),
                tasa_confirmacion=aliado_metrics.get("tasa_confirmacion", 0.0),
                meses_sin_trabajo=aliado_metrics.get("meses_sin_trabajo", 0),
                ciclos_consecutivos=decision.get("persistencia", {}).get("ciclos", 1),
                razones=decision["razones"],
                severidad=decision.get("severidad", "normal")
            )
            
            decisiones.append(decision)
            
            # Registrar evento en EventBus si está disponible
            if self.event_bus:
                evento = {
                    "timestamp": datetime.now().isoformat(),
                    "aliado_codigo": aliado_codigo,
                    "estado": decision["estado"],
                    "score": decision["score"],
                    "delta_score": decision.get("delta_score", 0),
                    "severidad": decision.get("severidad", "normal"),
                    "persistencia": decision.get("persistencia", {}),
                    "origen": "motor_evaluacion",
                    "version_motor": "0.2"
                }
                self.event_bus.register_event(evento)
            
            # Log de la decisión
            if self.logger:
                ciclos = decision.get("persistencia", {}).get("ciclos", 1)
                severidad = decision.get("severidad", "normal")
                
                self.logger.info(
                    f"[MOTOR] Aliado {aliado_codigo} → "
                    f"estado={decision['estado'].upper()} "
                    f"score={decision['score']:.1f} "
                    f"({ciclos} ciclos consecutivos)"
                )
                
                # Log adicional si severidad != normal
                if severidad == "alerta":
                    self.logger.warning(
                        f"[MOTOR][ALERTA] Aliado {aliado_codigo} → "
                        f"{ciclos} ciclos {decision['estado'].upper()}"
                    )
                elif severidad == "critico":
                    self.logger.error(
                        f"[MOTOR][CRITICO] Aliado {aliado_codigo} → "
                        f"{ciclos} ciclos {decision['estado'].upper()}"
                    )
        
        return decisiones
    
    def _evaluar_aliado(self, aliado_codigo: str, metrics: dict) -> dict:
        """
        Evalúa un aliado individual contra los 3 filtros
        
        FILTROS (orden fijo):
        1. tasa_respuesta >= 0.70
        2. tasa_confirmacion >= 0.80
        3. meses_sin_trabajo <= 6
        
        DECISIÓN:
        - 3 filtros OK → "verde", "mantener"
        - 2 filtros OK → "amarillo", "vigilar"
        - ≤1 filtro OK → "rojo", "evaluar_suplencia"
        """
        razones = []
        filtros_ok = 0
        
        # Extraer métricas con valores por defecto
        tasa_respuesta = metrics.get("tasa_respuesta", 0.0)
        tasa_confirmacion = metrics.get("tasa_confirmacion", 0.0)
        meses_sin_trabajo = metrics.get("meses_sin_trabajo", 999)
        
        # FILTRO 1: tasa_respuesta >= 0.70
        if tasa_respuesta >= 0.70:
            filtros_ok += 1
        else:
            razones.append(f"Respuesta {tasa_respuesta*100:.0f}% < 70%")
        
        # FILTRO 2: tasa_confirmacion >= 0.80
        if tasa_confirmacion >= 0.80:
            filtros_ok += 1
        else:
            razones.append(f"Confirmación {tasa_confirmacion*100:.0f}% < 80%")
        
        # FILTRO 3: meses_sin_trabajo <= 6
        if meses_sin_trabajo <= 6:
            filtros_ok += 1
        else:
            razones.append(f"Meses sin trabajo {meses_sin_trabajo} > 6")
        
        # Calcular score
        score = (filtros_ok / 3.0) * 100.0
        
        # Asignar estado e intención según filtros OK
        if filtros_ok == 3:
            estado = "verde"
            intencion = "mantener"
        elif filtros_ok == 2:
            estado = "amarillo"
            intencion = "vigilar"
        else:  # filtros_ok <= 1
            estado = "rojo"
            intencion = "evaluar_suplencia"
        
        # Construir decision (estructura obligatoria)
        decision = {
            "aliado_codigo": aliado_codigo,
            "estado": estado,
            "intencion": intencion,
            "score": score,
            "razones": razones
        }
        
        return decision
    
    def get_active_symbols(self) -> list:
        """Retorna símbolos activos (stub para compatibilidad)"""
        return []
    
    # ════════════════════════════════════════════════════════════════════
    # MÉTODOS DE PERSISTENCIA (v0.2 - SQLite)
    # ════════════════════════════════════════════════════════════════════
    
    def _incorporar_persistencia(self, aliado_codigo: str, decision: dict) -> dict:
        """
        Incorpora información de persistencia desde SQLite a la decisión:
        - ciclos_consecutivos
        - tendencia
        - severidad
        
        Calcula basándose en el histórico en la BD.
        """
        # Obtener evaluación anterior de SQLite
        evaluacion_anterior = self.db.obtener_evaluacion(aliado_codigo)
        
        # Extraer datos de decisión actual
        estado_actual = decision["estado"]
        score_actual = decision["score"]
        
        # Si no hay evaluación anterior, es el primer ciclo
        if not evaluacion_anterior:
            ciclos_consecutivos = 1
            tendencia = "nueva"
        else:
            estado_anterior = evaluacion_anterior.get("estado")
            score_anterior = evaluacion_anterior.get("score", 0.0)
            
            # Calcular ciclos consecutivos
            if estado_actual == estado_anterior:
                # Mismo estado → incrementar contador
                ciclos_consecutivos = evaluacion_anterior.get("ciclos_consecutivos", 1) + 1
            else:
                # Estado cambió → resetear a 1
                ciclos_consecutivos = 1
            
            # Calcular tendencia
            if score_actual == score_anterior:
                tendencia = "estable"
            elif score_actual > score_anterior:
                tendencia = "mejora"
            else:
                tendencia = "empeora"
        
        # Evaluar severidad
        severidad = self._evaluar_severidad(estado_actual, ciclos_consecutivos)
        
        # Añadir bloque de persistencia a la decisión
        decision["persistencia"] = {
            "ciclos": ciclos_consecutivos,
            "tendencia": tendencia
        }
        
        # Añadir severidad
        decision["severidad"] = severidad
        
        # Delta para score operativo (aliados.score): verde +, amarillo -, rojo -
        base = {"verde": self.config.get("motor_delta_verde", 5),
                "amarillo": self.config.get("motor_delta_amarillo", -3),
                "rojo": self.config.get("motor_delta_rojo", -8)}
        delta = base.get(estado_actual, 0)
        if severidad == "critico":
            mult = self.config.get("motor_severidad_critico_multiplicador", 1.5)
            delta = int(round(delta * mult))
        decision["delta_score"] = delta
        
        return decision
    
    def _evaluar_severidad(self, estado: str, ciclos: int) -> str:
        """
        Evalúa la severidad según persistencia.
        
        REGLAS (orden obligatorio, NO duplicar):
        1. "critico" SI: (estado=="rojo" AND ciclos>=2) OR (estado=="amarillo" AND ciclos>=6)
        2. "alerta" SI: estado=="amarillo" AND ciclos>=3 (y NO es critico)
        3. "normal" EN CUALQUIER OTRO CASO
        
        Args:
            estado: str - "verde", "amarillo" o "rojo"
            ciclos: int - ciclos consecutivos en este estado
        
        Returns:
            str - "normal", "alerta" o "critico"
        """
        # Regla 1: CRÍTICO
        if (estado == "rojo" and ciclos >= 2) or (estado == "amarillo" and ciclos >= 6):
            return "critico"
        
        # Regla 2: ALERTA
        if estado == "amarillo" and ciclos >= 3:
            return "alerta"
        
        # Regla 3: NORMAL (cualquier otro caso)
        return "normal"
