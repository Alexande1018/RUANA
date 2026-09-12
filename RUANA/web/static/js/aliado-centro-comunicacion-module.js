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

  function soporteToken(host) {
    if (host && host.soporteToken) return String(host.soporteToken);
    if (global.RUANA_APELACION_TOKEN) return String(global.RUANA_APELACION_TOKEN);
    return '';
  }

  function soporteEnModoToken(host) {
    return Boolean(soporteToken(host));
  }

  function soporteHeaders(host, extra) {
    if (soporteEnModoToken(host)) {
      return extra || {};
    }
    return getAuthHeadersSafe(extra);
  }

  function soporteUrls(host, conversacionId) {
    var token = soporteToken(host);
    if (token) {
      var tokenBase = '/api/apelar/' + encodeURIComponent(token) + '/centro-comunicacion';
      return {
        list: tokenBase,
        create: tokenBase,
        messages: tokenBase + '/' + Number(conversacionId) + '/mensajes',
        markRead: tokenBase + '/' + Number(conversacionId) + '/marcar-leida'
      };
    }
    var codigo = (host && (host.codigoAliado || (host.aliado && host.aliado.codigo))) || '';
    var aliadoBase = '/api/aliados/' + encodeURIComponent(codigo) + '/centro-comunicacion';
    return {
      list: aliadoBase,
      create: aliadoBase,
      messages: aliadoBase + '/' + Number(conversacionId) + '/mensajes',
      markRead: aliadoBase + '/' + Number(conversacionId) + '/marcar-leida'
    };
  }

  function applyTokenModeUi(host) {
    var nuevo = document.getElementById('ruana-help-new-wrap');
    if (nuevo) nuevo.hidden = soporteEnModoToken(host);
    var sub = document.getElementById('ruana-help-sub');
    if (sub && soporteEnModoToken(host)) {
      sub.textContent = 'Escribe tu apelación aquí. Tienes 5 días hábiles desde la notificación de expulsión.';
    }
  }

  function ensureHelpWidget() {
    if (document.getElementById('ruana-help-fab')) return;
    var mount = document.getElementById('ruana-help-mount') || document.body;
    var wrap = document.createElement('div');
    wrap.innerHTML =
      '<button type="button" class="ruana-help-fab" id="ruana-help-fab" aria-label="Hablar con el equipo de RUANA" title="Hablar con RUANA">' +
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>' +
        '<span class="ruana-help-fab-badge" id="ruana-help-fab-badge" aria-hidden="true">0</span>' +
      '</button>' +
      '<div class="ruana-help-overlay" id="ruana-help-overlay" aria-hidden="true">' +
        '<section class="ruana-help-center" id="ruana-help-center" role="dialog" aria-modal="true" aria-labelledby="ruana-help-title">' +
          '<div class="ruana-help-header">' +
            '<h2 class="ruana-help-title" id="ruana-help-title">Habla con el equipo de RUANA</h2>' +
            '<div class="ruana-help-header-actions">' +
              '<span class="ruana-help-pill" id="ruana-help-unread-pill">0 sin leer</span>' +
              '<button type="button" class="ruana-help-close" id="ruana-help-close" aria-label="Cerrar">✕</button>' +
            '</div>' +
          '</div>' +
          '<p class="ruana-help-sub" id="ruana-help-sub">Consultas, incidencias e ideas.</p>' +
          '<div class="ruana-help-layout">' +
            '<div class="ruana-help-card" id="ruana-help-new-wrap">' +
              '<h3 style="margin:0 0 10px;">Nuevo mensaje</h3>' +
              '<div class="ruana-help-form-row">' +
                '<input id="ruana-help-subject" class="ruana-help-input" maxlength="160" placeholder="Asunto" />' +
                '<select id="ruana-help-category" class="ruana-help-select">' +
                  '<option value="consulta">Consulta</option>' +
                '</select>' +
                '<textarea id="ruana-help-message" class="ruana-help-textarea" rows="4" maxlength="3000"></textarea>' +
                '<button type="button" class="btn-admin-action" id="ruana-help-send-btn">Enviar al equipo RUANA</button>' +
              '</div>' +
            '</div>' +
            '<div class="ruana-help-card">' +
              '<h3 style="margin:0 0 8px;">Conversación</h3>' +
              '<div class="ruana-help-list" id="ruana-help-threads"></div>' +
            '</div>' +
            '<div class="ruana-help-card">' +
              '<div id="ruana-help-thread-header" class="ruana-help-empty">Selecciona una conversación para ver el historial.</div>' +
              '<div class="ruana-help-messages" id="ruana-help-messages"></div>' +
              '<div class="ruana-help-form-row">' +
                '<textarea id="ruana-help-reply" class="ruana-help-textarea" rows="3" maxlength="3000" placeholder="Escribe tu apelación..." disabled></textarea>' +
                '<button type="button" class="btn-admin-action" id="ruana-help-reply-btn" disabled>Enviar apelación</button>' +
              '</div>' +
            '</div>' +
          '</div>' +
        '</section>' +
      '</div>';
    mount.appendChild(wrap);
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
    ensureHelpWidget();
    applyTokenModeUi(host);
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
    applyTokenModeUi(host);
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
    if ((!codigo && !soporteEnModoToken(host)) || !conversacionId) return Promise.resolve();
    host.soporteSelectedId = Number(conversacionId);
    var apiBase = getApiBaseSafe();
    var urls = soporteUrls(host, conversacionId);
    return fetch(apiBase + urls.messages, {
      credentials: 'same-origin',
      headers: soporteHeaders(host)
    })
      .then(function (r) { return r.json().catch(function () { return {}; }); })
      .then(function (data) {
        host.soporteMensajes = data.status === 'success' && Array.isArray(data.mensajes) ? data.mensajes : [];
        return fetch(apiBase + urls.markRead, {
          method: 'POST',
          credentials: 'same-origin',
          headers: soporteHeaders(host)
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
    if (soporteEnModoToken(host)) {
      return responderConversacionSoporte(host);
    }
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
    var urls = soporteUrls(host);
    return fetch(apiBase + urls.create, {
      method: 'POST',
      credentials: 'same-origin',
      headers: soporteHeaders(host, { 'Content-Type': 'application/json' }),
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
    if ((!codigo && !soporteEnModoToken(host)) || !convId) return Promise.resolve();
    var replyEl = document.getElementById('ruana-help-reply');
    if (!replyEl) return Promise.resolve();
    var mensaje = (replyEl.value || '').trim();
    if (!mensaje) return Promise.resolve();
    var apiBase = getApiBaseSafe();
    var urls = soporteUrls(host, convId);
    return fetch(apiBase + urls.messages, {
      method: 'POST',
      credentials: 'same-origin',
      headers: soporteHeaders(host, { 'Content-Type': 'application/json' }),
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
    ensureHelpWidget: ensureHelpWidget,
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
