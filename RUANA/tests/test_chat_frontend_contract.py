from pathlib import Path


def test_negociacion_guiada_replaces_free_chat_modal():
    # Test contrato: modal negociación / conversación del encargo reemplaza chat libre.
    root = Path(__file__).resolve().parents[1] / "web"
    aliado = (root / "aliado.html").read_text(encoding="utf-8")
    neg_js = (root / "static" / "js" / "negociacion-guiada.js").read_text(encoding="utf-8")

    assert 'id="modal-negociacion-guiada"' in aliado
    assert "ruana-conversacion-ui.js" in aliado
    assert "negociacion-guiada.js" in aliado
    assert "negociacion-guiada.css" in aliado
    assert 'id="perfil-mensajes-lista"' in aliado
    assert 'data-aliado-badge="mensajes"' in aliado
    assert "chat-modal-overlay" not in aliado
    sync_js = (root / "static" / "js" / "aliado-sync-module.js").read_text(encoding="utf-8")
    assert "NegociacionGuiada" in sync_js
    assert "host.negociacionGuiada" in sync_js
    assert "new NegociacionGuiada(host)" in sync_js

    # Contrato API vigente (ya no chat_horas_restantes / chat libre).
    assert "/api/contactos/${contactoId}/negociacion" in neg_js or "/api/contactos/" in neg_js
    assert "negociacion/proponer" in neg_js or "_negociacionApiUrl" in neg_js
    assert "chat_horas_restantes" not in aliado


def test_confirmar_acuerdo_es_cta_flotante_centrado():
    """Al terminar la negociación el confirmar acuerdo es flotante y centrado."""
    root = Path(__file__).resolve().parents[1] / "web"
    aliado = (root / "aliado.html").read_text(encoding="utf-8")
    neg_js = (root / "static" / "js" / "negociacion-guiada.js").read_text(encoding="utf-8")
    css = (root / "static" / "css" / "negociacion-guiada.css").read_text(encoding="utf-8")

    assert 'id="neg-cta-flotante"' in aliado
    assert 'id="neg-cta-flotante-confirmar"' in aliado
    assert "Confirmar acuerdo" in aliado
    assert "renderCtaFlotante" in neg_js
    assert "neg-cta-flotante.is-visible" in css
    assert "justify-content: center" in css
    assert ".acuerdo-flotante" in css
    assert "inset: 0" in css
    assert 'id="acuerdo-flotante-pagar"' in aliado
    assert 'id="neg-cta-flotante-pagar"' in aliado
