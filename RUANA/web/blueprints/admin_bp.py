"""Blueprint admin — bloque dashboard / lecturas (Campamento Base #3).

Rutas GET movidas desde web/app.py. Comportamiento y paths idénticos.
Auth, login/logout y mutaciones destructivas permanecen en app.py por ahora.
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

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
