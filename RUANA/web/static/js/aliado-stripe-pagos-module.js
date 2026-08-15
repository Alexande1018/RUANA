/**
 * Pagos Stripe Connect en panel aliado (checkout + confirmación por contratante).
 */
(function (global) {
  'use strict';

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
    window.location.href = data.checkout_url;
  }

  async function confirmarTrabajoStripe(host, contactoId) {
    if (!window.confirm('¿Confirmas que el trabajo se realizó correctamente? Se liberará el pago al profesional.')) {
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
    window.location.href = data.onboarding_url;
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

  global.RuanaStripePagos = {
    iniciarPagoStripe,
    confirmarTrabajoStripe,
    iniciarOnboardingStripe,
    renderStripeAcciones,
  };
})(window);
