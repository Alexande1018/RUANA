/**
 * Módulo AdminPanel `operaciones` (pagos / conflictos).
 * Render de conflictos de pago, pagos Apoyo y pagos en revisión.
 * AdminPanel conserva fachadas delgadas que delegan aquí.
 * Fetches de operaciones viven aquí; cargarDesdeApi en resumen.
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

  function buildAdminDocumentLink(host, storedUrl, label) {
      if (!storedUrl) return '—';
      const safeLabel = host.escapeHtml(label || 'Ver');
      const safeUrl = host.escapeHtml(storedUrl);
      return `<button type="button" class="btn-link btn-ver-documento-admin" data-documento-url="${safeUrl}">${safeLabel}</button>`;
}

async function abrirDocumentoAdmin(host, storedUrl) {
      if (!storedUrl) return;
      const authHeaders = AdminAuthenticator.getAdminAuthHeaders();
      try {
          const r = await fetch(`/api/admin/documentos/acceso?url=${encodeURIComponent(storedUrl)}`, {
              method: 'GET',
              credentials: 'same-origin',
              headers: authHeaders
          });
          if (r.status === 401) { host._adminSessionExpired(); return; }
          const data = await r.json();
          if (data.status === 'success' && data.url) {
              window.open(data.url, '_blank', 'noopener');
              return;
          }
          host.showToast(data.message || 'No se pudo abrir el documento.', 'error');
      } catch (e) {
          host.showToast('Error de conexión al abrir el documento.', 'error');
      }
}

function abrirModalRechazarPago(host, contactoId) {
      host._contactoIdRechazo = contactoId;
      const modal = document.getElementById('modal-rechazar-pago');
      const input = document.getElementById('input-motivo-rechazo-pago');
      if (input) input.value = '';
      if (modal) modal.style.display = 'flex';
}

async function confirmarRechazarPago(host) {
      const contactoId = host._contactoIdRechazo;
      const input = document.getElementById('input-motivo-rechazo-pago');
      const motivo = input && input.value ? input.value.trim() : '';
      if (!contactoId) { host.showToast('No hay contacto seleccionado.', 'error'); return; }
      if (!motivo) {
          host.showToast('Debe escribir un mensaje al Aliado.', 'error');
          return;
      }
      const authHeaders = AdminAuthenticator.getAdminAuthHeaders();
      try {
          const r = await fetch(`/api/admin/contactos/${contactoId}/estado-pago`, {
              method: 'POST',
              credentials: 'same-origin',
              headers: { ...authHeaders, 'Content-Type': 'application/json' },
              body: JSON.stringify({ estado_pago: 'rechazado', motivo: motivo })
          });
          const data = await r.json();
          if (r.status === 401) { host._adminSessionExpired(); return; }
          const modal = document.getElementById('modal-rechazar-pago');
          if (modal) modal.style.display = 'none';
          if (data.status === 'success') {
              host.showToast('Mensaje enviado y pago rechazado. El profesional puede volver a subir comprobante.', 'success');
              host._contactoIdRechazo = null;
              host.cargarDesdeApi();
          } else {
              host.showToast(data.message || 'Error al rechazar.', 'error');
          }
      } catch (e) {
          host.showToast('Error de conexión.', 'error');
      }
}

async function cambiarEstadoPagoContacto(host, contactoId, nuevoEstado, rowEl) {
      const authHeaders = AdminAuthenticator.getAdminAuthHeaders();
      try {
          const body = { estado_pago: nuevoEstado };
          const r = await fetch(`/api/admin/contactos/${contactoId}/estado-pago`, {
              method: 'POST',
              credentials: 'same-origin',
              headers: { ...authHeaders, 'Content-Type': 'application/json' },
              body: JSON.stringify(body)
          });
          const data = await r.json();
          if (r.status === 401) { host._adminSessionExpired(); return; }
          if (data.status === 'success') {
              host.showToast('Estado de pago actualizado.', 'success');
              if (rowEl) {
                  const badge = rowEl.querySelector('.estado-pago-badge');
                  if (badge) {
                      badge.textContent = (nuevoEstado || '').replace(/_/g, ' ');
                      badge.className = 'estado-pago-badge estado-pago-' + (nuevoEstado || '').replace(/_/g, '-');
                  }
              }
              host.cargarDesdeApi();
          } else {
              host.showToast(data.message || 'Error al actualizar estado.', 'error');
          }
      } catch (e) {
          host.showToast('Error de conexión.', 'error');
      }
}

async function abrirModalDetalleConflicto(host, conflictId, rowEl) {
      host._conflictoId = conflictId;
      host._conflictoRowEl = rowEl;
      const modal = document.getElementById('modal-detalle-conflicto');
      const infoEl = document.getElementById('detalle-conflicto-info');
      const pruebaEl = document.getElementById('detalle-conflicto-prueba');
      const comentarioEl = document.getElementById('detalle-conflicto-comentario-admin');
      const inputComentario = document.getElementById('input-comentario-resolver');
      if (modal) modal.style.display = 'flex';
      if (inputComentario) inputComentario.value = '';
      if (infoEl) infoEl.textContent = 'Cargando...';
      if (pruebaEl) pruebaEl.innerHTML = '';
      if (comentarioEl) comentarioEl.textContent = '';
      const authHeaders = AdminAuthenticator.getAdminAuthHeaders();
      try {
          const r = await fetch(`/api/admin/payment-conflicts/${conflictId}`, { credentials: 'same-origin', headers: authHeaders });
          const data = await r.json();
          if (r.status === 401) { host._adminSessionExpired(); return; }
          if (data.status !== 'success' || !data.conflicto) {
              host.showToast(data.message || 'Error al cargar conflicto.', 'error');
              return;
          }
          const c = data.conflicto;
          if (infoEl) {
              infoEl.innerHTML = `Trabajo #${c.trabajo_id || '—'} · Contratante: ${host.escapeHtml(c.contratante_nombre || c.contratante_codigo || '')} · Profesional: ${host.escapeHtml(c.profesional_nombre || c.profesional_codigo || '')}<br>` +
                  `Importe contratante: ${c.importe_contratante != null ? Number(c.importe_contratante).toFixed(2) : '—'} € · Importe profesional: ${c.importe_profesional != null ? Number(c.importe_profesional).toFixed(2) : '—'} € · Estado: ${host.escapeHtml(c.estado || '')}`;
          }
          if (pruebaEl) {
              if (c.prueba_url) pruebaEl.innerHTML = `Documento: ${host.buildAdminDocumentLink(c.prueba_url, 'Abrir prueba')}`;
              else pruebaEl.textContent = 'Sin prueba subida.';
          }
          if (comentarioEl && (c.estado === 'RESUELTO' || c.estado === 'RECHAZADO') && c.comentario_admin) {
              comentarioEl.textContent = 'Comentario admin: ' + c.comentario_admin;
          }
      } catch (e) {
          if (infoEl) infoEl.textContent = 'Error de conexión.';
      }
}

async function resolverConflictoDecision(host, decision) {
      const id = host._conflictoId;
      const rowEl = host._conflictoRowEl;
      const input = document.getElementById('input-comentario-resolver');
      const comentario = input && input.value ? input.value.trim() : '';
      if (!id) { host.showToast('No hay conflicto seleccionado.', 'error'); return; }
      if (!comentario) { host.showToast('El comentario es obligatorio.', 'error'); return; }
      const authHeaders = AdminAuthenticator.getAdminAuthHeaders();
      try {
          const r = await fetch(`/api/admin/payment-conflicts/${id}/resolver`, {
              method: 'POST',
              credentials: 'same-origin',
              headers: { ...authHeaders, 'Content-Type': 'application/json' },
              body: JSON.stringify({ decision, comentario })
          });
          const data = await r.json();
          if (r.status === 401) { host._adminSessionExpired(); return; }
          if (data.status === 'success') {
              host.showToast('Resolución registrada.', 'success');
              document.getElementById('modal-detalle-conflicto').style.display = 'none';
              if (rowEl && rowEl.parentNode) rowEl.remove();
              const tbody = document.getElementById('tbody-conflictos-pago');
              const emptyEl = document.getElementById('conflictos-pago-empty');
              if (emptyEl && tbody && !tbody.querySelector('tr')) emptyEl.style.display = 'block';
              await host.cargarDesdeApi();
          } else {
              host.showToast(data.message || 'Error al resolver.', 'error');
          }
      } catch (e) {
          host.showToast('Error de conexión.', 'error');
      }
}

function abrirModalResolverConflicto(host, contactoId, rowEl) {
      host._conflictoContactoId = contactoId;
      host._conflictoRowEl = rowEl;
      const modal = document.getElementById('modal-resolver-conflicto');
      const input = document.getElementById('input-importe-valido');
      if (modal) modal.style.display = 'flex';
      if (input) { input.value = ''; input.focus(); }
}

async function confirmarResolverConflicto(host) {
      const id = host._conflictoContactoId;
      const rowEl = host._conflictoRowEl;
      const input = document.getElementById('input-importe-valido');
      const importeValido = input && input.value ? parseFloat(input.value) : NaN;
      if (!id) { host.showToast('No hay conflicto seleccionado.', 'error'); return; }
      if (isNaN(importeValido) || importeValido <= 0) { host.showToast('Introduce un importe válido mayor que cero.', 'error'); return; }
      const authHeaders = AdminAuthenticator.getAdminAuthHeaders();
      try {
          const r = await fetch(`/api/admin/conflictos-pago/${id}/resolver`, {
              method: 'POST',
              credentials: 'same-origin',
              headers: { ...authHeaders, 'Content-Type': 'application/json' },
              body: JSON.stringify({ importe_valido: importeValido })
          });
          const data = await r.json();
          if (r.status === 401) { host._adminSessionExpired(); return; }
          if (data.status === 'success') {
              host.showToast('Conflicto resuelto. Contacto cerrado.', 'success');
              document.getElementById('modal-resolver-conflicto').style.display = 'none';
              if (rowEl && rowEl.parentNode) rowEl.remove();
              const tbody = document.getElementById('tbody-conflictos-pago');
              const emptyEl = document.getElementById('conflictos-pago-empty');
              if (emptyEl && tbody && !tbody.querySelector('tr')) emptyEl.style.display = 'block';
          } else {
              host.showToast(data.message || 'Error al resolver.', 'error');
          }
      } catch (e) {
          host.showToast('Error de conexión.', 'error');
      }
}

async function cargarCentroComunicacionAdmin(host) {
      const authHeaders = AdminAuthenticator.getAdminAuthHeaders();
      const status = (document.getElementById('cc-admin-status')?.value || '').trim();
      const unreadOnly = document.getElementById('cc-admin-only-unread')?.checked ? '1' : '0';
      const params = new URLSearchParams({ limite: '120', solo_no_leidas: unreadOnly });
      if (status) params.set('estado', status);
      try {
          const r = await fetch('/api/admin/centro-comunicacion?' + params.toString(), { method: 'GET', credentials: 'same-origin', headers: authHeaders });
          if (r.status === 401) { host._adminSessionExpired(); return; }
          const data = await r.json().catch(() => ({}));
          host._centroComunicacion = data.status === 'success' && Array.isArray(data.conversaciones) ? data.conversaciones : [];
          host.renderCentroComunicacionAdmin(host._centroComunicacion);
      } catch (_) {
          host.showToast('No se pudo cargar el centro de comunicación.', 'error');
      }
}

function renderCentroComunicacionAdmin(host, conversaciones) {
      const tbody = document.getElementById('tbody-centro-comunicacion-admin');
      const empty = document.getElementById('centro-comunicacion-admin-empty');
      if (!tbody) return;
      const filtro = (document.getElementById('cc-admin-search')?.value || '').trim().toLowerCase();
      const lista = (Array.isArray(conversaciones) ? conversaciones : []).filter((c) => {
          if (!filtro) return true;
          const full = `${c.aliado_codigo || ''} ${c.aliado_nombre || ''} ${c.asunto || ''}`.toLowerCase();
          return full.includes(filtro);
      });
      tbody.innerHTML = '';
      if (empty) empty.style.display = lista.length ? 'none' : 'block';
      lista.forEach((c) => {
          const tr = document.createElement('tr');
          const fecha = c.ultimo_mensaje_en ? host.formatearHora(c.ultimo_mensaje_en) : '—';
          const estadoClass = (c.estado || 'pendiente').replace(/[^a-z_]/g, '');
          const nuevo = Number(c.tiene_no_leido_admin || 0) > 0 ? '<span class="estado-pago-badge" style="background:rgba(251,191,36,0.2);color:#fbbf24;">Nuevo</span>' : '—';
          tr.innerHTML = `
              <td>#${c.id}</td>
              <td>${host.escapeHtml((c.aliado_nombre || c.aliado_codigo || '—'))}<br><span style="color:#94a3b8;font-size:0.75rem;">${host.escapeHtml(c.aliado_codigo || '')}</span></td>
              <td>${host.escapeHtml(c.asunto || 'Consulta')}</td>
              <td><span class="estado-pago-badge estado-pago-${estadoClass.replace('_', '-')}">${host.escapeHtml((c.estado || 'pendiente').replace('_', ' '))}</span></td>
              <td>${host.escapeHtml(c.ultimo_mensaje_preview || '—')}</td>
              <td>${fecha}</td>
              <td>${nuevo}</td>
              <td><button type="button" class="btn-accion btn-cc-ver" data-cc-id="${c.id}">Abrir</button></td>
          `;
          tr.querySelector('.btn-cc-ver')?.addEventListener('click', () => host.abrirModalCentroComunicacionAdmin(c));
          tbody.appendChild(tr);
      });
}

async function abrirModalCentroComunicacionAdmin(host, conv) {
      host._centroComunicacionActiva = conv || null;
      const modal = document.getElementById('modal-centro-comunicacion-admin');
      const title = document.getElementById('cc-admin-modal-title');
      const msgBox = document.getElementById('cc-admin-modal-messages');
      const status = document.getElementById('cc-admin-modal-status');
      if (!modal || !conv) return;
      if (title) title.textContent = `Conversación #${conv.id} · ${conv.aliado_nombre || conv.aliado_codigo || ''}`;
      if (status) status.value = conv.estado || 'pendiente';
      if (msgBox) msgBox.innerHTML = '<p style="color:#94a3b8;">Cargando mensajes…</p>';
      modal.style.display = 'flex';
      const authHeaders = AdminAuthenticator.getAdminAuthHeaders();
      const r = await fetch('/api/admin/centro-comunicacion/' + conv.id + '/mensajes', { method: 'GET', credentials: 'same-origin', headers: authHeaders });
      const data = await r.json().catch(() => ({}));
      const mensajes = data.status === 'success' && Array.isArray(data.mensajes) ? data.mensajes : [];
      if (msgBox) {
          msgBox.innerHTML = mensajes.map((m) => {
              const esAdmin = (m.emisor_tipo || '') === 'admin';
              const fecha = m.creado_en ? new Date(m.creado_en).toLocaleString('es-ES', { dateStyle: 'short', timeStyle: 'short' }) : '';
              return `<div style="padding:8px 10px; border-radius:8px; margin-bottom:8px; background:${esAdmin ? 'rgba(34,197,94,0.15)' : 'rgba(59,130,246,0.16)'}; border:1px solid ${esAdmin ? 'rgba(74,222,128,0.38)' : 'rgba(147,197,253,0.35)'};">
                  ${host.escapeHtml(m.mensaje || '')}
                  <div style="font-size:0.76rem;color:#94a3b8;margin-top:4px;">${esAdmin ? 'RUANA' : 'Aliado'} · ${fecha}</div>
              </div>`;
          }).join('') || '<p style="color:#94a3b8;">Sin mensajes.</p>';
          msgBox.scrollTop = msgBox.scrollHeight;
      }
}

function cerrarModalCentroComunicacionAdmin(host) {
      const modal = document.getElementById('modal-centro-comunicacion-admin');
      if (modal) modal.style.display = 'none';
      host._centroComunicacionActiva = null;
}

async function responderCentroComunicacionAdmin(host) {
      const conv = host._centroComunicacionActiva;
      if (!conv) return;
      const msgEl = document.getElementById('cc-admin-modal-reply');
      const estadoEl = document.getElementById('cc-admin-modal-status');
      const mensaje = (msgEl?.value || '').trim();
      if (!mensaje) { host.showToast('Escribe una respuesta.', 'error'); return; }
      const authHeaders = Object.assign({}, AdminAuthenticator.getAdminAuthHeaders(), { 'Content-Type': 'application/json' });
      const r = await fetch('/api/admin/centro-comunicacion/' + conv.id + '/responder', {
          method: 'POST',
          credentials: 'same-origin',
          headers: authHeaders,
          body: JSON.stringify({ mensaje, estado: estadoEl?.value || 'respondido' })
      });
      const data = await r.json().catch(() => ({}));
      if (data.status !== 'success') { host.showToast(data.message || 'No se pudo responder.', 'error'); return; }
      if (msgEl) msgEl.value = '';
      host.showToast('Respuesta enviada.', 'success');
      await host.cargarCentroComunicacionAdmin();
      await host.abrirModalCentroComunicacionAdmin((host._centroComunicacion || []).find(c => Number(c.id) === Number(conv.id)) || conv);
}

async function actualizarEstadoCentroComunicacionAdmin(host) {
      const conv = host._centroComunicacionActiva;
      const estado = (document.getElementById('cc-admin-modal-status')?.value || '').trim();
      if (!conv || !estado) return;
      const authHeaders = Object.assign({}, AdminAuthenticator.getAdminAuthHeaders(), { 'Content-Type': 'application/json' });
      const r = await fetch('/api/admin/centro-comunicacion/' + conv.id + '/estado', {
          method: 'POST',
          credentials: 'same-origin',
          headers: authHeaders,
          body: JSON.stringify({ estado })
      });
      const data = await r.json().catch(() => ({}));
      if (data.status !== 'success') { host.showToast(data.message || 'No se pudo actualizar estado.', 'error'); return; }
      host.showToast('Estado actualizado.', 'success');
      await host.cargarCentroComunicacionAdmin();
}

async function eliminarCentroComunicacionAdmin(host) {
      const conv = host._centroComunicacionActiva;
      if (!conv) return;
      if (!window.confirm('¿Eliminar esta conversación del panel admin?')) return;
      const authHeaders = AdminAuthenticator.getAdminAuthHeaders();
      const r = await fetch('/api/admin/centro-comunicacion/' + conv.id, { method: 'DELETE', credentials: 'same-origin', headers: authHeaders });
      const data = await r.json().catch(() => ({}));
      if (data.status !== 'success') { host.showToast(data.message || 'No se pudo eliminar.', 'error'); return; }
      host.showToast('Conversación eliminada.', 'success');
      host.cerrarModalCentroComunicacionAdmin();
      await host.cargarCentroComunicacionAdmin();
}

async function abrirModalVerChat(host, contactoId) {
      host._negociacionContactoId = contactoId;
      const modal = document.getElementById('modal-ver-chat');
      const titulo = document.getElementById('modal-chat-titulo');
      const cont = document.getElementById('admin-chat-mensajes');
      const resumenEl = document.getElementById('admin-neg-resumen');
      if (!modal || !cont) return;
      if (titulo) titulo.textContent = 'Negociación del contacto #' + contactoId;
      cont.innerHTML = '<p style="color:#888;">Cargando...</p>';
      if (resumenEl) resumenEl.textContent = '';
      modal.style.display = 'flex';
      const authHeaders = AdminAuthenticator.getAdminAuthHeaders();
      const btnDel = document.getElementById('btn-eliminar-negociacion');
      if (btnDel && !btnDel._bound) {
          btnDel._bound = true;
          btnDel.addEventListener('click', () => host.eliminarNegociacion(host._negociacionContactoId));
      }
      try {
          const r = await fetch(`/api/admin/contactos/${contactoId}/negociacion`, { method: 'GET', credentials: 'same-origin', headers: authHeaders });
          const data = await r.json().catch(() => null);
          if (r.status === 401) { host._adminSessionExpired(); return; }
          if (!data || data.status !== 'success') {
              cont.innerHTML = '<p style="color:#f87171;">No se pudo cargar la negociación.</p>';
              return;
          }
          if (resumenEl && Array.isArray(data.resumen)) {
              resumenEl.innerHTML = data.resumen.map(item =>
                  `<span style="margin-right:12px;"><strong>${host.escapeHtml(item.label)}:</strong> ${host.escapeHtml(String(item.valor || '—'))} (${item.estado})</span>`
              ).join('');
          }
          const eventos = Array.isArray(data.eventos) ? data.eventos : [];
          if (!eventos.length) {
              cont.innerHTML = '<p style="color:#888;">Sin eventos aún</p>';
              return;
          }
          cont.innerHTML = eventos.map(ev => {
              const fecha = ev.creado_en ? new Date(ev.creado_en).toLocaleString('es-ES', { dateStyle: 'short', timeStyle: 'short' }) : '';
              return `<div style="margin-bottom:12px; padding:10px 12px; border-radius:8px; background:rgba(255,255,255,0.06); border-left:3px solid ${ev.tipo === 'sistema' ? '#22c55e' : '#6366f1'}"><strong>${host.escapeHtml(ev.tipo || '')}</strong> — ${fecha}<br>${host.escapeHtml(ev.mensaje || '')}</div>`;
          }).join('');
          cont.scrollTop = cont.scrollHeight;
      } catch (e) {
          cont.innerHTML = '<p style="color:#f87171;">Error de conexión.</p>';
      }
}

async function eliminarNegociacion(host, contactoId) {
      if (!contactoId) return;
      if (!confirm('¿Eliminar esta negociación y todo el contacto asociado? Esta acción no se puede deshacer.')) return;
      const authHeaders = AdminAuthenticator.getAdminAuthHeaders();
      try {
          const r = await fetch(`/api/admin/contactos/${contactoId}/negociacion`, {
              method: 'DELETE',
              credentials: 'same-origin',
              headers: authHeaders,
          });
          const data = await r.json().catch(() => ({}));
          if (r.status === 401) { host._adminSessionExpired(); return; }
          if (data.status !== 'success') {
              alert(data.message || 'No se pudo eliminar');
              return;
          }
          const modal = document.getElementById('modal-ver-chat');
          if (modal) modal.style.display = 'none';
          host._conversacionesList = (host._conversacionesList || []).filter(c => (c.contacto_id || c.id) !== contactoId);
          host.renderConversaciones(host._conversacionesList);
          host.showToast('Negociación eliminada', 'success');
      } catch (e) {
          alert('Error de conexión');
      }
}

modules.operaciones = {
    renderConflictosPago: renderConflictosPago,
    renderPagosApoyo: renderPagosApoyo,
    renderPagosEnRevision: renderPagosEnRevision,
  
    buildAdminDocumentLink: buildAdminDocumentLink,
    abrirDocumentoAdmin: abrirDocumentoAdmin,
    abrirModalRechazarPago: abrirModalRechazarPago,
    confirmarRechazarPago: confirmarRechazarPago,
    cambiarEstadoPagoContacto: cambiarEstadoPagoContacto,
    abrirModalDetalleConflicto: abrirModalDetalleConflicto,
    resolverConflictoDecision: resolverConflictoDecision,
    abrirModalResolverConflicto: abrirModalResolverConflicto,
    confirmarResolverConflicto: confirmarResolverConflicto,
    cargarCentroComunicacionAdmin: cargarCentroComunicacionAdmin,
    renderCentroComunicacionAdmin: renderCentroComunicacionAdmin,
    abrirModalCentroComunicacionAdmin: abrirModalCentroComunicacionAdmin,
    cerrarModalCentroComunicacionAdmin: cerrarModalCentroComunicacionAdmin,
    responderCentroComunicacionAdmin: responderCentroComunicacionAdmin,
    actualizarEstadoCentroComunicacionAdmin: actualizarEstadoCentroComunicacionAdmin,
    eliminarCentroComunicacionAdmin: eliminarCentroComunicacionAdmin,
    abrirModalVerChat: abrirModalVerChat,
    eliminarNegociacion: eliminarNegociacion,
};
})(typeof window !== 'undefined' ? window : globalThis);
