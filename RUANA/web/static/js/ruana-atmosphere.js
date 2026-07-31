/**
 * RUANA — Red viva de fondo: nodos conectados + movimiento ligero
 */
(function (global) {
    'use strict';

    if (global.matchMedia && global.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

    var isMobile = global.matchMedia && global.matchMedia('(max-width: 640px)').matches;
    var COUNT = isMobile ? 16 : 26;
    var LINK = isMobile ? 110 : 155;
    var DRIFT = isMobile ? 0.16 : 0.22;
    var canvas, ctx, nodes, w, h, raf, tick = 0;

    function rand(a, b) { return a + Math.random() * (b - a); }

    function bootNodes() {
        nodes = [];
        for (var i = 0; i < COUNT; i++) {
            nodes.push({
                x: rand(0, w),
                y: rand(0, h),
                vx: rand(-DRIFT, DRIFT),
                vy: rand(-DRIFT, DRIFT),
                r: rand(1.4, 2.6),
                pulse: rand(0, Math.PI * 2),
                pulseSpeed: rand(0.008, 0.018)
            });
        }
    }

    function resize() {
        w = global.innerWidth;
        h = global.innerHeight;
        if (!canvas) return;
        canvas.width = w;
        canvas.height = h;
        if (!nodes || nodes.length !== COUNT) bootNodes();
    }

    function drawNode(n, alpha) {
        var glow = 0.35 + Math.sin(n.pulse) * 0.25;
        var r = n.r * (0.92 + Math.sin(n.pulse) * 0.08);

        ctx.beginPath();
        ctx.fillStyle = 'rgba(184, 232, 106, ' + (alpha * glow * 0.35) + ')';
        ctx.arc(n.x, n.y, r * 3.2, 0, Math.PI * 2);
        ctx.fill();

        ctx.beginPath();
        ctx.fillStyle = 'rgba(63, 159, 110, ' + (alpha * glow * 0.55) + ')';
        ctx.arc(n.x, n.y, r, 0, Math.PI * 2);
        ctx.fill();

        ctx.beginPath();
        ctx.fillStyle = 'rgba(220, 248, 200, ' + (alpha * glow * 0.7) + ')';
        ctx.arc(n.x, n.y, r * 0.45, 0, Math.PI * 2);
        ctx.fill();
    }

    function frame() {
        tick += 1;
        ctx.clearRect(0, 0, w, h);

        var waveX = Math.sin(tick * 0.004) * 6;
        var waveY = Math.cos(tick * 0.003) * 5;

        for (var i = 0; i < nodes.length; i++) {
            var n = nodes[i];
            n.x += n.vx + waveX * 0.02;
            n.y += n.vy + waveY * 0.02;
            n.pulse += n.pulseSpeed;

            if (n.x < -40) n.x = w + 40;
            if (n.x > w + 40) n.x = -40;
            if (n.y < -40) n.y = h + 40;
            if (n.y > h + 40) n.y = -40;
        }

        var lineAlphaMax = isMobile ? 0.14 : 0.2;

        for (var a = 0; a < nodes.length; a++) {
            for (var b = a + 1; b < nodes.length; b++) {
                var dx = nodes[a].x - nodes[b].x;
                var dy = nodes[a].y - nodes[b].y;
                var d = Math.sqrt(dx * dx + dy * dy);
                if (d < LINK) {
                    var t = 1 - d / LINK;
                    var al = t * t * lineAlphaMax;
                    ctx.beginPath();
                    ctx.strokeStyle = 'rgba(184, 232, 106, ' + al + ')';
                    ctx.lineWidth = 0.6 + t * 0.5;
                    ctx.moveTo(nodes[a].x, nodes[a].y);
                    ctx.lineTo(nodes[b].x, nodes[b].y);
                    ctx.stroke();
                }
            }
        }

        for (var j = 0; j < nodes.length; j++) {
            drawNode(nodes[j], 1);
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
