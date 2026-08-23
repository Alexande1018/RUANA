"""Contrato frontend de la cinta de actividad RUANA."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


def _read(rel_path: str) -> str:
    return (WEB / rel_path).read_text(encoding="utf-8")


def test_actividad_cinta_assets_wired_in_aliado_html():
    aliado = _read("aliado.html")
    assert 'href="/static/css/ruana-actividad-cinta.css"' in aliado
    assert 'src="/static/js/ruana-actividad-cinta.js"' in aliado
    assert 'id="inicio-actividad-cinta"' in aliado
    assert aliado.index("inicio-actividad-cinta") < aliado.index("inicio-quick-grid")


def test_actividad_cinta_js_exports_testable_helpers():
    js = _read("static/js/ruana-actividad-cinta.js")
    for symbol in (
        "MAX_ITEMS",
        "trimToMax",
        "sortByDateDesc",
        "formatRelativeTime",
        "prefersReducedMotion",
    ):
        assert symbol in js
    assert "host.actividadCinta" in js
    assert "ruana-actividad-cinta__track--clone" in js
    assert "animation-play-state" in _read("static/css/ruana-actividad-cinta.css")
    assert "translate3d" in _read("static/css/ruana-actividad-cinta.css")


def test_actividad_cinta_css_continuous_motion_and_accessibility():
    css = _read("static/css/ruana-actividad-cinta.css")
    assert "@keyframes ruana-cinta-scroll" in css
    assert "translate3d" in css
    assert "animation-play-state: paused" in css
    assert "prefers-reduced-motion: reduce" in css
    assert "overflow: hidden" in css
    assert "max-height:" in css


def test_inicio_module_renders_actividad_cinta():
    inicio = _read("static/js/aliado-inicio-module.js")
    assert "renderActividadCinta" in inicio
    assert "RuanaActividadCinta.render" in inicio


def test_sync_module_stores_actividad_cinta_from_api():
    sync = _read("static/js/aliado-sync-module.js")
    assert "actividad_cinta" in sync
    assert "host.actividadCinta" in sync


def test_aliado_bp_exposes_actividad_cinta():
    bp = (ROOT / "web" / "blueprints" / "aliado_bp.py").read_text(encoding="utf-8")
    assert "preparar_actividad_cinta" in bp
    assert "'actividad_cinta': actividad_cinta" in bp
    assert "preparar_actividad_cinta_para_aliado" in bp


def test_notificaciones_endpoint_includes_actividad_cinta():
    bp = (ROOT / "web" / "blueprints" / "aliado_bp.py").read_text(encoding="utf-8")
    start = bp.index("def get_notificaciones_aliado")
    end = bp.index("def marcar_todas_notificaciones_leidas_api", start)
    block = bp[start:end]
    assert "preparar_actividad_cinta_para_aliado" in block
    assert "'actividad_cinta': actividad_cinta" in block


def test_sync_exports_actividad_cinta_helpers():
    sync = _read("static/js/aliado-sync-module.js")
    assert "RuanaAliadoSync" in sync
    assert "applyNotificacionesPayload" in sync
    assert "renderActividadCinta" in sync


def test_alertas_refresh_updates_actividad_cinta():
    alertas = _read("static/js/aliado-alertas-module.js")
    assert "actividad_cinta" in alertas
    assert "renderActividadCinta" in alertas
