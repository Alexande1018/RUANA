"""Contratos frontend/backend de las fases 2–5 de entrada a paneles."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
SERVICE = ROOT / "core" / "services" / "admin_dashboard_service.py"
ALIADO_SVC = ROOT / "core" / "services" / "aliado_service.py"
ALIADO_BP = ROOT / "web" / "blueprints" / "aliado_bp.py"


def _read(rel):
    return (WEB / rel).read_text(encoding="utf-8")


def test_fase2_admin_pinta_snapshot_y_quita_loader_sin_esperar_apis():
    resumen = _read("static/js/admin-resumen-module.js")
    admin = _read("admin.html")
    assert "ADMIN_SNAPSHOT_TTL_MS = 60000" in resumen
    assert "readAdminSnapshot()" in resumen
    assert "applyAdminSnapshot" in resumen
    assert "paintedFromSnapshot" in resumen
    assert "setTimeout(() => new AdminPanel(), 100)" not in admin
    assert "new AdminPanel()" in admin


def test_fase2_aliado_pinta_cache_tras_sesion():
    sync = _read("static/js/aliado-sync-module.js")
    boot = sync[sync.index("function bootstrapPrivatePanel()") : sync.index("function initState(host)")]
    assert "hasCachedAliado" in boot
    assert boot.index("hasCachedAliado") < boot.index("await datosPromise")
    assert "__ruanaDatosPromise" in sync


def test_fase3_listar_y_datos_sin_side_effects():
    listar = ALIADO_SVC.read_text(encoding="utf-8")
    start = listar.index("def listar_aliados")
    end = listar.index("def listar_aliados_directorio_grupo")
    assert "backfill_invitado_por_linaje" not in listar[start:end]
    datos = ALIADO_BP.read_text(encoding="utf-8")
    start = datos.index("def get_aliado_datos")
    end = datos.index("def get_aliado_by_codigo")
    assert "aplicar_penalizaciones_contactos_abiertos" not in datos[start:end]


def test_fase3_servicio_comparte_formula_summary():
    text = SERVICE.read_text(encoding="utf-8")
    assert "def build_dashboard_summary" in text
    assert "SUMMARY_COUNT_KEYS" in text
    assert "def get_admin_bootstrap_cached" in text
    assert "_BOOTSTRAP_TTL_S = 20.0" in text


def test_fase4_lazy_modulos_admin_y_aliado():
    resumen = _read("static/js/admin-resumen-module.js")
    shell = _read("static/js/admin-shell.js")
    sync = _read("static/js/aliado-sync-module.js")
    assert "MODULE_SECONDARY_IDX" in resumen
    assert "async function ensureModuleData" in resumen
    assert "ensureModuleData(panel, moduleId)" in shell
    assert "function sectionsForVisibleModule" in sync
    assert ", 60000)" in sync


def test_fase5_snapshot_ttl_y_cache_bootstrap_con_generacion_compartida():
    resumen = _read("static/js/admin-resumen-module.js")
    service = SERVICE.read_text(encoding="utf-8")
    assert "ADMIN_SNAPSHOT_TTL_MS = 60000" in resumen
    assert "persistAdminSnapshot" in resumen
    assert "_BOOTSTRAP_TTL_S = 20.0" in service
    assert "def clear_admin_bootstrap_cache" in service
    assert "def bump_admin_bootstrap_generation" in service
    assert "def read_admin_bootstrap_generation" in service
    assert "ruana_cache_meta" in service
    assert "cached_gen == generation" in service


def test_fase3_sigue_usando_listar_admin_completo():
    """La lista del bootstrap no es lite: sigue a.* + 5 subconsultas por fila."""
    repo = ROOT / "core" / "repositories" / "aliado_repo.py"
    text = repo.read_text(encoding="utf-8")
    start = text.index("def listar_admin")
    block = text[start : start + 2500]
    assert "a.*" in block
    assert "hijos_directos_count" in block
    assert "total_contactos" in block
    assert "contactos_30d" in block
    assert "es_retador_activo" in block
    assert "es_titular_en_competencia" in block
    service = SERVICE.read_text(encoding="utf-8")
    assert "aliado_service.listar_aliados(db)" in service
    assert "no aligerar la query" in service
