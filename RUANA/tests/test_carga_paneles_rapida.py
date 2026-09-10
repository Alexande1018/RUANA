"""Contrato de carga rápida: app, panel aliado y admin sin cambiar comportamiento."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


def _read(rel):
    return (WEB / rel).read_text(encoding="utf-8")


def test_index_carga_ruana_ui_una_sola_vez():
    html = _read("index.html")
    assert html.count('src="/static/js/ruana-ui.js"') == 1


def test_aliado_lucide_es_local_y_preloads_shell():
    html = _read("aliado.html")
    assert 'src="/static/js/vendor/lucide.min.js?v=0.469.0"' in html
    assert "unpkg.com/lucide" not in html
    assert 'rel="preload" href="/static/css/aliado-shell.css?v=20260910a" as="style"' in html
    lucide = WEB / "static" / "js" / "vendor" / "lucide.min.js"
    assert lucide.is_file()
    text = lucide.read_text(encoding="utf-8")
    assert "lucide v0.469.0" in text
    assert "createIcons" in text


def test_aliado_bootstrap_sesion_y_datos_en_paralelo():
    sync_js = _read("static/js/aliado-sync-module.js")
    start = sync_js.index("function bootstrapPrivatePanel()")
    end = sync_js.index("function initState(host)")
    boot = sync_js[start:end]
    assert "const sesionPromise =" in boot
    assert "const datosPromise =" in boot
    assert boot.index("sesionPromise") < boot.index("await sesionPromise")
    assert boot.index("datosPromise") < boot.index("await sesionPromise")
    assert "ruana_aliado_notificaciones" in boot
    assert "__ruanaBootstrapNotificaciones" in boot


def test_aliado_load_data_omite_notificaciones_del_bootstrap():
    sync_js = _read("static/js/aliado-sync-module.js")
    start = sync_js.index("async function loadData")
    snippet = sync_js[start : start + 4500]
    assert "host._notificacionesFromBootstrap" in snippet
    assert "fetchedRecently && Array.isArray(host.notificaciones)" in snippet
    init_state = sync_js[sync_js.index("function initState(host)") :]
    assert "host._notificacionesFromBootstrap = true" in init_state


def test_aliado_init_semanales_no_refetch_si_ya_hay_snapshot():
    sem_js = _read("static/js/aliado-solicitudes-semanales-module.js")
    start = sem_js.index("async function initSemanales(host)")
    fn = sem_js[start : start + 700]
    assert "host.solicitudesSemanales" in fn
    assert "semana_inicio" in fn
    assert fn.index("fetchSnapshot(host)") > fn.index("semana_inicio")


def test_admin_precarga_css_de_shell_sin_quitar_import():
    html = _read("admin.html")
    assert 'rel="preload" href="/static/css/admin-shell.css" as="style"' in html
    assert 'rel="preload" href="/static/css/admin-panel.css" as="style"' in html
    assert 'url("/static/css/admin-shell.css")' in html
    assert html.count("fetch(") < 15


def test_admin_hidratacion_en_dos_fases():
    resumen = _read("static/js/admin-resumen-module.js")
    start = resumen.index("async function cargarDesdeApi(host)")
    end = resumen.index("function buildIndicadoresAdmin(")
    fn = resumen[start:end]
    assert "criticalIdx = [0, 1, 2, 3, 4, 5, 16]" in fn
    assert "fetchOptsAliados" in fn
    assert "applyAliadosList(host, parsed[2])" in fn
    assert fn.index("applyAliadosList(host, parsed[2])") < fn.index("hideAdminLoader(loader)")
    assert "hideAdminLoader(loader)" in fn
    assert fn.index("hideAdminLoader(loader)") < fn.index("settleIndexes(secondaryIdx)")
    assert "heavy: false" in fn
    assert "heavy: true" in fn
    assert "fetch('/api/admin/dashboard-summary', fetchOpts)" in fn
    assert "fetch('/api/admin/pagos-en-revision', fetchOpts)" in fn
    assert "fetch('/api/admin/solicitudes-semanales', fetchOpts)" in fn
    assert "fetch('/api/admin/metodos-pago', fetchOpts)" in fn
    assert "async function refreshCommandCenterPanels(host, payload, options)" in resumen
    assert "options.heavy === false" in resumen


def test_admin_panel_territorial_carga_aliados_en_critico():
    """Grupos/CP no depende de la hidratación secundaria ni del abort de 12s."""
    resumen = _read("static/js/admin-resumen-module.js")
    explorer = _read("static/js/admin-red-explorer-module.js")
    html = _read("admin.html")
    assert "fetch('/api/aliados/listar', fetchOptsAliados)" in resumen
    assert "function applyAliadosList(host, aliadosData)" in resumen
    assert "Cargando grupos territoriales" in explorer
    assert "function ensureAliadosTerritoriales(host)" in explorer
    assert "fetch('/api/aliados/listar'" in explorer
    assert 'src="/static/js/admin-resumen-module.js?v=20260909e"' in html
    assert 'src="/static/js/admin-red-explorer-module.js?v=20260909e"' in html


def test_static_versioned_assets_tienen_cache_largo(client):
    versioned = client.get("/static/js/vendor/lucide.min.js?v=0.469.0")
    assert versioned.status_code == 200
    cache = versioned.headers.get("Cache-Control", "")
    assert "max-age=31536000" in cache.replace(" ", "")
    assert "immutable" in cache.lower()

    plain = client.get("/static/js/ruana-ui.js")
    assert plain.status_code == 200
    plain_cache = plain.headers.get("Cache-Control", "")
    assert "max-age=3600" in plain_cache.replace(" ", "")
    assert "must-revalidate" in plain_cache.lower()
