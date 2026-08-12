"""Blueprint admin — bloque dashboard / lecturas (Campamento Base #3).

Rutas GET movidas desde web/app.py. Comportamiento y paths idénticos.
Auth, login/logout y mutaciones destructivas permanecen en app.py por ahora.
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

import json
from datetime import datetime

from core.settings import get_settings
from core.storage_manager import resolve_admin_document_access_url

from core import db_manager as db_manager_mod
from web.auth_decorators import (
    _admin_codigo,
    _admin_permisos,
    require_admin,
)

admin_bp = Blueprint("admin", __name__)


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


@admin_bp.route("/api/admin/bp-health", methods=["GET"])
def admin_bp_health():
    """Ping ligero del blueprint admin (no sustituye /api/admin/validar)."""
    return jsonify({"status": "ok", "dominio": "admin"})


@admin_bp.route("/api/admin/me", methods=["GET"])
@require_admin
def admin_me():
    """GET permisos del admin actual (store por header o JWT)."""
    permisos = _admin_permisos()
    if not permisos and _admin_codigo():
        permisos = ["leer", "escribir", "eliminar", "configurar"]
    return jsonify({"permisos": permisos or []})


@admin_bp.route("/api/admin/health-metrics", methods=["GET"])
@require_admin
def admin_health_metrics():
    """GET métricas de salud del sistema para el panel admin."""
    try:
        db = get_db()
        umbral = request.args.get("umbral_suplentes", 1, type=int)
        umbral = max(0, min(umbral, 10))
        metrics = db.obtener_health_metrics_admin(umbral_suplentes=umbral)
        return jsonify(metrics)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@admin_bp.route("/api/admin/stats-24h", methods=["GET"])
@require_admin
def admin_stats_24h():
    """GET métricas de movimiento en las últimas 24h."""
    try:
        db = get_db()
        data = db.obtener_stats_24h_panel()
        return jsonify({"status": "success", **data})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@admin_bp.route("/api/admin/invitaciones-recientes", methods=["GET"])
@require_admin
def admin_invitaciones_recientes():
    """GET últimas invitaciones generadas."""
    try:
        limite = request.args.get("limite", type=int) or 20
        limite = min(max(1, limite), 100)
        db = get_db()
        lista = db.listar_invitaciones_recientes(limite=limite)
        return jsonify({"status": "success", "invitaciones": lista})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@admin_bp.route("/api/admin/dashboard-summary", methods=["GET"])
@require_admin
def admin_dashboard_summary():
    """GET resumen del dashboard global para el panel admin."""
    try:
        db = get_db()
        aliados = db.listar_aliados()
        total_users = len(aliados)
        active_users = len([a for a in aliados if a.get("estado") == "activo"])
        retadores = db.contar_retadores_activos()
        suplentes = retadores  # alias
        en_espera = db.contar_aliados_en_espera() if hasattr(db, "contar_aliados_en_espera") else 0
        en_riesgo = db.contar_aliados_en_riesgo()
        solicitudes_activas = db.contar_solicitudes_activas()
        oficios_ocupados = db.contar_oficios_ocupados()
        grupos_data = db.contar_grupos()
        grupos = int(grupos_data.get("total", 0) or 0)

        contactos_metricas = db.obtener_metricas_contactos()
        contactos_disputa = contactos_metricas.get("contactos_en_disputa", 0) or 0
        contactos_disputa_prolongada = contactos_metricas.get(
            "contactos_en_disputa_prolongada", 0
        ) or 0
        pct_riesgo = (en_riesgo / active_users * 100) if active_users else 0
        if pct_riesgo <= 10 and contactos_disputa <= 2 and contactos_disputa_prolongada == 0:
            estado_sistema = "Estable"
        elif pct_riesgo <= 25 and contactos_disputa <= 5:
            estado_sistema = "Alerta"
        else:
            estado_sistema = "Cr?tico"

        return jsonify({
            "total_users": total_users,
            "active_users": active_users,
            "retadores": retadores,
            "suplentes": suplentes,
            "en_espera": en_espera,
            "en_riesgo": en_riesgo,
            "solicitudes_activas": solicitudes_activas,
            "oficios_ocupados": oficios_ocupados,
            "grupos": grupos,
            "grupos_activos": int(grupos_data.get("activos", 0) or 0),
            "grupos_en_competencia": int(grupos_data.get("en_competencia", 0) or 0),
            "grupos_disueltos": int(grupos_data.get("disueltos", 0) or 0),
            "estado_sistema": estado_sistema,
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@admin_bp.route("/api/admin/suplentes-espera", methods=["GET"])
@require_admin
def admin_suplentes_espera():
    """GET aliados en estado en_espera."""
    try:
        db = get_db()
        aliados = db.listar_aliados_en_espera()
        return jsonify({"status": "success", "aliados": aliados, "total": len(aliados)})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@admin_bp.route("/api/admin/pending-users", methods=["GET"])
@admin_bp.route("/api/admin/aliados-pendientes", methods=["GET"])
@require_admin
def admin_pending_users():
    """GET aliados pendiente_validacion."""
    try:
        db = get_db()
        aliados = db.listar_aliados_pendiente_validacion()
        return jsonify({"status": "success", "aliados": aliados, "total": len(aliados)})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# --- Campamento Base #3 Fase 2: más lecturas admin ---

@admin_bp.route('/api/admin/metodos-pago', methods=['GET'])
@require_admin
def admin_obtener_metodos_pago():
    """Admin lee la configuracion actual de metodos de pago."""
    try:
        db = get_db()
        return jsonify({'status': 'success', 'metodos': db.obtener_metodos_pago_ruana()}), 200
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@admin_bp.route('/api/admin/aliados/<codigo>/catalogo-servicios', methods=['GET'])
@require_admin
def admin_ver_catalogo_servicios_aliado(codigo):
    """
    GET /api/admin/aliados/<codigo>/catalogo-servicios
    Consulta privada del catálogo de servicios del aliado para administración.
    """
    try:
        codigo = (codigo or '').strip()
        if not codigo:
            return jsonify({'status': 'error', 'message': 'Código requerido'}), 400
        db = get_db()
        aliado = db.obtener_aliado_por_codigo(codigo)
        if not aliado:
            return jsonify({'status': 'error', 'message': f'Aliado {codigo} no encontrado'}), 404
        catalogo = db.listar_catalogo_servicios_aliado(codigo)
        return jsonify({
            'status': 'success',
            'codigo': codigo,
            'nombre': aliado.get('nombre') or codigo,
            'catalogo_servicios': catalogo,
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@admin_bp.route('/api/admin/evaluaciones/<codigo_aliado>', methods=['GET'])
@require_admin
def admin_obtener_evaluacion(codigo_aliado):
    """
    GET /api/admin/evaluaciones/XXXXX
    Obtiene la evaluaci?n de un aliado para el panel admin (VER DETALLE).
    Si no existe en BD, calcula m?tricas e intenci?n/severidad/razones con el motor.
    """
    try:
        codigo_aliado = (codigo_aliado or '').strip()
        if not codigo_aliado:
            return jsonify({'status': 'error', 'message': 'Código de aliado requerido'}), 400
        db = get_db()
        evaluacion = db.obtener_evaluacion(codigo_aliado)
        if evaluacion:
            # Asegurar razones como lista para el frontend
            r = evaluacion.get('razones')
            if r is not None and not isinstance(r, list):
                try:
                    evaluacion = dict(evaluacion)
                    evaluacion['razones'] = json.loads(r) if isinstance(r, str) else (r if isinstance(r, list) else [])
                except Exception:
                    evaluacion = dict(evaluacion)
                    evaluacion['razones'] = []
            return jsonify({'status': 'success', 'evaluacion': evaluacion, 'timestamp': datetime.now().isoformat()})
        # Sin fila en evaluaciones: calcular m?tricas y decisión del motor (sin persistir)
        metrics = db.obtener_metricas_motor_por_aliado(codigo_aliado)
        from engines.motor_evaluacion import MotorEvaluacion
        motor = MotorEvaluacion()
        decision = motor._evaluar_aliado(codigo_aliado, metrics)
        decision = motor._incorporar_persistencia(codigo_aliado, decision)
        evaluacion = {
            'intencion': decision.get('intencion', ''),
            'tasa_respuesta': metrics.get('tasa_respuesta'),
            'tasa_confirmacion': metrics.get('tasa_confirmacion'),
            'meses_sin_trabajo': metrics.get('meses_sin_trabajo'),
            'severidad': decision.get('severidad', 'normal'),
            'razones': decision.get('razones', []),
            'estado': decision.get('estado'),
            'score': decision.get('score'),
            'actualizado_en': datetime.now().isoformat(),
        }
        return jsonify({'status': 'success', 'evaluacion': evaluacion, 'timestamp': datetime.now().isoformat()})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


def _registro_url_para_invitacion(codigo):
    base = (getattr(get_settings(), 'public_app_url', '') or request.host_url).rstrip('/')
    return f"{base}/invite.html?codigo={codigo}"


@admin_bp.route('/api/admin/invitacion-campanas', methods=['GET'])
@require_admin
def admin_listar_campanas_invitacion():
    """GET /api/admin/invitacion-campanas - Lista codigos multiuso de invitacion."""
    try:
        limite = request.args.get('limite', type=int) or 50
        db = get_db()
        campanas = db.listar_campanas_invitacion(limite=limite)
        for campana in campanas:
            campana['registro_url'] = _registro_url_para_invitacion(campana.get('codigo', ''))
        return jsonify({'status': 'success', 'campanas': campanas})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@admin_bp.route('/api/admin/aliados-eliminados', methods=['GET'])
@require_admin
def admin_listar_aliados_eliminados():
    """
    GET /api/admin/aliados-eliminados
    Lista el archivo de aliados eliminados definitivamente (solo registro de auditoría).
    """
    try:
        db = get_db()
        aliados = db.listar_aliados_eliminados()
        return jsonify({'status': 'success', 'aliados': aliados}), 200
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@admin_bp.route('/api/admin/grupos/<int:grupo_id>/oficios-cerrados', methods=['GET'])
@require_admin
def admin_grupo_oficios_cerrados(grupo_id):
    """
    GET /api/admin/grupos/<grupo_id>/oficios-cerrados
    Lista oficios cerrados en ese grupo (para modal Abrir plaza → Reabrir plaza cerrada).
    """
    try:
        db = get_db()
        oficios = db.listar_oficios_cerrados_grupo(grupo_id)
        return jsonify({'status': 'success', 'oficios': oficios})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@admin_bp.route('/api/admin/solicitudes', methods=['GET'])
@require_admin
def admin_solicitudes():
    """
    GET /api/admin/solicitudes
    Todas las solicitudes (pendientes y atendidas). Orden created_at DESC.
    """
    try:
        db = get_db()
        lista = db.listar_solicitudes_admin_todas()
        return jsonify(lista)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/api/admin/payment-conflicts', methods=['GET'])
@admin_bp.route('/api/admin/conflictos-pago', methods=['GET'])
@require_admin
def admin_payment_conflicts():
    """
    GET /api/admin/payment-conflicts
    Lista conflictos desde payment_conflicts (orden created_at DESC).
    Campos: id, trabajo_id, contratante_nombre, profesional_nombre, importes, estado, prueba_url, created_at.
    """
    try:
        db = get_db()
        lista = db.listar_payment_conflicts_admin()
        return jsonify({'status': 'success', 'conflictos': lista, 'total': len(lista)})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@admin_bp.route('/api/admin/payment-conflicts/<int:conflict_id>', methods=['GET'])
@require_admin
def admin_payment_conflict_detail(conflict_id):
    """
    GET /api/admin/payment-conflicts/<id>
    Detalle de un conflicto para el panel admin (datos completos + prueba_url).
    """
    try:
        db = get_db()
        c = db.obtener_payment_conflict(conflict_id)
        if not c:
            return jsonify({'status': 'error', 'message': 'Conflicto no encontrado'}), 404
        return jsonify({'status': 'success', 'conflicto': c})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@admin_bp.route('/api/admin/conversations', methods=['GET'])
@admin_bp.route('/api/admin/contactos-conversaciones', methods=['GET'])
@require_admin
def admin_conversations():
    """
    GET /api/admin/conversations
    Lista contactos con: id, solicitante, profesional, servicio, estado, importe,
    total_mensajes, ultimo_mensaje, fecha_inicio, fecha_cierre.
    """
    try:
        db = get_db()
        limite = request.args.get('limite', 10000, type=int)
        limite = min(max(1, limite), 50000)
        raw = db.listar_contactos_recientes_con_chat(limite=limite)
        lista = []
        for c in raw:
            lista.append({
                'id': c.get('id'),
                'solicitante': c.get('solicitante_codigo'),
                'profesional': c.get('profesional_codigo'),
                'servicio': c.get('servicio'),
                'estado': c.get('estado'),
                'importe': c.get('importe_final'),
                'total_mensajes': c.get('num_mensajes', 0),
                'ultimo_mensaje': c.get('ultimo_mensaje_en'),
                'fecha_inicio': c.get('creado_en'),
                'fecha_cierre': c.get('fecha_cierre') or c.get('fecha_no_concretado'),
                # Compatibilidad con renderConversaciones
                'solicitante_codigo': c.get('solicitante_codigo'),
                'profesional_codigo': c.get('profesional_codigo'),
                'motivo_contacto': c.get('motivo_contacto'),
                'es_urgente': bool(c.get('es_urgente')),
                'urgente_marcado_en': c.get('urgente_marcado_en'),
                'importe_final': c.get('importe_final'),
                'comision': c.get('comision'),
                'num_mensajes': c.get('num_mensajes'),
                'ultimo_mensaje_en': c.get('ultimo_mensaje_en'),
                'creado_en': c.get('creado_en'),
            })
        return jsonify({'status': 'success', 'contactos': lista})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@admin_bp.route('/api/admin/competencias-activas', methods=['GET'])
@require_admin
def admin_competencias_activas():
    """
    GET /api/admin/competencias-activas
    Lista competencias activas: titular, suplente, grupo origen, scores, tiempo en competencia.
    Ordenado por fecha_inicio ascendente (m?s antiguas arriba).
    """
    try:
        db = get_db()
        try:
            db.procesar_competencia_automatica()
        except Exception:
            pass
        lista = db.listar_competencias_activas_admin()
        return jsonify({'status': 'success', 'competencias': lista})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@admin_bp.route('/api/admin/competencias-pendientes', methods=['GET'])
@require_admin
def admin_competencias_pendientes():
    """GET /api/admin/competencias-pendientes — titulares esperando retador."""
    try:
        db = get_db()
        lista = db.listar_competencias_pendientes_admin()
        return jsonify({'status': 'success', 'pendientes': lista})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@admin_bp.route('/api/admin/competencias-historial', methods=['GET'])
@require_admin
def admin_competencias_historial():
    """GET /api/admin/competencias-historial — auditoría de competencias finalizadas."""
    try:
        limite = request.args.get('limite', 50, type=int)
        db = get_db()
        lista = db.listar_competencias_historial_admin(limite=limite)
        return jsonify({'status': 'success', 'historial': lista})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@admin_bp.route('/api/admin/negociaciones', methods=['GET'])
@admin_bp.route('/api/admin/chats', methods=['GET'])
@require_admin
def admin_negociaciones():
    """
    GET /api/admin/negociaciones — listado de negociaciones guiadas (paginado).
    Alias legacy: /api/admin/chats
    """
    try:
        limite = request.args.get('limite', 10, type=int)
        limite = min(max(1, limite), 100)
        offset = request.args.get('offset', 0, type=int)
        offset = max(0, offset)
        db = get_db()
        raw = db.listar_negociaciones_admin(limite=limite, offset=offset)
        conversaciones = []
        for c in raw:
            conversaciones.append({
                'contacto_id': c.get('contacto_id'),
                'solicitante': c.get('solicitante_codigo') or '',
                'profesional': c.get('profesional_codigo') or '',
                'estado': c.get('estado') or '',
                'paso_actual': c.get('paso_actual') or '',
                'acuerdo_completo': c.get('acuerdo_completo', False),
                'precio_acordado': c.get('precio_acordado') or '',
                'ultimo_evento': (c.get('ultimo_evento') or '')[:200],
                'fecha_ultimo': c.get('fecha_ultimo'),
                'num_eventos': c.get('num_eventos', 0),
                'es_urgente': c.get('es_urgente', False),
            })
        return jsonify({'status': 'success', 'conversaciones': conversaciones, 'negociaciones': conversaciones})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@admin_bp.route('/api/admin/contactos/<int:contacto_id>/negociacion', methods=['GET'])
@admin_bp.route('/api/admin/contactos/<int:contacto_id>/mensajes', methods=['GET'])
@require_admin
def admin_get_negociacion(contacto_id):
    """Detalle de negociación guiada para admin."""
    try:
        db = get_db()
        contacto = db.obtener_contacto_resumen(contacto_id)
        if not contacto:
            return jsonify({'status': 'error', 'message': 'Contacto no encontrado'}), 404
        eventos = db.listar_eventos_negociacion(contacto_id)
        from core import negociacion_manager as neg_mgr
        neg = neg_mgr.parse_negociacion(contacto.get('negociacion_json'))
        return jsonify({
            'status': 'success',
            'contacto_id': contacto_id,
            'solicitante': contacto.get('solicitante_codigo'),
            'profesional': contacto.get('profesional_codigo'),
            'estado_contacto': contacto.get('estado'),
            'resumen': neg_mgr.resumen_acuerdo(neg),
            'negociacion': neg,
            'eventos': eventos,
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@admin_bp.route('/api/admin/chat-messages', methods=['GET'])
@require_admin
def admin_chat_messages_legacy():
    """Legacy — redirige a negociaciones."""
    return jsonify({
        'status': 'error',
        'message': 'El registro de chat libre fue reemplazado. Usa GET /api/admin/negociaciones',
        'messages': [],
    }), 410


@admin_bp.route('/api/admin/centro-comunicacion', methods=['GET'])
@require_admin
def admin_listar_centro_comunicacion():
    try:
        db = get_db()
        conversaciones = db.listar_conversaciones_soporte_admin(
            aliado_codigo=request.args.get('aliado', ''),
            estado=request.args.get('estado', ''),
            solo_no_leidas=(request.args.get('solo_no_leidas', '0') == '1'),
            limite=request.args.get('limite', 100, type=int),
            offset=request.args.get('offset', 0, type=int),
        )
        return jsonify({'status': 'success', 'conversaciones': conversaciones})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@admin_bp.route('/api/admin/centro-comunicacion/<int:conversacion_id>/mensajes', methods=['GET'])
@require_admin
def admin_mensajes_centro_comunicacion(conversacion_id):
    try:
        db = get_db()
        mensajes = db.listar_mensajes_soporte_admin(conversacion_id)
        return jsonify({'status': 'success', 'mensajes': mensajes})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


def _resolve_admin_document_access_url(stored_url):
    """Respeta monkeypatch de web.app.resolve_admin_document_access_url en tests."""
    import sys
    for key in ("RUANA.web.app", "web.app"):
        mod = sys.modules.get(key)
        if mod is not None:
            fn = getattr(mod, "resolve_admin_document_access_url", None)
            if callable(fn):
                return fn(stored_url)
    return resolve_admin_document_access_url(stored_url)


@admin_bp.route('/api/admin/documentos/acceso', methods=['GET'])
@require_admin
def admin_documento_acceso():
    """
    GET /api/admin/documentos/acceso?url=<referencia>
    Devuelve una URL temporal para que el admin pueda abrir comprobantes en bucket privado.
    """
    stored_url = (request.args.get('url') or '').strip()
    if not stored_url:
        return jsonify({'status': 'error', 'message': 'Falta la referencia del documento.'}), 400
    try:
        access_url = _resolve_admin_document_access_url(stored_url)
        return jsonify({'status': 'success', 'url': access_url})
    except ValueError as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@admin_bp.route('/api/admin/pagos-apoyo', methods=['GET'])
@require_admin
def admin_pagos_apoyo():
    """
    GET /api/admin/pagos-apoyo
    Lista contactos con trabajo_cerrado e importe_final (Apoyo RUANA) para confirmar pagos manuales.
    """
    try:
        db = get_db()
        lista = db.listar_contactos_pagos_apoyo()
        return jsonify({'status': 'success', 'pagos': lista})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@admin_bp.route('/api/admin/pagos-en-revision', methods=['GET'])
@require_admin
def admin_pagos_en_revision():
    """
    GET /api/admin/pagos-en-revision
    Lista contactos con estado_pago = en_revision (comprobante subido, pendiente de aprobar/rechazar).
    """
    try:
        db = get_db()
        lista = db.listar_contactos_pagos_en_revision()
        return jsonify({'status': 'success', 'pagos': lista})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
