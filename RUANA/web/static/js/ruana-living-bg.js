/**
 * RUANA — Fondo vivo: red de nodos conectados
 * Movimiento extremadamente ligero. Solo capa visual.
 */
(function (global) {
    'use strict';

    var prefersReduced = global.matchMedia && global.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (prefersReduced) return;

    var NODE_COUNT = 28;
    var CONNECT_DIST = 140;
    var DRIFT = 0.18;
    var canvas, ctx, nodes, w, h, rafId;

    function rand(min, max) {
        return min + Math.random() * (max - min);
    }

    function createNodes() {
        nodes = [];
        for (var i = 0; i < NODE_COUNT; i++) {
            nodes.push({
                x: rand(0, w),
                y: rand(0, h),
                vx: rand(-DRIFT, DRIFT),
                vy: rand(-DRIFT, DRIFT),
                r: rand(1.2, 2.4),
                pulse: rand(0, Math.PI * 2)
            });
        }
    }

    function resize() {
        w = global.innerWidth;
        h = global.innerHeight;
        if (!canvas) return;
        canvas.width = w;
        canvas.height = h;
        if (!nodes || nodes.length === 0) createNodes();
    }

    function step() {
        ctx.clearRect(0, 0, w, h);

        for (var i = 0; i < nodes.length; i++) {
            var n = nodes[i];
            n.x += n.vx;
            n.y += n.vy;
            n.pulse += 0.012;

            if (n.x < -20) n.x = w + 20;
            if (n.x > w + 20) n.x = -20;
            if (n.y < -20) n.y = h + 20;
            if (n.y > h + 20) n.y = -20;
        }

        for (var a = 0; a < nodes.length; a++) {
            for (var b = a + 1; b < nodes.length; b++) {
                var dx = nodes[a].x - nodes[b].x;
                var dy = nodes[a].y - nodes[b].y;
                var dist = Math.sqrt(dx * dx + dy * dy);
                if (dist < CONNECT_DIST) {
                    var alpha = (1 - dist / CONNECT_DIST) * 0.14;
                    ctx.beginPath();
                    ctx.strokeStyle = 'rgba(156, 200, 122, ' + alpha + ')';
                    ctx.lineWidth = 0.6;
                    ctx.moveTo(nodes[a].x, nodes[a].y);
                    ctx.lineTo(nodes[b].x, nodes[b].y);
                    ctx.stroke();
                }
            }
        }

        for (var j = 0; j < nodes.length; j++) {
            var node = nodes[j];
            var glow = 0.35 + Math.sin(node.pulse) * 0.15;
            ctx.beginPath();
            ctx.fillStyle = 'rgba(74, 155, 114, ' + glow + ')';
            ctx.arc(node.x, node.y, node.r, 0, Math.PI * 2);
            ctx.fill();
        }

        rafId = global.requestAnimationFrame(step);
    }

    function init() {
        if (document.querySelector('.ruana-living-bg')) return;

        canvas = document.createElement('canvas');
        canvas.className = 'ruana-living-bg';
        canvas.setAttribute('aria-hidden', 'true');
        document.body.insertBefore(canvas, document.body.firstChild);
        ctx = canvas.getContext('2d');
        resize();
        global.addEventListener('resize', resize);
        step();
    }

    function destroy() {
        if (rafId) global.cancelAnimationFrame(rafId);
        if (canvas && canvas.parentNode) canvas.parentNode.removeChild(canvas);
        global.removeEventListener('resize', resize);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    global.RuanaLivingBg = { init: init, destroy: destroy };
})(typeof window !== 'undefined' ? window : globalThis);
