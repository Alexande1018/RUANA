from pathlib import Path


def test_admin_shell_assets_linked():
    admin_html = Path(__file__).resolve().parents[1] / "web" / "admin.html"
    text = admin_html.read_text(encoding="utf-8")
    assert 'url("/static/css/admin-shell.css")' in text
    assert 'url("/static/css/admin-command-center.css")' in text
    assert 'href="/static/css/admin-ops-identity.css' in text
    assert 'src="/static/js/admin-shell.js"' in text
    assert 'src="/static/js/admin-command-center-module.js"' in text
    assert 'src="/static/js/admin-score-bands-module.js"' in text


def test_admin_shell_js_exports_api():
    shell_js = Path(__file__).resolve().parents[1] / "web" / "static" / "js" / "admin-shell.js"
    text = shell_js.read_text(encoding="utf-8")
    assert "window.AdminShell" in text
    assert "confirmDanger" in text
    assert "enhanceAll" in text
    assert "tbody-pendientes-validacion" in text


def test_admin_shell_js_has_delete_controls():
    shell_js = Path(__file__).resolve().parents[1] / "web" / "static" / "js" / "admin-shell.js"
    text = shell_js.read_text(encoding="utf-8")
    assert "btn-row-delete" in text
    assert "injectSectionHeaders" in text
    assert "tbody-conflictos-pago" in text
    assert "Eliminar todos" in text


def test_admin_shell_css_has_sidebar_layout():
    shell_css = Path(__file__).resolve().parents[1] / "web" / "static" / "css" / "admin-shell.css"
    text = shell_css.read_text(encoding="utf-8")
    assert ".admin-sidebar" in text
    assert ".admin-bulk-toolbar" in text
    assert ".admin-danger-modal" in text
    assert ".admin-module" in text
    assert ".admin-shell-bottom" in text
    assert ".admin-module-chip" in text


def test_admin_shell_js_has_modules():
    shell_js = Path(__file__).resolve().parents[1] / "web" / "static" / "js" / "admin-shell.js"
    text = shell_js.read_text(encoding="utf-8")
    assert "MODULE_DEFS" in text
    assert "buildModules" in text
    assert "showModule" in text
    assert "data-admin-module" in text
    assert "acciones-admin-wrap" in text
    assert "adminBottomNav" in text


def test_admin_html_acciones_wrap_id():
    admin_html = Path(__file__).resolve().parents[1] / "web" / "admin.html"
    text = admin_html.read_text(encoding="utf-8")
    assert 'id="acciones-admin-wrap"' in text
    assert 'id="invitaciones-admin-wrap"' in text
    assert 'id="red-view-referidos"' in text
    assert 'data-action="crear-campana-invitacion"' in text
    assert "Panel de administración" in text


def test_admin_shell_resumen_module_aligned_with_module_defs():
    """admin-resumen-module.js cubre targets del MODULE_DEFS.id=resumen."""
    root = Path(__file__).resolve().parents[1] / "web"
    shell_js = (root / "static" / "js" / "admin-shell.js").read_text(encoding="utf-8")
    resumen_js = (root / "static" / "js" / "admin-resumen-module.js").read_text(encoding="utf-8")
    admin = (root / "admin.html").read_text(encoding="utf-8")

    assert "id: 'resumen'" in shell_js
    assert "#command-center-wrap" in shell_js
    assert ".estado-global" in shell_js
    assert ".movimiento-sistema" in shell_js
    assert 'src="/static/js/admin-resumen-module.js"' in admin
    assert "renderEstadoGlobal" in resumen_js
    assert "estado-sistema-label" in resumen_js
    assert "mov-sol-nuevas" in resumen_js
    assert "metrica-retencion" in resumen_js


def test_admin_shell_js_has_invitaciones_target():
    shell_js = Path(__file__).resolve().parents[1] / "web" / "static" / "js" / "admin-shell.js"
    text = shell_js.read_text(encoding="utf-8")
    assert "#invitaciones-admin-wrap" in text
    assert "onModuleActivated" in text
    assert "handleSpecialNavigation" in text


def test_admin_shell_operaciones_module_aligned_with_module_defs():
    """admin-operaciones-module.js cubre targets de pagos/conflictos en MODULE_DEFS.pagos."""
    root = Path(__file__).resolve().parents[1] / "web"
    shell_js = (root / "static" / "js" / "admin-shell.js").read_text(encoding="utf-8")
    ops_js = (root / "static" / "js" / "admin-operaciones-module.js").read_text(encoding="utf-8")
    admin = (root / "admin.html").read_text(encoding="utf-8")

    assert "id: 'pagos'" in shell_js
    assert "#conflictos-pago-wrap" in shell_js
    assert "#pagos-apoyo-wrap" in shell_js
    assert "#pagos-en-revision-wrap" in shell_js
    assert 'src="/static/js/admin-operaciones-module.js"' in admin
    assert "renderConflictosPago" in ops_js
    assert "renderPagosApoyo" in ops_js
    assert "renderPagosEnRevision" in ops_js
    assert "tbody-conflictos-pago" in ops_js
    assert "_operacionesModule" in admin


def test_admin_shell_sidebar_does_not_overlay_desktop():
    """En escritorio el menú reserva columna y no se superpone al contenido."""
    root = Path(__file__).resolve().parents[1] / "web"
    css = (root / "static" / "css" / "admin-shell.css").read_text(encoding="utf-8")
    ops_css = (root / "static" / "css" / "admin-ops-identity.css").read_text(encoding="utf-8")
    js = (root / "static" / "js" / "admin-shell.js").read_text(encoding="utf-8")

    assert "html.admin-shell-enabled .admin-main" in ops_css
    assert "margin-left: var(--admin-sidebar-w" in ops_css

    main_block = css[css.index(".admin-main {") : css.index("}", css.index(".admin-main {"))]
    assert "margin-left: var(--admin-sidebar-w)" in main_block
    assert "margin-left: 0" not in main_block

    sidebar_block = css[css.index(".admin-sidebar {") : css.index("}", css.index(".admin-sidebar {"))]
    assert "translateX(-100%)" not in sidebar_block
    assert "visibility: visible" in sidebar_block

    toggle_block = css[
        css.index(".admin-sidebar-toggle {") : css.index("}", css.index(".admin-sidebar-toggle {"))
    ]
    assert "display: none" in toggle_block

    mobile_idx = css.index("@media (max-width: 960px)")
    mobile_css = css[mobile_idx:]
    assert "translateX(-100%)" in mobile_css
    assert "display: inline-flex" in mobile_css
    assert "margin-left: 0" in mobile_css

    assert ".admin-sidebar-backdrop" in css
    assert ".admin-sidebar-toggle-label" in css
    assert "function setSidebarOpen" in js
    assert "function toggleSidebar" in js
    assert "function closeSidebarIfOverlay" in js
    assert "setSidebarOpen(!isMobileShell())" in js
    assert "admin-sidebar-open" in js
    assert "adminSidebarBackdrop" in js
    assert "aria-expanded" in js
    assert "aria-controls" in js
    assert "toggleSidebar," in js
    assert "setSidebarOpen" in js
    assert 'id="adminSidebarToggle"' in js or "adminSidebarToggle" in js
    assert "Mostrar menú" in js
    assert "Ocultar menú" in js


def test_admin_shell_sidebar_nav_not_blocked_by_backdrop():
    """El backdrop móvil no debe cubrir el sidebar ni atraparlo bajo un stacking context."""
    root = Path(__file__).resolve().parents[1] / "web"
    shell_css = (root / "static" / "css" / "admin-shell.css").read_text(encoding="utf-8")
    ops_css = (root / "static" / "css" / "admin-ops-identity.css").read_text(encoding="utf-8")

    assert "admin-sidebar-backdrop.is-visible" in shell_css
    assert "left: var(--admin-sidebar-w)" in shell_css

    assert "admin-sidebar-open .admin-app" not in ops_css
    assert ops_css.index(".admin-sidebar {") < ops_css.index("z-index: 140")


def test_admin_ops_identity_restores_dark_ruana_look():
    """El panel admin recupera lima, fondo oscuro y árbol; no fuerza el tema claro."""
    root = Path(__file__).resolve().parents[1] / "web"
    ops_css = (root / "static" / "css" / "admin-ops-identity.css").read_text(encoding="utf-8")
    admin_html = (root / "admin.html").read_text(encoding="utf-8")
    shell_js = (root / "static" / "js" / "admin-shell.js").read_text(encoding="utf-8")
    cc_js = (root / "static" / "js" / "admin-command-center-module.js").read_text(
        encoding="utf-8"
    )

    assert "--mod-resumen-accent: #a2ff00" in ops_css
    assert "#eef1f6" not in ops_css
    assert "#ffffff" not in ops_css
    assert ".ruana-atmosphere" not in ops_css
    assert "background-image: none !important" not in ops_css
    assert "referidos-tree-panel" in ops_css
    assert "red-explorer-tabs" in ops_css
    assert 'href="/static/css/referidos-tree.css"' in admin_html
    assert 'id="red-view-referidos"' in admin_html
    assert "Árbol genealógico" in shell_js
    assert "Sala de control" in cc_js
