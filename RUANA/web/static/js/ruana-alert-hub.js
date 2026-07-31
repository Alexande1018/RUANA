/**
 * RUANA Alert Hub — tarjetas compactas con priorización y agrupación
 */
(function (global) {
    'use strict';

    var MAX_VISIBLE_COLLAPSED = 1;

    var ICONS = {
        payment: '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="20" height="14" x="2" y="5" rx="2"/><line x1="2" y1="10" x2="22" y2="10"/></svg>',
        message: '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>',
        action: '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>',
        info: '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>'
    };

    function truncate(str, max) {
        var s = String(str || '');
        if (s.length <= max) return s;
        return s.slice(0, max - 1).trim() + '…';
    }

    function escapeHtml(str) {
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function createCard(item, opts) {
        opts = opts || {};
        var card = document.createElement('div');
        card.className = 'ruana-alert-card ruana-alert-card--' + (item.type || 'info');
        card.setAttribute('data-alert-id', item.id);
        if (opts.expanded) card.classList.add('is-expanded');

        var actionHtml = '';
        if (item.actionLabel) {
            actionHtml = '<button type="button" class="ruana-alert-card__action" data-alert-action="' +
                escapeHtml(item.id) + '">' + escapeHtml(item.actionLabel) + '</button>';
        }

        card.innerHTML =
            '<span class="ruana-alert-card__icon" aria-hidden="true">' +
                (ICONS[item.type] || ICONS.info) +
            '</span>' +
            '<div class="ruana-alert-card__body">' +
                '<div class="ruana-alert-card__title">' + escapeHtml(item.title) + '</div>' +
                (item.description
                    ? '<div class="ruana-alert-card__desc">' + escapeHtml(item.description) + '</div>'
                    : '') +
            '</div>' +
            actionHtml;

        if (item.actionLabel && typeof opts.onAction === 'function') {
            var btn = card.querySelector('[data-alert-action]');
            if (btn) {
                btn.addEventListener('click', function (e) {
                    e.stopPropagation();
                    opts.onAction(item);
                });
            }
        }

        if (typeof opts.onCardClick === 'function') {
            card.addEventListener('click', function () { opts.onCardClick(item); });
            card.style.cursor = 'pointer';
        }

        return card;
    }

    /**
     * Renderiza el hub de alertas.
     * @param {HTMLElement} hubEl contenedor #ruana-alert-hub
     * @param {Array} items alertas ordenadas por prioridad
     * @param {Object} state { showAll, expandedDetailId }
     * @param {Object} callbacks { onAction, onShowAll, onCloseDetail }
     */
    function render(hubEl, items, state, callbacks) {
        if (!hubEl) return;
        callbacks = callbacks || {};
        state = state || {};
        items = Array.isArray(items) ? items : [];

        var cardsEl = hubEl.querySelector('.ruana-alert-hub__cards');
        var moreEl = hubEl.querySelector('.ruana-alert-hub__more');
        var detailEl = hubEl.querySelector('.ruana-alert-hub__detail');

        if (!items.length) {
            hubEl.hidden = true;
            if (cardsEl) cardsEl.innerHTML = '';
            if (moreEl) moreEl.hidden = true;
            if (detailEl) detailEl.hidden = true;
            return;
        }

        hubEl.hidden = false;

        var showAll = !!state.showAll;
        var visible = showAll ? items : items.slice(0, MAX_VISIBLE_COLLAPSED);
        var hiddenCount = showAll ? 0 : Math.max(0, items.length - MAX_VISIBLE_COLLAPSED);

        if (cardsEl) {
            cardsEl.innerHTML = '';
            visible.forEach(function (item) {
                cardsEl.appendChild(createCard(item, {
                    expanded: state.expandedDetailId === item.id,
                    onAction: callbacks.onAction,
                    onCardClick: item.hasDetail ? callbacks.onAction : null
                }));
            });
        }

        if (moreEl) {
            if (hiddenCount > 0) {
                moreEl.hidden = false;
                moreEl.innerHTML =
                    'Ver <span class="ruana-alert-hub__more-count">' + hiddenCount + '</span> aviso' +
                    (hiddenCount > 1 ? 's' : '') + ' más';
                moreEl.onclick = function () {
                    if (typeof callbacks.onShowAll === 'function') callbacks.onShowAll();
                };
            } else if (!showAll && items.length > 1) {
                moreEl.hidden = false;
                moreEl.innerHTML = 'Ver todos los avisos (' + items.length + ')';
                moreEl.onclick = function () {
                    if (typeof callbacks.onShowAll === 'function') callbacks.onShowAll();
                };
            } else {
                moreEl.hidden = true;
            }
        }

        if (detailEl) {
            if (state.expandedDetailId && typeof callbacks.renderDetail === 'function') {
                detailEl.hidden = false;
                callbacks.renderDetail(detailEl, state.expandedDetailId);
            } else {
                detailEl.hidden = true;
                detailEl.innerHTML = '';
            }
        }
    }

    function renderDetailHeader(detailEl, title, onClose) {
        detailEl.innerHTML =
            '<div class="ruana-alert-hub__detail-header">' +
                '<span class="ruana-alert-hub__detail-title">' + escapeHtml(title) + '</span>' +
                '<button type="button" class="ruana-alert-hub__detail-close">Cerrar</button>' +
            '</div>' +
            '<div class="ruana-alert-hub__detail-body"></div>';
        var closeBtn = detailEl.querySelector('.ruana-alert-hub__detail-close');
        if (closeBtn && typeof onClose === 'function') {
            closeBtn.addEventListener('click', onClose);
        }
        return detailEl.querySelector('.ruana-alert-hub__detail-body');
    }

    global.RuanaAlertHub = {
        render: render,
        createCard: createCard,
        renderDetailHeader: renderDetailHeader,
        truncate: truncate,
        escapeHtml: escapeHtml,
        ICONS: ICONS,
        MAX_VISIBLE_COLLAPSED: MAX_VISIBLE_COLLAPSED
    };
})(typeof window !== 'undefined' ? window : globalThis);
