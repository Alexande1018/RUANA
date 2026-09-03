const { test, expect } = require('@playwright/test');
const {
  ADMIN_CODE,
  ADMIN_PASSWORD,
  adminLogin,
  aliadoLogin,
  buildAliadoData,
  createAcceptedContact,
  createCampaign,
  declareImporte,
  expectOk,
  nationalPhoneFromE164,
  proponerNegociacionCompleta,
  registerAliado,
  uniqueId,
} = require('./utils/ruana-fixtures');
const {
  checkVisible,
  clickVisible,
  dismissAdminOverlayIfNeeded,
  fillVisible,
  narrate,
  pass,
  reviewSection,
  selectVisible,
  setInputFilesVisible,
} = require('./utils/qa-narrator');

async function openAliadoPanel(page, session, scenario, label) {
  await test.step(`${label} abre su panel de aliado`, async () => {
    await page.goto('/');
    await page.evaluate((sessionId) => {
      sessionStorage.setItem('ruana_session_id', sessionId);
    }, session.sessionId);
    await page.goto('/aliado');
    await expect(page.locator('#metric-score')).toBeVisible();
    await pass(page, scenario, {
      step: `${label} en panel aliado`,
      action: 'El usuario entra al panel con su sesion real de navegador.',
      result: 'Se abre el modulo Inicio con metricas, score y accesos rapidos.',
    });
  });
}

async function goAliadoModule(page, moduleName) {
  const desktopNav = page.locator(`.aliado-shell-nav [data-aliado-nav="${moduleName}"]`);
  const mobileNav = page.locator(`.aliado-shell-bottom [data-aliado-nav="${moduleName}"]`);
  if (await desktopNav.isVisible().catch(() => false)) {
    await desktopNav.click();
  } else {
    await mobileNav.click();
  }
  await expect(page.locator(`.aliado-module[data-aliado-module="${moduleName}"]`)).toBeVisible();
}

/** Activa el módulo del admin shell que contiene el selector (los demás están display:none). */
async function goAdminSection(page, selector) {
  await page.waitForFunction(
    () => window.AdminShell && typeof window.AdminShell.navigateTo === 'function',
    null,
    { timeout: 15000 }
  );
  await page.evaluate((sel) => {
    window.AdminShell.navigateTo(sel);
  }, selector);
  await expect(page.locator(selector).first()).toBeVisible({ timeout: 15000 });
  await dismissAdminOverlayIfNeeded(page);
}

async function loginAdminAsUser(page, scenario, code = ADMIN_CODE, label = 'admin') {
  const password = code === ADMIN_CODE ? ADMIN_PASSWORD : code;
  await test.step(`Usuario ${label} abre el panel e introduce su codigo`, async () => {
    await page.goto('/');
    await page.evaluate(() => sessionStorage.removeItem('admin_session_id'));
    await page.goto('/admin');
    await narrate(page, scenario, {
      step: 'Abrir panel de administracion',
      action: 'El usuario navega a /admin y ve el formulario de acceso.',
      expected: 'Debe aparecer identificador y contraseña admin.',
    });
    await fillVisible(page, '#adminLoginCodigo', code);
    await fillVisible(page, '#adminLoginPassword', password);
    await narrate(page, scenario, {
      step: 'Introducir credenciales admin',
      action: `Se escribe el codigo ${code}, la contraseña y se pulsa Entrar.`,
      expected: 'RUANA debe conceder acceso al panel segun permisos.',
    });
    await clickVisible(page, '#adminLoginBtn');
    await expect(page.locator('#adminLoginModal')).toHaveClass(/hidden/, { timeout: 15000 });
    await expect(page.locator('body')).not.toHaveClass(/admin-is-loading/, { timeout: 30000 });
    await goAdminSection(page, '#command-center-wrap');
    await pass(page, scenario, {
      step: 'Acceso admin concedido',
      action: 'El panel principal queda visible y termina de cargar.',
      result: 'Login admin correcto; se ven KPIs, registros y secciones de gestion.',
    });
  });
}

async function openNegociacionViaUi(page, scenario, roleLabel = 'Usuario') {
  await test.step(`${roleLabel} abre la negociacion guiada`, async () => {
    await reviewSection(page, scenario, '#contacto-aviso-persistente', {
      step: 'Ver aviso de contacto activo',
      action: `${roleLabel} localiza el seguimiento del encargo en su panel.`,
      expected: 'Debe aparecer la accion Abrir negociacion.',
      result: 'El aviso de contacto queda visible.',
    });
    await clickVisible(page, '#btn-contacto-abrir-negociacion');
    await expect(page.locator('#modal-negociacion-guiada')).toHaveClass(/show/);
    await pass(page, scenario, {
      step: `${roleLabel} abre negociacion`,
      action: `${roleLabel} pulsa Abrir negociacion.`,
      result: 'El modal de negociacion guiada queda visible.',
    });
  });
}

async function closeNegociacionViaUi(page) {
  const panelBtn = page.locator('#neg-btn-cerrar');
  if (await panelBtn.isVisible().catch(() => false)) {
    await panelBtn.click();
  }
  await expect(page.locator('#modal-negociacion-guiada')).not.toHaveClass(/show/);
}

async function verifyNegociacionVisibleViaUi(page, scenario, expectedSnippet, roleLabel) {
  await openNegociacionViaUi(page, scenario, roleLabel);
  await test.step(`${roleLabel} ve la negociacion`, async () => {
    await expect(page.locator('#neg-timeline')).toContainText(expectedSnippet, { timeout: 15000 });
    await pass(page, scenario, {
      step: `${roleLabel} ve propuesta`,
      action: `${roleLabel} revisa el historial de la negociacion.`,
      result: `La negociacion muestra: "${expectedSnippet}".`,
    });
  });
  await closeNegociacionViaUi(page);
}

async function confirmImporteViaUi(
  page,
  request,
  scenario,
  solicitanteSession,
  contactoId,
  importe,
  roleLabel = 'Solicitante'
) {
  await test.step(`${roleLabel} confirma importe (API + panel)`, async () => {
    await narrate(page, scenario, {
      step: 'Confirmar importe del encargo',
      action: `${roleLabel} declara ${importe} EUR mediante la API de cierre.`,
      expected: 'El contacto debe pasar a trabajo_cerrado y generar Apoyo RUANA.',
    });
    const cierre = await declareImporte(request, solicitanteSession, contactoId, 'solicitante', importe);
    expect(cierre.estado).toBe('trabajo_cerrado');
    await page.reload();
    await expect(page.locator('#metric-score')).toBeVisible();
    await expect(page.locator('#contacto-aviso-persistente')).toBeHidden({ timeout: 15000 });
    await pass(page, scenario, {
      step: 'Importe confirmado',
      action: `${roleLabel} declara ${importe} EUR; el panel actualiza el aviso de contacto.`,
      result: 'Contacto cerrado; el aviso de seguimiento desaparece del Inicio.',
    });
  });
}

async function expectProfessionalCannotConfirmImporteViaUi(
  page,
  request,
  scenario,
  profesionalSession,
  contactoId
) {
  await test.step('Ofertador no puede declarar importe por API', async () => {
    const response = await request.post(`/api/contactos/${contactoId}/declarar-importe`, {
      headers: profesionalSession.headers,
      data: { parte: 'solicitante', importe: 100, moneda: 'EUR' },
    });
    expect(response.status()).toBe(400);
    const body = await response.json();
    expect(body.status).toBe('error');
    expect(body.message).toMatch(/contrat[oó] el encargo/i);
    await reviewSection(page, scenario, '#contacto-aviso-persistente', {
      step: 'Encargo sigue activo en panel',
      action: 'Tras el bloqueo API, el profesional revisa que el encargo sigue en curso.',
      expected: 'El aviso de seguimiento permanece visible.',
      result: 'El encargo no se cierra por el ofertador.',
    });
    await pass(page, scenario, {
      step: 'Cierre por ofertador bloqueado',
      action: 'La API rechaza declareImporte del profesional.',
      result: 'RUANA impide que el ofertador cierre el encargo con importe.',
    });
  });
}

async function closeNoWorkViaUi(page, scenario, roleLabel) {
  await test.step(`${roleLabel} cierra contacto sin trabajo`, async () => {
    await reviewSection(page, scenario, '#contacto-aviso-persistente', {
      step: 'Cerrar sin trabajo',
      action: `${roleLabel} decide que el contacto no se concreto.`,
      expected: 'Debe aparecer modal de confirmacion antes de cerrar.',
      result: 'El aviso de contacto queda visible.',
    });
    await clickVisible(page, '#btn-contacto-no-concreto');
    await expect(page.locator('#modal-no-concretado')).toHaveClass(/show/);
    await clickVisible(page, '#btn-no-concretado-confirm');
    await expect(page.locator('#contacto-aviso-persistente')).toBeHidden();
    await pass(page, scenario, {
      step: 'Contacto cerrado sin trabajo',
      action: `${roleLabel} confirma el cierre sin trabajo desde el modal.`,
      result: 'El aviso desaparece y el contacto queda cerrado/no concretado.',
    });
  });
}

async function uploadComprobanteViaUi(page, scenario) {
  await test.step('Profesional sube comprobante desde el panel', async () => {
    await reviewSection(page, scenario, '#ruana-alert-hub', {
      step: 'Revisar Apoyo RUANA pendiente',
      action: 'El profesional revisa el aviso compacto de Apoyo RUANA.',
      expected: 'Debe aparecer la tarjeta con accion Gestionar.',
      result: 'El hub de alertas muestra el pago pendiente.',
    });
    await clickVisible(page, '[data-alert-action="apoyo-pago"]');
    // Pago manual (Bizum/IBAN) está off salvo allowlist; el comprobante sigue disponible.
    await clickVisible(page, '.btn-enviar-comprobante');
    await expect(page.locator('#modal-comprobante-apoyo')).toHaveClass(/show/);
    await expect(page.locator('#modal-pago-apoyo')).not.toHaveClass(/show/);
    await pass(page, scenario, {
      step: 'Modal de comprobante Apoyo visible',
      action: 'El profesional pulsa Comprobante en el detalle de Apoyo RUANA.',
      result: 'RUANA abre la subida de comprobante sin mostrar pago manual.',
    });
    await setInputFilesVisible(page, '#input-comprobante-apoyo', {
      name: 'comprobante-qa.png',
      mimeType: 'image/png',
      buffer: Buffer.from('comprobante QA RUANA'),
    });
    await fillVisible(page, '#input-comprobante-apoyo-comentario', 'Comprobante QA subido por la interfaz');
    await clickVisible(page, '#btn-comprobante-apoyo-enviar');
    await expect(page.locator('#modal-comprobante-apoyo')).not.toHaveClass(/show/);
    await pass(page, scenario, {
      step: 'Comprobante enviado por UI',
      action: 'El profesional selecciona archivo, escribe comentario y envia.',
      result: 'RUANA acepta el comprobante y lo envia a revision admin.',
    });
  });
}

async function registerAliadoViaUi(page, scenario, data) {
  await test.step('Usuario completa el formulario de registro de aliado', async () => {
    await narrate(page, scenario, {
      step: 'Rellenar datos del aliado',
      action: `Nombre: ${data.nombre}; oficio: ${data.oficio}; CP: ${data.codigo_postal}.`,
      expected: 'El formulario debe aceptar datos validos del catalogo.',
    });
    await fillVisible(page, '#nombre', data.nombre);
    await fillVisible(page, '#marca', data.marca);
    await fillVisible(page, '#codigo-postal', data.codigo_postal);
    await selectVisible(page, '#oficio-principal', { label: data.oficio });
    await fillVisible(page, '#descripcion', data.descripcion);
    await fillVisible(page, '#email', data.email);
    await fillVisible(page, '#telefono-nacional', nationalPhoneFromE164(data.telefono));
    await checkVisible(page, '#condiciones');

    await narrate(page, scenario, {
      step: 'Enviar solicitud de registro',
      action: 'El usuario pulsa Solicitar registro.',
      expected: 'RUANA debe registrar al aliado y mostrar su codigo.',
    });
    await clickVisible(page, '#submit-btn');
    const codigo = await page.waitForFunction(() => sessionStorage.getItem('ruana_codigo_aliado'));
    const codigoAliado = await codigo.jsonValue();
    await pass(page, scenario, {
      step: 'Registro completado',
      action: 'La aplicacion muestra el codigo unico del aliado.',
      result: `Aliado creado con codigo ${codigoAliado}.`,
      pauseMs: 1100,
    });
    return codigoAliado;
  });
}

async function createContactPrecondition(page, request, scenario, solicitanteOverrides, profesionalOverrides) {
  await page.goto('/');
  await narrate(page, scenario, {
    step: 'Preparar usuarios y contacto',
    action: 'QA crea aliados activos y un contacto aceptado para entrar por UI.',
    expected: 'La preparacion no sustituye las acciones visibles del usuario.',
  });
  const solicitante = await registerAliado(request, solicitanteOverrides);
  const profesional = await registerAliado(request, profesionalOverrides);
  const solicitanteSession = await aliadoLogin(request, solicitante.codigo);
  const profesionalSession = await aliadoLogin(request, profesional.codigo);
  const contactoId = await createAcceptedContact(request, solicitanteSession, profesionalSession);
  await pass(page, scenario, {
    step: 'Precondicion creada',
    action: 'El contacto queda aceptado y en progreso.',
    result: `Contacto ${contactoId}; solicitante ${solicitante.codigo}; profesional ${profesional.codigo}.`,
  });
  return { solicitante, profesional, solicitanteSession, profesionalSession, contactoId };
}

async function createPaymentInReviewViaUi(page, request, scenario, suffix) {
  const data = await createContactPrecondition(
    page,
    request,
    scenario,
    {
      nombre: `Solicitante QA Pago ${suffix}`,
      oficio: 'Fontaner\u00eda y fontaner\u00eda-gas',
      oficio_principal: 'Fontaner\u00eda y fontaner\u00eda-gas',
      especializacion: 'Reparaci\u00f3n de fugas y grifos',
      codigo_postal: '28020',
    },
    {
      nombre: `Profesional QA Pago ${suffix}`,
      oficio: 'Electricidad',
      oficio_principal: 'Electricidad',
      especializacion: 'Aver\u00edas y reparaciones el\u00e9ctricas',
      codigo_postal: '28021',
    }
  );
  await openAliadoPanel(page, data.solicitanteSession, scenario, 'Solicitante');
  await confirmImporteViaUi(
    page,
    request,
    scenario,
    data.solicitanteSession,
    data.contactoId,
    180,
    'Solicitante'
  );
  await openAliadoPanel(page, data.profesionalSession, scenario, 'Profesional');
  await uploadComprobanteViaUi(page, scenario);
  return data;
}

async function adminApprovePaymentViaUi(page, scenario, contactoId) {
  await test.step('Admin aprueba pago desde la tabla', async () => {
    await goAdminSection(page, '#pagos-en-revision-wrap');
    await reviewSection(page, scenario, '#pagos-en-revision-wrap', {
      step: 'Pago pendiente de aprobacion',
      action: 'El admin localiza el comprobante en pagos en revision.',
      expected: 'Debe aparecer la accion Aprobar pago.',
      result: 'La tabla de pagos en revision queda visible.',
    });
    const row = page.locator(`#tbody-pagos-en-revision tr[data-contacto-id="${contactoId}"]`);
    await expect(row).toBeVisible();
    await clickVisible(page, row.locator('.btn-aprobar-pago'));
    await expect(page.locator('.ruana-toast.success, .admin-toast.success')).toContainText(
      'Estado de pago actualizado'
    );
    await pass(page, scenario, {
      step: 'Pago aprobado',
      action: 'El administrador pulsa Aprobar pago.',
      result: `Contacto ${contactoId} queda actualizado como pagado.`,
    });
  });
}

async function adminRejectPaymentViaUi(page, scenario, contactoId) {
  await test.step('Admin rechaza pago con motivo', async () => {
    await goAdminSection(page, '#pagos-en-revision-wrap');
    await reviewSection(page, scenario, '#pagos-en-revision-wrap', {
      step: 'Pago pendiente de rechazo',
      action: 'El admin localiza el comprobante que quiere rechazar.',
      expected: 'Debe abrirse modal de motivo obligatorio.',
      result: 'La tabla de pagos en revision queda visible.',
    });
    const row = page.locator(`#tbody-pagos-en-revision tr[data-contacto-id="${contactoId}"]`);
    await expect(row).toBeVisible();
    await clickVisible(page, row.locator('.btn-rechazar-pago'));
    await expect(page.locator('#modal-rechazar-pago')).toBeVisible();
    await fillVisible(page, '#input-motivo-rechazo-pago', 'Comprobante ilegible en prueba QA');
    await clickVisible(page, '#btn-confirmar-rechazar-pago');
    await expect(page.locator('.ruana-toast.success, .admin-toast.success')).toContainText(
      /pago rechazado/i
    );
    await pass(page, scenario, {
      step: 'Pago rechazado',
      action: 'El administrador escribe motivo y rechaza.',
      result: `Contacto ${contactoId} queda rechazado y se notifica al profesional.`,
    });
  });
}

test.describe('RUANA QA critica con video human-readable', () => {
  test('admin: login, resumen, registros, score, solicitudes y pagos', async ({ page }) => {
    const scenario = 'Admin revisa panel, score, registros y pagos';

    await loginAdminAsUser(page, scenario);

    const sections = [
      ['#command-center-wrap', 'Estado global', 'El admin revisa KPIs del Command Center, aliados activos, suplentes, riesgo y solicitudes.'],
      ['#movimiento-grid', 'Movimiento 24h', 'El admin revisa solicitudes, invitaciones recientes y actividad por hora.'],
      ['.metricas-salud', 'Metricas clave', 'El admin revisa ratios de salud y disponibilidad de oficios.'],
      ['#pendientes-validacion-wrap', 'Aliados pendientes', 'El admin revisa altas pendientes y estados de registro.'],
      ['#conflictos-pago-wrap', 'Conflictos de pago', 'El admin revisa reclamaciones abiertas o vacias.'],
      ['#pagos-apoyo-wrap', 'Pagos Apoyo RUANA', 'El admin revisa trabajos cerrados y acciones de pago.'],
      ['#pagos-en-revision-wrap', 'Pagos en revision', 'El admin revisa comprobantes enviados.'],
      ['#solicitudes-admin-wrap', 'Solicitudes', 'El admin revisa filtros y registros de nuevas conexiones.'],
      ['#solicitudes-semanales-admin-wrap', 'Solicitudes semanales', 'El admin revisa necesidades de grupo y respuestas de la semana.'],
      ['#competencias-activas-wrap', 'Competencias activas', 'El admin revisa score, suplencias y competencias.'],
      ['#conversaciones-ruana-wrap', 'Registro de chats', 'El admin revisa conversaciones entre solicitante y profesional.'],
    ];

    for (const [selector, label, action] of sections) {
      await test.step(`Admin recorre ${label}`, async () => {
        await goAdminSection(page, selector);
        await reviewSection(page, scenario, selector, {
          step: label,
          action,
          expected: 'La seccion debe estar presente y alimentada por el panel.',
          result: `${label} visible en el video.`,
        });
      });
    }

    await goAdminSection(page, '#movimiento-grid');
    await clickVisible(page, '#btn-toggle-desglose-hora');
    await expect(page.locator('#desglose-por-hora-container')).toBeVisible();
    await pass(page, scenario, {
      step: 'Desglose horario abierto',
      action: 'El admin pulsa Ver desglose por hora.',
      result: 'La tabla de las ultimas 24h aparece desplegada.',
    });
  });

  test('invitaciones y creacion de aliado: usuario valida codigo y se registra por UI', async ({
    page,
    request,
  }) => {
    const scenario = 'Invitacion y registro de aliado como usuario real';
    const admin = await adminLogin(request);
    const campaign = await createCampaign(request, admin, { max_usos: 1 });
    const code = campaign.campana.codigo;
    const data = buildAliadoData({
      nombre: 'Aliado QA Invitado',
      codigo_invitacion: code,
      codigo_postal: '28001',
    });

    await test.step('Usuario abre invite.html y escribe el codigo recibido', async () => {
      await page.goto('/invite.html');
      await narrate(page, scenario, {
        step: 'Introducir codigo de invitacion',
        action: `El usuario escribe ${code} en la pantalla de invitacion.`,
        expected: 'Si el codigo existe y tiene usos, debe avanzar al registro.',
      });
      await fillVisible(page, '#invite-code', code);
      await clickVisible(page, '#invite-btn');
      await expect(page).toHaveURL(/register\.html/);
      const inviteValid = await page.evaluate(() => sessionStorage.getItem('ruana_invite_valid'));
      const inviteCode = await page.evaluate(() => sessionStorage.getItem('ruana_invite_codigo'));
      expect(inviteValid).toBe('true');
      expect(inviteCode).toBe(code);
      await pass(page, scenario, {
        step: 'Codigo validado',
        action: 'RUANA redirige a register.html.',
        result: 'La invitacion queda cargada en la sesion del navegador.',
      });
    });

    await registerAliadoViaUi(page, scenario, data);

    await test.step('QA comprueba que la invitacion ya no se puede reutilizar', async () => {
      await page.goto('/invite.html');
      await narrate(page, scenario, {
        step: 'Verificar consumo del codigo',
        action: 'El usuario vuelve a escribir el mismo codigo agotado.',
        expected: 'Un codigo de un solo uso debe quedar agotado.',
      });
      await fillVisible(page, '#invite-code', code);
      await clickVisible(page, '#invite-btn');
      await expect(page.locator('#invite-error')).toBeVisible();
      await pass(page, scenario, {
        step: 'Codigo agotado',
        action: 'La pantalla muestra el error al reutilizar la invitacion.',
        result: 'No se permite reutilizar la invitacion desde la UI.',
      });
    });
  });

  test('QA-03 admin crea campana de invitacion desde UI y QA-29 solo lectura queda bloqueado', async ({
    page,
  }) => {
    const scenario = 'Admin crea invitacion y permisos solo lectura';
    const code = uniqueId('UI-QA').toUpperCase();

    await loginAdminAsUser(page, scenario);
    await goAdminSection(page, '#admin-campanas-invitacion-panel');
    await reviewSection(page, scenario, '#admin-campanas-invitacion-panel', {
      step: 'Panel de campanas de invitacion',
      action: 'El admin baja hasta la gestion de invitaciones multiuso.',
      expected: 'Debe existir la accion Crear Invitacion Multiuso.',
      result: 'El panel de campanas queda visible.',
    });
    await clickVisible(page, 'button[data-action="crear-campana-invitacion"]');
    await expect(page.locator('#modal-accion-admin')).toBeVisible();
    await fillVisible(page, '#accion-campana-nombre', 'Campana QA UI visible');
    await fillVisible(page, '#accion-campana-codigo', code);
    await fillVisible(page, '#accion-campana-zona', '28030');
    await fillVisible(page, '#accion-campana-max-usos', '2');
    await clickVisible(page, '#modal-accion-confirmar');
    await expect(page.locator('#modal-accion-body')).toContainText(code);
    await clickVisible(page, '#modal-accion-confirmar');
    await expect(page.locator('#admin-campana-invitacion-result')).toContainText(code);
    await pass(page, scenario, {
      step: 'Campana creada por UI',
      action: 'El admin rellena formulario, confirma resumen y ve codigo generado.',
      result: `Campana ${code} visible en el panel.`,
    });

    await loginAdminAsUser(page, scenario, '0000', 'admin solo lectura');
    await goAdminSection(page, '#admin-campanas-invitacion-panel');
    await reviewSection(page, scenario, '#admin-campanas-invitacion-panel', {
      step: 'Admin solo lectura revisa invitaciones',
      action: 'El usuario de solo lectura entra en la misma seccion.',
      expected: 'Las acciones de escritura deben estar deshabilitadas.',
      result: 'El panel es visible, pero las acciones no son ejecutables.',
    });
    await expect(page.locator('button[data-action="crear-campana-invitacion"]')).toBeDisabled();
    await goAdminSection(page, '#acciones-admin-wrap');
    await reviewSection(page, scenario, '#acciones-admin-wrap', {
      step: 'Acciones admin bloqueadas',
      action: 'El usuario de solo lectura baja a acciones de administrador.',
      expected: 'Los botones de escritura deben aparecer deshabilitados.',
      result: 'Las acciones administrativas quedan bloqueadas para solo lectura.',
    });
    await expect(page.locator('#acciones-admin-wrap button[data-action="cambiar-reglas"]')).toBeDisabled();
    await pass(page, scenario, {
      step: 'Permisos solo lectura validados',
      action: 'Se comprueba visualmente que no puede crear ni cambiar reglas.',
      result: 'El rol puede leer el panel, pero no ejecutar acciones de escritura.',
    });
  });

  test('admin: modal de confirmacion purga mensual sin ejecutar', async ({ page }) => {
    const scenario = 'Confirmacion purga mensual admin';
    await loginAdminAsUser(page, scenario);
    await goAdminSection(page, '#acciones-admin-wrap');
    await clickVisible(page, 'button[data-action="purga-mensual"]');
    await expect(page.locator('#modal-accion-admin')).toBeVisible();
    await expect(page.locator('#modal-accion-body')).toContainText('No es reversible');
    await clickVisible(page, '#modal-accion-confirmar');
    await expect(page.locator('#modal-accion-body')).toContainText('purga mensual');
    await clickVisible(page, '#modal-accion-cancelar');
    await expect(page.locator('#modal-accion-admin')).not.toBeVisible();
    await pass(page, scenario, {
      step: 'Modal purga validado',
      action: 'El admin abre purga mensual y cancela en el segundo paso.',
      result: 'El flujo de confirmacion aparece sin ejecutar la purga real.',
    });
  });

  test('QA-08 QA-09 aliado crea solicitud y otro aliado la atiende con invitacion visible', async ({
    page,
    request,
  }) => {
    const scenario = 'Solicitudes de nuevas conexiones entre aliados';
    const solicitante = await registerAliado(request, {
      nombre: 'Aliado QA Solicita',
      oficio: 'Electricidad',
      oficio_principal: 'Electricidad',
      especializacion: 'Aver\u00edas y reparaciones el\u00e9ctricas',
      codigo_postal: '28040',
    });
    const respondedor = await registerAliado(request, {
      nombre: 'Aliado QA Responde Solicitud',
      oficio: 'Pintura y decoraci\u00f3n',
      oficio_principal: 'Pintura y decoraci\u00f3n',
      especializacion: 'Pintura interior y exterior',
      codigo_postal: '28040',
    });
    const solicitanteSession = await aliadoLogin(request, solicitante.codigo);
    const respondedorSession = await aliadoLogin(request, respondedor.codigo);

    await openAliadoPanel(page, solicitanteSession, scenario, 'Aliado solicitante');
    await goAliadoModule(page, 'conexiones');
    await reviewSection(page, scenario, '.crear-solicitud-zone', {
      step: 'Formulario de solicitud',
      action: 'El aliado abre el modulo Conexiones para crear una nueva solicitud.',
      expected: 'Debe poder indicar oficio y descripcion.',
      result: 'El formulario de solicitud queda visible.',
    });
    await fillVisible(page, '#nueva-solicitud-oficio', 'Cerrajeria urgente');
    await fillVisible(page, '#nueva-solicitud', 'Necesito un profesional de cerrajeria para una puerta bloqueada.');
    await clickVisible(page, '#btn-enviar');
    await goAliadoModule(page, 'solicitudes');
    await expect(page.locator('#solicitudes-propias-list')).toContainText('Cerrajeria urgente');
    await pass(page, scenario, {
      step: 'Solicitud enviada',
      action: 'El aliado rellena y envia la solicitud.',
      result: 'La solicitud aparece en Mis solicitudes.',
    });

    await openAliadoPanel(page, respondedorSession, scenario, 'Aliado respondedor');
    await goAliadoModule(page, 'solicitudes');
    await reviewSection(page, scenario, '#solicitudes-entrantes-wrap', {
      step: 'Solicitud entrante visible',
      action: 'Otro aliado del grupo revisa las solicitudes entrantes.',
      expected: 'Debe ver la solicitud y poder responder Conozco a alguien.',
      result: 'La solicitud entrante queda visible.',
    });
    await expect(page.locator('#solicitudes-list')).toContainText('Cerrajeria urgente');
    await clickVisible(page, '#solicitudes-list .btn-conocer');
    await expect(page.locator('#code-value')).not.toContainText('XXXXX');
    await pass(page, scenario, {
      step: 'Solicitud atendida con invitacion',
      action: 'El aliado pulsa Conozco a alguien y recibe un codigo visible.',
      result: 'El codigo de invitacion aparece en pantalla para compartir.',
    });
  });

  test('QA-12 QA-13 QA-14 negociacion guiada visible para ambos usuarios y admin', async ({
    page,
    request,
  }) => {
    const scenario = 'Negociacion guiada entre solicitante y profesional';
    const obsQa = 'Observaciones QA negociacion visible';
    const { solicitanteSession, profesionalSession, contactoId } = await createContactPrecondition(
      page,
      request,
      scenario,
      {
        nombre: 'Solicitante QA Negociacion',
        oficio: 'Fontaner\u00eda y fontaner\u00eda-gas',
        oficio_principal: 'Fontaner\u00eda y fontaner\u00eda-gas',
        especializacion: 'Reparaci\u00f3n de fugas y grifos',
        codigo_postal: '28050',
      },
      {
        nombre: 'Profesional QA Negociacion',
        oficio: 'Electricidad',
        oficio_principal: 'Electricidad',
        especializacion: 'Aver\u00edas y reparaciones el\u00e9ctricas',
        codigo_postal: '28051',
      }
    );

    await test.step('Solicitante envia propuesta completa de negociacion', async () => {
      await proponerNegociacionCompleta(request, solicitanteSession, contactoId, {
        servicio: 'Servicio QA integral',
        fecha: '2026-12-15',
        hora: '10:00',
        direccion: 'Calle QA Negociacion 1',
        observaciones: obsQa,
      });
      await pass(page, scenario, {
        step: 'Propuesta enviada',
        action: 'El solicitante envia la propuesta completa de negociacion.',
        result: 'Quedan eventos de negociacion listos para ver en UI.',
      });
    });

    await openAliadoPanel(page, solicitanteSession, scenario, 'Solicitante');
    await verifyNegociacionVisibleViaUi(page, scenario, obsQa, 'Solicitante');

    await openAliadoPanel(page, profesionalSession, scenario, 'Profesional');
    await verifyNegociacionVisibleViaUi(page, scenario, obsQa, 'Profesional');
    await openNegociacionViaUi(page, scenario, 'Profesional');
    await test.step('Profesional confirma el primer punto de la negociacion', async () => {
      await expect(page.locator('#neg-btn-aceptar')).toBeVisible({ timeout: 15000 });
      await clickVisible(page, '#neg-btn-aceptar');
      await expect(page.locator('#neg-timeline')).toContainText(/confirm|acept|servicio/i, {
        timeout: 15000,
      });
      await pass(page, scenario, {
        step: 'Profesional confirma servicio',
        action: 'El profesional pulsa Confirmar en el primer punto pendiente.',
        result: 'La negociacion avanza y el historial se actualiza.',
      });
    });
    await closeNegociacionViaUi(page);

    await loginAdminAsUser(page, scenario);
    await goAdminSection(page, '#conversaciones-ruana-wrap');
    await reviewSection(page, scenario, '#conversaciones-ruana-wrap', {
      step: 'Admin revisa registro de negociaciones',
      action: 'El admin baja a conversaciones y localiza el contacto.',
      expected: 'Debe poder abrir el historial de negociacion.',
      result: 'La tabla de conversaciones queda visible.',
    });
    const row = page.locator(`#tbody-conversaciones tr:has-text("${contactoId}")`);
    await expect(row).toBeVisible();
    await clickVisible(page, row.locator('.btn-ver-chat'));
    await expect(page.locator('#admin-chat-mensajes')).not.toContainText('Sin eventos aún', {
      timeout: 15000,
    });
    await expect(page.locator('#admin-chat-mensajes')).toContainText(obsQa);
    await pass(page, scenario, {
      step: 'Admin ve negociacion completa',
      action: 'El admin abre Ver desde el registro.',
      result: 'El historial muestra eventos de la negociacion guiada.',
    });
  });

  test('QA-16 ofertador no puede cerrar con importe y QA-17 cierre sin trabajo por UI', async ({
    page,
    request,
  }) => {
    const scenario = 'Cierres alternativos del encargo';
    const flowBloqueo = await createContactPrecondition(
      page,
      request,
      scenario,
      {
        nombre: 'Solicitante QA Bloqueo',
        oficio: 'Fontaner\u00eda y fontaner\u00eda-gas',
        oficio_principal: 'Fontaner\u00eda y fontaner\u00eda-gas',
        especializacion: 'Reparaci\u00f3n de fugas y grifos',
        codigo_postal: '28060',
      },
      {
        nombre: 'Profesional QA Bloqueo',
        oficio: 'Electricidad',
        oficio_principal: 'Electricidad',
        especializacion: 'Aver\u00edas y reparaciones el\u00e9ctricas',
        codigo_postal: '28061',
      }
    );
    await openAliadoPanel(page, flowBloqueo.profesionalSession, scenario, 'Ofertador');
    await expectProfessionalCannotConfirmImporteViaUi(
      page,
      request,
      scenario,
      flowBloqueo.profesionalSession,
      flowBloqueo.contactoId
    );

    const flowNoTrabajo = await createContactPrecondition(
      page,
      request,
      scenario,
      {
        nombre: 'Solicitante QA No Trabajo',
        oficio: 'Carpinter\u00eda de madera e interior',
        oficio_principal: 'Carpinter\u00eda de madera e interior',
        especializacion: 'Muebles a medida b\u00e1sicos',
        codigo_postal: '28062',
      },
      {
        nombre: 'Profesional QA No Trabajo',
        oficio: 'Pintura y decoraci\u00f3n',
        oficio_principal: 'Pintura y decoraci\u00f3n',
        especializacion: 'Pintura interior y exterior',
        codigo_postal: '28063',
      }
    );
    await openAliadoPanel(page, flowNoTrabajo.solicitanteSession, scenario, 'Solicitante');
    await closeNoWorkViaUi(page, scenario, 'Solicitante');
  });

  test('QA-20 QA-21 admin aprueba pago en revision desde UI', async ({
    page,
    request,
  }) => {
    const scenario = 'Revision admin de pago aprobado';
    const pagoAprobar = await createPaymentInReviewViaUi(page, request, scenario, 'Aprobar');
    await loginAdminAsUser(page, scenario);
    await adminApprovePaymentViaUi(page, scenario, pagoAprobar.contactoId);
  });

  test('QA-22 admin rechaza pago y profesional ve notificacion', async ({ page, request }) => {
    const scenario = 'Revision admin de pago rechazado y notificacion';
    const pagoRechazar = await createPaymentInReviewViaUi(page, request, scenario, 'Rechazar');
    await loginAdminAsUser(page, scenario);
    await adminRejectPaymentViaUi(page, scenario, pagoRechazar.contactoId);
    await openAliadoPanel(page, pagoRechazar.profesionalSession, scenario, 'Profesional con pago rechazado');
    await reviewSection(page, scenario, '#ruana-alert-hub', {
      step: 'Profesional recibe mensaje de RUANA',
      action: 'Tras el rechazo, el profesional revisa el hub de alertas.',
      expected: 'Debe ver una notificacion con el motivo del rechazo.',
      result: 'La tarjeta de mensajes de RUANA queda visible.',
    });
    // El hub colapsa a 1 aviso (pago pendiente); hay que expandir para ver mensajes.
    const moreAlerts = page.locator('.ruana-alert-hub__more');
    if (await moreAlerts.isVisible().catch(() => false)) {
      await clickVisible(page, '.ruana-alert-hub__more');
    }
    await clickVisible(page, '[data-alert-action="mensajes-ruana"]');
    await expect(page.locator('#ruana-alert-hub')).toContainText('Comprobante ilegible');
    await pass(page, scenario, {
      step: 'Notificacion de rechazo visible',
      action: 'El profesional ve el motivo enviado por admin.',
      result: 'El rechazo queda registrado a nivel usuario.',
    });
  });

  test('encargo, confirmacion, pago y revision admin', async ({ page, request }) => {
    const scenario = 'Encargo, confirmacion de trabajo y pago';
    await page.goto('/');
    await narrate(page, scenario, {
      step: 'Preparar usuarios de prueba',
      action: 'QA crea por BBDD/API los usuarios necesarios para abrir el flujo visual.',
      expected: 'Ambos aliados deben quedar activos para operar en el panel.',
    });

    const solicitante = await registerAliado(request, {
      nombre: 'Solicitante QA',
      oficio: 'Fontaner\u00eda y fontaner\u00eda-gas',
      oficio_principal: 'Fontaner\u00eda y fontaner\u00eda-gas',
      especializacion: 'Reparaci\u00f3n de fugas y grifos',
      codigo_postal: '28002',
    });
    const profesional = await registerAliado(request, {
      nombre: 'Profesional QA',
      oficio: 'Electricidad',
      oficio_principal: 'Electricidad',
      especializacion: 'Aver\u00edas y reparaciones el\u00e9ctricas',
      codigo_postal: '28003',
    });
    await pass(page, scenario, {
      step: 'Usuarios preparados',
      action: 'Se crean los aliados necesarios para simular el encargo.',
      result: `Solicitante ${solicitante.codigo}; profesional ${profesional.codigo}.`,
    });

    const solicitanteSession = await aliadoLogin(request, solicitante.codigo);
    const profesionalSession = await aliadoLogin(request, profesional.codigo);
    let contactoId;

    await test.step('Usuario solicitante crea encargo y profesional lo acepta', async () => {
      await narrate(page, scenario, {
        step: 'Crear encargo',
        action: 'QA crea la precondicion de contacto aceptado para poder probar el panel.',
        expected: 'El encargo debe crearse, aceptarse y pasar a trabajo en progreso.',
      });
      contactoId = await createAcceptedContact(request, solicitanteSession, profesionalSession);
      await pass(page, scenario, {
        step: 'Encargo aceptado',
        action: 'El contacto queda listo para que el usuario lo gestione desde UI.',
        result: `Contacto ${contactoId} listo para confirmar importe.`,
      });

      await openAliadoPanel(page, solicitanteSession, scenario, 'Solicitante');
      await openNegociacionViaUi(page, scenario, 'Solicitante');
      await closeNegociacionViaUi(page);
      await confirmImporteViaUi(
        page,
        request,
        scenario,
        solicitanteSession,
        contactoId,
        250
      );

      await openAliadoPanel(page, profesionalSession, scenario, 'Profesional');
      await uploadComprobanteViaUi(page, scenario);
    });

    await test.step('Admin revisa la cola de pagos', async () => {
      await loginAdminAsUser(page, scenario);
      const admin = await adminLogin(request);
      await goAdminSection(page, '#pagos-en-revision-wrap');
      await reviewSection(page, scenario, '#pagos-en-revision-wrap', {
        step: 'Consultar pagos Apoyo RUANA',
        action: 'El administrador baja a la tabla de pagos en revision.',
        expected: 'El pago del contacto debe aparecer disponible para revision.',
        result: 'La cola de pagos en revision queda visible.',
      });
      await expect(page.locator(`#tbody-pagos-en-revision tr[data-contacto-id="${contactoId}"]`)).toBeVisible();
      const pagosResponse = await request.get('/api/admin/pagos-en-revision', { headers: admin.headers });
      await expectOk(pagosResponse, 'admin pagos en revision');
      await pass(page, scenario, {
        step: 'Pago visible para admin',
        action: 'La tabla admin contiene el contacto revisado en el video.',
        result: `Contacto ${contactoId} visible; verificacion tecnica HTTP ${pagosResponse.status()}.`,
      });
    });
  });

  test('reclamaciones: profesional impugna y admin ve el conflicto', async ({ page, request }) => {
    const scenario = 'Reclamacion e investigacion de conflicto';
    await page.goto('/');
    await narrate(page, scenario, {
      step: 'Preparar trabajo reclamable',
      action: 'QA crea contratante, profesional y contacto cerrado con pago pendiente.',
      expected: 'El profesional debe poder impugnar el Apoyo RUANA generado.',
    });

    const contratante = await registerAliado(request, {
      nombre: 'Contratante QA Reclamo',
      oficio: 'Carpinter\u00eda de madera e interior',
      oficio_principal: 'Carpinter\u00eda de madera e interior',
      especializacion: 'Muebles a medida b\u00e1sicos',
      codigo_postal: '28004',
    });
    const profesional = await registerAliado(request, {
      nombre: 'Profesional QA Reclamo',
      oficio: 'Pintura y decoraci\u00f3n',
      oficio_principal: 'Pintura y decoraci\u00f3n',
      especializacion: 'Pintura interior y exterior',
      codigo_postal: '28005',
    });
    const contratanteSession = await aliadoLogin(request, contratante.codigo);
    const profesionalSession = await aliadoLogin(request, profesional.codigo);
    const contactoId = await createAcceptedContact(request, contratanteSession, profesionalSession);
    const cierre = await declareImporte(request, contratanteSession, contactoId, 'solicitante', 100);
    expect(cierre.estado).toBe('trabajo_cerrado');
    await pass(page, scenario, {
      step: 'Trabajo preparado',
      action: 'El contacto se cierra con importe declarado por contratante.',
      result: `Contacto ${contactoId} cerrado con pago pendiente.`,
    });

    await test.step('Profesional presenta reclamacion', async () => {
      await openAliadoPanel(page, profesionalSession, scenario, 'Profesional');
      await narrate(page, scenario, {
        step: 'Impugnar Apoyo RUANA',
        action: 'El profesional baja a Apoyo RUANA y reclama el importe declarado.',
        expected: 'RUANA debe abrir un conflicto pendiente de prueba.',
      });
      await reviewSection(page, scenario, '#ruana-alert-hub', {
        step: 'Ver pago reclamable',
        action: 'El profesional abre el detalle del Apoyo RUANA pendiente.',
        expected: 'Debe aparecer Reclamar.',
        result: 'El hub de Apoyo RUANA queda visible.',
      });
      await clickVisible(page, '[data-alert-action="apoyo-pago"]');
      await clickVisible(page, '.btn-impugnar-apoyo');
      await expect(page.locator('#modal-impugnar-apoyo')).toHaveClass(/show/);
      await fillVisible(
        page,
        '#input-motivo-impugnar-apoyo',
        'Importe declarado no coincide con presupuesto aceptado'
      );
      await clickVisible(page, '#btn-impugnar-apoyo-confirmar');
      await expect(page.locator('#modal-impugnar-apoyo')).not.toHaveClass(/show/, { timeout: 15000 });
      await pass(page, scenario, {
        step: 'Reclamacion creada',
        action: 'El profesional escribe el motivo y confirma en el modal de reclamacion.',
        result: 'RUANA registra el conflicto para revision admin.',
      });
    });

    await test.step('Admin consulta la cola de conflictos', async () => {
      await loginAdminAsUser(page, scenario);
      const admin = await adminLogin(request);
      await goAdminSection(page, '#conflictos-pago-wrap');
      await reviewSection(page, scenario, '#conflictos-pago-wrap', {
        step: 'Revisar conflictos de pago',
        action: 'El administrador baja a la cola de reclamaciones.',
        expected: 'Debe existir informacion del conflicto para investigacion.',
        result: 'La tabla de conflictos queda visible.',
      });
      await expect(page.locator('#tbody-conflictos-pago')).toContainText(String(contactoId));
      const conflicts = await request.get('/api/admin/payment-conflicts', { headers: admin.headers });
      await expectOk(conflicts, 'admin payment conflicts');
      await pass(page, scenario, {
        step: 'Conflicto visible para admin',
        action: 'La cola de conflictos muestra el contacto reclamado.',
        result: `Contacto ${contactoId} visible; verificacion tecnica HTTP ${conflicts.status()}.`,
      });
    });
  });

  test('pago manual oculto si el aliado no esta en la allowlist', async ({ page, request }) => {
    const scenario = 'Aliado sin allowlist no ve pago manual';
    const bizumFake = '600000000';
    const ibanFake = 'ES0000000000000000000000';
    const flow = await createContactPrecondition(
      page,
      request,
      scenario,
      {
        nombre: 'Solicitante QA Manual Off',
        oficio: 'Fontaner\u00eda y fontaner\u00eda-gas',
        oficio_principal: 'Fontaner\u00eda y fontaner\u00eda-gas',
        especializacion: 'Reparaci\u00f3n de fugas y grifos',
        codigo_postal: '28110',
      },
      {
        nombre: 'Profesional QA Manual Off',
        oficio: 'Electricidad',
        oficio_principal: 'Electricidad',
        especializacion: 'Aver\u00edas y reparaciones el\u00e9ctricas',
        codigo_postal: '28111',
      }
    );
    const admin = await adminLogin(request);
    const saved = await request.post('/api/admin/metodos-pago', {
      headers: admin.headers,
      data: { bizum_num: bizumFake, iban: ibanFake },
    });
    await expectOk(saved, 'guardar metodos pago');

    await openAliadoPanel(page, flow.solicitanteSession, scenario, 'Solicitante');
    await confirmImporteViaUi(
      page,
      request,
      scenario,
      flow.solicitanteSession,
      flow.contactoId,
      120,
      'Solicitante'
    );
    await openAliadoPanel(page, flow.profesionalSession, scenario, 'Profesional sin pago manual');
    const metodos = await request.get('/api/metodos-pago', { headers: flow.profesionalSession.headers });
    const metodosBody = await expectOk(metodos, 'metodos pago aliado no habilitado');
    expect(metodosBody.metodos.habilitado).toBe(false);
    expect(metodosBody.metodos.bizum_num).toBeNull();
    expect(metodosBody.metodos.iban).toBeNull();

    await clickVisible(page, '[data-alert-action="apoyo-pago"]');
    await expect(page.locator('.btn-aceptar-pagar')).toHaveCount(0);
    await expect(page.locator('#modal-pago-apoyo')).not.toHaveClass(/show/);
    await expect(page.locator('#ruana-alert-hub')).not.toContainText(ibanFake);
    await expect(page.locator('#ruana-alert-hub')).not.toContainText(bizumFake);
    await pass(page, scenario, {
      step: 'Pago manual ausente en cobro',
      action: 'El profesional abre Apoyo RUANA sin estar en la allowlist.',
      result: 'No aparece Aceptar y pagar ni IBAN/Bizum reales en el flujo de cobro.',
    });
  });

  test('admin habilita y deshabilita pago manual aliado desde el panel', async ({ page, request }) => {
    const scenario = 'Allowlist pago manual desde admin';
    const bizumFake = '600000000';
    const ibanFake = 'ES0000000000000000000000';
    const flow = await createContactPrecondition(
      page,
      request,
      scenario,
      {
        nombre: 'Solicitante QA Manual On',
        oficio: 'Fontaner\u00eda y fontaner\u00eda-gas',
        oficio_principal: 'Fontaner\u00eda y fontaner\u00eda-gas',
        especializacion: 'Reparaci\u00f3n de fugas y grifos',
        codigo_postal: '28120',
      },
      {
        nombre: 'Profesional QA Manual On',
        oficio: 'Electricidad',
        oficio_principal: 'Electricidad',
        especializacion: 'Aver\u00edas y reparaciones el\u00e9ctricas',
        codigo_postal: '28121',
      }
    );

    await openAliadoPanel(page, flow.solicitanteSession, scenario, 'Solicitante');
    await confirmImporteViaUi(
      page,
      request,
      scenario,
      flow.solicitanteSession,
      flow.contactoId,
      140,
      'Solicitante'
    );

    await loginAdminAsUser(page, scenario);
    await goAdminSection(page, '#metodos-pago-admin-wrap');
    await page.waitForFunction((codigo) => {
      const panel = window._ruanaAdminPanel;
      return Boolean(
        panel &&
          Array.isArray(panel._aliadosData) &&
          panel._aliadosData.some((a) => a && a.codigo === codigo)
      );
    }, flow.profesional.codigo, { timeout: 20000 });

    await clickVisible(page, 'button[data-action="editar-metodos-pago"]');
    await expect(page.locator('#modal-accion-admin')).toBeVisible();
    await fillVisible(page, '#accion-mp-bizum', bizumFake);
    await fillVisible(page, '#accion-mp-iban', ibanFake);
    await clickVisible(page, '#modal-accion-confirmar');
    await clickVisible(page, '#modal-accion-confirmar');
    await expect(page.locator('#admin-metodo-bizum')).toHaveText(bizumFake, { timeout: 15000 });
    await expect(page.locator('#admin-metodo-iban')).toHaveText(ibanFake);

    await fillVisible(page, '#admin-pago-manual-buscar', flow.profesional.codigo);
    await clickVisible(page, '#btn-habilitar-pago-manual');
    await expect(page.locator('#admin-pago-manual-aliados-tbody')).toContainText(flow.profesional.codigo, {
      timeout: 15000,
    });
    await pass(page, scenario, {
      step: 'Admin habilita pago manual',
      action: 'Se guardan Bizum/IBAN de prueba y se habilita al profesional.',
      result: `Aliado ${flow.profesional.codigo} aparece en la allowlist.`,
    });

    await openAliadoPanel(page, flow.profesionalSession, scenario, 'Profesional con pago manual');
    await clickVisible(page, '[data-alert-action="apoyo-pago"]');
    await expect(page.locator('.btn-aceptar-pagar')).toBeVisible();
    await clickVisible(page, '.btn-aceptar-pagar');
    await expect(page.locator('#modal-pago-apoyo')).toHaveClass(/show/);
    await expect(page.locator('#pago-apoyo-bizum-numero')).toHaveText(bizumFake);
    await expect(page.locator('#pago-apoyo-iban')).toHaveText(ibanFake);
    await pass(page, scenario, {
      step: 'Pago manual visible con datos reales',
      action: 'El profesional recarga el panel con la misma sesion y abre Aceptar y pagar.',
      result: 'Ve Bizum e IBAN de prueba.',
    });

    await loginAdminAsUser(page, scenario);
    await goAdminSection(page, '#metodos-pago-admin-wrap');
    await clickVisible(
      page,
      `#admin-pago-manual-aliados-tbody [data-deshabilitar-pago="${flow.profesional.codigo}"]`
    );
    await expect(page.locator('#admin-pago-manual-aliados-tbody')).not.toContainText(flow.profesional.codigo);

    await page.goto('/aliado');
    await page.evaluate((sessionId) => {
      sessionStorage.setItem('ruana_session_id', sessionId);
    }, flow.profesionalSession.sessionId);
    await page.goto('/aliado');
    await expect(page.locator('#metric-score')).toBeVisible();
    await clickVisible(page, '[data-alert-action="apoyo-pago"]');
    await expect(page.locator('.btn-aceptar-pagar')).toHaveCount(0);
    await expect(page.locator('#modal-pago-apoyo')).not.toHaveClass(/show/);
    await pass(page, scenario, {
      step: 'Pago manual desaparece sin nuevo login',
      action: 'El admin quita al aliado; el profesional recarga con la misma sesion.',
      result: 'Aceptar y pagar ya no aparece; no se pidieron credenciales nuevas.',
    });
  });
});
