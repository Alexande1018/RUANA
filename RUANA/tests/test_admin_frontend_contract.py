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


def test_admin_document_view_uses_authenticated_access_endpoint():
    admin_html = Path(__file__).resolve().parents[1] / "web" / "admin.html"
    text = admin_html.read_text(encoding="utf-8")

    assert "buildAdminDocumentLink" in text
    assert "abrirDocumentoAdmin" in text
    assert "/api/admin/documentos/acceso" in text
    assert 'class="btn-link btn-ver-documento-admin"' in text


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
    assert "/api/admin/dashboard-summary" in admin


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
