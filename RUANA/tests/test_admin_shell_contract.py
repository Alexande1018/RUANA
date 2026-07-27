from pathlib import Path


def test_admin_shell_assets_linked():
    admin_html = Path(__file__).resolve().parents[1] / "web" / "admin.html"
    text = admin_html.read_text(encoding="utf-8")
    assert 'href="/static/css/admin-shell.css"' in text
    assert 'src="/static/js/admin-shell.js"' in text


def test_admin_shell_js_exports_api():
    shell_js = Path(__file__).resolve().parents[1] / "web" / "static" / "js" / "admin-shell.js"
    text = shell_js.read_text(encoding="utf-8")
    assert "window.AdminShell" in text
    assert "confirmDanger" in text
    assert "enhanceAll" in text
    assert "tbody-pendientes-validacion" in text


def test_admin_shell_css_has_sidebar_layout():
    shell_css = Path(__file__).resolve().parents[1] / "web" / "static" / "css" / "admin-shell.css"
    text = shell_css.read_text(encoding="utf-8")
    assert ".admin-sidebar" in text
    assert ".admin-bulk-toolbar" in text
    assert ".admin-danger-modal" in text
