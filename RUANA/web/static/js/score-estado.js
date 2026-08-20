/**
 * Estados de Score RUANA (fuente única para panel admin).
 * Espejo de core.services.score_service.score_a_estado:
 * ÉLITE 350-500, DESTACADO 200-349, ESTABLE 50-199, EN RIESGO 15-49, COMPETENCIA 0-14.
 */
(function (global) {
    'use strict';

    function parseScore(score) {
        var s = parseInt(score, 10);
        return isNaN(s) ? 0 : s;
    }

    function scoreAEstado(score) {
        var s = parseScore(score);
        if (s >= 350) return 'ÉLITE';
        if (s >= 200) return 'DESTACADO';
        if (s >= 50) return 'ESTABLE';
        if (s >= 15) return 'EN RIESGO';
        return 'COMPETENCIA';
    }

    var BANDS = [
        { key: 'elite', estado: 'ÉLITE', label: 'Élite (350-500)', min: 350, color: '#a2ff00' },
        { key: 'destacado', estado: 'DESTACADO', label: 'Destacado (200-349)', min: 200, color: '#5ecf9a' },
        { key: 'estable', estado: 'ESTABLE', label: 'Estable (50-199)', min: 50, color: '#e8c468' },
        { key: 'en_riesgo', estado: 'EN RIESGO', label: 'En riesgo (15-49)', min: 15, color: '#d4926e' },
        { key: 'competencia', estado: 'COMPETENCIA', label: 'Competencia (0-14)', min: 0, color: '#b86a8a' }
    ];

    var ESTADO_TO_KEY = {
        'ÉLITE': 'elite',
        'ELITE': 'elite',
        'DESTACADO': 'destacado',
        'ESTABLE': 'estable',
        'EN RIESGO': 'en_riesgo',
        'COMPETENCIA': 'competencia'
    };

    function emptyBuckets() {
        return { elite: 0, destacado: 0, estable: 0, en_riesgo: 0, competencia: 0 };
    }

    function scoreOfAliado(a) {
        if (!a) return 0;
        if (a.score != null && a.score !== '') return parseScore(a.score);
        return parseScore(a.score_panel);
    }

    function bucketsFromAliados(aliados) {
        var buckets = emptyBuckets();
        (aliados || []).forEach(function (a) {
            var estado = a && a.estado_ruana ? String(a.estado_ruana).trim().toUpperCase() : '';
            var key = ESTADO_TO_KEY[estado];
            if (!key) key = ESTADO_TO_KEY[scoreAEstado(scoreOfAliado(a))];
            buckets[key] += 1;
        });
        return buckets;
    }

    function chartSegments(buckets) {
        var b = buckets || emptyBuckets();
        return BANDS.map(function (band) {
            return { label: band.label, value: b[band.key] || 0, color: band.color };
        });
    }

    function esEnRiesgo(a) {
        return scoreAEstado(scoreOfAliado(a)) === 'EN RIESGO';
    }

    function esAtencion(a) {
        var estado = scoreAEstado(scoreOfAliado(a));
        return estado === 'EN RIESGO' || estado === 'COMPETENCIA';
    }

    global.RuanaScoreEstado = {
        scoreAEstado: scoreAEstado,
        scoreOfAliado: scoreOfAliado,
        bucketsFromAliados: bucketsFromAliados,
        chartSegments: chartSegments,
        esEnRiesgo: esEnRiesgo,
        esAtencion: esAtencion,
        BANDS: BANDS
    };
})(typeof window !== 'undefined' ? window : globalThis);
