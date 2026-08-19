/**
 * Módulo AdminPanel `red` (Campamento Base).
 * Jerarquía de aliados (CP → grupo → tarjetas), pendientes y suplentes.
 * AdminPanel conserva fachadas delgadas que delegan aquí.
 */

(function (global) {
  'use strict';

  var modules = global.RuanaAdminModules = global.RuanaAdminModules || {
    resumen: null,
    operaciones: null,
    red: null,
    sistema: null,
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

  function esAliadoPlaceholder(host, a) {
    if (!a) return false;
    const est = (a.estado || '').toLowerCase();
    return est === 'pendiente_completar' || est === 'eliminado';
  }

  function getClaveGrupoRed(host, a) {
    if (!a) return '__sin_grupo__';
    if (a.grupo_id != null && String(a.grupo_id).trim() !== '') {
        return String(a.grupo_id);
    }
    return '__sin_grupo__';
  }

  function getNombreGrupoRed(host, a) {
    if (!a) return 'Sin grupo';
    const nombre = (a.grupo_nombre || '').toString().trim();
    if (nombre) return nombre;
    if (a.grupo_id != null && String(a.grupo_id).trim() !== '') {
        return 'Grupo #' + a.grupo_id;
    }
    return 'Sin grupo';
  }

  function normalizarCpAliado(host, a) {
    return (a && (a.codigo_postal || a.zona) || '').toString().trim() || '(sin CP)';
  }

  function renderAliadosJerarquia(host) {
    const nav = document.getElementById('aliados-jerarquia-nav');
    const breadcrumb = document.getElementById('aliados-breadcrumb');
    const nivelCps = document.getElementById('aliados-nivel-cps');
    const nivelGrupos = document.getElementById('aliados-nivel-grupos');
    const nivelOficios = document.getElementById('aliados-nivel-oficios');
    const nivelTarjetas = document.getElementById('aliados-nivel-tarjetas');
    const btnVolverCps = document.getElementById('aliados-btn-volver-cps');
    const btnVolverGrupos = document.getElementById('aliados-btn-volver-grupos');
    const btnVolverOficios = document.getElementById('aliados-btn-volver-oficios');
    if (nav) nav.style.display = host.aliadosNivel !== 'cps' ? 'flex' : 'none';
    if (btnVolverCps) btnVolverCps.style.display = host.aliadosNivel !== 'cps' ? 'inline-block' : 'none';
    if (btnVolverGrupos) btnVolverGrupos.style.display = ['oficios', 'tarjetas'].includes(host.aliadosNivel) ? 'inline-block' : 'none';
    if (btnVolverOficios) btnVolverOficios.style.display = host.aliadosNivel === 'tarjetas' ? 'inline-block' : 'none';
    if (nivelCps) nivelCps.style.display = host.aliadosNivel === 'cps' ? 'block' : 'none';
    if (nivelGrupos) nivelGrupos.style.display = host.aliadosNivel === 'grupos' ? 'block' : 'none';
    if (nivelOficios) nivelOficios.style.display = host.aliadosNivel === 'oficios' ? 'block' : 'none';
    if (nivelTarjetas) nivelTarjetas.style.display = host.aliadosNivel === 'tarjetas' ? 'block' : 'none';
    if (breadcrumb) {
        if (host.aliadosNivel === 'grupos' && host.aliadosCPSeleccionado) {
            breadcrumb.textContent = 'CP ' + host.aliadosCPSeleccionado + ' — Elige un grupo';
        } else if (host.aliadosNivel === 'oficios' && host.aliadosCPSeleccionado && host.aliadosGrupoSeleccionado != null) {
            const grupoLabel = host.aliadosGrupoNombreSeleccionado || host.aliadosGrupoSeleccionado;
            breadcrumb.textContent = 'CP ' + host.aliadosCPSeleccionado + ' → ' + grupoLabel + ' — Elige un oficio';
        } else if (host.aliadosNivel === 'tarjetas' && host.aliadosCPSeleccionado && host.aliadosGrupoSeleccionado != null) {
            const grupoLabel = host.aliadosGrupoNombreSeleccionado || host.aliadosGrupoSeleccionado;
            const oficioLabel = host.aliadosOficioSeleccionado || 'Todos';
            breadcrumb.textContent = 'CP ' + host.aliadosCPSeleccionado + ' → ' + grupoLabel + ' → ' + oficioLabel;
        } else {
            breadcrumb.textContent = '';
        }
    }
    if (host.aliadosNivel === 'cps') host.renderAliadosNivel1();
    else if (host.aliadosNivel === 'grupos') host.renderAliadosNivel2();
    else if (host.aliadosNivel === 'oficios') host.renderAliadosNivelOficios();
    else if (host.aliadosNivel === 'tarjetas') host.renderAliadosNivel3();
  }

  function renderAliadosNivel1(host) {
    const list = document.getElementById('aliados-cps-list');
    if (!list) return;
    list.innerHTML = '';
    const data = host._aliadosData || [];
    const byCp = new Map();
    data.forEach(a => {
        if (host.esAliadoPlaceholder(a)) return;
        const cp = host.normalizarCpAliado(a);
        let entry = byCp.get(cp);
        if (!entry) {
            entry = { count: 0, grupos: new Set() };
            byCp.set(cp, entry);
        }
        entry.count += 1;
        entry.grupos.add(host.getClaveGrupoRed(a));
    });
    const cps = Array.from(byCp.entries()).sort((x, y) => String(x[0]).localeCompare(String(y[0])));
    if (cps.length === 0) {
        list.innerHTML = '<p style="color:#94a3b8; padding:20px;">No hay aliados con código postal.</p>';
        return;
    }
    cps.forEach(([cp, info]) => {
        const count = info.count;
        const nGrupos = info.grupos.size;
        const card = document.createElement('div');
        card.className = 'cp-card';
        card.dataset.cp = cp;
        card.innerHTML =
            '<div class="cp-codigo">' + host.escapeHtml(cp) + '</div>' +
            '<div class="cp-count">' + count + ' aliado' + (count !== 1 ? 's' : '') +
            ' · ' + nGrupos + ' grupo' + (nGrupos !== 1 ? 's' : '') + '</div>';
        card.addEventListener('click', () => {
            host.aliadosCPSeleccionado = cp;
            host.aliadosGrupoSeleccionado = null;
            host.aliadosGrupoNombreSeleccionado = null;
            host.aliadosNivel = 'grupos';
            host.renderAliadosJerarquia();
        });
        list.appendChild(card);
    });
  }

  function renderAliadosNivel2(host) {
    const list = document.getElementById('aliados-grupos-list');
    if (!list) return;
    list.innerHTML = '';
    const cp = host.aliadosCPSeleccionado;
    if (!cp) return host.renderAliadosNivel1();
    const data = (host._aliadosData || []).filter(a => {
        if (host.esAliadoPlaceholder(a)) return false;
        return host.normalizarCpAliado(a) === cp;
    });
    const byGrupo = new Map();
    data.forEach(a => {
        const key = host.getClaveGrupoRed(a);
        let entry = byGrupo.get(key);
        if (!entry) {
            entry = { key, nombre: host.getNombreGrupoRed(a), count: 0 };
            byGrupo.set(key, entry);
        }
        entry.count += 1;
        // Preferir un nombre no vacío si llega más tarde
        const nombre = host.getNombreGrupoRed(a);
        if (nombre && nombre !== 'Sin grupo' && (!entry.nombre || entry.nombre === 'Sin grupo' || entry.nombre.indexOf('Grupo #') === 0)) {
            if (nombre.indexOf('Grupo #') !== 0) entry.nombre = nombre;
        }
    });
    const grupos = Array.from(byGrupo.values()).sort((a, b) => {
        if (a.key === '__sin_grupo__') return 1;
        if (b.key === '__sin_grupo__') return -1;
        return String(a.nombre).localeCompare(String(b.nombre), 'es', { sensitivity: 'base' });
    });
    if (grupos.length === 0) {
        list.innerHTML = '<p style="color:#94a3b8; padding:20px;">Ningún grupo con aliados en este CP.</p>';
        return;
    }
    grupos.forEach((g) => {
        const card = document.createElement('div');
        card.className = 'grupo-card' + (g.key === '__sin_grupo__' ? ' is-sin-grupo' : '');
        card.dataset.grupo = g.key;
        const idLine = (g.key !== '__sin_grupo__')
            ? '<div class="grupo-id">ID ' + host.escapeHtml(g.key) + '</div>'
            : '';
        card.innerHTML =
            '<div class="grupo-nombre">' + host.escapeHtml(g.nombre) + '</div>' +
            idLine +
            '<div class="grupo-count">' + g.count + ' aliado' + (g.count !== 1 ? 's' : '') + '</div>';
        card.addEventListener('click', () => {
            host.aliadosGrupoSeleccionado = g.key;
            host.aliadosGrupoNombreSeleccionado = g.nombre;
            host.aliadosOficioSeleccionado = null;
            host.aliadosNivel = 'oficios';
            host.renderAliadosJerarquia();
        });
        list.appendChild(card);
    });
  }

  function renderAliadosNivelOficios(host) {
    const list = document.getElementById('aliados-oficios-list');
    if (!list) return;
    list.innerHTML = '';
    const cp = host.aliadosCPSeleccionado;
    const grupo = host.aliadosGrupoSeleccionado;
    if (!cp || grupo == null) return host.renderAliadosNivel2();
    const data = (host._aliadosData || []).filter(a => {
        if (host.esAliadoPlaceholder(a)) return false;
        if (host.normalizarCpAliado(a) !== cp) return false;
        return host.getClaveGrupoRed(a) === grupo;
    });
    const byOficio = new Map();
    data.forEach(a => {
        const oficio = (a.oficio || 'Sin oficio').trim() || 'Sin oficio';
        byOficio.set(oficio, (byOficio.get(oficio) || 0) + 1);
    });
    const oficios = Array.from(byOficio.entries()).sort((a, b) => String(a[0]).localeCompare(String(b[0]), 'es', { sensitivity: 'base' }));
    if (!oficios.length) {
        list.innerHTML = '<p style="color:#94a3b8; padding:20px;">Ningún oficio con aliados en este grupo.</p>';
        return;
    }
    oficios.forEach(([oficio, count]) => {
        const card = document.createElement('div');
        card.className = 'oficio-card';
        card.innerHTML =
            '<div class="oficio-nombre">' + host.escapeHtml(oficio) + '</div>' +
            '<div class="oficio-count">' + count + ' aliado' + (count !== 1 ? 's' : '') + '</div>';
        card.addEventListener('click', () => {
            host.aliadosOficioSeleccionado = oficio;
            host.aliadosNivel = 'tarjetas';
            host.renderAliadosJerarquia();
        });
        list.appendChild(card);
    });
  }

  function renderAliadosNivel3(host) {
    const cp = host.aliadosCPSeleccionado;
    const grupo = host.aliadosGrupoSeleccionado;
    const oficio = host.aliadosOficioSeleccionado;
    if (!cp || grupo == null) return;
    const data = (host._aliadosData || []).filter(a => {
        if (host.esAliadoPlaceholder(a)) return false;
        if (host.normalizarCpAliado(a) !== cp) return false;
        if (host.getClaveGrupoRed(a) !== grupo) return false;
        if (oficio) {
            const aOficio = (a.oficio || 'Sin oficio').trim() || 'Sin oficio';
            return aOficio === oficio;
        }
        return true;
    });
    host.renderAliados(data);
  }

  function renderAliados(host, aliadosData) {
    /**
     * Renderiza la lista de aliados (tarjetas) en #aliados-admin-list.
     */
    const lista = document.getElementById('aliados-admin-list');
    if (!lista) return;
    lista.innerHTML = '';

    const aliados = Array.isArray(aliadosData) ? aliadosData : [];

    aliados.forEach(aliado => {
        // No mostrar placeholders de invitación en el panel de control
        if (host.esAliadoPlaceholder(aliado)) return;

        const estadoBd = (aliado.estado || '').toLowerCase();
        const card = document.createElement('div');
        card.className = 'aliado-admin-card';

        const estadoPanel = aliado.estado_panel || aliado.estado || 'activos';
        const badgeKey = estadoBd === 'pendiente_validacion'
            ? 'pendientes'
            : estadoPanel;
        const estadoBadgeClasses = `aliado-estado-badge ${badgeKey}`;
        let estadoTexto = 'Activo';
        if (badgeKey === 'pendientes' || estadoBd === 'pendiente_validacion') estadoTexto = 'Pendiente de validación';
        else if (estadoPanel === 'observacion') estadoTexto = 'En Observación';
        else if (estadoPanel === 'riesgo') estadoTexto = 'En Riesgo';
        else if (estadoPanel === 'suspendido_temporal') estadoTexto = 'Pausado';
        else if (estadoPanel === 'rechazado') estadoTexto = 'Rechazado';
        const badgeRetador = (aliado.es_retador_activo || aliado.es_suplente_activo) ? '<span class="aliado-badge suplente">Retador</span>' : '';
        const badgeCompetencia = aliado.es_titular_en_competencia ? '<span class="aliado-badge competencia">En competencia</span>' : '';

        const scoreTexto = (aliado.score_panel != null ? aliado.score_panel : aliado.score || 0);
        const esp = Array.isArray(aliado.especializaciones) ? aliado.especializaciones : [];
        const espTexto = esp.length ? esp.join(', ') : '—';
        const fechaRegistro = aliado.creado_en ? host.formatearHora(aliado.creado_en) : '—';
        const totalContactos = aliado.total_contactos != null ? aliado.total_contactos : '—';
        const contactos30d = aliado.contactos_30d != null ? aliado.contactos_30d : '—';
        const hijosCount = Number(aliado.hijos_directos_count || 0);
        const invitadoPorNombre = (aliado.invitado_por_nombre || '').trim();
        const invitadoPorCodigo = (aliado.invitado_por_codigo || '').trim();
        let invitadoPorTexto = 'Registro directo / Admin';
        if (invitadoPorCodigo) {
            invitadoPorTexto = host.escapeHtml(invitadoPorNombre || invitadoPorCodigo) +
                (invitadoPorNombre ? ' (' + host.escapeHtml(invitadoPorCodigo) + ')' : '');
        }

        card.innerHTML = `
            <div class="aliado-header-admin">
                <div class="aliado-nombre-admin">${host.escapeHtml(aliado.nombre)}</div>
                <div class="aliado-badges-wrap">
                    <div class="${estadoBadgeClasses}">${estadoTexto}</div>
                    ${badgeRetador}
                    ${badgeCompetencia}
                </div>
            </div>
            <div class="aliado-codigo-destacado">
                <strong>Código de aliado:</strong>
                <span class="codigo-valor">${host.escapeHtml(aliado.codigo || '—')}</span>
            </div>
            <div class="aliado-info-grid">
                <div class="aliado-info">
                    <span class="info-label">Oficio</span>
                    <span class="info-value">${host.escapeHtml(aliado.oficio)}</span>
                </div>
                <div class="aliado-info">
                    <span class="info-label">Zona</span>
                    <span class="info-value">${host.escapeHtml(aliado.zona || '')}</span>
                </div>
                <div class="aliado-info">
                    <span class="info-label">Grupo</span>
                    <span class="info-value">${host.escapeHtml(host.getGrupoTerritorialLabel(aliado))}</span>
                </div>
                <div class="aliado-info">
                    <span class="info-label">Marca</span>
                    <span class="info-value">${host.escapeHtml(aliado.marca)}</span>
                </div>
                <div class="aliado-info">
                    <span class="info-label">Score</span>
                    <span class="info-value">${scoreTexto}</span>
                </div>
                <div class="aliado-info">
                    <span class="info-label">Especialidades</span>
                    <span class="info-value">${host.escapeHtml(espTexto)}</span>
                </div>
                <div class="aliado-info">
                    <span class="info-label">Contacto</span>
                    <span class="info-value">${host.escapeHtml((aliado.telefono || '') + (aliado.email ? ' • ' + aliado.email : ''))}</span>
                </div>
                <div class="aliado-info">
                    <span class="info-label">Registro</span>
                    <span class="info-value">${fechaRegistro}</span>
                </div>
                <div class="aliado-info">
                    <span class="info-label">Historial</span>
                    <span class="info-value">Contactos: ${totalContactos} (30d: ${contactos30d})</span>
                </div>
            </div>
            <div class="aliado-linaje-row">
                <div><strong>Invitado por:</strong> ${invitadoPorTexto}</div>
                <div><strong>Invitó a:</strong> ${hijosCount} aliado${hijosCount === 1 ? '' : 's'}</div>
            </div>
            <div class="aliado-acciones">
                <button class="btn-accion btn-ver-detalle">Ver Detalle</button>
                <button class="btn-accion btn-linaje">Ver linaje</button>
                <button class="btn-accion btn-catalogo">Ver catálogo</button>
                <button class="btn-accion danger btn-pausar">Pausar</button>
            </div>
        `;

        const verDetalleBtn = card.querySelector('.btn-ver-detalle');
        if (verDetalleBtn) {
            verDetalleBtn.addEventListener('click', () => host.abrirModalDetalle(aliado));
        }

        const linajeBtn = card.querySelector('.btn-linaje');
        if (linajeBtn) {
            linajeBtn.addEventListener('click', () => host.abrirLinajeDrawer(aliado));
        }

        const pausarBtn = card.querySelector('.btn-pausar');
        if (pausarBtn) {
            pausarBtn.addEventListener('click', () => host.confirmarPausa(aliado));
        }
        const catalogoBtn = card.querySelector('.btn-catalogo');
        if (catalogoBtn) {
            catalogoBtn.addEventListener('click', () => host.abrirCatalogoServiciosModal(aliado));
        }

        lista.appendChild(card);
    });
  }

  function renderPendientesValidacion(host, aliados) {
    const tbody = document.getElementById('tbody-pendientes-validacion');
    const emptyEl = document.getElementById('pendientes-empty');
    const wrap = document.getElementById('pendientes-validacion-wrap');
    if (!tbody || !wrap) return;

    wrap.style.display = 'block';
    tbody.innerHTML = '';
    if (emptyEl) emptyEl.style.display = 'none';

    if (!aliados || !aliados.length) {
        if (emptyEl) emptyEl.style.display = 'block';
        return;
    }

    aliados.forEach(a => {
        const fechaRegistro = a.creado_en ? host.formatearHora(a.creado_en) : '—';
        const tr = document.createElement('tr');
        tr.setAttribute('data-id', String(a.id || ''));
        tr.innerHTML = `
            <td>${a.id || '—'}</td>
            <td>${host.escapeHtml(a.codigo || '')}</td>
            <td>${host.escapeHtml(a.nombre || '')}</td>
            <td>${host.escapeHtml(a.marca || '')}</td>
            <td>${host.escapeHtml(a.oficio || '')}</td>
            <td>${host.escapeHtml(a.codigo_postal || '')}</td>
            <td>${host.escapeHtml(a.email || '')}</td>
            <td>${host.escapeHtml(a.telefono || '')}</td>
            <td>${fechaRegistro}</td>
            <td><button type="button" class="btn-accion btn-activar-pendiente" data-id="${a.id}">Activar</button>
            <button type="button" class="btn-accion btn-rechazar-pendiente" data-codigo="${host.escapeHtml(a.codigo || '')}" style="margin-left:4px; background:rgba(239,68,68,0.2); color:#f87171;">Rechazar</button></td>
        `;
        const btnActivar = tr.querySelector('.btn-activar-pendiente');
        const btnRechazar = tr.querySelector('.btn-rechazar-pendiente');
        if (btnActivar) {
            btnActivar.addEventListener('click', () => host.activarAliadoPendiente(a.id, tr));
        }
        if (btnRechazar) {
            btnRechazar.addEventListener('click', () => host.rechazarAliadoPendiente(a.codigo, tr));
        }
        tbody.appendChild(tr);
    });
  }

  function renderAliadosEliminados(host, aliados) {
    const tbody = document.getElementById('tbody-aliados-eliminados');
    const emptyEl = document.getElementById('eliminados-empty');
    const wrap = document.getElementById('aliados-eliminados-wrap');
    if (!tbody || !wrap) return;

    wrap.style.display = 'block';
    tbody.innerHTML = '';
    if (emptyEl) emptyEl.style.display = 'none';

    if (!aliados || !aliados.length) {
        if (emptyEl) emptyEl.style.display = 'block';
        return;
    }

    aliados.forEach(a => {
        const fechaElim = a.eliminado_en ? host.formatearHora(a.eliminado_en) : '—';
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${host.escapeHtml(a.codigo || '')}</td>
            <td>${host.escapeHtml(a.nombre || '')}</td>
            <td>${host.escapeHtml(a.oficio || '')}</td>
            <td>${host.escapeHtml(a.codigo_postal || '')}</td>
            <td>${host.escapeHtml(a.estado_anterior || '')}</td>
            <td>${host.escapeHtml(a.motivo || '')}</td>
            <td>${host.escapeHtml(a.admin_codigo || '—')}</td>
            <td>${fechaElim}</td>
        `;
        tbody.appendChild(tr);
    });
  }

  function renderSolicitudesBaja(host, solicitudes) {
    const tbody = document.getElementById('tbody-solicitudes-baja');
    const emptyEl = document.getElementById('solicitudes-baja-empty');
    const wrap = document.getElementById('solicitudes-baja-wrap');
    if (!tbody || !wrap) return;

    wrap.style.display = 'block';
    tbody.innerHTML = '';
    if (emptyEl) emptyEl.style.display = 'none';

    const lista = Array.isArray(solicitudes) ? solicitudes : [];
    if (!lista.length) {
        if (emptyEl) emptyEl.style.display = 'block';
        return;
    }

    lista.forEach(s => {
        const id = s.id;
        const estado = (s.estado || 'pendiente').toLowerCase();
        const fecha = s.creado_en ? host.formatearHora(s.creado_en) : '—';
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${host.escapeHtml(String(id || ''))}</td>
            <td><code>${host.escapeHtml(s.codigo_aliado || '')}</code></td>
            <td>${host.escapeHtml(s.motivo || '—')}</td>
            <td>${host.escapeHtml(estado)}</td>
            <td>${fecha}</td>
            <td>${host.escapeHtml(s.admin_codigo || '—')}</td>
            <td>
                ${estado === 'pendiente' || estado === 'en_revision' ? (
                    '<button type="button" class="btn-activar-pendiente btn-marcar-baja-revision" data-id="' + id + '" style="padding:4px 10px; font-size:0.8rem; margin-right:6px;">En revisión</button>' +
                    '<button type="button" class="btn-activar-pendiente btn-marcar-baja-completada" data-id="' + id + '" style="padding:4px 10px; font-size:0.8rem;">Marcar gestionada</button>'
                ) : ''}
            </td>
        `;
        const btnRev = tr.querySelector('.btn-marcar-baja-revision');
        if (btnRev) btnRev.addEventListener('click', () => host.marcarSolicitudBaja(id, 'en_revision'));
        const btnDone = tr.querySelector('.btn-marcar-baja-completada');
        if (btnDone) btnDone.addEventListener('click', () => host.marcarSolicitudBaja(id, 'completada'));
        tbody.appendChild(tr);
    });
  }

  async function marcarSolicitudBaja(host, solicitudId, estado) {
    try {
        const r = await fetch('/api/admin/solicitudes-baja/' + encodeURIComponent(solicitudId), {
            method: 'POST',
            credentials: 'same-origin',
            headers: host.getAuthHeaders({ 'Content-Type': 'application/json' }),
            body: JSON.stringify({ estado: estado })
        });
        const data = await r.json().catch(() => ({}));
        if (data.status === 'success') {
            if (typeof host.showToast === 'function') host.showToast('Solicitud de baja actualizada', 'success');
            if (typeof host.loadDashboard === 'function') host.loadDashboard();
        } else if (typeof host.showToast === 'function') {
            host.showToast(data.message || 'No se pudo actualizar la solicitud', 'error');
        }
    } catch (_) {
        if (typeof host.showToast === 'function') host.showToast('Error de conexión', 'error');
    }
  }

  function renderSuplentesEspera(host, aliados) {
    const tbody = document.getElementById('tbody-suplentes-espera');
    const emptyEl = document.getElementById('suplentes-espera-empty');
    const wrap = document.getElementById('suplentes-espera-wrap');
    if (!tbody) return;
    tbody.innerHTML = '';
    const lista = Array.isArray(aliados) ? aliados : [];
    if (wrap) wrap.style.display = 'block';
    if (emptyEl) emptyEl.style.display = lista.length ? 'none' : 'block';
    lista.forEach(a => {
        const codigo = host.escapeHtml(a.codigo || '—');
        const nombre = host.escapeHtml(a.nombre || a.marca || '—');
        const oficio = host.escapeHtml(a.oficio_principal || a.oficio || '—');
        const cp = host.escapeHtml(a.codigo_postal || a.zona || '—');
        const fecha = a.creado_en ? new Date(a.creado_en).toLocaleDateString('es-ES') : '—';
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td><code>${codigo}</code></td>
            <td>${nombre}</td>
            <td>${oficio}</td>
            <td>${cp}</td>
            <td>${fecha}</td>
            <td>
                <button class="btn-activar-pendiente" data-codigo="${codigo}" style="padding:4px 10px; font-size:0.8rem;" title="Incorporar al aliado asignándolo al grupo con plaza libre más adecuado">
                    Incorporar
                </button>
            </td>
        `;
        const btn = tr.querySelector('.btn-activar-pendiente');
        if (btn) btn.addEventListener('click', () => host.accionIncorporarSuplente(codigo));
        tbody.appendChild(tr);
    });
  }

  function getGrupoTerritorialLabel(host, aliado) {
    const nombre = ((aliado && aliado.grupo_nombre) || '').trim();
    if (nombre) return nombre;
    if (aliado && aliado.grupo_id) return '#' + aliado.grupo_id;
    const estado = ((aliado && aliado.estado) || '').toLowerCase();
    if (estado === 'en_espera') return 'Suplente en espera (sin plaza)';
    if (estado === 'pendiente_validacion') return 'Pendiente de validación';
    if (estado === 'pendiente_completar') return 'Registro incompleto';
    return 'Sin grupo asignado';
  }

  function abrirCatalogoServiciosModal(host, aliado) {
    if (!aliado || !aliado.codigo) return;
    const modal = document.getElementById('aliadoCatalogoModal');
    const nombreEl = document.getElementById('catalogo-nombre');
    const codigoEl = document.getElementById('catalogo-codigo');
    const grid = document.getElementById('catalogo-admin-grid');
    if (!modal || !grid) return;
    if (nombreEl) nombreEl.textContent = `Catálogo de servicios · ${aliado.nombre || aliado.codigo}`;
    if (codigoEl) codigoEl.textContent = aliado.codigo || '';
    grid.innerHTML = '<p style="color:#94a3b8;">Cargando catálogo...</p>';
    modal.classList.remove('hidden');

    const authHeaders = AdminAuthenticator.getAdminAuthHeaders();
    fetch('/api/admin/aliados/' + encodeURIComponent(aliado.codigo) + '/catalogo-servicios', {
        method: 'GET',
        credentials: 'same-origin',
        headers: authHeaders,
    })
        .then((resp) => resp.ok ? resp.json() : null)
        .then((data) => {
            if (!data || data.status !== 'success') {
                grid.innerHTML = '<p style="color:#f87171;">No se pudo cargar el catálogo.</p>';
                return;
            }
            const servicios = Array.isArray(data.catalogo_servicios) ? data.catalogo_servicios : [];
            if (!servicios.length) {
                grid.innerHTML = '<p style="color:#94a3b8;">Sin servicios configurados.</p>';
                return;
            }
            grid.innerHTML = servicios.map((serv) => {
                const pos = Number(serv.posicion || 0);
                const descripcion = host.escapeHtml(serv.descripcion || '');
                const precio = host.escapeHtml(serv.precio || '');
                const configurado = Boolean(descripcion && precio);
                return `
                    <article class="catalogo-admin-card">
                        <h4>Servicio ${pos}</h4>
                        <div class="estado ${configurado ? 'ok' : ''}">${configurado ? 'Configurado' : 'Servicio no configurado'}</div>
                        <div class="campo">Descripción</div>
                        <div class="valor">${descripcion || '—'}</div>
                        <div class="campo" style="margin-top:8px;">Precio</div>
                        <div class="valor">${precio || '—'}</div>
                    </article>
                `;
            }).join('');
        })
        .catch(() => {
            grid.innerHTML = '<p style="color:#f87171;">Error de red al cargar el catálogo.</p>';
        });
  }

  function setupFichaTabs() {
    var tabs = document.getElementById('aliado-ficha-tabs');
    if (!tabs || tabs._bound) return;
    tabs._bound = true;
    tabs.addEventListener('click', function (e) {
      var btn = e.target.closest('[data-ficha-tab]');
      if (!btn) return;
      activateFichaTab(btn.getAttribute('data-ficha-tab'));
    });
  }

  function activateFichaTab(tabId) {
    document.querySelectorAll('.aliado-ficha-tab').forEach(function (btn) {
      btn.classList.toggle('is-active', btn.getAttribute('data-ficha-tab') === tabId);
    });
    document.querySelectorAll('.aliado-ficha-pane').forEach(function (pane) {
      pane.classList.toggle('is-active', pane.getAttribute('data-ficha-pane') === tabId);
    });
  }

  function abrirLinajeDrawer(host, aliado) {
    if (!aliado || !aliado.codigo) return;
    const overlay = document.getElementById('linaje-drawer-overlay');
    const meta = document.getElementById('linaje-drawer-meta');
    const rutaEl = document.getElementById('linaje-drawer-ruta');
    const padreEl = document.getElementById('linaje-drawer-padre');
    const hijosEl = document.getElementById('linaje-drawer-hijos');
    const title = document.getElementById('linaje-drawer-title');
    if (!overlay || !padreEl || !hijosEl) return;
    if (title) title.textContent = 'Linaje · ' + (aliado.nombre || aliado.codigo);
    if (meta) meta.textContent = 'Cargando genealogía…';
    if (rutaEl) rutaEl.textContent = '';
    padreEl.innerHTML = '<p class="linaje-empty">Cargando…</p>';
    hijosEl.innerHTML = '<p class="linaje-empty">Cargando…</p>';
    overlay.classList.add('show');
    overlay.setAttribute('aria-hidden', 'false');
    const authHeaders = AdminAuthenticator.getAdminAuthHeaders();
    fetch('/api/admin/aliados/' + encodeURIComponent(aliado.codigo) + '/linaje', {
        credentials: 'same-origin',
        headers: authHeaders,
    })
        .then(r => r.ok ? r.json() : null)
        .then(data => {
            if (!data || data.status !== 'success' || !data.linaje) {
                if (meta) meta.textContent = 'No se pudo cargar el linaje.';
                padreEl.innerHTML = '<p class="linaje-empty">Sin datos</p>';
                hijosEl.innerHTML = '<p class="linaje-empty">Sin datos</p>';
                return;
            }
            const linaje = data.linaje;
            const nodo = linaje.aliado || {};
            if (meta) {
                meta.textContent = (nodo.nombre || aliado.nombre || '') + ' · ' + (nodo.codigo || aliado.codigo || '');
            }
            const ruta = Array.isArray(linaje.ruta) ? linaje.ruta : [];
            if (rutaEl) {
                rutaEl.textContent = ruta.length
                    ? ('Ruta: ' + ruta.map(n => (n.nombre || n.codigo)).join(' → '))
                    : 'Ruta: (raíz)';
            }
            const padre = linaje.padre;
            if (!padre) {
                padreEl.innerHTML = '<p class="linaje-empty">Registro directo / raíz admin</p>';
            } else {
                padreEl.innerHTML = host._linajeCardHtml(padre);
                const card = padreEl.querySelector('.linaje-card');
                if (card) card.addEventListener('click', () => host.abrirLinajeDrawer(padre));
            }
            const hijos = Array.isArray(linaje.hijos) ? linaje.hijos : [];
            if (!hijos.length) {
                hijosEl.innerHTML = '<p class="linaje-empty">Aún no ha invitado a nadie.</p>';
            } else {
                hijosEl.innerHTML = hijos.map(h => host._linajeCardHtml(h)).join('');
                hijosEl.querySelectorAll('.linaje-card').forEach((el, idx) => {
                    el.addEventListener('click', () => host.abrirLinajeDrawer(hijos[idx]));
                });
            }
        })
        .catch(() => {
            if (meta) meta.textContent = 'Error de red al cargar linaje.';
        });
  }

  function abrirModalDetalle(host, aliado) {
    const modal = document.getElementById('aliadoDetalleModal');
    if (!modal) return;

    host._aliadoDetalleActual = aliado;

    const set = (id, value) => {
        const el = document.getElementById(id);
        if (el) el.textContent = value;
    };

    set('det-nombre', aliado.nombre || '');
    set('det-codigo', aliado.codigo || '');
    set('det-oficio', aliado.oficio || '');
    set('det-zona', aliado.zona || aliado.codigo_postal || '');
    set('det-marca', aliado.marca || '');
    set('det-contacto', (aliado.telefono || '') + (aliado.email ? ' • ' + aliado.email : ''));

    const esp = Array.isArray(aliado.especializaciones) ? aliado.especializaciones : [];
    set('det-especialidades', esp.length ? esp.join(', ') : '—');
    set('det-score', aliado.score_panel != null ? aliado.score_panel : (aliado.score || 0));
    set('det-estado', aliado.estado_panel || aliado.estado || 'activos');
    set('det-grupo', host.getGrupoTerritorialLabel ? host.getGrupoTerritorialLabel(aliado) : (aliado.grupo_nombre || '—'));

    set('det-total-contactos', aliado.total_contactos != null ? aliado.total_contactos : '—');
    set('det-contactos-30d', aliado.contactos_30d != null ? aliado.contactos_30d : '—');
    set('det-actividad-contactos', (aliado.total_contactos != null ? aliado.total_contactos : '—') + ' total · ' + (aliado.contactos_30d != null ? aliado.contactos_30d : '—') + ' en 30d');
    set('det-actividad-invitaciones', (aliado.hijos_directos_count != null ? aliado.hijos_directos_count : 0) + ' invitados directos');

    setupFichaTabs();
    activateFichaTab('datos');

    set('det-intencion', '—');
    set('det-tasa-respuesta', '—');
    set('det-tasa-confirmacion', '—');
    set('det-meses-sin-trabajo', '—');
    set('det-severidad', '—');
    set('det-evaluado-en', '—');
    set('det-razones', '—');

    const eliminarBtn = document.getElementById('aliadoDetalleEliminar');
    if (eliminarBtn) {
        const estadoBd = (aliado.estado || '').toLowerCase();
        const yaEliminado = estadoBd === 'expulsado' || estadoBd === 'rechazado' || estadoBd === 'sistema' || estadoBd === 'eliminado';
        eliminarBtn.disabled = yaEliminado;
        eliminarBtn.title = yaEliminado
            ? 'Este perfil ya está eliminado o no se puede borrar'
            : 'Eliminar perfil del aliado';
    }

    modal.classList.remove('hidden');

    var linajeBtn = document.getElementById('aliadoDetalleLinaje');
    if (linajeBtn) linajeBtn.onclick = function () { host.abrirLinajeDrawer(aliado); };
    var catBtn = document.getElementById('aliadoDetalleCatalogo');
    if (catBtn) catBtn.onclick = function () { host.abrirCatalogoServiciosModal(aliado); };
    var pausarBtn = document.getElementById('aliadoDetallePausar');
    if (pausarBtn) pausarBtn.onclick = function () { host.confirmarPausa(aliado); };

    // Cargar detalles de evaluación e histórico (endpoint admin: calcula si no hay fila en BD)
    if (aliado.codigo) {
        const authHeaders = AdminAuthenticator.getAdminAuthHeaders();
        fetch(`/api/admin/evaluaciones/${encodeURIComponent(aliado.codigo)}`, { method: 'GET', credentials: 'same-origin', headers: authHeaders })
            .then(r => r.ok ? r.json() : null)
            .then(data => {
                if (!data || data.status !== 'success' || !data.evaluacion) return;
                const ev = data.evaluacion;
                set('det-intencion', ev.intencion || '—');
                const tasaResp = ev.tasa_respuesta;
                const tasaConf = ev.tasa_confirmacion;
                set('det-tasa-respuesta', tasaResp != null ? (typeof tasaResp === 'number' ? (tasaResp * 100).toFixed(1) + '%' : tasaResp) : '—');
                set('det-tasa-confirmacion', tasaConf != null ? (typeof tasaConf === 'number' ? (tasaConf * 100).toFixed(1) + '%' : tasaConf) : '—');
                set('det-meses-sin-trabajo', ev.meses_sin_trabajo != null ? ev.meses_sin_trabajo : '—');
                set('det-severidad', ev.severidad || '—');
                const fechaEv = ev.actualizado_en || ev.evaluado_en;
                set('det-evaluado-en', fechaEv ? (fechaEv.replace('T', ' ').substring(0, 19) || fechaEv) : '—');
                const razones = Array.isArray(ev.razones) ? ev.razones : [];
                set('det-razones', razones.length ? razones.join(' • ') : '—');
            })
            .catch(() => {});

        fetch(`/api/evaluaciones/${encodeURIComponent(aliado.codigo)}/historico`, {
            credentials: 'same-origin',
            headers: AdminAuthenticator.getAdminAuthHeaders(),
        })
            .then(r => r.ok ? r.json() : null)
            .then(data => {
                const cont = document.getElementById('det-historico');
                if (!cont) return;
                cont.innerHTML = '';
                if (!data || data.status !== 'success' || !Array.isArray(data.historico) || !data.historico.length) {
                    cont.textContent = 'Sin cambios registrados.';
                    return;
                }
                data.historico.slice(0, 10).forEach(h => {
                    const li = document.createElement('div');
                    li.className = 'historico-item';
                    const fecha = h.registrado_en || '';
                    li.textContent = `[${fecha}] ${h.estado_anterior || '—'} → ${h.estado_nuevo || '—'} (score ${h.score_anterior ?? '—'} → ${h.score_nuevo ?? '—'})`;
                    cont.appendChild(li);
                });
            })
            .catch(() => {});
    }
  }

  async function confirmarEliminarPerfil(host) {
    const aliado = host._aliadoDetalleActual;
    if (!aliado || !aliado.codigo) return;

    const nombre = aliado.nombre || aliado.codigo;
    const confirmFn = window.AdminShell && window.AdminShell.confirmDanger;
    let ok = false;
    if (confirmFn) {
        ok = await confirmFn({
            title: 'Eliminar perfil',
            description: `Vas a eliminar el perfil de ${nombre} (${aliado.codigo}).`,
            consequences: [
                'Se eliminarán todos los datos del aliado (perfil, contactos, notificaciones, etc.).',
                'El correo, teléfono y código quedarán liberados para un nuevo registro.',
                'En el árbol genealógico el nodo seguirá visible como «Usuario eliminado» para no romper el linaje.',
                'Solo quedará un registro de auditoría en «Aliados eliminados».',
                'Esta acción no se puede deshacer.'
            ],
            confirmPhrase: 'ELIMINAR'
        });
    } else {
        ok = window.confirm(`¿Eliminar el perfil de ${nombre} (${aliado.codigo})?`);
    }
    if (!ok) return;

    const motivo = window.prompt('Motivo (opcional):', '') || '';
    const authHeaders = AdminAuthenticator.getAdminAuthHeaders();
    const headers = Object.assign({}, authHeaders, { 'Content-Type': 'application/json' });

    try {
        const r = await fetch('/api/admin/eliminar-aliado', {
            method: 'POST',
            credentials: 'same-origin',
            headers,
            body: JSON.stringify({ codigo: aliado.codigo, motivo })
        });
        if (r.status === 401) { host._adminSessionExpired(); return; }
        if (r.status === 403) { host.showToast('Sin permiso de escritura (solo lectura).', 'error'); return; }
        const data = await r.json().catch(() => null);
        if (!data || data.status !== 'success') {
            host.showToast((data && data.message) ? data.message : 'No se pudo eliminar el perfil.', 'error');
            return;
        }
        host.showToast(data.message || 'Perfil eliminado.', 'success');
        host.cerrarModalDetalle();
        host.cargarDesdeApi();
    } catch (e) {
        host.showToast('Error de red al eliminar perfil.', 'error');
    }
  }

  function accionPausarAliado(host) {
      host._abrirModalAccionAdmin({
          title: 'Pausar aliado',
          bodyHtml: `
              <label class="modal-importe-label" style="display:block; margin-bottom:6px;">Código del aliado (5 dígitos) *</label>
              <input type="text" id="accion-pausar-codigo" placeholder="Ej: A0001" style="width:100%; padding:8px; margin-bottom:12px; box-sizing:border-box;" />
              <label class="modal-importe-label" style="display:block; margin-bottom:6px;">Motivo (opcional)</label>
              <input type="text" id="accion-pausar-razon" placeholder="Motivo de la pausa" style="width:100%; padding:8px; box-sizing:border-box;" />
          `,
          getPayload: () => ({
              codigo: (document.getElementById('accion-pausar-codigo')?.value || '').trim(),
              razon: (document.getElementById('accion-pausar-razon')?.value || '').trim() || ''
          }),
          validate: (p) => !p.codigo ? 'El código del aliado es obligatorio.' : null,
          getConfirmSummary: (p) => `¿Confirmar que desea <strong>pausar</strong> al aliado con código <strong>${p.codigo}</strong>?${p.razon ? ' Motivo: ' + p.razon : ''}`,
          execute: async (p) => {
              const r = await fetch('/api/aliado/pausar', { method: 'POST', credentials: 'same-origin', headers: host.getAuthHeaders(), body: JSON.stringify({ codigo: p.codigo, razon: p.razon }) });
              if (r.status === 401) { host._adminSessionExpired(); return; }
              const data = await r.json().catch(() => ({}));
              if (data.status === 'success') { host.showToast(data.message || 'Aliado pausado correctamente.', 'success'); host.cargarDesdeApi(); }
              else { host.showToast(data.message || 'Error al pausar.', 'error'); }
          }
      });
}

function accionCerrarOficio(host) {
      host._abrirModalAccionAdmin({
          title: 'Cerrar oficio',
          bodyHtml: `
              <label class="modal-importe-label" style="display:block; margin-bottom:6px;">ID del grupo *</label>
              <input type="number" id="accion-co-grupo" placeholder="Ej: 1" style="width:100%; padding:8px; margin-bottom:12px; box-sizing:border-box;" />
              <label class="modal-importe-label" style="display:block; margin-bottom:6px;">Oficio a cerrar *</label>
              <input type="text" id="accion-co-oficio" placeholder="Ej: Fontanería" style="width:100%; padding:8px; box-sizing:border-box;" />
          `,
          getPayload: () => ({
              grupo_id: document.getElementById('accion-co-grupo')?.value?.trim(),
              oficio: (document.getElementById('accion-co-oficio')?.value || '').trim()
          }),
          validate: (p) => !p.grupo_id || !p.oficio ? 'Grupo y oficio son obligatorios.' : null,
          getConfirmSummary: (p) => `¿Confirmar <strong>cerrar el oficio</strong> "${p.oficio}" en el grupo ${p.grupo_id}? No se asignarán nuevos aliados a esa plaza.`,
          execute: async (p) => {
              const r = await fetch('/api/admin/cerrar-oficio', { method: 'POST', credentials: 'same-origin', headers: host.getAuthHeaders(), body: JSON.stringify({ grupo_id: parseInt(p.grupo_id, 10), oficio: p.oficio }) });
              if (r.status === 401) { host._adminSessionExpired(); return; }
              if (r.status === 403) { host.showToast('Sin permiso de escritura (solo lectura).', 'error'); return; }
              const data = await r.json().catch(() => ({}));
              if (data.status === 'success') { host.showToast(data.message || 'Oficio cerrado.', 'success'); host.cargarDesdeApi(); }
              else { host.showToast(data.message || 'Error.', 'error'); }
          }
      });
}

async function activarAliadoPendiente(host, id, rowEl) {
      const authHeaders = AdminAuthenticator.getAdminAuthHeaders();
      try {
          const r = await fetch(`/api/admin/users/${id}/activate`, {
              method: 'PATCH',
              credentials: 'same-origin',
              headers: authHeaders
          });
          const data = await r.json();
          if (r.status === 401) { host._adminSessionExpired(); return; }
          if (data.status === 'success') {
              host.showToast('Aliado activado. Puede ingresar con su código.', 'success');
              // Actualización en tiempo real: quitar fila sin recargar
              if (rowEl && rowEl.parentNode) rowEl.remove();
              const tbody = document.getElementById('tbody-pendientes-validacion');
              const emptyEl = document.getElementById('pendientes-empty');
              if (emptyEl && tbody && !tbody.querySelector('tr')) emptyEl.style.display = 'block';
          } else {
              host.showToast(data.message || 'Error al activar', 'error');
          }
      } catch (e) {
          host.showToast('Error de conexión', 'error');
      }
}

async function rechazarAliadoPendiente(host, codigo, rowEl) {
      if (!confirm('¿Rechazar a este aliado? No podrá acceder al panel hasta que un administrador lo reactive.')) return;
      const authHeaders = AdminAuthenticator.getAdminAuthHeaders();
      try {
          const r = await fetch('/api/admin/rechazar-aliado', {
              method: 'POST',
              credentials: 'same-origin',
              headers: authHeaders,
              body: JSON.stringify({ codigo })
          });
          const data = await r.json();
          if (r.status === 401) { host._adminSessionExpired(); return; }
          if (data.status === 'success') {
              host.showToast('Aliado rechazado. No podrá entrar al panel.', 'success');
              if (rowEl && rowEl.parentNode) rowEl.remove();
              const tbody = document.getElementById('tbody-pendientes-validacion');
              const emptyEl = document.getElementById('pendientes-empty');
              if (emptyEl && tbody && !tbody.querySelector('tr')) emptyEl.style.display = 'block';
          } else {
              host.showToast(data.message || 'Error al rechazar', 'error');
          }
      } catch (e) {
          host.showToast('Error de conexión', 'error');
      }
}

function confirmarPausa(host, aliado) {
      if (!aliado || !aliado.codigo) return;
      const ok = window.confirm(`¿Pausar temporalmente al aliado ${aliado.nombre} (${aliado.codigo})?`);
      if (!ok) return;

      const razon = window.prompt('Motivo de la pausa (opcional):', '') || '';
      const authHeaders = AdminAuthenticator.getAdminAuthHeaders();
      const headers = Object.assign({}, authHeaders, { 'Content-Type': 'application/json' });

      fetch('/api/aliado/pausar', {
          method: 'POST',
          credentials: 'same-origin',
          headers,
          body: JSON.stringify({ codigo: aliado.codigo, razon })
      })
          .then(r => r.json().catch(() => null))
          .then(data => {
              if (!data || data.status !== 'success') {
                  alert(data && data.message ? data.message : 'No se pudo pausar al aliado.');
                  return;
              }
              host.cargarDesdeApi();
          })
          .catch(() => {
              alert('Error de red al pausar aliado.');
          });
}

function accionIncorporarSuplente(host, codigo) {
      host._abrirModalAccionAdmin({
          title: 'Incorporar Suplente en Espera',
          bodyHtml: `
              <p style="color:#ccc; margin-bottom:12px;">Aliado: <strong>${host.escapeHtml(codigo)}</strong></p>
              <label class="modal-importe-label" style="display:block; margin-bottom:6px;">ID de grupo (opcional — dejar vacío para asignar automáticamente)</label>
              <input type="number" id="accion-inc-grupo" placeholder="Dejar vacío = automático" style="width:100%; padding:8px; box-sizing:border-box;" />
          `,
          getPayload: () => ({
              grupo_id: (document.getElementById('accion-inc-grupo')?.value || '').trim() || null
          }),
          validate: () => null,
          getConfirmSummary: (p) => `¿Incorporar <strong>${host.escapeHtml(codigo)}</strong>${p.grupo_id ? ' al grupo ' + p.grupo_id : ' automáticamente'}?`,
          execute: async (p) => {
              const body = p.grupo_id ? { grupo_id: parseInt(p.grupo_id, 10) } : {};
              const r = await fetch(`/api/admin/suplentes-espera/${encodeURIComponent(codigo)}/incorporar`, { method: 'POST', credentials: 'same-origin', headers: host.getAuthHeaders(), body: JSON.stringify(body) });
              if (r.status === 401) { host._adminSessionExpired(); return; }
              if (r.status === 403) { host.showToast('Sin permiso de escritura (solo lectura).', 'error'); return; }
              const data = await r.json().catch(() => ({}));
              if (data.status === 'success') { host.showToast(data.message || 'Suplente incorporado.', 'success'); host.cargarDesdeApi(); }
              else { host.showToast(data.message || 'Error al incorporar.', 'error'); }
          }
      });
}

modules.red = {
    esAliadoPlaceholder: esAliadoPlaceholder,
    getClaveGrupoRed: getClaveGrupoRed,
    getNombreGrupoRed: getNombreGrupoRed,
    normalizarCpAliado: normalizarCpAliado,
    renderAliadosJerarquia: renderAliadosJerarquia,
    renderAliadosNivel1: renderAliadosNivel1,
    renderAliadosNivel2: renderAliadosNivel2,
    renderAliadosNivelOficios: renderAliadosNivelOficios,
    renderAliadosNivel3: renderAliadosNivel3,
    renderAliados: renderAliados,
    renderPendientesValidacion: renderPendientesValidacion,
    renderAliadosEliminados: renderAliadosEliminados,
    renderSolicitudesBaja: renderSolicitudesBaja,
    marcarSolicitudBaja: marcarSolicitudBaja,
    renderSuplentesEspera: renderSuplentesEspera,
    getGrupoTerritorialLabel: getGrupoTerritorialLabel,
    abrirCatalogoServiciosModal: abrirCatalogoServiciosModal,
    abrirLinajeDrawer: abrirLinajeDrawer,
    abrirModalDetalle: abrirModalDetalle,
    confirmarEliminarPerfil: confirmarEliminarPerfil,
  
    accionPausarAliado: accionPausarAliado,
    accionCerrarOficio: accionCerrarOficio,
    activarAliadoPendiente: activarAliadoPendiente,
    rechazarAliadoPendiente: rechazarAliadoPendiente,
    confirmarPausa: confirmarPausa,
    accionIncorporarSuplente: accionIncorporarSuplente,
};
})(typeof window !== 'undefined' ? window : globalThis);
