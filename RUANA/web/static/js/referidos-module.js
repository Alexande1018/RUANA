/**
 * RUANA — Árbol genealógico de referidos (lazy expand + tarjetas enriquecidas).
 *
 * Cableado en admin.html (#red-view-referidos) y aliado.html (modal #modal-linaje-hijos).
 * y en admin-red-explorer-module.js. Exporta `RuanaReferidos` / `RuanaReferidosTree`
 * para bosque admin (loadAdminFull) y árbol aliado (lazy expand + polling).
 * Estilos en referidos-tree.css (tokens ruana-identity.css).
 */
(function (global) {
    'use strict';

    function escapeHtml(str) {
        if (str == null) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function getIniciales(nombre) {
        var parts = String(nombre || '').split(/\s+/).filter(Boolean).slice(0, 2);
        return parts.map(function (p) { return p[0]; }).join('').toUpperCase() || '?';
    }

    function formatFecha(iso) {
        if (!iso) return '—';
        try {
            var d = new Date(iso);
            if (isNaN(d.getTime())) return '—';
            return d.toLocaleDateString('es-ES', { day: '2-digit', month: 'short', year: 'numeric' });
        } catch (e) {
            return '—';
        }
    }

    var GEN_NODE_W = 108;
    var GEN_NODE_H = 128;
    var GEN_H_GAP = 28;
    var GEN_V_GAP = 72;
    var GEN_FOREST_GAP = 48;

    function buildAvatarHtml(nodo, className) {
        className = className || 'referidos-gen-avatar';
        var foto = (nodo.foto_perfil_url || nodo.foto_perfil || '').trim();
        var iniciales = getIniciales(nodo.nombre);
        if (foto) {
            return '<div class="' + className + ' referidos-gen-avatar-photo">' +
                '<img src="' + escapeHtml(foto) + '" alt="" loading="lazy">' +
                '</div>';
        }
        return '<div class="' + className + '" aria-hidden="true">' + escapeHtml(iniciales) + '</div>';
    }

    function measureGenealogyTree(nodo) {
        var children = (nodo && nodo.referidos) ? nodo.referidos.filter(Boolean) : [];
        if (!children.length) {
            return { width: GEN_NODE_W, nodo: nodo, children: [] };
        }
        var childLayouts = children.map(measureGenealogyTree);
        var totalW = childLayouts.reduce(function (sum, cl) { return sum + cl.width; }, 0);
        totalW += GEN_H_GAP * Math.max(0, childLayouts.length - 1);
        return {
            width: Math.max(GEN_NODE_W, totalW),
            nodo: nodo,
            children: childLayouts
        };
    }

    function layoutGenealogyTree(layout, x, y, depth, positions, connectors) {
        if (!layout) return;
        var nodeX = x + layout.width / 2;
        positions.push({ nodo: layout.nodo, x: nodeX, y: y, depth: depth });
        if (!layout.children.length) return;

        var childY = y + GEN_NODE_H + GEN_V_GAP;
        var cx = x;
        var childCenters = [];
        layout.children.forEach(function (cl) {
            layoutGenealogyTree(cl, cx, childY, depth + 1, positions, connectors);
            childCenters.push(cx + cl.width / 2);
            cx += cl.width + GEN_H_GAP;
        });
        connectors.push({
            fromX: nodeX,
            fromY: y + 52,
            childCenters: childCenters,
            childY: childY
        });
    }

    function buildGenealogyNodeHtml(nodo, selectedCodigo) {
        var isVirtual = isVirtualNodo(nodo);
        var selected = selectedCodigo === nodo.codigo;
        var fecha = formatFecha(nodo.creado_en || nodo.referido_en);
        var nombre = nodo.nombre || (isVirtual ? 'Categoría' : '(sin nombre)');
        var subtitulo = isVirtual
            ? (nodo.oficio || 'Agrupación')
            : (nodo.oficio || '—');
        var extraClass = (selected ? ' selected' : '') +
            (isVirtual ? ' is-virtual' : '') +
            (nodo.estado === 'sistema' ? ' is-admin' : '') +
            (nodo.perfil_eliminado ? ' is-eliminado' : '') +
            (nodo.perfil_pausado ? ' is-pausado' : '') +
            (nodo.pendiente_alta ? ' pendiente-alta' : '');

        var avatarHtml = isVirtual
            ? '<div class="referidos-gen-avatar is-virtual-icon" aria-hidden="true">◉</div>'
            : buildAvatarHtml(nodo, 'referidos-gen-avatar');

        return (
            '<div class="referidos-gen-node' + extraClass + '" role="button" tabindex="0" data-codigo="' + escapeHtml(nodo.codigo) + '">' +
            avatarHtml +
            '<div class="referidos-gen-nombre" title="' + escapeHtml(nombre) + '">' + escapeHtml(nombre) + '</div>' +
            '<div class="referidos-gen-fecha">' + escapeHtml(isVirtual ? subtitulo : fecha) + '</div>' +
            (!isVirtual ? '<div class="referidos-gen-oficio">' + escapeHtml(subtitulo) + '</div>' : '') +
            '</div>'
        );
    }

    function renderGenealogySvg(connectors, width, height) {
        var paths = '';
        connectors.forEach(function (c) {
            if (!c.childCenters.length) return;
            var midY = c.fromY + (c.childY - c.fromY) * 0.45;
            paths += '<path class="referidos-gen-line" d="M' + c.fromX + ' ' + c.fromY + ' V' + midY + '"/>';
            if (c.childCenters.length === 1) {
                paths += '<path class="referidos-gen-line" d="M' + c.fromX + ' ' + midY + ' V' + c.childY + '"/>';
            } else {
                var minX = Math.min.apply(null, c.childCenters);
                var maxX = Math.max.apply(null, c.childCenters);
                paths += '<path class="referidos-gen-line" d="M' + minX + ' ' + midY + ' H' + maxX + '"/>';
                c.childCenters.forEach(function (cx) {
                    paths += '<path class="referidos-gen-line" d="M' + cx + ' ' + midY + ' V' + c.childY + '"/>';
                });
            }
        });
        return '<svg class="referidos-genealogy-svg" width="' + width + '" height="' + height + '" aria-hidden="true">' + paths + '</svg>';
    }

    function indexGenealogyNodes(nodo, map, invitadoresMap, invitador) {
        if (!nodo || !nodo.codigo) return;
        map[nodo.codigo] = nodo;
        if (invitador && invitador.codigo) {
            invitadoresMap[nodo.codigo] = invitador;
        }
        (nodo.referidos || []).forEach(function (hijo) {
            indexGenealogyNodes(hijo, map, invitadoresMap, nodo);
        });
    }

    function isVirtualNodo(nodo) {
        if (!nodo) return false;
        var codigo = String(nodo.codigo || '');
        return !!(
            nodo.virtual === true ||
            nodo.estado === 'virtual' ||
            nodo.tipo_nodo === 'campana' ||
            nodo.tipo_nodo === 'sin_atribucion' ||
            nodo.tipo_nodo === 'pendiente_vinculo' ||
            codigo.indexOf('__') === 0
        );
    }

    function applyDetailPanelClass(container, mode) {
        if (!container) return;
        var isFloat = !!(container.closest && container.closest('.referidos-detail-float-wrap'));
        if (mode === 'empty') {
            container.className = 'referidos-detail-panel empty' + (isFloat ? ' referidos-detail-float' : '');
            return;
        }
        container.className = 'referidos-detail-panel' + (isFloat ? ' referidos-detail-float' : '');
    }

    function findFirstSelectableCodigo(bosques) {
        var queue = (bosques || []).slice();
        while (queue.length) {
            var n = queue.shift();
            if (n && n.codigo && !isVirtualNodo(n)) return n.codigo;
            (n.referidos || []).forEach(function (h) { queue.push(h); });
        }
        return bosques && bosques[0] ? bosques[0].codigo : null;
    }

    function explorerSvgIcon(pathD) {
        return '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">' +
            pathD + '</svg>';
    }

    function origenLabel(origen, origenLabelField) {
        if (origenLabelField) return origenLabelField;
        var map = {
            aliado: 'Invitación de aliado',
            ampliar_red: 'Ampliar mi red',
            yo_conozco_a_alguien: 'Conozco a alguien',
            oficio: 'Invitación por oficio',
            campana: 'Campaña del administrador',
            admin_invitacion: 'Código del administrador',
            organico: 'Registro orgánico',
            huerfano: 'Sin atribución',
            sin_atribucion: 'Sin atribución'
        };
        return map[String(origen || '').toLowerCase()] || '';
    }

    function estadoLabel(estado, pendienteAlta) {
        if (pendienteAlta) return 'Pendiente de completar alta';
        var e = String(estado || 'activo').toLowerCase();
        if (e === 'sistema') return 'Admin RUANA';
        if (e === 'pendiente_validacion') return 'Pendiente';
        if (e === 'pendiente_completar') return 'Pendiente de completar alta';
        if (e === 'suspendido_temporal') return 'Pausado';
        if (e === 'eliminado') return 'Usuario eliminado';
        if (e === 'virtual') return 'Categoría';
        if (e === 'expulsado') return 'Expulsado';
        if (e === 'rechazado') return 'Rechazado';
        return 'Activo';
    }

    function estadoClass(estado, pendienteAlta) {
        if (pendienteAlta) return 'pendiente-alta-label';
        var e = String(estado || 'activo').toLowerCase();
        if (e === 'sistema') return 'sistema';
        if (e === 'pendiente_validacion' || e === 'pendiente_completar') return 'pendiente';
        if (e === 'suspendido_temporal' || e === 'expulsado' || e === 'rechazado') return 'riesgo';
        if (e === 'eliminado') return 'eliminado';
        if (e === 'observacion') return 'observacion';
        return 'activo';
    }

    function indexarNodo(nodo, map, invitadoresMap, invitador) {
        if (!nodo || !nodo.codigo) return;
        map[nodo.codigo] = nodo;
        if (invitador && invitador.codigo) {
            invitadoresMap[nodo.codigo] = invitador;
        }
    }

    function renderDetailPanel(container, nodo, invitador, options) {
        options = options || {};
        if (!container) return;
        if (!nodo) {
            applyDetailPanelClass(container, 'empty');
            container.innerHTML = '<p>Selecciona un aliado en el árbol para ver su ficha.</p>';
            return;
        }
        applyDetailPanelClass(container, 'content');
        var esp = Array.isArray(nodo.especializaciones) ? nodo.especializaciones.join(', ') : '—';
        var contacto = (nodo.telefono || '') + (nodo.email ? (nodo.telefono ? ' • ' : '') + nodo.email : '');
        if (!contacto) contacto = '—';
        var referidosCount = nodo.referidos_count != null ? nodo.referidos_count : 0;

        var invitadorHtml = '';
        if (invitador && invitador.codigo) {
            invitadorHtml =
                '<div class="referidos-detail-invitador">' +
                '<div class="referidos-detail-invitador-label">Invitado por</div>' +
                '<button type="button" class="referidos-detail-invitador-link" data-invitador-codigo="' + escapeHtml(invitador.codigo) + '">' +
                escapeHtml(invitador.nombre || invitador.codigo) + ' · ' + escapeHtml(invitador.oficio || '') +
                '</button></div>';
        }
        var origenTexto = origenLabel(nodo.origen, nodo.origen_label);
        var origenHtml = origenTexto
            ? '<div class="referidos-detail-origen"><span class="referidos-detail-invitador-label">Origen</span>' +
              '<span class="referidos-origen-badge">' + escapeHtml(origenTexto) + '</span></div>'
            : '';

        var adminActions = '';
        if (options.mode === 'admin' && !isVirtualNodo(nodo)) {
            var accionesAdmin = '';
            if (!nodo.perfil_eliminado && String(nodo.estado || '').toLowerCase() !== 'eliminado') {
                accionesAdmin +=
                    '<button type="button" class="btn-accion referidos-btn-pausar">Pausar aliado</button>' +
                    '<button type="button" class="btn-accion danger referidos-btn-eliminar">Eliminar perfil</button>';
            }
            adminActions =
                '<div class="referidos-detail-actions">' +
                '<button type="button" class="btn-accion referidos-btn-ver-detalle">Ver detalle completo</button>' +
                '<button type="button" class="btn-accion referidos-btn-centrar">Centrar árbol aquí</button>' +
                accionesAdmin +
                '</div>';
        } else if (options.mode === 'admin' && typeof options.onVerDetalleCompleto === 'function') {
            adminActions =
                '<div class="referidos-detail-actions">' +
                '<button type="button" class="btn-accion referidos-btn-ver-detalle">Ver detalle completo</button>' +
                '<button type="button" class="btn-accion referidos-btn-centrar">Centrar árbol aquí</button>' +
                '</div>';
        }

        container.innerHTML =
            '<div class="referidos-detail-header">' +
            '<div class="referidos-detail-avatar" aria-hidden="true">' + escapeHtml(getIniciales(nodo.nombre)) + '</div>' +
            '<div><div class="referidos-detail-nombre">' + escapeHtml(nodo.nombre || '') + '</div>' +
            '<div class="referidos-detail-sub">' + escapeHtml(nodo.codigo || '') + ' · ' + escapeHtml(nodo.oficio || '') + '</div></div></div>' +
            '<div class="referidos-detail-grid">' +
            '<div class="referidos-detail-item"><span class="info-label">Zona</span><span class="info-value">' + escapeHtml(nodo.zona || nodo.codigo_postal || '—') + '</span></div>' +
            '<div class="referidos-detail-item"><span class="info-label">Marca</span><span class="info-value">' + escapeHtml(nodo.marca || '—') + '</span></div>' +
            '<div class="referidos-detail-item"><span class="info-label">Score</span><span class="info-value">' + escapeHtml(String(nodo.score != null ? nodo.score : '—')) + '</span></div>' +
            '<div class="referidos-detail-item"><span class="info-label">Estado</span><span class="info-value">' + escapeHtml(estadoLabel(nodo.estado, nodo.pendiente_alta)) + '</span></div>' +
            '<div class="referidos-detail-item"><span class="info-label">Referidos directos</span><span class="info-value">' + escapeHtml(String(referidosCount)) + '</span></div>' +
            '<div class="referidos-detail-item"><span class="info-label">Registro</span><span class="info-value">' + escapeHtml(formatFecha(nodo.creado_en || nodo.referido_en)) + '</span></div>' +
            (options.mode === 'admin'
                ? '<div class="referidos-detail-item referidos-detail-wide"><span class="info-label">Contacto</span><span class="info-value">' + escapeHtml(contacto) + '</span></div>' +
                  '<div class="referidos-detail-item referidos-detail-wide"><span class="info-label">Especialidades</span><span class="info-value">' + escapeHtml(esp) + '</span></div>'
                : '') +
            '</div>' +
            invitadorHtml +
            origenHtml +
            adminActions;

        var invBtn = container.querySelector('.referidos-detail-invitador-link');
        if (invBtn && typeof options.onSelectCodigo === 'function') {
            invBtn.addEventListener('click', function () {
                options.onSelectCodigo(invitador.codigo, invitador);
            });
        }
        var verDetalle = container.querySelector('.referidos-btn-ver-detalle');
        if (verDetalle && options.onVerDetalleCompleto) {
            verDetalle.addEventListener('click', function () { options.onVerDetalleCompleto(nodo); });
        }
        var centrar = container.querySelector('.referidos-btn-centrar');
        if (centrar && options.onCentrarArbol) {
            centrar.addEventListener('click', function () { options.onCentrarArbol(nodo.codigo); });
        }
        var pausarBtn = container.querySelector('.referidos-btn-pausar');
        if (pausarBtn && typeof options.onPausarAliado === 'function') {
            pausarBtn.addEventListener('click', function () { options.onPausarAliado(nodo); });
        }
        var eliminarBtn = container.querySelector('.referidos-btn-eliminar');
        if (eliminarBtn && typeof options.onEliminarAliado === 'function') {
            eliminarBtn.addEventListener('click', function () { options.onEliminarAliado(nodo); });
        }
    }

    function RuanaReferidosTree(config) {
        this.treeContainer = config.treeContainer;
        this.detailContainer = config.detailContainer;
        this.metaContainer = config.metaContainer || null;
        this.fetchOptions = config.fetchOptions || {};
        this.mode = config.mode || 'aliado';
        this.onVerDetalleCompleto = config.onVerDetalleCompleto || null;
        this.onCentrarArbol = config.onCentrarArbol || null;
        this.apiRaices = config.apiRaices || '/api/admin/referidos/raices';
        this.apiRaiz = config.apiRaiz || '/api/aliado/referidos/raiz';
        this.apiHijos = config.apiHijos || (this.mode === 'admin' ? '/api/admin/referidos/hijos/' : '/api/aliado/referidos/hijos/');
        this.apiRuta = config.apiRuta || '/api/admin/referidos/ruta/';
        this.apiBuscar = config.apiBuscar || '/api/admin/referidos/buscar';
        this.apiCambios = config.apiCambios || (this.mode === 'admin'
            ? '/api/admin/referidos/cambios'
            : '/api/aliado/referidos/cambios');
        this.apiDetalle = config.apiDetalle || (this.mode === 'admin'
            ? '/api/admin/referidos/aliado/'
            : '/api/aliado/referidos/aliado/');
        this.onPausarAliado = config.onPausarAliado || null;
        this.onEliminarAliado = config.onEliminarAliado || null;
        this.pollIntervalMs = config.pollIntervalMs || 15000;

        this._nodosMap = {};
        this._invitadoresMap = {};
        this._childrenCache = {};
        this._expanded = {};
        this._selectedCodigo = null;
        this._totalNodos = 0;
        this._knownReferidos = {};
        this._lastSyncAt = null;
        this._pollTimer = null;
        this._pollInFlight = false;

        this._explorerReady = false;
        this._explorerRoot = null;
        this._panViewport = null;
        this._panLayer = null;
        this._detailFloatWrap = null;
        this._panX = 0;
        this._panY = 0;
        this._initExplorerChrome();
    }

    RuanaReferidosTree.prototype._getTreeRenderTarget = function () {
        return this._ensurePanShell() || this.treeContainer;
    };

    RuanaReferidosTree.prototype._ensurePanShell = function () {
        if (!this.treeContainer) return null;
        if (this._panLayer && this.treeContainer.contains(this._panLayer)) {
            return this._panLayer;
        }
        this.treeContainer.classList.add('referidos-explorer-viewport');
        var panViewport = document.createElement('div');
        panViewport.className = 'referidos-pan-viewport';
        var panLayer = document.createElement('div');
        panLayer.className = 'referidos-pan-layer';
        panViewport.appendChild(panLayer);
        this.treeContainer.innerHTML = '';
        this.treeContainer.appendChild(panViewport);
        this._panViewport = panViewport;
        this._panLayer = panLayer;
        this._panX = 0;
        this._panY = 0;
        this._bindPanHandlers();
        return panLayer;
    };

    RuanaReferidosTree.prototype._clearTreeRenderTarget = function () {
        var target = this._getTreeRenderTarget();
        if (target) target.innerHTML = '';
    };

    RuanaReferidosTree.prototype._showTreeError = function (msg) {
        var target = this._getTreeRenderTarget();
        if (target) {
            target.innerHTML = '<div class="referidos-empty-state">' + escapeHtml(msg || 'Error de conexión') + '</div>';
        }
    };

    RuanaReferidosTree.prototype._applyPanTransform = function () {
        if (!this._panLayer) return;
        this._panLayer.style.transform = 'translate(' + this._panX + 'px, ' + this._panY + 'px)';
    };

    RuanaReferidosTree.prototype._resetPanView = function () {
        this._panX = 0;
        this._panY = 0;
        this._applyPanTransform();
    };

    RuanaReferidosTree.prototype._resolveDetailFloatWrap = function () {
        if (this._detailFloatWrap && document.body.contains(this._detailFloatWrap)) {
            return this._detailFloatWrap;
        }
        if (this.detailContainer) {
            this._detailFloatWrap = this.detailContainer.closest('.referidos-detail-float-wrap');
        }
        return this._detailFloatWrap || null;
    };

    RuanaReferidosTree.prototype._updateDetailFloatVisibility = function () {
        var wrap = this._resolveDetailFloatWrap();
        if (!wrap) return;
        var nodo = this._selectedCodigo && this._nodosMap[this._selectedCodigo];
        var show = !!(nodo && !isVirtualNodo(nodo));
        wrap.classList.toggle('is-visible', show);
        wrap.setAttribute('aria-hidden', show ? 'false' : 'true');
    };

    RuanaReferidosTree.prototype._clearDetailSelection = function () {
        this._selectedCodigo = null;
        if (this.treeContainer) {
            this.treeContainer.querySelectorAll('.referidos-gen-node.selected, .referidos-node-card.selected')
                .forEach(function (el) { el.classList.remove('selected'); });
        }
        renderDetailPanel(this.detailContainer, null);
        this._updateDetailFloatVisibility();
    };

    RuanaReferidosTree.prototype._bindPanHandlers = function () {
        var self = this;
        var viewport = this._panViewport;
        if (!viewport || viewport._panBound) return;
        viewport._panBound = true;

        var dragging = false;
        var startX = 0;
        var startY = 0;
        var origPanX = 0;
        var origPanY = 0;

        function canPanTarget(target) {
            return !target.closest('.referidos-gen-node') &&
                !target.closest('.referidos-explorer-toolbar') &&
                !target.closest('.referidos-detail-float-wrap');
        }

        function onPointerDown(e) {
            if (!canPanTarget(e.target)) return;
            if (e.pointerType === 'mouse' && e.button !== 0) return;
            dragging = true;
            viewport.classList.add('is-panning');
            startX = e.clientX;
            startY = e.clientY;
            origPanX = self._panX;
            origPanY = self._panY;
            if (viewport.setPointerCapture) {
                try { viewport.setPointerCapture(e.pointerId); } catch (err) { /* noop */ }
            }
            e.preventDefault();
        }

        function onPointerMove(e) {
            if (!dragging) return;
            self._panX = origPanX + (e.clientX - startX);
            self._panY = origPanY + (e.clientY - startY);
            self._applyPanTransform();
        }

        function onPointerUp(e) {
            if (!dragging) return;
            dragging = false;
            viewport.classList.remove('is-panning');
            if (viewport.releasePointerCapture) {
                try { viewport.releasePointerCapture(e.pointerId); } catch (err) { /* noop */ }
            }
        }

        viewport.addEventListener('pointerdown', onPointerDown);
        viewport.addEventListener('pointermove', onPointerMove);
        viewport.addEventListener('pointerup', onPointerUp);
        viewport.addEventListener('pointercancel', onPointerUp);
    };

    RuanaReferidosTree.prototype._toggleFullscreen = function () {
        var explorer = this._explorerRoot;
        if (!explorer) return;
        var goingFull = !explorer.classList.contains('is-fullscreen');
        explorer.classList.toggle('is-fullscreen', goingFull);
        var req = explorer.requestFullscreen || explorer.webkitRequestFullscreen || explorer.msRequestFullscreen;
        if (goingFull && req) {
            req.call(explorer).catch(function () { /* fallback CSS fullscreen */ });
        } else if (!goingFull && document.fullscreenElement) {
            (document.exitFullscreen || document.webkitExitFullscreen || function () {}).call(document);
        }
        var btn = explorer.querySelector('[data-action="fullscreen"]');
        if (btn) btn.setAttribute('aria-pressed', goingFull ? 'true' : 'false');
    };

    RuanaReferidosTree.prototype._syncFullscreenState = function () {
        if (!this._explorerRoot) return;
        var active = !!document.fullscreenElement || this._explorerRoot.classList.contains('is-fullscreen');
        if (!document.fullscreenElement && this._explorerRoot.classList.contains('is-fullscreen')) {
            /* CSS-only fullscreen still valid until user exits */
        }
        if (!document.fullscreenElement) {
            /* native exited — keep CSS class unless user clicked exit */
        }
        var btn = this._explorerRoot.querySelector('[data-action="fullscreen"]');
        if (btn) btn.setAttribute('aria-pressed', active ? 'true' : 'false');
    };

    RuanaReferidosTree.prototype._bindExplorerToolbar = function (toolbar) {
        var self = this;
        if (!toolbar || toolbar._bound) return;
        toolbar._bound = true;
        toolbar.addEventListener('click', function (e) {
            var btn = e.target.closest('[data-action]');
            if (!btn) return;
            var action = btn.getAttribute('data-action');
            if (action === 'fullscreen') self._toggleFullscreen();
            if (action === 'pan-reset') self._resetPanView();
        });
        document.addEventListener('fullscreenchange', function () {
            if (!self._explorerRoot) return;
            if (!document.fullscreenElement) {
                self._explorerRoot.classList.remove('is-fullscreen');
            }
            self._syncFullscreenState();
        });
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && self._explorerRoot && self._explorerRoot.classList.contains('is-fullscreen')) {
                self._explorerRoot.classList.remove('is-fullscreen');
                if (document.fullscreenElement) document.exitFullscreen().catch(function () {});
            }
        });
    };

    RuanaReferidosTree.prototype._initExplorerChrome = function () {
        if (this._explorerReady || !this.treeContainer) return;
        var layout = this.treeContainer.closest('.referidos-layout');
        if (!layout) return;
        var self = this;

        layout.classList.add('referidos-layout-explorer');

        var explorer = document.createElement('div');
        explorer.className = 'referidos-explorer';

        var toolbar = document.createElement('div');
        toolbar.className = 'referidos-explorer-toolbar';
        toolbar.innerHTML =
            '<div class="referidos-explorer-toolbar-left">' +
            '<button type="button" class="referidos-explorer-btn" data-action="pan-reset" title="Recentrar vista" aria-label="Recentrar vista">' +
            explorerSvgIcon('<path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>') +
            '</button>' +
            '<span class="referidos-explorer-hint">Arrastra en cualquier dirección para navegar · Clic en un aliado para ver su ficha</span>' +
            '</div>' +
            '<button type="button" class="referidos-explorer-btn referidos-explorer-btn-primary" data-action="fullscreen" aria-pressed="false" title="Pantalla completa">' +
            explorerSvgIcon('<path d="M8 3H5a2 2 0 0 0-2 2v3M21 8V5a2 2 0 0 0-2-2h-3M3 16v3a2 2 0 0 0 2 2h3M16 21h3a2 2 0 0 0 2-2v-3"/>') +
            '<span>Pantalla completa</span></button>';

        var stage = document.createElement('div');
        stage.className = 'referidos-explorer-stage';

        this.treeContainer.classList.add('referidos-explorer-viewport');
        stage.appendChild(this.treeContainer);

        if (this.detailContainer) {
            var floatWrap = document.createElement('div');
            floatWrap.className = 'referidos-detail-float-wrap';
            floatWrap.setAttribute('aria-hidden', 'true');
            floatWrap.innerHTML = '<button type="button" class="referidos-detail-float-close" aria-label="Cerrar ficha">×</button>';
            this.detailContainer.classList.add('referidos-detail-float');
            floatWrap.appendChild(this.detailContainer);
            stage.appendChild(floatWrap);
            this._detailFloatWrap = floatWrap;
            floatWrap.querySelector('.referidos-detail-float-close').addEventListener('click', function () {
                self._clearDetailSelection();
            });
        }

        explorer.appendChild(toolbar);
        explorer.appendChild(stage);

        while (layout.firstChild) layout.removeChild(layout.firstChild);
        layout.appendChild(explorer);

        this._explorerRoot = explorer;
        this._ensurePanShell();
        this._bindExplorerToolbar(toolbar);
        this._explorerReady = true;
    };

    RuanaReferidosTree.prototype._fetchJson = function (url) {
        var opts = Object.assign({ credentials: 'same-origin' }, this.fetchOptions || {});
        return fetch(url, opts).then(function (r) {
            return r.json().then(function (data) {
                if (!r.ok && data && !data.message) {
                    data.message = 'Error HTTP ' + r.status;
                }
                if (!r.ok && (!data || data.status !== 'success')) {
                    throw new Error((data && data.message) || ('Error HTTP ' + r.status));
                }
                return data;
            });
        });
    };

    RuanaReferidosTree.prototype._setLoading = function (msg) {
        var target = this._getTreeRenderTarget();
        if (!target) return;
        target.innerHTML =
            '<div class="referidos-loading"><div class="referidos-loading-spinner"></div>' +
            escapeHtml(msg || 'Cargando red de referidos…') + '</div>';
    };

    RuanaReferidosTree.prototype._updateMeta = function (text) {
        if (this.metaContainer && text) {
            this.metaContainer.textContent = text;
        }
    };

    RuanaReferidosTree.prototype._adminMetaText = function (data) {
        var raices = data.total_raices || 0;
        var nodos = data.total_nodos || 0;
        var enRed = data.total_aliados_en_red;
        var fuera = data.aliados_fuera_red;
        var base =
            raices + ' raíz' + (raices !== 1 ? 'es' : '') +
            ' · ' + nodos + ' aliado' + (nodos !== 1 ? 's' : '') + ' en la red';
        if (enRed != null && enRed > 0) {
            base += ' · ' + enRed + ' registrado' + (enRed !== 1 ? 's' : '') + ' en total';
        }
        if (fuera != null && fuera > 0) {
            base += ' · ' + fuera + ' pendiente' + (fuera !== 1 ? 's' : '') + ' de vincular';
        }
        base += ' · Todos los aliados registrados aparecen con su origen';
        return base;
    };

    RuanaReferidosTree.prototype._createNestedRow = function (nodo, depth, invitador) {
        var self = this;
        indexarNodo(nodo, this._nodosMap, this._invitadoresMap, invitador);
        var temp = document.createElement('div');
        temp.innerHTML = this._buildCardHtml(nodo, { depth: depth, isRoot: depth === 0 });
        var row = temp.firstElementChild;
        if (!row) return document.createElement('div');
        var wrap = row.querySelector('.referidos-children-wrap');
        var hijos = nodo.referidos || [];
        if (hijos.length && wrap) {
            wrap.classList.add('expanded');
            var list = document.createElement('div');
            list.className = 'referidos-children-list';
            hijos.forEach(function (hijo) {
                list.appendChild(self._createNestedRow(hijo, depth + 1, nodo));
            });
            wrap.appendChild(list);
            this._expanded[nodo.codigo] = true;
            this._childrenCache[nodo.codigo] = hijos;
        }
        return row;
    };

    RuanaReferidosTree.prototype._renderGenealogyForest = function (bosques, container) {
        var self = this;
        var target = this._getTreeRenderTarget();
        target.innerHTML = '<div class="referidos-genealogy-scroll"><div class="referidos-genealogy-forest"></div></div>';
        var forest = target.querySelector('.referidos-genealogy-forest');
        if (!bosques || !bosques.length) {
            forest.innerHTML = '<div class="referidos-empty-state">No hay aliados registrados en la red.</div>';
            return;
        }

        self._nodosMap = {};
        self._invitadoresMap = {};
        bosques.forEach(function (root) {
            indexGenealogyNodes(root, self._nodosMap, self._invitadoresMap, null);
        });

        var offsetY = 0;
        var maxForestWidth = 0;
        bosques.forEach(function (root, idx) {
            var layout = measureGenealogyTree(root);
            var positions = [];
            var connectors = [];
            layoutGenealogyTree(layout, 0, 24, 0, positions, connectors);
            var treeWidth = Math.max(layout.width + 48, 320);
            var treeHeight = 24 + GEN_NODE_H;
            positions.forEach(function (p) {
                treeHeight = Math.max(treeHeight, p.y + GEN_NODE_H + 24);
            });

            var treeWrap = document.createElement('div');
            treeWrap.className = 'referidos-genealogy-tree';
            treeWrap.style.width = treeWidth + 'px';
            treeWrap.style.height = treeHeight + 'px';
            treeWrap.style.marginTop = (idx > 0 ? GEN_FOREST_GAP : 0) + 'px';

            var nodesHtml = positions.map(function (p) {
                return '<div class="referidos-gen-node-wrap" style="left:' + (p.x - GEN_NODE_W / 2) + 'px;top:' + p.y + 'px;">' +
                    buildGenealogyNodeHtml(p.nodo, self._selectedCodigo) +
                    '</div>';
            }).join('');

            treeWrap.innerHTML = renderGenealogySvg(connectors, treeWidth, treeHeight) +
                '<div class="referidos-genealogy-nodes">' + nodesHtml + '</div>';
            forest.appendChild(treeWrap);
            maxForestWidth = Math.max(maxForestWidth, treeWidth);
            offsetY += treeHeight + GEN_FOREST_GAP;
        });

        forest.style.minWidth = maxForestWidth + 'px';
        self._bindGenealogyEvents(target);
        self._resetPanView();
    };

    RuanaReferidosTree.prototype._bindGenealogyEvents = function (rootEl) {
        var self = this;
        if (!rootEl) return;
        if (rootEl._genealogyBound) return;
        rootEl._genealogyBound = true;

        rootEl.addEventListener('pointerdown', function (e) {
            if (e.target.closest('.referidos-gen-node')) {
                e.stopPropagation();
            }
        }, true);

        rootEl.addEventListener('click', function (e) {
            var nodeEl = e.target.closest('.referidos-gen-node');
            if (!nodeEl || !nodeEl.dataset.codigo) return;
            e.stopPropagation();
            self.selectNode(nodeEl.dataset.codigo);
        });

        rootEl.addEventListener('keydown', function (e) {
            var nodeEl = e.target.closest('.referidos-gen-node');
            if (!nodeEl || !nodeEl.dataset.codigo) return;
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                self.selectNode(nodeEl.dataset.codigo);
            }
        });
    };

    RuanaReferidosTree.prototype._renderNestedForest = function (bosques, container) {
        var self = this;
        container.innerHTML = '<div class="referidos-lazy-tree referidos-lazy-tree-full"></div>';
        var inner = container.querySelector('.referidos-lazy-tree-full');
        (bosques || []).forEach(function (root) {
            inner.appendChild(self._createNestedRow(root, 0, null));
        });
        if (!inner.children.length) {
            inner.innerHTML = '<div class="referidos-empty-state">No hay aliados en la red de referidos.</div>';
        }
        this._bindTreeEvents(container);
    };

    RuanaReferidosTree.prototype.loadAdminFull = function () {
        var self = this;
        this._setLoading('Cargando árbol genealógico completo…');
        return this._fetchJson('/api/admin/referidos/arbol?profundidad=50').then(function (data) {
            if (data.status !== 'success') throw new Error(data.message || 'Error');
            self._expanded = {};
            self._childrenCache = {};
            self._nodosMap = {};
            self._invitadoresMap = {};
            self._knownReferidos = {};
            self._totalNodos = data.total_nodos || 0;
            self._clearTreeRenderTarget();
            var bosques = data.bosques || (data.arbol ? [data.arbol] : []);
            self._renderGenealogyForest(bosques, self.treeContainer);
            var meta = (data.total_nodos || 0) + ' aliado' + ((data.total_nodos || 0) !== 1 ? 's' : '') + ' en vista genealógica';
            if (data.total_aliados_en_red) {
                meta += ' · ' + data.total_aliados_en_red + ' registrados';
            }
            if (data.aliados_fuera_red) {
                meta += ' · ' + data.aliados_fuera_red + ' pendientes de vincular';
            }
            meta += ' · Arrastra para mover · Pantalla completa arriba a la derecha';
            self._updateMeta(meta);
            if (bosques.length) {
                var firstCodigo = findFirstSelectableCodigo(bosques);
                if (firstCodigo) self.selectNode(firstCodigo);
                else self._clearDetailSelection();
            } else {
                renderDetailPanel(self.detailContainer, null);
                self._updateDetailFloatVisibility();
            }
            self.startPolling();
            self._adminLoaded = true;
            return data;
        }).catch(function (err) {
            self._showTreeError(err.message || 'Error de conexión');
            renderDetailPanel(self.detailContainer, null);
            throw err;
        });
    };

    RuanaReferidosTree.prototype._buildCardHtml = function (nodo, opts) {
        opts = opts || {};
        var depth = opts.depth || 0;
        var selected = this._selectedCodigo === nodo.codigo;
        var expanded = !!this._expanded[nodo.codigo];
        var referidosCount = nodo.referidos_count != null ? nodo.referidos_count : (nodo.hijos_directos || 0);
        var hasChildren = nodo.tiene_hijos || referidosCount > 0 || nodo.virtual;
        var isVirtual = !!nodo.virtual || nodo.tipo_nodo === 'campana' || nodo.tipo_nodo === 'sin_atribucion';
        var loading = !!opts.loading;
        var zona = nodo.zona || nodo.codigo_postal || (isVirtual ? 'RUANA' : '—');
        var badgeCount = referidosCount > 0
            ? referidosCount + ' aliado' + (referidosCount !== 1 ? 's' : '')
            : (isVirtual ? 'Vacío' : 'Sin referidos');
        var origenTexto = origenLabel(nodo.origen, nodo.origen_label);
        var origenLine = origenTexto
            ? '<div class="referidos-node-meta referidos-node-origen">' + escapeHtml(origenTexto) + '</div>'
            : (nodo.invitador_nombre
                ? '<div class="referidos-node-meta referidos-node-origen">Incorporado por ' + escapeHtml(nodo.invitador_nombre) + '</div>'
                : (isVirtual ? '<div class="referidos-node-meta referidos-node-origen">Nodo de agrupación</div>' : ''));
        var pendienteAlta = !!nodo.pendiente_alta;
        var cardExtraClass = (opts.isRoot ? ' is-root' : '') +
            (nodo.estado === 'sistema' ? ' is-admin' : '') +
            (pendienteAlta ? ' pendiente-alta' : '') +
            (nodo.perfil_eliminado ? ' is-eliminado' : '') +
            (nodo.perfil_pausado ? ' is-pausado' : '') +
            (isVirtual ? ' is-virtual' : '');

        return (
            '<div class="referidos-row" data-codigo="' + escapeHtml(nodo.codigo) + '" data-depth="' + depth + '">' +
            '<div class="referidos-node-card' + (selected ? ' selected' : '') + cardExtraClass + '" role="button" tabindex="0" data-codigo="' + escapeHtml(nodo.codigo) + '">' +
            (hasChildren
                ? '<button type="button" class="referidos-expand-btn' + (expanded ? ' expanded' : '') + (loading ? ' loading' : '') + '" data-codigo="' + escapeHtml(nodo.codigo) + '" aria-label="' + (expanded ? 'Contraer' : 'Expandir') + ' referidos">' +
                  (loading ? '<span class="referidos-expand-spinner"></span>' : '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>') +
                  '</button>'
                : '<span class="referidos-expand-spacer" aria-hidden="true"></span>') +
            '<div class="referidos-node-avatar" aria-hidden="true">' + escapeHtml(getIniciales(nodo.nombre)) + '</div>' +
            '<div class="referidos-node-body">' +
            '<div class="referidos-node-top">' +
            '<div class="referidos-node-nombre" title="' + escapeHtml(nodo.nombre || '') + '">' + escapeHtml(nodo.nombre || '(sin nombre)') + '</div>' +
            '<span class="referidos-node-estado ' + estadoClass(nodo.estado, pendienteAlta) + '">' + escapeHtml(estadoLabel(nodo.estado, pendienteAlta)) + '</span>' +
            '</div>' +
            '<div class="referidos-node-meta"><span class="referidos-node-codigo">' + escapeHtml(nodo.codigo || '') + '</span> · ' + escapeHtml(nodo.oficio || '—') + ' · ' + escapeHtml(zona) + '</div>' +
            '<div class="referidos-node-meta">Marca: ' + escapeHtml(nodo.marca || '—') + ' · Score: ' + escapeHtml(String(nodo.score != null ? nodo.score : '—')) + '</div>' +
            origenLine +
            '</div>' +
            '<span class="referidos-node-badge' + (referidosCount === 0 ? ' empty' : '') + '">' + escapeHtml(badgeCount) + '</span>' +
            '</div>' +
            '<div class="referidos-children-wrap' + (expanded ? ' expanded' : '') + '" data-parent="' + escapeHtml(nodo.codigo) + '"></div>' +
            '</div>'
        );
    };

    RuanaReferidosTree.prototype._renderSubtree = function (nodos, container, depth) {
        var self = this;
        var html = '';
        (nodos || []).forEach(function (nodo) {
            html += self._buildCardHtml(nodo, { depth: depth, isRoot: depth === 0 });
        });
        container.innerHTML = html || '<div class="referidos-empty-state">No hay aliados en esta rama.</div>';
        this._bindTreeEvents(container);
        var selfRef = this;
        Object.keys(this._expanded).forEach(function (codigo) {
            if (selfRef._expanded[codigo] && selfRef._childrenCache[codigo]) {
                selfRef._renderChildren(codigo, selfRef._childrenCache[codigo], depth + 1);
            }
        });
    };

    RuanaReferidosTree.prototype._renderChildren = function (parentCodigo, hijos, depth) {
        var wrap = this.treeContainer.querySelector('.referidos-children-wrap[data-parent="' + parentCodigo + '"]');
        if (!wrap) return;
        var self = this;
        var html = '<div class="referidos-children-list">';
        (hijos || []).forEach(function (hijo) {
            html += self._buildCardHtml(hijo, { depth: depth });
        });
        html += '</div>';
        wrap.innerHTML = html;
        wrap.classList.add('expanded');
        this._bindTreeEvents(wrap);
    };

    RuanaReferidosTree.prototype._bindTreeEvents = function (rootEl) {
        var self = this;
        if (!rootEl) return;

        rootEl.querySelectorAll('.referidos-node-card').forEach(function (card) {
            card.addEventListener('click', function (e) {
                if (e.target.closest('.referidos-expand-btn')) return;
                e.stopPropagation();
                var codigo = card.dataset.codigo;
                self.activateNode(codigo, true);
            });
            card.addEventListener('keydown', function (e) {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    self.activateNode(card.dataset.codigo, true);
                }
            });
        });

        rootEl.querySelectorAll('.referidos-expand-btn').forEach(function (btn) {
            btn.addEventListener('click', function (e) {
                e.stopPropagation();
                self.toggleExpand(btn.dataset.codigo);
            });
        });
    };

    RuanaReferidosTree.prototype.activateNode = function (codigo, autoExpand) {
        var self = this;
        this.selectNode(codigo);
        var nodo = this._nodosMap[codigo];
        if (autoExpand && nodo && (nodo.referidos_count || 0) > 0) {
            this.toggleExpand(codigo, true).catch(function () {});
        }
    };

    RuanaReferidosTree.prototype.selectNode = function (codigo, invitadorOverride) {
        if (!codigo) return;
        var nodo = this._nodosMap[codigo];
        if (!nodo) return;
        this._selectedCodigo = codigo;
        var invitador = invitadorOverride != null ? invitadorOverride : this._invitadoresMap[codigo] || null;

        if (this.treeContainer) {
            this.treeContainer.querySelectorAll('.referidos-node-card, .referidos-gen-node').forEach(function (el) {
                el.classList.toggle('selected', el.dataset.codigo === codigo);
            });
        }

        var self = this;
        renderDetailPanel(this.detailContainer, nodo, invitador, {
            mode: this.mode,
            onSelectCodigo: function (c, inv) { self.focusOnCodigo(c); },
            onVerDetalleCompleto: this.onVerDetalleCompleto,
            onCentrarArbol: this.onCentrarArbol,
            onPausarAliado: this.onPausarAliado,
            onEliminarAliado: this.onEliminarAliado
        });
        this._updateDetailFloatVisibility();

        if (!nodo.virtual && this.apiDetalle) {
            this._fetchJson(this.apiDetalle + encodeURIComponent(codigo)).then(function (data) {
                if (data.status === 'success' && data.aliado) {
                    var merged = Object.assign({}, nodo, data.aliado);
                    indexarNodo(merged, self._nodosMap, self._invitadoresMap, invitador);
                    renderDetailPanel(self.detailContainer, merged, invitador, {
                        mode: self.mode,
                        onSelectCodigo: function (c) { self.focusOnCodigo(c); },
                        onVerDetalleCompleto: self.onVerDetalleCompleto,
                        onCentrarArbol: self.onCentrarArbol,
                        onPausarAliado: self.onPausarAliado,
                        onEliminarAliado: self.onEliminarAliado
                    });
                    self._updateDetailFloatVisibility();
                }
            }).catch(function () {});
        }

        var nodeEl = this.treeContainer && (
            this.treeContainer.querySelector('.referidos-node-card[data-codigo="' + codigo + '"]') ||
            this.treeContainer.querySelector('.referidos-gen-node[data-codigo="' + codigo + '"]')
        );
        if (nodeEl && nodeEl.scrollIntoView) {
            nodeEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
    };

    RuanaReferidosTree.prototype._nodeExistsInDom = function (codigo) {
        if (!this.treeContainer) return false;
        return !!(
            this.treeContainer.querySelector('.referidos-row[data-codigo="' + codigo + '"]') ||
            this.treeContainer.querySelector('.referidos-gen-node[data-codigo="' + codigo + '"]')
        );
    };

    RuanaReferidosTree.prototype._updateNodeBadge = function (codigo, referidosCount) {
        var card = this.treeContainer && this.treeContainer.querySelector('.referidos-node-card[data-codigo="' + codigo + '"]');
        if (!card) return;
        var nodo = this._nodosMap[codigo];
        if (nodo) nodo.referidos_count = referidosCount;
        var badge = card.querySelector('.referidos-node-badge');
        if (badge) {
            var text = referidosCount > 0
                ? referidosCount + ' referido' + (referidosCount !== 1 ? 's' : '')
                : 'Sin referidos';
            badge.textContent = text;
            badge.classList.toggle('empty', referidosCount === 0);
        }
        var expandBtn = card.querySelector('.referidos-expand-btn');
        var spacer = card.querySelector('.referidos-expand-spacer');
        if (referidosCount > 0 && !expandBtn && spacer) {
            var btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'referidos-expand-btn' + (this._expanded[codigo] ? ' expanded' : '');
            btn.dataset.codigo = codigo;
            btn.setAttribute('aria-label', 'Expandir referidos');
            btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>';
            spacer.replaceWith(btn);
            var self = this;
            btn.addEventListener('click', function (e) {
                e.stopPropagation();
                self.toggleExpand(codigo);
            });
        }
    };

    RuanaReferidosTree.prototype._appendRootNode = function (nodo) {
        if (!nodo || !nodo.codigo || this._nodeExistsInDom(nodo.codigo)) return;
        indexarNodo(nodo, this._nodosMap, this._invitadoresMap, null);
        var inner = this.treeContainer.querySelector('.referidos-lazy-tree');
        if (!inner) return;
        var empty = inner.querySelector('.referidos-empty-state');
        if (empty) empty.remove();
        var temp = document.createElement('div');
        temp.innerHTML = this._buildCardHtml(nodo, { depth: 0, isRoot: true });
        var row = temp.firstElementChild;
        if (row) {
            row.querySelector('.referidos-node-card').classList.add('is-new');
            inner.appendChild(row);
            this._bindTreeEvents(row);
        }
    };

    RuanaReferidosTree.prototype._appendChildIfMissing = function (parentCodigo, hijo) {
        if (!hijo || !hijo.codigo) return;
        if (this.treeContainer.querySelector('.referidos-row[data-codigo="' + hijo.codigo + '"]')) return;

        if (!this._childrenCache[parentCodigo]) this._childrenCache[parentCodigo] = [];
        var exists = this._childrenCache[parentCodigo].some(function (h) { return h.codigo === hijo.codigo; });
        if (!exists) this._childrenCache[parentCodigo].push(hijo);

        var wrap = this.treeContainer.querySelector('.referidos-children-wrap[data-parent="' + parentCodigo + '"]');
        if (!wrap) return;

        var list = wrap.querySelector('.referidos-children-list');
        if (!list) {
            wrap.innerHTML = '<div class="referidos-children-list"></div>';
            list = wrap.querySelector('.referidos-children-list');
            wrap.classList.add('expanded');
        }

        var parentRow = this.treeContainer.querySelector('.referidos-row[data-codigo="' + parentCodigo + '"]');
        var depth = parentRow ? parseInt(parentRow.dataset.depth || '0', 10) + 1 : 1;

        var temp = document.createElement('div');
        temp.innerHTML = this._buildCardHtml(hijo, { depth: depth });
        var row = temp.firstElementChild;
        if (row) {
            row.querySelector('.referidos-node-card').classList.add('is-new');
            list.appendChild(row);
            this._bindTreeEvents(row);
            setTimeout(function () {
                var card = row.querySelector('.referidos-node-card.is-new');
                if (card) card.classList.remove('is-new');
            }, 2400);
        }
    };

    RuanaReferidosTree.prototype._ensureInvitadorVisible = function (invitador) {
        if (!invitador || !invitador.codigo) return;
        if (this._nodeExistsInDom(invitador.codigo)) return;
        if (this.mode === 'admin') {
            this._appendRootNode(invitador);
        }
    };

    RuanaReferidosTree.prototype._integrateCambio = function (cambio) {
        var refCodigo = cambio.codigo_referido;
        var invCodigo = cambio.codigo_invitador;
        var hijo = cambio.nodo;
        var invitador = cambio.invitador;
        if (!refCodigo || !invCodigo || !hijo) return false;
        if (this._knownReferidos[refCodigo]) return false;

        this._knownReferidos[refCodigo] = true;
        indexarNodo(hijo, this._nodosMap, this._invitadoresMap, invitador || null);
        if (invitador) indexarNodo(invitador, this._nodosMap, this._invitadoresMap, null);

        this._ensureInvitadorVisible(invitador);

        var invCount = invitador && invitador.referidos_count != null
            ? invitador.referidos_count
            : ((this._nodosMap[invCodigo] && this._nodosMap[invCodigo].referidos_count) || 0);
        if (invitador && invitador.referidos_count != null) {
            this._updateNodeBadge(invCodigo, invitador.referidos_count);
        } else if (this._nodosMap[invCodigo]) {
            invCount = (this._nodosMap[invCodigo].referidos_count || 0) + 1;
            this._nodosMap[invCodigo].referidos_count = invCount;
            this._updateNodeBadge(invCodigo, invCount);
        }

        if (this._expanded[invCodigo]) {
            this._appendChildIfMissing(invCodigo, hijo);
        }

        return true;
    };

    RuanaReferidosTree.prototype._mergeNewRaices = function (raices) {
        var self = this;
        (raices || []).forEach(function (n) {
            if (!self._nodeExistsInDom(n.codigo)) {
                self._appendRootNode(n);
            } else {
                indexarNodo(n, self._nodosMap, self._invitadoresMap, null);
                self._updateNodeBadge(n.codigo, n.referidos_count || 0);
            }
        });
    };

    RuanaReferidosTree.prototype.startPolling = function () {
        this.stopPolling();
        this._lastSyncAt = new Date().toISOString();
        var self = this;
        this._pollTimer = setInterval(function () {
            if (document.hidden) return;
            self.pollCambios().catch(function () {});
        }, this.pollIntervalMs);
    };

    RuanaReferidosTree.prototype.stopPolling = function () {
        if (this._pollTimer) {
            clearInterval(this._pollTimer);
            this._pollTimer = null;
        }
    };

    RuanaReferidosTree.prototype.pollCambios = function () {
        var self = this;
        if (this._pollInFlight || !this._lastSyncAt) return Promise.resolve();
        this._pollInFlight = true;
        var url = this.apiCambios + '?desde=' + encodeURIComponent(this._lastSyncAt);
        return this._fetchJson(url).then(function (data) {
            if (data.status !== 'success') return;
            var nuevos = 0;
            (data.cambios || []).forEach(function (c) {
                if (self._integrateCambio(c)) nuevos += 1;
            });

            if (self.mode === 'admin') {
                if (data.raices) self._mergeNewRaices(data.raices);
                if (data.total_nodos != null) self._totalNodos = data.total_nodos;
                self._updateMeta(self._adminMetaText(data) + ' · Se actualiza automáticamente');
            } else if (data.nodo_raiz) {
                indexarNodo(data.nodo_raiz, self._nodosMap, self._invitadoresMap, null);
                self._updateNodeBadge(data.nodo_raiz.codigo, data.nodo_raiz.referidos_count || 0);
                self._updateMeta(
                    (data.nodo_raiz.referidos_count || 0) + ' referido' + ((data.nodo_raiz.referidos_count || 0) !== 1 ? 's' : '') +
                    ' directo' + ((data.nodo_raiz.referidos_count || 0) !== 1 ? 's' : '') +
                    ' · Se actualiza automáticamente'
                );
            }

            if (nuevos > 0 && self._selectedCodigo && self._nodosMap[self._selectedCodigo]) {
                self.selectNode(self._selectedCodigo);
            }

            Object.keys(self._expanded).forEach(function (codigo) {
                if (!self._expanded[codigo]) return;
                self._fetchJson(self.apiHijos + encodeURIComponent(codigo)).then(function (resp) {
                    if (resp.status !== 'success') return;
                    if (resp.nodo) self._updateNodeBadge(codigo, resp.nodo.referidos_count || 0);
                    (resp.hijos || []).forEach(function (h) {
                        self._integrateCambio({
                            codigo_referido: h.codigo,
                            codigo_invitador: codigo,
                            nodo: h,
                            invitador: resp.nodo
                        });
                    });
                }).catch(function () {});
            });

            if (data.timestamp) self._lastSyncAt = data.timestamp;
        }).finally(function () {
            self._pollInFlight = false;
        });
    };

    RuanaReferidosTree.prototype.toggleExpand = function (codigo, forceOpen) {
        var self = this;
        if (!codigo) return Promise.resolve();

        if (this._expanded[codigo] && !forceOpen) {
            this._expanded[codigo] = false;
            var wrap = this.treeContainer.querySelector('.referidos-children-wrap[data-parent="' + codigo + '"]');
            if (wrap) {
                wrap.classList.remove('expanded');
                wrap.innerHTML = '';
            }
            var btn = this.treeContainer.querySelector('.referidos-expand-btn[data-codigo="' + codigo + '"]');
            if (btn) btn.classList.remove('expanded');
            return Promise.resolve();
        }

        this._expanded[codigo] = true;
        var expandBtn = this.treeContainer.querySelector('.referidos-expand-btn[data-codigo="' + codigo + '"]');
        if (expandBtn) expandBtn.classList.add('expanded', 'loading');

        return this._fetchJson(this.apiHijos + encodeURIComponent(codigo))
            .then(function (data) {
                if (data.status !== 'success') throw new Error(data.message || 'Error');
                if (data.nodo) {
                    self._nodosMap[codigo] = data.nodo;
                    self._updateNodeBadge(codigo, data.nodo.referidos_count || 0);
                }
                if (data.invitador && data.nodo) {
                    self._invitadoresMap[data.nodo.codigo] = data.invitador;
                }
                var hijos = data.hijos || [];
                self._childrenCache[codigo] = hijos;
                hijos.forEach(function (h) {
                    indexarNodo(h, self._nodosMap, self._invitadoresMap, data.nodo);
                    self._knownReferidos[h.codigo] = true;
                });
                var parentRow = self.treeContainer.querySelector('.referidos-row[data-codigo="' + codigo + '"]');
                var depth = parentRow ? parseInt(parentRow.dataset.depth || '0', 10) + 1 : 1;
                self._renderChildren(codigo, hijos, depth);
            })
            .finally(function () {
                if (expandBtn) expandBtn.classList.remove('loading');
            });
    };

    RuanaReferidosTree.prototype.loadAdmin = function () {
        return this.loadAdminFull();
    };

    RuanaReferidosTree.prototype.loadAdminLazy = function () {
        var self = this;
        this._setLoading('Cargando raíces del árbol genealógico…');
        return this._fetchJson(this.apiRaices).then(function (data) {
            if (data.status !== 'success') throw new Error(data.message || 'Error');
            self._expanded = {};
            self._childrenCache = {};
            self._nodosMap = {};
            self._invitadoresMap = {};
            self._knownReferidos = {};
            self._totalNodos = data.total_nodos || 0;
            (data.raices || []).forEach(function (n) {
                indexarNodo(n, self._nodosMap, self._invitadoresMap, null);
            });
            var target = self._getTreeRenderTarget();
            target.innerHTML = '<div class="referidos-lazy-tree"></div>';
            var inner = target.querySelector('.referidos-lazy-tree');
            if (!data.raices || !data.raices.length) {
                inner.innerHTML = '<div class="referidos-empty-state">No hay aliados en la red de referidos.</div>';
                renderDetailPanel(self.detailContainer, null);
            } else {
                self._renderSubtree(data.raices, inner, 0);
                self.selectNode(data.raices[0].codigo);
            }
            self._updateMeta(self._adminMetaText(data) + ' · Clic en ▶ para expandir · Se actualiza solo');
            self.startPolling();
            self._adminLoaded = true;
            return data;
        }).catch(function (err) {
            self._showTreeError(err.message || 'Error de conexión');
            renderDetailPanel(self.detailContainer, null);
            self._adminLoaded = false;
            throw err;
        });
    };

    RuanaReferidosTree.prototype.loadAliado = function () {
        var self = this;
        this._setLoading('Cargando tu árbol genealógico…');
        return this._fetchJson('/api/aliado/referidos?profundidad=50').then(function (data) {
            if (data.status !== 'success') throw new Error(data.message || 'Error');
            self._expanded = {};
            self._childrenCache = {};
            self._nodosMap = {};
            self._invitadoresMap = {};
            self._knownReferidos = {};
            var arbol = data.arbol;
            if (data.invitador && data.invitador.codigo) {
                self._invitadoresMap[arbol.codigo] = data.invitador;
            }
            self._clearTreeRenderTarget();
            self._renderGenealogyForest([arbol], self.treeContainer);
            var total = (arbol.referidos_count || 0);
            self._updateMeta(
                total + ' referido' + (total !== 1 ? 's' : '') +
                ' directo' + (total !== 1 ? 's' : '') +
                ' · Vista genealógica · Se actualiza solo'
            );
            self.selectNode(arbol.codigo, data.invitador);
            self.startPolling();
            return data;
        }).catch(function (err) {
            self._showTreeError(err.message || 'Error de conexión');
            renderDetailPanel(self.detailContainer, null);
            throw err;
        });
    };

    RuanaReferidosTree.prototype.loadAliadoLazy = function () {
        var self = this;
        this._setLoading();
        return this._fetchJson(this.apiRaiz).then(function (data) {
            if (data.status !== 'success') throw new Error(data.message || 'Error');
            self._expanded = {};
            self._childrenCache = {};
            self._nodosMap = {};
            self._invitadoresMap = {};
            self._knownReferidos = {};
            var nodo = data.nodo;
            indexarNodo(nodo, self._nodosMap, self._invitadoresMap, data.invitador);
            var target = self._getTreeRenderTarget();
            target.innerHTML = '<div class="referidos-lazy-tree"></div>';
            var inner = target.querySelector('.referidos-lazy-tree');
            self._renderSubtree([nodo], inner, 0);
            self._updateMeta(
                (nodo.referidos_count || 0) + ' referido' + ((nodo.referidos_count || 0) !== 1 ? 's' : '') +
                ' directo' + ((nodo.referidos_count || 0) !== 1 ? 's' : '') +
                ' · Clic para expandir · Se actualiza solo'
            );
            self.selectNode(nodo.codigo, data.invitador);
            self.startPolling();
            return data;
        }).catch(function (err) {
            self.treeContainer.innerHTML = '<div class="referidos-empty-state">' + escapeHtml(err.message || 'Error de conexión') + '</div>';
            renderDetailPanel(self.detailContainer, null);
            throw err;
        });
    };

    RuanaReferidosTree.prototype.load = function () {
        if (this.mode === 'admin') return this.loadAdmin();
        return this.loadAliado();
    };

    RuanaReferidosTree.prototype.focusOnCodigo = function (codigo) {
        var self = this;
        if (this.mode !== 'admin') {
            this.activateNode(codigo, true);
            return Promise.resolve();
        }
        if (this._nodosMap[codigo]) {
            this.selectNode(codigo);
            return Promise.resolve();
        }
        return this.loadAdminFull().then(function () {
            self.selectNode(codigo);
        });
    };

    RuanaReferidosTree.prototype.searchAndFocus = function (query) {
        var self = this;
        if (!query) return this.loadAdminFull();
        return this._fetchJson(this.apiBuscar + '?q=' + encodeURIComponent(query)).then(function (data) {
            if (data.status !== 'success') throw new Error(data.message || 'Error');
            var resultados = data.resultados || [];
            if (!resultados.length) throw new Error('Ningún aliado coincide en la red de referidos');
            return self.focusOnCodigo(resultados[0].codigo);
        });
    };

    RuanaReferidosTree.prototype.findNodeBySearch = function (query) {
        return this._nodosMap[query] || null;
    };

    RuanaReferidosTree.prototype.centrarEn = function (codigo) {
        return this.focusOnCodigo(codigo);
    };

    global.RuanaReferidos = {
        escapeHtml: escapeHtml,
        getIniciales: getIniciales,
        renderDetailPanel: renderDetailPanel,
        RuanaReferidosTree: RuanaReferidosTree
    };
})(typeof window !== 'undefined' ? window : this);
