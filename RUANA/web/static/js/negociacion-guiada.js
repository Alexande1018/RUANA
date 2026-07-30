/**
 * Negociación guiada RUANA — sustituye chat libre.
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
        }

        iniciarPolling() {
            this.detenerPolling();
            this._pollId = setInterval(() => this.refrescar(true), 2500);
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
                this.data = data;
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
            this.renderTimeline();
            this.renderResumen();
            this.renderAcciones();
            this.renderAcuerdoFinal();
            this.renderBotonesHeader();
        }

        renderPasoActual() {
            const el = document.getElementById('neg-paso-actual');
            if (!el) return;
            const paso = this.data.paso_actual || (this.data.accion && this.data.accion.campo) || 'servicio';
            const label = PASO_LABELS[paso] || paso;
            const rol = this.data.rol === 'profesional' ? 'Profesional' : 'Contratante';
            el.textContent = `Paso actual: ${label} · Tu rol: ${rol}`;
        }

        renderBotonesHeader() {
            const btnCerrarNeg = document.getElementById('neg-btn-cerrar-negociacion');
            if (!btnCerrarNeg) return;
            const estado = this.data.estado_contacto || '';
            const cerrado = ['cerrado_no_concretado', 'no_concretado', 'trabajo_cerrado', 'acuerdo_alcanzado'].includes(estado)
                || this.data.acuerdo_alcanzado;
            btnCerrarNeg.style.display = cerrado ? 'none' : '';
        }

        renderTimeline() {
            const el = document.getElementById('neg-timeline');
            if (!el) return;
            const eventos = Array.isArray(this.data.eventos) ? this.data.eventos : [];
            if (!eventos.length) {
                el.innerHTML = '<p class="neg-esperar-msg">RUANA os guiará paso a paso hasta alcanzar un acuerdo.</p>';
                return;
            }
            el.innerHTML = eventos.map(ev => {
                const cls = ev.tipo === 'sistema' ? 'neg-evento sistema' : 'neg-evento';
                const fecha = ev.creado_en ? new Date(ev.creado_en).toLocaleString('es-ES') : '';
                return `<div class="${cls}">
                    <div>${this.escapeHtml(ev.mensaje || '')}</div>
                    <div class="neg-evento-meta">${fecha}${ev.emisor_codigo ? ' · ' + this.escapeHtml(ev.emisor_codigo) : ''}</div>
                </div>`;
            }).join('');
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
                <p style="margin-top:12px;color:#94a3b8;font-size:0.9rem;">Cuando se realice el servicio, usa el seguimiento del contacto en tu panel para cerrar el encargo.</p>
            </div>`;
        }

        renderAcciones() {
            const el = document.getElementById('neg-acciones-wrap');
            if (!el || !this.data.accion) return;
            const acc = this.data.accion;

            if (this.data.acuerdo_alcanzado || this.data.estado_contacto === 'acuerdo_alcanzado') {
                el.innerHTML = '<p class="neg-esperar-msg">Negociación completada. Cuando se realice el servicio, indica el resultado desde tu panel.</p>';
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
                el.innerHTML = `<div class="neg-accion-info">
                    <p class="neg-accion-mensaje">${this.escapeHtml(acc.mensaje || 'Esperando a la otra parte.')}</p>
                    <p class="neg-esperar-hint">RUANA actualizará esta pantalla automáticamente en cuanto haya novedades.</p>
                </div>`;
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

        _renderFormProponer(acc) {
            const el = document.getElementById('neg-acciones-wrap');
            const campo = acc.campo;
            const inputType = INPUT_TYPES[campo] || 'text';
            const isTextarea = inputType === 'textarea';
            const catalogoHtml = campo === 'servicio'
                ? '<div id="neg-catalogo-servicios" class="neg-catalogo-list"></div>'
                : '';
            const valorInicial = acc.valor_actual || acc.valor_sugerido || '';
            const inputHtml = isTextarea
                ? `<textarea id="neg-input-valor" placeholder="${this.escapeHtml(acc.label)}">${this.escapeHtml(valorInicial)}</textarea>`
                : `<input id="neg-input-valor" type="${inputType}" ${campo === 'precio' ? 'step="0.01" min="0"' : ''} placeholder="${this.escapeHtml(acc.label)}" value="${this.escapeHtml(valorInicial)}" />`;
            const btnLabel = acc.modificar_propia ? 'Actualizar propuesta' : 'Enviar propuesta';
            el.innerHTML = `<div class="neg-acciones-form neg-acciones-form-servicio">
                <p class="neg-accion-mensaje">${this.escapeHtml(acc.mensaje || '')}</p>
                <label style="width:100%;color:#94a3b8;font-size:0.85rem;">${this.escapeHtml(acc.label)}</label>
                ${catalogoHtml}
                ${inputHtml}
                <button type="button" class="neg-btn neg-btn-primary" id="neg-btn-proponer">${btnLabel}</button>
            </div>`;
            if (campo === 'servicio') {
                const profCodigo = (this.data.profesional_codigo || '').trim();
                if (profCodigo) this._cargarCatalogoServicios(profCodigo, 'neg-catalogo-servicios', 'neg-input-valor');
            }
            document.getElementById('neg-btn-proponer').addEventListener('click', () => this.proponer(campo));
        }

        _renderFormResponder(acc) {
            const el = document.getElementById('neg-acciones-wrap');
            const campo = acc.campo;
            const valorActual = acc.valor_actual || '';
            el.innerHTML = `<div class="neg-acciones-form" style="flex-direction:column;align-items:stretch;">
                <p class="neg-accion-mensaje">${this.escapeHtml(acc.mensaje || '')}</p>
                <div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:8px;">
                    <button type="button" class="neg-btn neg-btn-primary" id="neg-btn-aceptar">Confirmar</button>
                    <button type="button" class="neg-btn neg-btn-warn" id="neg-btn-contraoferta-toggle">Sugerir cambio</button>
                </div>
                <div id="neg-contraoferta-form" style="display:none;margin-top:10px;">
                    <input id="neg-input-contraoferta" type="${INPUT_TYPES[campo] === 'textarea' ? 'text' : (INPUT_TYPES[campo] || 'text')}" placeholder="Tu alternativa" value="" />
                    ${campo === 'observaciones' ? '<textarea id="neg-input-obs-prof" placeholder="Tus observaciones (opcional)" style="margin-top:8px;width:100%;"></textarea>' : ''}
                    <button type="button" class="neg-btn neg-btn-warn" id="neg-btn-contraoferta" style="margin-top:8px;">Enviar alternativa</button>
                </div>
            </div>`;
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

        async _post(url, body) {
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
                this.render();
                if (this.panel && typeof this.panel.cargarContactosPendientes === 'function') {
                    await this.panel.cargarContactosPendientes();
                }
                if (this.panel && typeof this.panel.refreshAfterAction === 'function') {
                    await this.panel.refreshAfterAction(['contactos', 'alertas', 'metricas']);
                }
                setTimeout(() => this.refrescar(true), 400);
            } catch (e) {
                alert('Error de conexión');
            }
        }

        async _cargarCatalogoServicios(codigoProfesional, containerId, inputId) {
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
                        const input = document.getElementById(inputId);
                        if (input && item) input.value = item.descripcion || '';
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
