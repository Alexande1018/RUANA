/**
 * RUANA — Atmósfera v2: red viva ultra sutil
 * Nodos + hilos apenas perceptibles. Sin canvas pesado en móvil.
 */
(function (global) {
    'use strict';

    if (global.matchMedia && global.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    if (global.matchMedia && global.matchMedia('(max-width: 640px)').matches) return;

    var COUNT = 14;
    var LINK = 120;
    var DRIFT = 0.12;
    var canvas, ctx, nodes, w, h, raf;

    function rand(a, b) { return a + Math.random() * (b - a); }

    function bootNodes() {
        nodes = [];
        for (var i = 0; i < COUNT; i++) {
            nodes.push({
                x: rand(0, w),
                y: rand(0, h),
                vx: rand(-DRIFT, DRIFT),
                vy: rand(-DRIFT, DRIFT),
                r: rand(1, 1.8)
            });
        }
    }

    function resize() {
        w = global.innerWidth;
        h = global.innerHeight;
        if (!canvas) return;
        canvas.width = w;
        canvas.height = h;
        if (!nodes) bootNodes();
    }

    function frame() {
        ctx.clearRect(0, 0, w, h);
        for (var i = 0; i < nodes.length; i++) {
            var n = nodes[i];
            n.x += n.vx;
            n.y += n.vy;
            if (n.x < -30) n.x = w + 30;
            if (n.x > w + 30) n.x = -30;
            if (n.y < -30) n.y = h + 30;
            if (n.y > h + 30) n.y = -30;
        }
        for (var a = 0; a < nodes.length; a++) {
            for (var b = a + 1; b < nodes.length; b++) {
                var dx = nodes[a].x - nodes[b].x;
                var dy = nodes[a].y - nodes[b].y;
                var d = Math.sqrt(dx * dx + dy * dy);
                if (d < LINK) {
                    var al = (1 - d / LINK) * 0.07;
                    ctx.beginPath();
                    ctx.strokeStyle = 'rgba(184, 232, 106, ' + al + ')';
                    ctx.lineWidth = 0.5;
                    ctx.moveTo(nodes[a].x, nodes[a].y);
                    ctx.lineTo(nodes[b].x, nodes[b].y);
                    ctx.stroke();
                }
            }
        }
        for (var j = 0; j < nodes.length; j++) {
            ctx.beginPath();
            ctx.fillStyle = 'rgba(63, 159, 110, 0.28)';
            ctx.arc(nodes[j].x, nodes[j].y, nodes[j].r, 0, Math.PI * 2);
            ctx.fill();
        }
        raf = global.requestAnimationFrame(frame);
    }

    function init() {
        if (document.querySelector('.ruana-atmosphere')) return;
        canvas = document.createElement('canvas');
        canvas.className = 'ruana-atmosphere';
        canvas.setAttribute('aria-hidden', 'true');
        document.body.insertBefore(canvas, document.body.firstChild);
        ctx = canvas.getContext('2d');
        resize();
        global.addEventListener('resize', resize);
        frame();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})(typeof window !== 'undefined' ? window : globalThis);
