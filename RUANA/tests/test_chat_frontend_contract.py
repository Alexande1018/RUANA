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

    assert 'id="neg-acuerdo-confirm-flotante"' in aliado
    assert 'id="neg-btn-confirmar-acuerdo-flotante"' in aliado
    assert 'id="acuerdo-flotante-confirmar"' in aliado
    assert "_debeMostrarPagoStripe" in neg_js
    assert "_enlazarBotonPagoStripe" in neg_js
    assert "renderAcuerdoConfirmFlotante" in neg_js
    stripe_js = (root / "static" / "js" / "aliado-stripe-pagos-module.js").read_text(encoding="utf-8")
    assert "function apiUrl(path)" in stripe_js
    assert "contactoEstado === 'pendiente_de_pago'" in stripe_js
