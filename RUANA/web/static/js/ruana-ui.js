/**
 * RUANA UI — Sistema unificado de comunicación visual
 * Toasts, confirmaciones, banners, errores, éxito y estados de carga.
 */
(function (global) {
    'use strict';

    const ANIM_MS = 240;

    const ICONS = {
        success: '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
        error: '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>',
        warning: '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
        info: '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>',
        loading: '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>',
        close: '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>',
        confirm: '<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
        danger: '<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>'
    };

    function escapeHtml(str) {
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function inferToastType(message) {
        const msg = String(message || '').toLowerCase();
        if (/error|no se pudo|no hemos podido|fallo|inválid|incorrecto|conexión|inténtalo/.test(msg)) return 'error';
        if (/obligatorio|debe|introduce|revisa|pendiente|atención|completa/.test(msg)) return 'warning';
        if (/éxito|listo|copiado|enviad|guardad|correctamente|actualizad/.test(msg)) return 'success';
        return 'info';
    }

    function normalizeToastInput(messageOrOpts, type, duration) {
        if (messageOrOpts && typeof messageOrOpts === 'object') {
            const o = messageOrOpts;
            return {
                title: o.title || '',
                message: o.message || o.body || '',
                type: o.type || inferToastType(o.message || o.title),
                duration: typeof o.duration === 'number' ? o.duration : 4500,
                actions: o.actions || null
            };
        }
        return {
            title: '',
            message: String(messageOrOpts || ''),
            type: type || inferToastType(messageOrOpts),
            duration: typeof duration === 'number' ? duration : 4500,
            actions: null
        };
    }

    function ensureContainer() {
        let container = document.getElementById('ruana-toast-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'ruana-toast-container';
            container.className = 'ruana-toast-container';
            container.setAttribute('aria-live', 'polite');
            document.body.appendChild(container);
        }
        return container;
    }

    function buildActionsHtml(actions, onAction) {
        if (!actions || !actions.length) return '';
        let html = '<div class="ruana-feedback__actions">';
        actions.forEach(function (action, idx) {
            const primary = action.primary ? ' ruana-feedback__action--primary' : '';
            html += '<button type="button" class="ruana-feedback__action' + primary + '" data-action-idx="' + idx + '">' +
                escapeHtml(action.label || 'Acción') + '</button>';
        });
        html += '</div>';
        return html;
    }

    function toast(messageOrOpts, type, duration) {
        const opts = normalizeToastInput(messageOrOpts, type, duration);
        const container = ensureContainer();
        const resolvedType = opts.type || 'info';
        const icon = ICONS[resolvedType] || ICONS.info;

        const el = document.createElement('div');
        el.className = 'ruana-feedback ruana-toast ' + resolvedType;
        el.setAttribute('role', 'alert');

        let bodyHtml = '<div class="ruana-toast-body">';
        if (opts.title) {
            bodyHtml += '<div class="ruana-toast-title">' + escapeHtml(opts.title) + '</div>';
        }
        if (opts.message) {
            bodyHtml += '<div class="ruana-toast-message">' + escapeHtml(opts.message) + '</div>';
        }
        bodyHtml += buildActionsHtml(opts.actions);
        bodyHtml += '</div>';

        el.innerHTML =
            '<span class="ruana-toast-icon" aria-hidden="true">' + icon + '</span>' +
            bodyHtml +
            '<button type="button" class="ruana-toast-close" aria-label="Cerrar">' + ICONS.close + '</button>';

        const closeBtn = el.querySelector('.ruana-toast-close');
        let timer = null;

        function removeToast() {
            if (timer) clearTimeout(timer);
            el.classList.add('is-leaving');
            setTimeout(function () { el.remove(); }, ANIM_MS);
        }

        closeBtn.addEventListener('click', removeToast);

        if (opts.actions) {
            el.querySelectorAll('[data-action-idx]').forEach(function (btn) {
                btn.addEventListener('click', function () {
                    const idx = parseInt(btn.getAttribute('data-action-idx'), 10);
                    const action = opts.actions[idx];
                    if (action && typeof action.onClick === 'function') {
                        action.onClick();
                    }
                    removeToast();
                });
            });
        }

        container.appendChild(el);

        const resolvedDuration = opts.actions && opts.actions.length ? 0 : opts.duration;
        if (resolvedDuration > 0) {
            timer = setTimeout(removeToast, resolvedDuration);
        }

        return el;
    }

    function success(title, message, duration) {
        if (!message && title && title.length < 80) {
            return toast({ title: title, type: 'success', duration: duration || 4500 });
        }
        return toast({
            title: title || 'Listo',
            message: message || '',
            type: 'success',
            duration: duration || 4500
        });
    }

    function showError(title, message, options) {
        options = options || {};
        const actions = options.actions || null;
        const defaultTitle = title && !message ? '' : (title || 'Algo no ha salido como esperábamos');
        const defaultMessage = message || (title && !message ? title : 'Inténtalo de nuevo en unos momentos.');

        return toast({
            title: defaultTitle,
            message: defaultMessage,
            type: 'error',
            duration: actions ? 0 : (options.duration || 6000),
            actions: actions
        });
    }

    function warning(title, message, duration) {
        return toast({
            title: title || 'Atención',
            message: message || '',
            type: 'warning',
            duration: duration || 5000
        });
    }

    function info(title, message, duration) {
        return toast({
            title: title || '',
            message: message || title || '',
            type: 'info',
            duration: duration || 4500
        });
    }

    function confirm(message, options) {
        options = options || {};
        return new Promise(function (resolve) {
            const variant = options.variant || options.type || 'default';
            const overlay = document.createElement('div');
            overlay.className = 'ruana-dialog-overlay';
            if (variant === 'danger' || variant === 'warning') {
                overlay.classList.add('ruana-dialog-overlay--' + variant);
            }

            overlay.setAttribute('role', 'dialog');
            overlay.setAttribute('aria-modal', 'true');

            const title = options.title || 'Confirmar';
            const confirmLabel = options.confirmLabel || options.confirmText || 'Confirmar';
            const cancelLabel = options.cancelLabel || options.cancelText || 'Cancelar';
            const iconKey = variant === 'danger' ? 'danger' : (variant === 'warning' ? 'warning' : 'confirm');
            const icon = ICONS[iconKey] || ICONS.confirm;

            overlay.innerHTML =
                '<div class="ruana-feedback ruana-dialog">' +
                    '<div class="ruana-dialog-icon" aria-hidden="true">' + icon + '</div>' +
                    '<div class="ruana-dialog-title">' + escapeHtml(title) + '</div>' +
                    '<div class="ruana-dialog-message">' + escapeHtml(String(message || '')) + '</div>' +
                    '<div class="ruana-dialog-actions">' +
                        '<button type="button" class="ruana-button secondary ruana-dialog-cancel">' + escapeHtml(cancelLabel) + '</button>' +
                        '<button type="button" class="ruana-button ruana-dialog-confirm">' + escapeHtml(confirmLabel) + '</button>' +
                    '</div>' +
                '</div>';

            function close(result) {
                overlay.classList.add('is-leaving');
                setTimeout(function () {
                    overlay.remove();
                    resolve(result);
                }, ANIM_MS);
            }

            overlay.querySelector('.ruana-dialog-cancel').addEventListener('click', function () { close(false); });
            overlay.querySelector('.ruana-dialog-confirm').addEventListener('click', function () { close(true); });
            overlay.addEventListener('click', function (e) {
                if (e.target === overlay) close(false);
            });

            document.body.appendChild(overlay);
            overlay.querySelector('.ruana-dialog-confirm').focus();
        });
    }

    function applyBannerClasses(el, type) {
        if (!el) return;
        el.classList.add('ruana-feedback', 'ruana-feedback--banner', 'ruana-feedback--' + (type || 'info'));
    }

    function renderBannerContent(el, opts) {
        opts = opts || {};
        const type = opts.type || 'info';
        const icon = ICONS[type] || ICONS.info;
        const title = opts.title || '';
        const message = opts.message || opts.text || '';

        el.innerHTML =
            '<span class="ruana-feedback__icon" aria-hidden="true">' + icon + '</span>' +
            '<div class="ruana-feedback__content">' +
                (title ? '<div class="ruana-feedback__title">' + escapeHtml(title) + '</div>' : '') +
                (message ? '<div class="ruana-feedback__message">' + escapeHtml(message) + '</div>' : '') +
            '</div>';

        applyBannerClasses(el, type);
    }

    const loadingState = {
        _el: null,

        show(message, subtext) {
            this.hide();
            const overlay = document.createElement('div');
            overlay.className = 'ruana-loading-overlay';
            overlay.setAttribute('role', 'status');
            overlay.setAttribute('aria-live', 'polite');

            overlay.innerHTML =
                '<div class="ruana-feedback ruana-loading-card">' +
                    '<div class="ruana-loading-spinner" aria-hidden="true"></div>' +
                    '<div class="ruana-loading-message">' + escapeHtml(message || 'Cargando...') + '</div>' +
                    (subtext ? '<p class="ruana-loading-subtext">' + escapeHtml(subtext) + '</p>' : '') +
                '</div>';

            document.body.appendChild(overlay);
            this._el = overlay;
            return overlay;
        },

        setMessage(message, subtext) {
            if (!this._el) return;
            const msgEl = this._el.querySelector('.ruana-loading-message');
            const subEl = this._el.querySelector('.ruana-loading-subtext');
            if (msgEl) msgEl.textContent = message || '';
            if (subtext) {
                if (subEl) subEl.textContent = subtext;
                else if (message) {
                    const p = document.createElement('p');
                    p.className = 'ruana-loading-subtext';
                    p.textContent = subtext;
                    this._el.querySelector('.ruana-loading-card').appendChild(p);
                }
            }
        },

        hide() {
            if (!this._el) return;
            const el = this._el;
            this._el = null;
            el.classList.add('is-leaving');
            setTimeout(function () { el.remove(); }, ANIM_MS);
        }
    };

    function initLucideIcons(root) {
        if (typeof global.lucide === 'undefined' || !global.lucide.createIcons) return;
        try {
            global.lucide.createIcons({ attrs: { 'stroke-width': 1.75 }, nameAttr: 'data-lucide' }, root || document);
        } catch (_) {}
    }

    function patchNativeDialogs() {
        if (global.__ruanaUiPatched) return;
        global.__ruanaUiPatched = true;

        global.alert = function (message) {
            const msg = String(message || '');
            const type = inferToastType(msg);
            if (type === 'error') {
                showError('', msg);
            } else if (type === 'success') {
                success(msg);
            } else if (type === 'warning') {
                warning('', msg);
            } else {
                toast(msg, type);
            }
        };
    }

    const RuanaUI = {
        toast: toast,
        success: success,
        error: showError,
        warning: warning,
        info: info,
        confirm: confirm,
        banner: {
            apply: applyBannerClasses,
            render: renderBannerContent
        },
        loading: loadingState,
        initIcons: initLucideIcons,
        patchNativeDialogs: patchNativeDialogs,
        inferToastType: inferToastType,
        escapeHtml: escapeHtml
    };

    global.RuanaUI = RuanaUI;

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () {
            patchNativeDialogs();
            initLucideIcons();
        });
    } else {
        patchNativeDialogs();
        initLucideIcons();
    }
})(typeof window !== 'undefined' ? window : globalThis);
