"""Contratos del script de reset de datos de prueba (sin tocar Postgres real)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "reset_datos_prueba.py"


def _load_mod():
    spec = importlib.util.spec_from_file_location("reset_datos_prueba", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def reset_mod():
    return _load_mod()


class FakeCursor:
    def __init__(self, counts, fk_rows=(), cascade_rows=()):
        self.counts = dict(counts)
        self.fk_rows = list(fk_rows)
        self.cascade_rows = list(cascade_rows)
        self.executed = []
        self._result = []

    def execute(self, sql, params=None):
        self.executed.append(sql.strip())
        text = " ".join(sql.split())
        if "FROM pg_constraint" in text and "ruana_metodos_pago_manual" in text:
            self._result = list(self.fk_rows)
        elif "FROM pg_constraint" in text:
            self._result = list(self.cascade_rows)
        elif text.upper().startswith("TRUNCATE"):
            for table in ("aliados", "grupos", "cp_estado", "contactos_ruana"):
                if table in self.counts:
                    self.counts[table] = 0
            self._result = []
        elif "COUNT(*)" in text.upper():
            table = text.rsplit(" ", 1)[-1]
            self._result = [(self.counts.get(table, 0),)]
        else:
            self._result = []

    def fetchall(self):
        return list(self._result)

    def fetchone(self):
        return self._result[0] if self._result else (0,)


def test_default_mode_is_dry_run(reset_mod):
    args = reset_mod.parse_args([])
    assert args.dry_run is True
    assert args.execute is False


def test_execute_without_confirm_exits(reset_mod):
    assert reset_mod.main(["--execute"]) == 2


def test_execute_wrong_confirm_exits(reset_mod):
    assert reset_mod.main(["--execute", "--confirm", "si"]) == 2


def test_execute_requires_prior_dry_run(reset_mod, tmp_path, monkeypatch):
    url = "postgresql://u:p@localhost:5432/ruana"
    monkeypatch.setattr(reset_mod, "load_database_url", lambda: url)
    monkeypatch.setattr(reset_mod, "dry_run_flag_path", lambda _url: tmp_path / "missing.flag")
    rc = reset_mod.main(["--execute", "--confirm", reset_mod.CONFIRM_PHRASE])
    assert rc == 2


def test_fk_to_aliados_aborts(reset_mod):
    hits = reset_mod.fk_references_aliados(
        [("ruana_metodos_pago_manual_aliado_codigo_fkey", "aliados")]
    )
    assert hits
    with pytest.raises(reset_mod.ResetAborted, match="ruana_metodos_pago_manual"):
        reset_mod.abort_if_metodos_pago_fk_aliados(hits)


def test_fk_to_other_table_is_ok(reset_mod):
    rows = [("algo_fkey", "public.otra")]
    reset_mod.abort_if_metodos_pago_fk_aliados(rows)
    assert reset_mod.fk_references_aliados(rows) == []


def test_truncate_sql_is_exact_and_has_no_delete_drop(reset_mod):
    sql = reset_mod.TRUNCATE_SQL
    assert sql == "TRUNCATE aliados, grupos, cp_estado RESTART IDENTITY CASCADE;"
    reset_mod.assert_safe_sql(sql)
    with pytest.raises(reset_mod.ResetAborted):
        reset_mod.assert_safe_sql("DELETE FROM aliados")
    with pytest.raises(reset_mod.ResetAborted):
        reset_mod.assert_safe_sql("DROP TABLE aliados")
    with pytest.raises(reset_mod.ResetAborted):
        reset_mod.assert_safe_sql("TRUNCATE aliados;")


def test_script_source_does_not_issue_delete_or_drop():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "DELETE FROM" not in text.upper()
    assert "DROP TABLE" not in text.upper()
    assert "TRUNCATE aliados, grupos, cp_estado RESTART IDENTITY CASCADE;" in text


def test_redact_database_url(reset_mod):
    redacted = reset_mod.redact_database_url(
        "postgresql://postgres.abc:supersecret@aws-0-eu-west-1.pooler.supabase.com:6543/postgres"
    )
    assert "supersecret" not in redacted
    assert "***" in redacted
    assert "pooler.supabase.com" in redacted


def test_project_counts_after_zeroes_wipe_and_cascade(reset_mod):
    before = {
        "aliados": 12,
        "grupos": 4,
        "cp_estado": 3,
        "contactos_ruana": 9,
        "ruana_metodos_pago_manual": 1,
        "migraciones": 8,
    }
    after = reset_mod.project_counts_after(before, ["contactos_ruana"])
    assert after["aliados"] == 0
    assert after["grupos"] == 0
    assert after["cp_estado"] == 0
    assert after["contactos_ruana"] == 0
    assert after["ruana_metodos_pago_manual"] == 1
    assert after["migraciones"] == 8


def test_execute_truncate_rolls_back_if_keep_tables_change(reset_mod):
    counts = {
        "aliados": 2,
        "grupos": 1,
        "cp_estado": 1,
        "contactos_ruana": 3,
        "ruana_metodos_pago_manual": 1,
        "migraciones": 5,
    }
    cur = FakeCursor(counts)

    class Conn:
        def __init__(self):
            self.rolled_back = False
            self.committed = False

        def cursor(self):
            return DummyCtx(cur)

        def rollback(self):
            self.rolled_back = True

        def commit(self):
            self.committed = True

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class DummyCtx:
        def __init__(self, inner):
            self.inner = inner

        def __enter__(self):
            return self.inner

        def __exit__(self, *args):
            return False

    conn = Conn()

    def fake_connect(_url, autocommit=False):
        return conn

    original_fetch = reset_mod.fetch_counts

    def fetch_that_zeros_keep(cursor, tables=reset_mod.COUNT_TABLES):
        result = original_fetch(cursor, tables)
        result["migraciones"] = 0
        result["ruana_metodos_pago_manual"] = 0
        return result

    reset_mod.connect = fake_connect  # type: ignore[assignment]
    reset_mod.fetch_counts = fetch_that_zeros_keep  # type: ignore[assignment]
    with pytest.raises(reset_mod.ResetAborted, match="ROLLBACK"):
        reset_mod.execute_truncate("postgresql://x", counts)
    assert conn.rolled_back is True
    assert conn.committed is False


def test_dry_run_flag_roundtrip(reset_mod, tmp_path, monkeypatch):
    url = "postgresql://u:p@db.example:5432/ruana"
    flag = tmp_path / "flag.json"
    monkeypatch.setattr(reset_mod, "dry_run_flag_path", lambda _url: flag)
    written = reset_mod.write_dry_run_flag(url)
    assert written == flag
    payload = json.loads(flag.read_text(encoding="utf-8"))
    assert payload["fingerprint"] == reset_mod.database_fingerprint(url)
    assert reset_mod.require_prior_dry_run(url) == flag


def test_print_report_looks_the_same_for_both_modes(reset_mod, capsys):
    counts = {t: 1 for t in reset_mod.COUNT_TABLES}
    kwargs = dict(
        database_url="postgresql://u:secret@host/db",
        fk_rows=[],
        cascade_rows=[("contactos_ruana", "aliados")],
        counts_before=counts,
        backup_path="/tmp/backup_pre_reset_x.dump",
        counts_after=reset_mod.project_counts_after(counts, ["contactos_ruana"]),
    )
    reset_mod.print_report(
        mode="DRY-RUN",
        backup_status="OMITIDO",
        truncate_status="OMITIDO",
        commit_status="OMITIDO",
        **kwargs,
    )
    dry = capsys.readouterr().out
    reset_mod.print_report(
        mode="EXECUTE",
        backup_status="CREADO (10 bytes)",
        truncate_status="EJECUTADO",
        commit_status="COMMIT",
        **kwargs,
    )
    exe = capsys.readouterr().out
    assert "conteos_antes:" in dry and "conteos_antes:" in exe
    assert "conteos_despues:" in dry and "conteos_despues:" in exe
    assert reset_mod.TRUNCATE_SQL in dry and reset_mod.TRUNCATE_SQL in exe
    assert "secret" not in dry and "secret" not in exe
    assert "SELECT conname, confrelid::regclass" in dry
