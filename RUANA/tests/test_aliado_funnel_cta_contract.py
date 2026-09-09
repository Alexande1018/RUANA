"""Contrato UI del embudo aliado: CTA de solicitudes asignadas y botones de pago."""
from pathlib import Path
import subprocess
import textwrap


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


def test_solicitud_asignada_a_mi_tiene_boton_aceptar():
    js = (WEB / "static" / "js" / "aliado-solicitudes-module.js").read_text(encoding="utf-8")
    assert "function codigoAliadoHost" in js
    assert "function codigoAsignadoSolicitud" in js
    assert "var mostrarAtender = conBotonConocer && estado === 'pendiente' && asignadaAMi;" in js
    assert "var mostrarConocer = conBotonConocer && estado === 'pendiente' && !asignadaAMi;" in js
    assert "btn-atender" in js
    assert "Aceptar solicitud" in js
    assert "postAccionSolicitud(host, 'atender', id)" in js
    assert "&& !asignadaA;" not in js


def test_conectar_gestionar_pago_disparan_accion_real():
    shell = (WEB / "static" / "js" / "aliado-shell.js").read_text(encoding="utf-8")
    pulse = (WEB / "static" / "js" / "ruana-pulse.js").read_text(encoding="utf-8")
    stripe = (WEB / "static" / "js" / "aliado-stripe-pagos-module.js").read_text(encoding="utf-8")
    aliado = (WEB / "aliado.html").read_text(encoding="utf-8")

    assert "paymentAction: 'stripe-pendiente'" in shell
    assert "paymentAction: 'apoyo-pago'" in shell
    assert "data-inicio-alert" in shell
    assert "iniciarOnboardingStripe" in shell
    assert "handleAction(panel, 'stripe-pendiente')" in shell
    assert "handleAction(panel, 'apoyo-pago')" in shell

    assert "handleAction: handleAction" in pulse
    assert "if (!state.isOpen) open(host);" in pulse

    assert "apiUrl('/api/aliado/stripe/onboarding')" in stripe
    assert "fetch('/api/aliado/stripe/onboarding'" not in stripe

    assert "aliado-solicitudes-module.js?v=20260909a" in aliado
    assert "aliado-shell.js?v=20260909a" in aliado
    assert "aliado-stripe-pagos-module.js?v=20260909a" in aliado
    assert "ruana-pulse.js?v=20260909a" in aliado


def test_render_solicitudes_asignadas_muestra_cta(tmp_path):
    """Render real de tarjetas: asignada a mí → Aceptar; resto pendientes → Conozco."""
    script = tmp_path / "render_solicitudes_cta.js"
    script.write_text(
        textwrap.dedent(
            r"""
            const fs = require('fs');
            const path = require('path');
            const webRoot = process.argv[2];

            function el(tag) {
              return {
                tagName: String(tag || 'div').toUpperCase(),
                className: '',
                innerHTML: '',
                children: [],
                appendChild(child) { this.children.push(child); return child; },
              };
            }

            const document = {
              getElementById() { return null; },
              createElement(tag) { return el(tag); },
              querySelector() { return null; },
              querySelectorAll() { return []; },
              addEventListener() {},
            };
            const windowObj = { document, RuanaAliadoModules: {} };
            global.window = windowObj;
            global.document = document;
            global.globalThis = windowObj;

            eval(fs.readFileSync(path.join(webRoot, 'static/js/aliado-solicitudes-module.js'), 'utf8'));
            const mod = windowObj.RuanaAliadoModules.solicitudes;
            if (!mod || typeof mod.appendSolicitudCard !== 'function') {
              throw new Error('modulo solicitudes no cargado');
            }

            const host = {
              codigoAliado: '66803',
              aliado: { codigo: '66803' },
              escapeHtml(value) { return String(value || ''); },
            };

            const assignedMine = el('div');
            mod.appendSolicitudCard(host, assignedMine, {
              id: 11,
              descripcion: 'Puerta bloqueada',
              solicitante_nombre: 'Ana',
              oficio: 'Cerrajeria',
              estado: 'pendiente',
              asignada_a_codigo: '66803',
              asignada_a_nombre: 'Yo',
            }, true);
            const mineHtml = String(assignedMine.children[0].innerHTML);
            if (!mineHtml.includes('btn-atender') || !mineHtml.includes('Aceptar solicitud')) {
              throw new Error('falta Aceptar solicitud en asignada a mi');
            }
            if (mineHtml.includes('btn-conocer')) {
              throw new Error('no debe salir Conozco a alguien en asignada a mi');
            }

            const assignedOther = el('div');
            mod.appendSolicitudCard(host, assignedOther, {
              id: 12,
              descripcion: 'Fuga cocina',
              solicitante_nombre: 'Luis',
              oficio: 'Fontaneria',
              estado: 'pendiente',
              asignada_a_codigo: '77001',
              asignada_a_nombre: 'Otro',
            }, true);
            const otherHtml = String(assignedOther.children[0].innerHTML);
            if (!otherHtml.includes('btn-conocer')) {
              throw new Error('falta Conozco a alguien en asignada a otro');
            }
            if (otherHtml.includes('btn-atender')) {
              throw new Error('no debe salir Aceptar en asignada a otro');
            }

            const unassigned = el('div');
            mod.appendSolicitudCard(host, unassigned, {
              id: 13,
              descripcion: 'Pintar salon',
              solicitante_nombre: 'Marta',
              oficio: 'Pintura',
              estado: 'pendiente',
            }, true);
            if (!String(unassigned.children[0].innerHTML).includes('btn-conocer')) {
              throw new Error('falta Conozco a alguien en pendiente sin asignar');
            }

            console.log('ok');
            """
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        ["node", str(script), str(WEB)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "ok" in result.stdout
