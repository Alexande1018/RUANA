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

  async function iniciarPagoStripe(host, contactoId) {
    const resp = await fetch(`/api/contactos/${contactoId}/stripe/checkout`, {
      method: 'POST',
      credentials: 'include',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
    });
    const data = await resp.json();
    if (data.status !== 'success' || !data.checkout_url) {
      throw new Error(data.message || 'No se pudo iniciar el pago');
    }
    global.location.href = data.checkout_url;
  }

  async function confirmarTrabajoStripe(host, contactoId) {
    if (!global.confirm('¿Confirmas que el trabajo se realizó correctamente? Se liberará el pago al profesional.')) {
      return;
    }
    const resp = await fetch(`/api/contactos/${contactoId}/stripe/confirmar-trabajo`, {
      method: 'POST',
      credentials: 'include',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
    });
    const data = await resp.json();
    if (data.status !== 'success') {
      throw new Error(data.message || 'No se pudo confirmar el trabajo');
    }
    if (host && typeof host.refreshAfterAction === 'function') {
      await host.refreshAfterAction(['contactos', 'alertas', 'metricas']);
    }
    alert('Trabajo confirmado. El pago al profesional ha sido liberado.');
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

  function renderStripeAcciones(host, contacto, container) {
    if (!container || !contacto) return;
    const modo = contacto.modo_pago || 'manual';
    const estadoPago = contacto.estado_pago || '';
    const codigo = (host.codigoAliado || (host.aliado && host.aliado.codigo) || '').toString().trim();
    const esContratante = codigo === String(contacto.solicitante_codigo || '').trim();
    const esProfesional = codigo === String(contacto.profesional_codigo || '').trim();
    container.innerHTML = '';
    if (modo !== 'stripe') return;

    const importeVal = contacto.importe_acordado != null ? Number(contacto.importe_acordado) : NaN;
    const importeTxt = (!Number.isNaN(importeVal) && importeVal > 0)
      ? `${importeVal.toFixed(2)} €`
      : '';
    const parts = [];

    if (esProfesional) {
      if (['esperando_cobro_cliente', 'checkout_activo', 'no_generado'].includes(estadoPago)) {
        parts.push(
          '<p class="stripe-estado-msg stripe-estado-msg--pro">'
          + 'Tu pago quedará retenido hasta que el contratante pague. '
          + 'Después se liberará cuando confirme que el trabajo quedó hecho.</p>'
        );
      } else if (estadoPago === 'cobro_confirmado') {
        parts.push(
          '<p class="stripe-estado-msg stripe-estado-msg--pro">'
          + 'El contratante ya pagó. Tu importe está retenido y se liberará '
          + 'cuando confirme que el trabajo quedó hecho.</p>'
        );
      } else if (estadoPago === 'transferido') {
        parts.push('<p class="stripe-estado-msg stripe-estado-msg--ok">Pago transferido a tu cuenta.</p>');
      }
    }

    if (esContratante) {
      if (['esperando_cobro_cliente', 'checkout_activo'].includes(estadoPago)) {
        parts.push(
          `<p class="stripe-estado-msg">${importeTxt
            ? `Importe acordado: <strong>${escapeHtml(importeTxt)}</strong>. `
            : ''}Completa el pago para reservar el encargo.</p>`
          + '<button type="button" class="encargo-card-btn stripe-pagar-btn">Ir a pagar</button>'
        );
      } else if (estadoPago === 'cobro_confirmado') {
        parts.push(
          '<p class="stripe-estado-msg">Pago realizado. Confirma que el trabajo quedó hecho '
          + 'para liberar el importe al profesional.</p>'
          + '<button type="button" class="encargo-card-btn stripe-confirmar-btn">'
          + 'Confirmar trabajo y liberar pago</button>'
        );
      }
    }

    container.innerHTML = parts.join('');
    const btnPagar = container.querySelector('.stripe-pagar-btn');
    if (btnPagar) {
      btnPagar.addEventListener('click', () => {
        iniciarPagoStripe(host, contacto.id).catch((e) => alert(e.message));
      });
    }
    const btnConfirmar = container.querySelector('.stripe-confirmar-btn');
    if (btnConfirmar) {
      btnConfirmar.addEventListener('click', () => {
        confirmarTrabajoStripe(host, contacto.id).catch((e) => alert(e.message));
      });
    }
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
        if (typeof global.RuanaUI !== 'undefined' && global.RuanaUI.success) {
          global.RuanaUI.success('Pago recibido correctamente.');
        } else {
          alert('Pago recibido correctamente.');
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
  };
})(window);
