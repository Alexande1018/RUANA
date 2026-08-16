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

  var ESTADO_ORDEN = {
    pendiente: 0,
    candidato_pendiente: 1,
    atendida: 2,
    contestada: 2,
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

  function normalizarEstadoSolicitud(solicitud) {
    var estado = (solicitud && solicitud.estado ? solicitud.estado : 'pendiente').toLowerCase();
    if (estado === 'contestada') return 'atendida';
    return estado;
  }

  function ordenarPorEstadoYFecha(a, b) {
    var ea = normalizarEstadoSolicitud(a);
    var eb = normalizarEstadoSolicitud(b);
    var pa = ESTADO_ORDEN[ea] != null ? ESTADO_ORDEN[ea] : 9;
    var pb = ESTADO_ORDEN[eb] != null ? ESTADO_ORDEN[eb] : 9;
    if (pa !== pb) return pa - pb;
    var fa = new Date(a.creado_en || a.fecha || a.created_at || 0).getTime();
    var fb = new Date(b.creado_en || b.fecha || b.created_at || 0).getTime();
    return fb - fa;
  }

  function formatoFechaCorta(valor) {
    if (!valor) return '';
    var fecha = new Date(valor);
    if (Number.isNaN(fecha.getTime())) return '';
    return fecha.toLocaleString('es-ES', { dateStyle: 'medium', timeStyle: 'short' });
  }

  function etiquetaEstado(estado) {
    if (estado === 'atendida') {
      return { label: 'Atendida', badgeClass: 'ruana-badge atendida' };
    }
    if (estado === 'candidato_pendiente') {
      return { label: 'Candidato pendiente', badgeClass: 'ruana-badge warning' };
    }
    return { label: 'Pendiente', badgeClass: 'ruana-badge pendiente' };
  }

  function actualizarContadorSubseccion(wrapId, count) {
    var wrap = document.getElementById(wrapId);
    if (!wrap) return;
    var badge = wrap.querySelector('[data-solicitudes-count]');
    if (!badge) return;
    if (count > 0) {
      badge.textContent = String(count);
      badge.hidden = false;
    } else {
      badge.textContent = '';
      badge.hidden = true;
    }
  }

  function appendGrupoHeader(container, titulo, count) {
    var header = document.createElement('div');
    header.className = 'solicitudes-group-header';
    header.innerHTML =
      '<span class="solicitudes-group-title">' + escapeHtmlSafe(null, titulo) + '</span>' +
      (count > 0 ? '<span class="solicitudes-group-count">' + count + '</span>' : '');
    container.appendChild(header);
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
    var estado = normalizarEstadoSolicitud(solicitud);
    card.className = 'solicitud-card estado-' + estado;
    var estadoInfo = etiquetaEstado(estado);
    var fechaFmt = formatoFechaCorta(solicitud.creado_en || solicitud.fecha || solicitud.created_at || '');
    var atendidoPor = solicitud.atendido_por_nombre || solicitud.atendido_por_codigo || '';
    var atendidoAt = formatoFechaCorta(solicitud.atendido_at || '');
    var candidatoPor = solicitud.candidato_por_nombre || solicitud.candidato_por_codigo || '';
    var candidatoAt = formatoFechaCorta(solicitud.candidato_at || '');
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
        escapeHtmlSafe(host, candidatoPor) + (candidatoAt ? ' · ' + candidatoAt : '') + '</span></div>'
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
        '<span class="solicitud-estado-badge ' + estadoInfo.badgeClass + '"><span class="ruana-badge-dot"></span>' + estadoInfo.label + '</span>' +
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

  function renderListaPropias(host, propias) {
    if (!host.solicitudesPropiasList) return;
    host.solicitudesPropiasList.innerHTML = '';
    if (propias.length === 0) {
      host.solicitudesPropiasList.innerHTML = '<p class="solicitudes-empty">Aún no has enviado ninguna solicitud. Usa Conexiones para crear una.</p>';
      return;
    }
    var enCurso = propias.filter(function (s) {
      var e = normalizarEstadoSolicitud(s);
      return e === 'pendiente' || e === 'candidato_pendiente';
    });
    var atendidas = propias.filter(function (s) {
      return normalizarEstadoSolicitud(s) === 'atendida';
    });
    if (enCurso.length) {
      appendGrupoHeader(host.solicitudesPropiasList, 'En curso', enCurso.length);
      enCurso.forEach(function (solicitud) {
        appendSolicitudCard(host, host.solicitudesPropiasList, solicitud, false);
      });
    }
    if (atendidas.length) {
      appendGrupoHeader(host.solicitudesPropiasList, 'Atendidas', atendidas.length);
      atendidas.forEach(function (solicitud) {
        appendSolicitudCard(host, host.solicitudesPropiasList, solicitud, false);
      });
    }
  }

  function renderListaHistorial(host, historial) {
    if (!host.solicitudesHistorialList) return;
    host.solicitudesHistorialList.innerHTML = '';
    if (historial.length === 0) {
      host.solicitudesHistorialList.innerHTML = '<p class="solicitudes-empty">Aún no hay solicitudes cerradas o con candidato en el grupo</p>';
      return;
    }
    historial.forEach(function (solicitud) {
      appendSolicitudCard(host, host.solicitudesHistorialList, solicitud, false);
    });
  }

  /**
   * Renderizar solicitudes del grupo: entrantes, propias e historial.
   * @param {object} host PrivatePanel
   */
  function renderSolicitudes(host) {
    var entrantes = Array.isArray(host.solicitudesEntrantes) ? host.solicitudesEntrantes.slice() : [];
    var propias = Array.isArray(host.solicitudesPropias) ? host.solicitudesPropias.slice() : [];
    var historial = Array.isArray(host.solicitudesHistorial) ? host.solicitudesHistorial.slice() : [];

    entrantes.sort(ordenarPorEstadoYFecha);
    propias.sort(ordenarPorEstadoYFecha);
    historial.sort(ordenarPorEstadoYFecha);

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

    renderListaPropias(host, propias);
    renderListaHistorial(host, historial);

    actualizarContadorSubseccion('solicitudes-entrantes-wrap', entrantes.length);
    actualizarContadorSubseccion('solicitudes-propias-wrap', propias.length);
    actualizarContadorSubseccion('solicitudes-historial-wrap', historial.length);

    var contactosMod = global.RuanaAliadoModules && global.RuanaAliadoModules.contactos;
    if (contactosMod && typeof contactosMod.renderEncargosActivos === 'function') {
      contactosMod.renderEncargosActivos(host);
    }

    if (typeof global.RuanaUI !== 'undefined') global.RuanaUI.initIcons(document.querySelector('.solicitudes-zone'));
    if (global.AliadoShell && typeof global.AliadoShell.updateNavBadges === 'function') {
      global.AliadoShell.updateNavBadges();
    }
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
