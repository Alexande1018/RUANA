const { chromium } = require('@playwright/test');
const path = require('path');
const fs = require('fs');

const OUT = '/opt/cursor/artifacts/screenshots';
const BASE = 'http://127.0.0.1:8765/feedback-preview.html';

async function shot(page, name) {
  const file = path.join(OUT, name);
  await page.waitForTimeout(400);
  await page.screenshot({ path: file, fullPage: false });
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
  await desktop.waitForTimeout(800);
  await shot(desktop, 'feedback-overview-desktop.png');

  await desktop.locator('[data-toast="success"]').click();
  await desktop.waitForTimeout(500);
  await shot(desktop, 'feedback-toast-success.png');

  await desktop.locator('[data-error="send"]').click();
  await desktop.waitForTimeout(500);
  await shot(desktop, 'feedback-error-actions.png');

  await desktop.locator('[data-confirm="danger"]').click();
  await desktop.waitForTimeout(500);
  await shot(desktop, 'feedback-confirm-danger.png');
  await desktop.keyboard.press('Escape');
  await desktop.waitForTimeout(200);

  await desktop.evaluate(() => {
    document.querySelector('.ruana-dialog-overlay .ruana-dialog-cancel')?.click();
  });
  await desktop.waitForTimeout(300);

  await desktop.locator('#section-banners').scrollIntoViewIfNeeded();
  await shot(desktop, 'feedback-banners.png');

  await desktop.locator('#section-loading').scrollIntoViewIfNeeded();
  await shot(desktop, 'feedback-loading-inline.png');

  await desktop.locator('[data-loading="search"]').click();
  await desktop.waitForTimeout(400);
  await shot(desktop, 'feedback-loading-overlay.png');

  const mobile = await browser.newPage({
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
  });
  await mobile.goto(BASE, { waitUntil: 'networkidle' });
  await mobile.waitForTimeout(600);
  await mobile.locator('[data-toast="payment"]').click();
  await mobile.waitForTimeout(500);
  await shot(mobile, 'feedback-mobile-toast.png');

  await browser.close();
  console.log('done');
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
