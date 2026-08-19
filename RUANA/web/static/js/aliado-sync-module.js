/**
 * Módulo PrivatePanel `sync` (Campamento Base).
 * Warmup post-render, snapshots y refreshAfterAction.
 * PrivatePanel conserva fachadas delgadas que delegan aquí.
 */

(function (global) {
  'use strict';

  var modules = global.RuanaAliadoModules = global.RuanaAliadoModules || {
    inicio: null,
    directorio: null,
    solicitudes: null,
    conexiones: null,
    perfil: null,
    referidos: null,
    acuerdos: null,
    centroComunicacion: null,
    invitaciones: null,
    alertas: null,
    catalogo: null,
    contactos: null,
    grupo: null,
    sync: null,
  };

  function getApiBaseSafe() {
    if (typeof global.getApiBase === 'function') return global.getApiBase();
    return '';
  }

  function getAuthHeadersSafe(extra) {
    if (typeof global.getRuanaAuthHeaders === 'function') {
      return global.getRuanaAuthHeaders(extra || {});
    }
    return extra || {};
  }

  async function runWarmupSync(host) {
    const bootstrapTasks = await Promise.allSettled([
        host.fetchCentroComunicacionSnapshot(),
        host.cargarMetodosPagoRuana(),
        host.cargarContactosPendientes(),
        host.cargarMisAcuerdos(),
        host.cargarResumenesAcuerdoFlotantes(),
    ]);
    bootstrapTasks.forEach((task, idx) => {
        if (task.status === 'rejected') {
            const labels = ['centro-comunicacion', 'metodos-pago', 'contactos-pendientes', 'mis-acuerdos', 'resumenes-acuerdo'];
            console.error(`Error en carga de fondo (${labels[idx]}):`, task.reason);
        }
    });
    host.renderCentroComunicacion();
    host.renderAlertas();
    host.renderNotificaciones();
    host.renderListaPagosPendientes();
    host.renderMisAcuerdos();
  }

  function getSyncElements(host, sections) {
    const map = {
        perfil: '.perfil-block',
        metricas: '.metricas-block',
        directorio: '.directorio-panel',
        solicitudes: '.solicitudes-zone',
        alertas: '#ruana-alert-hub',
        centro: '#ruana-help-center'
    };
    return (sections || [])
        .map((k) => map[k])
        .filter(Boolean)
        .map((selector) => document.querySelector(selector))
        .filter(Boolean);
  }

  function setSectionsSyncing(host, sections, syncing) {
    host.getSyncElements(sections).forEach((el) => {
        el.classList.toggle('ruana-syncing', Boolean(syncing));
    });
  }

  async function fetchAliadoSnapshot(host) {
    const apiBase = getApiBaseSafe();
    const resp = await fetch(apiBase + '/api/aliado/datos', { credentials: 'same-origin', headers: getAuthHeadersSafe() });
    if (!resp.ok) return;
    const data = await resp.json();
    if (data.status === 'success' && data.aliado) {
        host.aliado = { ...(host.aliado || {}), ...data.aliado };
        if (Array.isArray(data.notificaciones)) host.notificaciones = data.notificaciones;
    }
  }

  async function fetchSolicitudesSnapshot(host) {
    const codigo = host.codigoAliado || (host.aliado && host.aliado.codigo) || '';
    if (!codigo) return;
    const apiBase = getApiBaseSafe();
    const resp = await fetch(apiBase + '/api/solicitudes?codigo=' + encodeURIComponent(codigo), {
        credentials: 'same-origin',
        headers: getAuthHeadersSafe()
    });
    if (!resp.ok) return;
    const data = await resp.json();
    if (data && typeof data === 'object' && !Array.isArray(data)) {
        host.solicitudesEntrantes = Array.isArray(data.entrantes) ? data.entrantes : [];
        host.solicitudesPropias = Array.isArray(data.propias) ? data.propias : [];
        host.solicitudesHistorial = Array.isArray(data.historial) ? data.historial : [];
    } else {
        host.solicitudesEntrantes = Array.isArray(data) ? data : [];
        host.solicitudesPropias = [];
        host.solicitudesHistorial = [];
    }
  }

  async function refreshAfterAction(host, sections, options) {
    const opts = options || {};
    if (host._syncInProgress && !opts.allowConcurrent) return;
    const targetSections = Array.isArray(sections) ? sections : [];
    host._syncInProgress = true;
    host.setSectionsSyncing(targetSections, true);
    try {
        const jobs = [];
        if (targetSections.includes('perfil') || targetSections.includes('metricas') || targetSections.includes('alertas')) jobs.push(host.fetchAliadoSnapshot());
        if (targetSections.includes('solicitudes')) jobs.push(host.fetchSolicitudesSnapshot());
        if (targetSections.includes('solicitudes')) {
            var semMod = global.RuanaAliadoModules && global.RuanaAliadoModules.solicitudesSemanales;
            if (semMod && typeof semMod.fetchSnapshot === 'function') {
                jobs.push(semMod.fetchSnapshot(host));
            }
        }
        if (targetSections.includes('directorio')) jobs.push(host.fetchDirectorioSnapshot());
        if (targetSections.includes('alertas')) jobs.push(host.actualizarEstadoAlertas());
        if (targetSections.includes('centro')) jobs.push(host.fetchCentroComunicacionSnapshot());
        if (targetSections.includes('contactos')) jobs.push(host.cargarContactosPendientes());
        await Promise.all(jobs);

        if (targetSections.includes('perfil')) { host.renderPerfil(); host.renderGrupo(); }
        if (targetSections.includes('perfil') || targetSections.includes('metricas')) {
            if (global.RuanaStripePagos && typeof global.RuanaStripePagos.renderOnboardingUi === 'function') {
                global.RuanaStripePagos.renderOnboardingUi(host);
            }
        }
        if (targetSections.includes('metricas')) host.renderMetricas();
        if (targetSections.includes('solicitudes')) host.renderSolicitudes();
        if (targetSections.includes('solicitudes')) {
            var semModR = global.RuanaAliadoModules && global.RuanaAliadoModules.solicitudesSemanales;
            if (semModR && typeof semModR.renderSeccion === 'function') semModR.renderSeccion(host);
        }
        if (targetSections.includes('directorio')) host.renderProfesionales();
        if (targetSections.includes('alertas')) {
            host.renderNotificaciones();
            host.renderListaPagosPendientes();
            host.renderAlertas();
        }
        if (targetSections.includes('centro')) host.renderCentroComunicacion();
    } catch (e) {
        console.error('Error de sincronización UI:', e);
    } finally {
        host.setSectionsSyncing(targetSections, false);
        host._syncInProgress = false;
    }
  }

  function initOnboarding(host) {
    host.onboardingTour = new RuanaOnboardingTour(host);
    const replayBtn = document.getElementById('btn-replay-onboarding');
    if (replayBtn) {
        replayBtn.addEventListener('click', () => host.onboardingTour.start(true));
    }
    if (host.onboardingTour.shouldAutoStart()) {
        setTimeout(() => host.onboardingTour.start(), 450);
    }
    window.addEventListener('resize', () => {
        if (host.onboardingTour && (host.onboardingTour.overlay || host.onboardingTour.cloud)) {
            host.onboardingTour.renderStep();
        }
    });
  }

  function startAutoSync(host) {
    if (host._autoSyncIntervalId) clearInterval(host._autoSyncIntervalId);
    host._autoSyncIntervalId = setInterval(() => {
        if (document.visibilityState !== 'visible') return;
        host.refreshAfterAction(['perfil', 'metricas', 'solicitudes', 'directorio', 'alertas', 'contactos', 'centro']);
    }, 20000);
  }

  async function loadData(host) {
    try {
        // Código: primero URL, luego sessionStorage, luego datos aliado
        const codigoURL = PrivatePanel.getCodigoFromURL();
        if (codigoURL) host.codigoAliado = codigoURL;
        if (!host.codigoAliado) host.codigoAliado = sessionStorage.getItem('ruana_codigo_aliado') || null;

        // Cargar datos básicos del aliado desde sesión si existen
        const aliadoData = JSON.parse(sessionStorage.getItem('ruana_aliado_data') || '{}');
        if (aliadoData && Object.keys(aliadoData).length > 0) {
            host.aliado = aliadoData;
            if (!host.codigoAliado && (aliadoData.codigo || aliadoData.codigo_aliado)) {
                host.codigoAliado = aliadoData.codigo || aliadoData.codigo_aliado;
            }
        }

        // Si aún no tenemos código, sessionStorage directo
        if (!host.codigoAliado) {
            const codigoSesion = sessionStorage.getItem('ruana_codigo_aliado');
            if (codigoSesion) host.codigoAliado = codigoSesion;
        }

        // Refrescar datos del aliado desde la API (sesión cookie; backend usa sesión)
        const apiBase = getApiBaseSafe();
        if (host.codigoAliado) {
            const fetchedAtRaw = sessionStorage.getItem('ruana_aliado_data_fetched_at');
            const fetchedAt = fetchedAtRaw ? Number(fetchedAtRaw) : 0;
            const fetchedRecently = Number.isFinite(fetchedAt) && fetchedAt > 0 && (Date.now() - fetchedAt) < 15000;
            try {
                // Evita fetch duplicado inmediato tras bootstrap (DOMContentLoaded ya lo hizo).
                if (!fetchedRecently) {
                    const respDatos = await fetch(apiBase + '/api/aliado/datos', { credentials: 'same-origin', headers: getAuthHeadersSafe() });
                    if (respDatos.ok) {
                        const dataDatos = await respDatos.json();
                        if (dataDatos.status === 'success' && dataDatos.aliado) {
                            host.aliado = { ...(host.aliado || {}), ...dataDatos.aliado };
                            host.notificaciones = Array.isArray(dataDatos.notificaciones) ? dataDatos.notificaciones : [];
                        }
                    } else if (respDatos.status === 403) {
                        // Cuenta pendiente de validación: no puede acceder al panel
                        const errData = await respDatos.json().catch(() => ({}));
                        sessionStorage.removeItem('ruana_aliado_data');
                        sessionStorage.removeItem('ruana_codigo_aliado');
                        sessionStorage.removeItem('ruana_aliado_data_fetched_at');
                        alert(errData.message || 'Tu cuenta está pendiente de validación. Un administrador debe activarla.');
                        window.location.href = '/';
                        return;
                    }
                }
            } catch (e) {
                console.error('Error refrescando datos aliado:', e);
            }

            const [notificacionesTask, solicitudesTask, directorioTask] = await Promise.allSettled([
                (async () => {
                    // Cargar notificaciones explícitamente (mensajes de RUANA: comprobante rechazado, etc.)
                    const respNotif = await fetch(apiBase + '/api/aliados/' + encodeURIComponent(host.codigoAliado) + '/notificaciones?limite=50', {
                        credentials: 'same-origin',
                        headers: getAuthHeadersSafe()
                    });
                    if (!respNotif.ok) return;
                    const dataNotif = await respNotif.json();
                    if (dataNotif.status === 'success' && Array.isArray(dataNotif.notificaciones)) {
                        host.notificaciones = dataNotif.notificaciones;
                    }
                })(),
                (async () => {
                    const respSol = await fetch(apiBase + '/api/solicitudes?codigo=' + encodeURIComponent(host.codigoAliado), {
                        credentials: 'same-origin',
                        headers: getAuthHeadersSafe()
                    });
                    if (!respSol.ok) return;
                    const dataSol = await respSol.json();
                    if (dataSol && typeof dataSol === 'object' && !Array.isArray(dataSol)) {
                        host.solicitudesEntrantes = Array.isArray(dataSol.entrantes) ? dataSol.entrantes : [];
                        host.solicitudesPropias = Array.isArray(dataSol.propias) ? dataSol.propias : [];
                        host.solicitudesHistorial = Array.isArray(dataSol.historial) ? dataSol.historial : [];
                    } else {
                        host.solicitudesEntrantes = Array.isArray(dataSol) ? dataSol : [];
                        host.solicitudesPropias = [];
                        host.solicitudesHistorial = [];
                    }
                })(),
                (async () => {
                    // Directorio: todos los profesionales del mismo grupo (API dedicada)
                    const respDirectorio = await fetch('/api/aliados/directorio', {
                        credentials: 'same-origin',
                        headers: getAuthHeadersSafe()
                    });
                    if (!respDirectorio.ok) return;
                    const dataDirectorio = await respDirectorio.json();
                    if (dataDirectorio.status === 'success' && Array.isArray(dataDirectorio.aliados)) {
                        host.profesionales = dataDirectorio.aliados;
                    }
                })()
            ]);

            if (notificacionesTask.status === 'rejected') {
                console.error('Error cargando notificaciones:', notificacionesTask.reason);
            }
            if (solicitudesTask.status === 'rejected') {
                console.error('Error cargando solicitudes de grupo:', solicitudesTask.reason);
            }
            if (directorioTask.status === 'rejected') {
                console.error('Error cargando directorio de profesionales:', directorioTask.reason);
            }
        }

        // Métricas se calculan directamente a partir de datos reales
        host.isDataLoaded = true;
    } catch (error) {
        console.error('Error cargando datos:', error);
        host.isDataLoaded = false;
    }
  }

    async function fetchDirectorioSnapshot(host) {
      const resp = await fetch('/api/aliados/directorio', { credentials: 'same-origin', headers: getRuanaAuthHeaders() });
      if (!resp.ok) return;
      const data = await resp.json();
      if (data.status === 'success' && Array.isArray(data.aliados)) {
          host.profesionales = data.aliados;
      }
  }

  async function fetchCentroComunicacionSnapshot(host) {
      const codigo = host.codigoAliado || (host.aliado && host.aliado.codigo) || '';
      if (!codigo) return;
      const apiBase = getApiBase();
      const resp = await fetch(apiBase + '/api/aliados/' + encodeURIComponent(codigo) + '/centro-comunicacion', {
          credentials: 'same-origin',
          headers: getRuanaAuthHeaders()
      });
      if (!resp.ok) return;
      const data = await resp.json().catch(() => ({}));
      if (data.status === 'success' && Array.isArray(data.conversaciones)) {
          host.soporteConversations = data.conversaciones;
          if (host.soporteSelectedId && !host.soporteConversations.some(c => Number(c.id) === Number(host.soporteSelectedId))) {
              host.soporteSelectedId = null;
              host.soporteMensajes = [];
          }
      }
  }

  function setPanelLoading(host, isLoading) {
      document.body.classList.toggle('panel-loading', Boolean(isLoading));
      const loadingEl = document.getElementById('panel-loading');
      if (loadingEl) loadingEl.style.display = isLoading ? '' : 'none';
      if (!isLoading && window.AliadoShell && typeof window.AliadoShell.refresh === 'function') {
          window.AliadoShell.refresh();
          if (typeof RuanaUI !== 'undefined') RuanaUI.initIcons(document.querySelector('.aliado-shell-nav') || document.body);
          if (typeof RuanaUI !== 'undefined') RuanaUI.initIcons(document.querySelector('.aliado-shell-bottom'));
          if (typeof RuanaUI !== 'undefined') RuanaUI.initIcons(document.getElementById('module-inicio'));
      }
  }

  async function init(host) {
      // Configurar listeners primero (SIEMPRE)
      host.setupEventListeners();
      if (typeof NegociacionGuiada !== 'undefined') {
          host.negociacionGuiada = new NegociacionGuiada(host);
      }

      // Luego, cargar datos base para pintar el panel lo antes posible
      await host.loadData();

      // Render temprano: el usuario entra al panel sin esperar sincronizaciones largas.
      host.render();
      host.renderAlertas();
      const semModInit = global.RuanaAliadoModules && global.RuanaAliadoModules.solicitudesSemanales;
      if (semModInit && typeof semModInit.initSemanales === 'function') {
          await semModInit.initSemanales(host);
      }
      host.setPanelLoading(false);
      host.initOnboarding();
      if (global.RuanaStripePagos && typeof global.RuanaStripePagos.handleOnboardingReturn === 'function') {
          global.RuanaStripePagos.handleOnboardingReturn(host);
      }
      if (global.RuanaStripePagos && typeof global.RuanaStripePagos.handlePagoReturn === 'function') {
          global.RuanaStripePagos.handlePagoReturn(host);
      }
      host.startAutoSync();

      // Sincronización post-render en segundo plano (mismo comportamiento final).
      host.runWarmupSync();
  }

  function render(host) {
      host.renderPerfil();
      host.renderCompetencia();
      host.renderGrupo();
      host.renderMetricas();
      host.renderSolicitudes();
      const semModRender = global.RuanaAliadoModules && global.RuanaAliadoModules.solicitudesSemanales;
      if (semModRender && typeof semModRender.renderSeccion === 'function') {
          semModRender.renderSeccion(host);
      }
      host.renderProfesionales();
      host.renderNotificaciones();
      host.renderCentroComunicacion();
      if (global.RuanaStripePagos && typeof global.RuanaStripePagos.renderOnboardingUi === 'function') {
          global.RuanaStripePagos.renderOnboardingUi(host);
      }
  }

  async function handleLogout(host) {
      try {
          await fetch('/api/aliado/logout', { method: 'POST', credentials: 'same-origin', headers: getRuanaAuthHeaders() });
      } catch (_) {}
      sessionStorage.removeItem('ruana_codigo_aliado');
      sessionStorage.removeItem('ruana_aliado_data');
      sessionStorage.removeItem('ruana_invite_valid');
      sessionStorage.removeItem('ruana_invite_payload');
      sessionStorage.removeItem('ruana_invite_codigo');
      const keysToRemove = [];
      for (let i = 0; i < sessionStorage.length; i++) {
          const key = sessionStorage.key(i);
          if (key && key.startsWith('ruana_')) keysToRemove.push(key);
      }
      keysToRemove.forEach(key => sessionStorage.removeItem(key));
      window.location.href = '/';
  }

  function copyCode(host) {
      if (!host.currentCode) {
          alert('Error: No hay código disponible');
          return;
      }

      navigator.clipboard.writeText(host.currentCode).then(() => {
          const originalText = host.btnCopyCode.textContent;
          host.btnCopyCode.textContent = '✓ Copiado';

          setTimeout(() => {
              host.btnCopyCode.textContent = originalText;
          }, 2000);
      }).catch(err => {
          console.error('Error copiando código:', err);
          alert('No se pudo copiar el código');
      });
  }

  function closeCodeModal(host) {
      if (host.modalCode) {
          host.modalCode.classList.remove('show');
      }
  }

  function normalizarEstado(host, estado) {
      // Validar que estado sea string
      if (typeof estado !== 'string') {
          return 'observacion'; // Fallback si estado no es válido
      }

      // Normalizar a minúsculas para comparación case-insensitive
      const estadoLower = estado.toLowerCase().trim();

      // Mapeo de estados backend → estados visuales
      const estadoMap = {
          'activo': 'activo',           // Backend: activo → Visual: activo (verde)
          'active': 'activo',           // Posible variante en inglés
          'inactivo': 'inactivo',       // Backend: inactivo → Visual: inactivo (gris/rojo)
          'inactive': 'inactivo',       // Posible variante en inglés
          'observacion': 'observacion', // Backend: observación → Visual: observación (amarillo)
          'riesgo': 'riesgo',           // Backend: riesgo → Visual: riesgo (naranja)
          'risk': 'riesgo'              // Posible variante en inglés
      };

      // Retornar estado mapeado, o 'observacion' si no existe
      return estadoMap[estadoLower] || 'observacion';
  }

  function escapeHtml(host, text) {
      if (!text) return '';
      const div = document.createElement('div');
      div.textContent = text;
      return div.innerHTML;
  }

  function getCodigoFromURL() {
      try {
          const params = new URLSearchParams(window.location.search);
          const codigo = params.get('codigo');
          return codigo && codigo.trim().length > 0 ? codigo.trim() : null;
      } catch (e) {
          console.error('Error parsing URL params:', e);
          return null;
      }
  }

  async function fetchAliadoDatos(codigo) {
      try {
          const base = getApiBase();
          const response = await fetch(base + '/api/aliado/datos', {
              method: 'GET',
              headers: getRuanaAuthHeaders({ 'Content-Type': 'application/json' }),
              credentials: 'same-origin'
          });

          if (!response.ok) {
              if (response.status === 401) return null;
              console.error(`Backend responded con status ${response.status}`);
              return null;
          }

          const data = await response.json();
          if (data && data.status === 'success' && data.aliado) {
              return data;
          }
          console.error('Respuesta del backend sin campos requeridos:', data);
          return null;
      } catch (error) {
          console.error('Error fetching aliado datos:', error);
          return null;
      }
  }

  function bootstrapPrivatePanel() {
    document.addEventListener('DOMContentLoaded', async () => {
      const errorContainer = document.getElementById('error-bootstrap');
      const apiBase = (typeof getApiBase === 'function') ? getApiBase() : '';

      const sesionRes = await fetch(apiBase + '/api/aliado/sesion', { method: 'GET', credentials: 'same-origin', headers: getAuthHeadersSafe() });
      if (!sesionRes.ok) {
        window.location.replace('/');
        return;
      }
      let sesionData;
      try {
        sesionData = await sesionRes.json();
      } catch (_) {
        window.location.replace('/');
        return;
      }
      if (!sesionData || sesionData.status !== 'ok' || !sesionData.codigo) {
        window.location.replace('/');
        return;
      }
      const datos = await global.PrivatePanel.fetchAliadoDatos(sesionData.codigo);
      if (!datos || !datos.aliado) {
        document.body.classList.remove('panel-loading');
        const loadingEl = document.getElementById('panel-loading');
        if (loadingEl) loadingEl.style.display = 'none';
        if (errorContainer) {
          const textEl = document.getElementById('error-bootstrap-text');
          const msg = 'No se pudieron cargar tus datos. Intenta de nuevo desde el inicio.';
          if (textEl) textEl.textContent = msg;
          errorContainer.style.display = 'flex';
        }
        return;
      }
      sessionStorage.setItem('ruana_codigo_aliado', sesionData.codigo);
      sessionStorage.setItem('ruana_aliado_data', JSON.stringify(datos.aliado));
      sessionStorage.setItem('ruana_aliado_data_fetched_at', String(Date.now()));
      new global.PrivatePanel();
    });
  }


  function initState(host) {
    // ==================================================
    // ESTADO INICIAL SEGURO (inicializado siempre)
    // ==================================================
    host.motor = null; // Reservado para futuros usos backend; sin motor JS
    host.aliadoId = 1;

    // DOM references
    host.modalCode = document.getElementById('modal-code');
    host.btnEnviar = document.getElementById('btn-enviar');
    host.nuevaSolicitud = document.getElementById('nueva-solicitud');
    host.solicitudSuccess = document.getElementById('solicitud-success');
    host.btnCopyCode = document.getElementById('btn-copy-code');
    host.btnCloseCode = document.getElementById('btn-close-code');
    host.solicitudesList = document.getElementById('solicitudes-list');
    host.solicitudesPropiasList = document.getElementById('solicitudes-propias-list');
    host.solicitudesHistorialList = document.getElementById('solicitudes-historial-list');
    global.__ruanaPanel = host;

    // Estructura de métricas por defecto (nunca undefined)
    // Estas son las claves que espera el motor RUANA
    host.metricasDefault = {
        solicitudes_recibidas: 0,
        solicitudes_enviadas: 0,
        trabajos_realizados: 0,
        rating_promedio: 0,
        invitaciones_generadas: 0,
        invitaciones_aceptadas: 0,
        score: 0
    };

    // Estado de datos - INICIALIZADOS SIEMPRE
    host.aliado = null; // Se llena en loadData()
    host.solicitudesEntrantes = [];   // Solicitudes de otros del grupo (pendientes) para poder atender
    host.solicitudesPropias = [];     // Mis solicitudes enviadas (pendientes y atendidas)
    host.solicitudesHistorial = [];   // Historial del grupo (todas, para contexto)
    host.profesionales = []; // Array vacío por defecto
    host.metricas = { ...host.metricasDefault }; // Copia de valores por defecto

    host.currentCode = null;
    host.isDataLoaded = false;
    host._referidosTree = null;

    // Onboarding premium
    host.onboardingTour = null;

    // Contactos RUANA
    host.codigoAliado = sessionStorage.getItem('ruana_codigo_aliado') || null;
    host.contactosAbiertos = [];
    host.contactoActual = null;
    host.profesionalSeleccionado = null;
    host.negociacionGuiada = null;
    host.notificaciones = [];
    host.soporteConversations = [];
    host.soporteMensajes = [];
    host.soporteSelectedId = null;
    host.contactosPagoPendiente = [];
    host.tienePagosPendientes = false;
    host.misAcuerdos = [];
    host.misAcuerdosFiltro = 'todos';
    host.misAcuerdosFiltroEstado = '';
    host.misAcuerdosFiltroDesde = '';
    host.misAcuerdosFiltroHasta = '';
    host.misAcuerdosPageSize = 5;
    host.misAcuerdosVisibles = 5;
    host.misAcuerdosExpandidos = new Set();
    host.catalogoEditandoPos = null;
    host.acuerdoFlotanteActual = null;
    host.scoreNotifActive = false;
    host.scoreNotifShownIds = new Set();
    host._syncInProgress = false;
    host._autoSyncIntervalId = null;
    host._contactoIdImpugnarApoyo = null;
    host._alertHubState = { showAll: false, expandedDetailId: null };
    host.metodosPagoRuana = {
        bizum_num: window.RUANA_BIZUM_NUM || '642868261',
        iban: window.RUANA_IBAN || 'ES8915830001119028625152',
        qr_revolut_path: window.RUANA_QR_REVOLUT_PATH || '/static/images/PayPal.png'
    };
  }

modules.sync = {
    initState: initState,
    runWarmupSync: runWarmupSync,
    getSyncElements: getSyncElements,
    setSectionsSyncing: setSectionsSyncing,
    fetchAliadoSnapshot: fetchAliadoSnapshot,
    fetchSolicitudesSnapshot: fetchSolicitudesSnapshot,
    refreshAfterAction: refreshAfterAction,
    initOnboarding: initOnboarding,
    startAutoSync: startAutoSync,
    loadData: loadData,
  
    fetchDirectorioSnapshot: fetchDirectorioSnapshot,
    fetchCentroComunicacionSnapshot: fetchCentroComunicacionSnapshot,
    setPanelLoading: setPanelLoading,
    init: init,
    render: render,
    handleLogout: handleLogout,
    copyCode: copyCode,
    closeCodeModal: closeCodeModal,
    normalizarEstado: normalizarEstado,
    escapeHtml: escapeHtml,

    getCodigoFromURL: getCodigoFromURL,
    fetchAliadoDatos: fetchAliadoDatos,
    bootstrapPrivatePanel: bootstrapPrivatePanel,
};

  // El script inline de aliado.html corre antes que los defer; PrivatePanel ya está en window.
  if (typeof global.PrivatePanel !== 'undefined') {
    bootstrapPrivatePanel();
  }
})(typeof window !== 'undefined' ? window : globalThis);
