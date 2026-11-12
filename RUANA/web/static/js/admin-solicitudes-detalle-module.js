/**
 * RUANA Admin — Todas las solicitudes y su detalle completo (solo lectura).
 * - Sección «Todas las solicitudes»: semanales + de conexión, todas las semanas y estados,
 *   con filtros (tipo, estado, semana, grupo, texto) y paginación.
 * - Cualquier fila marcada con data-detalle-tipo/data-detalle-id (también en
 *   «Solicitudes de esta semana» y «Nuevas conexiones») abre el detalle completo.
 * Módulo autónomo: no cambia acciones existentes ni el flujo del aliado.
 */
(function (global) {
  'use strict';

  var modules = global.RuanaAdminModules = global.RuanaAdminModules || {};
  var API = '/api/admin/solicitudes-todas';
  var PAGINA = 50;
  var estado = { offset: 0, total: 0, cargando: false };

  var TIPOS = { semanal: 'Semanal', conexion: 'Conexión' };
  var RESPUESTAS = {
    puedo_ayudar: 'Puede ayudar',
    conozco_alguien: 'Recomienda a alguien',
    no_puedo_ayudar: 'No puede',
    atendida: 'Atendió la solicitud',
    candidato: 'Propuso candidato'
  };
  var CANDIDATOS = {
    puedo_ayudar: 'Se ofreció',
    conozco_alguien: 'Recomendado',
    asignada_a: 'Asignada a',
    proximidad: 'Profesional cercano',
    candidato: 'Candidato propuesto',
    atendido_por: 'Atendida por'
  };

  function esc(s) {
    if (global.RuanaUi && typeof global.RuanaUi.escapeHtml === 'function') {
      return global.RuanaUi.escapeHtml(s);
    }
    var d = document.createElement('div');
    d.textContent = s == null ? '' : String(s);
    return d.innerHTML;
  }

  function authHeaders(extra) {
    var base = Object.assign({}, extra || {});
    /* global AdminAuthenticator */
    if (typeof AdminAuthenticator !== 'undefined' && typeof AdminAuthenticator.getAdminAuthHeaders === 'function') {
      return AdminAuthenticator.getAdminAuthHeaders(base);
    }
    try {
      var sid = global.sessionStorage && global.sessionStorage.getItem('admin_session_id');
      if (sid) base['X-Ruana-Session-Id'] = sid;
    } catch (e) { /* ignore */ }
    return base;
  }

  function fecha(v) {
    if (!v) return '—';
    var s = String(v);
    var d = new Date(s.replace(' ', 'T') + (/[zZ]|[+-]\d\d:?\d\d$/.test(s) || s.length <= 10 ? '' : 'Z'));
    if (isNaN(d.getTime())) return esc(v);
    if (s.length <= 10) return d.toLocaleDateString('es-ES', { timeZone: 'UTC' });
    return d.toLocaleString('es-ES', { dateStyle: 'short', timeStyle: 'short', timeZone: 'Europe/Madrid' });
  }

  function corto(t, n) {
    t = String(t || '');
    return t.length > n ? t.substring(0, n) + '…' : t;
  }

  function getJson(url) {
    return fetch(url, { credentials: 'same-origin', headers: authHeaders() })
      .then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (j) { return { ok: r.ok, code: r.status, j: j }; });
      });
  }

  /* ---------- lista «Todas las solicitudes» ---------- */

  function val(id) {
    var el = document.getElementById(id);
    return el ? String(el.value || '').trim() : '';
  }

  function rellenarEstados(disponibles) {
    var sel = document.getElementById('filtro-sol-todas-estado');
    if (!sel || !Array.isArray(disponibles)) return;
    var actual = sel.value;
    var html = '<option value="">Todos los estados</option>' + disponibles.map(function (e) {
      return '<option value="' + esc(e) + '">' + esc(e) + '</option>';
    }).join('');
    sel.innerHTML = html;
    sel.value = actual;
  }

  function renderLista(data) {
    var tbody = document.getElementById('tbody-solicitudes-todas');
    var empty = document.getElementById('solicitudes-todas-empty');
    var info = document.getElementById('solicitudes-todas-paginacion-info');
    var prev = document.getElementById('btn-sol-todas-prev');
    var next = document.getElementById('btn-sol-todas-next');
    var avisos = document.getElementById('solicitudes-todas-avisos');
    if (!tbody) return;
    var items = (data && data.items) || [];
    estado.total = Number(data && data.total) || 0;
    if (empty) empty.style.display = items.length ? 'none' : 'block';
    if (avisos) {
      var lista = (data && data.avisos) || [];
      avisos.style.display = lista.length ? 'block' : 'none';
      avisos.textContent = lista.join(' · ');
    }
    rellenarEstados(data && data.filtros_disponibles && data.filtros_disponibles.estados);
    tbody.innerHTML = items.map(function (s) {
      var resp = [];
      if (s.pueden_ayudar_count) resp.push(s.pueden_ayudar_count + ' ayudan');
      if (s.recomiendan_count) resp.push(s.recomiendan_count + ' recomiendan');
      if (s.no_pueden_count) resp.push(s.no_pueden_count + ' no pueden');
      return '<tr class="fila-detalle-solicitud" tabindex="0" role="button" title="Ver el detalle completo"' +
        ' data-detalle-tipo="' + esc(s.tipo) + '" data-detalle-id="' + esc(s.id) + '">' +
        '<td>' + esc(TIPOS[s.tipo] || s.tipo) + ' #' + esc(s.id) + '</td>' +
        '<td>' + fecha(s.created_at) + '</td>' +
        '<td>' + esc(s.semana_inicio || '—') + '</td>' +
        '<td>' + esc(s.grupo_nombre || ('#' + (s.grupo_id || ''))) + '</td>' +
        '<td>' + esc(s.solicitante_nombre || s.solicitante_codigo || '—') +
          (s.solicitante_codigo ? ' <small style="color:#999;">' + esc(s.solicitante_codigo) + '</small>' : '') + '</td>' +
        '<td>' + esc(s.oficio || '—') + '</td>' +
        '<td style="max-width:280px; white-space:normal;">' + esc(corto(s.descripcion, 90) || '—') + '</td>' +
        '<td>' + esc(s.estado || '—') + '</td>' +
        '<td>' + esc(resp.join(' · ') || '—') + '</td>' +
        '</tr>';
    }).join('');
    var desde = estado.total ? estado.offset + 1 : 0;
    var hasta = Math.min(estado.offset + items.length, estado.total);
    if (info) info.textContent = desde + '–' + hasta + ' de ' + estado.total;
    if (prev) prev.disabled = estado.offset <= 0;
    if (next) next.disabled = estado.offset + PAGINA >= estado.total;
  }

  function refresh(resetOffset) {
    if (estado.cargando) return Promise.resolve();
    if (resetOffset) estado.offset = 0;
    estado.cargando = true;
    var params = new URLSearchParams();
    [['tipo', 'filtro-sol-todas-tipo'], ['estado', 'filtro-sol-todas-estado'], ['semana', 'filtro-sol-todas-semana'],
     ['grupo', 'filtro-sol-todas-grupo'], ['q', 'filtro-sol-todas-q']].forEach(function (p) {
      var v = val(p[1]);
      if (v) params.set(p[0], v);
    });
    params.set('limit', String(PAGINA));
    params.set('offset', String(estado.offset));
    return getJson(API + '?' + params.toString())
      .then(function (res) {
        if (res.ok && res.j && res.j.status === 'success') {
          renderLista(res.j);
        } else {
          var avisos = document.getElementById('solicitudes-todas-avisos');
          if (avisos) { avisos.style.display = 'block'; avisos.textContent = (res.j && (res.j.error || res.j.message)) || ('Error ' + res.code); }
        }
      })
      .catch(function () { /* el panel sigue funcionando aunque falle esta lista */ })
      .then(function () { estado.cargando = false; });
  }

  /* ---------- modal de detalle ---------- */

  function modal() {
    var m = document.getElementById('modal-detalle-solicitud');
    if (m) return m;
    m = document.createElement('div');
    m.id = 'modal-detalle-solicitud';
    m.className = 'modal-overlay admin-modal';
    m.setAttribute('role', 'dialog');
    m.setAttribute('aria-modal', 'true');
    m.setAttribute('aria-labelledby', 'modal-detalle-solicitud-titulo');
    m.style.cssText = 'display:none; align-items:center; justify-content:center;';
    m.innerHTML =
      '<div class="modal-content" style="max-width:760px; width:94vw; max-height:88vh; overflow:auto; text-align:left;">' +
        '<div style="display:flex; justify-content:space-between; align-items:center; gap:12px;">' +
          '<h3 class="modal-title" id="modal-detalle-solicitud-titulo" style="margin:0;">Solicitud</h3>' +
          '<button type="button" class="btn-admin-action" data-cerrar-detalle-solicitud aria-label="Cerrar">Cerrar</button>' +
        '</div>' +
        '<div id="modal-detalle-solicitud-cuerpo" style="margin-top:12px;"></div>' +
      '</div>';
    m.addEventListener('click', function (ev) {
      if (ev.target === m || (ev.target.closest && ev.target.closest('[data-cerrar-detalle-solicitud]'))) cerrar();
    });
    document.body.appendChild(m);
    return m;
  }

  function cerrar() {
    var m = document.getElementById('modal-detalle-solicitud');
    if (m) m.style.display = 'none';
  }

  function fila(etiqueta, valor) {
    return '<tr><th style="text-align:left; padding:4px 10px 4px 0; color:#999; font-weight:500; vertical-align:top; white-space:nowrap;">' +
      esc(etiqueta) + '</th><td style="padding:4px 0; white-space:normal;">' + valor + '</td></tr>';
  }

  function txt(v) { return (v === null || v === undefined || v === '') ? '—' : esc(v); }

  function aliadoTxt(a, codigo, nombre) {
    var n = (a && a.nombre) || nombre || '';
    var c = (a && a.codigo) || codigo || '';
    var extra = [];
    if (a && a.oficio) extra.push(a.oficio);
    if (a && a.codigo_postal) extra.push('CP ' + a.codigo_postal);
    if (a && a.telefono) extra.push(a.telefono);
    if (a && a.email) extra.push(a.email);
    return esc(n || '—') + (c ? ' <small style="color:#999;">' + esc(c) + '</small>' : '') +
      (extra.length ? '<br><small style="color:#aaa;">' + esc(extra.join(' · ')) + '</small>' : '');
  }

  function renderDetalle(d) {
    var s = d.solicitud || {};
    var titulo = document.getElementById('modal-detalle-solicitud-titulo');
    if (titulo) titulo.textContent = 'Solicitud ' + (TIPOS[d.tipo] || d.tipo) + ' #' + (s.id || '');
    var h = '';
    h += '<h4 style="margin:6px 0;">Texto de la solicitud</h4>';
    h += '<div style="white-space:pre-wrap; padding:10px; border-radius:8px; background:rgba(255,255,255,0.05);">' +
      (s.descripcion ? esc(s.descripcion) : '<em style="color:#999;">Sin texto</em>') + '</div>';
    h += '<table style="margin-top:12px; border-collapse:collapse; width:100%;">';
    h += fila('Tipo', esc(TIPOS[d.tipo] || d.tipo));
    h += fila('Estado', txt(s.estado));
    h += fila('Oficio', txt(s.oficio) + (s.es_oficio_personalizado ? ' <small>(personalizado)</small>' : ''));
    h += fila('Solicitante', aliadoTxt(d.solicitante, s.solicitante_codigo, s.solicitante_nombre));
    h += fila('Grupo', txt(s.grupo_nombre) + (s.grupo_id ? ' <small style="color:#999;">#' + esc(s.grupo_id) + '</small>' : ''));
    h += fila('Creada', fecha(s.created_at));
    h += fila('Semana', txt(s.semana_inicio));
    if (s.expira_at) h += fila('Caduca', fecha(s.expira_at));
    if (s.destino) h += fila('Destino', txt(s.destino));
    if (s.atendido_at) h += fila('Atendida', fecha(s.atendido_at));
    h += '</table>';

    var resp = d.respuestas || [];
    h += '<h4 style="margin:16px 0 6px;">Respuestas (' + resp.length + ')</h4>';
    if (!resp.length) {
      h += '<p style="color:#999; margin:0;">Nadie ha respondido todavía.</p>';
    } else {
      h += '<ul style="margin:0; padding-left:18px;">' + resp.map(function (r) {
        var extra = [];
        if (r.contacto_id) extra.push('contacto #' + r.contacto_id);
        if (r.invitacion_codigo) extra.push('invitación ' + r.invitacion_codigo + (r.invitacion && r.invitacion.usado ? ' (usada)' : ''));
        return '<li style="margin-bottom:6px;"><strong>' + esc(RESPUESTAS[r.tipo_respuesta] || r.tipo_respuesta || '—') + '</strong> · ' +
          aliadoTxt(r.aliado, r.aliado_codigo, r.aliado_nombre) + ' · ' + fecha(r.created_at) +
          (extra.length ? '<br><small style="color:#aaa;">' + esc(extra.join(' · ')) + '</small>' : '') + '</li>';
      }).join('') + '</ul>';
    }

    var cands = d.candidatos || [];
    h += '<h4 style="margin:16px 0 6px;">Candidatos (' + cands.length + ')</h4>';
    if (!cands.length) {
      h += '<p style="color:#999; margin:0;">Sin candidatos.</p>';
    } else {
      h += '<ul style="margin:0; padding-left:18px;">' + cands.map(function (c) {
        var extra = [];
        if (c.oficio) extra.push(c.oficio);
        if (c.cp) extra.push('CP ' + c.cp);
        if (c.zona) extra.push(c.zona);
        if (c.estado) extra.push(c.estado);
        if (c.invitacion_codigo) extra.push('invitación ' + c.invitacion_codigo + (c.invitacion_usada ? ' (usada)' : ''));
        return '<li style="margin-bottom:6px;"><strong>' + esc(CANDIDATOS[c.origen] || c.origen || '—') + '</strong> · ' +
          esc(c.nombre || '—') + (c.codigo ? ' <small style="color:#999;">' + esc(c.codigo) + '</small>' : '') +
          (c.fecha ? ' · ' + fecha(c.fecha) : '') +
          (extra.length ? '<br><small style="color:#aaa;">' + esc(extra.join(' · ')) + '</small>' : '') + '</li>';
      }).join('') + '</ul>';
    }

    var invs = d.invitaciones || [];
    if (invs.length) {
      h += '<h4 style="margin:16px 0 6px;">Invitaciones ligadas (' + invs.length + ')</h4>';
      h += '<ul style="margin:0; padding-left:18px;">' + invs.map(function (i) {
        return '<li>' + esc(i.codigo || '—') + ' · ' + (i.usado ? 'usada' : 'sin usar') +
          (i.revocada_en ? ' · revocada' : '') + ' · ' + fecha(i.creado_en || i.created_at) + '</li>';
      }).join('') + '</ul>';
    }

    h += '<details style="margin-top:16px;"><summary style="cursor:pointer; color:#999;">Todos los campos (datos en bruto)</summary>' +
      '<pre style="white-space:pre-wrap; word-break:break-word; font-size:12px; margin-top:8px;">' + esc(JSON.stringify(s, null, 2)) + '</pre></details>';
    return h;
  }

  function abrirDetalle(tipo, id) {
    if (!tipo || !id) return Promise.resolve();
    var m = modal();
    var cuerpo = document.getElementById('modal-detalle-solicitud-cuerpo');
    var titulo = document.getElementById('modal-detalle-solicitud-titulo');
    if (titulo) titulo.textContent = 'Solicitud ' + (TIPOS[tipo] || tipo) + ' #' + id;
    if (cuerpo) cuerpo.innerHTML = '<p style="color:#999;">Cargando…</p>';
    m.style.display = 'flex';
    return getJson(API + '/' + encodeURIComponent(tipo) + '/' + encodeURIComponent(id))
      .then(function (res) {
        if (!cuerpo) return;
        if (res.ok && res.j && res.j.status === 'success') {
          cuerpo.innerHTML = renderDetalle(res.j);
        } else {
          cuerpo.innerHTML = '<p style="color:#f87171;">' + esc((res.j && (res.j.error || res.j.message)) || ('No se pudo cargar (error ' + res.code + ')')) + '</p>';
        }
      })
      .catch(function () {
        if (cuerpo) cuerpo.innerHTML = '<p style="color:#f87171;">Error de conexión. Inténtalo de nuevo.</p>';
      });
  }

  function filaDesdeEvento(ev) {
    var t = ev.target;
    if (!t || !t.closest) return null;
    // No secuestrar clics en botones, casillas o enlaces de la fila (acciones existentes).
    if (t.closest('button, a, input, select, textarea, label')) return null;
    return t.closest('tr[data-detalle-tipo][data-detalle-id]');
  }

  function init() {
    document.addEventListener('click', function (ev) {
      var tr = filaDesdeEvento(ev);
      if (tr) abrirDetalle(tr.getAttribute('data-detalle-tipo'), tr.getAttribute('data-detalle-id'));
    });
    document.addEventListener('keydown', function (ev) {
      if (ev.key === 'Escape') { cerrar(); return; }
      if (ev.key !== 'Enter' && ev.key !== ' ') return;
      var tr = filaDesdeEvento(ev);
      if (tr && ev.target === tr) {
        ev.preventDefault();
        abrirDetalle(tr.getAttribute('data-detalle-tipo'), tr.getAttribute('data-detalle-id'));
      }
    });

    var wrap = document.getElementById('solicitudes-todas-admin-wrap');
    if (!wrap) return;
    var btn = document.getElementById('btn-filtrar-solicitudes-todas');
    if (btn) btn.addEventListener('click', function () { refresh(true); });
    ['filtro-sol-todas-tipo', 'filtro-sol-todas-estado', 'filtro-sol-todas-semana'].forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.addEventListener('change', function () { refresh(true); });
    });
    ['filtro-sol-todas-grupo', 'filtro-sol-todas-q'].forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.addEventListener('keydown', function (ev) { if (ev.key === 'Enter') refresh(true); });
    });
    var prev = document.getElementById('btn-sol-todas-prev');
    if (prev) prev.addEventListener('click', function () { estado.offset = Math.max(0, estado.offset - PAGINA); refresh(false); });
    var next = document.getElementById('btn-sol-todas-next');
    if (next) next.addEventListener('click', function () { estado.offset += PAGINA; refresh(false); });
    // Carga perezosa: solo cuando la sección se ve (sesión admin ya lista).
    if ('IntersectionObserver' in global) {
      var obs = new IntersectionObserver(function (entries) {
        entries.forEach(function (en) { if (en.isIntersecting) refresh(false); });
      });
      obs.observe(wrap);
    } else {
      refresh(true);
    }
  }

  modules.solicitudesDetalle = { refresh: refresh, abrirDetalle: abrirDetalle, renderDetalle: renderDetalle };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})(typeof window !== 'undefined' ? window : globalThis);
