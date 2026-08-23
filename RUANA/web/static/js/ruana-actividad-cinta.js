/**
 * Cinta de actividad RUANA — presentación continua de noticias reales (máx. 10).
 * Fuente: host.actividadCinta (backend) derivada de notificaciones y avisos de grupo.
 */
(function (global) {
  'use strict';

  var MAX_ITEMS = 10;
  var PX_PER_SECOND = 42;

  function parseTimestamp(value) {
    if (value == null || value === '') return null;
    if (typeof value === 'number' && Number.isFinite(value)) return value;
    var text = String(value).trim();
    if (!text) return null;
    var normalized = text.indexOf('T') === -1 && text.indexOf(' ') !== -1
      ? text.replace(' ', 'T')
      : text;
    var ms = Date.parse(normalized);
    return Number.isFinite(ms) ? ms : null;
  }

  function formatRelativeTime(value, nowMs) {
    var ts = parseTimestamp(value);
    if (ts == null) return '';
    var now = typeof nowMs === 'number' ? nowMs : Date.now();
    var diff = Math.max(0, now - ts);
    var mins = Math.floor(diff / 60000);
    if (mins < 1) return 'Ahora';
    if (mins < 60) return 'Hace ' + mins + ' min';
    var hours = Math.floor(mins / 60);
    if (hours < 24) return 'Hace ' + hours + ' h';
    var days = Math.floor(hours / 24);
    if (days === 1) return 'Ayer';
    if (days < 7) return 'Hace ' + days + ' d';
    return '';
  }

  function trimToMax(items, max) {
    var limit = typeof max === 'number' ? max : MAX_ITEMS;
    if (!Array.isArray(items)) return [];
    return items.slice(0, Math.max(0, limit));
  }

  function sortByDateDesc(items) {
    return (Array.isArray(items) ? items.slice() : []).sort(function (a, b) {
      var ta = parseTimestamp(a && a.creado_en) || 0;
      var tb = parseTimestamp(b && b.creado_en) || 0;
      return tb - ta;
    });
  }

  function escapeHtml(text) {
    return String(text || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function buildTrackHtml(items, nowMs) {
    if (!items.length) return '';
    return items.map(function (item, index) {
      var texto = escapeHtml(item && item.texto);
      var rel = formatRelativeTime(item && item.creado_en, nowMs);
      var timeHtml = rel
        ? '<span class="ruana-actividad-cinta__item-time">' + escapeHtml(rel) + '</span>'
        : '';
      var sep = index < items.length - 1
        ? '<span class="ruana-actividad-cinta__sep" aria-hidden="true">·</span>'
        : '';
      return (
        '<span class="ruana-actividad-cinta__item">' + texto + timeHtml + '</span>' + sep
      );
    }).join('');
  }

  function prefersReducedMotion() {
    try {
      return global.matchMedia && global.matchMedia('(prefers-reduced-motion: reduce)').matches;
    } catch (_) {
      return false;
    }
  }

  function applyMarqueeTiming(root, marquee) {
    if (!root || !marquee) return;
    var track = marquee.querySelector('.ruana-actividad-cinta__track:not(.ruana-actividad-cinta__track--clone)');
    if (!track) return;
    var width = track.offsetWidth;
    if (!width) return;
    var seconds = Math.max(28, Math.round(width / PX_PER_SECOND));
    root.style.setProperty('--ruana-cinta-speed', seconds + 's');
  }

  function render(host) {
    var root = document.getElementById('inicio-actividad-cinta');
    if (!root) return;

    var raw = host && Array.isArray(host.actividadCinta) ? host.actividadCinta : [];
    var items = trimToMax(sortByDateDesc(raw), MAX_ITEMS);

    if (!items.length) {
      root.hidden = true;
      root.innerHTML = '';
      root.classList.remove('ruana-actividad-cinta--static');
      return;
    }

    root.hidden = false;
    var reduced = prefersReducedMotion();
    var nowMs = Date.now();
    var trackHtml = buildTrackHtml(items, nowMs);
    var cloneAttr = reduced ? '' : ' ruana-actividad-cinta__track--clone';

    root.className = 'ruana-actividad-cinta' + (reduced ? ' ruana-actividad-cinta--static' : '');
    root.setAttribute('role', 'region');
    root.setAttribute('aria-label', 'Noticias de actividad RUANA');
    root.setAttribute('aria-live', 'off');

    root.innerHTML =
      '<div class="ruana-actividad-cinta__badge" aria-hidden="true">' +
        '<span class="ruana-actividad-cinta__pulse"></span>' +
        '<span class="ruana-actividad-cinta__label ruana-actividad-cinta__label--full">Noticias RUANA</span>' +
        '<span class="ruana-actividad-cinta__label ruana-actividad-cinta__label--short">Noticias</span>' +
      '</div>' +
      '<div class="ruana-actividad-cinta__viewport">' +
        '<div class="ruana-actividad-cinta__marquee">' +
          '<div class="ruana-actividad-cinta__track">' + trackHtml + '</div>' +
          (reduced ? '' : '<div class="ruana-actividad-cinta__track' + cloneAttr + '" aria-hidden="true">' + trackHtml + '</div>') +
        '</div>' +
      '</div>';

    if (!reduced) {
      var marquee = root.querySelector('.ruana-actividad-cinta__marquee');
      requestAnimationFrame(function () {
        applyMarqueeTiming(root, marquee);
      });
    }
  }

  global.RuanaActividadCinta = {
    MAX_ITEMS: MAX_ITEMS,
    PX_PER_SECOND: PX_PER_SECOND,
    parseTimestamp: parseTimestamp,
    formatRelativeTime: formatRelativeTime,
    trimToMax: trimToMax,
    sortByDateDesc: sortByDateDesc,
    buildTrackHtml: buildTrackHtml,
    render: render,
    applyMarqueeTiming: applyMarqueeTiming,
    prefersReducedMotion: prefersReducedMotion,
  };
})(typeof window !== 'undefined' ? window : globalThis);
