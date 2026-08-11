"""Helpers de catálogo de oficios (extraídos de web/app.py)."""

from __future__ import annotations

import json
from pathlib import Path


def catalogo_oficios_desde_archivo():
    """Lee el catálogo desde config/oficios_ruana.json. Devuelve lista de {nombre, especializaciones} o [].
    Especializaciones se incluyen por compatibilidad pero no se usan en la lógica de plaza.
    """
    try:
        config_path = Path(__file__).resolve().parent.parent / 'config' / 'oficios_ruana.json'
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            oficios = data.get('oficios', [])
            if isinstance(oficios, list) and oficios:
                out = []
                for o in oficios:
                    if isinstance(o, dict) and o.get('nombre'):
                        nombre = str(o['nombre']).strip()
                        esp = o.get('especializaciones') or []
                        if isinstance(esp, list):
                            esp = [str(e).strip() for e in esp if str(e).strip()]
                        else:
                            esp = []
                        out.append({'nombre': nombre, 'especializaciones': esp})
                    elif isinstance(o, str) and o.strip():
                        n = str(o).strip()
                        out.append({'nombre': n, 'especializaciones': []})
                return out if out else []
    except Exception:
        pass
    return []


# Alias compatible con el nombre original en app.py
_catalogo_oficios_desde_archivo = catalogo_oficios_desde_archivo
