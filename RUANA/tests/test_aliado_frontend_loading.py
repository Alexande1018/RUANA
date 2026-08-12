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
    assert "setPanelLoading(false)" in text


def test_aliado_panel_does_not_ship_demo_profile_values():
    aliado_html = Path(__file__).resolve().parents[1] / "web" / "aliado.html"
    text = aliado_html.read_text(encoding="utf-8")

    assert "Juan P" not in text
    assert "JP Instalaciones" not in text
    assert 'id="detail-oficio">Electricidad<' not in text


def test_aliado_solicitudes_initial_load_sends_auth_headers():
    aliado_html = Path(__file__).resolve().parents[1] / "web" / "aliado.html"
    text = aliado_html.read_text(encoding="utf-8")
    start = text.index("fetch(apiBase + '/api/solicitudes?codigo='")
    snippet = text[start : start + 260]

    assert "credentials: 'same-origin'" in snippet
    assert "headers: getRuanaAuthHeaders()" in snippet


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
    assert 'src="/static/js/aliado-shell.js"' in aliado
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
    """Módulo PrivatePanel `referidos` (modal linaje); PrivatePanel solo fachada."""
    root = Path(__file__).resolve().parents[1] / "web"
    aliado = (root / "aliado.html").read_text(encoding="utf-8")
    referidos_js = (root / "static" / "js" / "aliado-referidos-module.js").read_text(encoding="utf-8")
    modules_js = (root / "static" / "js" / "aliado-modules.js").read_text(encoding="utf-8")

    assert 'src="/static/js/aliado-modules.js"' in aliado
    assert 'src="/static/js/aliado-referidos-module.js"' in aliado
    assert "RuanaAliadoModules" in modules_js
    assert "referidos: null" in modules_js
    assert "RuanaAliadoModules.referidos" in referidos_js or "modules.referidos" in referidos_js
    assert "abrirModalLinajeHijos" in referidos_js
    assert "cerrarModalLinajeHijos" in referidos_js
    assert "/api/aliado/linaje/hijos" in referidos_js
    assert "modal-linaje-hijos" in referidos_js
    # Fachadas delgadas en PrivatePanel
    assert "_referidosModule" in aliado
    assert "mod.abrirModalLinajeHijos(this)" in aliado
    assert "mod.cerrarModalLinajeHijos()" in aliado
    # Markup del modal permanece en aliado.html (sin reescritura masiva)
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
    assert 'src="/static/js/aliado-solicitudes-module.js"' in aliado
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
    assert 'id="solicitudes-historial-list"' in aliado
