from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "supabase" / "migrations" / "20260902000200_enable_rls_public_tables.sql"


def test_rls_migration_file_exists():
    assert MIGRATION.is_file()
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "ENABLE ROW LEVEL SECURITY" in sql
    assert "relrowsecurity = false" in sql


def test_rls_migration_does_not_force_rls():
    import re

    sql = MIGRATION.read_text(encoding="utf-8")
    assert re.search(r"ALTER\s+TABLE[\s\S]{0,80}FORCE\s+ROW\s+LEVEL", sql, re.I) is None


def test_rls_migration_denies_anon_and_protects_secrets():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon" in sql
    assert "aliado_recuperacion_acceso" in sql
    assert "ruana_metodos_pago_manual" in sql
    assert "stripe_webhook_events" in sql
    assert "FOR ALL TO anon" not in sql
    assert "TO anon USING" not in sql


def test_rls_migration_score_is_select_only_for_authenticated():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "ruana_score_mov_select_own_or_admin" in sql
    assert "FOR INSERT" not in sql
    assert "FOR UPDATE" not in sql
    assert "FOR DELETE" not in sql
    assert "USING (true)" not in sql.lower()
    assert "using (true)" not in sql.lower()
