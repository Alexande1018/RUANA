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
    const msg = data.estado_pago === 'transferido'
      ? `Pago completado. Se transfirieron ${netoTxt} a la cuenta del profesional.`
      : `Trabajo confirmado. RUANA está transfiriendo ${netoTxt} a la cuenta Stripe del profesional.`;
    if (typeof global.RuanaUI !== 'undefined' && global.RuanaUI.success) {
      global.RuanaUI.success(msg);
    } else {
      alert(msg);
    }
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
    const desglose = desgloseStripeHtml(contacto);
    const enTransferencia = transferenciaStripeEnCurso(contacto);
    const transferido = transferenciaStripeCompletada(contacto);

    if (esProfesional) {
      if (['esperando_cobro_cliente', 'checkout_activo', 'no_generado'].includes(estadoPago)) {
        parts.push(
          '<p class="stripe-estado-msg stripe-estado-msg--pro">'
          + 'Tu pago quedará retenido hasta que el contratante pague. '
          + 'Después se liberará cuando confirme que el trabajo quedó hecho.</p>'
        );
      } else if (transferido) {
        const netoTxt = formatEuros(contacto.importe_neto_profesional) || 'tu importe neto';
        parts.push(
          '<p class="stripe-estado-msg stripe-estado-msg--ok">'
          + `Pago transferido a tu cuenta Stripe (${escapeHtml(netoTxt)}). `
          + 'Puede tardar 1–2 días hábiles en verse en tu banco.</p>'
        );
        if (desglose) parts.push(desglose);
      } else if (enTransferencia || estadoPago === 'transfer_pendiente') {
        const netoTxt = formatEuros(contacto.importe_neto_profesional) || 'tu importe neto';
        parts.push(
          '<p class="stripe-estado-msg stripe-estado-msg--ok">'
          + 'El contratante confirmó el trabajo. RUANA está transfiriendo '
          + `<strong>${escapeHtml(netoTxt)}</strong> a tu cuenta Stripe Connect.</p>`
        );
        if (desglose) parts.push(desglose);
      } else if (estadoPago === 'cobro_confirmado') {
        parts.push(
          '<p class="stripe-estado-msg stripe-estado-msg--pro">'
          + 'El contratante ya pagó. Tu importe está retenido y se liberará '
          + 'cuando confirme que el trabajo quedó hecho.</p>'
        );
        if (desglose) parts.push(desglose);
      }
    }

    if (esContratante) {
      const contactoEstado = String(contacto.estado || '').trim();
      const puedeIniciarPago = ['esperando_cobro_cliente', 'checkout_activo', 'no_generado', ''].includes(estadoPago)
        && !enTransferencia && !transferido
        && contactoEstado === 'pendiente_de_pago';
      if (puedeIniciarPago) {
        parts.push(
          `<p class="stripe-estado-msg">${importeTxt
            ? `Importe acordado: <strong>${escapeHtml(importeTxt)}</strong>. `
            : ''}Completa el pago para reservar el encargo.</p>`
          + '<button type="button" class="encargo-card-btn stripe-pagar-btn">Ir a pagar</button>'
        );
      } else if (transferido) {
        parts.push(
          '<p class="stripe-estado-msg stripe-estado-msg--ok">'
          + 'Confirmaste la entrega y el pago al profesional se completó.</p>'
        );
        if (desglose) parts.push(desglose);
      } else if (enTransferencia || estadoPago === 'transfer_pendiente') {
        parts.push(
          '<p class="stripe-estado-msg stripe-estado-msg--ok">'
          + 'Confirmaste la entrega. El pago al profesional está en proceso en Stripe.</p>'
        );
        if (desglose) parts.push(desglose);
      } else if (estadoPago === 'cobro_confirmado') {
        parts.push(
          '<p class="stripe-estado-msg">Pago realizado. Confirma que el trabajo quedó hecho '
          + 'para liberar el importe al profesional.</p>'
          + '<button type="button" class="encargo-card-btn stripe-confirmar-btn">'
          + 'Confirmar trabajo y liberar pago</button>'
        );
        if (desglose) parts.push(desglose);
      }
    }

    container.innerHTML = parts.join('');
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
