from pathlib import Path


def test_admin_fetch_response_destructuring_matches_fetch_order():
    admin_html = Path(__file__).resolve().parents[1] / "web" / "admin.html"
    text = admin_html.read_text(encoding="utf-8")

    assert "fetch('/api/admin/pagos-en-revision', fetchOpts)" in text
    assert (
        "conflictosData, pagosApoyoData, pagosEnRevisionData, solicitudesData"
        in text
    )


def test_readonly_admin_disables_all_write_actions():
    admin_html = Path(__file__).resolve().parents[1] / "web" / "admin.html"
    text = admin_html.read_text(encoding="utf-8")

    assert "document.querySelectorAll('.btn-admin-action[data-action]')" in text
    assert "data-action=\"crear-campana-invitacion\"" in text


def test_admin_has_payment_methods_management_contract():
    admin_html = Path(__file__).resolve().parents[1] / "web" / "admin.html"
    text = admin_html.read_text(encoding="utf-8")

    assert 'id="metodos-pago-admin-wrap"' in text
    assert 'data-action="editar-metodos-pago"' in text
    assert "fetch('/api/admin/metodos-pago', fetchOpts)" in text
    assert "accionEditarMetodosPago" in text
    assert "/api/admin/metodos-pago/qr-revolut" in text


def test_admin_qr_upload_does_not_send_json_content_type():
    admin_html = Path(__file__).resolve().parents[1] / "web" / "admin.html"
    text = admin_html.read_text(encoding="utf-8")

    assert "_skipContentType" in text
    start = text.index("fetch('/api/admin/metodos-pago/qr-revolut'")
    snippet = text[start : start + 360]

    assert "AdminAuthenticator.getAdminAuthHeaders({ _skipContentType: true })" in snippet


def test_admin_conflict_resolution_refreshes_api_data():
    admin_html = Path(__file__).resolve().parents[1] / "web" / "admin.html"
    text = admin_html.read_text(encoding="utf-8")
    start = text.index("async resolverConflictoDecision(decision)")
    snippet = text[start : start + 2200]

    assert "await this.cargarDesdeApi()" in snippet


def test_admin_aliado_detalle_has_delete_profile_button():
    admin_html = Path(__file__).resolve().parents[1] / "web" / "admin.html"
    text = admin_html.read_text(encoding="utf-8")

    assert 'id="aliadoDetalleEliminar"' in text
    assert "confirmarEliminarPerfil" in text
    assert "/api/admin/eliminar-aliado" in text
