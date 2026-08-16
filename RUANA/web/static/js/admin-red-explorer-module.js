/**
 * RUANA Admin — Explorador de red: árbol genealógico, grupos/CP, scores, incidencias.
 */
(function (global) {
    'use strict';

    function esc(s) {
        var d = document.createElement('div');
        d.textContent = s == null ? '' : String(s);
        return d.innerHTML;
    }

    function ensureSections() {
        if (!document.getElementById('red-explorer-tabs')) {
            var tabs = document.createElement('div');
            tabs.id = 'red-explorer-tabs';
            tabs.className = 'red-explorer-tabs';
            tabs.innerHTML =
                '<button type="button" class="red-tab is-active" data-red-view="jerarquia">Jerarquía CP → Grupo → Oficio</button>' +
                '<button type="button" class="red-tab" data-red-view="referidos">Árbol genealógico</button>';
            var controlWrap = document.getElementById('control-aliados-wrap');
            if (controlWrap) {
                var titulo = controlWrap.querySelector('.seccion-titulo');
                if (titulo) titulo.parentNode.insertBefore(tabs, titulo.nextSibling);
            }
        }
        var referidos = document.getElementById('referidos-red-wrap');
        if (referidos) referidos.style.display = 'none';
    }

    var referidosTree = null;

    function setupRedTabs() {
        var tabs = document.getElementById('red-explorer-tabs');
        if (!tabs || tabs._bound) return;
        tabs._bound = true;
        tabs.addEventListener('click', function (e) {
            var btn = e.target.closest('[data-red-view]');
            if (!btn) return;
            var view = btn.getAttribute('data-red-view');
            tabs.querySelectorAll('.red-tab').forEach(function (b) {
                b.classList.toggle('is-active', b === btn);
            });
            var control = document.getElementById('control-aliados-wrap');
            var referidos = document.getElementById('referidos-red-wrap');
            if (view === 'referidos') {
                if (control) control.style.display = 'none';
                if (referidos) referidos.style.display = 'block';
                initReferidosTree();
            } else {
                if (control) control.style.display = 'block';
                if (referidos) referidos.style.display = 'none';
            }
        });
        var referidos = document.getElementById('referidos-red-wrap');
        if (referidos) referidos.style.display = 'none';
    }

    function initReferidosTree() {
        if (!global.RuanaReferidos || !global.RuanaReferidos.RuanaReferidosTree) return;
        if (referidosTree) return;
        var panel = global._ruanaAdminPanel;
        var TreeCtor = global.RuanaReferidos.RuanaReferidosTree;
        referidosTree = new TreeCtor({
            treeContainer: document.getElementById('referidos-tree-admin'),
            detailContainer: document.getElementById('referidos-detail-admin'),
            metaContainer: document.getElementById('referidos-meta-admin'),
            mode: 'admin',
            fetchOptions: {
                headers: typeof AdminAuthenticator !== 'undefined' ? AdminAuthenticator.getAdminAuthHeaders() : {}
            },
            onVerDetalleCompleto: function (nodo) {
                if (panel && panel._aliadosData) {
                    var aliado = panel._aliadosData.find(function (a) { return a.codigo === nodo.codigo; });
                    if (aliado && typeof panel.abrirModalDetalle === 'function') {
                        panel.abrirModalDetalle(aliado);
                    }
                }
            },
            onCentrarArbol: function (codigo) {
                if (referidosTree && typeof referidosTree.focusOnCodigo === 'function') {
                    referidosTree.focusOnCodigo(codigo);
                }
            }
        });
        referidosTree.loadAdmin();
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
            overview.innerHTML = '<p style="color:#94a3b8;">Sin datos de grupos.</p>';
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
            card.addEventListener('click', function () {
                var cp = card.getAttribute('data-cp');
                if (host && cp) {
                    host.aliadosCPSeleccionado = cp;
                    host.aliadosGrupoSeleccionado = null;
                    host.aliadosOficioSeleccionado = null;
                    host.aliadosNivel = 'grupos';
                    if (global.AdminShell) global.AdminShell.navigateTo('#control-aliados-wrap');
                    if (typeof host.renderAliadosJerarquia === 'function') host.renderAliadosJerarquia();
                }
            });
        });
    }

    function renderScores(host) {
        var grid = document.getElementById('scores-eval-grid');
        var chartEl = document.getElementById('scores-eval-chart');
        if (!grid) return;
        var aliados = (host && host._aliadosData) || [];
        var buckets = { alto: 0, medio: 0, bajo: 0, riesgo: 0 };
        var enRiesgo = 0;
        aliados.forEach(function (a) {
            var s = Number(a.score_panel != null ? a.score_panel : a.score) || 0;
            if (s >= 400) buckets.alto++;
            else if (s >= 250) buckets.medio++;
            else if (s >= 100) buckets.bajo++;
            else buckets.riesgo++;
            if (a.estado_panel === 'riesgo') enRiesgo++;
        });
        grid.innerHTML =
            '<div class="score-stat-card"><strong>' + buckets.alto + '</strong><span>Score alto (400+)</span></div>' +
            '<div class="score-stat-card"><strong>' + buckets.medio + '</strong><span>Score medio</span></div>' +
            '<div class="score-stat-card"><strong>' + buckets.bajo + '</strong><span>Score bajo</span></div>' +
            '<div class="score-stat-card"><strong>' + buckets.riesgo + '</strong><span>En riesgo (&lt;100)</span></div>' +
            '<div class="score-stat-card"><strong>' + enRiesgo + '</strong><span>Estado panel: riesgo</span></div>';
        if (chartEl && global.RuanaAdminCharts) {
            global.RuanaAdminCharts.renderDonutChart(chartEl, {
                title: 'Distribución de scores en la red',
                segments: [
                    { label: 'Alto', value: buckets.alto, color: '#a2ff00' },
                    { label: 'Medio', value: buckets.medio, color: '#5ecf9a' },
                    { label: 'Bajo', value: buckets.bajo, color: '#e8c468' },
                    { label: 'Riesgo', value: buckets.riesgo, color: '#d4926e' }
                ]
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
        renderScores(host);
        renderIncidencias(host);
    }

    function setup() {
        ensureSections();
        setupRedTabs();
    }

    global.RuanaAdminModules = global.RuanaAdminModules || {};
    global.RuanaAdminModules.redExplorer = {
        setup: setup,
        refresh: refresh,
        renderGruposCp: renderGruposCp,
        renderScores: renderScores,
        renderIncidencias: renderIncidencias,
        initReferidosTree: initReferidosTree
    };
})(typeof window !== 'undefined' ? window : globalThis);
