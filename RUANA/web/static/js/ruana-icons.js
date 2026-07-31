/**
 * RUANA — Iconografía exclusiva
 * Nodos, hilos, red y colaboración. Sin iconos genéricos.
 */
(function (global) {
    'use strict';

  /* Estilo: nodos circulares + líneas de conexión, stroke 1.65 */
    var STYLE = 'fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round"';

    var ICONS = {
        'user-plus': '<circle cx="9" cy="7" r="3.5"/><path d="M3 19v-1.5a4 4 0 0 1 4-4h4"/><circle cx="17" cy="11" r="2.5"/><path d="M17 8.5V14M15.5 11h3"/>',
        send: '<circle cx="5" cy="12" r="2"/><circle cx="12" cy="6" r="2"/><circle cx="19" cy="12" r="2"/><path d="M7 11l5-4M13 7l5 4"/><path d="M7 13l5 4M13 17l5-4"/>',
        activity: '<circle cx="5" cy="18" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="19" cy="6" r="2"/><path d="M7 16.5l4.5-4.5M13.5 10.5l4.5-4.5"/>',
        users: '<circle cx="9" cy="8" r="3"/><circle cx="17" cy="10" r="2.5"/><path d="M3 20v-1a5 5 0 0 1 5-5h2"/><path d="M15 20v-1a3.5 3.5 0 0 1 3.5-3.5H19"/>',
        gauge: '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="2"/><path d="M12 10V6"/><path d="M16.5 14l2.5 2.5"/>',
        shield: '<path d="M12 3l7 3v5c0 5-3 8.5-7 10-4-1.5-7-5-7-10V6l7-3z"/><circle cx="12" cy="11" r="2"/><path d="M10.5 13.5L12 15l1.5-1.5"/>',
        search: '<circle cx="11" cy="11" r="6"/><path d="M16 16l4.5 4.5"/><circle cx="11" cy="11" r="2" opacity="0.5"/>',
        'message-circle': '<circle cx="12" cy="12" r="8"/><circle cx="8.5" cy="11" r="1"/><circle cx="12" cy="11" r="1"/><circle cx="15.5" cy="11" r="1"/><path d="M8 15c1.2 1 2.8 1.5 4 1.5s2.8-.5 4-1.5"/>',
        handshake: '<circle cx="7" cy="9" r="2.5"/><circle cx="17" cy="9" r="2.5"/><path d="M4.5 14l3-2.5 2.5 2 3-3L19.5 14"/><path d="M9.5 11.5l1.5 1.5M14 11.5l1.5 1.5"/>',
        grid: '<rect x="4" y="4" width="6" height="6" rx="1.5"/><rect x="14" y="4" width="6" height="6" rx="1.5"/><rect x="4" y="14" width="6" height="6" rx="1.5"/><rect x="14" y="14" width="6" height="6" rx="1.5"/><circle cx="7" cy="7" r="1" fill="currentColor" stroke="none"/><circle cx="17" cy="17" r="1" fill="currentColor" stroke="none"/>',
        inbox: '<path d="M4 6h16v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6z"/><path d="M4 12h4l2 2h6l2-2h4"/><circle cx="12" cy="13" r="1.5" fill="currentColor" stroke="none"/>',
        network: '<circle cx="12" cy="5" r="2.5"/><circle cx="5" cy="18" r="2.5"/><circle cx="19" cy="18" r="2.5"/><path d="M12 7.5L5.5 15.5M12 7.5l6.5 8"/><path d="M7.5 18h9"/>',
        settings: '<circle cx="12" cy="12" r="2.5"/><path d="M12 3v2.5M12 18.5V21M3 12h2.5M18.5 12H21M5.6 5.6l1.8 1.8M16.4 16.4l1.8 1.8M5.6 18.4l1.8-1.8M16.4 7.6l1.8-1.8"/>',
        heart: '<circle cx="12" cy="10" r="2"/><path d="M12 21s-7-4.5-7-10a4 4 0 0 1 7-2.5A4 4 0 0 1 19 11c0 5.5-7 10-7 10z"/>',
        'user-check': '<circle cx="9" cy="8" r="3.5"/><path d="M3 20v-1.5a4 4 0 0 1 4-4h4"/><path d="M16 11l1.5 1.5L20 8"/>',
        alert: '<circle cx="12" cy="16" r="1.5" fill="currentColor" stroke="none"/><path d="M12 3l8.5 14.5H3.5L12 3z"/><path d="M12 9v4"/>',
        credit: '<rect x="3" y="6" width="18" height="12" rx="2"/><path d="M3 11h18"/><circle cx="7" cy="15" r="1" fill="currentColor" stroke="none"/>',
        clock: '<circle cx="12" cy="12" r="8"/><path d="M12 8v4l3 2"/><circle cx="12" cy="12" r="1.5" fill="currentColor" stroke="none"/>',
        zap: '<circle cx="7" cy="7" r="2"/><circle cx="17" cy="17" r="2"/><path d="M9 7h7l-4 6h5l-7 9 2-7H7l4-6"/>',
        message: '<circle cx="6" cy="10" r="2"/><circle cx="18" cy="10" r="2"/><path d="M8 10h8"/><path d="M6 14c1.5 2 4.5 3 6 3s4.5-1 6-3"/>',
        list: '<circle cx="5" cy="6" r="1.5" fill="currentColor" stroke="none"/><circle cx="5" cy="12" r="1.5" fill="currentColor" stroke="none"/><circle cx="5" cy="18" r="1.5" fill="currentColor" stroke="none"/><path d="M10 6h11M10 12h11M10 18h11"/>',
        wallet: '<rect x="3" y="7" width="18" height="11" rx="2"/><circle cx="16" cy="14.5" r="1.5" fill="currentColor" stroke="none"/><path d="M3 11h18"/>',
        'trending-up': '<circle cx="5" cy="18" r="2"/><circle cx="19" cy="6" r="2"/><path d="M7 16l5-5 3 3 5-6"/>',
        close: '<circle cx="12" cy="12" r="8"/><path d="M9 9l6 6M15 9l-6 6"/>',
        success: '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="2" fill="currentColor" stroke="none"/><path d="M8 12l2.5 2.5L16 9"/>',
        error: '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="2" fill="currentColor" stroke="none"/><path d="M9 9l6 6M15 9l-6 6"/>',
        warning: '<path d="M12 3l8.5 14.5H3.5L12 3z"/><circle cx="12" cy="14" r="1" fill="currentColor" stroke="none"/>',
        info: '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="2" fill="currentColor" stroke="none"/><path d="M12 10v5"/>',
        menu: '<circle cx="5" cy="6" r="1.5" fill="currentColor" stroke="none"/><circle cx="5" cy="12" r="1.5" fill="currentColor" stroke="none"/><circle cx="5" cy="18" r="1.5" fill="currentColor" stroke="none"/><path d="M10 6h11M10 12h11M10 18h11"/>'
    };

    function svg(name, size) {
        var inner = ICONS[name] || ICONS.info;
        var w = size || 24;
        var h = size || 24;
        return '<svg class="ruana-icon-svg" xmlns="http://www.w3.org/2000/svg" width="' + w + '" height="' + h + '" viewBox="0 0 24 24" aria-hidden="true" focusable="false" ' + STYLE + '>' + inner + '</svg>';
    }

    function inject(root) {
        var scope = root || document;
        var lucideEls = scope.querySelectorAll('[data-lucide]');
        for (var i = 0; i < lucideEls.length; i++) {
            var el = lucideEls[i];
            var name = el.getAttribute('data-lucide');
            if (!ICONS[name]) continue;
            var w = el.style.width || el.getAttribute('width') || '20';
            var h = el.style.height || el.getAttribute('height') || w;
            el.outerHTML = svg(name, parseInt(w, 10) || 20);
        }
        var ruanaEls = scope.querySelectorAll('[data-ruana-icon]');
        for (var j = 0; j < ruanaEls.length; j++) {
            var rel = ruanaEls[j];
            var rname = rel.getAttribute('data-ruana-icon');
            if (!ICONS[rname]) continue;
            rel.innerHTML = svg(rname, 20);
        }
    }

    global.RuanaIcons = {
        svg: svg,
        inject: inject,
        icons: ICONS
    };
})(typeof window !== 'undefined' ? window : globalThis);
