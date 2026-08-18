"""Tests máquina de estados financiera — FASE 01."""

from __future__ import annotations

import json
import threading
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from core import db_manager as db_module
from core.financial.estados import EstadoFinanciero
from core.financial.modelo import InvarianteFinancieraError, ModeloFinanciero
from core.financial.state_machine import FinancialStateMachine, TransicionInvalidaError
from core.services import financial_transaction_service as fts
from core.services import pago_service


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
    return db_module.DBManager(str(tmp_path / "ruana_financial.db"))


def _seed_contacto_financiero(db, importe=1000.0, estado_financiero="PAGO_NO_INICIADO"):
    conn = db._connect()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO aliados (codigo, nombre, email) VALUES (?, ?, ?)", ("SOL", "Sol", "s@test.com"))
    cursor.execute(
        "INSERT INTO aliados (codigo, nombre, email, stripe_account_id, stripe_charges_enabled) "
        "VALUES (?, ?, ?, ?, ?)",
        ("PRO", "Pro", "p@test.com", "acct_test", 1),
    )
    apoyo = round(importe * 0.12, 2)
    neto = round(importe - apoyo, 2)
    cursor.execute(
        """
        INSERT INTO contactos_ruana (
            solicitante_codigo, profesional_codigo, servicio, estado,
            importe_acordado, importe_final, apoyo_ruana, comision,
            comision_porcentaje, importe_neto_profesional, modo_pago,
            estado_financiero, estado_transferencia
        ) VALUES (?, ?, ?, 'pendiente_de_pago', ?, ?, ?, ?, 0.12, ?, 'stripe', ?, 'NO_APLICA')
        """,
        ("SOL", "PRO", "Servicio", importe, importe, apoyo, apoyo, neto, estado_financiero),
    )
    cid = cursor.lastrowid
    conn.commit()
    conn.close()
    return cid


def _set_estado(db, contacto_id, estado):
    conn = db._connect()
    conn.execute(
        "UPDATE contactos_ruana SET estado_financiero = ? WHERE id = ?",
        (estado, contacto_id),
    )
    conn.commit()
    conn.close()


# --- TEST 1-3: transiciones básicas ---

def test_01_pago_no_iniciado_a_pendiente(sqlite_db):
    cid = _seed_contacto_financiero(sqlite_db, estado_financiero="PAGO_NO_INICIADO")
    res = fts.transicionar(sqlite_db, cid, EstadoFinanciero.PAGO_PENDIENTE)
    assert res["status"] == "success"
    assert fts.obtener_estado_financiero(sqlite_db, cid) == EstadoFinanciero.PAGO_PENDIENTE


def test_02_pendiente_a_confirmado(sqlite_db):
    cid = _seed_contacto_financiero(sqlite_db, estado_financiero="PAGO_PENDIENTE")
    res = fts.transicionar(sqlite_db, cid, EstadoFinanciero.PAGO_CONFIRMADO)
    assert res["status"] == "success"


def test_03_pendiente_a_transferido_falla(sqlite_db):
    cid = _seed_contacto_financiero(sqlite_db, estado_financiero="PAGO_PENDIENTE")
    res = fts.transicionar(sqlite_db, cid, EstadoFinanciero.TRANSFERIDO)
    assert res["status"] == "error"


# --- TEST 4-5: conflictos ---

def test_04_esperando_confirmacion_a_conflicto(sqlite_db):
    cid = _seed_contacto_financiero(sqlite_db, estado_financiero="ESPERANDO_CONFIRMACION")
    res = fts.transicionar(sqlite_db, cid, EstadoFinanciero.CONFLICTO_ABIERTO, motivo="disputa")
    assert res["status"] == "success"


def test_05_conflicto_a_transferido_falla(sqlite_db):
    cid = _seed_contacto_financiero(sqlite_db, estado_financiero="CONFLICTO_ABIERTO")
    res = fts.transicionar(sqlite_db, cid, EstadoFinanciero.TRANSFERIDO)
    assert res["status"] == "error"


# --- TEST 6-9: transferencias ---

def test_06_liberacion_a_transferencia_pendiente(sqlite_db):
    cid = _seed_contacto_financiero(sqlite_db, estado_financiero="LIBERACION_AUTORIZADA")
    res = fts.transicionar(sqlite_db, cid, EstadoFinanciero.TRANSFERENCIA_PENDIENTE)
    assert res["status"] == "success"


def test_07_transferencia_pendiente_a_transferido_falla(sqlite_db):
    cid = _seed_contacto_financiero(sqlite_db, estado_financiero="TRANSFERENCIA_PENDIENTE")
    res = fts.transicionar(sqlite_db, cid, EstadoFinanciero.TRANSFERIDO)
    assert res["status"] == "error"


def test_08_transferencia_enviada_a_transferido(sqlite_db):
    cid = _seed_contacto_financiero(sqlite_db, estado_financiero="TRANSFERENCIA_ENVIADA")
    res = fts.transicionar(sqlite_db, cid, EstadoFinanciero.TRANSFERIDO)
    assert res["status"] == "success"


def test_09_transferido_a_pendiente_falla(sqlite_db):
    cid = _seed_contacto_financiero(sqlite_db, estado_financiero="TRANSFERIDO")
    res = fts.transicionar(sqlite_db, cid, EstadoFinanciero.TRANSFERENCIA_PENDIENTE)
    assert res["status"] == "error"


# --- TEST 10: concurrencia doble liberación ---

def test_10_doble_liberacion_solo_una_gana(sqlite_db):
    cid = _seed_contacto_financiero(sqlite_db, estado_financiero="ESPERANDO_CONFIRMACION")
    resultados = []
    barrera = threading.Barrier(2)

    def intentar():
        barrera.wait()
        resultados.append(fts.intentar_autorizar_liberacion(sqlite_db, cid, "SOL"))

    t1 = threading.Thread(target=intentar)
    t2 = threading.Thread(target=intentar)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    exitos = [r for r in resultados if r.get("status") == "success"]
    fallos = [r for r in resultados if r.get("status") == "error"]
    assert len(exitos) == 1
    assert len(fallos) == 1
    assert fts.obtener_estado_financiero(sqlite_db, cid) == EstadoFinanciero.LIBERACION_AUTORIZADA


# --- TEST 11-12: invariantes importes ---

def test_11_importe_negativo_falla():
    with pytest.raises(InvarianteFinancieraError, match="INVARIANTE 1"):
        ModeloFinanciero(
            contacto_id=1, importe_bruto=-10, comision_ruana=0, importe_profesional=0
        )


def test_12_comision_mas_neto_distinto_bruto_falla():
    with pytest.raises(InvarianteFinancieraError, match="INVARIANTE 4"):
        ModeloFinanciero(
            contacto_id=1, importe_bruto=1000, comision_ruana=120, importe_profesional=800
        )


# --- TEST 13-14: bloqueos transferencia ---

def test_13_conflicto_abierto_bloquea_liberacion(sqlite_db):
    cid = _seed_contacto_financiero(sqlite_db, estado_financiero="ESPERANDO_CONFIRMACION")
    conn = sqlite_db._connect()
    conn.execute(
        """
        INSERT INTO payment_conflicts (
            trabajo_id, contratante_id, profesional_id,
            importe_contratante, importe_profesional, estado
        ) VALUES (?, 1, 2, 1000, 880, 'PENDIENTE_PRUEBA')
        """,
        (cid,),
    )
    conn.commit()
    conn.close()
    res = fts.intentar_autorizar_liberacion(sqlite_db, cid, "SOL")
    assert res["status"] == "error"
    assert "conflicto" in res["message"].lower()


def test_14_ya_transferido_no_segunda_transferencia(sqlite_db):
    cid = _seed_contacto_financiero(sqlite_db, estado_financiero="TRANSFERIDO")
    conn = sqlite_db._connect()
    conn.execute(
        "UPDATE contactos_ruana SET stripe_transfer_id = 'tr_existing' WHERE id = ?",
        (cid,),
    )
    conn.commit()
    conn.close()
    res = fts.transicionar(sqlite_db, cid, EstadoFinanciero.TRANSFERENCIA_PENDIENTE)
    assert res["status"] == "error"


# --- TEST 15: importe inmutable tras pago confirmado ---

def test_15_no_modificar_importe_tras_pago_confirmado(sqlite_db):
    cid = _seed_contacto_financiero(sqlite_db, estado_financiero="PAGO_CONFIRMADO")
    conn = sqlite_db._connect()
    conn.execute(
        "UPDATE contactos_ruana SET stripe_payment_intent_id = 'pi_locked' WHERE id = ?",
        (cid,),
    )
    conn.commit()
    conn.close()
    val = fts.validar_modelo_contacto(sqlite_db, cid)
    assert val["status"] == "success"
    assert val["puede_modificar_importe"] is False


# --- Auditoría ---

def test_auditoria_registra_transicion(sqlite_db):
    cid = _seed_contacto_financiero(sqlite_db, estado_financiero="PAGO_NO_INICIADO")
    fts.transicionar(
        sqlite_db, cid, EstadoFinanciero.PAGO_PENDIENTE,
        actor_tipo="sistema", motivo="test",
    )
    conn = sqlite_db._connect()
    row = conn.execute(
        "SELECT accion, detalles FROM audit_log WHERE entidad_id = ? AND accion = 'financiero_transicion'",
        (cid,),
    ).fetchone()
    conn.close()
    assert row is not None
    detalles = json.loads(row[1])
    assert detalles["estado_anterior"] == "PAGO_NO_INICIADO"
    assert detalles["estado_nuevo"] == "PAGO_PENDIENTE"


# --- Integración Stripe existente no rota ---

@patch("core.services.financial_transfer_service.stripe_client.create_transfer")
def test_stripe_confirmar_trabajo_sincroniza_estados(mock_transfer, sqlite_db):
    conn = sqlite_db._connect()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO aliados (codigo, nombre, email) VALUES (?, ?, ?)", ("SOL", "Sol", "s@test.com"))
    cursor.execute(
        "INSERT INTO aliados (codigo, nombre, email, stripe_account_id, stripe_charges_enabled) "
        "VALUES (?, ?, ?, ?, ?)",
        ("PRO", "Pro", "p@test.com", "acct_test", 1),
    )
    cursor.execute(
        """
        INSERT INTO contactos_ruana (
            solicitante_codigo, profesional_codigo, servicio, estado, pendiente_resolucion,
            importe_acordado, modo_pago, estado_pago, estado_financiero, estado_transferencia,
            importe_neto_profesional, stripe_payment_intent_id
        ) VALUES (?, ?, ?, 'trabajo_en_progreso', 0, 500, 'stripe', 'cobro_confirmado',
                  'ESPERANDO_CONFIRMACION', 'RETENIDO', 440, 'pi_test')
        """,
        ("SOL", "PRO", "Servicio"),
    )
    cid = cursor.lastrowid
    conn.commit()
    conn.close()

    mock_transfer.return_value = {"id": "tr_test_fin"}
    res = pago_service.confirmar_trabajo_y_transferir(sqlite_db, cid, "SOL")
    assert res["status"] == "success"
    assert fts.obtener_estado_financiero(sqlite_db, cid) == EstadoFinanciero.TRANSFERENCIA_ENVIADA


def test_state_machine_pure_transiciones_invalidas():
    sm = FinancialStateMachine()
    with pytest.raises(TransicionInvalidaError):
        sm.validar_transicion(EstadoFinanciero.PAGO_PENDIENTE, EstadoFinanciero.TRANSFERIDO)
