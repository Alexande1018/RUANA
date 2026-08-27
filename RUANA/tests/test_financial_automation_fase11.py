"""Tests FASE 11: automatización y monitorización financiera."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from core import db_manager as db_module
from core.financial_automation_authorization import AUTOMATION_EXECUTE, MONITORING_VIEW, tiene_permiso_automation
from core.repositories.financial_automation_repo import FinancialAutomationRepo
from core.services import financial_automation_service as fas
from RUANA.web import app as app_module


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setenv("RUANA_STRIPE_PAYMENTS_ENABLED", "1")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setenv("RUANA_FIN_AUTOMATION_LEASE_TTL", "300")
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(
            postgres_configured=False,
            database_url="",
            public_app_url="http://localhost:5000",
            stripe_secret_key="sk_test_x",
            stripe_webhook_secret="whsec_test",
        ),
    )
    db = db_module.DBManager(str(tmp_path / "ruana_fase11.db"))
    monkeypatch.setattr(app_module, "get_db", lambda: db)
    monkeypatch.setattr(db_module, "get_db", lambda: db)
    return db


def _headers(session_headers, permisos=None):
    return session_headers("admin", "ADMIN_F11", permisos=permisos or ["configurar"])


def _cron_headers(monkeypatch):
    monkeypatch.setenv("RUANA_CRON_SECRET", "cron-secret-f11")
    return {"X-Ruana-Cron-Secret": "cron-secret-f11"}


def _seed_conflict_bloqueante(db):
    conn = db._connect()
    c = conn.cursor()
    c.execute("INSERT INTO aliados (codigo, nombre, email) VALUES (?, ?, ?)", ("SOL11", "S", "s@t.com"))
    c.execute(
        "INSERT INTO aliados (codigo, nombre, email, stripe_account_id, stripe_charges_enabled) "
        "VALUES (?, ?, ?, ?, ?)",
        ("PRO11", "P", "p@t.com", "acct_f11", 1),
    )
    c.execute("SELECT id FROM aliados WHERE codigo = 'SOL11'")
    sol_id = c.fetchone()[0]
    c.execute("SELECT id FROM aliados WHERE codigo = 'PRO11'")
    pro_id = c.fetchone()[0]
    c.execute(
        """
        INSERT INTO contactos_ruana (
            solicitante_codigo, profesional_codigo, servicio, estado, pendiente_resolucion,
            importe_acordado, modo_pago, estado_pago, estado_financiero, estado_transferencia,
            importe_neto_profesional, apoyo_ruana, comision,
            stripe_payment_intent_id, stripe_charge_id
        ) VALUES (?, ?, ?, 'trabajo_en_progreso', 0, 500, 'stripe', 'cobro_confirmado',
                  'CONFLICTO_ABIERTO', 'RETENIDO', 440, 60, 60, 'pi_f11', 'ch_f11')
        """,
        ("SOL11", "PRO11", "Srv"),
    )
    cid = c.lastrowid
    c.execute(
        """
        INSERT INTO payment_conflicts (
            trabajo_id, contratante_id, profesional_id,
            importe_contratante, importe_profesional,
            estado_conflicto, bloqueo_financiero, tipo
        ) VALUES (?, ?, ?, 500, 440, 'ABIERTO', 1, 'importe_discrepante')
        """,
        (cid, sol_id, pro_id),
    )
    conn.commit()
    conn.close()
    return cid


def test_01_permisos_automation_configurar():
    assert tiene_permiso_automation(["configurar"], AUTOMATION_EXECUTE)
    assert tiene_permiso_automation(["leer"], MONITORING_VIEW)
    assert not tiene_permiso_automation(["leer"], AUTOMATION_EXECUTE)


def test_02_lease_exclusivo(sqlite_db):
    repo = FinancialAutomationRepo()
    conn = sqlite_db._connect()
    c = conn.cursor()
    assert repo.adquirir_lease(c, job_name="test_job", holder="w1", ttl_seconds=300)
    assert not repo.adquirir_lease(c, job_name="test_job", holder="w2", ttl_seconds=300)
    repo.liberar_lease(c, job_name="test_job", holder="w1")
    assert repo.adquirir_lease(c, job_name="test_job", holder="w2", ttl_seconds=300)
    conn.commit()
    conn.close()


def test_03_alerta_idempotente(sqlite_db):
    repo = FinancialAutomationRepo()
    conn = sqlite_db._connect()
    c = conn.cursor()
    n1, _ = repo.upsert_alerta(
        c, alert_key="test:1", tipo="conflicto_bloqueante", severidad="critical",
        contacto_id=1, accion_recomendada="revisar", accion_disponible=None,
        fuente="test", run_id="run-1",
    )
    n2, _ = repo.upsert_alerta(
        c, alert_key="test:1", tipo="conflicto_bloqueante", severidad="critical",
        contacto_id=1, accion_recomendada="revisar", accion_disponible=None,
        fuente="test", run_id="run-2",
    )
    c.execute("SELECT COUNT(*) FROM financial_alerts WHERE alert_key = ?", ("test:1",))
    count = c.fetchone()[0]
    conn.commit()
    conn.close()
    assert n1 is True
    assert n2 is False
    assert count == 1


def test_04_ciclo_monitoreo_genera_run_y_alertas(sqlite_db):
    _seed_conflict_bloqueante(sqlite_db)
    with patch.object(fas, "ejecutar_reconciliacion_periodica", return_value={"status": "success", "metricas": {}}):
        result = fas.ejecutar_ciclo_monitoreo(
            sqlite_db, actor="test", permiso=AUTOMATION_EXECUTE, incluir_reconciliacion=False,
        )
    assert result["status"] == "success"
    assert result.get("run_id")
    conn = sqlite_db._connect()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM financial_automation_runs WHERE run_id = ?", (result["run_id"],))
    assert c.fetchone()[0] == 1
    c.execute("SELECT COUNT(*) FROM financial_alerts WHERE estado = 'OPEN'")
    assert c.fetchone()[0] >= 1
    c.execute("SELECT COUNT(*) FROM financial_audit_log WHERE accion LIKE 'automation_%'")
    assert c.fetchone()[0] >= 2
    conn.close()


def test_05_segundo_ciclo_actualiza_sin_duplicar(sqlite_db):
    _seed_conflict_bloqueante(sqlite_db)
    with patch.object(fas, "ejecutar_reconciliacion_periodica", return_value={"status": "success", "metricas": {}}):
        fas.ejecutar_ciclo_monitoreo(sqlite_db, actor="t1", incluir_reconciliacion=False)
        fas.ejecutar_ciclo_monitoreo(sqlite_db, actor="t2", incluir_reconciliacion=False)
    conn = sqlite_db._connect()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM financial_alerts WHERE tipo = 'conflicto_bloqueante'")
    assert c.fetchone()[0] == 1
    conn.close()


def test_06_lease_impide_ejecucion_simultanea(sqlite_db):
    holder = "bloqueado-f11"
    assert fas.adquirir_lease(sqlite_db, job_name=fas.JOB_MONITORING_CYCLE, holder=holder)
    try:
        result = fas.ejecutar_ciclo_monitoreo(sqlite_db, actor="otro", incluir_reconciliacion=False)
        assert result["status"] == "skipped"
    finally:
        fas.liberar_lease(sqlite_db, job_name=fas.JOB_MONITORING_CYCLE, holder=holder)


def test_07_cron_ejecutar_ciclo(client, sqlite_db, monkeypatch):
    _seed_conflict_bloqueante(sqlite_db)
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    with patch.object(fas, "ejecutar_reconciliacion_periodica", return_value={"status": "success", "metricas": {}}):
        resp = client.post(
            "/api/admin/financial-automation/ejecutar-ciclo",
            json={"incluir_reconciliacion": False},
            headers=_cron_headers(monkeypatch),
        )
    assert resp.status_code == 200
    assert resp.get_json().get("status") == "success"


def test_08_resumen_http(client, sqlite_db, monkeypatch, session_headers):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    resp = client.get("/api/admin/financial-automation/resumen", headers=_headers(session_headers))
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "success"
    assert data.get("automation_disponible") is True


def test_09_dashboard_incluye_automation(client, sqlite_db, monkeypatch, session_headers):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    from core.financial_admin_authorization import DASHBOARD_VIEW
    headers = session_headers("admin", "DASH11", permisos=["leer"])
    resp = client.get("/api/admin/financial/dashboard", headers=headers)
    assert resp.status_code == 200
    assert "automation" in resp.get_json()


def test_10_metricas_por_dominio(sqlite_db):
    _seed_conflict_bloqueante(sqlite_db)
    m = fas.calcular_metricas(sqlite_db)
    assert "pagos" in m
    assert "refunds" in m
    assert "disputas" in m
    assert "conflictos" in m
    assert "ledger" in m


def test_11_fallo_aislado_no_detiene_ciclo(sqlite_db):
    _seed_conflict_bloqueante(sqlite_db)

    def _boom(cursor, run_id):
        raise RuntimeError("detector roto")

    with patch.object(fas, "_detectar_webhooks", _boom):
        with patch.object(fas, "ejecutar_reconciliacion_periodica", return_value={"status": "success", "metricas": {}}):
            result = fas.ejecutar_ciclo_monitoreo(sqlite_db, actor="test", incluir_reconciliacion=False)
    assert result["status"] == "success"
    assert any("webhooks" in e for e in result.get("errores", []))
    assert result.get("alertas_nuevas", 0) >= 0


def test_12_listar_ejecuciones(client, sqlite_db, monkeypatch, session_headers):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    with patch.object(fas, "ejecutar_reconciliacion_periodica", return_value={"status": "success", "metricas": {}}):
        fas.ejecutar_ciclo_monitoreo(sqlite_db, actor="hist", incluir_reconciliacion=False)
    resp = client.get("/api/admin/financial-automation/ejecuciones", headers=_headers(session_headers))
    assert resp.status_code == 200
    items = resp.get_json().get("items") or []
    assert len(items) >= 1


def test_13_finalizar_run_serializa_datetime_postgres_like(sqlite_db):
    """Regresión B6: metricas con datetime (Postgres/psycopg) no deben romper el ciclo."""
    from datetime import datetime, timezone

    repo = FinancialAutomationRepo()
    conn = sqlite_db._connect()
    cur = conn.cursor()
    repo.insertar_run(cur, run_id="run_dt13", job_name=fas.JOB_MONITORING_CYCLE, actor="cron")
    conn.commit()
    metricas = {
        "ultima_ejecucion": {
            "run_id": "run_dt13",
            "iniciado_en": datetime(2026, 8, 27, 9, 0, tzinfo=timezone.utc),
        }
    }
    repo.finalizar_run(cur, "run_dt13", estado="SUCCESS", metricas=metricas)
    conn.commit()
    row = cur.execute(
        "SELECT metricas_json FROM financial_automation_runs WHERE run_id = ?",
        ("run_dt13",),
    ).fetchone()
    conn.close()
    assert row is not None
    assert "2026-08-27" in row[0]


def test_14_cron_ejecutar_ciclo_con_metricas_datetime(client, sqlite_db, monkeypatch):
    """HTTP 500 en prod: calcular_metricas + finalizar_run con datetimes."""
    from datetime import datetime, timezone

    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    fake_ultimo = {
        "run_id": "prev",
        "iniciado_en": datetime(2026, 8, 27, 8, 0, tzinfo=timezone.utc),
    }
    with patch.object(fas, "calcular_metricas", return_value={"ultima_ejecucion": fake_ultimo}), \
         patch.object(fas, "ejecutar_reconciliacion_periodica", return_value={"status": "success", "metricas": {}}):
        resp = client.post(
            "/api/admin/financial-automation/ejecutar-ciclo",
            json={"incluir_reconciliacion": False},
            headers=_cron_headers(monkeypatch),
        )
    assert resp.status_code == 200
    assert resp.get_json().get("status") == "success"
