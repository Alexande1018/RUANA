from datetime import datetime, timedelta, timezone
from threading import RLock
from types import SimpleNamespace

import pytest

from core import db_manager as db_module


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    return db_module.DBManager(str(tmp_path / "ruana.db"))


def _crear_contacto_basico(db):
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
    return contacto_id


def test_parse_timestamp_normalizes_postgres_timezone_aware_datetime(sqlite_db):
    parsed = sqlite_db._parse_timestamp(
        datetime(2026, 5, 29, 10, 35, 50, tzinfo=timezone.utc)
    )

    assert parsed == datetime(2026, 5, 29, 10, 35, 50)
    assert parsed.tzinfo is None


def test_estado_chat_contacto_uses_recent_timezone_aware_reference(sqlite_db):
    contacto_id = _crear_contacto_basico(sqlite_db)
    sqlite_db._chat_referencia_ts = (
        lambda cursor, contacto_id: datetime.now(timezone.utc) - timedelta(minutes=5)
    )

    estado = sqlite_db.estado_chat_contacto(contacto_id, "SOL")

    assert estado["chat_expirado"] is False
    assert estado["mensajes_restantes"] == sqlite_db.CHAT_MAX_MENSAJES_POR_USUARIO
    assert estado["chat_max_mensajes"] == 30


def test_enviar_mensaje_chat_accepts_recent_timezone_aware_reference(sqlite_db):
    contacto_id = _crear_contacto_basico(sqlite_db)
    sqlite_db._chat_referencia_ts = (
        lambda cursor, contacto_id: datetime.now(timezone.utc) - timedelta(minutes=5)
    )

    result = sqlite_db.enviar_mensaje_chat(contacto_id, "SOL", "Hola, seguimos por aqui")

    assert result["status"] == "success"


def test_chat_limit_is_30_total_messages_per_contact(sqlite_db):
    contacto_id = _crear_contacto_basico(sqlite_db)
    sqlite_db._chat_referencia_ts = (
        lambda cursor, contacto_id: datetime.now(timezone.utc) - timedelta(minutes=5)
    )

    for i in range(30):
        emisor = "SOL" if i % 2 == 0 else "PRO"
        result = sqlite_db.enviar_mensaje_chat(contacto_id, emisor, f"Mensaje {i + 1}")
        assert result["status"] == "success"

    estado = sqlite_db.estado_chat_contacto(contacto_id, "SOL")
    assert estado["mensajes_restantes"] == 0
    assert estado["chat_max_mensajes"] == 30

    blocked = sqlite_db.enviar_mensaje_chat(contacto_id, "SOL", "Mensaje extra")
    assert blocked["status"] == "error"
    assert "30 mensajes" in blocked["message"]


def test_legacy_chat_mensajes_endpoint_redirects_to_negociacion(
    client, sqlite_db, monkeypatch, session_headers
):
    """GET /api/chat_mensajes redirige a negociación guiada (ya no expone clave mensajes)."""
    from RUANA.web import app as app_module

    contacto_id = _crear_contacto_basico(sqlite_db)
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)

    resp = client.get(
        f"/api/chat_mensajes?contacto_id={contacto_id}",
        headers=session_headers("aliado", "SOL"),
    )
    data = resp.get_json()

    assert resp.status_code == 200
    assert data["status"] == "success"
    assert "mensajes" not in data
    assert "eventos" in data


def test_open_contacts_expose_negociacion_metadata(sqlite_db):
    """Contactos abiertos incluyen metadatos de negociación (sustituye prioridad por mensajes)."""
    conn = sqlite_db._connect()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO aliados (codigo, nombre) VALUES (?, ?)", ("SOL", "Solicitante"))
    cursor.execute("INSERT INTO aliados (codigo, nombre) VALUES (?, ?)", ("PRO", "Profesional"))
    cursor.execute(
        """
        INSERT INTO contactos_ruana (
            solicitante_codigo, profesional_codigo, servicio, estado, pendiente_resolucion, creado_en
        ) VALUES (?, ?, ?, 'iniciado', 1, datetime('now', '-1 hour'))
        """,
        ("SOL", "PRO", "En negociacion"),
    )
    contacto_id = cursor.lastrowid
    conn.commit()
    conn.close()

    abiertos = sqlite_db.obtener_contactos_abiertos_por_codigo("SOL")
    assert any(c["id"] == contacto_id for c in abiertos)
    target = next(c for c in abiertos if c["id"] == contacto_id)
    assert "negociacion_completa" in target


def test_api_contact_priority_keeps_negociacion_in_progress_first():
    from RUANA.web import app as app_module

    contactos = [
        {"id": 9, "estado": "iniciado", "negociacion_completa": False},
        {"id": 8, "estado": "acuerdo_alcanzado", "negociacion_completa": True},
        {"id": 7, "estado": "en_conversacion", "negociacion_completa": True},
    ]

    ordenados = app_module._priorizar_contactos_negociacion(contactos)

    # Comportamiento actual: sorted ascending por flag en_curso (0 → 1).
    assert [c["id"] for c in ordenados] == [9, 8, 7]
    assert all(
        c["id"] in (8, 7)
        for c in ordenados
        if c.get("negociacion_completa") or c.get("estado") == "acuerdo_alcanzado"
    )


def test_contratante_amount_closes_contact_and_generates_pending_support(sqlite_db):
    contacto_id = _crear_contacto_basico(sqlite_db)

    result = sqlite_db.registrar_importe_contacto(
        contacto_id, "solicitante", 100.0, usuario="SOL"
    )

    assert result["status"] == "success"
    assert result["estado"] == "trabajo_cerrado"

    contacto = sqlite_db.obtener_contacto_por_id(contacto_id)
    assert contacto["importe_final"] == 100.0
    assert contacto["importe_profesional"] is None
    assert contacto["apoyo_ruana"] == 12.0
    assert contacto["comision"] == 12.0
    assert contacto["comision_porcentaje"] == 0.12
    assert contacto["estado_pago"] == "pendiente_pago"
    assert contacto["pendiente_pago"] == 1

    pendientes = sqlite_db.listar_contactos_pago_pendiente_profesional("PRO")
    assert len(pendientes) == 1
    assert pendientes[0]["id"] == contacto_id
    assert pendientes[0]["apoyo_ruana"] == 12.0


def test_profesional_with_pending_support_cannot_receive_new_contact(sqlite_db):
    contacto_id = _crear_contacto_basico(sqlite_db)
    result = sqlite_db.registrar_importe_contacto(
        contacto_id, "solicitante", 100.0, usuario="SOL"
    )
    assert result["estado"] == "trabajo_cerrado"

    conn = sqlite_db._connect()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO aliados (codigo, nombre) VALUES (?, ?)", ("SOL2", "Otro solicitante"))
    conn.commit()
    conn.close()

    nuevo = sqlite_db.crear_contacto_ruana("SOL2", "PRO", "Otro servicio", "Encargo")

    assert nuevo["status"] == "error"
    assert "pagos pendientes" in nuevo["message"]


def test_profesional_can_dispute_pending_support_and_request_contratante_proof(sqlite_db):
    contacto_id = _crear_contacto_basico(sqlite_db)
    result = sqlite_db.registrar_importe_contacto(
        contacto_id, "solicitante", 100.0, usuario="SOL"
    )
    assert result["estado"] == "trabajo_cerrado"

    disputa = sqlite_db.impugnar_apoyo_ruana(contacto_id, "PRO", "Importe incorrecto")

    assert disputa["status"] == "success"
    assert disputa["estado"] == "importe_en_disputa"
    contacto = sqlite_db.obtener_contacto_por_id(contacto_id)
    assert contacto["estado"] == "importe_en_disputa"
    assert contacto["estado_pago"] == "no_generado"
    assert contacto["pendiente_pago"] == 0

    conflicto = sqlite_db.obtener_payment_conflict_por_trabajo(contacto_id, "SOL")
    assert conflicto is not None
    assert conflicto["estado"] == "PENDIENTE_PRUEBA"
    assert conflicto["importe_contratante"] == 100.0
    assert conflicto["importe_profesional"] == 0.0


def test_evento_sistema_casts_nullable_actor_parameter_for_postgres():
    class FakeCursor:
        def __init__(self):
            self.executed = []

        def execute(self, sql, params=None):
            self.executed.append((sql, params))

        def fetchone(self):
            return None

    db = object.__new__(db_module.DBManager)
    cursor = FakeCursor()

    db._insert_evento_sistema(cursor, "apoyo_generado", "descripcion")

    assert "CAST(? AS TEXT) IS NULL" in cursor.executed[0][0]


def test_postgres_contactos_abiertos_query_does_not_use_sqlite_datetime():
    class FakeCursor:
        def __init__(self):
            self.sql = ""
            self.params = None

        def execute(self, sql, params=None):
            self.sql = sql
            self.params = params

        def fetchall(self):
            return []

    class FakeConn:
        def __init__(self):
            self.cursor_obj = FakeCursor()
            self.row_factory = None

        def cursor(self):
            return self.cursor_obj

        def close(self):
            pass

    db = object.__new__(db_module.DBManager)
    db._lock = RLock()
    db.backend = "postgres"
    fake_conn = FakeConn()
    db._connect = lambda: fake_conn

    db.obtener_contactos_abiertos_por_codigo("SOL")

    assert "datetime(" not in fake_conn.cursor_obj.sql.lower()
