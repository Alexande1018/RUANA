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

  /**
   * Manejar envío de solicitud de conexión.
   * @param {object} host PrivatePanel
   */
  async function handleEnviarSolicitud(host) {
    if (!host) return;
    var oficioInput = document.getElementById('nueva-solicitud-oficio');
    var oficio = oficioInput ? oficioInput.value.trim() : '';
    var descripcion = host.nuevaSolicitud ? host.nuevaSolicitud.value.trim() : '';
    if (!oficio.trim()) {
      alert('El oficio es obligatorio');
      return;
    }
    if (!descripcion) {
      alert('La descripción es obligatoria');
      return;
    }
    if (descripcion.length < 5) {
      alert('La descripción debe tener al menos 5 caracteres');
      return;
    }
    var codigo = host.codigoAliado || (host.aliado && host.aliado.codigo) || '';
    if (!codigo) {
      alert('No hay sesión');
      return;
    }
    if (host.btnEnviar) {
      host.btnEnviar.disabled = true;
      host.btnEnviar.textContent = 'Enviando...';
    }
    var apiBase = getApiBaseSafe();
    var url = apiBase + '/api/solicitudes';
    try {
      var r = await fetch(url, {
        method: 'POST',
        headers: getAuthHeadersSafe({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ oficio: oficio, descripcion: descripcion }),
        credentials: 'same-origin',
      });
      if (!r.ok) {
        var txt = await r.text();
        throw new Error('HTTP ' + r.status + (txt ? ': ' + txt.slice(0, 100) : ''));
      }
      var data = await r.json().catch(function () { return {}; });
      if (data.ok === true || data.status === 'success') {
        if (oficioInput) oficioInput.value = '';
        if (host.nuevaSolicitud) host.nuevaSolicitud.value = '';
        if (host.solicitudSuccess) {
          host.solicitudSuccess.classList.add('show');
          setTimeout(function () {
            host.solicitudSuccess.classList.remove('show');
          }, 3000);
        }
        var respSol = await fetch(apiBase + '/api/solicitudes', {
          credentials: 'same-origin',
          headers: getAuthHeadersSafe(),
        });
        if (respSol.ok) {
          var dataSol = await respSol.json();
          if (dataSol && typeof dataSol === 'object' && !Array.isArray(dataSol)) {
            host.solicitudesEntrantes = Array.isArray(dataSol.entrantes) ? dataSol.entrantes : [];
            host.solicitudesPropias = Array.isArray(dataSol.propias) ? dataSol.propias : [];
            host.solicitudesHistorial = Array.isArray(dataSol.historial) ? dataSol.historial : [];
          } else {
            host.solicitudesEntrantes = Array.isArray(dataSol) ? dataSol : [];
            host.solicitudesPropias = [];
            host.solicitudesHistorial = [];
          }
        }
        if (typeof host.renderSolicitudes === 'function') {
          host.renderSolicitudes();
        }
        if (typeof host.refreshAfterAction === 'function') {
          await host.refreshAfterAction(['metricas', 'solicitudes', 'alertas']);
        }
      } else {
        alert(data.error || data.message || 'Error al enviar');
      }
    } catch (e) {
      alert('Error al enviar: ' + (e.message || e));
    }
    if (host.btnEnviar) {
      host.btnEnviar.disabled = false;
      host.btnEnviar.textContent = 'Enviar solicitud';
    }
  }

  modules.conexiones = {
    handleEnviarSolicitud: handleEnviarSolicitud,
  };
})(typeof window !== 'undefined' ? window : globalThis);
