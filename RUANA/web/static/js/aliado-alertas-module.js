/**
 * Módulo PrivatePanel `alertas` (Campamento Base).
 * Hub de alertas, pagos Apoyo RUANA, comprobantes e impugnación.
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

  function formatApoyoRuana(host, raw) {
    const apoyoNum = (raw != null && raw !== '' && !Number.isNaN(Number(raw))) ? Number(raw) : null;
    if (apoyoNum != null && Number.isFinite(apoyoNum) && apoyoNum > 0) {
        return apoyoNum.toFixed(2) + ' €';
    }
    return 'Pendiente de cálculo';
  }

  function buildCompetenciaAlertCopy(info, host) {
    if (!info) return null;
    const oficio = info.oficio || (host.aliado && host.aliado.oficio) || 'tu oficio';
    if (info.competencia_pendiente) {
      return {
        title: 'Competencia pendiente',
        description: info.mensaje || 'Esperando retador para iniciar la competencia por permanencia.',
        pendiente: true,
        criticalTone: 'prioritario',
      };
    }
    const rol = info.rol || 'titular';
    if (rol === 'retador') {
      return {
        title: 'Oportunidad de plaza',
        description: 'Compites por la plaza del grupo principal. Durante 30 días, quien acumule mayor score permanece en la plaza.',
        pendiente: false,
        criticalTone: 'competencia',
      };
    }
    return {
      title: 'En competencia',
      description: 'Compites por la permanencia en la plaza de ' + oficio + '. Al finalizar el periodo, gana quien tenga mayor score.',
      pendiente: false,
      criticalTone: 'competencia',
    };
  }

  function buildCompetenciaAlertMeta(info) {
    if (!info) return '';
    if (info.competencia_pendiente) {
      return 'Cuando haya un profesional disponible del mismo oficio y código postal, comenzará un periodo de 30 días.';
    }
    const partes = [];
    const dias = info.dias_restantes != null ? info.dias_restantes : null;
    if (dias != null) partes.push(dias + ' día' + (dias === 1 ? '' : 's') + ' restante' + (dias === 1 ? '' : 's'));
    if (info.fecha_fin_prevista) {
      const fin = new Date(String(info.fecha_fin_prevista).replace(' ', 'T'));
      if (!isNaN(fin.getTime())) {
        partes.push('Fin previsto: ' + fin.toLocaleDateString('es-ES'));
      }
    }
    if (info.contrincante_codigo) {
      partes.push('Contrincante: ' + info.contrincante_codigo);
    }
    return partes.join(' · ');
  }

  function buildAlertItems(host) {
    const items = [];
    const contactos = Array.isArray(host.contactosPagoPendiente) ? host.contactosPagoPendiente : [];
    const notifs = (Array.isArray(host.notificaciones) ? host.notificaciones : []).filter(n => n && n.leida === 0);
    const hub = typeof RuanaAlertHub !== 'undefined' ? RuanaAlertHub : null;
    const trunc = hub ? hub.truncate.bind(hub) : (s, n) => String(s || '').slice(0, n);

    if (host.aliado && typeof host.aliado.score === 'number' && host.aliado.score < 50) {
        items.push({
            id: 'score-bajo',
            type: 'info',
            critical: true,
            criticalTone: 'riesgo',
            priority: 300,
            title: 'Tu Score RUANA necesita atención',
            description: 'Tu Score RUANA está por debajo de 50. Mejora el cierre de contactos y la coherencia en importes para recuperar posición.',
            actionLabel: null,
            hasDetail: false,
            createdAt: Date.now()
        });
    }

    const competenciaInfo = (host.aliado && host.aliado.competencia_info) ? host.aliado.competencia_info : null;
    if (competenciaInfo && (competenciaInfo.en_competencia || competenciaInfo.competencia_pendiente)) {
        const compCopy = buildCompetenciaAlertCopy(competenciaInfo, host);
        if (compCopy) {
            items.push({
                id: 'competencia',
                type: 'action',
                critical: true,
                criticalTone: compCopy.criticalTone,
                priority: 320,
                title: compCopy.title,
                description: compCopy.description,
                actionLabel: 'Ver detalle',
                hasDetail: true,
                pendiente: !!competenciaInfo.competencia_pendiente,
                createdAt: Date.now()
            });
        }
    }

    if (global.RuanaStripePagos && global.RuanaStripePagos.stripePagosActivos() &&
        host.aliado && !global.RuanaStripePagos.isStripeConectado(host.aliado)) {
        items.push({
            id: 'stripe-pendiente',
            type: 'payment',
            critical: true,
            criticalTone: 'prioritario',
            priority: 310,
            title: 'Conecta tu cuenta de pago',
            description: 'Para recibir encargos pagados debes conectar tu cuenta de pago.',
            actionLabel: 'Conectar ahora',
            hasDetail: false,
            createdAt: Date.now()
        });
    }

    if (contactos.length > 0) {
        const first = contactos[0];
        const apoyo = host.formatApoyoRuana(first.apoyo_ruana);
        items.push({
            id: 'apoyo-pago',
            type: 'payment',
            priority: 100,
            title: contactos.length === 1 ? 'Apoyo RUANA (12%) pendiente' : contactos.length + ' apoyos RUANA pendientes',
            description: contactos.length === 1
                ? trunc((first.servicio || 'Contacto') + ' · ' + apoyo, 52)
                : 'Regulariza el 12% de ' + contactos.length + ' encargos cerrados',
            actionLabel: 'Gestionar',
            hasDetail: true
        });
        items.push({
            id: 'pagos-restriccion',
            type: 'info',
            priority: 70,
            title: 'Nuevos trabajos limitados',
            description: 'Regulariza tus pagos para aceptar encargos',
            actionLabel: null,
            hasDetail: false
        });
    }

    if (notifs.length > 0) {
        const firstN = notifs[0];
        items.push({
            id: 'mensajes-ruana',
            type: 'message',
            priority: 90,
            title: notifs.length === 1 ? (firstN.titulo || 'Mensaje de RUANA') : notifs.length + ' mensajes de RUANA',
            description: notifs.length === 1
                ? trunc(firstN.mensaje || '', 56)
                : 'Comunicaciones sin leer del equipo RUANA',
            actionLabel: 'Ver',
            hasDetail: true
        });
    }

    return items.sort((a, b) => b.priority - a.priority);
  }

  function renderAlertDetailPanel(host, detailEl, detailId) {
    const hub = typeof RuanaAlertHub !== 'undefined' ? RuanaAlertHub : null;
    if (!hub) return;
    const titles = {
        'apoyo-pago': 'Apoyo RUANA pendiente',
        'mensajes-ruana': 'Mensajes de RUANA',
        'competencia': 'Estado de competencia'
    };
    const body = hub.renderDetailHeader(detailEl, titles[detailId] || 'Detalle', function () {
        host._alertHubState.expandedDetailId = null;
        renderAlertHub(host);
    });

    if (detailId === 'apoyo-pago') {
        const contactos = Array.isArray(host.contactosPagoPendiente) ? host.contactosPagoPendiente : [];
        contactos.forEach(c => {
            const apoyo = host.formatApoyoRuana(c.apoyo_ruana);
            const servicio = host.escapeHtml(c.servicio || 'Contacto');
            const apoyoNum = (c.apoyo_ruana != null && c.apoyo_ruana !== '' && !Number.isNaN(Number(c.apoyo_ruana))) ? Number(c.apoyo_ruana) : 0;
            const div = document.createElement('div');
            div.className = 'ruana-alert-detail-item';
            div.innerHTML =
                '<div class="ruana-alert-detail-item__text">' +
                    'Contacto <strong>#' + c.id + '</strong> · ' + servicio +
                    ' · Apoyo: <strong>' + apoyo + '</strong>' +
                '</div>' +
                '<div class="ruana-alert-detail-item__actions">' +
                    '<button type="button" class="ruana-alert-detail-btn ruana-alert-detail-btn--primary btn-aceptar-pagar">Aceptar y pagar</button>' +
                    '<button type="button" class="ruana-alert-detail-btn btn-impugnar-apoyo">Reclamar</button>' +
                    '<button type="button" class="ruana-alert-detail-btn btn-enviar-comprobante">Comprobante</button>' +
                '</div>';
            div.querySelector('.btn-enviar-comprobante')?.addEventListener('click', () => host.abrirModalComprobanteApoyo(c.id));
            div.querySelector('.btn-aceptar-pagar')?.addEventListener('click', () => host.abrirModalPagoApoyo(c.id, apoyoNum, c.servicio || 'Contacto'));
            div.querySelector('.btn-impugnar-apoyo')?.addEventListener('click', () => host.abrirModalImpugnarApoyo(c.id));
            body.appendChild(div);
        });
    } else if (detailId === 'mensajes-ruana') {
        const notifs = (Array.isArray(host.notificaciones) ? host.notificaciones : []).filter(n => n && n.leida === 0);
        notifs.forEach(n => {
            const fecha = (n.creado_en ? new Date(n.creado_en).toLocaleString('es-ES', { dateStyle: 'short', timeStyle: 'short' }) : '');
            const div = document.createElement('div');
            div.className = 'ruana-alert-notif is-unread';
            div.innerHTML =
                '<div class="ruana-alert-notif__head">' +
                    '<span class="ruana-alert-notif__title">' + host.escapeHtml(n.titulo || 'Mensaje de RUANA') + '</span>' +
                    (fecha ? '<span class="ruana-alert-notif__date">' + fecha + '</span>' : '') +
                '</div>' +
                '<div class="ruana-alert-notif__body">' + host.escapeHtml(n.mensaje || '') + '</div>';
            body.appendChild(div);
        });
        const footer = document.createElement('div');
        footer.className = 'ruana-alert-hub__detail-footer';
        footer.innerHTML = '<button type="button" class="ruana-alert-detail-btn" id="btn-marcar-notificaciones-leidas">Marcar como leídos</button>';
        body.appendChild(footer);
        footer.querySelector('#btn-marcar-notificaciones-leidas')?.addEventListener('click', () => host.marcarTodasNotificacionesLeidas());
    } else if (detailId === 'competencia') {
        const info = (host.aliado && host.aliado.competencia_info) ? host.aliado.competencia_info : null;
        const compCopy = buildCompetenciaAlertCopy(info, host);
        const meta = buildCompetenciaAlertMeta(info);
        const div = document.createElement('div');
        div.className = 'ruana-alert-detail-item';
        let rolLabel = 'Titular';
        if (info && info.competencia_pendiente) rolLabel = 'Pendiente de retador';
        else if (info && info.rol === 'retador') rolLabel = 'Retador';
        div.innerHTML =
            '<div class="ruana-alert-detail-item__text">' +
                (compCopy ? '<strong>' + host.escapeHtml(compCopy.title) + '</strong><br>' : '') +
                host.escapeHtml((compCopy && compCopy.description) || '') +
                (meta ? '<br><span style="opacity:0.85">' + host.escapeHtml(meta) + '</span>' : '') +
                '<br><span style="opacity:0.75">Rol: ' + host.escapeHtml(rolLabel) + '</span>' +
            '</div>';
        body.appendChild(div);
    }
  }

  function renderAlertHub(host) {
    const hubEl = document.getElementById('ruana-alert-hub');
    if (!hubEl || typeof RuanaAlertHub === 'undefined') return;
    const items = host.buildAlertItems();

    if (items.length === 0) {
        host._alertHubState = { showAll: false, expandedDetailId: null };
    } else if (host._alertHubState.expandedDetailId &&
        !items.some(i => i.id === host._alertHubState.expandedDetailId)) {
        host._alertHubState.expandedDetailId = null;
    }

    RuanaAlertHub.render(hubEl, items, host._alertHubState, {
        onAction: function (item) {
            if (item.id === 'stripe-pendiente') {
                if (global.RuanaStripePagos && typeof global.RuanaStripePagos.iniciarOnboardingStripe === 'function') {
                    global.RuanaStripePagos.iniciarOnboardingStripe().catch(function (e) {
                        alert(e && e.message ? e.message : String(e));
                    });
                }
                return;
            }
            if (item.hasDetail) {
                host._alertHubState.expandedDetailId =
                    host._alertHubState.expandedDetailId === item.id ? null : item.id;
                host._alertHubState.showAll = true;
            }
            renderAlertHub(host);
        },
        onShowAll: function () {
            host._alertHubState.showAll = true;
            renderAlertHub(host);
        },
        renderDetail: function (detailEl, detailId) {
            renderAlertDetailPanel(host, detailEl, detailId);
        }
    });
  }

  function renderAlertas(host) {
    host.renderAlertHub();
  }

  async function cargarMetodosPagoRuana(host) {
    try {
        const resp = await fetch('/api/metodos-pago', { credentials: 'same-origin', headers: getAuthHeadersSafe() });
        if (!resp.ok) return;
        const data = await resp.json();
        if (data.status === 'success' && data.metodos) {
            host.metodosPagoRuana = {
                ...host.metodosPagoRuana,
                ...data.metodos
            };
        }
    } catch (e) {
        console.error('Error cargando metodos de pago RUANA:', e);
    }
  }

  async function actualizarEstadoAlertas(host) {
    const codigo = host.codigoAliado || (host.aliado && host.aliado.codigo) || '';
    if (!codigo) return;
    const apiBase = getApiBaseSafe();
    try {
        const [respNotif, respPagos] = await Promise.all([
            fetch(apiBase + '/api/aliados/' + encodeURIComponent(codigo) + '/notificaciones?limite=50', { credentials: 'same-origin', headers: getAuthHeadersSafe() }),
            fetch(apiBase + '/api/aliado/contactos-pago-pendiente', { credentials: 'same-origin', headers: getAuthHeadersSafe() })
        ]);
        const dataNotif = respNotif.ok ? await respNotif.json() : {};
        const dataPagos = respPagos.ok ? await respPagos.json() : {};
        const notifList = (dataNotif.status === 'success' && Array.isArray(dataNotif.notificaciones))
            ? dataNotif.notificaciones
            : [];
        const contactosPago = (dataPagos.status === 'success' && Array.isArray(dataPagos.contactos))
            ? dataPagos.contactos
            : [];
        host.notificaciones = notifList;
        host.contactosPagoPendiente = contactosPago;
        host.tienePagosPendientes = contactosPago.length > 0;

        host.renderNotificaciones();
        host.renderListaPagosPendientes();
        host.renderAlertas();
        host.maybeShowScoreChangeNotification();
    } catch (e) {
        console.error('Error actualizarEstadoAlertas:', e);
        host.renderAlertas();
    }
  }

  function renderListaPagosPendientes(host) {
    host.renderAlertHub();
  }

  function renderNotificaciones(host) {
    host.renderAlertHub();
  }

  async function marcarTodasNotificacionesLeidas(host) {
    const codigo = host.codigoAliado || (host.aliado && host.aliado.codigo) || '';
    if (!codigo) return;
    const apiBase = getApiBaseSafe();
    try {
        const r = await fetch(apiBase + '/api/aliados/' + encodeURIComponent(codigo) + '/notificaciones/marcar-todas-leidas', { method: 'POST', credentials: 'same-origin', headers: getAuthHeadersSafe() });
        const data = await r.json().catch(() => ({}));
        if (data.status === 'success') {
            // Recargar estado real y cerrar mensajes (ya no habrá no leídas)
            await host.actualizarEstadoAlertas();
            await host.refreshAfterAction(['alertas']);
        }
    } catch (e) {
        console.error('Error marcando notificaciones leídas:', e);
    }
  }

  async function cargarPagosApoyoPendientes(host) {
    const codigo = host.codigoAliado || (host.aliado && host.aliado.codigo) || '';
    if (!codigo) return;
    try {
        const resp = await fetch(`/api/aliado/contactos-pago-pendiente`, { credentials: 'same-origin', headers: getAuthHeadersSafe() });
        if (!resp.ok) return;
        const data = await resp.json();
        const contactos = (data.status === 'success' && Array.isArray(data.contactos)) ? data.contactos : [];
        host.contactosPagoPendiente = contactos;
        host.tienePagosPendientes = contactos.length > 0;
        host.renderListaPagosPendientes();
        host.renderAlertas();
    } catch (e) {
        console.error('Error cargando pagos apoyo pendientes:', e);
        host.contactosPagoPendiente = [];
        host.tienePagosPendientes = false;
        host.renderListaPagosPendientes();
        host.renderAlertas();
    }
  }

  function abrirModalComprobanteApoyo(host, contactoId) {
    host._contactoIdComprobante = contactoId;
    const modal = document.getElementById('modal-comprobante-apoyo');
    const input = document.getElementById('input-comprobante-apoyo');
    const comentario = document.getElementById('input-comprobante-apoyo-comentario');
    const resultado = document.getElementById('comprobante-apoyo-resultado');
    const nombreEl = document.getElementById('comprobante-apoyo-nombre');
    if (input) input.value = '';
    if (comentario) comentario.value = '';
    if (resultado) resultado.textContent = '';
    if (nombreEl) nombreEl.textContent = '';
    if (modal) modal.classList.add('show');
    // Abrir el selector de archivos del sistema en el mismo gesto de usuario (tras pintar el modal)
    if (input) {
        const abrirSelector = () => {
            try { input.click(); } catch (e) { console.warn('File input click:', e); }
        };
        setTimeout(abrirSelector, 150);
    }
  }

  function abrirModalPagoApoyo(host, contactoId, apoyoRuana, servicio) {
    const modal = document.getElementById('modal-pago-apoyo');
    const infoEl = document.getElementById('pago-apoyo-info');
    const bizumEl = document.getElementById('pago-apoyo-bizum-numero');
    const importeEl = document.getElementById('pago-apoyo-bizum-importe');
    const conceptoEl = document.getElementById('pago-apoyo-concepto');
    const qrRevolutEl = document.getElementById('pago-apoyo-revolut-qr');
    const revolutImporteEl = document.getElementById('pago-apoyo-revolut-importe');
    const ibanEl = document.getElementById('pago-apoyo-iban');
    const transferenciaImporteEl = document.getElementById('pago-apoyo-transferencia-importe');
    const transferenciaConceptoEl = document.getElementById('pago-apoyo-transferencia-concepto');
    if (!modal || !infoEl || !bizumEl || !importeEl || !conceptoEl || !qrRevolutEl || !revolutImporteEl || !ibanEl || !transferenciaImporteEl || !transferenciaConceptoEl) return;

    const importe = (apoyoRuana != null && !Number.isNaN(Number(apoyoRuana)) && Number(apoyoRuana) > 0)
        ? Number(apoyoRuana) : null;
    const importeStr = importe != null ? importe.toFixed(2) + ' EUR' : 'Pendiente de calculo';
    const concepto = `RUANA contacto #${contactoId}`;
    const metodos = host.metodosPagoRuana || {};
    const bizumNum = metodos.bizum_num || window.RUANA_BIZUM_NUM || '642868261';
    const iban = metodos.iban || window.RUANA_IBAN || 'ES8915830001119028625152';
    const qrRevolut = metodos.qr_revolut_path || window.RUANA_QR_REVOLUT_PATH || '/static/images/PayPal.png';

    host._contactoIdPagoActual = contactoId;
    infoEl.textContent = `Contacto #${contactoId} - ${servicio || 'Contacto'} - Apoyo RUANA: ${importeStr}`;
    bizumEl.textContent = bizumNum;
    importeEl.textContent = importeStr;
    conceptoEl.textContent = concepto;
    qrRevolutEl.src = qrRevolut;
    revolutImporteEl.textContent = importeStr;
    ibanEl.textContent = iban;
    transferenciaImporteEl.textContent = importeStr;
    transferenciaConceptoEl.textContent = concepto;
    host.setPagoApoyoMetodo('bizum');
    modal.classList.add('show');
  }

  function setPagoApoyoMetodo(host, metodo) {
    const bizumPanel = document.getElementById('pago-apoyo-bizum-panel');
    const revolutPanel = document.getElementById('pago-apoyo-revolut-panel');
    const transferenciaPanel = document.getElementById('pago-apoyo-transferencia-panel');
    const btnBizum = document.getElementById('btn-pago-apoyo-tab-bizum');
    const btnRevolut = document.getElementById('btn-pago-apoyo-tab-revolut');
    const btnTransferencia = document.getElementById('btn-pago-apoyo-tab-transferencia');
    const usaBizum = metodo === 'bizum';
    const usaRevolut = metodo === 'revolut';
    const usaTransferencia = metodo === 'transferencia';
    if (bizumPanel) bizumPanel.style.display = usaBizum ? 'block' : 'none';
    if (revolutPanel) revolutPanel.style.display = usaRevolut ? 'block' : 'none';
    if (transferenciaPanel) transferenciaPanel.style.display = usaTransferencia ? 'block' : 'none';
    if (btnBizum) {
        btnBizum.classList.toggle('confirm', usaBizum);
        btnBizum.classList.toggle('cancel', !usaBizum);
        btnBizum.setAttribute('aria-pressed', String(usaBizum));
    }
    if (btnRevolut) {
        btnRevolut.classList.toggle('confirm', usaRevolut);
        btnRevolut.classList.toggle('cancel', !usaRevolut);
        btnRevolut.setAttribute('aria-pressed', String(usaRevolut));
    }
    if (btnTransferencia) {
        btnTransferencia.classList.toggle('confirm', usaTransferencia);
        btnTransferencia.classList.toggle('cancel', !usaTransferencia);
        btnTransferencia.setAttribute('aria-pressed', String(usaTransferencia));
    }
  }

  function abrirModalPayPalApoyo(host, contactoId, apoyoRuana, servicio) {
    const modal = document.getElementById('modal-paypal-apoyo');
    const infoEl = document.getElementById('paypal-apoyo-info');
    const linkEl = document.getElementById('paypal-apoyo-link');
    if (!modal || !infoEl || !linkEl) return;
    const importe = (apoyoRuana != null && !Number.isNaN(Number(apoyoRuana)) && Number(apoyoRuana) > 0)
        ? Number(apoyoRuana) : null;
    const importeStr = importe != null ? importe.toFixed(2) + ' €' : 'Pendiente de cálculo';
    infoEl.textContent = `Contacto #${contactoId} · ${host.escapeHtml(servicio || 'Contacto')} · Apoyo RUANA: ${importeStr}`;
    const email = (typeof window.RUANA_PAYPAL_EMAIL !== 'undefined' && window.RUANA_PAYPAL_EMAIL) ? window.RUANA_PAYPAL_EMAIL : 'acerotrade.signal@gmail.com';
    const amountForUrl = importe != null ? importe.toFixed(2) : '0';
    const paypalUrl = `https://www.paypal.com/send?email=${encodeURIComponent(email)}&amount=${amountForUrl}`;
    linkEl.href = paypalUrl;
    linkEl.textContent = 'Continuar a PayPal';
    linkEl.setAttribute('title', 'Abrir PayPal para enviar pago a ' + email);
    modal.classList.add('show');
  }

  function abrirModalBizumApoyo(host, contactoId, apoyoRuana, servicio) {
    const modal = document.getElementById('modal-bizum-apoyo');
    const infoEl = document.getElementById('bizum-apoyo-info');
    const importeEl = document.getElementById('bizum-apoyo-importe');
    if (!modal || !infoEl || !importeEl) return;
    const importe = (apoyoRuana != null && !Number.isNaN(Number(apoyoRuana)) && Number(apoyoRuana) > 0)
        ? Number(apoyoRuana) : null;
    const importeStr = importe != null ? importe.toFixed(2) + ' €' : 'Pendiente de cálculo';
    infoEl.textContent = `Contacto #${contactoId} · ${host.escapeHtml(servicio || 'Contacto')}`;
    importeEl.textContent = importeStr;
    modal.classList.add('show');
  }

  async function enviarComprobanteApoyo(host) {
    const contactoId = host._contactoIdComprobante;
    const codigo = host.codigoAliado || (host.aliado && host.aliado.codigo) || '';
    const input = document.getElementById('input-comprobante-apoyo');
    const comentarioEl = document.getElementById('input-comprobante-apoyo-comentario');
    const resultadoEl = document.getElementById('comprobante-apoyo-resultado');
    if (!contactoId || !codigo) {
        if (resultadoEl) resultadoEl.textContent = 'Sesión o contacto no válido.';
        return;
    }
    if (!input || !input.files || !input.files.length) {
        if (resultadoEl) resultadoEl.textContent = 'Elige una imagen o PDF.';
        return;
    }
    const file = input.files[0];
    const ext = (file.name || '').toLowerCase().split('.').pop();
    if (!['pdf', 'jpg', 'jpeg', 'png', 'gif', 'webp'].includes(ext)) {
        if (resultadoEl) resultadoEl.textContent = 'Formato no permitido. Usa imagen o PDF.';
        return;
    }
    if (resultadoEl) resultadoEl.textContent = 'Enviando...';
    const fd = new FormData();
    fd.append('codigo', codigo);
    fd.append('archivo', file);
    if (comentarioEl && comentarioEl.value.trim()) fd.append('comentario', comentarioEl.value.trim());
    try {
        const r = await fetch(`/api/contactos/${contactoId}/comprobante-apoyo`, { method: 'POST', body: fd, credentials: 'same-origin', headers: getAuthHeadersSafe() });
        const data = await r.json();
        if (data.status === 'success') {
            if (resultadoEl) resultadoEl.textContent = 'Comprobante enviado. RUANA lo revisará.';
            const modal = document.getElementById('modal-comprobante-apoyo');
            if (modal) modal.classList.remove('show');
            host._contactoIdComprobante = null;
            await host.cargarPagosApoyoPendientes();
        } else {
            if (resultadoEl) resultadoEl.textContent = data.message || 'Error al enviar.';
        }
    } catch (e) {
        if (resultadoEl) resultadoEl.textContent = 'Error de conexión.';
    }
  }

  function abrirModalImpugnarApoyo(host, contactoId) {
    const modal = document.getElementById('modal-impugnar-apoyo');
    const infoEl = document.getElementById('impugnar-apoyo-info');
    const input = document.getElementById('input-motivo-impugnar-apoyo');
    const resultadoEl = document.getElementById('impugnar-apoyo-resultado');
    const btn = document.getElementById('btn-impugnar-apoyo-confirmar');
    if (!modal || !contactoId) return;
    host._contactoIdImpugnarApoyo = contactoId;
    if (infoEl) infoEl.textContent = `Contacto #${contactoId}. Explica brevemente por que reclamas este Apoyo RUANA.`;
    if (input) input.value = '';
    if (resultadoEl) {
        resultadoEl.textContent = '';
        resultadoEl.style.color = '';
    }
    if (btn) {
        btn.disabled = false;
        btn.textContent = 'Enviar reclamacion';
    }
    modal.classList.add('show');
    if (input) input.focus();
  }

  async function impugnarApoyoRuana(host, contactoId) {
    if (!contactoId) return;
    const modal = document.getElementById('modal-impugnar-apoyo');
    const input = document.getElementById('input-motivo-impugnar-apoyo');
    const resultadoEl = document.getElementById('impugnar-apoyo-resultado');
    const btn = document.getElementById('btn-impugnar-apoyo-confirmar');
    const motivo = input && input.value ? input.value.trim() : '';
    if (!motivo) {
        if (resultadoEl) {
            resultadoEl.textContent = 'Indica un motivo para enviar la reclamacion.';
            resultadoEl.style.color = '#fbbf24';
        }
        return;
    }
    if (btn) {
        btn.disabled = true;
        btn.textContent = 'Enviando...';
    }
    if (resultadoEl) {
        resultadoEl.textContent = 'Enviando reclamacion...';
        resultadoEl.style.color = '#93c5fd';
    }
    try {
        const resp = await fetch(`/api/contactos/${contactoId}/impugnar-apoyo`, {
            method: 'POST',
            headers: getAuthHeadersSafe({ 'Content-Type': 'application/json' }),
            credentials: 'same-origin',
            body: JSON.stringify({ motivo })
        });
        const data = await resp.json().catch(() => ({}));
        if (resp.ok && data.status === 'success') {
            if (resultadoEl) {
                resultadoEl.textContent = 'Reclamacion enviada. RUANA pedira la documentacion al aliado contratante.';
                resultadoEl.style.color = '#4ade80';
            }
            await host.cargarPagosApoyoPendientes();
            await host.cargarContactosPendientes();
            await host.actualizarEstadoAlertas();
            await host.refreshAfterAction(['perfil', 'metricas', 'solicitudes', 'directorio', 'alertas', 'contactos']);
            setTimeout(() => {
                if (modal) modal.classList.remove('show');
                host._contactoIdImpugnarApoyo = null;
            }, 900);
        } else {
            if (resultadoEl) {
                resultadoEl.textContent = data.message || 'No se pudo registrar la reclamacion.';
                resultadoEl.style.color = '#f87171';
            }
            if (btn) {
                btn.disabled = false;
                btn.textContent = 'Enviar reclamacion';
            }
        }
    } catch (e) {
        console.error('Error impugnando Apoyo RUANA:', e);
        if (resultadoEl) {
            resultadoEl.textContent = 'Error de conexion al registrar la reclamacion.';
            resultadoEl.style.color = '#f87171';
        }
        if (btn) {
            btn.disabled = false;
            btn.textContent = 'Enviar reclamacion';
        }
    }
  }

  modules.alertas = {
    formatApoyoRuana: formatApoyoRuana,
    buildAlertItems: buildAlertItems,
    renderAlertDetailPanel: renderAlertDetailPanel,
    renderAlertHub: renderAlertHub,
    renderAlertas: renderAlertas,
    cargarMetodosPagoRuana: cargarMetodosPagoRuana,
    actualizarEstadoAlertas: actualizarEstadoAlertas,
    renderListaPagosPendientes: renderListaPagosPendientes,
    renderNotificaciones: renderNotificaciones,
    marcarTodasNotificacionesLeidas: marcarTodasNotificacionesLeidas,
    cargarPagosApoyoPendientes: cargarPagosApoyoPendientes,
    abrirModalComprobanteApoyo: abrirModalComprobanteApoyo,
    abrirModalPagoApoyo: abrirModalPagoApoyo,
    setPagoApoyoMetodo: setPagoApoyoMetodo,
    abrirModalPayPalApoyo: abrirModalPayPalApoyo,
    abrirModalBizumApoyo: abrirModalBizumApoyo,
    enviarComprobanteApoyo: enviarComprobanteApoyo,
    abrirModalImpugnarApoyo: abrirModalImpugnarApoyo,
    impugnarApoyoRuana: impugnarApoyoRuana,
  };
})(typeof window !== 'undefined' ? window : globalThis);
