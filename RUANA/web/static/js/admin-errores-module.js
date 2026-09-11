/**
 * RUANA Admin — visor de errores/warnings (Cloud Logging).
 * Solo lectura. El stack se pide al expandir una fila.
 */
(function (global) {
    'use strict';

    var modules = global.RuanaAdminModules = global.RuanaAdminModules || {};
    var loadedOnce = false;
    var nextPageToken = null;
    var expandedId = null;

    function esc(s) {
        if (global.RuanaUi && global.RuanaUi.escapeHtml) return global.RuanaUi.escapeHtml(s);
        var d = document.createElement('div');
        d.textContent = s == null ? '' : String(s);
        return d.innerHTML;
    }

    function authHeaders(extra) {
        if (global.AdminAuthenticator && global.AdminAuthenticator.getAdminAuthHeaders) {
            return global.AdminAuthenticator.getAdminAuthHeaders(extra);
        }
        if (global.getRuanaAuthHeaders) {
            return global.getRuanaAuthHeaders(extra);
        }
        if (global.RuanaApiClient && global.RuanaApiClient.getRuanaAuthHeaders) {
            return global.RuanaApiClient.getRuanaAuthHeaders(extra);
        }
        return extra || {};
    }

    function statusEl() {
        return document.getElementById('errores-logs-status');
    }

    function setStatus(text, isError) {
        var el = statusEl();
        if (!el) return;
        el.textContent = text || '';
        el.style.color = isError ? '#f87171' : '#999';
    }

    function filtrosActuales() {
        var horas = document.getElementById('filtro-errores-horas');
        var sev = document.getElementById('filtro-errores-severity');
        var ident = document.getElementById('filtro-errores-identificador');
        return {
            horas: horas ? horas.value : '24',
            severity: sev ? sev.value : 'ERROR',
            identificador: ident ? String(ident.value || '').trim() : ''
        };
    }

    function buildUrl(opts) {
        var f = filtrosActuales();
        var q = new URLSearchParams();
        q.set('severity', f.severity || 'ERROR');
        q.set('horas', f.horas || '24');
        q.set('limite', '50');
        if (f.identificador) q.set('identificador', f.identificador);
        if (opts && opts.incluirStack) q.set('incluir_stack', 'true');
        if (opts && opts.pageToken) q.set('page_token', opts.pageToken);
        if (opts && opts.insertId) q.set('insert_id', opts.insertId);
        return '/api/admin/logs/errores?' + q.toString();
    }

    function formatHora(ts) {
        if (!ts) return '—';
        var d = new Date(ts);
        if (Number.isNaN(d.getTime())) return esc(ts);
        return d.toLocaleString('es-ES', { dateStyle: 'short', timeStyle: 'medium' });
    }

    function idsFromExtra(extra) {
        extra = extra || {};
        var parts = [];
        if (extra.aliado_codigo) parts.push('aliado ' + extra.aliado_codigo);
        if (extra.contacto_id != null && extra.contacto_id !== '') parts.push('contacto #' + extra.contacto_id);
        if (extra.admin_codigo) parts.push('admin ' + extra.admin_codigo);
        return parts.length ? parts.join(' · ') : '—';
    }

    function sevClass(sev) {
        var s = String(sev || '').toUpperCase();
        if (s === 'ERROR' || s === 'CRITICAL' || s === 'ALERT' || s === 'EMERGENCY') return 'log-sev-error';
        if (s === 'WARNING') return 'log-sev-warning';
        return 'log-sev-other';
    }

    function renderRows(entradas, append) {
        var tbody = document.getElementById('tbody-errores-logs');
        var empty = document.getElementById('errores-logs-empty');
        if (!tbody) return;
        if (!append) tbody.innerHTML = '';
        (entradas || []).forEach(function (item) {
            var insertId = item.insert_id || '';
            var tr = document.createElement('tr');
            tr.className = 'errores-log-row';
            tr.setAttribute('data-insert-id', insertId);
            tr.innerHTML =
                '<td>' + esc(formatHora(item.timestamp)) + '</td>' +
                '<td><span class="log-sev-badge ' + sevClass(item.severity) + '">' + esc(item.severity || '—') + '</span></td>' +
                '<td class="errores-log-msg">' + esc(item.mensaje || '—') + '</td>' +
                '<td>' + esc(item.logger || '—') + '</td>' +
                '<td>' + esc(idsFromExtra(item.extra)) + '</td>';
            var detail = document.createElement('tr');
            detail.className = 'errores-log-detail';
            detail.hidden = true;
            detail.setAttribute('data-insert-id', insertId);
            detail.innerHTML = '<td colspan="5"><pre class="errores-stack">Pulsa la fila para cargar el detalle.</pre></td>';
            tbody.appendChild(tr);
            tbody.appendChild(detail);
        });
        if (empty) {
            empty.style.display = tbody.querySelector('.errores-log-row') ? 'none' : 'block';
        }
    }

    function fetchJson(url) {
        return fetch(url, { method: 'GET', credentials: 'same-origin', headers: authHeaders() })
            .then(function (r) {
                return r.json().then(function (j) { return { status: r.status, data: j || {} }; });
            });
    }

    function cargar(opts) {
        var append = !!(opts && opts.append);
        var moreBtn = document.getElementById('btn-errores-cargar-mas');
        setStatus(append ? 'Cargando más…' : 'Cargando logs…', false);
        return fetchJson(buildUrl(opts)).then(function (res) {
            var data = res.data || {};
            if (res.status === 401 || res.status === 403) {
                setStatus(data.message || 'Sesión admin no autorizada.', true);
                return;
            }
            if (data.status === 'error') {
                setStatus(data.message || 'No se pudieron leer los logs.', true);
                if (!append) renderRows([], false);
                if (moreBtn) moreBtn.style.display = 'none';
                return;
            }
            var entradas = data.entradas || [];
            renderRows(entradas, append);
            nextPageToken = data.next_page_token || null;
            if (moreBtn) moreBtn.style.display = nextPageToken ? 'inline-flex' : 'none';
            var n = document.querySelectorAll('#tbody-errores-logs .errores-log-row').length;
            setStatus(n ? (n + ' entradas') : 'Sin entradas', false);
        }).catch(function () {
            setStatus('No se pudo contactar con el servidor.', true);
        });
    }

    function expandirFila(insertId) {
        var details = document.querySelectorAll('#tbody-errores-logs .errores-log-detail');
        details.forEach(function (row) {
            var match = row.getAttribute('data-insert-id') === insertId;
            if (!match) {
                row.hidden = true;
                return;
            }
            if (expandedId === insertId && !row.hidden) {
                row.hidden = true;
                expandedId = null;
                return;
            }
            row.hidden = false;
            expandedId = insertId;
            var pre = row.querySelector('.errores-stack');
            if (pre) pre.textContent = 'Cargando stack…';
            fetchJson(buildUrl({ insertId: insertId, incluirStack: true })).then(function (res) {
                var data = res.data || {};
                var item = (data.entradas || [])[0] || {};
                var extra = item.extra || {};
                var stack = item.stack || '(sin stack en esta entrada)';
                var lines = [
                    stack,
                    '',
                    'extra: ' + JSON.stringify(extra, null, 2)
                ];
                if (pre) pre.textContent = lines.join('\n');
            }).catch(function () {
                if (pre) pre.textContent = 'No se pudo cargar el detalle.';
            });
        });
    }

    function bind() {
        var wrap = document.getElementById('errores-logs-wrap');
        if (!wrap || wrap.dataset.erroresBound === '1') return;
        wrap.dataset.erroresBound = '1';
        var refresh = document.getElementById('btn-actualizar-errores');
        if (refresh) {
            refresh.addEventListener('click', function () {
                nextPageToken = null;
                expandedId = null;
                cargar({ append: false });
            });
        }
        var more = document.getElementById('btn-errores-cargar-mas');
        if (more) {
            more.addEventListener('click', function () {
                if (nextPageToken) cargar({ append: true, pageToken: nextPageToken });
            });
        }
        var tbody = document.getElementById('tbody-errores-logs');
        if (tbody) {
            tbody.addEventListener('click', function (ev) {
                var row = ev.target.closest('.errores-log-row');
                if (!row) return;
                expandirFila(row.getAttribute('data-insert-id') || '');
            });
        }
    }

    function onModuleActivated() {
        bind();
        if (!loadedOnce) {
            loadedOnce = true;
            cargar({ append: false });
        }
    }

    modules.errores = {
        onModuleActivated: onModuleActivated,
        reload: function () {
            loadedOnce = true;
            nextPageToken = null;
            return cargar({ append: false });
        }
    };
})(typeof window !== 'undefined' ? window : globalThis);
