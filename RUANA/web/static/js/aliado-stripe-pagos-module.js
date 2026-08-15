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

  async function iniciarPagoStripe(host, contactoId) {
    const resp = await fetch(`/api/contactos/${contactoId}/stripe/checkout`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
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
      headers: { 'Content-Type': 'application/json' },
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
      headers: { 'Content-Type': 'application/json' },
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
        headers: typeof global.getRuanaAuthHeaders === 'function'
          ? global.getRuanaAuthHeaders()
          : {},
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
        headers: typeof global.getRuanaAuthHeaders === 'function'
          ? global.getRuanaAuthHeaders()
          : {},
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
    container.innerHTML = '';
    if (modo !== 'stripe') return;

    if (esContratante && ['esperando_cobro_cliente', 'checkout_activo'].includes(estadoPago)) {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'encargo-card-btn stripe-pagar-btn';
      btn.textContent = 'Pagar ahora';
      btn.addEventListener('click', () => {
        iniciarPagoStripe(host, contacto.id).catch((e) => alert(e.message));
      });
      container.appendChild(btn);
    }

    if (esContratante && estadoPago === 'cobro_confirmado') {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'encargo-card-btn stripe-confirmar-btn';
      btn.textContent = 'Confirmar trabajo realizado';
      btn.addEventListener('click', () => {
        confirmarTrabajoStripe(host, contacto.id).catch((e) => alert(e.message));
      });
      container.appendChild(btn);
    }
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
    isStripeConectado,
    labelEstadoPago,
    MSG_PAGO_NO_DISPONIBLE,
  };
})(window);
