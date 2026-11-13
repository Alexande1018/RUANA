/**
 * Piloto Red Centro — modal de bienvenida.
 * - Solo se muestra si el backend dice mostrar=true (aliado validado, miembro de
 *   Red Centro, flag activo y aún no visto). El «visto» se guarda en backend,
 *   así que se ve una sola vez aunque cambie de dispositivo o cierre sesión.
 * - Fail-open: cualquier error = no se muestra y la app sigue igual.
 * - «Recomendar trabajo» abre la función existente «Nueva conexión».
 * - «Invitar aliado» pulsa el botón existente «Ampliar mi red».
 */
(function (global) {
  'use strict';

  var modules = global.RuanaAliadoModules = global.RuanaAliadoModules || {};
  var abierto = false;
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

  var HTML =
    '<div class="red-centro-modal" role="dialog" aria-modal="true" aria-labelledby="red-centro-title">' +
      '<button type="button" class="red-centro-close" data-rc-accion="cerrar" aria-label="Cerrar">✕</button>' +
      '<div class="red-centro-body">' +
        '<h2 class="red-centro-title" id="red-centro-title">🤝 ¡Juntos conseguimos más trabajo!</h2>' +
        '<p>¡Hola, aliado! 👋</p>' +
        '<p>Tenemos una novedad en RUANA.</p>' +
        '<p>Estamos conectando a los profesionales de Madrid y Toledo para que tengáis más oportunidades de conseguir trabajos.</p>' +
        '<h3>🔄 ¿Cómo funciona?</h3>' +
        '<p>Muy sencillo:</p>' +
        '<p>Si te llega un trabajo que no puedes realizar porque es de otro oficio, recomiéndaselo a un compañero de RUANA.</p>' +
        '<p>Y cuando a ese compañero le llegue un trabajo de tu especialidad, podrá recomendártelo a ti.</p>' +
        '<p><strong>Hoy recomiendas tú, mañana te recomiendan a ti.</strong></p>' +
        '<h3>🚀 ¡Ayúdanos a hacer crecer la red!</h3>' +
        '<p>Dentro de RUANA tienes dos herramientas fundamentales:</p>' +
        '<p><strong>🔧 RECOMENDAR:</strong> comparte trabajos con otros aliados. No dejes perder una oportunidad porque no sea de tu oficio.</p>' +
        '<p><strong>👥 INVITAR:</strong> invita a profesionales de confianza, especialmente de otros oficios. Cuantos más aliados activos tengamos, más posibilidades habrá de recibir recomendaciones.</p>' +
        '<p><strong>No esperes solamente a que te lleguen trabajos. Participa, recomienda e invita.</strong></p>' +
        '<p>Tu oficio, tu zona y tus condiciones siguen siendo los mismos. Solo estamos ampliando temporalmente las oportunidades de colaboración.</p>' +
        '<p><strong>RUANA funciona cuando nos ayudamos entre todos. 💪</strong></p>' +
      '</div>' +
      '<div class="red-centro-actions">' +
        '<button type="button" class="red-centro-btn" data-rc-accion="recomendar" id="red-centro-btn-recomendar">Recomendar trabajo</button>' +
        '<button type="button" class="red-centro-btn" data-rc-accion="invitar" id="red-centro-btn-invitar">Invitar aliado</button>' +
        '<button type="button" class="red-centro-btn red-centro-btn--primary" data-rc-accion="aceptar" id="red-centro-btn-aceptar">Entendido, ¡vamos allá!</button>' +
      '</div>' +
    '</div>';

  function registrar(accion) {
    try {
      return fetch(apiBase() + '/api/aliado/red-centro/aviso', {
        method: 'POST',
        credentials: 'same-origin',
        headers: headers({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ accion: accion })
      }).catch(function () { /* fail-open */ });
    } catch (e) {
      return Promise.resolve();
    }
  }

  function abrirRecomendar() {
    // Función existente: módulo «Nueva conexión» (crear solicitud para otro oficio).
    try {
      if (global.AliadoShell && typeof global.AliadoShell.show === 'function') {
        global.AliadoShell.show('conexiones');
      } else {
        var goto = document.querySelector('[data-aliado-goto="conexiones"]');
        if (goto) goto.click();
      }
      setTimeout(function () {
        var input = document.getElementById('nueva-solicitud-oficio');
        if (input && typeof input.focus === 'function') input.focus();
      }, 150);
    } catch (e) { /* no bloquea */ }
  }

  function abrirInvitar() {
    // Función existente: cualquier botón [data-action="invitar-aliado"] («Ampliar mi red»).
    try {
      var btn = document.getElementById('btn-invitar-global') ||
        document.querySelector('[data-action="invitar-aliado"]');
      if (btn) btn.click();
    } catch (e) { /* no bloquea */ }
  }

  function cerrar(overlay) {
    abierto = false;
    if (overlay && overlay.parentNode) overlay.parentNode.removeChild(overlay);
    document.body.classList.remove('red-centro-modal-open');
    document.removeEventListener('keydown', onKey);
  }

  function onKey(ev) {
    if (ev.key === 'Escape') {
      var ov = document.getElementById('red-centro-overlay');
      if (ov) accion(ov, 'cerrar');
    }
  }

  function accion(overlay, acc) {
    registrar(acc);
    cerrar(overlay);
    if (acc === 'recomendar') abrirRecomendar();
    else if (acc === 'invitar') abrirInvitar();
  }

  function mostrar() {
    if (abierto || document.getElementById('red-centro-overlay')) return;
    abierto = true;
    var overlay = document.createElement('div');
    overlay.className = 'red-centro-overlay';
    overlay.id = 'red-centro-overlay';
    overlay.innerHTML = HTML;
    overlay.addEventListener('click', function (ev) {
      var btn = ev.target.closest && ev.target.closest('[data-rc-accion]');
      if (btn) accion(overlay, btn.getAttribute('data-rc-accion'));
    });
    document.body.appendChild(overlay);
    document.body.classList.add('red-centro-modal-open');
    document.addEventListener('keydown', onKey);
    var primary = document.getElementById('red-centro-btn-aceptar');
    if (primary && typeof primary.focus === 'function') primary.focus();
  }

  function comprobar() {
    try {
      return fetch(apiBase() + '/api/aliado/red-centro/aviso', { credentials: 'same-origin', headers: headers() })
        .then(function (r) {
          if (r.status === 401 && intentos < 3) {
            intentos += 1;
            setTimeout(comprobar, 2000 * intentos);
            return null;
          }
          return r.ok ? r.json() : null;
        })
        .then(function (d) { if (d && d.status === 'success' && d.mostrar === true) mostrar(); })
        .catch(function () { /* fail-open: no se muestra */ });
    } catch (e) {
      return Promise.resolve();
    }
  }

  modules.redCentro = { comprobar: comprobar, mostrar: mostrar };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', comprobar);
  } else {
    comprobar();
  }
})(typeof window !== 'undefined' ? window : globalThis);
