from pathlib import Path


def test_comprobante_apoyo_upload_sends_auth_headers():
    alertas_js = (
        Path(__file__).resolve().parents[1]
        / "web"
        / "static"
        / "js"
        / "aliado-alertas-module.js"
    )
    text = alertas_js.read_text(encoding="utf-8")
    start = text.index("fetch(`/api/contactos/${contactoId}/comprobante-apoyo`")
    snippet = text[start : start + 280]

    assert "getAuthHeadersSafe()" in snippet or "getRuanaAuthHeaders()" in snippet


def test_aceptar_y_pagar_opens_manual_payment_modal_with_bizum_first():
    root = Path(__file__).resolve().parents[1] / "web"
    aliado_html = (root / "aliado.html").read_text(encoding="utf-8")
    alertas_js = (root / "static" / "js" / "aliado-alertas-module.js").read_text(encoding="utf-8")

    # El CTA vive en el hub de alertas (markup dinámico), no en una clase legacy fija.
    assert "btn-aceptar-pagar" in alertas_js
    assert "abrirModalPagoApoyo(" in alertas_js
    assert "Aceptar y pagar" in alertas_js

    bind_start = alertas_js.index("btn-aceptar-pagar")
    bind_snippet = alertas_js[bind_start : bind_start + 900]
    assert "abrirModalPagoApoyo(" in bind_snippet
    assert "abrirModalPayPalApoyo(" not in bind_snippet

    assert 'id="modal-pago-apoyo"' in aliado_html
    assert 'id="pago-apoyo-bizum-panel"' in aliado_html
    assert 'id="pago-apoyo-revolut-panel"' in aliado_html
    assert 'id="pago-apoyo-transferencia-panel"' in aliado_html
    # Tabs en setupEventListeners (aliado-events-module) + default bizum en módulo
    events_js = (root / "static" / "js" / "aliado-events-module.js").read_text(encoding="utf-8")
    assert "host.setPagoApoyoMetodo('bizum')" in events_js
    assert "host.setPagoApoyoMetodo('revolut')" in events_js
    assert "host.setPagoApoyoMetodo('transferencia')" in events_js
    assert "host.setPagoApoyoMetodo('bizum')" in alertas_js
    assert "/api/metodos-pago" in alertas_js


def test_conflict_proof_upload_refreshes_alert_state():
    contactos_js = (
        Path(__file__).resolve().parents[1]
        / "web"
        / "static"
        / "js"
        / "aliado-contactos-module.js"
    )
    text = contactos_js.read_text(encoding="utf-8")
    start = text.index("async function subirPruebaConflicto(host)")
    snippet = text[start : start + 1900]

    assert "await host.actualizarEstadoAlertas()" in snippet


def test_dispute_support_uses_ruana_modal_instead_of_browser_dialogs():
    root = Path(__file__).resolve().parents[1] / "web"
    aliado_html = (root / "aliado.html").read_text(encoding="utf-8")
    alertas_js = (root / "static" / "js" / "aliado-alertas-module.js").read_text(encoding="utf-8")
    start = alertas_js.index("async function impugnarApoyoRuana(host, contactoId)")
    snippet = alertas_js[start : start + 1200]

    assert 'id="modal-impugnar-apoyo"' in aliado_html
    assert 'id="impugnar-apoyo-resultado"' in aliado_html
    assert "abrirModalImpugnarApoyo(c.id)" in alertas_js
    assert "window.prompt" not in snippet
    assert "window.confirm" not in snippet
    assert "alert(" not in snippet
