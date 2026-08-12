/**
 * Módulo PrivatePanel `referidos` (Campamento Base).
 * Modal de hijos directos del linaje (/api/aliado/linaje/hijos).
 * PrivatePanel conserva fachadas delgadas que delegan aquí.
 * El árbol genealógico compartido vive en referidos-module.js (RuanaReferidos).
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
    if (global.RuanaReferidos && typeof global.RuanaReferidos.escapeHtml === 'function') {
      return global.RuanaReferidos.escapeHtml(str);
    }
    if (str == null) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  /**
   * Abre el modal de referidos directos y carga /api/aliado/linaje/hijos.
   * @param {object} host PrivatePanel (escapeHtml opcional)
   */
  function abrirModalLinajeHijos(host) {
    var modal = document.getElementById('modal-linaje-hijos');
    var list = document.getElementById('modal-linaje-hijos-list');
    var meta = document.getElementById('modal-linaje-hijos-meta');
    if (!modal || !list) return Promise.resolve();
    list.innerHTML = '<p style="color:#94a3b8;">Cargando…</p>';
    if (meta) meta.textContent = 'Tus invitaciones directas';
    modal.style.display = 'flex';
    var apiBase = getApiBaseSafe();
    return fetch(apiBase + '/api/aliado/linaje/hijos', {
      credentials: 'same-origin',
      headers: getAuthHeadersSafe(),
    })
      .then(function (resp) {
        return resp.json().then(function (data) {
          return { resp: resp, data: data };
        });
      })
      .then(function (result) {
        var resp = result.resp;
        var data = result.data;
        if (!resp.ok || data.status !== 'success') {
          list.innerHTML = '<p style="color:#f87171;">No se pudieron cargar tus referidos.</p>';
          return;
        }
        var hijos = Array.isArray(data.hijos) ? data.hijos : [];
        if (meta) {
          meta.textContent = hijos.length === 0
            ? 'Aún no has referido aliados a RUANA.'
            : (hijos.length + ' referido' + (hijos.length === 1 ? '' : 's') + ' directo' + (hijos.length === 1 ? '' : 's'));
        }
        if (!hijos.length) {
          list.innerHTML = '<p style="color:#94a3b8;">Cuando alguien se registre con tu invitación, aparecerá aquí.</p>';
          return;
        }
        list.innerHTML = hijos.map(function (h) {
          var nombre = escapeHtmlSafe(host, h.nombre || '(sin nombre)');
          var codigo = escapeHtmlSafe(host, h.codigo || '');
          var oficio = escapeHtmlSafe(host, h.oficio || '—');
          var zona = escapeHtmlSafe(host, h.zona || h.codigo_postal || '—');
          return '<div style="border:1px solid rgba(255,255,255,0.1); border-radius:10px; padding:10px 12px; margin-bottom:8px;">' +
            '<div style="font-weight:600;">' + nombre + '</div>' +
            '<div style="font-size:0.85rem; color:#94a3b8; margin-top:2px;">' + codigo + ' · ' + oficio + ' · ' + zona + '</div>' +
            '</div>';
        }).join('');
      })
      .catch(function () {
        list.innerHTML = '<p style="color:#f87171;">Error de red al cargar referidos.</p>';
      });
  }

  function cerrarModalLinajeHijos() {
    var modal = document.getElementById('modal-linaje-hijos');
    if (modal) modal.style.display = 'none';
  }

  modules.referidos = {
    abrirModalLinajeHijos: abrirModalLinajeHijos,
    cerrarModalLinajeHijos: cerrarModalLinajeHijos,
  };
})(typeof window !== 'undefined' ? window : globalThis);
