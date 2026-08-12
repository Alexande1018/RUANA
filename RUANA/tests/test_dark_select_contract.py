from pathlib import Path


def test_global_selects_use_dark_color_scheme():
    styles = Path(__file__).resolve().parents[1] / "web" / "static" / "css" / "styles.css"
    text = styles.read_text(encoding="utf-8")

    assert "select," in text
    assert "select option" in text
    assert "color-scheme: dark" in text
    # Token actual del tema (antes #111827).
    assert "background-color: #141827" in text
    assert "color: #e5e7eb" in text


def test_pages_with_selects_include_dark_select_fallback_for_file_preview():
    web_dir = Path(__file__).resolve().parents[1] / "web"
    css_dir = web_dir / "static" / "css"

    sources = (
        css_dir / "admin-panel.css",
        css_dir / "aliado-panel.css",
        web_dir / "register.html",
    )
    for path in sources:
        text = path.read_text(encoding="utf-8")
        assert "color-scheme: dark" in text
        assert "select option" in text
        assert "background-color: #111827" in text
