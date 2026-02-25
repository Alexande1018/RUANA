#!/usr/bin/env python3
"""
🚀 PREFLIGHT VALIDATOR - RUANA
Validador pre-operativo simplificado
Estructura adaptada desde AceroTradefinal
"""

import sys
import json
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

from utils.logger import setup_logger


class PreflightValidator:
    """Validador pre-operativo para RUANA"""
    
    def __init__(self):
        self.logger = setup_logger("preflight_validator", "logs")
        self.report = {
            "timestamp": datetime.utcnow().isoformat(),
            "tests": {},
            "warnings": [],
            "authorization": "ABORTED"
        }
        self.failed_tests = []
    
    def run_all_tests(self) -> bool:
        """Ejecuta todas las pruebas y retorna True si todo pasa"""
        self.logger.info("")
        self.logger.info("=" * 80)
        self.logger.info("🚀 PREFLIGHT VALIDATOR - RUANA")
        self.logger.info("=" * 80)
        self.logger.info("")
        
        # A. Validar estructura de archivos
        self._test_file_structure()
        
        # B. Validar configuración
        self._test_configuration()
        
        # C. Validar directorios
        self._test_directories()
        
        # Generar reporte final
        all_passed = len(self.failed_tests) == 0
        self.report["authorization"] = "READY" if all_passed else "ABORTED"
        self._generate_report()
        
        if all_passed:
            self.logger.info("")
            self.logger.info("=" * 80)
            self.logger.info("✅ RUANA listo para ejecutar")
            self.logger.info("=" * 80)
            self.logger.info("")
        else:
            self.logger.error("")
            self.logger.error("=" * 80)
            self.logger.error(f"❌ VALIDACIÓN FALLIDA - {len(self.failed_tests)} test(s) fallaron")
            self.logger.error("=" * 80)
            self.logger.error("")
        
        return all_passed
    
    def _test_file_structure(self):
        """A. Validar estructura de archivos"""
        self.logger.info("📁 A. Validando estructura de archivos...")
        
        # A1. Validar config/ruana_reglas_v1.json
        try:
            config_file = BASE_DIR / "config" / "ruana_reglas_v1.json"
            if config_file.exists():
                with open(config_file, 'r') as f:
                    config = json.load(f)
                    if config:
                        self._mark_test("A1_config_file", True, "config/ruana_reglas_v1.json existente")
                    else:
                        self._mark_test("A1_config_file", False, "config vacío")
            else:
                self._mark_test("A1_config_file", False, "config/ruana_reglas_v1.json no encontrado")
        except Exception as e:
            self._mark_test("A1_config_file", False, f"Error: {str(e)}")
        
        # A2. Validar directorio logs/
        try:
            logs_dir = BASE_DIR / "logs"
            if logs_dir.exists():
                self._mark_test("A2_logs_dir", True, "logs/ existente")
            else:
                logs_dir.mkdir(exist_ok=True)
                self._mark_test("A2_logs_dir", True, "logs/ creado")
        except Exception as e:
            self._mark_test("A2_logs_dir", False, f"Error: {str(e)}")
        
        # A3. Validar módulos principales existen
        try:
            core_modules = [
                "core/orquestador.py",
                "core/db_manager.py",
                "core/preflight_validator.py"
            ]
            
            missing = []
            for module in core_modules:
                module_path = BASE_DIR / module
                if not module_path.exists():
                    missing.append(module)
            
            if len(missing) == 0:
                self._mark_test("A3_core_modules", True, "Módulos core presentes")
            else:
                self._mark_test("A3_core_modules", False, f"Módulos faltantes: {', '.join(missing)}")
        except Exception as e:
            self._mark_test("A3_core_modules", False, f"Error: {str(e)}")
    
    def _test_configuration(self):
        """B. Validar configuración"""
        self.logger.info("⚙️  B. Validando configuración...")
        
        # B1. config/ruana_reglas_v1.json es válido JSON
        try:
            config_file = BASE_DIR / "config" / "ruana_reglas_v1.json"
            if config_file.exists():
                with open(config_file, 'r') as f:
                    config = json.load(f)
                    self._mark_test("B1_config_json", True, "JSON válido")
            else:
                self._mark_test("B1_config_json", False, "Archivo no encontrado")
        except json.JSONDecodeError as e:
            self._mark_test("B1_config_json", False, f"JSON inválido: {str(e)}")
        except Exception as e:
            self._mark_test("B1_config_json", False, f"Error: {str(e)}")
        
        # B2. config tiene fields básicos
        try:
            config_file = BASE_DIR / "config" / "ruana_reglas_v1.json"
            if config_file.exists():
                with open(config_file, 'r') as f:
                    config = json.load(f)
                    # Solo validar que es un dict válido
                    if isinstance(config, dict):
                        self._mark_test("B2_config_fields", True, "Estructura válida")
                    else:
                        self._mark_test("B2_config_fields", False, "Config no es un diccionario")
            else:
                self._mark_test("B2_config_fields", False, "Archivo no encontrado")
        except Exception as e:
            self._mark_test("B2_config_fields", False, f"Error: {str(e)}")
    
    def _test_directories(self):
        """C. Validar directorios"""
        self.logger.info("📂 C. Validando directorios...")
        
        required_dirs = [
            "core",
            "engines",
            "metrics",
            "config",
            "logs",
            "tests"
        ]
        
        missing = []
        for dir_name in required_dirs:
            dir_path = BASE_DIR / dir_name
            if not dir_path.exists():
                missing.append(dir_name)
        
        if len(missing) == 0:
            self._mark_test("C1_directories", True, "Todos los directorios presentes")
        else:
            self._mark_test("C1_directories", False, f"Directorios faltantes: {', '.join(missing)}")
    
    def _mark_test(self, test_name: str, passed: bool, message: str):
        """Marca un test como pasado o fallido"""
        self.report["tests"][test_name] = {
            "status": "OK" if passed else "FAIL",
            "message": message
        }
        
        if not passed:
            self.failed_tests.append(test_name)
            self.logger.error(f"  ❌ {test_name}: {message}")
        else:
            self.logger.info(f"  ✅ {test_name}: {message}")
    
    def _generate_report(self):
        """Genera el reporte final en JSON"""
        report_path = BASE_DIR / "preflight_report.json"
        
        try:
            with open(report_path, 'w') as f:
                json.dump(self.report, f, indent=2)
            
            self.logger.info(f"📄 Reporte generado: {report_path}")
        except Exception as e:
            self.logger.error(f"❌ Error generando reporte: {e}")


def main() -> str:
    """
    Función principal del validador pre-operativo
    
    Returns:
        "READY" si todas las validaciones pasan, "ABORTED" si falla algo
    """
    validator = PreflightValidator()
    success = validator.run_all_tests()
    
    # Retornar estado en lugar de hacer sys.exit
    return "READY" if success else "ABORTED"


def run_preflight() -> str:
    """
    Ejecuta el preflight validator y retorna el estado
    
    Returns:
        "READY" o "ABORTED"
    """
    return main()


if __name__ == "__main__":
    result = main()
    sys.exit(0 if result == "READY" else 1)
