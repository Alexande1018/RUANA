/**
 * Módulo PrivatePanel `centroComunicacion` (Campamento Base).
 * Overlay FAB de soporte: hilos, mensajes, envío y respuesta.
 * PrivatePanel conserva fachadas delgadas que delegan aquí.
 * fetchCentroComunicacionSnapshot puede vivir en el host (sync) o aquí.
 */
(function (global) {
  'use strict';

  var modules = global.RuanaAliadoModules = global.RuanaAliadoModules || {
    inicio: null,
    directorio: null,
    solicitudes: null,
    conexiones: null,
    perfil: null,
    referidos: null,
    acuerdos: null,
    centroComunicacion: null,
  };

  function getApiBaseSafe() {
    if (typeof global.getApiBase === 'function') return global.getApiBase();
    return '';
  }

  function getAuthHeadersSafe(extra) {
    if (typeof global.getRuanaAuthHeaders === 'function') {
      return global.getRuanaAuthHeaders(extra || {});
    }
    return extra || {};
  }

  function escapeHtmlSafe(host, str) {
    if (host && typeof host.escapeHtml === 'function') {
      return host.escapeHtml(str);
    }
    if (str == null || str === '') return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function formatHelpStatus(estado) {
    var key = String(estado || 'pendiente').toLowerCase();
    var labels = {
      pendiente: 'Pendiente',
      en_revision: 'En revisión',
      respondido: 'Respondido',
      cerrado: 'Cerrado',
      reabierto: 'Reabierto'
    };
    return labels[key] || 'Pendiente';
  }

  function abrirCentroComunicacion(host) {
    var overlay = document.getElementById('ruana-help-overlay');
    var fab = document.getElementById('ruana-help-fab');
    if (!overlay) return;
    overlay.classList.add('is-open');
    overlay.setAttribute('aria-hidden', 'false');
    if (fab) fab.classList.add('is-open');
    renderCentroComunicacion(host);
    var subject = document.getElementById('ruana-help-subject');
    if (subject) setTimeout(function () { subject.focus(); }, 220);
  }

  function cerrarCentroComunicacion() {
    var overlay = document.getElementById('ruana-help-overlay');
    var fab = document.getElementById('ruana-help-fab');
    if (!overlay) return;
    overlay.classList.remove('is-open');
    overlay.setAttribute('aria-hidden', 'true');
    if (fab) fab.classList.remove('is-open');
  }

  function toggleCentroComunicacion(host) {
    var overlay = document.getElementById('ruana-help-overlay');
    if (!overlay) return;
    if (overlay.classList.contains('is-open')) cerrarCentroComunicacion();
    else abrirCentroComunicacion(host);
  }

  function renderMensajesCentroComunicacion(host) {
    if (!host) return;
    var box = document.getElementById('ruana-help-messages');
    var header = document.getElementById('ruana-help-thread-header');
    var reply = document.getElementById('ruana-help-reply');
    var replyBtn = document.getElementById('ruana-help-reply-btn');
    if (!box || !header || !reply || !replyBtn) return;
    var conv = (host.soporteConversations || []).find(function (c) {
      return Number(c.id) === Number(host.soporteSelectedId);
    });
    if (!conv) {
      header.textContent = 'Selecciona una conversación para ver el historial.';
      box.innerHTML = '';
      reply.disabled = true;
      replyBtn.disabled = true;
      return;
    }
    header.innerHTML = '<strong>' + escapeHtmlSafe(host, conv.asunto || 'Consulta') + '</strong> · <span class="ruana-help-status estado-' + escapeHtmlSafe(host, conv.estado || 'pendiente') + '">' + formatHelpStatus(conv.estado) + '</span>';
    reply.disabled = false;
    replyBtn.disabled = false;
    var mensajes = Array.isArray(host.soporteMensajes) ? host.soporteMensajes : [];
    box.innerHTML = mensajes.map(function (m) {
      var fromAdmin = (m.emisor_tipo || '') === 'admin';
      var fecha = m.creado_en ? new Date(m.creado_en).toLocaleString('es-ES', { dateStyle: 'short', timeStyle: 'short' }) : '';
      return '<div class="ruana-help-message ' + (fromAdmin ? 'from-admin' : 'from-aliado') + '">' +
        escapeHtmlSafe(host, m.mensaje || '') +
        '<span class="ruana-help-meta">' + (fromAdmin ? 'Equipo RUANA' : 'Tú') + ' · ' + fecha + '</span>' +
      '</div>';
    }).join('');
    box.scrollTop = box.scrollHeight;
  }

  /**
   * Pinta hilos del centro de comunicación y badge FAB.
   * @param {object} host PrivatePanel
   */
  function renderCentroComunicacion(host) {
    if (!host) return;
    var list = document.getElementById('ruana-help-threads');
    var unreadPill = document.getElementById('ruana-help-unread-pill');
    var fabBadge = document.getElementById('ruana-help-fab-badge');
    if (!list || !unreadPill) return;
    var conversaciones = Array.isArray(host.soporteConversations) ? host.soporteConversations : [];
    var unreadCount = conversaciones.filter(function (c) {
      return Number(c.tiene_no_leido_aliado || 0) > 0;
    }).length;
    unreadPill.textContent = unreadCount + ' sin leer';
    if (fabBadge) {
      fabBadge.textContent = String(unreadCount);
      fabBadge.classList.toggle('is-visible', unreadCount > 0);
    }
    if (!conversaciones.length) {
      list.innerHTML = '<div class="ruana-help-empty">Aún no tienes conversaciones. Escríbenos y te respondemos por aquí.</div>';
      renderMensajesCentroComunicacion(host);
      return;
    }
    list.innerHTML = conversaciones.map(function (c) {
      var active = Number(c.id) === Number(host.soporteSelectedId) ? ' is-active' : '';
      var hasUnread = Number(c.tiene_no_leido_aliado || 0) > 0 ? ' has-unread' : '';
      var fecha = c.ultimo_mensaje_en ? new Date(c.ultimo_mensaje_en).toLocaleString('es-ES', { dateStyle: 'short', timeStyle: 'short' }) : '';
      return '<div class="ruana-help-thread-item' + active + hasUnread + '" data-conv-id="' + c.id + '">' +
        '<div style="display:flex;justify-content:space-between;gap:8px;align-items:center;">' +
          '<strong style="font-size:0.85rem;">' + escapeHtmlSafe(host, c.asunto || 'Consulta') + '</strong>' +
          '<span class="ruana-help-status estado-' + escapeHtmlSafe(host, c.estado || 'pendiente') + '">' + formatHelpStatus(c.estado) + '</span>' +
        '</div>' +
        '<div style="color:#cbd5e1;font-size:0.8rem;margin-top:6px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">' + escapeHtmlSafe(host, c.ultimo_mensaje_preview || 'Sin mensajes') + '</div>' +
        '<div class="ruana-help-meta">' + fecha + '</div>' +
      '</div>';
    }).join('');
    list.querySelectorAll('[data-conv-id]').forEach(function (el) {
      el.addEventListener('click', function () {
        seleccionarConversacionSoporte(host, el.getAttribute('data-conv-id'));
      });
    });
    renderMensajesCentroComunicacion(host);
  }

  function seleccionarConversacionSoporte(host, conversacionId) {
    if (!host) return Promise.resolve();
    var codigo = host.codigoAliado || (host.aliado && host.aliado.codigo) || '';
    if (!codigo || !conversacionId) return Promise.resolve();
    host.soporteSelectedId = Number(conversacionId);
    var apiBase = getApiBaseSafe();
    return fetch(apiBase + '/api/aliados/' + encodeURIComponent(codigo) + '/centro-comunicacion/' + Number(conversacionId) + '/mensajes', {
      credentials: 'same-origin',
      headers: getAuthHeadersSafe()
    })
      .then(function (r) { return r.json().catch(function () { return {}; }); })
      .then(function (data) {
        host.soporteMensajes = data.status === 'success' && Array.isArray(data.mensajes) ? data.mensajes : [];
        return fetch(apiBase + '/api/aliados/' + encodeURIComponent(codigo) + '/centro-comunicacion/' + Number(conversacionId) + '/marcar-leida', {
          method: 'POST',
          credentials: 'same-origin',
          headers: getAuthHeadersSafe()
        }).catch(function () { return null; });
      })
      .then(function () {
        if (typeof host.fetchCentroComunicacionSnapshot === 'function') {
          return host.fetchCentroComunicacionSnapshot();
        }
        return null;
      })
      .then(function () {
        renderCentroComunicacion(host);
      });
  }

  function enviarNuevoMensajeSoporte(host) {
    if (!host) return Promise.resolve();
    var codigo = host.codigoAliado || (host.aliado && host.aliado.codigo) || '';
    if (!codigo) return Promise.resolve();
    var asuntoEl = document.getElementById('ruana-help-subject');
    var categoriaEl = document.getElementById('ruana-help-category');
    var mensajeEl = document.getElementById('ruana-help-message');
    if (!asuntoEl || !mensajeEl || !categoriaEl) return Promise.resolve();
    var asunto = (asuntoEl.value || '').trim();
    var mensaje = (mensajeEl.value || '').trim();
    if (!asunto || !mensaje) {
      if (global.RuanaUI) global.RuanaUI.toast('Completa asunto y mensaje.', 'warning');
      return Promise.resolve();
    }
    var apiBase = getApiBaseSafe();
    return fetch(apiBase + '/api/aliados/' + encodeURIComponent(codigo) + '/centro-comunicacion', {
      method: 'POST',
      credentials: 'same-origin',
      headers: getAuthHeadersSafe({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ asunto: asunto, categoria: categoriaEl.value || 'consulta', mensaje: mensaje })
    })
      .then(function (r) { return r.json().catch(function () { return {}; }); })
      .then(function (data) {
        if (data.status !== 'success') {
          if (global.RuanaUI) global.RuanaUI.toast(data.message || 'No se pudo enviar el mensaje.', 'error');
          return null;
        }
        asuntoEl.value = '';
        mensajeEl.value = '';
        if (global.RuanaUI) global.RuanaUI.toast('Tu mensaje fue enviado. ✅', 'success');
        var convId = Number(data.conversacion_id || 0) || host.soporteSelectedId;
        var chain = typeof host.fetchCentroComunicacionSnapshot === 'function'
          ? host.fetchCentroComunicacionSnapshot()
          : Promise.resolve();
        return chain.then(function () {
          host.soporteSelectedId = convId;
          if (host.soporteSelectedId) {
            return seleccionarConversacionSoporte(host, host.soporteSelectedId);
          }
          renderCentroComunicacion(host);
        });
      });
  }

  function responderConversacionSoporte(host) {
    if (!host) return Promise.resolve();
    var codigo = host.codigoAliado || (host.aliado && host.aliado.codigo) || '';
    var convId = Number(host.soporteSelectedId || 0);
    if (!codigo || !convId) return Promise.resolve();
    var replyEl = document.getElementById('ruana-help-reply');
    if (!replyEl) return Promise.resolve();
    var mensaje = (replyEl.value || '').trim();
    if (!mensaje) return Promise.resolve();
    var apiBase = getApiBaseSafe();
    return fetch(apiBase + '/api/aliados/' + encodeURIComponent(codigo) + '/centro-comunicacion/' + convId + '/mensajes', {
      method: 'POST',
      credentials: 'same-origin',
      headers: getAuthHeadersSafe({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ mensaje: mensaje })
    })
      .then(function (r) { return r.json().catch(function () { return {}; }); })
      .then(function (data) {
        if (data.status !== 'success') {
          if (global.RuanaUI) global.RuanaUI.toast(data.message || 'No se pudo responder.', 'error');
          return null;
        }
        replyEl.value = '';
        if (global.RuanaUI) global.RuanaUI.toast('Respuesta enviada al equipo RUANA. 💬', 'success');
        return seleccionarConversacionSoporte(host, convId);
      });
  }

  function render(host) {
    renderCentroComunicacion(host);
  }

  function refresh(host) {
    renderCentroComunicacion(host);
  }

  modules.centroComunicacion = {
    render: render,
    refresh: refresh,
    formatHelpStatus: formatHelpStatus,
    abrirCentroComunicacion: abrirCentroComunicacion,
    cerrarCentroComunicacion: cerrarCentroComunicacion,
    toggleCentroComunicacion: toggleCentroComunicacion,
    renderCentroComunicacion: renderCentroComunicacion,
    renderMensajesCentroComunicacion: renderMensajesCentroComunicacion,
    seleccionarConversacionSoporte: seleccionarConversacionSoporte,
    enviarNuevoMensajeSoporte: enviarNuevoMensajeSoporte,
    responderConversacionSoporte: responderConversacionSoporte,
  };
})(typeof window !== 'undefined' ? window : globalThis);
