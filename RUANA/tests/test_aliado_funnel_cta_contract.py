"""Contrato UI: CTA de solicitudes asignadas. No toca el cobro «Ir a pagar»."""
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


def test_ir_a_pagar_sigue_en_el_encargo_tras_acuerdo():
    """El cobro del trabajo es «Ir a pagar» del contratante, no «Conectar pago» de Inicio."""
    stripe = (WEB / "static" / "js" / "aliado-stripe-pagos-module.js").read_text(encoding="utf-8")
    negociacion = (WEB / "static" / "js" / "negociacion-guiada.js").read_text(encoding="utf-8")
    contactos = (WEB / "static" / "js" / "aliado-contactos-module.js").read_text(encoding="utf-8")

    checkout = stripe[stripe.index("async function iniciarPagoStripe") : stripe.index("async function iniciarPagoStripe") + 520]
    assert "apiUrl(`/api/contactos/${contactoId}/stripe/checkout`)" in checkout
    assert "checkout_url" in checkout
    assert "btnLabel: importeTxt ? `Ir a pagar (${importeTxt})` : 'Ir a pagar'" in stripe
    assert "tipo: 'pagar_stripe'" in stripe
    assert "stripe-pagar-btn" in stripe
    assert "iniciarPagoStripe(host, contacto.id)" in stripe

    assert "Ir a pagar" in negociacion
    assert "iniciarPagoStripe(host, cid)" in negociacion
    assert "getAccionPendienteStripe" in contactos


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
