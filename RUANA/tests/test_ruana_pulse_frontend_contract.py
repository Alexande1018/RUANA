"""Contrato frontend de RUANA Pulse (Centro de Actividad)."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


def _read(rel_path: str) -> str:
    return (WEB / rel_path).read_text(encoding="utf-8")


def test_ruana_pulse_assets_wired_in_aliado_html():
    aliado = _read("aliado.html")
    assert 'href="/static/css/ruana-alert-hub.css' in aliado
    assert 'src="/static/js/ruana-alert-hub.js' in aliado
    assert 'id="ruana-pulse"' in aliado
    assert 'id="ruana-pulse-trigger"' in aliado
    assert 'id="ruana-alert-hub"' in aliado
    assert "Centro de Actividad" in aliado
    assert "RUANA Pulse" in aliado
    assert 'aria-controls="ruana-alert-hub"' in aliado
    # Trigger en Inicio, panel flotante fuera del flujo de avisos fijos.
    assert aliado.index("ruana-pulse-trigger") < aliado.index("inicio-actividad-cinta")
    assert aliado.index('id="aliado-shell-alerts"') < aliado.index('id="contacto-aviso-persistente"')
    assert "ruana-alert-hub" not in aliado[
        aliado.index('id="aliado-shell-alerts"') : aliado.index('id="contacto-aviso-persistente"')
    ]


def test_ruana_pulse_js_exposes_panel_api():
    js = _read("static/js/ruana-alert-hub.js")
    for symbol in (
        "RuanaAlertHub",
        "RuanaPulse",
        "classifyPriority",
        "countPending",
        "createTimelineItem",
        "open",
        "close",
        "toggle",
        "prefersReducedMotion",
        "data-alert-action",
        "Escape",
        "data-ruana-pulse-dismiss",
    ):
        assert symbol in js
    assert "host.notificaciones" not in js
    assert "fetch(" not in js


def test_ruana_pulse_css_is_floating_premium_panel():
    css = _read("static/css/ruana-alert-hub.css")
    assert "position: fixed" in css
    assert "z-index: 800" in css
    assert "max-height: 70vh" in css
    assert "90vw" in css
    assert "backdrop-filter" in css
    assert "prefers-reduced-motion: reduce" in css
    assert ".ruana-pulse-trigger" in css
    assert ".ruana-pulse__timeline" in css
    assert ".ruana-pulse-item--action" in css
    assert ".ruana-pulse-item--important" in css
    assert ".ruana-pulse-item--info" in css
    assert ".ruana-pulse-item--done" in css
    assert "html.is-ruana-pulse-open" in css


def test_ruana_pulse_reuses_alertas_data_without_new_business_logic():
    alertas = _read("static/js/aliado-alertas-module.js")
    assert "buildAlertItems" in alertas
    assert "RuanaAlertHub.render" in alertas
    assert "host.contactosPagoPendiente" in alertas
    assert "host.notificaciones" in alertas
    assert "/api/" in alertas
    # El módulo sigue siendo el único adaptador de datos; Pulse solo presenta.
    pulse = _read("static/js/ruana-alert-hub.js")
    assert "contactosPagoPendiente" not in pulse
    assert "marcarTodasNotificacionesLeidas" not in pulse


def test_shell_opens_pulse_instead_of_listing_every_alert():
    shell = _read("static/js/aliado-shell.js")
    assert "openPulse" in shell
    assert "RuanaAlertHub.open" in shell
    assert "Ver actividad" in shell
    assert "scrollAlerts" in shell
    assert "Centro de Actividad" in shell


def test_pulse_overlay_lives_outside_panel_container():
    aliado = _read("aliado.html")
    panel_close = aliado.index("</div>\n\n    <!-- Solicitudes semanales")
    pulse_idx = aliado.index('id="ruana-pulse"')
    assert pulse_idx > panel_close
    assert pulse_idx < aliado.index("ruana-toast-container")
