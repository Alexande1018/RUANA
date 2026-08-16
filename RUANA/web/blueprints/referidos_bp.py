"""Blueprint de referidos / linaje (Campamento Base #2).

Rutas GET movidas desde web/app.py. Comportamiento y paths idénticos.
"""

from __future__ import annotations

from datetime import datetime

from flask import Blueprint, jsonify, request

from core import db_manager as db_manager_mod
from core.services import referido_service
from web.auth_decorators import _aliado_codigo, require_admin, require_aliado

referidos_bp = Blueprint("referidos", __name__)


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
        arbol = referido_service.obtener_arbol_referidos(db, codigo, max_depth=profundidad_int)
        if not arbol:
            return jsonify({"status": "error", "message": "Aliado no encontrado"}), 404
        invitador = referido_service.obtener_invitador_de(db, codigo)
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
            arbol = referido_service.obtener_arbol_referidos(
                db, codigo, max_depth=profundidad_int, incluir_pendientes=True
            )
            if not arbol:
                return jsonify({"status": "error", "message": f"Aliado {codigo} no encontrado"}), 404
            invitador = referido_service.obtener_invitador_de(db, codigo)
            return jsonify({
                "status": "success",
                "modo": "subarbol",
                "arbol": arbol,
                "invitador": invitador,
                "total_nodos": _contar_nodos_arbol(arbol),
                "timestamp": datetime.now().isoformat(),
            })
        bosques = referido_service.obtener_bosques_referidos(
            db, max_depth=profundidad_int, incluir_pendientes=True
        )
        total_nodos = sum(_contar_nodos_arbol(b) for b in bosques)
        resumen = referido_service.obtener_resumen_referidos_red(db)
        return jsonify({
            "status": "success",
            "modo": "bosque",
            "bosques": bosques,
            "total_nodos": total_nodos,
            "total_raices": len(bosques),
            "total_aliados_en_red": resumen.get("total_aliados_en_red", 0),
            "aliados_fuera_red": resumen.get("aliados_fuera_red", 0),
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
        raices = referido_service.listar_nodos_raiz_referidos(db, incluir_pendientes=True)
        resumen = referido_service.obtener_resumen_referidos_red(db)
        return jsonify({
            "status": "success",
            "modo": "raices",
            "raices": raices,
            "total_nodos": resumen.get("total_nodos", 0),
            "total_raices": len(raices),
            "total_aliados_activos": resumen.get("total_aliados_activos", 0),
            "total_aliados_en_red": resumen.get("total_aliados_en_red", 0),
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
        nodo = referido_service.obtener_nodo_referidos(db, codigo)
        if not nodo:
            return jsonify({"status": "error", "message": "Aliado no encontrado"}), 404
        hijos = referido_service.listar_referidos_directos(db, codigo)
        invitador = referido_service.obtener_invitador_de(db, codigo)
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
        ruta = referido_service.obtener_ruta_referidos_hacia_arriba(db, codigo)
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
        resultados = referido_service.buscar_en_red_referidos(
            db, query, limite=50, incluir_pendientes=True
        )
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
        if not referido_service.aliado_puede_ver_nodo_referidos(db, codigo_sesion, codigo):
            return jsonify({"status": "error", "message": "No autorizado"}), 403
        nodo = referido_service.obtener_nodo_referidos(db, codigo)
        if not nodo:
            return jsonify({"status": "error", "message": "Aliado no encontrado"}), 404
        hijos = referido_service.listar_referidos_directos(db, codigo)
        invitador = referido_service.obtener_invitador_de(db, codigo)
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
        nodo = referido_service.obtener_nodo_referidos(db, codigo)
        if not nodo:
            return jsonify({"status": "error", "message": "Aliado no encontrado"}), 404
        invitador = referido_service.obtener_invitador_de(db, codigo)
        total_desc = referido_service.contar_referidos_por_codigo(db, codigo)
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
        cambios = referido_service.listar_referidos_desde(db, desde)
        raices = referido_service.listar_nodos_raiz_referidos(db)
        resumen = referido_service.obtener_resumen_referidos_red(db)
        return jsonify({
            "status": "success",
            "cambios": cambios,
            "raices": raices,
            "total_nodos": resumen.get("total_nodos", 0),
            "total_raices": len(raices),
            "total_aliados_activos": resumen.get("total_aliados_activos", 0),
            "total_aliados_en_red": resumen.get("total_aliados_en_red", 0),
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
        todos = referido_service.listar_referidos_desde(db, desde)
        cambios = [
            c for c in todos
            if referido_service.aliado_puede_ver_nodo_referidos(db, codigo_sesion, c.get("codigo_referido") or "")
        ]
        nodo_raiz = referido_service.obtener_nodo_referidos(db, codigo_sesion)
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
        linaje = referido_service.obtener_linaje_aliado(db, codigo)
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
        hijos = referido_service.listar_hijos_directos_linaje(db, codigo)
        return jsonify({
            "status": "success",
            "codigo": codigo,
            "hijos": hijos,
            "total": len(hijos),
            "timestamp": datetime.now().isoformat(),
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
