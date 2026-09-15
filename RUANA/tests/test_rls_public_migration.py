from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "supabase" / "migrations" / "20260902000200_enable_rls_public_tables.sql"
CATCHALL = ROOT / "supabase" / "migrations" / "20260915000100_enable_rls_new_public_tables.sql"


def test_rls_migration_file_exists():
    assert MIGRATION.is_file()
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "ENABLE ROW LEVEL SECURITY" in sql
    assert "relrowsecurity = false" in sql


def test_rls_migration_does_not_force_rls():
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


def test_pago_manual_app_access_migration_keeps_anon_denied():
    sql = (
        ROOT / "supabase" / "migrations" / "20260909000100_pago_manual_metodos_app_access.sql"
    ).read_text(encoding="utf-8")
    assert re.search(r"ALTER\s+TABLE[\s\S]{0,80}FORCE\s+ROW\s+LEVEL", sql, re.I) is None
    assert "ruana_metodos_pago_manual_app" in sql
    assert "TO anon" not in sql
    assert "REVOKE ALL ON TABLE public.ruana_metodos_pago_manual FROM anon" in sql
    assert "GRANT SELECT, INSERT, UPDATE, DELETE" in sql


def test_rls_catchall_covers_tables_created_after_sept_4():
    sql = CATCHALL.read_text(encoding="utf-8")
    assert CATCHALL.is_file()
    assert "relrowsecurity = false" in sql
    assert "ENABLE ROW LEVEL SECURITY" in sql
    assert re.search(r"ALTER\s+TABLE[\s\S]{0,80}FORCE\s+ROW\s+LEVEL", sql, re.I) is None
    assert "REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon" in sql
    assert "FOR ALL TO anon" not in sql
    assert "TO anon USING" not in sql
    assert "USING (true)" not in sql.lower()
    for table in (
        "competencia",
        "competencia_pendiente",
        "cp_ciudad",
        "cp_estado",
        "cp_independencia_solicitudes",
        "aliado_avisos_vistos",
        "migracion_territorio_backup",
        "migracion_territorio_informe",
        "migraciones",
    ):
        assert table in sql
    assert "FOR INSERT" not in sql
    assert "FOR UPDATE" not in sql
    assert "FOR DELETE" not in sql
    assert "ruana_enable_rls_on_create_table" in sql


def test_apply_rls_script_globs_catchall():
    script = (
        ROOT / ".github" / "scripts" / "apply_rls_migration.py"
    ).read_text(encoding="utf-8")
    assert "*enable_rls*.sql" in script
