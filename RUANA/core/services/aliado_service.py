"""Servicio de dominio aliado (Campamento Base).

Extracción progresiva desde DBManager. Las fachadas permanecen en DBManager.
SQL de aliados vía AliadoRepo.
"""
from __future__ import annotations

from core.db_constants import ALIADO_FOTO_PERFIL_COLUMN, MAX_GRUPOS_POR_CP, _email_liberado_aliado, _telefono_liberado_aliado
from core.repositories.aliado_repo import AliadoRepo


from datetime import datetime, timedelta, timezone
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

_repo = AliadoRepo()

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

            if _repo.select_id_por_codigo(cursor, codigo) is not None:
                return {'status': 'error', 'message': f'Código {codigo} ya existe'}

            if _repo.select_id_por_email_ocupado(cursor, email) is not None:
                return {'status': 'error', 'message': f'El email {email} ya está registrado'}

            if _repo.select_id_por_telefono_ocupado(cursor, telefono) is not None:
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

            aliado_id = _repo.insertar(
                cursor, codigo, nombre, marca, oficio_stripped or oficio, codigo_postal, email, telefono,
                estado_final, score, descripcion_servicio,
            )
            conn.commit()

            # Asignar grupo
            if estado_final not in ('pendiente_validacion', 'pendiente_completar', 'en_espera'):
                if grupo_preferido_id:
                    _repo.update_grupo_id(cursor, grupo_preferido_id, aliado_id)
                    conn.commit()
                elif codigo_postal and en_catalogo and oficio_stripped:
                    grupo_asignar = db.buscar_grupo_sin_oficio(codigo_postal, oficio_stripped)
                    if grupo_asignar:
                        _repo.update_grupo_id(cursor, grupo_asignar['id'], aliado_id)
                    elif db.contar_grupos_activos_por_cp(codigo_postal) < MAX_GRUPOS_POR_CP:
                        nuevo_grupo = db.crear_grupo_en_cp(codigo_postal)
                        if isinstance(nuevo_grupo, dict) and 'id' in nuevo_grupo:
                            _repo.update_grupo_id(cursor, nuevo_grupo['id'], aliado_id)
                    if cursor.rowcount:
                        conn.commit()

            row = _repo.select_fila_basica_por_id(cursor, aliado_id)
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

            row = _repo.select_id_estado_por_codigo(cursor, codigo)
            if not row:
                return {'status': 'error', 'message': 'Codigo de invitacion no encontrado'}
            aliado_id = row[0]
            estado_actual = (row[1] or '').strip()
            if estado_actual != 'pendiente_completar':
                return {'status': 'error', 'message': 'Codigo de invitacion ya usado'}

            if _repo.select_id_por_email_ocupado_excluyendo(cursor, email, codigo) is not None:
                return {'status': 'error', 'message': f'El email {email} ya esta registrado'}

            if _repo.select_id_por_telefono_ocupado_excluyendo(cursor, telefono, codigo) is not None:
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

            if _repo.update_completar_pendiente(
                cursor, aliado_id, nombre, marca, oficio_stripped or oficio, codigo_postal, email, telefono,
                estado_final, score, descripcion_servicio,
            ) != 1:
                conn.rollback()
                return {'status': 'error', 'message': 'Codigo de invitacion ya usado'}
            conn.commit()

            if en_catalogo and oficio_stripped and estado_final not in ('pendiente_validacion', 'en_espera'):
                if grupo_preferido_id:
                    _repo.update_grupo_id(cursor, grupo_preferido_id, aliado_id)
                    conn.commit()
                elif codigo_postal:
                    grupo_asignar = db.buscar_grupo_sin_oficio(codigo_postal, oficio_stripped)
                    if grupo_asignar:
                        _repo.update_grupo_id(cursor, grupo_asignar['id'], aliado_id)
                    elif db.contar_grupos_activos_por_cp(codigo_postal) < MAX_GRUPOS_POR_CP:
                        nuevo_grupo = db.crear_grupo_en_cp(codigo_postal)
                        if isinstance(nuevo_grupo, dict) and 'id' in nuevo_grupo:
                            _repo.update_grupo_id(cursor, nuevo_grupo['id'], aliado_id)
                    if cursor.rowcount:
                        conn.commit()

            row = _repo.select_fila_basica_por_id(cursor, aliado_id)
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
            if _repo.select_id_por_codigo(cursor, codigo) is not None:
                return {
                    'status': 'error',
                    'message': f'Código {codigo} ya existe'
                }

            # Reutilizar las mismas validaciones de email/teléfono que crear_aliado
            if _repo.select_id_por_email_ocupado(cursor, email) is not None:
                return {
                    'status': 'error',
                    'message': f'El email {email} ya está registrado'
                }

            if _repo.select_id_por_telefono_ocupado(cursor, telefono) is not None:
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

            aliado_id = _repo.insertar_seed(
                cursor, codigo, nombre, marca, oficio, codigo_postal, email, telefono, estado, score,
            )
            conn.commit()

            # Asignación automática de grupo (misma lógica que registro; seeds no rechazan por límite 5)
            grupo_id_final = None
            if codigo_postal and oficio and str(oficio).strip():
                grupo_asignar = db.buscar_grupo_sin_oficio(codigo_postal, oficio)
                if grupo_asignar:
                    _repo.update_grupo_id(cursor, grupo_asignar['id'], aliado_id)
                    grupo_id_final = grupo_asignar['id']
                elif db.contar_grupos_activos_por_cp(codigo_postal) < MAX_GRUPOS_POR_CP:
                    nuevo_grupo = db.crear_grupo_en_cp(codigo_postal)
                    if isinstance(nuevo_grupo, dict) and 'id' in nuevo_grupo:
                        _repo.update_grupo_id(cursor, nuevo_grupo['id'], aliado_id)
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
            row = _repo.select_todo_por_codigo(cursor, codigo_str)
            
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
            
            row = _repo.select_todo_por_id(cursor, aliado_id)
            
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
                grupo_id_prev = _repo.select_grupo_id_por_codigo(cursor, codigo)
                grupo_id_anterior = grupo_id_prev if grupo_id_prev else None

                rowcount = _repo.update_campos_por_codigo(cursor, campos_update, codigo)

                conn.commit()

                if rowcount == 0:
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
            return [dict(row) for row in _repo.listar_en_pool(cursor)]
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
            rows = _repo.listar_admin(cursor, col_retador, filtro_postal)

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
                cp_grupo = _repo.select_codigo_postal_grupo(cursor, grupo_id)
                if cp_grupo and str(cp_grupo).strip():
                    cp_filtro = str(cp_grupo).strip()

            if grupo_id is not None and cp_filtro:
                rows = _repo.listar_directorio_grupo_con_cp(
                    cursor, select_cols, codigo_excluir, grupo_id, cp_filtro, estados_ok,
                )
            elif grupo_id is not None:
                rows = _repo.listar_directorio_solo_grupo(
                    cursor, grupo_id, codigo_excluir, estados_ok,
                )
            elif cp_filtro:
                rows = _repo.listar_directorio_por_cp(
                    cursor, cp_filtro, codigo_excluir, estados_ok,
                )
            else:
                return []
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
            rows = _repo.listar_pendiente_validacion(cursor)
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
        rowcount = _repo.update_activar_con_grupo(cursor, grupo_id, int(aliado_id))
    else:
        rowcount = _repo.update_activar_sin_grupo(cursor, int(aliado_id))

    if rowcount == 0:
        return {
            'status': 'error',
            'message': f'Aliado {codigo} no encontrado o no está pendiente de validación',
        }

    if grupo_id:
        grupo_nombre = _repo.select_nombre_grupo(cursor, grupo_id) or f'#{grupo_id}'
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
            row = _repo.select_activacion_por_id(cursor, int(aliado_id))
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
            row = _repo.select_activacion_por_codigo(cursor, codigo.strip())
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

            row = _repo.select_id_estado_por_codigo(cursor, codigo_aliado)
            if not row:
                return {'status': 'error', 'message': f'Aliado {codigo_aliado} no encontrado'}

            # Si ya está expulsado, no tiene sentido pausar
            estado_actual = row[1]
            if estado_actual == 'expulsado':
                return {
                    'status': 'error',
                    'message': f'Aliado {codigo_aliado} ya está expulsado y no se puede pausar'
                }

            _repo.update_suspendido_temporal(cursor, codigo_aliado)

            # Opcional: registrar en histórico de evaluaciones si existe alguna
            if razon:
                try:
                    _repo.insertar_historico_pausa(cursor, razon, codigo_aliado)
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
            rows = _repo.listar_eliminados(cursor, limite)
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
            row = _repo.select_para_eliminar(cursor, codigo)
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

            _repo.insertar_eliminado(
                cursor,
                codigo, nombre, marca, oficio, codigo_postal, email, telefono,
                estado_actual, motivo_txt, admin_codigo,
            )

            if _repo.delete_por_codigo(cursor, codigo) <= 0:
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
            return [dict(row) for row in _repo.listar_en_espera(cursor)]
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
            row = _repo.select_espera_por_codigo(cursor, codigo)
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
                g = _repo.select_grupo_activo_por_id(cursor, grupo_id)
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
            _repo.update_incorporar_espera(cursor, grupo_asignado, aliado_id)
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
            return _repo.existe_codigo(cursor, codigo)
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
            if not _repo.existe_codigo_limit(cursor, codigo_aliado):
                return {'status': 'error', 'message': 'Aliado no encontrado'}
            _repo.insertar_acceso_dia(cursor, codigo_aliado, dia_val)
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


def rechazar_aliado_pendiente(db, codigo: str) -> Dict[str, Any]:
    """Rechaza un aliado en pendiente_validacion: estado pasa a rechazado. No podrá entrar al panel."""
    codigo = (codigo or '').strip()
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            cursor.execute(
                f"""
                UPDATE aliados
                SET estado = 'rechazado',
                    email = ?,
                    telefono = ?,
                    qr_paypal_path = NULL,
                    bizum_num = NULL,
                    {ALIADO_FOTO_PERFIL_COLUMN} = NULL,
                    actualizado_en = CURRENT_TIMESTAMP
                WHERE codigo = ? AND estado = 'pendiente_validacion'
                """,
                (
                    _email_liberado_aliado(codigo),
                    _telefono_liberado_aliado(codigo),
                    codigo,
                ),
            )
            conn.commit()
            if cursor.rowcount > 0:
                return {'status': 'success', 'message': f'Aliado {codigo} rechazado. No podrá acceder al panel.'}
            return {'status': 'error', 'message': f'Aliado {codigo} no encontrado o no está pendiente de validación'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
        finally:
            conn.close()

