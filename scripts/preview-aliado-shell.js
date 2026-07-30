const { chromium, devices } = require('playwright-core');
const path = require('path');
const fs = require('fs');

const OUT = '/opt/cursor/artifacts/screenshots';
const BASE = 'http://127.0.0.1:8765/aliado-shell-preview.html';
const MODULES = ['inicio', 'directorio', 'solicitudes', 'conexiones', 'perfil'];

async function shot(page, name) {
  const file = path.join(OUT, name);
  await page.waitForTimeout(350);
  await page.screenshot({ path: file, fullPage: true });
  console.log('saved', file);
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({
    executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || undefined,
    headless: true,
  });

  const desktop = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await desktop.goto(BASE, { waitUntil: 'networkidle' });
  await desktop.waitForTimeout(600);
  await shot(desktop, 'aliado-inicio-desktop.png');
  for (const mod of MODULES.slice(1)) {
    await desktop.locator(`.aliado-shell-nav [data-aliado-nav="${mod}"]`).click();
    await desktop.waitForTimeout(350);
    await shot(desktop, `aliado-${mod}-desktop.png`);
  }

  const iPhone = devices['iPhone 13'];
  const mobile = await browser.newPage({
    viewport: iPhone.viewport,
    userAgent: iPhone.userAgent,
    isMobile: true,
    hasTouch: true,
  });
  await mobile.goto(BASE, { waitUntil: 'networkidle' });
  await mobile.waitForTimeout(600);
  await shot(mobile, 'aliado-inicio-mobile.png');
  for (const mod of ['directorio', 'solicitudes', 'conexiones', 'perfil']) {
    await mobile.locator(`.aliado-shell-bottom [data-aliado-nav="${mod}"]`).click();
    await mobile.waitForTimeout(350);
    await shot(mobile, `aliado-${mod}-mobile.png`);
  }

  await browser.close();
  console.log('done');
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
