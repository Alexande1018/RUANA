/**
 * Negociación guiada RUANA — conversación del encargo.
 */
(function (global) {
    'use strict';

    const INPUT_TYPES = {
        servicio: 'text',
        fecha: 'date',
        hora: 'time',
        direccion: 'text',
        precio: 'number',
        observaciones: 'textarea',
    };

    const ESTADO_LABELS = {
        pendiente: 'Pendiente',
        en_negociacion: 'En negociación',
        confirmado: 'Confirmado',
    };

    const PASO_LABELS = {
        servicio: 'Servicio',
        fecha: 'Fecha',
        hora: 'Hora',
        direccion: 'Dirección',
        precio: 'Precio',
        observaciones: 'Observaciones',
    };

    function notify(message, type) {
        const msg = String(message || '');
        if (typeof global.RuanaUI !== 'undefined') {
            const inferred = type || global.RuanaUI.inferToastType(msg);
            if (inferred === 'error') {
                global.RuanaUI.error('', msg);
            } else if (inferred === 'warning') {
                global.RuanaUI.warning('', msg);
            } else if (inferred === 'success') {
                global.RuanaUI.success(msg);
            } else {
                global.RuanaUI.toast(msg, inferred);
            }
            return;
        }
        alert(msg);
    }

    const PREGUNTAS_DEFAULT = {
        servicio: 'Hola, ¿qué servicio necesitas? Puedes elegir del catálogo o escribirlo tú.',
        fecha: '¿Qué fecha te vendría bien para el servicio?',
        hora: '¿A qué hora prefieres que vayamos?',
        direccion: '¿Cuál es la dirección donde realizar el trabajo?',
        observaciones: '¿Alguna observación adicional? (acceso, detalles del trabajo, etc.)',
        precio: 'Indica el precio que propones por este encargo.',
    };

    function getAuthHeaders(extra) {
        if (typeof global.getRuanaAuthHeaders === 'function') {
            return global.getRuanaAuthHeaders(extra || {});
        }
        return extra || {};
    }

    function getApiBase() {
        if (typeof global.getApiBase === 'function') {
            return String(global.getApiBase() || '').replace(/\/$/, '');
        }
        const base = global.RUANA_API_BASE
            || (typeof global.location !== 'undefined' ? global.location.origin : '');
        return String(base || '').replace(/\/$/, '');
    }

    function apiUrl(path) {
        const normalized = path.startsWith('/') ? path : `/${path}`;
        return `${getApiBase()}${normalized}`;
    }

    function contactoIdValido(id) {
        const n = Number(id);
        return Number.isFinite(n) && n > 0 ? n : null;
    }

    class NegociacionGuiada {
        constructor(panel) {
            this.panel = panel;
            this.contactoId = null;
            this.data = null;
            this._pollId = null;
            this._drafts = {};
            this._lastAccionKey = '';
            this._wizard = null;
            this._catalogoCache = {};
            this._catalogoAbierto = false;
            this._cambiarServicio = false;
            this._precioReferencia = '';
            this._bindModal();
        }

        _bindModal() {
            const cerrar = document.getElementById('neg-btn-cerrar');
            const cerrarX = document.getElementById('neg-btn-cerrar-x');
            const cerrarNeg = document.getElementById('neg-btn-cerrar-negociacion');
            if (cerrar) cerrar.addEventListener('click', () => this.cerrar());
            if (cerrarX) cerrarX.addEventListener('click', () => this.cerrar());
            if (cerrarNeg) cerrarNeg.addEventListener('click', () => this.confirmarCerrarNegociacion());
            const ctaConfirmar = document.getElementById('neg-cta-flotante-confirmar');
            if (ctaConfirmar) {
                ctaConfirmar.addEventListener('click', () => this.confirmarCerrarNegociacion());
            }
            const overlay = document.getElementById('modal-negociacion-guiada');
            if (overlay) {
                overlay.addEventListener('click', (e) => {
                    if (e.target === overlay) this.cerrar();
                });
                overlay.addEventListener('keydown', (e) => {
                    if (e.key === 'Escape') this.cerrar();
                });
            }
            const toggleResumen = document.getElementById('neg-resumen-toggle');
            if (toggleResumen) {
                toggleResumen.addEventListener('click', () => {
                    const panel = document.getElementById('neg-resumen-panel');
                    if (panel) panel.classList.toggle('open');
                });
            }
        }

        async abrir(contactoId, tituloExtra) {
            const id = contactoIdValido(contactoId);
            if (!id) {
                notify('No se pudo abrir la negociación: contacto no válido.', 'error');
                return;
            }
            this.contactoId = id;
            const modal = document.getElementById('modal-negociacion-guiada');
            const title = document.getElementById('neg-modal-title');
            if (title) title.textContent = tituloExtra || 'Negociación guiada RUANA';
            if (modal) {
                modal.classList.add('show');
                modal.setAttribute('aria-hidden', 'false');
                const focusTarget = document.getElementById('neg-btn-cerrar-x')
                    || document.getElementById('neg-btn-cerrar');
                if (focusTarget) focusTarget.focus();
            }
            document.body.classList.add('neg-modal-abierto');
            if (this.panel && typeof this.panel.ocultarAcuerdoFlotantePorModal === 'function') {
                this.panel.ocultarAcuerdoFlotantePorModal();
            }
            await this.refrescar();
            this.iniciarPolling();
        }

        cerrar() {
            const dataSnapshot = this.data;
            const contactoId = this.contactoId;
            this.detenerPolling();
            const modal = document.getElementById('modal-negociacion-guiada');
            if (modal) {
                modal.classList.remove('show');
                modal.setAttribute('aria-hidden', 'true');
            }
            this.contactoId = null;
            this.data = null;
            this._drafts = {};
            this._lastAccionKey = '';
            this._wizard = null;
            this._catalogoAbierto = false;
            this._cambiarServicio = false;
            this._precioReferencia = '';
            this._ocultarCtaFlotante();
            document.body.classList.remove('neg-modal-abierto');
            if (this.panel && typeof this.panel.restaurarAcuerdoFlotanteTrasNegociacion === 'function') {
                this.panel.restaurarAcuerdoFlotanteTrasNegociacion(contactoId, dataSnapshot);
            } else if (dataSnapshot && contactoId && this.panel && typeof this.panel.mostrarAcuerdoFlotanteDesdeNegociacion === 'function') {
                this.panel.mostrarAcuerdoFlotanteDesdeNegociacion(contactoId, dataSnapshot);
            }
        }

        _miCodigo() {
            if (!this.data) return '';
            return this.data.rol === 'profesional'
                ? String(this.data.profesional_codigo || '').trim()
                : String(this.data.solicitante_codigo || '').trim();
        }

        _stripePagoBloqueado() {
            return !!(this.data && this.data.profesional_stripe_listo === false);
        }

        _htmlAvisoStripeBloqueo() {
            const rol = this.data.rol || 'solicitante';
            const opts = {
                mensaje: this.data.mensaje_stripe_negociacion
                    || this.data.aviso_stripe_profesional
                    || this.data.aviso_pago_no_disponible,
            };
            if (global.RuanaStripePagos && global.RuanaStripePagos.htmlBloqueoPrecioNegociacion) {
                return global.RuanaStripePagos.htmlBloqueoPrecioNegociacion(rol, opts);
            }
            const detalle = rol === 'profesional'
                ? 'Conecta tu cuenta de pago para poder cerrar encargos con precio.'
                : 'Este profesional debe activar su cuenta de pago antes de que puedas confirmar el precio final.';
            return `<div class="neg-stripe-bloqueo-precio" role="alert"><p>${this.escapeHtml(detalle)}</p></div>`;
        }

        _enlazarStripeEnAcciones() {
            const wrap = document.getElementById('neg-acciones-wrap');
            if (wrap && global.RuanaStripePagos && global.RuanaStripePagos.enlazarBotonesOnboarding) {
                global.RuanaStripePagos.enlazarBotonesOnboarding(wrap);
            }
        }

        _hostStripe() {
            if (this.panel) return this.panel;
            return {
                codigoAliado: this._miCodigo(),
                aliado: { codigo: this._miCodigo() },
                cargarContactosPendientes: async () => {
                    if (this.panel && typeof this.panel.cargarContactosPendientes === 'function') {
                        await this.panel.cargarContactosPendientes();
                    }
                },
                refreshAfterAction: async (keys) => {
                    if (this.panel && typeof this.panel.refreshAfterAction === 'function') {
                        await this.panel.refreshAfterAction(keys);
                    }
                },
            };
        }

        _contactoStripeDesdeData() {
            return {
                id: this.contactoId,
                estado: this.data.estado_contacto || '',
                estado_contacto: this.data.estado_contacto || '',
                modo_pago: this.data.modo_pago || 'stripe',
                estado_pago: this.data.estado_pago || '',
                importe_acordado: this.data.importe_acordado,
                solicitante_codigo: this.data.solicitante_codigo,
                profesional_codigo: this.data.profesional_codigo,
            };
        }

        _renderAccionesPagoStripe() {
            const el = document.getElementById('neg-acciones-wrap');
            if (!el || !this.data) return;
            const importe = this.data.importe_acordado;
            const importeTxt = importe != null && Number(importe) > 0
                ? ` Importe acordado: ${Number(importe).toFixed(2)} €.`
                : '';
            el.innerHTML = `<div class="neg-compose-stack neg-pago-stripe-wrap">
                <p class="neg-esperar-msg">Acuerdo confirmado.${importeTxt}</p>
                <div id="neg-stripe-pago-acciones" class="encargo-stripe-acciones"></div>
            </div>`;
            const slot = document.getElementById('neg-stripe-pago-acciones');
            if (slot && global.RuanaStripePagos && global.RuanaStripePagos.renderStripeAcciones) {
                global.RuanaStripePagos.renderStripeAcciones(
                    this._hostStripe(),
                    this._contactoStripeDesdeData(),
                    slot
                );
            }
            const btnPagar = slot && slot.querySelector('.stripe-pagar-btn');
            if (btnPagar && this.contactoId) {
                btnPagar.setAttribute('data-contacto-id', String(this.contactoId));
            }
        }

        _camposSolicitante() {
            if (this.data && Array.isArray(this.data.campos_solicitante)) {
                return this.data.campos_solicitante;
            }
            return ['servicio', 'fecha', 'hora', 'direccion', 'observaciones'];
        }

        _camposWizard(acc) {
            if (acc && Array.isArray(acc.campos) && acc.campos.length) {
                return acc.campos;
            }
            return this._camposSolicitante();
        }

        _camposWizardActivos(acc) {
            const base = this._camposWizard(acc);
            if (this._cambiarServicio && !base.includes('servicio')) {
                return ['servicio'].concat(base);
            }
            return base;
        }

        _servicioPrecargado() {
            if (!this.data) return '';
            const acc = this.data.accion || {};
            if (acc.servicio_precargado) return String(acc.servicio_precargado).trim();
            if (this.data.servicio_contacto) return String(this.data.servicio_contacto).trim();
            const sug = (acc.valores_sugeridos || {}).servicio;
            return sug ? String(sug).trim() : '';
        }

        _ensureWizardServicioPrecargado(acc) {
            const servicio = this._servicioPrecargado();
            if (!servicio || this._cambiarServicio) return;
            const w = this._loadWizard();
            if (!w.respuestas.servicio) {
                w.respuestas.servicio = servicio;
            }
            const yaHistorial = w.historial.some(h =>
                h.tipo === 'sistema' && h.campo === 'servicio'
            );
            if (!yaHistorial) {
                w.historial.push({
                    tipo: 'sistema',
                    campo: 'servicio',
                    texto: 'Servicio seleccionado al contactar: «' + servicio + '»',
                });
            }
            this._saveWizard();
        }

        _htmlSelectorServicio(campo) {
            if (campo !== 'servicio') return '';
            return '<div class="neg-servicio-compose">' +
                '<button type="button" class="neg-btn neg-btn-catalogo-toggle" id="neg-btn-mostrar-catalogo">' +
                    'Mostrar catálogo de servicios' +
                '</button>' +
                '<div id="neg-catalogo-panel" class="neg-catalogo-panel" hidden>' +
                    '<div id="neg-catalogo-servicios" class="neg-catalogo-list"></div>' +
                    '<label class="neg-catalogo-otro-label" for="neg-input-valor">Otros</label>' +
                '</div>' +
            '</div>';
        }

        _enlazarCatalogoServicio(campo, profCodigo) {
            if (campo !== 'servicio' || !profCodigo) return;
            const btnToggle = document.getElementById('neg-btn-mostrar-catalogo');
            const panel = document.getElementById('neg-catalogo-panel');
            if (!btnToggle || !panel) return;

            const abrir = () => {
                panel.hidden = false;
                this._catalogoAbierto = true;
                btnToggle.textContent = 'Ocultar catálogo';
                btnToggle.setAttribute('aria-expanded', 'true');
                this._cargarCatalogoServicios(profCodigo, 'neg-catalogo-servicios', 'neg-input-valor');
            };

            const cerrar = () => {
                panel.hidden = true;
                this._catalogoAbierto = false;
                btnToggle.textContent = 'Mostrar catálogo de servicios';
                btnToggle.setAttribute('aria-expanded', 'false');
            };

            if (this._catalogoAbierto) {
                abrir();
            } else {
                cerrar();
            }

            btnToggle.onclick = () => {
                if (panel.hidden) abrir();
                else cerrar();
            };
        }

        _preguntasWizard(acc) {
            if (acc && acc.preguntas) return acc.preguntas;
            return PREGUNTAS_DEFAULT;
        }

        _wizardStorageKey() {
            return `ruana_neg_wizard_${this.contactoId}`;
        }

        _loadWizard() {
            if (this._wizard) return this._wizard;
            try {
                const raw = sessionStorage.getItem(this._wizardStorageKey());
                if (raw) this._wizard = JSON.parse(raw);
            } catch (e) { /* ignore */ }
            if (!this._wizard) {
                this._wizard = { historial: [], respuestas: {}, pasoIdx: 0 };
            }
            return this._wizard;
        }

        _saveWizard() {
            if (!this.contactoId || !this._wizard) return;
            try {
                sessionStorage.setItem(this._wizardStorageKey(), JSON.stringify(this._wizard));
            } catch (e) { /* ignore */ }
        }

        _clearWizard() {
            this._wizard = null;
            if (this.contactoId) {
                try { sessionStorage.removeItem(this._wizardStorageKey()); } catch (e) { /* ignore */ }
            }
        }

        _accionKey(acc) {
            if (!acc) return '';
            if (acc.tipo === 'wizard_contratante') {
                const w = this._loadWizard();
                return `wizard|${w.pasoIdx}|${w.historial.length}`;
            }
            return [
                acc.tipo,
                acc.campo || '',
                acc.valor_actual || '',
                acc.propuesto_por || '',
                acc.modificar_propia ? '1' : '0',
                (this.data && this.data.eventos ? this.data.eventos.length : 0),
            ].join('|');
        }

        _formularioEnUso() {
            if (this._catalogoAbierto) return true;
            const wrap = document.getElementById('neg-acciones-wrap');
            return !!(wrap && document.activeElement && wrap.contains(document.activeElement));
        }

        _guardarBorradoresFormulario(campo) {
            const wrap = document.getElementById('neg-acciones-wrap');
            if (wrap) {
                wrap.querySelectorAll('[data-neg-campo]').forEach(input => {
                    const c = input.getAttribute('data-neg-campo');
                    if (c) this._drafts[c] = input.value;
                });
            }
            if (!campo) return;
            const input = document.getElementById('neg-input-valor');
            if (input) this._drafts[campo] = input.value;
            const contra = document.getElementById('neg-input-contraoferta');
            if (contra) this._drafts[`contra_${campo}`] = contra.value;
        }

        _valorBorrador(campo, fallback) {
            const draft = this._drafts[campo];
            if (draft !== undefined && draft !== null && String(draft).length > 0) {
                return String(draft);
            }
            return fallback || '';
        }

        _enlazarGuardadoBorrador(campo) {
            const guardar = () => this._guardarBorradoresFormulario(campo);
            const wrap = document.getElementById('neg-acciones-wrap');
            if (wrap) {
                wrap.querySelectorAll('[data-neg-campo]').forEach(input => {
                    input.addEventListener('input', guardar);
                    input.addEventListener('change', guardar);
                });
            }
            const input = document.getElementById('neg-input-valor');
            if (input) {
                input.addEventListener('input', guardar);
                input.addEventListener('change', guardar);
            }
            const contra = document.getElementById('neg-input-contraoferta');
            if (contra) {
                contra.addEventListener('input', guardar);
                contra.addEventListener('change', guardar);
            }
        }

        iniciarPolling() {
            this.detenerPolling();
            this._pollId = setInterval(() => {
                if (this._formularioEnUso()) return;
                this.refrescar(true);
            }, 2500);
        }

        detenerPolling() {
            if (this._pollId) {
                clearInterval(this._pollId);
                this._pollId = null;
            }
        }

        async refrescar(silent) {
            const contactoId = contactoIdValido(this.contactoId);
            if (!contactoId) return;
            try {
                const resp = await fetch(apiUrl(`/api/contactos/${contactoId}/negociacion`), {
                    credentials: 'same-origin',
                    headers: getAuthHeaders(),
                });
                const data = await resp.json();
                if (data.status !== 'success') {
                    if (!silent) notify(data.message || 'No se pudo cargar la negociación', 'error');
                    return;
                }
                const prevTipo = this.data && this.data.accion && this.data.accion.tipo;
                this.data = data;
                if (prevTipo === 'wizard_contratante' && data.accion && data.accion.tipo !== 'wizard_contratante') {
                    this._clearWizard();
                }
                this.render();
                const estadoCerrado = ['cerrado_no_concretado', 'no_concretado'].includes(data.estado_contacto || '')
                    || (data.accion && data.accion.tipo === 'cerrado' && data.estado_contacto !== 'trabajo_cerrado');
                if (estadoCerrado && this.panel && typeof this.panel.finalizarContactoCerradoEnUI === 'function') {
                    await this.panel.finalizarContactoCerradoEnUI(this.contactoId, { cerrarModal: true });
                } else if (this.panel && typeof this.panel.syncAcuerdoFlotante === 'function') {
                    this.panel.syncAcuerdoFlotante(data);
                }
            } catch (e) {
                if (!silent) console.error(e);
            }
        }

        render() {
            if (!this.data) return;
            this.renderHeaderContext();
            this.renderStripeAviso();
            this.renderPasoActual();
            this.renderEstadoBar();
            this.renderTimeline();
            this.renderResumen();
            this.renderAcciones();
            this.renderAcuerdoFinal();
            this.renderCtaFlotante();
            this.renderBotonesHeader();
        }

        _contactoAbiertoActual() {
            if (!this.panel || !this.contactoId) return null;
            const list = Array.isArray(this.panel.contactosAbiertos) ? this.panel.contactosAbiertos : [];
            return list.find(c => Number(c.id) === Number(this.contactoId)) || null;
        }

        _uiConversacion() {
            return typeof global.RuanaConversacionUI !== 'undefined' ? global.RuanaConversacionUI : null;
        }

        renderHeaderContext() {
            const ui = this._uiConversacion();
            const contacto = this._contactoAbiertoActual();
            const avatarEl = document.getElementById('neg-header-avatar');
            const subtitleEl = document.getElementById('neg-header-subtitle');
            const estadoEl = document.getElementById('neg-header-estado');
            const servicioEl = document.getElementById('neg-header-servicio');
            const titleEl = document.getElementById('neg-modal-title');

            let contraparte = { nombre: 'Conversación del encargo', oficio: '', fotoUrl: '', codigo: '' };
            if (ui && contacto) {
                contraparte = ui.resolveContraparte(this.panel, contacto);
            } else if (this.data) {
                const cod = this.data.rol === 'profesional'
                    ? this.data.solicitante_codigo
                    : this.data.profesional_codigo;
                contraparte.codigo = cod || '';
                contraparte.nombre = cod ? ('Aliado ' + cod) : contraparte.nombre;
            }

            if (titleEl) titleEl.textContent = contraparte.nombre;
            if (subtitleEl) {
                subtitleEl.textContent = contraparte.oficio
                    ? contraparte.oficio
                    : (contacto && contacto.servicio) || 'Encargo RUANA';
            }
            if (servicioEl) {
                const serv = (contacto && contacto.servicio)
                    || this.data.servicio_contacto
                    || '';
                servicioEl.textContent = serv ? ('Encargo: ' + serv) : '';
                servicioEl.style.display = serv ? '' : 'none';
            }
            if (avatarEl && ui) {
                avatarEl.innerHTML = ui.renderAvatarHtml(
                    this.panel,
                    contraparte.fotoUrl,
                    contraparte.nombre,
                    'neg-header-avatar-inner'
                );
            }
            if (estadoEl && contacto && this.panel && typeof this.panel._encargoUiLabels === 'function') {
                const labels = this.panel._encargoUiLabels(contacto);
                estadoEl.textContent = labels.estadoLabel || 'En negociación';
                estadoEl.className = 'neg-header-estado' + (labels.requiereRespuesta ? ' is-turno' : '');
            } else if (estadoEl && this.data && this.data.negociacion_meta) {
                const meta = this.data.negociacion_meta;
                estadoEl.textContent = meta.requiere_mi_respuesta ? 'Tu turno' : 'En negociación';
                estadoEl.className = 'neg-header-estado' + (meta.requiere_mi_respuesta ? ' is-turno' : '');
            }
        }

        renderStripeAviso() {
            const el = document.getElementById('neg-stripe-aviso');
            if (!el || !this.data) return;
            if (this.data.profesional_stripe_listo !== false) {
                el.style.display = 'none';
                el.innerHTML = '';
                return;
            }
            if (global.RuanaStripePagos && global.RuanaStripePagos.renderAvisoNegociacion) {
                global.RuanaStripePagos.renderAvisoNegociacion(el, this.data.rol, {
                    mensaje: this.data.mensaje_stripe_negociacion
                        || this.data.aviso_stripe_profesional,
                    aviso: this.data.aviso_pago_no_disponible,
                });
                return;
            }
            el.style.display = 'block';
            el.textContent = this.data.mensaje_stripe_negociacion
                || this.data.aviso_pago_no_disponible
                || 'Pago no disponible todavía con este profesional';
        }

        renderEstadoBar() {
            const el = document.getElementById('neg-estado-bar');
            if (!el) return;
            const meta = this.data.negociacion_meta;
            const acc = this.data.accion || {};
            if (!meta && !acc.tipo) {
                el.style.display = 'none';
                return;
            }
            const confirmados = meta ? (meta.progreso_confirmados || 0) : 0;
            const total = meta ? (meta.progreso_total || 6) : 6;
            const pct = total > 0 ? Math.round((confirmados / total) * 100) : 0;
            const requiere = meta && meta.requiere_mi_respuesta;
            const espera = acc.tipo === 'esperar';
            el.className = 'neg-estado-bar' + (requiere ? ' requiere-respuesta' : (espera ? ' espera' : ''));
            el.style.display = 'block';
            const titulo = requiere
                ? 'Es tu turno'
                : (meta && meta.fase === 'acuerdo' ? 'Acuerdo alcanzado' : (espera ? 'Esperando respuesta' : 'Negociación en curso'));
            const contexto = (meta && meta.siguiente_accion) || acc.mensaje || '';
            const pasoLabel = meta && meta.paso_label ? meta.paso_label : '';
            el.innerHTML = `<p class="neg-estado-titulo">${this.escapeHtml(titulo)}${pasoLabel ? ' · ' + this.escapeHtml(pasoLabel) : ''}</p>
                <p class="neg-estado-contexto">${this.escapeHtml(contexto)}</p>
                <div class="neg-estado-progreso">
                    <div class="neg-estado-progreso-bar"><div class="neg-estado-progreso-fill" style="width:${pct}%"></div></div>
                    <span class="neg-estado-progreso-texto">${confirmados}/${total}</span>
                </div>`;
        }

        renderPasoActual() {
            const el = document.getElementById('neg-paso-actual');
            if (!el) return;
            const paso = this.data.paso_actual || (this.data.accion && this.data.accion.campo) || 'servicio';
            const label = PASO_LABELS[paso] || paso;
            const rol = this.data.rol === 'profesional' ? 'Profesional' : 'Contratante';
            el.textContent = `${label} · ${rol}`;
        }

        _stripePagoPendiente() {
            if (!this.data) return false;
            const modo = (this.data.modo_pago || 'stripe').toString().trim() || 'stripe';
            if (modo !== 'stripe') return false;
            const estado = this.data.estado_contacto || '';
            const estadoPago = this.data.estado_pago || '';
            if (['cobro_confirmado', 'transferido'].includes(estadoPago)) return false;
            if (estado === 'pendiente_de_pago') return true;
            return ['esperando_cobro_cliente', 'checkout_activo', 'no_generado'].includes(estadoPago);
        }

        _soyContratante() {
            if (!this.data) return false;
            return this.data.rol === 'solicitante'
                || this._miCodigo() === String(this.data.solicitante_codigo || '').trim();
        }

        _ocultarCtaFlotante() {
            const wrap = document.getElementById('neg-cta-flotante');
            if (!wrap) return;
            wrap.hidden = true;
            wrap.classList.remove('is-visible');
        }

        renderCtaFlotante() {
            const wrap = document.getElementById('neg-cta-flotante');
            if (!wrap || !this.data) return;
            const estado = this.data.estado_contacto || '';
            const acuerdo = !!(this.data.acuerdo_alcanzado
                || ['acuerdo_alcanzado', 'pendiente_de_pago', 'trabajo_cerrado'].includes(estado));
            if (!acuerdo) {
                this._ocultarCtaFlotante();
                return;
            }
            const yaConfirme = !!this.data.yo_confirme_cierre;
            const trabajoCerrado = estado === 'trabajo_cerrado';
            const mostrarConfirmar = !yaConfirme && !trabajoCerrado;
            const mostrarPagar = this._soyContratante() && this._stripePagoPendiente();
            if (!mostrarConfirmar && !mostrarPagar) {
                this._ocultarCtaFlotante();
                return;
            }
            const kicker = document.getElementById('neg-cta-flotante-kicker');
            const msg = document.getElementById('neg-cta-flotante-msg');
            const btnConfirmar = document.getElementById('neg-cta-flotante-confirmar');
            const btnPagar = document.getElementById('neg-cta-flotante-pagar');
            if (kicker) kicker.textContent = mostrarPagar && yaConfirme ? 'Pago pendiente' : 'Acuerdo alcanzado';
            if (msg) {
                if (mostrarPagar && !mostrarConfirmar) {
                    msg.textContent = 'El importe acordado está listo. Pulsa «Ir a pagar» para completar el cobro con Stripe.';
                } else if (mostrarPagar) {
                    msg.textContent = 'Confirma el acuerdo y pulsa «Ir a pagar» para no dejar el encargo a medias.';
                } else {
                    msg.textContent = 'Revisa el resumen y confirma el acuerdo. Este paso no debe pasar desapercibido.';
                }
            }
            if (btnConfirmar) {
                btnConfirmar.hidden = !mostrarConfirmar;
                btnConfirmar.disabled = !mostrarConfirmar;
            }
            if (btnPagar) {
                btnPagar.hidden = !mostrarPagar;
                btnPagar.disabled = !mostrarPagar;
                if (this.contactoId) {
                    btnPagar.setAttribute('data-contacto-id', String(this.contactoId));
                } else {
                    btnPagar.removeAttribute('data-contacto-id');
                }
            }
            wrap.hidden = false;
            wrap.classList.add('is-visible');
        }

        renderBotonesHeader() {
            const btnCerrarNeg = document.getElementById('neg-btn-cerrar-negociacion');
            if (!btnCerrarNeg) return;
            const estado = this.data.estado_contacto || '';
            const abandonado = ['cerrado_no_concretado', 'no_concretado'].includes(estado);
            const trabajoCerrado = estado === 'trabajo_cerrado';
            const acuerdo = estado === 'acuerdo_alcanzado'
                || estado === 'pendiente_de_pago'
                || this.data.acuerdo_alcanzado;
            if (abandonado || (trabajoCerrado && this.data.yo_confirme_cierre)) {
                btnCerrarNeg.style.display = 'none';
                return;
            }
            if (acuerdo || trabajoCerrado) {
                // El CTA flotante centrado sustituye al botón pequeño de cabecera.
                btnCerrarNeg.style.display = 'none';
                return;
            }
            btnCerrarNeg.style.display = '';
            btnCerrarNeg.textContent = 'Cerrar';
            btnCerrarNeg.disabled = false;
        }

        _bubbleHtml(tipo, texto, meta) {
            const cls = tipo === 'mine' ? 'neg-bubble mine'
                : tipo === 'system' ? 'neg-bubble system'
                    : 'neg-bubble theirs';
            return `<div class="${cls}">
                <div class="neg-bubble-text">${this.escapeHtml(texto || '')}</div>
                ${meta ? `<div class="neg-bubble-meta">${this.escapeHtml(meta)}</div>` : ''}
            </div>`;
        }

        _formatValor(campo, valor) {
            const ui = this._uiConversacion();
            if (ui && typeof ui.formatValor === 'function') {
                return ui.formatValor(campo, valor);
            }
            if (campo === 'fecha' && valor) {
                try {
                    const d = new Date(valor + 'T12:00:00');
                    return d.toLocaleDateString('es-ES', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' });
                } catch (e) { /* fallthrough */ }
            }
            return valor;
        }

        _wrapComposeCard(titulo, innerHtml) {
            return `<div class="neg-context-card" role="form" aria-label="${this.escapeHtml(titulo)}">
                <p class="neg-context-card-title">${this.escapeHtml(titulo)}</p>
                <div class="neg-context-card-body">${innerHtml}</div>
            </div>`;
        }

        _timelineItems() {
            const ui = this._uiConversacion();
            const items = [];
            const miCodigo = this._miCodigo();
            const contacto = this._contactoAbiertoActual();
            let contraparte = { nombre: 'Profesional', fotoUrl: '' };
            if (ui && contacto) {
                contraparte = ui.resolveContraparte(this.panel, contacto);
            }
            const avatarTheirs = ui
                ? ui.renderAvatarHtml(this.panel, contraparte.fotoUrl, contraparte.nombre, 'neg-msg-avatar')
                : '';
            const avatarMine = ui && this.panel
                ? ui.renderAvatarHtml(
                    this.panel,
                    (this.panel.aliado && (this.panel.aliado.foto_perfil_url || this.panel.aliado.foto_perfil)) || '',
                    (this.panel.aliado && this.panel.aliado.nombre) || 'Tú',
                    'neg-msg-avatar'
                )
                : '';

            const acc = this.data.accion || {};
            if (acc.tipo === 'wizard_contratante') {
                const w = this._loadWizard();
                const preguntas = this._preguntasWizard(acc);
                const campos = this._camposWizardActivos(acc);
                w.historial.forEach(item => {
                    const date = new Date();
                    if (item.tipo === 'pregunta') {
                        items.push({
                            kind: 'message',
                            side: 'theirs',
                            name: contraparte.nombre,
                            avatarHtml: avatarTheirs,
                            text: item.texto,
                            time: ui ? ui.formatTimeShort(date) : '',
                            date: date,
                        });
                    } else if (item.tipo === 'sistema') {
                        items.push({
                            kind: 'event',
                            event: { tipo: 'sistema', mensaje: item.texto, creado_en: date.toISOString() },
                        });
                    } else {
                        items.push({
                            kind: 'message',
                            side: 'mine',
                            name: 'Tú',
                            avatarHtml: avatarMine,
                            text: this._formatValor(item.campo, item.texto),
                            time: ui ? ui.formatTimeShort(date) : '',
                            date: date,
                        });
                    }
                });
                if (w.pasoIdx < campos.length) {
                    const campo = campos[w.pasoIdx];
                    const pregunta = preguntas[campo] || PREGUNTAS_DEFAULT[campo] || '';
                    const yaMostrada = w.historial.some(h => h.tipo === 'pregunta' && h.campo === campo);
                    if (!yaMostrada && pregunta) {
                        items.push({
                            kind: 'message',
                            side: 'theirs',
                            name: contraparte.nombre,
                            avatarHtml: avatarTheirs,
                            text: pregunta,
                            time: '',
                            date: new Date(),
                        });
                    }
                } else if (w.pasoIdx >= campos.length && campos.length) {
                    items.push({
                        kind: 'event',
                        event: {
                            tipo: 'sistema',
                            mensaje: 'Revisa tus respuestas y envía todo al profesional cuando estés listo.',
                            creado_en: new Date().toISOString(),
                        },
                    });
                }
            }

            const eventos = Array.isArray(this.data.eventos) ? this.data.eventos : [];
            eventos.forEach(ev => {
                const fecha = ev.creado_en ? new Date(ev.creado_en) : new Date();
                const time = ui ? ui.formatTimeShort(fecha) : '';
                if (ev.tipo === 'sistema' || ev.tipo === 'propuesta' || ev.tipo === 'contraoferta' || ev.tipo === 'aceptacion') {
                    items.push({ kind: 'event', event: ev });
                    return;
                }
                const emisor = String(ev.emisor_codigo || '').trim();
                const esMio = emisor && emisor === miCodigo;
                items.push({
                    kind: 'message',
                    side: esMio ? 'mine' : 'theirs',
                    name: esMio ? 'Tú' : contraparte.nombre,
                    avatarHtml: esMio ? avatarMine : avatarTheirs,
                    text: ev.mensaje || '',
                    time: time,
                    date: fecha,
                });
            });
            return items;
        }

        renderTimeline() {
            const el = document.getElementById('neg-timeline');
            if (!el) return;
            const ui = this._uiConversacion();
            const items = this._timelineItems();
            if (!items.length) {
                el.innerHTML = '<p class="neg-chat-empty">La conversación del encargo aparecerá aquí.</p>';
                return;
            }
            if (ui && typeof ui.buildTimelineHtml === 'function') {
                el.innerHTML = ui.buildTimelineHtml({
                    items: items,
                    escapeHtml: (s) => this.escapeHtml(s),
                });
            } else {
                el.innerHTML = items.map(i => {
                    if (i.kind === 'event') return this._bubbleHtml('system', i.event.mensaje || '', '');
                    return this._bubbleHtml(i.side === 'mine' ? 'mine' : 'theirs', i.text, i.name);
                }).join('');
            }
            el.scrollTop = el.scrollHeight;
        }

        renderResumen() {
            const el = document.getElementById('neg-resumen-lista');
            if (!el) return;
            const items = Array.isArray(this.data.resumen) ? this.data.resumen : [];
            el.innerHTML = items.map(item => {
                const estado = item.estado || 'pendiente';
                const estadoLabel = item.estado_label || ESTADO_LABELS[estado] || estado;
                const badge = `<span class="neg-badge ${estado}">${this.escapeHtml(estadoLabel)}</span>`;
                const val = item.valor ? this.escapeHtml(String(item.valor)) : '—';
                return `<div class="neg-resumen-item">
                    <span class="neg-resumen-label">${this.escapeHtml(item.label || item.campo)}</span>
                    <span class="neg-resumen-valor">${val}<br>${badge}</span>
                </div>`;
            }).join('');
        }

        renderAcuerdoFinal() {
            const wrap = document.getElementById('neg-acuerdo-final');
            if (!wrap) return;
            const estado = this.data.estado_contacto || '';
            const completo = this.data.acuerdo_alcanzado
                || estado === 'acuerdo_alcanzado'
                || estado === 'trabajo_cerrado';
            if (!completo) {
                wrap.style.display = 'none';
                return;
            }
            wrap.style.display = 'block';
            const items = (this.data.resumen || []).filter(i => i.valor && i.campo !== 'observaciones_profesional');
            let hint = 'El precio aceptado es el importe oficial del encargo y se genera el Apoyo RUANA.';
            if (this.data.ambos_confirmaron_cierre || estado === 'trabajo_cerrado' || this.data.cierre_automatico) {
                hint = 'Precio aceptado como importe oficial. Encargo cerrado y Apoyo RUANA generado.';
            } else if (this.data.yo_confirme_cierre) {
                hint = 'Ya confirmaste el resumen. El cobro se basa en el precio aceptado.';
            } else if (this.data.cierre_aviso) {
                hint = String(this.data.cierre_aviso);
            }
            wrap.innerHTML = `<div class="neg-acuerdo-resumen neg-acuerdo-resumen--destacado">
                <div class="neg-acuerdo-resumen-head">
                    <span class="neg-acuerdo-resumen-icon" aria-hidden="true">✓</span>
                    <h3>Acuerdo alcanzado</h3>
                </div>
                <dl class="neg-acuerdo-resumen-dl">
                ${items.map(i => `<div class="neg-acuerdo-resumen-row"><dt>${this.escapeHtml(i.label)}</dt><dd>${this.escapeHtml(String(i.valor))}</dd></div>`).join('')}
                </dl>
                <p class="neg-acuerdo-hint">${this.escapeHtml(hint)}</p>
            </div>`;
        }

        renderAcciones() {
            const el = document.getElementById('neg-acciones-wrap');
            if (!el || !this.data) return;
            const acc = this.data.accion || {};
            const accionKey = this._accionKey(acc);

            if (this._catalogoAbierto && (
                acc.tipo === 'wizard_contratante'
                || (acc.tipo === 'proponer' && acc.campo === 'servicio')
            )) {
                return;
            }

            if (acc.tipo === 'wizard_contratante') {
                this._guardarBorradoresFormulario(null);
            } else if (acc.campo) {
                this._guardarBorradoresFormulario(acc.campo);
            }
            if (acc.tipo && this._formularioEnUso() && accionKey === this._lastAccionKey) {
                return;
            }
            this._lastAccionKey = accionKey;

            if (this._stripePagoPendiente() && (this._soyContratante() || acc.tipo === 'pago')) {
                this._renderAccionesPagoStripe();
                return;
            }

            if (!this.data.accion) return;

            if (this.data.acuerdo_alcanzado
                || this.data.estado_contacto === 'acuerdo_alcanzado'
                || this.data.estado_contacto === 'trabajo_cerrado') {
                let msg = 'Negociación completada. El precio aceptado es el importe oficial.';
                if (this.data.cierre_automatico || this.data.estado_contacto === 'trabajo_cerrado') {
                    msg = 'Negociación completada. Precio aceptado; Apoyo RUANA generado.';
                } else if (this.data.yo_confirme_cierre) {
                    msg = 'Ya revisaste el resumen del acuerdo.';
                }
                el.innerHTML = `<div class="neg-compose-stack">
                    <p class="neg-esperar-msg">${this.escapeHtml(msg)}</p>
                    <button type="button" class="neg-btn neg-btn-primary neg-btn-block" id="neg-btn-acuerdo-listo">Entendido</button>
                </div>`;
                const btnListo = document.getElementById('neg-btn-acuerdo-listo');
                if (btnListo) btnListo.addEventListener('click', () => this.cerrar());
                return;
            }
            if (acc.tipo === 'cerrado') {
                el.innerHTML = `<p class="neg-esperar-msg">${this.escapeHtml(acc.mensaje || 'Negociación cerrada.')}</p>`;
                return;
            }
            if (acc.tipo === 'resumen') {
                el.innerHTML = `<p class="neg-esperar-msg">${this.escapeHtml(acc.mensaje || '')}</p>`;
                return;
            }
            if (acc.tipo === 'esperar') {
                el.innerHTML = this._wrapComposeCard('Esperando respuesta', `<div class="neg-compose-espera">
                    <p>${this.escapeHtml(acc.mensaje || 'Esperando a la otra parte.')}</p>
                    <span class="neg-esperar-hint">La conversación se actualiza sola. Te avisaremos cuando sea tu turno.</span>
                </div>`);
                return;
            }
            if (acc.tipo === 'wizard_contratante') {
                this._renderWizardCompose(acc);
                return;
            }
            if (acc.tipo === 'proponer') {
                this._renderFormProponer(acc);
                return;
            }
            if (acc.tipo === 'responder') {
                this._renderFormResponder(acc);
            }
        }

        _renderWizardCompose(acc) {
            const el = document.getElementById('neg-acciones-wrap');
            this._ensureWizardServicioPrecargado(acc);
            const w = this._loadWizard();
            const campos = this._camposWizardActivos(acc);
            const preguntas = this._preguntasWizard(acc);
            const sugeridos = acc.valores_sugeridos || {};
            const servicioPre = this._servicioPrecargado();

            if (w.pasoIdx >= campos.length) {
                const respuestasFinales = Object.assign({}, w.respuestas);
                if (servicioPre && !respuestasFinales.servicio) {
                    respuestasFinales.servicio = servicioPre;
                }
                el.innerHTML = this._wrapComposeCard('Revisar y enviar', `<div class="neg-compose-stack">
                    ${servicioPre ? `<div class="neg-servicio-precargado"><span class="neg-servicio-precargado-label">Servicio</span><span class="neg-servicio-precargado-valor">${this.escapeHtml(servicioPre)}</span></div>` : ''}
                    <button type="button" class="neg-btn neg-btn-primary neg-btn-block" id="neg-btn-proponer-completa">Enviar todo al profesional</button>
                </div>`);
                document.getElementById('neg-btn-proponer-completa').addEventListener('click', () => this.proponerCompleta(respuestasFinales));
                return;
            }

            const campo = campos[w.pasoIdx];
            const inputType = INPUT_TYPES[campo] || 'text';
            const isTextarea = inputType === 'textarea';
            const valorInicial = this._valorBorrador(campo, w.respuestas[campo] || sugeridos[campo] || '');
            const servicioBanner = (servicioPre && !this._cambiarServicio && campo !== 'servicio')
                ? `<div class="neg-servicio-precargado">
                    <span class="neg-servicio-precargado-label">Servicio</span>
                    <span class="neg-servicio-precargado-valor">${this.escapeHtml(servicioPre)}</span>
                    <button type="button" class="neg-btn-link" id="neg-btn-cambiar-servicio">Modificar</button>
                   </div>`
                : '';
            const catalogoHtml = (campo === 'servicio') ? this._htmlSelectorServicio(campo) : '';
            const otroPlaceholder = campo === 'servicio'
                ? 'Describe el servicio que necesitas…'
                : 'Escribe tu respuesta…';
            const inputHtml = isTextarea
                ? `<textarea id="neg-input-valor" class="neg-compose-input" placeholder="${otroPlaceholder}" rows="2">${this.escapeHtml(valorInicial)}</textarea>`
                : `<input id="neg-input-valor" class="neg-compose-input" type="${inputType}" ${campo === 'precio' ? 'step="0.01" min="0"' : ''} placeholder="${otroPlaceholder}" value="${this.escapeHtml(valorInicial)}" />`;

            const preguntaActual = preguntas[campo] || PREGUNTAS_DEFAULT[campo] || PASO_LABELS[campo] || 'Tu respuesta';
            el.innerHTML = this._wrapComposeCard(preguntaActual, `<div class="neg-compose-stack">
                ${servicioBanner}
                ${catalogoHtml}
                <div class="neg-compose-row">
                    ${inputHtml}
                    <button type="button" class="neg-btn neg-btn-primary neg-btn-send" id="neg-btn-wizard-enviar" aria-label="Enviar respuesta">➤</button>
                </div>
            </div>`);

            if (campo === 'servicio') {
                const profCodigo = (this.data.profesional_codigo || '').trim();
                this._enlazarCatalogoServicio(campo, profCodigo);
            }

            const btnCambiar = document.getElementById('neg-btn-cambiar-servicio');
            if (btnCambiar) {
                btnCambiar.addEventListener('click', () => {
                    this._cambiarServicio = true;
                    this._catalogoAbierto = false;
                    this._lastAccionKey = '';
                    this.renderAcciones();
                });
            }

            this._enlazarGuardadoBorrador(campo);

            const enviar = () => this._wizardEnviarRespuesta(acc, campo, preguntas);
            document.getElementById('neg-btn-wizard-enviar').addEventListener('click', enviar);
            const input = document.getElementById('neg-input-valor');
            if (input) {
                input.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter' && !isTextarea) {
                        e.preventDefault();
                        enviar();
                    }
                });
            }
        }

        _wizardEnviarRespuesta(acc, campo, preguntas) {
            const input = document.getElementById('neg-input-valor');
            const valor = input ? String(input.value || '').trim() : '';
            if (!valor) {
                notify('Escribe una respuesta para continuar.', 'warning');
                return;
            }
            const w = this._loadWizard();
            const campos = this._camposWizardActivos(acc);
            const pregunta = (preguntas || this._preguntasWizard(acc))[campo] || PREGUNTAS_DEFAULT[campo] || '';
            if (!w.historial.some(h => h.tipo === 'pregunta' && h.campo === campo)) {
                w.historial.push({ tipo: 'pregunta', campo, texto: pregunta });
            }
            w.historial.push({ tipo: 'respuesta', campo, texto: valor });
            w.respuestas[campo] = valor;
            w.pasoIdx = campos.indexOf(campo) + 1;
            if (campo === 'servicio') {
                this._cambiarServicio = false;
                this._catalogoAbierto = false;
            }
            delete this._drafts[campo];
            this._saveWizard();
            this._lastAccionKey = '';
            this.render();
            const nextInput = document.getElementById('neg-input-valor');
            if (nextInput) nextInput.focus();
        }

        async proponerCompleta(respuestasPrecargadas) {
            const body = Object.assign({}, respuestasPrecargadas || {});
            const servicioPre = this._servicioPrecargado();
            if (servicioPre && !body.servicio) {
                body.servicio = servicioPre;
            }
            const w = this._loadWizard();
            if (w && w.respuestas) {
                Object.assign(body, w.respuestas);
            }
            const campos = this._camposSolicitante();
            if (!Object.keys(body).length) {
                campos.forEach(campo => {
                    const input = document.querySelector(`[data-neg-campo="${campo}"]`);
                    body[campo] = input ? String(input.value || '').trim() : '';
                });
            }
            for (const campo of campos) {
                if (!String(body[campo] || '').trim()) {
                    notify('Completa todos los campos antes de enviar al profesional.', 'warning');
                    return;
                }
            }
            await this._post('proponer-completa', {
                ...body,
                precio_catalogo: this._precioReferencia || '',
            }, true);
            this._clearWizard();
            this._cambiarServicio = false;
            this._catalogoAbierto = false;
        }

        _renderFormProponer(acc) {
            const el = document.getElementById('neg-acciones-wrap');
            const campo = acc.campo;
            const inputType = INPUT_TYPES[campo] || 'text';
            const isTextarea = inputType === 'textarea';
            const valorInicial = this._valorBorrador(campo, acc.valor_actual || acc.valor_sugerido || '');
            const catalogoHtml = campo === 'servicio' ? this._htmlSelectorServicio(campo) : '';
            const placeholder = campo === 'servicio' ? 'Describe el servicio…' : (campo === 'precio' ? 'Precio en €' : 'Escribe…');
            const hintCatalogo = (campo === 'precio' && acc.precio_desde_catalogo && valorInicial)
                ? `<p class="neg-precio-catalogo-hint">Precio del catálogo: ${this.escapeHtml(String(valorInicial))} €. Confirma o edítalo.</p>`
                : '';
            const inputHtml = isTextarea
                ? `<textarea id="neg-input-valor" class="neg-compose-input" placeholder="${placeholder}" rows="2">${this.escapeHtml(valorInicial)}</textarea>`
                : `<input id="neg-input-valor" class="neg-compose-input" type="${inputType}" ${campo === 'precio' ? 'step="0.01" min="0"' : ''} placeholder="${placeholder}" value="${this.escapeHtml(valorInicial)}" />`;
            let btnLabel = acc.modificar_propia ? 'Actualizar' : (campo === 'precio' ? 'Proponer precio' : 'Enviar');
            if (campo === 'precio' && acc.precio_desde_catalogo && valorInicial) {
                btnLabel = 'Confirmar precio';
            }
            const bloqueoPrecio = campo === 'precio' && this._stripePagoBloqueado();
            const avisoProponerPrecio = bloqueoPrecio
                && this.data.rol === 'profesional' && acc.tipo === 'proponer';
            const avisoHtml = avisoProponerPrecio ? this._htmlAvisoStripeBloqueo() : '';
            const filaProponerHtml = avisoProponerPrecio
                ? ''
                : `<div class="neg-compose-row">
                    ${inputHtml}
                    <button type="button" class="neg-btn neg-btn-primary neg-btn-send" id="neg-btn-proponer">${btnLabel}</button>
                </div>`;
            el.innerHTML = this._wrapComposeCard(
                acc.modificar_propia ? 'Actualizar ' + (PASO_LABELS[campo] || campo).toLowerCase() : ('Indica ' + (PASO_LABELS[campo] || campo).toLowerCase()),
                `<div class="neg-compose-stack">
                ${avisoHtml}
                ${catalogoHtml}
                ${hintCatalogo}
                ${filaProponerHtml}
            </div>`
            );
            if (campo === 'servicio') {
                const profCodigo = (this.data.profesional_codigo || '').trim();
                this._enlazarCatalogoServicio(campo, profCodigo);
            }
            if (!avisoProponerPrecio) {
                this._enlazarGuardadoBorrador(campo);
            }
            this._enlazarStripeEnAcciones();
            const btnProponer = document.getElementById('neg-btn-proponer');
            if (btnProponer) btnProponer.addEventListener('click', () => this.proponer(campo));
        }

        _renderFormResponder(acc) {
            const el = document.getElementById('neg-acciones-wrap');
            const campo = acc.campo;
            const valorActual = acc.valor_actual || '';
            const valorContra = this._valorBorrador(`contra_${campo}`, '');
            const label = PASO_LABELS[campo] || campo;
            const inputType = INPUT_TYPES[campo] || 'text';
            const isTextarea = inputType === 'textarea';
            const bloqueoPrecio = campo === 'precio' && this._stripePagoBloqueado();
            const contraInput = isTextarea
                ? `<textarea id="neg-input-contraoferta" class="neg-compose-input" placeholder="Tu alternativa" rows="2">${this.escapeHtml(valorContra)}</textarea>`
                : `<input id="neg-input-contraoferta" class="neg-compose-input" type="${inputType}" ${campo === 'precio' ? 'step="0.01" min="0"' : ''} placeholder="Tu alternativa" value="${this.escapeHtml(valorContra)}" />`;
            const accionesHtml = bloqueoPrecio
                ? `${this._htmlAvisoStripeBloqueo()}
                   <button type="button" class="neg-btn neg-btn-secondary neg-btn-block" id="neg-btn-contraoferta-toggle">Sugerir otro valor</button>`
                : `<button type="button" class="neg-btn neg-btn-primary neg-btn-block" id="neg-btn-aceptar">Confirmar</button>
                   <button type="button" class="neg-btn neg-btn-secondary neg-btn-block" id="neg-btn-contraoferta-toggle">Sugerir otro valor</button>`;
            el.innerHTML = this._wrapComposeCard('Confirmar ' + label.toLowerCase(), `<div class="neg-compose-stack">
                <div class="neg-respuesta-valor">
                    <span class="neg-respuesta-label">${this.escapeHtml(label)}:</span>
                    <strong>${this.escapeHtml(String(valorActual))}</strong>
                </div>
                <div class="neg-compose-actions">
                    ${accionesHtml}
                </div>
                <div id="neg-contraoferta-form" class="neg-contraoferta-form" style="display:none;">
                    ${contraInput}
                    ${campo === 'observaciones' ? '<textarea id="neg-input-obs-prof" class="neg-compose-input" placeholder="Tus observaciones (opcional)" rows="2"></textarea>' : ''}
                    <button type="button" class="neg-btn neg-btn-warn neg-btn-block" id="neg-btn-contraoferta">Enviar alternativa</button>
                </div>
            </div>`);
            this._enlazarGuardadoBorrador(campo);
            const btnAceptar = document.getElementById('neg-btn-aceptar');
            if (btnAceptar) btnAceptar.addEventListener('click', () => this.aceptar(campo));
            this._enlazarStripeEnAcciones();
            document.getElementById('neg-btn-contraoferta-toggle').addEventListener('click', () => {
                const f = document.getElementById('neg-contraoferta-form');
                if (f) f.style.display = f.style.display === 'none' ? 'block' : 'none';
            });
            document.getElementById('neg-btn-contraoferta').addEventListener('click', () => this.contraoferta(campo));
        }

        _negociacionApiUrl(accion) {
            const contactoId = contactoIdValido(this.contactoId);
            if (!contactoId) return null;
            return apiUrl(`/api/contactos/${contactoId}/negociacion/${accion}`);
        }

        async proponer(campo) {
            const input = document.getElementById('neg-input-valor');
            const valor = input ? String(input.value || '').trim() : '';
            if (!valor) { notify('Introduce un valor para continuar', 'warning'); return; }
            await this._post('proponer', { campo, valor });
        }

        async aceptar(campo) {
            let obs = '';
            const obsEl = document.getElementById('neg-input-obs-prof');
            if (obsEl) obs = obsEl.value.trim();
            await this._post('aceptar', {
                campo, observaciones_profesional: obs,
            });
        }

        async contraoferta(campo) {
            const input = document.getElementById('neg-input-contraoferta');
            const valor = input ? String(input.value || '').trim() : '';
            if (!valor) { notify('Introduce tu alternativa', 'warning'); return; }
            await this._post('contraoferta', { campo, valor });
        }

        async _post(accion, body, limpiarTodosBorradores) {
            const url = this._negociacionApiUrl(accion);
            if (!url) {
                notify('No hay un contacto activo. Cierra y vuelve a abrir la negociación.', 'warning');
                return;
            }
            try {
                const resp = await fetch(url, {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: getAuthHeaders({ 'Content-Type': 'application/json' }),
                    body: JSON.stringify(body),
                });
                let data = {};
                try {
                    data = await resp.json();
                } catch (parseErr) {
                    notify(resp.ok ? 'Respuesta inválida del servidor' : `Error del servidor (${resp.status})`, 'error');
                    return;
                }
                if (data.status !== 'success') {
                    const tipo = data.stripe_pago_no_disponible ? 'warning' : 'error';
                    notify(data.message || `Error en la operación (${resp.status})`, tipo);
                    return;
                }
                this.data = data;
                if (limpiarTodosBorradores) {
                    this._drafts = {};
                } else if (body && body.campo) {
                    delete this._drafts[body.campo];
                    delete this._drafts[`contra_${body.campo}`];
                }
                this._lastAccionKey = '';
                this.render();
                if (this.panel && typeof this.panel.cargarContactosPendientes === 'function') {
                    await this.panel.cargarContactosPendientes();
                }
                if (this.panel && typeof this.panel.renderProfesionales === 'function') {
                    this.panel.renderProfesionales();
                }
                if (this.panel && typeof this.panel.refreshAfterAction === 'function') {
                    await this.panel.refreshAfterAction(['contactos', 'alertas', 'metricas', 'perfil']);
                }
                const cerradoAuto = !!(data.cierre_automatico
                    || data.estado_contacto === 'trabajo_cerrado'
                    || data.ambos_confirmaron_cierre);
                if (cerradoAuto && this.panel && typeof this.panel.cargarPagosApoyoPendientes === 'function') {
                    await this.panel.cargarPagosApoyoPendientes();
                }
                if (this.panel && typeof this.panel.syncAcuerdoFlotante === 'function') {
                    this.panel.syncAcuerdoFlotante(data);
                }
                if (this.panel && typeof this.panel.cargarMisAcuerdos === 'function') {
                    await this.panel.cargarMisAcuerdos();
                }
                setTimeout(() => this.refrescar(true), 400);
            } catch (e) {
                notify('No hemos podido conectar. Comprueba tu conexión e inténtalo de nuevo.', 'error');
            }
        }

        async _cargarCatalogoServicios(codigoProfesional, containerId, inputId, onSelect) {
            const container = document.getElementById(containerId);
            if (!container || !codigoProfesional) return;

            const renderItems = (servicios) => {
                if (!servicios.length) {
                    container.innerHTML = '<p class="neg-catalogo-empty">Este profesional aún no tiene servicios en su catálogo. Usa el campo «Otros».</p>';
                    return;
                }
                container.innerHTML = servicios.map((s, idx) => {
                    const descHtml = this.escapeHtml(s.descripcion || '');
                    const precioHtml = s.precio ? this.escapeHtml(String(s.precio)) : '';
                    return `<button type="button" class="neg-catalogo-item" data-idx="${idx}">
                        <span class="neg-catalogo-desc">${descHtml}</span>
                        ${precioHtml ? `<span class="neg-catalogo-precio">${precioHtml}</span>` : ''}
                    </button>`;
                }).join('');
                container._catalogoItems = servicios;
                container.querySelectorAll('.neg-catalogo-item').forEach(btn => {
                    btn.addEventListener('click', () => {
                        container.querySelectorAll('.neg-catalogo-item').forEach(b => b.classList.remove('selected'));
                        btn.classList.add('selected');
                        const idx = parseInt(btn.getAttribute('data-idx') || '-1', 10);
                        const item = container._catalogoItems[idx];
                        if (typeof onSelect === 'function') {
                            onSelect(item);
                        } else {
                            const input = document.getElementById(inputId);
                            if (input && item) input.value = item.descripcion || '';
                            if (item && item.precio) {
                                this._precioReferencia = String(item.precio).trim();
                            }
                        }
                    });
                });
            };

            if (this._catalogoCache[codigoProfesional]) {
                renderItems(this._catalogoCache[codigoProfesional]);
                return;
            }

            container.innerHTML = '<p class="neg-catalogo-loading">Cargando catálogo…</p>';
            try {
                const resp = await fetch(apiUrl(`/api/aliados/${encodeURIComponent(codigoProfesional)}/catalogo-servicios`), {
                    credentials: 'same-origin',
                    headers: getAuthHeaders(),
                });
                const data = await resp.json();
                const servicios = (data.status === 'success' && Array.isArray(data.servicios))
                    ? data.servicios.filter(s => s.configurado && s.descripcion)
                    : [];
                this._catalogoCache[codigoProfesional] = servicios;
                if (!document.getElementById(containerId)) return;
                renderItems(servicios);
            } catch (e) {
                if (container) {
                    container.innerHTML = '<p class="neg-catalogo-empty">No se pudo cargar el catálogo. Escribe el servicio manualmente.</p>';
                }
            }
        }

        async confirmarCerrarNegociacion() {
            const contactoId = contactoIdValido(this.contactoId);
            if (!contactoId) return;
            const estado = (this.data && this.data.estado_contacto) || '';
            const esAcuerdo = estado === 'acuerdo_alcanzado' || (this.data && this.data.acuerdo_alcanzado);
            if (esAcuerdo && this.data && this.data.yo_confirme_cierre) {
                notify('Ya confirmaste este acuerdo. Esperando a la otra parte.', 'info');
                return;
            }
            const mensaje = esAcuerdo
                ? (estado === 'trabajo_cerrado' || (this.data && this.data.cierre_automatico)
                    ? '¿Confirmas que has revisado el resumen del acuerdo?\n\nEl precio aceptado ya es el importe oficial y el Apoyo RUANA ya se generó.'
                    : '¿Confirmas que has revisado el resumen del acuerdo?\n\nEl precio aceptado es el importe oficial del encargo.')
                : '¿Cerrar esta negociación?\n\nSe finalizará la conversación para ambas partes y el contacto quedará registrado como no concretado.';
            const titulo = esAcuerdo ? 'Confirmar revisión del acuerdo' : 'Cerrar negociación';
            const confirmLabel = esAcuerdo ? 'Sí, confirmado' : 'Sí, cerrar';
            let ok = false;
            if (typeof global.RuanaUI !== 'undefined' && typeof global.RuanaUI.confirm === 'function') {
                ok = await global.RuanaUI.confirm(mensaje, {
                    title: titulo,
                    confirmLabel,
                    cancelLabel: 'Cancelar',
                    zIndex: 20100,
                });
            } else {
                ok = window.confirm(mensaje);
            }
            if (!ok) return;
            const url = this._negociacionApiUrl('cerrar');
            if (!url) {
                notify('No hay un contacto activo. Cierra y vuelve a abrir la negociación.', 'warning');
                return;
            }
            try {
                const resp = await fetch(url, {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: getAuthHeaders({ 'Content-Type': 'application/json' }),
                    body: JSON.stringify({}),
                });
                let data = {};
                try {
                    data = await resp.json();
                } catch (parseErr) {
                    notify(`Error del servidor (${resp.status})`, 'error');
                    return;
                }
                if (data.status === 'success') {
                    this.data = data;
                    this._lastAccionKey = '';
                    this.render();
                    if (this.panel && typeof this.panel.syncAcuerdoFlotante === 'function') {
                        this.panel.syncAcuerdoFlotante(data);
                    }
                    if (this.panel && typeof this.panel.cargarMisAcuerdos === 'function') {
                        await this.panel.cargarMisAcuerdos();
                    }
                    if (this.panel && typeof this.panel.cargarContactosPendientes === 'function') {
                        await this.panel.cargarContactosPendientes();
                    }
                    if (data.cierre_automatico || data.estado_contacto === 'trabajo_cerrado') {
                        if (this.panel && typeof this.panel.cargarPagosApoyoPendientes === 'function') {
                            await this.panel.cargarPagosApoyoPendientes();
                        }
                        if (this.panel && typeof this.panel.refreshAfterAction === 'function') {
                            await this.panel.refreshAfterAction(['contactos', 'alertas', 'metricas']);
                        }
                    } else if (!esAcuerdo) {
                        if (this.panel && typeof this.panel.finalizarContactoCerradoEnUI === 'function') {
                            await this.panel.finalizarContactoCerradoEnUI(contactoId);
                        } else {
                            this.cerrar();
                        }
                    }
                } else {
                    const yaCerrado = /ya está cerrado|estado final/i.test(data.message || '');
                    if (yaCerrado && this.panel && typeof this.panel.finalizarContactoCerradoEnUI === 'function') {
                        await this.panel.finalizarContactoCerradoEnUI(contactoId);
                    } else {
                        notify(data.message || 'No se pudo cerrar la negociación', 'error');
                    }
                }
            } catch (e) {
                notify('No hemos podido conectar. Comprueba tu conexión e inténtalo de nuevo.', 'error');
            }
        }

        escapeHtml(s) {
            if (this.panel && typeof this.panel.escapeHtml === 'function') {
                return this.panel.escapeHtml(s);
            }
            const d = document.createElement('div');
            d.textContent = s;
            return d.innerHTML;
        }
    }

    global.NegociacionGuiada = NegociacionGuiada;
})(typeof window !== 'undefined' ? window : globalThis);
