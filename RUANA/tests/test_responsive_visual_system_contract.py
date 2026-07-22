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


def test_admin_has_sticky_topbar_and_hides_content_while_loading():
    text = _read(WEB / "admin.html")

    assert '<body class="admin-is-loading">' in text
    assert 'class="admin-topbar"' in text
    assert 'class="admin-topbar-link"' in text
    assert 'class="admin-data-content"' in text
    assert "document.body.classList.add('admin-is-loading')" in text
    assert "document.body.classList.remove('admin-is-loading')" in text
    assert '<a href="/" class="btn-back">' not in text


def test_admin_can_render_and_deactivate_invitation_campaigns():
    text = _read(WEB / "admin.html")

    assert "admin-campanas-invitacion-panel" in text
    assert "admin-campanas-invitacion-tbody" in text
    assert "admin-campana-invitacion-result" in text
    assert "renderCampanasInvitacion" in text
    assert "cargarCampanasInvitacion" in text
    assert "btn-ver-campana" in text
    assert "verDetalleCampanaInvitacion" in text
    assert "buildCampanaRegistroUrl" in text
    assert "buildCampanaQrUrl" in text
    assert "desactivarCampanaInvitacion" in text
    assert "fetch('/api/admin/invitacion-campanas?limite=30'" in text
    assert "/api/admin/invitacion-campanas/' + encodeURIComponent(codigo) + '/desactivar" in text
    assert '<button type="button" class="btn-admin-action" data-action="crear-campana-invitacion">Crear Invitacion Multiuso</button>\n                <button type="button" class="btn-admin-action" data-action="crear-codigo-aliado">' not in text


def test_aliado_logout_button_does_not_use_fixed_overlay_position():
    text = _read(WEB / "aliado.html")

    assert "#btn-logout" in text
    assert "position: sticky" in text
    assert "margin: 16px 20px 0 auto" in text


def test_aliado_perfil_tiene_boton_generar_codigo_invitacion():
    text = _read(WEB / "aliado.html")

    assert 'id="btn-invitar-aliado"' in text
    assert "btn-invitar-aliado" in text
    assert "Generar código de invitación" in text
    assert "generarCodigoInvitacionPerfil" in text
    assert "/api/invitaciones/crear" in text
