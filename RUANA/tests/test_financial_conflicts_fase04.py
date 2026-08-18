"""Tests FASE 04: sistema formal de conflictos financieros."""

from __future__ import annotations

import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from core import db_manager as db_module
from core.financial.conflict_estados import EstadoConflicto, ResolucionConflicto, TipoConflicto
from core.financial.estados import EstadoFinanciero
from core.financial.transfer_reconciliation import DecisionReconciliacionTransfer, evaluar_reconciliacion_transfer
from core.services import financial_conflict_service as fcs
from core.services import financial_transaction_service as fts
from core.services import pago_service
from core.services import stripe_transfer_events as te
from core.services import stripe_webhook_service


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
    return db_module.DBManager(str(tmp_path / "ruana_fase04.db"))


def _seed_stripe_listo(db, importe=500.0):
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
                  'ESPERANDO_CONFIRMACION', 'RETENIDO', ?, ?, ?, 'pi_f04')
        """,
        ("SOL", "PRO", "Srv", importe, neto, apoyo, apoyo),
    )
    cid = c.lastrowid
    conn.commit()
    conn.close()
    return cid, int(round(neto * 100))


def _abrir(db, cid, key="k1", motivo="Disputa test"):
    return fcs.abrir_conflicto(
        db, cid, tipo=TipoConflicto.IMPORTE_DISPUTADO, motivo=motivo,
        abierto_por="SOL", idempotency_key=key,
    )


def _transfer_obj(cid, tid="tr_f04", **kw):
    base = {
        "id": tid, "amount": 44000, "currency": "eur", "destination": "acct_test",
        "reversed": False, "balance_transaction": "txn", "destination_payment": "py",
        "metadata": {"contacto_id": str(cid)},
    }
    base.update(kw)
    return base


def _webhook(db, eid, etype, obj):
    ev = MagicMock()
    ev.id = eid
    ev.type = etype
    ev.data.object = obj
    with patch("core.stripe_client.construct_webhook_event", return_value=ev):
        return stripe_webhook_service.procesar_webhook(db, b"{}", "sig")


# 1-2 apertura
def test_01_abrir_conflicto_correctamente(sqlite_db):
    cid, _ = _seed_stripe_listo(sqlite_db)
    r = _abrir(sqlite_db, cid)
    assert r["status"] == "success"
    assert r["estado_conflicto"] == EstadoConflicto.ABIERTO.value
    bloquea, _ = fcs.bloquea_operaciones_financieras(sqlite_db, cid)
    assert bloquea is True


def test_02_abrir_duplicado_idempotente(sqlite_db):
    cid, _ = _seed_stripe_listo(sqlite_db)
    r1 = _abrir(sqlite_db, cid, key="dup-key")
    r2 = _abrir(sqlite_db, cid, key="dup-key")
    assert r1["status"] == "success"
    assert r2["status"] == "success"
    assert r2.get("idempotent") is True
    conn = sqlite_db._connect()
    n = conn.execute("SELECT COUNT(*) FROM payment_conflicts WHERE trabajo_id=?", (cid,)).fetchone()[0]
    conn.close()
    assert n == 1


# 3-6 bloqueos financieros
@patch("core.services.financial_transfer_service.stripe_client.create_transfer")
def test_03_conflicto_bloquea_confirmar_trabajo(mock_tr, sqlite_db):
    cid, _ = _seed_stripe_listo(sqlite_db)
    _abrir(sqlite_db, cid)
    mock_tr.return_value = {"id": "tr_x"}
    res = pago_service.confirmar_trabajo_y_transferir(sqlite_db, cid, "SOL")
    assert res["status"] == "error"
    assert res.get("bloqueo") == "conflicto"
    assert mock_tr.call_count == 0


@patch("core.services.financial_transfer_service.stripe_client.create_transfer")
def test_04_conflicto_bloquea_reintento(mock_tr, sqlite_db):
    cid, _ = _seed_stripe_listo(sqlite_db)
    _abrir(sqlite_db, cid, key="pre-transfer")
    mock_tr.return_value = {"id": "tr_r"}
    res = pago_service.confirmar_trabajo_y_transferir(sqlite_db, cid, "SOL")
    assert res["status"] == "error"
    assert res.get("bloqueo") == "conflicto"
    assert mock_tr.call_count == 0


def test_05_conflicto_bloquea_reconciliacion_confirmed(sqlite_db):
    cid, neto = _seed_stripe_listo(sqlite_db)
    _abrir(sqlite_db, cid)
    decision, motivo = evaluar_reconciliacion_transfer(
        contacto_id=cid,
        estado_financiero=EstadoFinanciero.TRANSFERENCIA_ENVIADA,
        financial_transfer={"amount_cents": neto, "currency": "eur", "destination_account_id": "acct_test"},
        stripe_snapshot=_transfer_obj(cid),
        conflicto_abierto=True,
    )
    assert decision == DecisionReconciliacionTransfer.BLOCKED
    assert motivo == "conflicto_abierto"


@patch("core.services.financial_transfer_service.stripe_client.create_transfer")
def test_06_conflicto_bloquea_webhook_transferencia(mock_tr, sqlite_db):
    cid, _ = _seed_stripe_listo(sqlite_db)
    mock_tr.return_value = {"id": "tr_wh"}
    pago_service.confirmar_trabajo_y_transferir(sqlite_db, cid, "SOL")
    assert fts.obtener_estado_financiero(sqlite_db, cid) == EstadoFinanciero.TRANSFERENCIA_ENVIADA
    _abrir(sqlite_db, cid, key="wh-block")
    wh = _webhook(sqlite_db, "e6", "transfer.created", _transfer_obj(cid, tid="tr_wh"))
    assert wh.get("resultado") == "bloqueado_conflicto"
    assert fts.obtener_estado_financiero(sqlite_db, cid) != EstadoFinanciero.TRANSFERIDO


# 7-13 resoluciones
def test_07_no_resolver_sin_decision_valida(sqlite_db):
    cid, _ = _seed_stripe_listo(sqlite_db)
    r = _abrir(sqlite_db, cid)
    cid_conf = r["conflict_id"]
    bad = fcs.resolver_conflicto(
        sqlite_db, cid_conf, ResolucionConflicto.ESCALAR_ADMIN,
        actor="admin", responsable_codigo="", comentario="",
    )
    assert bad["status"] == "error"


def test_08_liberar_profesional_valida_importe(sqlite_db):
    cid, neto = _seed_stripe_listo(sqlite_db)
    r = _abrir(sqlite_db, cid)
    ok = fcs.resolver_conflicto(
        sqlite_db, r["conflict_id"], ResolucionConflicto.LIBERAR_PROFESIONAL,
        actor="admin", importe_liberar_cents=neto, motivo="liberar ok",
    )
    assert ok["status"] == "success"
    bad = fcs.resolver_conflicto(
        sqlite_db, r["conflict_id"], ResolucionConflicto.LIBERAR_PROFESIONAL,
        actor="admin", importe_liberar_cents=neto + 99999, idempotency_key="bad-lib",
    )
    assert bad["status"] == "error"


def test_09_reembolsar_total_pendiente_sin_stripe(sqlite_db):
    cid, neto = _seed_stripe_listo(sqlite_db)
    r = _abrir(sqlite_db, cid)
    res = fcs.resolver_conflicto(
        sqlite_db, r["conflict_id"], ResolucionConflicto.REEMBOLSAR_TOTAL,
        actor="admin", importe_reembolsar_cents=neto, motivo="reembolso total",
    )
    assert res["status"] == "success"
    assert res.get("orden_financiera_pendiente") is True
    conn = sqlite_db._connect()
    row = conn.execute(
        "SELECT resolucion FROM payment_conflicts WHERE id=?", (r["conflict_id"],),
    ).fetchone()
    conn.close()
    assert row[0] == ResolucionConflicto.REEMBOLSAR_TOTAL.value


def test_10_reembolsar_parcial_valida_maximo(sqlite_db):
    cid, neto = _seed_stripe_listo(sqlite_db)
    r = _abrir(sqlite_db, cid)
    bad = fcs.resolver_conflicto(
        sqlite_db, r["conflict_id"], ResolucionConflicto.REEMBOLSAR_PARCIAL,
        actor="admin", importe_reembolsar_cents=neto + 1, motivo="demasiado",
    )
    assert bad["status"] == "error"
    ok = fcs.resolver_conflicto(
        sqlite_db, r["conflict_id"], ResolucionConflicto.REEMBOLSAR_PARCIAL,
        actor="admin", importe_reembolsar_cents=1000, motivo="parcial ok",
        idempotency_key="ok-parc",
    )
    assert ok["status"] == "success"


def test_11_dividir_importe_valida_suma(sqlite_db):
    cid, neto = _seed_stripe_listo(sqlite_db)
    r = _abrir(sqlite_db, cid)
    ok = fcs.resolver_conflicto(
        sqlite_db, r["conflict_id"], ResolucionConflicto.DIVIDIR_IMPORTE,
        actor="admin", importe_profesional_cents=neto // 2,
        importe_contratante_cents=neto // 2, motivo="dividir ok",
    )
    assert ok["status"] == "success"
    bad = fcs.resolver_conflicto(
        sqlite_db, r["conflict_id"], ResolucionConflicto.DIVIDIR_IMPORTE,
        actor="admin", importe_profesional_cents=neto, importe_contratante_cents=neto,
        idempotency_key="bad-div",
    )
    assert bad["status"] == "error"


def test_12_mantener_retenido_conserva_bloqueo(sqlite_db):
    cid, _ = _seed_stripe_listo(sqlite_db)
    r = _abrir(sqlite_db, cid)
    res = fcs.resolver_conflicto(
        sqlite_db, r["conflict_id"], ResolucionConflicto.MANTENER_RETENIDO, actor="admin",
    )
    assert res["status"] == "success"
    bloquea, _ = fcs.bloquea_operaciones_financieras(sqlite_db, cid)
    assert bloquea is True


def test_13_escalar_admin_exige_responsable_y_comentario(sqlite_db):
    cid, _ = _seed_stripe_listo(sqlite_db)
    r = _abrir(sqlite_db, cid)
    ok = fcs.resolver_conflicto(
        sqlite_db, r["conflict_id"], ResolucionConflicto.ESCALAR_ADMIN,
        actor="admin", responsable_codigo="ADM01", comentario="escalado",
    )
    assert ok["status"] == "success"
    conn = sqlite_db._connect()
    row = conn.execute(
        "SELECT estado_conflicto, responsable_codigo FROM payment_conflicts WHERE id=?",
        (r["conflict_id"],),
    ).fetchone()
    conn.close()
    assert row[0] == EstadoConflicto.ESCALADO.value


# 14-16 evidencia, comentarios, concurrencia admin
def test_14_evidencia_auditada(sqlite_db):
    cid, _ = _seed_stripe_listo(sqlite_db)
    r = _abrir(sqlite_db, cid)
    ev = fcs.agregar_evidencia(
        sqlite_db, r["conflict_id"], tipo="documento", nombre="factura.pdf",
        referencia="https://safe/ref", subido_por="SOL",
    )
    assert ev["status"] == "success"
    conn = sqlite_db._connect()
    n = conn.execute(
        "SELECT COUNT(*) FROM payment_conflict_audit WHERE conflicto_id=? AND accion='evidencia'",
        (r["conflict_id"],),
    ).fetchone()[0]
    conn.close()
    assert n >= 1


def test_15_comentario_append_only(sqlite_db):
    cid, _ = _seed_stripe_listo(sqlite_db)
    r = _abrir(sqlite_db, cid)
    c1 = fcs.agregar_comentario(sqlite_db, r["conflict_id"], autor="admin", texto="nota 1")
    c2 = fcs.agregar_comentario(sqlite_db, r["conflict_id"], autor="admin", texto="nota 2")
    assert c1["comment_id"] != c2["comment_id"]
    conn = sqlite_db._connect()
    n = conn.execute(
        "SELECT COUNT(*) FROM payment_conflict_comments WHERE conflicto_id=?",
        (r["conflict_id"],),
    ).fetchone()[0]
    conn.close()
    assert n == 2


def test_16_dos_admins_no_resuelven_dos_veces(sqlite_db):
    cid, neto = _seed_stripe_listo(sqlite_db)
    r = _abrir(sqlite_db, cid)
    cf = r["conflict_id"]
    results = []
    barrier = threading.Barrier(2)

    def run():
        barrier.wait(timeout=10)
        results.append(
            fcs.resolver_conflicto(
                sqlite_db, cf, ResolucionConflicto.REEMBOLSAR_TOTAL,
                actor="admin", importe_reembolsar_cents=neto, motivo="concurrente",
                idempotency_key="misma-resolucion",
            )
        )

    t1 = threading.Thread(target=run)
    t2 = threading.Thread(target=run)
    t1.start()
    t2.start()
    t1.join(timeout=30)
    t2.join(timeout=30)
    assert len(results) == 2
    success = [x for x in results if x.get("status") == "success"]
    assert len(success) >= 1
    assert len(success) + sum(1 for x in results if x.get("status") == "error") == 2
    conn = sqlite_db._connect()
    ec = conn.execute(
        "SELECT estado_conflicto FROM payment_conflicts WHERE id=?", (cf,),
    ).fetchone()[0]
    conn.close()
    assert ec == EstadoConflicto.RESUELTO.value


# 17-18 cerrar
def test_17_cerrar_exige_resuelto(sqlite_db):
    cid, _ = _seed_stripe_listo(sqlite_db)
    r = _abrir(sqlite_db, cid)
    bad = fcs.cerrar_conflicto(sqlite_db, r["conflict_id"], actor="admin")
    assert bad["status"] == "error"


def test_18_cerrado_no_reabre(sqlite_db):
    cid, neto = _seed_stripe_listo(sqlite_db)
    r = _abrir(sqlite_db, cid)
    cf = r["conflict_id"]
    fcs.resolver_conflicto(
        sqlite_db, cf, ResolucionConflicto.REEMBOLSAR_TOTAL,
        actor="admin", importe_reembolsar_cents=neto, motivo="cerrar flujo",
    )
    cerr = fcs.cerrar_conflicto(sqlite_db, cf, actor="admin")
    assert cerr["status"] == "success"
    trans = fcs.transicionar_conflicto(sqlite_db, cf, EstadoConflicto.ABIERTO, actor="admin")
    assert trans["status"] == "error"
    conn = sqlite_db._connect()
    ec = conn.execute(
        "SELECT estado_conflicto FROM payment_conflicts WHERE id=?", (cf,),
    ).fetchone()[0]
    conn.close()
    assert ec == EstadoConflicto.CERRADO.value


# 19-21 casos especiales
def test_19_conflicto_post_transferido_alerta(sqlite_db):
    cid, neto = _seed_stripe_listo(sqlite_db)
    conn = sqlite_db._connect()
    conn.execute(
        "UPDATE contactos_ruana SET estado_financiero='TRANSFERIDO', estado_pago='transferido' WHERE id=?",
        (cid,),
    )
    conn.commit()
    conn.close()
    r = _abrir(sqlite_db, cid, key="post-tr", motivo="post transferido")
    assert r["status"] == "success"
    bloquea, _ = fcs.bloquea_operaciones_financieras(sqlite_db, cid)
    assert bloquea is True


def test_20_conflicto_durante_stripe_en_proceso(sqlite_db):
    cid, _ = _seed_stripe_listo(sqlite_db)
    conn = sqlite_db._connect()
    conn.execute(
        """
        INSERT INTO financial_transfers (
            contacto_id, idempotency_key, amount_cents, currency,
            destination_account_id, professional_codigo, estado
        ) VALUES (?, ?, 44000, 'eur', 'acct_test', 'PRO', 'STRIPE_EN_PROCESO')
        """,
        (cid, f"transfer-contacto-{cid}"),
    )
    conn.commit()
    conn.close()
    r = _abrir(sqlite_db, cid, key="during-proc", motivo="durante stripe")
    assert r["status"] == "success"
    with patch("core.services.financial_transfer_service.stripe_client.create_transfer") as mock_tr:
        res = pago_service.confirmar_trabajo_y_transferir(sqlite_db, cid, "SOL")
        assert mock_tr.call_count == 0
        assert res.get("bloqueo") == "conflicto" or res.get("estado") == "transferencia_en_proceso"


def test_21_importes_en_centimos(sqlite_db):
    cid, neto = _seed_stripe_listo(sqlite_db)
    r = _abrir(sqlite_db, cid, motivo="centimos")
    conn = sqlite_db._connect()
    row = conn.execute(
        "SELECT importe_reclamado_cents FROM payment_conflicts WHERE id=?",
        (r["conflict_id"],),
    ).fetchone()
    conn.close()
    assert isinstance(row[0], int)
    assert row[0] == neto


def test_22_bloqueo_central_coherente_con_reconciliacion(sqlite_db):
    """El bloqueo financiero usa un único punto de entrada compartido con reconciliación."""
    cid, neto = _seed_stripe_listo(sqlite_db)
    _abrir(sqlite_db, cid, key="central-block")
    bloquea_svc, _ = fcs.bloquea_operaciones_financieras(sqlite_db, cid)
    decision, motivo = evaluar_reconciliacion_transfer(
        contacto_id=cid,
        estado_financiero=EstadoFinanciero.TRANSFERENCIA_ENVIADA,
        financial_transfer={"amount_cents": neto, "currency": "eur", "destination_account_id": "acct_test"},
        stripe_snapshot=_transfer_obj(cid),
        conflicto_abierto=bloquea_svc,
    )
    assert bloquea_svc is True
    assert decision == DecisionReconciliacionTransfer.BLOCKED
    assert motivo == "conflicto_abierto"