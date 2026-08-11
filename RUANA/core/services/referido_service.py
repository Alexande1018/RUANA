"""Servicio de dominio referido (Campamento Base).

Extracción progresiva desde DBManager. Las fachadas permanecen en DBManager.
"""
from __future__ import annotations

import sqlite3
from typing import Any, Dict, List, Optional, Tuple
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
            if not db._aliados_tiene_invitado_por(cursor):
                return False
            if overwrite:
                cursor.execute("""
                    UPDATE aliados
                    SET invitado_por_codigo = ?,
                        invitado_origen = COALESCE(NULLIF(?, ''), invitado_origen),
                        actualizado_en = CURRENT_TIMESTAMP
                    WHERE codigo = ?
                """, (codigo_invitador, origen, codigo_referido))
            else:
                cursor.execute("""
                    UPDATE aliados
                    SET invitado_por_codigo = ?,
                        invitado_origen = CASE
                            WHEN COALESCE(invitado_origen, '') = '' THEN ?
                            ELSE invitado_origen
                        END,
                        actualizado_en = CURRENT_TIMESTAMP
                    WHERE codigo = ?
                      AND (invitado_por_codigo IS NULL OR TRIM(COALESCE(invitado_por_codigo, '')) = '')
                """, (codigo_invitador, origen, codigo_referido))
            updated = cursor.rowcount > 0
            if db._referidos_tiene_origen(cursor):
                cursor.execute("""
                    INSERT OR IGNORE INTO referidos (codigo_referido, codigo_invitador, origen)
                    VALUES (?, ?, ?)
                """, (codigo_referido, codigo_invitador, origen))
                if origen:
                    cursor.execute("""
                        UPDATE referidos
                        SET origen = ?
                        WHERE codigo_referido = ?
                          AND (origen IS NULL OR origen = '')
                    """, (origen, codigo_referido))
            else:
                cursor.execute("""
                    INSERT OR IGNORE INTO referidos (codigo_referido, codigo_invitador)
                    VALUES (?, ?)
                """, (codigo_referido, codigo_invitador))
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
            if not db._aliados_tiene_invitado_por(cursor):
                return stats
            has_origen = db._referidos_tiene_origen(cursor)
            if has_origen:
                cursor.execute("""
                    SELECT r.codigo_referido, r.codigo_invitador,
                           COALESCE(r.origen, '') AS origen
                    FROM referidos r
                    JOIN aliados a ON a.codigo = r.codigo_referido
                    WHERE a.invitado_por_codigo IS NULL OR TRIM(COALESCE(a.invitado_por_codigo, '')) = ''
                """)
            else:
                cursor.execute("""
                    SELECT r.codigo_referido, r.codigo_invitador, '' AS origen
                    FROM referidos r
                    JOIN aliados a ON a.codigo = r.codigo_referido
                    WHERE a.invitado_por_codigo IS NULL OR TRIM(COALESCE(a.invitado_por_codigo, '')) = ''
                """)
            rows = cursor.fetchall()
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
            cursor.execute("""
                SELECT i.codigo AS codigo_referido, inv.codigo AS codigo_invitador,
                       inv.estado AS invitador_estado
                FROM invitaciones i
                JOIN aliados inv ON inv.id = i.invitador_aliado_id
                JOIN aliados ref ON ref.codigo = i.codigo
                WHERE COALESCE(ref.estado, '') NOT IN ('pendiente_completar', 'sistema')
                  AND (ref.invitado_por_codigo IS NULL OR TRIM(COALESCE(ref.invitado_por_codigo, '')) = '')
            """)
            pendientes = cursor.fetchall()
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
            cursor.execute("""
                SELECT a.codigo
                FROM aliados a
                WHERE COALESCE(a.estado, '') NOT IN (
                    'pendiente_completar', 'sistema', 'rechazado', 'expulsado'
                )
                  AND a.codigo != ?
                  AND (a.invitado_por_codigo IS NULL OR TRIM(COALESCE(a.invitado_por_codigo, '')) = '')
            """, (admin_codigo,))
            huerfanos = [r['codigo'] for r in cursor.fetchall() if r and r['codigo']]
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
            cursor.execute("""
                SELECT a.codigo, a.nombre, a.oficio, a.codigo_postal, a.marca,
                       a.estado, a.score, a.telefono, a.email,
                       a.creado_en, a.invitado_origen AS origen,
                       (
                           SELECT COUNT(*) FROM aliados h
                           WHERE h.invitado_por_codigo = a.codigo
                             AND COALESCE(h.estado, '') NOT IN (
                                 'pendiente_completar', 'sistema', 'rechazado', 'expulsado'
                             )
                       ) AS referidos_count
                FROM aliados a
                WHERE a.invitado_por_codigo = ?
                  AND COALESCE(a.estado, '') NOT IN (
                      'pendiente_completar', 'sistema', 'rechazado', 'expulsado'
                  )
                ORDER BY a.creado_en ASC
            """, (codigo_invitador,))
            result = []
            for row in cursor.fetchall():
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
            if db._aliados_tiene_invitado_por(cursor):
                cursor.execute(
                    "SELECT COALESCE(invitado_origen, '') AS origen FROM aliados WHERE codigo = ?",
                    (codigo_referido,),
                )
                row = cursor.fetchone()
                if row and (row['origen'] or '').strip():
                    return (row['origen'] or '').strip()
            if db._referidos_tiene_origen(cursor):
                cursor.execute(
                    "SELECT origen FROM referidos WHERE codigo_referido = ?",
                    (codigo_referido,),
                )
                row = cursor.fetchone()
                if row and (row['origen'] or '').strip():
                    return (row['origen'] or '').strip()
            cursor.execute(
                "SELECT 1 FROM invitacion_campana_usos WHERE codigo_aliado = ? LIMIT 1",
                (codigo_referido,),
            )
            if cursor.fetchone():
                return 'campana'
            cursor.execute("""
                SELECT 1 FROM invitaciones_oficio
                WHERE codigo_referido = ? AND estado = 'usado'
                LIMIT 1
            """, (codigo_referido,))
            if cursor.fetchone():
                return 'oficio'
            cursor.execute("""
                SELECT inv.estado AS invitador_estado
                FROM referidos r
                JOIN aliados inv ON inv.codigo = r.codigo_invitador
                WHERE r.codigo_referido = ?
            """, (codigo_referido,))
            inv_row = cursor.fetchone()
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
            if db._aliados_tiene_invitado_por(cursor):
                cursor.execute("""
                    SELECT COUNT(*) FROM (
                        SELECT a.codigo AS codigo
                        FROM aliados a
                        WHERE a.invitado_por_codigo = ?
                          AND COALESCE(a.estado, '') NOT IN (
                              'pendiente_completar', 'sistema', 'rechazado', 'expulsado'
                          )
                        UNION
                        SELECT r.codigo_referido AS codigo
                        FROM referidos r
                        JOIN aliados a ON a.codigo = r.codigo_referido
                        WHERE r.codigo_invitador = ?
                          AND COALESCE(a.estado, '') NOT IN (
                              'pendiente_completar', 'sistema', 'rechazado', 'expulsado'
                          )
                    )
                """, (codigo_aliado, codigo_aliado))
                return cursor.fetchone()[0] or 0
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM referidos r
                JOIN aliados a ON a.codigo = r.codigo_referido
                WHERE r.codigo_invitador = ?
                  AND COALESCE(a.estado, '') NOT IN (
                      'pendiente_completar', 'sistema', 'rechazado', 'expulsado'
                  )
                """,
                (codigo_aliado,),
            )
            return cursor.fetchone()[0] or 0
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
    invitador = db.obtener_invitador_de(codigo)
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
            cursor.execute("""
                SELECT i.invitador_aliado_id, inv.codigo AS codigo_invitador, inv.estado AS invitador_estado
                FROM invitaciones i
                JOIN aliados inv ON inv.id = i.invitador_aliado_id
                WHERE i.codigo = ?
            """, (codigo_invitacion,))
            row = cursor.fetchone()
            if not row:
                return False
            origen = 'admin_invitacion' if (row['invitador_estado'] or '').strip() == 'sistema' else 'aliado'
            registrado = db._insert_referido(
                nuevo_aliado_codigo,
                row['codigo_invitador'],
                origen,
            )
            cursor.execute(
                "UPDATE invitaciones SET usado = 1 WHERE codigo = ?",
                (codigo_invitacion,),
            )
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
        invitador = db.obtener_invitador_de(current)
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
            cursor.execute("""
                SELECT DISTINCT a.codigo
                FROM aliados a
                WHERE a.codigo IN (
                    SELECT codigo_referido FROM referidos
                    UNION
                    SELECT codigo_invitador FROM referidos
                )
                AND (
                    a.codigo LIKE ? OR a.nombre LIKE ? OR a.oficio LIKE ?
                    OR a.marca LIKE ? OR a.codigo_postal LIKE ?
                )
                ORDER BY a.nombre
                LIMIT ?
            """, (like, like, like, like, like, limite))
            codigos = [row['codigo'] for row in cursor.fetchall() if row and row['codigo']]
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
            cursor.execute("""
                SELECT DISTINCT r.codigo_invitador
                FROM referidos r
                WHERE r.codigo_invitador NOT IN (SELECT codigo_referido FROM referidos)
                ORDER BY r.codigo_invitador
            """)
            return [row[0] for row in cursor.fetchall() if row and row[0]]
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
            cursor.execute("""
                SELECT i.codigo AS codigo_referido,
                       inv.codigo AS codigo_invitador,
                       inv.estado AS invitador_estado
                FROM invitaciones i
                JOIN aliados inv ON inv.id = i.invitador_aliado_id
                JOIN aliados ref ON ref.codigo = i.codigo
                WHERE i.invitador_aliado_id IS NOT NULL
                  AND COALESCE(ref.estado, '') NOT IN ('pendiente_completar', 'sistema')
                  AND NOT EXISTS (
                      SELECT 1 FROM referidos r WHERE r.codigo_referido = i.codigo
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
            cursor.execute("""
                SELECT io.codigo_referido, inv.codigo AS codigo_invitador
                FROM invitaciones_oficio io
                JOIN aliados inv ON inv.id = io.aliado_id
                WHERE io.estado = 'usado'
                  AND COALESCE(io.codigo_referido, '') != ''
                  AND EXISTS (
                      SELECT 1 FROM aliados a WHERE a.codigo = io.codigo_referido
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM referidos r WHERE r.codigo_referido = io.codigo_referido
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
            cursor.execute("""
                SELECT COUNT(DISTINCT codigo) FROM (
                    SELECT codigo_referido AS codigo FROM referidos
                    UNION
                    SELECT codigo_invitador AS codigo FROM referidos
                )
            """)
            total_nodos = cursor.fetchone()[0] or 0
            cursor.execute("""
                SELECT COUNT(*) FROM aliados
                WHERE COALESCE(estado, '') NOT IN (
                    'pendiente_completar', 'sistema', 'rechazado', 'expulsado'
                )
            """)
            total_aliados_activos = cursor.fetchone()[0] or 0
            cursor.execute("""
                SELECT COUNT(*) FROM aliados a
                WHERE COALESCE(a.estado, '') = 'pendiente_completar'
                   OR (
                       COALESCE(a.estado, '') NOT IN ('sistema', 'rechazado', 'expulsado')
                       AND NOT EXISTS (
                           SELECT 1 FROM referidos r
                           WHERE r.codigo_referido = a.codigo
                              OR r.codigo_invitador = a.codigo
                       )
                   )
            """)
            aliados_fuera_red = cursor.fetchone()[0] or 0
            return {
                'total_nodos': total_nodos,
                'total_aliados_activos': total_aliados_activos,
                'aliados_fuera_red': aliados_fuera_red,
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
            if desde:
                cursor.execute("""
                    SELECT r.codigo_referido, r.codigo_invitador, r.creado_en
                    FROM referidos r
                    WHERE datetime(r.creado_en) > datetime(?)
                    ORDER BY r.creado_en ASC
                """, (desde,))
            else:
                cursor.execute("""
                    SELECT r.codigo_referido, r.codigo_invitador, r.creado_en
                    FROM referidos r
                    ORDER BY r.creado_en ASC
                """)
            rows = cursor.fetchall()
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
            cursor.execute("""
                SELECT COALESCE(a.codigo, r.codigo_referido) AS codigo,
                       COALESCE(a.nombre, r.codigo_referido) AS nombre,
                       COALESCE(a.oficio, '—') AS oficio,
                       COALESCE(a.codigo_postal, '') AS codigo_postal,
                       COALESCE(a.marca, '') AS marca,
                       COALESCE(a.estado, 'desconocido') AS estado,
                       COALESCE(a.score, 0) AS score,
                       COALESCE(a.telefono, '') AS telefono,
                       COALESCE(a.email, '') AS email,
                       COALESCE(a.creado_en, r.creado_en) AS creado_en,
                       r.creado_en AS referido_en,
                       COALESCE(r.origen, '') AS origen
                FROM referidos r
                LEFT JOIN aliados a ON a.codigo = r.codigo_referido
                WHERE r.codigo_invitador = ?
                ORDER BY r.creado_en ASC
            """, (codigo_invitador,))
            rows = cursor.fetchall()
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

