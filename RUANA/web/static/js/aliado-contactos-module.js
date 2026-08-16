/**
 * Módulo PrivatePanel `contactos` (Campamento Base).
 * Contactos pendientes, encargos activos, cierre e importes.
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

  function mostrarAcuerdoFlotante(host, item) {
    const panel = document.getElementById('acuerdo-flotante');
    if (!panel || !item) return;
    host.acuerdoFlotanteActual = item;
    const title = document.getElementById('acuerdo-flotante-title');
    const body = document.getElementById('acuerdo-flotante-body');
    const estadoEl = document.getElementById('acuerdo-flotante-estado');
    const btnConfirmar = document.getElementById('acuerdo-flotante-confirmar');
    if (title) title.textContent = item.servicio || 'Resumen del acuerdo';
    const items = Array.isArray(item.resumen)
        ? item.resumen.filter((r) => r && r.valor && r.campo !== 'observaciones_profesional')
        : [];
    if (body) {
        body.innerHTML = items.length
            ? items.map((r) => `<p><strong>${host.escapeHtml(r.label || r.campo)}:</strong> ${host.escapeHtml(String(r.valor))}</p>`).join('')
            : '<p>Consulta el detalle en la negociación.</p>';
    }
    let estadoTxt = 'El precio aceptado es el importe oficial del encargo.';
    if (item.estado === 'trabajo_cerrado' || item.ambos_confirmaron_cierre) {
        estadoTxt = 'Precio aceptado. Encargo cerrado y Apoyo RUANA generado.';
    } else if (item.yo_confirme_cierre) {
        estadoTxt = 'Ya revisaste el resumen.';
    }
    if (estadoEl) estadoEl.textContent = estadoTxt;
    if (btnConfirmar) {
        const hide = !!(item.yo_confirme_cierre || item.estado === 'trabajo_cerrado' || item.ambos_confirmaron_cierre);
        btnConfirmar.style.display = hide ? 'none' : '';
        btnConfirmar.disabled = hide;
    }
    panel.hidden = false;
    panel.classList.add('show');
  }

  async function cargarContactosPendientes(host) {
    try {
        const codigo = (host.codigoAliado || (host.aliado && host.aliado.codigo) || '').toString().trim();
        const avisoEl = document.getElementById('contacto-aviso-persistente');
        if (!codigo || !avisoEl) {
            return;
        }

        const resp = await fetch(`/api/contactos/abiertos/${encodeURIComponent(codigo)}`, { credentials: 'same-origin', headers: getAuthHeadersSafe() });
        if (!resp.ok) {
            console.warn('No se pudieron cargar contactos abiertos');
            return;
        }
        const data = await resp.json();
        if (data.status !== 'success' || !Array.isArray(data.contactos)) {
            return;
        }

        host.contactosAbiertos = data.contactos || [];
        // Backend ya excluye contactos con posponer_recordatorio=1 (server-driven)
        host.contactoActual = host.contactosAbiertos.length > 0 ? host.contactosAbiertos[0] : null;

        if (!host.contactoActual) {
            await host.cargarPagosApoyoPendientes();
            avisoEl.style.display = 'none';
            avisoEl.classList.remove('contacto-aviso-urgente');
            avisoEl.removeAttribute('data-contacto-id');
            avisoEl.removeAttribute('data-requiere-respuesta');
            const badgeUrgenteOff = document.getElementById('contacto-aviso-badge-urgente');
            if (badgeUrgenteOff) badgeUrgenteOff.style.display = 'none';
            const stripeSlotOff = document.getElementById('contacto-aviso-stripe-acciones');
            if (stripeSlotOff) stripeSlotOff.innerHTML = '';
            host.renderEncargosActivos();
            if (typeof host.renderMensajesEncargo === 'function') {
                host.renderMensajesEncargo();
            }
            return;
        }

        avisoEl.classList.toggle('contacto-aviso-urgente', !!host.contactoActual.es_urgente);
        const badgeUrgente = document.getElementById('contacto-aviso-badge-urgente');
        if (badgeUrgente) badgeUrgente.style.display = host.contactoActual.es_urgente ? 'inline-block' : 'none';

        const ui = host._encargoUiLabels(host.contactoActual);
        const estado = host.contactoActual.estado;
        const estadoEl = document.getElementById('contacto-aviso-estado');
        const contextoEl = document.getElementById('contacto-aviso-contexto');
        const pasoEl = document.getElementById('contacto-aviso-paso');
        const accionEl = document.getElementById('contacto-aviso-accion');
        const progresoFill = document.getElementById('contacto-aviso-progreso-fill');
        const progresoTexto = document.getElementById('contacto-aviso-progreso-texto');
        const btnAbrir = document.getElementById('btn-contacto-abrir-negociacion')
            || document.getElementById('btn-contacto-abrir-chat');
        let progresoConf = ui.progresoConf;
        let progresoTotal = ui.progresoTotal;
        if (estado === 'acuerdo_alcanzado' || host.contactoActual.negociacion_completa) {
            progresoConf = progresoTotal;
        }
        if (estado === 'pendiente_de_pago') {
            progresoConf = progresoTotal;
        }

        if (estadoEl) estadoEl.textContent = ui.estadoLabel;
        if (contextoEl) contextoEl.textContent = ui.contexto;
        if (pasoEl) {
            pasoEl.textContent = ui.pasoTxt;
            pasoEl.style.display = ui.pasoTxt ? 'block' : 'none';
        }
        if (accionEl) accionEl.textContent = ui.accionTxt;
        const stripeSlot = document.getElementById('contacto-aviso-stripe-acciones');
        if (stripeSlot) {
            stripeSlot.innerHTML = '';
            if (global.RuanaStripePagos && typeof global.RuanaStripePagos.renderStripeAcciones === 'function') {
                global.RuanaStripePagos.renderStripeAcciones(host, host.contactoActual, stripeSlot);
            }
        }
        if (progresoTexto) progresoTexto.textContent = `${progresoConf}/${progresoTotal}`;
        if (progresoFill && progresoTotal > 0) {
            progresoFill.style.width = `${Math.round((progresoConf / progresoTotal) * 100)}%`;
        }
        if (btnAbrir) btnAbrir.textContent = ui.btnPrincipal;
        avisoEl.classList.toggle('encargo-requiere-respuesta', ui.requiereRespuesta);
        avisoEl.dataset.contactoId = String(host.contactoActual.id);
        avisoEl.dataset.requiereRespuesta = ui.requiereRespuesta ? '1' : '0';
        // Ocultar "Sigue en conversación" tras acuerdo alcanzado
        const btnSigue = document.getElementById('btn-contacto-sigue');
        if (btnSigue) btnSigue.style.display = (estado === 'acuerdo_alcanzado' || estado === 'trabajo_cerrado') ? 'none' : '';
        const btnSiTrabajo = document.getElementById('btn-contacto-si-trabajo');
        const btnNoConcreto = document.getElementById('btn-contacto-no-concreto');
        // Fase 3: el cierre manual por «Sí, hubo trabajo» no está disponible en el panel normal.
        if (btnSiTrabajo) btnSiTrabajo.style.display = 'none';
        if (btnNoConcreto) btnNoConcreto.style.display = (estado === 'trabajo_cerrado') ? 'none' : '';

        const subirPruebaEl = document.getElementById('contacto-aviso-subir-prueba');
        const codigoAliado = host.codigoAliado || (host.aliado && host.aliado.codigo) || '';
        if (estado === 'importe_en_disputa' && codigoAliado && host.contactoActual.solicitante_codigo === codigoAliado) {
            try {
                const r = await fetch(`/api/conflictos/por-trabajo/${host.contactoActual.id}`, { credentials: 'same-origin', headers: getAuthHeadersSafe() });
                const data = await r.json();
                if (data.status === 'success' && data.conflicto && data.conflicto.estado === 'PENDIENTE_PRUEBA') {
                    host._conflictoIdParaPrueba = data.conflicto.id;
                    if (subirPruebaEl) { subirPruebaEl.style.display = 'block'; subirPruebaEl.dataset.conflictId = data.conflicto.id; }
                    const inp = document.getElementById('input-prueba-conflicto');
                    if (inp) inp.value = '';
                    const res = document.getElementById('subir-prueba-resultado');
                    if (res) res.textContent = '';
                } else {
                    host._conflictoIdParaPrueba = null;
                    if (subirPruebaEl) subirPruebaEl.style.display = 'none';
                }
            } catch (err) {
                host._conflictoIdParaPrueba = null;
                if (subirPruebaEl) subirPruebaEl.style.display = 'none';
            }
        } else {
            host._conflictoIdParaPrueba = null;
            if (subirPruebaEl) subirPruebaEl.style.display = 'none';
        }

        avisoEl.style.display = 'flex';
        await host.cargarPagosApoyoPendientes();
        host.renderEncargosActivos();
        if (typeof host.renderMensajesEncargo === 'function') {
            host.renderMensajesEncargo();
        }
    } catch (e) {
        console.error('Error cargando contactos pendientes:', e);
    }
  }

  async function mostrarAvisoPrevioContacto(host, profesional) {
    host.profesionalSeleccionado = profesional;
    host._catalogoPrevioItems = [];
    const modal = document.getElementById('modal-contacto-previo');
    const textoEl = document.getElementById('modal-contacto-previo-text');
    const catalogoWrap = document.getElementById('contacto-previo-catalogo-wrap');
    const catalogoList = document.getElementById('contacto-previo-catalogo-list');
    const inputOtro = document.getElementById('contacto-previo-servicio-otro');
    if (inputOtro) inputOtro.value = '';
    if (textoEl && profesional) {
        const nombre = host.escapeHtml(profesional.nombre || '');
        const oficio = host.escapeHtml(profesional.oficio || '');
        textoEl.innerHTML = `Vas a iniciar un contacto RUANA con <strong>${nombre}</strong> (${oficio}). Este contacto contará en tu historial y métricas personales.`;
    }
    const avisoStripe = document.getElementById('contacto-previo-stripe-aviso');
    const stripeListo = profesional && profesional.stripe_pago_listo !== false;
    if (avisoStripe) {
        avisoStripe.style.display = stripeListo ? 'none' : 'block';
        avisoStripe.textContent = (global.RuanaStripePagos && global.RuanaStripePagos.MSG_PAGO_NO_DISPONIBLE)
            || 'Pago no disponible todavía con este profesional';
    }
    const profesionalCodigo = (profesional && (profesional.codigo || '').toString().trim())
        || (profesional && profesional.id != null ? String(profesional.id).padStart(5, '0') : '');
    if (catalogoList) catalogoList.innerHTML = '';
    if (catalogoWrap) catalogoWrap.style.display = 'none';
    if (profesionalCodigo) {
        await host._cargarCatalogoEnPrevioContacto(profesionalCodigo);
    }
    if (modal) {
        modal.classList.add('show');
    }
  }

  async function _cargarCatalogoEnPrevioContacto(host, profesionalCodigo) {
    const catalogoWrap = document.getElementById('contacto-previo-catalogo-wrap');
    const catalogoList = document.getElementById('contacto-previo-catalogo-list');
    const inputOtro = document.getElementById('contacto-previo-servicio-otro');
    if (!catalogoList || !profesionalCodigo) return;
    try {
        const resp = await fetch(`/api/aliados/${encodeURIComponent(profesionalCodigo)}/catalogo-servicios`, {
            credentials: 'same-origin',
            headers: getAuthHeadersSafe(),
        });
        const data = await resp.json();
        const servicios = (data.status === 'success' && Array.isArray(data.servicios))
            ? data.servicios.filter(s => s.configurado && s.descripcion)
            : [];
        host._catalogoPrevioItems = servicios;
        if (!servicios.length) {
            if (catalogoWrap) catalogoWrap.style.display = 'none';
            return;
        }
        if (catalogoWrap) catalogoWrap.style.display = 'block';
        catalogoList.innerHTML = servicios.map((s, idx) => {
            const desc = host.escapeHtml(s.descripcion || '');
            const precio = s.precio ? `<span class="neg-catalogo-precio">${host.escapeHtml(String(s.precio))}</span>` : '';
            return `<button type="button" class="neg-catalogo-item" data-idx="${idx}"><span class="neg-catalogo-desc">${desc}</span>${precio}</button>`;
        }).join('');
        catalogoList.querySelectorAll('.neg-catalogo-item').forEach(btn => {
            btn.addEventListener('click', () => {
                catalogoList.querySelectorAll('.neg-catalogo-item').forEach(b => b.classList.remove('selected'));
                btn.classList.add('selected');
                const idx = parseInt(btn.getAttribute('data-idx') || '-1', 10);
                const item = host._catalogoPrevioItems[idx];
                if (inputOtro && item) inputOtro.value = item.descripcion || '';
            });
        });
    } catch (e) {
        if (catalogoWrap) catalogoWrap.style.display = 'none';
    }
  }

  function _encargoUiLabels(host, contacto) {
    const estado = contacto.estado;
    const meta = contacto.negociacion_meta || {};
    const yaDeclaraste = contacto.ya_declaraste_importe === true;
    const codigo = (host.codigoAliado || (host.aliado && host.aliado.codigo) || '').toString().trim();
    const esContratante = codigo === String(contacto.solicitante_codigo || '').trim();
    const esProfesional = codigo === String(contacto.profesional_codigo || '').trim();
    const modoStripe = contacto.modo_pago === 'stripe';
    let estadoLabel = 'Encargo activo';
    let contexto = meta.contexto || 'Tienes un encargo activo con otro aliado RUANA.';
    let pasoTxt = meta.paso_label ? `Pendiente: ${meta.paso_label}` : '';
    let accionTxt = meta.siguiente_accion || 'Abre la negociación para continuar.';
    let btnPrincipal = 'Abrir negociación';
    let requiereRespuesta = !!contacto.negociacion_requiere_mi_respuesta;
    if (contacto.es_urgente) estadoLabel = 'Encargo urgente';
    if (
        estado === 'pendiente_de_pago'
        || (contacto.modo_pago === 'stripe' && estado === 'trabajo_en_progreso')
    ) {
        estadoLabel = contacto.modo_pago === 'stripe' ? 'Pago Stripe pendiente' : estadoLabel;
        if (contacto.modo_pago === 'stripe') {
            contexto = 'El importe acordado está congelado. El contratante debe completar el pago.';
            if (esProfesional) {
                accionTxt = contacto.estado_pago === 'cobro_confirmado'
                    ? 'El contratante ya pagó. Tu importe está retenido y se liberará cuando confirme que el trabajo quedó hecho.'
                    : 'Tu pago quedará retenido hasta que el contratante pague y confirme que el trabajo quedó hecho.';
            } else if (esContratante) {
                accionTxt = contacto.estado_pago === 'cobro_confirmado'
                    ? 'Confirma que el trabajo se realizó para liberar el pago al profesional.'
                    : 'Pulsa «Ir a pagar» para completar el pago con Stripe.';
            } else {
                accionTxt = contacto.estado_pago === 'cobro_confirmado'
                    ? 'Confirma que el trabajo se realizó para liberar el pago al profesional.'
                    : 'El contratante debe completar el pago con Stripe.';
            }
            btnPrincipal = 'Ver encargo';
        }
    } else if (estado === 'acuerdo_alcanzado' || contacto.negociacion_completa) {
        estadoLabel = 'Acuerdo alcanzado';
        contexto = 'Todos los puntos del encargo están confirmados.';
        pasoTxt = '';
        if (modoStripe && esProfesional) {
            accionTxt = 'Acuerdo confirmado. Tu pago está reservado y se desbloqueará automáticamente en cuanto el contratante confirme que el trabajo quedó hecho.';
        } else if (modoStripe && esContratante) {
            accionTxt = 'El importe acordado está congelado. Completa el pago con «Pagar ahora» para reservar el encargo.';
        } else if (modoStripe) {
            accionTxt = 'El importe acordado está congelado. El contratante debe completar el pago.';
        } else {
            accionTxt = 'El importe acordado está congelado. El contratante debe completar el pago con tarjeta.';
        }
        btnPrincipal = 'Ver acuerdo';
    } else if (requiereRespuesta) {
        estadoLabel = 'Tu turno';
        btnPrincipal = 'Responder ahora';
        accionTxt = meta.siguiente_accion || 'Confirma o sugiere un cambio para continuar.';
    } else if (meta.fase === 'revision' && !requiereRespuesta) {
        estadoLabel = 'Esperando al profesional';
        btnPrincipal = 'Ver negociación';
    } else if (meta.fase === 'inicio' && estado !== 'acuerdo_alcanzado') {
        estadoLabel = 'Preparar encargo';
        btnPrincipal = 'Continuar negociación';
    } else if (estado === 'importe_en_disputa') {
        estadoLabel = 'Importe en disputa';
        contexto = 'Hay una diferencia en el importe declarado. Debes aclararlo para proteger tu reputación.';
        pasoTxt = '';
        accionTxt = 'Revisa el contacto y aporta la información necesaria.';
        btnPrincipal = 'Revisar contacto';
    } else if (estado === 'trabajo_cerrado') {
        estadoLabel = 'Trabajo cerrado';
        contexto = 'El encargo quedó registrado como realizado.';
        pasoTxt = '';
        accionTxt = modoStripe
            ? 'Revisa el estado del pago en el detalle del encargo.'
            : 'Revisa el detalle del encargo si necesitas más información.';
        btnPrincipal = 'Ver detalle';
    }
    if (yaDeclaraste && estado !== 'importe_en_disputa' && estado !== 'trabajo_cerrado') {
        accionTxt += ' Ya confirmaste el importe.';
    }
    const contraparte = esContratante
        ? contacto.profesional_codigo
        : contacto.solicitante_codigo;
    return {
        estadoLabel, contexto, pasoTxt, accionTxt, btnPrincipal, requiereRespuesta, contraparte,
        progresoConf: meta.progreso_confirmados || 0,
        progresoTotal: meta.progreso_total || 6,
    };
  }

  function renderEncargosActivos(host) {
    const list = document.getElementById('encargos-activos-list');
    const wrap = document.getElementById('solicitudes-encargos-wrap');
    if (!list || !wrap) return;
    const encargos = Array.isArray(host.contactosAbiertos) ? host.contactosAbiertos : [];
    if (!encargos.length) {
        list.innerHTML = '<p class="encargos-activos-empty">No tienes encargos activos en este momento.</p>';
        wrap.style.display = '';
        return;
    }
    list.innerHTML = encargos.map((c) => {
        const ui = host._encargoUiLabels(c);
        const servicio = host.escapeHtml(c.servicio || 'Encargo RUANA');
        const contraparte = host.escapeHtml(String(ui.contraparte || ''));
        const pasoHtml = ui.pasoTxt
            ? `<p class="encargo-card-paso">${host.escapeHtml(ui.pasoTxt)}</p>`
            : '';
        const urgente = c.es_urgente ? '<span class="encargo-card-badge urgente">Urgente</span>' : '';
        const turno = ui.requiereRespuesta ? '<span class="encargo-card-badge turno">Tu turno</span>' : '';
        return `<article class="encargo-card${ui.requiereRespuesta ? ' encargo-requiere-respuesta' : ''}" data-contacto-id="${c.id}" data-requiere-respuesta="${ui.requiereRespuesta ? '1' : '0'}">
            <div class="encargo-card-header">
                <span class="encargo-card-estado">${host.escapeHtml(ui.estadoLabel)}</span>
                ${urgente}${turno}
            </div>
            <h4 class="encargo-card-servicio">${servicio}</h4>
            <p class="encargo-card-meta">Con aliado ${contraparte}</p>
            <p class="encargo-card-contexto">${host.escapeHtml(ui.contexto)}</p>
            ${pasoHtml}
            <p class="encargo-card-accion">${host.escapeHtml(ui.accionTxt)}</p>
            <div class="encargo-stripe-acciones" data-stripe-contacto="${c.id}"></div>
            <button type="button" class="encargo-card-btn" data-abrir-negociacion="${c.id}">${host.escapeHtml(ui.btnPrincipal)}</button>
        </article>`;
    }).join('');
    list.querySelectorAll('[data-abrir-negociacion]').forEach((btn) => {
        btn.addEventListener('click', () => {
            const id = parseInt(btn.getAttribute('data-abrir-negociacion') || '0', 10);
            if (id) host.abrirNegociacionContacto(id, null);
        });
    });
    if (global.RuanaStripePagos && typeof global.RuanaStripePagos.renderStripeAcciones === 'function') {
        encargos.forEach((c) => {
            const slot = list.querySelector(`[data-stripe-contacto="${c.id}"]`);
            if (slot) global.RuanaStripePagos.renderStripeAcciones(host, c, slot);
        });
    }
    wrap.style.display = '';
    if (window.AliadoShell && typeof window.AliadoShell.refresh === 'function') {
        window.AliadoShell.refresh();
    }
  }

  async function crearContactoYAbrirNegociacion(host) {
    const modalPrevio = document.getElementById('modal-contacto-previo');
    if (!host.profesionalSeleccionado) {
        if (modalPrevio) modalPrevio.classList.remove('show');
        return;
    }

    const codigoSolicitante = host.codigoAliado || (host.aliado && host.aliado.codigo);
    if (!codigoSolicitante) {
        alert('No se pudo determinar tu código RUANA. Vuelve a entrar desde el inicio.');
        if (modalPrevio) modalPrevio.classList.remove('show');
        host.profesionalSeleccionado = null;
        return;
    }

    const profesional = host.profesionalSeleccionado;
    const profesionalCodigo = (profesional.codigo || '').toString().trim() || (profesional.id != null ? String(profesional.id).padStart(5, '0') : '');
    if (!profesionalCodigo) {
        alert('No se pudo obtener el código del profesional. Vuelve al directorio e inténtalo de nuevo.');
        return;
    }
    const servicio = host._obtenerServicioSeleccionadoPrevio(profesional);
    if (!servicio) {
        alert('Elige un servicio del catálogo o escribe cuál necesitas.');
        return;
    }
    const precioCatalogo = host._obtenerPrecioCatalogoPrevio();
    const btnConfirm = document.getElementById('btn-contacto-previo-confirm');
    if (btnConfirm) btnConfirm.disabled = true;

    try {
        const resp = await fetch('/api/contactos', {
            method: 'POST',
            headers: getAuthHeadersSafe({ 'Content-Type': 'application/json' }),
            credentials: 'same-origin',
            body: JSON.stringify({
                profesional_codigo: profesionalCodigo,
                servicio,
                es_urgente: !!(document.getElementById('check-contacto-urgente') || {}).checked,
                precio_catalogo: precioCatalogo,
            })
        });
        const data = await resp.json();
        if (!resp.ok || data.status !== 'success') {
            alert(data.message || 'No se pudo registrar el contacto. Revisa que ambos códigos existan.');
            return;
        }
        if (modalPrevio) modalPrevio.classList.remove('show');
        const checkUrgente = document.getElementById('check-contacto-urgente');
        if (checkUrgente) checkUrgente.checked = false;
        const inputOtro = document.getElementById('contacto-previo-servicio-otro');
        if (inputOtro) inputOtro.value = '';
        const catalogoList = document.getElementById('contacto-previo-catalogo-list');
        if (catalogoList) catalogoList.innerHTML = '';
        await host.cargarContactosPendientes();
        await host.refreshAfterAction(['metricas', 'solicitudes', 'directorio', 'alertas', 'contactos']);
        host.abrirNegociacionContacto(data.id, profesional, { es_urgente: !!data.es_urgente });
    } catch (e) {
        console.error('Error de red:', e);
        alert('Error de conexión al registrar el contacto.');
    } finally {
        if (btnConfirm) btnConfirm.disabled = false;
        host.profesionalSeleccionado = null;
    }
  }

  function handleAvisoSiHuboTrabajo(host) {
    if (!host.contactoActual) return;
    if (host.contactoActual.estado === 'trabajo_cerrado') {
        alert('Este contacto ya esta cerrado. Revisa el bloque de Apoyo RUANA si tienes pago pendiente.');
        return;
    }
    const codigo = String(host.codigoAliado || (host.aliado && host.aliado.codigo) || '').trim();
    const solCodigo = String(host.contactoActual.solicitante_codigo || '').trim();
    if (codigo !== solCodigo) {
        alert('El importe lo confirma el aliado que contrato el encargo. Si el importe declarado no es correcto, usa Impugnar o reclamar en el bloque de Apoyo RUANA.');
        return;
    }
    if (host.contactoActual.ya_declaraste_importe === true) {
        alert('Ya confirmaste el importe para este contacto.');
        return;
    }
    const modal = document.getElementById('modal-contacto-importe');
    const resumenEl = document.getElementById('modal-importe-resumen');
    const acordadoWrap = document.getElementById('modal-importe-acordado-wrap');
    const acordadoValor = document.getElementById('modal-importe-acordado-valor');
    const inputWrap = document.getElementById('modal-importe-input-wrap');
    const input = document.getElementById('contacto-importe-input');
    const texto = document.getElementById('modal-contacto-importe-text');
    const btnConfirm = document.getElementById('btn-contacto-importe-confirm');
    if (resumenEl) {
        resumenEl.style.display = 'none';
        resumenEl.textContent = '';
    }
    const oficial = host.contactoActual.importe_acordado != null
        ? Number(host.contactoActual.importe_acordado)
        : (host.contactoActual.precio_acordado != null ? Number(host.contactoActual.precio_acordado) : NaN);
    const tieneOficial = !isNaN(oficial) && oficial > 0;
    if (tieneOficial) {
        if (texto) {
            texto.textContent = 'El precio quedó fijado en la negociación. Confirma ese valor oficial del encargo.';
        }
        if (acordadoWrap) acordadoWrap.style.display = 'block';
        if (acordadoValor) acordadoValor.textContent = `${oficial.toLocaleString('es-ES', { minimumFractionDigits: 0, maximumFractionDigits: 2 })} €`;
        if (inputWrap) inputWrap.style.display = 'none';
        if (input) { input.value = String(oficial); input.required = false; }
        if (btnConfirm) btnConfirm.textContent = 'Confirmar valor acordado';
    } else {
        if (texto) {
            texto.textContent = 'No hay un precio numérico en el acuerdo. Introduce el importe para cerrar el encargo.';
        }
        if (acordadoWrap) acordadoWrap.style.display = 'none';
        if (inputWrap) inputWrap.style.display = 'block';
        if (input) { input.value = ''; input.required = true; }
        if (btnConfirm) btnConfirm.textContent = 'Confirmar importe';
    }
    if (modal) modal.classList.add('show');
  }

  async function confirmarImporteContacto(host) {
    if (!host.contactoActual) return;
    const input = document.getElementById('contacto-importe-input');
    const btnConfirm = document.getElementById('btn-contacto-importe-confirm');
    const codigo = String(host.codigoAliado || (host.aliado && host.aliado.codigo) || '').trim();
    const solCodigo = String(host.contactoActual.solicitante_codigo || '').trim();
    const parte = (solCodigo === codigo) ? 'solicitante' : 'profesional';

    const oficial = host.contactoActual.importe_acordado != null
        ? Number(host.contactoActual.importe_acordado)
        : (host.contactoActual.precio_acordado != null ? Number(host.contactoActual.precio_acordado) : NaN);
    const tieneOficial = !isNaN(oficial) && oficial > 0;

    if (!tieneOficial) {
        if (!input) return;
        const raw = String(input.value || '').trim().replace(',', '.');
        const valor = parseFloat(raw);
        if (raw === '' || isNaN(valor) || valor <= 0) {
            alert('Introduce un importe válido mayor que cero.');
            return;
        }
    }

    if (btnConfirm) { btnConfirm.disabled = true; }
    try {
        const body = tieneOficial
            ? { parte, confirmar_acordado: true, usar_precio_acordado: true, moneda: 'EUR' }
            : { parte, importe: parseFloat(String(input.value || '').trim().replace(',', '.')), moneda: 'EUR' };
        const resp = await fetch(`/api/contactos/${host.contactoActual.id}/declarar-importe`, {
            method: 'POST',
            headers: getAuthHeadersSafe({ 'Content-Type': 'application/json' }),
            credentials: 'same-origin',
            body: JSON.stringify(body)
        });
        const data = await resp.json();
        if (data.status !== 'success') {
            if (btnConfirm) btnConfirm.disabled = false;
            const msg = data.message || 'No se pudo registrar el importe.';
            if (data.estado === 'trabajo_cerrado' || (msg && msg.indexOf('ya está cerrado') !== -1)) {
                alert('Este contacto ya está cerrado. Ambas partes han confirmado el importe.');
                host.contactoActual = null;
                const avisoEl = document.getElementById('contacto-aviso-persistente');
                if (avisoEl) avisoEl.style.display = 'none';
                await host.cargarContactosPendientes();
                await host.cargarPagosApoyoPendientes();
                await host.refreshAfterAction(['metricas', 'solicitudes', 'alertas', 'contactos']);
                const modal = document.getElementById('modal-contacto-importe');
                if (modal) modal.classList.remove('show');
            } else if (msg.indexOf('Ya has declarado') !== -1) {
                alert('Solo puedes confirmar el importe una vez por contacto.');
            } else {
                alert(msg);
            }
            return;
        }

        const modal = document.getElementById('modal-contacto-importe');
        const resumenEl = document.getElementById('modal-importe-resumen');
        if (data.estado === 'trabajo_cerrado') {
            await host.mostrarResumenCierre(host.contactoActual.id);
            const avisoEl = document.getElementById('contacto-aviso-persistente');
            if (avisoEl) avisoEl.style.display = 'none';
            host.contactoActual = null;
            await host.cargarPagosApoyoPendientes();
        } else if (data.estado === 'importe_en_disputa') {
            const ctx = document.getElementById('contacto-aviso-contexto');
            const acc = document.getElementById('contacto-aviso-accion');
            if (ctx) ctx.textContent = 'Los importes declarados no coinciden.';
            if (acc) acc.textContent = 'Adjunta un comprobante de pago para continuar.';
        }
        if (modal) modal.classList.remove('show');
        if (input) input.value = '';
        if (resumenEl) { resumenEl.style.display = 'none'; resumenEl.innerHTML = ''; }

        await host.cargarContactosPendientes();
        await host.refreshAfterAction(['metricas', 'solicitudes', 'directorio', 'alertas', 'contactos']);
    } catch (e) {
        console.error('Error declarando importe:', e);
        alert('Error de conexión al confirmar el importe.');
    } finally {
        if (btnConfirm) btnConfirm.disabled = false;
    }
  }

  async function mostrarResumenCierre(host, contactoId) {
    try {
        const resp = await fetch(`/api/contactos/${contactoId}`, { credentials: 'same-origin', headers: getAuthHeadersSafe() });
        if (!resp.ok) return;
        const data = await resp.json();
        if (data.status !== 'success' || !data.contacto) return;

        const c = data.contacto;
        const resumenEl = document.getElementById('modal-importe-resumen');
        if (!resumenEl) return;

        const codigo = (host.codigoAliado || (host.aliado && host.aliado.codigo) || '').toString().trim();
        const esProfesional = codigo === String(c.profesional_codigo || '').trim();
        const importeVal = c.importe_acordado != null ? Number(c.importe_acordado)
            : (c.importe_final != null ? Number(c.importe_final) : NaN);
        const importe = (!Number.isNaN(importeVal) && importeVal > 0)
            ? importeVal.toFixed(2) + ' €'
            : 'Pendiente de cálculo';
        const estadoPagoRaw = c.estado_pago || 'no_generado';
        const labelFn = global.RuanaStripePagos && global.RuanaStripePagos.labelEstadoPago;
        let estadoPago = labelFn ? labelFn(estadoPagoRaw) : estadoPagoRaw.replace(/_/g, ' ');
        if (esProfesional && ['esperando_cobro_cliente', 'checkout_activo', 'no_generado'].includes(estadoPagoRaw)) {
            estadoPago = 'Reservado — se desbloqueará cuando el contratante confirme el trabajo';
        }

        resumenEl.innerHTML = `
            <strong>Importe acordado:</strong> ${importe}<br>
            <strong>Estado del pago:</strong> ${estadoPago}
        `;
        resumenEl.style.display = 'block';
    } catch (e) {
        console.error('Error obteniendo resumen de cierre:', e);
    }
  }

  async function subirPruebaConflicto(host) {
    const conflictId = host._conflictoIdParaPrueba;
    const codigo = host.codigoAliado || (host.aliado && host.aliado.codigo) || '';
    const input = document.getElementById('input-prueba-conflicto');
    const resultadoEl = document.getElementById('subir-prueba-resultado');
    if (!conflictId || !codigo) {
        if (resultadoEl) resultadoEl.textContent = 'No hay conflicto pendiente.';
        return;
    }
    if (!input || !input.files || !input.files.length) {
        if (resultadoEl) resultadoEl.textContent = 'Elige un archivo (PDF o imagen).';
        return;
    }
    const file = input.files[0];
    const fd = new FormData();
    fd.append('codigo', codigo);
    fd.append('archivo', file);
    if (resultadoEl) resultadoEl.textContent = 'Enviando...';
    try {
        const r = await fetch(`/api/conflictos/${conflictId}/subir-prueba`, {
            method: 'POST',
            body: fd,
            credentials: 'same-origin',
            headers: getAuthHeadersSafe()
        });
        const data = await r.json();
        if (data.status === 'success') {
            if (resultadoEl) resultadoEl.textContent = 'Prueba enviada. En revisión.';
            host._conflictoIdParaPrueba = null;
            const subirPruebaEl = document.getElementById('contacto-aviso-subir-prueba');
            if (subirPruebaEl) subirPruebaEl.style.display = 'none';
            await host.cargarContactosPendientes();
            await host.actualizarEstadoAlertas();
            await host.refreshAfterAction(['metricas', 'solicitudes', 'alertas', 'contactos']);
        } else {
            if (resultadoEl) resultadoEl.textContent = data.message || 'Error al subir.';
        }
    } catch (e) {
        if (resultadoEl) resultadoEl.textContent = 'Error de conexión.';
    }
  }

  async function confirmarNoConcretado(host) {
    if (!host.contactoActual) return;
    const modal = document.getElementById('modal-no-concretado');
    const contactoId = host.contactoActual.id;
    try {
        const resp = await fetch(`/api/contactos/${contactoId}/no-concretado`, {
            method: 'POST',
            headers: getAuthHeadersSafe({ 'Content-Type': 'application/json' }),
            credentials: 'same-origin',
            body: JSON.stringify({
                motivo: 'Cierre sin trabajo desde panel RUANA'
            })
        });
        const data = await resp.json();
        if (modal) modal.classList.remove('show');
        const yaCerrado = data.status !== 'success' && (resp.status === 200 || resp.status === 400) && /ya está cerrado|estado final/i.test(data.message || '');
        if (data.status !== 'success' && !yaCerrado) {
            alert(data.message || 'No se pudo marcar como no concretado.');
            return;
        }
        await host.finalizarContactoCerradoEnUI(contactoId);
    } catch (e) {
        if (modal) modal.classList.remove('show');
        console.error('Error marcando no concretado:', e);
        alert('Error de conexión al actualizar el contacto.');
    }
  }

  async function cargarResumenesAcuerdoFlotantes(host) {
    try {
        const resp = await fetch('/api/aliado/resumenes-acuerdo', {
            credentials: 'same-origin',
            headers: getAuthHeadersSafe(),
        });
        if (!resp.ok) return;
        const data = await resp.json();
        const resumenes = (data.status === 'success' && Array.isArray(data.resumenes))
            ? data.resumenes
            : [];
        if (!resumenes.length) {
            host.ocultarAcuerdoFlotante();
            return;
        }
        host.mostrarAcuerdoFlotante(resumenes[0]);
    } catch (e) {
        console.error('Error cargando resúmenes de acuerdo:', e);
    }
  }

  async function handleAvisoSigueEnConversacion(host) {
    if (!host.contactoActual) return;
    const codigo = host.codigoAliado || (host.aliado && host.aliado.codigo) || '';
    const contactoId = host.contactoActual.id;
    try {
        const resp = await fetch(`/api/contactos/${contactoId}/en-conversacion`, {
            method: 'POST',
            headers: getAuthHeadersSafe({ 'Content-Type': 'application/json' }),
            credentials: 'same-origin',
            body: JSON.stringify({})
        });
        const data = await resp.json();
        if (data.status !== 'success') {
            alert(data.message || 'No se pudo actualizar el estado del contacto.');
            return;
        }
        await host.cargarContactosPendientes();
        await host.refreshAfterAction(['metricas', 'solicitudes', 'alertas', 'contactos']);
    } catch (e) {
        console.error('Error actualizando contacto en conversación:', e);
        alert('Error de conexión al actualizar el contacto.');
    }
  }

    function syncAcuerdoFlotante(host, data) {
      if (!data || data.resumen_dismissed) return;
      const estado = data.estado_contacto || '';
      if (!(['acuerdo_alcanzado', 'trabajo_cerrado'].includes(estado) || data.acuerdo_alcanzado)) {
          return;
      }
      host.mostrarAcuerdoFlotante({
          contacto_id: data.contacto_id || host.negociacionGuiada && host.negociacionGuiada.contactoId,
          estado,
          servicio: data.servicio_contacto || '',
          resumen: data.resumen || [],
          yo_confirme_cierre: !!data.yo_confirme_cierre,
          ambos_confirmaron_cierre: !!data.ambos_confirmaron_cierre,
          cierre_confirmado_solicitante: !!data.cierre_confirmado_solicitante,
          cierre_confirmado_profesional: !!data.cierre_confirmado_profesional,
      });
  }

  function mostrarAcuerdoFlotanteDesdeNegociacion(host, contactoId, data) {
      if (!data || data.resumen_dismissed) return;
      const estado = data.estado_contacto || '';
      if (!(data.acuerdo_alcanzado || ['acuerdo_alcanzado', 'trabajo_cerrado'].includes(estado))) {
          return;
      }
      host.mostrarAcuerdoFlotante({
          contacto_id: contactoId,
          estado,
          servicio: data.servicio_contacto || '',
          resumen: data.resumen || [],
          yo_confirme_cierre: !!data.yo_confirme_cierre,
          ambos_confirmaron_cierre: !!data.ambos_confirmaron_cierre,
      });
  }

  function ocultarAcuerdoFlotante(host) {
      const panel = document.getElementById('acuerdo-flotante');
      if (panel) {
          panel.hidden = true;
          panel.classList.remove('show');
      }
      host.acuerdoFlotanteActual = null;
      host._acuerdoFlotanteOcultoPorModal = false;
      host._acuerdoFlotanteSnapshot = null;
  }

  function ocultarAcuerdoFlotantePorModal(host) {
      const panel = document.getElementById('acuerdo-flotante');
      if (panel && panel.classList.contains('show')) {
          host._acuerdoFlotanteOcultoPorModal = true;
          host._acuerdoFlotanteSnapshot = host.acuerdoFlotanteActual;
          panel.classList.remove('show');
          panel.hidden = true;
      }
  }

  function restaurarAcuerdoFlotanteTrasNegociacion(host, contactoId, dataSnapshot) {
      host._acuerdoFlotanteOcultoPorModal = false;
      const snap = host._acuerdoFlotanteSnapshot;
      host._acuerdoFlotanteSnapshot = null;
      if (dataSnapshot && contactoId) {
          host.mostrarAcuerdoFlotanteDesdeNegociacion(contactoId, dataSnapshot);
      } else if (snap) {
          host.mostrarAcuerdoFlotante(snap);
      }
  }

  async function dismissAcuerdoFlotante(host) {
      const item = host.acuerdoFlotanteActual;
      if (!item || !item.contacto_id) {
          host.ocultarAcuerdoFlotante();
          return;
      }
      try {
          await fetch(`/api/contactos/${item.contacto_id}/negociacion/dismiss-resumen`, {
              method: 'POST',
              credentials: 'same-origin',
              headers: getRuanaAuthHeaders({ 'Content-Type': 'application/json' }),
              body: '{}',
          });
      } catch (e) { /* ignore */ }
      host.ocultarAcuerdoFlotante();
  }

  async function confirmarAcuerdoDesdeFlotante(host) {
      const item = host.acuerdoFlotanteActual;
      if (!item || !item.contacto_id) return;
      if (host.negociacionGuiada) {
          host.negociacionGuiada.contactoId = item.contacto_id;
          host.negociacionGuiada.data = Object.assign({}, host.negociacionGuiada.data || {}, {
              estado_contacto: item.estado || 'acuerdo_alcanzado',
              acuerdo_alcanzado: true,
              yo_confirme_cierre: !!item.yo_confirme_cierre,
          });
          await host.negociacionGuiada.confirmarCerrarNegociacion();
      }
  }

  function handleAvisoNoSeConcreto(host) {
      if (!host.contactoActual) return;
      const modal = document.getElementById('modal-no-concretado');
      if (modal) modal.classList.add('show');
  }

  async function finalizarContactoCerradoEnUI(host, contactoId, opts) {
      const options = opts || {};
      const id = contactoId != null ? Number(contactoId) : null;
      if (id != null && host.contactoActual && Number(host.contactoActual.id) === id) {
          host.contactoActual = null;
      }
      if (Array.isArray(host.contactosAbiertos) && id != null) {
          host.contactosAbiertos = host.contactosAbiertos.filter(c => Number(c.id) !== id);
      }
      const avisoEl = document.getElementById('contacto-aviso-persistente');
      if (avisoEl) avisoEl.style.display = 'none';
      if (options.cerrarModal !== false && host.negociacionGuiada && typeof host.negociacionGuiada.cerrar === 'function') {
          host.negociacionGuiada.cerrar();
      }
      await host.refreshAfterAction(['contactos', 'directorio', 'alertas', 'metricas']);
  }

  function abrirNegociacionContacto(host, contactoId, profesional, opts) {
      if (!host.negociacionGuiada) {
          alert('Negociación guiada no disponible.');
          return;
      }
      let titulo = 'Negociación guiada RUANA';
      if (profesional && profesional.nombre) {
          titulo += ' · ' + profesional.nombre;
      }
      let esUrgente = !!(opts && opts.es_urgente);
      if (!esUrgente && host.contactoActual && Number(host.contactoActual.id) === Number(contactoId)) {
          esUrgente = !!host.contactoActual.es_urgente;
      }
      const badge = document.getElementById('neg-urgente-badge');
      if (badge) badge.style.display = esUrgente ? 'inline-block' : 'none';
      host.negociacionGuiada.abrir(contactoId, titulo);
  }

  function abrirNegociacionDesdeContactoActual(host) {
      if (!host.contactoActual || !host.contactoActual.id) return;
      host.abrirNegociacionContacto(host.contactoActual.id, null);
  }

  function abrirChatContacto(host, contactoId, profesional, opts) {
      host.abrirNegociacionContacto(contactoId, profesional, opts);
  }

  function _obtenerServicioSeleccionadoPrevio(host, profesional) {
      const inputOtro = document.getElementById('contacto-previo-servicio-otro');
      const custom = inputOtro ? String(inputOtro.value || '').trim() : '';
      if (custom) return custom;
      const catalogoList = document.getElementById('contacto-previo-catalogo-list');
      const selected = catalogoList ? catalogoList.querySelector('.neg-catalogo-item.selected') : null;
      if (selected) {
          const idx = parseInt(selected.getAttribute('data-idx') || '-1', 10);
          const item = (host._catalogoPrevioItems || [])[idx];
          if (item && item.descripcion) return item.descripcion;
      }
      if ((host._catalogoPrevioItems || []).length > 0) return '';
      return (profesional && profesional.oficio) || 'Servicio RUANA';
  }

  function _obtenerPrecioCatalogoPrevio(host) {
      const catalogoList = document.getElementById('contacto-previo-catalogo-list');
      const selected = catalogoList ? catalogoList.querySelector('.neg-catalogo-item.selected') : null;
      if (selected) {
          const idx = parseInt(selected.getAttribute('data-idx') || '-1', 10);
          const item = (host._catalogoPrevioItems || [])[idx];
          if (item && item.precio) return String(item.precio).trim();
      }
      return '';
  }

modules.contactos = {
    mostrarAcuerdoFlotante: mostrarAcuerdoFlotante,
    cargarContactosPendientes: cargarContactosPendientes,
    mostrarAvisoPrevioContacto: mostrarAvisoPrevioContacto,
    _cargarCatalogoEnPrevioContacto: _cargarCatalogoEnPrevioContacto,
    _encargoUiLabels: _encargoUiLabels,
    renderEncargosActivos: renderEncargosActivos,
    crearContactoYAbrirNegociacion: crearContactoYAbrirNegociacion,
    handleAvisoSiHuboTrabajo: handleAvisoSiHuboTrabajo,
    confirmarImporteContacto: confirmarImporteContacto,
    mostrarResumenCierre: mostrarResumenCierre,
    subirPruebaConflicto: subirPruebaConflicto,
    confirmarNoConcretado: confirmarNoConcretado,
    cargarResumenesAcuerdoFlotantes: cargarResumenesAcuerdoFlotantes,
    handleAvisoSigueEnConversacion: handleAvisoSigueEnConversacion,
  
    syncAcuerdoFlotante: syncAcuerdoFlotante,
    mostrarAcuerdoFlotanteDesdeNegociacion: mostrarAcuerdoFlotanteDesdeNegociacion,
    ocultarAcuerdoFlotante: ocultarAcuerdoFlotante,
    ocultarAcuerdoFlotantePorModal: ocultarAcuerdoFlotantePorModal,
    restaurarAcuerdoFlotanteTrasNegociacion: restaurarAcuerdoFlotanteTrasNegociacion,
    dismissAcuerdoFlotante: dismissAcuerdoFlotante,
    confirmarAcuerdoDesdeFlotante: confirmarAcuerdoDesdeFlotante,
    handleAvisoNoSeConcreto: handleAvisoNoSeConcreto,
    finalizarContactoCerradoEnUI: finalizarContactoCerradoEnUI,
    abrirNegociacionContacto: abrirNegociacionContacto,
    abrirNegociacionDesdeContactoActual: abrirNegociacionDesdeContactoActual,
    abrirChatContacto: abrirChatContacto,
    _obtenerServicioSeleccionadoPrevio: _obtenerServicioSeleccionadoPrevio,
    _obtenerPrecioCatalogoPrevio: _obtenerPrecioCatalogoPrevio,
};
})(typeof window !== 'undefined' ? window : globalThis);
