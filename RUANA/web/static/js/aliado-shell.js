/**
 * RUANA Ally Shell — navegación por módulos (solo presentación).
 * No modifica lógica de negocio de PrivatePanel.
 */
(function (global) {
    'use strict';

    const MODULES = ['inicio', 'directorio', 'solicitudes', 'conexiones', 'perfil'];
    const SELECTOR_MODULE = {
        '#inicio-identity': 'inicio',
        '#inicio-actividad-cinta': 'inicio',
        '.inicio-quick-grid': 'inicio',
        '#inicio-tasks': 'inicio',
        '#inicio-solicitudes-semanales-wrap': 'inicio',
        '.metricas-block': 'inicio',
        '#metrica-card-score': 'inicio',
        '#inicio-score-pill': 'inicio',
        '#module-inicio': 'inicio',
        '.directorio-panel': 'directorio',
        '#directorio-panel': 'directorio',
        '#directorio-search': 'directorio',
        '#module-directorio': 'directorio',
        '#solicitudes-entrantes-wrap': 'solicitudes',
        '#solicitudes-encargos-wrap': 'solicitudes',
        '#solicitudes-semanales-wrap': 'solicitudes',
        '#solicitudes-propias-wrap': 'solicitudes',
        '#solicitudes-historial-wrap': 'solicitudes',
        '#encargos-activos-list': 'solicitudes',
        '#solicitudes-list': 'solicitudes',
        '#solicitudes-propias-list': 'solicitudes',
        '#solicitudes-historial-list': 'solicitudes',
        '.solicitudes-zone': 'solicitudes',
        '#module-solicitudes': 'solicitudes',
        '.crear-solicitud-zone': 'conexiones',
        '#module-conexiones': 'conexiones',
        '.perfil-block': 'perfil',
        '.perfil-header': 'perfil',
        '#perfil-avatar': 'perfil',
        '#perfil-nombre': 'perfil',
        '#detail-descripcion-wrap': 'perfil',
        '#perfil-status': 'perfil',
        '#perfil-seguridad-wrap': 'perfil',
        '#perfil-mis-datos-wrap': 'perfil',
        '#catalogo-servicios-wrap': 'perfil',
        '#btn-invitar-aliado': 'perfil',
        '#module-perfil': 'perfil',
        '#btn-invitar-nav': null,
        '#btn-invitar-global': null,
        '#btn-invitar-inicio': null,
        '#ruana-help-fab': null,
        '#btn-replay-onboarding': null,
        '.aliado-shell-nav': null,
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

    function refreshSolicitudesPanel() {
        const panel = global.__ruanaPanel;
        if (!panel) return;
        if (typeof panel.refreshAfterAction === 'function') {
            panel.refreshAfterAction(['solicitudes', 'contactos']);
            return;
        }
        if (typeof panel.renderSolicitudes === 'function') {
            panel.renderSolicitudes();
        }
        const semMod = global.RuanaAliadoModules && global.RuanaAliadoModules.solicitudesSemanales;
        if (semMod && typeof semMod.renderSeccion === 'function') {
            semMod.renderSeccion(panel);
        }
        const contactosMod = global.RuanaAliadoModules && global.RuanaAliadoModules.contactos;
        if (contactosMod && typeof contactosMod.renderEncargosActivos === 'function') {
            contactosMod.renderEncargosActivos(panel);
        }
    }

    function showModule(name, options) {
        const opts = options || {};
        const previous = current;
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
        if (target === 'solicitudes' && previous !== 'solicitudes') {
            refreshSolicitudesPanel();
        }
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

    function syncInicioGrupo() {
        const src = document.getElementById('grupo-nombre');
        const dst = document.getElementById('inicio-grupo');
        if (!dst) return;
        const nombre = (src && src.textContent ? src.textContent : '').trim();
        if (nombre && nombre !== '---') {
            dst.textContent = 'Grupo: ' + nombre;
            dst.hidden = false;
        } else {
            dst.textContent = '';
            dst.hidden = true;
        }
    }

    function syncInicioIdentity() {
        copyText('perfil-nombre', 'inicio-nombre');
        copyText('perfil-marca', 'inicio-marca');
        copyText('metric-score', 'inicio-score');
        syncInicioGrupo();

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

    function countEncargosRequierenRespuesta() {
        const list = document.getElementById('encargos-activos-list');
        if (!list) return 0;
        return list.querySelectorAll('[data-requiere-respuesta="1"]').length;
    }

    function abrirNegociacionDesdeShell(contactoId) {
        if (!contactoId) return;
        showModule('solicitudes', { skipScroll: false });
        document.dispatchEvent(new CustomEvent('ruana:abrir-negociacion', {
            detail: { contactoId: String(contactoId) },
        }));
    }

    function refreshInicioTasks() {
        const list = document.getElementById('inicio-tasks-list');
        const empty = document.getElementById('inicio-tasks-empty');
        if (!list || !empty) return;

        const tasks = [];

        const panel = global.PrivatePanel;
        const hayAlertasHub = global.RuanaPulse && typeof global.RuanaPulse.hasPendingActivity === 'function'
            ? global.RuanaPulse.hasPendingActivity(panel)
            : (function () {
                const pagosHub = document.getElementById('ruana-alert-hub');
                return pagosHub && !pagosHub.hidden;
            }());
        const hubSummaries = (hayAlertasHub && global.RuanaPulse && typeof global.RuanaPulse.getSummaries === 'function')
            ? global.RuanaPulse.getSummaries(panel)
            : (function () {
                const pagosHub = document.getElementById('ruana-alert-hub');
                if (!pagosHub || pagosHub.hidden || !global.RuanaAlertHub) return [];
                return typeof global.RuanaAlertHub.getVisibleAlertSummaries === 'function'
                    ? global.RuanaAlertHub.getVisibleAlertSummaries(pagosHub)
                    : [];
            }());

        const contacto = document.getElementById('contacto-aviso-persistente');
        if (contacto && isVisible(contacto)) {
            const requiere = contacto.dataset.requiereRespuesta === '1';
            const contactoId = contacto.dataset.contactoId;
            if (requiere && contactoId) {
                tasks.push({
                    text: 'Negociación pendiente de tu respuesta',
                    action: 'solicitudes',
                    label: 'Responder ahora',
                    openNegociacion: contactoId,
                });
            } else {
                tasks.push({
                    text: 'Tienes un contacto activo pendiente de cierre',
                    action: 'solicitudes',
                    label: contactoId ? 'Ver encargo' : 'Revisar',
                    openNegociacion: contactoId || null,
                });
            }
        }

        if (hayAlertasHub) {
            const taskById = {
                'score-bajo': { label: 'Ver score', action: 'inicio', scrollAlerts: true },
                'apoyo-pago': { label: 'Gestionar pago', action: 'inicio', scrollAlerts: true },
                'mensajes-ruana': { label: 'Leer mensajes', action: 'inicio', scrollAlerts: true },
                'stripe-pendiente': { label: 'Conectar pago', action: 'perfil', scrollAlerts: true },
                'competencia': { label: 'Ver competencia', action: 'perfil', scrollAlerts: true },
            };
            const seen = new Set();
            hubSummaries.forEach(function (entry) {
                if (!entry || !entry.id || seen.has(entry.id)) return;
                seen.add(entry.id);
                const meta = taskById[entry.id];
                tasks.push({
                    text: entry.title || 'Aviso RUANA pendiente',
                    action: meta ? meta.action : 'inicio',
                    label: meta ? meta.label : 'Ver avisos',
                    scrollAlerts: true
                });
            });
            if (!hubSummaries.length) {
                tasks.push({
                    text: 'Pagos o avisos RUANA pendientes',
                    action: 'inicio',
                    label: 'Ver avisos',
                    scrollAlerts: true
                });
            }
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

        if (panel && panel.solicitudesSemanales && Array.isArray(panel.solicitudesSemanales.activas_grupo)) {
            const pendientesSem = panel.solicitudesSemanales.activas_grupo.filter(function (s) {
                return !s.mi_respuesta;
            });
            if (pendientesSem.length > 0) {
                tasks.push({
                    text: pendientesSem.length === 1
                        ? '1 solicitud de esta semana sin responder'
                        : pendientesSem.length + ' solicitudes de esta semana sin responder',
                    action: 'inicio',
                    label: 'Ver ahora',
                    scrollSolSem: true,
                });
            }
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
                if (task.openNegociacion) {
                    abrirNegociacionDesdeShell(task.openNegociacion);
                    return;
                }
                showModule(task.action);
                if (task.scrollSolSem) {
                    const block = qs('#inicio-solicitudes-semanales-wrap');
                    if (block) block.scrollIntoView({ behavior: 'smooth', block: 'start' });
                    return;
                }
                if (task.scrollAlerts) {
                    if (global.RuanaPulse && typeof global.RuanaPulse.open === 'function') {
                        global.RuanaPulse.open(panel);
                    } else {
                        const alerts = qs('.aliado-shell-alerts');
                        if (alerts) alerts.scrollIntoView({ behavior: 'smooth', block: 'start' });
                    }
                }
            });
            li.appendChild(span);
            li.appendChild(btn);
            list.appendChild(li);
        });
    }

    function countMensajesPendientes() {
        const panel = global.PrivatePanel;
        if (panel && Array.isArray(panel.contactosAbiertos)) {
            const ui = global.RuanaConversacionUI;
            if (ui && typeof ui.countMensajesPendientes === 'function') {
                return ui.countMensajesPendientes(panel.contactosAbiertos);
            }
            return panel.contactosAbiertos.filter(function (c) {
                return c && c.negociacion_requiere_mi_respuesta;
            }).length;
        }
        const list = document.getElementById('perfil-mensajes-lista');
        if (list) {
            return list.querySelectorAll('.perfil-mensaje-card.is-pendiente').length;
        }
        return countEncargosRequierenRespuesta();
    }

    function updateNavBadges() {
        const entrantes = countListItems('solicitudes-list');
        const encargosTurno = countEncargosRequierenRespuesta();
        const totalSolicitudes = entrantes + encargosTurno;
        qsa('[data-aliado-badge="solicitudes"]').forEach((badge) => {
            if (totalSolicitudes > 0) {
                badge.textContent = String(totalSolicitudes > 99 ? '99+' : totalSolicitudes);
                badge.classList.add('is-visible');
            } else {
                badge.classList.remove('is-visible');
                badge.textContent = '';
            }
        });
        const mensajesPendientes = countMensajesPendientes();
        qsa('[data-aliado-badge="mensajes"]').forEach((badge) => {
            if (mensajesPendientes > 0) {
                badge.textContent = String(mensajesPendientes > 99 ? '99+' : mensajesPendientes);
                badge.classList.add('is-visible');
                badge.setAttribute('aria-label', mensajesPendientes + ' mensajes pendientes');
            } else {
                badge.classList.remove('is-visible');
                badge.textContent = '';
                badge.setAttribute('aria-label', 'Sin mensajes pendientes');
            }
        });
    }

    function refreshInicioSurface() {
        syncInicioIdentity();
        refreshInicioTasks();
        updateNavBadges();
    }

    function bindScorePill() {
        const pill = document.getElementById('inicio-score-pill');
        const metricCard = document.getElementById('metrica-card-score');
        if (!pill || !metricCard) return;
        pill.addEventListener('click', () => {
            showModule('inicio');
            metricCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
            metricCard.classList.add('is-highlighted');
            setTimeout(() => metricCard.classList.remove('is-highlighted'), 1200);
        });
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
            document.getElementById('encargos-activos-list'),
            document.getElementById('ruana-alert-hub'),
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
        bindScorePill();
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
        refresh: refreshInicioSurface,
        updateNavBadges: updateNavBadges,
        refreshSolicitudes: refreshSolicitudesPanel,
    };

    global.AliadoShell = api;

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})(window);
