#!/usr/bin/env python3
"""
🎯 ORQUESTADOR - RUANA
Sistema modular de evaluación y ejecución
Estructura adaptada desde AceroTradefinal (sin lógica de trading)
"""

import sys
import json
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Any

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

from utils.logger import setup_logger
from core.preflight_validator import run_preflight
from core.db_manager import get_db
from engines.motor_evaluacion import MotorEvaluacion
from metrics.collector import MetricsCollector
from events.event_bus import EventBus


class Orquestador:
    """Orquestador principal - Sistema vacío para RUANA"""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Inicializa el orquestador
        
        Args:
            config_path: Path a config JSON (ej: "config/ruana_reglas_v1.json")
                        Si es None, usa valores por defecto
        """
        self.logger = setup_logger("orquestador", "logs")
        
        # Cargar configuración
        if config_path is None:
            config_path = str(BASE_DIR / "config" / "ruana_reglas_v1.json")
        
        self.config = self._load_config(config_path)
        
        # Inicializar EventBus para registro de eventos
        self.event_bus = EventBus(logger=self.logger)
        
        # Inicializar componentes del motor
        self.metrics_collector = MetricsCollector(logger=self.logger)
        self.motor = MotorEvaluacion(config=self.config, logger=self.logger, event_bus=self.event_bus)
        
        # Estado inicial
        self.ctrader_connected = False
        self.shutdown_requested = False
        self.ciclos_ejecutados = 0
        self.operaciones_realizadas = 0
        
        # Capital inicial (stub)
        self.capital_inicial = self.config.get("capital", 1000.0)
        self.equity_actual = self.capital_inicial
        self.equity_max = self.capital_inicial
        
        # Métricas (stub)
        self.trades_ganadores = 0
        self.trades_perdedores = 0
        self.pnl_total = 0.0
        self.contador_racha_negativa = 0
        self.tiempo_inicio = datetime.now()
        
        # Log de inicialización
        self.logger.info("")
        self.logger.info("=" * 70)
        self.logger.info("🤖 RUANA - ORQUESTADOR v0.1")
        self.logger.info("=" * 70)
        self.logger.info(f"💰 Capital inicial: €{self.capital_inicial:.2f}")
        self.logger.info(f"📝 Configuración: {config_path}")
        self.logger.info("=" * 70)
        self.logger.info("")
    
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Carga la configuración desde JSON"""
        try:
            config_file = Path(config_path)
            if not config_file.exists():
                self.logger.warning(f"⚠️ Config no encontrado en {config_path}, usando defaults")
                return {"capital": 1000.0, "version": "1.0"}
            
            with open(config_file, 'r') as f:
                config = json.load(f)
            
            self.logger.info(f"✅ Configuración cargada: {config_file}")
            return config
        except Exception as e:
            self.logger.error(f"❌ Error cargando config: {e}")
            return {"capital": 1000.0, "version": "1.0"}
    
    def preflight(self) -> bool:
        """Ejecuta validación preflight y retorna True si pasa"""
        self.logger.info("")
        self.logger.info("🚀 Ejecutando PREFLIGHT...")
        
        result = run_preflight()
        
        if result == "READY":
            self.logger.info("✅ PREFLIGHT COMPLETADO")
            return True
        else:
            self.logger.error("❌ PREFLIGHT FALLIDO")
            return False
    
    def ejecutar_ciclo(self):
        """Ejecuta un ciclo con evaluación real del motor"""
        try:
            self.ciclos_ejecutados += 1
            
            # Log del ciclo
            self.logger.debug(f"🔄 Ciclo #{self.ciclos_ejecutados} iniciado")
            
            # INIT - Validar estado
            self.logger.debug("  [INIT] Validando estado del sistema...")
            
            # PREFLIGHT - Validar recursos
            self.logger.debug("  [PREFLIGHT] Verificando disponibilidad de recursos...")
            
            # LOOP - Procesar datos con motor real
            self.logger.debug("  [LOOP] Evaluando aliados...")
            
            # Recolectar métricas
            metricas = self.metrics_collector.collect()
            
            # Evaluar con motor
            if metricas:
                decisiones = self.motor.evaluate_all(metricas, self.config)
                
                # Log de resultados
                for decision in decisiones:
                    self.operaciones_realizadas += 1
            
            self.logger.debug(f"    - Capital: €{self.equity_actual:.2f}")
            self.logger.debug(f"    - Operaciones: {self.operaciones_realizadas}")
            
            # EXIT - Limpieza
            self.logger.debug("  [EXIT] Limpiando estado...")
            
            self.logger.debug(f"✅ Ciclo #{self.ciclos_ejecutados} completado")
            
        except KeyboardInterrupt:
            raise
        except Exception as e:
            self.logger.error(f"❌ Error en ciclo: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
    
    def detener(self):
        """Detiene el orquestador"""
        self.logger.info("")
        self.logger.info("=" * 70)
        self.logger.info("🛑 DETENIENDO RUANA...")
        self.logger.info("=" * 70)
        
        # Mostrar resumen
        tiempo_operativo = (datetime.now() - self.tiempo_inicio).total_seconds() / 60.0
        self.logger.info(f"⏱️  Tiempo operativo: {tiempo_operativo:.1f} minutos")
        self.logger.info(f"🔄 Ciclos ejecutados: {self.ciclos_ejecutados}")
        self.logger.info(f"💰 Capital final: €{self.equity_actual:.2f}")
        
        self.logger.info("=" * 70)
        self.logger.info("✅ RUANA detenido")


def main():
    """Función principal"""
    orquestador = None
    
    try:
        # INIT: Crear orquestador
        orquestador = Orquestador()
        
        # PREFLIGHT: Validar sistema
        if not orquestador.preflight():
            orquestador.logger.error("❌ Sistema no listo, abortando")
            return
        
        # LOOP: Ejecutar ciclos vacíos
        orquestador.logger.info("")
        orquestador.logger.info("=" * 70)
        orquestador.logger.info("▶️  INICIANDO CICLOS VACÍOS")
        orquestador.logger.info("=" * 70)
        orquestador.logger.info("")
        
        ciclos = 0
        max_ciclos = 5  # Ejecutar 5 ciclos como demo
        
        while ciclos < max_ciclos:
            try:
                if orquestador.shutdown_requested:
                    break
                
                orquestador.ejecutar_ciclo()
                ciclos += 1
                
                # Pequeña pausa entre ciclos
                time.sleep(2)
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                orquestador.logger.error(f"❌ Error en ciclo: {e}")
                time.sleep(2)
        
        # EXIT: Detener
        if orquestador:
            orquestador.detener()
        
        orquestador.logger.info("")
        orquestador.logger.info("✅ RUANA finalizó correctamente")
        
    except KeyboardInterrupt:
        orquestador.logger.info("")
        orquestador.logger.info("🛑 Detenimiento manual solicitado")
        if orquestador:
            orquestador.detener()
    except Exception as e:
        if orquestador:
            orquestador.logger.error(f"❌ Error fatal: {e}")
            import traceback
            orquestador.logger.error(traceback.format_exc())
        else:
            print(f"❌ Error fatal: {e}")


if __name__ == "__main__":
    main()
