from pathlib import Path


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
        "conflictosData, pagosApoyoData, pagosEnRevisionData, stripeResumenData, solicitudesData"
        in text
    )


def test_readonly_admin_disables_all_write_actions():
    admin_html = Path(__file__).resolve().parents[1] / "web" / "admin.html"
    text = admin_html.read_text(encoding="utf-8")

    assert "document.querySelectorAll('.btn-admin-action[data-action]')" in text
    assert "data-action=\"crear-campana-invitacion\"" in text


def test_admin_has_payment_methods_management_contract():
    root = Path(__file__).resolve().parents[1] / "web"
    admin_html = (root / "admin.html").read_text(encoding="utf-8")
    sistema_js = (root / "static" / "js" / "admin-sistema-module.js").read_text(encoding="utf-8")
    resumen_js = (root / "static" / "js" / "admin-resumen-module.js").read_text(encoding="utf-8")

    assert 'id="metodos-pago-admin-wrap"' in admin_html
    assert 'data-action="editar-metodos-pago"' in admin_html
    assert "fetch('/api/admin/metodos-pago', fetchOpts)" in resumen_js
    assert "accionEditarMetodosPago" in admin_html
    assert "accionEditarMetodosPago" in sistema_js
    assert "/api/admin/metodos-pago/qr-revolut" in sistema_js


def test_admin_qr_upload_does_not_send_json_content_type():
    root = Path(__file__).resolve().parents[1] / "web"
    sistema_js = (root / "static" / "js" / "admin-sistema-module.js").read_text(encoding="utf-8")
    admin_html = (root / "admin.html").read_text(encoding="utf-8")

    assert "_sistemaModule" in admin_html
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
    assert "confirmarEliminarPerfil" in admin_html
    assert "confirmarEliminarPerfil" in red_js
    assert "/api/admin/eliminar-aliado" in red_js


def test_admin_document_view_uses_authenticated_access_endpoint():
    root = Path(__file__).resolve().parents[1] / "web"
    admin_html = (root / "admin.html").read_text(encoding="utf-8")
    ops_js = (root / "static" / "js" / "admin-operaciones-module.js").read_text(encoding="utf-8")

    assert "buildAdminDocumentLink" in admin_html
    assert "abrirDocumentoAdmin" in admin_html
    assert "/api/admin/documentos/acceso" in ops_js
    assert 'class="btn-link btn-ver-documento-admin"' in ops_js


def test_admin_resumen_module_is_wired():
    """Módulo AdminShell `resumen` extraído; AdminPanel solo fachada de render."""
    root = Path(__file__).resolve().parents[1] / "web"
    admin = (root / "admin.html").read_text(encoding="utf-8")
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
    assert "_resumenModule" in admin
    assert "mod.renderEstadoGlobal(data)" in admin
    assert "mod.renderMovimiento(this, data)" in admin
    assert "mod.renderMetricas(data)" in admin
    # Markup del resumen permanece (sin vaciar admin.html)
    assert 'class="estado-global"' in admin
    assert 'class="movimiento-sistema"' in admin
    assert 'class="metricas-salud"' in admin
    assert "cargarDesdeApi" in admin
    assert "mod.cargarDesdeApi(this)" in admin
    assert "/api/admin/dashboard-summary" in resumen_js
    assert "function cargarDesdeApi(host)" in resumen_js or "async function cargarDesdeApi(host)" in resumen_js


def test_admin_operaciones_module_is_wired():
    """Módulo AdminShell `operaciones` (pagos/conflictos); AdminPanel solo fachada de render."""
    root = Path(__file__).resolve().parents[1] / "web"
    admin = (root / "admin.html").read_text(encoding="utf-8")
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
    assert "_operacionesModule" in admin
    assert "mod.renderConflictosPago(this, conflictos)" in admin
    assert "mod.renderPagosApoyo(this, pagos)" in admin
    assert "mod.renderPagosEnRevision(this, pagos)" in admin
    # Markup permanece
    assert 'id="conflictos-pago-wrap"' in admin
    assert 'id="pagos-apoyo-wrap"' in admin
    assert 'id="pagos-en-revision-wrap"' in admin
    assert "cargarDesdeApi" in admin


def test_admin_referidos_tree_is_wired():
    """Árbol genealógico admin: referidos-module + red-explorer tras cargarDesdeApi."""
    root = Path(__file__).resolve().parents[1] / "web"
    admin = (root / "admin.html").read_text(encoding="utf-8")
    red_ex = (root / "static" / "js" / "admin-red-explorer-module.js").read_text(encoding="utf-8")
    referidos_js = (root / "static" / "js" / "referidos-module.js").read_text(encoding="utf-8")
    resumen_js = (root / "static" / "js" / "admin-resumen-module.js").read_text(encoding="utf-8")

    assert 'href="/static/css/referidos-tree.css"' in admin
    assert 'src="/static/js/referidos-module.js"' in admin
    assert 'src="/static/js/admin-red-explorer-module.js"' in admin
    assert 'id="red-view-referidos"' in admin
    assert 'id="referidos-tree-admin"' in admin
    assert 'id="referidos-detail-admin"' in admin
    assert 'id="referidos-meta-admin"' in admin
    assert 'class="referidos-detail-panel empty"' in admin
    assert "RuanaReferidosTree" in referidos_js
    assert "loadAdmin" in referidos_js
    assert "/api/admin/referidos/raices" in referidos_js
    assert "initReferidosTree" in red_ex
    assert "initReferidosArbol" in red_ex
    assert "referidosTree.load()" in red_ex
    assert "mode: 'admin'" in red_ex
    assert "redEx.initReferidosTree(true)" in resumen_js
    assert "_redExplorerModule" in admin
    assert "mod.initReferidosArbol()" in admin


def test_admin_red_module_is_wired():
    """Módulo AdminShell `red` (jerarquía aliados); AdminPanel solo fachada."""
    root = Path(__file__).resolve().parents[1] / "web"
    admin = (root / "admin.html").read_text(encoding="utf-8")
    red_js = (root / "static" / "js" / "admin-red-module.js").read_text(encoding="utf-8")
    modules_js = (root / "static" / "js" / "admin-modules.js").read_text(encoding="utf-8")

    assert 'src="/static/js/admin-red-module.js"' in admin
    assert "red: null" in modules_js
    assert "modules.red" in red_js or "RuanaAdminModules.red" in red_js
    assert "renderAliadosJerarquia" in red_js
    assert "renderAliados" in red_js
    assert "abrirModalDetalle" in red_js
    assert "abrirLinajeDrawer" in red_js
    assert "_redModule" in admin
    assert "mod.renderAliadosJerarquia(this)" in admin
    assert "mod.renderAliados(this, aliadosData)" in admin
    assert 'id="aliados-jerarquia-nav"' in admin or 'id="aliados-cps-list"' in admin
    assert 'id="aliados-admin-list"' in admin


def test_admin_sistema_module_is_wired():
    """Módulo AdminShell `sistema` (campañas / reglas / métodos pago); fachadas."""
    root = Path(__file__).resolve().parents[1] / "web"
    admin = (root / "admin.html").read_text(encoding="utf-8")
    sistema_js = (root / "static" / "js" / "admin-sistema-module.js").read_text(encoding="utf-8")
    modules_js = (root / "static" / "js" / "admin-modules.js").read_text(encoding="utf-8")

    assert 'src="/static/js/admin-sistema-module.js"' in admin
    assert "sistema: null" in modules_js
    assert "modules.sistema" in sistema_js or "RuanaAdminModules.sistema" in sistema_js
    assert "accionCrearCampanaInvitacion" in sistema_js
    assert "accionCambiarReglas" in sistema_js
    assert "accionEditarMetodosPago" in sistema_js
    assert "accionAbrirPlaza" in sistema_js
    assert "_sistemaModule" in admin
    assert "mod.accionEditarMetodosPago(this)" in admin
    assert "mod.accionCrearCampanaInvitacion(this)" in admin
    assert 'data-action="crear-campana-invitacion"' in admin
    assert 'id="metodos-pago-admin-wrap"' in admin


def test_admin_inline_fetch_budget_and_module_coverage():
    """admin.html conserva auth fetches; carga/ops viven en módulos."""
    root = Path(__file__).resolve().parents[1] / "web"
    admin = (root / "admin.html").read_text(encoding="utf-8")
    resumen = (root / "static" / "js" / "admin-resumen-module.js").read_text(encoding="utf-8")
    ops = (root / "static" / "js" / "admin-operaciones-module.js").read_text(encoding="utf-8")
    sistema = (root / "static" / "js" / "admin-sistema-module.js").read_text(encoding="utf-8")
    red = (root / "static" / "js" / "admin-red-module.js").read_text(encoding="utf-8")

    assert admin.count("fetch(") < 15
    assert "fetch('/api/admin/validar'" in admin
    assert "fetch('/api/admin/me'" in admin or "fetch('/api/admin/me'," in admin
    assert "async function cargarDesdeApi(host)" in resumen
    assert "function setupEventListeners(host)" in resumen
    assert "abrirDocumentoAdmin" in ops
    assert "resolverConflictoDecision" in ops
    assert "cargarCampanasInvitacion" in sistema
    assert "activarAliadoPendiente" in red
    assert "mod.cargarDesdeApi(this)" in admin
    assert "mod.setupEventListeners(this)" in admin
