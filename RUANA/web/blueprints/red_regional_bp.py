"""Blueprint de redes regionales reversibles (hoy: Red Huesca).

Las rutas se registran a partir de ``REDES``: una provincia nueva no necesita
otro blueprint, solo una entrada de configuración. Sin el flag maestro las
rutas responden pero no activan nada y el aviso nunca se muestra.

Red Centro conserva sus propias rutas en ``red_centro_bp``.
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from core import db_manager as db_manager_mod
from core.services import red_regional_service as rr
from web.auth_decorators import (
    _admin_codigo,
    _aliado_codigo,
    require_admin,
    require_admin_escritura,
    require_aliado,
)

red_regional_bp = Blueprint("red_regional", __name__)


def get_db():
    import sys
    for key in ("RUANA.web.app", "web.app"):
        mod = sys.modules.get(key)
        if mod is not None:
            fn = getattr(mod, "get_db", None)
            if callable(fn):
                return fn()
    return db_manager_mod.get_db()


def _respuesta(result, ok_status=200):
    result = dict(result or {})
    if result.get("status") != "success":
        code = int(result.pop("http", 400) or 400)
        return jsonify({"status": "error", "error": result.get("message"), "message": result.get("message")}), code
    result.pop("http", None)
    return jsonify(result), ok_status


def _red_o_404(slug: str):
    cfg = rr.red_por_slug((slug or "").replace("-", "_"))
    if cfg is None:
        return None
    return cfg


# --- Admin: listado de redes configuradas --------------------------------------

@red_regional_bp.route("/api/admin/redes-regionales", methods=["GET"])
@require_admin
def admin_redes_regionales():
    try:
        return _respuesta(rr.estado_todas(get_db()))
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


def _registrar_rutas(cfg: rr.RedRegional) -> None:
    slug_url = cfg.slug.replace("_", "-")

    def admin_estado():
        try:
            return _respuesta(rr.estado(get_db(), cfg))
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    def admin_activar():
        try:
            return _respuesta(rr.activar(get_db(), _admin_codigo() or "", cfg))
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    def admin_revertir():
        try:
            return _respuesta(rr.revertir(get_db(), _admin_codigo() or "", cfg))
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    def admin_plantilla():
        return jsonify({"status": "success", "plantilla": rr.plantilla_notificacion(cfg),
                        "envio_masivo": False})

    def aliado_aviso():
        try:
            return _respuesta(rr.aviso_para_aliado(get_db(), _aliado_codigo(), cfg))
        except Exception:
            return jsonify({"status": "success", "mostrar": False})

    def aliado_aviso_accion():
        data = request.get_json(silent=True) or {}
        try:
            return _respuesta(
                rr.registrar_accion_aviso(get_db(), _aliado_codigo(), data.get("accion") or "", cfg)
            )
        except Exception:
            return jsonify({"status": "error", "message": "No se pudo guardar."}), 500

    admin_estado.__name__ = f"admin_{cfg.slug}_estado"
    admin_activar.__name__ = f"admin_{cfg.slug}_activar"
    admin_revertir.__name__ = f"admin_{cfg.slug}_revertir"
    admin_plantilla.__name__ = f"admin_{cfg.slug}_plantilla"
    aliado_aviso.__name__ = f"aliado_{cfg.slug}_aviso"
    aliado_aviso_accion.__name__ = f"aliado_{cfg.slug}_aviso_accion"

    red_regional_bp.add_url_rule(
        f"/api/admin/{slug_url}", view_func=require_admin(admin_estado), methods=["GET"],
        endpoint=admin_estado.__name__,
    )
    red_regional_bp.add_url_rule(
        f"/api/admin/{slug_url}/activar", view_func=require_admin_escritura(admin_activar),
        methods=["POST"], endpoint=admin_activar.__name__,
    )
    red_regional_bp.add_url_rule(
        f"/api/admin/{slug_url}/revertir", view_func=require_admin_escritura(admin_revertir),
        methods=["POST"], endpoint=admin_revertir.__name__,
    )
    red_regional_bp.add_url_rule(
        f"/api/admin/{slug_url}/plantilla-notificacion", view_func=require_admin(admin_plantilla),
        methods=["GET"], endpoint=admin_plantilla.__name__,
    )
    red_regional_bp.add_url_rule(
        f"/api/aliado/{slug_url}/aviso", view_func=require_aliado(aliado_aviso),
        methods=["GET"], endpoint=aliado_aviso.__name__,
    )
    red_regional_bp.add_url_rule(
        f"/api/aliado/{slug_url}/aviso", view_func=require_aliado(aliado_aviso_accion),
        methods=["POST"], endpoint=aliado_aviso_accion.__name__,
    )


for _cfg in rr.REDES.values():
    _registrar_rutas(_cfg)


# --- Aliado: aviso genérico (el JS no tiene que conocer el slug) ---------------

@red_regional_bp.route("/api/aliado/red-regional/aviso", methods=["GET"])
@require_aliado
def aliado_red_regional_aviso():
    try:
        return _respuesta(rr.aviso_para_aliado_cualquier_red(get_db(), _aliado_codigo()))
    except Exception:
        return jsonify({"status": "success", "mostrar": False})


@red_regional_bp.route("/api/aliado/red-regional/aviso", methods=["POST"])
@require_aliado
def aliado_red_regional_aviso_accion():
    data = request.get_json(silent=True) or {}
    slug = (data.get("slug") or "").strip() or rr.RED_HUESCA.slug
    cfg = _red_o_404(slug)
    if cfg is None:
        return jsonify({"status": "error", "message": "Red desconocida."}), 404
    try:
        return _respuesta(
            rr.registrar_accion_aviso(get_db(), _aliado_codigo(), data.get("accion") or "", cfg)
        )
    except Exception:
        return jsonify({"status": "error", "message": "No se pudo guardar."}), 500
