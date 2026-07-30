/**
 * RUANA Ally Shell — navegación por módulos (solo presentación).
 * No modifica lógica de negocio de PrivatePanel.
 */
(function (global) {
    'use strict';

    const MODULES = ['inicio', 'directorio', 'solicitudes', 'conexiones', 'perfil'];
    const SELECTOR_MODULE = {
        '#inicio-identity': 'inicio',
        '.inicio-quick-grid': 'inicio',
        '#inicio-tasks': 'inicio',
        '.metricas-block': 'inicio',
        '#metrica-card-score': 'inicio',
        '#module-inicio': 'inicio',
        '.directorio-panel': 'directorio',
        '#directorio-panel': 'directorio',
        '#directorio-search': 'directorio',
        '#module-directorio': 'directorio',
        '#solicitudes-entrantes-wrap': 'solicitudes',
        '#solicitudes-list': 'solicitudes',
        '.solicitudes-zone': 'solicitudes',
        '#module-solicitudes': 'solicitudes',
        '.crear-solicitud-zone': 'conexiones',
        '#module-conexiones': 'conexiones',
        '.perfil-block': 'perfil',
        '#perfil-avatar': 'perfil',
        '#perfil-nombre': 'perfil',
        '#detail-descripcion-wrap': 'perfil',
        '#perfil-status': 'perfil',
        '#catalogo-servicios-wrap': 'perfil',
        '#btn-invitar-aliado': 'perfil',
        '#module-perfil': 'perfil',
        '#ruana-help-fab': null,
        '#btn-replay-onboarding': null,
        '.aliado-shell-nav-list': null,
        '#aliado-shell-bottom': null,
        '.ruana-brand': null
    };

    let current = 'inicio';
    let mirrorObserver = null;

    function qs(sel, root) {
        return (root || document).querySelector(sel);
    }

    function qsa(sel, root) {
        return Array.from((root || document).querySelectorAll(sel));
    }

    function isVisible(el) {
        if (!el) return false;
        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden') return false;
        return el.getAttribute('style') ? !/display\s*:\s*none/i.test(el.getAttribute('style')) || style.display !== 'none' : true;
    }

    function showModule(name, options) {
        const opts = options || {};
        const target = MODULES.includes(name) ? name : 'inicio';
        current = target;

        qsa('.aliado-module').forEach((pane) => {
            const active = pane.getAttribute('data-aliado-module') === target;
            pane.classList.toggle('is-active', active);
            pane.setAttribute('aria-hidden', active ? 'false' : 'true');
        });

        qsa('[data-aliado-nav]').forEach((btn) => {
            const active = btn.getAttribute('data-aliado-nav') === target;
            btn.classList.toggle('is-active', active);
            if (btn.hasAttribute('aria-selected')) {
                btn.setAttribute('aria-selected', active ? 'true' : 'false');
            }
        });

        if (!opts.skipHash) {
            try {
                const hash = target === 'inicio' ? '#inicio' : '#' + target;
                if (location.hash !== hash) {
                    history.replaceState(null, '', hash);
                }
            } catch (_) { /* ignore */ }
        }

        if (!opts.skipScroll) {
            const main = qs('.panel-container');
            if (main) {
                window.scrollTo({ top: 0, behavior: opts.instant ? 'auto' : 'smooth' });
            }
        }

        refreshInicioSurface();
        updateNavBadges();

        document.dispatchEvent(new CustomEvent('aliado-module-change', { detail: { module: target } }));
        return target;
    }

    function moduleForSelector(selector) {
        if (!selector) return null;
        if (SELECTOR_MODULE[selector] !== undefined) return SELECTOR_MODULE[selector];
        for (const key of Object.keys(SELECTOR_MODULE)) {
            if (selector.indexOf(key.replace(/^[.#]/, '')) !== -1 && SELECTOR_MODULE[key]) {
                return SELECTOR_MODULE[key];
            }
        }
        try {
            const el = document.querySelector(selector);
            if (!el) return null;
            const pane = el.closest('.aliado-module');
            return pane ? pane.getAttribute('data-aliado-module') : null;
        } catch (_) {
            return null;
        }
    }

    function ensureModuleForSelector(selector) {
        const mod = moduleForSelector(selector);
        if (mod) showModule(mod, { skipScroll: true, instant: true });
        return mod;
    }

    function copyText(fromId, toId) {
        const from = document.getElementById(fromId);
        const to = document.getElementById(toId);
        if (from && to) to.textContent = from.textContent || '—';
    }

    function syncInicioIdentity() {
        copyText('perfil-nombre', 'inicio-nombre');
        copyText('perfil-marca', 'inicio-marca');
        copyText('metric-score', 'inicio-score');

        const statusSrc = document.getElementById('perfil-status');
        const statusDst = document.getElementById('inicio-status');
        if (statusSrc && statusDst) {
            const text = statusSrc.querySelector('.status-text');
            statusDst.dataset.status = statusSrc.dataset.status || '';
            const label = statusDst.querySelector('.inicio-status-label');
            if (label && text) label.textContent = text.textContent || '—';
        }

        const avatarImg = document.getElementById('perfil-avatar-img');
        const avatarIni = document.getElementById('perfil-avatar-iniciales');
        const mirror = document.getElementById('inicio-avatar');
        const mirrorImg = document.getElementById('inicio-avatar-img');
        const mirrorIni = document.getElementById('inicio-avatar-iniciales');
        if (!mirror) return;

        if (avatarImg && mirrorImg && !avatarImg.hidden && avatarImg.getAttribute('src')) {
            mirrorImg.src = avatarImg.getAttribute('src');
            mirrorImg.hidden = false;
            if (mirrorIni) mirrorIni.hidden = true;
        } else {
            if (mirrorImg) {
                mirrorImg.removeAttribute('src');
                mirrorImg.hidden = true;
            }
            if (mirrorIni && avatarIni) {
                mirrorIni.textContent = avatarIni.textContent || 'RU';
                mirrorIni.hidden = false;
            }
        }

        const srcAvatar = document.getElementById('perfil-avatar');
        if (srcAvatar && srcAvatar.dataset.etiqueta) {
            mirror.dataset.etiqueta = srcAvatar.dataset.etiqueta;
        }
    }

    function countListItems(listId) {
        const list = document.getElementById(listId);
        if (!list) return 0;
        return list.querySelectorAll('.solicitud-card, .profesional-card').length;
    }

    function refreshInicioTasks() {
        const list = document.getElementById('inicio-tasks-list');
        const empty = document.getElementById('inicio-tasks-empty');
        if (!list || !empty) return;

        const tasks = [];

        const contacto = document.getElementById('contacto-aviso-persistente');
        if (contacto && isVisible(contacto)) {
            tasks.push({
                text: 'Tienes un contacto activo pendiente de cierre',
                action: 'conexiones',
                label: 'Revisar'
            });
        }

        const pagosBanner = document.getElementById('aviso-pagos-pendientes-banner');
        const pagosWrap = document.getElementById('pagos-apoyo-ruana-wrap');
        if ((pagosBanner && isVisible(pagosBanner)) || (pagosWrap && isVisible(pagosWrap))) {
            tasks.push({
                text: 'Pagos o apoyos RUANA pendientes',
                action: 'inicio',
                label: 'Ver avisos',
                scrollAlerts: true
            });
        }

        const notif = document.getElementById('notificaciones-ruana-wrap');
        if (notif && isVisible(notif)) {
            tasks.push({
                text: 'Mensajes nuevos de RUANA',
                action: 'inicio',
                label: 'Abrir',
                scrollAlerts: true
            });
        }

        const scoreAlerta = document.getElementById('score-alerta-panel');
        if (scoreAlerta && scoreAlerta.classList.contains('visible')) {
            tasks.push({
                text: 'Tu Score RUANA necesita atención',
                action: 'inicio',
                label: 'Ver score'
            });
        }

        const entrantes = countListItems('solicitudes-list');
        if (entrantes > 0) {
            tasks.push({
                text: entrantes === 1
                    ? '1 solicitud entrante por atender'
                    : entrantes + ' solicitudes entrantes por atender',
                action: 'solicitudes',
                label: 'Bandeja'
            });
        }

        list.innerHTML = '';
        if (!tasks.length) {
            empty.hidden = false;
            return;
        }
        empty.hidden = true;
        tasks.forEach((task) => {
            const li = document.createElement('li');
            const span = document.createElement('span');
            span.textContent = task.text;
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.textContent = task.label;
            btn.addEventListener('click', () => {
                showModule(task.action);
                if (task.scrollAlerts) {
                    const alerts = qs('.aliado-shell-alerts');
                    if (alerts) alerts.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }
            });
            li.appendChild(span);
            li.appendChild(btn);
            list.appendChild(li);
        });
    }

    function updateNavBadges() {
        const entrantes = countListItems('solicitudes-list');
        qsa('[data-aliado-badge="solicitudes"]').forEach((badge) => {
            if (entrantes > 0) {
                badge.textContent = String(entrantes > 99 ? '99+' : entrantes);
                badge.classList.add('is-visible');
            } else {
                badge.classList.remove('is-visible');
                badge.textContent = '';
            }
        });
    }

    function refreshInicioSurface() {
        syncInicioIdentity();
        refreshInicioTasks();
        updateNavBadges();
    }

    function bindNav() {
        qsa('[data-aliado-nav]').forEach((btn) => {
            btn.addEventListener('click', () => {
                const name = btn.getAttribute('data-aliado-nav');
                showModule(name);
            });
        });

        qsa('[data-aliado-goto]').forEach((btn) => {
            btn.addEventListener('click', () => {
                showModule(btn.getAttribute('data-aliado-goto'));
            });
        });
    }

    function readHashModule() {
        const hash = (location.hash || '').replace(/^#/, '').toLowerCase();
        if (MODULES.includes(hash)) return hash;
        return 'inicio';
    }

    function startMirrorObserver() {
        const sources = [
            document.getElementById('perfil-nombre'),
            document.getElementById('perfil-marca'),
            document.getElementById('perfil-status'),
            document.getElementById('metric-score'),
            document.getElementById('perfil-avatar'),
            document.getElementById('solicitudes-list'),
            document.getElementById('contacto-aviso-persistente'),
            document.getElementById('pagos-apoyo-ruana-wrap'),
            document.getElementById('notificaciones-ruana-wrap'),
            document.getElementById('score-alerta-panel')
        ].filter(Boolean);

        if (!sources.length || typeof MutationObserver === 'undefined') return;

        mirrorObserver = new MutationObserver(() => {
            refreshInicioSurface();
        });
        sources.forEach((el) => {
            mirrorObserver.observe(el, {
                childList: true,
                subtree: true,
                characterData: true,
                attributes: true,
                attributeFilter: ['style', 'class', 'data-status', 'data-etiqueta', 'hidden', 'src']
            });
        });
    }

    function init() {
        document.documentElement.classList.add('aliado-shell-enabled');
        document.body.classList.add('aliado-app');
        bindNav();
        showModule(readHashModule(), { skipHash: false, instant: true });
        startMirrorObserver();
        refreshInicioSurface();

        window.addEventListener('hashchange', () => {
            showModule(readHashModule(), { skipHash: true });
        });

        // Re-sync when panel finishes loading / data paints
        const loading = document.getElementById('panel-loading');
        if (loading && typeof MutationObserver !== 'undefined') {
            const loadObs = new MutationObserver(() => {
                if (!document.body.classList.contains('panel-loading')) {
                    refreshInicioSurface();
                }
            });
            loadObs.observe(document.body, { attributes: true, attributeFilter: ['class'] });
        }

        setInterval(refreshInicioSurface, 8000);
    }

    const api = {
        show: showModule,
        current: () => current,
        modules: MODULES.slice(),
        ensureModuleForSelector: ensureModuleForSelector,
        moduleForSelector: moduleForSelector,
        refresh: refreshInicioSurface
    };

    global.AliadoShell = api;

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})(window);
