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
        if (targetSections.includes('directorio')) jobs.push(host.fetchDirectorioSnapshot());
        if (targetSections.includes('alertas')) jobs.push(host.actualizarEstadoAlertas());
        if (targetSections.includes('centro')) jobs.push(host.fetchCentroComunicacionSnapshot());
        if (targetSections.includes('contactos')) jobs.push(host.cargarContactosPendientes());
        await Promise.all(jobs);

        if (targetSections.includes('perfil')) { host.renderPerfil(); host.renderGrupo(); }
        if (targetSections.includes('metricas')) host.renderMetricas();
        if (targetSections.includes('solicitudes')) host.renderSolicitudes();
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
    host.onboardingTour = new RuanaOnboardingTour(this);
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

  modules.sync = {
    runWarmupSync: runWarmupSync,
    getSyncElements: getSyncElements,
    setSectionsSyncing: setSectionsSyncing,
    fetchAliadoSnapshot: fetchAliadoSnapshot,
    fetchSolicitudesSnapshot: fetchSolicitudesSnapshot,
    refreshAfterAction: refreshAfterAction,
    initOnboarding: initOnboarding,
    startAutoSync: startAutoSync,
    loadData: loadData,
  };
})(typeof window !== 'undefined' ? window : globalThis);
