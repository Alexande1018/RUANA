/**
 * Módulo PrivatePanel `centroComunicacion` (Campamento Base).
 * Overlay FAB de soporte: hilos, mensajes, envío y respuesta.
 * PrivatePanel conserva fachadas delgadas que delegan aquí.
 * fetchCentroComunicacionSnapshot puede vivir en el host (sync) o aquí.
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
    if (typeof global.getApiBase === 'function') return global.getApiBase();
    return '';
  }

  function getAuthHeadersSafe(extra) {
    if (typeof global.getRuanaAuthHeaders === 'function') {
      return global.getRuanaAuthHeaders(extra || {});
    }
    return extra || {};
  }

  function soporteToken(host) {
    if (host && host.soporteToken) return String(host.soporteToken);
    if (global.RUANA_APELACION_TOKEN) return String(global.RUANA_APELACION_TOKEN);
    return '';
  }

  function soporteEnModoToken(host) {
    return Boolean(soporteToken(host));
  }

  function soporteHeaders(host, extra) {
    if (soporteEnModoToken(host)) {
      return extra || {};
    }
    return getAuthHeadersSafe(extra);
  }

  function soporteUrls(host, conversacionId) {
    var token = soporteToken(host);
    if (token) {
      var tokenBase = '/api/apelar/' + encodeURIComponent(token) + '/centro-comunicacion';
      return {
        list: tokenBase,
        create: tokenBase,
        messages: tokenBase + '/' + Number(conversacionId) + '/mensajes',
        markRead: tokenBase + '/' + Number(conversacionId) + '/marcar-leida'
      };
    }
    var codigo = (host && (host.codigoAliado || (host.aliado && host.aliado.codigo))) || '';
    var aliadoBase = '/api/aliados/' + encodeURIComponent(codigo) + '/centro-comunicacion';
    return {
      list: aliadoBase,
      create: aliadoBase,
      messages: aliadoBase + '/' + Number(conversacionId) + '/mensajes',
      markRead: aliadoBase + '/' + Number(conversacionId) + '/marcar-leida'
    };
  }

  function applyTokenModeUi(host) {
    var nuevo = document.getElementById('ruana-help-new-wrap');
    if (nuevo) nuevo.hidden = soporteEnModoToken(host);
    var sub = document.getElementById('ruana-help-sub');
    if (sub && soporteEnModoToken(host)) {
      sub.textContent = 'Escribe tu apelación aquí. Tienes 5 días hábiles desde la notificación de expulsión.';
    }
  }

  function ensureHelpWidget() {
    if (document.getElementById('ruana-help-fab')) return;
    var mount = document.getElementById('ruana-help-mount') || document.body;
    var wrap = document.createElement('div');
    wrap.innerHTML =
      '<button type="button" class="ruana-help-fab" id="ruana-help-fab" aria-label="Hablar con el equipo de RUANA" title="Hablar con RUANA">' +
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>' +
        '<span class="ruana-help-fab-badge" id="ruana-help-fab-badge" aria-hidden="true">0</span>' +
      '</button>' +
      '<div class="ruana-help-overlay" id="ruana-help-overlay" aria-hidden="true">' +
        '<section class="ruana-help-center" id="ruana-help-center" role="dialog" aria-modal="true" aria-labelledby="ruana-help-title">' +
          '<div class="ruana-help-header">' +
            '<h2 class="ruana-help-title" id="ruana-help-title">Habla con el equipo de RUANA</h2>' +
            '<div class="ruana-help-header-actions">' +
              '<span class="ruana-help-pill" id="ruana-help-unread-pill">0 sin leer</span>' +
              '<button type="button" class="ruana-help-close" id="ruana-help-close" aria-label="Cerrar">✕</button>' +
            '</div>' +
          '</div>' +
          '<p class="ruana-help-sub" id="ruana-help-sub">Consultas, incidencias e ideas.</p>' +
          '<div class="ruana-help-layout">' +
            '<div class="ruana-help-card" id="ruana-help-new-wrap">' +
              '<h3 style="margin:0 0 10px;">Nuevo mensaje</h3>' +
              '<div class="ruana-help-form-row">' +
                '<input id="ruana-help-subject" class="ruana-help-input" maxlength="160" placeholder="Asunto" />' +
                '<select id="ruana-help-category" class="ruana-help-select">' +
                  '<option value="consulta">Consulta</option>' +
                '</select>' +
                '<textarea id="ruana-help-message" class="ruana-help-textarea" rows="4" maxlength="3000"></textarea>' +
                '<button type="button" class="btn-admin-action" id="ruana-help-send-btn">Enviar al equipo RUANA</button>' +
              '</div>' +
            '</div>' +
            '<div class="ruana-help-card">' +
              '<h3 style="margin:0 0 8px;">Conversación</h3>' +
              '<div class="ruana-help-list" id="ruana-help-threads"></div>' +
            '</div>' +
            '<div class="ruana-help-card">' +
              '<div id="ruana-help-thread-header" class="ruana-help-empty">Selecciona una conversación para ver el historial.</div>' +
              '<div class="ruana-help-messages" id="ruana-help-messages"></div>' +
              '<button type="button" class="ruana-activacion-btn ruana-activacion-whatsapp" id="ruana-activacion-whatsapp" hidden>Invitar por WhatsApp</button>' +
              '<div id="ruana-activacion-form" class="ruana-activacion-form" hidden>' +
                '<p class="ruana-activacion-lead">Puedes responder o saltar. Si respondes, el equipo lo lee aquí.</p>' +
                '<label class="ruana-activacion-label" for="ruana-activacion-oficio">¿A qué oficio de tu zona le pasarías trabajo?</label>' +
                '<select id="ruana-activacion-oficio" class="ruana-help-select"><option value="">Elige un oficio (opcional)</option></select>' +
                '<input id="ruana-activacion-oficio-otro" class="ruana-help-input" maxlength="80" placeholder="O escríbelo tú" />' +
                '<label class="ruana-activacion-label" for="ruana-activacion-encargo">¿Tienes ahora mismo algún encargo que no puedas hacer tú?</label>' +
                '<select id="ruana-activacion-encargo" class="ruana-help-select"><option value="">—</option><option value="Sí">Sí</option><option value="No">No</option></select>' +
                '<button type="button" class="ruana-activacion-btn ruana-activacion-btn-primary" id="ruana-activacion-crear" hidden>Crear solicitud</button>' +
                '<label class="ruana-activacion-label" for="ruana-activacion-freno">¿Qué te frenaría para pasar tu primer encargo por RUANA?</label>' +
                '<textarea id="ruana-activacion-freno" class="ruana-help-textarea" rows="2" maxlength="400" placeholder="Si quieres, en una frase"></textarea>' +
                '<div class="ruana-activacion-actions">' +
                  '<button type="button" class="ruana-activacion-btn ruana-activacion-btn-primary" id="ruana-activacion-enviar">Enviar</button>' +
                  '<button type="button" class="ruana-activacion-btn ruana-activacion-btn-secondary" id="ruana-activacion-saltar">Saltar</button>' +
                '</div>' +
              '</div>' +
              '<div class="ruana-help-form-row" id="ruana-help-reply-wrap">' +
                '<textarea id="ruana-help-reply" class="ruana-help-textarea" rows="3" maxlength="3000" placeholder="Escribe tu apelación..." disabled></textarea>' +
                '<button type="button" class="btn-admin-action" id="ruana-help-reply-btn" disabled>Enviar apelación</button>' +
              '</div>' +
            '</div>' +
          '</div>' +
        '</section>' +
      '</div>';
    mount.appendChild(wrap);
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

  function formatHelpStatus(estado) {
    var key = String(estado || 'pendiente').toLowerCase();
    var labels = {
      pendiente: 'Pendiente',
      en_revision: 'En revisión',
      respondido: 'Respondido',
      cerrado: 'Cerrado',
      reabierto: 'Reabierto'
    };
    return labels[key] || 'Pendiente';
  }

  function abrirCentroComunicacion(host) {
    ensureHelpWidget();
    applyTokenModeUi(host);
    var overlay = document.getElementById('ruana-help-overlay');
    var fab = document.getElementById('ruana-help-fab');
    if (!overlay) return;
    overlay.classList.add('is-open');
    overlay.setAttribute('aria-hidden', 'false');
    document.body.classList.add('ruana-help-open');
    if (fab) fab.classList.add('is-open');
    renderCentroComunicacion(host);
    var conversaciones = Array.isArray(host.soporteConversations) ? host.soporteConversations : [];
    var activacion = conversaciones.find(function (c) {
      return String(c.tipo || '') === 'activacion' && Number(c.tiene_no_leido_aliado || 0) > 0;
    });
    if (activacion && Number(host.soporteSelectedId) !== Number(activacion.id)) {
      seleccionarConversacionSoporte(host, activacion.id);
    }
    var subject = document.getElementById('ruana-help-subject');
    if (subject && !activacion) setTimeout(function () { subject.focus(); }, 220);
  }

  function cerrarCentroComunicacion() {
    var overlay = document.getElementById('ruana-help-overlay');
    var fab = document.getElementById('ruana-help-fab');
    if (!overlay) return;
    overlay.classList.remove('is-open');
    overlay.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('ruana-help-open');
    if (fab) fab.classList.remove('is-open');
  }

  function toggleCentroComunicacion(host) {
    var overlay = document.getElementById('ruana-help-overlay');
    if (!overlay) return;
    if (overlay.classList.contains('is-open')) cerrarCentroComunicacion();
    else abrirCentroComunicacion(host);
  }

  function renderMensajesCentroComunicacion(host) {
    if (!host) return;
    var box = document.getElementById('ruana-help-messages');
    var header = document.getElementById('ruana-help-thread-header');
    var reply = document.getElementById('ruana-help-reply');
    var replyBtn = document.getElementById('ruana-help-reply-btn');
    if (!box || !header || !reply || !replyBtn) return;
    var conv = (host.soporteConversations || []).find(function (c) {
      return Number(c.id) === Number(host.soporteSelectedId);
    });
    var mensajes = Array.isArray(host.soporteMensajes) ? host.soporteMensajes : [];
    if (!conv) {
      header.textContent = 'Selecciona una conversación para ver el historial.';
      box.innerHTML = '';
      reply.disabled = true;
      replyBtn.disabled = true;
      pintarActivacion(host, null, []);
      return;
    }
    header.innerHTML = '<strong>' + escapeHtmlSafe(host, conv.asunto || 'Consulta') + '</strong> · <span class="ruana-help-status estado-' + escapeHtmlSafe(host, conv.estado || 'pendiente') + '">' + formatHelpStatus(conv.estado) + '</span>';
    var esActivacion = String(conv.tipo || '') === 'activacion';
    var yaRespondio = (host && Number(host.activacionRespondidaId) === Number(host.soporteSelectedId)) || mensajes.some(function (m) { return (m.emisor_tipo || '') === 'aliado'; });
    var mostrarFormulario = esActivacion && !yaRespondio;
    reply.disabled = mostrarFormulario;
    replyBtn.disabled = mostrarFormulario;
    var replyWrap = document.getElementById('ruana-help-reply-wrap');
    if (replyWrap) replyWrap.hidden = mostrarFormulario;
    if (!mostrarFormulario) {
      reply.disabled = false;
      replyBtn.disabled = false;
    }
    box.innerHTML = mensajes.map(function (m) {
      var fromEquipo = (m.emisor_tipo || '') === 'admin' || (m.emisor_tipo || '') === 'sistema';
      var fecha = m.creado_en ? new Date(m.creado_en).toLocaleString('es-ES', { dateStyle: 'short', timeStyle: 'short' }) : '';
      return '<div class="ruana-help-message ' + (fromEquipo ? 'from-admin' : 'from-aliado') + '">' +
        escapeHtmlSafe(host, m.mensaje || '') +
        '<span class="ruana-help-meta">' + (fromEquipo ? 'Equipo RUANA' : 'Tú') + ' · ' + fecha + '</span>' +
      '</div>';
    }).join('');
    box.scrollTop = box.scrollHeight;
    pintarActivacion(host, conv, mensajes);
  }

  function mensajeTieneHueco(mensajes) {
    return (mensajes || []).some(function (m) {
      return String(m.mensaje || '').indexOf('Pásale tu código por WhatsApp') !== -1;
    });
  }

  function pintarActivacion(host, conv, mensajes) {
    bindActivacion(host);
    var form = document.getElementById('ruana-activacion-form');
    var whatsapp = document.getElementById('ruana-activacion-whatsapp');
    var esActivacion = conv && String(conv.tipo || '') === 'activacion';
    var yaLocal = host && Number(host.activacionRespondidaId) === Number(host.soporteSelectedId);
    var yaRespondio = yaLocal || (mensajes || []).some(function (m) { return (m.emisor_tipo || '') === 'aliado'; });
    if (form) form.hidden = !(esActivacion && !yaRespondio);
    if (whatsapp) whatsapp.hidden = !mensajeTieneHueco(mensajes);
    if (esActivacion && !yaRespondio) {
      cargarOficiosActivacion(host);
      var mensajesBox = document.getElementById('ruana-help-messages');
      if (mensajesBox && typeof mensajesBox.scrollIntoView === 'function') {
        setTimeout(function () { mensajesBox.scrollIntoView({ block: 'start' }); }, 60);
      }
    }
    var crear = document.getElementById('ruana-activacion-crear');
    var encargo = document.getElementById('ruana-activacion-encargo');
    if (crear) crear.hidden = !encargo || encargo.value !== 'Sí' || !esActivacion || yaRespondio;
  }

  var oficiosActivacionCargados = false;

  function cargarOficiosActivacion(host) {
    if (oficiosActivacionCargados) return;
    var select = document.getElementById('ruana-activacion-oficio');
    if (!select) return;
    oficiosActivacionCargados = true;
    var apiBase = getApiBaseSafe();
    fetch(apiBase + '/api/catalogo/oficios', { credentials: 'same-origin' })
      .then(function (r) { return r.json().catch(function () { return {}; }); })
      .then(function (data) {
        var lista = data && Array.isArray(data.oficios) ? data.oficios : [];
        lista.forEach(function (item) {
          var nombre = typeof item === 'string' ? item : (item && item.nombre) || '';
          nombre = String(nombre || '').trim();
          if (!nombre) return;
          var opt = document.createElement('option');
          opt.value = nombre;
          opt.textContent = nombre;
          select.appendChild(opt);
        });
      })
      .catch(function () {
        oficiosActivacionCargados = false;
      });
  }

  function bindActivacion(host) {
    var form = document.getElementById('ruana-activacion-form');
    if (!form || form.getAttribute('data-bound') === '1') return;
    form.setAttribute('data-bound', '1');
    var encargo = document.getElementById('ruana-activacion-encargo');
    if (encargo) {
      encargo.addEventListener('change', function () {
        var crear = document.getElementById('ruana-activacion-crear');
        if (crear) crear.hidden = encargo.value !== 'Sí';
      });
    }
    var crear = document.getElementById('ruana-activacion-crear');
    if (crear) {
      crear.addEventListener('click', function () {
        guardarYAbrirCrearSolicitud(host);
      });
    }
    var enviar = document.getElementById('ruana-activacion-enviar');
    var saltar = document.getElementById('ruana-activacion-saltar');
    if (enviar) enviar.addEventListener('click', function () { enviarRespuestaActivacion(host, false); });
    if (saltar) saltar.addEventListener('click', function () { enviarRespuestaActivacion(host, true); });
    var whatsapp = document.getElementById('ruana-activacion-whatsapp');
    if (whatsapp && whatsapp.getAttribute('data-bound') !== '1') {
      whatsapp.setAttribute('data-bound', '1');
      whatsapp.addEventListener('click', function () { abrirWhatsappActivacion(host); });
    }
  }

  function datosActivacion(saltar) {
    var otro = document.getElementById('ruana-activacion-oficio-otro');
    var select = document.getElementById('ruana-activacion-oficio');
    var frenoEl = document.getElementById('ruana-activacion-freno');
    var encargoEl = document.getElementById('ruana-activacion-encargo');
    if (saltar) {
      return { oficio: '', oficio_libre: '', encargo: '', freno: '', saltar: true };
    }
    return {
      oficio: select ? String(select.value || '').trim() : '',
      oficio_libre: otro ? String(otro.value || '').trim() : '',
      encargo: encargoEl ? String(encargoEl.value || '') : '',
      freno: frenoEl ? String(frenoEl.value || '').trim() : '',
      saltar: false
    };
  }

  function guardarYAbrirCrearSolicitud(host) {
    var aviso = 'No hemos podido guardar tus respuestas; puedes volver a enviarlas luego';
    return enviarRespuestaActivacion(host, false, { avisoSiFalla: aviso, silencioso: true }).then(function () {
      cerrarCentroComunicacion();
      if (global.AliadoShell && typeof global.AliadoShell.show === 'function') {
        global.AliadoShell.show('conexiones');
      }
    });
  }

  function avisarActivacion(texto, tipo) {
    if (global.RuanaUI && typeof global.RuanaUI.toast === 'function') {
      global.RuanaUI.toast(texto, tipo || 'warning');
      return;
    }
    alert(texto);
  }

  function enviarRespuestaActivacion(host, saltar, opciones) {
    opciones = opciones || {};
    if (!host) return Promise.resolve(false);
    var convId = Number(host.soporteSelectedId || 0);
    if (!convId) return Promise.resolve(false);
    if (Number(host.activacionRespondidaId) === convId) return Promise.resolve(true);
    if (host.activacionEnvioPendiente) return host.activacionEnvioPendiente;
    var cuerpo = { activacion: datosActivacion(saltar) };
    var apiBase = getApiBaseSafe();
    var urls = soporteUrls(host, convId);
    host.activacionEnvioPendiente = fetch(apiBase + urls.messages, {
      method: 'POST',
      credentials: 'same-origin',
      headers: soporteHeaders(host, { 'Content-Type': 'application/json' }),
      body: JSON.stringify(cuerpo)
    })
      .then(function (r) { return r.json().catch(function () { return {}; }); })
      .then(function (data) {
        if (!data || data.status !== 'success') {
          if (data && String(data.message || '').indexOf('Ya has respondido') !== -1) {
            host.activacionRespondidaId = convId;
            return true;
          }
          avisarActivacion(opciones.avisoSiFalla || (data && data.message) || 'No se pudo enviar.', opciones.avisoSiFalla ? 'warning' : 'error');
          return false;
        }
        host.activacionRespondidaId = convId;
        if (!opciones.silencioso) {
          avisarActivacion(saltar ? 'Preguntas saltadas.' : 'Respuesta enviada. Gracias.', 'success');
        }
        return seleccionarConversacionSoporte(host, convId).then(function () { return true; });
      })
      .catch(function () {
        avisarActivacion(opciones.avisoSiFalla || 'No se pudo enviar.', 'warning');
        return false;
      })
      .then(function (ok) {
        host.activacionEnvioPendiente = null;
        return ok;
      });
    return host.activacionEnvioPendiente;
  }

  function abrirWhatsappActivacion(host) {
    var inv = global.RuanaAliadoModules && global.RuanaAliadoModules.invitaciones;
    if (inv && typeof inv.invitarPorWhatsapp === 'function') {
      return inv.invitarPorWhatsapp(host);
    }
    if (global.RuanaUI) global.RuanaUI.toast('No se pudo abrir WhatsApp.', 'error');
    return Promise.resolve();
  }

  /**
   * Pinta hilos del centro de comunicación y badge FAB.
   * @param {object} host PrivatePanel
   */
  function renderCentroComunicacion(host) {
    if (!host) return;
    applyTokenModeUi(host);
    var list = document.getElementById('ruana-help-threads');
    var unreadPill = document.getElementById('ruana-help-unread-pill');
    var fabBadge = document.getElementById('ruana-help-fab-badge');
    if (!list || !unreadPill) return;
    var conversaciones = Array.isArray(host.soporteConversations) ? host.soporteConversations : [];
    var unreadCount = conversaciones.filter(function (c) {
      return Number(c.tiene_no_leido_aliado || 0) > 0;
    }).length;
    unreadPill.textContent = unreadCount + ' sin leer';
    if (fabBadge) {
      fabBadge.textContent = String(unreadCount);
      fabBadge.classList.toggle('is-visible', unreadCount > 0);
    }
    if (!conversaciones.length) {
      list.innerHTML = '<div class="ruana-help-empty">Aún no tienes conversaciones. Escríbenos y te respondemos por aquí.</div>';
      renderMensajesCentroComunicacion(host);
      return;
    }
    list.innerHTML = conversaciones.map(function (c) {
      var active = Number(c.id) === Number(host.soporteSelectedId) ? ' is-active' : '';
      var hasUnread = Number(c.tiene_no_leido_aliado || 0) > 0 ? ' has-unread' : '';
      var fecha = c.ultimo_mensaje_en ? new Date(c.ultimo_mensaje_en).toLocaleString('es-ES', { dateStyle: 'short', timeStyle: 'short' }) : '';
      return '<div class="ruana-help-thread-item' + active + hasUnread + '" data-conv-id="' + c.id + '">' +
        '<div style="display:flex;justify-content:space-between;gap:8px;align-items:center;">' +
          '<strong style="font-size:0.85rem;">' + escapeHtmlSafe(host, c.asunto || 'Consulta') + '</strong>' +
          '<span class="ruana-help-status estado-' + escapeHtmlSafe(host, c.estado || 'pendiente') + '">' + formatHelpStatus(c.estado) + '</span>' +
        '</div>' +
        '<div style="color:#cbd5e1;font-size:0.8rem;margin-top:6px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">' + escapeHtmlSafe(host, c.ultimo_mensaje_preview || 'Sin mensajes') + '</div>' +
        '<div class="ruana-help-meta">' + fecha + '</div>' +
      '</div>';
    }).join('');
    list.querySelectorAll('[data-conv-id]').forEach(function (el) {
      el.addEventListener('click', function () {
        seleccionarConversacionSoporte(host, el.getAttribute('data-conv-id'));
      });
    });
    renderMensajesCentroComunicacion(host);
  }

  function seleccionarConversacionSoporte(host, conversacionId) {
    if (!host) return Promise.resolve();
    var codigo = host.codigoAliado || (host.aliado && host.aliado.codigo) || '';
    if ((!codigo && !soporteEnModoToken(host)) || !conversacionId) return Promise.resolve();
    host.soporteSelectedId = Number(conversacionId);
    var apiBase = getApiBaseSafe();
    var urls = soporteUrls(host, conversacionId);
    return fetch(apiBase + urls.messages, {
      credentials: 'same-origin',
      headers: soporteHeaders(host)
    })
      .then(function (r) { return r.json().catch(function () { return {}; }); })
      .then(function (data) {
        host.soporteMensajes = data.status === 'success' && Array.isArray(data.mensajes) ? data.mensajes : [];
        return fetch(apiBase + urls.markRead, {
          method: 'POST',
          credentials: 'same-origin',
          headers: soporteHeaders(host)
        }).catch(function () { return null; });
      })
      .then(function () {
        if (typeof host.fetchCentroComunicacionSnapshot === 'function') {
          return host.fetchCentroComunicacionSnapshot();
        }
        return null;
      })
      .then(function () {
        renderCentroComunicacion(host);
      });
  }

  function enviarNuevoMensajeSoporte(host) {
    if (!host) return Promise.resolve();
    if (soporteEnModoToken(host)) {
      return responderConversacionSoporte(host);
    }
    var codigo = host.codigoAliado || (host.aliado && host.aliado.codigo) || '';
    if (!codigo) return Promise.resolve();
    var asuntoEl = document.getElementById('ruana-help-subject');
    var categoriaEl = document.getElementById('ruana-help-category');
    var mensajeEl = document.getElementById('ruana-help-message');
    if (!asuntoEl || !mensajeEl || !categoriaEl) return Promise.resolve();
    var asunto = (asuntoEl.value || '').trim();
    var mensaje = (mensajeEl.value || '').trim();
    if (!asunto || !mensaje) {
      if (global.RuanaUI) global.RuanaUI.toast('Completa asunto y mensaje.', 'warning');
      return Promise.resolve();
    }
    var apiBase = getApiBaseSafe();
    var urls = soporteUrls(host);
    return fetch(apiBase + urls.create, {
      method: 'POST',
      credentials: 'same-origin',
      headers: soporteHeaders(host, { 'Content-Type': 'application/json' }),
      body: JSON.stringify({ asunto: asunto, categoria: categoriaEl.value || 'consulta', mensaje: mensaje })
    })
      .then(function (r) { return r.json().catch(function () { return {}; }); })
      .then(function (data) {
        if (data.status !== 'success') {
          if (global.RuanaUI) global.RuanaUI.toast(data.message || 'No se pudo enviar el mensaje.', 'error');
          return null;
        }
        asuntoEl.value = '';
        mensajeEl.value = '';
        if (global.RuanaUI) global.RuanaUI.toast('Tu mensaje fue enviado. ✅', 'success');
        var convId = Number(data.conversacion_id || 0) || host.soporteSelectedId;
        var chain = typeof host.fetchCentroComunicacionSnapshot === 'function'
          ? host.fetchCentroComunicacionSnapshot()
          : Promise.resolve();
        return chain.then(function () {
          host.soporteSelectedId = convId;
          if (host.soporteSelectedId) {
            return seleccionarConversacionSoporte(host, host.soporteSelectedId);
          }
          renderCentroComunicacion(host);
        });
      });
  }

  function responderConversacionSoporte(host) {
    if (!host) return Promise.resolve();
    var codigo = host.codigoAliado || (host.aliado && host.aliado.codigo) || '';
    var convId = Number(host.soporteSelectedId || 0);
    if ((!codigo && !soporteEnModoToken(host)) || !convId) return Promise.resolve();
    var replyEl = document.getElementById('ruana-help-reply');
    if (!replyEl) return Promise.resolve();
    var mensaje = (replyEl.value || '').trim();
    if (!mensaje) return Promise.resolve();
    var apiBase = getApiBaseSafe();
    var urls = soporteUrls(host, convId);
    return fetch(apiBase + urls.messages, {
      method: 'POST',
      credentials: 'same-origin',
      headers: soporteHeaders(host, { 'Content-Type': 'application/json' }),
      body: JSON.stringify({ mensaje: mensaje })
    })
      .then(function (r) { return r.json().catch(function () { return {}; }); })
      .then(function (data) {
        if (data.status !== 'success') {
          if (global.RuanaUI) global.RuanaUI.toast(data.message || 'No se pudo responder.', 'error');
          return null;
        }
        replyEl.value = '';
        if (global.RuanaUI) global.RuanaUI.toast('Respuesta enviada al equipo RUANA. 💬', 'success');
        return seleccionarConversacionSoporte(host, convId);
      });
  }

  function render(host) {
    renderCentroComunicacion(host);
  }

  function refresh(host) {
    renderCentroComunicacion(host);
  }

  modules.centroComunicacion = {
    render: render,
    refresh: refresh,
    formatHelpStatus: formatHelpStatus,
    ensureHelpWidget: ensureHelpWidget,
    abrirCentroComunicacion: abrirCentroComunicacion,
    cerrarCentroComunicacion: cerrarCentroComunicacion,
    toggleCentroComunicacion: toggleCentroComunicacion,
    renderCentroComunicacion: renderCentroComunicacion,
    renderMensajesCentroComunicacion: renderMensajesCentroComunicacion,
    seleccionarConversacionSoporte: seleccionarConversacionSoporte,
    enviarNuevoMensajeSoporte: enviarNuevoMensajeSoporte,
    responderConversacionSoporte: responderConversacionSoporte,
  };
})(typeof window !== 'undefined' ? window : globalThis);
