from pathlib import Path


def _web_root() -> Path:
    return Path(__file__).resolve().parents[1] / "web"


def _admin_host_js() -> str:
    """AdminPanel + auth host (antes inline en admin.html)."""
    return (_web_root() / "static" / "js" / "admin-panel-host.js").read_text(encoding="utf-8")


def test_admin_fetch_response_destructuring_matches_fetch_order():
    resumen_js = (
        Path(__file__).resolve().parents[1]
        / "web"
        / "static"
        / "js"
        / "admin-resumen-module.js"
    )
    text = resumen_js.read_text(encoding="utf-8")

    assert "fetch('/api/admin/pagos-en-revision', fetchOpts)" in text
    assert (
        "conflictosData, pagosApoyoData, pagosEnRevisionData, solicitudesData"
        in text
    )


def test_readonly_admin_disables_all_write_actions():
    root = _web_root()
    admin_html = (root / "admin.html").read_text(encoding="utf-8")
    host = _admin_host_js()

    assert "document.querySelectorAll('.btn-admin-action[data-action]')" in host
    assert 'data-action="crear-campana-invitacion"' in admin_html


def test_admin_has_payment_methods_management_contract():
    root = Path(__file__).resolve().parents[1] / "web"
    admin_html = (root / "admin.html").read_text(encoding="utf-8")
    host = _admin_host_js()
    sistema_js = (root / "static" / "js" / "admin-sistema-module.js").read_text(encoding="utf-8")
    resumen_js = (root / "static" / "js" / "admin-resumen-module.js").read_text(encoding="utf-8")

    assert 'id="metodos-pago-admin-wrap"' in admin_html
    assert 'data-action="editar-metodos-pago"' in admin_html
    assert "fetch('/api/admin/metodos-pago', fetchOpts)" in resumen_js
    assert "accionEditarMetodosPago" in host
    assert "accionEditarMetodosPago" in sistema_js
    assert "/api/admin/metodos-pago/qr-revolut" in sistema_js


def test_admin_qr_upload_does_not_send_json_content_type():
    root = Path(__file__).resolve().parents[1] / "web"
    sistema_js = (root / "static" / "js" / "admin-sistema-module.js").read_text(encoding="utf-8")
    host = _admin_host_js()

    assert "_sistemaModule" in host
    assert "_skipContentType" in sistema_js
    start = sistema_js.index("fetch('/api/admin/metodos-pago/qr-revolut'")
    snippet = sistema_js[start : start + 360]

    assert "AdminAuthenticator.getAdminAuthHeaders({ _skipContentType: true })" in snippet


def test_admin_conflict_resolution_refreshes_api_data():
    ops_js = (
        Path(__file__).resolve().parents[1]
        / "web"
        / "static"
        / "js"
        / "admin-operaciones-module.js"
    )
    text = ops_js.read_text(encoding="utf-8")
    start = text.index("async function resolverConflictoDecision(host, decision)")
    snippet = text[start : start + 2200]

    assert "await host.cargarDesdeApi()" in snippet


def test_admin_aliado_detalle_has_delete_profile_button():
    root = Path(__file__).resolve().parents[1] / "web"
    admin_html = (root / "admin.html").read_text(encoding="utf-8")
    red_js = (root / "static" / "js" / "admin-red-module.js").read_text(encoding="utf-8")

    assert 'id="aliadoDetalleEliminar"' in admin_html
    host = _admin_host_js()
    assert "confirmarEliminarPerfil" in host
    assert "confirmarEliminarPerfil" in red_js
    assert "/api/admin/eliminar-aliado" in red_js


def test_admin_document_view_uses_authenticated_access_endpoint():
    root = Path(__file__).resolve().parents[1] / "web"
    admin_html = (root / "admin.html").read_text(encoding="utf-8")
    ops_js = (root / "static" / "js" / "admin-operaciones-module.js").read_text(encoding="utf-8")

    host = _admin_host_js()
    assert "buildAdminDocumentLink" in host
    assert "abrirDocumentoAdmin" in host
    assert "/api/admin/documentos/acceso" in ops_js
    assert 'class="btn-link btn-ver-documento-admin"' in ops_js


def test_admin_resumen_module_is_wired():
    """Módulo AdminShell `resumen` extraído; AdminPanel solo fachada de render."""
    root = Path(__file__).resolve().parents[1] / "web"
    admin = (root / "admin.html").read_text(encoding="utf-8")
    host = _admin_host_js()
    resumen_js = (root / "static" / "js" / "admin-resumen-module.js").read_text(encoding="utf-8")
    modules_js = (root / "static" / "js" / "admin-modules.js").read_text(encoding="utf-8")

    assert 'src="/static/js/admin-modules.js"' in admin
    assert 'src="/static/js/admin-resumen-module.js"' in admin
    assert "RuanaAdminModules" in modules_js
    assert "resumen: null" in modules_js
    assert "RuanaAdminModules.resumen" in resumen_js or "modules.resumen" in resumen_js
    assert "renderEstadoGlobal" in resumen_js
    assert "renderMovimiento" in resumen_js
    assert "renderMovimientoError" in resumen_js
    assert "renderMetricas" in resumen_js
    assert "total-aliados" in resumen_js
    assert "metrica-ratio-sol-inv" in resumen_js
    # Fachadas delgadas en AdminPanel
    assert "_resumenModule" in host
    assert "mod.renderEstadoGlobal(data)" in host
    assert "mod.renderMovimiento(this, data)" in host
    assert "mod.renderMetricas(data)" in host
    # Markup del resumen permanece (sin vaciar admin.html)
    assert 'class="estado-global"' in admin
    assert 'class="movimiento-sistema"' in admin
    assert 'class="metricas-salud"' in admin
    assert "cargarDesdeApi" in host
    assert "mod.cargarDesdeApi(this)" in host
    assert "/api/admin/dashboard-summary" in resumen_js
    assert "function cargarDesdeApi(host)" in resumen_js or "async function cargarDesdeApi(host)" in resumen_js


def test_admin_operaciones_module_is_wired():
    """Módulo AdminShell `operaciones` (pagos/conflictos); AdminPanel solo fachada de render."""
    root = Path(__file__).resolve().parents[1] / "web"
    admin = (root / "admin.html").read_text(encoding="utf-8")
    host = _admin_host_js()
    ops_js = (root / "static" / "js" / "admin-operaciones-module.js").read_text(encoding="utf-8")
    modules_js = (root / "static" / "js" / "admin-modules.js").read_text(encoding="utf-8")

    assert 'src="/static/js/admin-modules.js"' in admin
    assert 'src="/static/js/admin-operaciones-module.js"' in admin
    assert "RuanaAdminModules" in modules_js
    assert "operaciones: null" in modules_js
    assert "RuanaAdminModules.operaciones" in ops_js or "modules.operaciones" in ops_js
    assert "renderConflictosPago" in ops_js
    assert "renderPagosApoyo" in ops_js
    assert "renderPagosEnRevision" in ops_js
    assert "tbody-conflictos-pago" in ops_js
    assert "tbody-pagos-apoyo" in ops_js
    assert "tbody-pagos-en-revision" in ops_js
    # Fachadas delgadas en AdminPanel
    assert "_operacionesModule" in host
    assert "mod.renderConflictosPago(this, conflictos)" in host
    assert "mod.renderPagosApoyo(this, pagos)" in host
    assert "mod.renderPagosEnRevision(this, pagos)" in host
    # Markup permanece
    assert 'id="conflictos-pago-wrap"' in admin
    assert 'id="pagos-apoyo-wrap"' in admin
    assert 'id="pagos-en-revision-wrap"' in admin
    assert "cargarDesdeApi" in host


def test_admin_red_module_is_wired():
    """Módulo AdminShell `red` (jerarquía aliados); AdminPanel solo fachada."""
    root = Path(__file__).resolve().parents[1] / "web"
    admin = (root / "admin.html").read_text(encoding="utf-8")
    host = _admin_host_js()
    red_js = (root / "static" / "js" / "admin-red-module.js").read_text(encoding="utf-8")
    modules_js = (root / "static" / "js" / "admin-modules.js").read_text(encoding="utf-8")

    assert 'src="/static/js/admin-red-module.js"' in admin
    assert "red: null" in modules_js
    assert "modules.red" in red_js or "RuanaAdminModules.red" in red_js
    assert "renderAliadosJerarquia" in red_js
    assert "renderAliados" in red_js
    assert "abrirModalDetalle" in red_js
    assert "abrirLinajeDrawer" in red_js
    assert "_redModule" in host
    assert "mod.renderAliadosJerarquia(this)" in host
    assert "mod.renderAliados(this, aliadosData)" in host
    assert 'id="aliados-jerarquia-nav"' in admin or 'id="aliados-cps-list"' in admin
    assert 'id="aliados-admin-list"' in admin


def test_admin_sistema_module_is_wired():
    """Módulo AdminShell `sistema` (campañas / reglas / métodos pago); fachadas."""
    root = Path(__file__).resolve().parents[1] / "web"
    admin = (root / "admin.html").read_text(encoding="utf-8")
    host = _admin_host_js()
    sistema_js = (root / "static" / "js" / "admin-sistema-module.js").read_text(encoding="utf-8")
    modules_js = (root / "static" / "js" / "admin-modules.js").read_text(encoding="utf-8")

    assert 'src="/static/js/admin-sistema-module.js"' in admin
    assert "sistema: null" in modules_js
    assert "modules.sistema" in sistema_js or "RuanaAdminModules.sistema" in sistema_js
    assert "accionCrearCampanaInvitacion" in sistema_js
    assert "accionCambiarReglas" in sistema_js
    assert "accionEditarMetodosPago" in sistema_js
    assert "accionAbrirPlaza" in sistema_js
    assert "_sistemaModule" in host
    assert "mod.accionEditarMetodosPago(this)" in host
    assert "mod.accionCrearCampanaInvitacion(this)" in host
    assert 'data-action="crear-campana-invitacion"' in admin
    assert 'id="metodos-pago-admin-wrap"' in admin


def test_admin_inline_fetch_budget_and_module_coverage():
    """Auth vive en admin-panel-host; carga/ops viven en módulos; markup en HTML."""
    root = Path(__file__).resolve().parents[1] / "web"
    admin = (root / "admin.html").read_text(encoding="utf-8")
    host = _admin_host_js()
    resumen = (root / "static" / "js" / "admin-resumen-module.js").read_text(encoding="utf-8")
    ops = (root / "static" / "js" / "admin-operaciones-module.js").read_text(encoding="utf-8")
    sistema = (root / "static" / "js" / "admin-sistema-module.js").read_text(encoding="utf-8")
    red = (root / "static" / "js" / "admin-red-module.js").read_text(encoding="utf-8")

    assert 'src="/static/js/admin-panel-host.js"' in admin
    assert "class AdminPanel" not in admin
    assert "class AdminAuthenticator" in host
    assert "class AdminPanel" in host
    assert host.count("fetch(") < 20
    assert "fetch('/api/admin/validar'" in host
    assert "fetch('/api/admin/me'" in host or "fetch('/api/admin/me'," in host
    assert "async function cargarDesdeApi(host)" in resumen
    assert "function setupEventListeners(host)" in resumen
    assert "abrirDocumentoAdmin" in ops
    assert "resolverConflictoDecision" in ops
    assert "cargarCampanasInvitacion" in sistema
    assert "activarAliadoPendiente" in red
    assert "mod.cargarDesdeApi(this)" in host
    assert "mod.setupEventListeners(this)" in host


def test_admin_panel_host_is_wired():
    """AdminPanel/Authenticator viven en admin-panel-host.js."""
    root = _web_root()
    admin = (root / "admin.html").read_text(encoding="utf-8")
    host = _admin_host_js()
    assert 'src="/static/js/admin-panel-host.js"' in admin
    assert "class AdminPanel" in host
    assert "class AdminAuthenticator" in host
    assert "window._ruanaAdminPanel" in host
