/**
 * Encargos de RUANA — clientes que RUANA asigna al aliado (sin cobro).
 * Módulo autónomo: solo pinta la sección si el aliado tiene alguno.
 */
(function (global) {
  'use strict';

  var modules = global.RuanaAliadoModules = global.RuanaAliadoModules || {};
  var ESTADOS = { creado: 'Pendiente', aceptado: 'Aceptado', hecho: 'Hecho', rechazado: 'Rechazado' };
  var intentos = 0;

  function apiBase() {
    return typeof global.getApiBase === 'function' ? global.getApiBase() : '';
  }

  function headers(extra) {
    if (typeof global.getRuanaAuthHeaders === 'function') {
      return global.getRuanaAuthHeaders(extra || {});
    }
    return extra || {};
  }

  function esc(str) {
    return String(str == null ? '' : str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function precio(v) {
    if (v == null || v === '') return '';
    var n = Number(v);
    return isNaN(n) ? '' : n.toLocaleString('es-ES', { style: 'currency', currency: 'EUR' });
  }

  function acciones(e) {
    if (e.estado === 'creado') {
      return '<button type="button" class="encargo-ruana-btn encargo-ruana-btn--primary" data-ee-accion="aceptar" data-ee-id="' + esc(e.id) + '">Lo cojo</button>' +
        '<button type="button" class="encargo-ruana-btn" data-ee-accion="rechazar" data-ee-id="' + esc(e.id) + '">No puedo</button>';
    }
    if (e.estado === 'aceptado') {
      return '<button type="button" class="encargo-ruana-btn encargo-ruana-btn--primary" data-ee-accion="hecho" data-ee-id="' + esc(e.id) + '">Marcar como hecho</button>';
    }
    return '';
  }

  function tarjeta(e) {
    var tel = e.cliente_telefono ? '<a href="tel:' + esc(e.cliente_telefono) + '">📞 ' + esc(e.cliente_telefono) + '</a>' : '';
    var mail = e.cliente_email ? '<a href="mailto:' + esc(e.cliente_email) + '">✉️ ' + esc(e.cliente_email) + '</a>' : '';
    var p = precio(e.precio_orientativo);
    return '<article class="encargo-ruana-card" data-ee-card="' + esc(e.id) + '">' +
      '<div class="encargo-ruana-head"><span class="encargo-ruana-kicker">Encargo de RUANA</span>' +
      '<span class="encargo-ruana-estado" data-estado="' + esc(e.estado) + '">' + esc(ESTADOS[e.estado] || e.estado) + '</span></div>' +
      '<p class="encargo-ruana-cliente">' + esc(e.cliente_nombre) + ' · CP ' + esc(e.codigo_postal) + '</p>' +
      '<p class="encargo-ruana-desc">' + esc(e.descripcion) + '</p>' +
      '<div class="encargo-ruana-datos">' + tel + mail + (p ? '<span>Precio orientativo: ' + esc(p) + '</span>' : '') + '</div>' +
      '<div class="encargo-ruana-acciones">' + acciones(e) + '</div>' +
      '<p class="encargo-ruana-msg" hidden></p>' +
      '</article>';
  }

  function render(list) {
    var wrap = document.getElementById('inicio-encargos-ruana-wrap');
    var cont = document.getElementById('inicio-encargos-ruana-list');
    if (!wrap || !cont) return;
    list = list || [];
    // Los rechazados no se muestran al aliado: ya no hay nada que hacer con ellos.
    var visibles = list.filter(function (e) { return e.estado !== 'rechazado'; });
    wrap.hidden = visibles.length === 0;
    cont.innerHTML = visibles.map(tarjeta).join('');
  }

  function refresh() {
    return fetch(apiBase() + '/api/encargos-externos', { credentials: 'same-origin', headers: headers() })
      .then(function (r) {
        if (r.status === 401 && intentos < 3) {
          intentos += 1;
          setTimeout(refresh, 2000 * intentos);
          return null;
        }
        return r.ok ? r.json() : null;
      })
      .then(function (d) { if (d && d.status === 'success') render(d.encargos); })
      .catch(function () { /* no bloquea el panel */ });
  }

  function onClick(ev) {
    var btn = ev.target.closest && ev.target.closest('[data-ee-accion]');
    if (!btn) return;
    var accion = btn.getAttribute('data-ee-accion');
    var id = btn.getAttribute('data-ee-id');
    var body = {};
    if (accion === 'rechazar') {
      var motivo = global.prompt('¿Por qué no puedes cogerlo? (opcional)', '');
      if (motivo === null) return;
      body.motivo = motivo;
    } else if (accion === 'hecho') {
      if (!global.confirm('¿Confirmas que el trabajo está hecho?')) return;
    }
    var card = btn.closest('[data-ee-card]');
    var msg = card && card.querySelector('.encargo-ruana-msg');
    Array.prototype.forEach.call(card ? card.querySelectorAll('button') : [], function (b) { b.disabled = true; });
    fetch(apiBase() + '/api/encargos-externos/' + encodeURIComponent(id) + '/' + accion, {
      method: 'POST',
      credentials: 'same-origin',
      headers: headers({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(body)
    })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (j) { return { ok: r.ok, j: j }; }); })
      .then(function (res) {
        if (!res.ok) throw new Error(res.j.error || 'No se pudo guardar. Inténtalo de nuevo.');
        return refresh();
      })
      .catch(function (err) {
        if (msg) { msg.hidden = false; msg.textContent = err.message || 'No se pudo guardar. Inténtalo de nuevo.'; }
        Array.prototype.forEach.call(card ? card.querySelectorAll('button') : [], function (b) { b.disabled = false; });
      });
  }

  function init() {
    var wrap = document.getElementById('inicio-encargos-ruana-wrap');
    if (!wrap) return;
    wrap.addEventListener('click', onClick);
    refresh();
    document.addEventListener('visibilitychange', function () {
      if (document.visibilityState === 'visible') refresh();
    });
  }

  modules.encargosExternos = { refresh: refresh, render: render };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})(typeof window !== 'undefined' ? window : globalThis);
