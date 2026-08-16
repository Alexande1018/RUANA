/**
 * RUANA Admin — gráficos SVG ligeros (sin dependencias externas).
 */
(function (global) {
    'use strict';

    function esc(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
    }

    function niceMax(val) {
        if (!val || val <= 0) return 10;
        const p = Math.pow(10, Math.floor(Math.log10(val)));
        return Math.ceil(val / p) * p;
    }

    function polylineArea(points, w, h, pad) {
        if (!points.length) return '';
        const max = niceMax(Math.max.apply(null, points.map(function (p) { return p.v; })));
        const step = points.length > 1 ? (w - pad * 2) / (points.length - 1) : 0;
        const coords = points.map(function (p, i) {
            const x = pad + i * step;
            const y = h - pad - (p.v / max) * (h - pad * 2);
            return x + ',' + y;
        });
        const base = (h - pad) + ' ' + pad + ',' + (h - pad);
        return coords.join(' ') + ' ' + base;
    }

    function renderAreaChart(container, opts) {
        if (!container) return;
        const points = (opts && opts.points) || [];
        const w = (opts && opts.width) || 400;
        const h = (opts && opts.height) || 120;
        const pad = 8;
        const color = (opts && opts.color) || '#a2ff00';
        const title = (opts && opts.title) || '';
        const subtitle = (opts && opts.subtitle) || '';
        const coords = polylineArea(points, w, h, pad);
        const line = coords.split(' ').slice(0, points.length).join(' ');
        const gradId = 'cc-grad-' + Math.random().toString(36).slice(2, 9);
        container.innerHTML =
            '<div class="cc-chart-head">' +
            (title ? '<span class="cc-chart-title">' + esc(title) + '</span>' : '') +
            (subtitle ? '<span class="cc-chart-sub">' + esc(subtitle) + '</span>' : '') +
            '</div>' +
            '<svg class="cc-chart-svg" viewBox="0 0 ' + w + ' ' + h + '" preserveAspectRatio="none" role="img" aria-label="' + esc(title) + '">' +
            '<defs><linearGradient id="' + gradId + '" x1="0" y1="0" x2="0" y2="1">' +
            '<stop offset="0%" stop-color="' + color + '" stop-opacity="0.35"/>' +
            '<stop offset="100%" stop-color="' + color + '" stop-opacity="0.02"/>' +
            '</linearGradient></defs>' +
            '<polygon fill="url(#' + gradId + ')" points="' + coords + '"/>' +
            '<polyline fill="none" stroke="' + color + '" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" points="' + line + '"/>' +
            '</svg>';
    }

    function renderBarChart(container, opts) {
        if (!container) return;
        const items = (opts && opts.items) || [];
        const w = (opts && opts.width) || 400;
        const h = (opts && opts.height) || 140;
        const pad = 12;
        const title = (opts && opts.title) || '';
        const color = (opts && opts.color) || '#5ecf9a';
        const max = niceMax(Math.max.apply(null, items.map(function (i) { return i.value; }).concat([1])));
        const barW = items.length ? (w - pad * 2) / items.length * 0.65 : 20;
        const gap = items.length ? (w - pad * 2) / items.length : 0;
        let bars = '';
        items.forEach(function (item, i) {
            const bh = (item.value / max) * (h - pad * 2 - 18);
            const x = pad + i * gap + (gap - barW) / 2;
            const y = h - pad - 18 - bh;
            bars += '<rect x="' + x + '" y="' + y + '" width="' + barW + '" height="' + bh + '" rx="4" fill="' + color + '" opacity="0.85"/>' +
                '<text x="' + (x + barW / 2) + '" y="' + (h - 4) + '" text-anchor="middle" class="cc-chart-label">' + esc(item.label) + '</text>';
        });
        container.innerHTML =
            '<div class="cc-chart-head"><span class="cc-chart-title">' + esc(title) + '</span></div>' +
            '<svg class="cc-chart-svg" viewBox="0 0 ' + w + ' ' + h + '" role="img" aria-label="' + esc(title) + '">' + bars + '</svg>';
    }

    function renderDonutChart(container, opts) {
        if (!container) return;
        const segments = (opts && opts.segments) || [];
        const size = (opts && opts.size) || 120;
        const title = (opts && opts.title) || '';
        const total = segments.reduce(function (s, seg) { return s + seg.value; }, 0) || 1;
        const r = size / 2 - 10;
        const cx = size / 2;
        const cy = size / 2;
        let angle = -Math.PI / 2;
        let paths = '';
        const colors = ['#a2ff00', '#5ecf9a', '#e8c468', '#d4926e', '#b86a8a', '#6b8cce'];
        segments.forEach(function (seg, i) {
            const slice = (seg.value / total) * Math.PI * 2;
            const x1 = cx + r * Math.cos(angle);
            const y1 = cy + r * Math.sin(angle);
            angle += slice;
            const x2 = cx + r * Math.cos(angle);
            const y2 = cy + r * Math.sin(angle);
            const large = slice > Math.PI ? 1 : 0;
            paths += '<path d="M ' + cx + ' ' + cy + ' L ' + x1 + ' ' + y1 + ' A ' + r + ' ' + r + ' 0 ' + large + ' 1 ' + x2 + ' ' + y2 + ' Z" fill="' + (seg.color || colors[i % colors.length]) + '" opacity="0.9"/>';
        });
        const legend = segments.map(function (seg, i) {
            return '<span class="cc-donut-legend-item"><i style="background:' + (seg.color || colors[i % colors.length]) + '"></i>' + esc(seg.label) + ' <strong>' + seg.value + '</strong></span>';
        }).join('');
        container.innerHTML =
            '<div class="cc-chart-head"><span class="cc-chart-title">' + esc(title) + '</span></div>' +
            '<div class="cc-donut-wrap">' +
            '<svg width="' + size + '" height="' + size + '" viewBox="0 0 ' + size + ' ' + size + '">' + paths +
            '<circle cx="' + cx + '" cy="' + cy + '" r="' + (r * 0.58) + '" fill="#0c0d12"/>' +
            '<text x="' + cx + '" y="' + (cy + 5) + '" text-anchor="middle" class="cc-donut-center">' + total + '</text></svg>' +
            '<div class="cc-donut-legend">' + legend + '</div></div>';
    }

    function renderNetworkMap(container, nodes) {
        if (!container) return;
        const list = Array.isArray(nodes) ? nodes : [];
        const w = 360;
        const h = 200;
        const pad = 24;
        const max = niceMax(Math.max.apply(null, list.map(function (n) { return n.count; }).concat([1])));
        let circles = '';
        const cols = Math.ceil(Math.sqrt(list.length)) || 1;
        list.forEach(function (node, i) {
            const col = i % cols;
            const row = Math.floor(i / cols);
            const cellW = (w - pad * 2) / cols;
            const cellH = (h - pad * 2) / Math.ceil(list.length / cols);
            const cx = pad + col * cellW + cellW / 2;
            const cy = pad + row * cellH + cellH / 2;
            const r = 8 + (node.count / max) * 22;
            const opacity = 0.35 + (node.count / max) * 0.55;
            circles += '<circle cx="' + cx + '" cy="' + cy + '" r="' + r + '" fill="#a2ff00" fill-opacity="' + opacity + '" class="cc-network-node" data-cp="' + esc(node.cp) + '"/>' +
                '<text x="' + cx + '" y="' + (cy + r + 12) + '" text-anchor="middle" class="cc-network-label">' + esc(node.cp) + '</text>';
        });
        container.innerHTML =
            '<div class="cc-chart-head"><span class="cc-chart-title">Mapa de la red por CP</span>' +
            '<span class="cc-chart-sub">Tamaño = aliados activos</span></div>' +
            '<svg class="cc-chart-svg cc-network-svg" viewBox="0 0 ' + w + ' ' + h + '" role="img" aria-label="Mapa de red">' + circles + '</svg>';
    }

    function renderSparkline(container, values, color) {
        if (!container || !values || !values.length) return;
        const points = values.map(function (v, i) { return { v: v, label: String(i) }; });
        renderAreaChart(container, { points: points, width: 80, height: 28, color: color || '#a2ff00', title: '' });
        const head = container.querySelector('.cc-chart-head');
        if (head) head.remove();
    }

    global.RuanaAdminCharts = {
        renderAreaChart: renderAreaChart,
        renderBarChart: renderBarChart,
        renderDonutChart: renderDonutChart,
        renderNetworkMap: renderNetworkMap,
        renderSparkline: renderSparkline
    };
})(typeof window !== 'undefined' ? window : globalThis);
