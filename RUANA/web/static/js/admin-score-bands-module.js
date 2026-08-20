/**
 * Bandas oficiales de score RUANA para el panel admin.
 * Espejo de score_service.score_a_estado (350/200/50/15).
 */
(function (global) {
    'use strict';

    var BANDS = [
        { key: 'elite', label: 'Élite', range: '350–500', min: 350, color: '#6b8cce' },
        { key: 'destacado', label: 'Destacado', range: '200–349', min: 200, color: '#e8c468' },
        { key: 'estable', label: 'Estable', range: '50–199', min: 50, color: '#5ecf9a' },
        { key: 'en_riesgo', label: 'En riesgo', range: '15–49', min: 15, color: '#d4926e' },
        { key: 'competencia', label: 'Competencia', range: '0–14', min: 0, color: '#b86a8a' }
    ];

    function scoreFromAliado(aliado) {
        if (!aliado) return 0;
        var raw = aliado.score_panel != null ? aliado.score_panel : aliado.score;
        var n = Number(raw);
        return Number.isFinite(n) ? n : 0;
    }

    function scoreRuanaEstado(score) {
        var s = Math.floor(Number(score) || 0);
        if (s >= 350) return 'elite';
        if (s >= 200) return 'destacado';
        if (s >= 50) return 'estable';
        if (s >= 15) return 'en_riesgo';
        return 'competencia';
    }

    function scoreRuanaBuckets(aliados) {
        var buckets = { elite: 0, destacado: 0, estable: 0, en_riesgo: 0, competencia: 0 };
        (aliados || []).forEach(function (a) {
            buckets[scoreRuanaEstado(scoreFromAliado(a))]++;
        });
        return buckets;
    }

    function bandMeta(key) {
        for (var i = 0; i < BANDS.length; i++) {
            if (BANDS[i].key === key) return BANDS[i];
        }
        return null;
    }

    function isEnRiesgo(aliado) {
        return scoreRuanaEstado(scoreFromAliado(aliado)) === 'en_riesgo';
    }

    function isCompetencia(aliado) {
        return scoreRuanaEstado(scoreFromAliado(aliado)) === 'competencia';
    }

    function isCritico(aliado) {
        var estado = scoreRuanaEstado(scoreFromAliado(aliado));
        return estado === 'en_riesgo' || estado === 'competencia';
    }

    function donutSegments(buckets) {
        return BANDS.map(function (band) {
            return {
                label: band.label,
                value: buckets[band.key] || 0,
                color: band.color
            };
        });
    }

    function statCardsHtml(buckets) {
        return BANDS.map(function (band) {
            return '<div class="score-stat-card"><strong>' + (buckets[band.key] || 0) +
                '</strong><span>' + band.label + ' (' + band.range + ')</span></div>';
        }).join('');
    }

    global.RuanaAdminScoreBands = {
        BANDS: BANDS,
        scoreFromAliado: scoreFromAliado,
        scoreRuanaEstado: scoreRuanaEstado,
        scoreRuanaBuckets: scoreRuanaBuckets,
        bandMeta: bandMeta,
        isEnRiesgo: isEnRiesgo,
        isCompetencia: isCompetencia,
        isCritico: isCritico,
        donutSegments: donutSegments,
        statCardsHtml: statCardsHtml
    };
})(typeof window !== 'undefined' ? window : globalThis);
