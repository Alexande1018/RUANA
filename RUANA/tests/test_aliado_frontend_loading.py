from pathlib import Path


def test_aliado_panel_starts_with_loading_state():
    aliado_html = Path(__file__).resolve().parents[1] / "web" / "aliado.html"
    styles = Path(__file__).resolve().parents[1] / "web" / "static" / "css" / "styles.css"
    text = aliado_html.read_text(encoding="utf-8")
    css = styles.read_text(encoding="utf-8")

    assert '<body class="panel-loading">' in text
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

    assert "Juan Pérez" not in text
    assert "JP Instalaciones Eléctricas" not in text
    assert 'id="detail-oficio">Electricidad<' not in text
