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
            host.mostrarModalCodigoInvitacion(data.codigo, false);
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
            host.mostrarModalCodigoInvitacion(data.codigo, true);
            const modalText = document.querySelector('#modal-code .modal-text');
            if (host.currentSolicitud && modalText) {
                modalText.innerHTML = `
                    <strong>Profesional que pidió:</strong> ${host.escapeHtml(host.currentSolicitud.por)}<br>
                    <strong>Solicitud:</strong> ${host.escapeHtml(host.currentSolicitud.texto)}<br><br>
                    Entrega este código a esa persona para que se registre. La solicitud quedará como <strong>candidato pendiente</strong> hasta que se incorpore; entonces se le asignará automáticamente.
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

  function mostrarModalCodigoInvitacion(host, codigo, desdeSolicitud) {
    const modal = document.getElementById('modal-code');
    const codeEl = document.getElementById('code-value');
    const codeMessageEl = modal ? modal.querySelector('.invite-code-message') : null;
    if (codeEl) codeEl.textContent = codigo || '---';
    if (codeMessageEl) codeMessageEl.textContent = desdeSolicitud ? 'Válido para una solicitud' : 'Código de invitación';
    if (modal) modal.classList.add('show');
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

  function buildInvitacionOficioRegistroUrl(codigo) {
    const origin = global.RUANA_PUBLIC_APP_URL || window.location.origin;
    return `${origin}/invite.html?codigo=${encodeURIComponent(codigo || '')}`;
  }

  function buildMensajeCompartirInvitacionOficio(oficio, codigo, puntosScore, registroUrl) {
    const puntos = puntosScore != null ? puntosScore : 5;
    return (
      '¿Conoces un ' + oficio + '?\n\n' +
      'RUANA está buscando un profesional de este oficio para formar parte de un grupo de profesionales de su zona.\n\n' +
      'Si te registras con este código de invitación, el usuario que te invitó recibirá ' + puntos +
      ' puntos de score por tu incorporación justo después de que tu registro como aliado haya sido confirmado.\n\n' +
      'Regístrate en RUANA utilizando este código de invitación:\n\n' +
      codigo + '\n\n' +
      (registroUrl || buildInvitacionOficioRegistroUrl(codigo))
    );
  }

  async function generarInvitacionOficio(host, oficio) {
    const codigo = host.codigoAliado;
    if (!codigo) { alert('No hay código de aliado.'); return; }
    const apiBase = getApiBaseSafe();
    try {
        const resp = await fetch(apiBase + '/api/generar-invitacion', {
            method: 'POST',
            headers: getAuthHeadersSafe({ 'Content-Type': 'application/json' }),
            credentials: 'same-origin',
            body: JSON.stringify({ oficio })
        });
        const data = await resp.json();
        if (data.status === 'success' && data.codigo) {
            const registroUrl = data.registro_url || buildInvitacionOficioRegistroUrl(data.codigo);
            host._invitacionOficioActual = {
                oficio,
                codigo: data.codigo,
                registroUrl,
                puntosScore: data.puntos_score_recompensa,
            };
            const nombreEl = document.getElementById('modal-invitacion-oficio-nombre');
            const codigoEl = document.getElementById('modal-invitacion-oficio-codigo');
            const modalEl = document.getElementById('modal-invitacion-oficio');
            if (nombreEl) nombreEl.textContent = oficio;
            if (codigoEl) codigoEl.textContent = data.codigo;
            if (modalEl) modalEl.classList.add('show');
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
        host.mostrarModalCodigoInvitacion(data.codigo, false);
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
    const data = host._invitacionOficioActual;
    const texto = (data && data.codigo) || (document.getElementById('modal-invitacion-oficio-codigo') || {}).textContent;
    if (!texto || texto === '---') return;
    navigator.clipboard.writeText(texto).then(() => {
        const btn = document.getElementById('btn-copiar-invitacion-oficio');
        if (btn) { const t = btn.textContent; btn.textContent = '¡Copiado!'; setTimeout(() => btn.textContent = t, 1500); }
    }).catch(() => alert('No se pudo copiar'));
  }

  async function compartirInvitacionOficio(host) {
    const data = host._invitacionOficioActual;
    if (!data || !data.codigo) return;
    const mensaje = buildMensajeCompartirInvitacionOficio(
        data.oficio,
        data.codigo,
        data.puntosScore,
        data.registroUrl
    );
    const btn = document.getElementById('btn-compartir-invitacion-oficio');
    if (navigator.share) {
        try {
            await navigator.share({
                title: 'Invitación RUANA',
                text: mensaje,
            });
            return;
        } catch (e) {
            if (e && e.name === 'AbortError') return;
        }
    }
    try {
        await navigator.clipboard.writeText(mensaje);
        if (btn) {
            const t = btn.textContent;
            btn.textContent = '¡Mensaje copiado!';
            setTimeout(() => { btn.textContent = t; }, 1500);
        }
    } catch (_) {
        alert('No se pudo compartir ni copiar el mensaje.');
    }
  }

  function cerrarModalInvitacionOficio(host) {
    document.getElementById('modal-invitacion-oficio')?.classList.remove('show');
    host._invitacionOficioActual = null;
  }

  modules.invitaciones = {
    generarCodigoInvitacionPerfil: generarCodigoInvitacionPerfil,
    generarCodigoInvitacionCrecimientoGrupo: generarCodigoInvitacionCrecimientoGrupo,
    generateInviteCode: generateInviteCode,
    mostrarModalCodigoInvitacion: mostrarModalCodigoInvitacion,
    registerInviteCodeWithBackend: registerInviteCodeWithBackend,
    getFechaExpiracion: getFechaExpiracion,
    generateRandomCode: generateRandomCode,
    generarInvitacionOficio: generarInvitacionOficio,
    buildInvitacionOficioRegistroUrl: buildInvitacionOficioRegistroUrl,
    buildMensajeCompartirInvitacionOficio: buildMensajeCompartirInvitacionOficio,
    compartirInvitacionOficio: compartirInvitacionOficio,
    copiarCodigoInvitacionOficio: copiarCodigoInvitacionOficio,
    cerrarModalInvitacionOficio: cerrarModalInvitacionOficio,
  };
})(typeof window !== 'undefined' ? window : globalThis);
