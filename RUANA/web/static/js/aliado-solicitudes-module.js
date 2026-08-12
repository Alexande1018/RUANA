/**
 * Módulo PrivatePanel `solicitudes` (Campamento Base).
 * Render de entrantes / propias / historial y tarjetas de solicitud.
 * PrivatePanel conserva fachadas delgadas que delegan aquí.
 * Acciones (invite code, envío) siguen en PrivatePanel.
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
  };

  function escapeHtmlSafe(host, str) {
    if (host && typeof host.escapeHtml === 'function') {
      return host.escapeHtml(str);
    }
    if (str == null || str === '') return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  /**
   * Append de una tarjeta de solicitud al contenedor.
   * @param {object} host PrivatePanel
   * @param {HTMLElement} container
   * @param {object} solicitud
   * @param {boolean} conBotonConocer
   */
  function appendSolicitudCard(host, container, solicitud, conBotonConocer) {
    if (!container) return;
    var card = document.createElement('div');
    var texto = solicitud.descripcion || solicitud.texto || '(sin descripción)';
    var por = solicitud.solicitante_nombre || solicitud.por || '(sin autor)';
    var zona = solicitud.oficio || solicitud.zona || '(sin oficio)';
    var estado = (solicitud.estado || 'pendiente').toLowerCase();
    card.className = 'solicitud-card estado-' + estado;
    var estadoLabel = 'Pendiente';
    var badgeClass = 'ruana-badge pendiente';
    if (estado === 'atendida') {
      estadoLabel = 'Atendida';
      badgeClass = 'ruana-badge atendida';
    } else if (estado === 'candidato_pendiente') {
      estadoLabel = 'Candidato pendiente';
      badgeClass = 'ruana-badge warning';
    }
    var fechaRaw = solicitud.creado_en || solicitud.fecha || solicitud.created_at || '';
    var fechaFmt = fechaRaw ? new Date(fechaRaw).toLocaleString('es-ES', { dateStyle: 'medium', timeStyle: 'short' }) : '';
    var atendidoPor = solicitud.atendido_por_nombre || solicitud.atendido_por_codigo || '';
    var atendidoAt = solicitud.atendido_at ? new Date(solicitud.atendido_at).toLocaleString('es-ES', { dateStyle: 'short', timeStyle: 'short' }) : '';
    var candidatoPor = solicitud.candidato_por_nombre || solicitud.candidato_por_codigo || '';
    var asignadaA = solicitud.asignada_a_nombre || solicitud.asignada_a_codigo || '';
    var metaExtraParts = [];
    if (estado === 'atendida' && (atendidoPor || atendidoAt)) {
      metaExtraParts.push(
        '<div class="meta-item"><span class="meta-label">Atendida por</span><span class="meta-value"><span class="solicitud-timeline-dot"></span>' +
        escapeHtmlSafe(host, atendidoPor || '—') + (atendidoAt ? ' · ' + atendidoAt : '') + '</span></div>'
      );
    }
    if (estado === 'candidato_pendiente' && candidatoPor) {
      metaExtraParts.push(
        '<div class="meta-item"><span class="meta-label">Candidato propuesto por</span><span class="meta-value">' +
        escapeHtmlSafe(host, candidatoPor) + '</span></div>'
      );
    }
    if (asignadaA) {
      metaExtraParts.push(
        '<div class="meta-item"><span class="meta-label">Asignada a</span><span class="meta-value">' +
        escapeHtmlSafe(host, asignadaA) + '</span></div>'
      );
    }
    var metaExtra = metaExtraParts.join('');
    var mostrarConocer = conBotonConocer && estado === 'pendiente' && !asignadaA;
    card.innerHTML =
      '<div class="solicitud-card-header">' +
        '<div class="solicitud-texto">' + escapeHtmlSafe(host, texto) + '</div>' +
        '<span class="solicitud-estado-badge ' + badgeClass + '"><span class="ruana-badge-dot"></span>' + estadoLabel + '</span>' +
      '</div>' +
      '<div class="solicitud-meta">' +
        '<div class="meta-item">' +
          '<span class="meta-label">Por</span>' +
          '<span class="meta-value">' + escapeHtmlSafe(host, por) + '</span>' +
        '</div>' +
        '<div class="meta-item">' +
          '<span class="meta-label">Oficio</span>' +
          '<span class="meta-value">' + escapeHtmlSafe(host, zona) + '</span>' +
        '</div>' +
        (fechaFmt ? '<div class="meta-item"><span class="meta-label">Fecha</span><span class="meta-value">' + fechaFmt + '</span></div>' : '') +
        metaExtra +
      '</div>' +
      (mostrarConocer
        ? '<div class="solicitud-actions"><button class="btn-conocer" data-id="' + (solicitud.id || 0) + '"><i data-lucide="user-plus" style="width:16px;height:16px;vertical-align:-2px;margin-right:6px"></i>Conozco a alguien</button></div>'
        : '');
    container.appendChild(card);
  }

  /**
   * Renderizar solicitudes del grupo: entrantes, propias e historial.
   * @param {object} host PrivatePanel
   */
  function renderSolicitudes(host) {
    var entrantes = Array.isArray(host.solicitudesEntrantes) ? host.solicitudesEntrantes : [];
    var propias = Array.isArray(host.solicitudesPropias) ? host.solicitudesPropias : [];
    var historial = Array.isArray(host.solicitudesHistorial) ? host.solicitudesHistorial : [];

    if (host.solicitudesList) {
      host.solicitudesList.innerHTML = '';
      if (entrantes.length === 0) {
        host.solicitudesList.innerHTML = '<p class="solicitudes-empty">No hay solicitudes entrantes en este momento</p>';
      } else {
        entrantes.forEach(function (solicitud) {
          appendSolicitudCard(host, host.solicitudesList, solicitud, true);
        });
      }
      document.querySelectorAll('#solicitudes-list .btn-conocer').forEach(function (btn) {
        btn.addEventListener('click', function (e) {
          var el = e.currentTarget || e.target.closest('.btn-conocer');
          host.generateInviteCode(el && el.dataset ? el.dataset.id : null);
        });
      });
    }

    if (host.solicitudesPropiasList) {
      host.solicitudesPropiasList.innerHTML = '';
      if (propias.length === 0) {
        host.solicitudesPropiasList.innerHTML = '<p class="solicitudes-empty">Aún no has enviado ninguna solicitud. Usa el formulario de abajo.</p>';
      } else {
        propias.forEach(function (solicitud) {
          appendSolicitudCard(host, host.solicitudesPropiasList, solicitud, false);
        });
      }
    }

    if (host.solicitudesHistorialList) {
      host.solicitudesHistorialList.innerHTML = '';
      if (historial.length === 0) {
        host.solicitudesHistorialList.innerHTML = '<p class="solicitudes-empty">No hay historial de solicitudes en el grupo</p>';
      } else {
        historial.forEach(function (solicitud) {
          appendSolicitudCard(host, host.solicitudesHistorialList, solicitud, false);
        });
      }
    }
    if (typeof global.RuanaUI !== 'undefined') global.RuanaUI.initIcons(document.querySelector('.solicitudes-zone'));
  }

  function render(host) {
    renderSolicitudes(host);
  }

  function refresh(host) {
    renderSolicitudes(host);
  }

  modules.solicitudes = {
    render: render,
    refresh: refresh,
    renderSolicitudes: renderSolicitudes,
    appendSolicitudCard: appendSolicitudCard,
  };
})(typeof window !== 'undefined' ? window : globalThis);
