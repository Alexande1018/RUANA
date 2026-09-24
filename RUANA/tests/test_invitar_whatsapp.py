"""Contrato: WhatsApp en el modal Ampliar mi red, sin cambiar el Score."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_modal_tiene_whatsapp_y_la_frase_de_score():
    html = _read("web/aliado.html")
    start = html.index('id="modal-code"')
    end = html.index('id="modal-contacto-previo"', start)
    modal = html[start:end]
    assert 'id="btn-copy-code"' in modal
    assert "Copiar código" in modal
    assert 'id="btn-whatsapp-code"' in modal
    assert "Enviar por WhatsApp" in modal
    copy_at = modal.index("Copiar código")
    wa_at = modal.index("Enviar por WhatsApp")
    assert copy_at < wa_at
    assert "Ganas puntos de Score por cada colega que se una." in modal
    assert "enviarInvitacionWhatsapp" in html


def test_mensaje_usa_invite_html_y_los_puntos_reales():
    js = _read("web/static/js/aliado-invitaciones-module.js")
    score = _read("core/services/invitacion_service.py")
    constants = _read("core/db_constants.py")

    assert "https://wa.me/?text=" in js
    assert "encodeURIComponent(mensajeWhatsappInvitacion(codigo))" in js
    assert "/invite.html?codigo=" in js
    assert "https://ruana-4293f.web.app" in js
    assert "Oye, estoy en RUANA, una red de oficios de Alicante" in js
    assert "SCORE_AMPLIAR_RED = 3" in js
    assert "SCORE_CRECIMIENTO_GRUPO = 5" in js
    assert "SCORE_CRECIMIENTO_MAX = 10" in js
    assert "mostrarModalCodigoInvitacion(data.codigo, false, SCORE_AMPLIAR_RED)" in js
    assert "mostrarModalCodigoInvitacion(data.codigo, false, SCORE_CRECIMIENTO_GRUPO)" in js
    assert "Con este código son +3 cuando se registra." in js
    assert "Con este código son +5 cuando se registra (hasta " in js

    # Los números del modal son los que ya aplica el backend. No se toca la regla.
    assert "aplicar_cambio_score(codigo_invitador, 3, 'aliado_referido_registro_valido')" in score
    assert "CRECIMIENTO_GRUPO_SCORE_DELTA = 5" in constants
    assert "CRECIMIENTO_GRUPO_MAX_RECOMPENSAS = 10" in constants


def test_el_banner_sigue_abriendo_ampliar_red_no_crecimiento():
    """Recomendación aparte: no cambiar el banner en este PR."""
    aliado = _read("web/aliado.html")
    events = _read("web/static/js/aliado-events-module.js")
    inicio = _read("web/static/js/aliado-inicio-module.js")
    banner = aliado[aliado.index('id="inicio-grupo-en-creacion-banner"') : aliado.index("inicio-actividad-cinta")]
    assert 'data-action="invitar-aliado"' in banner
    assert "invitar-crecimiento-grupo" not in banner
    assert "host.generarCodigoInvitacionPerfil()" in events
    assert "generarCodigoInvitacionCrecimientoGrupo" not in inicio
