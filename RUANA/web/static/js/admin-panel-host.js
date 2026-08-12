
/**
 * RUANA - Panel de Administrador
 * Sistema de Autenticación y Control
 */

class AdminAuthenticator {
    constructor() {
        this.setupLoginForm();
        this.checkExistingSession();
    }

    setupLoginForm() {
        const form = document.getElementById('adminLoginForm');
        const codigoInput = document.getElementById('adminLoginCodigo');
        const passwordInput = document.getElementById('adminLoginPassword');
        const errorEl = document.getElementById('adminLoginError');
        const btn = document.getElementById('adminLoginBtn');
        if (!form || !codigoInput) return;
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const codigo = (codigoInput.value || '').trim().toUpperCase();
            const password = (passwordInput?.value || '').trim();
            if (!codigo) {
                if (errorEl) { errorEl.textContent = 'Introduce el identificador de administrador'; errorEl.style.display = 'block'; }
                return;
            }
            if (!password) {
                if (errorEl) { errorEl.textContent = 'Introduce la contraseña'; errorEl.style.display = 'block'; }
                return;
            }
            if (btn) btn.disabled = true;
            if (errorEl) errorEl.style.display = 'none';
            try {
                const r = await fetch('/api/admin/validar', {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ codigo, password })
                });
                const data = await r.json().catch(() => ({}));
                if (r.ok && data.status === 'success') {
                    if (data.session_id) sessionStorage.setItem('admin_session_id', data.session_id);
                    document.getElementById('adminLoginModal').classList.add('hidden');
                    setTimeout(() => new AdminPanel(), 100);
                } else {
                    if (errorEl) { errorEl.textContent = data.message || 'Código no válido'; errorEl.style.display = 'block'; }
                }
            } catch (err) {
                if (errorEl) { errorEl.textContent = 'Error de conexión'; errorEl.style.display = 'block'; }
            } finally {
                if (btn) btn.disabled = false;
            }
        });
    }

    checkExistingSession() {
        const sessionId = sessionStorage.getItem('admin_session_id');
        if (!sessionId) {
            document.getElementById('adminLoginModal').classList.remove('hidden');
            return;
        }
        const h = { 'X-Ruana-Session-Id': sessionId };
        fetch('/api/admin/me', { method: 'GET', credentials: 'same-origin', headers: h })
            .then(resp => {
                if (resp.ok) {
                    document.getElementById('adminLoginModal').classList.add('hidden');
                    setTimeout(() => new AdminPanel(), 100);
                } else {
                    sessionStorage.removeItem('admin_session_id');
                    document.getElementById('adminLoginModal').classList.remove('hidden');
                }
            })
            .catch(() => {
                document.getElementById('adminLoginModal').classList.remove('hidden');
            });
    }

    static getAdminAuthHeaders(extra) {
        const sessionId = sessionStorage.getItem('admin_session_id');
        const h = { ...(extra || {}) };
        const skipContentType = Boolean(h._skipContentType);
        delete h._skipContentType;
        if (!skipContentType && !h['Content-Type']) h['Content-Type'] = 'application/json';
        if (sessionId) h['X-Ruana-Session-Id'] = sessionId;
        return h;
    }
}

class AdminPanel {
    constructor() {
        this.filtroActual = 'todos';
        this._aliadosData = [];
        this.aliadosNivel = 'cps';
        this.aliadosCPSeleccionado = null;
        this.aliadosGrupoSeleccionado = null;
        this.aliadosGrupoNombreSeleccionado = null;
        this._conversacionesList = [];
        this._conversacionesHasMore = false;
        this._conversacionesOffset = 0;
        this._centroComunicacion = [];
        this._centroComunicacionActiva = null;
        this._campanasInvitacion = [];
        this._referidosTree = null;
        this._referidosModoBosque = true;
        window._ruanaAdminPanel = this;
        this.init();
    }

    init() {
        /**
         * Consulta la API real para obtener resumen administrativo.
         * En esta fase, el panel admin sólo refleja datos reales.
         */
        this.cargarDesdeApi();
        this.setupEventListeners();
    }

    async cargarDesdeApi() {
        const mod = this._resumenModule();
        if (mod && typeof mod.cargarDesdeApi === 'function') {
            return mod.cargarDesdeApi(this);
        }
    }

    async cargarChatsFallback() {
        const mod = this._resumenModule();
        if (mod && typeof mod.cargarChatsFallback === 'function') {
            return mod.cargarChatsFallback(this);
        }
    }

    applyPermisosUI(permisos) {
        const puedeEscribir = Array.isArray(permisos) && (permisos.includes('escribir') || permisos.includes('configurar'));
        const container = document.querySelector('.acciones-admin');
        if (container) {
            container.classList.toggle('solo-lectura', !puedeEscribir);
        }
        document.querySelectorAll('.btn-admin-action[data-action]').forEach(btn => {
            btn.disabled = !puedeEscribir;
        });
        document.querySelectorAll('.btn-activar-pendiente').forEach(btn => {
            btn.disabled = !puedeEscribir;
        });
        const readonlyBadge = document.getElementById('admin-readonly-badge');
        if (readonlyBadge) readonlyBadge.style.display = puedeEscribir ? 'none' : 'inline';
    }

    _adminSessionExpired() {
        sessionStorage.removeItem('admin_session_id');
        window.location.replace('/admin');
    }

    /** Fachada Campamento Base → RuanaAdminModules.resumen */
    _resumenModule() {
        return (typeof RuanaAdminModules !== 'undefined' && RuanaAdminModules.resumen) || null;
    }

    /** Fachada Campamento Base → RuanaAdminModules.operaciones */
    _operacionesModule() {
        return (typeof RuanaAdminModules !== 'undefined' && RuanaAdminModules.operaciones) || null;
    }

    /** Fachada Campamento Base → RuanaAdminModules.red */
    _redModule() {
        return (typeof RuanaAdminModules !== 'undefined' && RuanaAdminModules.red) || null;
    }

    /** Fachada Campamento Base → RuanaAdminModules.sistema */
    _sistemaModule() {
        return (typeof RuanaAdminModules !== 'undefined' && RuanaAdminModules.sistema) || null;
    }

    renderEstadoGlobal(data) {
        const mod = this._resumenModule();
        if (mod && typeof mod.renderEstadoGlobal === 'function') {
            return mod.renderEstadoGlobal(data);
        }
    }

    renderMovimientoError(message) {
        const mod = this._resumenModule();
        if (mod && typeof mod.renderMovimientoError === 'function') {
            return mod.renderMovimientoError(message);
        }
    }

    renderMovimiento(data) {
        const mod = this._resumenModule();
        if (mod && typeof mod.renderMovimiento === 'function') {
            return mod.renderMovimiento(this, data);
        }
    }

    renderMetricas(data) {
        const mod = this._resumenModule();
        if (mod && typeof mod.renderMetricas === 'function') {
            return mod.renderMetricas(data);
        }
    }

    setupEventListeners() {
        const mod = this._resumenModule();
        if (mod && typeof mod.setupEventListeners === 'function') {
            return mod.setupEventListeners(this);
        }
    }

    async toggleDesglosePorHora(mostrar) {
        const mod = this._resumenModule();
        if (mod && typeof mod.toggleDesglosePorHora === 'function') {
            return mod.toggleDesglosePorHora(this, mostrar);
        }
    }

    renderInvitacionesRecientes(invitaciones) {
        const mod = this._sistemaModule();
        if (mod && typeof mod.renderInvitacionesRecientes === 'function') {
            return mod.renderInvitacionesRecientes(this, invitaciones);
        }
    }

    renderCampanasInvitacion(campanas) {
        const mod = this._sistemaModule();
        if (mod && typeof mod.renderCampanasInvitacion === 'function') {
            return mod.renderCampanasInvitacion(this, campanas);
        }
    }

    async cargarCampanasInvitacion() {
        const mod = this._sistemaModule();
        if (mod && typeof mod.cargarCampanasInvitacion === 'function') {
            return mod.cargarCampanasInvitacion(this);
        }
    }

    buildCampanaRegistroUrl(codigo) {
        const mod = this._sistemaModule();
        if (mod && typeof mod.buildCampanaRegistroUrl === 'function') {
            return mod.buildCampanaRegistroUrl(this, codigo);
        }
    }

    buildCampanaQrUrl(registroUrl) {
        const mod = this._sistemaModule();
        if (mod && typeof mod.buildCampanaQrUrl === 'function') {
            return mod.buildCampanaQrUrl(this, registroUrl);
        }
    }

    verDetalleCampanaInvitacion(codigo) {
        const mod = this._sistemaModule();
        if (mod && typeof mod.verDetalleCampanaInvitacion === 'function') {
            return mod.verDetalleCampanaInvitacion(this, codigo);
        }
    }

    async desactivarCampanaInvitacion(codigo) {
        const mod = this._sistemaModule();
        if (mod && typeof mod.desactivarCampanaInvitacion === 'function') {
            return mod.desactivarCampanaInvitacion(this, codigo);
        }
    }

    showToast(message, type = 'success') {
        if (typeof RuanaUI !== 'undefined') {
            if (type === 'error') {
                RuanaUI.error('', message);
            } else if (type === 'warning') {
                RuanaUI.warning('', message);
            } else {
                RuanaUI.success(message);
            }
            return;
        }
        const container = document.getElementById('adminToastContainer');
        if (!container) return;
        const toast = document.createElement('div');
        toast.className = `admin-toast ${type}`;
        toast.textContent = message;
        container.appendChild(toast);
        setTimeout(() => { toast.remove(); }, 4000);
    }

    getAuthHeaders() {
        return Object.assign(
            { 'Content-Type': 'application/json' },
            AdminAuthenticator.getAdminAuthHeaders()
        );
    }

    setupAdminActionButtons() {
        const self = this;
        document.querySelectorAll('.btn-admin-action[data-action]').forEach(btn => {
            btn.addEventListener('click', function() {
                const action = this.getAttribute('data-action');
                if (action === 'crear-campana-invitacion') self.accionCrearCampanaInvitacion();
                else if (action === 'crear-codigo-aliado') self.accionCrearCodigoAliado();
                else if (action === 'pausar-aliado') self.accionPausarAliado();
                else if (action === 'forzar-suplencia') self.accionForzarSuplencia();
                else if (action === 'cerrar-oficio') self.accionCerrarOficio();
                else if (action === 'abrir-plaza') self.accionAbrirPlaza();
                else if (action === 'generar-reporte') self.accionGenerarReporte();
                else if (action === 'editar-metodos-pago') self.accionEditarMetodosPago();
                else if (action === 'cambiar-reglas') self.accionCambiarReglas();
            });
        });
        const campanasTbody = document.getElementById('admin-campanas-invitacion-tbody');
        if (campanasTbody) {
            campanasTbody.addEventListener('click', (event) => {
                const target = event.target && event.target.closest ? event.target : null;
                const btnVer = target ? target.closest('.btn-ver-campana') : null;
                if (btnVer) {
                    this.verDetalleCampanaInvitacion(btnVer.getAttribute('data-codigo') || '');
                    return;
                }
                const btn = target ? target.closest('.btn-desactivar-campana') : null;
                if (btn) this.desactivarCampanaInvitacion(btn.getAttribute('data-codigo') || '');
            });
        }
        this._setupModalAccionAdmin();
    }

    _setupModalAccionAdmin() {
        const modal = document.getElementById('modal-accion-admin');
        const body = document.getElementById('modal-accion-body');
        const title = document.getElementById('modal-accion-title');
        const btnCancel = document.getElementById('modal-accion-cancelar');
        const btnConfirm = document.getElementById('modal-accion-confirmar');
        if (!modal || !body || !btnCancel || !btnConfirm) return;
        btnCancel.addEventListener('click', () => this._cerrarModalAccion());
        btnConfirm.addEventListener('click', () => this._onConfirmarModalAccion());
        this._modalAccion = { step: 1, config: null, payload: null };
    }

    _abrirModalAccionAdmin(config) {
        this._modalAccion = { step: 1, config, payload: null };
        const modal = document.getElementById('modal-accion-admin');
        const title = document.getElementById('modal-accion-title');
        const body = document.getElementById('modal-accion-body');
        const btnConfirm = document.getElementById('modal-accion-confirmar');
        if (title) title.textContent = config.title;
        if (body) body.innerHTML = config.bodyHtml;
        if (btnConfirm) btnConfirm.textContent = 'Continuar';
        if (modal) {
            modal.style.display = 'flex';
            modal.style.alignItems = 'center';
            modal.style.justifyContent = 'center';
        }
        if (typeof config.onShow === 'function') {
            setTimeout(() => config.onShow(body), 0);
        }
    }

    _cerrarModalAccion() {
        const modal = document.getElementById('modal-accion-admin');
        if (modal) modal.style.display = 'none';
        this._modalAccion = { step: 1, config: null, payload: null };
    }

    async _onConfirmarModalAccion() {
        const { step, config, payload } = this._modalAccion || {};
        if (!config) return;
        if (step === 1) {
            const payload = config.getPayload ? config.getPayload() : null;
            const error = config.validate ? config.validate(payload) : null;
            if (error) { this.showToast(error, 'error'); return; }
            this._modalAccion.payload = payload;
            this._modalAccion.step = 2;
            const body = document.getElementById('modal-accion-body');
            const btnConfirm = document.getElementById('modal-accion-confirmar');
            if (body && config.getConfirmSummary) body.innerHTML = '<p class="modal-accion-resumen" style="color:#ccc; line-height:1.5;">' + config.getConfirmSummary(payload) + '</p>';
            if (btnConfirm) btnConfirm.textContent = 'Confirmar ejecución';
            return;
        }
        if (step === 2 && config.execute) {
            const btnConfirm = document.getElementById('modal-accion-confirmar');
            if (btnConfirm) btnConfirm.disabled = true;
            try {
                await config.execute(this._modalAccion.payload);
            } finally {
                if (btnConfirm) btnConfirm.disabled = false;
            }
            this._cerrarModalAccion();
        }
    }

    accionCrearCampanaInvitacion() {
        const mod = this._sistemaModule();
        if (mod && typeof mod.accionCrearCampanaInvitacion === 'function') {
            return mod.accionCrearCampanaInvitacion(this);
        }
    }

    renderCampanaInvitacionCreada(data) {
        const mod = this._sistemaModule();
        if (mod && typeof mod.renderCampanaInvitacionCreada === 'function') {
            return mod.renderCampanaInvitacionCreada(this, data);
        }
    }

    accionCrearCodigoAliado() {
        const mod = this._sistemaModule();
        if (mod && typeof mod.accionCrearCodigoAliado === 'function') {
            return mod.accionCrearCodigoAliado(this);
        }
    }

    renderCodigoAliadoCreado(codigo) {
        const mod = this._sistemaModule();
        if (mod && typeof mod.renderCodigoAliadoCreado === 'function') {
            return mod.renderCodigoAliadoCreado(this, codigo);
        }
    }

    accionPausarAliado() {
        const mod = this._redModule();
        if (mod && typeof mod.accionPausarAliado === 'function') {
            return mod.accionPausarAliado(this);
        }
    }

    accionForzarSuplencia() {
        const mod = this._sistemaModule();
        if (mod && typeof mod.accionForzarSuplencia === 'function') {
            return mod.accionForzarSuplencia(this);
        }
    }

    accionCerrarOficio() {
        const mod = this._redModule();
        if (mod && typeof mod.accionCerrarOficio === 'function') {
            return mod.accionCerrarOficio(this);
        }
    }

    accionAbrirPlaza() {
        const mod = this._sistemaModule();
        if (mod && typeof mod.accionAbrirPlaza === 'function') {
            return mod.accionAbrirPlaza(this);
        }
    }

    async accionGenerarReporte() {
        const mod = this._sistemaModule();
        if (mod && typeof mod.accionGenerarReporte === 'function') {
            return mod.accionGenerarReporte(this);
        }
    }

    accionCambiarReglas() {
        const mod = this._sistemaModule();
        if (mod && typeof mod.accionCambiarReglas === 'function') {
            return mod.accionCambiarReglas(this);
        }
    }

    renderMetodosPago(metodos) {
        const mod = this._sistemaModule();
        if (mod && typeof mod.renderMetodosPago === 'function') {
            return mod.renderMetodosPago(this, metodos);
        }
    }

    accionEditarMetodosPago() {
        const mod = this._sistemaModule();
        if (mod && typeof mod.accionEditarMetodosPago === 'function') {
            return mod.accionEditarMetodosPago(this);
        }
    }

    async logout() {
        try {
            await fetch('/api/admin/logout', {
                method: 'POST',
                credentials: 'same-origin',
                headers: AdminAuthenticator.getAdminAuthHeaders()
            });
        } catch (_) {}
        sessionStorage.removeItem('admin_session_id');
        delete window._ruanaAdminPanel;
        window.location.href = '/admin';
    }

    openChangePasswordModal() {
        const modal = document.getElementById('adminChangePasswordModal');
        const errorEl = document.getElementById('adminChangePasswordError');
        const successEl = document.getElementById('adminChangePasswordSuccess');
        ['adminCurrentPassword', 'adminNewPassword', 'adminConfirmPassword'].forEach((id) => {
            const input = document.getElementById(id);
            if (input) input.value = '';
        });
        if (errorEl) errorEl.style.display = 'none';
        if (successEl) successEl.style.display = 'none';
        if (modal) modal.classList.remove('hidden');
    }

    closeChangePasswordModal() {
        const modal = document.getElementById('adminChangePasswordModal');
        if (modal) modal.classList.add('hidden');
    }

    setupChangePasswordForm() {
        const form = document.getElementById('adminChangePasswordForm');
        const cancelBtn = document.getElementById('adminChangePasswordCancel');
        const errorEl = document.getElementById('adminChangePasswordError');
        const successEl = document.getElementById('adminChangePasswordSuccess');
        const submitBtn = document.getElementById('adminChangePasswordBtn');
        if (cancelBtn) {
            cancelBtn.addEventListener('click', () => this.closeChangePasswordModal());
        }
        if (!form) return;
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const currentPassword = (document.getElementById('adminCurrentPassword')?.value || '').trim();
            const newPassword = (document.getElementById('adminNewPassword')?.value || '').trim();
            const confirmPassword = (document.getElementById('adminConfirmPassword')?.value || '').trim();
            if (errorEl) errorEl.style.display = 'none';
            if (successEl) successEl.style.display = 'none';
            if (!currentPassword || !newPassword || !confirmPassword) {
                if (errorEl) {
                    errorEl.textContent = 'Completa todos los campos';
                    errorEl.style.display = 'block';
                }
                return;
            }
            if (newPassword !== confirmPassword) {
                if (errorEl) {
                    errorEl.textContent = 'La confirmación no coincide con la nueva contraseña';
                    errorEl.style.display = 'block';
                }
                return;
            }
            if (submitBtn) submitBtn.disabled = true;
            try {
                const r = await fetch('/api/admin/cambiar-contraseña', {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: this.getAuthHeaders(),
                    body: JSON.stringify({
                        contraseña_actual: currentPassword,
                        contraseña_nueva: newPassword,
                        contraseña_confirmacion: confirmPassword
                    })
                });
                const data = await r.json().catch(() => ({}));
                if (r.ok && data.status === 'success') {
                    if (successEl) {
                        successEl.textContent = data.message || 'Contraseña actualizada';
                        successEl.style.display = 'block';
                    }
                    setTimeout(() => this.closeChangePasswordModal(), 1500);
                } else {
                    if (r.status === 401) {
                        this._adminSessionExpired();
                        return;
                    }
                    if (errorEl) {
                        errorEl.textContent = data.message || 'No se pudo cambiar la contraseña';
                        errorEl.style.display = 'block';
                    }
                }
            } catch (_) {
                if (errorEl) {
                    errorEl.textContent = 'Error de conexión';
                    errorEl.style.display = 'block';
                }
            } finally {
                if (submitBtn) submitBtn.disabled = false;
            }
        });
    }

    renderSolicitudesAdmin(solicitudes) {
        const mod = this._sistemaModule();
        if (mod && typeof mod.renderSolicitudesAdmin === 'function') {
            return mod.renderSolicitudesAdmin(this, solicitudes);
        }
    }

    async cargarSolicitudesAdminConFiltros() {
        const mod = this._sistemaModule();
        if (mod && typeof mod.cargarSolicitudesAdminConFiltros === 'function') {
            return mod.cargarSolicitudesAdminConFiltros(this);
        }
    }

    async marcarSolicitudAtendidaAdmin(solicitudId, tr) {
        const mod = this._sistemaModule();
        if (mod && typeof mod.marcarSolicitudAtendidaAdmin === 'function') {
            return mod.marcarSolicitudAtendidaAdmin(this, solicitudId, tr);
        }
    }

    renderConflictosPago(conflictos) {
        const mod = this._operacionesModule();
        if (mod && typeof mod.renderConflictosPago === 'function') {
            return mod.renderConflictosPago(this, conflictos);
        }
    }

    renderPagosApoyo(pagos) {
        const mod = this._operacionesModule();
        if (mod && typeof mod.renderPagosApoyo === 'function') {
            return mod.renderPagosApoyo(this, pagos);
        }
    }

    renderPagosEnRevision(pagos) {
        const mod = this._operacionesModule();
        if (mod && typeof mod.renderPagosEnRevision === 'function') {
            return mod.renderPagosEnRevision(this, pagos);
        }
    }

    buildAdminDocumentLink(storedUrl, label) {
        const mod = this._operacionesModule();
        if (mod && typeof mod.buildAdminDocumentLink === 'function') {
            return mod.buildAdminDocumentLink(this, storedUrl, label);
        }
    }

    async abrirDocumentoAdmin(storedUrl) {
        const mod = this._operacionesModule();
        if (mod && typeof mod.abrirDocumentoAdmin === 'function') {
            return mod.abrirDocumentoAdmin(this, storedUrl);
        }
    }

    abrirModalRechazarPago(contactoId) {
        const mod = this._operacionesModule();
        if (mod && typeof mod.abrirModalRechazarPago === 'function') {
            return mod.abrirModalRechazarPago(this, contactoId);
        }
    }

    async confirmarRechazarPago() {
        const mod = this._operacionesModule();
        if (mod && typeof mod.confirmarRechazarPago === 'function') {
            return mod.confirmarRechazarPago(this);
        }
    }

    async cambiarEstadoPagoContacto(contactoId, nuevoEstado, rowEl) {
        const mod = this._operacionesModule();
        if (mod && typeof mod.cambiarEstadoPagoContacto === 'function') {
            return mod.cambiarEstadoPagoContacto(this, contactoId, nuevoEstado, rowEl);
        }
    }

    async abrirModalDetalleConflicto(conflictId, rowEl) {
        const mod = this._operacionesModule();
        if (mod && typeof mod.abrirModalDetalleConflicto === 'function') {
            return mod.abrirModalDetalleConflicto(this, conflictId, rowEl);
        }
    }

    async resolverConflictoDecision(decision) {
        const mod = this._operacionesModule();
        if (mod && typeof mod.resolverConflictoDecision === 'function') {
            return mod.resolverConflictoDecision(this, decision);
        }
    }

    abrirModalResolverConflicto(contactoId, rowEl) {
        const mod = this._operacionesModule();
        if (mod && typeof mod.abrirModalResolverConflicto === 'function') {
            return mod.abrirModalResolverConflicto(this, contactoId, rowEl);
        }
    }

    async confirmarResolverConflicto() {
        const mod = this._operacionesModule();
        if (mod && typeof mod.confirmarResolverConflicto === 'function') {
            return mod.confirmarResolverConflicto(this);
        }
    }

    renderPendientesValidacion(aliados) {
        const mod = this._redModule();
        if (mod && typeof mod.renderPendientesValidacion === 'function') {
            return mod.renderPendientesValidacion(this, aliados);
        }
    }

    renderAliadosEliminados(aliados) {
        const mod = this._redModule();
        if (mod && typeof mod.renderAliadosEliminados === 'function') {
            return mod.renderAliadosEliminados(this, aliados);
        }
    }

    async activarAliadoPendiente(id, rowEl) {
        const mod = this._redModule();
        if (mod && typeof mod.activarAliadoPendiente === 'function') {
            return mod.activarAliadoPendiente(this, id, rowEl);
        }
    }

    async rechazarAliadoPendiente(codigo, rowEl) {
        const mod = this._redModule();
        if (mod && typeof mod.rechazarAliadoPendiente === 'function') {
            return mod.rechazarAliadoPendiente(this, codigo, rowEl);
        }
    }

    esAliadoPlaceholder(a) {
        const mod = this._redModule();
        if (mod && typeof mod.esAliadoPlaceholder === 'function') {
            return mod.esAliadoPlaceholder(this, a);
        }
    }

    /**
     * Clave del grupo de red para la jerarquía CP → Grupo → Tarjetas.
     * Usa grupo_id cuando existe; aliados sin grupo van a una bandeja común.
     */
    getClaveGrupoRed(a) {
        const mod = this._redModule();
        if (mod && typeof mod.getClaveGrupoRed === 'function') {
            return mod.getClaveGrupoRed(this, a);
        }
    }

    /**
     * Etiqueta visible del grupo de red (nombre, o #id, o «Sin grupo»).
     */
    getNombreGrupoRed(a) {
        const mod = this._redModule();
        if (mod && typeof mod.getNombreGrupoRed === 'function') {
            return mod.getNombreGrupoRed(this, a);
        }
    }

    getGrupoTerritorialLabel(aliado) {
        const mod = this._redModule();
        if (mod && typeof mod.getGrupoTerritorialLabel === 'function') {
            return mod.getGrupoTerritorialLabel(this, aliado);
        }
    }

    normalizarCpAliado(a) {
        const mod = this._redModule();
        if (mod && typeof mod.normalizarCpAliado === 'function') {
            return mod.normalizarCpAliado(this, a);
        }
    }

    renderAliadosJerarquia() {
        const mod = this._redModule();
        if (mod && typeof mod.renderAliadosJerarquia === 'function') {
            return mod.renderAliadosJerarquia(this);
        }
    }

    renderAliadosNivel1() {
        const mod = this._redModule();
        if (mod && typeof mod.renderAliadosNivel1 === 'function') {
            return mod.renderAliadosNivel1(this);
        }
    }

    renderAliadosNivel2() {
        const mod = this._redModule();
        if (mod && typeof mod.renderAliadosNivel2 === 'function') {
            return mod.renderAliadosNivel2(this);
        }
    }

    renderAliadosNivel3() {
        const mod = this._redModule();
        if (mod && typeof mod.renderAliadosNivel3 === 'function') {
            return mod.renderAliadosNivel3(this);
        }
    }

    renderAliados(aliadosData) {
        const mod = this._redModule();
        if (mod && typeof mod.renderAliados === 'function') {
            return mod.renderAliados(this, aliadosData);
        }
    }

    abrirCatalogoServiciosModal(aliado) {
        const mod = this._redModule();
        if (mod && typeof mod.abrirCatalogoServiciosModal === 'function') {
            return mod.abrirCatalogoServiciosModal(this, aliado);
        }
    }

    cerrarCatalogoServiciosModal() {
        const modal = document.getElementById('aliadoCatalogoModal');
        if (modal) modal.classList.add('hidden');
    }

    abrirLinajeDrawer(aliado) {
        const mod = this._redModule();
        if (mod && typeof mod.abrirLinajeDrawer === 'function') {
            return mod.abrirLinajeDrawer(this, aliado);
        }
    }

    _linajeCardHtml(nodo) {
        const nombre = this.escapeHtml(nodo.nombre || '(sin nombre)');
        const codigo = this.escapeHtml(nodo.codigo || '');
        const oficio = this.escapeHtml(nodo.oficio || '—');
        const zona = this.escapeHtml(nodo.zona || nodo.codigo_postal || '—');
        const hijos = nodo.referidos_count != null ? nodo.referidos_count : (nodo.hijos_directos_count || 0);
        return '<div class="linaje-card" data-codigo="' + codigo + '">' +
            '<div class="nombre">' + nombre + '</div>' +
            '<div class="sub">' + codigo + ' · ' + oficio + ' · ' + zona + ' · ' + hijos + ' hijos</div>' +
            '</div>';
    }

    cerrarLinajeDrawer() {
        const overlay = document.getElementById('linaje-drawer-overlay');
        if (!overlay) return;
        overlay.classList.remove('show');
        overlay.setAttribute('aria-hidden', 'true');
    }

    abrirModalDetalle(aliado) {
        const mod = this._redModule();
        if (mod && typeof mod.abrirModalDetalle === 'function') {
            return mod.abrirModalDetalle(this, aliado);
        }
    }

    cerrarModalDetalle() {
        const modal = document.getElementById('aliadoDetalleModal');
        if (modal) modal.classList.add('hidden');
        this._aliadoDetalleActual = null;
    }

    async confirmarEliminarPerfil() {
        const mod = this._redModule();
        if (mod && typeof mod.confirmarEliminarPerfil === 'function') {
            return mod.confirmarEliminarPerfil(this);
        }
    }

    confirmarPausa(aliado) {
        const mod = this._redModule();
        if (mod && typeof mod.confirmarPausa === 'function') {
            return mod.confirmarPausa(this, aliado);
        }
    }

    renderEventos(eventosData) {
        const mod = this._sistemaModule();
        if (mod && typeof mod.renderEventos === 'function') {
            return mod.renderEventos(this, eventosData);
        }
    }

    formatearHora(timestamp) {
        const mod = this._resumenModule();
        if (mod && typeof mod.formatearHora === 'function') {
            return mod.formatearHora(this, timestamp);
        }
    }

    renderConversaciones(conversaciones) {
        const mod = this._resumenModule();
        if (mod && typeof mod.renderConversaciones === 'function') {
            return mod.renderConversaciones(this, conversaciones);
        }
    }

    appendConversacionRow(tbody, c) {
        const mod = this._resumenModule();
        if (mod && typeof mod.appendConversacionRow === 'function') {
            return mod.appendConversacionRow(this, tbody, c);
        }
    }

    updateConversacionesPaginationUI() {
        const mod = this._resumenModule();
        if (mod && typeof mod.updateConversacionesPaginationUI === 'function') {
            return mod.updateConversacionesPaginationUI(this);
        }
    }

    async loadMoreConversaciones() {
        const mod = this._resumenModule();
        if (mod && typeof mod.loadMoreConversaciones === 'function') {
            return mod.loadMoreConversaciones(this);
        }
    }

    mostrarMenosConversaciones() {
        const mod = this._resumenModule();
        if (mod && typeof mod.mostrarMenosConversaciones === 'function') {
            return mod.mostrarMenosConversaciones(this);
        }
    }

    async cargarCentroComunicacionAdmin() {
        const mod = this._operacionesModule();
        if (mod && typeof mod.cargarCentroComunicacionAdmin === 'function') {
            return mod.cargarCentroComunicacionAdmin(this);
        }
    }

    renderCentroComunicacionAdmin(conversaciones) {
        const mod = this._operacionesModule();
        if (mod && typeof mod.renderCentroComunicacionAdmin === 'function') {
            return mod.renderCentroComunicacionAdmin(this, conversaciones);
        }
    }

    async abrirModalCentroComunicacionAdmin(conv) {
        const mod = this._operacionesModule();
        if (mod && typeof mod.abrirModalCentroComunicacionAdmin === 'function') {
            return mod.abrirModalCentroComunicacionAdmin(this, conv);
        }
    }

    cerrarModalCentroComunicacionAdmin() {
        const mod = this._operacionesModule();
        if (mod && typeof mod.cerrarModalCentroComunicacionAdmin === 'function') {
            return mod.cerrarModalCentroComunicacionAdmin(this);
        }
    }

    async responderCentroComunicacionAdmin() {
        const mod = this._operacionesModule();
        if (mod && typeof mod.responderCentroComunicacionAdmin === 'function') {
            return mod.responderCentroComunicacionAdmin(this);
        }
    }

    async actualizarEstadoCentroComunicacionAdmin() {
        const mod = this._operacionesModule();
        if (mod && typeof mod.actualizarEstadoCentroComunicacionAdmin === 'function') {
            return mod.actualizarEstadoCentroComunicacionAdmin(this);
        }
    }

    async eliminarCentroComunicacionAdmin() {
        const mod = this._operacionesModule();
        if (mod && typeof mod.eliminarCentroComunicacionAdmin === 'function') {
            return mod.eliminarCentroComunicacionAdmin(this);
        }
    }

    renderCompetenciasActivas(competencias) {
        const mod = this._sistemaModule();
        if (mod && typeof mod.renderCompetenciasActivas === 'function') {
            return mod.renderCompetenciasActivas(this, competencias);
        }
    }

    renderCompetenciasPendientes(pendientes) {
        const mod = this._sistemaModule();
        if (mod && typeof mod.renderCompetenciasPendientes === 'function') {
            return mod.renderCompetenciasPendientes(this, pendientes);
        }
    }

    renderCompetenciasHistorial(historial) {
        const mod = this._sistemaModule();
        if (mod && typeof mod.renderCompetenciasHistorial === 'function') {
            return mod.renderCompetenciasHistorial(this, historial);
        }
    }

    renderSuplentesEspera(aliados) {
        const mod = this._redModule();
        if (mod && typeof mod.renderSuplentesEspera === 'function') {
            return mod.renderSuplentesEspera(this, aliados);
        }
    }

    accionIncorporarSuplente(codigo) {
        const mod = this._redModule();
        if (mod && typeof mod.accionIncorporarSuplente === 'function') {
            return mod.accionIncorporarSuplente(this, codigo);
        }
    }

    async abrirModalVerChat(contactoId) {
        const mod = this._operacionesModule();
        if (mod && typeof mod.abrirModalVerChat === 'function') {
            return mod.abrirModalVerChat(this, contactoId);
        }
    }

    async eliminarNegociacion(contactoId) {
        const mod = this._operacionesModule();
        if (mod && typeof mod.eliminarNegociacion === 'function') {
            return mod.eliminarNegociacion(this, contactoId);
        }
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Inicializar cuando DOM esté listo
document.addEventListener('DOMContentLoaded', () => {
    new AdminAuthenticator();
});
    
