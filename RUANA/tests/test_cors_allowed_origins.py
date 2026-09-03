"""CORS: orígenes explícitos; un Origin no listado no recibe ACAO."""

from __future__ import annotations


def test_cors_permite_origen_de_produccion(client):
    resp = client.get(
        "/api/pagos/bp-health",
        headers={"Origin": "https://ruana-4293f.web.app"},
    )
    assert resp.status_code == 200
    assert resp.headers.get("Access-Control-Allow-Origin") == "https://ruana-4293f.web.app"


def test_cors_rechaza_origen_no_listado(client):
    resp = client.get(
        "/api/pagos/bp-health",
        headers={"Origin": "https://evil.example"},
    )
    assert resp.status_code == 200
    assert "Access-Control-Allow-Origin" not in resp.headers
