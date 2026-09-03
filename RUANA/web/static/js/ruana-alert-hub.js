/**
 * RUANA Pulse — Centro de Actividad
 * Panel flotante premium. Reutiliza los avisos existentes (sin lógica de negocio nueva).
 * API pública: RuanaAlertHub (fachada de compatibilidad) y RuanaPulse (alias).
 */
(function (global) {
    'use strict';

    var MAX_VISIBLE_COLLAPSED = 3;
    var hubStateMap = new WeakMap();
    var boundDocs = false;
    var lastPendingCount = 0;

    var PRIORITY_RANK = { action: 0, important: 1, info: 2, done: 3 };
    var PRIORITY_LABELS = {
        action: 'Acción necesaria',
        important: 'Importante',
        info: 'Información',
        done: 'Completado'
    };

    var ICONS = {
        payment: '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="20" height="14" x="2" y="5" rx="2"/><line x1="2" y1="10" x2="22" y2="10"/></svg>',
        message: '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>',
        action: '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>',
        info: '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>',
        critical: '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M8 10.5c1.2-1.1 2.4-1.1 4 0s2.8 1.1 4 0"/><line x1="12" y1="14.5" x2="12" y2="17"/><circle cx="12" cy="7.5" r="0.75" fill="currentColor" stroke="none"/></svg>',
        done: '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>'
    };

    var EXIT_TOASTS = {
        'score-bajo': 'Tu Score ya no requiere atención urgente.',
        'stripe-pendiente': 'Cuenta de pago conectada correctamente.',
        'apoyo-pago': 'Apoyo RUANA regularizado.',
        'mensajes-ruana': 'No tienes mensajes pendientes de RUANA.',
        'competencia': 'El estado de competencia se ha actualizado.'
    };

    var TONE_BY_TYPE = {
        payment: 'prioritario',
        message: 'estable',
        action: 'competencia',
        info: 'thread'
    };

    var ENCARGO_DUPLICATE_RE = /confirma[\s\S]{0,40}trabajo[\s\S]{0,40}liberar[\s\S]{0,20}pago/;

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

    function parseTimestamp(value) {
        if (value == null || value === '') return null;
        if (typeof value === 'number' && Number.isFinite(value)) return value;
        var date = new Date(value);
        return Number.isNaN(date.getTime()) ? null : date.getTime();
    }

    function startOfDay(ms) {
        var d = new Date(ms);
        d.setHours(0, 0, 0, 0);
        return d.getTime();
    }

    function dayBucket(ts) {
        var ms = parseTimestamp(ts);
        if (ms == null) return 'hoy';
        var today = startOfDay(Date.now());
        var day = startOfDay(ms);
        if (day === today) return 'hoy';
        if (day === today - 86400000) return 'ayer';
        return 'anterior';
    }

    function dayLabel(bucket) {
        if (bucket === 'ayer') return 'Ayer';
        if (bucket === 'anterior') return 'Anterior';
        return 'Hoy';
    }

    function isEncargoVisible() {
        var el = document.getElementById('contacto-aviso-persistente');
        if (!el) return false;
        if (el.hidden) return false;
        var display = (el.style && el.style.display) || '';
        if (display === 'none') return false;
        return true;
    }

    function looksLikeEncargoDuplicate(item) {
        var blob = String((item && item.title) || '') + ' ' + String((item && item.description) || '');
        return ENCARGO_DUPLICATE_RE.test(blob.toLowerCase());
    }

    function classifyPriority(item) {
        if (!item) return 'info';
        if (item.visualPriority && PRIORITY_RANK[item.visualPriority] != null) {
            return item.visualPriority;
        }
        if (item.completed || item.type === 'done') return 'done';
        if (item.demoted) return 'info';
        if (item.critical || item.type === 'payment') return 'action';
        if (item.type === 'message' || item.type === 'action') return 'important';
        return 'info';
    }

    function applyVisualHierarchy(item) {
        var next = item || {};
        if (isEncargoVisible() && looksLikeEncargoDuplicate(next) && classifyPriority(next) === 'action') {
            next = Object.assign({}, next, { visualPriority: 'info', demoted: true });
        }
        return next;
    }

    function isPendingForBadge(item) {
        var priority = classifyPriority(item);
        return priority === 'action' || priority === 'important';
    }

    function getHubRuntime(hubEl) {
        if (!hubStateMap.has(hubEl)) {
            hubStateMap.set(hubEl, {
                prevItemIds: new Set(),
                initialized: false,
                timeInterval: null,
                bound: false
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
            hubEl.querySelectorAll('.ruana-pulse-item__time[data-ts], .ruana-alert-card__time[data-ts]').forEach(function (el) {
                el.textContent = formatRelativeTime(Number(el.getAttribute('data-ts')));
            });
        }, 30000);
    }

    function showResolvedToast(id) {
        var msg = EXIT_TOASTS[id];
        if (!msg) return;
        if (global.RuanaUI && typeof global.RuanaUI.success === 'function') {
            global.RuanaUI.success('Resuelto', msg, 3500);
        }
    }

    function syncResolvedExits(nextIds, runtime) {
        var prevIds = runtime.prevItemIds || new Set();
        prevIds.forEach(function (id) {
            if (nextIds.has(id)) return;
            showResolvedToast(id);
        });
        runtime.prevItemIds = nextIds;
    }

    function getPulseRoot(hubEl) {
        if (hubEl && hubEl.closest) {
            var nested = hubEl.closest('.ruana-pulse');
            if (nested) return nested;
        }
        return document.getElementById('ruana-pulse');
    }

    function getHubEl(root) {
        if (root && root.classList && root.classList.contains('ruana-alert-hub')) return root;
        if (root) {
            var nested = root.querySelector('#ruana-alert-hub, .ruana-alert-hub');
            if (nested) return nested;
        }
        return document.getElementById('ruana-alert-hub');
    }

    function isOpen(hubEl) {
        var root = getPulseRoot(hubEl);
        if (root) return root.classList.contains('is-open') && !root.hidden;
        var hub = getHubEl(hubEl);
        return !!(hub && !hub.hidden);
    }

    function setPageLocked(locked) {
        var root = document.documentElement;
        if (!root) return;
        root.classList.toggle('is-ruana-pulse-open', !!locked);
        if (document.body) {
            if (locked) {
                if (document.body.dataset.ruanaPulseOverflow == null) {
                    document.body.dataset.ruanaPulseOverflow = document.body.style.overflow || '';
                }
                document.body.style.overflow = 'hidden';
            } else if (document.body.dataset.ruanaPulseOverflow != null) {
                document.body.style.overflow = document.body.dataset.ruanaPulseOverflow;
                delete document.body.dataset.ruanaPulseOverflow;
            }
        }
    }

    function syncTriggerAria(open) {
        document.querySelectorAll('#ruana-pulse-trigger, .ruana-pulse-trigger').forEach(function (btn) {
            btn.setAttribute('aria-expanded', open ? 'true' : 'false');
            btn.classList.toggle('is-open', !!open);
        });
    }

    function open(hubEl) {
        var root = getPulseRoot(hubEl);
        var hub = getHubEl(root || hubEl);
        if (root) {
            root.hidden = false;
            root.classList.add('is-open');
            root.setAttribute('aria-hidden', 'false');
        }
        if (hub) {
            hub.hidden = false;
            if (!prefersReducedMotion()) hub.classList.add('is-pulse-enter');
        }
        setPageLocked(true);
        syncTriggerAria(true);
        if (hub) {
            var closeBtn = hub.querySelector('.ruana-pulse__close');
            if (closeBtn && typeof closeBtn.focus === 'function') {
                try { closeBtn.focus(); } catch (e) { /* ignore */ }
            }
        }
        return true;
    }

    function close(hubEl) {
        var root = getPulseRoot(hubEl);
        var hub = getHubEl(root || hubEl);
        if (root) {
            root.classList.remove('is-open');
            root.classList.add('is-closing');
            var finish = function () {
                root.hidden = true;
                root.classList.remove('is-closing');
                root.setAttribute('aria-hidden', 'true');
            };
            if (prefersReducedMotion()) {
                finish();
            } else {
                setTimeout(finish, 220);
            }
        } else if (hub) {
            hub.hidden = true;
        }
        if (hub) hub.classList.remove('is-pulse-enter');
        setPageLocked(false);
        syncTriggerAria(false);
        var trigger = document.getElementById('ruana-pulse-trigger');
        if (trigger && typeof trigger.focus === 'function' && document.body.contains(trigger)) {
            try { trigger.focus({ preventScroll: true }); } catch (e) { /* ignore */ }
        }
        return true;
    }

    function toggle(hubEl) {
        if (isOpen(hubEl)) return close(hubEl);
        return open(hubEl);
    }

    function bindEscapeAndBackdrop() {
        if (boundDocs) return;
        boundDocs = true;
        document.addEventListener('keydown', function (e) {
            if (e.key !== 'Escape') return;
            if (!isOpen()) return;
            e.preventDefault();
            close();
        });
        document.addEventListener('click', function (e) {
            var dismiss = e.target && e.target.closest && e.target.closest('[data-ruana-pulse-dismiss]');
            if (dismiss) close();
        });
    }

    function bindHubChrome(hubEl, runtime) {
        if (!hubEl || runtime.bound) return;
        runtime.bound = true;
        bindEscapeAndBackdrop();
        var closeBtn = hubEl.querySelector('.ruana-pulse__close');
        if (closeBtn) {
            closeBtn.addEventListener('click', function (e) {
                e.preventDefault();
                e.stopPropagation();
                close(hubEl);
            });
        }
        var root = getPulseRoot(hubEl);
        if (root && !root.dataset.pulseBound) {
            root.dataset.pulseBound = '1';
            root.addEventListener('click', function (e) {
                if (e.target === root) close(hubEl);
            });
        }
    }

    function bindTriggers() {
        document.querySelectorAll('#ruana-pulse-trigger, .ruana-pulse-trigger').forEach(function (btn) {
            if (btn.dataset.pulseBound) return;
            btn.dataset.pulseBound = '1';
            btn.setAttribute('aria-haspopup', 'dialog');
            btn.setAttribute('aria-controls', 'ruana-alert-hub');
            btn.setAttribute('aria-expanded', 'false');
            btn.addEventListener('click', function (e) {
                e.preventDefault();
                e.stopPropagation();
                toggle();
            });
        });
    }

    function countPending(items) {
        return (Array.isArray(items) ? items : []).filter(isPendingForBadge).length;
    }

    function syncTrigger(items) {
        var pending = countPending(items);
        var grew = pending > lastPendingCount;
        lastPendingCount = pending;
        document.querySelectorAll('#ruana-pulse-trigger, .ruana-pulse-trigger').forEach(function (btn) {
            var badge = btn.querySelector('.ruana-pulse-trigger__badge');
            if (!badge) return;
            if (pending > 0) {
                badge.hidden = false;
                badge.textContent = pending > 99 ? '99+' : String(pending);
                badge.setAttribute('aria-label', pending + (pending === 1 ? ' aviso pendiente' : ' avisos pendientes'));
                btn.classList.add('has-pending');
                if (grew && !prefersReducedMotion()) {
                    badge.classList.remove('is-live');
                    void badge.offsetWidth;
                    badge.classList.add('is-live');
                }
            } else {
                badge.hidden = true;
                badge.textContent = '';
                badge.removeAttribute('aria-label');
                badge.classList.remove('is-live');
                btn.classList.remove('has-pending');
            }
        });
    }

    function ensurePulseChrome(hubEl) {
        if (!hubEl) return;
        hubEl.classList.add('ruana-alert-hub', 'ruana-pulse__panel');
        hubEl.setAttribute('role', 'dialog');
        hubEl.setAttribute('aria-modal', 'true');
        hubEl.setAttribute('aria-labelledby', 'ruana-pulse-title');

        if (!hubEl.querySelector('.ruana-pulse__header')) {
            var header = document.createElement('header');
            header.className = 'ruana-pulse__header';
            header.innerHTML =
                '<div class="ruana-pulse__heading">' +
                    '<p class="ruana-pulse__kicker">RUANA Pulse</p>' +
                    '<h2 class="ruana-pulse__title" id="ruana-pulse-title">Centro de Actividad</h2>' +
                '</div>' +
                '<button type="button" class="ruana-pulse__close" aria-label="Cerrar centro de actividad">' +
                    '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>' +
                '</button>';
            hubEl.insertBefore(header, hubEl.firstChild);
        }

        var body = hubEl.querySelector('.ruana-pulse__body');
        if (!body) {
            body = document.createElement('div');
            body.className = 'ruana-pulse__body';
            var pinned = hubEl.querySelector('.ruana-alert-hub__pinned');
            var cards = hubEl.querySelector('.ruana-alert-hub__cards');
            var more = hubEl.querySelector('.ruana-alert-hub__more');
            var detail = hubEl.querySelector('.ruana-alert-hub__detail');
            if (!cards) {
                cards = document.createElement('div');
                cards.className = 'ruana-alert-hub__cards';
            }
            cards.classList.add('ruana-pulse__timeline');
            if (pinned) body.appendChild(pinned);
            body.appendChild(cards);
            if (more) body.appendChild(more);
            if (detail) body.appendChild(detail);
            else {
                detail = document.createElement('div');
                detail.className = 'ruana-alert-hub__detail';
                detail.hidden = true;
                body.appendChild(detail);
            }
            hubEl.appendChild(body);
        } else {
            var cardsEl = body.querySelector('.ruana-alert-hub__cards');
            if (cardsEl) cardsEl.classList.add('ruana-pulse__timeline');
        }

        var pinnedEl = hubEl.querySelector('.ruana-alert-hub__pinned');
        if (pinnedEl) pinnedEl.hidden = true;

        var moreEl = hubEl.querySelector('.ruana-alert-hub__more');
        if (moreEl) moreEl.hidden = true;
    }

    function createTimelineItem(item, opts) {
        opts = opts || {};
        var priority = classifyPriority(item);
        var row = document.createElement('li');
        var tone = item.tone || TONE_BY_TYPE[item.type] || 'thread';
        row.className = 'ruana-pulse-item ruana-pulse-item--' + priority;
        row.setAttribute('data-alert-id', item.id);
        row.setAttribute('data-alert-tone', item.criticalTone || tone);
        row.setAttribute('data-priority', priority);
        if (opts.expanded) row.classList.add('is-expanded');
        if (item._isNew) row.classList.add('is-new');
        if (item.demoted) row.classList.add('is-demoted');
        if (item.critical) row.classList.add('is-critical');

        var iconKey = priority === 'done' ? 'done' : (item.critical ? 'critical' : (item.type || 'info'));
        var timeHtml = '';
        if (item.createdAt) {
            timeHtml = '<time class="ruana-pulse-item__time" data-ts="' + Number(item.createdAt) + '">' +
                escapeHtml(formatRelativeTime(item.createdAt)) + '</time>';
        }
        var actionHtml = '';
        if (item.actionLabel) {
            actionHtml = '<button type="button" class="ruana-pulse-item__action" data-alert-action="' +
                escapeHtml(item.id) + '">' + escapeHtml(item.actionLabel) +
                '<span aria-hidden="true"> →</span></button>';
        }

        row.innerHTML =
            '<span class="ruana-pulse-item__rail" aria-hidden="true"></span>' +
            '<span class="ruana-pulse-item__dot" aria-hidden="true"></span>' +
            '<div class="ruana-pulse-item__card">' +
                '<span class="ruana-pulse-item__icon" aria-hidden="true">' +
                    (ICONS[iconKey] || ICONS.info) +
                '</span>' +
                '<div class="ruana-pulse-item__body">' +
                    '<p class="ruana-pulse-item__kind">' + escapeHtml(PRIORITY_LABELS[priority] || 'Información') + '</p>' +
                    '<div class="ruana-pulse-item__title-row">' +
                        '<p class="ruana-pulse-item__title">' + escapeHtml(item.title) + '</p>' +
                        timeHtml +
                    '</div>' +
                    (item.description
                        ? '<p class="ruana-pulse-item__desc">' + escapeHtml(item.description) + '</p>'
                        : '') +
                    actionHtml +
                '</div>' +
            '</div>';

        if (item.actionLabel && typeof opts.onAction === 'function') {
            var btn = row.querySelector('[data-alert-action]');
            if (btn) {
                btn.addEventListener('click', function (e) {
                    e.stopPropagation();
                    opts.onAction(item);
                });
            }
        }

        if (typeof opts.onCardClick === 'function') {
            row.addEventListener('click', function (e) {
                if (e.target && e.target.closest && e.target.closest('[data-alert-action]')) return;
                opts.onCardClick(item);
            });
        }

        return row;
    }

    function sortForTimeline(items) {
        var bucketOrder = { hoy: 0, ayer: 1, anterior: 2 };
        return items.slice().sort(function (a, b) {
            var ba = bucketOrder[dayBucket(a.createdAt)] - bucketOrder[dayBucket(b.createdAt)];
            if (ba !== 0) return ba;
            var pa = PRIORITY_RANK[classifyPriority(a)] - PRIORITY_RANK[classifyPriority(b)];
            if (pa !== 0) return pa;
            return (Number(b.priority) || 0) - (Number(a.priority) || 0);
        });
    }

    function renderTimeline(cardsEl, items, state, callbacks) {
        cardsEl.innerHTML = '';
        cardsEl.classList.remove('has-stack-peek');
        if (!items.length) {
            cardsEl.innerHTML =
                '<div class="ruana-pulse__empty">' +
                    '<p class="ruana-pulse__empty-title">Sin actividad pendiente</p>' +
                    '<p class="ruana-pulse__empty-copy">Cuando RUANA tenga avisos o mensajes para ti, aparecerán aquí.</p>' +
                '</div>';
            return;
        }

        var sorted = sortForTimeline(items);
        var groups = [];
        sorted.forEach(function (item) {
            var bucket = dayBucket(item.createdAt);
            var last = groups[groups.length - 1];
            if (!last || last.bucket !== bucket) {
                groups.push({ bucket: bucket, items: [item] });
            } else {
                last.items.push(item);
            }
        });

        groups.forEach(function (group) {
            var section = document.createElement('section');
            section.className = 'ruana-pulse__day';
            section.setAttribute('data-day', group.bucket);
            var heading = document.createElement('h3');
            heading.className = 'ruana-pulse__day-label';
            heading.textContent = dayLabel(group.bucket);
            var list = document.createElement('ol');
            list.className = 'ruana-pulse__list';
            group.items.forEach(function (item) {
                list.appendChild(createTimelineItem(item, {
                    expanded: state && state.expandedDetailId === item.id,
                    onAction: callbacks.onAction,
                    onCardClick: item.hasDetail ? callbacks.onAction : null
                }));
            });
            section.appendChild(heading);
            section.appendChild(list);
            cardsEl.appendChild(section);
        });
    }

    function render(hubEl, items, state, callbacks) {
        if (!hubEl) return;
        callbacks = callbacks || {};
        state = state || {};
        items = Array.isArray(items) ? items : [];

        var runtime = getHubRuntime(hubEl);
        ensurePulseChrome(hubEl);
        bindHubChrome(hubEl, runtime);
        bindTriggers();

        var visualItems = items.map(applyVisualHierarchy);
        var nextAllIds = new Set(visualItems.map(function (i) { return i.id; }));

        if (runtime.initialized) {
            visualItems.forEach(function (item) {
                if (!runtime.prevItemIds.has(item.id)) item._isNew = true;
            });
        }

        if (visualItems.length) {
            hubEl.hidden = false;
            hubEl.removeAttribute('hidden');
        }

        var pulseRoot = getPulseRoot(hubEl);
        var panelMode = !!pulseRoot;

        if (!visualItems.length) {
            if (!panelMode) {
                hubEl.hidden = true;
                clearTimeInterval(runtime);
                var emptyCards = hubEl.querySelector('.ruana-alert-hub__cards');
                if (emptyCards) emptyCards.innerHTML = '';
                var emptyMore = hubEl.querySelector('.ruana-alert-hub__more');
                if (emptyMore) emptyMore.hidden = true;
                var emptyDetail = hubEl.querySelector('.ruana-alert-hub__detail');
                if (emptyDetail) {
                    emptyDetail.hidden = true;
                    emptyDetail.innerHTML = '';
                }
                runtime.prevItemIds = new Set();
                syncTrigger([]);
                return;
            }
        }

        if (runtime.initialized) syncResolvedExits(nextAllIds, runtime);
        else runtime.prevItemIds = nextAllIds;
        runtime.initialized = true;

        startTimeInterval(hubEl, runtime);

        var cardsEl = hubEl.querySelector('.ruana-alert-hub__cards');
        var moreEl = hubEl.querySelector('.ruana-alert-hub__more');
        var detailEl = hubEl.querySelector('.ruana-alert-hub__detail');

        if (cardsEl) {
            renderTimeline(cardsEl, visualItems, state, callbacks);
        }

        if (moreEl) moreEl.hidden = true;

        if (detailEl) {
            if (state.expandedDetailId && typeof callbacks.renderDetail === 'function') {
                detailEl.hidden = false;
                callbacks.renderDetail(detailEl, state.expandedDetailId);
                if (typeof detailEl.scrollIntoView === 'function') {
                    requestAnimationFrame(function () {
                        detailEl.scrollIntoView({ block: 'nearest', behavior: prefersReducedMotion() ? 'auto' : 'smooth' });
                    });
                }
            } else {
                detailEl.hidden = true;
                detailEl.innerHTML = '';
            }
        }

        syncTrigger(visualItems);
        hubEl.setAttribute('data-pulse-count', String(visualItems.length));
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

    function getVisibleAlertSummaries(hubEl) {
        var hub = hubEl || document.getElementById('ruana-alert-hub');
        if (!hub) return [];
        return Array.from(hub.querySelectorAll('[data-alert-id]')).map(function (node) {
            var titleEl = node.querySelector('.ruana-pulse-item__title, .ruana-alert-card__title');
            return {
                id: node.getAttribute('data-alert-id'),
                title: titleEl ? titleEl.textContent.trim() : ''
            };
        }).filter(function (entry) {
            return entry.id && entry.id !== 'null';
        });
    }

    function createCard(item, opts) {
        return createTimelineItem(item, opts);
    }

    if (typeof document !== 'undefined') {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', function () {
                bindTriggers();
                bindEscapeAndBackdrop();
            });
        } else {
            bindTriggers();
            bindEscapeAndBackdrop();
        }
    }

    var api = {
        render: render,
        createCard: createCard,
        createTimelineItem: createTimelineItem,
        renderDetailHeader: renderDetailHeader,
        getVisibleAlertSummaries: getVisibleAlertSummaries,
        truncate: truncate,
        escapeHtml: escapeHtml,
        formatRelativeTime: formatRelativeTime,
        parseTimestamp: parseTimestamp,
        classifyPriority: classifyPriority,
        countPending: countPending,
        open: open,
        close: close,
        toggle: toggle,
        isOpen: isOpen,
        bindTriggers: bindTriggers,
        ICONS: ICONS,
        PRIORITY_LABELS: PRIORITY_LABELS,
        MAX_VISIBLE_COLLAPSED: MAX_VISIBLE_COLLAPSED
    };

    global.RuanaAlertHub = api;
    global.RuanaPulse = api;
})(typeof window !== 'undefined' ? window : globalThis);
