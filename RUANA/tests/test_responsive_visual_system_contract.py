from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
STYLES = WEB / "static" / "css" / "styles.css"


def _read(path):
    return path.read_text(encoding="utf-8")


def test_global_design_tokens_and_responsive_helpers_exist():
    text = _read(STYLES)

    for token in (
        "--ruana-bg",
        "--ruana-surface",
        "--ruana-border",
        "--ruana-text",
        "--ruana-accent",
        "--ruana-radius-md",
    ):
        assert token in text

    for class_name in (
        ".ruana-form-control",
        ".ruana-button",
        ".ruana-page-loader",
        ".ruana-loader-orbit",
        ".ruana-auth-card",
    ):
        assert class_name in text

    assert "@media (max-width: 640px)" in text
    assert "min-height: 44px" in text


def test_auth_pages_use_shared_responsive_access_controls():
    for filename in ("index.html", "invite.html"):
        text = _read(WEB / filename)
        assert "ruana-auth-card" in text
        assert "access-mode-switch" in text or filename == "invite.html"
        assert 'style="flex: 1; background:' not in text


def test_register_uses_real_select_class_and_shared_form_styles():
    text = _read(WEB / "register.html")

    assert 'class="register-select"' in text
    assert "register-input" in text
    assert "ruana-form-control" in _read(STYLES)


def test_admin_uses_shared_loader_and_filter_classes():
    text = _read(WEB / "admin.html")

    assert "ruana-page-loader" in text
    assert "admin-filter-row" in text
    assert 'id="admin-loader" style=' not in text
    assert 'class="filtros-solicitudes-admin" style=' not in text


def test_aliado_logout_button_does_not_use_fixed_overlay_position():
    text = _read(WEB / "aliado.html")

    assert "#btn-logout" in text
    assert "position: sticky" in text
    assert "margin: 16px 20px 0 auto" in text
