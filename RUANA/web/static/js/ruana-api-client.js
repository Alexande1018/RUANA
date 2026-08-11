/**
 * RUANA API client — helpers mínimos compartibles (aliado/admin).
 * No sustituye aún las copias inline en aliado.html / admin.html.
 */
(function (global) {
    'use strict';

    function getApiBase() {
        if (typeof global.getApiBase === 'function') {
            try {
                return String(global.getApiBase() || '').replace(/\/$/, '');
            } catch (e) { /* ignore */ }
        }
        const base = global.RUANA_API_BASE
            || (typeof global.location !== 'undefined' ? global.location.origin : '');
        return String(base || '').replace(/\/$/, '');
    }

    function apiUrl(path) {
        const raw = path == null ? '' : String(path);
        const normalized = raw.startsWith('/') ? raw : `/${raw}`;
        return `${getApiBase()}${normalized}`;
    }

    /**
     * Cabeceras de sesión por pestaña (sessionStorage).
     * Compatible con aliado (`ruana_session_id`) y admin (`admin_session_id`).
     */
    function getRuanaAuthHeaders(extra) {
        const h = Object.assign({}, extra || {});
        let sid = null;
        try {
            if (typeof sessionStorage !== 'undefined') {
                sid = sessionStorage.getItem('ruana_session_id')
                    || sessionStorage.getItem('admin_session_id');
            }
        } catch (e) { /* ignore */ }
        if (sid) h['X-Ruana-Session-Id'] = sid;
        return h;
    }

    function escapeHtml(str) {
        return String(str == null ? '' : str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    global.apiUrl = global.apiUrl || apiUrl;
    global.getRuanaAuthHeaders = global.getRuanaAuthHeaders || getRuanaAuthHeaders;
    global.escapeHtml = global.escapeHtml || escapeHtml;

    global.RuanaApiClient = {
        apiUrl: apiUrl,
        getRuanaAuthHeaders: getRuanaAuthHeaders,
        escapeHtml: escapeHtml,
        getApiBase: getApiBase
    };
})(typeof window !== 'undefined' ? window : this);
