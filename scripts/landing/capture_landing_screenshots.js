#!/usr/bin/env node
/**
 * Capturas corporativas de RUANA con viewport, zoom y marco de navegador idénticos.
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '../..');
const OUT = path.join(ROOT, 'docs/exports/landing-screenshots');
const RAW = path.join(OUT, 'raw');
const STATE_PATH = path.join(__dirname, '.demo-state.json');
const BASE = process.env.RUANA_BASE_URL || 'http://127.0.0.1:5000';

const VIEWPORT = { width: 1440, height: 900 };
const SCALE = 2;
const FRAME = {
  pad: 56,
  bar: 52,
  radius: 18,
};

const SHARED_CSS = `
  * { cursor: none !important; }
  html, body { scrollbar-width: none !important; }
  ::-webkit-scrollbar { width: 0 !important; height: 0 !important; display: none !important; }
  #panel-loading, .panel-loading-state, .ruana-page-loader { display: none !important; }
  body.panel-loading .aliado-shell-nav,
  body.panel-loading .panel-container > :not(#error-bootstrap):not(#panel-loading) {
    display: flex !important;
  }
  .ruana-legal-nav-inline,
  .ruana-legal-footer,
  #admin-change-password-btn,
  .perfil-seguridad-wrap,
  .perfil-mis-datos-wrap,
  #stripe-onboarding-banner,
  .stripe-onboarding-banner,
  #stripe-perfil-section,
  #stripe-admin-wrap,
  #cron-status-wrap,
  .cron-status-grid,
  .ruana-score-callout,
  #sol-sem-minimized,
  #btn-quitar-foto-perfil,
  .admin-bulk-toolbar,
  .admin-bulk-cell,
  button.admin-bulk-btn {
    display: none !important;
  }
`;

const SHOTS = [
  {
    id: '01-dashboard-aliado',
    title: 'Panel del aliado',
    urlBar: 'app.ruana.es/aliado',
    role: 'aliado',
    css: `
      #ruana-alert-hub,
      #contacto-aviso-persistente,
      #inicio-solicitudes-semanales-wrap,
      .inicio-tasks,
      .aliado-module-subtitle { display: none !important; }
      .panel-container { padding-top: 20px !important; padding-bottom: 28px !important; }
      .aliado-module-header { margin-bottom: 14px !important; }
      html, body { overflow: hidden !important; }
    `,
  },
  {
    id: '02-panel-admin',
    title: 'Command Center',
    urlBar: 'app.ruana.es/admin',
    role: 'admin',
    adminTarget: '#command-center-wrap',
    css: `
      #cc-bottom-feed, .estado-global, .movimiento-sistema, .cc-charts-row { display: none !important; }
      html, body { overflow: hidden !important; }
    `,
  },
  {
    id: '03-negociacion-guiada',
    title: 'Negociación guiada',
    urlBar: 'app.ruana.es/aliado/negociacion',
    role: 'aliado',
    openNegociacion: true,
    css: `
      #ruana-alert-hub { display: none !important; }
    `,
  },
  {
    id: '04-grupos-territorio',
    title: 'Grupos y territorio',
    urlBar: 'app.ruana.es/admin/territorio',
    role: 'admin',
    adminTarget: '#grupos-cp-wrap',
    css: `
      #btn-procesar-grupos-no-viables,
      #aliados-sin-grupo-wrap,
      #grupos-tabla-wrap .admin-subtitle { display: none !important; }
      html, body { overflow: hidden !important; }
    `,
  },
  {
    id: '05-score-operativo',
    title: 'Score operativo',
    urlBar: 'app.ruana.es/admin/score',
    role: 'admin',
    adminTarget: '#scores-evaluaciones-wrap',
    css: `html, body { overflow: hidden !important; }`,
  },
  {
    id: '06-pagos-apoyo',
    title: 'Pagos y Apoyo RUANA',
    urlBar: 'app.ruana.es/admin/pagos',
    role: 'admin',
    adminTarget: '#pagos-en-revision-wrap',
    css: `
      #conflictos-pago-wrap, #stripe-admin-wrap { display: none !important; }
      #pagos-apoyo-wrap .admin-subtitle,
      #pagos-en-revision-wrap .admin-subtitle { max-width: 70ch; }
      html, body { overflow: hidden !important; }
    `,
  },
  {
    id: '07-directorio-red',
    title: 'Directorio de aliados',
    urlBar: 'app.ruana.es/aliado/directorio',
    role: 'aliado',
    aliadoModule: 'directorio',
    css: `
      #ruana-alert-hub, #contacto-aviso-persistente, .aliado-module-subtitle { display: none !important; }
      html, body { overflow: hidden !important; }
    `,
  },
  {
    id: '08-perfil-aliado',
    title: 'Perfil del aliado',
    urlBar: 'app.ruana.es/aliado/perfil',
    role: 'aliado',
    aliadoModule: 'perfil',
    css: `
      #ruana-alert-hub, #contacto-aviso-persistente,
      #mis-acuerdos-wrap, .perfil-mensajes-wrap,
      .perfil-acciones, #btn-invitar-aliado,
      .aliado-module-header { display: none !important; }
      .panel-container { padding-top: 18px !important; }
      html, body { overflow: hidden !important; }
    `,
  },
  {
    id: '09-notificaciones',
    title: 'Centro de avisos',
    urlBar: 'app.ruana.es/aliado/avisos',
    role: 'aliado',
    expandNotificaciones: true,
    css: `
      #contacto-aviso-persistente,
      #module-inicio,
      .inicio-quick-grid,
      .inicio-tasks,
      .metricas-block,
      #inicio-solicitudes-semanales-wrap { display: none !important; }
      html, body { overflow: hidden !important; }
    `,
  },
  {
    id: '10-competencia-suplencia',
    title: 'Competencia y suplencia',
    urlBar: 'app.ruana.es/admin/competencia',
    role: 'admin',
    adminTarget: '#competencias-activas-wrap',
    css: `
      #competencias-pendientes-wrap,
      #competencias-historial-wrap,
      #suplentes-espera-wrap { display: none !important; }
      html, body { overflow: hidden !important; }
    `,
  },
];

function loadState() {
  if (!fs.existsSync(STATE_PATH)) {
    throw new Error(`Falta ${STATE_PATH}. Ejecuta antes seed_landing_demo.py`);
  }
  return JSON.parse(fs.readFileSync(STATE_PATH, 'utf8'));
}

async function apiJson(url, options = {}) {
  const res = await fetch(url, options);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(`${options.method || 'GET'} ${url} -> ${res.status} ${JSON.stringify(body)}`);
  }
  return body;
}

async function loginAliado(codigo, pin) {
  const first = await apiJson(`${BASE}/api/aliado/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ codigo, pin }),
  });
  if (first.session_id) return first.session_id;
  throw new Error(`Login aliado sin sesión: ${JSON.stringify(first)}`);
}

async function loginAdmin(codigo, password) {
  const body = await apiJson(`${BASE}/api/admin/validar`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ codigo, password }),
  });
  if (!body.session_id) throw new Error(`Login admin sin sesión: ${JSON.stringify(body)}`);
  return body.session_id;
}

async function waitReady(page, role) {
  if (role === 'aliado') {
    await page.waitForFunction(() => !document.body.classList.contains('panel-loading'), null, { timeout: 30000 });
    await page.locator('#metric-score').waitFor({ state: 'visible', timeout: 30000 });
    await page.waitForFunction(() => {
      const el = document.getElementById('inicio-nombre');
      return el && el.textContent && !/cargando/i.test(el.textContent);
    }, null, { timeout: 30000 });
  } else {
    await page.waitForFunction(() => !document.body.classList.contains('admin-is-loading'), null, { timeout: 40000 });
    await page.waitForFunction(
      () => window.AdminShell && typeof window.AdminShell.navigateTo === 'function',
      null,
      { timeout: 20000 }
    );
    await page.locator('#command-center-wrap, .admin-module-title').first().waitFor({ state: 'visible', timeout: 20000 });
  }
  await page.evaluate(() => document.fonts && document.fonts.ready);
  await page.waitForTimeout(400);
}

async function applyLook(page, extraCss) {
  await page.addStyleTag({ content: SHARED_CSS + (extraCss || '') });
}

async function polishPage(page, spec) {
  await applyLook(page, spec.css);
  await page.evaluate(() => {
    const fecha = document.getElementById('detail-fecha');
    if (fecha && fecha.closest('.detail-item')) {
      fecha.closest('.detail-item').style.display = 'none';
    }
    document.querySelectorAll('button, a').forEach((el) => {
      const t = (el.textContent || '').trim().toLowerCase();
      if (t === 'eliminar' || t.startsWith('eliminar seleccionados') || t.startsWith('eliminar todos')) {
        el.style.display = 'none';
      }
    });
    document.querySelectorAll('th, td').forEach((el) => {
      const t = (el.textContent || '').trim().toLowerCase();
      if (t === 'eliminar') el.style.display = 'none';
    });
  });
  await page.evaluate(async () => {
    const imgs = Array.from(document.images);
    await Promise.all(imgs.map((img) => {
      if (!img.src || img.hidden) return Promise.resolve();
      if (img.complete && img.naturalWidth) return Promise.resolve();
      return Promise.race([
        img.decode ? img.decode().catch(() => {}) : Promise.resolve(),
        new Promise((resolve) => setTimeout(resolve, 1500)),
      ]);
    }));
  });
  await page.waitForTimeout(200);
}

async function openAliado(page, sessionId, codigo) {
  await page.goto(`${BASE}/`, { waitUntil: 'domcontentloaded' });
  await page.evaluate(({ sessionId, codigo }) => {
    sessionStorage.setItem('ruana_session_id', sessionId);
    sessionStorage.setItem('ruana_codigo_aliado', codigo);
  }, { sessionId, codigo });
  await page.goto(`${BASE}/aliado`, { waitUntil: 'domcontentloaded' });
  await waitReady(page, 'aliado');
}

async function openAdmin(page, sessionId) {
  await page.goto(`${BASE}/`, { waitUntil: 'domcontentloaded' });
  await page.evaluate((sessionId) => {
    sessionStorage.setItem('admin_session_id', sessionId);
  }, sessionId);
  await page.goto(`${BASE}/admin`, { waitUntil: 'domcontentloaded' });
  await waitReady(page, 'admin');
}

async function goAliadoModule(page, name) {
  const nav = page.locator(`.aliado-shell-nav [data-aliado-nav="${name}"]`);
  await nav.click();
  await page.locator(`.aliado-module[data-aliado-module="${name}"]`).waitFor({ state: 'visible' });
  await page.waitForTimeout(350);
}

async function goAdmin(page, selector) {
  await page.evaluate((sel) => window.AdminShell.navigateTo(sel), selector);
  await page.locator(selector).first().waitFor({ state: 'visible', timeout: 20000 });
  await page.waitForTimeout(500);
}

function frameHtml(imgSrc, urlBar) {
  const width = VIEWPORT.width;
  const height = VIEWPORT.height + FRAME.bar;
  const stageW = width + FRAME.pad * 2;
  const stageH = height + FRAME.pad * 2;
  return `<!doctype html>
<html><head><meta charset="utf-8">
<style>
  html, body { margin:0; padding:0; background:#e7e4dc; }
  .stage {
    width:${stageW}px; height:${stageH}px;
    display:flex; align-items:center; justify-content:center;
    background:
      radial-gradient(1200px 600px at 50% -10%, rgba(255,255,255,.65), transparent 60%),
      #e7e4dc;
  }
  .window {
    width:${width}px;
    height:${height}px;
    border-radius:${FRAME.radius}px;
    overflow:hidden;
    box-shadow:
      0 28px 80px rgba(28, 24, 20, .22),
      0 2px 0 rgba(255,255,255,.65) inset;
    background:#111;
    border:1px solid rgba(28,24,20,.12);
  }
  .bar {
    height:${FRAME.bar}px;
    display:flex; align-items:center; gap:14px;
    padding:0 16px;
    background:linear-gradient(180deg,#f7f5f0 0%, #efece5 100%);
    border-bottom:1px solid rgba(28,24,20,.08);
  }
  .dots { display:flex; gap:7px; }
  .dots i { width:11px; height:11px; border-radius:50%; display:block; }
  .dots i:nth-child(1){ background:#e26b5a; }
  .dots i:nth-child(2){ background:#e0b04a; }
  .dots i:nth-child(3){ background:#6cbf6a; }
  .url {
    flex:1; height:28px; border-radius:8px;
    background:#fff; border:1px solid rgba(28,24,20,.08);
    display:flex; align-items:center; justify-content:center;
    font: 500 13px/1 "Plus Jakarta Sans", "Segoe UI", sans-serif;
    color:#4a4741; letter-spacing:.01em;
  }
  img { display:block; width:${width}px; height:${VIEWPORT.height}px; }
</style></head>
<body>
  <div class="stage">
    <div class="window">
      <div class="bar">
        <div class="dots"><i></i><i></i><i></i></div>
        <div class="url">${urlBar}</div>
      </div>
      <img src="${imgSrc}" alt="">
    </div>
  </div>
</body></html>`;
}

async function composeFrame(browser, rawPath, framedPath, urlBar) {
  const b64 = fs.readFileSync(rawPath).toString('base64');
  const html = frameHtml(`data:image/png;base64,${b64}`, urlBar);
  const page = await browser.newPage({
    viewport: {
      width: VIEWPORT.width + FRAME.pad * 2,
      height: VIEWPORT.height + FRAME.bar + FRAME.pad * 2,
    },
    deviceScaleFactor: SCALE,
  });
  await page.setContent(html, { waitUntil: 'load' });
  await page.screenshot({ path: framedPath, type: 'png' });
  await page.close();
}

async function captureShot(page, spec) {
  const rawPath = path.join(RAW, `${spec.id}.png`);
  await polishPage(page, spec);
  if (spec.openNegociacion) {
    const aviso = page.locator('#contacto-aviso-persistente');
    await aviso.waitFor({ state: 'visible', timeout: 20000 });
    await page.locator('#btn-contacto-abrir-negociacion').click();
    await page.locator('#modal-negociacion-guiada').waitFor({ state: 'visible' });
    await page.waitForFunction(() => {
      const el = document.querySelector('#modal-negociacion-guiada');
      return el && el.classList.contains('show');
    });
    await page.locator('#neg-timeline').waitFor({ state: 'visible' });
    await page.waitForTimeout(500);
  }
  if (spec.aliadoModule) {
    await goAliadoModule(page, spec.aliadoModule);
  }
  if (spec.adminTarget) {
    await goAdmin(page, spec.adminTarget);
  }
  if (spec.expandNotificaciones) {
    const hub = page.locator('#ruana-alert-hub');
    await hub.waitFor({ state: 'visible', timeout: 20000 });
    const more = page.locator('#ruana-alert-hub .ruana-alert-hub__more');
    if (await more.isVisible().catch(() => false)) {
      await more.click();
      await page.waitForTimeout(200);
    }
    const ver = page.locator('#ruana-alert-hub [data-alert-action="mensajes-ruana"], #ruana-alert-hub button:has-text("Ver")').first();
    if (await ver.isVisible().catch(() => false)) {
      await ver.click();
      await page.waitForTimeout(400);
    }
  }
  await polishPage(page, spec);
  await page.waitForTimeout(250);
  await page.screenshot({ path: rawPath, type: 'png', animations: 'disabled' });
  return rawPath;
}

async function main() {
  fs.mkdirSync(RAW, { recursive: true });
  const state = loadState();
  const aliadoSid = await loginAliado(state.hero.codigo, state.pin);
  const adminSid = await loginAdmin(state.admin.codigo, state.admin.password);

  const browser = await chromium.launch({
    executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || undefined,
    headless: true,
  });
  const context = await browser.newContext({
    viewport: VIEWPORT,
    deviceScaleFactor: SCALE,
    locale: 'es-ES',
    timezoneId: 'Europe/Madrid',
    colorScheme: 'dark',
  });
  const page = await context.newPage();

  const index = [];
  for (const spec of SHOTS) {
    console.log(`[landing] capturando ${spec.id}…`);
    if (spec.role === 'aliado') {
      await openAliado(page, aliadoSid, state.hero.codigo);
    } else {
      await openAdmin(page, adminSid);
    }
    const rawPath = await captureShot(page, spec);
    const framedPath = path.join(OUT, `${spec.id}.png`);
    await composeFrame(browser, rawPath, framedPath, spec.urlBar);
    index.push({
      id: spec.id,
      title: spec.title,
      file: path.relative(ROOT, framedPath),
      raw: path.relative(ROOT, rawPath),
      urlBar: spec.urlBar,
    });
    console.log(`[landing] ok ${spec.id}`);
  }

  fs.writeFileSync(path.join(OUT, 'manifest.json'), JSON.stringify({
    generated_at: new Date().toISOString(),
    viewport: VIEWPORT,
    deviceScaleFactor: SCALE,
    shots: index,
  }, null, 2));

  await browser.close();
  console.log(`[landing] ${index.length} capturas en ${OUT}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
