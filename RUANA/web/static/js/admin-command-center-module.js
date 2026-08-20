/**
 * RUANA Admin — Command Center (Inicio).
 * Vista visual de operaciones; reutiliza datos de cargarDesdeApi sin tocar APIs.
 */
(function (global) {
    'use strict';

    var charts = global.RuanaAdminCharts;

    function esc(s) {
        if (global.RuanaUi && typeof global.RuanaUi.escapeHtml === 'function') {
            return global.RuanaUi.escapeHtml(s);
        }
        var d = document.createElement('div');
        d.textContent = s == null ? '' : String(s);
        return d.innerHTML;
    }

    function ensureMarkup() {
        var wrap = document.getElementById('command-center-wrap');
        if (!wrap) {
            var host = document.querySelector('.admin-data-content');
            if (!host) return;
            wrap = document.createElement('div');
            wrap.id = 'command-center-wrap';
            wrap.className = 'command-center';
            var estado = host.querySelector('.estado-global');
            if (estado) {
                host.insertBefore(wrap, estado);
            } else {
                host.insertBefore(wrap, host.firstChild);
            }
        }
        if (wrap.dataset.ccBuilt === '1') return;
        wrap.dataset.ccBuilt = '1';
        wrap.innerHTML =
            '<header class="cc-header">' +
            '<div><p class="cc-kicker">RUANA · Centro de mando</p>' +
            '<h1 class="cc-title">Command Center</h1>' +
            '<p class="cc-lead">Control y supervisión de la red RUANA.</p></div>' +
            '<div class="cc-health-pill" id="cc-health-pill"><span class="cc-health-dot"></span><span id="cc-health-label">Estable</span></div>' +
            '</header>' +
            '<div class="cc-kpi-strip" id="cc-kpi-strip"></div>' +
            '<div class="cc-main-grid">' +
            '<div class="cc-main-center">' +
            '<div class="cc-card cc-card-wide"><div id="cc-chart-activity"></div></div>' +
            '<div class="cc-charts-row">' +
            '<div class="cc-card"><div id="cc-chart-allies-jobs"></div></div>' +
            '<div class="cc-card"><div id="cc-chart-scores"></div></div>' +
            '</div>' +
            '<div class="cc-charts-row">' +
            '<div class="cc-card"><div id="cc-chart-cp-activity"></div></div>' +
            '<div class="cc-card"><div id="cc-chart-network"></div></div>' +
            '</div></div>' +
            '<aside class="cc-aside" id="cc-aside"></aside></div>' +
            '<div class="cc-bottom-feed" id="cc-bottom-feed"></div>';
    }

    function buildKpis(data) {
        var ind = data.indicadores || {};
        var conflictos = data.conflictos || 0;
        var trabajos = data.trabajos || 0;
        var items = [
            { id: 'aliados', label: 'Aliados activos', value: ind.aliadosActivos, nav: '#control-aliados-wrap' },
            { id: 'grupos', label: 'Grupos activos', value: ind.gruposActivos, sub: (ind.gruposEnCompetencia || 0) + ' en competencia · ' + (ind.totalGrupos || 0) + ' total', nav: '#grupos-cp-wrap' },
            { id: 'competencia', label: 'En competencia', value: ind.retadores != null ? ind.retadores : '—', sub: (ind.gruposEnCompetencia || 0) + ' grupos', nav: '#competencias-activas-wrap', warn: (ind.retadores || 0) > 0 },
            { id: 'espera', label: 'Suplentes en espera', value: ind.enEspera != null ? ind.enEspera : '—', nav: '#suplentes-espera-wrap', warn: (ind.enEspera || 0) > 0 },
            { id: 'trabajos', label: 'Trabajos abiertos', value: trabajos, nav: '#conversaciones-ruana-wrap' },
            { id: 'solicitudes', label: 'Solicitudes pendientes', value: ind.solicitudesActivas, nav: '#solicitudes-admin-wrap', warn: (ind.solicitudesActivas || 0) > 0 },
            { id: 'conflictos', label: 'Conflictos', value: conflictos, nav: '#conflictos-pago-wrap', warn: conflictos > 0 },
            { id: 'riesgo', label: 'En riesgo', value: ind.enRiesgo != null ? ind.enRiesgo : '—', nav: '#scores-evaluaciones-wrap', warn: (ind.enRiesgo || 0) > 0 }
        ];
        return items.map(function (k) {
            var cls = 'cc-kpi' + (k.warn ? ' is-warn' : '');
            var val = k.isText ? esc(k.value) : esc(k.value != null ? k.value : '—');
            var sub = k.sub ? '<span class="cc-kpi-sub">' + esc(k.sub) + '</span>' : '';
            return '<button type="button" class="' + cls + '" data-cc-nav="' + esc(k.nav || '') + '">' +
                '<span class="cc-kpi-value">' + val + '</span>' +
                '<span class="cc-kpi-label">' + esc(k.label) + '</span>' + sub + '</button>';
        }).join('');
    }

    function scoreBuckets(aliados) {
        var bands = global.RuanaAdminScoreBands;
        if (!bands) return { elite: 0, destacado: 0, estable: 0, en_riesgo: 0, competencia: 0 };
        return bands.scoreRuanaBuckets(aliados);
    }

    function groupByCp(aliados) {
        var map = {};
        (aliados || []).forEach(function (a) {
            var cp = (a.codigo_postal || a.zona || '').toString().trim() || '(sin CP)';
            map[cp] = (map[cp] || 0) + 1;
        });
        return Object.keys(map).sort().map(function (cp) {
            return { cp: cp, count: map[cp] };
        });
    }

    function buildAside(data) {
        var alerts = [];
        if ((data.indicadores.pendientesValidacion || 0) > 0) {
            alerts.push({ level: 'warn', text: data.indicadores.pendientesValidacion + ' aliados pendientes de validación', nav: '#pendientes-validacion-wrap' });
        }
        if ((data.indicadores.enRiesgo || 0) > 0) {
            alerts.push({ level: 'danger', text: data.indicadores.enRiesgo + ' aliados en riesgo', nav: '#scores-evaluaciones-wrap' });
        }
        if ((data.conflictos || 0) > 0) {
            alerts.push({ level: 'danger', text: data.conflictos + ' conflictos de pago sin resolver', nav: '#conflictos-pago-wrap' });
        }
        if ((data.indicadores.gruposEnCompetencia || 0) > 0) {
            alerts.push({ level: 'info', text: data.indicadores.gruposEnCompetencia + ' grupos en competencia', nav: '#competencias-activas-wrap' });
        }
        if (!alerts.length) {
            alerts.push({ level: 'ok', text: 'Sin alertas críticas en este momento.', nav: '' });
        }

        var riesgoList = (data.aliadosEnRiesgo || []).slice(0, 5).map(function (a) {
            return '<li><button type="button" class="cc-aside-link" data-codigo="' + esc(a.codigo) + '">' +
                esc(a.nombre || a.codigo) + ' <span>' + esc(a.score || '—') + '</span></button></li>';
        }).join('') || '<li class="cc-aside-empty">Ninguno detectado</li>';

        var solicitudesPendientes = (data.solicitudes || []).filter(function (s) {
            return (s.estado || '') === 'pendiente';
        });
        var solList = solicitudesPendientes.slice(0, 5).map(function (s) {
            return '<li><button type="button" class="cc-aside-link" data-cc-nav="#solicitudes-admin-wrap">' +
                '<span>' + esc(s.oficio || 'Solicitud') + '</span><small>#' + esc(s.id) + '</small></button></li>';
        }).join('') || '<li class="cc-aside-empty">Sin pendientes</li>';

        var compList = (data.competencias || []).slice(0, 5).map(function (c) {
            var titular = (c.titular && c.titular.nombre) ? c.titular.nombre : (c.titular_codigo || '—');
            var retadorData = c.retador || c.suplente || null;
            var retador = (retadorData && retadorData.nombre) ? retadorData.nombre : '—';
            return '<li><button type="button" class="cc-aside-link" data-cc-nav="#competencias-activas-wrap">' +
                esc(titular) + ' vs ' + esc(retador) + '</button></li>';
        }).join('') || '<li class="cc-aside-empty">Sin competencias activas</li>';

        var incList = (data.incidencias || []).slice(0, 4).map(function (c) {
            return '<li><button type="button" class="cc-aside-link" data-cc-nav="#incidencias-wrap">' +
                esc(c.asunto || c.tipo || 'Incidencia') + '</button></li>';
        }).join('') || '<li class="cc-aside-empty">Sin incidencias abiertas</li>';

        return '<section class="cc-aside-block">' +
            '<h3>Alertas importantes</h3><ul class="cc-alerts">' +
            alerts.map(function (a) {
                return '<li class="cc-alert cc-alert-' + a.level + '">' +
                    (a.nav ? '<button type="button" class="cc-aside-link" data-cc-nav="' + a.nav + '">' + esc(a.text) + '</button>' : esc(a.text)) +
                    '</li>';
            }).join('') + '</ul></section>' +
            '<section class="cc-aside-block"><h3>Aliados en riesgo</h3><ul class="cc-aside-list">' + riesgoList + '</ul></section>' +
            '<section class="cc-aside-block"><h3>Competencias activas</h3><ul class="cc-aside-list">' + compList + '</ul></section>' +
            '<section class="cc-aside-block"><h3>Solicitudes pendientes</h3><ul class="cc-aside-list cc-aside-compact">' + solList + '</ul></section>' +
            '<section class="cc-aside-block"><h3>Incidencias</h3><ul class="cc-aside-list">' + incList + '</ul></section>';
    }

    function buildBottomFeed(data) {
        var eventos = (data.eventos || []).slice(0, 5).map(function (e) {
            return '<div class="cc-feed-item"><time>' + esc(e.fecha || '') + '</time><p>' + esc(e.descripcion || e.tipo || '') + '</p></div>';
        }).join('') || '<p class="cc-aside-empty">Sin eventos recientes</p>';

        var trabajos = (data.trabajosRecientes || []).slice(0, 4).map(function (t) {
            return '<div class="cc-feed-item"><span class="cc-feed-tag">Trabajo</span><p>#' + esc(t.id) + ' · ' + esc(t.estado || '') + '</p></div>';
        }).join('') || '<p class="cc-aside-empty">Sin trabajos recientes</p>';

        return '<div class="cc-feed-grid">' +
            '<div class="cc-card"><h3>Actividad reciente</h3>' + eventos + '</div>' +
            '<div class="cc-card"><h3>Últimos trabajos</h3>' + trabajos + '</div>' +
            '<div class="cc-card"><h3>Últimas solicitudes</h3>' +
            ((data.solicitudes || []).slice(0, 4).map(function (s) {
                return '<div class="cc-feed-item"><span class="cc-feed-tag">Solicitud</span><p>' + esc(s.oficio || '') + ' · ' + esc(s.descripcion || '').slice(0, 60) + '</p></div>';
            }).join('') || '<p class="cc-aside-empty">Sin solicitudes</p>') + '</div>' +
            '<div class="cc-card"><h3>Cambios del sistema</h3>' + eventos + '</div></div>';
    }

    function activityFromHoras(porHora) {
        if (!porHora) return [];
        return Object.keys(porHora).sort().map(function (h) {
            var row = porHora[h] || {};
            var v = (Number(row.contactos_creados) || 0) + (Number(row.nuevas) || 0) + (Number(row.invitaciones_usadas) || 0);
            return { label: h + 'h', v: v };
        });
    }

    function refresh(host, payload) {
        ensureMarkup();
        if (!charts) return;

        var aliados = (host && host._aliadosData) || (payload && payload.aliados) || [];
        var indicadores = payload && payload.indicadores ? payload.indicadores : {};
        if (!indicadores.aliadosActivos && document.getElementById('aliados-activos')) {
            indicadores = {
                aliadosActivos: document.getElementById('aliados-activos').textContent,
                gruposActivos: document.getElementById('total-grupos-desglose') ? (document.getElementById('total-grupos-desglose').textContent.match(/(\d+)\s+activos/) || [])[1] : 0,
                totalGrupos: document.getElementById('total-grupos') ? document.getElementById('total-grupos').textContent : 0,
                solicitudesActivas: document.getElementById('solicitudes-activas') ? document.getElementById('solicitudes-activas').textContent : 0,
                enRiesgo: document.getElementById('en-riesgo-count') ? document.getElementById('en-riesgo-count').textContent : 0,
                pendientesValidacion: document.getElementById('pendientes-validacion-count') ? document.getElementById('pendientes-validacion-count').textContent : 0,
                gruposEnCompetencia: document.getElementById('total-grupos-desglose') ? parseInt((document.getElementById('total-grupos-desglose').textContent.match(/(\d+)\s+en competencia/) || [])[1], 10) || 0 : 0,
                retadores: document.getElementById('retadores-count') ? document.getElementById('retadores-count').textContent : 0,
                enEspera: document.getElementById('en-espera-count') ? document.getElementById('en-espera-count').textContent : 0,
                estadoSistema: document.getElementById('estado-sistema-label') ? document.getElementById('estado-sistema-label').textContent : 'Estable'
            };
        }

        var conflictos = payload && payload.conflictos != null ? payload.conflictos : 0;
        var trabajosCount = payload && payload.trabajos != null ? payload.trabajos : ((host && host._conversacionesList) ? host._conversacionesList.length : 0);
        var solicitudes = payload && payload.solicitudes ? payload.solicitudes : [];
        var eventos = payload && payload.eventos ? payload.eventos : [];
        var incidencias = payload && payload.incidencias ? payload.incidencias : [];
        var competencias = payload && payload.competencias ? payload.competencias : [];
        var scoreBands = global.RuanaAdminScoreBands;
        var aliadosEnRiesgo = aliados.filter(function (a) {
            return scoreBands && scoreBands.isEnRiesgo(a);
        });

        var kpiStrip = document.getElementById('cc-kpi-strip');
        if (kpiStrip) {
            kpiStrip.innerHTML = buildKpis({
                indicadores: indicadores,
                conflictos: conflictos,
                trabajos: trabajosCount
            });
        }

        var healthLabel = document.getElementById('cc-health-label');
        var healthPill = document.getElementById('cc-health-pill');
        if (healthLabel) healthLabel.textContent = indicadores.estadoSistema || 'Estable';
        if (healthPill) {
            var st = String(indicadores.estadoSistema || '').toLowerCase();
            healthPill.className = 'cc-health-pill' + (st.indexOf('crít') >= 0 || st.indexOf('crit') >= 0 ? ' is-critical' : st === 'alerta' ? ' is-warn' : '');
        }

        var porHora = payload && payload.movimiento24hHoras;
        var activityPoints = activityFromHoras(porHora);
        if (!activityPoints.length && host && host._lastMovimiento24h) {
            var m = host._lastMovimiento24h;
            activityPoints = [
                { label: 'Sol', v: (m.solicitudes && m.solicitudes.nuevas) || 0 },
                { label: 'At', v: (m.solicitudes && m.solicitudes.atendidas) || 0 },
                { label: 'Inv', v: (m.invitaciones && m.invitaciones.usadas) || 0 }
            ];
        }

        charts.renderAreaChart(document.getElementById('cc-chart-activity'), {
            title: 'Evolución de actividad',
            subtitle: 'Últimas 24h · clic para detalle',
            points: activityPoints,
            width: 520,
            height: 140,
            color: '#a2ff00',
            nav: '.movimiento-sistema'
        });

        var activos = aliados.filter(function (a) { return (a.estado || '').toLowerCase() === 'activo'; }).length;
        charts.renderBarChart(document.getElementById('cc-chart-allies-jobs'), {
            title: 'Aliados y trabajos',
            items: [
                { label: 'Activos', value: activos || Number(indicadores.aliadosActivos) || 0, nav: '#control-aliados-wrap' },
                { label: 'Riesgo', value: Number(indicadores.enRiesgo) || aliadosEnRiesgo.length, nav: '#scores-evaluaciones-wrap' },
                { label: 'Compet.', value: Number(indicadores.retadores) || competencias.length, nav: '#competencias-activas-wrap' },
                { label: 'Trabajos', value: trabajosCount, nav: '#conversaciones-ruana-wrap' },
                { label: 'Solic.', value: Number(indicadores.solicitudesActivas) || solicitudes.length, nav: '#solicitudes-admin-wrap' }
            ],
            color: '#5ecf9a'
        });

        var buckets = scoreBuckets(aliados);
        var scoreNav = '#scores-evaluaciones-wrap';
        charts.renderDonutChart(document.getElementById('cc-chart-scores'), {
            title: 'Distribución de scores',
            segments: scoreBands ? scoreBands.BANDS.map(function (band) {
                return {
                    label: band.label,
                    value: buckets[band.key] || 0,
                    color: band.color,
                    nav: scoreNav
                };
            }) : []
        });

        var cpGroups = groupByCp(aliados).slice(0, 8);
        charts.renderBarChart(document.getElementById('cc-chart-cp-activity'), {
            title: 'Actividad por CP',
            items: cpGroups.map(function (g) { return { label: g.cp.slice(-4), value: g.count, nav: '#grupos-cp-wrap' }; }),
            color: '#6b8cce'
        });

        charts.renderNetworkMap(document.getElementById('cc-chart-network'), cpGroups);

        var aside = document.getElementById('cc-aside');
        if (aside) {
            aside.innerHTML = buildAside({
                indicadores: indicadores,
                conflictos: conflictos,
                aliadosEnRiesgo: aliadosEnRiesgo,
                solicitudes: solicitudes,
                incidencias: incidencias,
                competencias: competencias
            });
        }

        var feed = document.getElementById('cc-bottom-feed');
        if (feed) {
            feed.innerHTML = buildBottomFeed({
                eventos: eventos,
                trabajosRecientes: (host && host._conversacionesList) || [],
                solicitudes: solicitudes
            });
        }

        bindNavClicks(host);
    }

    function bindNavClicks(host) {
        var root = document.getElementById('command-center-wrap');
        if (!root || root._ccBound) return;
        root._ccBound = true;
        root.addEventListener('click', function (e) {
            var navBtn = e.target.closest('[data-cc-nav], [data-cc-chart-nav]');
            if (navBtn && global.AdminShell && typeof global.AdminShell.navigateTo === 'function') {
                var target = navBtn.getAttribute('data-cc-nav') || navBtn.getAttribute('data-cc-chart-nav');
                if (target) {
                    global.AdminShell.navigateTo(target);
                    return;
                }
            }
            var cpNode = e.target.closest('[data-cc-cp]');
            if (cpNode && host) {
                var cp = cpNode.getAttribute('data-cc-cp');
                if (cp && global.RuanaAdminModules && global.RuanaAdminModules.redExplorer) {
                    host.aliadosCPSeleccionado = cp;
                    host.aliadosGrupoSeleccionado = null;
                    host.aliadosGrupoNombreSeleccionado = null;
                    host.aliadosOficioSeleccionado = null;
                    host.aliadosNivel = 'grupos';
                    global.AdminShell.showModule('red');
                    global.RuanaAdminModules.redExplorer.switchRedView('jerarquia');
                    if (typeof host.renderAliadosJerarquia === 'function') host.renderAliadosJerarquia();
                    global.AdminShell.navigateTo('#control-aliados-wrap');
                }
                return;
            }
            var codigoBtn = e.target.closest('[data-codigo]');
            if (codigoBtn && host) {
                var codigo = codigoBtn.getAttribute('data-codigo');
                var aliado = (host._aliadosData || []).find(function (a) { return a.codigo === codigo; });
                if (aliado && typeof host.abrirModalDetalle === 'function') {
                    global.AdminShell.navigateTo('#control-aliados-wrap');
                    host.abrirModalDetalle(aliado);
                }
            }
        });
    }

    function setup() {
        ensureMarkup();
        document.documentElement.classList.add('command-center-enabled');
    }

    global.RuanaAdminModules = global.RuanaAdminModules || {};
    global.RuanaAdminModules.commandCenter = {
        setup: setup,
        refresh: refresh,
        ensureMarkup: ensureMarkup
    };
})(typeof window !== 'undefined' ? window : globalThis);
