from pathlib import Path


def test_negociacion_guiada_replaces_free_chat_modal():
    """El chat libre fue sustituido por negociación guiada en el panel aliado."""
    root = Path(__file__).resolve().parents[1] / "web"
    aliado = (root / "aliado.html").read_text(encoding="utf-8")
    neg_js = (root / "static" / "js" / "negociacion-guiada.js").read_text(encoding="utf-8")

    assert 'id="modal-negociacion-guiada"' in aliado
    assert "negociacion-guiada.js" in aliado
    assert "negociacion-guiada.css" in aliado
    assert "NegociacionGuiada" in aliado
    assert "this.negociacionGuiada" in aliado

    # Contrato API vigente (ya no chat_horas_restantes / chat libre).
    assert "/api/contactos/${contactoId}/negociacion" in neg_js or "/api/contactos/" in neg_js
    assert "negociacion/proponer" in neg_js or "_negociacionApiUrl" in neg_js
    assert "chat_horas_restantes" not in aliado
