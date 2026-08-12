/**
 * Módulo shell `inicio` del PrivatePanel (Campamento Base).
 * Métricas, score/estado, alerta de score y callout de cambio de score.
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

  function formatScoreMotivo(motivo) {
    var key = String(motivo || '').trim();
    if (!key) return 'actualización de reglas RUANA';
    var mappings = [
      [/^aliado_referido_registro_valido/, 'registro válido de un aliado referido'],
      [/^encargo_completado_apoyo_pagado/, 'encargo completado con apoyo RUANA validado'],
      [/^referido_encargo_completado_gen/, 'impacto positivo de tu red de referidos'],
      [/^regla4_/, 'constancia de encargos completados en el mes'],
      [/^regla5_/, 'respuesta rápida y buena atención en chat'],
      [/^regla6_/, 'gestión efectiva de un contacto urgente'],
      [/^regla7_/, 'declaración oportuna del cierre del trabajo'],
      [/^regla8_/, 'actividad constante en la app'],
      [/^invitacion_oficio_usada/, 'invitar a un nuevo aliado que se registró'],
      [/^contacto_cerrado_no_concretado/, 'cierre de contacto sin trabajo concretado'],
      [/^contacto_sin_cerrar_7d/, 'contacto abierto sin cierre durante 7 días'],
      [/^contacto_sin_cerrar_21d/, 'contacto abierto sin cierre durante 21 días'],
      [/^descendiente_entra_competencia_gen/, 'impacto por riesgo dentro de tu red'],
      [/^chat_sin_respuesta_48h_/, 'chat sin respuesta durante 48 horas'],
      [/^sin_acceso_7d_/, 'inactividad en la app por 7 días'],
      [/^chat_agotado_sin_resultado_/, 'chat agotado sin cierre de resultado'],
      [/^disputa_perdida_/, 'disputa de importe resuelta en contra'],
      [/^comprobante_apoyo_3d_/, 'demora en subir comprobante de apoyo RUANA']
    ];
    for (var i = 0; i < mappings.length; i++) {
      if (mappings[i][0].test(key)) return mappings[i][1];
    }
    return key.replace(/_/g, ' ');
  }

  function getScoreNotifVariants(isUp) {
    if (isUp) {
      return [
        'Tu reputación creció gracias a {{reason}}.',
        'Buen trabajo: el cambio se debe a {{reason}}.',
        'Tu score mejoró por {{reason}}.',
        'Has ganado puntos por {{reason}}.'
      ];
    }
    return [
      'El ajuste se debe a {{reason}}.',
      'Tu score bajó por {{reason}}.',
      'Cambio registrado por {{reason}}.',
      'Puedes recuperarlo con próximos cierres: {{reason}}.'
    ];
  }

  function positionScoreCallout(callout) {
    var anchor = document.getElementById('inicio-score-pill');
    if (!callout || !anchor) return;
    var rect = anchor.getBoundingClientRect();
    var gap = 14;
    var viewportPad = 12;
    var prevVisibility = callout.style.visibility;
    callout.style.visibility = 'hidden';
    callout.classList.add('show');

    var calloutW = callout.offsetWidth;
    var calloutH = callout.offsetHeight;
    var left = rect.left + (rect.width / 2) - (calloutW / 2);
    left = Math.max(viewportPad, Math.min(left, window.innerWidth - calloutW - viewportPad));

    var top = rect.top - calloutH - gap;
    var isBelow = false;
    if (top < viewportPad) {
      top = rect.bottom + gap;
      isBelow = true;
    }
    callout.classList.toggle('is-below', isBelow);
    callout.style.top = Math.round(top) + 'px';
    callout.style.left = Math.round(left) + 'px';
    callout.style.setProperty('--score-callout-arrow-x', Math.round(rect.left + (rect.width / 2) - left) + 'px');
    callout.style.visibility = prevVisibility || '';
  }

  function teardownScoreCallout(host, callout, anchor) {
    if (host && host._scoreCalloutReposition) {
      window.removeEventListener('resize', host._scoreCalloutReposition);
      window.removeEventListener('scroll', host._scoreCalloutReposition, true);
      document.removeEventListener('aliado-module-change', host._scoreCalloutReposition);
      host._scoreCalloutReposition = null;
    }
    if (anchor) anchor.classList.remove('is-highlighted');
    if (callout) callout.remove();
  }

  function markNotificationRead(host, notifId) {
    var codigo = (host && (host.codigoAliado || (host.aliado && host.aliado.codigo))) || '';
    if (!codigo || !notifId) return Promise.resolve();
    try {
      var apiBase = getApiBaseSafe();
      return fetch(
        apiBase + '/api/aliados/' + encodeURIComponent(codigo) + '/notificaciones/' + encodeURIComponent(notifId) + '/leida',
        { method: 'POST', credentials: 'same-origin', headers: getAuthHeadersSafe() }
      ).catch(function () {});
    } catch (_) {
      return Promise.resolve();
    }
  }

  function maybeShowScoreChangeNotification(host) {
    if (!host) return;
    if (host.scoreNotifActive) return;
    var scoreAnchor = document.getElementById('inicio-score-pill');
    if (!scoreAnchor) return;
    var notifs = Array.isArray(host.notificaciones) ? host.notificaciones : [];
    var pendientes = notifs
      .filter(function (n) { return n && n.tipo === 'score_change' && Number(n.leida) === 0; })
      .sort(function (a, b) {
        return new Date(a.creado_en || 0) - new Date(b.creado_en || 0);
      });
    if (pendientes.length === 0) return;
    if (!host.scoreNotifShownIds) host.scoreNotifShownIds = new Set();
    var notif = pendientes.find(function (n) {
      var moveId = n.metadata && n.metadata.movimiento_id ? String(n.metadata.movimiento_id) : ('notif-' + n.id);
      return !host.scoreNotifShownIds.has(moveId);
    });
    if (!notif) return;

    if (global.AliadoShell && typeof global.AliadoShell.show === 'function') {
      global.AliadoShell.show('inicio', { skipScroll: true, instant: true });
    }

    var deltaRaw = Number(notif.metadata && notif.metadata.delta);
    var delta = Number.isFinite(deltaRaw) ? deltaRaw : 0;
    if (!delta) return;
    var isUp = delta > 0;
    var deltaText = (delta > 0 ? '+' : '') + delta + ' puntos';
    var reason = formatScoreMotivo(notif.metadata && notif.metadata.motivo);
    var variants = getScoreNotifVariants(isUp);
    var template = variants[Math.floor(Math.random() * variants.length)];
    var message = template.replace('{{reason}}', reason);
    var iconSvg = isUp
      ? '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/></svg>'
      : '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 18 13.5 8.5 8.5 13.5 1 6"/><polyline points="17 18 23 18 23 12"/></svg>';

    var callout = document.createElement('div');
    callout.className = 'ruana-score-callout ruana-score-callout--' + (isUp ? 'up' : 'down');
    callout.setAttribute('role', 'status');
    callout.innerHTML =
      '<div class="ruana-score-callout__inner">' +
        '<span class="ruana-score-callout__icon" aria-hidden="true">' + iconSvg + '</span>' +
        '<div class="ruana-score-callout__body">' +
          '<div class="ruana-score-callout__title">Score RUANA <span class="ruana-score-callout__delta">' + deltaText + '</span></div>' +
          '<p class="ruana-score-callout__copy">' + message + '</p>' +
        '</div>' +
        '<button type="button" class="ruana-score-callout__close" aria-label="Cerrar notificación">' +
          '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>' +
        '</button>' +
      '</div>' +
      '<span class="ruana-score-callout__arrow" aria-hidden="true"></span>';
    document.body.appendChild(callout);
    scoreAnchor.classList.add('is-highlighted');

    var reposition = function () { positionScoreCallout(callout); };
    host._scoreCalloutReposition = reposition;
    window.addEventListener('resize', reposition);
    window.addEventListener('scroll', reposition, true);
    document.addEventListener('aliado-module-change', reposition);

    positionScoreCallout(callout);
    requestAnimationFrame(function () {
      positionScoreCallout(callout);
      callout.classList.add('show');
    });
    host.scoreNotifActive = true;

    var moveId = notif.metadata && notif.metadata.movimiento_id
      ? String(notif.metadata.movimiento_id)
      : ('notif-' + notif.id);
    host.scoreNotifShownIds.add(moveId);
    notif.leida = 1;
    markNotificationRead(host, notif.id);

    var closeCallout = function () {
      callout.classList.remove('show');
      setTimeout(function () {
        teardownScoreCallout(host, callout, scoreAnchor);
        host.scoreNotifActive = false;
        maybeShowScoreChangeNotification(host);
      }, 240);
    };
    callout.querySelector('.ruana-score-callout__close').addEventListener('click', closeCallout);
    setTimeout(closeCallout, 7000);
  }

  /**
   * Pinta métricas del home, color/estado del score y alerta score < 50.
   * @param {object} host PrivatePanel (aliado, notificaciones, scoreNotif*)
   */
  function renderMetricas(host) {
    if (!host) return;
    var aliado = host.aliado;
    var solicitudesEnviadasContestadas = (aliado && typeof aliado.solicitudes_enviadas_contestadas === 'number')
      ? aliado.solicitudes_enviadas_contestadas
      : 0;
    var referidosCount = (aliado && typeof aliado.referidos_count === 'number')
      ? aliado.referidos_count
      : 0;
    var score = aliado && typeof aliado.score === 'number' ? aliado.score : 0;

    var mapping = {
      'metric-solicitudes': solicitudesEnviadasContestadas,
      'metric-invitaciones': referidosCount,
      'metric-score': score
    };
    Object.keys(mapping).forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.textContent = mapping[id];
    });

    // Color del Score RUANA por etiqueta (ÉLITE ≥350, DESTACADO ≥200, ESTABLE ≥50, EN RIESGO ≥15, COMPETENCIA <15)
    var cardScore = document.getElementById('metrica-card-score');
    if (cardScore) {
      cardScore.classList.remove(
        'score-elite', 'score-destacado', 'score-prioritario',
        'score-estable', 'score-riesgo', 'score-competencia'
      );
      if (score >= 350) cardScore.classList.add('score-elite');
      else if (score >= 200) cardScore.classList.add('score-destacado');
      else if (score >= 50) cardScore.classList.add('score-estable');
      else if (score >= 15) cardScore.classList.add('score-riesgo');
      else cardScore.classList.add('score-competencia');
    }
    // Alerta automática cuando score < 50
    var alerta = document.getElementById('score-alerta-panel');
    if (alerta) alerta.classList.toggle('visible', score < 50);
    if (typeof global.RuanaUI !== 'undefined') global.RuanaUI.initIcons();
    maybeShowScoreChangeNotification(host);
  }

  /**
   * Refresca superficie inicio del shell (identidad, tareas, badges).
   * Los quick actions (data-aliado-goto / invitar) los enlaza el shell y PrivatePanel.
   */
  function refreshInicioSurface() {
    if (global.AliadoShell && typeof global.AliadoShell.refresh === 'function') {
      global.AliadoShell.refresh();
    }
  }

  function render(host) {
    renderMetricas(host);
    refreshInicioSurface();
  }

  function refresh(host) {
    renderMetricas(host);
    refreshInicioSurface();
  }

  modules.inicio = {
    render: render,
    refresh: refresh,
    renderMetricas: renderMetricas,
    maybeShowScoreChangeNotification: maybeShowScoreChangeNotification,
    formatScoreMotivo: formatScoreMotivo,
    getScoreNotifVariants: getScoreNotifVariants,
    positionScoreCallout: positionScoreCallout,
    teardownScoreCallout: function (host, callout, anchor) {
      return teardownScoreCallout(host, callout, anchor);
    },
    markNotificationRead: markNotificationRead,
  };
})(typeof window !== 'undefined' ? window : globalThis);
