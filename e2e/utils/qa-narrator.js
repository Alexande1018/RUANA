const DEFAULT_PAUSE_MS = Number(process.env.RUANA_QA_VIDEO_PAUSE_MS || 1500);
const ACTION_PAUSE_MS = Number(process.env.RUANA_QA_ACTION_PAUSE_MS || 800);

async function ensureNarrator(page, scenario) {
  await page.evaluate((scenarioTitle) => {
    let root = document.getElementById('qa-video-narrator');
    if (!root) {
      root = document.createElement('aside');
      root.id = 'qa-video-narrator';
      root.innerHTML = `
        <div class="qa-video-kicker">QA RUANA - prueba grabada</div>
        <div class="qa-video-scenario"></div>
        <div class="qa-video-status"></div>
        <div class="qa-video-step"></div>
        <div class="qa-video-action"></div>
        <div class="qa-video-expected"></div>
        <div class="qa-video-result"></div>
      `;
      const style = document.createElement('style');
      style.id = 'qa-video-narrator-style';
      style.textContent = `
        #qa-video-narrator {
          position: fixed;
          right: 18px;
          top: 18px;
          z-index: 2147483647;
          width: min(440px, calc(100vw - 36px));
          padding: 16px 18px;
          border: 2px solid #14b8a6;
          border-radius: 8px;
          background: rgba(8, 14, 24, 0.94);
          color: #f8fafc;
          box-shadow: 0 18px 48px rgba(0, 0, 0, 0.45);
          font-family: Arial, Helvetica, sans-serif;
          line-height: 1.35;
          pointer-events: none;
        }
        #qa-video-narrator .qa-video-kicker {
          color: #5eead4;
          font-size: 12px;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.08em;
          margin-bottom: 6px;
        }
        #qa-video-narrator .qa-video-scenario {
          font-size: 16px;
          font-weight: 700;
          margin-bottom: 10px;
        }
        #qa-video-narrator .qa-video-status {
          display: inline-block;
          padding: 4px 8px;
          border-radius: 6px;
          background: #334155;
          color: #f8fafc;
          font-size: 12px;
          font-weight: 700;
          margin-bottom: 10px;
        }
        #qa-video-narrator .qa-video-status[data-status="PASS"] {
          background: #15803d;
        }
        #qa-video-narrator .qa-video-status[data-status="FAIL"] {
          background: #b91c1c;
        }
        #qa-video-narrator .qa-video-step {
          font-size: 18px;
          font-weight: 700;
          margin-bottom: 8px;
        }
        #qa-video-narrator .qa-video-action,
        #qa-video-narrator .qa-video-expected,
        #qa-video-narrator .qa-video-result {
          font-size: 14px;
          margin-top: 7px;
        }
        #qa-video-narrator strong {
          color: #bae6fd;
        }
        #qa-video-cursor {
          position: fixed;
          left: 0;
          top: 0;
          z-index: 2147483647;
          width: 22px;
          height: 22px;
          border: 3px solid #facc15;
          border-radius: 999px;
          background: rgba(250, 204, 21, 0.16);
          box-shadow: 0 0 0 8px rgba(250, 204, 21, 0.14);
          pointer-events: none;
          transform: translate(-80px, -80px);
          transition: transform 240ms ease;
        }
        .qa-video-highlight {
          outline: 3px solid #facc15 !important;
          outline-offset: 4px !important;
          box-shadow: 0 0 0 7px rgba(250, 204, 21, 0.22) !important;
          transition: outline-color 180ms ease, box-shadow 180ms ease !important;
        }
      `;
      document.head.appendChild(style);
      document.body.appendChild(root);
    }
    if (!document.getElementById('qa-video-cursor')) {
      const cursor = document.createElement('div');
      cursor.id = 'qa-video-cursor';
      document.body.appendChild(cursor);
    }
    root.querySelector('.qa-video-scenario').textContent = scenarioTitle || 'Escenario QA';
  }, scenario);
}

async function narrate(page, scenario, entry) {
  await ensureNarrator(page, scenario);
  const status = entry.status || 'EN CURSO';
  const line = `${status} | ${entry.step} | ${entry.action || ''} | ${entry.result || ''}`;
  console.log(`[QA] ${line}`);
  await page.evaluate((payload) => {
    const root = document.getElementById('qa-video-narrator');
    root.querySelector('.qa-video-status').textContent = payload.status;
    root.querySelector('.qa-video-status').dataset.status = payload.status;
    root.querySelector('.qa-video-step').textContent = payload.step || '';
    root.querySelector('.qa-video-action').innerHTML = payload.action
      ? `<strong>Accion:</strong> ${payload.action}`
      : '';
    root.querySelector('.qa-video-expected').innerHTML = payload.expected
      ? `<strong>Esperado:</strong> ${payload.expected}`
      : '';
    root.querySelector('.qa-video-result').innerHTML = payload.result
      ? `<strong>Resultado:</strong> ${payload.result}`
      : '';
  }, { ...entry, status });
  await page.waitForTimeout(entry.pauseMs ?? DEFAULT_PAUSE_MS);
}

async function pass(page, scenario, entry) {
  await narrate(page, scenario, { ...entry, status: 'PASS', pauseMs: entry.pauseMs ?? DEFAULT_PAUSE_MS });
}

async function pointAt(page, locator) {
  await locator.evaluate((element) => {
    element.scrollIntoView({ block: 'center', inline: 'nearest', behavior: 'smooth' });
  });
  await page.waitForTimeout(ACTION_PAUSE_MS);
  const box = await locator.boundingBox();
  if (!box) return;
  await page.evaluate(({ x, y }) => {
    const cursor = document.getElementById('qa-video-cursor');
    if (cursor) cursor.style.transform = `translate(${x}px, ${y}px)`;
  }, {
    x: Math.round(box.x + box.width / 2),
    y: Math.round(box.y + box.height / 2),
  });
  await locator.evaluate((element) => {
    element.classList.add('qa-video-highlight');
    window.setTimeout(() => element.classList.remove('qa-video-highlight'), 1200);
  });
  await page.waitForTimeout(ACTION_PAUSE_MS);
}

async function reveal(page, target, options = {}) {
  const locator = typeof target === 'string' ? page.locator(target).first() : target.first();
  await locator.waitFor({ state: options.state || 'visible', timeout: options.timeout || 12000 });
  await pointAt(page, locator);
  return locator;
}

async function dismissAdminOverlayIfNeeded(page) {
  await page.evaluate(() => {
    const shell = window.AdminShell;
    if (!shell || typeof shell.setSidebarOpen !== 'function') return;
    const sidebar = document.getElementById('adminSidebar');
    const mobile = typeof window.matchMedia === 'function'
      && window.matchMedia('(max-width: 960px)').matches;
    const overlay = !!(sidebar && sidebar.classList.contains('is-mobile-open'));
    if (mobile || overlay) shell.setSidebarOpen(false);
  });
}

async function clickVisible(page, target, options = {}) {
  const locator = await reveal(page, target, options);
  await dismissAdminOverlayIfNeeded(page);
  try {
    await locator.click(options.clickOptions || {});
  } catch (error) {
    const message = String(error && error.message ? error.message : error);
    if (!/intercepts pointer events/i.test(message)) throw error;
    await dismissAdminOverlayIfNeeded(page);
    await locator.evaluate((element) => {
      element.scrollIntoView({ block: 'center', inline: 'nearest' });
    });
    try {
      await locator.click(options.clickOptions || {});
    } catch (retryError) {
      const retryMessage = String(
        retryError && retryError.message ? retryError.message : retryError
      );
      if (!/adminSidebar|intercepts pointer events/i.test(retryMessage)) throw retryError;
      await page.evaluate(() => {
        const sidebar = document.getElementById('adminSidebar');
        if (!sidebar) return;
        sidebar.dataset.qaPrevPe = sidebar.style.pointerEvents || '';
        sidebar.style.pointerEvents = 'none';
      });
      try {
        await locator.click(options.clickOptions || {});
      } finally {
        await page.evaluate(() => {
          const sidebar = document.getElementById('adminSidebar');
          if (!sidebar) return;
          sidebar.style.pointerEvents = sidebar.dataset.qaPrevPe || '';
          delete sidebar.dataset.qaPrevPe;
        });
      }
    }
  }
  await page.waitForTimeout(options.pauseMs ?? ACTION_PAUSE_MS);
  return locator;
}

async function fillVisible(page, target, value, options = {}) {
  const locator = await reveal(page, target, options);
  await locator.fill(value);
  await page.waitForTimeout(options.pauseMs ?? ACTION_PAUSE_MS);
  return locator;
}

async function selectVisible(page, target, value, options = {}) {
  const locator = await reveal(page, target, options);
  await locator.selectOption(value);
  await page.waitForTimeout(options.pauseMs ?? ACTION_PAUSE_MS);
  return locator;
}

async function checkVisible(page, target, options = {}) {
  const locator = await reveal(page, target, { ...options, state: options.state || 'attached' });
  await locator.check(options.checkOptions || {});
  await page.waitForTimeout(options.pauseMs ?? ACTION_PAUSE_MS);
  return locator;
}

async function setInputFilesVisible(page, target, files, options = {}) {
  const locator = await reveal(page, target, { ...options, state: options.state || 'attached' });
  await pointAt(page, locator);
  await locator.setInputFiles(files);
  await page.waitForTimeout(options.pauseMs ?? ACTION_PAUSE_MS);
  return locator;
}

async function reviewSection(page, scenario, target, entry) {
  await narrate(page, scenario, entry);
  await reveal(page, target, { timeout: entry.timeout || 15000 });
  await pass(page, scenario, {
    step: entry.resultStep || `${entry.step} visible`,
    action: entry.resultAction || 'El video muestra la seccion revisada.',
    result: entry.result || 'Seccion localizada y visible en pantalla.',
  });
}

module.exports = {
  checkVisible,
  clickVisible,
  ensureNarrator,
  fillVisible,
  narrate,
  pass,
  reveal,
  reviewSection,
  selectVisible,
  setInputFilesVisible,
  dismissAdminOverlayIfNeeded,
};
