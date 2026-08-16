/**
 * Módulo PrivatePanel `perfil` (Campamento Base).
 * Foto/avatar, detalles del perfil y edición básica de descripción.
 * PrivatePanel conserva fachadas delgadas que delegan aquí.
 * Catálogo, acuerdos y competencia siguen en PrivatePanel (llamados desde renderPerfil).
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

  function getIniciales(nombre) {
    var texto = (nombre || '').trim();
    return texto.split(/\s+/).filter(Boolean).slice(0, 2).map(function (p) {
      return p[0];
    }).join('').toUpperCase().slice(0, 2) || '?';
  }

  function mapEtiquetaAvatarStatus(status) {
    var key = (status || '').toString().trim().toLowerCase();
    var map = {
      elite: 'elite',
      destacado: 'destacado',
      estable: 'estable',
      en_riesgo: 'en_riesgo',
      competencia: 'competencia',
      activo: 'estable',
      observacion: 'en_riesgo',
      riesgo: 'competencia',
      inactivo: 'inactivo'
    };
    return map[key] || 'estable';
  }

  function renderAvatarHtml(host, fotoUrl, nombre, className, etiquetaStatus) {
    var iniciales = getIniciales(nombre);
    var foto = (fotoUrl || '').trim();
    var etiqueta = mapEtiquetaAvatarStatus(etiquetaStatus || 'estable');
    var etiquetaAttr = ' data-etiqueta="' + escapeHtmlSafe(host, etiqueta) + '"';
    if (foto) {
      return '<div class="' + className + ' avatar-has-photo"' + etiquetaAttr +
        '><img src="' + escapeHtmlSafe(host, foto) + '" alt="" class="ruana-avatar-photo"></div>';
    }
    return '<div class="' + className + '"' + etiquetaAttr +
      ' aria-hidden="true"><span class="ruana-avatar-iniciales">' +
      escapeHtmlSafe(host, iniciales) + '</span></div>';
  }

  function syncPerfilAvatarEtiqueta(status) {
    var avatarEl = document.getElementById('perfil-avatar');
    if (!avatarEl) return;
    avatarEl.dataset.etiqueta = mapEtiquetaAvatarStatus(status);
  }

  function aplicarAvatarPerfil(host, aliadoData) {
    var nombre = (aliadoData && aliadoData.nombre) || 'Nombre no disponible';
    var fotoUrl = (aliadoData && (aliadoData.foto_perfil_url || aliadoData.foto_perfil)) || '';
    var avatarEl = document.getElementById('perfil-avatar');
    var imgEl = document.getElementById('perfil-avatar-img');
    var inicialesEl = document.getElementById('perfil-avatar-iniciales');
    var btnQuitar = document.getElementById('btn-quitar-foto-perfil');
    var iniciales = getIniciales(nombre);
    if (inicialesEl) inicialesEl.textContent = iniciales;
    if (avatarEl) avatarEl.classList.toggle('avatar-has-photo', Boolean(fotoUrl));
    if (imgEl) {
      if (fotoUrl) {
        imgEl.src = fotoUrl;
        imgEl.hidden = false;
        if (inicialesEl) inicialesEl.hidden = true;
        if (btnQuitar) btnQuitar.hidden = false;
      } else {
        imgEl.removeAttribute('src');
        imgEl.hidden = true;
        if (inicialesEl) inicialesEl.hidden = false;
        if (btnQuitar) btnQuitar.hidden = true;
      }
    }
  }

  function subirFotoPerfil(host, file) {
    var codigo = host && host.codigoAliado;
    if (!codigo || !file) return Promise.resolve();
    var sid = null;
    try {
      sid = sessionStorage.getItem('ruana_session_id');
    } catch (_) {}
    if (!sid) {
      alert('Tu sesión expiró. Vuelve a iniciar sesión con tu código.');
      window.location.replace('/');
      return Promise.resolve();
    }
    var maxBytes = 15 * 1024 * 1024;
    if (file.size > maxBytes) {
      var mb = (file.size / (1024 * 1024)).toFixed(1);
      alert('La foto pesa ' + mb + ' MB. El máximo permitido es 15 MB. Prueba con otra imagen o reduce su tamaño.');
      var inputEarly = document.getElementById('input-foto-perfil');
      if (inputEarly) inputEarly.value = '';
      return Promise.resolve();
    }
    var formData = new FormData();
    formData.append('archivo', file);
    var inputEl = document.getElementById('input-foto-perfil');
    if (inputEl) inputEl.disabled = true;
    var apiBase = getApiBaseSafe();
    return fetch(apiBase + '/api/aliados/' + encodeURIComponent(codigo) + '/foto-perfil', {
      method: 'POST',
      credentials: 'same-origin',
      headers: getAuthHeadersSafe(),
      body: formData,
    })
      .then(function (resp) {
        if (resp.status === 401) {
          alert('Tu sesión expiró. Vuelve a iniciar sesión con tu código.');
          window.location.replace('/');
          return null;
        }
        return resp.json().then(function (data) {
          return { resp: resp, data: data };
        });
      })
      .then(function (result) {
        if (!result) return;
        var data = result.data;
        if (data.status === 'success') {
          if (!host.aliado) host.aliado = {};
          host.aliado.foto_perfil_url = data.foto_perfil_url || null;
          aplicarAvatarPerfil(host, host.aliado);
          var refresh = host.refreshAfterAction
            ? host.refreshAfterAction(['perfil', 'directorio'])
            : Promise.resolve();
          return Promise.resolve(refresh).then(function () {
            if (typeof global.RuanaUI !== 'undefined') {
              global.RuanaUI.toast('Foto de perfil actualizada', 'success');
            }
          });
        }
        alert(data.message || 'No se pudo subir la foto.');
      })
      .catch(function () {
        alert('Error de conexión al subir la foto.');
      })
      .then(function () {
        if (inputEl) {
          inputEl.value = '';
          inputEl.disabled = false;
        }
      });
  }

  function quitarFotoPerfil(host) {
    var codigo = host && host.codigoAliado;
    if (!codigo) return Promise.resolve();
    var confirmPromise = typeof global.RuanaUI !== 'undefined'
      ? global.RuanaUI.confirm('¿Quitar tu foto de perfil y volver a mostrar las iniciales?', { title: 'Quitar foto' })
      : Promise.resolve(confirm('¿Quitar tu foto de perfil y volver a mostrar las iniciales?'));
    return Promise.resolve(confirmPromise).then(function (ok) {
      if (!ok) return;
      var apiBase = getApiBaseSafe();
      return fetch(apiBase + '/api/aliados/' + encodeURIComponent(codigo) + '/foto-perfil', {
        method: 'DELETE',
        credentials: 'same-origin',
        headers: getAuthHeadersSafe(),
      })
        .then(function (resp) {
          if (resp.status === 401) {
            alert('Tu sesión expiró. Vuelve a iniciar sesión con tu código.');
            window.location.replace('/');
            return null;
          }
          return resp.json().then(function (data) {
            return { resp: resp, data: data };
          });
        })
        .then(function (result) {
          if (!result) return;
          var data = result.data;
          if (data.status === 'success') {
            if (!host.aliado) host.aliado = {};
            host.aliado.foto_perfil_url = null;
            aplicarAvatarPerfil(host, host.aliado);
            if (host.refreshAfterAction) {
              return host.refreshAfterAction(['perfil', 'directorio']);
            }
          } else {
            alert(data.message || 'No se pudo quitar la foto.');
          }
        })
        .catch(function () {
          alert('Error de conexión.');
        });
    });
  }

  function renderMensajesEncargo(host) {
    var lista = document.getElementById('perfil-mensajes-lista');
    var wrap = document.getElementById('perfil-mensajes-wrap');
    if (!lista) return;
    var ui = global.RuanaConversacionUI;
    var contactos = Array.isArray(host.contactosAbiertos) ? host.contactosAbiertos : [];
    if (ui && typeof ui.sortContactosParaMensajes === 'function') {
      contactos = ui.sortContactosParaMensajes(contactos);
    }
    if (!contactos.length) {
      lista.innerHTML = '<p class="perfil-mensajes-empty">No tienes conversaciones de encargo activas.</p>';
      if (wrap) wrap.style.display = '';
      if (window.AliadoShell && typeof window.AliadoShell.refresh === 'function') {
        window.AliadoShell.refresh();
      }
      return;
    }
    lista.innerHTML = contactos.map(function (c) {
      var contraparte = ui
        ? ui.resolveContraparte(host, c)
        : { nombre: 'Aliado', oficio: c.servicio || '', fotoUrl: '' };
      var preview = ui ? ui.previewFromContacto(host, c) : { texto: c.servicio || '', tiempo: '' };
      var pendiente = !!c.negociacion_requiere_mi_respuesta;
      var avatarHtml = ui
        ? ui.renderAvatarHtml(host, contraparte.fotoUrl, contraparte.nombre, 'perfil-mensaje-avatar')
        : '';
      return '<button type="button" class="perfil-mensaje-card' + (pendiente ? ' is-pendiente' : '') + '" role="listitem" data-contacto-id="' + c.id + '" aria-label="Abrir conversación con ' + escapeHtmlSafe(host, contraparte.nombre) + '">' +
        avatarHtml +
        '<div class="perfil-mensaje-body">' +
          '<p class="perfil-mensaje-nombre">' + escapeHtmlSafe(host, contraparte.nombre) + '</p>' +
          '<p class="perfil-mensaje-oficio">' + escapeHtmlSafe(host, contraparte.oficio) + '</p>' +
          '<p class="perfil-mensaje-preview">' + escapeHtmlSafe(host, preview.texto) + '</p>' +
        '</div>' +
        '<div class="perfil-mensaje-meta">' +
          (preview.tiempo ? '<span class="perfil-mensaje-time">' + escapeHtmlSafe(host, preview.tiempo) + '</span>' : '') +
          (pendiente ? '<span class="perfil-mensaje-badge" aria-hidden="true"></span>' : '') +
        '</div>' +
      '</button>';
    }).join('');
    lista.querySelectorAll('.perfil-mensaje-card').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var id = parseInt(btn.getAttribute('data-contacto-id') || '0', 10);
        if (!id) return;
        if (typeof host.abrirNegociacionContacto === 'function') {
          host.abrirNegociacionContacto(id, null);
        }
      });
    });
    if (wrap) wrap.style.display = '';
    if (window.AliadoShell && typeof window.AliadoShell.refresh === 'function') {
      window.AliadoShell.refresh();
    }
  }

  /**
   * Pinta nombre, marca, avatar, detalles y estado; delega catálogo/acuerdos/competencia al host.
   * @param {object} host PrivatePanel
   */
  function renderPerfil(host) {
    if (!host) return;
    var aliadoData = host.aliado || {};

    var nombre = aliadoData.nombre || 'Nombre no disponible';
    var nombreEl = document.getElementById('perfil-nombre');
    var marcaEl = document.getElementById('perfil-marca');
    if (nombreEl) nombreEl.textContent = nombre;
    if (marcaEl) marcaEl.textContent = aliadoData.marca || 'Marca no disponible';
    aplicarAvatarPerfil(host, aliadoData);

    var codigoEl = document.getElementById('detail-codigo');
    var oficioEl = document.getElementById('detail-oficio');
    if (codigoEl) codigoEl.textContent = aliadoData.codigo || host.codigoAliado || '---';
    if (oficioEl) oficioEl.textContent = aliadoData.oficio || '---';

    var esp = aliadoData.especializaciones;
    var espWrap = document.getElementById('detail-especializaciones-wrap');
    var espEl = document.getElementById('detail-especializaciones');
    if (espWrap && espEl) {
      if (Array.isArray(esp) && esp.length > 0) {
        espEl.textContent = esp.join(', ');
        espWrap.style.display = '';
      } else {
        espWrap.style.display = 'none';
      }
    }

    var postalEl = document.getElementById('detail-codigo-postal');
    if (postalEl) postalEl.textContent = aliadoData.codigo_postal || '---';

    var descripcionServicio = aliadoData.descripcion_servicio || aliadoData.descripcion || '(sin descripción)';
    var descEl = document.getElementById('detail-descripcion');
    var btnEditarDesc = document.getElementById('btn-editar-descripcion');
    if (descEl) {
      descEl.textContent = descripcionServicio;
    }
    if (btnEditarDesc) {
      btnEditarDesc.textContent = (descripcionServicio === '(sin descripción)' || !(aliadoData.descripcion_servicio || aliadoData.descripcion))
        ? 'Completar'
        : 'Editar';
    }

    var desdeTexto = '---';
    if (aliadoData.creado_en) {
      var d = new Date(aliadoData.creado_en);
      if (!isNaN(d.getTime())) {
        desdeTexto = d.toLocaleString('es-ES');
      }
    } else if (aliadoData.fecha_registro) {
      var d2 = new Date(aliadoData.fecha_registro);
      if (!isNaN(d2.getTime())) {
        desdeTexto = d2.toLocaleString('es-ES');
      }
    }
    var fechaEl = document.getElementById('detail-fecha');
    if (fechaEl) fechaEl.textContent = desdeTexto;

    var statusEl = document.getElementById('perfil-status');
    if (statusEl) {
      var estadoRuana = (aliadoData.estado_ruana || '').trim().toUpperCase();
      var estadoMap = {
        'ÉLITE': { status: 'elite', label: 'Élite' },
        'ELITE': { status: 'elite', label: 'Élite' },
        'DESTACADO': { status: 'destacado', label: 'Destacado' },
        'PRIORITARIO': { status: 'destacado', label: 'Destacado' },
        'ESTABLE': { status: 'estable', label: 'Estable' },
        'EN RIESGO': { status: 'en_riesgo', label: 'En riesgo' },
        'COMPETENCIA': { status: 'competencia', label: 'Competencia' },
        'EN COMPETENCIA': { status: 'competencia', label: 'En competencia' }
      };
      var statusTextEl = statusEl.querySelector('.status-text');
      if (estadoMap[estadoRuana]) {
        statusEl.dataset.status = estadoMap[estadoRuana].status;
        if (statusTextEl) statusTextEl.textContent = estadoMap[estadoRuana].label;
        syncPerfilAvatarEtiqueta(estadoMap[estadoRuana].status);
      } else {
        var estado = aliadoData.estado || aliadoData.status || 'observacion';
        var estadoNormalizado = (typeof host.normalizarEstado === 'function')
          ? host.normalizarEstado(estado)
          : 'observacion';
        statusEl.dataset.status = estadoNormalizado;
        var statusTexts = {
          activo: 'Activo',
          inactivo: 'Inactivo',
          observacion: 'En observación',
          riesgo: 'En riesgo'
        };
        if (statusTextEl) {
          statusTextEl.textContent = statusTexts[estadoNormalizado] || 'Estado desconocido';
        }
        syncPerfilAvatarEtiqueta(estadoNormalizado);
      }
    }

    if (typeof host.renderCatalogoServicios === 'function') host.renderCatalogoServicios();
    if (typeof host.renderMisAcuerdos === 'function') host.renderMisAcuerdos();
    if (typeof host.renderCompetencia === 'function') host.renderCompetencia();
    renderMensajesEncargo(host);
  }

  function iniciarEditarDescripcion(host) {
    var formEl = document.getElementById('form-editar-descripcion');
    var inputEl = document.getElementById('input-descripcion-servicio');
    var rowEl = document.querySelector('.detail-descripcion-row');
    if (!formEl || !inputEl || !rowEl) return;
    var actual = (host && host.aliado && (host.aliado.descripcion_servicio || host.aliado.descripcion)) || '';
    inputEl.value = actual;
    rowEl.style.display = 'none';
    formEl.style.display = 'block';
    inputEl.focus();
  }

  function cancelarEditarDescripcion() {
    var formEl = document.getElementById('form-editar-descripcion');
    var rowEl = document.querySelector('.detail-descripcion-row');
    if (formEl) formEl.style.display = 'none';
    if (rowEl) rowEl.style.display = 'flex';
  }

  function guardarDescripcion(host) {
    var codigo = host && host.codigoAliado;
    if (!codigo) {
      alert('No se puede guardar: código de aliado no disponible.');
      return Promise.resolve();
    }
    var inputEl = document.getElementById('input-descripcion-servicio');
    var btnGuardar = document.getElementById('btn-guardar-descripcion');
    if (!inputEl || !btnGuardar) return Promise.resolve();
    var valor = (inputEl.value || '').trim();

    var proceed = Promise.resolve(true);
    if (!valor) {
      proceed = typeof global.RuanaUI !== 'undefined'
        ? global.RuanaUI.confirm(
          '¿Guardar sin descripción? Tu perfil mostrará "(sin descripción)" para el resto de aliados.',
          { title: 'Guardar perfil' }
        )
        : Promise.resolve(confirm(
          '¿Guardar sin descripción? Tu perfil mostrará "(sin descripción)" para el resto de aliados.'
        ));
    }

    return Promise.resolve(proceed).then(function (ok) {
      if (!ok) return;
      btnGuardar.disabled = true;
      return fetch('/api/aliados/' + encodeURIComponent(codigo), {
        method: 'PUT',
        headers: getAuthHeadersSafe({ 'Content-Type': 'application/json' }),
        credentials: 'same-origin',
        body: JSON.stringify({ descripcion_servicio: valor || null })
      })
        .then(function (resp) {
          return resp.json();
        })
        .then(function (data) {
          if (data.status === 'success') {
            if (!host.aliado) host.aliado = {};
            host.aliado.descripcion_servicio = valor || null;
            cancelarEditarDescripcion();
            renderPerfil(host);
            if (host.refreshAfterAction) {
              return host.refreshAfterAction(['perfil', 'directorio']);
            }
          } else {
            alert(data.message || 'No se pudo guardar.');
          }
        })
        .catch(function () {
          alert('Error de conexión al guardar.');
        })
        .then(function () {
          btnGuardar.disabled = false;
        });
    });
  }

  modules.perfil = {
    getIniciales: getIniciales,
    mapEtiquetaAvatarStatus: mapEtiquetaAvatarStatus,
    renderAvatarHtml: renderAvatarHtml,
    syncPerfilAvatarEtiqueta: syncPerfilAvatarEtiqueta,
    aplicarAvatarPerfil: aplicarAvatarPerfil,
    subirFotoPerfil: subirFotoPerfil,
    quitarFotoPerfil: quitarFotoPerfil,
    renderPerfil: renderPerfil,
    renderMensajesEncargo: renderMensajesEncargo,
    iniciarEditarDescripcion: iniciarEditarDescripcion,
    cancelarEditarDescripcion: cancelarEditarDescripcion,
    guardarDescripcion: guardarDescripcion,
  };
})(typeof window !== 'undefined' ? window : globalThis);
