"""Servicio de dominio aliado (Campamento Base).

Extracción progresiva desde DBManager. Las fachadas permanecen en DBManager.
"""
from __future__ import annotations

from core.db_constants import ALIADO_FOTO_PERFIL_COLUMN, MAX_GRUPOS_POR_CP, SQL_ESTADO_CONTACTO_OCUPADO


from datetime import datetime, timedelta, timezone
import sqlite3
from typing import Any, Dict, List, Optional
# --- Extraído de DBManager (aliado) ---

def crear_aliado(db, codigo: str, nombre: str, marca: str = "",
                oficio: str = "", codigo_postal: str = "",
                email: str = "", telefono: str = "",
                estado: str = "activo", score: int = 50,
                especializaciones: Optional[List[str]] = None,
                especializacion: Optional[str] = None,
                descripcion_servicio: Optional[str] = None,
                grupo_id_invitacion: Optional[int] = None) -> Dict[str, Any]:
    """
    Crea un nuevo aliado en la BD.
    Plaza por oficio principal (especializacion ignorada).
    Si CP lleno y oficio ocupado en todos → estado en_espera (lista de Suplentes).
    """
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()

            cursor.execute("SELECT id FROM aliados WHERE codigo = ?", (codigo,))
            if cursor.fetchone():
                return {'status': 'error', 'message': f'Código {codigo} ya existe'}

            cursor.execute(
                f"SELECT id FROM aliados WHERE email = ? AND {SQL_ESTADO_CONTACTO_OCUPADO}",
                (email,),
            )
            if cursor.fetchone():
                return {'status': 'error', 'message': f'El email {email} ya está registrado'}

            cursor.execute(
                f"SELECT id FROM aliados WHERE telefono = ? AND {SQL_ESTADO_CONTACTO_OCUPADO}",
                (telefono,),
            )
            if cursor.fetchone():
                return {'status': 'error', 'message': f'El teléfono {telefono} ya está registrado'}

            if not codigo or len(codigo) != 5 or not codigo.isdigit():
                return {'status': 'error', 'message': 'El código debe ser un número de 5 dígitos (error de validación backend)'}

            if not nombre or len(nombre) < 3:
                return {'status': 'error', 'message': 'El nombre es obligatorio y debe tener al menos 3 caracteres (error de validación backend)'}

            if not email or '@' not in email:
                return {'status': 'error', 'message': 'El email es obligatorio y debe ser válido (error de validación backend)'}

            import re
            digitos_telefono = re.sub(r'\D', '', telefono)
            if not telefono or len(digitos_telefono) < 7:
                return {'status': 'error', 'message': 'El teléfono es obligatorio y debe tener al menos 7 dígitos (error de validación backend)'}

            oficio_stripped = str(oficio).strip() if oficio else ''
            catalogo_oficial = {str(o).strip() for o in db.get_catalogo_oficios_ruana() if o and str(o).strip()}
            oficio_canonico = db._resolver_en_conjunto_catalogo(oficio_stripped, catalogo_oficial) if oficio_stripped else None
            en_catalogo = oficio_canonico is not None
            if oficio_canonico:
                oficio_stripped = oficio_canonico
            estado_final = estado
            if oficio_stripped and not en_catalogo and estado != 'pendiente_completar':
                estado_final = 'pendiente_validacion'

            # Asignación de grupo: solo si oficio en catálogo
            grupo_preferido_id = None
            mensaje_lista_espera = None
            if en_catalogo and oficio_stripped and estado_final not in ('pendiente_validacion', 'pendiente_completar'):
                if grupo_id_invitacion:
                    if not db._grupo_tiene_oficio(cursor, grupo_id_invitacion, oficio_stripped):
                        grupo_pref = db.obtener_grupo_por_id(grupo_id_invitacion)
                        if grupo_pref and (grupo_pref.get('estado') or '') == 'activo':
                            grupo_preferido_id = grupo_id_invitacion
                    # Si invitador tiene oficio ocupado, buscar otro grupo del CP
                    if grupo_preferido_id is None and codigo_postal:
                        grupo_sin_oficio = db.buscar_grupo_sin_oficio(codigo_postal, oficio_stripped)
                        if grupo_sin_oficio:
                            grupo_preferido_id = grupo_sin_oficio['id']
                if grupo_preferido_id is None and codigo_postal:
                    grupo_sin_oficio = db.buscar_grupo_sin_oficio(codigo_postal, oficio_stripped)
                    if grupo_sin_oficio:
                        grupo_preferido_id = grupo_sin_oficio['id']
                    elif db.contar_grupos_activos_por_cp(codigo_postal) < MAX_GRUPOS_POR_CP:
                        pass  # Se creará el grupo después del INSERT
                    else:
                        # CP lleno y oficio ocupado en todos → en_espera
                        estado_final = 'en_espera'
                        mensaje_lista_espera = db.MENSAJE_LISTA_ESPERA

            cursor.execute("""
                INSERT INTO aliados
                (codigo, nombre, marca, oficio, codigo_postal, email, telefono, estado, score, descripcion_servicio)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (codigo, nombre, marca, oficio_stripped or oficio, codigo_postal, email, telefono,
                  estado_final, score, descripcion_servicio))

            aliado_id = cursor.lastrowid
            conn.commit()

            # Asignar grupo
            if estado_final not in ('pendiente_validacion', 'pendiente_completar', 'en_espera'):
                if grupo_preferido_id:
                    cursor.execute("UPDATE aliados SET grupo_id = ? WHERE id = ?", (grupo_preferido_id, aliado_id))
                    conn.commit()
                elif codigo_postal and en_catalogo and oficio_stripped:
                    grupo_asignar = db.buscar_grupo_sin_oficio(codigo_postal, oficio_stripped)
                    if grupo_asignar:
                        cursor.execute("UPDATE aliados SET grupo_id = ? WHERE id = ?", (grupo_asignar['id'], aliado_id))
                    elif db.contar_grupos_activos_por_cp(codigo_postal) < MAX_GRUPOS_POR_CP:
                        nuevo_grupo = db.crear_grupo_en_cp(codigo_postal)
                        if isinstance(nuevo_grupo, dict) and 'id' in nuevo_grupo:
                            cursor.execute("UPDATE aliados SET grupo_id = ? WHERE id = ?", (nuevo_grupo['id'], aliado_id))
                    if cursor.rowcount:
                        conn.commit()

            cursor.execute(
                "SELECT id, codigo, nombre, marca, oficio, codigo_postal, grupo_id, email, telefono, estado, score, descripcion_servicio, creado_en, actualizado_en FROM aliados WHERE id = ?",
                (aliado_id,)
            )
            row = cursor.fetchone()
            if row and hasattr(row, 'keys'):
                aliado_row = dict(row)
            elif row and isinstance(row, (list, tuple)):
                cols = ('id', 'codigo', 'nombre', 'marca', 'oficio', 'codigo_postal', 'grupo_id', 'email', 'telefono', 'estado', 'score', 'descripcion_servicio', 'creado_en', 'actualizado_en')
                aliado_row = dict(zip(cols, row))
            else:
                aliado_row = {
                    'id': aliado_id, 'codigo': codigo, 'nombre': nombre, 'marca': marca, 'oficio': oficio,
                    'codigo_postal': codigo_postal, 'grupo_id': None, 'email': email, 'telefono': telefono,
                    'estado': estado_final, 'score': score, 'creado_en': datetime.now().isoformat(), 'actualizado_en': None
                }

            out = {'status': 'success', **aliado_row}
            if mensaje_lista_espera:
                out['mensaje_lista_espera'] = mensaje_lista_espera
                try:
                    db._procesar_competencias_pendientes(codigo_postal, oficio_stripped)
                except Exception:
                    pass
            return out

        except sqlite3.IntegrityError as e:
            return {'status': 'error', 'message': f'Error de integridad: {e}'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
        finally:
            conn.close()

def completar_aliado_pendiente(db, codigo: str, nombre: str, marca: str = "",
                               oficio: str = "", codigo_postal: str = "",
                               email: str = "", telefono: str = "",
                               estado: str = "activo", score: int = 50,
                               especializaciones: Optional[List[str]] = None,
                               especializacion: Optional[str] = None,
                               descripcion_servicio: Optional[str] = None,
                               grupo_id_invitacion: Optional[int] = None) -> Dict[str, Any]:
    """Completa un aliado placeholder creado por invitacion y conserva su codigo.
    especializaciones y especializacion ignorados (plaza solo por oficio).
    """
    codigo = (codigo or "").strip()
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            cursor = conn.cursor()

            cursor.execute("SELECT id, estado FROM aliados WHERE codigo = ?", (codigo,))
            row = cursor.fetchone()
            if not row:
                return {'status': 'error', 'message': 'Codigo de invitacion no encontrado'}
            aliado_id = row[0]
            estado_actual = (row[1] or '').strip()
            if estado_actual != 'pendiente_completar':
                return {'status': 'error', 'message': 'Codigo de invitacion ya usado'}

            cursor.execute(
                f"SELECT id FROM aliados WHERE email = ? AND codigo != ? AND {SQL_ESTADO_CONTACTO_OCUPADO}",
                (email, codigo),
            )
            if cursor.fetchone():
                return {'status': 'error', 'message': f'El email {email} ya esta registrado'}

            cursor.execute(
                f"SELECT id FROM aliados WHERE telefono = ? AND codigo != ? AND {SQL_ESTADO_CONTACTO_OCUPADO}",
                (telefono, codigo),
            )
            if cursor.fetchone():
                return {'status': 'error', 'message': f'El telefono {telefono} ya esta registrado'}

            if not codigo or len(codigo) != 5 or not codigo.isdigit():
                return {'status': 'error', 'message': 'El codigo de invitacion debe ser un numero de 5 digitos'}
            if not nombre or len(nombre) < 3:
                return {'status': 'error', 'message': 'El nombre es obligatorio y debe tener al menos 3 caracteres'}
            if not email or '@' not in email:
                return {'status': 'error', 'message': 'El email es obligatorio y debe ser valido'}

            import re
            digitos_telefono = re.sub(r'\D', '', telefono)
            if not telefono or len(digitos_telefono) < 7:
                return {'status': 'error', 'message': 'El telefono es obligatorio y debe tener al menos 7 digitos'}

            oficio_stripped = str(oficio).strip() if oficio else ''
            catalogo_oficial = {str(o).strip() for o in db.get_catalogo_oficios_ruana() if o and str(o).strip()}
            oficio_canonico = db._resolver_en_conjunto_catalogo(oficio_stripped, catalogo_oficial) if oficio_stripped else None
            en_catalogo = oficio_canonico is not None
            if oficio_canonico:
                oficio_stripped = oficio_canonico
            estado_final = estado
            if oficio_stripped and not en_catalogo:
                estado_final = 'pendiente_validacion'

            # Asignación de grupo
            grupo_preferido_id = None
            mensaje_lista_espera = None
            if en_catalogo and oficio_stripped and estado_final not in ('pendiente_validacion',):
                if grupo_id_invitacion:
                    if not db._grupo_tiene_oficio(cursor, grupo_id_invitacion, oficio_stripped):
                        grupo_pref = db.obtener_grupo_por_id(grupo_id_invitacion)
                        if grupo_pref and (grupo_pref.get('estado') or '') == 'activo':
                            grupo_preferido_id = grupo_id_invitacion
                    if grupo_preferido_id is None and codigo_postal:
                        grupo_sin_oficio = db.buscar_grupo_sin_oficio(codigo_postal, oficio_stripped)
                        if grupo_sin_oficio:
                            grupo_preferido_id = grupo_sin_oficio['id']
                if grupo_preferido_id is None and codigo_postal:
                    grupo_sin_oficio = db.buscar_grupo_sin_oficio(codigo_postal, oficio_stripped)
                    if grupo_sin_oficio:
                        grupo_preferido_id = grupo_sin_oficio['id']
                    elif db.contar_grupos_activos_por_cp(codigo_postal) >= MAX_GRUPOS_POR_CP:
                        estado_final = 'en_espera'
                        mensaje_lista_espera = db.MENSAJE_LISTA_ESPERA

            cursor.execute("""
                UPDATE aliados
                SET nombre = ?,
                    marca = ?,
                    oficio = ?,
                    codigo_postal = ?,
                    email = ?,
                    telefono = ?,
                    estado = ?,
                    score = ?,
                    grupo_id = NULL,
                    descripcion_servicio = ?,
                    actualizado_en = CURRENT_TIMESTAMP
                WHERE id = ? AND estado = 'pendiente_completar'
            """, (
                nombre, marca, oficio_stripped or oficio, codigo_postal, email, telefono,
                estado_final, score, descripcion_servicio, aliado_id
            ))
            if cursor.rowcount != 1:
                conn.rollback()
                return {'status': 'error', 'message': 'Codigo de invitacion ya usado'}
            conn.commit()

            if en_catalogo and oficio_stripped and estado_final not in ('pendiente_validacion', 'en_espera'):
                if grupo_preferido_id:
                    cursor.execute("UPDATE aliados SET grupo_id = ? WHERE id = ?", (grupo_preferido_id, aliado_id))
                    conn.commit()
                elif codigo_postal:
                    grupo_asignar = db.buscar_grupo_sin_oficio(codigo_postal, oficio_stripped)
                    if grupo_asignar:
                        cursor.execute("UPDATE aliados SET grupo_id = ? WHERE id = ?", (grupo_asignar['id'], aliado_id))
                    elif db.contar_grupos_activos_por_cp(codigo_postal) < MAX_GRUPOS_POR_CP:
                        nuevo_grupo = db.crear_grupo_en_cp(codigo_postal)
                        if isinstance(nuevo_grupo, dict) and 'id' in nuevo_grupo:
                            cursor.execute("UPDATE aliados SET grupo_id = ? WHERE id = ?", (nuevo_grupo['id'], aliado_id))
                    if cursor.rowcount:
                        conn.commit()

            cursor.execute(
                "SELECT id, codigo, nombre, marca, oficio, codigo_postal, grupo_id, email, telefono, estado, score, descripcion_servicio, creado_en, actualizado_en FROM aliados WHERE id = ?",
                (aliado_id,)
            )
            row = cursor.fetchone()
            if row and hasattr(row, 'keys'):
                aliado_row = dict(row)
            elif row and isinstance(row, (list, tuple)):
                cols = ('id', 'codigo', 'nombre', 'marca', 'oficio', 'codigo_postal', 'grupo_id', 'email', 'telefono', 'estado', 'score', 'descripcion_servicio', 'creado_en', 'actualizado_en')
                aliado_row = dict(zip(cols, row))
            else:
                aliado_row = {
                    'id': aliado_id, 'codigo': codigo, 'nombre': nombre, 'marca': marca, 'oficio': oficio,
                    'codigo_postal': codigo_postal, 'grupo_id': None, 'email': email, 'telefono': telefono,
                    'estado': estado_final, 'score': score, 'creado_en': datetime.now().isoformat(), 'actualizado_en': None
                }

            out = {'status': 'success', **aliado_row}
            if mensaje_lista_espera:
                out['mensaje_lista_espera'] = mensaje_lista_espera
                try:
                    db._procesar_competencias_pendientes(codigo_postal, oficio_stripped)
                except Exception:
                    pass
            return out
        except sqlite3.IntegrityError as e:
            return {'status': 'error', 'message': f'Error de integridad: {e}'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
        finally:
            if conn:
                conn.close()

def crear_aliado_seed(db, codigo: str, nombre: str, marca: str = "",
                      oficio: str = "", codigo_postal: str = "",
                      email: str = "", telefono: str = "",
                      estado: str = "activo", score: int = 50) -> Dict[str, Any]:
    """
    Crea un aliado de *semilla* en la BD.

    Uso previsto:
    - Scripts de inicialización de datos (por ejemplo, aliados ALFA01/BETA02/GAMA03/DELTA04).
    - Permite códigos no numéricos (legacy o alfanuméricos) siempre que sean únicos.

    Importante:
    - Mantiene TODAS las validaciones de unicidad y formato de email/teléfono.
    - No se usa en el flujo normal de registro; sólo para seeds controlados.

    Args:
        codigo: Código único (puede ser alfanumérico).
        nombre: Nombre completo del aliado.
        marca: Marca personal o comercial.
        oficio: Oficio/profesión.
        codigo_postal: Código postal.
        email: Correo electrónico.
        telefono: Teléfono de contacto.
        estado: Estado del aliado (activo, inactivo, etc.).
        score: Score inicial.

    Returns:
        Dict con datos del aliado creado o error.
    """
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()

            # Verificar unicidad del código (independiente de su formato)
            cursor.execute("SELECT id FROM aliados WHERE codigo = ?", (codigo,))
            if cursor.fetchone():
                return {
                    'status': 'error',
                    'message': f'Código {codigo} ya existe'
                }

            # Reutilizar las mismas validaciones de email/teléfono que crear_aliado
            cursor.execute(
                f"SELECT id FROM aliados WHERE email = ? AND {SQL_ESTADO_CONTACTO_OCUPADO}",
                (email,),
            )
            if cursor.fetchone():
                return {
                    'status': 'error',
                    'message': f'El email {email} ya está registrado'
                }

            cursor.execute(
                f"SELECT id FROM aliados WHERE telefono = ? AND {SQL_ESTADO_CONTACTO_OCUPADO}",
                (telefono,),
            )
            if cursor.fetchone():
                return {
                    'status': 'error',
                    'message': f'El teléfono {telefono} ya está registrado'
                }

            if not nombre or len(nombre) < 3:
                return {
                    'status': 'error',
                    'message': 'El nombre es obligatorio y debe tener al menos 3 caracteres (error de validación backend)'
                }

            if not email or '@' not in email:
                return {
                    'status': 'error',
                    'message': 'El email es obligatorio y debe ser válido (error de validación backend)'
                }

            import re
            digitos_telefono = re.sub(r'\\D', '', telefono)
            if not telefono or len(digitos_telefono) < 7:
                return {
                    'status': 'error',
                    'message': 'El teléfono es obligatorio y debe tener al menos 7 dígitos (error de validación backend)'
                }

            cursor.execute("""
                INSERT INTO aliados
                (codigo, nombre, marca, oficio, codigo_postal, email, telefono, estado, score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (codigo, nombre, marca, oficio, codigo_postal, email, telefono, estado, score))

            aliado_id = cursor.lastrowid
            conn.commit()

            # Asignación automática de grupo (misma lógica que registro; seeds no rechazan por límite 5)
            grupo_id_final = None
            if codigo_postal and oficio and str(oficio).strip():
                grupo_asignar = db.buscar_grupo_sin_oficio(codigo_postal, oficio)
                if grupo_asignar:
                    cursor.execute("UPDATE aliados SET grupo_id = ? WHERE id = ?", (grupo_asignar['id'], aliado_id))
                    grupo_id_final = grupo_asignar['id']
                elif db.contar_grupos_activos_por_cp(codigo_postal) < MAX_GRUPOS_POR_CP:
                    nuevo_grupo = db.crear_grupo_en_cp(codigo_postal)
                    if isinstance(nuevo_grupo, dict) and 'id' in nuevo_grupo:
                        cursor.execute("UPDATE aliados SET grupo_id = ? WHERE id = ?", (nuevo_grupo['id'], aliado_id))
                        grupo_id_final = nuevo_grupo['id']
                if grupo_id_final is not None:
                    conn.commit()

            return {
                'status': 'success',
                'id': aliado_id,
                'codigo': codigo,
                'nombre': nombre,
                'marca': marca,
                'oficio': oficio,
                'codigo_postal': codigo_postal,
                'grupo_id': grupo_id_final,
                'email': email,
                'telefono': telefono,
                'estado': estado,
                'score': score,
                'creado_en': datetime.now().isoformat()
            }
        except sqlite3.IntegrityError as e:
            return {'status': 'error', 'message': f'Error de integridad: {e}'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
        finally:
            conn.close()

def obtener_aliado_por_codigo(db, codigo: str) -> Optional[Dict[str, Any]]:
    """
    Obtiene datos de un aliado por su código
    
    Args:
        codigo: Código del aliado (str o int; se normaliza a string para búsqueda)
        
    Returns:
        Dict con datos del aliado o None si no existe
    """
    codigo_str = str(codigo or "").strip() if codigo is not None else ""
    if not codigo_str:
        return None
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            # Comparar como string para que 85776 y "85776" coincidan (codigo en BD suele ser TEXT)
            cursor.execute("""
                SELECT * FROM aliados WHERE TRIM(CAST(codigo AS TEXT)) = ?
            """, (codigo_str,))
            
            row = cursor.fetchone()
            
            if not row:
                return None
            
            return dict(row)
            
        except Exception as e:
            print(f"Error obteniendo aliado: {e}")
            return None
        finally:
            conn.close()

def obtener_aliado_por_id(db, aliado_id: int) -> Optional[Dict[str, Any]]:
    """Obtiene aliado por ID interno"""
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("SELECT * FROM aliados WHERE id = ?", (aliado_id,))
            row = cursor.fetchone()
            
            return dict(row) if row else None
            
        except Exception as e:
            print(f"Error obteniendo aliado por ID: {e}")
            return None
        finally:
            conn.close()

def actualizar_aliado(db, codigo: str, **kwargs) -> Dict[str, Any]:
    """
    Actualiza datos de un aliado
    
    Args:
        codigo: Código del aliado
        **kwargs: Campos a actualizar (nombre, oficio, estado, score, etc.)
        
    Returns:
        Dict con resultado de la operación
    """
    with db._lock:
        # Campos permitidos para actualizar (qr_paypal_path, bizum_num para notificaciones Apoyo RUANA)
        campos_permitidos = {
            'nombre', 'marca', 'oficio', 'codigo_postal', 'email',
            'telefono', 'descripcion_servicio',
            'qr_paypal_path', 'bizum_num', ALIADO_FOTO_PERFIL_COLUMN,
        }
        campos_update = {k: v for k, v in kwargs.items()
                       if k in campos_permitidos}
        if not campos_update:
            return {'status': 'error', 'message': 'No fields to update'}

        try:
            with db._connect() as conn:
                cursor = conn.cursor()
                # Obtener grupo_id anterior por si hay que revisar viabilidad
                cursor.execute("SELECT grupo_id FROM aliados WHERE codigo = ?", (codigo,))
                row_prev = cursor.fetchone()
                grupo_id_anterior = row_prev[0] if row_prev and row_prev[0] else None

                set_clause = ", ".join([f"{k} = ?" for k in campos_update.keys()])
                values = list(campos_update.values()) + [codigo]

                cursor.execute(f"""
                    UPDATE aliados
                    SET {set_clause}, actualizado_en = CURRENT_TIMESTAMP
                    WHERE codigo = ?
                """, values)

                conn.commit()

                if cursor.rowcount == 0:
                    return {'status': 'error', 'message': f'Aliado {codigo} no encontrado'}

            # Si el aliado salió del grupo (estado inactivo o cambio de grupo), revisar viabilidad
            if grupo_id_anterior and ('estado' in campos_update or 'grupo_id' in campos_update):
                db.procesar_viabilidad_grupo(grupo_id_anterior)

            return {
                'status': 'success',
                'message': 'Aliado actualizado'
            }

        except Exception as e:
            return {'status': 'error', 'message': str(e)}

def listar_aliados_en_pool(db) -> List[Dict[str, Any]]:
    """Aliados en pool = activos con exactamente 1 derrota en competencia (segunda oportunidad)."""
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, codigo, nombre, marca, oficio, codigo_postal, grupo_id, email, telefono, estado, score,
                       COALESCE(derrotas_competencia, 0) AS derrotas_competencia, creado_en, actualizado_en
                FROM aliados
                WHERE estado = 'activo' AND COALESCE(derrotas_competencia, 0) = 1
                ORDER BY codigo
            """)
            return [dict(row) for row in cursor.fetchall()]
        except Exception:
            return []
        finally:
            conn.close()

def listar_aliados(db, filtro_postal: str = None) -> List[Dict[str, Any]]:
    """
    Lista todos los aliados, opcionalmente filtrados por código postal
    
    Args:
        filtro_postal: Código postal para filtrar (opcional)
        
    Returns:
        Lista de aliados
    """
    try:
        db.backfill_invitado_por_linaje()
    except Exception:
        pass
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            col_retador = db._columna_retador_competencia(cursor)

            base_query = """
                SELECT
                    a.*,
                    g.nombre AS grupo_nombre,
                    e.estado AS eval_estado,
                    e.score AS eval_score,
                    e.intencion AS eval_intencion,
                    e.tasa_respuesta,
                    e.tasa_confirmacion,
                    e.meses_sin_trabajo,
                    e.ciclos_consecutivos,
                    e.razones AS eval_razones,
                    e.severidad AS eval_severidad,
                    e.actualizado_en AS eval_actualizado_en,
                    inv.nombre AS invitado_por_nombre,
                    inv.codigo AS invitado_por_codigo_join,
                    (
                        SELECT COUNT(*)
                        FROM aliados h
                        WHERE h.invitado_por_codigo = a.codigo
                          AND COALESCE(h.estado, '') NOT IN (
                              'pendiente_completar', 'sistema', 'rechazado', 'expulsado'
                          )
                    ) AS hijos_directos_count,
                    (
                        SELECT COUNT(*)
                        FROM contactos_ruana c
                        WHERE c.solicitante_codigo = a.codigo OR c.profesional_codigo = a.codigo
                    ) AS total_contactos,
                    (
                        SELECT COUNT(*)
                        FROM contactos_ruana c
                        WHERE (c.solicitante_codigo = a.codigo OR c.profesional_codigo = a.codigo)
                          AND datetime(c.creado_en) >= datetime('now', '-30 day')
                    ) AS contactos_30d,
                    (
                        SELECT 1 FROM competencia c
                        WHERE c.""" + col_retador + """ = a.codigo AND c.estado = 'activa' LIMIT 1
                    ) AS es_retador_activo,
                    (
                        SELECT 1 FROM competencia c
                        WHERE c.aliado_original_codigo = a.codigo AND c.estado = 'activa' LIMIT 1
                    ) AS es_titular_en_competencia
                FROM aliados a
                LEFT JOIN grupos g ON g.id = a.grupo_id
                LEFT JOIN evaluaciones e ON e.codigo_aliado = a.codigo
                LEFT JOIN aliados inv ON inv.codigo = a.invitado_por_codigo
                WHERE (a.estado IS NULL OR (
                    a.estado != 'expulsado'
                    AND a.estado != 'suspendido_temporal'
                    AND a.estado != 'sistema'
                    AND a.estado != 'pendiente_completar'
                ))
            """

            params: Tuple[Any, ...] = ()
            if filtro_postal:
                base_query += " AND a.codigo_postal = ?"
                params = (filtro_postal,)

            base_query += " ORDER BY a.creado_en DESC"

            cursor.execute(base_query, params)
            rows = cursor.fetchall()

            aliados: List[Dict[str, Any]] = []
            for row in rows:
                item = dict(row)

                # Zona legible para el panel (usa código postal por ahora)
                item['zona'] = item.get('codigo_postal') or ''

                # Linaje (padre / hijos) para Control de Aliados
                invitado_por = (item.get('invitado_por_codigo') or item.get('invitado_por_codigo_join') or '').strip()
                item['invitado_por_codigo'] = invitado_por or None
                item['invitado_por_nombre'] = (item.get('invitado_por_nombre') or '').strip()
                origen = (item.get('invitado_origen') or '').strip()
                item['invitado_origen'] = origen
                item['invitado_origen_label'] = db.etiqueta_origen_referido(origen)
                try:
                    item['hijos_directos_count'] = int(item.get('hijos_directos_count') or 0)
                except (TypeError, ValueError):
                    item['hijos_directos_count'] = 0

                # Score de referencia para el panel (evaluación > aliado.score)
                eval_score = item.get('eval_score')
                if eval_score is not None:
                    try:
                        score_panel = float(eval_score)
                    except Exception:
                        score_panel = float(item.get('score') or 0)
                else:
                    score_panel = float(item.get('score') or 0)
                item['score_panel'] = score_panel

                # Estado de panel: prioriza estado real de BD (activo / pendiente_validacion / en_espera).
                # El score de evaluación solo reclasifica a observación/riesgo cuando existe evaluación.
                # pendiente_completar no se lista (placeholders de invitación se excluyen arriba).
                estado_bd = (item.get('estado') or 'activo').strip().lower()
                estado_panel = 'activos'
                if estado_bd == 'pendiente_validacion':
                    estado_panel = 'pendientes'
                elif estado_bd == 'en_espera':
                    estado_panel = 'suplentes_espera'
                elif estado_bd in ('expulsado', 'suspendido_temporal', 'rechazado'):
                    estado_panel = estado_bd
                elif estado_bd == 'activo' and eval_score is None:
                    estado_panel = 'activos'
                else:
                    if eval_score is not None:
                        try:
                            s = float(eval_score)
                        except Exception:
                            s = float(item.get('score') or 0)
                    else:
                        s = float(item.get('score') or 0)

                    if s < 15:
                        estado_panel = 'riesgo'
                    elif s < 50:
                        estado_panel = 'observacion'
                    else:
                        estado_panel = 'activos'

                item['estado_panel'] = estado_panel

                # Retador activo: en competencia como retador; alias es_suplente_activo para compat
                item['es_retador_activo'] = bool(item.get('es_retador_activo'))
                item['es_suplente_activo'] = item['es_retador_activo']  # alias compatibilidad
                # Titular en competencia: 1 si es el aliado original en competencia
                item['es_titular_en_competencia'] = bool(item.get('es_titular_en_competencia'))

                aliados.append(item)

            return aliados
            
        except Exception as e:
            print(f"Error listando aliados: {e}")
            return []
        finally:
            conn.close()

def listar_aliados_directorio_grupo(db, codigo_aliado: str) -> List[Dict[str, Any]]:
    """
    Lista profesionales del mismo grupo y código postal que el aliado (directorio).
    Excluye al propio aliado. Solo activos / pendiente_validacion.
    Nunca mezcla aliados de otros CP aunque compartan grupo_id por error de datos.
    """
    codigo_busqueda = (codigo_aliado or '').strip()
    aliado = db.obtener_aliado_por_codigo(codigo_busqueda)
    if not aliado:
        return []
    grupo_id = aliado.get('grupo_id')
    codigo_postal = (aliado.get('codigo_postal') or '').strip()
    codigo_excluir = (aliado.get('codigo') or codigo_busqueda or '').strip()

    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            estados_ok = ('activo', 'pendiente_validacion')
            select_cols = (
                f"a.id, a.codigo, a.nombre, a.marca, a.oficio, a.codigo_postal, a.grupo_id, "
                f"a.estado, a.score, a.descripcion_servicio, a.{ALIADO_FOTO_PERFIL_COLUMN}, a.creado_en"
            )

            cp_filtro = codigo_postal
            if grupo_id is not None:
                cursor.execute(
                    "SELECT codigo_postal FROM grupos WHERE id = ?",
                    (grupo_id,),
                )
                row_grupo = cursor.fetchone()
                if row_grupo and (row_grupo[0] or '').strip():
                    cp_filtro = (row_grupo[0] or '').strip()

            if grupo_id is not None and cp_filtro:
                cursor.execute(
                    f"""
                    SELECT {select_cols}
                    FROM aliados a
                    INNER JOIN grupos g ON g.id = a.grupo_id
                    WHERE a.estado IN (?, ?) AND a.codigo != ?
                      AND a.grupo_id = ?
                      AND TRIM(COALESCE(g.codigo_postal, '')) = ?
                      AND TRIM(COALESCE(a.codigo_postal, '')) = ?
                    ORDER BY a.nombre
                    """,
                    (estados_ok[0], estados_ok[1], codigo_excluir, grupo_id, cp_filtro, cp_filtro),
                )
            elif grupo_id is not None:
                cursor.execute(
                    f"""
                    SELECT id, codigo, nombre, marca, oficio, codigo_postal, grupo_id, estado, score,
                           descripcion_servicio, {ALIADO_FOTO_PERFIL_COLUMN}, creado_en
                    FROM aliados
                    WHERE grupo_id = ? AND estado IN (?, ?) AND codigo != ?
                    ORDER BY nombre
                    """,
                    (grupo_id, estados_ok[0], estados_ok[1], codigo_excluir),
                )
            elif cp_filtro:
                cursor.execute(
                    f"""
                    SELECT id, codigo, nombre, marca, oficio, codigo_postal, grupo_id, estado, score,
                           descripcion_servicio, {ALIADO_FOTO_PERFIL_COLUMN}, creado_en
                    FROM aliados
                    WHERE TRIM(COALESCE(codigo_postal, '')) = ?
                      AND estado IN (?, ?) AND codigo != ?
                    ORDER BY nombre
                    """,
                    (cp_filtro, estados_ok[0], estados_ok[1], codigo_excluir),
                )
            else:
                return []
            rows = cursor.fetchall()
            result = []
            for row in rows:
                item = dict(row)
                item['zona'] = item.get('codigo_postal') or ''
                item['estado_ruana'] = db.score_a_estado(item.get('score'))
                # M-06: marcar perfiles incompletos (placeholder o datos sin completar)
                nombre = (item.get('nombre') or '').strip()
                oficio = (item.get('oficio') or '').strip()
                estado = (item.get('estado') or '').strip()
                item['perfil_incompleto'] = (
                    estado == 'pendiente_completar'
                    or nombre.startswith('Nuevo Aliado -')
                    or not nombre
                    or oficio.lower() == 'pendiente'
                    or not oficio
                )
                result.append(item)
            return result
        except Exception as e:
            print(f"Error listar_aliados_directorio_grupo: {e}")
            return []
        finally:
            conn.close()

def listar_aliados_pendiente_validacion(db) -> List[Dict[str, Any]]:
    """Lista aliados con estado pendiente_validacion (oficio fuera de catálogo, requieren activación manual)."""
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, codigo, nombre, marca, oficio, codigo_postal, email, telefono, creado_en
                FROM aliados WHERE LOWER(TRIM(COALESCE(estado, ''))) = 'pendiente_validacion'
                ORDER BY creado_en DESC
            """)
            rows = cursor.fetchall()
            return [dict(r) for r in rows] if rows else []
        except Exception as e:
            print(f"Error listando aliados pendientes: {e}")
            return []
        finally:
            conn.close()

def _activar_aliado_pendiente_interno(db, cursor, aliado: Dict[str, Any]) -> Dict[str, Any]:
    """Activa pendiente_validacion y asigna grupo (priorizando el del invitador)."""
    codigo = (aliado.get('codigo') or '').strip()
    aliado_id = aliado.get('id')
    if not codigo or aliado_id is None:
        return {'status': 'error', 'message': 'Aliado no válido'}

    grupo_id = db._obtener_grupo_activacion_pendiente(cursor, aliado)
    if grupo_id:
        cursor.execute(
            """UPDATE aliados
               SET estado = 'activo', grupo_id = ?, actualizado_en = CURRENT_TIMESTAMP
               WHERE id = ? AND LOWER(TRIM(COALESCE(estado, ''))) = 'pendiente_validacion'""",
            (grupo_id, int(aliado_id)),
        )
    else:
        cursor.execute(
            """UPDATE aliados
               SET estado = 'activo', actualizado_en = CURRENT_TIMESTAMP
               WHERE id = ? AND LOWER(TRIM(COALESCE(estado, ''))) = 'pendiente_validacion'""",
            (int(aliado_id),),
        )

    if cursor.rowcount == 0:
        return {
            'status': 'error',
            'message': f'Aliado {codigo} no encontrado o no está pendiente de validación',
        }

    if grupo_id:
        cursor.execute("SELECT nombre FROM grupos WHERE id = ?", (grupo_id,))
        g_row = cursor.fetchone()
        grupo_nombre = (g_row[0] if g_row else None) or f'#{grupo_id}'
        return {
            'status': 'success',
            'message': f'Aliado {codigo} activado e incorporado al grupo {grupo_nombre}',
            'grupo_id': grupo_id,
        }

    return {
        'status': 'success',
        'message': (
            f'Aliado {codigo} activado correctamente. '
            'No había plaza disponible en ningún grupo del CP.'
        ),
        'grupo_id': None,
    }

def activar_aliado_por_id(db, aliado_id: int) -> Dict[str, Any]:
    """Activa aliado por ID numérico (pendiente_validacion → activo) y asigna grupo."""
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """SELECT id, codigo, oficio, codigo_postal, invitado_por_codigo, estado
                   FROM aliados WHERE id = ?""",
                (int(aliado_id),),
            )
            row = cursor.fetchone()
            if not row:
                return {'status': 'error', 'message': f'Aliado con ID {aliado_id} no encontrado'}
            if (row['estado'] or '').strip().lower() != 'pendiente_validacion':
                return {
                    'status': 'error',
                    'message': f'Aliado con ID {aliado_id} no está pendiente de validación',
                }
            result = db._activar_aliado_pendiente_interno(cursor, dict(row))
            conn.commit()
            return result
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
        finally:
            conn.close()

def activar_aliado_pendiente(db, codigo: str) -> Dict[str, Any]:
    """Cambia pendiente_validacion → activo y asigna grupo del invitador si hay plaza."""
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """SELECT id, codigo, oficio, codigo_postal, invitado_por_codigo, estado
                   FROM aliados WHERE codigo = ?""",
                (codigo.strip(),),
            )
            row = cursor.fetchone()
            if not row:
                return {'status': 'error', 'message': f'Aliado {codigo} no encontrado'}
            if (row['estado'] or '').strip().lower() != 'pendiente_validacion':
                return {
                    'status': 'error',
                    'message': f'Aliado {codigo} no está pendiente de validación',
                }
            result = db._activar_aliado_pendiente_interno(cursor, dict(row))
            conn.commit()
            return result
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
        finally:
            conn.close()

def pausar_aliado(db, codigo_aliado: str, razon: Optional[str] = None, admin_codigo: Optional[str] = None) -> Dict[str, Any]:
    """
    Pausa manualmente un aliado (lo saca temporalmente del pool).
    Implementación: marca estado = 'suspendido_temporal' en la tabla aliados.
    """
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()

            cursor.execute(
                "SELECT id, estado FROM aliados WHERE codigo = ?",
                (codigo_aliado,),
            )
            row = cursor.fetchone()
            if not row:
                return {'status': 'error', 'message': f'Aliado {codigo_aliado} no encontrado'}

            # Si ya está expulsado, no tiene sentido pausar
            estado_actual = row[1]
            if estado_actual == 'expulsado':
                return {
                    'status': 'error',
                    'message': f'Aliado {codigo_aliado} ya está expulsado y no se puede pausar'
                }

            cursor.execute(
                "UPDATE aliados SET estado = 'suspendido_temporal', actualizado_en = CURRENT_TIMESTAMP WHERE codigo = ?",
                (codigo_aliado,),
            )

            # Opcional: registrar en histórico de evaluaciones si existe alguna
            if razon:
                try:
                    cursor.execute(
                        """
                        INSERT INTO evaluaciones_historico
                        (codigo_aliado, estado_anterior, estado_nuevo, score_anterior, score_nuevo, razon_cambio)
                        SELECT
                            a.codigo,
                            e.estado AS estado_anterior,
                            'pausado_manual' AS estado_nuevo,
                            e.score AS score_anterior,
                            e.score AS score_nuevo,
                            ?
                        FROM aliados a
                        LEFT JOIN evaluaciones e ON e.codigo_aliado = a.codigo
                        WHERE a.codigo = ?
                        """,
                        (razon, codigo_aliado),
                    )
                except Exception:
                    # No romper por fallos en histórico
                    pass

            # Registrar evento de sistema dentro de la misma transacción
            try:
                db._insert_evento_sistema(
                    cursor,
                    tipo="aliado_pausado",
                    descripcion=f"Aliado {codigo_aliado} pausado manualmente",
                    actor_tipo="admin",
                    actor_codigo=admin_codigo,
                    metadata={"codigo_aliado": codigo_aliado, "razon": razon},
                )
            except Exception:
                # No romper operación principal por fallo en log
                pass

            conn.commit()

            return {
                'status': 'success',
                'codigo_aliado': codigo_aliado,
                'nuevo_estado': 'suspendido_temporal',
            }
        except Exception as e:
            print(f"Error pausando aliado {codigo_aliado}: {e}")
            return {'status': 'error', 'message': str(e)}
        finally:
            try:
                conn.close()
            except Exception:
                pass

def listar_aliados_eliminados(db, limite: int = 200) -> List[Dict[str, Any]]:
    """Lista el archivo de aliados eliminados definitivamente (solo registro de auditoría)."""
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, codigo, nombre, marca, oficio, codigo_postal,
                       email, telefono, estado_anterior, motivo, admin_codigo, eliminado_en
                FROM aliados_eliminados
                ORDER BY eliminado_en DESC
                LIMIT ?
                """,
                (max(1, min(limite, 500)),),
            )
            rows = cursor.fetchall()
            return [dict(r) for r in rows] if rows else []
        except Exception as e:
            print(f"Error listando aliados eliminados: {e}")
            return []
        finally:
            try:
                conn.close()
            except Exception:
                pass

def eliminar_perfil_aliado_admin(db,
    codigo_aliado: str,
    motivo: Optional[str] = None,
    admin_codigo: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Elimina el perfil de un aliado de forma definitiva desde el panel admin.
    Purga todos los datos relacionados, libera email/teléfono/código y archiva
    un único registro en aliados_eliminados para auditoría.
    """
    codigo = (codigo_aliado or '').strip()
    if not codigo:
        return {'status': 'error', 'message': 'Código de aliado obligatorio'}

    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, estado, nombre, marca, oficio, codigo_postal, email, telefono
                FROM aliados WHERE codigo = ?
                """,
                (codigo,),
            )
            row = cursor.fetchone()
            if not row:
                return {'status': 'error', 'message': f'Aliado {codigo} no encontrado'}

            aliado_id = row[0]
            estado_actual = (row[1] or '').strip().lower()
            nombre = row[2] or ''
            marca = row[3] or ''
            oficio = row[4] or ''
            codigo_postal = row[5] or ''
            email = row[6] or ''
            telefono = row[7] or ''

            if estado_actual == 'sistema':
                return {'status': 'error', 'message': 'No se puede eliminar un aliado del sistema'}

            motivo_txt = (motivo or '').strip() or 'Eliminado desde panel de administración'

            db._purga_datos_aliado_completa(cursor, codigo, aliado_id)

            cursor.execute(
                """
                INSERT INTO aliados_eliminados
                (codigo, nombre, marca, oficio, codigo_postal, email, telefono,
                 estado_anterior, motivo, admin_codigo)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    codigo, nombre, marca, oficio, codigo_postal, email, telefono,
                    estado_actual, motivo_txt, admin_codigo,
                ),
            )

            cursor.execute("DELETE FROM aliados WHERE codigo = ?", (codigo,))
            if cursor.rowcount <= 0:
                return {'status': 'error', 'message': f'No se pudo eliminar el perfil de {codigo}'}

            try:
                db._insert_evento_sistema(
                    cursor,
                    tipo="aliado_perfil_eliminado",
                    descripcion=f"Perfil de aliado {codigo} ({nombre}) eliminado definitivamente por admin",
                    actor_tipo="admin",
                    actor_codigo=admin_codigo,
                    metadata={
                        "codigo_aliado": codigo,
                        "estado_anterior": estado_actual,
                        "accion": "eliminado",
                        "motivo": motivo_txt,
                    },
                )
            except Exception:
                pass

            conn.commit()
            return {
                'status': 'success',
                'message': f'Perfil de {codigo} eliminado definitivamente',
                'codigo_aliado': codigo,
                'accion': 'eliminado',
                'nuevo_estado': None,
            }
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            return {'status': 'error', 'message': str(e)}
        finally:
            try:
                conn.close()
            except Exception:
                pass

def listar_aliados_en_espera(db) -> List[Dict[str, Any]]:
    """Lista aliados con estado en_espera (Suplentes). Para panel admin."""
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, codigo, nombre, marca, oficio, codigo_postal, email, telefono,
                       estado, score, descripcion_servicio, creado_en, actualizado_en
                FROM aliados WHERE estado = 'en_espera'
                ORDER BY creado_en ASC
            """)
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            print(f"[RUANA][DB] Error listar_aliados_en_espera: {e}")
            return []
        finally:
            conn.close()

def incorporar_aliado_espera(db, codigo: str, grupo_id: Optional[int] = None,
                              admin_codigo: Optional[str] = None) -> Dict[str, Any]:
    """Incorpora un aliado en_espera a un grupo: estado → activo, asigna grupo."""
    codigo = (codigo or '').strip()
    if not codigo:
        return {'status': 'error', 'message': 'Código obligatorio'}
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, codigo, oficio, codigo_postal, estado FROM aliados WHERE codigo = ?",
                (codigo,)
            )
            row = cursor.fetchone()
            if not row:
                return {'status': 'error', 'message': 'Aliado no encontrado'}
            aliado = dict(row)
            if aliado['estado'] != 'en_espera':
                return {'status': 'error', 'message': 'El aliado no está en lista de espera'}
            aliado_id = aliado['id']
            oficio = (aliado.get('oficio') or '').strip()
            codigo_postal = (aliado.get('codigo_postal') or '').strip()
            grupo_asignado = None
            if grupo_id:
                cursor.execute("SELECT id, estado FROM grupos WHERE id = ? AND estado = 'activo'", (grupo_id,))
                g = cursor.fetchone()
                if not g:
                    return {'status': 'error', 'message': 'Grupo no encontrado o no activo'}
                if oficio and db._grupo_tiene_oficio(cursor, grupo_id, oficio):
                    return {'status': 'error', 'message': f'El grupo ya tiene un aliado con oficio {oficio}'}
                grupo_asignado = grupo_id
            elif oficio and codigo_postal:
                g = db.buscar_grupo_sin_oficio(codigo_postal, oficio)
                if g:
                    grupo_asignado = g['id']
                elif db.contar_grupos_activos_por_cp(codigo_postal) < MAX_GRUPOS_POR_CP:
                    nuevo = db.crear_grupo_en_cp(codigo_postal)
                    if isinstance(nuevo, dict) and nuevo.get('id'):
                        grupo_asignado = nuevo['id']
            if grupo_asignado is None:
                return {'status': 'error', 'message': 'No hay plaza disponible. Especifica grupo_id o espera a que se libere una plaza.'}
            cursor.execute(
                "UPDATE aliados SET estado = 'activo', grupo_id = ?, actualizado_en = CURRENT_TIMESTAMP WHERE id = ?",
                (grupo_asignado, aliado_id)
            )
            conn.commit()
            try:
                db.registrar_evento_sistema(
                    'incorporar_espera',
                    f'Aliado {codigo} incorporado desde lista de espera al grupo {grupo_asignado}',
                    actor_tipo='admin',
                    actor_codigo=admin_codigo,
                    metadata={'codigo': codigo, 'grupo_id': grupo_asignado},
                )
            except Exception:
                pass
            try:
                aliado_row = db.obtener_aliado_por_codigo(codigo)
                if aliado_row:
                    cp = (aliado_row.get('codigo_postal') or '').strip()
                    of = (aliado_row.get('oficio') or '').strip()
                    if cp and of:
                        db._procesar_competencias_pendientes(cp, of)
            except Exception:
                pass
            return {'status': 'success', 'message': 'Aliado incorporado correctamente', 'grupo_id': grupo_asignado}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
        finally:
            if conn:
                conn.close()
# --- Extraído de DBManager (aliado) ---

def codigo_existe(db, codigo: str) -> bool:
    """Verifica si un código ya existe como aliado."""
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM aliados WHERE codigo = ?", (codigo,))
            return cursor.fetchone() is not None
        except Exception as e:
            print(f"Error verificando código: {e}")
            return False
        finally:
            if conn:
                conn.close()

def codigo_disponible_para_asignar(db, codigo: str) -> bool:
    """True si el código no choca con aliados ni con invitaciones existentes."""
    codigo = (codigo or '').strip()
    if not codigo:
        return False
    return (not db.codigo_existe(codigo)) and (not db.invitacion_codigo_existe(codigo))

def registrar_acceso_login(db,
    codigo_aliado: str,
    dia: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Registra un día de login (máx. 1 fila/día) y evalúa Regla 8.
    Antes de insertar el acceso de hoy aplica Penalización 6 (semanas sin entrar).
    Solo debe llamarse desde POST /api/aliado/login.
    """
    codigo_aliado = (codigo_aliado or '').strip()
    if not codigo_aliado:
        return {'status': 'error', 'message': 'Código obligatorio'}
    dia_val = (dia or '').strip() or db._dia_hoy_servidor()
    if len(dia_val) != 10 or dia_val[4] != '-' or dia_val[7] != '-':
        return {'status': 'error', 'message': 'Día inválido'}

    # Penalización 6 ANTES de registrar el acceso de hoy (si no, MAX(dia)=hoy y no penaliza)
    try:
        db.aplicar_penalizacion_sin_acceso_semanal(codigo_aliado, dia_ref=dia_val)
    except Exception:
        pass

    with db._lock:
        conn = None
        try:
            conn = db._connect()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM aliados WHERE codigo = ? LIMIT 1",
                (codigo_aliado,),
            )
            if not cursor.fetchone():
                return {'status': 'error', 'message': 'Aliado no encontrado'}
            cursor.execute(
                """
                INSERT OR IGNORE INTO aliado_accesos_dia (codigo_aliado, dia)
                VALUES (?, ?)
                """,
                (codigo_aliado, dia_val),
            )
            conn.commit()
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    aplicado = False
    motivo = None
    try:
        hito = db.evaluar_regla8_racha_7dias(codigo_aliado, dia_fin=dia_val)
        if hito:
            db.aplicar_cambio_score(hito[0], hito[1], hito[2])
            aplicado = True
            motivo = hito[2]
    except Exception:
        pass
    return {
        'status': 'success',
        'codigo': codigo_aliado,
        'dia': dia_val,
        'regla8_aplicada': aplicado,
        'motivo': motivo,
    }

