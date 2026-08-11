"""Blueprint de negociación guiada (extracción progresiva desde app.py)."""
from __future__ import annotations

from flask import Blueprint, jsonify

from core.db_manager import get_db

# Las rutas mutables siguen en app.py durante la transición.
# Este blueprint reserva el namespace y exporta helpers compartidos.

negociacion_bp = Blueprint("negociacion", __name__)


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
    """Ping ligero del dominio negociación (no sustituye rutas de contacto)."""
    return jsonify({"status": "ok", "dominio": "negociacion"})
