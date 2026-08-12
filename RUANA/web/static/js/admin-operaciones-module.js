/**
 * Módulo AdminPanel `operaciones` (pagos / conflictos).
 * Render de conflictos de pago, pagos Apoyo y pagos en revisión.
 * AdminPanel conserva fachadas delgadas que delegan aquí.
 * La orquestación de fetch (cargarDesdeApi) permanece en admin.html.
 */
(function (global) {
  'use strict';

  var modules = global.RuanaAdminModules = global.RuanaAdminModules || {
    resumen: null,
    operaciones: null,
    red: null,
    sistema: null,
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

  function formatearHoraSafe(host, raw) {
    if (host && typeof host.formatearHora === 'function') {
      return host.formatearHora(raw);
    }
    return raw || '—';
  }

  function buildDocLinkSafe(host, url, label) {
    if (host && typeof host.buildAdminDocumentLink === 'function') {
      return host.buildAdminDocumentLink(url, label);
    }
    return '—';
  }

  function renderConflictosPago(host, conflictos) {
    var tbody = document.getElementById('tbody-conflictos-pago');
    var emptyEl = document.getElementById('conflictos-pago-empty');
    var wrap = document.getElementById('conflictos-pago-wrap');
    if (!tbody || !wrap) return;
    tbody.innerHTML = '';
    if (emptyEl) emptyEl.style.display = 'none';
    if (!conflictos || !conflictos.length) {
      if (emptyEl) emptyEl.style.display = 'block';
      return;
    }
    conflictos.forEach(function (c) {
      var impCont = c.importe_contratante != null ? Number(c.importe_contratante).toFixed(2) : '—';
      var impProf = c.importe_profesional != null ? Number(c.importe_profesional).toFixed(2) : '—';
      var fecha = c.created_at ? formatearHoraSafe(host, c.created_at) : '—';
      var pruebaLink = c.prueba_url ? buildDocLinkSafe(host, c.prueba_url, 'Ver') : '—';
      var tr = document.createElement('tr');
      tr.setAttribute('data-conflict-id', String(c.id || ''));
      tr.innerHTML =
        '<td>' + (c.id || '—') + '</td>' +
        '<td>' + (c.trabajo_id != null ? c.trabajo_id : '—') + '</td>' +
        '<td>' + escapeHtmlSafe(host, c.contratante_nombre || c.contratante_codigo || '') + '</td>' +
        '<td>' + escapeHtmlSafe(host, c.profesional_nombre || c.profesional_codigo || '') + '</td>' +
        '<td>' + impCont + '</td>' +
        '<td>' + impProf + '</td>' +
        '<td>' + escapeHtmlSafe(host, c.estado || '') + '</td>' +
        '<td>' + fecha + '</td>' +
        '<td>' + pruebaLink + '</td>' +
        '<td><button type="button" class="btn-accion btn-ver-detalle-conflicto" data-id="' + c.id + '">Ver / Resolver</button></td>';
      var btn = tr.querySelector('.btn-ver-detalle-conflicto');
      if (btn) {
        btn.addEventListener('click', function () {
          if (host && typeof host.abrirModalDetalleConflicto === 'function') {
            host.abrirModalDetalleConflicto(c.id, tr);
          }
        });
      }
      tbody.appendChild(tr);
    });
  }

  function renderPagosApoyo(host, pagos) {
    var tbody = document.getElementById('tbody-pagos-apoyo');
    var emptyEl = document.getElementById('pagos-apoyo-empty');
    var wrap = document.getElementById('pagos-apoyo-wrap');
    if (!tbody || !wrap) return;
    tbody.innerHTML = '';
    if (emptyEl) emptyEl.style.display = 'none';
    if (!pagos || !pagos.length) {
      if (emptyEl) emptyEl.style.display = 'block';
      return;
    }
    var estadosPermitidos = ['en_revision', 'pagado', 'rechazado'];
    pagos.forEach(function (p) {
      var importeFinal = (p.importe_final != null && !Number.isNaN(Number(p.importe_final)))
        ? Number(p.importe_final).toFixed(2) + ' €' : '—';
      var apoyoVal = p.apoyo_ruana;
      var apoyo = (apoyoVal != null && apoyoVal !== '' && !Number.isNaN(Number(apoyoVal)) && Number(apoyoVal) >= 0)
        ? Number(apoyoVal).toFixed(2) + ' €' : 'Pendiente de cálculo';
      var estadoPago = (p.estado_pago || 'pendiente_pago').replace(/_/g, ' ');
      var comprobanteLink = p.comprobante_ruta ? buildDocLinkSafe(host, p.comprobante_ruta, 'Ver') : '—';
      var fechaCierre = p.fecha_cierre ? formatearHoraSafe(host, p.fecha_cierre) : '—';
      var urgenteHtml = p.es_urgente
        ? '<span class="estado-pago-badge" style="background:rgba(180,83,9,0.35);color:#fde68a;border:1px solid rgba(251,191,36,0.5);">URGENTE</span>'
        : '—';
      var tr = document.createElement('tr');
      tr.setAttribute('data-contacto-id', String(p.id || ''));
      if (p.es_urgente) tr.style.background = 'rgba(180, 83, 9, 0.12)';
      tr.innerHTML =
        '<td>' + (p.id || '—') + '</td>' +
        '<td>' + escapeHtmlSafe(host, p.solicitante_nombre || p.solicitante_codigo || '') + '</td>' +
        '<td>' + escapeHtmlSafe(host, p.profesional_nombre || p.profesional_codigo || '') + '</td>' +
        '<td>' + urgenteHtml + '</td>' +
        '<td>' + importeFinal + '</td>' +
        '<td>' + apoyo + '</td>' +
        '<td><span class="estado-pago-badge estado-pago-' + (p.estado_pago || '').replace(/_/g, '-') + '">' + escapeHtmlSafe(host, estadoPago) + '</span></td>' +
        '<td>' + comprobanteLink + '</td>' +
        '<td>' + fechaCierre + '</td>' +
        '<td class="acciones-estado-pago">' +
          estadosPermitidos.map(function (est) {
            var label = est === 'en_revision' ? 'En revisión' : est === 'pagado' ? 'Marcar pagado' : 'Rechazar';
            return '<button type="button" class="btn-accion btn-estado-pago" data-contacto-id="' + p.id + '" data-estado="' + est + '">' + label + '</button>';
          }).join(' ') +
        '</td>';
      tr.querySelectorAll('.btn-estado-pago').forEach(function (btn) {
        var estado = btn.getAttribute('data-estado');
        var contactoId = Number(btn.getAttribute('data-contacto-id'));
        if (estado === 'rechazado') {
          btn.addEventListener('click', function () {
            if (host && typeof host.abrirModalRechazarPago === 'function') {
              host.abrirModalRechazarPago(contactoId);
            }
          });
        } else {
          btn.addEventListener('click', function () {
            if (host && typeof host.cambiarEstadoPagoContacto === 'function') {
              host.cambiarEstadoPagoContacto(contactoId, estado, tr);
            }
          });
        }
      });
      tbody.appendChild(tr);
    });
  }

  function renderPagosEnRevision(host, pagos) {
    var tbody = document.getElementById('tbody-pagos-en-revision');
    var emptyEl = document.getElementById('pagos-en-revision-empty');
    var wrap = document.getElementById('pagos-en-revision-wrap');
    if (!tbody || !wrap) return;
    tbody.innerHTML = '';
    if (emptyEl) emptyEl.style.display = 'none';
    if (!pagos || !pagos.length) {
      if (emptyEl) emptyEl.style.display = 'block';
      return;
    }
    pagos.forEach(function (p) {
      var profesional = escapeHtmlSafe(host, p.profesional_codigo || '—');
      var contactoId = p.id || '—';
      var importeFinal = (p.importe_final != null && !Number.isNaN(Number(p.importe_final)))
        ? Number(p.importe_final).toFixed(2) + ' €' : '—';
      var apoyoValRev = p.apoyo_ruana;
      var apoyo = (apoyoValRev != null && apoyoValRev !== '' && !Number.isNaN(Number(apoyoValRev)) && Number(apoyoValRev) >= 0)
        ? Number(apoyoValRev).toFixed(2) + ' €' : 'Pendiente de cálculo';
      var comprobanteLink = p.comprobante_ruta ? buildDocLinkSafe(host, p.comprobante_ruta, 'Ver comprobante') : '—';
      var fecha = p.fecha_cierre ? formatearHoraSafe(host, p.fecha_cierre) : '—';
      var tr = document.createElement('tr');
      tr.setAttribute('data-contacto-id', String(p.id || ''));
      tr.innerHTML =
        '<td>' + profesional + '</td>' +
        '<td>' + contactoId + '</td>' +
        '<td>' + importeFinal + '</td>' +
        '<td>' + apoyo + '</td>' +
        '<td>' + comprobanteLink + '</td>' +
        '<td>' + fecha + '</td>' +
        '<td class="acciones-estado-pago">' +
          '<button type="button" class="btn-accion btn-aprobar-pago" data-contacto-id="' + p.id + '" title="Aprobar pago">✔️ Aprobar pago</button> ' +
          '<button type="button" class="btn-accion btn-rechazar-pago danger" data-contacto-id="' + p.id + '" title="Rechazar pago">❌ Rechazar pago</button>' +
        '</td>';
      var btnAprobar = tr.querySelector('.btn-aprobar-pago');
      var btnRechazar = tr.querySelector('.btn-rechazar-pago');
      if (btnAprobar) {
        btnAprobar.addEventListener('click', function () {
          if (host && typeof host.cambiarEstadoPagoContacto === 'function') {
            host.cambiarEstadoPagoContacto(Number(p.id), 'pagado', tr);
          }
        });
      }
      if (btnRechazar) {
        btnRechazar.addEventListener('click', function () {
          if (host && typeof host.abrirModalRechazarPago === 'function') {
            host.abrirModalRechazarPago(Number(p.id));
          }
        });
      }
      tbody.appendChild(tr);
    });
  }

  modules.operaciones = {
    renderConflictosPago: renderConflictosPago,
    renderPagosApoyo: renderPagosApoyo,
    renderPagosEnRevision: renderPagosEnRevision,
  };
})(typeof window !== 'undefined' ? window : globalThis);
