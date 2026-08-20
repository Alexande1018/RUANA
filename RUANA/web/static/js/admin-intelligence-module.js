/**
 * RUANA Admin — Intelligence (métricas y análisis decisionales).
 */
(function (global) {
    'use strict';

    var charts = global.RuanaAdminCharts;

    function esc(s) {
        var d = document.createElement('div');
        d.textContent = s == null ? '' : String(s);
        return d.innerHTML;
    }

    function ensureMarkup() {
        var el = document.getElementById('intelligence-wrap');
        if (!el) {
            var host = document.querySelector('.admin-data-content');
            if (!host) return;
            el = document.createElement('div');
            el.id = 'intelligence-wrap';
            el.className = 'intelligence-section';
            host.appendChild(el);
        }
        if (el.dataset.intelBuilt === '1') return;
        el.dataset.intelBuilt = '1';
        el.innerHTML =
            '<header class="cc-header">' +
            '<div><p class="cc-kicker">Análisis operativo</p>' +
            '<h2 class="cc-title">Intelligence</h2>' +
            '<p class="cc-lead">Métricas para decidir, no para decorar.</p></div></header>' +
            '<div class="intel-grid">' +
            '<div class="cc-card" id="intel-chart-trends"></div>' +
            '<div class="cc-card" id="intel-chart-response"></div>' +
            '<div class="cc-card" id="intel-chart-confirmation"></div>' +
            '<div class="cc-card" id="intel-chart-conflicts"></div>' +
            '<div class="cc-card" id="intel-chart-groups"></div>' +
            '<div class="cc-card" id="intel-chart-cp-compare"></div>' +
            '<div class="cc-card intel-wide" id="intel-alerts"></div>' +
            '</div>';
    }

    async function fetchIntelData(authHeaders) {
        var opts = { method: 'GET', credentials: 'same-origin', headers: authHeaders };
        var results = await Promise.allSettled([
            fetch('/api/evaluaciones/estadisticas', opts),
            fetch('/api/metricas-salud', opts),
            fetch('/api/movimiento-24h-horas', opts),
            fetch('/api/contactos/metricas', opts)
        ]);
        async function parse(r) {
            if (r.status !== 'fulfilled' || !r.value.ok) return null;
            return r.value.json().catch(function () { return null; });
        }
        return {
            evalStats: await parse(results[0]),
            salud: await parse(results[1]),
            horas: await parse(results[2]),
            contactos: await parse(results[3])
        };
    }

    function renderIntel(host, data, aliados) {
        ensureMarkup();
        if (!charts) return;

        var evalStats = (data.evalStats && data.evalStats.estadisticas) || data.evalStats || {};
        var metricas = (data.salud && data.salud.metricas) || {};
        var contactos = (data.contactos && data.contactos.metricas) || data.contactos || {};
        var porHora = (data.horas && data.horas.por_hora) || {};

        var trendPoints = Object.keys(porHora).sort().map(function (h) {
            var row = porHora[h] || {};
            return { label: h, v: (Number(row.contactos_creados) || 0) + (Number(row.nuevas) || 0) };
        });
        charts.renderAreaChart(document.getElementById('intel-chart-trends'), {
            title: 'Tendencia de actividad',
            subtitle: 'Contactos + solicitudes por hora',
            points: trendPoints,
            width: 480,
            height: 130,
            color: '#5ecf9a'
        });

        var tasaResp = Number(evalStats.tasa_respuesta_promedio || evalStats.tasa_respuesta || metricas.tasa_respuesta) || 0;
        var tasaConf = Number(evalStats.tasa_confirmacion_promedio || evalStats.tasa_confirmacion || metricas.tasa_confirmacion) || 0;
        charts.renderBarChart(document.getElementById('intel-chart-response'), {
            title: 'Tasa de respuesta',
            items: [
                { label: 'Respuesta', value: Math.round(tasaResp * (tasaResp <= 1 ? 100 : 1)) },
                { label: 'Objetivo', value: 80 }
            ],
            color: '#a2ff00'
        });
        charts.renderBarChart(document.getElementById('intel-chart-confirmation'), {
            title: 'Tasa de confirmación',
            items: [
                { label: 'Confirm.', value: Math.round(tasaConf * (tasaConf <= 1 ? 100 : 1)) },
                { label: 'Objetivo', value: 75 }
            ],
            color: '#e8c468'
        });

        var conflictos = Number(contactos.en_disputa || contactos.conflictos_abiertos || 0);
        var cerrados = Number(contactos.cerrados || contactos.trabajos_cerrados || 0);
        var abiertos = Number(contactos.abiertos || contactos.en_progreso || 0);
        charts.renderDonutChart(document.getElementById('intel-chart-conflicts'), {
            title: 'Trabajos y conflictos',
            segments: [
                { label: 'Abiertos', value: abiertos || 1, color: '#6b8cce' },
                { label: 'Cerrados', value: cerrados || 0, color: '#5ecf9a' },
                { label: 'Conflictos', value: conflictos, color: '#d4926e' }
            ]
        });

        var verde = Number(evalStats.verde || evalStats.estado_verde || 0);
        var amarillo = Number(evalStats.amarillo || evalStats.estado_amarillo || 0);
        var rojo = Number(evalStats.rojo || evalStats.estado_rojo || 0);
        charts.renderDonutChart(document.getElementById('intel-chart-groups'), {
            title: 'Salud de aliados (evaluación)',
            segments: [
                { label: 'Estable', value: verde, color: '#5ecf9a' },
                { label: 'Observación', value: amarillo, color: '#e8c468' },
                { label: 'Riesgo', value: rojo, color: '#d4926e' }
            ]
        });

        var byCp = {};
        (aliados || []).forEach(function (a) {
            var cp = (a.codigo_postal || '').toString().trim() || '—';
            if (!byCp[cp]) byCp[cp] = { activos: 0, riesgo: 0 };
            if ((a.estado || '').toLowerCase() === 'activo') byCp[cp].activos++;
            if (global.RuanaScoreEstado ? global.RuanaScoreEstado.esAtencion(a) : Number(a.score) < 50) {
                byCp[cp].riesgo++;
            }
        });
        var cpItems = Object.keys(byCp).slice(0, 6).map(function (cp) {
            return { label: cp.slice(-4), value: byCp[cp].activos };
        });
        charts.renderBarChart(document.getElementById('intel-chart-cp-compare'), {
            title: 'Comparativa por CP',
            items: cpItems.length ? cpItems : [{ label: '—', value: 0 }],
            color: '#6b8cce'
        });

        var anomalies = [];
        if (Number(metricas.oficios_saturados) > Number(metricas.oficios_disponibles)) {
            anomalies.push('Oficios saturados superan disponibles en la red.');
        }
        if (Number(metricas.ratio_solicitud_invitacion) > 2) {
            anomalies.push('Alta presión de solicitudes vs invitaciones.');
        }
        if (conflictos > 3) {
            anomalies.push(conflictos + ' conflictos activos requieren revisión.');
        }
        (aliados || []).filter(function (a) {
            return global.RuanaScoreEstado ? global.RuanaScoreEstado.esAtencion(a) : Number(a.score) < 50;
        }).slice(0, 3).forEach(function (a) {
            anomalies.push('Aliado en riesgo: ' + (a.nombre || a.codigo));
        });
        if (!anomalies.length) anomalies.push('Sin anomalías detectadas en los umbrales actuales.');

        var alertsEl = document.getElementById('intel-alerts');
        if (alertsEl) {
            alertsEl.innerHTML = '<h3>Alertas y anomalías</h3><ul class="intel-alert-list">' +
                anomalies.map(function (t) { return '<li>' + esc(t) + '</li>'; }).join('') +
                '</ul><div class="intel-metrics-row">' +
                '<div><span class="intel-metric-label">Ratio sol→inv</span><strong>' + esc(metricas.ratio_solicitud_invitacion != null ? metricas.ratio_solicitud_invitacion : '—') + '</strong></div>' +
                '<div><span class="intel-metric-label">Retención</span><strong>' + esc(metricas.tasa_retencion != null ? metricas.tasa_retencion + '%' : '—') + '</strong></div>' +
                '<div><span class="intel-metric-label">Zona demanda</span><strong>' + esc(metricas.zona_mayor_demanda || '—') + '</strong></div></div>';
        }
    }

    async function refresh(host) {
        ensureMarkup();
        var authHeaders = typeof AdminAuthenticator !== 'undefined' ? AdminAuthenticator.getAdminAuthHeaders() : {};
        try {
            var data = await fetchIntelData(authHeaders);
            renderIntel(host, data, host && host._aliadosData);
        } catch (e) {
            renderIntel(host, {}, host && host._aliadosData);
        }
    }

    global.RuanaAdminModules = global.RuanaAdminModules || {};
    global.RuanaAdminModules.intelligence = {
        ensureMarkup: ensureMarkup,
        refresh: refresh
    };
})(typeof window !== 'undefined' ? window : globalThis);
