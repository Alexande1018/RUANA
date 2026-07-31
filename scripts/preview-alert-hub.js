const { chromium } = require('@playwright/test');
const path = require('path');
const fs = require('fs');

const OUT = '/opt/cursor/artifacts/screenshots';
const HTML = `<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>RUANA Alert Hub Preview</title>
  <link rel="stylesheet" href="/static/css/styles.css">
  <link rel="stylesheet" href="/static/css/ruana-feedback.css">
  <link rel="stylesheet" href="/static/css/ruana-alert-hub.css">
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    body { background: #07090f; padding: 32px; font-family: 'Plus Jakarta Sans', sans-serif; max-width: 720px; margin: 0 auto; }
    h1 { color: #f8fafc; font-size: 1.1rem; margin-bottom: 24px; font-weight: 600; }
    .section { margin-bottom: 32px; }
    .section h2 { color: #6b7280; font-size: 0.72rem; letter-spacing: 0.1em; text-transform: uppercase; margin-bottom: 12px; }
  </style>
</head>
<body>
  <h1>Hub de alertas compactas — Apoyo RUANA, pagos, mensajes</h1>
  <div class="section" id="preview-collapsed"></div>
  <div class="section" id="preview-expanded"></div>
  <div class="section" id="preview-detail"></div>
  <script src="/static/js/ruana-alert-hub.js"></script>
  <script>
    const items = [
      { id: 'apoyo-pago', type: 'payment', priority: 100, title: 'Apoyo RUANA (12%) pendiente', description: 'Fontanería · 24,50 €', actionLabel: 'Gestionar', hasDetail: true },
      { id: 'mensajes-ruana', type: 'message', priority: 90, title: '2 mensajes de RUANA', description: 'Comunicaciones sin leer del equipo RUANA', actionLabel: 'Ver', hasDetail: true },
      { id: 'pagos-restriccion', type: 'info', priority: 70, title: 'Nuevos trabajos limitados', description: 'Regulariza tus pagos para aceptar encargos', actionLabel: null, hasDetail: false }
    ];

    function mount(targetId, state, label) {
      const wrap = document.createElement('div');
      wrap.innerHTML = '<h2>' + label + '</h2>';
      const hub = document.createElement('div');
      hub.className = 'ruana-alert-hub';
      hub.innerHTML = '<div class="ruana-alert-hub__cards"></div><button type="button" class="ruana-alert-hub__more" hidden></button><div class="ruana-alert-hub__detail" hidden></div>';
      wrap.appendChild(hub);
      document.getElementById(targetId).appendChild(wrap);
      RuanaAlertHub.render(hub, items, state, {
        onAction: function(item) { if (item.hasDetail) state.expandedDetailId = item.id; RuanaAlertHub.render(hub, items, state, arguments.callee._cb); },
        onShowAll: function() { state.showAll = true; RuanaAlertHub.render(hub, items, state, arguments.callee._cb); },
        renderDetail: function(el, id) {
          const body = RuanaAlertHub.renderDetailHeader(el, 'Apoyo RUANA pendiente', () => { state.expandedDetailId = null; RuanaAlertHub.render(hub, items, state, arguments.callee._cb); });
          body.innerHTML += '<div class="ruana-alert-detail-item"><div class="ruana-alert-detail-item__text">Contacto <strong>#42</strong> · Fontanería · Apoyo: <strong>24,50 €</strong></div><div class="ruana-alert-detail-item__actions"><button class="ruana-alert-detail-btn ruana-alert-detail-btn--primary">Aceptar y pagar</button><button class="ruana-alert-detail-btn">Comprobante</button></div></div>';
        }
      });
    }

    mount('preview-collapsed', { showAll: false, expandedDetailId: null }, 'Colapsado (prioridad)');
    mount('preview-expanded', { showAll: true, expandedDetailId: null }, 'Todos visibles');
    mount('preview-detail', { showAll: true, expandedDetailId: 'apoyo-pago' }, 'Detalle expandido');
  </script>
</body>
</html>`;

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  fs.writeFileSync('/workspace/RUANA/web/alert-hub-preview.html', HTML);
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 760, height: 1400 } });
  await page.goto('http://127.0.0.1:8765/alert-hub-preview.html', { waitUntil: 'networkidle' });
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(OUT, 'alert-hub-compact.png'), fullPage: true });
  console.log('saved alert-hub-compact.png');
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
