"""Blueprint de referidos / linaje (Campamento Base #2).

Rutas GET movidas desde web/app.py. Comportamiento y paths idénticos.
"""

from __future__ import annotations

from datetime import datetime

from flask import Blueprint, jsonify, request

from core import db_manager as db_manager_mod
from web.auth_decorators import _aliado_codigo, require_admin, require_aliado

referidos_bp = Blueprint("referidos", __name__)


def get_db():
    """Resuelve get_db en tiempo de llamada (compatible con monkeypatch de tests)."""
    return db_manager_mod.get_db()


def _contar_nodos_arbol(nodo: dict) -> int:
    """Cuenta nodos en un árbol de referidos (incluye la raíz)."""
    if not nodo or not isinstance(nodo, dict):
        return 0
    count = 1
    for hijo in nodo.get("referidos") or []:
        count += _contar_nodos_arbol(hijo)
    return count


@referidos_bp.route("/api/aliado/referidos", methods=["GET"])
@require_aliado
def aliado_referidos_arbol():
    """GET árbol de referidos del aliado autenticado."""
    try:
        codigo = _aliado_codigo()
        if not codigo:
            return jsonify({"status": "error", "message": "Sesión no válida"}), 401
        profundidad = request.args.get("profundidad", 8)
        try:
            profundidad_int = int(profundidad)
        except (TypeError, ValueError):
            profundidad_int = 8
        db = get_db()
        arbol = db.obtener_arbol_referidos(codigo, max_depth=profundidad_int)
        if not arbol:
            return jsonify({"status": "error", "message": "Aliado no encontrado"}), 404
        invitador = db.obtener_invitador_de(codigo)
        total_descendientes = _contar_nodos_arbol(arbol) - 1
        return jsonify({
            "status": "success",
            "arbol": arbol,
            "invitador": invitador,
            "total_descendientes": max(0, total_descendientes),
            "timestamp": datetime.now().isoformat(),
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@referidos_bp.route("/api/admin/referidos/arbol", methods=["GET"])
@require_admin
def admin_referidos_arbol():
    """GET árbol de referidos para admin (bosque o subárbol)."""
    try:
        codigo = (request.args.get("codigo") or "").strip()
        profundidad = request.args.get("profundidad", 8)
        try:
            profundidad_int = int(profundidad)
        except (TypeError, ValueError):
            profundidad_int = 8
        db = get_db()
        if codigo:
            arbol = db.obtener_arbol_referidos(codigo, max_depth=profundidad_int)
            if not arbol:
                return jsonify({"status": "error", "message": f"Aliado {codigo} no encontrado"}), 404
            invitador = db.obtener_invitador_de(codigo)
            return jsonify({
                "status": "success",
                "modo": "subarbol",
                "arbol": arbol,
                "invitador": invitador,
                "total_nodos": _contar_nodos_arbol(arbol),
                "timestamp": datetime.now().isoformat(),
            })
        bosques = db.obtener_bosques_referidos(max_depth=profundidad_int)
        total_nodos = sum(_contar_nodos_arbol(b) for b in bosques)
        return jsonify({
            "status": "success",
            "modo": "bosque",
            "bosques": bosques,
            "total_nodos": total_nodos,
            "total_raices": len(bosques),
            "timestamp": datetime.now().isoformat(),
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@referidos_bp.route("/api/admin/referidos/raices", methods=["GET"])
@require_admin
def admin_referidos_raices():
    """GET nodos raíz de la red."""
    try:
        db = get_db()
        raices = db.listar_nodos_raiz_referidos()
        resumen = db.obtener_resumen_referidos_red()
        return jsonify({
            "status": "success",
            "modo": "raices",
            "raices": raices,
            "total_nodos": resumen.get("total_nodos", 0),
            "total_raices": len(raices),
            "total_aliados_activos": resumen.get("total_aliados_activos", 0),
            "aliados_fuera_red": resumen.get("aliados_fuera_red", 0),
            "timestamp": datetime.now().isoformat(),
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@referidos_bp.route("/api/admin/referidos/hijos/<codigo>", methods=["GET"])
@require_admin
def admin_referidos_hijos(codigo):
    """GET referidos directos de un aliado."""
    try:
        codigo = (codigo or "").strip()
        if not codigo:
            return jsonify({"status": "error", "message": "Código requerido"}), 400
        db = get_db()
        nodo = db.obtener_nodo_referidos(codigo)
        if not nodo:
            return jsonify({"status": "error", "message": "Aliado no encontrado"}), 404
        hijos = db.listar_referidos_directos(codigo)
        invitador = db.obtener_invitador_de(codigo)
        return jsonify({
            "status": "success",
            "nodo": nodo,
            "hijos": hijos,
            "invitador": invitador,
            "timestamp": datetime.now().isoformat(),
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@referidos_bp.route("/api/admin/referidos/ruta/<codigo>", methods=["GET"])
@require_admin
def admin_referidos_ruta(codigo):
    """GET cadena desde raíz hasta el aliado."""
    try:
        codigo = (codigo or "").strip()
        if not codigo:
            return jsonify({"status": "error", "message": "Código requerido"}), 400
        db = get_db()
        ruta = db.obtener_ruta_referidos_hacia_arriba(codigo)
        if not ruta:
            return jsonify({"status": "error", "message": "Aliado no encontrado en la red"}), 404
        return jsonify({
            "status": "success",
            "ruta": ruta,
            "timestamp": datetime.now().isoformat(),
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@referidos_bp.route("/api/admin/referidos/buscar", methods=["GET"])
@require_admin
def admin_referidos_buscar():
    """GET busca aliados en la red."""
    try:
        query = (request.args.get("q") or "").strip()
        if not query:
            return jsonify({"status": "success", "resultados": []})
        db = get_db()
        resultados = db.buscar_en_red_referidos(query, limite=25)
        return jsonify({
            "status": "success",
            "resultados": resultados,
            "timestamp": datetime.now().isoformat(),
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@referidos_bp.route("/api/aliado/referidos/hijos/<codigo>", methods=["GET"])
@require_aliado
def aliado_referidos_hijos(codigo):
    """GET referidos directos visibles para el aliado."""
    try:
        codigo_sesion = _aliado_codigo()
        codigo = (codigo or "").strip()
        if not codigo_sesion:
            return jsonify({"status": "error", "message": "Sesión no válida"}), 401
        if not codigo:
            return jsonify({"status": "error", "message": "Código requerido"}), 400
        db = get_db()
        if not db.aliado_puede_ver_nodo_referidos(codigo_sesion, codigo):
            return jsonify({"status": "error", "message": "No autorizado"}), 403
        nodo = db.obtener_nodo_referidos(codigo)
        if not nodo:
            return jsonify({"status": "error", "message": "Aliado no encontrado"}), 404
        hijos = db.listar_referidos_directos(codigo)
        invitador = db.obtener_invitador_de(codigo)
        return jsonify({
            "status": "success",
            "nodo": nodo,
            "hijos": hijos,
            "invitador": invitador,
            "timestamp": datetime.now().isoformat(),
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@referidos_bp.route("/api/aliado/referidos/raiz", methods=["GET"])
@require_aliado
def aliado_referidos_raiz():
    """GET nodo raíz del aliado autenticado."""
    try:
        codigo = _aliado_codigo()
        if not codigo:
            return jsonify({"status": "error", "message": "Sesión no válida"}), 401
        db = get_db()
        nodo = db.obtener_nodo_referidos(codigo)
        if not nodo:
            return jsonify({"status": "error", "message": "Aliado no encontrado"}), 404
        invitador = db.obtener_invitador_de(codigo)
        total_desc = db.contar_referidos_por_codigo(codigo)
        return jsonify({
            "status": "success",
            "modo": "raiz",
            "nodo": nodo,
            "invitador": invitador,
            "total_descendientes_directos": total_desc,
            "timestamp": datetime.now().isoformat(),
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@referidos_bp.route("/api/admin/referidos/cambios", methods=["GET"])
@require_admin
def admin_referidos_cambios():
    """GET nuevos referidos desde un momento."""
    try:
        desde = (request.args.get("desde") or "").strip()
        db = get_db()
        cambios = db.listar_referidos_desde(desde)
        raices = db.listar_nodos_raiz_referidos()
        resumen = db.obtener_resumen_referidos_red()
        return jsonify({
            "status": "success",
            "cambios": cambios,
            "raices": raices,
            "total_nodos": resumen.get("total_nodos", 0),
            "total_raices": len(raices),
            "total_aliados_activos": resumen.get("total_aliados_activos", 0),
            "aliados_fuera_red": resumen.get("aliados_fuera_red", 0),
            "timestamp": datetime.now().isoformat(),
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@referidos_bp.route("/api/aliado/referidos/cambios", methods=["GET"])
@require_aliado
def aliado_referidos_cambios():
    """GET nuevos referidos visibles para el aliado."""
    try:
        codigo_sesion = _aliado_codigo()
        if not codigo_sesion:
            return jsonify({"status": "error", "message": "Sesión no válida"}), 401
        desde = (request.args.get("desde") or "").strip()
        db = get_db()
        todos = db.listar_referidos_desde(desde)
        cambios = [
            c for c in todos
            if db.aliado_puede_ver_nodo_referidos(codigo_sesion, c.get("codigo_referido") or "")
        ]
        nodo_raiz = db.obtener_nodo_referidos(codigo_sesion)
        return jsonify({
            "status": "success",
            "cambios": cambios,
            "nodo_raiz": nodo_raiz,
            "timestamp": datetime.now().isoformat(),
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@referidos_bp.route("/api/admin/aliados/<codigo>/linaje", methods=["GET"])
@require_admin
def admin_aliado_linaje(codigo):
    """GET linaje para Control de Aliados."""
    try:
        codigo = (codigo or "").strip()
        if not codigo:
            return jsonify({"status": "error", "message": "Código requerido"}), 400
        db = get_db()
        linaje = db.obtener_linaje_aliado(codigo)
        if not linaje:
            return jsonify({"status": "error", "message": "Aliado no encontrado"}), 404
        return jsonify({
            "status": "success",
            "linaje": linaje,
            "timestamp": datetime.now().isoformat(),
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@referidos_bp.route("/api/aliado/linaje/hijos", methods=["GET"])
@require_aliado
def aliado_linaje_hijos():
    """GET hijos directos del aliado autenticado."""
    try:
        codigo = _aliado_codigo()
        if not codigo:
            return jsonify({"status": "error", "message": "Sesión no válida"}), 401
        db = get_db()
        hijos = db.listar_hijos_directos_linaje(codigo)
        return jsonify({
            "status": "success",
            "codigo": codigo,
            "hijos": hijos,
            "total": len(hijos),
            "timestamp": datetime.now().isoformat(),
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
