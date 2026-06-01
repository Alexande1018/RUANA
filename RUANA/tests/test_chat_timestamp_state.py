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


def test_apoyo_ruana_default_is_12_percent_when_closing_contact(sqlite_db):
    contacto_id = _crear_contacto_basico(sqlite_db)

    first = sqlite_db.registrar_importe_contacto(
        contacto_id, "solicitante", 100.0, usuario="SOL"
    )
    second = sqlite_db.registrar_importe_contacto(
        contacto_id, "profesional", 100.0, usuario="PRO"
    )

    assert first["status"] == "success"
    assert second["status"] == "success"
    assert second["estado"] == "trabajo_cerrado"

    contacto = sqlite_db.obtener_contacto_por_id(contacto_id)
    assert contacto["apoyo_ruana"] == 12.0
    assert contacto["comision"] == 12.0
    assert contacto["comision_porcentaje"] == 0.12


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
