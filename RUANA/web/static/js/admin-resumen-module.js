/**
 * Módulo AdminPanel `resumen` (Campamento Base / AdminShell MODULE_DEFS).
 * Estado global, movimiento 24h y métricas de salud.
 * AdminPanel conserva fachadas delgadas que delegan aquí.
 * Orquestación de carga (cargarDesdeApi) vive aquí / en módulos admin-*.
 */
(function (global) {
  'use strict';

  var modules = global.RuanaAdminModules = global.RuanaAdminModules || {
    resumen: null,
    operaciones: null,
    red: null,
    sistema: null,
  };

  function setText(id, value) {
    var el = document.getElementById(id);
    if (el) el.textContent = value;
  }

  /**
   * Renderiza indicadores de estado global desde la API real.
   * @param {object} data { indicadores }
   */
  function renderEstadoGlobal(data) {
    var indicadores = (data && data.indicadores) ? data.indicadores : {};
    setText('total-aliados', indicadores.totalAliados);
    setText('aliados-activos', indicadores.aliadosActivos);
    setText('retadores-count', indicadores.retadores);
    setText('en-espera-count', indicadores.enEspera);
    setText('en-riesgo-count', indicadores.enRiesgo);
    setText('solicitudes-activas', indicadores.solicitudesActivas);
    setText(
      'oficios-ocupados',
      indicadores.oficiosOcupados !== undefined && indicadores.oficiosOcupados !== null
        ? indicadores.oficiosOcupados
        : '-'
    );
    setText(
      'total-grupos',
      indicadores.totalGrupos !== undefined && indicadores.totalGrupos !== null
        ? indicadores.totalGrupos
        : '0'
    );
    var desgloseEl = document.getElementById('total-grupos-desglose');
    if (desgloseEl) {
      var a = indicadores.gruposActivos != null ? indicadores.gruposActivos : 0;
      var c = indicadores.gruposEnCompetencia != null ? indicadores.gruposEnCompetencia : 0;
      var d = indicadores.gruposDisueltos != null ? indicadores.gruposDisueltos : 0;
      desgloseEl.textContent = a + ' activos, ' + c + ' en competencia, ' + d + ' disueltos';
    }
    var estadoLabel = indicadores.estadoSistema || 'Estable';
    var estadoEl = document.getElementById('estado-sistema-label');
    if (estadoEl) estadoEl.textContent = estadoLabel;
    var container = estadoEl && estadoEl.closest('.estado-sistema');
    if (container) {
      container.classList.remove('estable', 'alerta', 'crítico');
      var clase = (estadoLabel === 'Crítico' || estadoLabel === 'Alerta')
        ? estadoLabel.toLowerCase()
        : 'estable';
      container.classList.add(clase);
    }
  }

  function renderMovimientoError(message) {
    var errEl = document.getElementById('movimiento-24h-error');
    var gridEl = document.getElementById('movimiento-grid');
    if (errEl) {
      errEl.textContent = message || '';
      errEl.style.display = message ? 'block' : 'none';
    }
    if (gridEl) gridEl.style.display = message ? 'none' : '';
  }

  /**
   * Actualiza la UI de Movimiento del Sistema (24h): resumen y desglose por hora.
   * Si host se pasa, guarda _lastMovimiento24h en el panel.
   * @param {object} [host] AdminPanel opcional
   * @param {object} data { movimiento24h, movimiento24hHoras }
   */
  function renderMovimiento(hostOrData, maybeData) {
    var host = null;
    var data = hostOrData;
    if (maybeData !== undefined) {
      host = hostOrData;
      data = maybeData;
    }
    var mov = (data && data.movimiento24h) ? data.movimiento24h : null;
    var porHora = (data && data.movimiento24hHoras) ? data.movimiento24hHoras : null;
    if (mov && host) host._lastMovimiento24h = mov;
    if (mov) {
      setText('mov-sol-nuevas', mov.solicitudes ? mov.solicitudes.nuevas : '-');
      setText('mov-sol-atendidas', mov.solicitudes ? mov.solicitudes.atendidas : '-');
      setText('mov-sol-sin-respuesta', mov.solicitudes ? mov.solicitudes.sin_respuesta : '-');
      setText('mov-inv-generadas', mov.invitaciones ? mov.invitaciones.generadas : '-');
      setText('mov-inv-usadas', mov.invitaciones ? mov.invitaciones.usadas : '-');
      setText('mov-inv-expiradas', mov.invitaciones ? mov.invitaciones.expiradas : '-');
      var top = (mov.top_invitadores || []).slice(0, 3);
      for (var i = 0; i < 3; i++) {
        var t = top[i];
        setText('mov-top-' + (i + 1) + '-label', t ? t.nombre : '—');
        setText('mov-top-' + (i + 1) + '-value', t ? t.total : '-');
      }
    } else {
      setText('mov-sol-nuevas', '-');
      setText('mov-sol-atendidas', '-');
      setText('mov-sol-sin-respuesta', '-');
      setText('mov-inv-generadas', '-');
      setText('mov-inv-usadas', '-');
      setText('mov-inv-expiradas', '-');
      for (var j = 1; j <= 3; j++) {
        setText('mov-top-' + j + '-label', '—');
        setText('mov-top-' + j + '-value', '-');
      }
    }
    var tbody = document.getElementById('movimiento-24h-tbody');
    if (tbody) {
      tbody.innerHTML = '';
      if (porHora) {
        var horas = Array.from({ length: 24 }, function (_, idx) {
          return idx < 10 ? '0' + idx : '' + idx;
        });
        horas.forEach(function (h) {
          var row = porHora[h] || {};
          var n = function (v) {
            return v != null && v !== '' ? Number(v) : 0;
          };
          var tr = document.createElement('tr');
          tr.innerHTML = '<td>' + h + ':00</td><td>' + n(row.nuevas) + '</td><td>' + n(row.atendidas) + '</td><td>' + n(row.sin_respuesta) + '</td><td>' + n(row.invitaciones_generadas) + '</td><td>' + n(row.invitaciones_usadas) + '</td><td>' + n(row.invitaciones_expiradas) + '</td><td>' + n(row.contactos_creados) + '</td>';
          tbody.appendChild(tr);
        });
      }
    }
  }

  /**
   * Renderiza métricas de salud desde GET /api/metricas-salud.
   * @param {object} data { metricas }
   */
  function renderMetricas(data) {
    var m = (data && data.metricas) ? data.metricas : null;
    if (m) {
      setText('metrica-ratio-sol-inv', m.ratio_solicitud_invitacion != null ? m.ratio_solicitud_invitacion : '-');
      setText('metrica-ratio-inv-reg', m.ratio_invitacion_registro != null ? m.ratio_invitacion_registro : '-');
      setText('metrica-oficios-saturados', m.oficios_saturados != null ? m.oficios_saturados : '-');
      setText('metrica-oficios-disponibles', m.oficios_disponibles != null ? m.oficios_disponibles : '-');
      setText('metrica-zona-demanda', m.zona_mayor_demanda != null ? m.zona_mayor_demanda : '-');
      setText('metrica-retencion', m.tasa_retencion != null ? m.tasa_retencion + '%' : '-');
    } else {
      setText('metrica-ratio-sol-inv', '-');
      setText('metrica-ratio-inv-reg', '-');
      setText('metrica-oficios-saturados', '-');
      setText('metrica-oficios-disponibles', '-');
      setText('metrica-zona-demanda', '-');
      setText('metrica-retencion', '-');
    }
  }

  async function cargarDesdeApi(host) {
      const loader = document.getElementById('admin-loader');
      document.body.classList.add('admin-is-loading');
      if (loader) loader.style.display = 'flex';
      const authHeaders = AdminAuthenticator.getAdminAuthHeaders();
      const fetchOpts = { method: 'GET', credentials: 'same-origin', headers: authHeaders };
      try {
          const controller = new AbortController();
          const timeoutId = setTimeout(() => controller.abort(), 5000);
          const stats24hFetch = fetch('/api/admin/stats-24h', {
              method: 'GET',
              credentials: 'same-origin',
              headers: authHeaders,
              signal: controller.signal
          }).then(r => {
              clearTimeout(timeoutId);
              return r;
          }).then(r => r.ok ? r.json().catch(() => null) : null).catch(err => {
              clearTimeout(timeoutId);
              return { _error: err.name === 'AbortError' ? 'timeout' : 'fail' };
          });

          const fetchPromises = [
              fetch('/api/admin/dashboard-summary', fetchOpts),
              fetch('/api/stats', fetchOpts),
              fetch('/api/aliados/listar', fetchOpts),
              fetch('/api/admin/pending-users', fetchOpts),
              fetch('/api/metricas-salud', fetchOpts),
              fetch('/api/eventos-recientes', fetchOpts),
              fetch('/api/admin/payment-conflicts', fetchOpts),
              fetch('/api/admin/pagos-apoyo', fetchOpts),
              fetch('/api/admin/pagos-en-revision', fetchOpts),
              fetch('/api/admin/stripe/resumen', fetchOpts),
              fetch('/api/admin/solicitudes', fetchOpts),
              fetch('/api/admin/chats?limite=10&offset=0', fetchOpts),
              fetch('/api/admin/conversations?limite=100', fetchOpts),
              fetch('/api/admin/competencias-activas', fetchOpts),
              fetch('/api/admin/competencias-pendientes', fetchOpts),
              fetch('/api/admin/competencias-historial?limite=30', fetchOpts),
              stats24hFetch,
              fetch('/api/admin/invitaciones-recientes?limite=15', fetchOpts),
              fetch('/api/admin/invitacion-campanas?limite=30', fetchOpts),
              fetch('/api/admin/metodos-pago', fetchOpts),
              fetch('/api/admin/suplentes-espera', fetchOpts),
              fetch('/api/admin/centro-comunicacion?limite=120', fetchOpts),
              fetch('/api/admin/aliados-eliminados', fetchOpts)
          ];
          const settled = await Promise.allSettled(fetchPromises);
          const responses = settled.map((r, i) => (r.status === 'fulfilled' ? r.value : null));

          const any401 = responses.some(r => r && typeof r.status === 'number' && r.status === 401);
          if (any401) {
              host._adminSessionExpired();
              return;
          }

          async function parseResponse(r, isStats24h) {
              if (isStats24h) return r;
              if (!r || typeof r.ok !== 'boolean') return null;
              if (!r.ok) return null;
              return r.json().catch(() => null);
          }
          const idx16 = responses[16];
          const [dashboardData, statsData, aliadosData, pendientesData, metricasData, eventosData, conflictosData, pagosApoyoData, pagosEnRevisionData, stripeResumenData, solicitudesData, chatsData, contactosChatData, competenciasData, competenciasPendientesData, competenciasHistorialData, stats24hData, invitacionesRecData, campanasData, metodosPagoData, suplentesEsperaData, centroComData, eliminadosData] = await Promise.all([
              parseResponse(responses[0], false),
              parseResponse(responses[1], false),
              parseResponse(responses[2], false),
              parseResponse(responses[3], false),
              parseResponse(responses[4], false),
              parseResponse(responses[5], false),
              parseResponse(responses[6], false),
              parseResponse(responses[7], false),
              parseResponse(responses[8], false),
              parseResponse(responses[9], false),
              parseResponse(responses[10], false),
              parseResponse(responses[11], false),
              parseResponse(responses[12], false),
              parseResponse(responses[13], false),
              parseResponse(responses[14], false),
              parseResponse(responses[15], false),
              Promise.resolve(idx16),
              parseResponse(responses[17], false),
              parseResponse(responses[18], false),
              parseResponse(responses[19], false),
              parseResponse(responses[20], false),
              parseResponse(responses[21], false),
              parseResponse(responses[22], false)
          ]);

          // Pendientes de validación (unir API + lista por código)
          const pendientesFromApi = (pendientesData && pendientesData.status === 'success' && Array.isArray(pendientesData.aliados)) ? pendientesData.aliados : [];
          const pendientesFromLista = (aliadosData && Array.isArray(aliadosData.aliados)) ? aliadosData.aliados.filter(a => (a.estado || '').toLowerCase() === 'pendiente_validacion') : [];
          const byCodigoPend = new Map();
          pendientesFromLista.forEach(a => { if (a && a.codigo) byCodigoPend.set(String(a.codigo), a); });
          pendientesFromApi.forEach(a => { if (a && a.codigo) byCodigoPend.set(String(a.codigo), a); });
          const pendientes = Array.from(byCodigoPend.values());

          // Prioridad: dashboard-summary para indicadores del dashboard global
          const dashOk = dashboardData && !dashboardData.status;
          const statsOk = statsData && statsData.status === 'success';
          const tieneDatosCriticos = dashOk || statsOk;
          if (!tieneDatosCriticos) {
              host.showToast('Error de conexión. Comprueba la red.', 'error');
          }
          const totalGruposRaw = dashOk ? dashboardData.grupos : (statsOk ? statsData.total_grupos : undefined);
          const totalGrupos = typeof totalGruposRaw === 'number' ? totalGruposRaw : (totalGruposRaw && typeof totalGruposRaw.total === 'number' ? totalGruposRaw.total : 0);
          const indicadores = {
              totalAliados: dashOk ? (dashboardData.total_users ?? 0) : (statsOk ? statsData.total_aliados : (aliadosData && aliadosData.total) || 0),
              aliadosActivos: dashOk ? (dashboardData.active_users ?? 0) : (statsOk ? statsData.aliados_activos : 0),
              retadores: dashOk ? (dashboardData.retadores ?? dashboardData.suplentes ?? 0) : (statsOk ? (statsData.retadores || statsData.suplentes || 0) : 0),
              enEspera: dashOk ? (dashboardData.en_espera ?? 0) : (statsOk ? (statsData.en_espera || 0) : 0),
              enRiesgo: dashOk ? (dashboardData.en_riesgo ?? 0) : (statsOk ? (statsData.en_riesgo || 0) : 0),
              solicitudesActivas: dashOk ? (dashboardData.solicitudes_activas ?? 0) : (statsOk ? (statsData.solicitudes_activas || 0) : 0),
              pendientesValidacion: pendientes.length,
              oficiosOcupados: dashOk ? (dashboardData.oficios_ocupados ?? '-') : (statsOk ? (statsData.oficios_ocupados ?? '-') : '-'),
              totalGrupos: dashOk ? (dashboardData.grupos ?? 0) : totalGrupos,
              gruposActivos: dashOk ? (dashboardData.grupos_activos ?? 0) : (statsOk ? (statsData.grupos_activos ?? 0) : 0),
              gruposEnCompetencia: dashOk ? (dashboardData.grupos_en_competencia ?? 0) : (statsOk ? (statsData.grupos_en_competencia ?? 0) : 0),
              gruposDisueltos: dashOk ? (dashboardData.grupos_disueltos ?? 0) : (statsOk ? (statsData.grupos_disueltos ?? 0) : 0),
              estadoSistema: (() => {
                  const e = dashOk ? (dashboardData.estado_sistema || 'Estable') : (statsOk ? (statsData.estado_sistema || 'Estable') : 'Estable');
                  const low = String(e).toLowerCase();
                  if (low === 'estable' || low === 'alerta') return e.charAt(0).toUpperCase() + e.slice(1).toLowerCase();
                  if (low === 'crítico' || low === 'critico') return 'Crítico';
                  return 'Estable';
              })()
          };

          host.renderEstadoGlobal({ indicadores });
          const tieneMovimiento24h = stats24hData && !stats24hData._error && (stats24hData.status === 'success' || stats24hData.solicitudes != null || stats24hData.invitaciones != null || (Array.isArray(stats24hData.top_invitadores) && stats24hData.top_invitadores.length > 0));
          if (stats24hData && stats24hData._error) {
              host.renderMovimientoError(stats24hData._error === 'timeout' ? 'No se pudieron cargar estadísticas' : 'Sin datos disponibles');
          } else if (tieneMovimiento24h) {
              host.renderMovimientoError(null);
              host.renderMovimiento({
                  movimiento24h: {
                      solicitudes: stats24hData.solicitudes || { nuevas: 0, atendidas: 0, sin_respuesta: 0 },
                      invitaciones: stats24hData.invitaciones || { generadas: 0, usadas: 0, expiradas: 0 },
                      top_invitadores: stats24hData.top_invitadores || []
                  },
                  movimiento24hHoras: null
              });
          } else {
              host.renderMovimientoError('Sin datos disponibles');
          }
          const metricasPayload = (metricasData && metricasData.status === 'success' && metricasData.metricas != null)
              ? metricasData.metricas
              : { ratio_solicitud_invitacion: 0, ratio_invitacion_registro: 0, oficios_saturados: 0, oficios_disponibles: 0, zona_mayor_demanda: '—', tasa_retencion: 0 };
          host.renderMetricas({ metricas: metricasPayload });
          host.renderPendientesValidacion(pendientes);
          host.renderAliadosEliminados((eliminadosData && eliminadosData.status === 'success' && Array.isArray(eliminadosData.aliados)) ? eliminadosData.aliados : []);
          host._aliadosData = ((aliadosData && aliadosData.aliados) || []).filter(a => !host.esAliadoPlaceholder(a));
          host.renderAliadosJerarquia();
          host.renderEventos((eventosData && eventosData.status === 'success' && Array.isArray(eventosData.eventos)) ? eventosData.eventos : []);
          const permisos = (statsData && Array.isArray(statsData.permisos)) ? statsData.permisos : ['leer', 'escribir', 'eliminar', 'configurar'];
          host.applyPermisosUI(permisos);
          host.renderConflictosPago((conflictosData && conflictosData.status === 'success' && Array.isArray(conflictosData.conflictos)) ? conflictosData.conflictos : []);
          host.renderPagosApoyo((pagosApoyoData && pagosApoyoData.status === 'success' && Array.isArray(pagosApoyoData.pagos)) ? pagosApoyoData.pagos : []);
          host.renderPagosEnRevision((pagosEnRevisionData && pagosEnRevisionData.status === 'success' && Array.isArray(pagosEnRevisionData.pagos)) ? pagosEnRevisionData.pagos : []);
          host.renderStripeResumen(stripeResumenData && stripeResumenData.status === 'success' ? stripeResumenData : null);
          host.renderSolicitudesAdmin(Array.isArray(solicitudesData) ? solicitudesData : (solicitudesData && Array.isArray(solicitudesData.solicitudes) ? solicitudesData.solicitudes : []));
          host.renderInvitacionesRecientes(invitacionesRecData && invitacionesRecData.status === 'success' && Array.isArray(invitacionesRecData.invitaciones) ? invitacionesRecData.invitaciones : []);
          host.renderCampanasInvitacion(campanasData && campanasData.status === 'success' && Array.isArray(campanasData.campanas) ? campanasData.campanas : []);
          host.renderMetodosPago((metodosPagoData && metodosPagoData.status === 'success' && metodosPagoData.metodos) ? metodosPagoData.metodos : null);
          host.renderCompetenciasActivas((competenciasData && competenciasData.status === 'success' && Array.isArray(competenciasData.competencias)) ? competenciasData.competencias : []);
          host.renderCompetenciasPendientes((competenciasPendientesData && competenciasPendientesData.status === 'success' && Array.isArray(competenciasPendientesData.pendientes)) ? competenciasPendientesData.pendientes : []);
          host.renderCompetenciasHistorial((competenciasHistorialData && competenciasHistorialData.status === 'success' && Array.isArray(competenciasHistorialData.historial)) ? competenciasHistorialData.historial : []);
          host.renderSuplentesEspera((suplentesEsperaData && suplentesEsperaData.status === 'success' && Array.isArray(suplentesEsperaData.aliados)) ? suplentesEsperaData.aliados : []);
          host._centroComunicacion = (centroComData && centroComData.status === 'success' && Array.isArray(centroComData.conversaciones)) ? centroComData.conversaciones : [];
          host.renderCentroComunicacionAdmin(host._centroComunicacion);
          let conversaciones = (chatsData && chatsData.status === 'success' && Array.isArray(chatsData.conversaciones)) ? chatsData.conversaciones : [];
          host._conversacionesList = conversaciones;
          host._conversacionesOffset = conversaciones.length;
          host._conversacionesHasMore = conversaciones.length >= 10;
          host.renderConversaciones(conversaciones);
          host.updateConversacionesPaginationUI();
          host.renderContactosChat((contactosChatData && contactosChatData.status === 'success' && Array.isArray(contactosChatData.contactos)) ? contactosChatData.contactos : []);
          if (conversaciones.length === 0) {
              host.cargarChatsFallback();
          }

          refreshCommandCenterPanels(host, {
              indicadores: indicadores,
              conflictos: (conflictosData && conflictosData.status === 'success' && Array.isArray(conflictosData.conflictos)) ? conflictosData.conflictos.length : 0,
              solicitudes: Array.isArray(solicitudesData) ? solicitudesData : (solicitudesData && Array.isArray(solicitudesData.solicitudes) ? solicitudesData.solicitudes : []),
              eventos: (eventosData && eventosData.status === 'success' && Array.isArray(eventosData.eventos)) ? eventosData.eventos.map(function (ev) {
                  return { fecha: ev.fecha || ev.creado_en, descripcion: ev.descripcion, tipo: ev.tipo };
              }) : [],
              incidencias: (centroComData && centroComData.status === 'success' && Array.isArray(centroComData.conversaciones))
                  ? centroComData.conversaciones.filter(function (c) { return String(c.tipo || '').toLowerCase() === 'incidencia'; })
                  : [],
              competencias: (competenciasData && competenciasData.status === 'success' && Array.isArray(competenciasData.competencias)) ? competenciasData.competencias : [],
              trabajos: conversaciones.length
          });
      } catch (e) {
          host.showToast('Error de conexión. Comprueba la red.', 'error');
          host._conversacionesList = [];
          host._conversacionesOffset = 0;
          host._conversacionesHasMore = false;
          host.renderConversaciones([]);
          host.updateConversacionesPaginationUI();
          host.cargarChatsFallback();
      } finally {
          if (loader) loader.style.display = 'none';
          document.body.classList.remove('admin-is-loading');
      }
}

async function refreshCommandCenterPanels(host, payload) {
      var cc = global.RuanaAdminModules && global.RuanaAdminModules.commandCenter;
      if (cc && typeof cc.refresh === 'function') {
          cc.refresh(host, payload || {});
      }
      var intel = global.RuanaAdminModules && global.RuanaAdminModules.intelligence;
      if (intel && typeof intel.refresh === 'function') {
          intel.refresh(host);
      }
      var redEx = global.RuanaAdminModules && global.RuanaAdminModules.redExplorer;
      if (redEx && typeof redEx.refresh === 'function') {
          redEx.refresh(host);
      }
      if (redEx && typeof redEx.initReferidosTree === 'function') {
          redEx.initReferidosTree(true);
      }
}

async function cargarChatsFallback(host) {
      const authHeaders = AdminAuthenticator.getAdminAuthHeaders();
      try {
          const r = await fetch('/api/admin/chats?limite=10&offset=0', { method: 'GET', credentials: 'same-origin', headers: authHeaders });
          const data = await (r.ok ? r.json().catch(() => null) : null);
          if (data && data.status === 'success' && Array.isArray(data.conversaciones)) {
              host._conversacionesList = data.conversaciones;
              host._conversacionesOffset = data.conversaciones.length;
              host._conversacionesHasMore = data.conversaciones.length >= 10;
              host.renderConversaciones(data.conversaciones);
              host.updateConversacionesPaginationUI();
          }
      } catch (e) { /* ignorar */ }
}

async function toggleDesglosePorHora(host, mostrar) {
      const container = document.getElementById('desglose-por-hora-container');
      const btnVer = document.getElementById('btn-toggle-desglose-hora');
      if (!container || !btnVer) return;
      if (mostrar) {
          if (!container.dataset.loaded) {
              const authHeaders = AdminAuthenticator.getAdminAuthHeaders();
              try {
                  const r = await fetch('/api/movimiento-24h-horas', { method: 'GET', credentials: 'same-origin', headers: authHeaders });
                  const data = await (r.ok ? r.json().catch(() => null) : Promise.resolve(null));
                  const porHora = (data && data.status === 'success' && data.por_hora) ? data.por_hora : null;
                  host.renderMovimiento({ movimiento24h: host._lastMovimiento24h || null, movimiento24hHoras: porHora });
                  container.dataset.loaded = '1';
              } catch (e) { console.error(e); }
          }
          container.style.display = 'block';
          btnVer.textContent = 'Ocultar desglose';
      } else {
          container.style.display = 'none';
          btnVer.textContent = 'Ver desglose por hora (24h)';
      }
}

function setupEventListeners(host) {
      const indicadorPend = document.getElementById('indicador-pendientes-validacion');
      if (indicadorPend) {
          indicadorPend.addEventListener('click', () => {
              const wrap = document.getElementById('pendientes-validacion-wrap');
              if (wrap) wrap.scrollIntoView({ behavior: 'smooth', block: 'start' });
          });
      }
      const indicadorEnEspera = document.getElementById('indicador-en-espera');
      if (indicadorEnEspera) {
          indicadorEnEspera.addEventListener('click', () => {
              const wrap = document.getElementById('suplentes-espera-wrap');
              if (wrap) wrap.scrollIntoView({ behavior: 'smooth', block: 'start' });
          });
      }
      // Navegación jerárquica aliados: Volver a CPs / Volver a grupos
      const btnVolverCPs = document.getElementById('aliados-btn-volver-cps');
      const btnVolverGrupos = document.getElementById('aliados-btn-volver-grupos');
      if (btnVolverCPs) btnVolverCPs.addEventListener('click', () => { host.aliadosNivel = 'cps'; host.aliadosCPSeleccionado = null; host.aliadosGrupoSeleccionado = null; host.aliadosGrupoNombreSeleccionado = null; host.aliadosOficioSeleccionado = null; host.renderAliadosJerarquia(); });
      if (btnVolverGrupos) btnVolverGrupos.addEventListener('click', () => { host.aliadosNivel = 'grupos'; host.aliadosGrupoSeleccionado = null; host.aliadosGrupoNombreSeleccionado = null; host.aliadosOficioSeleccionado = null; host.renderAliadosJerarquia(); });
      const btnVolverOficios = document.getElementById('aliados-btn-volver-oficios');
      if (btnVolverOficios) btnVolverOficios.addEventListener('click', () => { host.aliadosNivel = 'oficios'; host.aliadosOficioSeleccionado = null; host.renderAliadosJerarquia(); });


      document.addEventListener('click', function ruanaConversacionesClick(e) {
          var target = e.target;
          if (!target || !target.closest) return;
          var btnMas = target.closest('#btn-conversaciones-mostrar-mas');
          var btnMenos = target.closest('#btn-conversaciones-mostrar-menos');
          var panel = window._ruanaAdminPanel;
          if (btnMas && panel && typeof panel.loadMoreConversaciones === 'function') {
              e.preventDefault();
              e.stopPropagation();
              panel.loadMoreConversaciones();
              return;
          }
          if (btnMenos && panel && typeof panel.mostrarMenosConversaciones === 'function') {
              e.preventDefault();
              e.stopPropagation();
              panel.mostrarMenosConversaciones();
          }
      }, true);

      const ccRefreshBtn = document.getElementById('cc-admin-refresh');
      const ccSearch = document.getElementById('cc-admin-search');
      const ccStatus = document.getElementById('cc-admin-status');
      const ccUnread = document.getElementById('cc-admin-only-unread');
      if (ccRefreshBtn) ccRefreshBtn.addEventListener('click', () => host.cargarCentroComunicacionAdmin());
      if (ccSearch) ccSearch.addEventListener('input', () => host.renderCentroComunicacionAdmin(host._centroComunicacion || []));
      if (ccStatus) ccStatus.addEventListener('change', () => host.cargarCentroComunicacionAdmin());
      if (ccUnread) ccUnread.addEventListener('change', () => host.cargarCentroComunicacionAdmin());
      const ccClose = document.getElementById('cc-admin-modal-close');
      if (ccClose) ccClose.addEventListener('click', () => host.cerrarModalCentroComunicacionAdmin());
      const ccSend = document.getElementById('cc-admin-modal-send');
      if (ccSend) ccSend.addEventListener('click', () => host.responderCentroComunicacionAdmin());
      const ccUpd = document.getElementById('cc-admin-modal-update-status');
      if (ccUpd) ccUpd.addEventListener('click', () => host.actualizarEstadoCentroComunicacionAdmin());
      const ccDel = document.getElementById('cc-admin-modal-delete');
      if (ccDel) ccDel.addEventListener('click', () => host.eliminarCentroComunicacionAdmin());
      const ccModal = document.getElementById('modal-centro-comunicacion-admin');
      if (ccModal) ccModal.addEventListener('click', (e) => { if (e.target === ccModal) host.cerrarModalCentroComunicacionAdmin(); });

      host.setupAdminActionButtons();

      document.addEventListener('click', (e) => {
          const btn = e.target && e.target.closest ? e.target.closest('.btn-ver-documento-admin') : null;
          if (!btn) return;
          e.preventDefault();
          const storedUrl = btn.getAttribute('data-documento-url');
          if (storedUrl) host.abrirDocumentoAdmin(storedUrl);
      });

      const logoutBtn = document.getElementById('admin-logout-btn');
      if (logoutBtn) {
          logoutBtn.addEventListener('click', () => host.logout());
      }

      const changePasswordBtn = document.getElementById('admin-change-password-btn');
      if (changePasswordBtn) {
          changePasswordBtn.addEventListener('click', () => host.openChangePasswordModal());
      }
      host.setupChangePasswordForm();

      const cerrarDetalleBtn = document.getElementById('aliadoDetalleCerrar');
      if (cerrarDetalleBtn) {
          cerrarDetalleBtn.addEventListener('click', () => host.cerrarModalDetalle());
      }
      const cerrarCatalogoBtn = document.getElementById('aliadoCatalogoCerrar');
      if (cerrarCatalogoBtn) {
          cerrarCatalogoBtn.addEventListener('click', () => host.cerrarCatalogoServiciosModal());
      }
      const catalogoModal = document.getElementById('aliadoCatalogoModal');
      if (catalogoModal) {
          catalogoModal.addEventListener('click', (e) => {
              if (e.target === catalogoModal) host.cerrarCatalogoServiciosModal();
          });
      }

      const eliminarDetalleBtn = document.getElementById('aliadoDetalleEliminar');
      if (eliminarDetalleBtn) {
          eliminarDetalleBtn.addEventListener('click', () => host.confirmarEliminarPerfil());
      }

      const linajeCerrar = document.getElementById('linaje-drawer-cerrar');
      const linajeOverlay = document.getElementById('linaje-drawer-overlay');
      if (linajeCerrar) {
          linajeCerrar.addEventListener('click', () => host.cerrarLinajeDrawer());
      }
      if (linajeOverlay) {
          linajeOverlay.addEventListener('click', (e) => {
              if (e.target === linajeOverlay) host.cerrarLinajeDrawer();
          });
      }

      const btnResolverConfirm = document.getElementById('btn-resolver-conflicto-confirm');
      const btnResolverCancel = document.getElementById('btn-resolver-conflicto-cancel');
      if (btnResolverConfirm) btnResolverConfirm.addEventListener('click', () => host.confirmarResolverConflicto());
      if (btnResolverCancel) btnResolverCancel.addEventListener('click', () => {
          document.getElementById('modal-resolver-conflicto').style.display = 'none';
      });

      const modalDetalleConflicto = document.getElementById('modal-detalle-conflicto');
      const btnCerrarDetalleConflicto = document.getElementById('btn-cerrar-detalle-conflicto');
      if (btnCerrarDetalleConflicto) btnCerrarDetalleConflicto.addEventListener('click', () => { if (modalDetalleConflicto) modalDetalleConflicto.style.display = 'none'; });
      const btnFavorContratante = document.getElementById('btn-resolver-favor-contratante');
      const btnFavorProfesional = document.getElementById('btn-resolver-favor-profesional');
      const btnRechazarPrueba = document.getElementById('btn-rechazar-prueba');
      if (btnFavorContratante) btnFavorContratante.addEventListener('click', () => host.resolverConflictoDecision('contratante'));
      if (btnFavorProfesional) btnFavorProfesional.addEventListener('click', () => host.resolverConflictoDecision('profesional'));
      if (btnRechazarPrueba) btnRechazarPrueba.addEventListener('click', () => host.resolverConflictoDecision('rechazado'));

      const btnFiltrarSolicitudes = document.getElementById('btn-filtrar-solicitudes');
      if (btnFiltrarSolicitudes) btnFiltrarSolicitudes.addEventListener('click', () => host.cargarSolicitudesAdminConFiltros());

      const modalVerChat = document.getElementById('modal-ver-chat');
      const btnCerrarVerChat = document.getElementById('btn-cerrar-ver-chat');
      function cerrarModalChat() {
          if (modalVerChat) modalVerChat.style.display = 'none';
      }
      if (btnCerrarVerChat) {
          btnCerrarVerChat.addEventListener('click', (e) => { e.preventDefault(); e.stopPropagation(); cerrarModalChat(); });
      }
      if (modalVerChat) {
          modalVerChat.addEventListener('click', (e) => {
              if (e.target === modalVerChat) cerrarModalChat();
          });
          const modalChatContent = modalVerChat.querySelector('.modal-content');
          if (modalChatContent) modalChatContent.addEventListener('click', (e) => e.stopPropagation());
      }

      const modalRechazarPago = document.getElementById('modal-rechazar-pago');
      const btnConfirmarRechazar = document.getElementById('btn-confirmar-rechazar-pago');
      const btnCancelarRechazar = document.getElementById('btn-cancelar-rechazar-pago');
      if (btnConfirmarRechazar) btnConfirmarRechazar.addEventListener('click', () => host.confirmarRechazarPago());
      if (btnCancelarRechazar && modalRechazarPago) {
          btnCancelarRechazar.addEventListener('click', () => { modalRechazarPago.style.display = 'none'; });
      }
      if (modalRechazarPago) {
          modalRechazarPago.addEventListener('click', (e) => {
              if (e.target === modalRechazarPago) {
                  e.preventDefault();
                  e.stopPropagation();
                  modalRechazarPago.style.display = 'none';
              }
          });
      }

      const btnToggleDesglose = document.getElementById('btn-toggle-desglose-hora');
      const btnOcultarDesglose = document.getElementById('btn-ocultar-desglose-hora');
      const desgloseContainer = document.getElementById('desglose-por-hora-container');
      if (btnToggleDesglose && desgloseContainer) {
          btnToggleDesglose.addEventListener('click', () => host.toggleDesglosePorHora(true));
      }
      if (btnOcultarDesglose && desgloseContainer) {
          btnOcultarDesglose.addEventListener('click', () => host.toggleDesglosePorHora(false));
      }
}

function renderContactosChat(host, contactos) {
    const tbody = document.getElementById('tbody-contactos-chat');
    const emptyEl = document.getElementById('contactos-chat-empty');
    if (!tbody) return;
    tbody.innerHTML = '';
    const lista = Array.isArray(contactos) ? contactos : [];
    if (emptyEl) emptyEl.style.display = lista.length ? 'none' : 'block';
    lista.forEach((c) => {
        const tr = document.createElement('tr');
        const ultimo = c.ultimo_mensaje ? host.formatearHora(c.ultimo_mensaje) : '—';
        tr.innerHTML = `
            <td>${host.escapeHtml(String(c.id != null ? c.id : '—'))}</td>
            <td>${host.escapeHtml(c.solicitante || c.solicitante_codigo || '')}</td>
            <td>${host.escapeHtml(c.profesional || c.profesional_codigo || '')}</td>
            <td>${host.escapeHtml(c.servicio || '—')}</td>
            <td>${host.escapeHtml(c.estado || '—')}</td>
            <td>${host.escapeHtml(String(c.importe != null ? c.importe : (c.importe_final != null ? c.importe_final : '—')))}</td>
            <td>${host.escapeHtml(String(c.total_mensajes != null ? c.total_mensajes : (c.num_mensajes != null ? c.num_mensajes : 0)))}</td>
            <td>${ultimo}</td>
        `;
        tbody.appendChild(tr);
    });
}

function renderConversaciones(host, conversaciones) {
      const tbody = document.getElementById('tbody-conversaciones');
      const emptyEl = document.getElementById('conversaciones-empty');
      if (!tbody) return;
      tbody.innerHTML = '';
      const lista = Array.isArray(conversaciones) ? conversaciones : [];
      if (emptyEl) emptyEl.style.display = lista.length ? 'none' : 'block';
      lista.forEach(c => host.appendConversacionRow(tbody, c));
}

function appendConversacionRow(host, tbody, c) {
      const id = c.contacto_id != null ? c.contacto_id : c.id;
      const ultimoTexto = (c.ultimo_evento || c.ultimo_mensaje || '').substring(0, 80) + ((c.ultimo_evento || c.ultimo_mensaje || '').length > 80 ? '…' : '');
      const fecha = c.fecha_ultimo ? host.formatearHora(c.fecha_ultimo) : '—';
      const estadoHtml = c.acuerdo_completo
          ? '<span class="estado-pago-badge" style="background:rgba(34,197,94,0.25);color:#86efac;">ACUERDO</span>'
          : host.escapeHtml(c.estado || '—');
      const tr = document.createElement('tr');
      if (c.es_urgente) tr.style.background = 'rgba(180, 83, 9, 0.12)';
      tr.innerHTML = `
          <td>${id}</td>
          <td>${host.escapeHtml(c.solicitante || '')}</td>
          <td>${host.escapeHtml(c.profesional || '')}</td>
          <td>${estadoHtml}</td>
          <td>${host.escapeHtml(c.paso_actual || '—')}</td>
          <td>${host.escapeHtml(String(c.precio_acordado || '—'))}</td>
          <td>${host.escapeHtml(ultimoTexto) || '—'}</td>
          <td>${fecha}</td>
          <td style="white-space:nowrap;">
              <button type="button" class="btn-accion btn-ver-chat" data-contacto-id="${id}">Ver</button>
              <button type="button" class="btn-accion btn-eliminar-neg" data-contacto-id="${id}" style="margin-left:6px;color:#f87171;">Eliminar</button>
          </td>
      `;
      const btn = tr.querySelector('.btn-ver-chat');
      const btnDel = tr.querySelector('.btn-eliminar-neg');
      if (btn) btn.addEventListener('click', () => host.abrirModalVerChat(id));
      if (btnDel) btnDel.addEventListener('click', () => host.eliminarNegociacion(id));
      tbody.appendChild(tr);
}

function updateConversacionesPaginationUI(host) {
      const wrap = document.getElementById('conversaciones-load-more-wrap');
      const btnMas = document.getElementById('btn-conversaciones-mostrar-mas');
      const btnMenos = document.getElementById('btn-conversaciones-mostrar-menos');
      const noMas = document.getElementById('conversaciones-no-mas');
      const total = (host._conversacionesList || []).length;
      const hasMore = host._conversacionesHasMore === true;
      const puedeMostrarMenos = total > 10;
      if (wrap) wrap.style.display = (hasMore || puedeMostrarMenos) ? 'flex' : 'none';
      if (btnMas) {
          btnMas.style.display = hasMore ? 'inline-block' : 'none';
          btnMas.disabled = false;
      }
      if (btnMenos) {
          btnMenos.style.display = puedeMostrarMenos ? 'inline-block' : 'none';
      }
      if (noMas) noMas.style.display = (!hasMore && total > 0 && !puedeMostrarMenos) ? 'block' : 'none';
}

async function loadMoreConversaciones(host) {
      const btn = document.getElementById('btn-conversaciones-mostrar-mas');
      const tbody = document.getElementById('tbody-conversaciones');
      if (!tbody) return;
      const list = host._conversacionesList || [];
      const offsetGuardado = host._conversacionesOffset != null ? host._conversacionesOffset : 0;
      const offset = Math.max(offsetGuardado, list.length);
      const scrollY = window.scrollY !== undefined ? window.scrollY : document.documentElement.scrollTop;
      if (btn) btn.disabled = true;
      const authHeaders = AdminAuthenticator.getAdminAuthHeaders();
      try {
          const r = await fetch('/api/admin/chats?limite=10&offset=' + offset, { method: 'GET', credentials: 'same-origin', headers: authHeaders });
          const data = await (r.ok ? r.json().catch(() => null) : null);
          if (r.status === 401) { host._adminSessionExpired(); return; }
          if (!data || data.status !== 'success') return;
          const conversaciones = Array.isArray(data.conversaciones) ? data.conversaciones : [];
          const yaMostrados = new Set(list.map(c => c.contacto_id != null ? c.contacto_id : c.id));
          const nuevas = conversaciones.filter(c => {
              const id = c.contacto_id != null ? c.contacto_id : c.id;
              return id != null && !yaMostrados.has(id);
          });
          host._conversacionesList = list.concat(nuevas);
          host._conversacionesOffset = offset + conversaciones.length;
          host._conversacionesHasMore = conversaciones.length >= 10;
          nuevas.forEach(c => host.appendConversacionRow(tbody, c));
          host.updateConversacionesPaginationUI();
          requestAnimationFrame(() => { window.scrollTo(0, scrollY); });
      } finally {
          if (btn) btn.disabled = false;
      }
}

function mostrarMenosConversaciones(host) {
      const list = host._conversacionesList || [];
      if (list.length <= 10) return;
      host._conversacionesList = list.slice(0, 10);
      host._conversacionesOffset = 10;
      host._conversacionesHasMore = true;
      host.renderConversaciones(host._conversacionesList);
      host.updateConversacionesPaginationUI();
}

function formatearHora(host, timestamp) {
      /**
       * Convierte timestamp a formato legible
       */
      const fecha = new Date(timestamp);
      const ahora = new Date();
      const diff = Math.floor((ahora - fecha) / 1000); // segundos

      if (diff < 60) return 'Hace segundos';
      if (diff < 3600) return `Hace ${Math.floor(diff / 60)} min`;
      if (diff < 86400) return `Hace ${Math.floor(diff / 3600)} horas`;
      return fecha.toLocaleDateString();
}

modules.resumen = {
    renderEstadoGlobal: renderEstadoGlobal,
    renderMovimiento: renderMovimiento,
    renderMovimientoError: renderMovimientoError,
    renderMetricas: renderMetricas,
  
    cargarDesdeApi: cargarDesdeApi,
    cargarChatsFallback: cargarChatsFallback,
    toggleDesglosePorHora: toggleDesglosePorHora,
    setupEventListeners: setupEventListeners,
    renderConversaciones: renderConversaciones,
    renderContactosChat: renderContactosChat,
    appendConversacionRow: appendConversacionRow,
    updateConversacionesPaginationUI: updateConversacionesPaginationUI,
    loadMoreConversaciones: loadMoreConversaciones,
    mostrarMenosConversaciones: mostrarMenosConversaciones,
    formatearHora: formatearHora,
};
})(typeof window !== 'undefined' ? window : globalThis);
