"""Servicio de dominio referido (Campamento Base).

Extracción progresiva desde DBManager. Las fachadas permanecen en DBManager.
SQL de referidos vía ReferidoRepo.
"""
from __future__ import annotations

import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from core.repositories.referido_repo import ReferidoRepo

_repo = ReferidoRepo()

# --- Extraído de DBManager (referido) ---

def asignar_invitado_por(db,
    codigo_referido: str,
    codigo_invitador: str,
    origen: str = '',
    overwrite: bool = False,
) -> bool:
    """
    Fuente de verdad del linaje: escribe aliados.invitado_por_codigo
    y mantiene referidos en paralelo por compatibilidad.
    """
    codigo_referido = (codigo_referido or '').strip()
    codigo_invitador = (codigo_invitador or '').strip()
    origen = (origen or '').strip()
    if not codigo_referido or not codigo_invitador or codigo_referido == codigo_invitador:
        return False
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            cursor = conn.cursor()
            if not _repo.aliados_tiene_invitado_por(cursor):
                return False
            if overwrite:
                updated = _repo.update_invitado_por_overwrite(
                    cursor, codigo_invitador, origen, codigo_referido
                ) > 0
            else:
                updated = _repo.update_invitado_por_si_vacio(
                    cursor, codigo_invitador, origen, codigo_referido
                ) > 0
            if _repo.referidos_tiene_origen(cursor):
                _repo.insert_referido_con_origen(
                    cursor, codigo_referido, codigo_invitador, origen
                )
                if origen:
                    _repo.update_origen_si_vacio(cursor, origen, codigo_referido)
            else:
                _repo.insert_referido_sin_origen(
                    cursor, codigo_referido, codigo_invitador
                )
            conn.commit()
            return updated or cursor.rowcount > 0
        except Exception:
            return False
        finally:
            if conn:
                conn.close()

def backfill_invitado_por_linaje(db) -> Dict[str, int]:
    """Rellena invitado_por_codigo desde referidos/invitaciones y huérfanos bajo admin."""
    admin_codigo = db.obtener_codigo_admin_referidos()
    stats = {'desde_referidos': 0, 'desde_invitaciones': 0, 'huerfanos': 0}
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if not _repo.aliados_tiene_invitado_por(cursor):
                return stats
            has_origen = _repo.referidos_tiene_origen(cursor)
            if has_origen:
                rows = _repo.listar_pendientes_backfill_desde_referidos_con_origen(cursor)
            else:
                rows = _repo.listar_pendientes_backfill_desde_referidos_sin_origen(cursor)
        except Exception:
            rows = []
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
    for row in rows:
        if db.asignar_invitado_por(row['codigo_referido'], row['codigo_invitador'], (row['origen'] or 'aliado')):
            stats['desde_referidos'] += 1

    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            pendientes = _repo.listar_pendientes_backfill_desde_invitaciones(cursor)
        except Exception:
            pendientes = []
        finally:
            if conn:
                conn.close()
    for row in pendientes:
        origen = 'admin_invitacion' if (row['invitador_estado'] or '').strip() == 'sistema' else 'aliado'
        if db.asignar_invitado_por(row['codigo_referido'], row['codigo_invitador'], origen):
            stats['desde_invitaciones'] += 1

    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            huerfanos_rows = _repo.listar_huerfanos_sin_invitado_por(cursor, admin_codigo)
            huerfanos = [r['codigo'] for r in huerfanos_rows if r and r['codigo']]
        except Exception:
            huerfanos = []
        finally:
            if conn:
                conn.close()
    for codigo in huerfanos:
        if db.asignar_invitado_por(codigo, admin_codigo, 'huerfano'):
            stats['huerfanos'] += 1
    return stats

def listar_hijos_directos_linaje(db, codigo_invitador: str) -> List[Dict[str, Any]]:
    """Hijos directos según aliados.invitado_por_codigo."""
    codigo_invitador = (codigo_invitador or '').strip()
    if not codigo_invitador:
        return []
    db.backfill_invitado_por_linaje()
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            result = []
            for row in _repo.listar_hijos_directos_linaje(cursor, codigo_invitador):
                item = dict(row)
                item['zona'] = item.get('codigo_postal') or ''
                item['especializaciones'] = []
                try:
                    item['score'] = float(item.get('score') or 0)
                except (TypeError, ValueError):
                    item['score'] = 0.0
                origen = (item.get('origen') or '').strip()
                item['origen'] = origen
                item['origen_label'] = db.etiqueta_origen_referido(origen)
                result.append(item)
            return result
        except Exception:
            return []
        finally:
            if conn:
                conn.close()

def _obtener_origen_referido(db, codigo_referido: str) -> str:
    codigo_referido = (codigo_referido or '').strip()
    if not codigo_referido:
        return ''
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if _repo.aliados_tiene_invitado_por(cursor):
                row = _repo.select_invitado_origen_aliado(cursor, codigo_referido)
                if row and (row['origen'] or '').strip():
                    return (row['origen'] or '').strip()
            if _repo.referidos_tiene_origen(cursor):
                row = _repo.select_origen_referidos(cursor, codigo_referido)
                if row and (row['origen'] or '').strip():
                    return (row['origen'] or '').strip()
            if _repo.existe_uso_campana(cursor, codigo_referido):
                return 'campana'
            if _repo.existe_invitacion_oficio_usada(cursor, codigo_referido):
                return 'oficio'
            inv_row = _repo.select_invitador_estado_por_referido(cursor, codigo_referido)
            if inv_row and (inv_row['invitador_estado'] or '').strip() == 'sistema':
                return 'huerfano'
            if inv_row:
                return 'aliado'
            return ''
        except Exception:
            return ''
        finally:
            if conn:
                conn.close()

def contar_referidos_por_codigo(db, codigo_aliado: str) -> int:
    """Cuenta hijos directos del linaje (invitado_por_codigo; une referidos por compatibilidad)."""
    codigo_aliado = (codigo_aliado or '').strip()
    if not codigo_aliado:
        return 0
    try:
        db.backfill_invitado_por_linaje()
    except Exception:
        pass
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            if _repo.aliados_tiene_invitado_por(cursor):
                return _repo.contar_referidos_union_linaje(cursor, codigo_aliado)
            return _repo.contar_referidos_tabla(cursor, codigo_aliado)
        except Exception:
            return 0
        finally:
            conn.close()

def _nodo_referido_resumen(db, codigo: str) -> Optional[Dict[str, Any]]:
    """Resumen de aliado para nodos del árbol de referidos."""
    aliado = db.obtener_aliado_por_codigo(codigo)
    if not aliado:
        return None
    referidos_count = db.contar_referidos_por_codigo(codigo)
    origen = db._obtener_origen_referido(codigo)
    invitador = obtener_invitador_de(db, codigo)
    especializaciones: List[str] = []
    score = aliado.get('score')
    try:
        score_val = float(score) if score is not None else 0.0
    except (TypeError, ValueError):
        score_val = 0.0
    return {
        'codigo': aliado.get('codigo') or codigo,
        'nombre': aliado.get('nombre') or '',
        'oficio': aliado.get('oficio') or '',
        'zona': aliado.get('codigo_postal') or '',
        'codigo_postal': aliado.get('codigo_postal') or '',
        'marca': aliado.get('marca') or '',
        'estado': aliado.get('estado') or 'activo',
        'score': score_val,
        'telefono': aliado.get('telefono') or '',
        'email': aliado.get('email') or '',
        'especializaciones': especializaciones,
        'referidos_count': referidos_count,
        'creado_en': aliado.get('creado_en') or '',
        'origen': origen,
        'origen_label': db.etiqueta_origen_referido(origen),
        'invitador_nombre': (invitador or {}).get('nombre') or '',
        'invitador_codigo': (invitador or {}).get('codigo') or '',
    }

def asegurar_referido_desde_invitacion(db, codigo_invitacion: str, nuevo_aliado_codigo: str) -> bool:
    """
    Registra el vínculo desde invitaciones aunque la invitación ya esté marcada como usada.
    No duplica la recompensa de score.
    """
    codigo_invitacion = (codigo_invitacion or '').strip()
    nuevo_aliado_codigo = (nuevo_aliado_codigo or '').strip()
    if not codigo_invitacion or not nuevo_aliado_codigo:
        return False
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            row = _repo.select_invitacion_con_invitador(cursor, codigo_invitacion)
            if not row:
                return False
            origen = 'admin_invitacion' if (row['invitador_estado'] or '').strip() == 'sistema' else 'aliado'
            registrado = db._insert_referido(
                nuevo_aliado_codigo,
                row['codigo_invitador'],
                origen,
            )
            _repo.marcar_invitacion_usada(cursor, codigo_invitacion)
            conn.commit()
            return registrado or True
        except Exception:
            return False
        finally:
            if conn:
                conn.close()

def aliado_puede_ver_nodo_referidos(db, codigo_sesion: str, codigo_nodo: str) -> bool:
    """True si el aliado de sesión es el nodo o un ancestro invitador suyo."""
    codigo_sesion = (codigo_sesion or '').strip()
    codigo_nodo = (codigo_nodo or '').strip()
    if not codigo_sesion or not codigo_nodo:
        return False
    if codigo_sesion == codigo_nodo:
        return True
    current = codigo_nodo
    visitados: set = set()
    while current and current not in visitados:
        invitador = obtener_invitador_de(db, current)
        if not invitador:
            return False
        current = (invitador.get('codigo') or '').strip()
        if current == codigo_sesion:
            return True
        visitados.add(current)
    return False

def buscar_en_red_referidos(db, query: str, limite: int = 20) -> List[Dict[str, Any]]:
    """Busca aliados presentes en la red de referidos."""
    query = (query or '').strip()
    if not query:
        return []
    db.sincronizar_referidos_completo()
    like = f'%{query}%'
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            rows = _repo.buscar_codigos_en_red(cursor, like, limite)
            codigos = [row['codigo'] for row in rows if row and row['codigo']]
        except Exception:
            return []
        finally:
            if conn:
                conn.close()
    return [db._nodo_referido_resumen(c) for c in codigos if db._nodo_referido_resumen(c)]

def listar_nodos_raiz_referidos(db) -> List[Dict[str, Any]]:
    """Nodos raíz de la red (invitadores que no fueron referidos)."""
    db.sincronizar_referidos_completo()
    raices = db.listar_raices_referidos()
    nodos: List[Dict[str, Any]] = []
    for codigo in raices:
        nodo = db._nodo_referido_resumen(codigo)
        if nodo:
            nodos.append(nodo)
    return nodos

def listar_raices_referidos(db) -> List[str]:
    """Códigos de aliados raíz: invitaron a alguien pero no fueron referidos."""
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            cursor = conn.cursor()
            return [row[0] for row in _repo.listar_raices(cursor) if row and row[0]]
        except Exception:
            return []
        finally:
            if conn:
                conn.close()

def obtener_arbol_referidos(db, codigo_raiz: str, max_depth: int = 8) -> Optional[Dict[str, Any]]:
    """Construye árbol recursivo de referidos desde codigo_raiz."""
    db.sincronizar_referidos_completo()
    codigo_raiz = (codigo_raiz or '').strip()
    if not codigo_raiz:
        return None
    max_depth = max(1, min(int(max_depth or 8), 50))

    def _build(codigo: str, depth: int) -> Optional[Dict[str, Any]]:
        nodo = db._nodo_referido_resumen(codigo)
        if not nodo:
            return None
        if depth >= max_depth:
            nodo['referidos'] = []
            nodo['truncado'] = True
            return nodo
        hijos = db.listar_referidos_directos(codigo)
        nodo['referidos'] = []
        for hijo in hijos:
            hijo_codigo = hijo.get('codigo')
            if not hijo_codigo:
                continue
            sub = _build(hijo_codigo, depth + 1)
            if sub:
                sub['referido_en'] = hijo.get('referido_en') or ''
                nodo['referidos'].append(sub)
            else:
                hoja = dict(hijo)
                hoja['referidos'] = []
                hoja['referido_en'] = hijo.get('referido_en') or ''
                nodo['referidos'].append(hoja)
        return nodo

    return _build(codigo_raiz, 0)
# --- Extraído de DBManager (referido) ---

def sincronizar_referidos_invitaciones_usadas(db) -> int:
    """Backfill: referidos desde invitaciones 5 dígitos (aliado o admin) ya completadas."""
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            pendientes = _repo.listar_invitaciones_usadas_sin_referido(cursor)
        except Exception:
            return 0
        finally:
            if conn:
                conn.close()
    sincronizados = 0
    for row in pendientes:
        codigo_referido = row['codigo_referido']
        codigo_invitador = row['codigo_invitador']
        if not codigo_referido or not codigo_invitador:
            continue
        origen = 'admin_invitacion' if (row['invitador_estado'] or '').strip() == 'sistema' else 'aliado'
        if db._insert_referido(codigo_referido, codigo_invitador, origen):
            sincronizados += 1
    return sincronizados

def sincronizar_referidos_invitaciones_oficio_usadas(db) -> int:
    """Backfill: referidos desde invitaciones por oficio consumidas."""
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            pendientes = _repo.listar_invitaciones_oficio_usadas_sin_referido(cursor)
        except Exception:
            return 0
        finally:
            if conn:
                conn.close()
    sincronizados = 0
    for row in pendientes:
        if db._insert_referido(row['codigo_referido'], row['codigo_invitador'], 'oficio'):
            sincronizados += 1
    return sincronizados

def obtener_resumen_referidos_red(db) -> Dict[str, int]:
    """Resumen de la red: nodos vinculados vs aliados activos fuera de la red."""
    db.sincronizar_referidos_completo()
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            cursor = conn.cursor()
            return {
                'total_nodos': _repo.contar_nodos_red(cursor),
                'total_aliados_activos': _repo.contar_aliados_activos_red(cursor),
                'aliados_fuera_red': _repo.contar_aliados_fuera_red(cursor),
            }
        except Exception:
            return {
                'total_nodos': 0,
                'total_aliados_activos': 0,
                'aliados_fuera_red': 0,
            }
        finally:
            if conn:
                conn.close()

def listar_referidos_desde(db, desde: str) -> List[Dict[str, Any]]:
    """Referidos registrados después de un timestamp ISO (para actualización en vivo del árbol)."""
    db.sincronizar_referidos_completo()
    desde = (desde or '').strip()
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            rows = _repo.listar_referidos_desde(cursor, desde)
        except Exception:
            return []
        finally:
            if conn:
                conn.close()
    cambios: List[Dict[str, Any]] = []
    for row in rows:
        codigo_referido = row['codigo_referido']
        codigo_invitador = row['codigo_invitador']
        nodo = db._nodo_referido_resumen(codigo_referido)
        if not nodo:
            nodo = {
                'codigo': codigo_referido,
                'nombre': codigo_referido,
                'oficio': '—',
                'referidos_count': 0,
            }
        invitador = db._nodo_referido_resumen(codigo_invitador)
        cambios.append({
            'codigo_referido': codigo_referido,
            'codigo_invitador': codigo_invitador,
            'referido_en': row['creado_en'],
            'nodo': nodo,
            'invitador': invitador,
        })
    return cambios

def listar_referidos_directos(db, codigo_invitador: str) -> List[Dict[str, Any]]:
    """Lista aliados referidos directamente por codigo_invitador."""
    codigo_invitador = (codigo_invitador or '').strip()
    if not codigo_invitador:
        return []
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            rows = _repo.listar_referidos_directos(cursor, codigo_invitador)
            result: List[Dict[str, Any]] = []
            for row in rows:
                item = dict(row)
                item['zona'] = item.get('codigo_postal') or ''
                item['referidos_count'] = db.contar_referidos_por_codigo(item['codigo'])
                item['especializaciones'] = []
                try:
                    item['score'] = float(item.get('score') or 0)
                except (TypeError, ValueError):
                    item['score'] = 0.0
                origen = (item.get('origen') or '').strip() or db._obtener_origen_referido(item['codigo'])
                item['origen'] = origen
                item['origen_label'] = db.etiqueta_origen_referido(origen)
                result.append(item)
            return result
        except Exception:
            return []
        finally:
            if conn:
                conn.close()


def obtener_invitador_de(db, codigo_aliado: str) -> Optional[Dict[str, Any]]:
    """Obtiene el aliado invitador de codigo_aliado, si existe en referidos."""
    codigo_aliado = (codigo_aliado or '').strip()
    if not codigo_aliado:
        return None
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT a.codigo, a.nombre, a.oficio, a.codigo_postal, a.marca,
                       a.estado, a.score, r.creado_en AS referido_en
                FROM referidos r
                JOIN aliados a ON a.codigo = r.codigo_invitador
                WHERE r.codigo_referido = ?
            """, (codigo_aliado,))
            row = cursor.fetchone()
            if not row:
                return None
            item = dict(row)
            item['zona'] = item.get('codigo_postal') or ''
            item['referidos_count'] = contar_referidos_por_codigo(db, item['codigo'])
            try:
                item['score'] = float(item.get('score') or 0)
            except (TypeError, ValueError):
                item['score'] = 0.0
            return item
        except Exception:
            return None
        finally:
            if conn:
                conn.close()


def obtener_nodo_referidos(db, codigo: str) -> Optional[Dict[str, Any]]:
    """Nodo individual con metadatos para el árbol."""
    db.sincronizar_referidos_completo()
    return _nodo_referido_resumen(db, codigo)


def obtener_ruta_referidos_hacia_arriba(db, codigo: str) -> List[Dict[str, Any]]:
    """Cadena desde la raíz hasta codigo (inclusive)."""
    codigo = (codigo or '').strip()
    if not codigo:
        return []
    cadena: List[Dict[str, Any]] = []
    actual = codigo
    visitados: set = set()
    while actual and actual not in visitados:
        nodo = _nodo_referido_resumen(db, actual)
        if nodo:
            cadena.insert(0, nodo)
        invitador = obtener_invitador_de(db, actual)
        if not invitador:
            break
        actual = (invitador.get('codigo') or '').strip()
        visitados.add(actual)
    return cadena


def obtener_bosques_referidos(db, max_depth: int = 5) -> List[Dict[str, Any]]:
    """Lista árboles raíz de toda la red de referidos."""
    db.sincronizar_referidos_completo()
    max_depth = max(1, min(int(max_depth or 8), 50))
    raices = listar_raices_referidos(db)
    bosques: List[Dict[str, Any]] = []
    for codigo in raices:
        arbol = obtener_arbol_referidos(db, codigo, max_depth=max_depth)
        if arbol:
            bosques.append(arbol)
    return bosques


def obtener_ruta_linaje_hacia_arriba(db, codigo: str) -> List[Dict[str, Any]]:
    """Ruta linaje (invitado_por) hacia la raíz."""
    codigo = (codigo or '').strip()
    if not codigo:
        return []
    cadena: List[Dict[str, Any]] = []
    actual = codigo
    visitados: set = set()
    while actual and actual not in visitados:
        nodo = _nodo_referido_resumen(db, actual)
        if nodo:
            cadena.insert(0, nodo)
        visitados.add(actual)
        padre_codigo = None
        with db._lock:
            conn = None
            try:
                conn = db._connect()
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT invitado_por_codigo FROM aliados WHERE codigo = ?",
                    (actual,),
                )
                row = cursor.fetchone()
                if row and row[0]:
                    padre_codigo = str(row[0]).strip()
            except Exception:
                padre_codigo = None
            finally:
                if conn:
                    conn.close()
        if not padre_codigo:
            invitador = obtener_invitador_de(db, actual)
            padre_codigo = (invitador or {}).get('codigo')
        if not padre_codigo or padre_codigo in visitados:
            break
        actual = padre_codigo
    return cadena


def obtener_linaje_aliado(db, codigo: str) -> Optional[Dict[str, Any]]:
    """Padre, nodo, hijos directos y ruta hacia la raíz para Control de Aliados."""
    codigo = (codigo or '').strip()
    if not codigo:
        return None
    backfill_invitado_por_linaje(db)
    nodo = _nodo_referido_resumen(db, codigo)
    if not nodo:
        return None
    padre = None
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT invitado_por_codigo, COALESCE(invitado_origen, '') AS origen FROM aliados WHERE codigo = ?",
                (codigo,),
            )
            row = cursor.fetchone()
            if row and (row['invitado_por_codigo'] or '').strip():
                padre_codigo = (row['invitado_por_codigo'] or '').strip()
                padre = _nodo_referido_resumen(db, padre_codigo)
                if padre:
                    padre['origen'] = (row['origen'] or '').strip()
                    padre['origen_label'] = db.etiqueta_origen_referido(padre['origen'])
        except Exception:
            padre = None
        finally:
            if conn:
                conn.close()
    if not padre:
        padre = obtener_invitador_de(db, codigo)
    hijos = listar_hijos_directos_linaje(db, codigo)
    ruta = obtener_ruta_linaje_hacia_arriba(db, codigo)
    return {
        'aliado': nodo,
        'padre': padre,
        'hijos': hijos,
        'ruta': ruta,
        'hijos_count': len(hijos),
    }

def etiqueta_origen_referido(db, origen: str) -> str:
    return db.ORIGEN_REFERIDO_LABELS.get((origen or '').strip(), '')


def obtener_codigo_admin_referidos(db) -> str:
    """Código del aliado sistema que actúa como raíz admin en la red."""
    codigo = db.obtener_o_crear_invitador_admin('RUANA-ADMIN')
    return codigo or 'RUANA-ADMIN'


def _referidos_tiene_origen(db, cursor) -> bool:
    try:
        cursor.execute("PRAGMA table_info(referidos)")
        return 'origen' in [row[1] for row in cursor.fetchall()]
    except Exception:
        return False


def _aliados_tiene_invitado_por(db, cursor) -> bool:
    try:
        cursor.execute("PRAGMA table_info(aliados)")
        return 'invitado_por_codigo' in [row[1] for row in cursor.fetchall()]
    except Exception:
        return False


def _insert_referido(db, codigo_referido: str, codigo_invitador: str, origen: str = '') -> bool:
    """Compatibilidad: delega en asignar_invitado_por (linaje en aliados + referidos)."""
    return db.asignar_invitado_por(codigo_referido, codigo_invitador, origen=origen)


def _origen_por_invitador(db, codigo_invitador: str, default: str = 'aliado') -> str:
    invitador = db.obtener_aliado_por_codigo(codigo_invitador)
    if invitador and (invitador.get('estado') or '').strip() == 'sistema':
        return 'admin_invitacion'
    return default


def sincronizar_referidos_completo(db) -> Dict[str, int]:
    """Sincroniza referidos legacy + backfill de linaje en aliados.invitado_por_codigo."""
    campanas = db.sincronizar_referidos_campanas_admin()
    invitaciones = db.sincronizar_referidos_invitaciones_usadas()
    oficio = db.sincronizar_referidos_invitaciones_oficio_usadas()
    huerfanos = db.sincronizar_referidos_huerfanos_admin()
    linaje = db.backfill_invitado_por_linaje()
    return {
        'campanas': campanas,
        'invitaciones': invitaciones,
        'oficio': oficio,
        'huerfanos': huerfanos,
        'linaje': linaje,
    }


def sincronizar_referidos_huerfanos_admin(db) -> int:
    """
    Asigna al administrador como invitador a aliados registrados sin vínculo previo.
    Garantiza que todos los aliados activos aparezcan en el árbol genealógico.
    """
    admin_codigo = db.obtener_codigo_admin_referidos()
    if not admin_codigo:
        return 0
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT a.codigo
                FROM aliados a
                WHERE COALESCE(a.estado, '') NOT IN (
                    'pendiente_completar', 'sistema', 'rechazado', 'expulsado'
                )
                  AND a.codigo != ?
                  AND NOT EXISTS (
                      SELECT 1 FROM referidos r WHERE r.codigo_referido = a.codigo
                  )
            """, (admin_codigo,))
            huerfanos = [row['codigo'] for row in cursor.fetchall() if row and row['codigo']]
        except Exception:
            return 0
        finally:
            if conn:
                conn.close()
    sincronizados = 0
    for codigo in huerfanos:
        if db._insert_referido(codigo, admin_codigo, 'huerfano'):
            sincronizados += 1
    return sincronizados


def contar_total_nodos_referidos_red(db) -> int:
    """Total de aliados que participan en la red (como referido o invitador)."""
    return db.obtener_resumen_referidos_red().get('total_nodos', 0)


def _registrar_referido_campana_admin(db, codigo_campana: str, codigo_aliado: str) -> bool:
    """Registra en referidos un aliado registrado por campaña admin."""
    codigo_campana = (codigo_campana or "").strip().upper()
    codigo_aliado = (codigo_aliado or "").strip()
    if not codigo_campana or not codigo_aliado:
        return False
    campana = db.obtener_campana_invitacion(codigo_campana)
    if not campana:
        return False
    admin_codigo = (campana.get('creado_por_admin_codigo') or "").strip() or "RUANA-ADMIN"
    invitador = db.obtener_o_crear_invitador_admin(admin_codigo)
    if not invitador:
        return False
    return db._insert_referido(codigo_aliado, invitador, 'campana')


def sincronizar_referidos_campanas_admin(db) -> int:
    """
    Backfill: crea filas referidos para usos de campaña admin que aún no están en referidos.
    """
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT u.codigo_aliado, u.codigo_campana, c.creado_por_admin_codigo
                FROM invitacion_campana_usos u
                JOIN invitacion_campanas c ON c.codigo = u.codigo_campana
                WHERE NOT EXISTS (
                    SELECT 1 FROM referidos r WHERE r.codigo_referido = u.codigo_aliado
                )
            """)
            pendientes = cursor.fetchall()
        except Exception:
            return 0
        finally:
            if conn:
                conn.close()
    sincronizados = 0
    for row in pendientes:
        admin_codigo = (row['creado_por_admin_codigo'] or "").strip() or "RUANA-ADMIN"
        invitador = db.obtener_o_crear_invitador_admin(admin_codigo)
        if not invitador:
            continue
        codigo_aliado = row['codigo_aliado']
        if db._insert_referido(codigo_aliado, invitador, 'campana'):
            sincronizados += 1
    return sincronizados

