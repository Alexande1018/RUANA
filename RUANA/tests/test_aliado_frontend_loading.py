from pathlib import Path


def test_aliado_panel_starts_with_loading_state():
    aliado_html = Path(__file__).resolve().parents[1] / "web" / "aliado.html"
    styles = Path(__file__).resolve().parents[1] / "web" / "static" / "css" / "styles.css"
    text = aliado_html.read_text(encoding="utf-8")
    css = styles.read_text(encoding="utf-8")

    # El body arranca en loading (puede combinar otras clases, p.ej. aliado-app).
    assert 'class="panel-loading' in text or ' panel-loading' in text
    assert "<body" in text and "panel-loading" in text.split("<body", 1)[1].split(">", 1)[0]
    assert 'id="panel-loading"' in text
    assert "Preparando tu panel..." in text
    assert 'class="ruana-loader-orbit"' in text
    assert 'class="ruana-loader-node node-a"' in text
    assert 'class="ruana-loader-line line-a"' in text
    assert "prefers-reduced-motion: reduce" in css
    sync_js = (
        Path(__file__).resolve().parents[1]
        / "web"
        / "static"
        / "js"
        / "aliado-sync-module.js"
    ).read_text(encoding="utf-8")
    assert "setPanelLoading(false)" in text or "host.setPanelLoading(false)" in sync_js


def test_aliado_panel_does_not_ship_demo_profile_values():
    aliado_html = Path(__file__).resolve().parents[1] / "web" / "aliado.html"
    text = aliado_html.read_text(encoding="utf-8")

    assert "Juan P" not in text
    assert "JP Instalaciones" not in text
    assert 'id="detail-oficio">Electricidad<' not in text


def test_aliado_solicitudes_initial_load_sends_auth_headers():
    """Carga de solicitudes (loadData/sync) envía credenciales + auth headers."""
    root = Path(__file__).resolve().parents[1] / "web"
    sync_js = (root / "static" / "js" / "aliado-sync-module.js").read_text(encoding="utf-8")
    start = sync_js.index("fetch(apiBase + '/api/solicitudes?codigo='")
    snippet = sync_js[start : start + 320]

    assert "credentials: 'same-origin'" in snippet
    assert "getAuthHeadersSafe()" in snippet or "getRuanaAuthHeaders()" in snippet


def test_aceptar_y_pagar_offers_manual_methods_and_receipt_upload():
    aliado_html = Path(__file__).resolve().parents[1] / "web" / "aliado.html"
    text = aliado_html.read_text(encoding="utf-8")

    assert "QR Revolut" in text
    assert "Transferencia" in text
    assert "Subir comprobante" in text


def test_aliado_inicio_module_is_wired():
    """Módulo shell `inicio` extraído a JS; PrivatePanel solo fachada."""
    root = Path(__file__).resolve().parents[1] / "web"
    aliado = (root / "aliado.html").read_text(encoding="utf-8")
    inicio_js = (root / "static" / "js" / "aliado-inicio-module.js").read_text(encoding="utf-8")
    modules_js = (root / "static" / "js" / "aliado-modules.js").read_text(encoding="utf-8")

    assert 'src="/static/js/aliado-modules.js"' in aliado
    assert 'src="/static/js/aliado-inicio-module.js"' in aliado
    assert '/static/js/aliado-shell.js' in aliado
    assert "RuanaAliadoModules" in modules_js
    assert "RuanaAliadoModules.inicio" in inicio_js or "modules.inicio" in inicio_js
    assert "renderMetricas" in inicio_js
    assert "score-alerta-panel" in inicio_js
    assert "metric-score" in inicio_js
    assert "maybeShowScoreChangeNotification" in inicio_js
    # Fachadas delgadas en PrivatePanel
    assert "_inicioModule" in aliado
    assert "mod.renderMetricas(this)" in aliado
    assert "mod.maybeShowScoreChangeNotification(this)" in aliado


def test_aliado_referidos_module_is_wired():
    """Módulo PrivatePanel `referidos` (árbol genealógico modal); PrivatePanel solo fachada."""
    root = Path(__file__).resolve().parents[1] / "web"
    aliado = (root / "aliado.html").read_text(encoding="utf-8")
    referidos_js = (root / "static" / "js" / "aliado-referidos-module.js").read_text(encoding="utf-8")
    modules_js = (root / "static" / "js" / "aliado-modules.js").read_text(encoding="utf-8")

    assert 'src="/static/js/aliado-modules.js"' in aliado
    assert 'src="/static/js/referidos-module.js"' in aliado
    assert 'src="/static/js/aliado-referidos-module.js"' in aliado
    assert 'href="/static/css/referidos-tree.css"' in aliado
    assert "RuanaAliadoModules" in modules_js
    assert "referidos: null" in modules_js
    assert "RuanaReferidos" in referidos_js or "RuanaReferidosTree" in referidos_js
    assert "abrirModalLinajeHijos" in referidos_js
    assert "cerrarModalLinajeHijos" in referidos_js
    assert "referidos-tree-aliado" in referidos_js
    assert "modal-linaje-hijos" in referidos_js
    # Fachadas delgadas en PrivatePanel
    assert "_referidosModule" in aliado
    assert "mod.abrirModalLinajeHijos(this)" in aliado
    assert "mod.cerrarModalLinajeHijos()" in aliado
    assert 'id="modal-linaje-hijos"' in aliado
    assert 'id="metrica-card-referidos"' in aliado


def test_aliado_perfil_module_is_wired():
    """Módulo PrivatePanel `perfil` (foto/avatar/detalles); PrivatePanel solo fachada."""
    root = Path(__file__).resolve().parents[1] / "web"
    aliado = (root / "aliado.html").read_text(encoding="utf-8")
    perfil_js = (root / "static" / "js" / "aliado-perfil-module.js").read_text(encoding="utf-8")
    modules_js = (root / "static" / "js" / "aliado-modules.js").read_text(encoding="utf-8")

    assert 'src="/static/js/aliado-modules.js"' in aliado
    assert 'src="/static/js/aliado-perfil-module.js"' in aliado
    assert "RuanaAliadoModules" in modules_js
    assert "perfil: null" in modules_js
    assert "RuanaAliadoModules.perfil" in perfil_js or "modules.perfil" in perfil_js
    assert "aplicarAvatarPerfil" in perfil_js
    assert "subirFotoPerfil" in perfil_js
    assert "quitarFotoPerfil" in perfil_js
    assert "renderPerfil" in perfil_js
    assert "guardarDescripcion" in perfil_js
    assert "/foto-perfil" in perfil_js
    # Fachadas delgadas en PrivatePanel
    assert "_perfilModule" in aliado
    assert "mod.renderPerfil(this)" in aliado
    assert "mod.subirFotoPerfil(this, file)" in aliado
    assert "mod.quitarFotoPerfil(this)" in aliado
    assert "mod.guardarDescripcion(this)" in aliado
    assert "mostrarFormularioCambiarPin" in perfil_js
    assert "ocultarFormularioCambiarPin" in perfil_js
    assert 'id="btn-mostrar-cambiar-pin"' in aliado
    assert 'id="form-cambiar-pin"' in aliado
    # Markup del perfil permanece en aliado.html (sin reescritura masiva)
    assert 'id="module-perfil"' in aliado
    assert 'id="perfil-avatar"' in aliado
    assert 'id="input-foto-perfil"' in aliado
    assert 'id="detail-descripcion"' in aliado


def test_aliado_directorio_module_is_wired():
    """Módulo PrivatePanel `directorio` (lista profesionales); PrivatePanel solo fachada."""
    root = Path(__file__).resolve().parents[1] / "web"
    aliado = (root / "aliado.html").read_text(encoding="utf-8")
    directorio_js = (root / "static" / "js" / "aliado-directorio-module.js").read_text(encoding="utf-8")
    modules_js = (root / "static" / "js" / "aliado-modules.js").read_text(encoding="utf-8")

    assert 'src="/static/js/aliado-modules.js"' in aliado
    assert 'src="/static/js/aliado-directorio-module.js"' in aliado
    assert "RuanaAliadoModules" in modules_js
    assert "directorio: null" in modules_js
    assert "RuanaAliadoModules.directorio" in directorio_js or "modules.directorio" in directorio_js
    assert "renderProfesionales" in directorio_js
    assert "codigosConConversacionActiva" in directorio_js
    assert "scoreEtiquetaMeta" in directorio_js
    assert "directorio-search" in directorio_js
    assert "profesionales-list" in directorio_js
    # Fachadas delgadas en PrivatePanel
    assert "_directorioModule" in aliado
    assert "mod.renderProfesionales(this)" in aliado
    assert "mod.codigosConConversacionActiva(this)" in aliado
    assert "mod.scoreEtiquetaMeta(score, estadoRuana)" in aliado
    # Markup del directorio permanece en aliado.html (sin reescritura masiva)
    assert 'id="module-directorio"' in aliado
    assert 'id="directorio-search"' in aliado
    assert 'id="profesionales-list"' in aliado


def test_aliado_solicitudes_module_is_wired():
    """Módulo PrivatePanel `solicitudes` (entrantes/propias/historial); PrivatePanel solo fachada."""
    root = Path(__file__).resolve().parents[1] / "web"
    aliado = (root / "aliado.html").read_text(encoding="utf-8")
    solicitudes_js = (root / "static" / "js" / "aliado-solicitudes-module.js").read_text(encoding="utf-8")
    modules_js = (root / "static" / "js" / "aliado-modules.js").read_text(encoding="utf-8")

    assert 'src="/static/js/aliado-modules.js"' in aliado
    assert '/static/js/aliado-solicitudes-module.js' in aliado
    assert "RuanaAliadoModules" in modules_js
    assert "solicitudes: null" in modules_js
    assert "RuanaAliadoModules.solicitudes" in solicitudes_js or "modules.solicitudes" in solicitudes_js
    assert "renderSolicitudes" in solicitudes_js
    assert "appendSolicitudCard" in solicitudes_js
    assert "solicitudes-list" in solicitudes_js
    assert "btn-conocer" in solicitudes_js
    # Fachadas delgadas en PrivatePanel
    assert "_solicitudesModule" in aliado
    assert "mod.renderSolicitudes(this)" in aliado
    assert "mod.appendSolicitudCard(this, container, solicitud, conBotonConocer)" in aliado
    # Markup de solicitudes permanece en aliado.html (sin reescritura masiva)
    assert 'id="module-solicitudes"' in aliado
    assert 'id="solicitudes-list"' in aliado
    assert 'id="solicitudes-propias-list"' in aliado
    assert 'solicitudes-historial-list' in aliado
    assert 'data-solicitudes-count' in solicitudes_js
    assert 'solicitudes-group-header' in solicitudes_js
    assert 'semMod.renderSeccion' in solicitudes_js
    assert "contactosMod.renderEncargosActivos(host)" in solicitudes_js


def test_aliado_solicitudes_panel_refresca_al_abrir_y_modulos_visibles():
    """El panel Solicitudes se ve al activarlo y recarga semanales/encargos/enviadas/historial."""
    root = Path(__file__).resolve().parents[1] / "web"
    aliado = (root / "aliado.html").read_text(encoding="utf-8")
    shell_js = (root / "static" / "js" / "aliado-shell.js").read_text(encoding="utf-8")
    shell_css = (root / "static" / "css" / "aliado-shell.css").read_text(encoding="utf-8")
    sync_js = (root / "static" / "js" / "aliado-sync-module.js").read_text(encoding="utf-8")

    for section_id in (
        "solicitudes-semanales-wrap",
        "solicitudes-encargos-wrap",
        "solicitudes-entrantes-wrap",
        "solicitudes-propias-wrap",
        "solicitudes-historial-wrap",
        "encargos-activos-list",
        "solicitudes-propias-list",
        "solicitudes-historial-list",
    ):
        assert f'id="{section_id}"' in aliado

    assert "function refreshSolicitudesPanel()" in shell_js
    assert "previous !== 'solicitudes'" in shell_js
    assert "refreshAfterAction(['solicitudes', 'contactos'])" in shell_js
    assert "refreshSolicitudes: refreshSolicitudesPanel" in shell_js
    assert "'#solicitudes-semanales-wrap': 'solicitudes'" in shell_js
    assert "'#solicitudes-historial-wrap': 'solicitudes'" in shell_js

    assert "animation: aliado-module-in 280ms ease both;" in shell_css
    active_block = shell_css.split(".aliado-module.is-active")[1].split("}")[0]
    assert "animation: aliado-module-in" in active_block
    assert "opacity: 1" in active_block
    base_block = shell_css.split(".aliado-module {")[1].split("}")[0]
    assert "animation:" not in base_block

    assert "semMod.fetchSnapshot(host)" in sync_js
    assert "semanalesTask" in sync_js
    assert "targetSections.includes('solicitudes') && !targetSections.includes('contactos')" in sync_js


def test_aliado_acuerdos_module_is_wired():
    """Módulo PrivatePanel `acuerdos` (Mis acuerdos); PrivatePanel solo fachada."""
    root = Path(__file__).resolve().parents[1] / "web"
    aliado = (root / "aliado.html").read_text(encoding="utf-8")
    acuerdos_js = (root / "static" / "js" / "aliado-acuerdos-module.js").read_text(encoding="utf-8")
    modules_js = (root / "static" / "js" / "aliado-modules.js").read_text(encoding="utf-8")

    assert 'src="/static/js/aliado-modules.js"' in aliado
    assert 'src="/static/js/aliado-acuerdos-module.js"' in aliado
    assert "RuanaAliadoModules" in modules_js
    assert "acuerdos: null" in modules_js
    assert "RuanaAliadoModules.acuerdos" in acuerdos_js or "modules.acuerdos" in acuerdos_js
    assert "cargarMisAcuerdos" in acuerdos_js
    assert "renderMisAcuerdos" in acuerdos_js
    assert "mis-acuerdos-lista" in acuerdos_js
    assert "/api/aliado/acuerdos" in acuerdos_js
    # Fachadas delgadas en PrivatePanel
    assert "_acuerdosModule" in aliado
    assert "mod.cargarMisAcuerdos(this)" in aliado
    assert "mod.renderMisAcuerdos(this)" in aliado
    assert "mod.toggleMisAcuerdoExpandido(this, contactoId)" in aliado
    # Markup permanece en aliado.html
    assert 'id="mis-acuerdos-wrap"' in aliado
    assert 'id="mis-acuerdos-lista"' in aliado
    assert 'id="mis-acuerdos-filtros"' in aliado


def test_aliado_centro_comunicacion_module_is_wired():
    """Módulo PrivatePanel `centroComunicacion` (FAB soporte); PrivatePanel solo fachada."""
    root = Path(__file__).resolve().parents[1] / "web"
    aliado = (root / "aliado.html").read_text(encoding="utf-8")
    centro_js = (root / "static" / "js" / "aliado-centro-comunicacion-module.js").read_text(
        encoding="utf-8"
    )
    modules_js = (root / "static" / "js" / "aliado-modules.js").read_text(encoding="utf-8")

    assert 'src="/static/js/aliado-modules.js"' in aliado
    assert 'src="/static/js/aliado-centro-comunicacion-module.js"' in aliado
    assert "RuanaAliadoModules" in modules_js
    assert "centroComunicacion: null" in modules_js
    assert (
        "RuanaAliadoModules.centroComunicacion" in centro_js
        or "modules.centroComunicacion" in centro_js
    )
    assert "renderCentroComunicacion" in centro_js
    assert "abrirCentroComunicacion" in centro_js
    assert "enviarNuevoMensajeSoporte" in centro_js
    assert "ruana-help-threads" in centro_js
    assert "/centro-comunicacion" in centro_js
    # Fachadas delgadas en PrivatePanel
    assert "_centroComunicacionModule" in aliado
    assert "mod.renderCentroComunicacion(this)" in aliado
    assert "mod.toggleCentroComunicacion(this)" in aliado
    assert "mod.enviarNuevoMensajeSoporte(this)" in aliado
    # Markup permanece en aliado.html
    assert 'id="ruana-help-fab"' in aliado
    assert 'id="ruana-help-overlay"' in aliado
    assert 'id="ruana-help-threads"' in aliado


def test_aliado_conexiones_module_is_wired():
    """Módulo PrivatePanel `conexiones` (enviar solicitud); PrivatePanel solo fachada."""
    root = Path(__file__).resolve().parents[1] / "web"
    aliado = (root / "aliado.html").read_text(encoding="utf-8")
    conexiones_js = (root / "static" / "js" / "aliado-conexiones-module.js").read_text(
        encoding="utf-8"
    )
    modules_js = (root / "static" / "js" / "aliado-modules.js").read_text(encoding="utf-8")

    assert 'src="/static/js/aliado-modules.js"' in aliado
    assert 'src="/static/js/aliado-conexiones-module.js"' in aliado
    assert "RuanaAliadoModules" in modules_js
    assert "conexiones: null" in modules_js
    assert (
        "RuanaAliadoModules.conexiones" in conexiones_js
        or "modules.conexiones" in conexiones_js
    )
    assert "handleEnviarSolicitud" in conexiones_js
    assert "/api/solicitudes" in conexiones_js
    assert "nueva-solicitud-oficio" in conexiones_js
    # Fachadas delgadas en PrivatePanel
    assert "_conexionesModule" in aliado
    assert "mod.handleEnviarSolicitud(this)" in aliado
    # Markup permanece en aliado.html
    assert 'id="module-conexiones"' in aliado
    assert 'id="nueva-solicitud-oficio"' in aliado
    assert 'id="btn-enviar"' in aliado


def test_aliado_invitaciones_module_is_wired():
    """Módulo PrivatePanel `invitaciones`; PrivatePanel solo fachada."""
    root = Path(__file__).resolve().parents[1] / "web"
    aliado = (root / "aliado.html").read_text(encoding="utf-8")
    inv_js = (root / "static" / "js" / "aliado-invitaciones-module.js").read_text(encoding="utf-8")
    modules_js = (root / "static" / "js" / "aliado-modules.js").read_text(encoding="utf-8")

    assert 'src="/static/js/aliado-invitaciones-module.js"' in aliado
    assert "invitaciones: null" in modules_js
    assert "modules.invitaciones" in inv_js or "RuanaAliadoModules.invitaciones" in inv_js
    assert "generarCodigoInvitacionPerfil" in inv_js
    assert "generateInviteCode" in inv_js
    assert "/api/invitaciones/crear" in inv_js
    assert "generarInvitacionOficio" in inv_js
    assert "_invitacionesModule" in aliado
    assert "mod.generateInviteCode(this, solicitudId)" in aliado
    assert 'id="modal-code"' in aliado
    assert 'id="modal-invitacion-oficio"' in aliado


def test_aliado_alertas_module_is_wired():
    """Módulo PrivatePanel `alertas` (hub + apoyo + impugnación); solo fachada."""
    root = Path(__file__).resolve().parents[1] / "web"
    aliado = (root / "aliado.html").read_text(encoding="utf-8")
    alertas_js = (root / "static" / "js" / "aliado-alertas-module.js").read_text(encoding="utf-8")
    modules_js = (root / "static" / "js" / "aliado-modules.js").read_text(encoding="utf-8")

    assert 'src="/static/js/aliado-alertas-module.js"' in aliado
    assert "alertas: null" in modules_js
    assert "modules.alertas" in alertas_js or "RuanaAliadoModules.alertas" in alertas_js
    assert "renderAlertHub" in alertas_js
    assert "abrirModalPagoApoyo" in alertas_js
    assert "impugnarApoyoRuana" in alertas_js
    assert "enviarComprobanteApoyo" in alertas_js
    assert "_alertasModule" in aliado
    assert "mod.renderAlertHub(this)" in aliado
    assert "mod.abrirModalPagoApoyo(this, contactoId, apoyoRuana, servicio)" in aliado
    assert 'id="ruana-alert-hub"' in aliado
    assert "renderAlertHub(host)" in alertas_js
    assert "renderAlertDetailPanel(host, detailEl, detailId)" in alertas_js
    assert "const self = this" not in alertas_js
    assert 'id="modal-pago-apoyo"' in aliado
    assert 'id="modal-impugnar-apoyo"' in aliado


def test_aliado_catalogo_contactos_grupo_sync_modules_are_wired():
    """Módulos catalogo / contactos / grupo / sync / events cableados con fachadas."""
    root = Path(__file__).resolve().parents[1] / "web"
    aliado = (root / "aliado.html").read_text(encoding="utf-8")
    modules_js = (root / "static" / "js" / "aliado-modules.js").read_text(encoding="utf-8")
    catalogo = (root / "static" / "js" / "aliado-catalogo-module.js").read_text(encoding="utf-8")
    contactos = (root / "static" / "js" / "aliado-contactos-module.js").read_text(encoding="utf-8")
    grupo = (root / "static" / "js" / "aliado-grupo-module.js").read_text(encoding="utf-8")
    sync = (root / "static" / "js" / "aliado-sync-module.js").read_text(encoding="utf-8")
    events = (root / "static" / "js" / "aliado-events-module.js").read_text(encoding="utf-8")

    for src in (
        "aliado-catalogo-module.js",
        "aliado-contactos-module.js",
        "aliado-grupo-module.js",
        "aliado-sync-module.js",
        "aliado-events-module.js",
    ):
        assert f'/static/js/{src}' in aliado

    assert "catalogo: null" in modules_js
    assert "contactos: null" in modules_js
    assert "grupo: null" in modules_js
    assert "sync: null" in modules_js
    assert "events: null" in modules_js
    assert "renderCatalogoServicios" in catalogo
    assert "cargarContactosPendientes" in contactos
    assert "renderGrupo" in grupo
    assert "runWarmupSync" in sync
    assert "loadData" in sync
    assert "initState" in sync
    assert "bootstrapPrivatePanel" in sync
    assert "global.PrivatePanel" in sync
    assert "bootstrapPrivatePanel();" in sync
    assert "setupEventListeners" in events
    assert "_catalogoModule" in aliado
    assert "_contactosModule" in aliado
    assert "_grupoModule" in aliado
    assert "_syncModule" in aliado
    assert "_eventsModule" in aliado
    assert "mod.loadData(this)" in aliado
    assert "mod.renderGrupo(this)" in aliado
    assert "mod.setupEventListeners(this)" in aliado
    # Bootstrap: inline define PrivatePanel; sync-module (defer) lo invoca al cargar
    assert "window.PrivatePanel = PrivatePanel" in aliado
    assert "RuanaAliadoModules.sync.bootstrapPrivatePanel()" not in aliado


def test_solicitudes_semanales_prompt_solo_lunes_y_minimizado_persiste():
    """El prompt semanal solo auto-abre el lunes; 'minimized' no reabre el overlay."""
    root = Path(__file__).resolve().parents[1] / "web"
    sem_js = (
        root / "static" / "js" / "aliado-solicitudes-semanales-module.js"
    ).read_text(encoding="utf-8")

    assert "function esLunesLocal()" in sem_js
    assert "st === 'minimized' && !opts.forceFull" in sem_js
    assert "!opts.forceFull && !esLunesLocal()" in sem_js
    assert "forceFull: true" in sem_js
    assert "host._solSemUiBound" in sem_js
    assert "st === 'hidden'" in sem_js
    assert "ocultarPromptCrear(host)" in sem_js
    assert "mostrarMinimizado(host)" in sem_js


def test_solicitudes_semanales_recuadro_inicio_panel():
    """Las solicitudes semanales se acumulan en Inicio y notifican al grupo."""
    root = Path(__file__).resolve().parents[1] / "web"
    aliado = (root / "aliado.html").read_text(encoding="utf-8")
    sem_js = (
        root / "static" / "js" / "aliado-solicitudes-semanales-module.js"
    ).read_text(encoding="utf-8")
    sync_js = (root / "static" / "js" / "aliado-sync-module.js").read_text(encoding="utf-8")

    assert 'id="inicio-solicitudes-semanales-wrap"' in aliado
    assert "Solicitudes de esta semana" in aliado
    assert "function renderInicioSeccion(host)" in sem_js
    assert "renderInicioSeccion: renderInicioSeccion" in sem_js or "renderInicioSeccion," in sem_js
    assert "actualizarModalEntrante: actualizarModalEntrante" in sem_js or "actualizarModalEntrante," in sem_js
    assert "renderInicioSeccion(host)" in sync_js
    assert "actualizarModalEntrante(host)" in sync_js
    assert "asegurarPromptCerradoSiPublicada(host)" in sync_js
    assert "function asegurarPromptCerradoSiPublicada(host)" in sem_js
    assert "ocultarPromptCrear(host)" in sem_js
    assert "limpiarFormularioPrompt()" in sem_js
