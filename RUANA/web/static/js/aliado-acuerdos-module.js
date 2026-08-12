/**
 * Módulo PrivatePanel `acuerdos` (Campamento Base).
 * Lista «Mis acuerdos»: carga, filtros de estado en UI, paginación local y cards.
 * PrivatePanel conserva fachadas delgadas que delegan aquí.
 * El panel flotante de resumen de acuerdo (negociación) sigue en PrivatePanel.
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
  };

  function getAuthHeadersSafe(extra) {
    if (typeof global.getRuanaAuthHeaders === 'function') {
      return global.getRuanaAuthHeaders(extra || {});
    }
    return extra || {};
  }

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

  function etiquetaEstadoAcuerdo(a) {
    if (a && a.estado_label) return a.estado_label;
    var labels = {
      iniciado: 'Iniciado',
      aceptado: 'Aceptado',
      en_conversacion: 'En conversación',
      trabajo_en_progreso: 'En curso',
      acuerdo_alcanzado: 'Acuerdo confirmado',
      trabajo_cerrado: 'Finalizado',
      cerrado_no_concretado: 'Cancelado',
      no_concretado: 'No concretado',
      importe_en_disputa: 'Importe en disputa',
    };
    var est = (a && a.estado) || '';
    return labels[est] || est || 'Sin estado';
  }

  function formatearFechaAcuerdo(raw) {
    if (!raw) return '';
    var s = String(raw).trim();
    var m = s.match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (m) return m[3] + '/' + m[2] + '/' + m[1];
    return s.slice(0, 16);
  }

  function toggleMisAcuerdoExpandido(host, contactoId) {
    var id = String(contactoId || '');
    if (!id || !host) return;
    if (!host.misAcuerdosExpandidos) host.misAcuerdosExpandidos = new Set();
    if (host.misAcuerdosExpandidos.has(id)) {
      host.misAcuerdosExpandidos.delete(id);
    } else {
      host.misAcuerdosExpandidos.add(id);
    }
    renderMisAcuerdos(host);
  }

  function mostrarMasMisAcuerdos(host) {
    if (!host) return;
    var page = host.misAcuerdosPageSize || 5;
    var total = (host.misAcuerdos || []).length;
    host.misAcuerdosVisibles = Math.min(
      total,
      (host.misAcuerdosVisibles || page) + page
    );
    renderMisAcuerdos(host);
  }

  /**
   * Render de la lista Mis acuerdos (filtros + cards colapsables).
   * @param {object} host PrivatePanel
   */
  function renderMisAcuerdos(host) {
    if (!host) return;
    var lista = document.getElementById('mis-acuerdos-lista');
    if (!lista) return;
    var filtro = host.misAcuerdosFiltro || 'todos';
    document.querySelectorAll('.mis-acuerdos-filtro').forEach(function (btn) {
      btn.classList.toggle('active', btn.getAttribute('data-filtro') === filtro);
    });
    var selEstado = document.getElementById('mis-acuerdos-filtro-estado');
    if (selEstado && selEstado.value !== (host.misAcuerdosFiltroEstado || '')) {
      selEstado.value = host.misAcuerdosFiltroEstado || '';
    }
    var inpDesde = document.getElementById('mis-acuerdos-filtro-desde');
    if (inpDesde) inpDesde.value = host.misAcuerdosFiltroDesde || '';
    var inpHasta = document.getElementById('mis-acuerdos-filtro-hasta');
    if (inpHasta) inpHasta.value = host.misAcuerdosFiltroHasta || '';

    var items = host.misAcuerdos || [];
    if (!items.length) {
      lista.innerHTML = '<p class="mis-acuerdos-empty">No hay acuerdos con estos filtros.</p>';
      return;
    }

    var page = host.misAcuerdosPageSize || 5;
    if (!host.misAcuerdosVisibles || host.misAcuerdosVisibles < page) {
      host.misAcuerdosVisibles = page;
    }
    var visibles = items.slice(0, host.misAcuerdosVisibles);
    var quedan = items.length - visibles.length;
    var expandidos = host.misAcuerdosExpandidos || new Set();

    var cardsHtml = visibles.map(function (a) {
      var cid = String(a.contacto_id);
      var abierto = expandidos.has(cid);
      var badge = a.rol === 'contrate'
        ? '<span class="mis-acuerdos-badge contrate">Contrataste</span>'
        : '<span class="mis-acuerdos-badge contratado">Te contrataron</span>';
      var campos = a.campos || {};
      var detalles = ['fecha', 'hora', 'precio', 'direccion']
        .filter(function (k) { return campos[k]; })
        .map(function (k) {
          return '<span>' + escapeHtmlSafe(host, k) + ': ' + escapeHtmlSafe(host, String(campos[k])) + '</span>';
        })
        .join('');
      var estadoTxt = etiquetaEstadoAcuerdo(a);
      var estadoCls = 'estado-' + escapeHtmlSafe(host, (a.estado || 'otro').replace(/_/g, '-'));
      var fechaTxt = formatearFechaAcuerdo(
        a.fecha_referencia || a.acuerdo_alcanzado_en || a.fecha_cierre || a.creado_en
      );
      var fechaHtml = fechaTxt
        ? '<time class="mis-acuerdos-fecha" datetime="' + escapeHtmlSafe(host, String(a.fecha_referencia || a.creado_en || '')) + '">' + escapeHtmlSafe(host, fechaTxt) + '</time>'
        : '';
      var detallesBlock = detalles
        ? '<div class="mis-acuerdos-detalles">' + detalles + '</div>'
        : '<p class="mis-acuerdos-detalles-empty">Sin detalles adicionales del acuerdo.</p>';
      return '<article class="mis-acuerdos-card ' + (abierto ? 'is-open' : 'is-collapsed') + '" data-contacto-id="' + escapeHtmlSafe(host, cid) + '" data-estado="' + escapeHtmlSafe(host, a.estado || '') + '" aria-expanded="' + (abierto ? 'true' : 'false') + '">' +
        '<button type="button" class="mis-acuerdos-card-toggle" data-acuerdo-toggle="' + escapeHtmlSafe(host, cid) + '" aria-expanded="' + (abierto ? 'true' : 'false') + '">' +
          '<div class="mis-acuerdos-card-head">' +
            badge +
            '<span class="mis-acuerdos-estado ' + estadoCls + '">' + escapeHtmlSafe(host, estadoTxt) + '</span>' +
          '</div>' +
          '<div class="mis-acuerdos-card-summary">' +
            '<h4 class="mis-acuerdos-servicio">' + escapeHtmlSafe(host, a.servicio || 'Servicio') + '</h4>' +
            '<span class="mis-acuerdos-chevron" aria-hidden="true"></span>' +
          '</div>' +
        '</button>' +
        '<div class="mis-acuerdos-card-body"' + (abierto ? '' : ' hidden') + '>' +
          '<p class="mis-acuerdos-meta">Con aliado ' + escapeHtmlSafe(host, a.contraparte_codigo || '—') + (fechaHtml ? ' · ' + fechaHtml : '') + '</p>' +
          detallesBlock +
        '</div>' +
      '</article>';
    }).join('');

    var masHtml = quedan > 0
      ? '<div class="mis-acuerdos-mas-wrap">' +
          '<button type="button" class="mis-acuerdos-mostrar-mas" id="mis-acuerdos-mostrar-mas" data-acuerdo-mas="1">' +
            'Mostrar más <span class="mis-acuerdos-mas-restantes">(+' + quedan + ')</span>' +
          '</button>' +
        '</div>'
      : '';

    lista.innerHTML = cardsHtml + masHtml;
  }

  /**
   * GET /api/aliado/acuerdos con filtros del host.
   * @param {object} host PrivatePanel
   */
  function cargarMisAcuerdos(host) {
    if (!host) return Promise.resolve();
    var codigo = host.codigoAliado || (host.aliado && host.aliado.codigo) || '';
    if (!codigo) return Promise.resolve();
    try {
      var params = new URLSearchParams();
      params.set('limite', '100');
      var rol = host.misAcuerdosFiltro || 'todos';
      if (rol && rol !== 'todos') params.set('rol', rol);
      var estado = (host.misAcuerdosFiltroEstado || '').trim();
      if (estado) params.set('estado', estado);
      var desde = (host.misAcuerdosFiltroDesde || '').trim();
      if (desde) params.set('desde', desde);
      var hasta = (host.misAcuerdosFiltroHasta || '').trim();
      if (hasta) params.set('hasta', hasta);
      return fetch('/api/aliado/acuerdos?' + params.toString(), {
        credentials: 'same-origin',
        headers: getAuthHeadersSafe(),
      })
        .then(function (resp) {
          if (!resp.ok) return null;
          return resp.json();
        })
        .then(function (data) {
          if (!data) return;
          host.misAcuerdos = (data.status === 'success' && Array.isArray(data.acuerdos))
            ? data.acuerdos
            : [];
          host.misAcuerdosVisibles = host.misAcuerdosPageSize || 5;
          host.misAcuerdosExpandidos = new Set();
          renderMisAcuerdos(host);
        })
        .catch(function (e) {
          console.error('Error cargando Mis acuerdos:', e);
        });
    } catch (e) {
      console.error('Error cargando Mis acuerdos:', e);
      return Promise.resolve();
    }
  }

  function render(host) {
    renderMisAcuerdos(host);
  }

  function refresh(host) {
    return cargarMisAcuerdos(host);
  }

  modules.acuerdos = {
    render: render,
    refresh: refresh,
    cargarMisAcuerdos: cargarMisAcuerdos,
    renderMisAcuerdos: renderMisAcuerdos,
    etiquetaEstadoAcuerdo: etiquetaEstadoAcuerdo,
    formatearFechaAcuerdo: formatearFechaAcuerdo,
    toggleMisAcuerdoExpandido: toggleMisAcuerdoExpandido,
    mostrarMasMisAcuerdos: mostrarMasMisAcuerdos,
  };
})(typeof window !== 'undefined' ? window : globalThis);
