/**
 * Módulo AdminPanel `resumen` (Campamento Base / AdminShell MODULE_DEFS).
 * Estado global, movimiento 24h y métricas de salud.
 * AdminPanel conserva fachadas delgadas que delegan aquí.
 * La orquestación de fetch (cargarDesdeApi) permanece en AdminPanel.
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

  modules.resumen = {
    renderEstadoGlobal: renderEstadoGlobal,
    renderMovimiento: renderMovimiento,
    renderMovimientoError: renderMovimientoError,
    renderMetricas: renderMetricas,
  };
})(typeof window !== 'undefined' ? window : globalThis);
