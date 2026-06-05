from pathlib import Path


def test_comprobante_apoyo_upload_sends_auth_headers():
    aliado_html = Path(__file__).resolve().parents[1] / "web" / "aliado.html"
    text = aliado_html.read_text(encoding="utf-8")
    start = text.index("fetch(`/api/contactos/${contactoId}/comprobante-apoyo`")
    snippet = text[start : start + 220]

    assert "headers: getRuanaAuthHeaders()" in snippet
