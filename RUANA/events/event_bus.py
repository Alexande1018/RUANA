"""
EventBus - Sistema central de registro de eventos
Persiste evaluaciones del motor en formato JSONL
"""

import json
from pathlib import Path
from datetime import datetime


class EventBus:
    """
    Bus de eventos interno para RUANA.
    Registra eventos de evaluación en archivo JSONL (logs/eventos_ruana.jsonl).
    """
    
    def __init__(self, logger=None, events_file: str = None):
        """
        Inicializa el EventBus.
        
        Args:
            logger: Logger instance (puede ser None)
            events_file: Ruta al archivo de eventos (default: logs/eventos_ruana.jsonl)
        """
        self.logger = logger
        
        # Determinar ruta del archivo de eventos
        if events_file:
            self.events_file = Path(events_file)
        else:
            # Default: logs/eventos_ruana.jsonl
            self.events_file = Path(__file__).parent.parent / "logs" / "eventos_ruana.jsonl"
        
        # Asegurar que el directorio logs/ existe
        self.events_file.parent.mkdir(parents=True, exist_ok=True)
        
        if self.logger:
            self.logger.debug(f"📨 EventBus inicializado: {self.events_file}")
    
    def register_event(self, evento: dict) -> None:
        """
        Registra un evento en el archivo JSONL.
        
        Args:
            evento: dict con estructura:
                {
                    "timestamp": ISO8601,
                    "aliado_id": str,
                    "estado": str,
                    "score": float,
                    "severidad": str,
                    "persistencia": {"ciclos": int, "tendencia": str},
                    "origen": str,
                    "version_motor": str
                }
        """
        try:
            # Asegurar que timestamp existe
            if "timestamp" not in evento:
                evento["timestamp"] = datetime.now().isoformat()
            
            # Escribir como línea JSON (JSONL)
            with open(self.events_file, 'a') as f:
                json.dump(evento, f, default=str)
                f.write('\n')
            
            if self.logger:
                self.logger.debug(
                    f"📨 Evento registrado: {evento.get('aliado_id', '?')} "
                    f"→ {evento.get('severidad', '?')}"
                )
        
        except Exception as e:
            # Loggear error sin romper la aplicación
            if self.logger:
                self.logger.warning(f"⚠️ Error registrando evento: {e}")
