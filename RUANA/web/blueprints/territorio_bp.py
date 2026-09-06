"""Blueprint territorial: resolución CP → ciudad."""

from flask import Blueprint, jsonify, request

from core.services import territorio_service

territorio_bp = Blueprint("territorio", __name__)


@territorio_bp.route("/api/territorio/resolver-cp", methods=["GET"])
def resolver_cp():
    cp = (request.args.get("cp") or request.args.get("codigo_postal") or "").strip()
    if not cp or not cp.isdigit():
        return jsonify({"status": "error", "message": "Código postal inválido"}), 400
    res = territorio_service.resolver_ciudad_por_cp(cp)
    if not res or not res.get("ciudad"):
        return jsonify({
            "status": "success",
            "resuelto": False,
            "codigo_postal": cp,
        })
    return jsonify({
        "status": "success",
        "resuelto": True,
        "codigo_postal": cp,
        "ciudad": res["ciudad"],
        "provincia": res.get("provincia") or "",
        "preview": f"Entrarás en la red de RUANA {res['ciudad']}",
    })
