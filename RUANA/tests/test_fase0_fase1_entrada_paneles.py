"""Fase 0/1: timings de hot paths, estáticos en Hosting y keepalive sin min-instances."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "RUANA" / "web"
STATIC = WEB / "static"
FIREBASE_JSON = ROOT / "firebase.json"
DEPLOY_WORKFLOW = ROOT / ".github" / "workflows" / "deploy-firebase.yml"
SYNC_SCRIPT = ROOT / ".github" / "scripts" / "sync-firebase-hosting-static.sh"

HOT_PATHS = (
    "/admin",
    "/aliado",
    "/api/aliado/datos",
    "/api/admin/dashboard-summary",
    "/api/aliados/listar",
    "/api/stats",
)

# CSS/JS servidos hoy por Flask /static. Todos son el mismo bytes para cualquier
# usuario: Flask solo hace send_from_directory. Ninguno se genera por sesión/rol.
STATIC_CSS_JS = (
    "css/admin-command-center.css",
    "css/admin-financial.css",
    "css/admin-ops-identity.css",
    "css/admin-panel.css",
    "css/admin-premium.css",
    "css/admin-shell.css",
    "css/aliado-panel.css",
    "css/aliado-shell.css",
    "css/aliado-solicitudes-semanales.css",
    "css/auth-premium.css",
    "css/config.css",
    "css/encargo-seguimiento.css",
    "css/negociacion-guiada.css",
    "css/panel-premium.css",
    "css/referidos-tree.css",
    "css/ruana-actividad-cinta.css",
    "css/ruana-alert-hub.css",
    "css/ruana-feedback.css",
    "css/ruana-fonts.css",
    "css/ruana-identity.css",
    "css/ruana-legal.css",
    "css/ruana-pulse.css",
    "css/ruana-score-callout.css",
    "css/styles.css",
    "js/admin-charts.js",
    "js/admin-command-center-module.js",
    "js/admin-errores-module.js",
    "js/admin-financial-module.js",
    "js/admin-intelligence-module.js",
    "js/admin-modules.js",
    "js/admin-operaciones-module.js",
    "js/admin-red-explorer-module.js",
    "js/admin-red-module.js",
    "js/admin-resumen-module.js",
    "js/admin-score-bands-module.js",
    "js/admin-shell.js",
    "js/admin-sistema-module.js",
    "js/admin-stripe-module.js",
    "js/admin-territorio-module.js",
    "js/aliado-acuerdos-module.js",
    "js/aliado-alertas-module.js",
    "js/aliado-catalogo-module.js",
    "js/aliado-centro-comunicacion-module.js",
    "js/aliado-conexiones-module.js",
    "js/aliado-contactos-module.js",
    "js/aliado-directorio-module.js",
    "js/aliado-events-module.js",
    "js/aliado-grupo-module.js",
    "js/aliado-inicio-module.js",
    "js/aliado-invitaciones-module.js",
    "js/aliado-modules.js",
    "js/aliado-perfil-module.js",
    "js/aliado-referidos-module.js",
    "js/aliado-shell.js",
    "js/aliado-solicitudes-module.js",
    "js/aliado-solicitudes-semanales-module.js",
    "js/aliado-stripe-pagos-module.js",
    "js/aliado-sync-module.js",
    "js/apelar-expulsion.js",
    "js/negociacion-guiada.js",
    "js/phone-countries.js",
    "js/phone-input.js",
    "js/referidos-module.js",
    "js/ruana-actividad-cinta.js",
    "js/ruana-alert-hub.js",
    "js/ruana-api-client.js",
    "js/ruana-atmosphere.js",
    "js/ruana-conversacion-ui.js",
    "js/ruana-legal-footer.js",
    "js/ruana-pulse.js",
    "js/ruana-ui.js",
    "js/vendor/lucide.min.js",
)


def test_inventario_css_js_son_archivos_estaticos():
    for rel in STATIC_CSS_JS:
        path = STATIC / rel
        assert path.is_file(), rel
        assert path.stat().st_size > 0, rel
    found = {
        p.relative_to(STATIC).as_posix()
        for p in STATIC.rglob("*")
        if p.suffix in {".css", ".js"} and "uploads" not in p.parts
    }
    assert found == set(STATIC_CSS_JS), (found - set(STATIC_CSS_JS), set(STATIC_CSS_JS) - found)


def test_uploads_no_son_paquete_estatico_de_hosting():
    """/static/uploads es de usuario/sesión local; no se mueve a Firebase Hosting."""
    script = SYNC_SCRIPT.read_text(encoding="utf-8")
    assert "uploads" in script
    assert "excluy" in script.lower() or "exclude" in script.lower() or "! -path './uploads/*'" in script
    firebase = json.loads(FIREBASE_JSON.read_text(encoding="utf-8"))
    ignore = firebase["hosting"]["ignore"]
    assert any("uploads" in item for item in ignore)


def test_hot_paths_emiten_server_timing(client):
    for path in HOT_PATHS:
        resp = client.get(path)
        timing = resp.headers.get("Server-Timing", "")
        assert timing.startswith("app;dur="), (path, resp.status_code, timing)
        dur = float(timing.split("dur=", 1)[1])
        assert dur >= 0.0


def test_health_no_lleva_server_timing(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "healthy"
    assert "Server-Timing" not in resp.headers


def test_cache_busting_versioned_sigue_en_paneles():
    aliado = (WEB / "aliado.html").read_text(encoding="utf-8")
    admin = (WEB / "admin.html").read_text(encoding="utf-8")
    assert "aliado-sync-module.js?v=20260910a" in aliado
    assert "lucide.min.js?v=0.469.0" in aliado
    assert "admin-resumen-module.js?v=20260909e" in admin
    assert "ruana-fonts.css?v=20260913a" in aliado
    assert "ruana-fonts.css?v=20260913a" in admin


def test_firebase_hosting_sirve_static_y_reescribe_api_html():
    data = json.loads(FIREBASE_JSON.read_text(encoding="utf-8"))
    hosting = data["hosting"]
    sources = [item["source"] for item in hosting["rewrites"]]
    assert "/api/**" in sources
    assert "**" in sources
    run_targets = {item["source"]: item["run"]["serviceId"] for item in hosting["rewrites"] if "run" in item}
    assert run_targets["/api/**"] == "ruana"
    assert run_targets["**"] == "ruana"
    headers = hosting["headers"]
    joined = json.dumps(headers)
    assert "/static/**" in joined
    assert "max-age=3600" in joined
    assert "max-age=31536000" in joined


def test_deploy_workflow_cpu_boost_sin_min_instances():
    content = DEPLOY_WORKFLOW.read_text(encoding="utf-8")
    assert "--cpu-boost" in content
    assert "--min-instances" not in content
    assert "sync-firebase-hosting-static.sh" in content
    assert "provision-keepalive-scheduler.sh" in content


def test_sync_static_script_syntax_and_copy(tmp_path, monkeypatch):
    result = subprocess.run(["bash", "-n", str(SYNC_SCRIPT)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    dest = ROOT / "firebase-public" / "static"
    if dest.exists():
        # El script regenera el directorio; no debe arrastrar uploads de usuario.
        leftover = [p for p in dest.rglob("*") if p.is_file() and "uploads" in p.parts and p.name != ".gitkeep"]
        assert leftover == []
    copied = subprocess.run(["bash", str(SYNC_SCRIPT)], capture_output=True, text=True)
    assert copied.returncode == 0, copied.stdout + copied.stderr
    assert (dest / "css" / "ruana-fonts.css").is_file()
    assert (dest / "js" / "vendor" / "lucide.min.js").is_file()
    assert (dest / "fonts" / "plus-jakarta-sans-latin-wght-normal.woff2").is_file()
    leaked = [p for p in dest.rglob("*") if p.is_file() and "uploads" in p.parts and p.name != ".gitkeep"]
    assert leaked == []
