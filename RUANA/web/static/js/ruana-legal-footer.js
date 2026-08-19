/**
 * Inserta el footer legal común si la página aún no lo tiene.
 * No añade banner de cookies: la sesión de aliado/admin usa JWT en
 * sessionStorage (X-Ruana-Session-Id), no cookies de tracking.
 */
(function (global) {
  'use strict';

  var FOOTER_ID = 'ruana-legal-footer';

  function buildFooter() {
    var footer = document.createElement('footer');
    footer.id = FOOTER_ID;
    footer.className = 'ruana-legal-footer';
    footer.setAttribute('role', 'contentinfo');
    footer.innerHTML =
      '<nav aria-label="Información legal">' +
      '<a href="/aviso-legal.html">Aviso legal</a>' +
      '<span aria-hidden="true"> · </span>' +
      '<a href="/politica-privacidad.html">Política de privacidad</a>' +
      '<span aria-hidden="true"> · </span>' +
      '<a href="/terminos.html">Términos de uso</a>' +
      '</nav>' +
      '<p>RUANA · España</p>';
    return footer;
  }

  function ensureFooter() {
    if (document.getElementById(FOOTER_ID)) {
      return;
    }
    if (!document.body) {
      return;
    }
    document.body.appendChild(buildFooter());
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', ensureFooter);
  } else {
    ensureFooter();
  }

  global.RuanaLegalFooter = { ensure: ensureFooter };
})(typeof window !== 'undefined' ? window : globalThis);
