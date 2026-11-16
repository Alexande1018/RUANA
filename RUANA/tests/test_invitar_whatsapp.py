"""Contrato: WhatsApp en el modal Ampliar mi red, sin cambiar el Score."""
import json
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
INVITACIONES_JS = ROOT / "web/static/js/aliado-invitaciones-module.js"


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _generar_mensaje(codigo, aliado=None):
    """Ejecuta la función real del módulo en Node (sin Jest/Vitest en el repo)."""
    node = shutil.which("node")
    assert node, "hace falta node para comprobar el texto generado"
    script = """
const fs = require('fs');
const jsPath = process.argv[1];
const codigo = process.argv[2];
const aliado = JSON.parse(process.argv[3]);
const src = fs.readFileSync(jsPath, 'utf8');
const context = { location: { origin: 'https://ruana-4293f.web.app' } };
const fn = new Function('window', 'globalThis', src + '\\n;return globalThis.RuanaAliadoModules.invitaciones.mensajeWhatsappInvitacion;');
const mensajeFn = fn(context, context);
process.stdout.write(mensajeFn(codigo, aliado));
"""
    result = subprocess.run(
        [node, "-e", script, str(INVITACIONES_JS), codigo, json.dumps(aliado or {}, ensure_ascii=False)],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


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
    html = _read("web/aliado.html")

    assert "https://wa.me/?text=" in js
    assert "encodeURIComponent(mensajeWhatsappInvitacion(codigo, aliado))" in js
    assert "urlWhatsappInvitacion(data.codigo, host && host.aliado)" in js
    assert "urlWhatsappInvitacion(codigo, host && host.aliado)" in js
    assert "/invite.html?codigo=" in js
    assert "https://ruana-4293f.web.app" in js
    assert "una red de oficios de Alicante" not in js
    assert "Estoy en RUANA: los profesionales de la zona nos pasamos los trabajos que no son de lo nuestro." in js
    assert "Me falta alguien de confianza de tu oficio, ¿te apuntas?" in js
    assert "de tu zona." in js
    assert "curro" not in js
    assert "SCORE_AMPLIAR_RED = 3" in js
    assert "SCORE_CRECIMIENTO_GRUPO = 5" in js
    assert "SCORE_CRECIMIENTO_MAX = 10" in js
    assert "mostrarModalCodigoInvitacion(data.codigo, false, SCORE_AMPLIAR_RED)" in js
    assert "mostrarModalCodigoInvitacion(data.codigo, false, SCORE_CRECIMIENTO_GRUPO)" in js
    assert "Con este código son +3 cuando se registra." in js
    assert "Con este código son +5 cuando se registra (hasta " in js
    assert "aliado-invitaciones-module.js?v=20261116a" in html

    # Los números del modal son los que ya aplica el backend. No se toca la regla.
    assert "aplicar_cambio_score(codigo_invitador, 3, 'aliado_referido_registro_valido')" in score
    assert "CRECIMIENTO_GRUPO_SCORE_DELTA = 5" in constants
    assert "CRECIMIENTO_GRUPO_MAX_RECOMPENSAS = 10" in constants


def test_mensaje_whatsapp_usa_zona_oficio_y_enlace():
    enlace = "https://ruana-4293f.web.app/invite.html?codigo=ALC-IG"
    con_ciudad = _generar_mensaje(
        "ALC-IG",
        {"nombre": "Daniel", "oficio": "Electricista", "grupo_info": {"ciudad": "Sevilla"}},
    )
    assert con_ciudad == (
        "Soy Daniel, electricista en Sevilla. "
        "Estoy en RUANA: los profesionales de la zona nos pasamos los trabajos que no son de lo nuestro. "
        "Me falta alguien de confianza de tu oficio, ¿te apuntas? " + enlace
    )

    por_cp = _generar_mensaje(
        "ALC-IG",
        {"nombre": "Lucía", "oficio": "Fontanería", "codigo_postal": "28001"},
    )
    assert por_cp.startswith("Soy Lucía, fontanería en Madrid.")
    assert por_cp.endswith(enlace)

    sin_zona = _generar_mensaje(
        "ALC-IG",
        {"nombre": "Elder", "oficio": "Albañilería"},
    )
    assert sin_zona == (
        "Soy Elder, albañilería de tu zona. "
        "Estoy en RUANA: los profesionales de la zona nos pasamos los trabajos que no son de lo nuestro. "
        "Me falta alguien de confianza de tu oficio, ¿te apuntas? " + enlace
    )

    sin_oficio = _generar_mensaje(
        "ALC-IG",
        {"nombre": "Ana", "ciudad": "Valencia"},
    )
    assert sin_oficio.startswith("Soy Ana en Valencia.")
    assert "undefined" not in sin_oficio
    assert enlace in sin_oficio


def test_el_front_no_repite_el_texto_viejo_de_curro():
    web = ROOT / "web"
    restos = []
    for path in list(web.rglob("*.js")) + list(web.rglob("*.html")):
        texto = path.read_text(encoding="utf-8")
        if "curro" in texto.lower() or "pasamos curro" in texto.lower():
            restos.append(str(path.relative_to(ROOT)))
    assert restos == []


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
