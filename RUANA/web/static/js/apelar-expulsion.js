/**
 * Arranque de /apelar/<token>: valida el token y reutiliza el FAB de soporte.
 */
(function (global) {
  'use strict';

  var MENSAJE_GENERICO = 'Este enlace no es válido o el plazo de apelación ha vencido.';

  function tokenDesdeRuta() {
    var partes = (location.pathname || '').split('/').filter(Boolean);
    var idx = partes.indexOf('apelar');
    if (idx < 0 || !partes[idx + 1]) return '';
    try {
      return decodeURIComponent(partes[idx + 1]);
    } catch (_) {
      return partes[idx + 1];
    }
  }

  function mostrarError(texto) {
    var el = document.getElementById('apelar-estado');
    if (!el) return;
    el.hidden = false;
    el.textContent = texto || MENSAJE_GENERICO;
  }

  function escapeHtml(str) {
    if (str == null || str === '') return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function arrancar() {
    var token = tokenDesdeRuta();
    var mod = global.RuanaAliadoModules && global.RuanaAliadoModules.centroComunicacion;
    if (!mod) {
      mostrarError(MENSAJE_GENERICO);
      return;
    }
    fetch('/api/apelar/' + encodeURIComponent(token), { credentials: 'same-origin' })
      .then(function (r) { return r.json().catch(function () { return {}; }); })
      .then(function (data) {
        if (!data || data.status !== 'success') {
          mostrarError(MENSAJE_GENERICO);
          return;
        }
        var host = {
          soporteToken: token,
          soporteConversations: [],
          soporteSelectedId: Number(data.conversacion_id || 0),
          soporteMensajes: [],
          escapeHtml: escapeHtml,
          fetchCentroComunicacionSnapshot: function () {
            return fetch('/api/apelar/' + encodeURIComponent(token) + '/centro-comunicacion', {
              credentials: 'same-origin'
            })
              .then(function (r) { return r.json().catch(function () { return {}; }); })
              .then(function (d) {
                host.soporteConversations = d.status === 'success' && Array.isArray(d.conversaciones)
                  ? d.conversaciones
                  : [];
              });
          }
        };
        global.RUANA_APELACION_TOKEN = token;
        mod.ensureHelpWidget();
        var fab = document.getElementById('ruana-help-fab');
        var closeBtn = document.getElementById('ruana-help-close');
        var overlay = document.getElementById('ruana-help-overlay');
        var replyBtn = document.getElementById('ruana-help-reply-btn');
        if (fab) fab.addEventListener('click', function () { mod.toggleCentroComunicacion(host); });
        if (closeBtn) closeBtn.addEventListener('click', function () { mod.cerrarCentroComunicacion(); });
        if (overlay) {
          overlay.addEventListener('click', function (ev) {
            if (ev.target === overlay) mod.cerrarCentroComunicacion();
          });
        }
        if (replyBtn) replyBtn.addEventListener('click', function () { mod.responderConversacionSoporte(host); });
        host.fetchCentroComunicacionSnapshot().then(function () {
          if (host.soporteSelectedId) {
            return mod.seleccionarConversacionSoporte(host, host.soporteSelectedId);
          }
          mod.renderCentroComunicacion(host);
        }).then(function () {
          mod.abrirCentroComunicacion(host);
        });
      })
      .catch(function () {
        mostrarError(MENSAJE_GENERICO);
      });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', arrancar);
  } else {
    arrancar();
  }
})(typeof window !== 'undefined' ? window : globalThis);
