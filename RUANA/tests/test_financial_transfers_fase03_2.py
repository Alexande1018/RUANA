"""Tests FASE 03.2: reconciliación explícita transfer.created / updated / reversed."""

from __future__ import annotations

import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from core import db_manager as db_module
from core.financial.estados import EstadoFinanciero
from core.financial.transfer_reconciliation import DecisionReconciliacionTransfer
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
    return db_module.DBManager(str(tmp_path / "ruana_fase032.db"))


def _seed(db, estado="TRANSFERENCIA_ENVIADA", with_ft=True):
    conn = db._connect()
    c = conn.cursor()
    c.execute("INSERT INTO aliados (codigo, nombre, email) VALUES (?, ?, ?)", ("SOL", "S", "s@t.com"))
    c.execute(
        "INSERT INTO aliados (codigo, nombre, email, stripe_account_id, stripe_charges_enabled) "
        "VALUES (?, ?, ?, ?, ?)",
        ("PRO", "P", "p@t.com", "acct_test", 1),
    )
    c.execute(
        """
        INSERT INTO contactos_ruana (
            solicitante_codigo, profesional_codigo, servicio, estado, pendiente_resolucion,
            importe_acordado, modo_pago, estado_pago, estado_financiero, estado_transferencia,
            importe_neto_profesional, stripe_payment_intent_id, stripe_transfer_id
        ) VALUES (?, ?, ?, 'trabajo_en_progreso', 0, 500, 'stripe', 'cobro_confirmado', ?,
                  'ENVIADA', 440, 'pi_f032', 'tr_f032')
        """,
        ("SOL", "PRO", "Srv", estado),
    )
    cid = c.lastrowid
    if with_ft:
        c.execute(
            """
            INSERT INTO financial_transfers (
                contacto_id, idempotency_key, stripe_transfer_id, amount_cents, currency,
                destination_account_id, professional_codigo, stripe_payment_intent_id, estado
            ) VALUES (?, ?, 'tr_f032', 44000, 'eur', 'acct_test', 'PRO', 'pi_f032', 'STRIPE_CREADA')
            """,
            (cid, f"transfer-contacto-{cid}"),
        )
    conn.commit()
    conn.close()
    return cid


def _obj(cid, tid="tr_f032", **kw):
    base = {
        "id": tid,
        "amount": 44000,
        "currency": "eur",
        "destination": "acct_test",
        "reversed": False,
        "balance_transaction": "txn_bt",
        "destination_payment": "py_dest",
        "metadata": {"contacto_id": str(cid)},
    }
    base.update(kw)
    return base


def _wh(db, eid, etype, obj):
    ev = MagicMock()
    ev.id = eid
    ev.type = etype
    ev.data.object = obj
    with patch("core.stripe_client.construct_webhook_event", return_value=ev):
        return stripe_webhook_service.procesar_webhook(db, b"{}", "sig")


def _count_notifs(db, cid):
    conn = db._connect()
    n = conn.execute(
        "SELECT COUNT(*) FROM notificaciones_aliado WHERE metadata LIKE ?",
        (f'%"contacto_id": {cid}%',),
    ).fetchone()[0]
    conn.close()
    return n


# 1-5 created valid / dup / amount / currency / destination
def test_01_transfer_created_valido_confirma_tras_reconciliacion(sqlite_db):
    cid = _seed(sqlite_db)
    _wh(sqlite_db, "e1", "transfer.created", _obj(cid))
    assert fts.obtener_estado_financiero(sqlite_db, cid) == EstadoFinanciero.TRANSFERIDO
    r = te.evaluar_reconciliacion_contacto(sqlite_db, cid)
    assert r["decision"] == DecisionReconciliacionTransfer.CONFIRMED.value


def test_02_transfer_created_duplicado(sqlite_db):
    cid = _seed(sqlite_db)
    o = _obj(cid)
    _wh(sqlite_db, "e2a", "transfer.created", o)
    _wh(sqlite_db, "e2b", "transfer.created", o)
    assert fts.obtener_estado_financiero(sqlite_db, cid) == EstadoFinanciero.TRANSFERIDO
    assert _count_notifs(sqlite_db, cid) <= 1


def test_03_created_importe_incorrecto(sqlite_db):
    cid = _seed(sqlite_db)
    _wh(sqlite_db, "e3", "transfer.created", _obj(cid, amount=99999))
    assert fts.obtener_estado_financiero(sqlite_db, cid) != EstadoFinanciero.TRANSFERIDO


def test_04_created_moneda_incorrecta(sqlite_db):
    cid = _seed(sqlite_db)
    _wh(sqlite_db, "e4", "transfer.created", _obj(cid, currency="usd"))
    assert fts.obtener_estado_financiero(sqlite_db, cid) != EstadoFinanciero.TRANSFERIDO


def test_05_created_destination_incorrecto(sqlite_db):
    cid = _seed(sqlite_db)
    _wh(sqlite_db, "e5", "transfer.created", _obj(cid, destination="acct_malo"))
    assert fts.obtener_estado_financiero(sqlite_db, cid) != EstadoFinanciero.TRANSFERIDO


# 6-8 updated
def test_06_updated_sin_cambio(sqlite_db):
    cid = _seed(sqlite_db, estado="TRANSFERIDO")
    conn = sqlite_db._connect()
    conn.execute("UPDATE contactos_ruana SET estado_pago='transferido' WHERE id=?", (cid,))
    conn.commit()
    conn.close()
    _wh(sqlite_db, "e6", "transfer.updated", _obj(cid))
    assert fts.obtener_estado_financiero(sqlite_db, cid) == EstadoFinanciero.TRANSFERIDO


def test_07_updated_cambio_importe(sqlite_db):
    cid = _seed(sqlite_db)
    _wh(sqlite_db, "e7a", "transfer.created", _obj(cid))
    _wh(sqlite_db, "e7b", "transfer.updated", _obj(cid, amount=99999))
    conn = sqlite_db._connect()
    n = conn.execute(
        "SELECT COUNT(*) FROM financial_reconciliation WHERE contacto_id=? AND tipo_discrepancia=?",
        (cid, "AMOUNT_MISMATCH"),
    ).fetchone()[0]
    conn.close()
    assert n >= 1


def test_08_updated_cambio_destination(sqlite_db):
    cid = _seed(sqlite_db)
    _wh(sqlite_db, "e8a", "transfer.created", _obj(cid))
    _wh(sqlite_db, "e8b", "transfer.updated", _obj(cid, destination="acct_x"))
    conn = sqlite_db._connect()
    n = conn.execute(
        "SELECT COUNT(*) FROM financial_reconciliation WHERE contacto_id=?",
        (cid,),
    ).fetchone()[0]
    conn.close()
    assert n >= 1


# 9-11 reversed
def test_09_reversed_antes_transferido(sqlite_db):
    cid = _seed(sqlite_db)
    _wh(sqlite_db, "e9", "transfer.reversed", _obj(cid, reversed=True))
    assert fts.obtener_estado_financiero(sqlite_db, cid) == EstadoFinanciero.TRANSFERENCIA_REVERTIDA


def test_10_reversed_despues_transferido(sqlite_db):
    cid = _seed(sqlite_db)
    _wh(sqlite_db, "e10a", "transfer.created", _obj(cid))
    _wh(sqlite_db, "e10b", "transfer.reversed", _obj(cid, reversed=True))
    assert fts.obtener_estado_financiero(sqlite_db, cid) == EstadoFinanciero.TRANSFERENCIA_REVERTIDA


def test_11_reversed_duplicado(sqlite_db):
    cid = _seed(sqlite_db, estado="TRANSFERENCIA_REVERTIDA")
    conn = sqlite_db._connect()
    conn.execute("UPDATE financial_transfers SET bloqueada=1 WHERE contacto_id=?", (cid,))
    conn.commit()
    conn.close()
    _wh(sqlite_db, "e11a", "transfer.reversed", _obj(cid, reversed=True))
    _wh(sqlite_db, "e11b", "transfer.reversed", _obj(cid, reversed=True))
    assert fts.obtener_estado_financiero(sqlite_db, cid) == EstadoFinanciero.TRANSFERENCIA_REVERTIDA


# 12-14 no duplicar score/notif/transfer
@patch("core.services.financial_transfer_service.stripe_client.create_transfer")
def test_12_no_duplicar_score(mock_tr, sqlite_db):
    cid = _seed(sqlite_db, estado="ESPERANDO_CONFIRMACION", with_ft=False)
    conn = sqlite_db._connect()
    conn.execute(
        "UPDATE contactos_ruana SET estado_financiero='TRANSFERENCIA_ENVIADA', stripe_transfer_id='tr_sc' WHERE id=?",
        (cid,),
    )
    conn.execute(
        "INSERT INTO financial_transfers (contacto_id, idempotency_key, stripe_transfer_id, amount_cents, "
        "currency, destination_account_id, professional_codigo, estado) "
        "VALUES (?, ?, 'tr_sc', 44000, 'eur', 'acct_test', 'PRO', 'STRIPE_CREADA')",
        (cid, f"transfer-contacto-{cid}"),
    )
    conn.commit()
    conn.close()
    with patch.object(pago_service, "_aplicar_score_tras_transfer") as mock_score:
        _wh(sqlite_db, "e12a", "transfer.created", _obj(cid, tid="tr_sc"))
        _wh(sqlite_db, "e12b", "transfer.created", _obj(cid, tid="tr_sc"))
        assert mock_score.call_count <= 1


def test_13_no_duplicar_notificacion(sqlite_db):
    cid = _seed(sqlite_db)
    _wh(sqlite_db, "e13a", "transfer.created", _obj(cid))
    n1 = _count_notifs(sqlite_db, cid)
    _wh(sqlite_db, "e13b", "transfer.created", _obj(cid))
    n2 = _count_notifs(sqlite_db, cid)
    assert n2 == n1


@patch("core.services.financial_transfer_service.stripe_client.create_transfer")
def test_14_no_segunda_transfer(mock_tr, sqlite_db):
    cid = _seed(sqlite_db, estado="ESPERANDO_CONFIRMACION", with_ft=False)
    conn = sqlite_db._connect()
    c = conn.cursor()
    c.execute(
        "UPDATE contactos_ruana SET estado_financiero='ESPERANDO_CONFIRMACION' WHERE id=?", (cid,)
    )
    conn.commit()
    conn.close()
    mock_tr.return_value = {"id": "tr_once"}
    pago_service.confirmar_trabajo_y_transferir(sqlite_db, cid, "SOL")
    pago_service.confirmar_trabajo_y_transferir(sqlite_db, cid, "SOL")
    assert mock_tr.call_count == 1


def test_15_revertida_bloquea_liberacion(sqlite_db):
    cid = _seed(sqlite_db, estado="TRANSFERENCIA_REVERTIDA")
    conn = sqlite_db._connect()
    conn.execute("UPDATE financial_transfers SET bloqueada=1 WHERE contacto_id=?", (cid,))
    conn.commit()
    conn.close()
    res = pago_service.confirmar_trabajo_y_transferir(sqlite_db, cid, "SOL")
    assert res["status"] == "error"
    assert res.get("bloqueo") == "reversion"


# 16-19 reconciliación API
def test_16_reconciliacion_confirmed(sqlite_db):
    cid = _seed(sqlite_db)
    _wh(sqlite_db, "e16", "transfer.created", _obj(cid))
    r = te.evaluar_reconciliacion_contacto(sqlite_db, cid)
    assert r["decision"] == "confirmed"


def test_17_reconciliacion_pending(sqlite_db):
    cid = _seed(sqlite_db)
    _wh(sqlite_db, "e17", "transfer.created", _obj(cid, balance_transaction="", destination_payment=""))
    r = te.evaluar_reconciliacion_contacto(sqlite_db, cid)
    assert r["decision"] == "pending"
    assert fts.obtener_estado_financiero(sqlite_db, cid) == EstadoFinanciero.TRANSFERENCIA_ENVIADA


def test_18_reconciliacion_reversed(sqlite_db):
    cid = _seed(sqlite_db)
    _wh(sqlite_db, "e18", "transfer.reversed", _obj(cid, reversed=True))
    r = te.evaluar_reconciliacion_contacto(sqlite_db, cid)
    assert r["decision"] in ("reversed", "pending")


def test_19_reconciliacion_mismatch(sqlite_db):
    cid = _seed(sqlite_db)
    _wh(sqlite_db, "e19", "transfer.created", _obj(cid, amount=1))
    r = te.evaluar_reconciliacion_contacto(sqlite_db, cid)
    assert r["decision"] == "mismatch"


def test_20_created_sin_evidencia_queda_enviada(sqlite_db):
    cid = _seed(sqlite_db)
    _wh(sqlite_db, "e20", "transfer.created", {
        "id": "tr_pend", "metadata": {"contacto_id": str(cid)},
        "amount": 44000, "currency": "eur", "destination": "acct_test", "reversed": False,
    })
    assert fts.obtener_estado_financiero(sqlite_db, cid) == EstadoFinanciero.TRANSFERENCIA_ENVIADA
