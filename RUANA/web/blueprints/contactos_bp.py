"""Blueprint de ciclo de vida de contactos (extraído de web/app.py).

Rutas /api/contactos* (y pago pendiente) que no viven en negociacion_bp.
Comportamiento y paths idénticos.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from flask import Blueprint, jsonify, request

from core import db_manager as db_manager_mod
from core.storage_manager import upload_ruana_file
from web.auth_decorators import _aliado_codigo, require_aliado
from web.blueprints.negociacion_bp import priorizar_contactos_negociacion

contactos_bp = Blueprint("contactos", __name__)


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


@contactos_bp.route("/api/contactos/bp-health", methods=["GET"])
def contactos_bp_health():
    """Ping ligero del dominio contactos."""
    return jsonify({"status": "ok", "dominio": "contactos"})


@contactos_bp.route("/api/contactos", methods=["POST"])
@require_aliado
def crear_contacto():
    """
    POST /api/contactos
    Crea un contacto RUANA. solicitante_codigo debe ser el aliado en sesi?n (no se conf?a en body).
        Body JSON: profesional_codigo, servicio, motivo_contacto (opcional), es_urgente (opcional).
    """
    try:
        solicitante_codigo = _aliado_codigo()
        if not solicitante_codigo:
            return jsonify({'status': 'error', 'message': 'Sesi?n expirada'}), 401
        data = request.get_json() or {}
        profesional_codigo = (data.get('profesional_codigo') or '').strip()
        servicio = (data.get('servicio') or '').strip()
        motivo_contacto = (data.get('motivo_contacto') or '').strip() or 'Negociación guiada'
        es_urgente_raw = data.get('es_urgente', False)
        es_urgente = es_urgente_raw in (True, 1, '1', 'true', 'True', 'yes', 'on')
        precio_catalogo = (data.get('precio_catalogo') or '').strip()

        if not profesional_codigo:
            return jsonify({
                'status': 'error',
                'message': 'profesional_codigo es obligatorio'
            }), 400

        db = get_db()
        result = db.crear_contacto_ruana(
            solicitante_codigo=solicitante_codigo,
            profesional_codigo=profesional_codigo,
            servicio=servicio,
            motivo_contacto=motivo_contacto,
            es_urgente=es_urgente,
            precio_catalogo=precio_catalogo,
        )

        status_code = 201 if result.get('status') == 'success' else 400
        return jsonify(result), status_code

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


def _finalizar_chat_contacto_impl(contacto_id):
    """Implementación compartida para finalizar-chat (ocultar contacto del panel del aliado)."""
    usuario = _aliado_codigo()
    if not usuario:
        return jsonify({'status': 'error', 'message': 'Sesión expirada'}), 401
    db = get_db()
    result = db.ocultar_contacto_del_panel(contacto_id, codigo_aliado=usuario)
    status_code = 200 if result.get('status') == 'success' else 400
    return jsonify(result), status_code


@contactos_bp.route("/api/contactos/<int:contacto_id>/finalizar-chat", methods=["POST"])
@require_aliado
def finalizar_chat_contacto(contacto_id):
    """POST /api/contactos/<id>/finalizar-chat - Oculta el contacto del panel del aliado."""
    try:
        return _finalizar_chat_contacto_impl(contacto_id)
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@contactos_bp.route("/api/contactos/<int:contacto_id>/finalizar_chat", methods=["POST"])
@require_aliado
def finalizar_chat_contacto_alias(contacto_id):
    """Alias: POST /api/contactos/<id>/finalizar_chat"""
    try:
        return _finalizar_chat_contacto_impl(contacto_id)
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@contactos_bp.route("/api/contactos/<int:contacto_id>/aceptar", methods=["POST"])
@require_aliado
def aceptar_contacto(contacto_id):
    """
    POST /api/contactos/<id>/aceptar
    El profesional (aliado en sesi?n) acepta el contacto.
    """
    try:
        profesional_codigo = _aliado_codigo()
        if not profesional_codigo:
            return jsonify({'status': 'error', 'message': 'Sesi?n expirada'}), 401

        db = get_db()
        if db.tiene_pagos_ruana_pendientes(profesional_codigo):
            return jsonify({
                'status': 'error',
                'message': 'Tienes pagos pendientes con RUANA. No puedes aceptar nuevos trabajos hasta regularizar la situaci?n.'
            }), 403
        result = db.aceptar_contacto_ruana(contacto_id, profesional_codigo)
        status_code = 200 if result.get('status') == 'success' else 400
        return jsonify(result), status_code

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@contactos_bp.route("/api/contactos/<int:contacto_id>/trabajo-en-progreso", methods=["POST"])
@require_aliado
def marcar_trabajo_en_progreso(contacto_id):
    """
    POST /api/contactos/<id>/trabajo-en-progreso
    Marca el contacto como trabajo_en_progreso. Solo un participante (sesi?n) puede hacerlo.
    """
    try:
        codigo = _aliado_codigo()
        if not codigo:
            return jsonify({'status': 'error', 'message': 'Sesi?n expirada'}), 401
        db = get_db()
        contacto = db.obtener_contacto_resumen(contacto_id)
        if not contacto:
            return jsonify({'status': 'error', 'message': 'Contacto no encontrado'}), 404
        sol = str(contacto.get('solicitante_codigo') or '').strip()
        pro = str(contacto.get('profesional_codigo') or '').strip()
        if codigo not in (sol, pro):
            return jsonify({'status': 'error', 'message': 'No autorizado'}), 403
        result = db.marcar_trabajo_en_progreso(contacto_id)
        status_code = 200 if result.get('status') == 'success' else 400
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@contactos_bp.route("/api/contactos/<int:contacto_id>/no-concretado", methods=["POST"])
@require_aliado
def marcar_contacto_no_concretado(contacto_id):
    """
    POST /api/contactos/<id>/no-concretado
    Cierra el contacto como no concretado. actor = aliado en sesi?n.
    """
    try:
        data = request.get_json() or {}
        motivo = (data.get('motivo') or '').strip()
        usuario = _aliado_codigo() or (data.get('usuario') or '').strip()

        db = get_db()
        result = db.marcar_cerrado_no_concretado(contacto_id, motivo=motivo, actor_codigo=usuario)
        status_code = 200 if result.get('status') == 'success' else 400
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@contactos_bp.route("/api/contactos/<int:contacto_id>/en-conversacion", methods=["POST"])
@require_aliado
def marcar_contacto_en_conversacion(contacto_id):
    """
    POST /api/contactos/<id>/en-conversacion
    Marca el contacto como en_conversacion. actor = aliado en sesi?n.
    """
    try:
        usuario = _aliado_codigo() or (request.get_json() or {}).get('usuario') or ''

        db = get_db()
        result = db.marcar_en_conversacion(contacto_id, actor_codigo=usuario)
        status_code = 200 if result.get('status') == 'success' else 400
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@contactos_bp.route("/api/contactos/<int:contacto_id>/declarar-importe", methods=["POST"])
@require_aliado
def declarar_importe_contacto(contacto_id):
    """
    POST /api/contactos/<id>/declarar-importe
    Confirma el importe del encargo. Si hay precio negociado, ese es el valor oficial
    (no se reingresa manualmente). Preferir body: confirmar_acordado=true.
    """
    try:
        usuario = _aliado_codigo()
        if not usuario:
            return jsonify({'status': 'error', 'message': 'Sesión expirada'}), 401
        data = request.get_json() or {}
        parte = data.get('parte') or 'solicitante'
        moneda = (data.get('moneda') or 'EUR').strip()
        confirmar_acordado = bool(
            data.get('confirmar_acordado')
            or data.get('usar_precio_acordado')
        )
        importe_body = data.get('importe')
        if confirmar_acordado or importe_body in (None, ''):
            importe_body = None
            confirmar_acordado = True

        db = get_db()
        result = db.registrar_importe_contacto(
            contacto_id=contacto_id,
            parte=parte,
            importe=importe_body,
            moneda=moneda,
            usuario=usuario,
            usar_precio_acordado=confirmar_acordado,
        )
        if result.get('status') != 'success':
            print(f"[RUANA] declarar-importe 400: contacto_id={contacto_id} message={result.get('message')}")
        status_code = 200 if result.get('status') == 'success' else 400

        safe_response = {
            'status': result.get('status'),
            'message': result.get('message'),
            'id': result.get('id'),
            'estado': result.get('estado'),
            'importe_acordado': result.get('importe_acordado'),
        }

        return jsonify(safe_response), status_code
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@contactos_bp.route("/api/contactos/metricas", methods=["GET"])
def metricas_contactos():
    """
    GET /api/contactos/metricas

    Devuelve m?tricas agregadas de contactos RUANA:
    - contactos_abiertos
    - contactos_no_resueltos
    - contactos_en_disputa
    - contactos_en_disputa_prolongada
    """
    try:
        db = get_db()
        metricas = db.obtener_metricas_contactos()
        status_code = 200 if metricas.get('status') == 'success' else 500
        return jsonify(metricas), status_code
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@contactos_bp.route("/api/contactos/abiertos/<codigo_aliado>", methods=["GET"])
@require_aliado
def contactos_abiertos_por_codigo(codigo_aliado):
    """
    GET /api/contactos/abiertos/<codigo_aliado>
    Devuelve contactos abiertos del aliado. Solo se permite el c?digo de la sesi?n.
    """
    try:
        codigo_aliado = codigo_aliado.strip()
        if codigo_aliado != _aliado_codigo():
            return jsonify({'status': 'error', 'message': 'No autorizado'}), 403

        db = get_db()
        contactos = db.obtener_contactos_abiertos_por_codigo(codigo_aliado)
        contactos = priorizar_contactos_negociacion(contactos)

        return jsonify({
            'status': 'success',
            'total': len(contactos),
            'contactos': contactos,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@contactos_bp.route("/api/aliado/contactos-pago-pendiente", methods=["GET"])
@require_aliado
def aliado_contactos_pago_pendiente():
    """
    GET /api/aliado/contactos-pago-pendiente
    Lista contactos donde el aliado en sesi?n es profesional y estado_pago = pendiente_pago.
    """
    try:
        codigo = _aliado_codigo()
        if not codigo:
            return jsonify({'status': 'error', 'message': 'Sesi?n expirada'}), 401
        db = get_db()
        lista = db.listar_contactos_pago_pendiente_profesional(codigo)
        return jsonify({'status': 'success', 'contactos': lista})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@contactos_bp.route("/api/contactos/<int:contacto_id>", methods=["GET"])
@require_aliado
def obtener_contacto_resumen(contacto_id):
    """
    GET /api/contactos/<id>
    Devuelve resumen del contacto solo si el aliado en sesi?n es solicitante o profesional.
    """
    try:
        codigo = _aliado_codigo()
        if not codigo:
            return jsonify({'status': 'error', 'message': 'Sesi?n expirada'}), 401
        db = get_db()
        contacto = db.obtener_contacto_resumen(contacto_id)
        if not contacto:
            return jsonify({
                'status': 'error',
                'message': f'Contacto {contacto_id} no encontrado'
            }), 404
        sol = str(contacto.get('solicitante_codigo') or '').strip()
        pro = str(contacto.get('profesional_codigo') or '').strip()
        if codigo not in (sol, pro):
            return jsonify({'status': 'error', 'message': 'No autorizado a ver este contacto'}), 403

        return jsonify({
            'status': 'success',
            'contacto': contacto,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@contactos_bp.route("/api/contactos/<int:contacto_id>/comprobante-apoyo", methods=["POST"])
@require_aliado
def subir_comprobante_apoyo(contacto_id):
    """
    POST /api/contactos/<id>/comprobante-apoyo
    El profesional (aliado en sesi?n) sube comprobante de pago del Apoyo RUANA.
    Form: archivo (o file), comentario (opcional).
    """
    try:
        codigo = _aliado_codigo()
        if not codigo:
            return jsonify({'status': 'error', 'message': 'Sesi?n expirada'}), 401
        if 'archivo' not in request.files and 'file' not in request.files:
            return jsonify({'status': 'error', 'message': 'Falta el archivo (archivo o file)'}), 400
        file = request.files.get('archivo') or request.files.get('file')
        if not file or not file.filename:
            return jsonify({'status': 'error', 'message': 'Archivo vac?o'}), 400
        comentario = (request.form.get('comentario') or '').strip()[:500]
        ext = (Path(file.filename).suffix or '.bin').lower()
        if ext not in ('.pdf', '.jpg', '.jpeg', '.png', '.gif', '.webp'):
            return jsonify({'status': 'error', 'message': 'Formato no permitido. Usa imagen (jpg, png, gif, webp) o PDF.'}), 400
        storage_result = upload_ruana_file(
            file_obj=file.stream,
            original_filename=file.filename,
            bucket='ruana-comprobantes',
            folder='pagos_ruana',
            prefix=str(contacto_id),
            content_type=file.mimetype,
        )
        comprobante_ruta = storage_result['url']
        db = get_db()
        result = db.subir_comprobante_apoyo_ruana(contacto_id, codigo, comprobante_ruta, comentario or None)
        if result.get('status') != 'success':
            return jsonify(result), 400
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@contactos_bp.route("/api/contactos/<int:contacto_id>/impugnar-apoyo", methods=["POST"])
@require_aliado
def impugnar_apoyo(contacto_id):
    """
    POST /api/contactos/<id>/impugnar-apoyo
    El profesional impugna el importe declarado por el contratante.
    """
    try:
        codigo = _aliado_codigo()
        if not codigo:
            return jsonify({'status': 'error', 'message': 'Sesi?n expirada'}), 401
        data = request.get_json(silent=True) or {}
        motivo = (data.get('motivo') or '').strip()
        db = get_db()
        result = db.impugnar_apoyo_ruana(contacto_id, codigo, motivo)
        status_code = 200 if result.get('status') == 'success' else 400
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
