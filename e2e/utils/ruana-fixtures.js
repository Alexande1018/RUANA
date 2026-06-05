const { expect } = require('@playwright/test');

const ADMIN_CODE = process.env.RUANA_QA_ADMIN_CODE || 'ADMIN001';

function uniqueId(prefix) {
  return `${prefix}-${Date.now()}-${Math.floor(Math.random() * 10000)}`;
}

function uniquePhone() {
  const tail = String(Date.now()).slice(-7);
  const random = String(Math.floor(Math.random() * 90) + 10);
  return `+346${random}${tail}`;
}

function buildAliadoData(overrides = {}) {
  const suffix = uniqueId('qa');
  return {
    nombre: overrides.nombre || `Aliado QA ${suffix}`,
    marca: overrides.marca || `Marca QA ${suffix}`,
    oficio: overrides.oficio || 'Electricidad',
    oficio_principal: overrides.oficio_principal || overrides.oficio || 'Electricidad',
    especializacion:
      overrides.especializacion || 'Aver\u00edas y reparaciones el\u00e9ctricas',
    codigo_postal: overrides.codigo_postal || '28001',
    email: overrides.email || `${suffix}@ruana.local`,
    telefono: overrides.telefono || uniquePhone(),
    descripcion: overrides.descripcion || 'Servicio de prueba QA automatizada',
    codigo_invitacion: overrides.codigo_invitacion || '',
  };
}

async function expectOk(response, label) {
  const body = await response.json().catch(() => ({}));
  expect(
    response.ok(),
    `${label} failed with HTTP ${response.status()}: ${JSON.stringify(body)}`
  ).toBeTruthy();
  return body;
}

async function adminLogin(request) {
  const response = await request.post('/api/admin/validar', {
    data: { codigo: ADMIN_CODE },
  });
  const body = await expectOk(response, 'admin login');
  expect(body.session_id).toBeTruthy();
  return {
    code: ADMIN_CODE,
    sessionId: body.session_id,
    headers: { 'X-Ruana-Session-Id': body.session_id },
  };
}

async function createCampaign(request, admin, overrides = {}) {
  const code = overrides.codigo || uniqueId('RUANA-QA').toUpperCase();
  const response = await request.post('/api/admin/invitacion-campanas', {
    headers: admin.headers,
    data: {
      codigo: code,
      nombre: overrides.nombre || `Campana QA ${code}`,
      codigo_postal: overrides.codigo_postal || '28001',
      max_usos: overrides.max_usos || 3,
    },
  });
  const body = await expectOk(response, 'create invitation campaign');
  expect(body.campana.codigo).toBe(code);
  return body;
}

async function registerAliado(request, overrides = {}) {
  const data = buildAliadoData(overrides);
  const response = await request.post('/api/aliados/registrar', {
    data,
  });
  const body = await expectOk(response, 'register aliado');
  expect(body.codigo).toBeTruthy();
  return body;
}

async function aliadoLogin(request, codigo) {
  const response = await request.post('/api/aliado/login', {
    data: { codigo },
  });
  const body = await expectOk(response, `aliado login ${codigo}`);
  expect(body.session_id).toBeTruthy();
  return {
    codigo,
    sessionId: body.session_id,
    headers: { 'X-Ruana-Session-Id': body.session_id },
  };
}

async function createAcceptedContact(request, solicitanteSession, profesionalSession) {
  const createResponse = await request.post('/api/contactos', {
    headers: solicitanteSession.headers,
    data: {
      profesional_codigo: profesionalSession.codigo,
      servicio: 'Servicio QA integral',
      motivo_contacto: 'Presupuesto',
    },
  });
  const createBody = await expectOk(createResponse, 'create contact');
  expect(createBody.id).toBeTruthy();

  const acceptResponse = await request.post(`/api/contactos/${createBody.id}/aceptar`, {
    headers: profesionalSession.headers,
  });
  await expectOk(acceptResponse, 'accept contact');

  const progressResponse = await request.post(
    `/api/contactos/${createBody.id}/trabajo-en-progreso`,
    { headers: profesionalSession.headers }
  );
  await expectOk(progressResponse, 'mark work in progress');

  return createBody.id;
}

async function declareImporte(request, session, contactoId, parte, importe) {
  const response = await request.post(`/api/contactos/${contactoId}/declarar-importe`, {
    headers: session.headers,
    data: { parte, importe, moneda: 'EUR' },
  });
  return expectOk(response, `declare importe ${parte}`);
}

module.exports = {
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
  uniquePhone,
};
