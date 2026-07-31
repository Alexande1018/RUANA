/**
 * RUANA UI — Sistema de notificaciones y diálogos premium
 * Solo capa visual; no modifica lógica de negocio.
 */
(function (global) {
    'use strict';

    function icon(name, size) {
        if (global.RuanaIcons && global.RuanaIcons.svg) {
            return global.RuanaIcons.svg(name, size);
        }
        return '';
    }

    const ICONS = {
        success: icon('success', 20),
        error: icon('error', 20),
        warning: icon('warning', 20),
        info: icon('info', 20),
        close: icon('close', 16)
    };

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

    function inferToastType(message) {
        const msg = String(message || '').toLowerCase();
        if (/error|no se pudo|fallo|inválid|incorrecto|conexión/.test(msg)) return 'error';
        if (/obligatorio|debe|introduce|revisa|pendiente/.test(msg)) return 'warning';
        if (/éxito|copiado|enviad|guardad|correctamente/.test(msg)) return 'success';
        return 'info';
    }

    function toast(message, type, duration) {
        const container = ensureContainer();
        const resolvedType = type || inferToastType(message);
        const resolvedDuration = typeof duration === 'number' ? duration : 4500;

        const el = document.createElement('div');
        el.className = 'ruana-toast ' + resolvedType;
        el.setAttribute('role', 'alert');
        el.innerHTML =
            '<span class="ruana-toast-icon" aria-hidden="true">' + (ICONS[resolvedType] || ICONS.info) + '</span>' +
            '<span class="ruana-toast-body">' + escapeHtml(String(message || '')) + '</span>' +
            '<button type="button" class="ruana-toast-close" aria-label="Cerrar">' + ICONS.close + '</button>';

        const closeBtn = el.querySelector('.ruana-toast-close');
        let timer = null;

        function removeToast() {
            if (timer) clearTimeout(timer);
            el.classList.add('is-leaving');
            setTimeout(function () { el.remove(); }, 180);
        }

        closeBtn.addEventListener('click', removeToast);
        container.appendChild(el);
        if (resolvedDuration > 0) {
            timer = setTimeout(removeToast, resolvedDuration);
        }
        return el;
    }

    function confirm(message, options) {
        options = options || {};
        return new Promise(function (resolve) {
            const overlay = document.createElement('div');
            overlay.className = 'ruana-dialog-overlay';
            overlay.setAttribute('role', 'dialog');
            overlay.setAttribute('aria-modal', 'true');

            const title = options.title || 'Confirmar';
            const confirmLabel = options.confirmLabel || 'Confirmar';
            const cancelLabel = options.cancelLabel || 'Cancelar';

            overlay.innerHTML =
                '<div class="ruana-dialog">' +
                    '<div class="ruana-dialog-title">' + escapeHtml(title) + '</div>' +
                    '<div class="ruana-dialog-message">' + escapeHtml(String(message || '')) + '</div>' +
                    '<div class="ruana-dialog-actions">' +
                        '<button type="button" class="ruana-button secondary ruana-dialog-cancel">' + escapeHtml(cancelLabel) + '</button>' +
                        '<button type="button" class="ruana-button ruana-dialog-confirm">' + escapeHtml(confirmLabel) + '</button>' +
                    '</div>' +
                '</div>';

            function close(result) {
                overlay.classList.add('is-leaving');
                overlay.style.opacity = '0';
                setTimeout(function () {
                    overlay.remove();
                    resolve(result);
                }, 180);
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

    function escapeHtml(str) {
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function initLucideIcons(root) {
        if (global.RuanaIcons && global.RuanaIcons.inject) {
            global.RuanaIcons.inject(root || document);
            return;
        }
        if (typeof global.lucide === 'undefined' || !global.lucide.createIcons) return;
        try {
            global.lucide.createIcons({ attrs: { 'stroke-width': 1.75 }, nameAttr: 'data-lucide' }, root || document);
        } catch (_) {}
    }

    function patchNativeDialogs() {
        if (global.__ruanaUiPatched) return;
        global.__ruanaUiPatched = true;

        global.alert = function (message) {
            toast(String(message || ''), inferToastType(message));
        };
    }

    const RuanaUI = {
        toast: toast,
        confirm: confirm,
        initIcons: initLucideIcons,
        patchNativeDialogs: patchNativeDialogs
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
