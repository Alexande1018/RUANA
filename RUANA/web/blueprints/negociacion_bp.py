"""Blueprint de negociación guiada (Campamento Base #2).

Rutas movidas desde web/app.py. Comportamiento y paths idénticos.
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from core import db_manager as db_manager_mod
from web.auth_decorators import _aliado_codigo, require_aliado

negociacion_bp = Blueprint("negociacion", __name__)


def get_db():
    """Resuelve get_db en tiempo de llamada (compatible con monkeypatch de tests)."""
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
    result = db.obtener_negociacion_contacto(contacto_id, codigo)
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
    result = db.proponer_negociacion(contacto_id, codigo, campo, valor)
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
    result = db.proponer_propuesta_completa_negociacion(
        contacto_id, codigo, campos, precio_catalogo=precio_catalogo,
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
    result = db.aceptar_negociacion(contacto_id, codigo, campo, obs_prof)
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
    result = db.contraoferta_negociacion(
        contacto_id, codigo, campo, valor, renegociar=renegociar
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
    result = db.cerrar_negociacion(contacto_id, codigo, motivo=motivo)
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
    result = db.dismiss_resumen_acuerdo(contacto_id, codigo)
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
    acuerdos = db.listar_acuerdos_aliado(
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
    resumenes = db.listar_resumenes_acuerdo_visibles(codigo)
    return jsonify({"status": "success", "resumenes": resumenes})
