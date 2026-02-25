#!/usr/bin/env python3
"""
📝 LOGGER - RUANA
Sistema simple de logging para terminal y archivo
Adaptado desde AceroTradefinal
"""

import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional


def setup_logger(name: str = "ruana", log_dir: str = "logs", subdir: Optional[str] = None) -> logging.Logger:
    """
    Configura un logger simple
    
    Args:
        name: Nombre del logger
        log_dir: Directorio para logs
        subdir: Subdirectorio opcional
        
    Returns:
        Logger configurado
    """
    # Calcular ruta relativa al proyecto
    current_file = Path(__file__).resolve()
    project_root = current_file.parent.parent
    log_path = project_root / log_dir
    if subdir:
        log_path = log_path / subdir
    log_path.mkdir(parents=True, exist_ok=True)
    
    # Crear logger (singleton por nombre)
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    # Evitar duplicados de handlers
    if logger.handlers:
        return logger
    
    # Handler para terminal
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    subdir_prefix = f"[{subdir.upper()}] " if subdir else ""
    console_format = logging.Formatter(
        f'[%(asctime)s] [%(levelname)s] [RUANA] {subdir_prefix}%(message)s',
        datefmt='%H:%M:%S'
    )
    console_handler.setFormatter(console_format)
    
    # Handler para archivo
    log_file = log_path / f"{name}_{datetime.now().strftime('%Y%m%d')}.log"
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    file_format = logging.Formatter(
        '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_format)
    
    # Agregar handlers
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    
    return logger
