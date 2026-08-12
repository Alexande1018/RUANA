"""Servicio de dominio catalogo (Campamento Base).

Extracción progresiva desde DBManager. Las fachadas permanecen en DBManager.
SQL de catálogo vía CatalogoRepo.
"""
from __future__ import annotations

from pathlib import Path

from core.db_constants import RUANA_ROOT

import json
import sqlite3
from typing import Any, Dict, List, Optional

from core.repositories.catalogo_repo import CatalogoRepo

_repo = CatalogoRepo()

# --- Extraído de DBManager (catalogo) ---

def _normalizar_texto_catalogo(texto: str) -> str:
    """Normaliza texto de catálogo: minúsculas, sin acentos ni espacios duplicados."""
    import re
    import unicodedata
    raw = unicodedata.normalize("NFD", str(texto or "").strip().lower())
    sin_acentos = "".join(c for c in raw if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", sin_acentos).strip()

def _resolver_en_conjunto_catalogo(db, valor: str, permitidos: set) -> Optional[str]:
    """Devuelve la forma canónica del catálogo si valor coincide (exacto o sin acentos)."""
    valor = (valor or "").strip()
    if not valor or not permitidos:
        return None
    if valor in permitidos:
        return valor
    objetivo = db._normalizar_texto_catalogo(valor)
    for item in permitidos:
        if db._normalizar_texto_catalogo(item) == objetivo:
            return item
    return None

def oficio_en_catalogo(db, oficio: str) -> bool:
    """True si el oficio está en el catálogo oficial RUANA (comparación normalizada)."""
    if not oficio or not str(oficio).strip():
        return False
    catalogo = db.get_catalogo_oficios_ruana()
    permitidos = {str(o).strip() for o in catalogo if o and str(o).strip()}
    return db._resolver_en_conjunto_catalogo(str(oficio).strip(), permitidos) is not None

def obtener_oficios_grupo(db, grupo_id: int) -> set:
    """Devuelve el conjunto de oficios presentes en el grupo (aliados activos)."""
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            rows = _repo.listar_oficios_distintos_grupo_activo(cursor, grupo_id)
            return {row[0].strip() for row in rows if row[0]}
        except Exception:
            return set()
        finally:
            conn.close()

def get_catalogo_oficios_ruana(db) -> List[str]:
    """Devuelve el catálogo de oficios RUANA (nombres de oficio principal). Compatible con formato jerárquico o lista plana."""
    try:
        config_path = RUANA_ROOT / 'config' / 'oficios_ruana.json'
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            oficios = data.get('oficios', [])
            if isinstance(oficios, list) and oficios:
                out = []
                for o in oficios:
                    if isinstance(o, dict) and o.get('nombre'):
                        out.append(str(o['nombre']).strip())
                    elif isinstance(o, str) and o.strip():
                        out.append(str(o).strip())
                if out:
                    return out
    except Exception:
        pass
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            rows = _repo.listar_oficios_distintos_todos(cursor)
            return [row[0].strip() for row in rows if row[0]]
        except Exception:
            return []
        finally:
            conn.close()

def get_catalogo_oficios_jerarquico(db) -> List[Dict[str, Any]]:
    """Devuelve el catálogo jerárquico: lista de { nombre, especializaciones: [] }. Compatible con lista plana (una esp = nombre)."""
    try:
        config_path = RUANA_ROOT / 'config' / 'oficios_ruana.json'
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            oficios = data.get('oficios', [])
            if isinstance(oficios, list) and oficios:
                out = []
                for o in oficios:
                    if isinstance(o, dict) and o.get('nombre'):
                        esp = o.get('especializaciones') or [o['nombre']]
                        if isinstance(esp, list):
                            esp = [str(e).strip() for e in esp if str(e).strip()]
                        else:
                            esp = [str(o['nombre']).strip()]
                        out.append({'nombre': str(o['nombre']).strip(), 'especializaciones': esp})
                    elif isinstance(o, str) and o.strip():
                        n = str(o).strip()
                        out.append({'nombre': n, 'especializaciones': [n]})
                if out:
                    return out
    except Exception:
        pass
    # Fallback: desde BD solo tenemos nombres
    nombres = db.get_catalogo_oficios_ruana()
    return [{'nombre': n, 'especializaciones': [n]} for n in nombres]

def listar_catalogo_servicios_aliado(db, codigo_aliado: str) -> List[Dict[str, Any]]:
    """
    Devuelve hasta 10 posiciones del catálogo privado del aliado.
    Siempre retorna 10 elementos (1..10), configurados o vacíos.
    """
    codigo = (codigo_aliado or '').strip()
    if not codigo:
        return [{'posicion': i, 'descripcion': None, 'precio': None, 'configurado': False} for i in range(1, 11)]
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            rows = _repo.listar_servicios_aliado(cursor, codigo)
            by_pos = {}
            for row in rows:
                item = dict(row)
                pos = int(item.get('posicion') or 0)
                desc = (item.get('descripcion') or '').strip() or None
                price = (item.get('precio') or '').strip() or None
                by_pos[pos] = {
                    'posicion': pos,
                    'descripcion': desc,
                    'precio': price,
                    'configurado': bool(desc and price),
                    'actualizado_en': item.get('actualizado_en'),
                }
            out: List[Dict[str, Any]] = []
            for pos in range(1, 11):
                out.append(by_pos.get(pos) or {
                    'posicion': pos,
                    'descripcion': None,
                    'precio': None,
                    'configurado': False,
                    'actualizado_en': None,
                })
            return out
        except Exception:
            return [{'posicion': i, 'descripcion': None, 'precio': None, 'configurado': False} for i in range(1, 11)]
        finally:
            if conn:
                conn.close()

def guardar_catalogo_servicio_aliado(db,
    codigo_aliado: str,
    posicion: int,
    descripcion: Optional[str],
    precio: Optional[str],
) -> Dict[str, Any]:
    """
    Guarda una posición (1..10) del catálogo privado del aliado.
    """
    codigo = (codigo_aliado or '').strip()
    if not codigo:
        return {'status': 'error', 'message': 'Código de aliado requerido'}
    try:
        pos = int(posicion)
    except Exception:
        return {'status': 'error', 'message': 'Posición inválida'}
    if pos < 1 or pos > 10:
        return {'status': 'error', 'message': 'Posición inválida'}

    desc = (descripcion or '').strip()
    pr = (precio or '').strip()
    if len(desc) > 1000:
        return {'status': 'error', 'message': 'La descripción supera el límite de 1000 caracteres'}
    if len(pr) > 120:
        return {'status': 'error', 'message': 'El precio supera el límite permitido'}

    # Permitir guardar vacío como "no configurado"
    desc_db = desc if desc else None
    pr_db = pr if pr else None
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            cursor = conn.cursor()
            if not _repo.existe_aliado(cursor, codigo):
                return {'status': 'error', 'message': f'Aliado {codigo} no encontrado'}
            _repo.upsert_servicio_aliado(cursor, codigo, pos, desc_db, pr_db)
            conn.commit()
            return {
                'status': 'success',
                'message': 'Servicio guardado',
                'servicio': {
                    'posicion': pos,
                    'descripcion': desc_db,
                    'precio': pr_db,
                    'configurado': bool(desc_db and pr_db),
                }
            }
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
        finally:
            if conn:
                conn.close()

def contar_oficios_ocupados(db) -> int:
    """Cuenta oficios distintos cubiertos por aliados activos (oficio principal)."""
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            return _repo.contar_oficios_ocupados(cursor)
        except Exception:
            return 0
        finally:
            conn.close()

def puede_ver_catalogo_aliado(db, visor_codigo: str, objetivo_codigo: str) -> bool:
    """Catálogo privado visible al propio aliado, directorio o contacto activo."""
    visor = (visor_codigo or '').strip()
    objetivo = (objetivo_codigo or '').strip()
    if not visor or not objetivo:
        return False
    if visor == objetivo:
        return True
    for aliado in db.listar_aliados_directorio_grupo(visor):
        if (aliado.get('codigo') or '').strip() == objetivo:
            return True
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT 1 FROM contactos_ruana
                WHERE ((solicitante_codigo = ? AND profesional_codigo = ?)
                    OR (solicitante_codigo = ? AND profesional_codigo = ?))
                  AND estado NOT IN ('trabajo_cerrado', 'no_concretado', 'cerrado_no_concretado')
                LIMIT 1
                """,
                (visor, objetivo, objetivo, visor),
            )
            return cursor.fetchone() is not None
        except Exception:
            return False
        finally:
            if conn:
                conn.close()


def listar_catalogo_servicios_configurados(db, codigo_aliado: str) -> List[Dict[str, Any]]:
    """Solo posiciones con descripción y precio (para elegir al contactar)."""
    return [s for s in db.listar_catalogo_servicios_aliado(codigo_aliado) if s.get('configurado')]

