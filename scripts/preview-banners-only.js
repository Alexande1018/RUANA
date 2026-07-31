const { chromium } = require('@playwright/test');
const path = require('path');
const fs = require('fs');

const OUT = '/opt/cursor/artifacts/screenshots';
const BASE = 'http://127.0.0.1:8765/feedback-preview.html';

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 900, height: 1200 } });
  await page.goto(BASE, { waitUntil: 'networkidle' });
  await page.waitForTimeout(600);

  // Ocultar toast de bienvenida si existe
  await page.evaluate(() => {
    document.querySelectorAll('.ruana-toast').forEach((el) => el.remove());
  });

  const sectionBanners = page.locator('#section-banners');
  await sectionBanners.scrollIntoViewIfNeeded();
  await page.waitForTimeout(300);
  await sectionBanners.screenshot({ path: path.join(OUT, 'banners-informativos.png') });
  console.log('saved banners-informativos.png');

  const sectionWarnings = page.locator('#section-warnings');
  await sectionWarnings.scrollIntoViewIfNeeded();
  await page.waitForTimeout(300);
  await sectionWarnings.screenshot({ path: path.join(OUT, 'banners-advertencias.png') });
  console.log('saved banners-advertencias.png');

  // Banners estilo panel aliado (warning + error)
  await page.setContent(`
    <!DOCTYPE html>
    <html lang="es">
    <head>
      <link rel="stylesheet" href="/static/css/styles.css">
      <link rel="stylesheet" href="/static/css/ruana-feedback.css">
      <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
      <style>
        body { background: #07090f; padding: 32px; font-family: 'Plus Jakarta Sans', sans-serif; }
        .stack { display: grid; gap: 16px; max-width: 720px; }
        h2 { color: #9ca3af; font-size: 0.75rem; letter-spacing: 0.1em; margin-bottom: 16px; }
      </style>
    </head>
    <body>
      <h2>PANEL ALIADO — ALERTAS SUPERIORES</h2>
      <div class="stack">
        <div id="banner-mensaje-nuevo-ruana" class="ruana-feedback ruana-feedback--banner ruana-feedback--warning" style="display:flex;">
          <span class="ruana-feedback__icon" aria-hidden="true"><svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg></span>
          <div class="ruana-feedback__content">
            <div class="ruana-feedback__title">Mensaje nuevo de RUANA</div>
            <div class="ruana-feedback__message">Tienes un mensaje nuevo pendiente de revisar.</div>
          </div>
        </div>
        <div id="aviso-pagos-pendientes-banner" class="ruana-feedback ruana-feedback--banner ruana-feedback--warning" style="display:flex;">
          <span class="ruana-feedback__icon" aria-hidden="true"><svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg></span>
          <div class="ruana-feedback__content">
            <div class="ruana-feedback__title">Pagos pendientes</div>
            <div class="ruana-feedback__message">Tienes pagos pendientes con RUANA. No podrás aceptar nuevos trabajos hasta regularizar la situación.</div>
          </div>
        </div>
        <div id="error-bootstrap" class="ruana-feedback ruana-feedback--banner ruana-feedback--error" style="display:flex;" role="alert">
          <span class="ruana-feedback__icon" aria-hidden="true"><svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg></span>
          <div class="ruana-feedback__content">
            <div class="ruana-feedback__title">No pudimos cargar tu panel</div>
            <div class="ruana-feedback__message">No se pudieron cargar tus datos. Intenta de nuevo desde el inicio.</div>
          </div>
        </div>
      </div>
    </body>
    </html>
  `, { waitUntil: 'networkidle' });
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(OUT, 'banners-panel-aliado.png'), fullPage: true });
  console.log('saved banners-panel-aliado.png');

  const mobile = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await mobile.setContent(await page.content(), { waitUntil: 'networkidle' });
  await mobile.waitForTimeout(400);
  await mobile.screenshot({ path: path.join(OUT, 'banners-panel-aliado-mobile.png'), fullPage: true });
  console.log('saved banners-panel-aliado-mobile.png');

  await browser.close();
  console.log('done');
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
