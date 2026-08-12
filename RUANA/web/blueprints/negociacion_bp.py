"""Blueprint de negociación guiada (Campamento Base #2).

Rutas movidas desde web/app.py. Comportamiento y paths idénticos.
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from core import db_manager as db_manager_mod
from core.services import negociacion_service
from web.auth_decorators import _aliado_codigo, require_aliado

negociacion_bp = Blueprint("negociacion", __name__)


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


def priorizar_contactos_negociacion(contactos):
    """Prioriza contactos con negociación en curso / acuerdo."""
    def en_curso(c):
        if c.get("estado") == "acuerdo_alcanzado":
            return 1
        if c.get("negociacion_completa"):
            return 1
        return 0

    return sorted(contactos or [], key=en_curso)


@negociacion_bp.route("/api/negociacion/health", methods=["GET"])
def negociacion_health():
    """Ping ligero del dominio negociación."""
    return jsonify({"status": "ok", "dominio": "negociacion"})


@negociacion_bp.route("/api/contactos/<int:contacto_id>/negociacion", methods=["GET"])
@require_aliado
def negociacion_get(contacto_id):
    """GET estado completo de la negociación guiada."""
    codigo = _aliado_codigo()
    if not codigo:
        return jsonify({"status": "error", "message": "Sesión expirada"}), 401
    db = get_db()
    result = negociacion_service.obtener_negociacion_contacto(db, contacto_id, codigo)
    code = 200 if result.get("status") == "success" else 400
    if result.get("message") == "Contacto no encontrado":
        code = 404
    elif result.get("message") == "No autorizado":
        code = 403
    return jsonify(result), code


@negociacion_bp.route("/api/contactos/<int:contacto_id>/negociacion/proponer", methods=["POST"])
@require_aliado
def negociacion_proponer(contacto_id):
    """POST propuesta de valor en el paso actual (solo contratante)."""
    codigo = _aliado_codigo()
    if not codigo:
        return jsonify({"status": "error", "message": "Sesión expirada"}), 401
    data = request.get_json() or {}
    campo = (data.get("campo") or "").strip()
    valor = (data.get("valor") or "").strip()
    if not campo:
        return jsonify({"status": "error", "message": "campo es obligatorio"}), 400
    db = get_db()
    result = negociacion_service.proponer_negociacion(db, contacto_id, codigo, campo, valor)
    return jsonify(result), 200 if result.get("status") == "success" else 400


@negociacion_bp.route(
    "/api/contactos/<int:contacto_id>/negociacion/proponer-completa", methods=["POST"]
)
@require_aliado
def negociacion_proponer_completa(contacto_id):
    """POST propuesta completa del contratante (todos los campos a la vez)."""
    codigo = _aliado_codigo()
    if not codigo:
        return jsonify({"status": "error", "message": "Sesión expirada"}), 401
    data = request.get_json() or {}
    campos = {
        "servicio": (data.get("servicio") or "").strip(),
        "fecha": (data.get("fecha") or "").strip(),
        "hora": (data.get("hora") or "").strip(),
        "direccion": (data.get("direccion") or "").strip(),
        "observaciones": (data.get("observaciones") or "").strip(),
    }
    precio_catalogo = (data.get("precio_catalogo") or "").strip()
    db = get_db()
    result = negociacion_service.proponer_propuesta_completa_negociacion(
        db, contacto_id, codigo, campos, precio_catalogo=precio_catalogo,
    )
    return jsonify(result), 200 if result.get("status") == "success" else 400


@negociacion_bp.route("/api/contactos/<int:contacto_id>/negociacion/aceptar", methods=["POST"])
@require_aliado
def negociacion_aceptar(contacto_id):
    """POST aceptar propuesta vigente de un campo."""
    codigo = _aliado_codigo()
    if not codigo:
        return jsonify({"status": "error", "message": "Sesión expirada"}), 401
    data = request.get_json() or {}
    campo = (data.get("campo") or "").strip()
    obs_prof = (data.get("observaciones_profesional") or "").strip()
    if not campo:
        return jsonify({"status": "error", "message": "campo es obligatorio"}), 400
    db = get_db()
    result = negociacion_service.aceptar_negociacion(db, contacto_id, codigo, campo, obs_prof)
    return jsonify(result), 200 if result.get("status") == "success" else 400


@negociacion_bp.route(
    "/api/contactos/<int:contacto_id>/negociacion/contraoferta", methods=["POST"]
)
@require_aliado
def negociacion_contraoferta(contacto_id):
    """POST contraoferta sobre un campo en negociación."""
    codigo = _aliado_codigo()
    if not codigo:
        return jsonify({"status": "error", "message": "Sesión expirada"}), 401
    data = request.get_json() or {}
    campo = (data.get("campo") or "").strip()
    valor = (data.get("valor") or "").strip()
    renegociar = data.get("renegociar") in (True, 1, "1", "true", "True")
    if not campo or not valor:
        return jsonify({"status": "error", "message": "campo y valor son obligatorios"}), 400
    db = get_db()
    result = negociacion_service.contraoferta_negociacion(
        db, contacto_id, codigo, campo, valor, renegociar=renegociar
    )
    return jsonify(result), 200 if result.get("status") == "success" else 400


@negociacion_bp.route("/api/contactos/<int:contacto_id>/negociacion/cerrar", methods=["POST"])
@require_aliado
def negociacion_cerrar(contacto_id):
    """POST — cierra la negociación."""
    codigo = _aliado_codigo()
    if not codigo:
        return jsonify({"status": "error", "message": "Sesión expirada"}), 401
    data = request.get_json() or {}
    motivo = (data.get("motivo") or "").strip()
    db = get_db()
    result = negociacion_service.cerrar_negociacion(db, contacto_id, codigo, motivo=motivo)
    return jsonify(result), 200 if result.get("status") == "success" else 400


@negociacion_bp.route(
    "/api/contactos/<int:contacto_id>/negociacion/dismiss-resumen", methods=["POST"]
)
@require_aliado
def negociacion_dismiss_resumen(contacto_id):
    """POST — oculta el panel flotante del resumen del acuerdo."""
    codigo = _aliado_codigo()
    if not codigo:
        return jsonify({"status": "error", "message": "Sesión expirada"}), 401
    db = get_db()
    result = negociacion_service.dismiss_resumen_acuerdo(db, contacto_id, codigo)
    return jsonify(result), 200 if result.get("status") == "success" else 400


@negociacion_bp.route("/api/aliado/acuerdos", methods=["GET"])
@require_aliado
def aliado_listar_acuerdos():
    """GET — historial «Mis acuerdos» del aliado autenticado."""
    codigo = _aliado_codigo()
    if not codigo:
        return jsonify({"status": "error", "message": "Sesión expirada"}), 401
    limite = request.args.get("limite", 100, type=int)
    estado = (request.args.get("estado") or "").strip() or None
    desde = (request.args.get("desde") or "").strip() or None
    hasta = (request.args.get("hasta") or "").strip() or None
    rol = (request.args.get("rol") or "").strip() or None
    db = get_db()
    acuerdos = negociacion_service.listar_acuerdos_aliado(
        db,
        codigo,
        limite=limite,
        estado=estado,
        desde=desde,
        hasta=hasta,
        rol=rol,
    )
    return jsonify({
        "status": "success",
        "acuerdos": acuerdos,
        "estados_disponibles": [
            {"valor": k, "label": v}
            for k, v in db.CONTACTO_ESTADO_LABELS.items()
        ],
    })


@negociacion_bp.route("/api/aliado/resumenes-acuerdo", methods=["GET"])
@require_aliado
def aliado_resumenes_acuerdo():
    """GET — acuerdos con resumen flotante aún visible."""
    codigo = _aliado_codigo()
    if not codigo:
        return jsonify({"status": "error", "message": "Sesión expirada"}), 401
    db = get_db()
    resumenes = negociacion_service.listar_resumenes_acuerdo_visibles(db, codigo)
    return jsonify({"status": "success", "resumenes": resumenes})

# ---------- Legacy chat libre → negociación ----------

@negociacion_bp.route('/api/chat_mensajes', methods=['GET'])
@negociacion_bp.route('/api/chat/mensajes', methods=['GET'])
@negociacion_bp.route('/api/contactos/<int:contacto_id>/mensajes', methods=['GET'])
@require_aliado
def chat_legacy_get_redirect(contacto_id=None):
    cid = contacto_id or request.args.get('contacto_id', type=int)
    if not cid:
        return jsonify({'status': 'error', 'message': 'El chat libre fue reemplazado por negociación guiada. Usa GET /api/contactos/<id>/negociacion'}), 410
    return negociacion_get(cid)


@negociacion_bp.route('/api/chat_enviar', methods=['POST', 'OPTIONS'])
@negociacion_bp.route('/api/chat/enviar', methods=['POST'])
@negociacion_bp.route('/api/contactos/<int:contacto_id>/mensajes', methods=['POST'])
def chat_legacy_post_disabled(contacto_id=None):
    if request.method == 'OPTIONS':
        return '', 200
    return jsonify({
        'status': 'error',
        'message': 'El chat libre fue reemplazado por negociación guiada. Usa /api/contactos/<id>/negociacion/proponer, /aceptar o /contraoferta',
    }), 410

