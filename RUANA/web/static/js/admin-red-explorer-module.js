/**
 * RUANA Admin — Explorador de red: árbol genealógico, grupos/CP, scores, incidencias.
 */
(function (global) {
    'use strict';

    var currentRedView = 'jerarquia';
    var referidosTree = null;

    function esc(s) {
        var d = document.createElement('div');
        d.textContent = s == null ? '' : String(s);
        return d.innerHTML;
    }

    function ensureSections() {
        var controlWrap = document.getElementById('control-aliados-wrap');
        if (!controlWrap) return;

        if (!document.getElementById('red-explorer-tabs')) {
            var tabs = document.createElement('div');
            tabs.id = 'red-explorer-tabs';
            tabs.className = 'red-explorer-tabs';
            tabs.innerHTML =
                '<button type="button" class="red-tab is-active" data-red-view="jerarquia">Jerarquía CP → Grupo → Oficio</button>' +
                '<button type="button" class="red-tab" data-red-view="referidos">Árbol genealógico</button>';
            var titulo = controlWrap.querySelector('.seccion-titulo');
            if (titulo) titulo.parentNode.insertBefore(tabs, titulo.nextSibling);
        }
    }

    function switchRedView(view, options) {
        var opts = options || {};
        var next = view === 'referidos' ? 'referidos' : 'jerarquia';
        currentRedView = next;

        var jerarquia = document.getElementById('red-view-jerarquia');
        var referidos = document.getElementById('red-view-referidos');
        if (jerarquia) jerarquia.classList.toggle('is-active', next === 'jerarquia');
        if (referidos) referidos.classList.toggle('is-active', next === 'referidos');

        var tabs = document.getElementById('red-explorer-tabs');
        if (tabs) {
            tabs.querySelectorAll('.red-tab').forEach(function (btn) {
                btn.classList.toggle('is-active', btn.getAttribute('data-red-view') === next);
            });
        }

        if (next === 'referidos') {
            initReferidosTree(true);
            setupReferidosSearch();
        } else if (!opts.skipRender && global._ruanaAdminPanel && typeof global._ruanaAdminPanel.renderAliadosJerarquia === 'function') {
            global._ruanaAdminPanel.renderAliadosJerarquia();
        }
    }

    function setupRedTabs() {
        var tabs = document.getElementById('red-explorer-tabs');
        if (!tabs || tabs._bound) return;
        tabs._bound = true;
        tabs.addEventListener('click', function (e) {
            var btn = e.target.closest('[data-red-view]');
            if (!btn) return;
            switchRedView(btn.getAttribute('data-red-view'));
        });
        switchRedView(currentRedView, { skipRender: true });
    }

    function initReferidosTree(forceReload) {
        if (!global.RuanaReferidos || !global.RuanaReferidos.RuanaReferidosTree) {
            var treeEl = document.getElementById('referidos-tree-admin');
            if (treeEl) {
                treeEl.innerHTML = '<p style="color:#94a3b8;padding:16px;">No se pudo cargar el módulo de referidos. Recarga la página.</p>';
            }
            return;
        }
        var panel = global._ruanaAdminPanel;
        var TreeCtor = global.RuanaReferidos.RuanaReferidosTree;
        var authHeaders = typeof AdminAuthenticator !== 'undefined'
            ? AdminAuthenticator.getAdminAuthHeaders()
            : {};
        var treeContainer = document.getElementById('referidos-tree-admin');
        var detailContainer = document.getElementById('referidos-detail-admin');
        var metaContainer = document.getElementById('referidos-meta-admin');
        if (!treeContainer || !detailContainer) return;

        if (!referidosTree) {
            if (!detailContainer.classList.contains('referidos-detail-panel')) {
                detailContainer.classList.add('referidos-detail-panel', 'empty');
            }
            referidosTree = new TreeCtor({
                treeContainer: treeContainer,
                detailContainer: detailContainer,
                metaContainer: metaContainer,
                mode: 'admin',
                fetchOptions: {
                    credentials: 'same-origin',
                    headers: authHeaders
                },
                onVerDetalleCompleto: function (nodo) {
                    if (panel && panel._aliadosData) {
                        var aliado = panel._aliadosData.find(function (a) { return a.codigo === nodo.codigo; });
                        if (aliado && typeof panel.abrirModalDetalle === 'function') {
                            panel.abrirModalDetalle(aliado);
                        } else if (typeof panel.abrirModalDetalle === 'function') {
                            panel.abrirModalDetalle(nodo);
                        }
                    }
                },
                onCentrarArbol: function (codigo) {
                    if (referidosTree && typeof referidosTree.focusOnCodigo === 'function') {
                        referidosTree.focusOnCodigo(codigo).catch(function (err) {
                            if (panel && typeof panel.showToast === 'function') {
                                panel.showToast((err && err.message) || 'No se pudo centrar el árbol', 'error');
                            }
                        });
                    }
                },
                onPausarAliado: function (nodo) {
                    if (panel && typeof panel.confirmarPausa === 'function') {
                        panel.confirmarPausa(panel, nodo);
                    }
                },
                onEliminarAliado: function (nodo) {
                    if (panel && typeof panel.confirmarEliminarPerfil === 'function') {
                        panel._aliadoDetalleActual = nodo;
                        panel.confirmarEliminarPerfil(panel);
                    }
                }
            });
        } else {
            referidosTree.fetchOptions = {
                credentials: 'same-origin',
                headers: authHeaders
            };
        }
        var needsLoad = forceReload || !referidosTree._adminLoaded ||
            (!treeContainer.querySelector('.referidos-node-card') &&
                !treeContainer.querySelector('.referidos-loading'));
        if (needsLoad) {
            referidosTree.load().then(function () {
                referidosTree._adminLoaded = true;
            }).catch(function (err) {
                referidosTree._adminLoaded = false;
                if (panel && typeof panel.showToast === 'function') {
                    panel.showToast((err && err.message) || 'No se pudo cargar la red de referidos', 'error');
                }
            });
        }
    }

    /** Compatibilidad con AdminPanel histórico (proyecto_original / f62952a). */
    function initReferidosArbol() {
        initReferidosTree(true);
    }

    function authHeaders(extra) {
        var base = typeof AdminAuthenticator !== 'undefined'
            ? AdminAuthenticator.getAdminAuthHeaders(extra)
            : {};
        if (extra) {
            Object.keys(extra).forEach(function (k) {
                if (k !== '_skipContentType') base[k] = extra[k];
            });
        }
        return base;
    }

    function renderGruposTabla(grupos) {
        var tbody = document.getElementById('tbody-grupos-admin');
        if (!tbody) return;
        if (!grupos || !grupos.length) {
            tbody.innerHTML = '<tr><td colspan="7" style="color:#94a3b8;">Sin grupos en la base de datos.</td></tr>';
            return;
        }
        tbody.innerHTML = grupos.map(function (g) {
            var estado = (g.estado || '').toString();
            var activos = Number(g.aliados_activos) || 0;
            var alertCls = (estado.toLowerCase() !== 'activo' || activos <= 1) ? 'grupo-admin-row--alert' : '';
            var creado = (g.fecha_creacion || '').toString().slice(0, 16);
            return '<tr class="' + alertCls + '">' +
                '<td>' + esc(g.id) + '</td>' +
                '<td>' + esc(g.nombre) + '</td>' +
                '<td>' + esc(g.codigo_postal) + '</td>' +
                '<td>' + esc(estado) + '</td>' +
                '<td>' + esc(activos) + '</td>' +
                '<td>' + esc(g.aliados_total) + '</td>' +
                '<td>' + esc(creado) + '</td></tr>';
        }).join('');
    }

    function loadGruposTabla() {
        var tbody = document.getElementById('tbody-grupos-admin');
        if (!tbody) return Promise.resolve();
        return fetch('/api/admin/grupos', {
            method: 'GET',
            credentials: 'same-origin',
            headers: authHeaders()
        }).then(function (r) {
            if (!r.ok) throw new Error('No se pudo cargar la tabla de grupos');
            return r.json();
        }).then(function (data) {
            if (data.status !== 'success') throw new Error(data.message || 'Error al cargar grupos');
            renderGruposTabla(data.grupos || []);
        }).catch(function (err) {
            tbody.innerHTML = '<tr><td colspan="7" style="color:var(--ruana-estado-riesgo,#d4926e);">' +
                esc((err && err.message) || 'Error al cargar grupos') + '</td></tr>';
        });
    }

    function statusClassForReasign(status) {
        if (status === 'reasignado') return 'reasign-status--ok';
        if (status === 'sin_plaza_disponible' || status === 'sin_oficio_o_cp') return 'reasign-status--warn';
        return 'reasign-status--error';
    }

    function renderAliadosSinGrupo(aliados, resultadosMap) {
        var tbody = document.getElementById('tbody-aliados-sin-grupo');
        var countEl = document.getElementById('aliados-sin-grupo-count');
        if (!tbody) return;
        var list = aliados || [];
        if (countEl) countEl.textContent = list.length ? '(' + list.length + ')' : '';
        if (!list.length) {
            tbody.innerHTML = '<tr><td colspan="7" style="color:#94a3b8;">No hay aliados activos sin grupo.</td></tr>';
            return;
        }
        tbody.innerHTML = list.map(function (a) {
            var codigo = a.codigo || '';
            var res = resultadosMap && resultadosMap[codigo];
            var resHtml = res
                ? '<span class="' + statusClassForReasign(res.status) + '">' + esc(res.status) + '</span>'
                : '—';
            var desde = (a.creado_en || a.fecha_registro || '').toString().slice(0, 16);
            var rowCls = res && res.status === 'reasignado' ? 'aliado-sin-grupo--done' : '';
            return '<tr data-codigo="' + esc(codigo) + '" class="' + rowCls + '">' +
                '<td>' + esc(codigo) + '</td>' +
                '<td>' + esc(a.nombre) + '</td>' +
                '<td>' + esc(a.oficio) + '</td>' +
                '<td>' + esc(a.codigo_postal) + '</td>' +
                '<td>' + esc(a.invitado_por_codigo || '—') + '</td>' +
                '<td>' + esc(desde) + '</td>' +
                '<td class="reasign-result-cell">' + resHtml + '</td></tr>';
        }).join('');
    }

    function loadAliadosSinGrupo() {
        return fetch('/api/admin/aliados-sin-grupo', {
            method: 'GET',
            credentials: 'same-origin',
            headers: authHeaders()
        }).then(function (r) {
            if (!r.ok) throw new Error('No se pudo cargar aliados sin grupo');
            return r.json();
        }).then(function (data) {
            if (data.status !== 'success') throw new Error(data.message || 'Error');
            renderAliadosSinGrupo(data.aliados || [], null);
        }).catch(function (err) {
            var tbody = document.getElementById('tbody-aliados-sin-grupo');
            if (tbody) {
                tbody.innerHTML = '<tr><td colspan="7" style="color:var(--ruana-estado-riesgo,#d4926e);">' +
                    esc((err && err.message) || 'Error') + '</td></tr>';
            }
        });
    }

    function summarizeProcesarNoViables(resultados) {
        var fusionados = 0;
        var disueltos = 0;
        (resultados || []).forEach(function (r) {
            var accion = (r.accion || r.resultado || '').toString().toLowerCase();
            if (accion.indexOf('fusion') >= 0 || accion.indexOf('absorb') >= 0) fusionados++;
            else if (accion.indexOf('disuel') >= 0) disueltos++;
        });
        if (!resultados || !resultados.length) {
            return 'No se procesaron grupos (ninguno no viable en este momento).';
        }
        return fusionados + ' fusionado(s), ' + disueltos + ' disuelto(s), ' + resultados.length + ' procesado(s) en total.';
    }

    function setupGruposAdminActions(host) {
        var btnProcesar = document.getElementById('btn-procesar-grupos-no-viables');
        if (btnProcesar && !btnProcesar._bound) {
            btnProcesar._bound = true;
            btnProcesar.addEventListener('click', function () {
                if (!confirm('¿Procesar grupos no viables? Se fusionarán o disolverán grupos activos con un solo aliado activo.')) return;
                btnProcesar.disabled = true;
                fetch('/api/admin/grupos/procesar-no-viables', {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: authHeaders({ 'Content-Type': 'application/json' })
                }).then(function (r) { return r.json().then(function (d) { return { ok: r.ok, data: d }; }); })
                    .then(function (res) {
                        if (!res.ok || res.data.status !== 'success') {
                            throw new Error((res.data && res.data.message) || 'Error al procesar');
                        }
                        var msg = summarizeProcesarNoViables(res.data.resultados);
                        if (host && typeof host.showToast === 'function') host.showToast(msg, 'success');
                        loadGruposTabla();
                    })
                    .catch(function (err) {
                        if (host && typeof host.showToast === 'function') {
                            host.showToast((err && err.message) || 'Error al procesar grupos', 'error');
                        }
                    })
                    .finally(function () { btnProcesar.disabled = false; });
            });
        }

        var btnReasignar = document.getElementById('btn-reasignar-aliados-sin-grupo');
        if (btnReasignar && !btnReasignar._bound) {
            btnReasignar._bound = true;
            btnReasignar.addEventListener('click', function () {
                if (!confirm('¿Reasignar todos los aliados sin grupo? Solo se asignará plaza existente; sin plaza quedan varados.')) return;
                btnReasignar.disabled = true;
                fetch('/api/admin/aliados-sin-grupo/reasignar', {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: authHeaders({ 'Content-Type': 'application/json' })
                }).then(function (r) { return r.json().then(function (d) { return { ok: r.ok, data: d }; }); })
                    .then(function (res) {
                        if (!res.ok || res.data.status !== 'success') {
                            throw new Error((res.data && res.data.message) || 'Error al reasignar');
                        }
                        var map = {};
                        (res.data.resultados || []).forEach(function (r) {
                            if (r.codigo) map[r.codigo] = r;
                        });
                        var tbody = document.getElementById('tbody-aliados-sin-grupo');
                        if (tbody) {
                            tbody.querySelectorAll('tr[data-codigo]').forEach(function (tr) {
                                var cod = tr.getAttribute('data-codigo');
                                var item = map[cod];
                                if (!item) return;
                                var cell = tr.querySelector('.reasign-result-cell');
                                if (cell) {
                                    cell.innerHTML = '<span class="' + statusClassForReasign(item.status) + '">' + esc(item.status) + '</span>';
                                }
                                if (item.status === 'reasignado') {
                                    tr.classList.add('aliado-sin-grupo--done');
                                    setTimeout(function () { tr.remove(); }, 2500);
                                }
                            });
                        }
                        var msg = res.data.reasignados + ' de ' + res.data.total + ' reasignado(s)';
                        if (host && typeof host.showToast === 'function') host.showToast(msg, 'success');
                        setTimeout(loadAliadosSinGrupo, 2600);
                    })
                    .catch(function (err) {
                        if (host && typeof host.showToast === 'function') {
                            host.showToast((err && err.message) || 'Error al reasignar', 'error');
                        }
                    })
                    .finally(function () { btnReasignar.disabled = false; });
            });
        }
    }

    function renderGruposCp(host) {
        var overview = document.getElementById('grupos-cp-overview');
        if (!overview) return;
        var aliados = (host && host._aliadosData) || [];
        var byCp = {};
        aliados.forEach(function (a) {
            if (host && host.esAliadoPlaceholder && host.esAliadoPlaceholder(a)) return;
            var cp = (a.codigo_postal || a.zona || '').toString().trim() || '(sin CP)';
            if (!byCp[cp]) byCp[cp] = { grupos: {}, total: 0, activos: 0 };
            byCp[cp].total++;
            if ((a.estado || '').toLowerCase() === 'activo') byCp[cp].activos++;
            var gKey = host && host.getClaveGrupoRed ? host.getClaveGrupoRed(a) : (a.grupo_id || '__sin_grupo__');
            var gName = host && host.getNombreGrupoRed ? host.getNombreGrupoRed(a) : (a.grupo_nombre || gKey);
            if (!byCp[cp].grupos[gKey]) byCp[cp].grupos[gKey] = { nombre: gName, count: 0 };
            byCp[cp].grupos[gKey].count++;
        });
        var cps = Object.keys(byCp).sort();
        if (!cps.length) {
            overview.innerHTML = '<p style="color:#94a3b8;">Sin datos de grupos. Carga el panel o revisa la conexión.</p>';
            return;
        }
        overview.innerHTML = cps.map(function (cp) {
            var info = byCp[cp];
            var gruposHtml = Object.keys(info.grupos).map(function (gk) {
                var g = info.grupos[gk];
                return '<div>· ' + esc(g.nombre) + ' — ' + g.count + ' aliado' + (g.count !== 1 ? 's' : '') + '</div>';
            }).join('');
            return '<div class="grupos-cp-card" role="button" tabindex="0" data-cp="' + esc(cp) + '">' +
                '<h4>CP ' + esc(cp) + '</h4>' +
                '<div class="grupos-cp-meta">' + info.activos + ' activos / ' + info.total + ' total · ' +
                Object.keys(info.grupos).length + ' grupo' + (Object.keys(info.grupos).length !== 1 ? 's' : '') + '</div>' +
                '<div class="grupos-cp-meta" style="margin-top:8px;">' + gruposHtml + '</div></div>';
        }).join('');
        overview.querySelectorAll('.grupos-cp-card').forEach(function (card) {
            function openCp() {
                var cp = card.getAttribute('data-cp');
                if (!host || !cp) return;
                host.aliadosCPSeleccionado = cp;
                host.aliadosGrupoSeleccionado = null;
                host.aliadosGrupoNombreSeleccionado = null;
                host.aliadosOficioSeleccionado = null;
                host.aliadosNivel = 'grupos';
                if (global.AdminShell) {
                    global.AdminShell.showModule('red', { skipScroll: false });
                    global.AdminShell.navigateTo('#control-aliados-wrap');
                }
                switchRedView('jerarquia');
                if (typeof host.renderAliadosJerarquia === 'function') host.renderAliadosJerarquia();
            }
            card.addEventListener('click', openCp);
            card.addEventListener('keydown', function (e) {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    openCp();
                }
            });
        });
    }

    function renderScores(host) {
        var grid = document.getElementById('scores-eval-grid');
        var chartEl = document.getElementById('scores-eval-chart');
        if (!grid) return;
        var aliados = (host && host._aliadosData) || [];
        var ruana = global.RuanaScoreEstado;
        var buckets = ruana
            ? ruana.bucketsFromAliados(aliados)
            : { elite: 0, destacado: 0, estable: 0, en_riesgo: 0, competencia: 0 };
        var bands = ruana ? ruana.BANDS : [];
        grid.innerHTML = bands.map(function (band) {
            return '<div class="score-stat-card"><strong>' + (buckets[band.key] || 0) + '</strong><span>' +
                esc(band.label) + '</span></div>';
        }).join('');
        if (chartEl && global.RuanaAdminCharts && ruana) {
            global.RuanaAdminCharts.renderDonutChart(chartEl, {
                title: 'Distribución de scores en la red',
                segments: ruana.chartSegments(buckets)
            });
        }
    }

    function renderIncidencias(host, conversaciones) {
        var tbody = document.getElementById('tbody-incidencias-admin');
        var empty = document.getElementById('incidencias-empty');
        var badge = document.getElementById('incidencias-count-badge');
        if (!tbody) return;
        var list = (conversaciones || (host && host._centroComunicacion) || []).filter(function (c) {
            return String(c.tipo || '').toLowerCase() === 'incidencia';
        });
        if (badge) badge.textContent = String(list.length);
        tbody.innerHTML = '';
        if (empty) empty.style.display = list.length ? 'none' : 'block';
        list.forEach(function (c) {
            var tr = document.createElement('tr');
            tr.innerHTML =
                '<td>' + esc(c.id) + '</td>' +
                '<td>' + esc(c.aliado_nombre || c.aliado_codigo || '—') + '</td>' +
                '<td>' + esc(c.asunto || c.ultimo_mensaje || '—') + '</td>' +
                '<td>' + esc(c.estado || 'abierta') + '</td>' +
                '<td>' + esc((c.actualizado_en || c.creado_en || '').toString().slice(0, 16)) + '</td>' +
                '<td><button type="button" class="btn-accion btn-ver-incidencia" data-id="' + esc(c.id) + '">Ver</button></td>';
            var btn = tr.querySelector('.btn-ver-incidencia');
            if (btn && global.AdminShell) {
                btn.addEventListener('click', function () {
                    global.AdminShell.navigateTo('#centro-comunicacion-admin-wrap');
                });
            }
            tbody.appendChild(tr);
        });
    }

    function refresh(host) {
        renderGruposCp(host);
        loadGruposTabla();
        loadAliadosSinGrupo();
        renderScores(host);
        renderIncidencias(host);
    }

    function onRedModuleActivated() {
        ensureSections();
        if (currentRedView === 'referidos') {
            initReferidosTree(false);
        } else if (global._ruanaAdminPanel && typeof global._ruanaAdminPanel.renderAliadosJerarquia === 'function') {
            global._ruanaAdminPanel.renderAliadosJerarquia();
        }
    }

    function setupReferidosSearch() {
        var input = document.getElementById('referidos-admin-search');
        var btn = document.getElementById('referidos-admin-search-btn');
        if (!input || input._bound) return;
        input._bound = true;
        function runSearch() {
            var q = (input.value || '').trim();
            if (!q) return;
            initReferidosTree(false);
            if (referidosTree && typeof referidosTree.searchAndFocus === 'function') {
                referidosTree.searchAndFocus(q).catch(function (err) {
                    var panel = global._ruanaAdminPanel;
                    if (panel && typeof panel.showToast === 'function') {
                        panel.showToast(err && err.message ? err.message : 'No se encontró el aliado en la red.', 'error');
                    }
                });
            }
        }
        if (btn) btn.addEventListener('click', runSearch);
        input.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                runSearch();
            }
        });
    }

    function setup() {
        ensureSections();
        setupRedTabs();
        setupReferidosSearch();
        setupGruposAdminActions(global._ruanaAdminPanel);
    }

    global.RuanaAdminModules = global.RuanaAdminModules || {};
    global.RuanaAdminModules.redExplorer = {
        setup: setup,
        refresh: refresh,
        renderGruposCp: renderGruposCp,
        loadGruposTabla: loadGruposTabla,
        loadAliadosSinGrupo: loadAliadosSinGrupo,
        renderScores: renderScores,
        renderIncidencias: renderIncidencias,
        initReferidosTree: initReferidosTree,
        initReferidosArbol: initReferidosArbol,
        switchRedView: switchRedView,
        onRedModuleActivated: onRedModuleActivated
    };
})(typeof window !== 'undefined' ? window : globalThis);
