"""Misión Maestra: contratos invitacion/evaluacion/aliado/soporte blueprints (registro y 401)."""

from web.blueprints.aliado_bp import aliado_bp
from web.blueprints.evaluacion_bp import evaluacion_bp
from web.blueprints.invitacion_bp import invitacion_bp
from web.blueprints.soporte_bp import soporte_bp


def test_invitacion_bp_health(client):
    resp = client.get("/api/invitacion/bp-health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert data["dominio"] == "invitacion"


def test_evaluacion_bp_health(client):
    resp = client.get("/api/evaluaciones/bp-health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert data["dominio"] == "evaluacion"


def test_aliado_bp_health(client):
    resp = client.get("/api/aliado/bp-health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert data["dominio"] == "aliado"


def test_soporte_bp_health(client):
    resp = client.get("/api/soporte/bp-health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert data["dominio"] == "soporte"


def test_invitacion_routes_exigen_sesion(client):
    for method, path in (
        ("post", "/api/generar-invitacion"),
        ("post", "/api/aliado/generar-invitacion"),
        ("post", "/api/invitaciones/crear"),
        ("post", "/api/admin/invitaciones/crear"),
        ("post", "/api/admin/invitacion-campanas"),
        ("post", "/api/admin/invitacion-campanas/X/desactivar"),
    ):
        resp = getattr(client, method)(path)
        assert resp.status_code == 401, path


def test_evaluacion_routes_exigen_sesion(client):
    for method, path in (
        ("get", "/api/evaluaciones/72001"),
        ("get", "/api/evaluaciones"),
        ("get", "/api/evaluaciones/72001/historico"),
        ("get", "/api/evaluaciones/estadisticas"),
    ):
        resp = getattr(client, method)(path)
        assert resp.status_code == 401, path


def test_aliado_routes_exigen_sesion(client):
    for method, path in (
        ("get", "/api/aliado/datos"),
        ("get", "/api/aliados/por-codigo/72001"),
        ("get", "/api/aliados"),
        ("get", "/api/aliados/directorio"),
        ("get", "/api/aliados/1"),
        ("get", "/api/aliados/obtener-por-codigo/72001"),
        ("get", "/api/aliados/verificar-codigo/72001"),
        ("get", "/api/aliados/listar"),
        ("post", "/api/aliado/pausar"),
        ("put", "/api/aliados/72001"),
        ("get", "/api/aliados/72001/notificaciones"),
        ("post", "/api/aliados/72001/notificaciones/marcar-todas-leidas"),
        ("post", "/api/aliados/72001/notificaciones/1/leida"),
        ("get", "/api/aliados/72001/catalogo-servicios"),
        ("put", "/api/aliados/72001/catalogo-servicios/1"),
    ):
        resp = getattr(client, method)(path)
        assert resp.status_code == 401, path


def test_soporte_routes_exigen_sesion(client):
    for method, path in (
        ("get", "/api/aliados/72001/centro-comunicacion"),
        ("post", "/api/aliados/72001/centro-comunicacion"),
        ("get", "/api/aliados/72001/centro-comunicacion/1/mensajes"),
        ("post", "/api/aliados/72001/centro-comunicacion/1/mensajes"),
        ("post", "/api/aliados/72001/centro-comunicacion/1/marcar-leida"),
        ("get", "/api/admin/centro-comunicacion"),
        ("get", "/api/admin/centro-comunicacion/1/mensajes"),
        ("post", "/api/admin/centro-comunicacion/1/responder"),
        ("post", "/api/admin/centro-comunicacion/1/estado"),
        ("delete", "/api/admin/centro-comunicacion/1"),
    ):
        resp = getattr(client, method)(path)
        assert resp.status_code == 401, path


def test_nuevos_bps_registrados(client):
    names = {bp.name for bp in client.application.blueprints.values()}
    assert invitacion_bp.name in names
    assert evaluacion_bp.name in names
    assert aliado_bp.name in names
    assert soporte_bp.name in names
