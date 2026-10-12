"""Contrato UI: banner de primer login en Inicio (grupo CP en formación)."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


def _read(rel_path: str) -> str:
    return (WEB / rel_path).read_text(encoding="utf-8")


def test_banner_markup_sits_under_identity_above_quick_grid():
    aliado = _read("aliado.html")
    identity = aliado.index('id="inicio-identity"')
    banner = aliado.index('id="inicio-grupo-en-creacion-banner"')
    quick = aliado.index("inicio-quick-grid")
    assert identity < banner < quick
    assert 'hidden' in aliado[banner : banner + 400]
    assert 'data-action="invitar-aliado"' in aliado[banner : aliado.index("inicio-actividad-cinta")]
    assert 'data-action="grupo-banner-entendido"' in aliado
    assert 'id="btn-invitar-grupo-banner"' in aliado
    assert 'id="btn-grupo-banner-entendido"' in aliado


def test_banner_copy_is_cp_group_in_formation_not_madre_or_city():
    aliado = _read("aliado.html")
    start = aliado.index('id="inicio-grupo-en-creacion-banner"')
    end = aliado.index("inicio-actividad-cinta", start)
    block = aliado[start:end]
    assert "Tu zona todavía se está formando" in block
    assert "grupo de tu código postal" in block
    assert "invitar a vecinos de tu zona" in block
    assert "Ampliar mi red" in block
    assert "Entendido" in block
    assert "Grupo Madre" not in block
    assert "grupo madre" not in block.lower()
    assert "grupo de tu ciudad" not in block.lower()
    assert "Grupo Madre" not in aliado


def test_banner_cta_reuses_existing_invite_flow():
    aliado = _read("aliado.html")
    invitaciones = _read("static/js/aliado-invitaciones-module.js")
    events = _read("static/js/aliado-events-module.js")
    inicio = _read("static/js/aliado-inicio-module.js")
    assert 'data-action="invitar-aliado"' in aliado
    assert "generarCodigoInvitacionPerfil" in invitaciones
    assert "/api/invitaciones/crear" in invitaciones
    assert 'id="modal-code"' in aliado
    assert 'querySelectorAll(\'[data-action="invitar-aliado"]\')' in events
    assert "host.generarCodigoInvitacionPerfil()" in events
    assert "/api/invitaciones/crear" not in inicio
    assert "generarCodigoInvitacionPerfil" not in inicio


def test_banner_logic_gates_on_data_ok_en_creacion_and_localstorage():
    inicio = _read("static/js/aliado-inicio-module.js")
    sync = _read("static/js/aliado-sync-module.js")
    aliado = _read("aliado.html")

    assert "ruana_grupo_en_creacion_seen" in inicio
    assert "ruana_onboarding_seen" in aliado
    assert "GRUPO_BANNER_SEEN_BASE" in inicio
    assert "shouldShowGrupoEnCreacionBanner" in inicio
    assert "maybeShowGrupoEnCreacionBanner" in inicio
    assert "host.isDataLoaded !== true" in inicio
    assert "host.datosOk === false" in inicio
    assert "panel-loading" in inicio
    assert "grupo_info" in inicio
    assert "en_creacion" in inicio
    assert "shouldAutoStart" in inicio
    assert "ruana-tour-active" in inicio
    assert "ruana-onboarding-finished" in inicio
    assert "ruana-onboarding-finished" in aliado

    assert "host.datosOk = false" in sync
    assert "host.datosOk = !!(host.aliado && (host.aliado.codigo || host.codigoAliado))" in sync
    assert "maybeShowGrupoBanner(host)" in sync
    assert "tourWillAutoStart" in sync


def test_banner_does_not_stack_with_onboarding_tour():
    aliado = _read("aliado.html")
    inicio = _read("static/js/aliado-inicio-module.js")
    sync = _read("static/js/aliado-sync-module.js")
    css = _read("static/css/aliado-shell.css")

    start_fn = aliado.index("start(force = false)")
    start_block = aliado[start_fn : aliado.index("createLayer()", start_fn)]
    assert "hideGrupoEnCreacionBanner" in start_block
    assert "ruana-tour-active" in start_block

    finish_fn = aliado.index("finish(markComplete)")
    finish_block = aliado[finish_fn : finish_fn + 2500]
    assert "ruana-onboarding-finished" in finish_block

    init_onboarding = sync.index("function initOnboarding")
    init_block = sync[init_onboarding : sync.index("function startAutoSync", init_onboarding)]
    assert "tourWillAutoStart" in init_block
    assert "maybeShowGrupoBanner(host)" in init_block
    assert init_block.index("tourWillAutoStart") < init_block.index("maybeShowGrupoBanner(host)")

    assert "body.ruana-tour-active #inicio-grupo-en-creacion-banner" in css
    assert "isTourBlockingBanner" in inicio


def test_banner_styles_are_inline_not_fullscreen_modal():
    css = _read("static/css/aliado-shell.css")
    assert ".inicio-grupo-banner" in css
    assert "position: fixed" not in css[css.index(".inicio-grupo-banner") : css.index(".inicio-quick-grid")]
    assert "body.panel-loading #inicio-grupo-en-creacion-banner" in css
    assert ".inicio-grupo-banner-cta" in css
    assert "min-height: 44px" in css[css.index(".inicio-grupo-banner-cta") : css.index(".inicio-quick-grid")]


def test_banner_primero_de_zona_solo_con_un_activo():
    """1 aliado activo → copy de fundador; 2–10 o número ausente → el de siempre."""
    import json
    import subprocess

    inicio = _read("static/js/aliado-inicio-module.js")
    primero = (
        "Todavía no hay más profesionales en tu grupo. Invita a 2 o 3 profesionales "
        "de confianza de otros oficios: cuantos más seamos, más encargos nos podremos pasar."
    )
    assert "Eres el primero de tu zona" in inicio
    assert primero in inicio
    assert "function grupoBannerVariant" in inicio
    assert "applyGrupoBannerCopy(host)" in inicio
    assert 'id="inicio-grupo-banner-text"' in _read("aliado.html")

    script = r"""
const fs = require('fs');
const vm = require('vm');
const code = fs.readFileSync('web/static/js/aliado-inicio-module.js', 'utf8');
const context = {};
vm.createContext(context);
vm.runInContext(code, context);
const mod = context.RuanaAliadoModules.inicio;
const banner = { hidden: true, attrs: {}, classList: { add() {}, remove() {} }, setAttribute(k, v) { this.attrs[k] = v; } };
const title = { textContent: '' };
const text = { textContent: '' };
context.document = {
  getElementById(id) {
    if (id === 'inicio-grupo-en-creacion-banner') return banner;
    if (id === 'inicio-grupo-banner-title') return title;
    if (id === 'inicio-grupo-banner-text') return text;
    return null;
  }
};
function paint(num) {
  const host = { aliado: { grupo_info: {} } };
  if (num !== '__missing__') host.aliado.grupo_info.num_aliados = num;
  mod.applyGrupoBannerCopy(host);
  return { variant: banner.attrs['data-banner-variant'], title: title.textContent, text: text.textContent };
}
const out = {
  uno: mod.grupoBannerVariant(1),
  dos: mod.grupoBannerVariant(2),
  diez: mod.grupoBannerVariant(10),
  cero: mod.grupoBannerVariant(0),
  once: mod.grupoBannerVariant(11),
  nulo: mod.grupoBannerVariant(null),
  vacio: mod.grupoBannerVariant(''),
  texto: mod.grupoBannerVariant('no-numero'),
  ausente: mod.numAliadosActivosGrupo({ aliado: { grupo_info: { en_creacion: true } } }),
  pintadoUno: paint(1),
  pintadoVarios: paint(4),
  pintadoAusente: paint('__missing__'),
};
process.stdout.write(JSON.stringify(out));
"""
    proc = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert data["uno"] == "primero"
    assert data["dos"] == "formacion"
    assert data["diez"] == "formacion"
    assert data["cero"] == "formacion"
    assert data["once"] == "formacion"
    assert data["nulo"] == "formacion"
    assert data["vacio"] == "formacion"
    assert data["texto"] == "formacion"
    assert data["ausente"] is None
    assert data["pintadoUno"]["variant"] == "primero"
    assert data["pintadoUno"]["title"] == "Eres el primero de tu zona"
    assert data["pintadoUno"]["text"] == primero
    assert data["pintadoVarios"]["variant"] == "formacion"
    assert data["pintadoVarios"]["title"] == "Tu zona todavía se está formando"
    assert "grupo de tu código postal" in data["pintadoVarios"]["text"]
    assert data["pintadoAusente"]["variant"] == "formacion"
    assert data["pintadoAusente"]["title"] == "Tu zona todavía se está formando"


def test_tour_en_espanol_de_espana():
    aliado = _read("aliado.html")
    start = aliado.index("class RuanaOnboardingTour")
    end = aliado.index("class PrivatePanel", start)
    tour = aliado[start:end]
    assert "Toca para avanzar" in tour
    assert "A por ello 🙌" in tour
    assert "lo esencial de RUANA" in tour
    assert "Da clic para avanzar" not in tour
    assert "Dale con todo" not in tour
    assert "lo clave" not in tour
    assert "ahorita" not in tour.lower()
    assert "chamba" not in tour.lower()
    assert "curro" not in tour.lower()
    assert "encargo" in tour
    assert "da clic" not in tour.lower()


def test_pr_does_not_change_aliado_datos_timeout():
    """Este PR no toca timeouts de /api/aliado/datos (cold-start va en otro PR)."""
    sync = _read("static/js/aliado-sync-module.js")
    assert "controller.abort(); }, 25000)" in sync
    assert "/api/aliado/datos" in sync
