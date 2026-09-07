"""Misión Maestra: contratos pagos_bp + solicitudes_bp (registro y 401)."""

from web.blueprints.pagos_bp import pagos_bp
from web.blueprints.solicitudes_bp import solicitudes_bp


def test_pagos_bp_health(client):
    resp = client.get("/api/pagos/bp-health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert data["dominio"] == "pagos"


def test_solicitudes_bp_health(client):
    resp = client.get("/api/solicitudes/bp-health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert data["dominio"] == "solicitudes"


def test_pagos_routes_exigen_sesion(client):
    for method, path in (
        ("get", "/api/metodos-pago"),
        ("post", "/api/admin/metodos-pago"),
        ("post", "/api/admin/metodos-pago/qr-revolut"),
        ("get", "/api/admin/metodos-pago/aliados"),
        ("post", "/api/admin/metodos-pago/aliados/A0001/habilitar"),
        ("post", "/api/admin/metodos-pago/aliados/A0001/deshabilitar"),
        ("post", "/api/admin/payment-conflicts/1/resolver"),
        ("get", "/api/conflictos/por-trabajo/1"),
        ("post", "/api/conflictos/1/subir-prueba"),
        ("post", "/api/admin/conflictos-pago/1/resolver"),
        ("post", "/api/admin/contactos/1/estado-pago"),
    ):
        resp = getattr(client, method)(path)
        assert resp.status_code == 401, path


def test_solicitudes_routes_exigen_sesion(client):
    for method, path in (
        ("get", "/api/solicitudes"),
        ("post", "/api/solicitudes"),
        ("post", "/api/solicitudes/1/atender"),
        ("post", "/api/admin/solicitudes/1/atender"),
    ):
        resp = getattr(client, method)(path)
        assert resp.status_code == 401, path


def test_pagos_y_solicitudes_bp_registrados(client):
    names = {bp.name for bp in client.application.blueprints.values()}
    assert pagos_bp.name in names
    assert solicitudes_bp.name in names
