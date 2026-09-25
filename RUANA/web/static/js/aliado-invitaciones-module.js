/**
 * Módulo PrivatePanel `invitaciones` (Campamento Base).
 * Códigos de invitación (perfil, solicitud, oficio) y modal asociado.
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
  };

  function getApiBaseSafe() {
    if (typeof global.getApiBase === 'function') return global.getApiBase();
    return '';
  }

  // Puntos reales al registrarse el invitado. No cambian las reglas:
  // +3 ampliar_red / solicitud → invitacion_service.consumir_invitacion_y_recompensar
  //    (aplicar_cambio_score(..., 3, 'aliado_referido_registro_valido'))
  // +5 crecimiento_grupo → CRECIMIENTO_GRUPO_SCORE_DELTA, tope CRECIMIENTO_GRUPO_MAX_RECOMPENSAS (10)
  var SCORE_AMPLIAR_RED = 3;
  var SCORE_CRECIMIENTO_GRUPO = 5;
  var SCORE_CRECIMIENTO_MAX = 10;
  var PUBLIC_APP_FALLBACK = 'https://ruana-4293f.web.app';

  function basePublicaInvitacion() {
    var origin = '';
    try {
      origin = (global.location && global.location.origin) || '';
    } catch (_) {
      origin = '';
    }
    if (!origin || /localhost|127\.0\.0\.1/i.test(origin)) {
      return PUBLIC_APP_FALLBACK;
    }
    return String(origin).replace(/\/$/, '');
  }

  function enlaceInvitacion(codigo) {
    var code = String(codigo || '').trim();
    return basePublicaInvitacion() + '/invite.html?codigo=' + encodeURIComponent(code);
  }

  function mensajeWhatsappInvitacion(codigo) {
    return 'Oye, me he apuntado a RUANA, una red de oficios de Alicante para pasarnos encargos por zona: lo que tú no haces me lo pasas y al revés. Entra con mi código: ' + enlaceInvitacion(codigo);
  }

  function urlWhatsappInvitacion(codigo) {
    return 'https://wa.me/?text=' + encodeURIComponent(mensajeWhatsappInvitacion(codigo));
  }

  function textoScoreInvitacion(puntos) {
    var base = 'Ganas puntos de Score por cada colega que se una.';
    var n = Number(puntos);
    if (n === SCORE_CRECIMIENTO_GRUPO) {
      return base + ' Con este código son +5 cuando se registra (hasta ' + SCORE_CRECIMIENTO_MAX + ' veces).';
    }
    if (n === SCORE_AMPLIAR_RED) {
      return base + ' Con este código son +3 cuando se registra.';
    }
    return base;
  }

  function aplicarNotaScore(puntos) {
    var note = document.getElementById('invite-score-note');
    if (note) note.textContent = textoScoreInvitacion(puntos);
  }

  function getAuthHeadersSafe(extra) {
    if (typeof global.getRuanaAuthHeaders === 'function') {
      return global.getRuanaAuthHeaders(extra || {});
    }
    return extra || {};
  }

  async function generarCodigoInvitacionPerfil(host) {
    const codigo = host.codigoAliado || (host.aliado && host.aliado.codigo) || '';
    if (!codigo) {
        alert('Sesión no válida');
        return;
    }
    const inviteBtns = Array.from(document.querySelectorAll('[data-action="invitar-aliado"]'));
    inviteBtns.forEach((btn) => { btn.disabled = true; });
    const zona = (host.aliado && host.aliado.codigo_postal) || '';
    const apiBase = getApiBaseSafe();
    try {
        const r = await fetch(apiBase + '/api/invitaciones/crear', {
            method: 'POST',
            headers: getAuthHeadersSafe({ 'Content-Type': 'application/json' }),
            body: JSON.stringify({ zona: zona }),
            credentials: 'same-origin'
        });
        const data = await r.json().catch(() => ({}));
        if (r.ok && data.status === 'success' && data.codigo) {
            host.currentCode = data.codigo;
            host.currentSolicitud = null;
            host.mostrarModalCodigoInvitacion(data.codigo, false, SCORE_AMPLIAR_RED);
            const modalText = document.querySelector('#modal-code .modal-text');
            if (modalText) {
                modalText.textContent = 'Comparte este código único con la persona que quieras invitar para que se registre como aliado:';
            }
        } else {
            alert(data.message || data.error || 'No se pudo generar el código. Intenta de nuevo.');
        }
    } catch (e) {
        alert('Error de conexión: ' + (e.message || e));
    } finally {
        inviteBtns.forEach((btn) => { btn.disabled = false; });
    }
  }

  async function generateInviteCode(host, solicitudId) {
    const solicitud = (host.solicitudesEntrantes || []).find(s => s.id == solicitudId);
    if (!solicitud) {
        alert('No se encontró la solicitud');
        return;
    }
    const codigo = host.codigoAliado || (host.aliado && host.aliado.codigo) || '';
    if (!codigo) {
        alert('Sesión no válida');
        return;
    }
    const aliadoId = (host.aliado && host.aliado.id) || host.aliadoId;
    const zona = (host.aliado && host.aliado.codigo_postal) || '';
    host.currentSolicitud = {
        por: solicitud.solicitante_nombre || solicitud.solicitante_codigo || '—',
        texto: (solicitud.descripcion || solicitud.oficio || '') + (solicitud.oficio ? ' (' + solicitud.oficio + ')' : '')
    };
    const apiBase = getApiBaseSafe();
    try {
        const r = await fetch(apiBase + '/api/invitaciones/crear', {
            method: 'POST',
            headers: getAuthHeadersSafe({ 'Content-Type': 'application/json' }),
            body: JSON.stringify({
                aliado_id: aliadoId,
                zona: zona,
                solicitud_id: parseInt(solicitudId, 10) || null
            }),
            credentials: 'same-origin'
        });
        const data = await r.json().catch(() => ({}));
        if (r.ok && data.status === 'success' && data.codigo) {
            host.currentCode = data.codigo;
            host.mostrarModalCodigoInvitacion(data.codigo, true, SCORE_AMPLIAR_RED);
            const modalText = document.querySelector('#modal-code .modal-text');
            if (host.currentSolicitud && modalText) {
                modalText.innerHTML = `
                    <strong>Profesional que pidió:</strong> ${host.escapeHtml(host.currentSolicitud.por)}<br>
                    <strong>Solicitud:</strong> ${host.escapeHtml(host.currentSolicitud.texto)}<br><br>
                    Entrega este código a esa persona para que se registre. La solicitud quedará como <strong>candidato pendiente</strong> hasta que se incorpore (máximo <strong>24 horas</strong>); si no se registra, la solicitud se reabrirá al grupo para que otro aliado pueda invitar.
                `;
            }
            try {
                await host.fetchSolicitudesSnapshot();
                host.renderSolicitudes();
            } catch (_) {
                // Fallback local: quitar de entrantes (ya no está pendiente) sin borrar el hilo
                host.solicitudesEntrantes = (host.solicitudesEntrantes || []).filter(s => s.id != solicitudId);
                host.renderSolicitudes();
            }
        } else {
            alert(data.message || data.error || 'No se pudo generar el código. Intenta de nuevo.');
        }
    } catch (e) {
        alert('Error de conexión: ' + (e.message || e));
    }
  }

  function _solicitudPorId(host, solicitudId) {
    var listas = [
      host.solicitudesPropias,
      host.solicitudesEntrantes,
      host.solicitudesHistorial,
    ];
    var i;
    var j;
    var lista;
    for (i = 0; i < listas.length; i += 1) {
      lista = listas[i] || [];
      for (j = 0; j < lista.length; j += 1) {
        if (lista[j] && lista[j].id == solicitudId) return lista[j];
      }
    }
    return null;
  }

  async function generarCodigoInvitarCercanoCp(host, solicitudId) {
    const sid = parseInt(solicitudId, 10);
    if (!sid) {
      alert('No se encontró la solicitud');
      return;
    }
    const solicitud = _solicitudPorId(host, sid);
    const codigo = host.codigoAliado || (host.aliado && host.aliado.codigo) || '';
    if (!codigo) {
      alert('Sesión no válida');
      return;
    }
    const aliadoId = (host.aliado && host.aliado.id) || host.aliadoId;
    const zona = (host.aliado && host.aliado.codigo_postal) || '';
    const oficio = (solicitud && (solicitud.oficio || solicitud.zona)) || '';
    const apiBase = getApiBaseSafe();
    try {
      const r = await fetch(apiBase + '/api/invitaciones/crear', {
        method: 'POST',
        headers: getAuthHeadersSafe({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
          aliado_id: aliadoId,
          zona: zona,
          solicitud_id: sid,
        }),
        credentials: 'same-origin',
      });
      const data = await r.json().catch(() => ({}));
      if (r.ok && data.status === 'success' && data.codigo) {
        host.currentCode = data.codigo;
        host.currentSolicitud = {
          por: (solicitud && (solicitud.solicitante_nombre || solicitud.solicitante_codigo)) || 'tú',
          texto: oficio ? ('Invitar a alguien más cerca · ' + oficio) : 'Invitar a alguien más cerca de tu CP',
        };
        host.mostrarModalCodigoInvitacion(data.codigo, true, SCORE_AMPLIAR_RED);
        const modalText = document.querySelector('#modal-code .modal-text');
        if (modalText) {
          modalText.innerHTML =
            'Comparte este código con <strong>alguien que conozcas más cerca de tu código postal</strong> para que se registre en RUANA.' +
            (oficio ? '<br><strong>Oficio:</strong> ' + host.escapeHtml(oficio) : '') +
            '<br><br>La solicitud quedará como <strong>candidato pendiente</strong> hasta que se incorpore (máximo <strong>24 horas</strong>). Si no se registra, volverás a ver la recomendación del aliado más cercano.';
        }
        try {
          if (typeof host.fetchSolicitudesSnapshot === 'function') {
            await host.fetchSolicitudesSnapshot();
          }
          if (typeof host.renderSolicitudes === 'function') {
            host.renderSolicitudes();
          }
        } catch (_) {
          if (typeof host.renderSolicitudes === 'function') host.renderSolicitudes();
        }
      } else {
        alert(data.message || data.error || 'No se pudo generar el código. Intenta de nuevo.');
      }
    } catch (e) {
      alert('Error de conexión: ' + (e.message || e));
    }
  }

  function mostrarModalCodigoInvitacion(host, codigo, desdeSolicitud, puntos) {
    const modal = document.getElementById('modal-code');
    const codeEl = document.getElementById('code-value');
    const codeMessageEl = modal ? modal.querySelector('.invite-code-message') : null;
    if (codeEl) codeEl.textContent = codigo || '---';
    if (codeMessageEl) codeMessageEl.textContent = desdeSolicitud ? 'Válido para una solicitud' : 'Código de invitación';
    aplicarNotaScore(puntos == null ? SCORE_AMPLIAR_RED : puntos);
    if (modal) modal.classList.add('show');
  }

  async function invitarPorWhatsapp(host) {
    var codigoAliado = (host && (host.codigoAliado || (host.aliado && host.aliado.codigo))) || '';
    if (!codigoAliado) {
      alert('Sesión no válida');
      return;
    }
    var zona = (host.aliado && host.aliado.codigo_postal) || '';
    var apiBase = getApiBaseSafe();
    try {
      var r = await fetch(apiBase + '/api/invitaciones/crear', {
        method: 'POST',
        headers: getAuthHeadersSafe({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ zona: zona }),
        credentials: 'same-origin'
      });
      var data = await r.json().catch(function () { return {}; });
      if (r.ok && data.status === 'success' && data.codigo) {
        host.currentCode = data.codigo;
        var url = urlWhatsappInvitacion(data.codigo);
        var opened = global.open(url, '_blank', 'noopener,noreferrer');
        if (!opened) global.location.href = url;
      } else {
        alert(data.message || data.error || 'No se pudo generar el código. Intenta de nuevo.');
      }
    } catch (e) {
      alert('Error de conexión: ' + (e.message || e));
    }
  }

  function enviarInvitacionWhatsapp(host) {
    var codeEl = document.getElementById('code-value');
    var codigo = (host && host.currentCode) || (codeEl && codeEl.textContent) || '';
    codigo = String(codigo).trim();
    if (!codigo || codigo === '---' || codigo === 'XXXXX') {
      alert('Error: No hay código disponible');
      return;
    }
    var url = urlWhatsappInvitacion(codigo);
    var opened = global.open(url, '_blank', 'noopener,noreferrer');
    if (!opened) {
      global.location.href = url;
    }
  }

  function registerInviteCodeWithBackend(host, code, solicitudId) {
    // Datos del aliado actual
    const aliadoData = host.aliado || {};
    const aliadoId = aliadoData.id || host.aliadoId;
    const zona = aliadoData.codigo_postal || '';
    const apiBase = getApiBaseSafe();
    fetch(apiBase + '/api/invitaciones/crear', {
        method: 'POST',
        headers: getAuthHeadersSafe({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
            aliado_id: aliadoId,
            zona: zona,
            solicitud_id: solicitudId || null
        })
    })
    .then(response => {
        console.log('Response status:', response.status);
        return response.json();
    })
    .then(result => {
        console.log('Result:', result);
        if (result.status === 'success') {
            // Código generado y registrado en backend
            const codigoGenerado = result.codigo;
            host.currentCode = codigoGenerado;

            // Actualizar el modal con contexto de la solicitud
            const codeValueEl = document.getElementById('code-value');
            const codeMessageEl = document.querySelector('.invite-code-message');
            const modalText = document.querySelector('.modal-text');

            console.log('Elements found:', { codeValueEl, codeMessageEl, modalText });

            if (codeValueEl) codeValueEl.textContent = codigoGenerado;

            // Personalizar el mensaje si hay solicitud
            if (host.currentSolicitud && modalText) {
                modalText.innerHTML = `
                    <strong>Profesional:</strong> ${host.escapeHtml(host.currentSolicitud.por)}<br>
                    <strong>Solicitud:</strong> ${host.escapeHtml(host.currentSolicitud.texto)}<br><br>
                    <strong>Instrucciones:</strong><br>
                    Entrega este código al profesional para que se registre en la app. Una vez registrado, podrá contactarte como aliado.
                `;
                if (codeMessageEl) codeMessageEl.textContent = `Válido por 7 días`;
            } else {
                if (codeMessageEl) codeMessageEl.textContent = `Válido para una solicitud`;
            }

            aplicarNotaScore(SCORE_AMPLIAR_RED);
            console.log('Modal:', host.modalCode);
            if (host.modalCode) {
                host.modalCode.classList.add('show');
                console.log('Modal shown, classes:', host.modalCode.className);
            } else {
                console.error('Modal element not found!');
            }
        } else {
            alert('Error generando código: ' + (result.message || 'Intenta de nuevo'));
        }
    })
    .catch(error => {
        console.error('Fetch error:', error);
        alert('Error al generar código de invitación: ' + error.message);
    });
  }

  function getFechaExpiracion(host, dias) {
    const fecha = new Date();
    fecha.setDate(fecha.getDate() + dias);
    return fecha.toISOString();
  }

  function generateRandomCode(host, length = 5) {
    // Generar código numérico de 5 dígitos
    // Esto asegura compatibilidad con la validación del backend
    // que espera exactamente 5 dígitos numéricos
    let code = '';
    for (let i = 0; i < length; i++) {
        code += Math.floor(Math.random() * 10);
    }
    return code;
  }

  async function generarInvitacionOficio(host, oficio) {
    const codigo = host.codigoAliado;
    if (!codigo) { alert('No hay código de aliado.'); return; }
    try {
        const resp = await fetch('/api/generar-invitacion', {
            method: 'POST',
            headers: getAuthHeadersSafe({ 'Content-Type': 'application/json' }),
            credentials: 'same-origin',
            body: JSON.stringify({ oficio })
        });
        const data = await resp.json();
        if (data.status === 'success' && data.codigo) {
            document.getElementById('modal-invitacion-oficio-nombre').textContent = oficio;
            document.getElementById('modal-invitacion-oficio-codigo').textContent = data.codigo;
            document.getElementById('modal-invitacion-oficio').classList.add('show');
            await host.refreshAfterAction(['metricas', 'alertas']);
        } else {
            alert(data.message || 'No se pudo generar el código.');
        }
    } catch (e) {
        alert('Error de conexión.');
    }
  }

  async function generarCodigoInvitacionCrecimientoGrupo(host) {
    const codigo = host.codigoAliado || (host.aliado && host.aliado.codigo) || '';
    if (!codigo) {
      alert('Sesión no válida');
      return;
    }
    const inviteBtns = Array.from(document.querySelectorAll('[data-action="invitar-crecimiento-grupo"]'));
    inviteBtns.forEach((b) => { b.disabled = true; });
    const apiBase = getApiBaseSafe();
    try {
      const r = await fetch(apiBase + '/api/invitaciones/crear', {
        method: 'POST',
        headers: getAuthHeadersSafe({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ crecimiento_grupo: true }),
        credentials: 'same-origin'
      });
      const data = await r.json().catch(() => ({}));
      if (r.ok && data.status === 'success' && data.codigo) {
        host.currentCode = data.codigo;
        host.currentSolicitud = null;
        host.mostrarModalCodigoInvitacion(data.codigo, false, SCORE_CRECIMIENTO_GRUPO);
        const modalText = document.querySelector('#modal-code .modal-text');
        if (modalText) {
          modalText.textContent = 'Comparte este código con un profesional de cualquier oficio para que se registre en RUANA y amplíe la red del grupo:';
        }
      } else {
        alert(data.message || data.error || 'No se pudo generar el código. Intenta de nuevo.');
      }
    } catch (e) {
      alert('Error de conexión: ' + (e.message || e));
    } finally {
      inviteBtns.forEach((b) => { b.disabled = false; });
    }
  }

  function copiarCodigoInvitacionOficio(host) {
    const el = document.getElementById('modal-invitacion-oficio-codigo');
    if (!el || !el.textContent) return;
    navigator.clipboard.writeText(el.textContent).then(() => {
        const btn = document.getElementById('btn-copiar-invitacion-oficio');
        if (btn) { const t = btn.textContent; btn.textContent = '¡Copiado!'; setTimeout(() => btn.textContent = t, 1500); }
    }).catch(() => alert('No se pudo copiar'));
  }

  function cerrarModalInvitacionOficio(host) {
    document.getElementById('modal-invitacion-oficio')?.classList.remove('show');
  }

  modules.invitaciones = {
    generarCodigoInvitacionPerfil: generarCodigoInvitacionPerfil,
    generarCodigoInvitacionCrecimientoGrupo: generarCodigoInvitacionCrecimientoGrupo,
    generateInviteCode: generateInviteCode,
    generarCodigoInvitarCercanoCp: generarCodigoInvitarCercanoCp,
    mostrarModalCodigoInvitacion: mostrarModalCodigoInvitacion,
    enviarInvitacionWhatsapp: enviarInvitacionWhatsapp,
    invitarPorWhatsapp: invitarPorWhatsapp,
    enlaceInvitacion: enlaceInvitacion,
    mensajeWhatsappInvitacion: mensajeWhatsappInvitacion,
    urlWhatsappInvitacion: urlWhatsappInvitacion,
    textoScoreInvitacion: textoScoreInvitacion,
    registerInviteCodeWithBackend: registerInviteCodeWithBackend,
    getFechaExpiracion: getFechaExpiracion,
    generateRandomCode: generateRandomCode,
    generarInvitacionOficio: generarInvitacionOficio,
    copiarCodigoInvitacionOficio: copiarCodigoInvitacionOficio,
    cerrarModalInvitacionOficio: cerrarModalInvitacionOficio,
  };
})(typeof window !== 'undefined' ? window : globalThis);
