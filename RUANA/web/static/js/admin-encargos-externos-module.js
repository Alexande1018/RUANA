/**
 * RUANA Admin — Encargos de RUANA (clientes de anuncios externos, sin cobro).
 * Módulo autónomo: no modifica otros módulos ni APIs existentes.
 */
(function (global) {
  'use strict';

  var modules = global.RuanaAdminModules = global.RuanaAdminModules || {};
  var ESTADOS = { creado: 'Creado', aceptado: 'Aceptado', hecho: 'Hecho', rechazado: 'Rechazado' };
  var cargando = false;

  function esc(s) {
    if (global.RuanaUi && typeof global.RuanaUi.escapeHtml === 'function') {
      return global.RuanaUi.escapeHtml(s);
    }
    var d = document.createElement('div');
    d.textContent = s == null ? '' : String(s);
    return d.innerHTML;
  }

  function authHeaders(extra) {
    var base = Object.assign({}, extra || {});
    /* global AdminAuthenticator */
    if (typeof AdminAuthenticator !== 'undefined' && typeof AdminAuthenticator.getAdminAuthHeaders === 'function') {
      return AdminAuthenticator.getAdminAuthHeaders(base);
    }
    try {
      var sid = global.sessionStorage && global.sessionStorage.getItem('admin_session_id');
      if (sid) base['X-Ruana-Session-Id'] = sid;
    } catch (e) { /* ignore */ }
    return base;
  }

  function fecha(v) {
    if (!v) return '—';
    var d = new Date(String(v).replace(' ', 'T') + (/[zZ]|[+-]\d\d:?\d\d$/.test(String(v)) ? '' : 'Z'));
    if (isNaN(d.getTime())) return esc(v);
    return d.toLocaleString('es-ES', { dateStyle: 'short', timeStyle: 'short', timeZone: 'Europe/Madrid' });
  }

  function precio(v) {
    if (v == null || v === '') return '—';
    var n = Number(v);
    return isNaN(n) ? esc(v) : n.toLocaleString('es-ES', { style: 'currency', currency: 'EUR' });
  }

  function render(data) {
    var conteos = (data && data.conteos) || {};
    Object.keys(ESTADOS).forEach(function (k) {
      var el = document.querySelector('[data-ee-conteo="' + k + '"]');
      if (el) el.textContent = String(conteos[k] || 0);
    });
    var tbody = document.getElementById('tbody-encargos-externos');
    var empty = document.getElementById('encargos-externos-empty');
    if (!tbody) return;
    var list = (data && data.encargos) || [];
    if (empty) empty.style.display = list.length ? 'none' : 'block';
    tbody.innerHTML = list.map(function (e) {
      var contacto = [e.cliente_telefono, e.cliente_email].filter(Boolean).map(esc).join('<br>');
      var estado = esc(ESTADOS[e.estado] || e.estado);
      if (e.estado === 'rechazado' && e.motivo_rechazo) {
        estado += '<br><small style="color:#999;">' + esc(e.motivo_rechazo) + '</small>';
      }
      return '<tr>' +
        '<td>' + esc(e.id) + '</td>' +
        '<td>' + fecha(e.created_at) + '</td>' +
        '<td>' + esc(e.aliado_nombre || '') + ' <small style="color:#999;">' + esc(e.aliado_codigo) + '</small></td>' +
        '<td>' + esc(e.cliente_nombre) + '</td>' +
        '<td>' + (contacto || '—') + '</td>' +
        '<td>' + esc(e.codigo_postal) + '</td>' +
        '<td style="max-width:280px; white-space:normal;">' + esc(e.descripcion) + '</td>' +
        '<td>' + esc(e.origen_anuncio || '—') + '</td>' +
        '<td>' + precio(e.precio_orientativo) + '</td>' +
        '<td>' + estado + '</td></tr>';
    }).join('');
  }

  function refresh() {
    if (cargando) return Promise.resolve();
    cargando = true;
    var sel = document.getElementById('filtro-encargos-externos-estado');
    var estado = sel ? sel.value : '';
    var url = '/api/admin/encargos-externos' + (estado ? '?estado=' + encodeURIComponent(estado) : '');
    return fetch(url, { credentials: 'same-origin', headers: authHeaders() })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) { if (d && d.status === 'success') render(d); })
      .catch(function () { /* el panel sigue funcionando aunque falle esta lista */ })
      .then(function () { cargando = false; });
  }

  function crear(ev) {
    ev.preventDefault();
    var form = ev.target;
    var msg = document.getElementById('encargo-externo-form-msg');
    var btn = document.getElementById('btn-crear-encargo-externo');
    var datos = {};
    Array.prototype.forEach.call(form.elements, function (el) {
      if (el.name) datos[el.name] = (el.value || '').trim();
    });
    if (!datos.cliente_telefono && !datos.cliente_email) {
      if (msg) { msg.style.color = '#f87171'; msg.textContent = 'Pon al menos un teléfono o un email del cliente.'; }
      return;
    }
    if (btn) btn.disabled = true;
    if (msg) { msg.style.color = '#999'; msg.textContent = 'Guardando…'; }
    fetch('/api/admin/encargos-externos', {
      method: 'POST',
      credentials: 'same-origin',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(datos)
    })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (j) { return { ok: r.ok, j: j }; }); })
      .then(function (res) {
        if (!res.ok) {
          if (msg) { msg.style.color = '#f87171'; msg.textContent = res.j.error || res.j.message || 'No se pudo crear el encargo.'; }
          return;
        }
        var n = res.j.notificacion || {};
        var aviso = n.email ? 'Aviso enviado por la app y por email.' : (n.app ? 'Aviso enviado por la app (el email no se pudo enviar).' : 'Ojo: no se pudo avisar al aliado; llámale.');
        if (msg) { msg.style.color = '#4ade80'; msg.textContent = 'Encargo #' + res.j.encargo.id + ' creado. ' + aviso; }
        form.reset();
        refresh();
      })
      .catch(function () {
        if (msg) { msg.style.color = '#f87171'; msg.textContent = 'Error de conexión. Inténtalo de nuevo.'; }
      })
      .then(function () { if (btn) btn.disabled = false; });
  }

  function init() {
    var wrap = document.getElementById('encargos-externos-admin-wrap');
    if (!wrap) return;
    var form = document.getElementById('form-encargo-externo');
    if (form) form.addEventListener('submit', crear);
    var btn = document.getElementById('btn-filtrar-encargos-externos');
    if (btn) btn.addEventListener('click', refresh);
    var sel = document.getElementById('filtro-encargos-externos-estado');
    if (sel) sel.addEventListener('change', refresh);
    // Carga perezosa: solo cuando la sección se ve (sesión admin ya lista).
    if ('IntersectionObserver' in global) {
      var obs = new IntersectionObserver(function (entries) {
        entries.forEach(function (en) { if (en.isIntersecting) refresh(); });
      });
      obs.observe(wrap);
    } else {
      refresh();
    }
  }

  modules.encargosExternos = { refresh: refresh, render: render };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})(typeof window !== 'undefined' ? window : globalThis);
