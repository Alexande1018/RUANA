const { test, expect } = require('@playwright/test');
const {
  ADMIN_CODE,
  adminLogin,
  aliadoLogin,
  buildAliadoData,
  createAcceptedContact,
  createCampaign,
  declareImporte,
  expectOk,
  registerAliado,
  uniqueId,
} = require('./utils/ruana-fixtures');
const {
  checkVisible,
  clickVisible,
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

async function loginAdminAsUser(page, scenario, code = ADMIN_CODE, label = 'admin') {
  await test.step(`Usuario ${label} abre el panel e introduce su codigo`, async () => {
    await page.goto('/');
    await page.evaluate(() => sessionStorage.removeItem('admin_session_id'));
    await page.goto('/admin');
    await narrate(page, scenario, {
      step: 'Abrir panel de administracion',
      action: 'El usuario navega a /admin y ve el formulario de acceso.',
      expected: 'Debe aparecer el campo Codigo admin.',
    });
    await fillVisible(page, '#adminLoginCodigo', code);
    await narrate(page, scenario, {
      step: 'Introducir codigo admin',
      action: `Se escribe el codigo ${code} y se pulsa Entrar.`,
      expected: 'RUANA debe conceder acceso al panel segun permisos.',
    });
    await clickVisible(page, '#adminLoginBtn');
    await expect(page.locator('#admin-main-content')).toBeVisible();
    await expect(page.locator('body')).not.toHaveClass(/admin-is-loading/, { timeout: 15000 });
    await pass(page, scenario, {
      step: 'Acceso admin concedido',
      action: 'El panel principal queda visible.',
      result: 'Login admin correcto; se ven KPIs, registros y secciones de gestion.',
    });
  });
}

async function sendChatMessageViaUi(page, scenario, message, roleLabel = 'Usuario') {
  await test.step(`${roleLabel} abre chat y envia un mensaje visible`, async () => {
    await reviewSection(page, scenario, '#contacto-aviso-persistente', {
      step: 'Ver aviso de contacto activo',
      action: `${roleLabel} localiza el seguimiento del encargo en su panel.`,
      expected: 'Debe aparecer la accion Abrir chat.',
      result: 'El aviso de contacto queda visible.',
    });
    await clickVisible(page, '#btn-contacto-abrir-chat');
    await expect(page.locator('#modal-chat-ruana')).toHaveClass(/show/);
    await fillVisible(page, '#chat-input-texto', message);
    await clickVisible(page, '#chat-btn-enviar');
    await expect(page.locator('#chat-mensajes-list')).toContainText(message);
    await pass(page, scenario, {
      step: `${roleLabel} envia mensaje por chat`,
      action: `${roleLabel} escribe y envia un mensaje desde el modal.`,
      result: `El chat muestra el mensaje: "${message}".`,
    });
    await clickVisible(page, '#ruana-chat-cerrar');
  });
}

async function verifyChatContainsViaUi(page, scenario, expectedText, roleLabel) {
  await test.step(`${roleLabel} abre chat y ve el mensaje`, async () => {
    await reviewSection(page, scenario, '#contacto-aviso-persistente', {
      step: `${roleLabel} localiza chat`,
      action: `${roleLabel} abre el seguimiento para comprobar mensajes.`,
      expected: 'El historial debe incluir mensajes del otro participante.',
      result: 'El aviso de contacto queda visible.',
    });
    await clickVisible(page, '#btn-contacto-abrir-chat');
    await expect(page.locator('#modal-chat-ruana')).toHaveClass(/show/);
    await expect(page.locator('#chat-mensajes-list')).toContainText(expectedText);
    await pass(page, scenario, {
      step: `${roleLabel} ve mensaje`,
      action: `${roleLabel} revisa el historial del chat.`,
      result: `El mensaje "${expectedText}" aparece en pantalla.`,
    });
    await clickVisible(page, '#ruana-chat-cerrar');
  });
}

async function confirmImporteViaUi(page, scenario, importe, roleLabel = 'Solicitante') {
  await test.step(`${roleLabel} confirma importe desde el panel`, async () => {
    await reviewSection(page, scenario, '#contacto-aviso-persistente', {
      step: 'Localizar cierre de trabajo',
      action: `${roleLabel} revisa el seguimiento antes de declarar importe.`,
      expected: 'Debe existir el boton Si, hubo trabajo.',
      result: 'El aviso de cierre queda visible.',
    });
    await clickVisible(page, '#btn-contacto-si-trabajo');
    await expect(page.locator('#modal-contacto-importe')).toHaveClass(/show/);
    await fillVisible(page, '#contacto-importe-input', String(importe));
    await clickVisible(page, '#btn-contacto-importe-confirm');
    await expect(page.locator('#contacto-aviso-persistente')).toBeHidden();
    await pass(page, scenario, {
      step: 'Importe confirmado por UI',
      action: `${roleLabel} declara ${importe} EUR desde el modal.`,
      result: 'El contacto se cierra y el aviso desaparece del panel.',
    });
  });
}

async function expectProfessionalCannotConfirmImporteViaUi(page, scenario) {
  await test.step('Ofertador intenta cerrar trabajo y ve bloqueo claro', async () => {
    const dialogPromise = new Promise((resolve) => {
      page.once('dialog', async (dialog) => {
        const message = dialog.message();
        await dialog.accept();
        resolve(message);
      });
    });
    await reviewSection(page, scenario, '#contacto-aviso-persistente', {
      step: 'Ofertador intenta confirmar trabajo',
      action: 'El profesional pulsa Si, hubo trabajo desde su panel.',
      expected: 'Si el producto reserva el cierre al solicitante, debe mostrar un mensaje claro.',
      result: 'El aviso de cierre queda visible para el ofertador.',
    });
    await clickVisible(page, '#btn-contacto-si-trabajo');
    const message = await dialogPromise;
    expect(message).toContain('contrato el encargo');
    await pass(page, scenario, {
      step: 'Cierre por ofertador bloqueado',
      action: 'El profesional no puede declarar importe en el flujo actual.',
      result: `Mensaje mostrado: ${message}`,
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
    await reviewSection(page, scenario, '#pagos-apoyo-ruana-wrap', {
      step: 'Revisar Apoyo RUANA pendiente',
      action: 'El profesional baja hasta el bloque de pagos pendientes.',
      expected: 'Debe aparecer la accion Enviar comprobante de pago a RUANA.',
      result: 'El bloque de pago pendiente queda visible.',
    });
    await clickVisible(page, '.btn-aceptar-pagar');
    await expect(page.locator('#modal-paypal-apoyo')).toHaveClass(/show/);
    await expect(page.locator('#modal-paypal-apoyo')).toContainText('Se te va a redirigir a PayPal');
    await expect(page.locator('#modal-paypal-apoyo')).toContainText('Guarda el comprobante de pago');
    await pass(page, scenario, {
      step: 'Aviso previo a PayPal visible',
      action: 'El profesional pulsa Aceptar y pagar antes de enviar el comprobante.',
      result: 'RUANA avisa que se redirige a PayPal y que debe guardar el comprobante.',
    });
    await clickVisible(page, '#btn-paypal-apoyo-cerrar');
    await clickVisible(page, '.btn-enviar-comprobante');
    await expect(page.locator('#modal-comprobante-apoyo')).toHaveClass(/show/);
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
    await expect(page.locator('#suboficios-section')).toBeVisible();
    await checkVisible(page, `input[name="suboficio"][value="${data.especializacion}"]`, {
      checkOptions: { force: true },
      state: 'attached',
    });
    await fillVisible(page, '#descripcion', data.descripcion);
    await fillVisible(page, '#email', data.email);
    await fillVisible(page, '#telefono', data.telefono);
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
  await confirmImporteViaUi(page, scenario, 180, 'Solicitante');
  await openAliadoPanel(page, data.profesionalSession, scenario, 'Profesional');
  await uploadComprobanteViaUi(page, scenario);
  return data;
}

async function adminApprovePaymentViaUi(page, scenario, contactoId) {
  await test.step('Admin aprueba pago desde la tabla', async () => {
    await reviewSection(page, scenario, '#pagos-en-revision-wrap', {
      step: 'Pago pendiente de aprobacion',
      action: 'El admin localiza el comprobante en pagos en revision.',
      expected: 'Debe aparecer la accion Aprobar pago.',
      result: 'La tabla de pagos en revision queda visible.',
    });
    const row = page.locator(`#tbody-pagos-en-revision tr[data-contacto-id="${contactoId}"]`);
    await expect(row).toBeVisible();
    await clickVisible(page, row.locator('.btn-aprobar-pago'));
    await expect(page.locator('.admin-toast.success')).toContainText('Estado de pago actualizado');
    await pass(page, scenario, {
      step: 'Pago aprobado',
      action: 'El administrador pulsa Aprobar pago.',
      result: `Contacto ${contactoId} queda actualizado como pagado.`,
    });
  });
}

async function adminRejectPaymentViaUi(page, scenario, contactoId) {
  await test.step('Admin rechaza pago con motivo', async () => {
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
    await expect(page.locator('.admin-toast.success')).toContainText('pago rechazado');
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
      ['.estado-global', 'Estado global', 'El admin revisa KPIs, aliados activos, suplentes, riesgo y solicitudes.'],
      ['#movimiento-grid', 'Movimiento 24h', 'El admin revisa solicitudes, invitaciones recientes y actividad por hora.'],
      ['.metricas-salud', 'Metricas clave', 'El admin revisa ratios de salud y disponibilidad de oficios.'],
      ['#pendientes-validacion-wrap', 'Aliados pendientes', 'El admin revisa altas pendientes y estados de registro.'],
      ['#conflictos-pago-wrap', 'Conflictos de pago', 'El admin revisa reclamaciones abiertas o vacias.'],
      ['#pagos-apoyo-wrap', 'Pagos Apoyo RUANA', 'El admin revisa trabajos cerrados y acciones de pago.'],
      ['#pagos-en-revision-wrap', 'Pagos en revision', 'El admin revisa comprobantes enviados.'],
      ['#solicitudes-admin-wrap', 'Solicitudes', 'El admin revisa filtros y registros de nuevas conexiones.'],
      ['#competencias-activas-wrap', 'Competencias activas', 'El admin revisa score, suplencias y competencias.'],
      ['#conversaciones-ruana-wrap', 'Registro de chats', 'El admin revisa conversaciones entre solicitante y profesional.'],
    ];

    for (const [selector, label, action] of sections) {
      await test.step(`Admin recorre ${label}`, async () => {
        await reviewSection(page, scenario, selector, {
          step: label,
          action,
          expected: 'La seccion debe estar presente y alimentada por el panel.',
          result: `${label} visible en el video.`,
        });
      });
    }

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
    await reviewSection(page, scenario, '#admin-campanas-invitacion-panel', {
      step: 'Admin solo lectura revisa invitaciones',
      action: 'El usuario de solo lectura entra en la misma seccion.',
      expected: 'Las acciones de escritura deben estar deshabilitadas.',
      result: 'El panel es visible, pero las acciones no son ejecutables.',
    });
    await expect(page.locator('button[data-action="crear-campana-invitacion"]')).toBeDisabled();
    await reviewSection(page, scenario, '.acciones-admin', {
      step: 'Acciones admin bloqueadas',
      action: 'El usuario de solo lectura baja a acciones de administrador.',
      expected: 'Los botones de escritura deben aparecer deshabilitados.',
      result: 'Las acciones administrativas quedan bloqueadas para solo lectura.',
    });
    await expect(page.locator('.acciones-admin button[data-action="cambiar-reglas"]')).toBeDisabled();
    await pass(page, scenario, {
      step: 'Permisos solo lectura validados',
      action: 'Se comprueba visualmente que no puede crear ni cambiar reglas.',
      result: 'El rol puede leer el panel, pero no ejecutar acciones de escritura.',
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

  test('QA-12 QA-13 QA-14 chat bidireccional visible para ambos usuarios y admin', async ({
    page,
    request,
  }) => {
    const scenario = 'Chat bidireccional entre solicitante y profesional';
    const { solicitanteSession, profesionalSession, contactoId } = await createContactPrecondition(
      page,
      request,
      scenario,
      {
        nombre: 'Solicitante QA Chat',
        oficio: 'Fontaner\u00eda y fontaner\u00eda-gas',
        oficio_principal: 'Fontaner\u00eda y fontaner\u00eda-gas',
        especializacion: 'Reparaci\u00f3n de fugas y grifos',
        codigo_postal: '28050',
      },
      {
        nombre: 'Profesional QA Chat',
        oficio: 'Electricidad',
        oficio_principal: 'Electricidad',
        especializacion: 'Aver\u00edas y reparaciones el\u00e9ctricas',
        codigo_postal: '28051',
      }
    );

    const msgSolicitante = 'Mensaje QA del solicitante para coordinar visita.';
    const msgProfesional = 'Respuesta QA del profesional confirmando disponibilidad.';

    await openAliadoPanel(page, solicitanteSession, scenario, 'Solicitante');
    await sendChatMessageViaUi(page, scenario, msgSolicitante, 'Solicitante');
    await openAliadoPanel(page, profesionalSession, scenario, 'Profesional');
    await verifyChatContainsViaUi(page, scenario, msgSolicitante, 'Profesional');
    await sendChatMessageViaUi(page, scenario, msgProfesional, 'Profesional');
    await openAliadoPanel(page, solicitanteSession, scenario, 'Solicitante');
    await verifyChatContainsViaUi(page, scenario, msgProfesional, 'Solicitante');

    await loginAdminAsUser(page, scenario);
    await reviewSection(page, scenario, '#conversaciones-ruana-wrap', {
      step: 'Admin revisa registro de chats',
      action: 'El admin baja a conversaciones y localiza el contacto.',
      expected: 'Debe poder abrir el historial completo.',
      result: 'La tabla de conversaciones queda visible.',
    });
    const row = page.locator(`#tbody-conversaciones tr:has-text("${contactoId}")`);
    await expect(row).toBeVisible();
    await clickVisible(page, row.locator('.btn-ver-chat'));
    await expect(page.locator('#admin-chat-mensajes')).toContainText(msgSolicitante);
    await expect(page.locator('#admin-chat-mensajes')).toContainText(msgProfesional);
    await pass(page, scenario, {
      step: 'Admin ve chat completo',
      action: 'El admin abre Ver chat desde el registro.',
      result: 'El historial muestra mensajes de solicitante y profesional.',
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
    await expectProfessionalCannotConfirmImporteViaUi(page, scenario);

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
    await reviewSection(page, scenario, '#notificaciones-ruana-wrap', {
      step: 'Profesional recibe mensaje de RUANA',
      action: 'Tras el rechazo, el profesional revisa sus mensajes.',
      expected: 'Debe ver una notificacion con el motivo del rechazo.',
      result: 'El bloque de mensajes de RUANA queda visible.',
    });
    await expect(page.locator('#notificaciones-ruana-wrap')).toContainText('Comprobante ilegible');
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
      await sendChatMessageViaUi(page, scenario, 'Hola, confirmo disponibilidad para coordinar el trabajo QA.');
      await confirmImporteViaUi(page, scenario, 250);

      await openAliadoPanel(page, profesionalSession, scenario, 'Profesional');
      await uploadComprobanteViaUi(page, scenario);
    });

    await test.step('Admin revisa la cola de pagos', async () => {
      await loginAdminAsUser(page, scenario);
      const admin = await adminLogin(request);
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
      const dialogHandler = async (dialog) => {
        if (dialog.type() === 'prompt') {
          await dialog.accept('Importe declarado no coincide con presupuesto aceptado');
          return;
        }
        await dialog.accept();
      };
      page.on('dialog', dialogHandler);
      await reviewSection(page, scenario, '#pagos-apoyo-ruana-wrap', {
        step: 'Ver pago reclamable',
        action: 'El profesional ve el pago pendiente antes de reclamar.',
        expected: 'Debe aparecer Impugnar o reclamar.',
        result: 'El bloque de Apoyo RUANA queda visible.',
      });
      await clickVisible(page, '.btn-impugnar-apoyo');
      page.off('dialog', dialogHandler);
      await pass(page, scenario, {
        step: 'Reclamacion creada',
        action: 'El profesional acepta los dialogos de reclamacion desde UI.',
        result: 'RUANA registra el conflicto para revision admin.',
      });
    });

    await test.step('Admin consulta la cola de conflictos', async () => {
      await loginAdminAsUser(page, scenario);
      const admin = await adminLogin(request);
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
});
