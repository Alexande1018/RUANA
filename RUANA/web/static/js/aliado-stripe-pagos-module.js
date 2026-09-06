/**
 * Pagos Stripe Connect en panel aliado (checkout + confirmación por contratante + onboarding).
 */
(function (global) {
  'use strict';

  const MSG_PAGO_NO_DISPONIBLE = 'Pago no disponible todavía con este profesional';

  function isStripeConectado(aliado) {
    if (!aliado) return false;
    if (aliado.stripe_pago_listo === true) return true;
    return Boolean(
      (aliado.stripe_account_id || '').toString().trim()
      && Number(aliado.stripe_charges_enabled) === 1
    );
  }

  function stripePagosActivos() {
    return true;
  }

  function authHeaders(extra) {
    const base = extra || {};
    if (typeof global.getRuanaAuthHeaders === 'function') {
      return global.getRuanaAuthHeaders(base);
    }
    return base;
  }

  function apiUrl(path) {
    const normalized = path.startsWith('/') ? path : `/${path}`;
    if (typeof global.getApiBase === 'function') {
      return `${String(global.getApiBase() || '').replace(/\/$/, '')}${normalized}`;
    }
    const base = global.RUANA_API_BASE
      || (typeof global.location !== 'undefined' ? global.location.origin : '');
    return `${String(base || '').replace(/\/$/, '')}${normalized}`;
  }

  async function iniciarPagoStripe(host, contactoId) {
    const resp = await fetch(apiUrl(`/api/contactos/${contactoId}/stripe/checkout`), {
      method: 'POST',
      credentials: 'same-origin',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
    });
    const data = await resp.json();
    if (data.status !== 'success' || !data.checkout_url) {
      throw new Error(data.message || 'No se pudo iniciar el pago');
    }
    global.location.href = data.checkout_url;
  }

  function formatEuros(val) {
    const n = Number(val);
    if (Number.isNaN(n) || n <= 0) return '';
    return `${n.toFixed(2)} €`;
  }

  function pctRuanaLabel(contacto) {
    const pct = Number(contacto.comision_porcentaje);
    if (!Number.isNaN(pct) && pct > 0) {
      return pct <= 1 ? `${Math.round(pct * 100)}%` : `${Math.round(pct)}%`;
    }
    return '12%';
  }

  function desgloseStripeHtml(contacto) {
    const bruto = Number(contacto.importe_acordado ?? contacto.importe_final);
    const neto = Number(contacto.importe_neto_profesional);
    const apoyo = Number(contacto.apoyo_ruana ?? contacto.comision);
    const pctTxt = pctRuanaLabel(contacto);
    const items = [];
    if (!Number.isNaN(bruto) && bruto > 0) {
      items.push(`Total pagado por el cliente: <strong>${escapeHtml(formatEuros(bruto))}</strong>`);
    }
    if (!Number.isNaN(apoyo) && apoyo > 0) {
      items.push(
        `Comisión RUANA (${pctTxt}): <strong>${escapeHtml(formatEuros(apoyo))}</strong> `
        + '(retenida en el cobro; no debes pagarla aparte)'
      );
    }
    if (!Number.isNaN(neto) && neto > 0) {
      items.push(`Tu importe neto: <strong>${escapeHtml(formatEuros(neto))}</strong>`);
    }
    if (!items.length) return '';
    return `<ul class="stripe-desglose-list">${items.map((t) => `<li>${t}</li>`).join('')}</ul>`;
  }

  function desgloseStripeTexto(contacto) {
    const bruto = Number(contacto.importe_acordado ?? contacto.importe_final);
    const neto = Number(contacto.importe_neto_profesional);
    const apoyo = Number(contacto.apoyo_ruana ?? contacto.comision);
    const pctTxt = pctRuanaLabel(contacto);
    const partes = [];
    if (!Number.isNaN(bruto) && bruto > 0) {
      partes.push(`Total pagado: ${formatEuros(bruto)}`);
    }
    if (!Number.isNaN(apoyo) && apoyo > 0) {
      partes.push(`Comisión RUANA (${pctTxt}): ${formatEuros(apoyo)}`);
    }
    if (!Number.isNaN(neto) && neto > 0) {
      partes.push(`Importe neto profesional: ${formatEuros(neto)}`);
    }
    return partes.join(' · ');
  }

  function parseEventTimestamp(raw) {
    if (!raw) return Date.now();
    const date = new Date(raw);
    return Number.isNaN(date.getTime()) ? Date.now() : date.getTime();
  }

  function buildPaymentActivityEvents(contacto, codigoAliado) {
    if (!contacto || contacto.modo_pago !== 'stripe') return [];
    const codigo = String(codigoAliado || '').trim();
    const esContratante = codigo === String(contacto.solicitante_codigo || '').trim();
    const esProfesional = codigo === String(contacto.profesional_codigo || '').trim();
    if (!esContratante && !esProfesional) return [];

    const estadoPago = String(contacto.estado_pago || '').trim();
    const netoTxt = formatEuros(contacto.importe_neto_profesional) || 'tu importe neto';
    const desglose = desgloseStripeTexto(contacto);
    const createdAt = parseEventTimestamp(
      contacto.fecha_confirmacion_trabajo || contacto.fecha_pago || contacto.actualizado_en
    );
    const events = [];

    if (transferenciaStripeCompletada(contacto)) {
      if (esProfesional) {
        events.push({
          id: `encargo-${contacto.id}-transferido`,
          contactoId: contacto.id,
          tipo: 'pago_transferido',
          tier: 'completed',
          title: 'Pago transferido',
          description: `RUANA ha enviado ${netoTxt} a tu cuenta Stripe Connect.${desglose ? ` ${desglose}.` : ''}`,
          createdAt,
        });
      } else if (esContratante) {
        events.push({
          id: `encargo-${contacto.id}-transferido`,
          contactoId: contacto.id,
          tipo: 'pago_transferido',
          tier: 'completed',
          title: 'Pago completado',
          description: `Confirmaste la entrega y el pago al profesional se completó.${desglose ? ` ${desglose}.` : ''}`,
          createdAt,
        });
      }
      return events;
    }

    if (transferenciaStripeEnCurso(contacto) || estadoPago === 'transfer_pendiente') {
      if (esProfesional) {
        events.push({
          id: `encargo-${contacto.id}-transfer-pendiente`,
          contactoId: contacto.id,
          tipo: 'transferencia_en_proceso',
          tier: 'important',
          title: 'Trabajo confirmado',
          description: `El contratante confirmó la entrega. Pago: ${netoTxt} → transferencia en proceso.${desglose ? ` ${desglose}.` : ''}`,
          createdAt,
        });
      } else if (esContratante) {
        events.push({
          id: `encargo-${contacto.id}-transfer-pendiente`,
          contactoId: contacto.id,
          tipo: 'transferencia_en_proceso',
          tier: 'important',
          title: 'Trabajo confirmado',
          description: `Confirmaste la entrega. El pago de ${netoTxt} está en proceso en Stripe.${desglose ? ` ${desglose}.` : ''}`,
          createdAt,
        });
      }
      return events;
    }

    if (estadoPago === 'cobro_confirmado') {
      if (esProfesional) {
        events.push({
          id: `encargo-${contacto.id}-cobro-retenido`,
          contactoId: contacto.id,
          tipo: 'pago_retenido',
          tier: 'info',
          title: 'Pago retenido',
          description: `El contratante ya pagó. Tu importe (${netoTxt}) está retenido hasta que confirme la entrega.${desglose ? ` ${desglose}.` : ''}`,
          createdAt: parseEventTimestamp(contacto.fecha_pago || contacto.actualizado_en),
        });
      } else if (esContratante) {
        events.push({
          id: `encargo-${contacto.id}-cobro-confirmado`,
          contactoId: contacto.id,
          tipo: 'pago_realizado',
          tier: 'info',
          title: 'Pago realizado',
          description: `Pago confirmado. Confirma la entrega para liberar ${netoTxt} al profesional.${desglose ? ` ${desglose}.` : ''}`,
          createdAt: parseEventTimestamp(contacto.fecha_pago || contacto.actualizado_en),
        });
      }
      return events;
    }

    if (esProfesional && ['esperando_cobro_cliente', 'checkout_activo', 'no_generado'].includes(estadoPago)) {
      events.push({
        id: `encargo-${contacto.id}-esperando-cobro`,
        contactoId: contacto.id,
        tipo: 'pago_pendiente',
        tier: 'info',
        title: 'Pago pendiente',
        description: 'Tu pago quedará retenido hasta que el contratante pague y confirme la entrega.',
        createdAt: parseEventTimestamp(contacto.actualizado_en || contacto.creado_en),
      });
    }

    return events;
  }

  function syncPaymentActivity(contacto, codigoAliado, options) {
    const events = buildPaymentActivityEvents(contacto, codigoAliado);
    if (!events.length) return;
    if (global.RuanaPulse && typeof global.RuanaPulse.registerEncargoEvents === 'function') {
      global.RuanaPulse.registerEncargoEvents(events, options || {});
    }
  }

  function showPaymentToast(title, message) {
    if (typeof global.RuanaUI !== 'undefined' && global.RuanaUI.success) {
      global.RuanaUI.success(title, message, 4200);
    } else {
      alert(`${title}\n${message}`);
    }
  }
  function transferenciaStripeEnCurso(contacto) {
    const estadoPago = String(contacto.estado_pago || '').trim();
    const estadoFin = String(contacto.estado_financiero || '').trim();
    if (estadoPago === 'transfer_pendiente') return true;
    if (estadoFin === 'TRANSFERENCIA_ENVIADA' || estadoFin === 'TRANSFERENCIA_PENDIENTE') return true;
    if (contacto.stripe_transfer_id && contacto.fecha_confirmacion_trabajo) return true;
    return false;
  }

  function transferenciaStripeCompletada(contacto) {
    const estadoPago = String(contacto.estado_pago || '').trim();
    const estadoFin = String(contacto.estado_financiero || '').trim();
    return estadoPago === 'transferido' || estadoFin === 'TRANSFERIDO'
      || String(contacto.estado || '').trim() === 'trabajo_cerrado';
  }

  async function confirmarTrabajoStripe(host, contactoId) {
    if (!global.confirm('¿Confirmas que el trabajo se realizó correctamente? Se liberará el pago al profesional.')) {
      return;
    }
    const resp = await fetch(apiUrl(`/api/contactos/${contactoId}/stripe/confirmar-trabajo`), {
      method: 'POST',
      credentials: 'same-origin',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
    });
    const data = await resp.json();
    if (data.status !== 'success') {
      throw new Error(data.message || 'No se pudo confirmar el trabajo');
    }
    if (host && typeof host.refreshAfterAction === 'function') {
      await host.refreshAfterAction(['contactos', 'alertas', 'metricas']);
    }
    const neto = data.importe_neto_profesional != null ? Number(data.importe_neto_profesional) : NaN;
    const netoTxt = !Number.isNaN(neto) && neto > 0 ? `${neto.toFixed(2)} €` : 'tu importe neto';
    const codigo = (host && (host.codigoAliado || (host.aliado && host.aliado.codigo)) || '').toString().trim();
    if (data.estado_pago === 'transferido') {
      showPaymentToast('Pago completado', `Se transfirieron ${netoTxt} a la cuenta del profesional.`);
    } else {
      showPaymentToast('Trabajo confirmado', `El pago de ${netoTxt} está en proceso.`);
    }
    if (host && host.contactoActual && Number(host.contactoActual.id) === Number(contactoId)) {
      host.contactoActual = { ...host.contactoActual, ...data };
    }
    syncPaymentActivity(
      { ...(host && host.contactoActual ? host.contactoActual : {}), ...data, id: contactoId, modo_pago: 'stripe' },
      codigo,
      { showToast: false, markNew: true }
    );
  }

  async function iniciarOnboardingStripe() {
    const resp = await fetch('/api/aliado/stripe/onboarding', {
      method: 'POST',
      credentials: 'include',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
    });
    const data = await resp.json();
    if (data.status !== 'success' || !data.onboarding_url) {
      throw new Error(data.message || 'No se pudo iniciar onboarding Stripe');
    }
    global.location.href = data.onboarding_url;
  }

  function _buildOnboardingMarkup(conectado) {
    if (conectado) {
      return '<span class="stripe-onboarding-ok">✓ Cuenta de pago conectada</span>';
    }
    return (
      '<p class="stripe-onboarding-text">Para recibir encargos pagados debes conectar tu cuenta de pago.</p>'
      + '<button type="button" class="encargo-card-btn stripe-onboarding-btn">'
      + 'Conectar cuenta de pago (obligatorio para recibir encargos)</button>'
    );
  }

  function _bindOnboardingButton(container) {
    const btn = container && container.querySelector('.stripe-onboarding-btn');
    if (!btn || btn.dataset.bound === '1') return;
    btn.dataset.bound = '1';
    btn.addEventListener('click', () => {
      iniciarOnboardingStripe().catch((e) => alert(e.message));
    });
  }

  function renderOnboardingUi(host) {
    if (typeof host.renderAlertHub === 'function') host.renderAlertHub();
    if (!stripePagosActivos()) return;
    const aliado = (host && host.aliado) || {};
    const conectado = isStripeConectado(aliado);
    const banner = document.getElementById('stripe-onboarding-banner');
    const perfil = document.getElementById('stripe-perfil-section');
    const markup = _buildOnboardingMarkup(conectado);

    if (banner) {
      banner.innerHTML = markup;
      banner.style.display = conectado ? 'none' : '';
      banner.classList.toggle('stripe-onboarding-banner--ok', conectado);
      _bindOnboardingButton(banner);
    }
    if (perfil) {
      perfil.innerHTML = '<h3 class="stripe-perfil-title">Cuenta de pago</h3>' + markup;
      perfil.style.display = '';
      perfil.classList.toggle('stripe-perboarding-section--ok', conectado);
      _bindOnboardingButton(perfil);
    }
  }

  async function refreshStripeEstadoFromServer(host) {
    if (!host) return;
    try {
      const resp = await fetch('/api/aliado/stripe/estado', {
        credentials: 'include',
        headers: authHeaders(),
      });
      const data = await resp.json();
      if (data.status === 'success') {
        if (host.aliado) {
          host.aliado.stripe_pago_listo = !!data.stripe_pago_listo;
          host.aliado.stripe_charges_enabled = data.stripe_pago_listo ? 1 : 0;
        }
        renderOnboardingUi(host);
        return data;
      }
      const respDatos = await fetch('/api/aliado/datos', {
        credentials: 'include',
        headers: authHeaders(),
      });
      const datos = await respDatos.json();
      if (datos.status === 'success' && datos.aliado) {
        host.aliado = { ...(host.aliado || {}), ...datos.aliado };
        renderOnboardingUi(host);
      }
    } catch (e) {
      console.error('Error refrescando estado Stripe:', e);
    }
    return null;
  }

  function handleOnboardingReturn(host) {
    if (!global.location || !global.location.search) return;
    const params = new URLSearchParams(global.location.search);
    const onboarding = params.get('stripe_onboarding');
    if (!onboarding) return;

    params.delete('stripe_onboarding');
    const clean = params.toString();
    const newUrl = global.location.pathname + (clean ? '?' + clean : '') + global.location.hash;
    global.history.replaceState({}, '', newUrl);

    if (onboarding === 'done') {
      refreshStripeEstadoFromServer(host).then(() => {
        if (typeof global.RuanaUI !== 'undefined' && global.RuanaUI.success) {
          global.RuanaUI.success('Cuenta de pago conectada correctamente.');
        } else {
          alert('Cuenta de pago conectada correctamente.');
        }
      });
    } else if (onboarding === 'refresh') {
      if (typeof global.RuanaUI !== 'undefined' && global.RuanaUI.warning) {
        global.RuanaUI.warning('', 'No se completó la conexión. Vuelve a intentarlo cuando puedas.');
      } else {
        alert('No se completó la conexión. Vuelve a intentarlo cuando pueda.');
      }
      renderOnboardingUi(host);
    }
  }

  function getAccionPendienteStripe(contacto, codigoAliado) {
    if (!contacto || contacto.modo_pago !== 'stripe') return null;
    const codigo = String(codigoAliado || '').trim();
    const esContratante = codigo === String(contacto.solicitante_codigo || '').trim();
    if (!esContratante) return null;

    const estadoPago = String(contacto.estado_pago || '').trim();
    const enTransferencia = transferenciaStripeEnCurso(contacto);
    const transferido = transferenciaStripeCompletada(contacto);
    const contactoEstado = String(contacto.estado || '').trim();

    if (estadoPago === 'cobro_confirmado' && !enTransferencia && !transferido) {
      return {
        tipo: 'confirmar_entrega',
        kicker: 'ACCIÓN PENDIENTE',
        texto: 'Confirma la entrega para liberar el pago.',
        btnLabel: 'Confirmar entrega',
      };
    }

    const puedeIniciarPago = ['esperando_cobro_cliente', 'checkout_activo', 'no_generado', ''].includes(estadoPago)
      && !enTransferencia && !transferido
      && ['pendiente_de_pago', 'trabajo_en_progreso', 'acuerdo_alcanzado'].includes(contactoEstado);
    if (puedeIniciarPago) {
      const importeVal = contacto.importe_acordado != null ? Number(contacto.importe_acordado) : NaN;
      const importeTxt = (!Number.isNaN(importeVal) && importeVal > 0)
        ? `${importeVal.toFixed(2)} €`
        : '';
      return {
        tipo: 'pagar_stripe',
        kicker: 'ACCIÓN PENDIENTE',
        texto: 'Completa el pago para reservar el encargo.',
        btnLabel: importeTxt ? `Ir a pagar (${importeTxt})` : 'Ir a pagar',
      };
    }

    return null;
  }

  function renderAccionPendienteStripe(host, contacto, container) {
    if (!container || !contacto) return;
    container.innerHTML = '';
    if (contacto.modo_pago !== 'stripe') return;

    const codigo = (host.codigoAliado || (host.aliado && host.aliado.codigo) || '').toString().trim();
    syncPaymentActivity(contacto, codigo, { silent: true });
    const accion = getAccionPendienteStripe(contacto, codigo);
    if (!accion) return;

    container.innerHTML = (
      '<div class="encargo-accion-compacta" role="status">'
      + `<p class="encargo-accion-compacta__kicker">${escapeHtml(accion.kicker)}</p>`
      + `<p class="encargo-accion-compacta__texto">${escapeHtml(accion.texto)}</p>`
      + `<button type="button" class="encargo-accion-compacta__btn encargo-card-btn ${accion.tipo === 'pagar_stripe' ? 'stripe-pagar-btn' : 'stripe-confirmar-btn'}">${escapeHtml(accion.btnLabel)}</button>`
      + '</div>'
    );

    const btnPagar = container.querySelector('.stripe-pagar-btn');
    if (btnPagar && btnPagar.dataset.negStripeBound !== '1') {
      btnPagar.dataset.negStripeBound = '1';
      btnPagar.addEventListener('click', () => {
        iniciarPagoStripe(host, contacto.id).catch((e) => alert(e.message));
      });
    }
    const btnConfirmar = container.querySelector('.stripe-confirmar-btn');
    if (btnConfirmar && btnConfirmar.dataset.negStripeBound !== '1') {
      btnConfirmar.dataset.negStripeBound = '1';
      btnConfirmar.addEventListener('click', () => {
        confirmarTrabajoStripe(host, contacto.id).catch((e) => alert(e.message));
      });
    }
  }

  function renderStripeAcciones(host, contacto, container) {
    renderAccionPendienteStripe(host, contacto, container);
  }

  function handlePagoReturn(host) {
    if (!global.location || !global.location.search) return;
    const params = new URLSearchParams(global.location.search);
    const pago = params.get('stripe_pago');
    if (!pago) return;

    const contactoId = params.get('contacto_id');
    params.delete('stripe_pago');
    params.delete('contacto_id');
    const clean = params.toString();
    const newUrl = global.location.pathname + (clean ? '?' + clean : '') + global.location.hash;
    global.history.replaceState({}, '', newUrl);

    const refresh = async () => {
      if (host && typeof host.cargarContactosPendientes === 'function') {
        await host.cargarContactosPendientes();
      }
      if (host && typeof host.refreshAfterAction === 'function') {
        await host.refreshAfterAction(['contactos', 'alertas', 'metricas']);
      }
    };

    if (pago === 'ok') {
      refresh().then(() => {
        showPaymentToast('Pago recibido', 'El pago se registró correctamente.');
        if (contactoId && host && host.contactoActual) {
          syncPaymentActivity(host.contactoActual, (host.codigoAliado || (host.aliado && host.aliado.codigo) || '').toString().trim());
        }
        if (contactoId && host && typeof host.abrirNegociacionContacto === 'function') {
          host.abrirNegociacionContacto(parseInt(contactoId, 10), null);
        }
      });
    } else if (pago === 'cancel') {
      refresh().then(() => {
        if (typeof global.RuanaUI !== 'undefined' && global.RuanaUI.warning) {
          global.RuanaUI.warning('', 'Pago cancelado. Puedes intentarlo de nuevo cuando quieras.');
        } else {
          alert('Pago cancelado. Puedes intentarlo de nuevo cuando quieras.');
        }
      });
    }
  }

  function enlazarBotonesOnboarding(container) {
    _bindOnboardingButton(container);
  }

  /**
   * Aviso en negociación cuando el pago Stripe del profesional no está listo.
   * @param {HTMLElement} el contenedor
   * @param {'profesional'|'solicitante'|string} rol
   * @param {object} [opts] mensajes opcionales del backend
   */
  function renderAvisoNegociacion(el, rol, opts) {
    if (!el) return;
    const options = opts || {};
    const esProfesional = rol === 'profesional';
    const titulo = esProfesional
      ? (options.mensaje || 'Debes conectar tu cuenta de pago antes de poder cerrar encargos con precio.')
      : (options.mensaje || options.aviso || MSG_PAGO_NO_DISPONIBLE);
    const detalle = esProfesional
      ? 'Sin esto, el contratante no podrá confirmar el precio final del encargo.'
      : 'Pídele al profesional que conecte su cuenta desde su panel RUANA (banner superior o Perfil).';
    const btnHtml = esProfesional
      ? '<button type="button" class="neg-btn neg-btn-primary neg-btn-block stripe-onboarding-btn">'
        + 'Conectar cuenta de pago ahora</button>'
      : '';
    el.className = 'neg-stripe-aviso';
    el.innerHTML = `<strong>${escapeHtml(titulo)}</strong><p>${escapeHtml(detalle)}</p>${btnHtml}`;
    el.style.display = 'block';
    enlazarBotonesOnboarding(el);
  }

  function htmlBloqueoPrecioNegociacion(rol, opts) {
    const options = opts || {};
    const esProfesional = rol === 'profesional';
    const titulo = esProfesional
      ? (options.mensaje || 'Debes conectar tu cuenta de pago para confirmar este precio.')
      : (options.mensaje || MSG_PAGO_NO_DISPONIBLE);
    const detalle = esProfesional
      ? 'Pulsa el botón para abrir el proceso de conexión con Stripe. Cuando termines, vuelve aquí y confirma el precio.'
      : 'El profesional debe activar su cuenta de pago. Hasta entonces no podrás confirmar el precio final.';
    const btnHtml = esProfesional
      ? '<button type="button" class="neg-btn neg-btn-primary neg-btn-block stripe-onboarding-btn">'
        + 'Conectar cuenta de pago ahora</button>'
      : '';
    return `<div class="neg-stripe-bloqueo-precio" role="alert">
      <strong>${escapeHtml(titulo)}</strong>
      <p>${escapeHtml(detalle)}</p>
      ${btnHtml}
    </div>`;
  }

  function escapeHtml(str) {
    return String(str || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function labelEstadoPago(estadoPago) {
    const map = {
      esperando_cobro_cliente: 'Pendiente de pago',
      checkout_activo: 'Pago en curso',
      cobro_confirmado: 'Cobrado — pendiente de confirmar trabajo',
      transferido: 'Transferido al profesional',
      transfer_pendiente: 'Transferencia en proceso',
    };
    return map[estadoPago] || (estadoPago || 'pendiente').replace(/_/g, ' ');
  }

  global.RuanaStripePagos = {
    iniciarPagoStripe,
    confirmarTrabajoStripe,
    iniciarOnboardingStripe,
    renderStripeAcciones,
    renderOnboardingUi,
    refreshStripeEstadoFromServer,
    handleOnboardingReturn,
    handlePagoReturn,
    renderAvisoNegociacion,
    htmlBloqueoPrecioNegociacion,
    enlazarBotonesOnboarding,
    isStripeConectado,
    stripePagosActivos,
    labelEstadoPago,
    MSG_PAGO_NO_DISPONIBLE,
    buildPaymentActivityEvents,
    syncPaymentActivity,
    getAccionPendienteStripe,
    renderAccionPendienteStripe,
  };
})(window);
