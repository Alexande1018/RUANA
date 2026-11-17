/**
 * Redes regionales (hoy: Red Huesca) — modal de bienvenida.
 * - El texto de la zona lo envía el backend (`zona`, p. ej. «Huesca»).
 * - Solo se muestra si el backend dice mostrar=true. El «visto» se guarda en
 *   backend, así que se ve una sola vez aunque cambie de dispositivo.
 * - Fail-open: cualquier error = no se muestra y la app sigue igual.
 * - Reutiliza el estilo de Red Centro y las funciones existentes
 *   «Nueva conexión» / «Ampliar mi red».
 * - Una provincia nueva no requiere otro JS: basta la config del backend.
 */
(function (global) {
  'use strict';

  var modules = global.RuanaAliadoModules = global.RuanaAliadoModules || {};
  var abierto = false;
  var intentos = 0;
  var slugActual = '';

  function apiBase() {
    return typeof global.getApiBase === 'function' ? global.getApiBase() : '';
  }

  function headers(extra) {
    if (typeof global.getRuanaAuthHeaders === 'function') {
      return global.getRuanaAuthHeaders(extra || {});
    }
    return extra || {};
  }

  function htmlModal(zona, nombreRed) {
    var z = zona || 'tu zona';
    var tituloId = 'red-regional-title';
    return (
      '<div class="red-centro-modal" role="dialog" aria-modal="true" aria-labelledby="' + tituloId + '">' +
        '<button type="button" class="red-centro-close" data-rr-accion="cerrar" aria-label="Cerrar">✕</button>' +
        '<div class="red-centro-body">' +
          '<h2 class="red-centro-title" id="' + tituloId + '">🤝 ¡Juntos conseguimos más trabajo!</h2>' +
          '<p>¡Hola, aliado! 👋</p>' +
          '<p>Tenemos una novedad en RUANA.</p>' +
          '<p>Estamos conectando a los profesionales de ' + z + ' para que tengáis más oportunidades de conseguir trabajos.</p>' +
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
          '<button type="button" class="red-centro-btn" data-rr-accion="recomendar" id="red-regional-btn-recomendar">Recomendar trabajo</button>' +
          '<button type="button" class="red-centro-btn" data-rr-accion="invitar" id="red-regional-btn-invitar">Invitar aliado</button>' +
          '<button type="button" class="red-centro-btn red-centro-btn--primary" data-rr-accion="aceptar" id="red-regional-btn-aceptar">Entendido, ¡vamos allá!</button>' +
        '</div>' +
      '</div>'
    );
  }

  function registrar(accion) {
    try {
      return fetch(apiBase() + '/api/aliado/red-regional/aviso', {
        method: 'POST',
        credentials: 'same-origin',
        headers: headers({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ accion: accion, slug: slugActual })
      }).catch(function () { /* fail-open */ });
    } catch (e) {
      return Promise.resolve();
    }
  }

  function abrirRecomendar() {
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
      var ov = document.getElementById('red-regional-overlay');
      if (ov) accion(ov, 'cerrar');
    }
  }

  function accion(overlay, acc) {
    registrar(acc);
    cerrar(overlay);
    if (acc === 'recomendar') abrirRecomendar();
    else if (acc === 'invitar') abrirInvitar();
  }

  function mostrar(datos) {
    if (abierto || document.getElementById('red-regional-overlay') || document.getElementById('red-centro-overlay')) return;
    abierto = true;
    slugActual = (datos && datos.slug) || '';
    var overlay = document.createElement('div');
    overlay.className = 'red-centro-overlay';
    overlay.id = 'red-regional-overlay';
    overlay.innerHTML = htmlModal((datos && datos.zona) || 'tu zona', (datos && datos.red) || '');
    overlay.addEventListener('click', function (ev) {
      var btn = ev.target.closest && ev.target.closest('[data-rr-accion]');
      if (btn) accion(overlay, btn.getAttribute('data-rr-accion'));
    });
    document.body.appendChild(overlay);
    document.body.classList.add('red-centro-modal-open');
    document.addEventListener('keydown', onKey);
    var primary = document.getElementById('red-regional-btn-aceptar');
    if (primary && typeof primary.focus === 'function') primary.focus();
  }

  function comprobar() {
    try {
      return fetch(apiBase() + '/api/aliado/red-regional/aviso', { credentials: 'same-origin', headers: headers() })
        .then(function (r) {
          if (r.status === 401 && intentos < 3) {
            intentos += 1;
            setTimeout(comprobar, 2000 * intentos);
            return null;
          }
          return r.ok ? r.json() : null;
        })
        .then(function (d) { if (d && d.status === 'success' && d.mostrar === true) mostrar(d); })
        .catch(function () { /* fail-open: no se muestra */ });
    } catch (e) {
      return Promise.resolve();
    }
  }

  modules.redRegional = { comprobar: comprobar, mostrar: mostrar };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', comprobar);
  } else {
    comprobar();
  }
})(typeof window !== 'undefined' ? window : globalThis);
