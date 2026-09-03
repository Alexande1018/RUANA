/**
 * RUANA Pulse — Centro de Actividad flotante premium.
 * Reutiliza buildAlertItems() y actividadCinta sin tocar backend.
 */
(function (global) {
    'use strict';

    var TIER_LABELS = {
        action: 'Acción necesaria',
        important: 'Importante',
        info: 'Información',
        completed: 'Completado'
    };

    var SKIP_IDS_WHEN_ENCARGO = ['pagos-restriccion'];

    var ENCARGO_DEDUP_PATTERNS = [
        /confirma.*trabajo/i,
        /liberar el pago/i,
        /encargo activo/i,
        /negociaci[oó]n pendiente/i
    ];

    var state = {
        isOpen: false,
        expandedDetailId: null,
        seenIds: new Set(),
        bound: false
    };

    function prefersReducedMotion() {
        return typeof global.matchMedia === 'function' &&
            global.matchMedia('(prefers-reduced-motion: reduce)').matches;
    }

    function escapeHtml(str) {
        return String(str || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function parseTimestamp(value) {
        if (global.RuanaAlertHub && typeof global.RuanaAlertHub.parseTimestamp === 'function') {
            return global.RuanaAlertHub.parseTimestamp(value);
        }
        if (value == null || value === '') return null;
        var date = new Date(value);
        return Number.isNaN(date.getTime()) ? null : date.getTime();
    }

    function formatRelativeTime(ts) {
        if (global.RuanaAlertHub && typeof global.RuanaAlertHub.formatRelativeTime === 'function') {
            return global.RuanaAlertHub.formatRelativeTime(ts);
        }
        if (!ts) return '';
        var diffMs = Date.now() - ts;
        if (diffMs < 60000) return 'ahora';
        var mins = Math.floor(diffMs / 60000);
        if (mins < 60) return 'hace ' + mins + 'm';
        var hours = Math.floor(mins / 60);
        if (hours < 24) return 'hace ' + hours + 'h';
        return new Date(ts).toLocaleDateString('es-ES', { day: 'numeric', month: 'short' });
    }

    function getDateGroup(ts) {
        if (!ts) return 'Reciente';
        var now = new Date();
        var date = new Date(ts);
        var startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
        var startDate = new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
        var diffDays = Math.floor((startToday - startDate) / 86400000);
        if (diffDays <= 0) return 'Hoy';
        if (diffDays === 1) return 'Ayer';
        if (diffDays < 7) return 'Esta semana';
        return date.toLocaleDateString('es-ES', { day: 'numeric', month: 'short' });
    }

    function isEncargoVisible() {
        var encargo = document.getElementById('contacto-aviso-persistente');
        if (!encargo) return false;
        if (encargo.hidden) return false;
        var style = global.getComputedStyle ? global.getComputedStyle(encargo) : null;
        return style ? style.display !== 'none' : encargo.style.display !== 'none';
    }

    function shouldSkipAlertItem(item) {
        if (!item || !item.id) return true;
        if (isEncargoVisible() && SKIP_IDS_WHEN_ENCARGO.indexOf(item.id) !== -1) return true;
        return false;
    }

    function shouldSkipCintaItem(texto) {
        if (!isEncargoVisible()) return false;
        var text = String(texto || '');
        return ENCARGO_DEDUP_PATTERNS.some(function (re) { return re.test(text); });
    }

    function mapAlertTier(item) {
        if (!item) return 'info';
        if (item.critical) return 'action';
        if (item.id === 'apoyo-pago' || item.id === 'stripe-pendiente') return 'action';
        if (item.type === 'message' || item.type === 'action' || item.id === 'competencia') return 'important';
        if (item.type === 'payment' && item.actionLabel) return 'action';
        return 'info';
    }

    function mapCintaTier(item, index) {
        if (index > 4) return 'completed';
        return 'info';
    }

    function isPendingItem(item) {
        if (!item) return false;
        if (item.critical) return true;
        if (item.actionLabel || item.hasDetail) return true;
        if (item.id === 'mensajes-ruana') return true;
        if (item.id === 'pagos-restriccion') return false;
        return false;
    }

    function buildTimelineEntries(host) {
        var entries = [];
        var buildItems = host && typeof host.buildAlertItems === 'function'
            ? host.buildAlertItems()
            : [];

        buildItems.forEach(function (item) {
            if (shouldSkipAlertItem(item)) return;
            entries.push({
                id: 'alert-' + item.id,
                sourceId: item.id,
                kind: 'alert',
                tier: mapAlertTier(item),
                title: item.title,
                description: item.description || '',
                createdAt: item.createdAt || Date.now(),
                actionLabel: item.actionLabel || null,
                hasDetail: !!item.hasDetail,
                raw: item,
                pending: isPendingItem(item)
            });
        });

        var cinta = host && Array.isArray(host.actividadCinta) ? host.actividadCinta : [];
        cinta.forEach(function (item, index) {
            if (!item || !item.texto) return;
            if (shouldSkipCintaItem(item.texto)) return;
            var ts = parseTimestamp(item.creado_en) || Date.now() - (index + 1) * 3600000;
            entries.push({
                id: 'cinta-' + index + '-' + String(item.texto).slice(0, 24),
                sourceId: null,
                kind: 'cinta',
                tier: mapCintaTier(item, index),
                title: item.texto,
                description: '',
                createdAt: ts,
                actionLabel: null,
                hasDetail: false,
                raw: item,
                pending: false
            });
        });

        entries.sort(function (a, b) {
            var tierOrder = { action: 0, important: 1, info: 2, completed: 3 };
            var ta = tierOrder[a.tier] != null ? tierOrder[a.tier] : 2;
            var tb = tierOrder[b.tier] != null ? tierOrder[b.tier] : 2;
            if (ta !== tb) return ta - tb;
            return (b.createdAt || 0) - (a.createdAt || 0);
        });

        return entries;
    }

    function countPending(entries) {
        return entries.filter(function (e) { return e.pending; }).length;
    }

    function ensureDom() {
        var trigger = document.getElementById('ruana-pulse-trigger');
        var backdrop = document.getElementById('ruana-pulse-backdrop');
        var panel = document.getElementById('ruana-pulse-panel');
        if (trigger && backdrop && panel) return { trigger: trigger, backdrop: backdrop, panel: panel };

        var wrap = document.getElementById('ruana-pulse-trigger-wrap');
        if (!wrap) {
            wrap = document.createElement('div');
            wrap.id = 'ruana-pulse-trigger-wrap';
            wrap.className = 'ruana-pulse-trigger-wrap';
            var anchor = document.querySelector('.inicio-identity');
            if (anchor && anchor.parentNode) {
                anchor.parentNode.insertBefore(wrap, anchor.nextSibling);
            } else {
                var inicio = document.getElementById('module-inicio');
                if (inicio) inicio.insertBefore(wrap, inicio.firstChild);
            }
        }

        if (!trigger) {
            trigger = document.createElement('button');
            trigger.type = 'button';
            trigger.id = 'ruana-pulse-trigger';
            trigger.className = 'ruana-pulse-trigger';
            trigger.setAttribute('aria-expanded', 'false');
            trigger.setAttribute('aria-controls', 'ruana-pulse-panel');
            trigger.innerHTML =
                '<span class="ruana-pulse-trigger__spark" aria-hidden="true">✦</span>' +
                '<span class="ruana-pulse-trigger__label">Actividad</span>' +
                '<span class="ruana-pulse-trigger__badge" hidden aria-label="Novedades pendientes"></span>';
            wrap.appendChild(trigger);
        }

        if (!backdrop) {
            backdrop = document.createElement('div');
            backdrop.id = 'ruana-pulse-backdrop';
            backdrop.className = 'ruana-pulse-backdrop';
            backdrop.setAttribute('aria-hidden', 'true');
            document.body.appendChild(backdrop);
        }

        if (!panel) {
            panel = document.createElement('aside');
            panel.id = 'ruana-pulse-panel';
            panel.className = 'ruana-pulse-panel';
            panel.setAttribute('role', 'dialog');
            panel.setAttribute('aria-modal', 'true');
            panel.setAttribute('aria-label', 'Centro de Actividad RUANA');
            panel.setAttribute('aria-hidden', 'true');
            panel.innerHTML =
                '<div class="ruana-pulse-panel__main">' +
                    '<header class="ruana-pulse-panel__header">' +
                        '<div>' +
                            '<p class="ruana-pulse-panel__kicker">RUANA Pulse</p>' +
                            '<h2 class="ruana-pulse-panel__title">Centro de Actividad</h2>' +
                        '</div>' +
                        '<button type="button" class="ruana-pulse-panel__close" aria-label="Cerrar">' +
                            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>' +
                        '</button>' +
                    '</header>' +
                    '<div class="ruana-pulse-panel__body" id="ruana-pulse-timeline"></div>' +
                '</div>' +
                '<div class="ruana-pulse-detail" id="ruana-pulse-detail" hidden>' +
                    '<div class="ruana-pulse-detail__header">' +
                        '<button type="button" class="ruana-pulse-detail__back">← Volver</button>' +
                        '<span class="ruana-pulse-detail__title" id="ruana-pulse-detail-title"></span>' +
                    '</div>' +
                    '<div class="ruana-pulse-detail__body" id="ruana-pulse-detail-body"></div>' +
                '</div>' +
                '<div id="ruana-pulse-detail-sink" hidden aria-hidden="true"></div>';
            document.body.appendChild(panel);
        }

        return { trigger: trigger, backdrop: backdrop, panel: panel };
    }

    function groupEntries(entries) {
        var groups = [];
        var map = {};
        entries.forEach(function (entry) {
            var label = getDateGroup(entry.createdAt);
            if (!map[label]) {
                map[label] = { label: label, items: [] };
                groups.push(map[label]);
            }
            map[label].items.push(entry);
        });
        return groups;
    }

    function renderTimeline(host, entries) {
        var timelineEl = document.getElementById('ruana-pulse-timeline');
        if (!timelineEl) return;

        if (!entries.length) {
            timelineEl.innerHTML = '<p class="ruana-pulse-panel__empty">Sin actividad pendiente.<br>Tu panel está al día.</p>';
            return;
        }

        var groups = groupEntries(entries);
        var html = '<div class="ruana-pulse-timeline">';

        groups.forEach(function (group) {
            html += '<section class="ruana-pulse-timeline__group">';
            html += '<h3 class="ruana-pulse-timeline__date">' + escapeHtml(group.label) + '</h3>';
            html += '<ul class="ruana-pulse-timeline__list">';

            group.items.forEach(function (entry) {
                var isNew = entry.pending && !state.seenIds.has(entry.id);
                var tierLabel = TIER_LABELS[entry.tier] || TIER_LABELS.info;
                var timeStr = formatRelativeTime(entry.createdAt);
                var actionHtml = entry.actionLabel
                    ? '<button type="button" class="ruana-pulse-item__action" data-pulse-action="' + escapeHtml(entry.sourceId || entry.id) + '">' +
                        escapeHtml(entry.actionLabel) + ' →</button>'
                    : '';

                html +=
                    '<li class="ruana-pulse-item ruana-pulse-item--' + entry.tier + (isNew ? ' is-new' : '') + '" data-pulse-id="' + escapeHtml(entry.id) + '">' +
                        '<div class="ruana-pulse-item__rail">' +
                            '<span class="ruana-pulse-item__dot" aria-hidden="true"></span>' +
                            '<span class="ruana-pulse-item__line" aria-hidden="true"></span>' +
                        '</div>' +
                        '<div class="ruana-pulse-item__content">' +
                            '<span class="ruana-pulse-item__tier">' + escapeHtml(tierLabel) + '</span>' +
                            '<p class="ruana-pulse-item__title">' + escapeHtml(entry.title) + '</p>' +
                            (entry.description
                                ? '<p class="ruana-pulse-item__desc">' + escapeHtml(entry.description) + '</p>'
                                : '') +
                            '<div class="ruana-pulse-item__meta">' +
                                (timeStr ? '<span class="ruana-pulse-item__time">' + escapeHtml(timeStr) + '</span>' : '<span></span>') +
                                actionHtml +
                            '</div>' +
                        '</div>' +
                    '</li>';
            });

            html += '</ul></section>';
        });

        html += '</div>';
        timelineEl.innerHTML = html;

        timelineEl.querySelectorAll('[data-pulse-action]').forEach(function (btn) {
            btn.addEventListener('click', function (e) {
                e.stopPropagation();
                var id = btn.getAttribute('data-pulse-action');
                handleAction(host, id);
            });
        });

        timelineEl.querySelectorAll('.ruana-pulse-item').forEach(function (item) {
            item.addEventListener('click', function () {
                var id = item.getAttribute('data-pulse-id');
                var entry = entries.find(function (e) { return e.id === id; });
                if (entry && entry.hasDetail && entry.sourceId) {
                    openDetail(host, entry.sourceId);
                }
            });
        });
    }

    function updateTriggerBadge(count) {
        var trigger = document.getElementById('ruana-pulse-trigger');
        if (!trigger) return;
        var badge = trigger.querySelector('.ruana-pulse-trigger__badge');
        trigger.classList.toggle('has-pending', count > 0);
        if (badge) {
            if (count > 0) {
                badge.hidden = false;
                badge.textContent = count > 99 ? '99+' : String(count);
            } else {
                badge.hidden = true;
                badge.textContent = '';
            }
        }
    }

    function positionPanel(panel, trigger) {
        if (!panel || !trigger || global.innerWidth < 768) return;
        var rect = trigger.getBoundingClientRect();
        var panelW = panel.offsetWidth || 400;
        var top = rect.bottom + 12;
        var right = Math.max(16, global.innerWidth - rect.right);
        if (right + panelW > global.innerWidth - 16) {
            right = Math.max(16, global.innerWidth - panelW - 16);
        }
        panel.style.top = Math.round(top) + 'px';
        panel.style.right = Math.round(right) + 'px';
        panel.style.bottom = 'auto';
        panel.style.left = 'auto';
        panel.style.transform = state.isOpen ? 'translateY(0) scale(1)' : 'translateY(8px) scale(0.96)';
        panel.classList.add('is-anchored');
    }

    function showDetailView(show) {
        var main = document.querySelector('.ruana-pulse-panel__main');
        var detail = document.getElementById('ruana-pulse-detail');
        if (main) main.style.display = show ? 'none' : '';
        if (detail) {
            detail.hidden = !show;
            detail.classList.toggle('is-active', show);
        }
    }

    function openDetail(host, detailId) {
        var detailBody = document.getElementById('ruana-pulse-detail-body');
        var detailTitle = document.getElementById('ruana-pulse-detail-title');
        var sink = document.getElementById('ruana-pulse-detail-sink');
        if (!detailBody || !host || typeof host.renderAlertDetailPanel !== 'function') return;

        var titles = {
            'apoyo-pago': 'Apoyo RUANA pendiente',
            'mensajes-ruana': 'Mensajes de RUANA',
            'competencia': 'Estado de competencia'
        };

        detailBody.innerHTML = '';
        if (sink) sink.innerHTML = '';

        var wrapper = document.createElement('div');
        wrapper.className = 'ruana-alert-hub__detail';
        detailBody.appendChild(wrapper);

        host._alertHubState = host._alertHubState || { showAll: true, expandedDetailId: null };
        host._alertHubState.expandedDetailId = detailId;

        host.renderAlertDetailPanel(host, wrapper, detailId);

        var closeBtn = wrapper.querySelector('.ruana-alert-hub__detail-close');
        if (closeBtn) {
            closeBtn.addEventListener('click', function () {
                closeDetail();
            });
        }

        if (detailTitle) detailTitle.textContent = titles[detailId] || 'Detalle';
        state.expandedDetailId = detailId;
        showDetailView(true);
    }

    function closeDetail() {
        state.expandedDetailId = null;
        showDetailView(false);
        var detailBody = document.getElementById('ruana-pulse-detail-body');
        if (detailBody) detailBody.innerHTML = '';
    }

    function handleAction(host, itemId) {
        if (!itemId || !host) return;

        if (itemId === 'stripe-pendiente') {
            if (global.RuanaStripePagos && typeof global.RuanaStripePagos.iniciarOnboardingStripe === 'function') {
                close();
                global.RuanaStripePagos.iniciarOnboardingStripe().catch(function (e) {
                    alert(e && e.message ? e.message : String(e));
                });
            }
            return;
        }

        var items = typeof host.buildAlertItems === 'function' ? host.buildAlertItems() : [];
        var item = items.find(function (i) { return i.id === itemId; });
        if (item && item.hasDetail) {
            openDetail(host, itemId);
            return;
        }
    }

    function open(host) {
        var dom = ensureDom();
        if (!dom.panel || state.isOpen) return;

        var entries = buildTimelineEntries(host || global.PrivatePanel);
        entries.forEach(function (e) {
            if (e.pending) state.seenIds.add(e.id);
        });

        renderTimeline(host || global.PrivatePanel, entries);
        updateTriggerBadge(countPending(entries));

        state.isOpen = true;
        dom.backdrop.classList.add('is-visible');
        dom.backdrop.setAttribute('aria-hidden', 'false');
        dom.panel.classList.add('is-open');
        dom.panel.setAttribute('aria-hidden', 'false');
        dom.trigger.classList.add('is-open');
        dom.trigger.setAttribute('aria-expanded', 'true');

        positionPanel(dom.panel, dom.trigger);
        document.body.classList.add('ruana-pulse-open');

        if (!prefersReducedMotion()) {
            requestAnimationFrame(function () { positionPanel(dom.panel, dom.trigger); });
        }
    }

    function close() {
        var dom = ensureDom();
        if (!dom.panel) return;

        closeDetail();
        state.isOpen = false;
        dom.backdrop.classList.remove('is-visible');
        dom.backdrop.setAttribute('aria-hidden', 'true');
        dom.panel.classList.remove('is-open');
        dom.panel.setAttribute('aria-hidden', 'true');
        dom.trigger.classList.remove('is-open');
        dom.trigger.setAttribute('aria-expanded', 'false');
        document.body.classList.remove('ruana-pulse-open');
    }

    function toggle(host) {
        if (state.isOpen) close();
        else open(host);
    }

    function bindEvents(host) {
        if (state.bound) return;
        var dom = ensureDom();

        dom.trigger.addEventListener('click', function () { toggle(host); });
        dom.backdrop.addEventListener('click', close);
        dom.panel.querySelector('.ruana-pulse-panel__close').addEventListener('click', close);

        var backBtn = dom.panel.querySelector('.ruana-pulse-detail__back');
        if (backBtn) backBtn.addEventListener('click', closeDetail);

        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && state.isOpen) {
                if (state.expandedDetailId) closeDetail();
                else close();
            }
        });

        global.addEventListener('resize', function () {
            if (state.isOpen) positionPanel(dom.panel, dom.trigger);
        });

        state.bound = true;
    }

    function render(host) {
        host = host || global.PrivatePanel;
        bindEvents(host);

        var hubEl = document.getElementById('ruana-alert-hub');
        if (hubEl) hubEl.classList.add('ruana-alert-hub--offscreen');

        var cintaEl = document.getElementById('inicio-actividad-cinta');
        if (cintaEl) cintaEl.classList.add('ruana-actividad-cinta--in-pulse');

        var entries = buildTimelineEntries(host);
        var pending = countPending(entries);
        updateTriggerBadge(pending);

        if (state.isOpen && !state.expandedDetailId) {
            renderTimeline(host, entries);
        }

        if (global.AliadoShell && typeof global.AliadoShell.refresh === 'function') {
            global.AliadoShell.refresh();
        }
    }

    function getPendingCount(host) {
        return countPending(buildTimelineEntries(host || global.PrivatePanel));
    }

    function getSummaries(host) {
        return buildTimelineEntries(host || global.PrivatePanel)
            .filter(function (e) { return e.pending && e.kind === 'alert'; })
            .map(function (e) {
                return { id: e.sourceId, title: e.title };
            });
    }

    function hasPendingActivity(host) {
        return getPendingCount(host) > 0;
    }

    global.RuanaPulse = {
        render: render,
        open: open,
        close: close,
        toggle: toggle,
        isOpen: function () { return state.isOpen; },
        getPendingCount: getPendingCount,
        getSummaries: getSummaries,
        hasPendingActivity: hasPendingActivity,
        buildTimelineEntries: buildTimelineEntries
    };
})(typeof window !== 'undefined' ? window : globalThis);
