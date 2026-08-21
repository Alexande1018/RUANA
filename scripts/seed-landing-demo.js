/**
 * Datos de demo premium para capturas de landing RUANA.
 * Ejecutar con el servidor Flask activo en BASE_URL.
 */
const path = require('path');
const {
  adminLogin,
  createCampaign,
  declareImporte,
  expectOk,
  proponerNegociacionCompleta,
} = require('../e2e/utils/ruana-fixtures');

const BASE_URL = process.env.RUANA_BASE_URL || 'http://127.0.0.1:5000';

const LANDING = {
  cp: '28001',
  campaignCode: 'RUANA-LANDING-2026',
  allies: {
    hero: {
      nombre: 'Carlos Mendoza',
      marca: 'Carpintería Mendoza',
      oficio: 'Carpintería de madera e interior',
      oficio_principal: 'Carpintería de madera e interior',
      especializacion: 'Muebles a medida y restauración',
      codigo_postal: '28001',
      email: 'carlos.mendoza@landing.local',
      telefono: '+34600100001',
      descripcion: 'Ebanistería de autor, restauración y proyectos a medida para viviendas y locales.',
    },
    ana: {
      nombre: 'Ana García',
      marca: 'Fontanería García',
      oficio: 'Fontanería y fontanería-gas',
      oficio_principal: 'Fontanería y fontanería-gas',
      especializacion: 'Instalaciones, fugas y mantenimiento',
      codigo_postal: '28001',
      email: 'ana.garcia@landing.local',
      telefono: '+34600100002',
      descripcion: 'Fontanería integral con respuesta rápida en zona centro.',
    },
    miguel: {
      nombre: 'Miguel Torres',
      marca: 'Electricidad Torres',
      oficio: 'Electricidad',
      oficio_principal: 'Electricidad',
      especializacion: 'Cuadros eléctricos y averías',
      codigo_postal: '28001',
      email: 'miguel.torres@landing.local',
      telefono: '+34600100003',
      descripcion: 'Instalaciones eléctricas residenciales y comerciales.',
    },
    laura: {
      nombre: 'Laura Ruiz',
      marca: 'Pinturas Ruiz',
      oficio: 'Pintura y decoración',
      oficio_principal: 'Pintura y decoración',
      especializacion: 'Interior, exterior y acabados',
      codigo_postal: '28001',
      email: 'laura.ruiz@landing.local',
      telefono: '+34600100004',
      descripcion: 'Acabados premium y reformas de pintura.',
    },
    javier: {
      nombre: 'Javier Herrera',
      marca: 'Cerrajería Herrera',
      oficio: 'Cerrajería',
      oficio_principal: 'Cerrajería',
      especializacion: 'Aperturas y blindajes',
      codigo_postal: '28001',
      email: 'javier.herrera@landing.local',
      telefono: '+34600100005',
      descripcion: 'Urgencias y cerrajería de seguridad.',
    },
    elena: {
      nombre: 'Elena Vargas',
      marca: 'Reformas Vargas',
      oficio: 'Albañilería y obra',
      oficio_principal: 'Albañilería y obra',
      especializacion: 'Reformas integrales',
      codigo_postal: '28001',
      email: 'elena.vargas@landing.local',
      telefono: '+34600100006',
      descripcion: 'Reformas de calidad con seguimiento completo.',
    },
    retador: {
      nombre: 'Roberto López',
      marca: 'Electricidad López',
      oficio: 'Electricidad',
      oficio_principal: 'Electricidad',
      especializacion: 'Instalaciones y domótica',
      codigo_postal: '28002',
      email: 'roberto.lopez@landing.local',
      telefono: '+34600100007',
      descripcion: 'Electricista certificado con enfoque en eficiencia energética.',
    },
  },
};

async function postJson(request, path, data, headers = {}) {
  const response = await request.post(path, { data, headers });
  return expectOk(response, path);
}

async function getJson(request, path, headers = {}) {
  const response = await request.get(path, { headers });
  return expectOk(response, path);
}

async function createLandingContact(request, solicitanteSession, profesionalSession, servicio) {
  const createResponse = await request.post('/api/contactos', {
    headers: solicitanteSession.headers,
    data: {
      profesional_codigo: profesionalSession.codigo,
      servicio,
      motivo_contacto: 'Presupuesto',
    },
  });
  const createBody = await expectOk(createResponse, 'create contact');
  const acceptResponse = await request.post(`/api/contactos/${createBody.id}/aceptar`, {
    headers: profesionalSession.headers,
  });
  await expectOk(acceptResponse, 'accept contact');
  const progressResponse = await request.post(`/api/contactos/${createBody.id}/trabajo-en-progreso`, {
    headers: profesionalSession.headers,
  });
  await expectOk(progressResponse, 'mark work in progress');
  return createBody.id;
}

async function ensureAliadoSession(request, codigo, pin = '2468') {
  const login = await request.post('/api/aliado/login', { data: { codigo } });
  const loginBody = await expectOk(login, `aliado login ${codigo}`);
  if (loginBody.pin_setup_required) {
    const pinResp = await request.post('/api/aliado/pin/crear', {
      data: {
        setup_token: loginBody.setup_token,
        pin,
        pin_confirmacion: pin,
      },
    });
    const pinBody = await expectOk(pinResp, `aliado pin ${codigo}`);
    return {
      codigo,
      sessionId: pinBody.session_id,
      headers: { 'X-Ruana-Session-Id': pinBody.session_id },
    };
  }
  if (loginBody.session_id) {
    return {
      codigo,
      sessionId: loginBody.session_id,
      headers: { 'X-Ruana-Session-Id': loginBody.session_id },
    };
  }
  const retry = await request.post('/api/aliado/login', { data: { codigo, pin } });
  const retryBody = await expectOk(retry, `aliado login retry ${codigo}`);
  return {
    codigo,
    sessionId: retryBody.session_id,
    headers: { 'X-Ruana-Session-Id': retryBody.session_id },
  };
}

async function main() {
  const { request: requestFactory } = require('@playwright/test');
  const request = await requestFactory.newContext({ baseURL: BASE_URL });

  console.log('Sembrando demo landing en', BASE_URL);

  const admin = await adminLogin(request);
  await createCampaign(request, admin, {
    codigo: LANDING.campaignCode,
    nombre: 'Campaña Landing Premium',
    codigo_postal: LANDING.cp,
    max_usos: 20,
  });

  const registered = {};
  for (const [key, data] of Object.entries(LANDING.allies)) {
    const payload = {
      ...data,
      codigo_invitacion: LANDING.campaignCode,
      acepta_privacidad_y_terminos: true,
    };
    const response = await request.post('/api/aliados/registrar', { data: payload });
    const body = await expectOk(response, `register ${key}`);
    registered[key] = body;
    console.log(`  Aliado ${key}: ${registered[key].codigo}`);
  }

  for (const ally of Object.values(registered)) {
    await postJson(
      request,
      '/api/admin/activar-aliado',
      { codigo: ally.codigo },
      admin.headers
    ).catch(() => {});
  }

  const sessions = {};
  for (const [key, ally] of Object.entries(registered)) {
    sessions[key] = await ensureAliadoSession(request, ally.codigo);
  }

  const contactoNegociacion = await createLandingContact(
    request,
    sessions.hero,
    sessions.ana,
    'Instalación de mobiliario a medida'
  );
  await proponerNegociacionCompleta(request, sessions.hero, contactoNegociacion, {
    servicio: 'Instalación de mobiliario a medida',
    fecha: '2026-09-12',
    hora: '10:30',
    direccion: 'Calle Serrano 42, Madrid',
    observaciones: 'Medición previa acordada. Material incluido en presupuesto.',
    precio_catalogo: '1.850 €',
  });
  console.log('  Contacto negociación:', contactoNegociacion);

  const contactoPago = await createLandingContact(
    request,
    sessions.laura,
    sessions.miguel,
    'Reforma eléctrica integral'
  );
  await declareImporte(request, sessions.laura, contactoPago, 'solicitante', 420);
  console.log('  Contacto pago/apoyo:', contactoPago);

  const grupos = await getJson(request, '/api/admin/grupos', admin.headers);
  const grupoMiguel = (grupos.grupos || []).find((g) =>
    String(g.codigo_postal || '').startsWith('28001')
  );
  if (grupoMiguel && registered.miguel && registered.retador) {
    const competencia = await postJson(
      request,
      '/api/admin/forzar-competencia',
      {
        grupo_id: grupoMiguel.id,
        oficio: 'Electricidad',
        aliado_original_codigo: registered.miguel.codigo,
        retador_codigo: registered.retador.codigo,
      },
      admin.headers
    );
    console.log('  Competencia forzada:', competencia.message || competencia.status);
  }

  const manifest = {
    baseURL: BASE_URL,
    admin: { code: 'ADMIN001', password: 'ADMIN001' },
    hero: {
      codigo: registered.hero.codigo,
      sessionId: sessions.hero.sessionId,
    },
    professionalNegociacion: {
      codigo: registered.ana.codigo,
      sessionId: sessions.ana.sessionId,
      contactoId: contactoNegociacion,
    },
    professionalPago: {
      codigo: registered.miguel.codigo,
      sessionId: sessions.miguel.sessionId,
      contactoId: contactoPago,
    },
    allies: Object.fromEntries(
      Object.entries(registered).map(([k, v]) => [k, { codigo: v.codigo }])
    ),
  };

  const fs = require('fs');
  const outPath = '/opt/cursor/artifacts/landing-demo-manifest.json';
  fs.mkdirSync('/opt/cursor/artifacts', { recursive: true });
  fs.writeFileSync(outPath, JSON.stringify(manifest, null, 2));
  console.log('Manifest guardado en', outPath);

  const { spawnSync } = require('child_process');
  const boost = spawnSync(
    'python3',
    ['scripts/boost-landing-scores.py'],
    {
      cwd: path.join(__dirname, '..'),
      env: { ...process.env, RUANA_LANDING_MANIFEST: outPath, RUANA_DB_PATH: process.env.RUANA_DB_PATH },
      encoding: 'utf8',
    }
  );
  if (boost.status !== 0) {
    console.error(boost.stdout || boost.stderr);
    throw new Error('No se pudieron actualizar los scores de landing');
  }
  if (boost.stdout) process.stdout.write(boost.stdout);

  await request.dispose();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
