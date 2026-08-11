from types import SimpleNamespace
from threading import RLock

import pytest

from core import db_manager as db_module
from core.postgres_compat import CompatRow


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    return db_module.DBManager(str(tmp_path / "ruana.db"))


def _crear_contacto_cerrado_con_apoyo(db, importe=100.0):
    conn = db._connect()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO aliados (codigo, nombre) VALUES (?, ?)", ("SOL", "Solicitante"))
    cursor.execute("INSERT INTO aliados (codigo, nombre) VALUES (?, ?)", ("PRO", "Profesional"))
    cursor.execute(
        """
        INSERT INTO contactos_ruana (
            solicitante_codigo, profesional_codigo, servicio, estado, pendiente_resolucion
        ) VALUES (?, ?, ?, 'iniciado', 1)
        """,
        ("SOL", "PRO", "Servicio de prueba"),
    )
    contacto_id = cursor.lastrowid
    conn.commit()
    conn.close()

    result = db.registrar_importe_contacto(contacto_id, "solicitante", importe, usuario="SOL")
    assert result["status"] == "success"
    assert result["estado"] == "trabajo_cerrado"
    return contacto_id


def _notificaciones(db, codigo):
    return db.listar_notificaciones_aliado(codigo, limite=50)


def _por_tipo(notificaciones, tipo):
    return [n for n in notificaciones if n["tipo"] == tipo]


def test_impugnar_apoyo_limpia_alerta_de_pago_y_desbloquea_profesional(sqlite_db):
    contacto_id = _crear_contacto_cerrado_con_apoyo(sqlite_db)

    antes = _notificaciones(sqlite_db, "PRO")
    assert _por_tipo(antes, "apoyo_ruana")[0]["leida"] == 0
    assert sqlite_db.tiene_pagos_ruana_pendientes("PRO") is True

    disputa = sqlite_db.impugnar_apoyo_ruana(contacto_id, "PRO", "Importe incorrecto")

    assert disputa["status"] == "success"
    assert sqlite_db.tiene_pagos_ruana_pendientes("PRO") is False
    despues_prof = _notificaciones(sqlite_db, "PRO")
    assert _por_tipo(despues_prof, "apoyo_ruana")[0]["leida"] == 1


def test_subir_comprobante_apoyo_ruana_pasa_a_en_revision(sqlite_db):
    """Regresión: dict(row) sin row_factory rompía la subida con TypeError."""
    contacto_id = _crear_contacto_cerrado_con_apoyo(sqlite_db)

    result = sqlite_db.subir_comprobante_apoyo_ruana(
        contacto_id,
        "PRO",
        "/static/uploads/pagos_ruana/qa-comprobante.png",
        "Comprobante QA",
    )

    assert result["status"] == "success", result
    assert result["estado_pago"] == "en_revision"
    en_revision = sqlite_db.listar_contactos_pagos_en_revision()
    assert any(int(c["id"]) == int(contacto_id) for c in en_revision)


def test_zero_amount_support_is_not_listed_as_pending_payment(sqlite_db):
    conn = sqlite_db._connect()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO aliados (codigo, nombre) VALUES (?, ?)", ("SOL", "Solicitante"))
    cursor.execute("INSERT INTO aliados (codigo, nombre) VALUES (?, ?)", ("PRO", "Profesional"))
    cursor.execute(
        """
        INSERT INTO contactos_ruana (
            solicitante_codigo, profesional_codigo, servicio, estado, pendiente_resolucion,
            importe_final, apoyo_ruana, estado_pago, pendiente_pago
        ) VALUES (?, ?, ?, 'trabajo_cerrado', 0, 0, 0, 'pendiente_pago', 1)
        """,
        ("SOL", "PRO", "Servicio legado con importe cero"),
    )
    conn.commit()
    conn.close()

    assert sqlite_db.tiene_pagos_ruana_pendientes("PRO") is False
    assert sqlite_db.listar_contactos_pago_pendiente_profesional("PRO") == []
    assert sqlite_db.listar_contactos_pagos_apoyo() == []


def test_subir_prueba_conflicto_sustituye_peticion_por_estado_en_revision(sqlite_db):
    contacto_id = _crear_contacto_cerrado_con_apoyo(sqlite_db)
    assert sqlite_db.impugnar_apoyo_ruana(contacto_id, "PRO", "Importe incorrecto")["status"] == "success"
    conflicto = sqlite_db.obtener_payment_conflict_por_trabajo(contacto_id, "SOL")

    antes_sol = _notificaciones(sqlite_db, "SOL")
    assert _por_tipo(antes_sol, "importe_impugnado")[0]["leida"] == 0

    subida = sqlite_db.subir_prueba_conflicto(conflicto["id"], "SOL", "https://storage.example/prueba.pdf")

    assert subida["status"] == "success"
    despues_sol = _notificaciones(sqlite_db, "SOL")
    assert _por_tipo(despues_sol, "importe_impugnado")[0]["leida"] == 1
    espera = _por_tipo(despues_sol, "prueba_conflicto_en_revision")
    assert len(espera) == 1
    assert espera[0]["leida"] == 0
    assert "pendiente de revision" in espera[0]["mensaje"].lower()


def test_admin_resuelve_disputa_limpia_alertas_contratante_y_reactiva_cobro(sqlite_db):
    contacto_id = _crear_contacto_cerrado_con_apoyo(sqlite_db)
    assert sqlite_db.impugnar_apoyo_ruana(contacto_id, "PRO", "Importe incorrecto")["status"] == "success"
    conflicto = sqlite_db.obtener_payment_conflict_por_trabajo(contacto_id, "SOL")
    assert sqlite_db.subir_prueba_conflicto(conflicto["id"], "SOL", "https://storage.example/prueba.pdf")["status"] == "success"

    resuelto = sqlite_db.resolver_payment_conflict_admin(
        conflicto["id"], "contratante", "La factura aportada valida el importe.", "ADMIN001"
    )

    assert resuelto["status"] == "success"
    contacto = sqlite_db.obtener_contacto_por_id(contacto_id)
    assert contacto["estado"] == "trabajo_cerrado"
    assert contacto["estado_pago"] == "pendiente_pago"
    assert contacto["pendiente_pago"] == 1

    notifs_sol = _notificaciones(sqlite_db, "SOL")
    assert all(n["leida"] == 1 for n in _por_tipo(notifs_sol, "importe_impugnado"))
    assert all(n["leida"] == 1 for n in _por_tipo(notifs_sol, "prueba_conflicto_en_revision"))

    notifs_prof = _notificaciones(sqlite_db, "PRO")
    apoyos = _por_tipo(notifs_prof, "apoyo_ruana")
    assert len(apoyos) == 2
    assert sum(1 for n in apoyos if n["leida"] == 0) == 1
    assert sqlite_db.tiene_pagos_ruana_pendientes("PRO") is True


def test_admin_conflicts_list_only_returns_actionable_open_conflicts(sqlite_db):
    contacto_id = _crear_contacto_cerrado_con_apoyo(sqlite_db)
    assert sqlite_db.impugnar_apoyo_ruana(contacto_id, "PRO", "Importe incorrecto")["status"] == "success"
    conflicto = sqlite_db.obtener_payment_conflict_por_trabajo(contacto_id, "SOL")

    abiertos = sqlite_db.listar_payment_conflicts_admin()
    assert [c["id"] for c in abiertos] == [conflicto["id"]]

    assert sqlite_db.resolver_payment_conflict_admin(
        conflicto["id"], "contratante", "Resolucion inicial.", "ADMIN001"
    )["status"] == "success"

    assert sqlite_db.listar_payment_conflicts_admin() == []
    repetido = sqlite_db.resolver_payment_conflict_admin(
        conflicto["id"], "contratante", "No debe reabrirse.", "ADMIN001"
    )
    assert repetido["status"] == "error"
    assert "ya esta resuelto" in repetido["message"].lower()


def test_admin_rejects_contractor_proof_closes_dispute_without_zero_payment(sqlite_db):
    contacto_id = _crear_contacto_cerrado_con_apoyo(sqlite_db)
    assert sqlite_db.impugnar_apoyo_ruana(contacto_id, "PRO", "Importe incorrecto")["status"] == "success"
    conflicto = sqlite_db.obtener_payment_conflict_por_trabajo(contacto_id, "SOL")

    rechazado = sqlite_db.resolver_payment_conflict_admin(
        conflicto["id"], "rechazado", "La documentacion no acredita el importe.", "ADMIN001"
    )

    assert rechazado["status"] == "success"
    assert rechazado["estado"] == "RECHAZADO"
    contacto = sqlite_db.obtener_contacto_por_id(contacto_id)
    assert contacto["estado"] == "trabajo_cerrado"
    assert contacto["importe_final"] == 0.0
    assert contacto["estado_pago"] == "no_generado"
    assert contacto["pendiente_pago"] == 0
    assert sqlite_db.listar_payment_conflicts_admin() == []
    assert sqlite_db.tiene_pagos_ruana_pendientes("PRO") is False


def test_admin_payment_validation_accepts_postgres_compat_rows():
    class FakeCursor:
        def __init__(self):
            self.description = [
                ("id",), ("estado",), ("importe_final",), ("estado_pago",),
                ("pendiente_pago",), ("profesional_codigo",),
            ]
            self.executed = []

        def execute(self, sql, params=None):
            self.executed.append((sql, params))

        def fetchone(self):
            return CompatRow({
                "id": 10,
                "estado": "trabajo_cerrado",
                "importe_final": 350.0,
                "estado_pago": "pendiente_pago",
                "pendiente_pago": 1,
                "profesional_codigo": "PRO",
            }, [c[0] for c in self.description])

    class FakeConn:
        def __init__(self):
            self.cursor_obj = FakeCursor()
            self.committed = False

        def cursor(self):
            return self.cursor_obj

        def commit(self):
            self.committed = True

        def close(self):
            pass

    fake_conn = FakeConn()
    db = object.__new__(db_module.DBManager)
    db._lock = RLock()
    db._connect = lambda: fake_conn
    db._audit_log = lambda *args, **kwargs: None
    db._marcar_notificaciones_contacto_leidas = lambda *args, **kwargs: 0

    result = db.actualizar_estado_pago_contacto(10, "en_revision", "ADMIN001")

    assert result["status"] == "success"
    assert result["estado_pago"] == "en_revision"
    assert fake_conn.committed is True
