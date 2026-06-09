from pathlib import Path


def test_comprobante_apoyo_upload_sends_auth_headers():
    aliado_html = Path(__file__).resolve().parents[1] / "web" / "aliado.html"
    text = aliado_html.read_text(encoding="utf-8")
    start = text.index("fetch(`/api/contactos/${contactoId}/comprobante-apoyo`")
    snippet = text[start : start + 220]

    assert "headers: getRuanaAuthHeaders()" in snippet


def test_aceptar_y_pagar_opens_manual_payment_modal_with_bizum_first():
    aliado_html = Path(__file__).resolve().parents[1] / "web" / "aliado.html"
    text = aliado_html.read_text(encoding="utf-8")

    render_start = text.index('class="contacto-aviso-btn btn-aceptar-pagar"')
    render_snippet = text[render_start : render_start + 1200]

    assert "this.abrirModalPagoApoyo(c.id, importeParaModal, c.servicio || 'Contacto')" in render_snippet
    assert "this.abrirModalPayPalApoyo(c.id, importeParaModal, c.servicio || 'Contacto')" not in render_snippet
    assert 'id="modal-pago-apoyo"' in text
    assert 'id="pago-apoyo-bizum-panel"' in text
    assert 'id="pago-apoyo-revolut-panel"' in text
    assert 'id="pago-apoyo-transferencia-panel"' in text
    assert "this.setPagoApoyoMetodo('bizum')" in text
    assert "this.setPagoApoyoMetodo('revolut')" in text
    assert "this.setPagoApoyoMetodo('transferencia')" in text
    assert "/api/metodos-pago" in text


def test_conflict_proof_upload_refreshes_alert_state():
    aliado_html = Path(__file__).resolve().parents[1] / "web" / "aliado.html"
    text = aliado_html.read_text(encoding="utf-8")
    start = text.index("async subirPruebaConflicto()")
    snippet = text[start : start + 1900]

    assert "await this.actualizarEstadoAlertas()" in snippet


def test_dispute_support_uses_ruana_modal_instead_of_browser_dialogs():
    aliado_html = Path(__file__).resolve().parents[1] / "web" / "aliado.html"
    text = aliado_html.read_text(encoding="utf-8")
    start = text.index("async impugnarApoyoRuana(contactoId)")
    snippet = text[start : start + 900]

    assert 'id="modal-impugnar-apoyo"' in text
    assert 'id="impugnar-apoyo-resultado"' in text
    assert "abrirModalImpugnarApoyo(c.id)" in text
    assert "window.prompt" not in snippet
    assert "window.confirm" not in snippet
    assert "alert(" not in snippet
