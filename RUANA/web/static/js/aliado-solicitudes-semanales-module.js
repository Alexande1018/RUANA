/**
 * Módulo solicitudes semanales — panel, modales flotantes y acciones.
 */
(function (global) {
  'use strict';

  var modules = global.RuanaAliadoModules = global.RuanaAliadoModules || {};

  function getApiBaseSafe() {
    return typeof global.getApiBase === 'function' ? global.getApiBase() : '';
  }

  function getAuthHeadersSafe(extra) {
    if (typeof global.getRuanaAuthHeaders === 'function') {
      return global.getRuanaAuthHeaders(extra || {});
    }
    return extra || {};
  }

  function escapeHtml(str) {
    if (str == null || str === '') return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function nombreAliado(host) {
    return (host.aliado && host.aliado.nombre) || 'Aliado';
  }

  function semanaStorageKey(semana) {
    return 'ruana_sol_sem_prompt_' + (semana || '');
  }

  function formatoFecha(valor) {
    if (!valor) return '';
    var d = new Date(valor);
    if (Number.isNaN(d.getTime())) return '';
    return d.toLocaleString('es-ES', { dateStyle: 'medium', timeStyle: 'short' });
  }

  function iconoOficio(oficio) {
    var o = (oficio || '').toLowerCase();
    if (o.indexOf('foto') >= 0) return '📸';
    if (o.indexOf('fontan') >= 0) return '🔧';
    if (o.indexOf('abog') >= 0) return '⚖️';
    if (o.indexOf('electric') >= 0) return '⚡';
    return '🔔';
  }

  async function fetchSnapshot(host) {
    var apiBase = getApiBaseSafe();
    var resp = await fetch(apiBase + '/api/solicitudes-semanales', {
      credentials: 'same-origin',
      headers: getAuthHeadersSafe(),
    });
    if (!resp.ok) return null;
    var data = await resp.json();
    if (data.status === 'success' || data.semana_inicio) {
      host.solicitudesSemanales = data;
      return data;
    }
    return null;
  }

  function renderSeccion(host) {
    var lista = document.getElementById('solicitudes-semanales-list');
    var propiaWrap = document.getElementById('solicitudes-semanales-propia');
    if (!lista) return;
    var snap = host.solicitudesSemanales || {};
    var activas = Array.isArray(snap.activas_grupo) ? snap.activas_grupo : [];
    var propia = snap.propia;

    if (propiaWrap) {
      if (propia && propia.estado === 'activa') {
        var count = propia.interesados_count || 0;
        var interTxt = count > 0
          ? '🟢 ' + count + ' aliado' + (count === 1 ? '' : 's') + ' puede' + (count === 1 ? '' : 'n') + ' ayudarte'
          : '🟡 Buscando ayuda';
        var interList = '';
        if (Array.isArray(propia.interesados) && propia.interesados.length) {
          interList = '<ul class="sol-sem-interesados">' +
            propia.interesados.map(function (i) {
              return '<li>' + escapeHtml(i.aliado_nombre || i.aliado_codigo) + '</li>';
            }).join('') + '</ul>';
        }
        propiaWrap.innerHTML =
          '<div class="sol-sem-propia-card">' +
          '<h4 class="sol-sem-propia-title">TU SOLICITUD</h4>' +
          '<p class="sol-sem-propia-oficio">Necesitas: <strong>' + escapeHtml(propia.oficio) + '</strong></p>' +
          (propia.descripcion ? '<p class="sol-sem-propia-desc">' + escapeHtml(propia.descripcion) + '</p>' : '') +
          '<p class="sol-sem-propia-estado">' + interTxt + '</p>' +
          interList +
          '<p class="sol-sem-propia-meta">Publicada ' + escapeHtml(formatoFecha(propia.created_at)) + '</p>' +
          '</div>';
        propiaWrap.hidden = false;
      } else {
        propiaWrap.innerHTML = '';
        propiaWrap.hidden = true;
      }
    }

    lista.innerHTML = '';
    if (!activas.length) {
      lista.innerHTML = '<p class="solicitudes-empty">No hay solicitudes activas de otros aliados esta semana.</p>';
      return;
    }
    activas.forEach(function (s) {
      var card = document.createElement('article');
      card.className = 'sol-sem-card';
      var yaResp = s.mi_respuesta === 'puedo_ayudar' || s.mi_respuesta === 'no_puedo_ayudar' || s.mi_respuesta === 'conozco_alguien';
      card.innerHTML =
        '<div class="sol-sem-card-head">' +
        '<span class="sol-sem-icon">' + iconoOficio(s.oficio) + '</span>' +
        '<div class="sol-sem-card-text">' +
        '<strong>' + escapeHtml(s.solicitante_nombre) + '</strong> necesita un ' + escapeHtml(s.oficio) +
        '</div></div>' +
        (s.descripcion ? '<p class="sol-sem-card-desc">' + escapeHtml(s.descripcion) + '</p>' : '') +
        '<p class="sol-sem-card-meta">Necesidad profesional de esta semana · ' + escapeHtml(formatoFecha(s.created_at)) + '</p>' +
        (yaResp
          ? '<p class="sol-sem-ya-respondido">Ya respondiste a esta solicitud.</p>'
          : '<div class="sol-sem-actions">' +
            '<button type="button" class="btn-sol-sem-ayudar" data-id="' + s.id + '">Puedo ayudar</button>' +
            '</div>');
      lista.appendChild(card);
    });

    lista.querySelectorAll('.btn-sol-sem-ayudar').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var id = parseInt(btn.getAttribute('data-id'), 10);
        mostrarModalRespuesta(host, id);
      });
    });
  }

  function ocultarOverlay(id) {
    var el = document.getElementById(id);
    if (el) {
      el.classList.remove('show');
      el.setAttribute('aria-hidden', 'true');
    }
  }

  function mostrarOverlay(id) {
    var el = document.getElementById(id);
    if (el) {
      el.classList.add('show');
      el.setAttribute('aria-hidden', 'false');
    }
  }

  function mostrarPromptCrear(host) {
    var snap = host.solicitudesSemanales || {};
    if (snap.propia && snap.propia.estado === 'activa') {
      ocultarPromptCrear(host);
      return;
    }
    var semana = snap.semana_inicio || '';
    var st = localStorage.getItem(semanaStorageKey(semana));
    if (st === 'hidden') {
      mostrarMinimizado(host);
      return;
    }
    var overlay = document.getElementById('sol-sem-prompt-overlay');
    var titulo = document.getElementById('sol-sem-prompt-titulo');
    if (titulo) {
      titulo.textContent = nombreAliado(host) + ', ¿qué profesional necesitas esta semana?';
    }
    poblarSelectorOficios(host);
    mostrarOverlay('sol-sem-prompt-overlay');
    ocultarMinimizado();
  }

  function ocultarPromptCrear(host) {
    ocultarOverlay('sol-sem-prompt-overlay');
    ocultarMinimizado();
  }

  function mostrarMinimizado(host) {
    var el = document.getElementById('sol-sem-minimized');
    if (el) el.classList.add('visible');
  }

  function ocultarMinimizado() {
    var el = document.getElementById('sol-sem-minimized');
    if (el) el.classList.remove('visible');
  }

  function minimizarPrompt(host) {
    var semana = (host.solicitudesSemanales && host.solicitudesSemanales.semana_inicio) || '';
    localStorage.setItem(semanaStorageKey(semana), 'minimized');
    ocultarOverlay('sol-sem-prompt-overlay');
    mostrarMinimizado(host);
  }

  function poblarSelectorOficios(host) {
    var select = document.getElementById('sol-sem-oficio-select');
    if (!select) return;
    var snap = host.solicitudesSemanales || {};
    var oficios = Array.isArray(snap.oficios_grupo) ? snap.oficios_grupo : [];
    select.innerHTML = '<option value="">Seleccionar oficio</option>';
    oficios.forEach(function (o) {
      var opt = document.createElement('option');
      opt.value = o;
      opt.textContent = o;
      select.appendChild(opt);
    });
    var otro = document.createElement('option');
    otro.value = '__OTRO__';
    otro.textContent = '+ Otro profesional';
    select.appendChild(otro);
    var otroWrap = document.getElementById('sol-sem-otro-wrap');
    if (otroWrap) otroWrap.style.display = 'none';
    select.onchange = function () {
      if (otroWrap) otroWrap.style.display = select.value === '__OTRO__' ? 'block' : 'none';
    };
  }

  async function publicarSolicitud(host) {
    var select = document.getElementById('sol-sem-oficio-select');
    var otroInput = document.getElementById('sol-sem-otro-input');
    var detalle = document.getElementById('sol-sem-detalle-input');
    var btn = document.getElementById('sol-sem-btn-publicar');
    if (!select) return;
    var val = select.value;
    var esOtro = val === '__OTRO__';
    var oficio = esOtro ? (otroInput && otroInput.value.trim()) : val;
    var descripcion = detalle ? detalle.value.trim() : '';
    if (!oficio) {
      alert(esOtro ? 'Indica qué profesional necesitas' : 'Selecciona un oficio');
      return;
    }
    if (btn) {
      btn.disabled = true;
      btn.textContent = 'Publicando…';
    }
    try {
      var resp = await fetch(getApiBaseSafe() + '/api/solicitudes-semanales', {
        method: 'POST',
        credentials: 'same-origin',
        headers: getAuthHeadersSafe({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
          oficio: oficio,
          descripcion: descripcion,
          es_oficio_personalizado: esOtro,
        }),
      });
      var data = await resp.json().catch(function () { return {}; });
      if (!resp.ok) {
        throw new Error(data.error || 'No se pudo publicar');
      }
      var semana = (host.solicitudesSemanales && host.solicitudesSemanales.semana_inicio) || '';
      localStorage.setItem(semanaStorageKey(semana), 'hidden');
      ocultarPromptCrear(host);
      await fetchSnapshot(host);
      renderSeccion(host);
      if (typeof host.refreshAfterAction === 'function') {
        await host.refreshAfterAction(['solicitudes']);
      }
    } catch (e) {
      alert(e.message || 'Error al publicar');
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = 'PUBLICAR SOLICITUD';
      }
    }
  }

  var _respuestaPendienteId = null;

  function mostrarModalRespuesta(host, solicitudId) {
    var snap = host.solicitudesSemanales || {};
    var activas = snap.activas_grupo || [];
    var sol = activas.find(function (s) { return Number(s.id) === Number(solicitudId); });
    if (!sol) return;
    _respuestaPendienteId = solicitudId;
    var texto = document.getElementById('sol-sem-respuesta-texto');
    if (texto) {
      texto.innerHTML =
        '<strong>' + escapeHtml(sol.solicitante_nombre) + '</strong> necesita un ' +
        escapeHtml(sol.oficio) + '.<br>¿Puedes ayudarlo?';
    }
    mostrarOverlay('sol-sem-respuesta-overlay');
  }

  function mostrarConfirmPuedo(host, onConfirm) {
    var snap = host.solicitudesSemanales || {};
    var sol = (snap.activas_grupo || []).find(function (s) {
      return Number(s.id) === Number(_respuestaPendienteId);
    });
    if (!sol) return;
    var txt = document.getElementById('sol-sem-confirm-texto');
    if (txt) {
      txt.textContent =
        '¿Eres ' + (sol.oficio || 'el profesional solicitado') +
        '? Vas a abrir una negociación con ' + (sol.solicitante_nombre || 'el solicitante') + '.';
    }
    var overlay = document.getElementById('sol-sem-confirm-overlay');
    var btnOk = document.getElementById('sol-sem-confirm-ok');
    var btnCancel = document.getElementById('sol-sem-confirm-cancel');
    if (!overlay || !btnOk) return;
    mostrarOverlay('sol-sem-confirm-overlay');
    var handler = function () {
      btnOk.removeEventListener('click', handler);
      ocultarOverlay('sol-sem-confirm-overlay');
      onConfirm();
    };
    btnOk.addEventListener('click', handler);
    if (btnCancel) {
      btnCancel.onclick = function () {
        btnOk.removeEventListener('click', handler);
        ocultarOverlay('sol-sem-confirm-overlay');
      };
    }
  }

  async function ejecutarPuedoAyudar(host) {
    if (!_respuestaPendienteId) return;
    try {
      var resp = await fetch(
        getApiBaseSafe() + '/api/solicitudes-semanales/' + _respuestaPendienteId + '/puedo-ayudar',
        {
          method: 'POST',
          credentials: 'same-origin',
          headers: getAuthHeadersSafe(),
        }
      );
      var data = await resp.json().catch(function () { return {}; });
      if (!resp.ok) throw new Error(data.error || 'Error');
      ocultarOverlay('sol-sem-respuesta-overlay');
      await fetchSnapshot(host);
      renderSeccion(host);
      if (data.contacto_id && typeof host.abrirNegociacionContacto === 'function') {
        host.abrirNegociacionContacto(data.contacto_id, {
          nombre: data.solicitante_nombre,
          codigo: data.solicitante_codigo,
          oficio: data.oficio,
        });
      }
    } catch (e) {
      alert(e.message || 'No se pudo registrar tu respuesta');
    }
  }

  async function ejecutarNoPuedo(host) {
    if (!_respuestaPendienteId) return;
    try {
      var resp = await fetch(
        getApiBaseSafe() + '/api/solicitudes-semanales/' + _respuestaPendienteId + '/no-puedo-ayudar',
        {
          method: 'POST',
          credentials: 'same-origin',
          headers: getAuthHeadersSafe(),
        }
      );
      if (!resp.ok) {
        var data = await resp.json().catch(function () { return {}; });
        throw new Error(data.error || 'Error');
      }
      ocultarOverlay('sol-sem-respuesta-overlay');
      await fetchSnapshot(host);
      renderSeccion(host);
      actualizarModalEntrante(host);
    } catch (e) {
      alert(e.message || 'Error');
    }
  }

  function mostrarConfirmConozco(onConfirm) {
    var txt = document.getElementById('sol-sem-confirm-texto');
    if (txt) {
      txt.textContent =
        'Estás a punto de generar un código para invitar a un nuevo profesional a registrarse en RUANA.';
    }
    var btnOk = document.getElementById('sol-sem-confirm-ok');
    var btnCancel = document.getElementById('sol-sem-confirm-cancel');
    if (!btnOk) return;
    mostrarOverlay('sol-sem-confirm-overlay');
    var handler = function () {
      btnOk.removeEventListener('click', handler);
      ocultarOverlay('sol-sem-confirm-overlay');
      onConfirm();
    };
    btnOk.addEventListener('click', handler);
    if (btnCancel) {
      btnCancel.onclick = function () {
        btnOk.removeEventListener('click', handler);
        ocultarOverlay('sol-sem-confirm-overlay');
      };
    }
  }

  async function ejecutarConozco(host) {
    if (!_respuestaPendienteId) return;
    try {
      var resp = await fetch(
        getApiBaseSafe() + '/api/solicitudes-semanales/' + _respuestaPendienteId + '/conozco-alguien',
        {
          method: 'POST',
          credentials: 'same-origin',
          headers: getAuthHeadersSafe(),
        }
      );
      var data = await resp.json().catch(function () { return {}; });
      if (!resp.ok) {
        if (data.ya_en_grupo) {
          alert('Este profesional ya pertenece al grupo.');
          return;
        }
        throw new Error(data.error || 'Error');
      }
      ocultarOverlay('sol-sem-respuesta-overlay');
      await fetchSnapshot(host);
      renderSeccion(host);
      if (data.codigo) {
        alert('Código de invitación: ' + data.codigo);
      }
    } catch (e) {
      alert(e.message || 'Error');
    }
  }

  function solicitudesPendientesModal(host) {
    var snap = host.solicitudesSemanales || {};
    return (snap.activas_grupo || []).filter(function (s) {
      return !s.mi_respuesta;
    });
  }

  function actualizarModalEntrante(host) {
    var pendientes = solicitudesPendientesModal(host);
    if (!pendientes.length) {
      ocultarOverlay('sol-sem-entrante-overlay');
      return;
    }
    var sol = pendientes[0];
    _respuestaPendienteId = sol.id;
    var titulo = document.getElementById('sol-sem-entrante-titulo');
    var texto = document.getElementById('sol-sem-entrante-texto');
    if (titulo) titulo.textContent = 'SOLICITUD PARA ESTA SEMANA';
    if (texto) {
      texto.innerHTML =
        escapeHtml(sol.solicitante_nombre) + ' necesita un ' + escapeHtml(sol.oficio) + '.<br>¿Puedes ayudarlo?';
    }
    mostrarOverlay('sol-sem-entrante-overlay');
  }

  function bindUi(host) {
    var btnMin = document.getElementById('sol-sem-prompt-minimize');
    var btnPub = document.getElementById('sol-sem-btn-publicar');
    var mini = document.getElementById('sol-sem-minimized');
    if (btnMin) btnMin.addEventListener('click', function () { minimizarPrompt(host); });
    if (btnPub) btnPub.addEventListener('click', function () { publicarSolicitud(host); });
    if (mini) mini.addEventListener('click', function () {
      ocultarMinimizado();
      mostrarOverlay('sol-sem-prompt-overlay');
    });

    var btnPuedo = document.getElementById('sol-sem-btn-puedo');
    var btnNo = document.getElementById('sol-sem-btn-no-puedo');
    var btnConozco = document.getElementById('sol-sem-btn-conozco');
    var btnEntPuedo = document.getElementById('sol-sem-entrante-puedo');
    var btnEntNo = document.getElementById('sol-sem-entrante-no-puedo');
    var btnEntConozco = document.getElementById('sol-sem-entrante-conozco');

    if (btnPuedo) {
      btnPuedo.addEventListener('click', function () {
        mostrarConfirmPuedo(host, function () { ejecutarPuedoAyudar(host); });
      });
    }
    if (btnNo) btnNo.addEventListener('click', function () { ejecutarNoPuedo(host); });
    if (btnConozco) {
      btnConozco.addEventListener('click', function () {
        mostrarConfirmConozco(function () { ejecutarConozco(host); });
      });
    }
    if (btnEntPuedo) {
      btnEntPuedo.addEventListener('click', function () {
        mostrarConfirmPuedo(host, function () { ejecutarPuedoAyudar(host); });
      });
    }
    if (btnEntNo) btnEntNo.addEventListener('click', function () { ejecutarNoPuedo(host); });
    if (btnEntConozco) {
      btnEntConozco.addEventListener('click', function () {
        mostrarConfirmConozco(function () { ejecutarConozco(host); });
      });
    }
  }

  async function initSemanales(host) {
    bindUi(host);
    await fetchSnapshot(host);
    renderSeccion(host);
    var snap = host.solicitudesSemanales || {};
    if (!snap.propia || snap.propia.estado !== 'activa') {
      mostrarPromptCrear(host);
    } else {
      ocultarPromptCrear(host);
    }
    actualizarModalEntrante(host);
  }

  modules.solicitudesSemanales = {
    fetchSnapshot: fetchSnapshot,
    renderSeccion: renderSeccion,
    initSemanales: initSemanales,
    mostrarPromptCrear: mostrarPromptCrear,
  };
})(typeof window !== 'undefined' ? window : this);
