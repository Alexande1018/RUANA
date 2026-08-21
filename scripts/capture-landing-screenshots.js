/**
 * Captura screenshots premium consistentes para landing RUANA.
 * Requiere servidor activo + manifest de seed-landing-demo.js
 */
const { chromium } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

const BASE_URL = process.env.RUANA_BASE_URL || 'http://127.0.0.1:5000';
const MANIFEST_PATH =
  process.env.RUANA_LANDING_MANIFEST || '/opt/cursor/artifacts/landing-demo-manifest.json';
const OUT_DIR = process.env.RUANA_SCREENSHOTS_DIR || '/opt/cursor/artifacts/screenshots/landing';

const VIEWPORT = { width: 1440, height: 960 };
const DEVICE_SCALE = 2;

const HIDE_UI = `
  #btn-logout,
  #ruana-help-fab,
  .ruana-help-fab,
  .admin-debug-banner,
  #cron-status-wrap,
  #stripe-admin-wrap,
  #detail-codigo,
  .detail-item:has(#detail-codigo),
  .inicio-identity-meta .detail-value,
  #neg-stripe-aviso,
  .ruana-toast-container { display: none !important; }
`;

async function waitStable(page, ms = 500) {
  await page.waitForLoadState('networkidle').catch(() => {});
  await page.evaluate(async () => {
    if (document.fonts && document.fonts.ready) await document.fonts.ready;
  });
  await page.waitForTimeout(ms);
}

async function injectCleanStyles(page) {
  await page.addStyleTag({ content: HIDE_UI });
}

async function polishDemoCopy(page) {
  await page.evaluate(() => {
    document.querySelectorAll('.ruana-toast').forEach((el) => el.remove());
    document.body.innerHTML = document.body.innerHTML
      .replace(/Contrincante:\s*\d+/g, 'Contrincante: Roberto López')
      .replace(/Servicio QA integral/g, 'Reforma eléctrica integral');
  });
}

async function setAliadoSession(page, sessionId) {
  await page.goto('/');
  await page.evaluate((sid) => {
    sessionStorage.setItem('ruana_session_id', sid);
  }, sessionId);
}

async function goAliadoModule(page, moduleName) {
  await page.evaluate((mod) => {
    if (window.AliadoShell && typeof window.AliadoShell.show === 'function') {
      window.AliadoShell.show(mod);
      return;
    }
    const desktop = document.querySelector(`.aliado-shell-nav [data-aliado-nav="${mod}"]`);
    const mobile = document.querySelector(`.aliado-shell-bottom [data-aliado-nav="${mod}"]`);
    (desktop || mobile)?.click();
  }, moduleName);
  await page.locator(`.aliado-module[data-aliado-module="${moduleName}"]`).waitFor({
    state: 'visible',
    timeout: 15000,
  });
}

async function goAdminSection(page, selector) {
  await page.waitForFunction(
    () => window.AdminShell && typeof window.AdminShell.navigateTo === 'function',
    null,
    { timeout: 20000 }
  );
  await page.evaluate((sel) => window.AdminShell.navigateTo(sel), selector);
  await page.locator(selector).first().waitFor({ state: 'visible', timeout: 20000 });
}

async function loginAdmin(page, code, password) {
  await page.goto('/admin');
  await page.evaluate(() => sessionStorage.removeItem('admin_session_id'));
  await page.reload();
  await page.locator('#adminLoginCodigo').fill(code);
  await page.locator('#adminLoginPassword').fill(password);
  await page.locator('#adminLoginBtn').click();
  await page.locator('#adminLoginModal').waitFor({ state: 'hidden', timeout: 20000 });
  await page.locator('body').waitFor({ state: 'attached' });
  await page.waitForFunction(
    () => !document.body.classList.contains('admin-is-loading'),
    null,
    { timeout: 30000 }
  );
}

async function capture(page, name, opts = {}) {
  const file = path.join(OUT_DIR, name);
  await waitStable(page, opts.delay || 700);
  await page.screenshot({
    path: file,
    fullPage: Boolean(opts.fullPage),
    animations: 'disabled',
  });
  console.log('saved', file);
}

async function main() {
  if (!fs.existsSync(MANIFEST_PATH)) {
    throw new Error(`Manifest no encontrado: ${MANIFEST_PATH}. Ejecuta seed-landing-demo.js primero.`);
  }
  const manifest = JSON.parse(fs.readFileSync(MANIFEST_PATH, 'utf8'));
  fs.mkdirSync(OUT_DIR, { recursive: true });

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    baseURL: BASE_URL,
    viewport: VIEWPORT,
    deviceScaleFactor: DEVICE_SCALE,
    locale: 'es-ES',
    timezoneId: 'Europe/Madrid',
    colorScheme: 'dark',
  });
  const page = await context.newPage();
  await injectCleanStyles(page);

  // 1. Dashboard principal del aliado
  await setAliadoSession(page, manifest.hero.sessionId);
  await page.goto('/aliado#inicio');
  await page.locator('#metric-score').waitFor({ state: 'visible', timeout: 20000 });
  await polishDemoCopy(page);
  await capture(page, '01-dashboard-aliado.png');

  // 2. Panel de administración
  await loginAdmin(page, manifest.admin.code, manifest.admin.password);
  await goAdminSection(page, '#command-center-wrap');
  await capture(page, '02-panel-admin.png');

  // 3. Flujo de negociación guiada
  await setAliadoSession(page, manifest.hero.sessionId);
  await page.goto('/aliado#inicio');
  await page.locator('#contacto-aviso-persistente').waitFor({ state: 'visible', timeout: 20000 });
  await page.locator('#btn-contacto-abrir-negociacion').click();
  await page.locator('#modal-negociacion-guiada.show').waitFor({ state: 'visible', timeout: 15000 });
  await page.addStyleTag({
    content: `
      #modal-negociacion-guiada.show .neg-modal-content {
        max-width: 92vw;
        margin: 24px auto;
      }
    `,
  });
  await polishDemoCopy(page);
  await capture(page, '03-negociacion-guiada.png');

  // 4. Grupos / CP / plazas
  await loginAdmin(page, manifest.admin.code, manifest.admin.password);
  await goAdminSection(page, '#grupos-cp-wrap');
  await page.locator('#grupos-cp-wrap table, #grupos-cp-wrap .grupos-cp-grid').first().waitFor({
    state: 'visible',
    timeout: 20000,
  }).catch(() => {});
  await capture(page, '04-grupos-cp-plazas.png', { fullPage: true });

  // 5. Score / estado operativo
  await goAdminSection(page, '#scores-evaluaciones-wrap');
  await capture(page, '05-score-operativo.png', { fullPage: true });

  // 6. Pagos / apoyo / revisión admin
  await goAdminSection(page, '#pagos-apoyo-wrap');
  await page.locator('#pagos-apoyo-wrap').waitFor({ state: 'visible', timeout: 20000 });
  await capture(page, '06-pagos-apoyo-revision.png');

  // 7. Directorio / red de aliados
  await setAliadoSession(page, manifest.hero.sessionId);
  await page.goto('/aliado#directorio');
  await goAliadoModule(page, 'directorio');
  await page.locator('#profesionales-list .profesional-card, #profesionales-list .preview-card').first()
    .waitFor({ state: 'visible', timeout: 20000 })
    .catch(async () => {
      await page.locator('#profesionales-list').waitFor({ state: 'visible', timeout: 10000 });
    });
  await capture(page, '07-directorio-red.png');

  // 8. Perfil del aliado
  await goAliadoModule(page, 'perfil');
  await page.locator('#perfil-nombre, .perfil-nombre').first().waitFor({ state: 'visible', timeout: 15000 });
  await polishDemoCopy(page);
  await capture(page, '08-perfil-aliado.png');

  // 9. Notificaciones (centro de avisos)
  await setAliadoSession(page, manifest.professionalPago.sessionId);
  await page.goto('/aliado#inicio');
  await page.locator('#ruana-alert-hub').waitFor({ state: 'visible', timeout: 20000 });
  await polishDemoCopy(page);
  const moreBtn = page.locator('.ruana-alert-hub__more');
  if (await moreBtn.isVisible().catch(() => false)) {
    await moreBtn.click();
  }
  const actionBtn = page.locator('[data-alert-action]').first();
  if (await actionBtn.isVisible().catch(() => false)) {
    await actionBtn.click();
    await page.locator('.ruana-alert-hub__detail:not([hidden])').waitFor({
      state: 'visible',
      timeout: 10000,
    }).catch(() => {});
  }
  await capture(page, '09-notificaciones.png');

  // 10. Competencia / suplencia
  await loginAdmin(page, manifest.admin.code, manifest.admin.password);
  await goAdminSection(page, '#competencias-activas-wrap');
  await capture(page, '10-competencia-suplencia.png', { fullPage: true });

  await browser.close();
  console.log('Capturas completadas en', OUT_DIR);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
