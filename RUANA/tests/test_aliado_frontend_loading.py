from pathlib import Path


def test_aliado_panel_starts_with_loading_state():
    aliado_html = Path(__file__).resolve().parents[1] / "web" / "aliado.html"
    styles = Path(__file__).resolve().parents[1] / "web" / "static" / "css" / "styles.css"
    text = aliado_html.read_text(encoding="utf-8")
    css = styles.read_text(encoding="utf-8")

    # El body arranca en loading (puede combinar otras clases, p.ej. aliado-app).
    assert 'class="panel-loading' in text or ' panel-loading' in text
    assert "<body" in text and "panel-loading" in text.split("<body", 1)[1].split(">", 1)[0]
    assert 'id="panel-loading"' in text
    assert "Preparando tu panel..." in text
    assert 'class="ruana-loader-orbit"' in text
    assert 'class="ruana-loader-node node-a"' in text
    assert 'class="ruana-loader-line line-a"' in text
    assert "prefers-reduced-motion: reduce" in css
    assert "setPanelLoading(false)" in text


def test_aliado_panel_does_not_ship_demo_profile_values():
    aliado_html = Path(__file__).resolve().parents[1] / "web" / "aliado.html"
    text = aliado_html.read_text(encoding="utf-8")

    assert "Juan P" not in text
    assert "JP Instalaciones" not in text
    assert 'id="detail-oficio">Electricidad<' not in text


def test_aliado_solicitudes_initial_load_sends_auth_headers():
    aliado_html = Path(__file__).resolve().parents[1] / "web" / "aliado.html"
    text = aliado_html.read_text(encoding="utf-8")
    start = text.index("fetch(apiBase + '/api/solicitudes?codigo='")
    snippet = text[start : start + 260]

    assert "credentials: 'same-origin'" in snippet
    assert "headers: getRuanaAuthHeaders()" in snippet


def test_aceptar_y_pagar_offers_manual_methods_and_receipt_upload():
    aliado_html = Path(__file__).resolve().parents[1] / "web" / "aliado.html"
    text = aliado_html.read_text(encoding="utf-8")

    assert "QR Revolut" in text
    assert "Transferencia" in text
    assert "Subir comprobante" in text
