"""Blueprint de aliados (CRUD/perfil/foto/directorio/notificaciones/catálogo).

Extraído de web/app.py. Centro-comunicación vive en soporte_bp.
Contratos y paths idénticos.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from flask import Blueprint, jsonify, request

from core import db_manager as db_manager_mod
from core.db_manager import RUANA_CODIGO_INVITACION_REGEX
from core.phone_utils import normalize_phone
from core.services import notificacion_service
from web.auth_decorators import (
    _admin_codigo,
    _aliado_codigo,
    _forbidden_unless_admin_or_aliado_self,
    require_admin,
    require_admin_escritura,
    require_aliado,
)

aliado_bp = Blueprint("aliado", __name__)

_ALIADO_SELF_EDITABLE_FIELDS = frozenset({
    'nombre', 'marca', 'oficio', 'codigo_postal', 'email',
    'telefono', 'descripcion_servicio', 'qr_paypal_path', 'bizum_num',
})

def get_db():
    """Usa get_db del módulo app cargado (RUANA.web.app o web.app) para respetar monkeypatch."""
    import sys
    for key in ("RUANA.web.app", "web.app"):
        mod = sys.modules.get(key)
        if mod is not None:
            fn = getattr(mod, "get_db", None)
            if callable(fn):
                return fn()
    return db_manager_mod.get_db()


def _resolve_app_attr(name, default=None):
    import sys
    for key in ("RUANA.web.app", "web.app"):
        mod = sys.modules.get(key)
        if mod is not None and hasattr(mod, name):
            return getattr(mod, name)
    return default


def upload_foto_perfil_file(**kwargs):
    override = _resolve_app_attr("upload_foto_perfil_file")
    if callable(override) and getattr(override, "__module__", "") not in (
        "web.blueprints.aliado_bp",
        "RUANA.web.blueprints.aliado_bp",
    ):
        return override(**kwargs)
    from core.storage_manager import upload_foto_perfil_file as _upload
    return _upload(**kwargs)


def enviar_correo_bienvenida_aliado(**kwargs):
    override = _resolve_app_attr("enviar_correo_bienvenida_aliado")
    if callable(override) and getattr(override, "__module__", "") not in (
        "web.blueprints.aliado_bp",
        "RUANA.web.blueprints.aliado_bp",
    ):
        return override(**kwargs)
    from core.email_service import enviar_correo_bienvenida_aliado as _send
    return _send(**kwargs)


def _generar_codigo_unico() -> str:
    """Genera un código único de 5 dígitos (monkeypatch vía app._generar_codigo_unico)."""
    override = _resolve_app_attr("_generar_codigo_unico")
    if callable(override) and getattr(override, "__module__", "") not in (
        "web.blueprints.aliado_bp",
        "RUANA.web.blueprints.aliado_bp",
    ):
        return override()
    return _generar_codigo_unico_impl()


def _generar_codigo_unico_impl() -> str:
    import random
    db = get_db()
    max_intentos = 100
    for _ in range(max_intentos):
        codigo = str(random.randint(10000, 99999))
        if hasattr(db, 'codigo_disponible_para_asignar'):
            if db.codigo_disponible_para_asignar(codigo):
                return codigo
        elif not db.codigo_existe(codigo):
            return codigo
    raise Exception("No se pudo generar c?digo ?nico despu?s de 100 intentos")


@aliado_bp.route("/api/aliado/bp-health", methods=["GET"])
def aliado_bp_health():
    return jsonify({"status": "ok", "dominio": "aliado"})

@aliado_bp.route('/api/aliado/datos', methods=['GET', 'POST'], strict_slashes=False)
@require_aliado
def get_aliado_datos():
    """
    GET/POST /api/aliado/datos
    Requiere sesi?n de aliado (cookie). Retorna datos del aliado autenticado.
    El c?digo se toma de la sesi?n; no se conf?a en query/body para autorizaci?n (S-01).
    """
    codigo = _aliado_codigo()
    if not codigo:
        return jsonify({'status': 'error', 'message': 'Sesi?n expirada'}), 401
    
    try:
        db = get_db()
        # Procesamiento automático de competencias (cierre 30d, abandonos, pendientes)
        try:
            db.procesar_competencia_automatica()
        except Exception:
            pass
        try:
            db.procesar_timeouts_sin_confirmacion_stripe()
        except Exception:
            pass
        # Aplicar penalizaciones (abiertos 7d/21d, chat 48h, sin acceso semanal, comprobante 3d)
        db.aplicar_penalizaciones_contactos_abiertos(codigo)
        aliado = db.obtener_aliado_por_codigo(codigo)
        
        if aliado:
            estado = aliado.get('estado')
            if estado == 'expulsado':
                return jsonify({
                    'status': 'error',
                    'message': 'C?digo desactivado. Se requiere nueva invitaci?n para volver.'
                }), 403
            if estado == 'pendiente_validacion':
                return jsonify({
                    'status': 'error',
                    'message': 'Tu cuenta est? pendiente de validaci?n. No puedes acceder al panel hasta que un administrador la active.'
                }), 403
            if estado == 'rechazado':
                return jsonify({
                    'status': 'error',
                    'message': 'Tu solicitud de registro no fue aceptada. Contacta al administrador si crees que es un error.'
                }), 403
            if estado == 'suspendido_temporal':
                return jsonify({
                    'status': 'error',
                    'message': 'Acceso suspendido temporalmente por purga de calidad. Contacte al administrador.'
                }), 403
            if estado == 'en_espera':
                return jsonify({
                    'status': 'error',
                    'message': 'Estás en la lista de Suplentes. En cuanto se libere una plaza en tu zona, el equipo RUANA te incorporará.'
                }), 403
            solicitudes = []
            if aliado.get('codigo_postal'):
                solicitudes = db.obtener_solicitudes_grupo(aliado['codigo_postal'])
            contar_contestadas = getattr(db, 'contar_solicitudes_enviadas_contestadas', lambda c: 0)
            solicitudes_enviadas_contestadas = contar_contestadas(codigo)
            referidos_count = db.contar_referidos_por_codigo(codigo)
            # Estado RUANA siempre calculado desde el score (ÉLITE/DESTACADO/ESTABLE/EN RIESGO/COMPETENCIA)
            score = aliado.get('score')
            if score is None:
                score = 0
            estado_ruana = db.score_a_estado(score)
            aliado_dict = dict(aliado)
            # Especializaciones: en BD es JSON string; exponer como lista
            if isinstance(aliado_dict.get('especializaciones'), str):
                try:
                    aliado_dict['especializaciones'] = json.loads(aliado_dict['especializaciones'])
                except Exception:
                    aliado_dict['especializaciones'] = []
            elif aliado_dict.get('especializaciones') is None:
                aliado_dict['especializaciones'] = []
            aliado_dict['solicitudes_enviadas_contestadas'] = solicitudes_enviadas_contestadas
            aliado_dict['referidos_count'] = referidos_count
            aliado_dict['estado_ruana'] = estado_ruana

            grupo_id = aliado_dict.get('grupo_id')
            avisos_grupo = []
            if grupo_id:
                avisos_grupo = db.obtener_avisos_grupo(grupo_id)
                # Info del grupo para el panel: nombre, estado, num oficios, oficios faltantes (cat?logo RUANA). Sin scores ni m?tricas de otros.
                grupo_info = db.info_grupo_para_panel(grupo_id, codigo)
                if grupo_info:
                    aliado_dict['grupo_info'] = grupo_info
            aliado_dict['competencia_activa'] = bool(
                grupo_id and db.grupo_tiene_competencia_activa(grupo_id)
            )
            competencia_info = db.obtener_competencia_info_aliado(codigo)
            aliado_dict['competencia_info'] = competencia_info
            if competencia_info and (
                competencia_info.get('en_competencia') or competencia_info.get('competencia_pendiente')
            ):
                aliado_dict['estado_ruana'] = 'EN COMPETENCIA'
                aliado_dict['competencia_activa'] = True

            from core.services import pago_service
            aliado_dict['stripe_pago_listo'] = (
                pago_service.profesional_stripe_listo(db, codigo)
                if pago_service.stripe_habilitado_global()
                else True
            )

            # Notificaciones del aliado (ej. comprobante rechazado con mensaje de admin)
            notificaciones = notificacion_service.listar_notificaciones_aliado(
                db, codigo, limite=50
            )
            listar_catalogo = getattr(db, 'listar_catalogo_servicios_aliado', None)
            aliado_dict['catalogo_servicios'] = listar_catalogo(codigo) if callable(listar_catalogo) else []

            return jsonify({
                'status': 'success',
                'aliado': aliado_dict,
                'solicitudes': solicitudes,
                'avisos_grupo': avisos_grupo,
                'solicitudes_enviadas_contestadas': solicitudes_enviadas_contestadas,
                'referidos_count': referidos_count,
                'notificaciones': notificaciones,
                'timestamp': datetime.now().isoformat()
            })
        
        # Si no existe, retornar error
        return jsonify({
            'status': 'error',
            'message': f'Aliado con c?digo {codigo} no encontrado'
        }), 404
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@aliado_bp.route('/api/aliados/por-codigo/<codigo>', methods=['GET'])
@require_aliado
def get_aliado_by_codigo(codigo):
    """
    GET /api/aliados/por-codigo/XXXXX
    Retorna datos del aliado. Solo se permite consultar el propio c?digo (sesi?n).
    """
    try:
        codigo = codigo.strip()
        if codigo != _aliado_codigo():
            return jsonify({'status': 'error', 'message': 'No autorizado a consultar otro aliado'}), 403
        db = get_db()
        aliado = db.obtener_aliado_por_codigo(codigo)
        
        if aliado:
            estado = aliado.get('estado')
            if estado == 'expulsado':
                return jsonify({
                    'status': 'error',
                    'message': 'C?digo desactivado. Se requiere nueva invitaci?n para volver.'
                }), 403
            if estado == 'suspendido_temporal':
                return jsonify({
                    'status': 'error',
                    'message': 'Acceso suspendido temporalmente por purga de calidad. Contacte al administrador.'
                }), 403
            aliado_out = dict(aliado)
            grupo_id = aliado_out.get('grupo_id')
            aliado_out['competencia_activa'] = bool(
                grupo_id and db.grupo_tiene_competencia_activa(grupo_id)
            )
            return jsonify({
                'status': 'success',
                'aliado': aliado_out,
                'timestamp': datetime.now().isoformat()
            })
        
        return jsonify({
            'status': 'error',
            'message': f'Aliado {codigo} no encontrado'
        }), 404
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500
@aliado_bp.route('/api/aliados', methods=['GET'])
@require_admin
def get_aliados():
    """
    GET /api/aliados
    Retorna lista de todos los aliados desde SQLite
    """
    try:
        db = get_db()
        aliados = db.listar_aliados()
        
        return jsonify({
            'status': 'success',
            'total': len(aliados),
            'aliados': aliados,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@aliado_bp.route('/api/aliados/directorio', methods=['GET'])
@require_aliado
def get_aliados_directorio():
    """
    GET /api/aliados/directorio
    Retorna profesionales del mismo grupo que el aliado en sesi?n (directorio). Excluye al propio aliado.
    """
    try:
        codigo = _aliado_codigo()
        if not codigo:
            return jsonify({'status': 'error', 'message': 'Sesi?n expirada'}), 401
        db = get_db()
        aliados = db.listar_aliados_directorio_grupo(codigo)
        from core.services import pago_service
        if pago_service.stripe_habilitado_global():
            for aliado in aliados:
                cod = str(aliado.get('codigo') or '').strip()
                aliado['stripe_pago_listo'] = pago_service.profesional_stripe_listo(db, cod)
        print(f"[directorio] codigo={codigo!r} -> {len(aliados)} profesionales")
        return jsonify({
            'status': 'success',
            'total': len(aliados),
            'aliados': aliados,
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@aliado_bp.route('/api/aliados/<int:aliado_id>', methods=['GET'])
@require_admin
def get_aliado(aliado_id):
    """
    GET /api/aliados/<id>
    Retorna detalles de un aliado espec?fico por ID
    """
    try:
        db = get_db()
        aliado = db.obtener_aliado_por_id(aliado_id)
        
        if not aliado:
            return jsonify({
                'status': 'error',
                'message': f'Aliado con ID {aliado_id} no encontrado'
            }), 404
        
        return jsonify({
            'status': 'success',
            'aliado': aliado,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@aliado_bp.route('/api/aliados/registrar', methods=['POST'])
def registrar_aliado():
    """
    POST /api/aliados/registrar
    
    Registra un nuevo aliado en SQLite
    
    Body JSON:
    {
        "nombre": "Juan P?rez",
        "marca": "JP Construcci?n",
        "oficio": "Constructor",
        "codigo_postal": "080001",
        "email": "juan@example.com",
        "telefono": "+57 3001234567"
    }
    """
    try:
        data = request.get_json() or {}
        db = get_db()
        
        # Validar campos requeridos
        # F07: Validaci?n coherente - Opci?n A: Email y tel?fono OBLIGATORIOS
        # Una ?nica fuente de verdad: frontend debe cumplir esto, backend lo valida
        required = ['nombre', 'email', 'telefono']
        for field in required:
            if not data.get(field, '').strip():
                return jsonify({
                    'status': 'error',
                    'message': f'Campo requerido: {field}'
                }), 400
        
        # F07: Validaci?n de formato ANTES de DB (una ?nica fuente de verdad en app.py)
        nombre = data.get('nombre', '').strip()
        email = data.get('email', '').strip()
        telefono = normalize_phone(data.get('telefono', '').strip())
        
        # Validar nombre
        if len(nombre) < 3:
            return jsonify({
                'status': 'error',
                'message': 'El nombre debe tener al menos 3 caracteres'
            }), 400
        
        # F07: Validar email
        if '@' not in email or '.' not in email.split('@')[1]:
            return jsonify({
                'status': 'error',
                'message': 'Email inv?lido (debe contener @ y dominio v?lido)'
            }), 400
        
        # F07: Validar tel?fono (solo d?gitos, al menos 7; se ignoran espacios y s?mbolos)
        import re
        digitos = re.sub(r'\D', '', telefono)
        if len(digitos) < 7:
            return jsonify({
                'status': 'error',
                'message': 'Tel?fono inv?lido (debe tener al menos 7 d?gitos)'
            }), 400
        
        # Oficio principal obligatorio (catálogo oficial)
        oficio = (data.get('oficio') or data.get('oficio_principal') or '').strip()
        if not oficio:
            return jsonify({
                'status': 'error',
                'message': 'El oficio principal es obligatorio. Elige uno del catálogo.'
            }), 400

        # Suboficios/especializaciones ignorados: plaza solo por oficio principal
        especializacion_plaza = oficio
        especializaciones = []


        # Si viene con código de invitación "Conozco a alguien", intentar asignar al grupo del invitador si cumple reglas
        grupo_id_invitacion = None
        codigo_postal = (data.get('codigo_postal') or '').strip()
        codigo_invitacion_raw = (data.get('codigo_invitacion') or '').strip()
        codigo_invitacion_simple = None
        codigo_campana_invitacion = None
        if codigo_invitacion_raw and not re.match(RUANA_CODIGO_INVITACION_REGEX, codigo_invitacion_raw.upper()):
            campana = db.validar_campana_invitacion(codigo_invitacion_raw.upper()) if hasattr(db, 'validar_campana_invitacion') else None
            if campana:
                codigo_campana_invitacion = (campana.get('codigo') or codigo_invitacion_raw).strip().upper()
                if not codigo_postal and campana.get('codigo_postal'):
                    codigo_postal = (campana.get('codigo_postal') or '').strip()
            else:
                invitacion_pendiente = None
                if hasattr(db, 'obtener_invitacion_pendiente'):
                    invitacion_pendiente = db.obtener_invitacion_pendiente(codigo_invitacion_raw)
                aliado_placeholder = db.obtener_aliado_por_codigo(codigo_invitacion_raw)
                es_placeholder = bool(
                    aliado_placeholder
                    and (aliado_placeholder.get('estado') or '').strip() == 'pendiente_completar'
                )
                if not invitacion_pendiente and not es_placeholder:
                    return jsonify({
                        'status': 'error',
                        'message': f'Codigo de invitacion {codigo_invitacion_raw} no encontrado o ya usado.'
                    }), 404
                codigo_invitacion_simple = (
                    (invitacion_pendiente.get('codigo') if invitacion_pendiente else None)
                    or (aliado_placeholder.get('codigo') if aliado_placeholder else None)
                    or codigo_invitacion_raw
                ).strip()
                grupo_inv = db.obtener_grupo_invitador_por_codigo_invitacion(codigo_invitacion_raw)
                if grupo_inv and grupo_inv.get('grupo_id'):
                    grupo_id_invitacion = grupo_inv['grupo_id']

        # Pre-check: si CP lleno y oficio ocupado en todos → se registrará como en_espera (no error)

        # Crear aliado con código personal NUEVO (distinto del código de invitación).
        # Si había placeholder legacy, se elimina tras el registro para no dejar duplicados.
        descripcion_servicio = (data.get('descripcion') or data.get('descripcion_servicio') or '').strip() or None
        codigo = _generar_codigo_unico()
        result = db.crear_aliado(
            codigo=codigo,
            nombre=nombre,
            marca=data.get('marca', '').strip(),
            oficio=oficio,
            codigo_postal=codigo_postal,
            email=email,
            telefono=telefono,
            estado='activo',
            score=50,
            descripcion_servicio=descripcion_servicio,
            grupo_id_invitacion=grupo_id_invitacion
        )
        
        if result['status'] == 'error':
            return jsonify(result), 400

        # Oficio fuera de catálogo → pendiente_validacion (validación manual por admin)
        if result.get('estado') == 'pendiente_validacion':
            result['mensaje_pendiente_validacion'] = (
                'Tu oficio no está en el catálogo oficial. Tu cuenta queda pendiente de validación. '
                'Guarda tu código personal. Tus datos se han enviado al panel de administración en "Aliados pendientes de validación", '
                'donde un administrador podrá aceptarte o rechazarte. Cuando te activen, podrás entrar con este mismo código.'
            )

        # CP lleno, oficio ocupado → en_espera (lista de Suplentes)
        # mensaje_lista_espera viene del db_manager si aplica

        # Si registr? con c?digo de invitaci?n v?lido
        codigo_invitacion = (data.get('codigo_invitacion') or '').strip()
        if codigo_invitacion:
            codigo_inv_upper = codigo_invitacion.upper()
            # C?digo RUANA-XXX-OFICIO-XXXX: invitaci?n por oficio (una sola vez)
            if re.match(RUANA_CODIGO_INVITACION_REGEX, codigo_inv_upper):
                db.consumir_invitacion_oficio(codigo_inv_upper, result['codigo'])
            elif codigo_campana_invitacion:
                db.consumir_campana_invitacion(codigo_campana_invitacion, result['codigo'])
            else:
                if not db.consumir_invitacion_y_recompensar(codigo_invitacion, result['codigo']):
                    db.asegurar_referido_desde_invitacion(codigo_invitacion, result['codigo'])
                # Limpia placeholder legacy si existía con el mismo código de invitación
                if hasattr(db, 'eliminar_aliado_placeholder'):
                    db.eliminar_aliado_placeholder(codigo_invitacion_simple or codigo_invitacion)
                # Si el código venía de «Conozco a alguien», vincular la solicitud al nuevo aliado
                if hasattr(db, 'vincular_solicitud_a_aliado_incorporado'):
                    try:
                        db.vincular_solicitud_a_aliado_incorporado(
                            codigo_invitacion_simple or codigo_invitacion,
                            result['codigo'],
                        )
                    except Exception as e:
                        print(f"[RUANA] Aviso vinculando solicitud a aliado incorporado: {e}")

        # Asegurar red completa: invitaciones pendientes de sync y huérfanos bajo admin
        db.sincronizar_referidos_completo()

        # Envío de correo de bienvenida (no bloquea el registro si falla)
        codigo_aliado = (result.get('codigo') or '').strip()
        if codigo_aliado:
            try:
                enviar_correo_bienvenida_aliado(
                    nombre=nombre,
                    email=email,
                    codigo=codigo_aliado,
                )
            except Exception as email_err:
                print(f"[RUANA][EMAIL] Error inesperado al enviar correo de bienvenida: {email_err}")

        return jsonify(result), 201
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@aliado_bp.route('/api/aliados/obtener-por-codigo/<codigo>', methods=['GET'])
def obtener_aliado_codigo(codigo):
    """
    GET /api/aliados/obtener-por-codigo/XXXXX
    
    Obtiene aliado por su c?digo (5 d?gitos o legacy alfanum?rico)
    F08: Aceptar c?digos num?ricos (12345) y legacy (A0001)
    Retorna todos sus datos para renderizar el panel din?mico
    """
    try:
        codigo = codigo.strip()
        auth_err = _forbidden_unless_admin_or_aliado_self(codigo)
        if auth_err:
            return auth_err
        
        # F08: Validaci?n de formato para compatibilidad legacy
        # Aceptar:
        #   - d?gitos num?ricos (^\d{5}$)  ? ej: 47604
        #   - legacy 1 letra + 4 d?gitos (^[A-Z]\d{4}$) ? ej: A0001
        #   - legacy 4 letras + 2 d?gitos (^[A-Z]{4}\d{2}$) ? ej: ALFA01/BETA02
        import re
        if not codigo:
            return jsonify({
                'status': 'error',
                'message': 'C?digo requerido'
            }), 400
        
        # Validar formato: 5 d?gitos OR 1 letra + 4 d?gitos OR 4 letras + 2 d?gitos (legacy)
        if not (
            re.match(r'^\d{5}$', codigo) or
            re.match(r'^[A-Z]\d{4}$', codigo) or
            re.match(r'^[A-Z]{4}\d{2}$', codigo)
        ):
            return jsonify({
                'status': 'error',
                'message': 'C?digo inv?lido (debe ser 5 d?gitos o formato legacy como A0001)'
            }), 400
        
        db = get_db()
        aliado = db.obtener_aliado_por_codigo(codigo)
        
        if not aliado:
            return jsonify({
                'status': 'error',
                'message': f'Aliado con c?digo {codigo} no encontrado'
            }), 404

        # Cuenta pendiente de validaci?n: se avisa al usuario y sus datos est?n en el panel admin para aceptar/rechazar
        if aliado.get('estado') == 'pendiente_validacion':
            return jsonify({
                'status': 'error',
                'message': 'Tu cuenta est? pendiente de validaci?n. Tus datos est?n en el panel de administraci?n en la secci?n "Pendientes de validaci?n", donde un administrador puede aceptarte o rechazarte. Cuando te activen, podr?s entrar con este mismo c?digo.'
            }), 403
        if aliado.get('estado') == 'rechazado':
            return jsonify({
                'status': 'error',
                'message': 'Tu solicitud de registro no fue aceptada. Contacta al administrador si crees que es un error.'
            }), 403
        
        # Obtener solicitudes del grupo si tiene c?digo postal
        solicitudes = []
        if aliado.get('codigo_postal'):
            solicitudes = db.obtener_solicitudes_grupo(aliado['codigo_postal'])
        
        aliado_dict = dict(aliado)
        aliado_dict['estado_ruana'] = db.score_a_estado(aliado.get('score'))
        aliado_dict['referidos_count'] = db.contar_referidos_por_codigo(codigo)
        contar_contestadas = getattr(db, 'contar_solicitudes_enviadas_contestadas', lambda c: 0)
        aliado_dict['solicitudes_enviadas_contestadas'] = contar_contestadas(codigo)
        
        return jsonify({
            'status': 'success',
            'aliado': aliado_dict,
            'solicitudes': solicitudes,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@aliado_bp.route('/api/aliados/verificar-codigo/<codigo>', methods=['GET'])
@require_admin
def verificar_codigo_existe(codigo):
    """
    GET /api/aliados/verificar-codigo/XXXXX
    
    Verifica si un c?digo ya existe en la BD
    Usado por el frontend para validaci?n de unicidad
    """
    try:
        codigo = codigo.strip()
        db = get_db()
        
        existe = db.codigo_existe(codigo)
        
        return jsonify({
            'status': 'success',
            'existe': existe,
            'codigo': codigo
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@aliado_bp.route('/api/aliados/listar', methods=['GET'])
@require_admin
def listar_aliados_db():
    """
    GET /api/aliados/listar
    GET /api/aliados/listar?codigo_postal=080001
    
    Lista todos los aliados o filtra por c?digo postal
    """
    try:
        codigo_postal = request.args.get('codigo_postal', '').strip() or None
        
        db = get_db()
        aliados = db.listar_aliados(codigo_postal)

        return jsonify({
            'status': 'success',
            'total': len(aliados),
            'aliados': aliados,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@aliado_bp.route('/api/aliado/pausar', methods=['POST'])
@require_admin_escritura
def pausar_aliado():
    """
    POST /api/aliado/pausar

    Body JSON:
    {
        "codigo": "12345",
        "razon": "Motivo opcional de la pausa"
    }
    """
    try:
        data = request.get_json() or {}
        codigo = (data.get('codigo') or '').strip()
        razon = (data.get('razon') or '').strip() or None

        if not codigo:
            return jsonify({'status': 'error', 'message': 'C?digo de aliado obligatorio'}), 400

        db = get_db()
        admin_codigo = _admin_codigo() or ''
        result = db.pausar_aliado(codigo, razon, admin_codigo=admin_codigo or None)

        status_code = 200 if result.get('status') == 'success' else 400
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@aliado_bp.route('/api/aliados/<codigo>/foto-perfil', methods=['POST'])
@require_aliado
def subir_foto_perfil_aliado(codigo):
    """
    POST /api/aliados/<codigo>/foto-perfil
    Sube o reemplaza la foto de perfil del aliado. Solo el propio aliado en sesión.
    Form: archivo (o file). Formatos: jpg, png, gif, webp, heic, heif. Máx. 15 MB.
    """
    try:
        codigo = (codigo or '').strip()
        if codigo != _aliado_codigo():
            return jsonify({'status': 'error', 'message': 'No autorizado a actualizar otro aliado'}), 403
        if 'archivo' not in request.files and 'file' not in request.files:
            return jsonify({'status': 'error', 'message': 'Falta el archivo (archivo o file)'}), 400
        file = request.files.get('archivo') or request.files.get('file')
        if not file or not file.filename:
            return jsonify({'status': 'error', 'message': 'Archivo vacío'}), 400
        ext = (Path(file.filename).suffix or '.bin').lower()
        if ext not in ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.heic', '.heif'):
            return jsonify({'status': 'error', 'message': 'Formato no permitido. Usa una imagen (jpg, png, gif, webp o heic).'}), 400
        storage_result = upload_foto_perfil_file(
            file_obj=file.stream,
            original_filename=file.filename,
            prefix=codigo,
        )
        db = get_db()
        result = db.actualizar_aliado(codigo, foto_perfil_url=storage_result['url'])
        if result.get('status') != 'success':
            return jsonify(result), 400
        return jsonify({
            'status': 'success',
            'message': 'Foto de perfil actualizada',
            'foto_perfil_url': storage_result['url'],
        }), 200
    except ValueError as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400
    except Exception as e:
        msg = str(e)
        if '413' in msg or 'Payload too large' in msg or 'maximum allowed size' in msg:
            return jsonify({
                'status': 'error',
                'message': 'La imagen es demasiado pesada para almacenarla. Prueba con otra foto.',
            }), 400
        return jsonify({'status': 'error', 'message': str(e)}), 500


@aliado_bp.route('/api/aliados/<codigo>/foto-perfil', methods=['DELETE'])
@require_aliado
def eliminar_foto_perfil_aliado(codigo):
    """DELETE /api/aliados/<codigo>/foto-perfil — quita la foto y vuelve a mostrar iniciales."""
    try:
        codigo = (codigo or '').strip()
        if codigo != _aliado_codigo():
            return jsonify({'status': 'error', 'message': 'No autorizado a actualizar otro aliado'}), 403
        db = get_db()
        result = db.actualizar_aliado(codigo, foto_perfil_url=None)
        if result.get('status') != 'success':
            return jsonify(result), 400
        return jsonify({'status': 'success', 'message': 'Foto de perfil eliminada'}), 200
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@aliado_bp.route('/api/aliados/<codigo>', methods=['PUT'])
@require_aliado
def actualizar_aliado_db(codigo):
    """
    PUT /api/aliados/XXXXX
    Actualiza datos del aliado. Solo se permite actualizar el propio c?digo (sesi?n).
    """
    try:
        codigo = codigo.strip()
        if codigo != _aliado_codigo():
            return jsonify({'status': 'error', 'message': 'No autorizado a actualizar otro aliado'}), 403
        data = request.get_json() or {}
        data = {k: v for k, v in data.items() if k in _ALIADO_SELF_EDITABLE_FIELDS}
        db = get_db()
        result = db.actualizar_aliado(codigo, **data)
        
        if result['status'] == 'error':
            return jsonify(result), 400
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@aliado_bp.route('/api/aliados/<codigo>/catalogo-servicios', methods=['GET'])
@require_aliado
def ver_catalogo_servicios_aliado(codigo):
    """
    GET /api/aliados/<codigo>/catalogo-servicios
    Catálogo privado del profesional (solo servicios configurados).
    Visible si está en el directorio del aliado o hay contacto activo.
    """
    try:
        visor = _aliado_codigo()
        if not visor:
            return jsonify({'status': 'error', 'message': 'Sesión expirada'}), 401
        objetivo = (codigo or '').strip()
        if not objetivo:
            return jsonify({'status': 'error', 'message': 'Código de aliado requerido'}), 400
        db = get_db()
        if not db.puede_ver_catalogo_aliado(visor, objetivo):
            return jsonify({'status': 'error', 'message': 'No autorizado a ver este catálogo'}), 403
        servicios = db.listar_catalogo_servicios_configurados(objetivo)
        return jsonify({
            'status': 'success',
            'codigo': objetivo,
            'servicios': servicios,
            'catalogo_servicios': servicios,
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@aliado_bp.route('/api/aliados/<codigo>/catalogo-servicios/<int:posicion>', methods=['PUT'])
@require_aliado
def guardar_catalogo_servicio_aliado(codigo, posicion):
    """
    PUT /api/aliados/<codigo>/catalogo-servicios/<posicion>
    Guarda una posición (1..10) del catálogo privado del aliado autenticado.
    """
    try:
        codigo = (codigo or '').strip()
        if codigo != _aliado_codigo():
            return jsonify({'status': 'error', 'message': 'No autorizado a actualizar otro aliado'}), 403
        data = request.get_json() or {}
        descripcion = data.get('descripcion')
        precio = data.get('precio')
        db = get_db()
        result = db.guardar_catalogo_servicio_aliado(codigo, posicion, descripcion, precio)
        if result.get('status') != 'success':
            return jsonify(result), 400
        return jsonify(result), 200
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500



@aliado_bp.route('/api/aliados/<codigo>/notificaciones', methods=['GET'])
@require_aliado
def get_notificaciones_aliado(codigo):
    """
    GET /api/aliados/XXXXX/notificaciones
    Lista notificaciones del aliado. Solo se permite el c?digo de la sesi?n.
    """
    try:
        codigo = (codigo or "").strip()
        if codigo != _aliado_codigo():
            return jsonify({'status': 'error', 'message': 'No autorizado'}), 403
        limite = request.args.get('limite', 50, type=int)
        db = get_db()
        notificaciones = notificacion_service.listar_notificaciones_aliado(
            db, codigo, limite=limite
        )
        return jsonify({'status': 'success', 'notificaciones': notificaciones})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@aliado_bp.route('/api/aliados/<codigo>/notificaciones/marcar-todas-leidas', methods=['POST'])
@require_aliado
def marcar_todas_notificaciones_leidas_api(codigo):
    """
    POST /api/aliados/<codigo>/notificaciones/marcar-todas-leidas
    Marca todas las notificaciones del aliado como le?das. Solo c?digo de sesi?n.
    """
    try:
        codigo = (codigo or "").strip()
        if codigo != _aliado_codigo():
            return jsonify({'status': 'error', 'message': 'No autorizado'}), 403
        db = get_db()
        result = notificacion_service.marcar_todas_notificaciones_leidas(db, codigo)
        if result.get('status') == 'error':
            return jsonify(result), 400
        return jsonify(result)
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@aliado_bp.route('/api/aliados/<codigo>/notificaciones/<int:notif_id>/leida', methods=['POST'])
@require_aliado
def marcar_notificacion_leida_api(codigo, notif_id):
    """
    POST /api/aliados/XXXXX/notificaciones/<id>/leida
    Marca una notificaci?n como le?da. Solo c?digo de sesi?n.
    """
    try:
        codigo = (codigo or "").strip()
        if codigo != _aliado_codigo():
            return jsonify({'status': 'error', 'message': 'No autorizado'}), 403
        db = get_db()
        result = notificacion_service.marcar_notificacion_leida(db, notif_id, codigo)
        if result.get('status') == 'error':
            return jsonify(result), 400
        return jsonify(result)
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


