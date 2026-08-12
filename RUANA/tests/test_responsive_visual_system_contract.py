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
    # Touch targets viven repartidos: styles (46px) + paneles/feedback (44px).
    assert "min-height: 46px" in text
    panel_premium = _read(WEB / "static" / "css" / "panel-premium.css")
    feedback = _read(WEB / "static" / "css" / "ruana-feedback.css")
    assert "min-height: 44px" in panel_premium or "min-height: 44px" in feedback


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


def test_admin_table_scroll_containers_allow_overflow():
    text = _read(WEB / "static" / "css" / "admin-premium.css")

    start = text.index(".movimiento-24h-tabla-scroll,")
    end = text.index(".movimiento-24h-tabla th,", start)
    block = text[start:end]

    assert "overflow-x: auto" in block
    assert "overflow-y: auto" in block
    assert "overflow: hidden" not in block


def test_admin_uses_shared_loader_and_filter_classes():
    text = _read(WEB / "admin.html")

    assert "ruana-page-loader" in text
    assert "admin-filter-row" in text
    assert 'id="admin-loader" style=' not in text
    assert 'class="filtros-solicitudes-admin" style=' not in text


def test_admin_has_sticky_topbar_and_hides_content_while_loading():
    text = _read(WEB / "admin.html")
    resumen = _read(WEB / "static" / "js" / "admin-resumen-module.js")

    assert '<body class="admin-is-loading">' in text
    assert 'class="admin-topbar"' in text
    assert 'class="admin-topbar-link"' in text
    assert 'class="admin-data-content"' in text
    assert "document.body.classList.add('admin-is-loading')" in resumen
    assert "document.body.classList.remove('admin-is-loading')" in resumen
    assert '<a href="/" class="btn-back">' not in text


def test_admin_can_render_and_deactivate_invitation_campaigns():
    text = _read(WEB / "admin.html")
    sistema = _read(WEB / "static" / "js" / "admin-sistema-module.js")
    resumen = _read(WEB / "static" / "js" / "admin-resumen-module.js")

    assert "admin-campanas-invitacion-panel" in text
    assert "admin-campanas-invitacion-tbody" in text
    assert "admin-campana-invitacion-result" in text
    assert "renderCampanasInvitacion" in text
    assert "cargarCampanasInvitacion" in text
    assert "btn-ver-campana" in sistema or "btn-ver-campana" in text
    assert "verDetalleCampanaInvitacion" in text
    assert "buildCampanaRegistroUrl" in text
    assert "buildCampanaQrUrl" in text
    assert "desactivarCampanaInvitacion" in text
    assert "fetch('/api/admin/invitacion-campanas?limite=30'" in resumen or "fetch('/api/admin/invitacion-campanas?limite=30'" in sistema
    assert "/api/admin/invitacion-campanas/' + encodeURIComponent(codigo) + '/desactivar" in sistema
    assert '<button type="button" class="btn-admin-action" data-action="crear-campana-invitacion">Crear Invitacion Multiuso</button>\n                <button type="button" class="btn-admin-action" data-action="crear-codigo-aliado">' not in text


def test_aliado_logout_button_does_not_use_fixed_overlay_position():
    text = _read(WEB / "static" / "css" / "aliado-panel.css")

    assert "#btn-logout" in text
    assert "position: sticky" in text
    assert "margin: 16px 20px 0 auto" in text


def test_aliado_perfil_tiene_boton_generar_codigo_invitacion():
    text = _read(WEB / "aliado.html")
    invitaciones = _read(WEB / "static" / "js" / "aliado-invitaciones-module.js")

    assert 'id="btn-invitar-aliado"' in text
    assert "btn-invitar-aliado" in text
    assert 'id="btn-invitar-global"' in text
    assert 'id="btn-invitar-nav"' in text
    assert 'data-action="invitar-aliado"' in text
    assert "Ampliar mi red" in text
    assert "generarCodigoInvitacionPerfil" in text
    assert "/api/invitaciones/crear" in invitaciones
