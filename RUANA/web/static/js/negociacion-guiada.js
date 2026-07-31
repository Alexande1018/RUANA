/**
 * Negociación guiada RUANA — chat conversacional.
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

    class NegociacionGuiada {
        constructor(panel) {
            this.panel = panel;
            this.contactoId = null;
            this.data = null;
            this._pollId = null;
            this._drafts = {};
            this._lastAccionKey = '';
            this._wizard = null;
            this._bindModal();
        }

        _bindModal() {
            const cerrar = document.getElementById('neg-btn-cerrar');
            const cerrarNeg = document.getElementById('neg-btn-cerrar-negociacion');
            if (cerrar) cerrar.addEventListener('click', () => this.cerrar());
            if (cerrarNeg) cerrarNeg.addEventListener('click', () => this.confirmarCerrarNegociacion());
            const overlay = document.getElementById('modal-negociacion-guiada');
            if (overlay) {
                overlay.addEventListener('click', (e) => {
                    if (e.target === overlay) this.cerrar();
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
            this.contactoId = contactoId;
            const modal = document.getElementById('modal-negociacion-guiada');
            const title = document.getElementById('neg-modal-title');
            if (title) title.textContent = tituloExtra || 'Negociación guiada RUANA';
            if (modal) modal.classList.add('show');
            await this.refrescar();
            this.iniciarPolling();
        }

        cerrar() {
            this.detenerPolling();
            const modal = document.getElementById('modal-negociacion-guiada');
            if (modal) modal.classList.remove('show');
            this.contactoId = null;
            this.data = null;
            this._drafts = {};
            this._lastAccionKey = '';
            this._wizard = null;
        }

        _miCodigo() {
            if (!this.data) return '';
            return this.data.rol === 'profesional'
                ? String(this.data.profesional_codigo || '').trim()
                : String(this.data.solicitante_codigo || '').trim();
        }

        _camposSolicitante() {
            if (this.data && Array.isArray(this.data.campos_solicitante)) {
                return this.data.campos_solicitante;
            }
            return ['servicio', 'fecha', 'hora', 'direccion', 'observaciones'];
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
            if (!this.contactoId) return;
            try {
                const resp = await fetch(`/api/contactos/${this.contactoId}/negociacion`, {
                    credentials: 'same-origin',
                    headers: getAuthHeaders(),
                });
                const data = await resp.json();
                if (data.status !== 'success') {
                    if (!silent) alert(data.message || 'No se pudo cargar la negociación');
                    return;
                }
                const prevTipo = this.data && this.data.accion && this.data.accion.tipo;
                this.data = data;
                if (prevTipo === 'wizard_contratante' && data.accion && data.accion.tipo !== 'wizard_contratante') {
                    this._clearWizard();
                }
                this.render();
                const estadoCerrado = ['cerrado_no_concretado', 'no_concretado', 'trabajo_cerrado'].includes(data.estado_contacto || '')
                    || (data.accion && data.accion.tipo === 'cerrado');
                if (estadoCerrado && this.panel && typeof this.panel.finalizarContactoCerradoEnUI === 'function') {
                    await this.panel.finalizarContactoCerradoEnUI(this.contactoId, { cerrarModal: true });
                }
            } catch (e) {
                if (!silent) console.error(e);
            }
        }

        render() {
            if (!this.data) return;
            this.renderPasoActual();
            this.renderEstadoBar();
            this.renderTimeline();
            this.renderResumen();
            this.renderAcciones();
            this.renderAcuerdoFinal();
            this.renderBotonesHeader();
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

        renderBotonesHeader() {
            const btnCerrarNeg = document.getElementById('neg-btn-cerrar-negociacion');
            if (!btnCerrarNeg) return;
            const estado = this.data.estado_contacto || '';
            const cerrado = ['cerrado_no_concretado', 'no_concretado', 'trabajo_cerrado', 'acuerdo_alcanzado'].includes(estado)
                || this.data.acuerdo_alcanzado;
            btnCerrarNeg.style.display = cerrado ? 'none' : '';
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
            if (campo === 'fecha' && valor) {
                try {
                    const d = new Date(valor + 'T12:00:00');
                    return d.toLocaleDateString('es-ES', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' });
                } catch (e) { /* fallthrough */ }
            }
            return valor;
        }

        renderTimeline() {
            const el = document.getElementById('neg-timeline');
            if (!el) return;
            const miCodigo = this._miCodigo();
            const profNombre = this.data.profesional_codigo ? `Profesional ${this.data.profesional_codigo}` : 'Profesional';
            const parts = [];

            const acc = this.data.accion || {};
            if (acc.tipo === 'wizard_contratante') {
                const w = this._loadWizard();
                const preguntas = this._preguntasWizard(acc);
                const campos = this._camposSolicitante();
                w.historial.forEach(item => {
                    if (item.tipo === 'pregunta') {
                        parts.push(this._bubbleHtml('theirs', item.texto, profNombre));
                    } else {
                        parts.push(this._bubbleHtml('mine', this._formatValor(item.campo, item.texto), 'Tú'));
                    }
                });
                if (w.pasoIdx < campos.length) {
                    const campo = campos[w.pasoIdx];
                    const pregunta = preguntas[campo] || PREGUNTAS_DEFAULT[campo] || '';
                    const yaMostrada = w.historial.some(h => h.tipo === 'pregunta' && h.campo === campo);
                    if (!yaMostrada && pregunta) {
                        parts.push(this._bubbleHtml('theirs', pregunta, profNombre));
                    }
                } else if (w.pasoIdx >= campos.length && campos.length) {
                    parts.push(this._bubbleHtml('system', 'Revisa tus respuestas y envía todo al profesional cuando estés listo.'));
                }
            }

            const eventos = Array.isArray(this.data.eventos) ? this.data.eventos : [];
            eventos.forEach(ev => {
                const fecha = ev.creado_en ? new Date(ev.creado_en).toLocaleString('es-ES', { hour: '2-digit', minute: '2-digit', day: 'numeric', month: 'short' }) : '';
                if (ev.tipo === 'sistema') {
                    parts.push(this._bubbleHtml('system', ev.mensaje || '', fecha));
                    return;
                }
                const emisor = String(ev.emisor_codigo || '').trim();
                const esMio = emisor && emisor === miCodigo;
                const meta = fecha + (emisor ? ` · ${emisor}` : '');
                parts.push(this._bubbleHtml(esMio ? 'mine' : 'theirs', ev.mensaje || '', meta));
            });

            if (!parts.length) {
                el.innerHTML = '<p class="neg-chat-empty">La conversación aparecerá aquí.</p>';
            } else {
                el.innerHTML = parts.join('');
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
            const completo = this.data.acuerdo_alcanzado || this.data.estado_contacto === 'acuerdo_alcanzado';
            if (!completo) {
                wrap.style.display = 'none';
                return;
            }
            wrap.style.display = 'block';
            const items = (this.data.resumen || []).filter(i => i.valor && i.campo !== 'observaciones_profesional');
            wrap.innerHTML = `<div class="neg-acuerdo-resumen">
                <h3>Acuerdo alcanzado</h3>
                ${items.map(i => `<p><strong>${this.escapeHtml(i.label)}:</strong> ${this.escapeHtml(String(i.valor))}</p>`).join('')}
                <p class="neg-acuerdo-hint">Cuando se realice el servicio, usa el seguimiento del contacto en tu panel para cerrar el encargo.</p>
            </div>`;
        }

        renderAcciones() {
            const el = document.getElementById('neg-acciones-wrap');
            if (!el || !this.data.accion) return;
            const acc = this.data.accion;
            const accionKey = this._accionKey(acc);

            if (acc.tipo === 'wizard_contratante') {
                this._guardarBorradoresFormulario(null);
            } else if (acc.campo) {
                this._guardarBorradoresFormulario(acc.campo);
            }
            if (this._formularioEnUso() && accionKey === this._lastAccionKey) {
                return;
            }
            this._lastAccionKey = accionKey;

            if (this.data.acuerdo_alcanzado || this.data.estado_contacto === 'acuerdo_alcanzado') {
                el.innerHTML = '<p class="neg-esperar-msg">Negociación completada.</p>';
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
                el.innerHTML = `<div class="neg-compose-espera">
                    <p>${this.escapeHtml(acc.mensaje || 'Esperando a la otra parte.')}</p>
                    <span class="neg-esperar-hint">La pantalla se actualiza sola. Te avisaremos cuando sea tu turno.</span>
                </div>`;
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
            const w = this._loadWizard();
            const campos = this._camposSolicitante();
            const preguntas = this._preguntasWizard(acc);
            const sugeridos = acc.valores_sugeridos || {};

            if (w.pasoIdx >= campos.length) {
                el.innerHTML = `<div class="neg-compose-stack">
                    <button type="button" class="neg-btn neg-btn-primary neg-btn-block" id="neg-btn-proponer-completa">Enviar todo al profesional</button>
                </div>`;
                document.getElementById('neg-btn-proponer-completa').addEventListener('click', () => this.proponerCompleta(w.respuestas));
                return;
            }

            const campo = campos[w.pasoIdx];
            const inputType = INPUT_TYPES[campo] || 'text';
            const isTextarea = inputType === 'textarea';
            const valorInicial = this._valorBorrador(campo, w.respuestas[campo] || sugeridos[campo] || '');
            const catalogoHtml = campo === 'servicio'
                ? '<div id="neg-catalogo-servicios" class="neg-catalogo-list"></div>'
                : '';
            const inputHtml = isTextarea
                ? `<textarea id="neg-input-valor" class="neg-compose-input" placeholder="Escribe tu respuesta…" rows="2">${this.escapeHtml(valorInicial)}</textarea>`
                : `<input id="neg-input-valor" class="neg-compose-input" type="${inputType}" ${campo === 'precio' ? 'step="0.01" min="0"' : ''} placeholder="Escribe tu respuesta…" value="${this.escapeHtml(valorInicial)}" />`;

            el.innerHTML = `<div class="neg-compose-stack">
                ${catalogoHtml}
                <div class="neg-compose-row">
                    ${inputHtml}
                    <button type="button" class="neg-btn neg-btn-primary neg-btn-send" id="neg-btn-wizard-enviar" aria-label="Enviar respuesta">➤</button>
                </div>
            </div>`;

            if (campo === 'servicio') {
                const profCodigo = (this.data.profesional_codigo || '').trim();
                if (profCodigo) this._cargarCatalogoServicios(profCodigo, 'neg-catalogo-servicios', 'neg-input-valor');
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
                alert('Escribe una respuesta para continuar.');
                return;
            }
            const w = this._loadWizard();
            const campos = this._camposSolicitante();
            const pregunta = (preguntas || this._preguntasWizard(acc))[campo] || PREGUNTAS_DEFAULT[campo] || '';
            if (!w.historial.some(h => h.tipo === 'pregunta' && h.campo === campo)) {
                w.historial.push({ tipo: 'pregunta', campo, texto: pregunta });
            }
            w.historial.push({ tipo: 'respuesta', campo, texto: valor });
            w.respuestas[campo] = valor;
            w.pasoIdx = campos.indexOf(campo) + 1;
            delete this._drafts[campo];
            this._saveWizard();
            this._lastAccionKey = '';
            this.render();
            const nextInput = document.getElementById('neg-input-valor');
            if (nextInput) nextInput.focus();
        }

        async proponerCompleta(respuestasPrecargadas) {
            const body = respuestasPrecargadas || {};
            const campos = this._camposSolicitante();
            if (!Object.keys(body).length) {
                campos.forEach(campo => {
                    const input = document.querySelector(`[data-neg-campo="${campo}"]`);
                    body[campo] = input ? String(input.value || '').trim() : '';
                });
            }
            for (const campo of campos) {
                if (!String(body[campo] || '').trim()) {
                    alert('Completa todos los campos antes de enviar al profesional.');
                    return;
                }
            }
            await this._post(`/api/contactos/${this.contactoId}/negociacion/proponer-completa`, body, true);
            this._clearWizard();
        }

        _renderFormProponer(acc) {
            const el = document.getElementById('neg-acciones-wrap');
            const campo = acc.campo;
            const inputType = INPUT_TYPES[campo] || 'text';
            const isTextarea = inputType === 'textarea';
            const valorInicial = this._valorBorrador(campo, acc.valor_actual || acc.valor_sugerido || '');
            const inputHtml = isTextarea
                ? `<textarea id="neg-input-valor" class="neg-compose-input" placeholder="Escribe…" rows="2">${this.escapeHtml(valorInicial)}</textarea>`
                : `<input id="neg-input-valor" class="neg-compose-input" type="${inputType}" ${campo === 'precio' ? 'step="0.01" min="0"' : ''} placeholder="${campo === 'precio' ? 'Precio en €' : 'Escribe…'}" value="${this.escapeHtml(valorInicial)}" />`;
            const btnLabel = acc.modificar_propia ? 'Actualizar' : (campo === 'precio' ? 'Proponer precio' : 'Enviar');
            el.innerHTML = `<div class="neg-compose-stack">
                <div class="neg-compose-row">
                    ${inputHtml}
                    <button type="button" class="neg-btn neg-btn-primary neg-btn-send" id="neg-btn-proponer">${btnLabel}</button>
                </div>
            </div>`;
            this._enlazarGuardadoBorrador(campo);
            document.getElementById('neg-btn-proponer').addEventListener('click', () => this.proponer(campo));
        }

        _renderFormResponder(acc) {
            const el = document.getElementById('neg-acciones-wrap');
            const campo = acc.campo;
            const valorActual = acc.valor_actual || '';
            const valorContra = this._valorBorrador(`contra_${campo}`, '');
            const label = PASO_LABELS[campo] || campo;
            const inputType = INPUT_TYPES[campo] || 'text';
            const isTextarea = inputType === 'textarea';
            const contraInput = isTextarea
                ? `<textarea id="neg-input-contraoferta" class="neg-compose-input" placeholder="Tu alternativa" rows="2">${this.escapeHtml(valorContra)}</textarea>`
                : `<input id="neg-input-contraoferta" class="neg-compose-input" type="${inputType}" ${campo === 'precio' ? 'step="0.01" min="0"' : ''} placeholder="Tu alternativa" value="${this.escapeHtml(valorContra)}" />`;
            el.innerHTML = `<div class="neg-compose-stack">
                <div class="neg-respuesta-valor">
                    <span class="neg-respuesta-label">${this.escapeHtml(label)}:</span>
                    <strong>${this.escapeHtml(String(valorActual))}</strong>
                </div>
                <div class="neg-compose-actions">
                    <button type="button" class="neg-btn neg-btn-primary neg-btn-block" id="neg-btn-aceptar">Confirmar</button>
                    <button type="button" class="neg-btn neg-btn-secondary neg-btn-block" id="neg-btn-contraoferta-toggle">Sugerir otro valor</button>
                </div>
                <div id="neg-contraoferta-form" class="neg-contraoferta-form" style="display:none;">
                    ${contraInput}
                    ${campo === 'observaciones' ? '<textarea id="neg-input-obs-prof" class="neg-compose-input" placeholder="Tus observaciones (opcional)" rows="2"></textarea>' : ''}
                    <button type="button" class="neg-btn neg-btn-warn neg-btn-block" id="neg-btn-contraoferta">Enviar alternativa</button>
                </div>
            </div>`;
            this._enlazarGuardadoBorrador(campo);
            document.getElementById('neg-btn-aceptar').addEventListener('click', () => this.aceptar(campo));
            document.getElementById('neg-btn-contraoferta-toggle').addEventListener('click', () => {
                const f = document.getElementById('neg-contraoferta-form');
                if (f) f.style.display = f.style.display === 'none' ? 'block' : 'none';
            });
            document.getElementById('neg-btn-contraoferta').addEventListener('click', () => this.contraoferta(campo));
        }

        async proponer(campo) {
            const input = document.getElementById('neg-input-valor');
            const valor = input ? String(input.value || '').trim() : '';
            if (!valor) { alert('Introduce un valor para continuar'); return; }
            await this._post(`/api/contactos/${this.contactoId}/negociacion/proponer`, { campo, valor });
        }

        async aceptar(campo) {
            let obs = '';
            const obsEl = document.getElementById('neg-input-obs-prof');
            if (obsEl) obs = obsEl.value.trim();
            await this._post(`/api/contactos/${this.contactoId}/negociacion/aceptar`, {
                campo, observaciones_profesional: obs,
            });
        }

        async contraoferta(campo) {
            const input = document.getElementById('neg-input-contraoferta');
            const valor = input ? String(input.value || '').trim() : '';
            if (!valor) { alert('Introduce tu alternativa'); return; }
            await this._post(`/api/contactos/${this.contactoId}/negociacion/contraoferta`, { campo, valor });
        }

        async _post(url, body, limpiarTodosBorradores) {
            try {
                const resp = await fetch(url, {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: getAuthHeaders({ 'Content-Type': 'application/json' }),
                    body: JSON.stringify(body),
                });
                const data = await resp.json();
                if (data.status !== 'success') {
                    alert(data.message || 'Error en la operación');
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
                    await this.panel.refreshAfterAction(['contactos', 'alertas', 'metricas']);
                }
                setTimeout(() => this.refrescar(true), 400);
            } catch (e) {
                alert('Error de conexión');
            }
        }

        async _cargarCatalogoServicios(codigoProfesional, containerId, inputId, onSelect) {
            const container = document.getElementById(containerId);
            if (!container || !codigoProfesional) return;
            container.innerHTML = '<p class="neg-esperar-msg">Cargando catálogo…</p>';
            try {
                const resp = await fetch(`/api/aliados/${encodeURIComponent(codigoProfesional)}/catalogo-servicios`, {
                    credentials: 'same-origin',
                    headers: getAuthHeaders(),
                });
                const data = await resp.json();
                const servicios = (data.status === 'success' && Array.isArray(data.servicios))
                    ? data.servicios.filter(s => s.configurado && s.descripcion)
                    : [];
                if (!servicios.length) {
                    container.innerHTML = '';
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
                        }
                    });
                });
            } catch (e) {
                container.innerHTML = '';
            }
        }

        async confirmarCerrarNegociacion() {
            if (!this.contactoId) return;
            const mensaje = '¿Cerrar esta negociación?\n\nSe finalizará la conversación para ambas partes y el contacto quedará registrado como no concretado.';
            let ok = false;
            if (typeof global.RuanaUI !== 'undefined' && typeof global.RuanaUI.confirm === 'function') {
                ok = await global.RuanaUI.confirm(mensaje, { title: 'Cerrar negociación', confirmText: 'Sí, cerrar', cancelText: 'Cancelar' });
            } else {
                ok = window.confirm(mensaje);
            }
            if (!ok) return;
            try {
                const resp = await fetch(`/api/contactos/${this.contactoId}/negociacion/cerrar`, {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: getAuthHeaders({ 'Content-Type': 'application/json' }),
                    body: JSON.stringify({}),
                });
                const data = await resp.json();
                const yaCerrado = data.status !== 'success' && /ya está cerrado|estado final/i.test(data.message || '');
                if (data.status === 'success' || yaCerrado) {
                    if (this.panel && typeof this.panel.finalizarContactoCerradoEnUI === 'function') {
                        await this.panel.finalizarContactoCerradoEnUI(this.contactoId);
                    } else {
                        this.cerrar();
                    }
                } else {
                    alert(data.message || 'No se pudo cerrar la negociación');
                }
            } catch (e) {
                alert('Error de conexión');
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
