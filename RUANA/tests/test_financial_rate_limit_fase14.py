"""Rate limiting en endpoints financieros sensibles (FASE 14)."""

from types import SimpleNamespace

from core import db_manager as db_module
from RUANA.web import app as app_module
from web.limiter import limiter


def _setup_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    db = db_module.DBManager(str(tmp_path / "fin_rate.db"))
    monkeypatch.setattr(app_module, "get_db", lambda: db)
    monkeypatch.setattr(db_module, "get_db", lambda: db)
    return db


def test_stripe_checkout_rate_limit(client, tmp_path, monkeypatch):
    """La petición 16 de checkout desde la misma IP debe devolver 429."""
    db = _setup_db(tmp_path, monkeypatch)
    conn = db._connect()
    conn.execute(
        "INSERT INTO aliados (codigo, nombre, email) VALUES (?, ?, ?)",
        ("SOLRL", "Sol", "solrl@test.com"),
    )
    conn.execute(
        "INSERT INTO aliados (codigo, nombre, email, stripe_account_id, stripe_charges_enabled) "
        "VALUES (?, ?, ?, ?, ?)",
        ("PRORL", "Pro", "prorl@test.com", "acct_rl", 1),
    )
    conn.execute(
        """
        INSERT INTO contactos_ruana (
            solicitante_codigo, profesional_codigo, servicio, estado,
            importe_acordado, modo_pago, precio_congelado, estado_pago, pendiente_pago
        ) VALUES (?, ?, ?, 'pendiente_de_pago', 100, 'stripe', 1, 'esperando_cobro_cliente', 0)
        """,
        ("SOLRL", "PRORL", "RL"),
    )
    contacto_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()

    monkeypatch.setenv("RUANA_STRIPE_PAYMENTS_ENABLED", "1")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")

    limiter.enabled = True
    try:
        path = f"/api/contactos/{contacto_id}/stripe/checkout"
        for i in range(15):
            resp = client.post(path)
            assert resp.status_code in (200, 400, 401), f"intento {i + 1}: {resp.status_code}"

        resp = client.post(path)
        assert resp.status_code == 429
        data = resp.get_json()
        assert data.get("status") == "error"
    finally:
        limiter.enabled = False


def test_financial_mutation_limit_configured():
    from web.financial_rate_limit import FINANCIAL_MUTATION_LIMIT, STRIPE_WEBHOOK_LIMIT

    assert "per minute" in FINANCIAL_MUTATION_LIMIT
    assert "per hour" in FINANCIAL_MUTATION_LIMIT
    assert "per minute" in STRIPE_WEBHOOK_LIMIT
