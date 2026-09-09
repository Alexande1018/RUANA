/**
 * RUANA Admin — estado territorial por código postal y comprobación de migración.
 */
(function (global) {
  'use strict';

  var modules = global.RuanaAdminModules = global.RuanaAdminModules || {};

  function esc(s) {
    if (global.RuanaUi && typeof global.RuanaUi.escapeHtml === 'function') {
      return global.RuanaUi.escapeHtml(s);
    }
    var d = document.createElement('div');
    d.textContent = s == null ? '' : String(s);
    return d.innerHTML;
  }

  function authHeaders() {
    if (global.AdminAuthenticator && typeof global.AdminAuthenticator.getAdminAuthHeaders === 'function') {
      return global.AdminAuthenticator.getAdminAuthHeaders();
    }
    return {};
  }

  function renderMigracion(data) {
    var wrap = document.getElementById('territorio-migracion-resumen');
    var tbody = document.getElementById('tbody-territorio-migracion');
    var filas = (data && data.sin_grupo_territorial_valido) || [];
    var total = data && data.total != null ? data.total : filas.length;
    if (wrap) {
      wrap.innerHTML = '<div class="grupos-cp-card"><h4>Comprobación</h4>' +
        '<div class="grupos-cp-meta">' + esc(total) + ' aliados sin grupo territorial válido</div></div>';
    }
    if (!tbody) return;
    if (!filas.length) {
      tbody.innerHTML = '<tr><td colspan="6" style="color:#94a3b8;">Todos los aliados activos tienen grupo territorial.</td></tr>';
      return;
    }
    tbody.innerHTML = filas.map(function (a) {
      return '<tr>' +
        '<td>' + esc(a.codigo) + '</td>' +
        '<td>' + esc(a.nombre) + '</td>' +
        '<td>' + esc(a.codigo_postal) + '</td>' +
        '<td>' + esc(a.oficio) + '</td>' +
        '<td>' + esc(a.estado) + '</td>' +
        '<td>' + esc(a.grupo_id || '—') + '</td></tr>';
    }).join('');
  }

  function renderEstado(data) {
    var tbody = document.getElementById('tbody-territorio-estado');
    if (!tbody) return;
    var list = (data && data.aliados) || [];
    if (!list.length) {
      tbody.innerHTML = '<tr><td colspan="6" style="color:#94a3b8;">Sin aliados territoriales.</td></tr>';
      return;
    }
    tbody.innerHTML = list.map(function (a) {
      return '<tr>' +
        '<td>' + esc(a.codigo) + '</td>' +
        '<td>' + esc(a.nombre) + '</td>' +
        '<td>' + esc(a.codigo_postal) + '</td>' +
        '<td>' + esc(a.grupo_nombre || a.grupo_id || '—') + '</td>' +
        '<td>' + esc(a.grupo_tipo || 'territorial') + '</td>' +
        '<td>' + esc(a.estado) + '</td></tr>';
    }).join('');
  }

  function refresh() {
    return Promise.all([
      fetch('/api/admin/territorio/migracion-check', { credentials: 'same-origin', headers: authHeaders() })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (d) { if (d && d.status === 'success') renderMigracion(d); }),
      fetch('/api/admin/territorio/estado', { credentials: 'same-origin', headers: authHeaders() })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (d) { if (d && d.status === 'success') renderEstado(d); })
    ]);
  }

  modules.territorio = {
    refresh: refresh,
    renderMigracion: renderMigracion,
    renderEstado: renderEstado
  };
})(typeof window !== 'undefined' ? window : globalThis);
