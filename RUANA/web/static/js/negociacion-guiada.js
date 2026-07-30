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
            const finalizar = document.getElementById('neg-btn-finalizar');
            if (cerrar) cerrar.addEventListener('click', () => this.cerrar());
            if (finalizar) finalizar.addEventListener('click', () => this.finalizarPanel());
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
            this._pollId = setInterval(() => this.refrescar(true), 5000);
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
            } catch (e) {
                if (!silent) console.error(e);
            }
        }

        render() {
            if (!this.data) return;
            this.renderTimeline();
            this.renderResumen();
            this.renderAcciones();
            this.renderAcuerdoFinal();
        }

        renderTimeline() {
            const el = document.getElementById('neg-timeline');
            if (!el) return;
            const eventos = Array.isArray(this.data.eventos) ? this.data.eventos : [];
            if (!eventos.length) {
                el.innerHTML = '<p class="neg-esperar-msg">RUANA guiará el acuerdo paso a paso.</p>';
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
                const badge = `<span class="neg-badge ${estado}">${estado.replace('_', ' ')}</span>`;
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
            const items = (this.data.resumen || []).filter(i => i.valor);
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
                el.innerHTML = '<p class="neg-esperar-msg">Negociación completada. Espera a realizar el servicio para cerrar el contacto.</p>';
                return;
            }
            if (acc.tipo === 'esperar' || acc.tipo === 'resumen') {
                el.innerHTML = `<p class="neg-esperar-msg">${this.escapeHtml(acc.mensaje || 'Esperando a la otra parte.')}</p>`;
                return;
            }
            if (acc.tipo === 'proponer') {
                const campo = acc.campo;
                const inputType = INPUT_TYPES[campo] || 'text';
                const isTextarea = inputType === 'textarea';
                const inputHtml = isTextarea
                    ? `<textarea id="neg-input-valor" placeholder="${this.escapeHtml(acc.label)}"></textarea>`
                    : `<input id="neg-input-valor" type="${inputType}" ${campo === 'precio' ? 'step="0.01" min="0"' : ''} placeholder="${this.escapeHtml(acc.label)}" />`;
                el.innerHTML = `<div class="neg-acciones-form">
                    <label style="width:100%;color:#94a3b8;font-size:0.85rem;">Proponer: ${this.escapeHtml(acc.label)}</label>
                    ${inputHtml}
                    <button type="button" class="neg-btn neg-btn-primary" id="neg-btn-proponer">Proponer</button>
                </div>`;
                document.getElementById('neg-btn-proponer').addEventListener('click', () => this.proponer(campo));
                return;
            }
            if (acc.tipo === 'responder') {
                const campo = acc.campo;
                const valorActual = acc.valor_actual || '';
                el.innerHTML = `<div class="neg-acciones-form" style="flex-direction:column;align-items:stretch;">
                    <p style="margin:0;color:#e2e8f0;">Propuesta de ${acc.propuesto_por === 'solicitante' ? 'contratante' : 'profesional'} — <strong>${this.escapeHtml(acc.label)}</strong>: «${this.escapeHtml(valorActual)}»</p>
                    <div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:8px;">
                        <button type="button" class="neg-btn neg-btn-primary" id="neg-btn-aceptar">Aceptar</button>
                        <button type="button" class="neg-btn neg-btn-warn" id="neg-btn-contraoferta-toggle">Proponer cambio</button>
                    </div>
                    <div id="neg-contraoferta-form" style="display:none;margin-top:10px;">
                        <input id="neg-input-contraoferta" type="${INPUT_TYPES[campo] === 'textarea' ? 'text' : (INPUT_TYPES[campo] || 'text')}" placeholder="Tu contraoferta" value="" />
                        ${campo === 'observaciones' ? '<textarea id="neg-input-obs-prof" placeholder="Tus observaciones (opcional)" style="margin-top:8px;width:100%;"></textarea>' : ''}
                        <button type="button" class="neg-btn neg-btn-warn" id="neg-btn-contraoferta" style="margin-top:8px;">Enviar contraoferta</button>
                    </div>
                </div>`;
                document.getElementById('neg-btn-aceptar').addEventListener('click', () => this.aceptar(campo));
                document.getElementById('neg-btn-contraoferta-toggle').addEventListener('click', () => {
                    const f = document.getElementById('neg-contraoferta-form');
                    if (f) f.style.display = f.style.display === 'none' ? 'block' : 'none';
                });
                document.getElementById('neg-btn-contraoferta').addEventListener('click', () => this.contraoferta(campo));
            }
        }

        async proponer(campo) {
            const input = document.getElementById('neg-input-valor');
            const valor = input ? String(input.value || '').trim() : '';
            if (!valor) { alert('Introduce un valor'); return; }
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
            if (!valor) { alert('Introduce tu contraoferta'); return; }
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
                if (data.completo || data.acuerdo_alcanzado) {
                    if (this.panel && typeof this.panel.cargarContactosPendientes === 'function') {
                        await this.panel.cargarContactosPendientes();
                    }
                }
            } catch (e) {
                alert('Error de conexión');
            }
        }

        async finalizarPanel() {
            if (!this.contactoId) return;
            try {
                const resp = await fetch(`/api/contactos/${this.contactoId}/finalizar-chat`, {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: getAuthHeaders({ 'Content-Type': 'application/json' }),
                    body: JSON.stringify({}),
                });
                const data = await resp.json();
                if (data.status === 'success') {
                    this.cerrar();
                    if (this.panel && typeof this.panel.cargarContactosPendientes === 'function') {
                        await this.panel.cargarContactosPendientes();
                    }
                } else {
                    alert(data.message || 'No se pudo ocultar del panel');
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
