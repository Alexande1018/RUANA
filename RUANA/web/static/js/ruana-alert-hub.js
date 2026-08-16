/**
 * RUANA Alert Hub — tarjetas compactas con priorización, críticas fijas y agrupación
 */
(function (global) {
    'use strict';

    var MAX_VISIBLE_COLLAPSED = 1;
    var hubStateMap = new WeakMap();

    var ICONS = {
        payment: '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="20" height="14" x="2" y="5" rx="2"/><line x1="2" y1="10" x2="22" y2="10"/></svg>',
        message: '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>',
        action: '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>',
        info: '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>',
        critical: '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M8 10.5c1.2-1.1 2.4-1.1 4 0s2.8 1.1 4 0"/><line x1="12" y1="14.5" x2="12" y2="17"/><circle cx="12" cy="7.5" r="0.75" fill="currentColor" stroke="none"/></svg>'
    };

    var EXIT_TOASTS = {
        'score-bajo': 'Tu Score ya no requiere atención urgente.',
        'stripe-pendiente': 'Cuenta de pago conectada correctamente.'
    };

    function prefersReducedMotion() {
        return typeof global.matchMedia === 'function' &&
            global.matchMedia('(prefers-reduced-motion: reduce)').matches;
    }

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

    function formatRelativeTime(ts) {
        if (!ts) return '';
        var date = new Date(ts);
        if (Number.isNaN(date.getTime())) return '';
        var diffMs = Date.now() - date.getTime();
        if (diffMs < 60000) return 'ahora';
        var mins = Math.floor(diffMs / 60000);
        if (mins < 60) return 'hace ' + mins + 'm';
        var hours = Math.floor(mins / 60);
        if (hours < 24) return 'hace ' + hours + 'h';
        return date.toLocaleDateString('es-ES', { day: 'numeric', month: 'short' });
    }

    function getHubRuntime(hubEl) {
        if (!hubStateMap.has(hubEl)) {
            hubStateMap.set(hubEl, {
                prevCriticalIds: new Set(),
                timeInterval: null
            });
        }
        return hubStateMap.get(hubEl);
    }

    function clearTimeInterval(runtime) {
        if (runtime.timeInterval) {
            clearInterval(runtime.timeInterval);
            runtime.timeInterval = null;
        }
    }

    function startTimeInterval(hubEl, runtime) {
        clearTimeInterval(runtime);
        runtime.timeInterval = setInterval(function () {
            hubEl.querySelectorAll('.ruana-alert-card__time[data-ts]').forEach(function (el) {
                el.textContent = formatRelativeTime(Number(el.getAttribute('data-ts')));
            });
        }, 30000);
    }

    function bindSwipeDismiss(card, item, callbacks) {
        if (!card || item.critical) return;
        var startX = 0;
        var startY = 0;
        var startTime = 0;
        var dragging = false;

        card.addEventListener('touchstart', function (e) {
            if (!e.touches || !e.touches.length) return;
            startX = e.touches[0].clientX;
            startY = e.touches[0].clientY;
            startTime = Date.now();
            dragging = true;
            card.style.transition = 'none';
        }, { passive: true });

        card.addEventListener('touchmove', function (e) {
            if (!dragging || !e.touches || !e.touches.length) return;
            var dx = e.touches[0].clientX - startX;
            var dy = e.touches[0].clientY - startY;
            if (Math.abs(dx) > Math.abs(dy)) {
                card.style.transform = 'translateX(' + dx + 'px)';
            }
        }, { passive: true });

        card.addEventListener('touchend', function (e) {
            if (!dragging) return;
            dragging = false;
            var touch = (e.changedTouches && e.changedTouches[0]) ? e.changedTouches[0] : null;
            var dx = touch ? touch.clientX - startX : 0;
            var elapsed = Math.max(Date.now() - startTime, 1);
            var velocity = Math.abs(dx) / elapsed;
            card.style.transition = 'transform var(--ruana-transition)';
            if (Math.abs(dx) > 80 || velocity > 0.5) {
                animateCardExit(card, false, function () {
                    if (typeof callbacks.onDismiss === 'function') callbacks.onDismiss(item);
                });
            } else {
                card.style.transform = '';
            }
        }, { passive: true });
    }

    function animateCardExit(card, isCritical, done) {
        if (!card) {
            if (typeof done === 'function') done();
            return;
        }
        if (prefersReducedMotion()) {
            card.style.transition = 'opacity 180ms ease';
            card.style.opacity = '0';
            setTimeout(function () {
                if (card.parentNode) card.parentNode.removeChild(card);
                if (typeof done === 'function') done();
            }, 190);
            return;
        }
        card.classList.add(isCritical ? 'is-critical-leaving' : 'is-leaving');
        setTimeout(function () {
            if (card.parentNode) card.parentNode.removeChild(card);
            if (typeof done === 'function') done();
        }, 220);
    }

    function showResolvedToast(id) {
        var msg = EXIT_TOASTS[id];
        if (!msg) return;
        if (global.RuanaUI && typeof global.RuanaUI.success === 'function') {
            global.RuanaUI.success('Resuelto', msg, 3500);
        }
    }

    function createCard(item, opts) {
        opts = opts || {};
        var card = document.createElement('div');
        var typeClass = 'ruana-alert-card--' + (item.type || 'info');
        card.className = 'ruana-alert-card ' + typeClass;
        card.setAttribute('data-alert-id', item.id);
        if (opts.expanded) card.classList.add('is-expanded');
        if (item.critical) {
            card.classList.add('ruana-alert-card--critical', 'ruana-surface');
            if (item.pendiente) card.classList.add('is-pendiente');
            if (item.criticalTone) card.setAttribute('data-critical-tone', item.criticalTone);
            if (!prefersReducedMotion()) card.classList.add('is-critical-enter');
        } else if (!prefersReducedMotion()) {
            card.classList.add('ruana-alert-enter');
        }

        var iconKey = item.critical ? 'critical' : (item.type || 'info');
        var timeHtml = '';
        if (item.createdAt) {
            timeHtml = '<span class="ruana-alert-card__time" data-ts="' + Number(item.createdAt) + '">' +
                escapeHtml(formatRelativeTime(item.createdAt)) + '</span>';
        }

        var actionHtml = '';
        if (item.actionLabel) {
            actionHtml = '<button type="button" class="ruana-alert-card__action" data-alert-action="' +
                escapeHtml(item.id) + '">' + escapeHtml(item.actionLabel) + '</button>';
        }

        card.innerHTML =
            '<span class="ruana-alert-card__icon" aria-hidden="true">' +
                (ICONS[iconKey] || ICONS.info) +
            '</span>' +
            '<div class="ruana-alert-card__body">' +
                '<div class="ruana-alert-card__title-row">' +
                    '<div class="ruana-alert-card__title">' + escapeHtml(item.title) + '</div>' +
                    timeHtml +
                '</div>' +
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

        if (!item.critical) bindSwipeDismiss(card, item, { onDismiss: opts.onDismiss });

        return card;
    }

    function syncCriticalCards(pinnedEl, criticalItems, opts, runtime) {
        var nextIds = new Set(criticalItems.map(function (i) { return i.id; }));

        Array.from(pinnedEl.querySelectorAll('.ruana-alert-card')).forEach(function (card) {
            var id = card.getAttribute('data-alert-id');
            if (!nextIds.has(id) && !card.classList.contains('is-critical-leaving')) {
                showResolvedToast(id);
                animateCardExit(card, true);
            }
        });

        criticalItems.forEach(function (item) {
            if (!pinnedEl.querySelector('[data-alert-id="' + item.id + '"]')) {
                pinnedEl.appendChild(createCard(item, opts));
            }
        });

        runtime.prevCriticalIds = nextIds;
    }

    /**
     * Renderiza el hub de alertas.
     * @param {HTMLElement} hubEl contenedor #ruana-alert-hub
     * @param {Array} items alertas ordenadas por prioridad
     * @param {Object} state { showAll, expandedDetailId }
     * @param {Object} callbacks { onAction, onShowAll, onCloseDetail, onDismiss, renderDetail }
     */
    function render(hubEl, items, state, callbacks) {
        if (!hubEl) return;
        callbacks = callbacks || {};
        state = state || {};
        items = Array.isArray(items) ? items : [];

        var runtime = getHubRuntime(hubEl);
        var pinnedEl = hubEl.querySelector('.ruana-alert-hub__pinned');
        var cardsEl = hubEl.querySelector('.ruana-alert-hub__cards');
        var moreEl = hubEl.querySelector('.ruana-alert-hub__more');
        var detailEl = hubEl.querySelector('.ruana-alert-hub__detail');

        if (!pinnedEl) {
            pinnedEl = document.createElement('div');
            pinnedEl.className = 'ruana-alert-hub__pinned';
            if (cardsEl) {
                hubEl.insertBefore(pinnedEl, cardsEl);
            } else {
                hubEl.appendChild(pinnedEl);
            }
        }

        var criticalItems = items.filter(function (i) { return i.critical; });
        var normalItems = items.filter(function (i) { return !i.critical; });

        if (!criticalItems.length && !normalItems.length) {
            hubEl.hidden = true;
            clearTimeInterval(runtime);
            pinnedEl.innerHTML = '';
            if (cardsEl) cardsEl.innerHTML = '';
            if (moreEl) moreEl.hidden = true;
            if (detailEl) detailEl.hidden = true;
            runtime.prevCriticalIds = new Set();
            return;
        }

        hubEl.hidden = false;
        startTimeInterval(hubEl, runtime);

        var cardOpts = {
            onAction: callbacks.onAction,
            onDismiss: callbacks.onDismiss
        };

        syncCriticalCards(pinnedEl, criticalItems, cardOpts, runtime);

        var showAll = !!state.showAll;
        var visible = showAll ? normalItems : normalItems.slice(0, MAX_VISIBLE_COLLAPSED);
        var hiddenCount = showAll ? 0 : Math.max(0, normalItems.length - MAX_VISIBLE_COLLAPSED);

        if (cardsEl) {
            cardsEl.innerHTML = '';
            cardsEl.classList.toggle('has-stack-peek', !showAll && normalItems.length > 1);
            visible.forEach(function (item, index) {
                var card = createCard(item, {
                    expanded: state.expandedDetailId === item.id,
                    onAction: callbacks.onAction,
                    onCardClick: item.hasDetail ? callbacks.onAction : null,
                    onDismiss: callbacks.onDismiss
                });
                if (index === 0 && !showAll && normalItems.length > 1) {
                    card.classList.add('is-stack-peek');
                }
                cardsEl.appendChild(card);
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
            } else if (!showAll && normalItems.length > 1) {
                moreEl.hidden = false;
                moreEl.innerHTML = 'Ver todos los avisos (' + normalItems.length + ')';
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
        formatRelativeTime: formatRelativeTime,
        ICONS: ICONS,
        MAX_VISIBLE_COLLAPSED: MAX_VISIBLE_COLLAPSED
    };
})(typeof window !== 'undefined' ? window : globalThis);
