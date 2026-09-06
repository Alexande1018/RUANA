/**
 * Módulo PrivatePanel `directorio` (Campamento Base).
 * Lista de profesionales del grupo, búsqueda y meta de score/etiqueta.
 * PrivatePanel conserva fachadas delgadas que delegan aquí.
 * Contactar / abrir chat siguen en PrivatePanel (callbacks desde render).
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
   * Códigos del directorio con los que ya hay una conversación activa (contacto abierto).
   * Mapa codigo -> { contacto } para abrir la conversación del encargo existente.
   * @param {object} host PrivatePanel
   */
  function codigosConConversacionActiva(host) {
    var codigo = (host.codigoAliado || (host.aliado && host.aliado.codigo) || '').toString().trim();
    var contactos = Array.isArray(host.contactosAbiertos) ? host.contactosAbiertos : [];
    var map = new Map();
    contactos.forEach(function (c) {
      var sol = (c.solicitante_codigo || '').toString().trim();
      var pro = (c.profesional_codigo || '').toString().trim();
      var otro = codigo === sol ? pro : codigo === pro ? sol : null;
      if (otro && c.id != null) map.set(otro, c);
    });
    return map;
  }

  /**
   * Meta de etiqueta/score RUANA para tarjetas del directorio.
   * Bandas: ÉLITE ≥350, DESTACADO ≥200, ESTABLE ≥50, EN RIESGO ≥15, COMPETENCIA <15.
   */
  function scoreEtiquetaMeta(score, estadoRuana) {
    var s = 0;
    try {
      s = score != null && score !== '' ? parseInt(score, 10) : 0;
      if (isNaN(s)) s = 0;
    } catch (e) {
      s = 0;
    }
    var map = {
      'ÉLITE': { status: 'elite', label: 'Élite' },
      'ELITE': { status: 'elite', label: 'Élite' },
      'DESTACADO': { status: 'destacado', label: 'Destacado' },
      'PRIORITARIO': { status: 'destacado', label: 'Destacado' },
      'ESTABLE': { status: 'estable', label: 'Estable' },
      'EN RIESGO': { status: 'en_riesgo', label: 'En riesgo' },
      'COMPETENCIA': { status: 'competencia', label: 'Competencia' }
    };
    var key = (estadoRuana || '').toString().trim().toUpperCase();
    if (map[key]) {
      return { score: s, status: map[key].status, label: map[key].label };
    }
    if (s >= 350) return { score: s, status: 'elite', label: 'Élite' };
    if (s >= 200) return { score: s, status: 'destacado', label: 'Destacado' };
    if (s >= 50) return { score: s, status: 'estable', label: 'Estable' };
    if (s >= 15) return { score: s, status: 'en_riesgo', label: 'En riesgo' };
    return { score: s, status: 'competencia', label: 'Competencia' };
  }

  /**
   * Renderizar lista de profesionales del grupo (panel Directorio).
   * @param {object} host PrivatePanel
   */
  function renderProfesionales(host) {
    var listaProfesionales = document.getElementById('profesionales-list');
    if (!listaProfesionales) return;

    listaProfesionales.innerHTML = '';

    var profesionalesArray = Array.isArray(host.profesionales) ? host.profesionales : [];
    var territorioModo = (host.aliado && host.aliado.territorio_modo) || 'territorial';
    var miCp = ((host.aliado && host.aliado.codigo_postal) || '').trim();
    if (miCp && territorioModo !== 'incubacion') {
      profesionalesArray = profesionalesArray.filter(function (p) {
        var cp = ((p && (p.codigo_postal || p.zona)) || '').trim();
        return cp === miCp;
      });
    }
    var profesionalesDisponibles = profesionalesArray.some(function (p) {
      return p && (p.rol !== undefined && p.rol !== null);
    })
      ? profesionalesArray.filter(function (p) { return p.rol === 'Titular'; })
      : profesionalesArray;

    var query = ((document.getElementById('directorio-search') || {}).value || '').trim().toLowerCase();
    var filtrados = query
      ? profesionalesDisponibles.filter(function (p) {
          var nombre = (p.nombre || '').toLowerCase();
          var oficio = (p.oficio || '').toLowerCase();
          var zona = (p.zona || p.codigo_postal || '').toLowerCase();
          return nombre.includes(query) || oficio.includes(query) || zona.includes(query);
        })
      : profesionalesDisponibles;

    if (filtrados.length === 0) {
      listaProfesionales.innerHTML = '<p style="color: #999; text-align: center; padding: 20px;">' +
        (query ? 'Ningún profesional coincide con la búsqueda.' : 'No hay profesionales disponibles en este momento') + '</p>';
      return;
    }

    var contactoPorCodigo = codigosConConversacionActiva(host);

    filtrados.forEach(function (prof) {
      var codigoProf = (prof.codigo || '').toString().trim();
      var tieneConversacion = codigoProf && contactoPorCodigo.has(codigoProf);
      var contactoExistente = tieneConversacion ? contactoPorCodigo.get(codigoProf) : null;

      var esIncompleto = prof.perfil_incompleto === true;
      var nombre = prof.nombre || '(sin nombre)';
      var oficio = prof.oficio || '(sin oficio)';
      var zona = prof.zona || prof.codigo_postal || '(sin zona)';
      var cercaniaBadge = '';
      if (territorioModo === 'incubacion' && prof.etiqueta_cercania) {
        cercaniaBadge = ' <span class="directorio-cercania-badge">' + escapeHtmlSafe(host, prof.etiqueta_cercania) + '</span>';
      }
      var descripcionServicio = (prof.descripcion_servicio || prof.descripcion || '').trim();
      var badgeTexto = tieneConversacion ? 'Negociación activa' : (esIncompleto ? 'Perfil incompleto' : 'DISPONIBLE');
      var scoreMeta = scoreEtiquetaMeta(prof.score, prof.estado_ruana);

      var badgeRuana = tieneConversacion ? 'conversacion-activa' : (esIncompleto ? 'perfil-incompleto' : '');
      var badgeTipo = tieneConversacion ? 'ruana-badge pendiente' : (esIncompleto ? 'ruana-badge observacion' : 'ruana-badge disponible');
      var avatarHtml = typeof host.renderAvatarHtml === 'function'
        ? host.renderAvatarHtml(prof.foto_perfil_url, nombre, 'profesional-avatar', scoreMeta.status)
        : '';

      var card = document.createElement('div');
      card.className = 'profesional-card' + (esIncompleto ? ' perfil-incompleto' : '');
      card.innerHTML =
        '<div class="profesional-header">' +
          '<div class="profesional-identity">' +
            avatarHtml +
            '<div>' +
              '<div class="profesional-nombre">' + escapeHtmlSafe(host, nombre) + '</div>' +
              '<div class="profesional-oficio-sub">' + escapeHtmlSafe(host, oficio) + ' · ' + escapeHtmlSafe(host, zona) + cercaniaBadge + '</div>' +
            '</div>' +
          '</div>' +
          '<div class="profesional-badge ' + badgeRuana + ' ' + badgeTipo + '"><span class="ruana-badge-dot"></span>' + escapeHtmlSafe(host, badgeTexto) + '</div>' +
        '</div>' +
        '<div class="profesional-score-row">' +
          '<span class="profesional-etiqueta ' + scoreMeta.status + '">' + escapeHtmlSafe(host, scoreMeta.label) + '</span>' +
          (scoreMeta.score >= 100
            ? '<span class="profesional-score ' + scoreMeta.status + '">Score <strong>' + escapeHtmlSafe(host, String(scoreMeta.score)) + '</strong></span>'
            : '') +
        '</div>' +
        (descripcionServicio ? '<div class="profesional-descripcion">' + escapeHtmlSafe(host, descripcionServicio) + '</div>' : '') +
        '<div class="profesional-acciones">' +
          (tieneConversacion
            ? '<button type="button" class="btn-abrir-negociacion btn-abrir-chat" data-contacto-id="' + contactoExistente.id + '" data-id="' + (prof.id || 0) + '"><i data-lucide="messages-square" style="width:16px;height:16px;vertical-align:-2px;margin-right:4px"></i>Abrir conversación</button>'
            : '<button type="button" class="btn-contactar" data-id="' + (prof.id || 0) + '"><i data-lucide="handshake" style="width:16px;height:16px;vertical-align:-2px;margin-right:4px"></i>Contactar</button>') +
        '</div>';
      listaProfesionales.appendChild(card);
    });

    document.querySelectorAll('.btn-contactar').forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        var proId = e.target.dataset.id;
        var profesional = profesionalesArray.find(function (p) { return p.id == proId; });
        if (profesional && profesional.nombre) host.mostrarAvisoPrevioContacto(profesional);
        else alert('No se pudo iniciar el contacto');
      });
    });
    document.querySelectorAll('.btn-abrir-negociacion, .btn-abrir-chat').forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        var contactoId = e.target.dataset.contactoId;
        var proId = e.target.dataset.id;
        var profesional = profesionalesArray.find(function (p) { return p.id == proId; });
        if (contactoId && profesional) host.abrirChatContacto(parseInt(contactoId, 10), profesional);
      });
    });
    if (typeof global.RuanaUI !== 'undefined') global.RuanaUI.initIcons(document.getElementById('profesionales-list'));
  }

  function render(host) {
    renderProfesionales(host);
  }

  function refresh(host) {
    renderProfesionales(host);
  }

  modules.directorio = {
    render: render,
    refresh: refresh,
    renderProfesionales: renderProfesionales,
    codigosConConversacionActiva: codigosConConversacionActiva,
    scoreEtiquetaMeta: scoreEtiquetaMeta,
  };
})(typeof window !== 'undefined' ? window : globalThis);
