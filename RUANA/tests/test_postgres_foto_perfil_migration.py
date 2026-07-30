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


def test_init_postgres_schema_runs_foto_perfil_migration(monkeypatch):
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
    monkeypatch.setattr(db, "_migrar_negociacion_guiada", lambda conn, cursor: calls.append("migrar_negociacion_guiada"))

    db._init_postgres_schema()

    assert "migrar_foto_perfil" in calls
    assert "migrar_negociacion_guiada" in calls
