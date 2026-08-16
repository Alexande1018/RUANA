"""Tests de optimizaciones de rendimiento (pool Postgres, dashboard admin, caché catálogo)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from core.db_manager import DBManager
from core.postgres_compat import PostgresCompatConnection, get_connection_pool
from core.services import admin_service, catalogo_service


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    db_path = tmp_path / "perf_test.db"
    monkeypatch.setattr(
        "core.settings.get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    return DBManager(str(db_path))


def test_postgres_compat_connection_returns_conn_to_pool_on_close():
    pool = MagicMock()
    raw_conn = MagicMock()
    pool.getconn.return_value = raw_conn

    conn = PostgresCompatConnection(raw_conn=raw_conn, pool=pool)
    conn.close()

    raw_conn.rollback.assert_called_once()
    pool.putconn.assert_called_once_with(raw_conn)


def test_get_connection_pool_reuses_same_instance():
    with patch("core.postgres_compat.ConnectionPool") as mock_pool_cls:
        instance = MagicMock()
        mock_pool_cls.return_value = instance

        import core.postgres_compat as pg_mod

        pg_mod._pools.clear()

        p1 = get_connection_pool("postgresql://user:pass@localhost/testdb")
        p2 = get_connection_pool("postgresql://user:pass@localhost/testdb")

        assert p1 is p2
        mock_pool_cls.assert_called_once()
        instance.open.assert_called_once_with(wait=True)


def test_obtener_movimiento_24h_por_hora_agrega_solicitudes_por_hora(sqlite_db):
    conn = sqlite_db._connect()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO grupos (nombre, codigo_postal, estado)
        VALUES ('Grupo Test', '28001', 'activo')
        """
    )
    grupo_id = cursor.lastrowid
    cursor.execute(
        """
        INSERT INTO solicitudes (
            grupo_id, solicitante_codigo, solicitante_nombre, oficio, descripcion,
            estado, created_at
        )
        VALUES (?, 'ALI-001', 'Aliado 1', 'Fontanero', 'Test', 'pendiente', datetime('now', '-2 hours'))
        """,
        (grupo_id,),
    )
    cursor.execute(
        """
        INSERT INTO solicitudes (
            grupo_id, solicitante_codigo, solicitante_nombre, oficio, descripcion,
            estado, created_at
        )
        VALUES (?, 'ALI-002', 'Aliado 2', 'Fontanero', 'Test', 'atendida', datetime('now', '-2 hours'))
        """,
        (grupo_id,),
    )
    conn.commit()
    conn.close()

    resultado = admin_service.obtener_movimiento_24h_por_hora(sqlite_db)

    assert len(resultado) == 24
    total_nuevas = sum(v["nuevas"] for v in resultado.values())
    total_atendidas = sum(v["atendidas"] for v in resultado.values())
    total_sin_respuesta = sum(v["sin_respuesta"] for v in resultado.values())
    assert total_nuevas >= 2
    assert total_atendidas >= 1
    assert total_sin_respuesta >= 1


def test_catalogo_oficios_cache_evita_relectura(monkeypatch, sqlite_db):
    catalogo_service._catalogo_oficios_cache = None
    calls = {"n": 0}
    real_open = open

    def counting_open(file, *args, **kwargs):
        calls["n"] += 1
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr("builtins.open", counting_open)

    first = catalogo_service.get_catalogo_oficios_ruana(sqlite_db)
    second = catalogo_service.get_catalogo_oficios_ruana(sqlite_db)

    assert first == second
    assert len(first) > 0
    assert calls["n"] == 1


def test_db_manager_postgres_usa_pool(monkeypatch, tmp_path):
    mock_pool = MagicMock()
    mock_conn = MagicMock()
    mock_pool.getconn.return_value = mock_conn

    monkeypatch.setattr(
        "core.db_manager.get_settings",
        lambda: SimpleNamespace(
            postgres_configured=True,
            database_url="postgresql://user:pass@localhost/testdb",
        ),
    )
    monkeypatch.setattr(
        "core.services.schema_service._init_postgres_schema",
        lambda db: None,
    )
    monkeypatch.setattr(
        "core.db_manager.get_connection_pool",
        lambda url, **kwargs: mock_pool,
    )

    db = DBManager(str(tmp_path / "unused.db"))
    conn = db._connect()
    conn.close()

    mock_pool.getconn.assert_called_once()
    mock_pool.putconn.assert_called_once_with(mock_conn)
