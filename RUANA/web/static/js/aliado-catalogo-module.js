/**
 * Módulo PrivatePanel `catalogo` (Campamento Base).
 * Catálogo de servicios del aliado (normalizar / render / guardar).
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
    referidos: null,
    acuerdos: null,
    centroComunicacion: null,
    invitaciones: null,
    alertas: null,
    catalogo: null,
    contactos: null,
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

  function normalizarCatalogoServicios(host, catalogoRaw) {
    const byPos = new Map();
    if (Array.isArray(catalogoRaw)) {
        catalogoRaw.forEach((item) => {
            const pos = Number(item && item.posicion);
            if (!Number.isInteger(pos) || pos < 1 || pos > 10) return;
            const descripcion = (item && item.descripcion ? String(item.descripcion) : '').trim();
            const precio = (item && item.precio ? String(item.precio) : '').trim();
            byPos.set(pos, {
                posicion: pos,
                descripcion: descripcion || '',
                precio: precio || '',
                configurado: Boolean(descripcion && precio),
            });
        });
    }
    const out = [];
    for (let i = 1; i <= 10; i += 1) {
        out.push(byPos.get(i) || {
            posicion: i,
            descripcion: '',
            precio: '',
            configurado: false,
        });
    }
    return out;
  }

  function renderCatalogoServicios(host) {
    const grid = document.getElementById('catalogo-servicios-grid');
    const btnAdd = document.getElementById('btn-catalogo-anadir');
    if (!grid) return;
    const aliadoData = host.aliado || {};
    const catalogo = host.normalizarCatalogoServicios(aliadoData.catalogo_servicios);
    const editando = host.catalogoEditandoPos;
    const configurados = catalogo.filter((s) => s.configurado);
    const editItem = editando
        ? catalogo.find((s) => s.posicion === editando)
        : null;

    // Mostrar configurados + la tarjeta en edición (aunque aún no esté configurada)
    const visibles = [];
    const seen = new Set();
    configurados.forEach((s) => {
        visibles.push(s);
        seen.add(s.posicion);
    });
    if (editItem && !seen.has(editItem.posicion)) {
        visibles.push(editItem);
    }
    visibles.sort((a, b) => a.posicion - b.posicion);

    if (!visibles.length) {
        grid.innerHTML = `
            <div class="catalogo-empty">
                <p>Aún no has añadido servicios al catálogo.</p>
                <p class="catalogo-empty-hint">Añade el primero con descripción y precio.</p>
            </div>`;
    } else {
        grid.innerHTML = visibles.map((servicio) => {
            const abierta = editando === servicio.posicion;
            if (!abierta && servicio.configurado) {
                return `
                    <article class="catalogo-servicio-card is-collapsed" data-servicio-pos="${servicio.posicion}" data-catalogo-toggle="${servicio.posicion}" role="button" tabindex="0" aria-expanded="false">
                        <div class="catalogo-servicio-summary">
                            <div class="catalogo-servicio-summary-main">
                                <span class="catalogo-servicio-num">Servicio ${servicio.posicion}</span>
                                <h4 class="catalogo-servicio-summary-title">${host.escapeHtml(host._catalogoResumenTitulo(servicio))}</h4>
                                <p class="catalogo-servicio-summary-precio">${host.escapeHtml(servicio.precio || '—')}</p>
                            </div>
                            <button type="button" class="catalogo-servicio-edit" data-servicio-edit="${servicio.posicion}">Editar</button>
                        </div>
                    </article>`;
            }
            return `
                <article class="catalogo-servicio-card is-open" data-servicio-pos="${servicio.posicion}" aria-expanded="true">
                    <div class="catalogo-servicio-head">
                        <span class="catalogo-servicio-num">${servicio.configurado ? `Servicio ${servicio.posicion}` : 'Nuevo servicio'}</span>
                        <span class="catalogo-servicio-state ${servicio.configurado ? 'ready' : 'pending'}">${servicio.configurado ? 'Editando' : 'En curso'}</span>
                    </div>
                    <label class="catalogo-servicio-label" for="catalogo-desc-${servicio.posicion}">Descripción</label>
                    <textarea id="catalogo-desc-${servicio.posicion}" data-servicio-desc="${servicio.posicion}" maxlength="1000" placeholder="Qué ofreces en este servicio" rows="3">${host.escapeHtml(servicio.descripcion || '')}</textarea>
                    <label class="catalogo-servicio-label" for="catalogo-precio-${servicio.posicion}">Precio</label>
                    <input id="catalogo-precio-${servicio.posicion}" type="text" data-servicio-precio="${servicio.posicion}" maxlength="120" placeholder="Ej: 45 € / hora" value="${host.escapeHtml(servicio.precio || '')}" />
                    <div class="catalogo-servicio-actions">
                        <button type="button" class="catalogo-servicio-save" data-servicio-save="${servicio.posicion}">Guardar</button>
                        <button type="button" class="catalogo-servicio-cancel" data-servicio-cancel="${servicio.posicion}">Cancelar</button>
                        <span class="catalogo-servicio-feedback" id="catalogo-servicio-feedback-${servicio.posicion}"></span>
                    </div>
                </article>`;
        }).join('');
    }

    const libres = catalogo.filter((s) => !s.configurado).length;
    const puedeAnadir = libres > 0 && editando == null;
    if (btnAdd) {
        btnAdd.hidden = !puedeAnadir;
        btnAdd.disabled = !puedeAnadir;
    }
    if (typeof RuanaUI !== 'undefined') {
        RuanaUI.initIcons(grid);
        if (btnAdd) RuanaUI.initIcons(btnAdd);
    }
  }

  async function guardarCatalogoServicio(host, posicion) {
    const codigo = host.codigoAliado || (host.aliado && host.aliado.codigo) || '';
    if (!codigo) return;
    const pos = Number(posicion);
    if (!Number.isInteger(pos) || pos < 1 || pos > 10) return;
    const inputDesc = document.querySelector(`[data-servicio-desc="${pos}"]`);
    const inputPrecio = document.querySelector(`[data-servicio-precio="${pos}"]`);
    const btnSave = document.querySelector(`[data-servicio-save="${pos}"]`);
    const feedback = document.getElementById(`catalogo-servicio-feedback-${pos}`);
    if (!inputDesc || !inputPrecio || !btnSave) return;
    const descripcion = (inputDesc.value || '').trim();
    const precio = (inputPrecio.value || '').trim();
    if (!descripcion || !precio) {
        if (feedback) feedback.textContent = 'Completa descripción y precio';
        if (typeof RuanaUI !== 'undefined') {
            RuanaUI.toast('Completa descripción y precio para guardar', 'warning', 2200);
        }
        return;
    }
    btnSave.disabled = true;
    if (feedback) feedback.textContent = 'Guardando...';
    try {
        const resp = await fetch(`/api/aliados/${encodeURIComponent(codigo)}/catalogo-servicios/${pos}`, {
            method: 'PUT',
            headers: getAuthHeadersSafe({ 'Content-Type': 'application/json' }),
            credentials: 'same-origin',
            body: JSON.stringify({
                descripcion: descripcion,
                precio: precio,
            })
        });
        const data = await resp.json();
        if (data.status !== 'success') {
            if (feedback) feedback.textContent = data.message || 'No se pudo guardar';
            return;
        }
        if (!host.aliado) host.aliado = {};
        const current = host.normalizarCatalogoServicios(host.aliado.catalogo_servicios);
        const idx = current.findIndex((s) => s.posicion === pos);
        if (idx >= 0) {
            current[idx] = {
                posicion: pos,
                descripcion: descripcion,
                precio: precio,
                configurado: true,
            };
        }
        host.aliado.catalogo_servicios = current;
        host.catalogoEditandoPos = null;
        host.renderCatalogoServicios();
        if (typeof RuanaUI !== 'undefined') {
            RuanaUI.toast('Servicio guardado en el catálogo', 'success', 1800);
        }
    } catch (e) {
        if (feedback) feedback.textContent = 'Error de conexión';
    } finally {
        btnSave.disabled = false;
    }
  }

    function abrirCatalogoEdicion(host, posicion) {
      const pos = Number(posicion);
      if (!Number.isInteger(pos) || pos < 1 || pos > 10) return;
      host.catalogoEditandoPos = pos;
      host.renderCatalogoServicios();
      const card = document.querySelector(`.catalogo-servicio-card[data-servicio-pos="${pos}"]`);
      if (card && typeof card.scrollIntoView === 'function') {
          card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }
      const inputDesc = document.querySelector(`[data-servicio-desc="${pos}"]`);
      if (inputDesc) {
          try { inputDesc.focus(); } catch (e) { /* ignore */ }
      }
  }

  function anadirEspecializacionCatalogo(host) {
      const catalogo = host.normalizarCatalogoServicios((host.aliado || {}).catalogo_servicios);
      const libre = host._primeraPosicionLibreCatalogo(catalogo);
      if (libre == null) {
          if (typeof RuanaUI !== 'undefined') {
              RuanaUI.toast('Has alcanzado el máximo de 10 servicios en el catálogo', 'info', 2200);
          }
          return;
      }
      host.abrirCatalogoEdicion(libre);
  }

  function cancelarEdicionCatalogo(host, posicion) {
      const pos = Number(posicion);
      const catalogo = host.normalizarCatalogoServicios((host.aliado || {}).catalogo_servicios);
      const item = catalogo.find((s) => s.posicion === pos);
      // Si era un hueco vacío sin guardar, solo cerramos; si tenía datos, restauramos vista resumen
      host.catalogoEditandoPos = null;
      host.renderCatalogoServicios();
      if (item && !item.configurado && typeof RuanaUI !== 'undefined') {
          RuanaUI.toast('Edición cancelada', 'info', 1400);
      }
  }

  function _catalogoResumenTitulo(host, servicio) {
      const desc = String(servicio.descripcion || '').trim();
      if (!desc) return `Servicio ${servicio.posicion}`;
      const primera = desc.split(/\n/)[0].trim();
      return primera.length > 72 ? `${primera.slice(0, 72)}…` : primera;
  }

  function _primeraPosicionLibreCatalogo(host, catalogo) {
      const item = (catalogo || []).find((s) => !s.configurado);
      return item ? item.posicion : null;
  }

modules.catalogo = {
    normalizarCatalogoServicios: normalizarCatalogoServicios,
    renderCatalogoServicios: renderCatalogoServicios,
    guardarCatalogoServicio: guardarCatalogoServicio,
  
    abrirCatalogoEdicion: abrirCatalogoEdicion,
    anadirEspecializacionCatalogo: anadirEspecializacionCatalogo,
    cancelarEdicionCatalogo: cancelarEdicionCatalogo,
    _catalogoResumenTitulo: _catalogoResumenTitulo,
    _primeraPosicionLibreCatalogo: _primeraPosicionLibreCatalogo,
};
})(typeof window !== 'undefined' ? window : globalThis);
