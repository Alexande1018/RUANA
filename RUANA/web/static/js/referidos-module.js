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
        if (e === 'eliminado') return 'Perfil eliminado';
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
            container.className = 'referidos-detail-panel empty';
            container.innerHTML = '<p>Selecciona un aliado en el árbol para ver su ficha.</p>';
            return;
        }
        container.className = 'referidos-detail-panel';
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
        if (options.mode === 'admin' && !nodo.virtual) {
            adminActions =
                '<div class="referidos-detail-actions">' +
                '<button type="button" class="btn-accion referidos-btn-ver-detalle">Ver detalle completo</button>' +
                '<button type="button" class="btn-accion referidos-btn-centrar">Centrar árbol aquí</button>' +
                '<button type="button" class="btn-accion referidos-btn-pausar">Pausar aliado</button>' +
                '<button type="button" class="btn-accion danger referidos-btn-eliminar">Eliminar perfil</button>' +
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
    }

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
        if (!this.treeContainer) return;
        this.treeContainer.innerHTML =
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
            self.treeContainer.innerHTML = '';
            var bosques = data.bosques || (data.arbol ? [data.arbol] : []);
            self._renderNestedForest(bosques, self.treeContainer);
            var meta = (data.total_nodos || 0) + ' aliado' + ((data.total_nodos || 0) !== 1 ? 's' : '') + ' en vista completa';
            if (data.total_aliados_en_red) {
                meta += ' · ' + data.total_aliados_en_red + ' registrados';
            }
            if (data.aliados_fuera_red) {
                meta += ' · ' + data.aliados_fuera_red + ' sin vincular';
            }
            meta += ' · Busca por nombre o código arriba';
            self._updateMeta(meta);
            if (bosques.length) {
                self.selectNode(bosques[0].codigo);
            } else {
                renderDetailPanel(self.detailContainer, null);
            }
            self.startPolling();
            self._adminLoaded = true;
            return data;
        }).catch(function (err) {
            self.treeContainer.innerHTML = '<div class="referidos-empty-state">' + escapeHtml(err.message || 'Error de conexión') + '</div>';
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
            this.treeContainer.querySelectorAll('.referidos-node-card').forEach(function (el) {
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
                }
            }).catch(function () {});
        }

        var nodeEl = this.treeContainer && this.treeContainer.querySelector('.referidos-node-card[data-codigo="' + codigo + '"]');
        if (nodeEl && nodeEl.scrollIntoView) {
            nodeEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
    };

    RuanaReferidosTree.prototype._nodeExistsInDom = function (codigo) {
        return !!(this.treeContainer && this.treeContainer.querySelector('.referidos-row[data-codigo="' + codigo + '"]'));
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
            self.treeContainer.innerHTML = '<div class="referidos-lazy-tree"></div>';
            var inner = self.treeContainer.querySelector('.referidos-lazy-tree');
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
            self.treeContainer.innerHTML = '<div class="referidos-empty-state">' + escapeHtml(err.message || 'Error de conexión') + '</div>';
            renderDetailPanel(self.detailContainer, null);
            self._adminLoaded = false;
            throw err;
        });
    };

    RuanaReferidosTree.prototype.loadAliado = function () {
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
            self.treeContainer.innerHTML = '<div class="referidos-lazy-tree"></div>';
            var inner = self.treeContainer.querySelector('.referidos-lazy-tree');
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
        if (this._nodeExistsInDom(codigo)) {
            this.selectNode(codigo);
            return Promise.resolve();
        }
        return this._fetchJson(this.apiRuta + encodeURIComponent(codigo)).then(function (data) {
            if (data.status !== 'success') throw new Error(data.message || 'No encontrado');
            var ruta = data.ruta || [];
            if (!ruta.length) throw new Error('Sin ruta');
            self._expanded = {};
            self._childrenCache = {};
            self._nodosMap = {};
            self._invitadoresMap = {};
            ruta.forEach(function (n, i) {
                indexarNodo(n, self._nodosMap, self._invitadoresMap, i > 0 ? ruta[i - 1] : null);
            });
            self.treeContainer.innerHTML = '<div class="referidos-lazy-tree referidos-lazy-tree-path"></div>';
            var inner = self.treeContainer.querySelector('.referidos-lazy-tree');
            self._renderSubtree([ruta[0]], inner, 0);
            var chain = Promise.resolve();
            for (var i = 0; i < ruta.length; i++) {
                (function (c, idx) {
                    chain = chain.then(function () {
                        self._expanded[c] = true;
                        return self.toggleExpand(c, true);
                    });
                })(ruta[i].codigo, i);
            }
            return chain.then(function () {
                self.selectNode(codigo);
                self.startPolling();
            });
        });
    };

    RuanaReferidosTree.prototype.searchAndFocus = function (query) {
        var self = this;
        if (!query) return this.loadAdmin();
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
