/**
 * RUANA Admin — visor de errores/warnings (Cloud Logging).
 * Lista compacta con «Ver más», copiar el error completo y ocultar filas.
 */
(function (global) {
    'use strict';

    var modules = global.RuanaAdminModules = global.RuanaAdminModules || {};
    var STORAGE_KEY = 'ruana.admin.errores.ocultos';
    var PAGE_SIZE = 8;
    var loadedOnce = false;
    var nextPageToken = null;
    var expandedId = null;
    var todas = [];
    var visibles = PAGE_SIZE;
    var cacheById = {};

    function ui() {
        return global.RuanaUI || global.RuanaUi || null;
    }

    function esc(s) {
        var api = ui();
        if (api && api.escapeHtml) return api.escapeHtml(s);
        var d = document.createElement('div');
        d.textContent = s == null ? '' : String(s);
        return d.innerHTML;
    }

    function toast(message, type) {
        var api = ui();
        if (api && typeof api.toast === 'function') {
            api.toast(message, type);
            return;
        }
        var panel = global.adminPanel;
        if (panel && typeof panel.showToast === 'function') {
            panel.showToast(message, type);
        }
    }

    function confirmar(message, opts) {
        var api = ui();
        if (api && typeof api.confirm === 'function') {
            return api.confirm(message, opts || {});
        }
        return Promise.resolve(global.confirm(message));
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
        if (Number.isNaN(d.getTime())) return String(ts);
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

    function claveEntrada(item) {
        var insertId = String((item && item.insert_id) || '').trim();
        if (insertId) return insertId;
        return [item && item.timestamp, item && item.severity, String((item && item.mensaje) || '').slice(0, 160)].join('|');
    }

    function leerOcultosLocal() {
        try {
            var raw = global.localStorage && global.localStorage.getItem(STORAGE_KEY);
            var arr = JSON.parse(raw || '[]');
            return Array.isArray(arr) ? arr.map(String).filter(Boolean) : [];
        } catch (e) {
            return [];
        }
    }

    function guardarOcultosLocal(ids) {
        try {
            if (global.localStorage) {
                global.localStorage.setItem(STORAGE_KEY, JSON.stringify(ids));
            }
        } catch (e) { /* ignore quota */ }
    }

    function marcarOcultosLocal(ids) {
        var set = {};
        leerOcultosLocal().forEach(function (id) { set[id] = true; });
        (ids || []).forEach(function (id) {
            if (id) set[id] = true;
        });
        guardarOcultosLocal(Object.keys(set));
    }

    function filtrarOcultas(entradas) {
        var hidden = {};
        leerOcultosLocal().forEach(function (id) { hidden[id] = true; });
        return (entradas || []).filter(function (item) {
            return !hidden[claveEntrada(item)];
        });
    }

    function textoCompleto(item) {
        item = item || {};
        return [
            'Hora: ' + formatHora(item.timestamp),
            'Severidad: ' + (item.severity || '—'),
            'Módulo: ' + (item.logger || '—'),
            'Identificadores: ' + idsFromExtra(item.extra),
            '',
            item.mensaje || '—',
            '',
            item.stack || '(sin stack en esta entrada)',
            '',
            'extra: ' + JSON.stringify(item.extra || {}, null, 2)
        ].join('\n');
    }

    function copiarTexto(texto) {
        if (global.navigator && global.navigator.clipboard && global.navigator.clipboard.writeText) {
            return global.navigator.clipboard.writeText(texto);
        }
        return new Promise(function (resolve, reject) {
            var ta = document.createElement('textarea');
            ta.value = texto;
            ta.setAttribute('readonly', '');
            ta.style.position = 'fixed';
            ta.style.left = '-9999px';
            document.body.appendChild(ta);
            ta.select();
            try {
                if (document.execCommand('copy')) resolve();
                else reject(new Error('copy'));
            } catch (e) {
                reject(e);
            }
            ta.remove();
        });
    }

    function fetchJson(url, opts) {
        opts = opts || {};
        return fetch(url, {
            method: opts.method || 'GET',
            credentials: 'same-origin',
            headers: authHeaders(opts.body ? { 'Content-Type': 'application/json' } : undefined),
            body: opts.body ? JSON.stringify(opts.body) : undefined
        }).then(function (r) {
            return r.json().then(function (j) { return { status: r.status, data: j || {} }; });
        });
    }

    function recordar(item) {
        var id = claveEntrada(item);
        var prev = cacheById[id] || {};
        cacheById[id] = Object.assign({}, prev, item);
        if (item && item.stack != null) cacheById[id].stack = item.stack;
        return cacheById[id];
    }

    function actualizarToolbar() {
        var toolbar = document.getElementById('errores-logs-toolbar');
        var countEl = document.getElementById('errores-sel-count');
        var selectAll = document.getElementById('errores-select-all');
        var checked = document.querySelectorAll('#tbody-errores-logs .errores-log-check:checked');
        var rows = document.querySelectorAll('#tbody-errores-logs .errores-log-row');
        if (countEl) countEl.textContent = checked.length + (checked.length === 1 ? ' seleccionado' : ' seleccionados');
        if (toolbar) toolbar.hidden = checked.length === 0;
        if (selectAll) {
            selectAll.checked = rows.length > 0 && checked.length === rows.length;
            selectAll.indeterminate = checked.length > 0 && checked.length < rows.length;
        }
    }

    function actualizarMas() {
        var moreBtn = document.getElementById('btn-errores-cargar-mas');
        var restantes = Math.max(0, todas.length - visibles);
        var hayMas = restantes > 0 || !!nextPageToken;
        if (!moreBtn) return;
        moreBtn.style.display = hayMas ? 'inline-flex' : 'none';
        if (!hayMas) return;
        moreBtn.textContent = restantes > 0
            ? ('Ver más · ' + restantes + ' más antiguos')
            : 'Ver más';
    }

    function actualizarEstado() {
        var n = todas.length;
        var shown = Math.min(visibles, n);
        if (!n) {
            setStatus('Sin entradas', false);
            return;
        }
        setStatus(
            shown < n
                ? ('Mostrando ' + shown + ' de ' + n + ' · pulsa Ver más para los más antiguos')
                : (n + (n === 1 ? ' entrada' : ' entradas')),
            false
        );
        actualizarMas();
    }

    function renderVisible() {
        var tbody = document.getElementById('tbody-errores-logs');
        var empty = document.getElementById('errores-logs-empty');
        if (!tbody) return;
        tbody.innerHTML = '';
        var slice = todas.slice(0, visibles);
        slice.forEach(function (item) {
            var insertId = claveEntrada(item);
            recordar(item);
            var tr = document.createElement('tr');
            tr.className = 'errores-log-row';
            tr.setAttribute('data-insert-id', insertId);
            tr.innerHTML =
                '<td class="errores-check-cell">' +
                    '<input type="checkbox" class="errores-log-check" aria-label="Seleccionar registro" />' +
                '</td>' +
                '<td class="errores-hora-cell">' + esc(formatHora(item.timestamp)) + '</td>' +
                '<td class="errores-sev-cell"><span class="log-sev-badge ' + sevClass(item.severity) + '">' + esc(item.severity || '—') + '</span></td>' +
                '<td class="errores-log-msg">' + esc(item.mensaje || '—') + '</td>' +
                '<td class="errores-mod-cell">' + esc(item.logger || '—') + '</td>' +
                '<td class="errores-ids-cell">' + esc(idsFromExtra(item.extra)) + '</td>' +
                '<td class="errores-actions-cell">' +
                    '<button type="button" class="btn-admin-action errores-btn-copiar" data-action="copiar">Copiar</button>' +
                    '<button type="button" class="btn-admin-action errores-btn-eliminar" data-action="eliminar">Eliminar</button>' +
                '</td>';
            var detail = document.createElement('tr');
            detail.className = 'errores-log-detail';
            detail.hidden = true;
            detail.setAttribute('data-insert-id', insertId);
            var cached = cacheById[insertId];
            var preview = (cached && cached.stack != null)
                ? esc(textoCompleto(cached))
                : 'Pulsa la fila para cargar el detalle.';
            detail.innerHTML = '<td colspan="7"><pre class="errores-stack">' + preview + '</pre></td>';
            tbody.appendChild(tr);
            tbody.appendChild(detail);
        });
        if (empty) {
            empty.style.display = slice.length ? 'none' : 'block';
        }
        actualizarToolbar();
        actualizarEstado();
    }

    function cargar(opts) {
        var append = !!(opts && opts.append);
        setStatus(append ? 'Cargando más…' : 'Cargando logs…', false);
        return fetchJson(buildUrl(opts)).then(function (res) {
            var data = res.data || {};
            if (res.status === 401 || res.status === 403) {
                setStatus(data.message || 'Sesión admin no autorizada.', true);
                return;
            }
            if (data.status === 'error') {
                setStatus(data.message || 'No se pudieron leer los logs.', true);
                if (!append) {
                    todas = [];
                    visibles = PAGE_SIZE;
                    renderVisible();
                }
                var moreBtn = document.getElementById('btn-errores-cargar-mas');
                if (moreBtn) moreBtn.style.display = 'none';
                return;
            }
            var entradas = filtrarOcultas(data.entradas || []);
            entradas.forEach(recordar);
            if (append) {
                todas = todas.concat(entradas);
            } else {
                todas = entradas;
                visibles = PAGE_SIZE;
                expandedId = null;
            }
            nextPageToken = data.next_page_token || null;
            if (!todas.length && nextPageToken && !append) {
                return cargar({ append: true, pageToken: nextPageToken });
            }
            renderVisible();
        }).catch(function () {
            setStatus('No se pudo contactar con el servidor.', true);
        });
    }

    function asegurarDetalle(insertId) {
        var cached = cacheById[insertId] || {};
        if (cached.stack != null) return Promise.resolve(cached);
        return fetchJson(buildUrl({ insertId: insertId, incluirStack: true })).then(function (res) {
            var data = res.data || {};
            var item = (data.entradas || [])[0] || cached;
            return recordar(Object.assign({}, cached, item));
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
            asegurarDetalle(insertId).then(function (item) {
                if (pre) pre.textContent = textoCompleto(item);
            }).catch(function () {
                if (pre) pre.textContent = 'No se pudo cargar el detalle.';
            });
        });
    }

    function idsSeleccionados() {
        return Array.prototype.map.call(
            document.querySelectorAll('#tbody-errores-logs .errores-log-row'),
            function (row) {
                var cb = row.querySelector('.errores-log-check');
                if (!cb || !cb.checked) return '';
                return row.getAttribute('data-insert-id') || '';
            }
        ).filter(Boolean);
    }

    function quitarDeLista(ids) {
        var hidden = {};
        (ids || []).forEach(function (id) { hidden[id] = true; });
        todas = todas.filter(function (item) { return !hidden[claveEntrada(item)]; });
        if (visibles > todas.length) visibles = Math.max(todas.length, 0);
        if (expandedId && hidden[expandedId]) expandedId = null;
        renderVisible();
    }

    function ocultarEnServidor(ids) {
        return fetchJson('/api/admin/logs/errores/ocultar', {
            method: 'POST',
            body: { insert_ids: ids }
        }).then(function (res) {
            if (res.status === 401 || res.status === 403) {
                toast(res.data.message || 'Sin permiso para eliminar registros.', 'error');
                return false;
            }
            if (res.data && res.data.status === 'error') {
                toast(res.data.message || 'No se pudieron eliminar.', 'error');
                return false;
            }
            return true;
        }).catch(function () {
            toast('No se pudo contactar con el servidor. Se ocultaron solo en este dispositivo.', 'warning');
            return false;
        });
    }

    function eliminarIds(ids) {
        ids = (ids || []).filter(Boolean);
        if (!ids.length) {
            toast('Selecciona al menos un registro.', 'error');
            return Promise.resolve();
        }
        var msg = ids.length === 1
            ? 'Vas a quitar este registro del visor. El log original sigue en Cloud Logging.'
            : ('Vas a quitar ' + ids.length + ' registros del visor. Los logs originales siguen en Cloud Logging.');
        return confirmar(msg, {
            title: ids.length === 1 ? 'Eliminar registro' : 'Eliminar registros',
            variant: 'danger',
            confirmLabel: 'Eliminar'
        }).then(function (ok) {
            if (!ok) return;
            marcarOcultosLocal(ids);
            quitarDeLista(ids);
            return ocultarEnServidor(ids).then(function (remoteOk) {
                toast(
                    remoteOk
                        ? (ids.length === 1 ? 'Registro eliminado del visor.' : ids.length + ' registros eliminados del visor.')
                        : 'Registro oculto en este dispositivo.',
                    remoteOk ? 'success' : 'warning'
                );
            });
        });
    }

    function copiarIds(ids) {
        ids = (ids || []).filter(Boolean);
        if (!ids.length) {
            toast('Selecciona al menos un registro.', 'error');
            return Promise.resolve();
        }
        return Promise.all(ids.map(function (id) {
            return asegurarDetalle(id).catch(function () {
                return cacheById[id] || { insert_id: id, mensaje: '(sin detalle)' };
            });
        })).then(function (items) {
            var texto = items.map(textoCompleto).join('\n\n----------\n\n');
            return copiarTexto(texto).then(function () {
                toast(ids.length === 1 ? 'Error copiado.' : ids.length + ' errores copiados.', 'success');
            });
        }).catch(function () {
            toast('No se pudo copiar automáticamente.', 'error');
        });
    }

    function verMas() {
        var restantes = Math.max(0, todas.length - visibles);
        if (restantes > 0) {
            visibles = Math.min(todas.length, visibles + PAGE_SIZE);
            renderVisible();
            return;
        }
        if (nextPageToken) {
            var prevLen = todas.length;
            cargar({ append: true, pageToken: nextPageToken }).then(function () {
                if (todas.length > prevLen) {
                    visibles = Math.min(todas.length, visibles + PAGE_SIZE);
                    renderVisible();
                }
            });
        }
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
            more.addEventListener('click', verMas);
        }
        var selectAll = document.getElementById('errores-select-all');
        if (selectAll) {
            selectAll.addEventListener('change', function () {
                var checked = !!selectAll.checked;
                document.querySelectorAll('#tbody-errores-logs .errores-log-check').forEach(function (cb) {
                    cb.checked = checked;
                    var row = cb.closest('.errores-log-row');
                    if (row) row.classList.toggle('is-selected', checked);
                });
                actualizarToolbar();
            });
        }
        var btnEliminarSel = document.getElementById('btn-errores-eliminar-sel');
        if (btnEliminarSel) {
            btnEliminarSel.addEventListener('click', function () {
                eliminarIds(idsSeleccionados());
            });
        }
        var btnCopiarSel = document.getElementById('btn-errores-copiar-sel');
        if (btnCopiarSel) {
            btnCopiarSel.addEventListener('click', function () {
                copiarIds(idsSeleccionados());
            });
        }
        var tbody = document.getElementById('tbody-errores-logs');
        if (tbody) {
            tbody.addEventListener('click', function (ev) {
                var actionBtn = ev.target.closest('[data-action]');
                if (actionBtn) {
                    ev.preventDefault();
                    ev.stopPropagation();
                    var row = actionBtn.closest('.errores-log-row');
                    var id = row ? (row.getAttribute('data-insert-id') || '') : '';
                    if (actionBtn.getAttribute('data-action') === 'copiar') copiarIds([id]);
                    if (actionBtn.getAttribute('data-action') === 'eliminar') eliminarIds([id]);
                    return;
                }
                if (ev.target.closest('.errores-check-cell')) {
                    ev.stopPropagation();
                    return;
                }
                var clickedRow = ev.target.closest('.errores-log-row');
                if (!clickedRow) return;
                expandirFila(clickedRow.getAttribute('data-insert-id') || '');
            });
            tbody.addEventListener('change', function (ev) {
                var cb = ev.target.closest('.errores-log-check');
                if (!cb) return;
                var row = cb.closest('.errores-log-row');
                if (row) row.classList.toggle('is-selected', cb.checked);
                actualizarToolbar();
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
