"""Advisory lock del init de esquema Postgres + cierre ordenado del pool.

Incidente 29 oct 2026 (10:37-10:43): varias instancias/workers migraban a la
vez → deadlocks (también en payment_conflicts). Y 17 avisos/24 h de pool sin
cerrar al apagar la instancia.
"""
from __future__ import annotations

import datetime as dt
import runpy
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import core.schema_lock as schema_lock
from core import postgres_compat


# ---------------------------------------------------------------- Postgres falso
class FakeServer:
    """Simula pg_try_advisory_xact_lock + la tabla marcador, compartido entre hilos."""

    def __init__(self):
        self.mu = threading.Lock()
        self.lock_owner = None
        self.marker = None  # (version, completed_at)
        self.connections = []

    def connect(self, _url):
        conn = FakeConn(self)
        with self.mu:
            self.connections.append(conn)
        return conn


class FakeConn:
    def __init__(self, server: FakeServer):
        self.server = server
        self.closed = False
        self.tx_start = None
        self.pending_marker = None

    def cursor(self):
        return FakeCursor(self)

    def _end_tx(self, commit: bool):
        with self.server.mu:
            if commit and self.pending_marker is not None:
                self.server.marker = self.pending_marker
            if self.server.lock_owner is self:
                self.server.lock_owner = None
        self.pending_marker = None
        self.tx_start = None

    def commit(self):
        self._end_tx(True)

    def rollback(self):
        self._end_tx(False)

    def close(self):
        self._end_tx(False)  # cerrar conexión = rollback = libera xact lock
        self.closed = True


class FakeCursor:
    def __init__(self, conn: FakeConn):
        self.conn = conn
        self._row = None

    def execute(self, sql, params=None):
        srv = self.conn.server
        now = dt.datetime.now(dt.timezone.utc)
        if self.conn.tx_start is None:
            self.conn.tx_start = now
        s = " ".join(sql.split())
        self._row = None
        if s.startswith("SELECT set_config"):
            self._row = (params[0],)
        elif s == "SELECT now()":
            self._row = (self.conn.tx_start,)
        elif s.startswith("SELECT pg_try_advisory_xact_lock"):
            assert params == (schema_lock.SCHEMA_INIT_LOCK_KEY,)
            with srv.mu:
                if srv.lock_owner is None or srv.lock_owner is self.conn:
                    srv.lock_owner = self.conn
                    self._row = (True,)
                else:
                    self._row = (False,)
        elif s.startswith("CREATE TABLE IF NOT EXISTS ruana_schema_init_marker"):
            pass
        elif s.startswith("SELECT 1 FROM ruana_schema_init_marker"):
            version, since = params
            m = srv.marker
            self._row = (1,) if m and m[0] == version and m[1] >= since else None
        elif s.startswith("INSERT INTO ruana_schema_init_marker"):
            self.conn.pending_marker = (params[0], dt.datetime.now(dt.timezone.utc))
        else:
            raise AssertionError(f"SQL inesperado: {s}")

    def fetchone(self):
        return self._row


def _run(server, migrate, **kw):
    kw.setdefault("timeout_s", 5)
    kw.setdefault("poll_s", 0.01)
    kw.setdefault("version", "v1")
    return schema_lock.run_with_schema_lock("postgresql://fake", migrate, connect=server.connect, **kw)


# ---------------------------------------------------------------- lock
def test_lock_se_toma_y_se_libera_y_graba_marcador():
    server = FakeServer()
    seen_owner = []

    def migrate():
        seen_owner.append(server.lock_owner is not None)
        return True

    assert _run(server, migrate) == "migrated"
    assert seen_owner == [True]  # migró CON el lock tomado
    assert server.lock_owner is None  # liberado
    assert server.marker and server.marker[0] == "v1"
    assert all(c.closed for c in server.connections)


def test_migracion_fallida_libera_lock_sin_marcador():
    server = FakeServer()
    assert _run(server, lambda: False) == "failed"
    assert server.lock_owner is None
    assert server.marker is None


def test_excepcion_en_migracion_libera_lock_y_no_reintenta():
    server = FakeServer()
    calls = []

    def migrate():
        calls.append(1)
        raise RuntimeError("boom")

    assert _run(server, migrate) == "failed"
    assert calls == [1]
    assert server.lock_owner is None
    assert all(c.closed for c in server.connections)


def test_concurrencia_solo_uno_migra_y_los_demas_omiten():
    server = FakeServer()
    active = 0
    max_active = 0
    calls = 0
    mu = threading.Lock()
    results = []

    def migrate():
        nonlocal active, max_active, calls
        with mu:
            active += 1
            calls += 1
            max_active = max(max_active, active)
        time.sleep(0.2)
        with mu:
            active -= 1
        return True

    barrier = threading.Barrier(5)

    def worker():
        barrier.wait()
        results.append(_run(server, migrate))

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)

    assert max_active == 1  # nunca dos migraciones a la vez
    assert calls == 1
    assert sorted(results) == ["migrated"] + ["skipped"] * 4
    assert server.lock_owner is None


def test_si_espera_pero_la_version_es_otra_migra_igualmente():
    server = FakeServer()
    other = FakeConn(server)
    server.lock_owner = other  # otra revisión (versión distinta) está migrando
    calls = []

    def release_later():
        time.sleep(0.1)
        with server.mu:
            server.marker = ("v-vieja", dt.datetime.now(dt.timezone.utc))
            server.lock_owner = None

    threading.Thread(target=release_later).start()
    assert _run(server, lambda: calls.append(1) or True, version="v-nueva") == "migrated"
    assert calls == [1]
    assert server.marker[0] == "v-nueva"


def test_sin_espera_migra_aunque_haya_marcador_previo():
    """Arranque en frío normal: mismo comportamiento que antes (siempre migra)."""
    server = FakeServer()
    server.marker = ("v1", dt.datetime.now(dt.timezone.utc))
    calls = []
    assert _run(server, lambda: calls.append(1) or True) == "migrated"
    assert calls == [1]


def test_timeout_de_espera_migra_sin_lock():
    server = FakeServer()
    server.lock_owner = FakeConn(server)  # nunca se libera
    calls = []
    assert _run(server, lambda: calls.append(1) or True, timeout_s=0.05) == "migrated_without_lock"
    assert calls == [1]
    assert all(c.closed for c in server.connections)


def test_sin_conexion_de_lock_migra_como_antes():
    calls = []

    def bad_connect(_url):
        raise OSError("sin red")

    res = schema_lock.run_with_schema_lock(
        "postgresql://fake", lambda: calls.append(1) or True, connect=bad_connect, version="v1"
    )
    assert res == "migrated_without_lock"
    assert calls == [1]


def test_schema_service_usa_el_lock(monkeypatch):
    from core.services import schema_service

    captured = {}

    def fake_run(url, migrate, **_kw):
        captured["url"] = url
        captured["migrate"] = migrate
        return "migrated"

    monkeypatch.setattr(schema_lock, "run_with_schema_lock", fake_run)
    db = SimpleNamespace(settings=SimpleNamespace(database_url="postgresql://x"))
    assert schema_service._init_postgres_schema(db) == "migrated"
    assert captured["url"] == "postgresql://x"


def test_schema_version_cambia_con_el_codigo(tmp_path):
    f = tmp_path / "s.py"
    f.write_text("a")
    v1 = schema_lock.schema_version([f])
    f.write_text("b")
    assert schema_lock.schema_version([f]) != v1
    assert len(schema_lock.schema_version()) == 16


# ---------------------------------------------------------------- pool
class _FakePool:
    def __init__(self):
        self.closed = False
        self.close_calls = 0

    def close(self, timeout=None):
        self.close_calls += 1
        self.closed = True


def test_close_pool_es_idempotente(monkeypatch):
    p1, p2 = _FakePool(), _FakePool()
    monkeypatch.setattr(postgres_compat, "_pools", {"a": p1, "b": p2})
    postgres_compat.close_pool()
    postgres_compat.close_pool()
    assert p1.close_calls == 1 and p2.close_calls == 1
    assert postgres_compat._pools == {}


def test_close_pool_no_revienta_si_un_pool_falla(monkeypatch):
    class Boom(_FakePool):
        def close(self, timeout=None):
            raise RuntimeError("x")

    good = _FakePool()
    monkeypatch.setattr(postgres_compat, "_pools", {"a": Boom(), "b": good})
    postgres_compat.close_pool()
    assert good.close_calls == 1


def test_close_pool_registrado_en_atexit():
    import atexit

    unregistered = atexit.unregister(postgres_compat.close_pool)  # devuelve None siempre
    assert unregistered is None
    atexit.register(postgres_compat.close_pool)  # lo dejamos como estaba
    src = Path(postgres_compat.__file__).read_text(encoding="utf-8")
    assert "atexit.register(close_pool)" in src


def test_gunicorn_worker_exit_cierra_pool(monkeypatch):
    calls = []
    monkeypatch.setattr(postgres_compat, "close_pool", lambda: calls.append(1))
    conf = Path(__file__).resolve().parents[1] / "gunicorn.conf.py"
    ns = runpy.run_path(str(conf))
    ns["worker_exit"](None, None)
    assert calls == [1]


def test_get_db_un_solo_init_con_hilos(monkeypatch):
    from core import db_manager

    created = []

    class SlowDB:
        def __init__(self):
            time.sleep(0.1)
            created.append(self)

    monkeypatch.setattr(db_manager, "_db_instance", None)
    monkeypatch.setattr(db_manager, "DBManager", SlowDB)
    out = []
    threads = [threading.Thread(target=lambda: out.append(db_manager.get_db())) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(5)
    assert len(created) == 1
    assert all(o is created[0] for o in out)
