"""Rate limiting en POST /api/aliado/login."""

from types import SimpleNamespace

from core import db_manager as db_module
from RUANA.web import app as app_module
from web.limiter import limiter


def test_aliado_login_rate_limit_por_ip(client, tmp_path, monkeypatch):
    """La petición 11 con credenciales inválidas desde la misma IP debe devolver 429."""
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    db = db_module.DBManager(str(tmp_path / "rate_limit.db"))
    monkeypatch.setattr(app_module, "get_db", lambda: db)
    monkeypatch.setattr(db_module, "get_db", lambda: db)

    limiter.enabled = True
    try:
        for i in range(10):
            resp = client.post(
                "/api/aliado/login",
                json={"codigo": f"9{i:04d}"},
            )
            assert resp.status_code == 401, f"intento {i + 1}: {resp.status_code}"

        resp = client.post("/api/aliado/login", json={"codigo": "99999"})
        assert resp.status_code == 429
        data = resp.get_json()
        assert data.get("status") == "error"
        assert "message" in data
    finally:
        limiter.enabled = False
