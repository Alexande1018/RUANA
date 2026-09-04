"""Tests FASE 03: transferencias Stripe blindadas."""

from __future__ import annotations

import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from core import db_manager as db_module
from core.financial.estados import EstadoFinanciero, EstadoTransferencia
from core.services import financial_transaction_service as fts
from core.services import financial_transfer_service as transfer_svc
from core.services import pago_service
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
    return db_module.DBManager(str(tmp_path / "ruana_fase03.db"))


def _seed_listo_transferir(db, importe=500.0, prof_account="acct_test", prof="PRO"):
    conn = db._connect()
    c = conn.cursor()
    c.execute("INSERT INTO aliados (codigo, nombre, email) VALUES (?, ?, ?)", ("SOL", "S", "s@t.com"))
    c.execute(
        "INSERT INTO aliados (codigo, nombre, email, stripe_account_id, stripe_charges_enabled) "
        "VALUES (?, ?, ?, ?, ?)",
        (prof, "P", "p@t.com", prof_account, 1),
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
                  'ESPERANDO_CONFIRMACION', 'RETENIDO', ?, ?, ?, 'pi_test_f03')
        """,
        ("SOL", prof, "Srv", importe, neto, apoyo, apoyo),
    )
    cid = c.lastrowid
    conn.commit()
    conn.close()
    return cid


def _mock_event(event_id, event_type, obj):
    event = MagicMock()
    event.id = event_id
    event.type = event_type
    event.data.object = obj
    return event


def _webhook(db, event_id, event_type, obj):
    event = _mock_event(event_id, event_type, obj)
    with patch("core.stripe_client.construct_webhook_event", return_value=event):
        return stripe_webhook_service.procesar_webhook(db, b"{}", "sig")


def _count_transfers(db, contacto_id):
    conn = db._connect()
    n = conn.execute(
        "SELECT COUNT(*) FROM financial_transfers WHERE contacto_id=?", (contacto_id,)
    ).fetchone()[0]
    conn.close()
    return n


@patch("core.services.financial_transfer_service.stripe_client.create_transfer")
def test_01_flujo_normal_hasta_transferido(mock_transfer, sqlite_db):
    cid = _seed_listo_transferir(sqlite_db)
    mock_transfer.return_value = {"id": "tr_normal"}

    res = pago_service.confirmar_trabajo_y_transferir(sqlite_db, cid, "SOL")
    assert res["status"] == "success"
    assert res["estado_financiero"] == EstadoFinanciero.TRANSFERENCIA_ENVIADA.value
    assert res["estado_pago"] == "transfer_pendiente"
    assert fts.obtener_estado_financiero(sqlite_db, cid) == EstadoFinanciero.TRANSFERENCIA_ENVIADA
    assert mock_transfer.call_count == 1

    _webhook(
        sqlite_db, "evt_tr_c", "transfer.created",
        {
            "id": "tr_normal", "amount": 44000, "currency": "eur", "destination": "acct_test",
            "balance_transaction": "txn_normal", "destination_payment": "py_normal",
            "metadata": {"contacto_id": str(cid)},
        },
    )
    assert fts.obtener_estado_financiero(sqlite_db, cid) == EstadoFinanciero.TRANSFERIDO
    conn = sqlite_db._connect()
    row = conn.execute(
        "SELECT estado_pago, estado_transferencia FROM contactos_ruana WHERE id=?", (cid,)
    ).fetchone()
    conn.close()
    assert row[0] == "transferido"
    assert row[1] == "COMPLETADA"
    assert _count_transfers(sqlite_db, cid) == 1


@patch("core.services.financial_transfer_service.stripe_client.create_transfer")
def test_02_doble_clic_una_transferencia(mock_transfer, sqlite_db):
    cid = _seed_listo_transferir(sqlite_db)
    mock_transfer.return_value = {"id": "tr_doble"}

    r1 = pago_service.confirmar_trabajo_y_transferir(sqlite_db, cid, "SOL")
    r2 = pago_service.confirmar_trabajo_y_transferir(sqlite_db, cid, "SOL")
    assert r1["status"] == "success"
    assert r2["status"] == "success"
    assert mock_transfer.call_count == 1
    assert _count_transfers(sqlite_db, cid) == 1


@patch("core.services.financial_transfer_service.stripe_client.create_transfer")
def test_03_concurrencia_una_transferencia(mock_transfer, sqlite_db):
    """Dos hilos simultáneos: exactamente una llamada Stripe y una fila financial_transfers."""
    cid = _seed_listo_transferir(sqlite_db)
    start_barrier = threading.Barrier(2, timeout=10)
    stripe_lock = threading.Lock()
    idempotency_keys_seen = []
    thread_errors = []

    def slow_create_transfer(**kwargs):
        with stripe_lock:
            idempotency_keys_seen.append(kwargs.get("idempotency_key"))
        import time
        time.sleep(0.1)
        return {"id": "tr_conc"}

    mock_transfer.side_effect = slow_create_transfer

    results = []

    def run():
        try:
            start_barrier.wait(timeout=10)
            results.append(pago_service.confirmar_trabajo_y_transferir(sqlite_db, cid, "SOL"))
        except Exception as exc:
            thread_errors.append(exc)

    t1 = threading.Thread(target=run, name="concurrencia-t1")
    t2 = threading.Thread(target=run, name="concurrencia-t2")
    t1.start()
    t2.start()
    t1.join(timeout=30)
    t2.join(timeout=30)
    if t1.is_alive():
        pytest.fail("Hilo concurrencia-t1 bloqueado (>30s)")
    if t2.is_alive():
        pytest.fail("Hilo concurrencia-t2 bloqueado (>30s)")

    assert not thread_errors, f"Excepciones en hilos: {thread_errors}"
    assert len(results) == 2, f"Resultados incompletos: {results}"
    assert all(r["status"] == "success" for r in results), results

    en_proceso = [r for r in results if r.get("estado") == "transferencia_en_proceso"]
    enviada = [r for r in results if r.get("estado") == "transferencia_enviada"]
    assert len(en_proceso) == 1, f"Un hilo debe recibir transferencia_en_proceso: {results}"
    assert len(enviada) == 1, f"Un hilo debe completar transferencia_enviada: {results}"
    assert en_proceso[0].get("idempotent") is True

    assert mock_transfer.call_count == 1, (
        f"Stripe create_transfer llamado {mock_transfer.call_count} veces; keys={idempotency_keys_seen}"
    )
    assert idempotency_keys_seen == [f"transfer-contacto-{cid}"]
    assert _count_transfers(sqlite_db, cid) == 1

    conn = sqlite_db._connect()
    ft = conn.execute(
        "SELECT estado, stripe_transfer_id, idempotency_key FROM financial_transfers WHERE contacto_id=?",
        (cid,),
    ).fetchone()
    conn.close()
    assert ft[0] == "STRIPE_CREADA"
    assert ft[1] == "tr_conc"
    assert ft[2] == f"transfer-contacto-{cid}"
    assert fts.obtener_estado_financiero(sqlite_db, cid) == EstadoFinanciero.TRANSFERENCIA_ENVIADA


@patch("core.services.financial_transfer_service.stripe_client.create_transfer")
def test_04_reintento_idempotente(mock_transfer, sqlite_db):
    cid = _seed_listo_transferir(sqlite_db)
    mock_transfer.return_value = {"id": "tr_reint"}
    for _ in range(3):
        res = pago_service.confirmar_trabajo_y_transferir(sqlite_db, cid, "SOL")
        assert res["status"] == "success"
    assert mock_transfer.call_count == 1


@patch("core.services.financial_transfer_service.stripe_client.create_transfer")
def test_05_timeout_recuperacion_sin_duplicar(mock_transfer, sqlite_db):
    cid = _seed_listo_transferir(sqlite_db)
    mock_transfer.side_effect = [TimeoutError("timeout red"), {"id": "tr_timeout"}]
    with patch(
        "core.services.financial_transfer_service.stripe_client.retrieve_transfer_by_idempotency_metadata",
        return_value=None,
    ):
        r1 = pago_service.confirmar_trabajo_y_transferir(sqlite_db, cid, "SOL")
        assert r1["status"] == "error"
    r2 = pago_service.confirmar_trabajo_y_transferir(sqlite_db, cid, "SOL")
    assert r2["status"] == "success"
    assert mock_transfer.call_count == 2
    assert _count_transfers(sqlite_db, cid) == 1


@patch("core.services.financial_transfer_service.stripe_client.create_transfer")
def test_06_webhook_duplicado_sin_efectos(mock_transfer, sqlite_db):
    cid = _seed_listo_transferir(sqlite_db)
    mock_transfer.return_value = {"id": "tr_dup_wh"}
    pago_service.confirmar_trabajo_y_transferir(sqlite_db, cid, "SOL")
    obj = {"id": "tr_dup_wh", "metadata": {"contacto_id": str(cid)}}
    for i in range(3):
        _webhook(sqlite_db, f"evt_dup_c_{i}", "transfer.created", obj)
    for i in range(3):
        _webhook(sqlite_db, f"evt_dup_p_{i}", "transfer.paid", obj)
    assert fts.obtener_estado_financiero(sqlite_db, cid) == EstadoFinanciero.TRANSFERIDO
    assert _count_transfers(sqlite_db, cid) == 1


@patch("core.services.financial_transfer_service.stripe_client.create_transfer")
def test_07_webhook_fuera_de_orden_paid_antes_created(mock_transfer, sqlite_db):
    cid = _seed_listo_transferir(sqlite_db)
    mock_transfer.return_value = {"id": "tr_ooo"}
    pago_service.confirmar_trabajo_y_transferir(sqlite_db, cid, "SOL")
    obj = {"id": "tr_ooo", "metadata": {"contacto_id": str(cid)}}
    _webhook(sqlite_db, "evt_ooo_p", "transfer.paid", obj)
    assert fts.obtener_estado_financiero(sqlite_db, cid) == EstadoFinanciero.TRANSFERIDO
    _webhook(sqlite_db, "evt_ooo_c", "transfer.created", obj)
    assert fts.obtener_estado_financiero(sqlite_db, cid) == EstadoFinanciero.TRANSFERIDO


@patch("core.services.financial_transfer_service.stripe_client.create_transfer")
def test_08_transferencia_fallida(mock_transfer, sqlite_db):
    cid = _seed_listo_transferir(sqlite_db)
    mock_transfer.return_value = {"id": "tr_fail"}
    pago_service.confirmar_trabajo_y_transferir(sqlite_db, cid, "SOL")
    _webhook(
        sqlite_db, "evt_fail", "transfer.failed",
        {"id": "tr_fail", "metadata": {"contacto_id": str(cid)}},
    )
    conn = sqlite_db._connect()
    est_tr = conn.execute(
        "SELECT estado_transferencia FROM contactos_ruana WHERE id=?", (cid,)
    ).fetchone()[0]
    conn.close()
    assert est_tr == EstadoTransferencia.FALLIDA.value
    assert fts.obtener_estado_financiero(sqlite_db, cid) == EstadoFinanciero.TRANSFERENCIA_FALLIDA


def test_09_conflicto_abierto_bloquea(sqlite_db):
    cid = _seed_listo_transferir(sqlite_db)
    conn = sqlite_db._connect()
    conn.execute(
        "UPDATE contactos_ruana SET estado='importe_en_disputa' WHERE id=?",
        (cid,),
    )
    conn.commit()
    conn.close()
    res = pago_service.confirmar_trabajo_y_transferir(sqlite_db, cid, "SOL")
    assert res["status"] == "error"
    assert "conflicto" in res["message"].lower()


@patch("core.services.financial_transfer_service.stripe_client.create_transfer")
def test_10_importe_incorrecto_bloquea(mock_transfer, sqlite_db):
    cid = _seed_listo_transferir(sqlite_db)
    conn = sqlite_db._connect()
    conn.execute(
        "INSERT INTO financial_transfers (contacto_id, idempotency_key, amount_cents, currency, "
        "destination_account_id, professional_codigo, estado) "
        "VALUES (?, ?, ?, 'eur', 'acct_test', 'PRO', 'RECLAMADA')",
        (cid, f"transfer-contacto-{cid}", 99999),
    )
    conn.commit()
    conn.close()
    res = pago_service.confirmar_trabajo_y_transferir(sqlite_db, cid, "SOL")
    assert res["status"] == "error"
    assert res.get("bloqueo") == "importe"
    mock_transfer.assert_not_called()


@patch("core.services.financial_transfer_service.stripe_client.create_transfer")
def test_11_profesional_incorrecto_bloquea(mock_transfer, sqlite_db):
    cid = _seed_listo_transferir(sqlite_db)
    conn = sqlite_db._connect()
    conn.execute(
        "INSERT INTO financial_transfers (contacto_id, idempotency_key, amount_cents, currency, "
        "destination_account_id, professional_codigo, estado) "
        "VALUES (?, ?, ?, 'eur', 'acct_test', 'OTRO', 'RECLAMADA')",
        (cid, f"transfer-contacto-{cid}", 44000),
    )
    conn.commit()
    conn.close()
    res = pago_service.confirmar_trabajo_y_transferir(sqlite_db, cid, "SOL")
    assert res["status"] == "error"
    assert res.get("bloqueo") == "profesional"
    mock_transfer.assert_not_called()


@patch("core.services.financial_transfer_service.stripe_client.create_transfer")
def test_12_cuenta_connect_obsoleta_se_actualiza_si_no_hay_transfer(mock_transfer, sqlite_db):
    """Caso Sandra: Connect de prueba/rotada sin Transfer Stripe → se corrige el destino."""
    cid = _seed_listo_transferir(sqlite_db)
    conn = sqlite_db._connect()
    conn.execute(
        "INSERT INTO financial_transfers (contacto_id, idempotency_key, amount_cents, currency, "
        "destination_account_id, professional_codigo, estado) "
        "VALUES (?, ?, ?, 'eur', 'acct_malo', 'PRO', 'RECLAMADA')",
        (cid, f"transfer-contacto-{cid}", 44000),
    )
    conn.commit()
    conn.close()
    mock_transfer.return_value = {"id": "tr_destino_ok"}
    res = pago_service.confirmar_trabajo_y_transferir(sqlite_db, cid, "SOL")
    assert res["status"] == "success"
    assert res.get("stripe_transfer_id") == "tr_destino_ok"
    mock_transfer.assert_called_once()
    assert mock_transfer.call_args.kwargs["destination_account_id"] == "acct_test"
    conn = sqlite_db._connect()
    dest = conn.execute(
        "SELECT destination_account_id FROM financial_transfers WHERE contacto_id=?",
        (cid,),
    ).fetchone()[0]
    conn.close()
    assert dest == "acct_test"


@patch("core.services.financial_transfer_service.stripe_client.create_transfer")
def test_12b_cuenta_connect_incorrecta_con_transfer_id_bloquea(mock_transfer, sqlite_db):
    cid = _seed_listo_transferir(sqlite_db)
    conn = sqlite_db._connect()
    conn.execute(
        "INSERT INTO financial_transfers (contacto_id, idempotency_key, amount_cents, currency, "
        "destination_account_id, professional_codigo, stripe_transfer_id, estado) "
        "VALUES (?, ?, ?, 'eur', 'acct_malo', 'PRO', 'tr_ya_creada', 'STRIPE_CREADA')",
        (cid, f"transfer-contacto-{cid}", 44000),
    )
    conn.commit()
    conn.close()
    res = pago_service.confirmar_trabajo_y_transferir(sqlite_db, cid, "SOL")
    assert res["status"] == "error"
    assert res.get("bloqueo") == "connect"
    mock_transfer.assert_not_called()


@patch("core.services.financial_transfer_service.stripe_client.create_transfer")
def test_13_ya_transferido_sin_nueva(mock_transfer, sqlite_db):
    cid = _seed_listo_transferir(sqlite_db)
    conn = sqlite_db._connect()
    conn.execute(
        "UPDATE contactos_ruana SET estado_pago='transferido', estado_financiero='TRANSFERIDO', "
        "stripe_transfer_id='tr_done' WHERE id=?",
        (cid,),
    )
    conn.commit()
    conn.close()
    res = pago_service.confirmar_trabajo_y_transferir(sqlite_db, cid, "SOL")
    assert res["status"] == "error"
    mock_transfer.assert_not_called()


@patch("core.services.financial_transfer_service.stripe_client.create_transfer")
def test_14_servidor_reiniciado_recuperacion(mock_transfer, sqlite_db):
    cid = _seed_listo_transferir(sqlite_db)
    conn = sqlite_db._connect()
    conn.execute(
        "INSERT INTO financial_transfers (contacto_id, idempotency_key, amount_cents, currency, "
        "destination_account_id, professional_codigo, stripe_payment_intent_id, estado) "
        "VALUES (?, ?, ?, 'eur', 'acct_test', 'PRO', 'pi_test_f03', 'RECLAMADA')",
        (cid, f"transfer-contacto-{cid}", 44000),
    )
    conn.execute(
        "UPDATE contactos_ruana SET estado_financiero='TRANSFERENCIA_PENDIENTE', "
        "estado_transferencia='PENDIENTE' WHERE id=?",
        (cid,),
    )
    conn.commit()
    conn.close()
    mock_transfer.return_value = {"id": "tr_recovery"}
    res = pago_service.confirmar_trabajo_y_transferir(sqlite_db, cid, "SOL")
    assert res["status"] == "success"
    assert mock_transfer.call_count == 1
    assert _count_transfers(sqlite_db, cid) == 1


def test_15_invariante_una_transferencia_por_operacion(sqlite_db):
    cid = _seed_listo_transferir(sqlite_db)
    inv = transfer_svc.validar_invariante_una_transferencia(sqlite_db, cid)
    assert inv["invariante_ok"] is True


@patch("core.services.financial_transfer_service.stripe_client.create_transfer")
def test_16_no_marca_transferido_sin_webhook(mock_transfer, sqlite_db):
    cid = _seed_listo_transferir(sqlite_db)
    mock_transfer.return_value = {"id": "tr_no_paid"}
    pago_service.confirmar_trabajo_y_transferir(sqlite_db, cid, "SOL")
    assert fts.obtener_estado_financiero(sqlite_db, cid) != EstadoFinanciero.TRANSFERIDO
    conn = sqlite_db._connect()
    estado_pago = conn.execute(
        "SELECT estado_pago FROM contactos_ruana WHERE id=?", (cid,)
    ).fetchone()[0]
    conn.close()
    assert estado_pago == "transfer_pendiente"


@patch("core.services.financial_transfer_service._validar_precondiciones")
@patch("core.services.financial_transfer_service.schema_service.asegurar_tabla_id_serial_postgres")
def test_liberacion_asegura_serial_financial_transfers_en_postgres(mock_asegurar, mock_validar):
    """En Postgres repara id sin DEFAULT justo antes de reclamar la transferencia."""
    import threading

    db = MagicMock()
    db.backend = "postgres"
    db._lock = threading.RLock()
    conn = MagicMock()
    cursor = MagicMock()
    db._connect.return_value = conn
    conn.cursor.return_value = cursor
    mock_validar.return_value = {"status": "error", "message": "test"}

    result = transfer_svc.ejecutar_liberacion_y_transferencia(db, 72, "SOL")

    mock_asegurar.assert_called_once_with(db, cursor, "financial_transfers")
    assert result["status"] == "error"


@patch("core.services.financial_transfer_service.schema_service.asegurar_tabla_id_serial_postgres")
def test_liberacion_no_asegura_serial_en_sqlite(mock_asegurar, sqlite_db):
    transfer_svc.ejecutar_liberacion_y_transferencia(sqlite_db, 999, "")
    mock_asegurar.assert_not_called()
