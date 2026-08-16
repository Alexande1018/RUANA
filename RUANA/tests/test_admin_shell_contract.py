from pathlib import Path


def test_admin_shell_assets_linked():
    admin_html = Path(__file__).resolve().parents[1] / "web" / "admin.html"
    text = admin_html.read_text(encoding="utf-8")
    assert 'href="/static/css/admin-shell.css"' in text
    assert 'href="/static/css/admin-command-center.css"' in text
    assert 'src="/static/js/admin-shell.js"' in text
    assert 'src="/static/js/admin-command-center-module.js"' in text


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
