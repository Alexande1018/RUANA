"""Blueprint de pagos / métodos de cobro / conflictos de pago (extraído de web/app.py).

Rutas de mutación y lecturas de pagos que no viven ya en admin_bp (GETs).
Comportamiento y paths idénticos.
"""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, jsonify, request

from core import db_manager as db_manager_mod
from core.services import pago_service
from core.storage_manager import upload_ruana_file as _upload_ruana_file_default
from web.auth_decorators import (
    _admin_codigo,
    _aliado_codigo,
    require_admin_escritura,
    require_aliado,
)

pagos_bp = Blueprint("pagos", __name__)


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


def upload_ruana_file(**kwargs):
    """Resuelve upload vía módulo app cargado para respetar monkeypatch en tests."""
    import sys
    for key in ("RUANA.web.app", "web.app"):
        mod = sys.modules.get(key)
        if mod is not None:
            fn = getattr(mod, "upload_ruana_file", None)
            if callable(fn):
                return fn(**kwargs)
    return _upload_ruana_file_default(**kwargs)


@pagos_bp.route("/api/pagos/bp-health", methods=["GET"])
def pagos_bp_health():
    """Ping ligero del dominio pagos."""
    return jsonify({"status": "ok", "dominio": "pagos"})


@pagos_bp.route("/api/metodos-pago", methods=["GET"])
@require_aliado
def metodos_pago_ruana():
    """Devuelve los metodos de pago RUANA visibles para aliados autenticados."""
    try:
        db = get_db()
        return jsonify({"status": "success", "metodos": pago_service.obtener_metodos_pago_ruana(db)}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@pagos_bp.route("/api/admin/metodos-pago", methods=["POST"])
@require_admin_escritura
def admin_actualizar_metodos_pago():
    """Admin actualiza Bizum e IBAN de cobro RUANA."""
    try:
        data = request.get_json() or {}
        valores = {}
        for clave in ("bizum_num", "iban"):
            if clave in data:
                valores[clave] = (data.get(clave) or "").strip()
        if "iban" in valores and valores["iban"]:
            iban_limpio = valores["iban"].replace(" ", "").upper()
            if not iban_limpio.startswith("ES") or len(iban_limpio) != 24:
                return jsonify({"status": "error", "message": "IBAN espanol no valido"}), 400
            valores["iban"] = iban_limpio
        db = get_db()
        result = pago_service.actualizar_metodos_pago_ruana(db, valores, admin_codigo=_admin_codigo() or None)
        status_code = 200 if result.get("status") == "success" else 400
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@pagos_bp.route("/api/admin/metodos-pago/qr-revolut", methods=["POST"])
@require_admin_escritura
def admin_subir_qr_revolut():
    """Admin sube el QR Revolut a Supabase Storage y actualiza la configuracion."""
    try:
        if "archivo" not in request.files and "file" not in request.files:
            return jsonify({"status": "error", "message": "Falta el archivo (archivo o file)"}), 400
        file = request.files.get("archivo") or request.files.get("file")
        if not file or not file.filename:
            return jsonify({"status": "error", "message": "Archivo vacio"}), 400
        ext = (Path(file.filename).suffix or ".bin").lower()
        if ext not in (".jpg", ".jpeg", ".png", ".webp"):
            return jsonify({"status": "error", "message": "Formato no permitido. Usa jpg, png o webp."}), 400
        storage_result = upload_ruana_file(
            file_obj=file.stream,
            original_filename=file.filename,
            bucket="ruana-public",
            folder="metodos_pago",
            prefix="revolut",
            content_type=file.mimetype,
        )
        db = get_db()
        result = pago_service.actualizar_metodos_pago_ruana(
            db,
            {"qr_revolut_path": storage_result["url"]},
            admin_codigo=_admin_codigo() or None,
        )
        status_code = 200 if result.get("status") == "success" else 400
        return jsonify(result), status_code
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@pagos_bp.route("/api/admin/payment-conflicts/<int:conflict_id>/resolver", methods=["POST"])
@require_admin_escritura
def admin_resolver_payment_conflict(conflict_id):
    """
    POST /api/admin/payment-conflicts/<id>/resolver
    Body: { "decision": "contratante" | "profesional" | "rechazado", "comentario": "texto obligatorio" }
    Marca estado RESUELTO/RECHAZADO, guarda comentario_admin; si resuelve a favor, cierra trabajo e importe.
    """
    try:
        data = request.get_json() or {}
        decision = data.get("decision")
        comentario = data.get("comentario")
        if not decision:
            return jsonify({"status": "error", "message": "Falta decision"}), 400
        if not (comentario or "").strip():
            return jsonify({"status": "error", "message": "El comentario es obligatorio"}), 400
        admin_codigo = _admin_codigo() or ""
        db = get_db()
        result = pago_service.resolver_payment_conflict_admin(db, conflict_id, decision, comentario, admin_codigo)
        status_code = 200 if result.get("status") == "success" else 400
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@pagos_bp.route("/api/conflictos/por-trabajo/<int:trabajo_id>", methods=["GET"])
@require_aliado
def get_conflicto_por_trabajo(trabajo_id):
    """
    GET /api/conflictos/por-trabajo/<trabajo_id>
    Devuelve el conflicto de pago para ese trabajo si el aliado en sesión es contratante o profesional.
    """
    try:
        codigo = _aliado_codigo()
        if not codigo:
            return jsonify({"status": "error", "message": "Sesi?n expirada"}), 401
        db = get_db()
        c = pago_service.obtener_payment_conflict_por_trabajo(db, trabajo_id, codigo)
        if not c:
            return jsonify({"status": "error", "message": "No hay conflicto o no autorizado"}), 404
        return jsonify({"status": "success", "conflicto": c})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@pagos_bp.route("/api/conflictos/<int:conflict_id>/subir-prueba", methods=["POST"])
@require_aliado
def subir_prueba_conflicto(conflict_id):
    """
    POST /api/conflictos/<id>/subir-prueba
    Solo el contratante (aliado en sesión). Form: archivo (file).
    """
    try:
        codigo = _aliado_codigo()
        if not codigo:
            return jsonify({"status": "error", "message": "Sesi?n expirada"}), 401
        if "archivo" not in request.files and "file" not in request.files:
            return jsonify({"status": "error", "message": "Falta el archivo (archivo o file)"}), 400
        file = request.files.get("archivo") or request.files.get("file")
        if not file or not file.filename:
            return jsonify({"status": "error", "message": "Archivo vac?o"}), 400
        ext = (Path(file.filename).suffix or ".bin").lower()
        if ext not in (".pdf", ".jpg", ".jpeg", ".png", ".gif", ".webp"):
            return jsonify(
                {
                    "status": "error",
                    "message": "Formato no permitido. Usa imagen (jpg, png, gif, webp) o PDF.",
                }
            ), 400
        storage_result = upload_ruana_file(
            file_obj=file.stream,
            original_filename=file.filename,
            bucket="ruana-comprobantes",
            folder="conflictos",
            prefix=str(conflict_id),
            content_type=file.mimetype,
        )
        prueba_url = storage_result["url"]
        db = get_db()
        result = pago_service.subir_prueba_conflicto(db, conflict_id, codigo, prueba_url)
        if result.get("status") != "success":
            return jsonify(result), 400
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@pagos_bp.route("/api/admin/conflictos-pago/<int:contacto_id>/resolver", methods=["POST"])
@require_admin_escritura
def admin_resolver_conflicto_pago(contacto_id):
    """
    PATCH /api/admin/payment/<id>/resolve  o  POST /api/admin/conflictos-pago/<id>/resolver
    Body: { "importe_valido": float }
        Admin define importe valido, se calcula apoyo_pct, se cierra contacto (Apoyo pendiente).
        El score +2 se aplica al confirmar el pago Apoyo como pagado (Regla 2).
    """
    try:
        data = request.get_json() or {}
        importe_valido = data.get("importe_valido")
        if importe_valido is None:
            return jsonify({"status": "error", "message": "Falta importe_valido"}), 400
        admin_codigo = _admin_codigo() or ""
        db = get_db()
        result = pago_service.resolver_conflicto_pago(db, contacto_id, float(importe_valido), admin_codigo)
        status_code = 200 if result.get("status") == "success" else 400
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@pagos_bp.route("/api/admin/contactos/<int:contacto_id>/estado-pago", methods=["POST"])
@require_admin_escritura
def admin_estado_pago_contacto(contacto_id):
    """
    POST /api/admin/contactos/<id>/estado-pago
    Body: { "estado_pago": "en_revision" | "pagado" | "rechazado", "motivo": "..." }
    Motivo obligatorio si estado_pago es rechazado (vuelve a pendiente_pago y notifica al profesional).
    """
    try:
        data = request.get_json() or {}
        estado_pago = data.get("estado_pago")
        if not estado_pago:
            return jsonify({"status": "error", "message": "Falta estado_pago"}), 400
        if (estado_pago or "").strip().lower() == "rechazado":
            motivo = (data.get("motivo") or "").strip()
            if not motivo:
                return jsonify({"status": "error", "message": "El motivo de rechazo es obligatorio"}), 400
        else:
            motivo = None
        admin_codigo = _admin_codigo() or ""
        db = get_db()
        result = pago_service.actualizar_estado_pago_contacto(
            db, contacto_id, estado_pago, admin_codigo, motivo_rechazo=motivo
        )
        status_code = 200 if result.get("status") == "success" else 400
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@pagos_bp.route("/api/contactos/<int:contacto_id>/stripe/checkout", methods=["POST"])
@require_aliado
def crear_checkout_stripe_contacto(contacto_id):
    """El contratante inicia el pago Stripe (importe desde BD)."""
    try:
        codigo = _aliado_codigo()
        if not codigo:
            return jsonify({"status": "error", "message": "Sesión expirada"}), 401
        db = get_db()
        result = pago_service.crear_checkout_stripe(db, contacto_id, codigo)
        status_code = 200 if result.get("status") == "success" else 400
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@pagos_bp.route("/api/contactos/<int:contacto_id>/stripe/confirmar-trabajo", methods=["POST"])
@require_aliado
def confirmar_trabajo_stripe(contacto_id):
    """Solo el contratante confirma trabajo realizado → Transfer al profesional."""
    try:
        codigo = _aliado_codigo()
        if not codigo:
            return jsonify({"status": "error", "message": "Sesión expirada"}), 401
        db = get_db()
        result = pago_service.confirmar_trabajo_y_transferir(db, contacto_id, codigo)
        status_code = 200 if result.get("status") == "success" else 400
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@pagos_bp.route("/api/contactos/<int:contacto_id>/stripe/estado", methods=["GET"])
@require_aliado
def estado_pago_stripe(contacto_id):
    """Estado de pago Stripe para participantes del contacto."""
    try:
        codigo = _aliado_codigo()
        if not codigo:
            return jsonify({"status": "error", "message": "Sesión expirada"}), 401
        db = get_db()
        result = pago_service.estado_pago_stripe_contacto(db, contacto_id, codigo)
        status_code = 200 if result.get("status") == "success" else 400
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@pagos_bp.route("/api/aliado/stripe/estado", methods=["GET"])
@require_aliado
def aliado_stripe_estado():
    """Sincroniza y devuelve el estado de la cuenta Connect del aliado en sesión."""
    try:
        codigo = _aliado_codigo()
        if not codigo:
            return jsonify({"status": "error", "message": "Sesión expirada"}), 401
        db = get_db()
        sync = pago_service.sincronizar_estado_stripe_profesional(db, codigo)
        listo = pago_service.profesional_stripe_listo(db, codigo)
        payload = {
            "status": "success",
            "stripe_pago_listo": listo,
            "sync": sync,
        }
        return jsonify(payload), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@pagos_bp.route("/api/aliado/stripe/onboarding", methods=["POST"])
@require_aliado
def aliado_stripe_onboarding():
    """Profesional inicia onboarding Stripe Connect Express."""
    try:
        codigo = _aliado_codigo()
        if not codigo:
            return jsonify({"status": "error", "message": "Sesión expirada"}), 401
        db = get_db()
        result = pago_service.iniciar_onboarding_stripe_profesional(db, codigo)
        status_code = 200 if result.get("status") == "success" else 400
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
