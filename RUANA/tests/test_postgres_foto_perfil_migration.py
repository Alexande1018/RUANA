import sqlite3
from pathlib import Path

import pytest

from RUANA.core.db_manager import ALIADO_FOTO_PERFIL_COLUMN, DBManager


def test_migrar_aliados_foto_perfil_adds_column_on_sqlite(tmp_path):
    db_path = tmp_path / "test.db"
    db = DBManager(db_path=str(db_path))

    with sqlite3.connect(db_path) as conn:
        cols = [row[1] for row in conn.execute("PRAGMA table_info(aliados)").fetchall()]

    assert ALIADO_FOTO_PERFIL_COLUMN in cols


def test_init_postgres_schema_runs_pin_migration_before_foto_perfil(monkeypatch):
    calls = []

    class FakeCursor:
        def execute(self, sql, params=None):
            calls.append(sql.strip())

        def fetchall(self):
            if calls and calls[-1] == "PRAGMA table_info(aliados)":
                return []
            return []

    class FakeConn:
        def cursor(self):
            return FakeCursor()

        def commit(self):
            pass

        def close(self):
            pass

    db = DBManager.__new__(DBManager)
    db.settings = type("S", (), {"postgres_configured": True, "database_url": "postgresql://example"})()
    db.backend = "postgres"
    db._lock = __import__("threading").RLock()
    db.db_path = str(Path("/tmp/fake.db"))

    monkeypatch.setattr(db, "_connect", lambda: FakeConn())
    monkeypatch.setattr(db, "_migrar_aliados_foto_perfil", lambda conn, cursor: calls.append("migrar_foto_perfil"))
    monkeypatch.setattr(db, "_migrar_aliados_pin_personal", lambda conn, cursor: calls.append("migrar_pin_personal"))
    monkeypatch.setattr(db, "_migrar_negociacion_guiada", lambda conn, cursor: calls.append("migrar_negociacion_guiada"))

    db._init_postgres_schema()

    assert calls.index("migrar_pin_personal") < calls.index("migrar_foto_perfil")
    assert "migrar_negociacion_guiada" in calls


def test_migrar_aliados_foto_perfil_postgres_adds_column(monkeypatch):
    from core.services import schema_service

    calls = []

    class FakeCursor:
        def execute(self, sql, params=None):
            calls.append(str(sql).strip())

    db = DBManager.__new__(DBManager)
    db.backend = "postgres"

    schema_service._migrar_aliados_foto_perfil(db, None, FakeCursor())

    assert f"ADD COLUMN IF NOT EXISTS {ALIADO_FOTO_PERFIL_COLUMN}" in calls[0]


def test_ensure_aliados_pin_schema_postgres_runs_migration(monkeypatch):
    from core.services import schema_service

    calls = []

    class FakeCursor:
        def execute(self, sql, params=None):
            calls.append(str(sql).strip())

        def fetchall(self):
            return []

        def fetchone(self):
            return None

    class FakeConn:
        def cursor(self):
            return FakeCursor()

        def commit(self):
            calls.append("commit")

        def rollback(self):
            calls.append("rollback")

        def close(self):
            pass

    db = DBManager.__new__(DBManager)
    db.backend = "postgres"
    db._lock = __import__("threading").RLock()
    monkeypatch.setattr(db, "_connect", lambda: FakeConn())

    schema_service.ensure_aliados_pin_schema(db)

    joined = "\n".join(calls)
    assert "ADD COLUMN IF NOT EXISTS pin_hash" in joined
    assert "commit" in calls


def test_ensure_aliados_pin_schema_noop_on_sqlite(tmp_path):
    from core.services import schema_service

    db = DBManager(str(tmp_path / "ensure_pin.db"))
    assert db.backend == "sqlite"
    schema_service.ensure_aliados_pin_schema(db)


def test_migrar_aliados_pin_personal_postgres_adds_columns(monkeypatch):
    from core.services import schema_service

    calls = []

    class FakeCursor:
        def execute(self, sql, params=None):
            calls.append(str(sql).strip())

        def fetchall(self):
            return []

        def fetchone(self):
            return None

    class FakeConn:
        def cursor(self):
            return FakeCursor()

    db = DBManager.__new__(DBManager)
    db.backend = "postgres"
    db._lock = __import__("threading").RLock()

    schema_service._migrar_aliados_pin_personal(db, FakeConn(), FakeCursor())

    joined = "\n".join(calls)
    assert "ADD COLUMN IF NOT EXISTS pin_hash" in joined
    assert "ADD COLUMN IF NOT EXISTS pin_intentos_fallidos" in joined
    assert "ADD COLUMN IF NOT EXISTS pin_bloqueado_hasta" in joined
    assert "CREATE TABLE IF NOT EXISTS aliado_recuperacion_acceso" in joined
