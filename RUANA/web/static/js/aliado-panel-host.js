
/**
 * RUANA - Panel Privado del Aliado
 * Capa de Presentación - Consume datos del Motor RUANA
 * Para apuntar al backend en otro host/puerto, definir antes: window.RUANA_API_BASE = 'http://127.0.0.1:5000';
 */
if (typeof window.RUANA_API_BASE === 'undefined') {
    // Por defecto, usa el mismo origen del panel para evitar desajustes (ej. panel en :5001 → API en :5001).
    window.RUANA_API_BASE = window.location.origin;
}
if (typeof window.RUANA_BIZUM_NUM === 'undefined') {
    window.RUANA_BIZUM_NUM = '642868261';
}
if (typeof window.RUANA_IBAN === 'undefined') {
    window.RUANA_IBAN = 'ES8915830001119028625152';
}
if (typeof window.RUANA_QR_REVOLUT_PATH === 'undefined') {
    window.RUANA_QR_REVOLUT_PATH = '/static/images/PayPal.png';
}

function getApiBase() {
    return window.RUANA_API_BASE || window.location.origin;
}
window.getApiBase = getApiBase;

/** Cabecera de sesión por pestaña (sessionStorage). Evita cruce de identidad entre pestañas. */
function getRuanaAuthHeaders(extra) {
    const sid = sessionStorage.getItem('ruana_session_id');
    const h = { ...(extra || {}) };
    if (sid) h['X-Ruana-Session-Id'] = sid;
    return h;
}

class PrivatePanel {
    /**
     * F06: Obtener código desde URLSearchParams
     * @returns {string|null} Código del aliado o null
     */
    static getCodigoFromURL() {
        const mod = (typeof RuanaAliadoModules !== 'undefined' && RuanaAliadoModules.sync) || null;
        if (mod && typeof mod.getCodigoFromURL === 'function') {
            return mod.getCodigoFromURL();
        }
        return null;
    }
    static async fetchAliadoDatos(codigo) {
        const mod = (typeof RuanaAliadoModules !== 'undefined' && RuanaAliadoModules.sync) || null;
        if (mod && typeof mod.fetchAliadoDatos === 'function') {
            return mod.fetchAliadoDatos(codigo);
        }
        return null;
    }
    constructor() {
        const mod = this._syncModule();
        if (mod && typeof mod.initState === 'function') {
            mod.initState(this);
        }
        // FLUJO: init → setupEventListeners → loadData → render
        this.init();
    }
    async init() {
        const mod = this._syncModule();
        if (mod && typeof mod.init === 'function') {
            return mod.init(this);
        }
    }
    async runWarmupSync() {
        const mod = this._syncModule();
        if (mod && typeof mod.runWarmupSync === 'function') {
            return mod.runWarmupSync(this);
        }
    }
    initOnboarding() {
        const mod = this._syncModule();
        if (mod && typeof mod.initOnboarding === 'function') {
            return mod.initOnboarding(this);
        }
    }
    getSyncElements(sections) {
        const mod = this._syncModule();
        if (mod && typeof mod.getSyncElements === 'function') {
            return mod.getSyncElements(this, sections);
        }
    }
    setSectionsSyncing(sections, syncing) {
        const mod = this._syncModule();
        if (mod && typeof mod.setSectionsSyncing === 'function') {
            return mod.setSectionsSyncing(this, sections, syncing);
        }
    }
    async fetchAliadoSnapshot() {
        const mod = this._syncModule();
        if (mod && typeof mod.fetchAliadoSnapshot === 'function') {
            return mod.fetchAliadoSnapshot(this);
        }
    }
    async fetchSolicitudesSnapshot() {
        const mod = this._syncModule();
        if (mod && typeof mod.fetchSolicitudesSnapshot === 'function') {
            return mod.fetchSolicitudesSnapshot(this);
        }
    }
    async fetchDirectorioSnapshot() {
        const mod = this._syncModule();
        if (mod && typeof mod.fetchDirectorioSnapshot === 'function') {
            return mod.fetchDirectorioSnapshot(this);
        }
    }
    async fetchCentroComunicacionSnapshot() {
        const mod = this._syncModule();
        if (mod && typeof mod.fetchCentroComunicacionSnapshot === 'function') {
            return mod.fetchCentroComunicacionSnapshot(this);
        }
    }
    async refreshAfterAction(sections, options) {
        const mod = this._syncModule();
        if (mod && typeof mod.refreshAfterAction === 'function') {
            return mod.refreshAfterAction(this, sections, options);
        }
    }
    startAutoSync() {
        const mod = this._syncModule();
        if (mod && typeof mod.startAutoSync === 'function') {
            return mod.startAutoSync(this);
        }
    }
    setPanelLoading(isLoading) {
        const mod = this._syncModule();
        if (mod && typeof mod.setPanelLoading === 'function') {
            return mod.setPanelLoading(this, isLoading);
        }
    }
    async loadData() {
        const mod = this._syncModule();
        if (mod && typeof mod.loadData === 'function') {
            return mod.loadData(this);
        }
    }
    render() {
        const mod = this._syncModule();
        if (mod && typeof mod.render === 'function') {
            return mod.render(this);
        }
    }
    _referidosModule() {
        return (typeof RuanaAliadoModules !== 'undefined' && RuanaAliadoModules.referidos) || null;
    }
    async abrirModalLinajeHijos() {
        const mod = this._referidosModule();
        if (mod && typeof mod.abrirModalLinajeHijos === 'function') {
            return mod.abrirModalLinajeHijos(this);
        }
    }
    cerrarModalLinajeHijos() {
        const mod = this._referidosModule();
        if (mod && typeof mod.cerrarModalLinajeHijos === 'function') {
            return mod.cerrarModalLinajeHijos();
        }
    }
    _perfilModule() {
        return (typeof RuanaAliadoModules !== 'undefined' && RuanaAliadoModules.perfil) || null;
    }
    getIniciales(nombre) {
        const mod = this._perfilModule();
        if (mod && typeof mod.getIniciales === 'function') {
            return mod.getIniciales(nombre);
        }
        const texto = (nombre || '').trim();
        return texto.split(/\s+/).filter(Boolean).slice(0, 2).map(p => p[0]).join('').toUpperCase().slice(0, 2) || '?';
    }
    renderAvatarHtml(fotoUrl, nombre, className, etiquetaStatus) {
        const mod = this._perfilModule();
        if (mod && typeof mod.renderAvatarHtml === 'function') {
            return mod.renderAvatarHtml(this, fotoUrl, nombre, className, etiquetaStatus);
        }
        return '';
    }
    _mapEtiquetaAvatarStatus(status) {
        const mod = this._perfilModule();
        if (mod && typeof mod.mapEtiquetaAvatarStatus === 'function') {
            return mod.mapEtiquetaAvatarStatus(status);
        }
        return 'estable';
    }
    _syncPerfilAvatarEtiqueta(status) {
        const mod = this._perfilModule();
        if (mod && typeof mod.syncPerfilAvatarEtiqueta === 'function') {
            return mod.syncPerfilAvatarEtiqueta(status);
        }
    }
    aplicarAvatarPerfil(aliadoData) {
        const mod = this._perfilModule();
        if (mod && typeof mod.aplicarAvatarPerfil === 'function') {
            return mod.aplicarAvatarPerfil(this, aliadoData);
        }
    }
    async subirFotoPerfil(file) {
        const mod = this._perfilModule();
        if (mod && typeof mod.subirFotoPerfil === 'function') {
            return mod.subirFotoPerfil(this, file);
        }
    }
    async quitarFotoPerfil() {
        const mod = this._perfilModule();
        if (mod && typeof mod.quitarFotoPerfil === 'function') {
            return mod.quitarFotoPerfil(this);
        }
    }
    renderPerfil() {
        const mod = this._perfilModule();
        if (mod && typeof mod.renderPerfil === 'function') {
            return mod.renderPerfil(this);
        }
    }
    _acuerdosModule() {
        return (typeof RuanaAliadoModules !== 'undefined' && RuanaAliadoModules.acuerdos) || null;
    }
    async cargarMisAcuerdos() {
        const mod = this._acuerdosModule();
        if (mod && typeof mod.cargarMisAcuerdos === 'function') {
            return mod.cargarMisAcuerdos(this);
        }
    }
    etiquetaEstadoAcuerdo(a) {
        const mod = this._acuerdosModule();
        if (mod && typeof mod.etiquetaEstadoAcuerdo === 'function') {
            return mod.etiquetaEstadoAcuerdo(a);
        }
        return (a && a.estado_label) || (a && a.estado) || 'Sin estado';
    }
    formatearFechaAcuerdo(raw) {
        const mod = this._acuerdosModule();
        if (mod && typeof mod.formatearFechaAcuerdo === 'function') {
            return mod.formatearFechaAcuerdo(raw);
        }
        return raw ? String(raw).slice(0, 16) : '';
    }
    toggleMisAcuerdoExpandido(contactoId) {
        const mod = this._acuerdosModule();
        if (mod && typeof mod.toggleMisAcuerdoExpandido === 'function') {
            return mod.toggleMisAcuerdoExpandido(this, contactoId);
        }
    }
    mostrarMasMisAcuerdos() {
        const mod = this._acuerdosModule();
        if (mod && typeof mod.mostrarMasMisAcuerdos === 'function') {
            return mod.mostrarMasMisAcuerdos(this);
        }
    }
    renderMisAcuerdos() {
        const mod = this._acuerdosModule();
        if (mod && typeof mod.renderMisAcuerdos === 'function') {
            return mod.renderMisAcuerdos(this);
        }
    }
    async cargarResumenesAcuerdoFlotantes() {
        const mod = this._contactosModule();
        if (mod && typeof mod.cargarResumenesAcuerdoFlotantes === 'function') {
            return mod.cargarResumenesAcuerdoFlotantes(this);
        }
    }
    syncAcuerdoFlotante(data) {
        const mod = this._contactosModule();
        if (mod && typeof mod.syncAcuerdoFlotante === 'function') {
            return mod.syncAcuerdoFlotante(this, data);
        }
    }
    mostrarAcuerdoFlotanteDesdeNegociacion(contactoId, data) {
        const mod = this._contactosModule();
        if (mod && typeof mod.mostrarAcuerdoFlotanteDesdeNegociacion === 'function') {
            return mod.mostrarAcuerdoFlotanteDesdeNegociacion(this, contactoId, data);
        }
    }
    mostrarAcuerdoFlotante(item) {
        const mod = this._contactosModule();
        if (mod && typeof mod.mostrarAcuerdoFlotante === 'function') {
            return mod.mostrarAcuerdoFlotante(this, item);
        }
    }
    ocultarAcuerdoFlotante() {
        const mod = this._contactosModule();
        if (mod && typeof mod.ocultarAcuerdoFlotante === 'function') {
            return mod.ocultarAcuerdoFlotante(this);
        }
    }
    ocultarAcuerdoFlotantePorModal() {
        const mod = this._contactosModule();
        if (mod && typeof mod.ocultarAcuerdoFlotantePorModal === 'function') {
            return mod.ocultarAcuerdoFlotantePorModal(this);
        }
    }
    restaurarAcuerdoFlotanteTrasNegociacion(contactoId, dataSnapshot) {
        const mod = this._contactosModule();
        if (mod && typeof mod.restaurarAcuerdoFlotanteTrasNegociacion === 'function') {
            return mod.restaurarAcuerdoFlotanteTrasNegociacion(this, contactoId, dataSnapshot);
        }
    }
    async dismissAcuerdoFlotante() {
        const mod = this._contactosModule();
        if (mod && typeof mod.dismissAcuerdoFlotante === 'function') {
            return mod.dismissAcuerdoFlotante(this);
        }
    }
    async confirmarAcuerdoDesdeFlotante() {
        const mod = this._contactosModule();
        if (mod && typeof mod.confirmarAcuerdoDesdeFlotante === 'function') {
            return mod.confirmarAcuerdoDesdeFlotante(this);
        }
    }
    normalizarCatalogoServicios(catalogoRaw) {
        const mod = this._catalogoModule();
        if (mod && typeof mod.normalizarCatalogoServicios === 'function') {
            return mod.normalizarCatalogoServicios(this, catalogoRaw);
        }
    }
    _catalogoResumenTitulo(servicio) {
        const mod = this._catalogoModule();
        if (mod && typeof mod._catalogoResumenTitulo === 'function') {
            return mod._catalogoResumenTitulo(this, servicio);
        }
    }
    _primeraPosicionLibreCatalogo(catalogo) {
        const mod = this._catalogoModule();
        if (mod && typeof mod._primeraPosicionLibreCatalogo === 'function') {
            return mod._primeraPosicionLibreCatalogo(this, catalogo);
        }
    }
    abrirCatalogoEdicion(posicion) {
        const mod = this._catalogoModule();
        if (mod && typeof mod.abrirCatalogoEdicion === 'function') {
            return mod.abrirCatalogoEdicion(this, posicion);
        }
    }
    anadirEspecializacionCatalogo() {
        const mod = this._catalogoModule();
        if (mod && typeof mod.anadirEspecializacionCatalogo === 'function') {
            return mod.anadirEspecializacionCatalogo(this);
        }
    }
    cancelarEdicionCatalogo(posicion) {
        const mod = this._catalogoModule();
        if (mod && typeof mod.cancelarEdicionCatalogo === 'function') {
            return mod.cancelarEdicionCatalogo(this, posicion);
        }
    }
    renderCatalogoServicios() {
        const mod = this._catalogoModule();
        if (mod && typeof mod.renderCatalogoServicios === 'function') {
            return mod.renderCatalogoServicios(this);
        }
    }
    async guardarCatalogoServicio(posicion) {
        const mod = this._catalogoModule();
        if (mod && typeof mod.guardarCatalogoServicio === 'function') {
            return mod.guardarCatalogoServicio(this, posicion);
        }
    }
    renderCompetencia() {
        const mod = this._grupoModule();
        if (mod && typeof mod.renderCompetencia === 'function') {
            return mod.renderCompetencia(this);
        }
    }
    renderGrupo() {
        const mod = this._grupoModule();
        if (mod && typeof mod.renderGrupo === 'function') {
            return mod.renderGrupo(this);
        }
    }
    renderOficiosFaltantesFullList(oficios) {
        const mod = this._grupoModule();
        if (mod && typeof mod.renderOficiosFaltantesFullList === 'function') {
            return mod.renderOficiosFaltantesFullList(this, oficios);
        }
    }
    _inicioModule() {
        return (typeof RuanaAliadoModules !== 'undefined' && RuanaAliadoModules.inicio) || null;
    }
    renderMetricas() {
        const mod = this._inicioModule();
        if (mod && typeof mod.renderMetricas === 'function') {
            return mod.renderMetricas(this);
        }
    }
    formatScoreMotivo(motivo) {
        const mod = this._inicioModule();
        if (mod && typeof mod.formatScoreMotivo === 'function') {
            return mod.formatScoreMotivo(motivo);
        }
        return String(motivo || '').replace(/_/g, ' ') || 'actualización de reglas RUANA';
    }
    getScoreNotifVariants(isUp) {
        const mod = this._inicioModule();
        if (mod && typeof mod.getScoreNotifVariants === 'function') {
            return mod.getScoreNotifVariants(isUp);
        }
        return [];
    }
    positionScoreCallout(callout) {
        const mod = this._inicioModule();
        if (mod && typeof mod.positionScoreCallout === 'function') {
            return mod.positionScoreCallout(callout);
        }
    }
    teardownScoreCallout(callout, anchor) {
        const mod = this._inicioModule();
        if (mod && typeof mod.teardownScoreCallout === 'function') {
            return mod.teardownScoreCallout(this, callout, anchor);
        }
    }
    async markNotificationRead(notifId) {
        const mod = this._inicioModule();
        if (mod && typeof mod.markNotificationRead === 'function') {
            return mod.markNotificationRead(this, notifId);
        }
    }
    maybeShowScoreChangeNotification() {
        const mod = this._inicioModule();
        if (mod && typeof mod.maybeShowScoreChangeNotification === 'function') {
            return mod.maybeShowScoreChangeNotification(this);
        }
    }
    _solicitudesModule() {
        return (typeof RuanaAliadoModules !== 'undefined' && RuanaAliadoModules.solicitudes) || null;
    }
    _conexionesModule() {
        return (typeof RuanaAliadoModules !== 'undefined' && RuanaAliadoModules.conexiones) || null;
    }
    _invitacionesModule() {
        return (typeof RuanaAliadoModules !== 'undefined' && RuanaAliadoModules.invitaciones) || null;
    }
    _alertasModule() {
        return (typeof RuanaAliadoModules !== 'undefined' && RuanaAliadoModules.alertas) || null;
    }
    _catalogoModule() {
        return (typeof RuanaAliadoModules !== 'undefined' && RuanaAliadoModules.catalogo) || null;
    }
    _contactosModule() {
        return (typeof RuanaAliadoModules !== 'undefined' && RuanaAliadoModules.contactos) || null;
    }
    _grupoModule() {
        return (typeof RuanaAliadoModules !== 'undefined' && RuanaAliadoModules.grupo) || null;
    }
    _syncModule() {
        return (typeof RuanaAliadoModules !== 'undefined' && RuanaAliadoModules.sync) || null;
    }
    _eventsModule() {
        return (typeof RuanaAliadoModules !== 'undefined' && RuanaAliadoModules.events) || null;
    }
    renderSolicitudes() {
        const mod = this._solicitudesModule();
        if (mod && typeof mod.renderSolicitudes === 'function') {
            return mod.renderSolicitudes(this);
        }
    }
    appendSolicitudCard(container, solicitud, conBotonConocer) {
        const mod = this._solicitudesModule();
        if (mod && typeof mod.appendSolicitudCard === 'function') {
            return mod.appendSolicitudCard(this, container, solicitud, conBotonConocer);
        }
    }
    async generarCodigoInvitacionPerfil() {
        const mod = this._invitacionesModule();
        if (mod && typeof mod.generarCodigoInvitacionPerfil === 'function') {
            return mod.generarCodigoInvitacionPerfil(this);
        }
    }
    async generateInviteCode(solicitudId) {
        const mod = this._invitacionesModule();
        if (mod && typeof mod.generateInviteCode === 'function') {
            return mod.generateInviteCode(this, solicitudId);
        }
    }
    mostrarModalCodigoInvitacion(codigo, desdeSolicitud) {
        const mod = this._invitacionesModule();
        if (mod && typeof mod.mostrarModalCodigoInvitacion === 'function') {
            return mod.mostrarModalCodigoInvitacion(this, codigo, desdeSolicitud);
        }
    }
    registerInviteCodeWithBackend(code, solicitudId) {
        const mod = this._invitacionesModule();
        if (mod && typeof mod.registerInviteCodeWithBackend === 'function') {
            return mod.registerInviteCodeWithBackend(this, code, solicitudId);
        }
    }
    getFechaExpiracion(dias) {
        const mod = this._invitacionesModule();
        if (mod && typeof mod.getFechaExpiracion === 'function') {
            return mod.getFechaExpiracion(this, dias);
        }
    }
    generateRandomCode(length = 5) {
        const mod = this._invitacionesModule();
        if (mod && typeof mod.generateRandomCode === 'function') {
            return mod.generateRandomCode(this, length);
        }
    }
    setupEventListeners() {
        const mod = this._eventsModule();
        if (mod && typeof mod.setupEventListeners === 'function') {
            return mod.setupEventListeners(this);
        }
    }
    async generarInvitacionOficio(oficio) {
        const mod = this._invitacionesModule();
        if (mod && typeof mod.generarInvitacionOficio === 'function') {
            return mod.generarInvitacionOficio(this, oficio);
        }
    }
    copiarCodigoInvitacionOficio() {
        const mod = this._invitacionesModule();
        if (mod && typeof mod.copiarCodigoInvitacionOficio === 'function') {
            return mod.copiarCodigoInvitacionOficio(this);
        }
    }
    cerrarModalInvitacionOficio() {
        const mod = this._invitacionesModule();
        if (mod && typeof mod.cerrarModalInvitacionOficio === 'function') {
            return mod.cerrarModalInvitacionOficio(this);
        }
    }
    expandirOficiosFaltantes() {
        const mod = this._grupoModule();
        if (mod && typeof mod.expandirOficiosFaltantes === 'function') {
            return mod.expandirOficiosFaltantes(this);
        }
    }
    ocultarOficiosFaltantes() {
        const mod = this._grupoModule();
        if (mod && typeof mod.ocultarOficiosFaltantes === 'function') {
            return mod.ocultarOficiosFaltantes(this);
        }
    }
    filtrarOficiosFaltantes() {
        const mod = this._grupoModule();
        if (mod && typeof mod.filtrarOficiosFaltantes === 'function') {
            return mod.filtrarOficiosFaltantes(this);
        }
    }
    iniciarEditarDescripcion() {
        const mod = this._perfilModule();
        if (mod && typeof mod.iniciarEditarDescripcion === 'function') {
            return mod.iniciarEditarDescripcion(this);
        }
    }
    cancelarEditarDescripcion() {
        const mod = this._perfilModule();
        if (mod && typeof mod.cancelarEditarDescripcion === 'function') {
            return mod.cancelarEditarDescripcion();
        }
    }
    async guardarDescripcion() {
        const mod = this._perfilModule();
        if (mod && typeof mod.guardarDescripcion === 'function') {
            return mod.guardarDescripcion(this);
        }
    }
    _directorioModule() {
        return (typeof RuanaAliadoModules !== 'undefined' && RuanaAliadoModules.directorio) || null;
    }
    _codigosConConversacionActiva() {
        const mod = this._directorioModule();
        if (mod && typeof mod.codigosConConversacionActiva === 'function') {
            return mod.codigosConConversacionActiva(this);
        }
        return new Map();
    }
    _scoreEtiquetaMeta(score, estadoRuana) {
        const mod = this._directorioModule();
        if (mod && typeof mod.scoreEtiquetaMeta === 'function') {
            return mod.scoreEtiquetaMeta(score, estadoRuana);
        }
        return { score: 0, status: 'competencia', label: 'Competencia' };
    }
    renderProfesionales() {
        const mod = this._directorioModule();
        if (mod && typeof mod.renderProfesionales === 'function') {
            return mod.renderProfesionales(this);
        }
    }
    formatApoyoRuana(raw) {
        const mod = this._alertasModule();
        if (mod && typeof mod.formatApoyoRuana === 'function') {
            return mod.formatApoyoRuana(this, raw);
        }
    }
    buildAlertItems() {
        const mod = this._alertasModule();
        if (mod && typeof mod.buildAlertItems === 'function') {
            return mod.buildAlertItems(this);
        }
    }
    renderAlertDetailPanel(detailEl, detailId) {
        const mod = this._alertasModule();
        if (mod && typeof mod.renderAlertDetailPanel === 'function') {
            return mod.renderAlertDetailPanel(this, detailEl, detailId);
        }
    }
    renderAlertHub() {
        const mod = this._alertasModule();
        if (mod && typeof mod.renderAlertHub === 'function') {
            return mod.renderAlertHub(this);
        }
    }
    renderAlertas() {
        const mod = this._alertasModule();
        if (mod && typeof mod.renderAlertas === 'function') {
            return mod.renderAlertas(this);
        }
    }
    async cargarMetodosPagoRuana() {
        const mod = this._alertasModule();
        if (mod && typeof mod.cargarMetodosPagoRuana === 'function') {
            return mod.cargarMetodosPagoRuana(this);
        }
    }
    async actualizarEstadoAlertas() {
        const mod = this._alertasModule();
        if (mod && typeof mod.actualizarEstadoAlertas === 'function') {
            return mod.actualizarEstadoAlertas(this);
        }
    }
    renderListaPagosPendientes() {
        const mod = this._alertasModule();
        if (mod && typeof mod.renderListaPagosPendientes === 'function') {
            return mod.renderListaPagosPendientes(this);
        }
    }
    renderNotificaciones() {
        const mod = this._alertasModule();
        if (mod && typeof mod.renderNotificaciones === 'function') {
            return mod.renderNotificaciones(this);
        }
    }
    async marcarTodasNotificacionesLeidas() {
        const mod = this._alertasModule();
        if (mod && typeof mod.marcarTodasNotificacionesLeidas === 'function') {
            return mod.marcarTodasNotificacionesLeidas(this);
        }
    }
    _centroComunicacionModule() {
        return (typeof RuanaAliadoModules !== 'undefined' && RuanaAliadoModules.centroComunicacion) || null;
    }
    formatHelpStatus(estado) {
        const mod = this._centroComunicacionModule();
        if (mod && typeof mod.formatHelpStatus === 'function') {
            return mod.formatHelpStatus(estado);
        }
        return 'Pendiente';
    }
    abrirCentroComunicacion() {
        const mod = this._centroComunicacionModule();
        if (mod && typeof mod.abrirCentroComunicacion === 'function') {
            return mod.abrirCentroComunicacion(this);
        }
    }
    cerrarCentroComunicacion() {
        const mod = this._centroComunicacionModule();
        if (mod && typeof mod.cerrarCentroComunicacion === 'function') {
            return mod.cerrarCentroComunicacion();
        }
    }
    toggleCentroComunicacion() {
        const mod = this._centroComunicacionModule();
        if (mod && typeof mod.toggleCentroComunicacion === 'function') {
            return mod.toggleCentroComunicacion(this);
        }
    }
    renderCentroComunicacion() {
        const mod = this._centroComunicacionModule();
        if (mod && typeof mod.renderCentroComunicacion === 'function') {
            return mod.renderCentroComunicacion(this);
        }
    }
    async seleccionarConversacionSoporte(conversacionId) {
        const mod = this._centroComunicacionModule();
        if (mod && typeof mod.seleccionarConversacionSoporte === 'function') {
            return mod.seleccionarConversacionSoporte(this, conversacionId);
        }
    }
    renderMensajesCentroComunicacion() {
        const mod = this._centroComunicacionModule();
        if (mod && typeof mod.renderMensajesCentroComunicacion === 'function') {
            return mod.renderMensajesCentroComunicacion(this);
        }
    }
    async enviarNuevoMensajeSoporte() {
        const mod = this._centroComunicacionModule();
        if (mod && typeof mod.enviarNuevoMensajeSoporte === 'function') {
            return mod.enviarNuevoMensajeSoporte(this);
        }
    }
    async responderConversacionSoporte() {
        const mod = this._centroComunicacionModule();
        if (mod && typeof mod.responderConversacionSoporte === 'function') {
            return mod.responderConversacionSoporte(this);
        }
    }
    async handleEnviarSolicitud() {
        const mod = this._conexionesModule();
        if (mod && typeof mod.handleEnviarSolicitud === 'function') {
            return mod.handleEnviarSolicitud(this);
        }
    }
    copyCode() {
        const mod = this._syncModule();
        if (mod && typeof mod.copyCode === 'function') {
            return mod.copyCode(this);
        }
    }
    closeCodeModal() {
        const mod = this._syncModule();
        if (mod && typeof mod.closeCodeModal === 'function') {
            return mod.closeCodeModal(this);
        }
    }
    async handleLogout() {
        const mod = this._syncModule();
        if (mod && typeof mod.handleLogout === 'function') {
            return mod.handleLogout(this);
        }
    }
    normalizarEstado(estado) {
        const mod = this._syncModule();
        if (mod && typeof mod.normalizarEstado === 'function') {
            return mod.normalizarEstado(this, estado);
        }
    }
    escapeHtml(text) {
        const mod = this._syncModule();
        if (mod && typeof mod.escapeHtml === 'function') {
            return mod.escapeHtml(this, text);
        }
    }
    async finalizarContactoCerradoEnUI(contactoId, opts) {
        const mod = this._contactosModule();
        if (mod && typeof mod.finalizarContactoCerradoEnUI === 'function') {
            return mod.finalizarContactoCerradoEnUI(this, contactoId, opts);
        }
    }
    async cargarContactosPendientes() {
        const mod = this._contactosModule();
        if (mod && typeof mod.cargarContactosPendientes === 'function') {
            return mod.cargarContactosPendientes(this);
        }
    }
    async cargarPagosApoyoPendientes() {
        const mod = this._alertasModule();
        if (mod && typeof mod.cargarPagosApoyoPendientes === 'function') {
            return mod.cargarPagosApoyoPendientes(this);
        }
    }
    abrirModalComprobanteApoyo(contactoId) {
        const mod = this._alertasModule();
        if (mod && typeof mod.abrirModalComprobanteApoyo === 'function') {
            return mod.abrirModalComprobanteApoyo(this, contactoId);
        }
    }
    abrirModalPagoApoyo(contactoId, apoyoRuana, servicio) {
        const mod = this._alertasModule();
        if (mod && typeof mod.abrirModalPagoApoyo === 'function') {
            return mod.abrirModalPagoApoyo(this, contactoId, apoyoRuana, servicio);
        }
    }
    setPagoApoyoMetodo(metodo) {
        const mod = this._alertasModule();
        if (mod && typeof mod.setPagoApoyoMetodo === 'function') {
            return mod.setPagoApoyoMetodo(this, metodo);
        }
    }
    abrirModalPayPalApoyo(contactoId, apoyoRuana, servicio) {
        const mod = this._alertasModule();
        if (mod && typeof mod.abrirModalPayPalApoyo === 'function') {
            return mod.abrirModalPayPalApoyo(this, contactoId, apoyoRuana, servicio);
        }
    }
    abrirModalBizumApoyo(contactoId, apoyoRuana, servicio) {
        const mod = this._alertasModule();
        if (mod && typeof mod.abrirModalBizumApoyo === 'function') {
            return mod.abrirModalBizumApoyo(this, contactoId, apoyoRuana, servicio);
        }
    }
    async enviarComprobanteApoyo() {
        const mod = this._alertasModule();
        if (mod && typeof mod.enviarComprobanteApoyo === 'function') {
            return mod.enviarComprobanteApoyo(this);
        }
    }
    abrirModalImpugnarApoyo(contactoId) {
        const mod = this._alertasModule();
        if (mod && typeof mod.abrirModalImpugnarApoyo === 'function') {
            return mod.abrirModalImpugnarApoyo(this, contactoId);
        }
    }
    async impugnarApoyoRuana(contactoId) {
        const mod = this._alertasModule();
        if (mod && typeof mod.impugnarApoyoRuana === 'function') {
            return mod.impugnarApoyoRuana(this, contactoId);
        }
    }
    async mostrarAvisoPrevioContacto(profesional) {
        const mod = this._contactosModule();
        if (mod && typeof mod.mostrarAvisoPrevioContacto === 'function') {
            return mod.mostrarAvisoPrevioContacto(this, profesional);
        }
    }
    async _cargarCatalogoEnPrevioContacto(profesionalCodigo) {
        const mod = this._contactosModule();
        if (mod && typeof mod._cargarCatalogoEnPrevioContacto === 'function') {
            return mod._cargarCatalogoEnPrevioContacto(this, profesionalCodigo);
        }
    }
    _obtenerServicioSeleccionadoPrevio(profesional) {
        const mod = this._contactosModule();
        if (mod && typeof mod._obtenerServicioSeleccionadoPrevio === 'function') {
            return mod._obtenerServicioSeleccionadoPrevio(this, profesional);
        }
    }
    _obtenerPrecioCatalogoPrevio() {
        const mod = this._contactosModule();
        if (mod && typeof mod._obtenerPrecioCatalogoPrevio === 'function') {
            return mod._obtenerPrecioCatalogoPrevio(this);
        }
    }
    _encargoUiLabels(contacto) {
        const mod = this._contactosModule();
        if (mod && typeof mod._encargoUiLabels === 'function') {
            return mod._encargoUiLabels(this, contacto);
        }
    }
    renderEncargosActivos() {
        const mod = this._contactosModule();
        if (mod && typeof mod.renderEncargosActivos === 'function') {
            return mod.renderEncargosActivos(this);
        }
    }
    async crearContactoYAbrirNegociacion() {
        const mod = this._contactosModule();
        if (mod && typeof mod.crearContactoYAbrirNegociacion === 'function') {
            return mod.crearContactoYAbrirNegociacion(this);
        }
    }
    abrirNegociacionContacto(contactoId, profesional, opts) {
        const mod = this._contactosModule();
        if (mod && typeof mod.abrirNegociacionContacto === 'function') {
            return mod.abrirNegociacionContacto(this, contactoId, profesional, opts);
        }
    }
    abrirNegociacionDesdeContactoActual() {
        const mod = this._contactosModule();
        if (mod && typeof mod.abrirNegociacionDesdeContactoActual === 'function') {
            return mod.abrirNegociacionDesdeContactoActual(this);
        }
    }
    abrirChatContacto(contactoId, profesional, opts) {
        const mod = this._contactosModule();
        if (mod && typeof mod.abrirChatContacto === 'function') {
            return mod.abrirChatContacto(this, contactoId, profesional, opts);
        }
    }
    handleAvisoSiHuboTrabajo() {
        const mod = this._contactosModule();
        if (mod && typeof mod.handleAvisoSiHuboTrabajo === 'function') {
            return mod.handleAvisoSiHuboTrabajo(this);
        }
    }
    async confirmarImporteContacto() {
        const mod = this._contactosModule();
        if (mod && typeof mod.confirmarImporteContacto === 'function') {
            return mod.confirmarImporteContacto(this);
        }
    }
    async mostrarResumenCierre(contactoId) {
        const mod = this._contactosModule();
        if (mod && typeof mod.mostrarResumenCierre === 'function') {
            return mod.mostrarResumenCierre(this, contactoId);
        }
    }
    async subirPruebaConflicto() {
        const mod = this._contactosModule();
        if (mod && typeof mod.subirPruebaConflicto === 'function') {
            return mod.subirPruebaConflicto(this);
        }
    }
    handleAvisoNoSeConcreto() {
        const mod = this._contactosModule();
        if (mod && typeof mod.handleAvisoNoSeConcreto === 'function') {
            return mod.handleAvisoNoSeConcreto(this);
        }
    }
    async confirmarNoConcretado() {
        const mod = this._contactosModule();
        if (mod && typeof mod.confirmarNoConcretado === 'function') {
            return mod.confirmarNoConcretado(this);
        }
    }
    async handleAvisoSigueEnConversacion() {
        const mod = this._contactosModule();
        if (mod && typeof mod.handleAvisoSigueEnConversacion === 'function') {
            return mod.handleAvisoSigueEnConversacion(this);
        }
    }
}

// Bootstrap sesión aliado → RuanaAliadoModules.sync.bootstrapPrivatePanel
window.PrivatePanel = PrivatePanel;
if (typeof RuanaAliadoModules !== 'undefined' && RuanaAliadoModules.sync &&
    typeof RuanaAliadoModules.sync.bootstrapPrivatePanel === 'function') {
    RuanaAliadoModules.sync.bootstrapPrivatePanel();
}
    
