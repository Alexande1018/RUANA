/**
 * Módulo PrivatePanel `conexiones` (Campamento Base).
 * Envío de nueva solicitud de conexión desde el módulo Conexiones.
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
  };

  var ENVIO_TIMEOUT_MS = 18000;
  var envioEnCurso = false;

  function getApiBaseSafe() {
    if (typeof global.getApiBase === 'function') {
      return global.getApiBase();
    }
    return '';
  }

  function getAuthHeadersSafe(extra) {
    if (typeof global.getRuanaAuthHeaders === 'function') {
      return global.getRuanaAuthHeaders(extra || {});
    }
    return extra || {};
  }

  function aviso(msg, kind) {
    kind = kind || 'info';
    if (global.RuanaUI && typeof global.RuanaUI.toast === 'function') {
      global.RuanaUI.toast(msg, kind, 6000);
      return;
    }
    alert(msg);
  }

  function botonEnviar() {
    return document.getElementById('btn-enviar');
  }

  function setEnviando(activo) {
    var btn = botonEnviar();
    if (!btn) return;
    btn.disabled = !!activo;
    btn.setAttribute('aria-busy', activo ? 'true' : 'false');
    btn.textContent = activo ? 'Enviando...' : 'Enviar solicitud';
  }

  function mostrarExito(host, msg) {
    var box = document.getElementById('solicitud-success');
    if (host) host.solicitudSuccess = box || host.solicitudSuccess;
    if (box) {
      box.textContent = '✓ ' + msg;
      box.classList.add('show');
      box.hidden = false;
      box.setAttribute('role', 'status');
      setTimeout(function () {
        box.classList.remove('show');
      }, 8000);
    }
    aviso(msg, 'success');
  }

  function aplicarListadoSolicitudes(host, dataSol) {
    if (!host || !dataSol) return;
    if (typeof dataSol === 'object' && !Array.isArray(dataSol)) {
      host.solicitudesEntrantes = Array.isArray(dataSol.entrantes) ? dataSol.entrantes : [];
      host.solicitudesPropias = Array.isArray(dataSol.propias) ? dataSol.propias : [];
      host.solicitudesHistorial = Array.isArray(dataSol.historial) ? dataSol.historial : [];
    } else {
      host.solicitudesEntrantes = Array.isArray(dataSol) ? dataSol : [];
      host.solicitudesPropias = [];
      host.solicitudesHistorial = [];
    }
    if (typeof host.renderSolicitudes === 'function') {
      host.renderSolicitudes();
    }
  }

  function refrescarTrasEnvio(host, apiBase) {
    var headers = getAuthHeadersSafe();
    return fetch(apiBase + '/api/solicitudes', {
      credentials: 'same-origin',
      headers: headers,
    }).then(function (respSol) {
      if (!respSol.ok) return null;
      return respSol.json();
    }).then(function (dataSol) {
      if (dataSol) aplicarListadoSolicitudes(host, dataSol);
      if (host && typeof host.refreshAfterAction === 'function') {
        return host.refreshAfterAction(['metricas', 'solicitudes', 'alertas']);
      }
      return null;
    }).catch(function (err) {
      console.error('Error al refrescar tras enviar conexión:', err);
    });
  }

  /**
   * Manejar envío de solicitud de conexión.
   * @param {object} host PrivatePanel
   */
  async function handleEnviarSolicitud(host) {
    if (!host) {
      aviso('No se pudo enviar: recarga el panel.', 'error');
      return;
    }
    if (envioEnCurso) {
      aviso('Ya se está enviando esta solicitud. Espera un momento.', 'warning');
      return;
    }
    var oficioInput = document.getElementById('nueva-solicitud-oficio');
    var descInput = document.getElementById('nueva-solicitud') || host.nuevaSolicitud;
    host.nuevaSolicitud = descInput || host.nuevaSolicitud;
    var oficio = oficioInput ? oficioInput.value.trim() : '';
    var descripcion = descInput ? String(descInput.value || '').trim() : '';
    if (!oficio) {
      aviso('El oficio es obligatorio', 'error');
      return;
    }
    if (!descripcion) {
      aviso('La descripción es obligatoria', 'error');
      return;
    }
    if (descripcion.length < 5) {
      aviso('La descripción debe tener al menos 5 caracteres', 'error');
      return;
    }
    var codigo = host.codigoAliado || (host.aliado && host.aliado.codigo) || '';
    if (!codigo) {
      aviso('No hay sesión. Vuelve a entrar al panel.', 'error');
      return;
    }
    envioEnCurso = true;
    setEnviando(true);
    var apiBase = getApiBaseSafe();
    var url = apiBase + '/api/solicitudes';
    var controller = (typeof AbortController !== 'undefined') ? new AbortController() : null;
    var timer = null;
    if (controller) {
      timer = setTimeout(function () {
        try { controller.abort(); } catch (_) {}
      }, ENVIO_TIMEOUT_MS);
    }
    try {
      var fetchOpts = {
        method: 'POST',
        headers: getAuthHeadersSafe({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ oficio: oficio, descripcion: descripcion }),
        credentials: 'same-origin',
      };
      if (controller) fetchOpts.signal = controller.signal;
      var r = await fetch(url, fetchOpts);
      if (r.status === 401) {
        throw new Error('Sesión caducada. Cierra sesión y vuelve a entrar.');
      }
      if (!r.ok) {
        var txt = await r.text();
        throw new Error('HTTP ' + r.status + (txt ? ': ' + txt.slice(0, 100) : ''));
      }
      var data = await r.json().catch(function () { return {}; });
      if (data.ok === true || data.status === 'success') {
        if (oficioInput) oficioInput.value = '';
        if (descInput) descInput.value = '';
        var msg = (data.mensaje || '').trim();
        if (!msg && data.enrutamiento === 'profesional_grupo' && data.profesional) {
          msg = 'Solicitud enviada a ' + (data.profesional.nombre || 'el profesional') + '.';
        }
        if (!msg) msg = 'Solicitud enviada';
        mostrarExito(host, msg);
        var irARecomendacion = !!(data.requiere_aprobacion_proximidad ||
          (data.enrutamiento === 'proximidad' && data.proximidad));
        if (global.AliadoShell && typeof global.AliadoShell.show === 'function') {
          global.AliadoShell.show('solicitudes', irARecomendacion ? { skipScroll: true } : undefined);
        }
        envioEnCurso = false;
        setEnviando(false);
        refrescarTrasEnvio(host, apiBase).then(function () {
          if (!irARecomendacion) return;
          var el = document.getElementById('solicitudes-recomendacion-wrap') ||
            document.getElementById('inicio-recomendacion-wrap');
          if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
        });
        return;
      }
      aviso(data.error || data.message || 'Error al enviar', 'error');
    } catch (e) {
      var fallido = (e && e.name === 'AbortError')
        ? 'El envío tardó demasiado. Inténtalo de nuevo.'
        : ('Error al enviar: ' + ((e && e.message) || e));
      aviso(fallido, 'error');
    } finally {
      if (timer) clearTimeout(timer);
      envioEnCurso = false;
      setEnviando(false);
    }
  }

  modules.conexiones = {
    handleEnviarSolicitud: handleEnviarSolicitud,
  };
})(typeof window !== 'undefined' ? window : globalThis);
