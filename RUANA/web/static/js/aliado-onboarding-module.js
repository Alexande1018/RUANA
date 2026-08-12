/**
 * RUANA — Tour de onboarding del panel aliado (Campamento Base).
 * Extraído de aliado-panel-host.js; el host solo instancia RuanaOnboardingTour.
 */
(function (global) {
  'use strict';

class RuanaOnboardingTour {
    constructor(panel) {
        this.panel = panel;
        // Clave estable (sin versionar): el autoarranque no debe reaparecer al cambiar el tour.
        this.seenKeyBase = 'ruana_onboarding_seen';
        this.pendingKeyBase = 'ruana_pending_onboarding';
        this.legacyCompletedBases = [
            'ruana_onboarding_completed_v4',
            'ruana_onboarding_completed_v3'
        ];
        this.stepIndex = 0;
        this.steps = [];
        this.activeTarget = null;
        this.cloud = null;
        this.arrow = null;
        this.renderToken = 0;
        this.stepListener = null;
        this.boundEsc = (event) => {
            if (event.key === 'Escape') this.finish(false);
        };
        this.boundClickAdvance = (event) => {
            if (!this.cloud) return;
            if (event.target && event.target.closest && event.target.closest('.ruana-tour-cloud-close')) return;
            if (event && typeof event.preventDefault === 'function') event.preventDefault();
            if (event && typeof event.stopPropagation === 'function') event.stopPropagation();
            if (event && typeof event.stopImmediatePropagation === 'function') event.stopImmediatePropagation();
            this.next();
        };
    }

    getAliadoCodigo() {
        const codigo = (
            (this.panel && (this.panel.codigoAliado || (this.panel.aliado && this.panel.aliado.codigo))) ||
            sessionStorage.getItem('ruana_codigo_aliado') ||
            ''
        ).toString().trim();
        return codigo || '';
    }

    getSeenKey(codigo) {
        const code = codigo || this.getAliadoCodigo();
        return code ? `${this.seenKeyBase}_${code}` : null;
    }

    getPendingKey(codigo) {
        const code = codigo || this.getAliadoCodigo();
        return code ? `${this.pendingKeyBase}_${code}` : null;
    }

    /** Compat: claves antiguas por versión del tour. */
    hasLegacyCompleted(codigo) {
        const code = codigo || this.getAliadoCodigo();
        if (!code) return false;
        try {
            for (let i = 0; i < this.legacyCompletedBases.length; i += 1) {
                if (localStorage.getItem(`${this.legacyCompletedBases[i]}_${code}`) === 'true') {
                    return true;
                }
            }
            if (localStorage.getItem('ruana_onboarding_completed_v2') === 'true') return true;
        } catch (_) {}
        return false;
    }

    hasSeen() {
        const codigo = this.getAliadoCodigo();
        if (!codigo) return true;
        try {
            const seenKey = this.getSeenKey(codigo);
            if (seenKey && localStorage.getItem(seenKey) === 'true') return true;
            if (this.hasLegacyCompleted(codigo)) {
                this.markSeen();
                return true;
            }
        } catch (_) {
            return true;
        }
        return false;
    }

    isElementUsable(el) {
        if (!el) return false;
        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden') return false;
        return true;
    }

    pickNavStep() {
        const bottom = document.getElementById('aliado-shell-bottom');
        if (this.isElementUsable(bottom)) {
            return {
                selector: '#aliado-shell-bottom',
                module: null,
                title: 'Menú de la app',
                copy: '<strong>Empieza por este menú.</strong><br><br>Inicio · Directorio · Solicitudes · Conexiones · Perfil. Cada botón abre su propio espacio de trabajo.',
                placement: 'top',
                anchor: 'center',
                skipScroll: true
            };
        }
        const side = document.querySelector('.aliado-shell-nav');
        if (this.isElementUsable(side)) {
            return {
                selector: '.aliado-shell-nav',
                module: null,
                title: 'Menú de la app',
                copy: '<strong>Empieza por este menú.</strong><br><br>Está a la izquierda: Inicio, Directorio, Solicitudes, Conexiones y Perfil. Úsalo para moverte por toda la app.',
                placement: 'right',
                anchor: 'start',
                skipScroll: true
            };
        }
        return null;
    }

    buildSteps() {
        const navStep = this.pickNavStep();
        const candidates = [
            navStep,
            {
                selector: '#inicio-identity',
                module: 'inicio',
                title: 'Tu centro operativo',
                copy: '<strong>Bienvenido a tu panel RUANA.</strong><br><br>Aquí ves quién eres, tu estado y tu Score. Desde Inicio controlas el resto de la app.',
                placement: 'bottom'
            },
            {
                selector: '.inicio-quick-grid',
                module: 'inicio',
                title: 'Atajos a cada módulo',
                copy: 'Un toque te lleva a Directorio, Solicitudes, Conexiones o Perfil. Es la forma más rápida de moverte.',
                placement: 'bottom'
            },
            {
                selector: '#inicio-tasks',
                module: 'inicio',
                title: 'Qué hacer hoy',
                copy: 'RUANA te deja pendientes claros: contactos, avisos, score o solicitudes por atender.',
                placement: 'top'
            },
            {
                selector: '.metricas-block',
                module: 'inicio',
                title: 'Tu radar de actividad',
                copy: 'Solicitudes, red de aliados y Score: el pulso de tu trabajo en el grupo.',
                placement: 'top'
            },
            {
                selector: '#metrica-card-score',
                module: 'inicio',
                title: 'Score de confianza',
                copy: 'Sube con perfil completo, respuestas rápidas y buenos cierres. Es tu credencial ante la red.',
                placement: 'left'
            },
            {
                selector: '.directorio-panel',
                module: 'directorio',
                title: 'Directorio del grupo',
                copy: 'Busca por nombre, oficio o zona. Con <strong>Contactar</strong> abres un chat privado con el aliado para conversar y gestionar la contratación.',
                placement: 'bottom'
            },
            {
                selector: '#solicitudes-entrantes-wrap',
                module: 'solicitudes',
                title: 'Bandeja de solicitudes',
                copy: 'Aquí llegan las peticiones del grupo. Responde, recomienda o negocia sin salir del panel.',
                placement: 'bottom'
            },
            {
                selector: '.crear-solicitud-zone',
                module: 'conexiones',
                title: 'Nueva conexión',
                copy: 'Describe el oficio y lo que necesitas. Tu solicitud llega a todos los aliados del grupo.',
                placement: 'top'
            },
            {
                selector: '.perfil-header',
                module: 'perfil',
                title: 'Tu perfil público',
                copy: 'Foto, datos, estado y descripción: lo que ven cuando alguien te encuentra en la red.',
                placement: 'bottom',
                scrollBlock: 'start'
            },
            {
                selector: '#detail-descripcion-wrap',
                module: 'perfil',
                title: 'Tu propuesta en claro',
                copy: 'Edita la descripción para explicar qué haces y en qué destacas. Cuanto más clara, más contactos útiles.',
                placement: 'bottom'
            },
            {
                selector: '#catalogo-servicios-wrap',
                module: 'perfil',
                title: 'Tu catálogo de servicios',
                copy: 'Añade servicios al catálogo en tarjetas. Al guardar se cierra y muestra un resumen; pulsa Editar para modificarlo. Así mantienes el perfil ordenado y profesional.',
                placement: 'top'
            },
            {
                selector: '#btn-invitar-nav, #btn-invitar-global, #btn-invitar-aliado',
                module: null,
                title: 'Invita nuevos aliados',
                copy: 'Genera un código en cualquier momento desde este acceso prioritario y fortalece tu grupo.',
                placement: 'top'
            },
            {
                selector: '#ruana-help-fab',
                module: null,
                title: 'Habla con el equipo RUANA',
                copy: 'Abre soporte desde este botón flotante: consultas, incidencias e ideas, sin salir del panel.',
                placement: 'left'
            },
            {
                selector: '#btn-replay-onboarding',
                module: null,
                title: 'Tour cuando lo necesites',
                copy: 'Puedes repetir esta guía cuando quieras con el botón ✨. Listo para trabajar.',
                placement: 'left',
                final: true
            }
        ].filter(Boolean);

        return candidates.filter((step) => {
            try {
                const el = document.querySelector(step.selector);
                return !!el;
            } catch (_) {
                return false;
            }
        });
    }

    shouldAutoStart() {
        try {
            const codigo = this.getAliadoCodigo();
            // Sin código de aliado no autoarrancamos (evita claves anon y repeticiones).
            if (!codigo) return false;
            if (this.hasSeen()) return false;
            const pendingKey = this.getPendingKey(codigo);
            return !!(pendingKey && localStorage.getItem(pendingKey) === '1');
        } catch (_) {
            return false;
        }
    }

    markSeen() {
        try {
            const codigo = this.getAliadoCodigo();
            if (!codigo) return;
            const seenKey = this.getSeenKey(codigo);
            const pendingKey = this.getPendingKey(codigo);
            if (seenKey) localStorage.setItem(seenKey, 'true');
            if (pendingKey) localStorage.removeItem(pendingKey);
            // Limpia claves legacy para no reactivar el autoarranque.
            this.legacyCompletedBases.forEach((base) => {
                try { localStorage.removeItem(`${base}_${codigo}`); } catch (_) {}
            });
        } catch (_) {}
    }

    start(force = false) {
        if (!force && !this.shouldAutoStart()) return;
        if (this.cloud) return;
        this.steps = this.buildSteps();
        if (!this.steps.length) return;
        // Autoarranque solo una vez: se marca al abrirse, aunque el usuario lo cierre a mitad.
        // El replay manual (force) también marca visto para no dejar pendiente activo.
        this.markSeen();
        document.body.classList.add('ruana-tour-active');
        this.stepIndex = 0;
        this.createLayer();
        document.addEventListener('keydown', this.boundEsc);
        document.addEventListener('click', this.boundClickAdvance, true);
        this.renderStep();
    }

    createLayer() {
        this.cloud = document.createElement('div');
        this.cloud.className = 'ruana-tour-cloud';
        this.cloud.innerHTML = '<button type="button" class="ruana-tour-cloud-close" aria-label="Cerrar tour">✕</button><h3 class="ruana-tour-cloud-title"></h3><p class="ruana-tour-cloud-copy"></p><span class="ruana-tour-hint">Da clic para avanzar</span>';
        document.body.appendChild(this.cloud);

        this.arrow = document.createElement('div');
        this.arrow.className = 'ruana-tour-arrow';
        this.arrow.innerHTML = '<div class="ruana-tour-arrow-line"></div><span class="ruana-tour-arrow-dot"></span>';
        document.body.appendChild(this.arrow);

        this.cloud.querySelector('.ruana-tour-cloud-close').addEventListener('click', (event) => { event.stopPropagation(); this.finish(false); });
        requestAnimationFrame(() => this.cloud.classList.add('is-visible'));
    }

    prepareModule(step) {
        if (!step) return;
        if (step.module && window.AliadoShell && typeof window.AliadoShell.show === 'function') {
            window.AliadoShell.show(step.module, { skipScroll: true, instant: true });
            return;
        }
        if (window.AliadoShell && typeof window.AliadoShell.ensureModuleForSelector === 'function') {
            window.AliadoShell.ensureModuleForSelector(step.selector);
        }
    }

    renderStep() {
        if (!this.cloud) return;
        const step = this.steps[this.stepIndex];
        if (!step) return;
        const token = ++this.renderToken;

        this.prepareModule(step);

        const apply = () => {
            if (!this.cloud || this.renderToken !== token) return;

            const target = document.querySelector(step.selector);

            if (this.activeTarget) this.activeTarget.classList.remove('ruana-tour-target');
            this.activeTarget = target;
            if (target) {
                target.classList.add('ruana-tour-target');
                if (!step.skipScroll) {
                    target.scrollIntoView({
                        behavior: 'smooth',
                        block: step.scrollBlock || 'center',
                        inline: 'nearest'
                    });
                }
            }

            this.cloud.querySelector('.ruana-tour-cloud-title').textContent = step.title;
            this.cloud.querySelector('.ruana-tour-cloud-copy').innerHTML = step.copy || '';
            this.cloud.classList.remove('is-step-entering');
            void this.cloud.offsetWidth;
            this.cloud.classList.add('is-step-entering');

            const paint = () => {
                if (!this.cloud || this.renderToken !== token) return;
                this.positionCloud(target, step.placement || 'bottom', step.anchor || 'center');
                this.positionArrow(target, step.anchor || 'center');
            };
            requestAnimationFrame(() => setTimeout(paint, target ? 120 : 0));
        };

        // Esperar a que el módulo activo pinte layout/animación antes de medir.
        requestAnimationFrame(() => setTimeout(apply, step.module ? 300 : 40));
    }

    positionCloud(target, placement, anchor) {
        if (!this.cloud) return;
        const margin = 14;
        const viewportPadding = 10;
        const vw = window.innerWidth;
        const vh = window.innerHeight;
        const align = anchor || 'center';
        const r = target ? target.getBoundingClientRect() : { top: vh * 0.4, left: vw * 0.5, width: 0, height: 0, right: vw * 0.5, bottom: vh * 0.5 };
        const c = this.cloud.getBoundingClientRect();

        const sideTop = () => {
            if (align === 'start') {
                return r.top + Math.min(28, Math.max(8, r.height * 0.06));
            }
            if (align === 'end') {
                return r.bottom - c.height - Math.min(28, Math.max(8, r.height * 0.06));
            }
            return r.top + (r.height / 2) - (c.height / 2);
        };

        const calcPos = (place) => {
            let top = r.bottom + margin;
            let left = r.left + (r.width / 2) - (c.width / 2);
            if (place === 'top') {
                top = r.top - c.height - margin;
            } else if (place === 'left') {
                top = sideTop();
                left = r.left - c.width - margin;
            } else if (place === 'right') {
                top = sideTop();
                left = r.right + margin;
            }
            return { top, left };
        };
        const scorePos = (pos) => {
            const overflowTop = Math.max(0, viewportPadding - pos.top);
            const overflowBottom = Math.max(0, (pos.top + c.height + viewportPadding) - vh);
            const overflowLeft = Math.max(0, viewportPadding - pos.left);
            const overflowRight = Math.max(0, (pos.left + c.width + viewportPadding) - vw);
            return overflowTop + overflowBottom + overflowLeft + overflowRight;
        };

        // Para el menú lateral, priorizar right/left y no “caer” a top/bottom (centra la nube en pantalla).
        const options = (align === 'start' && (placement === 'right' || placement === 'left'))
            ? [placement, placement === 'right' ? 'left' : 'right']
            : [placement, 'bottom', 'top', 'right', 'left']
                .filter((v, idx, arr) => arr.indexOf(v) === idx);
        let bestPlacement = options[0];
        let bestPos = calcPos(bestPlacement);
        let bestScore = scorePos(bestPos);
        options.slice(1).forEach((opt) => {
            const candidate = calcPos(opt);
            const score = scorePos(candidate);
            if (score < bestScore) {
                bestScore = score;
                bestPos = candidate;
                bestPlacement = opt;
            }
        });

        const top = Math.max(viewportPadding, Math.min(bestPos.top, vh - c.height - viewportPadding));
        const left = Math.max(viewportPadding, Math.min(bestPos.left, vw - c.width - viewportPadding));
        this.cloud.style.top = `${Math.round(top)}px`;
        this.cloud.style.left = `${Math.round(left)}px`;
        this.cloud.dataset.placement = bestPlacement;
    }

    positionArrow(target, anchor) {
        if (!this.arrow) return;
        if (!target || window.innerWidth < 721) {
            this.arrow.style.display = 'none';
            return;
        }
        this.arrow.style.display = '';
        const tr = target.getBoundingClientRect();
        const cr = this.cloud.getBoundingClientRect();
        const align = anchor || 'center';
        const x1 = cr.left + cr.width / 2;
        const y1 = cr.top + cr.height / 2;
        const x2 = tr.left + tr.width / 2;
        let y2 = tr.top + tr.height / 2;
        if (align === 'start') {
            y2 = tr.top + Math.min(56, Math.max(24, tr.height * 0.12));
        } else if (align === 'end') {
            y2 = tr.bottom - Math.min(56, Math.max(24, tr.height * 0.12));
        }
        const dx = x2 - x1;
        const dy = y2 - y1;
        const length = Math.max(22, Math.min(Math.hypot(dx, dy) - 18, 220));
        const angle = Math.atan2(dy, dx) * (180 / Math.PI);

        this.arrow.style.left = `${Math.round(x1)}px`;
        this.arrow.style.top = `${Math.round(y1)}px`;
        this.arrow.style.transform = `rotate(${angle}deg)`;
        const line = this.arrow.querySelector('.ruana-tour-arrow-line');
        line.style.width = `${Math.round(length)}px`;
    }

    playFinale() {
        const finale = document.createElement('div');
        finale.className = 'ruana-tour-finale';
        finale.innerHTML = '<div class="ruana-tour-finale-logo" aria-hidden="true">'
            + '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" fill="none">'
            + '<g stroke="#A2FF00" stroke-width="5.5" stroke-linecap="round" stroke-linejoin="round"><path d="M32 24v7.5"/><path d="M32 31.5H18v7.5"/><path d="M32 31.5H46v7.5"/></g>'
            + '<rect x="22" y="8" width="20" height="20" rx="5.5" fill="#A2FF00"/>'
            + '<rect x="8" y="39" width="20" height="20" rx="5.5" fill="#A2FF00"/>'
            + '<rect x="36" y="39" width="20" height="20" rx="5.5" fill="#A2FF00"/>'
            + '</svg></div>';
        document.body.appendChild(finale);
        setTimeout(() => finale.remove(), 980);
    }

    next() {
        if (this.stepIndex >= this.steps.length - 1) {
            this.finish(true);
            return;
        }
        this.stepIndex += 1;
        this.renderStep();
    }

    finish(markComplete) {
        // Cualquier cierre (completar, ✕ o Escape) evita un nuevo autoarranque.
        this.markSeen();
        this.renderToken += 1;
        if (markComplete) {
            this.playFinale();
            if (window.RuanaUI && typeof window.RuanaUI.toast === 'function') {
                window.RuanaUI.toast('Listo, ya conoces lo clave de RUANA. Dale con todo 🙌', 'success', 3200);
            }
        }
        if (this.activeTarget) this.activeTarget.classList.remove('ruana-tour-target');
        this.activeTarget = null;
        document.removeEventListener('keydown', this.boundEsc);
        document.removeEventListener('click', this.boundClickAdvance, true);
        if (this.cloud) {
            const cloud = this.cloud;
            this.cloud = null;
            cloud.remove();
        }
        if (this.arrow) {
            const arrow = this.arrow;
            this.arrow = null;
            arrow.remove();
        }
        document.body.classList.remove('ruana-tour-active');
        if (window.AliadoShell && typeof window.AliadoShell.show === 'function') {
            window.AliadoShell.show('inicio', { skipScroll: true, instant: true });
        }
    }
}


  global.RuanaOnboardingTour = RuanaOnboardingTour;
})(typeof window !== 'undefined' ? window : globalThis);
