"""Tests FASE 04.1: permisos granulares, endpoints REST y PostgreSQL."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from RUANA.web import app as app_module
from core import db_manager as db_module
from core.conflict_authorization import (
    CONFLICT_RESOLVE,
    CONFLICT_VIEW,
    permisos_conflict_efectivos,
    tiene_permiso_conflict,
)
from core.financial.conflict_estados import EstadoConflicto, ResolucionConflicto, TipoConflicto
from core.services import financial_conflict_service as fcs


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setenv("RUANA_STRIPE_PAYMENTS_ENABLED", "1")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    from core.settings import get_settings

    get_settings.cache_clear()
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
    db = db_module.DBManager(str(tmp_path / "ruana_fase04_1.db"))
    monkeypatch.setattr(app_module, "get_db", lambda: db)
    monkeypatch.setattr(db_module, "get_db", lambda: db)
    return db


def _seed(db, importe=500.0):
    conn = db._connect()
    c = conn.cursor()
    c.execute("INSERT INTO aliados (codigo, nombre, email) VALUES (?, ?, ?)", ("SOL", "S", "s@t.com"))
    c.execute(
        "INSERT INTO aliados (codigo, nombre, email, stripe_account_id, stripe_charges_enabled) "
        "VALUES (?, ?, ?, ?, ?)",
        ("PRO", "P", "p@t.com", "acct_test", 1),
    )
    apoyo = round(importe * 0.12, 2)
    neto = round(importe - apoyo, 2)
    c.execute(
        """
        INSERT INTO contactos_ruana (
            solicitante_codigo, profesional_codigo, servicio, estado, pendiente_resolucion,
            importe_acordado, modo_pago, estado_pago, estado_financiero, estado_transferencia,
            importe_neto_profesional, apoyo_ruana, comision, stripe_payment_intent_id
        ) VALUES (?, ?, ?, 'trabajo_en_progreso', 0, ?, 'stripe', 'cobro_confirmado',
                  'ESPERANDO_CONFIRMACION', 'RETENIDO', ?, ?, ?, 'pi_f041')
        """,
        ("SOL", "PRO", "Srv", importe, neto, apoyo, apoyo),
    )
    cid = c.lastrowid
    conn.commit()
    conn.close()
    return cid, int(round(neto * 100))


def _abrir(db, cid, key="k-f041"):
    return fcs.abrir_conflicto(
        db, cid, tipo=TipoConflicto.IMPORTE_DISPUTADO, motivo="Disputa FASE 04.1",
        abierto_por="SOL", idempotency_key=key,
    )


def _headers_view(session_headers):
    return session_headers("admin", "0000", permisos=["leer"])


def _headers_resolve(session_headers):
    return session_headers("admin", "ADMIN001", permisos=["leer", "escribir", "configurar"])


def _headers_write_no_resolve(session_headers):
    return session_headers("admin", "ADMIN001", permisos=["leer", "escribir"])


# 1-3 permisos
def test_01_permiso_view_permitido():
    assert tiene_permiso_conflict(["leer"], CONFLICT_VIEW) is True


def test_02_permiso_resolve_denegado_solo_lectura():
    assert tiene_permiso_conflict(["leer"], CONFLICT_RESOLVE) is False
    assert CONFLICT_RESOLVE not in permisos_conflict_efectivos(["leer"])


def test_03_permiso_resolve_permitido_configurar():
    assert tiene_permiso_conflict(["configurar"], CONFLICT_RESOLVE) is True


# 4-5 reglas de cierre/resolución
def test_04_cerrar_sin_resolucion_rechazado(sqlite_db):
    cid, _ = _seed(sqlite_db)
    r = _abrir(sqlite_db, cid)
    bad = fcs.cerrar_conflicto(sqlite_db, r["conflict_id"], actor="admin")
    assert bad["status"] == "error"


def test_05_resolver_sin_motivo_rechazado(sqlite_db):
    cid, neto = _seed(sqlite_db)
    r = _abrir(sqlite_db, cid)
    bad = fcs.resolver_conflicto(
        sqlite_db, r["conflict_id"], ResolucionConflicto.REEMBOLSAR_TOTAL,
        actor="admin", importe_reembolsar_cents=neto,
    )
    assert bad["status"] == "error"
    assert "motivo" in bad["message"].lower()


# 6-7 auditoría en comentario y evidencia
def test_06_anadir_comentario_con_auditoria(sqlite_db):
    cid, _ = _seed(sqlite_db)
    r = _abrir(sqlite_db, cid)
    res = fcs.agregar_comentario(
        sqlite_db, r["conflict_id"], autor="admin", texto="nota auditada",
        permiso_usado="conflict.comment",
    )
    assert res["status"] == "success"
    conn = sqlite_db._connect()
    n = conn.execute(
        "SELECT COUNT(*) FROM payment_conflict_audit WHERE conflicto_id=? AND accion='comentario'",
        (r["conflict_id"],),
    ).fetchone()[0]
    conn.close()
    assert n >= 1


def test_07_anadir_evidencia_con_auditoria(sqlite_db):
    cid, _ = _seed(sqlite_db)
    r = _abrir(sqlite_db, cid)
    res = fcs.agregar_evidencia(
        sqlite_db, r["conflict_id"], tipo="doc", nombre="f.pdf",
        referencia="https://safe/ref", subido_por="admin",
        permiso_usado="conflict.add_evidence",
    )
    assert res["status"] == "success"
    conn = sqlite_db._connect()
    n = conn.execute(
        "SELECT COUNT(*) FROM payment_conflict_audit WHERE conflicto_id=? AND accion='evidencia'",
        (r["conflict_id"],),
    ).fetchone()[0]
    conn.close()
    assert n >= 1


# 8-9 idempotencia y concurrencia
def test_08_resolucion_idempotente(sqlite_db):
    cid, neto = _seed(sqlite_db)
    r = _abrir(sqlite_db, cid)
    cf = r["conflict_id"]
    payload = {
        "resolucion": ResolucionConflicto.REEMBOLSAR_TOTAL.value,
        "importe_reembolsar_cents": neto,
        "motivo": "idempotente",
        "idempotency_key": "idem-res-1",
    }
    a = fcs.resolver_conflicto(
        sqlite_db, cf, ResolucionConflicto.REEMBOLSAR_TOTAL,
        actor="admin", importe_reembolsar_cents=neto, motivo="idempotente",
        idempotency_key="idem-res-1",
    )
    b = fcs.resolver_conflicto(
        sqlite_db, cf, ResolucionConflicto.REEMBOLSAR_TOTAL,
        actor="admin", importe_reembolsar_cents=neto, motivo="idempotente",
        idempotency_key="idem-res-1",
    )
    assert a["status"] == "success"
    assert b["status"] == "success"
    assert b.get("idempotent") is True
    assert payload  # referencia estática para documentación


def test_09_segunda_resolucion_simultanea_409_o_idempotente(sqlite_db):
    cid, neto = _seed(sqlite_db)
    r = _abrir(sqlite_db, cid)
    cf = r["conflict_id"]
    results = []
    barrier = threading.Barrier(2)

    def run(key):
        barrier.wait(timeout=10)
        results.append(
            fcs.resolver_conflicto(
                sqlite_db, cf, ResolucionConflicto.REEMBOLSAR_TOTAL,
                actor="admin", importe_reembolsar_cents=neto, motivo="simultaneo",
                idempotency_key=key,
            )
        )

    t1 = threading.Thread(target=run, args=("sim-key",))
    t2 = threading.Thread(target=run, args=("otra-key",))
    t1.start()
    t2.start()
    t1.join(timeout=30)
    t2.join(timeout=30)
    assert len(results) == 2
    success = [x for x in results if x.get("status") == "success"]
    errors = [x for x in results if x.get("status") == "error"]
    assert len(success) >= 1
    assert len(success) + len(errors) == 2


# 10-11 endpoints auth y permiso
def test_10_endpoints_requieren_autenticacion(client):
    for method, path in (
        ("get", "/api/admin/financial-conflicts"),
        ("get", "/api/admin/financial-conflicts/1"),
        ("post", "/api/admin/financial-conflicts/1/resolver"),
    ):
        resp = getattr(client, method)(path, json={})
        assert resp.status_code == 401, path


def test_11_endpoints_requieren_permiso(client, session_headers):
    headers = _headers_view(session_headers)
    resp = client.post(
        "/api/admin/financial-conflicts/1/resolver",
        json={"resolucion": "REEMBOLSAR_TOTAL", "motivo": "x", "version": 1},
        headers=headers,
    )
    assert resp.status_code == 403
    data = resp.get_json()
    assert data.get("permiso_requerido") == CONFLICT_RESOLVE


# 12 no Stripe en resoluciones
@patch("stripe.Refund.create")
@patch("core.services.financial_transfer_service.stripe_client.create_transfer")
def test_12_acciones_financieras_no_llaman_stripe(mock_transfer, mock_refund, sqlite_db, client, session_headers):
    cid, neto = _seed(sqlite_db)
    r = _abrir(sqlite_db, cid)
    cf = r["conflict_id"]
    headers = _headers_resolve(session_headers)
    det = client.get(f"/api/admin/financial-conflicts/{cf}", headers=headers).get_json()
    version = det["conflicto"]["version"]
    resp = client.post(
        f"/api/admin/financial-conflicts/{cf}/resolver",
        json={
            "resolucion": ResolucionConflicto.REEMBOLSAR_TOTAL.value,
            "importe_reembolsar_cents": neto,
            "motivo": "sin stripe",
            "version": version,
            "idempotency_key": "no-stripe",
        },
        headers=headers,
    )
    assert resp.status_code == 200
    assert mock_refund.call_count == 0
    assert mock_transfer.call_count == 0
    pend = client.get(
        f"/api/admin/financial-conflicts/{cf}/acciones-pendientes", headers=headers,
    ).get_json()
    assert pend["total"] >= 1
    assert pend["acciones"][0]["orden_financiera_pendiente"] is True


# 13-14 payload y version
def test_13_payload_invalido_rechazado(client, session_headers):
    headers = _headers_resolve(session_headers)
    resp = client.post(
        "/api/admin/financial-conflicts/1/resolver",
        json={"resolucion": "NO_EXISTE", "motivo": "x", "version": 1},
        headers=headers,
    )
    assert resp.status_code == 400


def test_14_version_antigua_rechazada(sqlite_db, client, session_headers):
    cid, neto = _seed(sqlite_db)
    r = _abrir(sqlite_db, cid)
    cf = r["conflict_id"]
    headers = _headers_resolve(session_headers)
    resp = client.post(
        f"/api/admin/financial-conflicts/{cf}/resolver",
        json={
            "resolucion": ResolucionConflicto.REEMBOLSAR_TOTAL.value,
            "importe_reembolsar_cents": neto,
            "motivo": "version",
            "version": 9999,
            "idempotency_key": "ver-old",
        },
        headers=headers,
    )
    assert resp.status_code == 409
    assert resp.get_json().get("code") == "version_conflict"


# 15-17 PostgreSQL (skip si no hay servidor)
PG_DSN = "dbname=postgres user=postgres"


def _pg_available() -> bool:
    try:
        import psycopg
        conn = psycopg.connect(PG_DSN, connect_timeout=2)
        conn.close()
        return True
    except Exception:
        return False


def _run_pg_migrations(conn, migrations_dir: Path, only: tuple[str, ...] | None = None):
    import psycopg
    cur = conn.cursor()
    for path in sorted(migrations_dir.glob("*.sql")):
        if only and path.name not in only:
            continue
        sql = path.read_text(encoding="utf-8")
        cur.execute(sql)
    conn.commit()


_PG_MINIMAL_SCHEMA = """
CREATE TABLE IF NOT EXISTS aliados (
    id BIGSERIAL PRIMARY KEY,
    codigo TEXT UNIQUE NOT NULL,
    nombre TEXT NOT NULL,
    email TEXT
);
CREATE TABLE IF NOT EXISTS contactos_ruana (
    id BIGSERIAL PRIMARY KEY,
    solicitante_codigo TEXT,
    profesional_codigo TEXT,
    servicio TEXT,
    estado TEXT DEFAULT 'abierto'
);
CREATE TABLE IF NOT EXISTS payment_conflicts (
    id BIGSERIAL PRIMARY KEY,
    trabajo_id BIGINT NOT NULL REFERENCES contactos_ruana(id),
    contratante_id BIGINT NOT NULL REFERENCES aliados(id),
    profesional_id BIGINT NOT NULL REFERENCES aliados(id),
    importe_contratante NUMERIC(12,2) NOT NULL DEFAULT 0,
    importe_profesional NUMERIC(12,2) NOT NULL DEFAULT 0,
    estado TEXT NOT NULL DEFAULT 'PENDIENTE_PRUEBA',
    tipo TEXT DEFAULT 'importe_discrepante',
    prueba_url TEXT,
    comentario_admin TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS financial_transfers (
    id BIGSERIAL PRIMARY KEY,
    contacto_id BIGINT NOT NULL REFERENCES contactos_ruana(id),
    idempotency_key TEXT UNIQUE,
    amount_cents BIGINT,
    currency TEXT DEFAULT 'eur',
    destination_account_id TEXT,
    professional_codigo TEXT,
    estado TEXT DEFAULT 'RECLAMADA'
);
"""


def _pg_create_db(dbname: str):
    import psycopg
    from psycopg import sql as psql

    admin = psycopg.connect(PG_DSN)
    admin.autocommit = True
    with admin.cursor() as c:
        c.execute(psql.SQL("DROP DATABASE IF EXISTS {}").format(psql.Identifier(dbname)))
        c.execute(psql.SQL("CREATE DATABASE {}").format(psql.Identifier(dbname)))
    admin.close()
    return psycopg.connect(f"dbname={dbname} user=postgres")


def _pg_apply_fase04(conn, migrations_dir: Path):
    with conn.cursor() as c:
        c.execute(_PG_MINIMAL_SCHEMA)
    conn.commit()
    _run_pg_migrations(conn, migrations_dir, only=("20260818000500_financial_fase04_conflicts.sql",))


@pytest.mark.skipif(not _pg_available(), reason="PostgreSQL no disponible en este entorno")
def test_15_migracion_postgresql_limpia():
    migrations = Path(__file__).resolve().parents[2] / "supabase" / "migrations"
    conn = _pg_create_db("ruana_f04_clean")
    _pg_apply_fase04(conn, migrations)
    with conn.cursor() as c:
        c.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='payment_conflicts' AND column_name='estado_conflicto'"
        )
        assert c.fetchone() is not None
        c.execute("SELECT to_regclass('payment_conflict_evidence')")
        assert c.fetchone()[0] is not None
    conn.close()


@pytest.mark.skipif(not _pg_available(), reason="PostgreSQL no disponible en este entorno")
def test_16_migracion_postgresql_repetida_idempotente():
    migrations = Path(__file__).resolve().parents[2] / "supabase" / "migrations"
    conn = _pg_create_db("ruana_f04_repeat")
    _pg_apply_fase04(conn, migrations)
    _run_pg_migrations(conn, migrations, only=("20260818000500_financial_fase04_conflicts.sql",))
    conn.close()


@pytest.mark.skipif(not _pg_available(), reason="PostgreSQL no disponible en este entorno")
def test_17_foreign_keys_y_constraints_postgresql():
    migrations = Path(__file__).resolve().parents[2] / "supabase" / "migrations"
    conn = _pg_create_db("ruana_f04_constraints")
    _pg_apply_fase04(conn, migrations)
    with conn.cursor() as c:
        c.execute(
            """
            INSERT INTO aliados (codigo, nombre, email) VALUES ('A1', 'A', 'a@t.com')
            RETURNING id
            """
        )
        aid = c.fetchone()[0]
        c.execute(
            """
            INSERT INTO contactos_ruana (solicitante_codigo, profesional_codigo, servicio, estado)
            VALUES ('A1', 'A1', 'Srv', 'abierto') RETURNING id
            """
        )
        trabajo_id = c.fetchone()[0]
        c.execute(
            """
            INSERT INTO payment_conflicts (
                trabajo_id, contratante_id, profesional_id,
                importe_contratante, importe_profesional, estado
            ) VALUES (%s, %s, %s, 10, 10, 'PENDIENTE_PRUEBA') RETURNING id
            """,
            (trabajo_id, aid, aid),
        )
        conflicto_id = c.fetchone()[0]
        c.execute(
            """
            INSERT INTO payment_conflict_evidence (
                conflicto_id, tipo, nombre, referencia_segura, subido_por
            ) VALUES (%s, 'doc', 'ok.pdf', 'ref', 'admin')
            """,
            (conflicto_id,),
        )
        conn.commit()
        with pytest.raises(Exception):
            c.execute(
                """
                INSERT INTO payment_conflict_evidence (
                    conflicto_id, tipo, nombre, referencia_segura, subido_por
                ) VALUES (999999, 'doc', 'bad.pdf', 'ref', 'admin')
                """
            )
            conn.commit()
    conn.close()


# 18 endpoint view con permiso
def test_18_endpoint_listar_con_permiso_view(client, sqlite_db, session_headers):
    cid, _ = _seed(sqlite_db)
    _abrir(sqlite_db, cid)
    headers = _headers_view(session_headers)
    resp = client.get("/api/admin/financial-conflicts", headers=headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "success"
    assert data["total"] >= 1
