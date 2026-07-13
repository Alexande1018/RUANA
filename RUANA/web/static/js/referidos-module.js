/**
 * RUANA — Árbol genealógico de referidos (lazy expand + tarjetas enriquecidas)
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

    function estadoLabel(estado) {
        var e = String(estado || 'activo').toLowerCase();
        if (e === 'sistema') return 'Admin RUANA';
        if (e === 'pendiente_validacion') return 'Pendiente';
        if (e === 'suspendido_temporal') return 'Pausado';
        if (e === 'expulsado') return 'Expulsado';
        if (e === 'rechazado') return 'Rechazado';
        return 'Activo';
    }

    function estadoClass(estado) {
        var e = String(estado || 'activo').toLowerCase();
        if (e === 'sistema') return 'sistema';
        if (e === 'pendiente_validacion') return 'pendiente';
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

        var adminActions = '';
        if (options.mode === 'admin' && typeof options.onVerDetalleCompleto === 'function') {
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
            '<div class="referidos-detail-item"><span class="info-label">Estado</span><span class="info-value">' + escapeHtml(estadoLabel(nodo.estado)) + '</span></div>' +
            '<div class="referidos-detail-item"><span class="info-label">Referidos directos</span><span class="info-value">' + escapeHtml(String(referidosCount)) + '</span></div>' +
            '<div class="referidos-detail-item"><span class="info-label">Registro</span><span class="info-value">' + escapeHtml(formatFecha(nodo.creado_en || nodo.referido_en)) + '</span></div>' +
            (options.mode === 'admin'
                ? '<div class="referidos-detail-item referidos-detail-wide"><span class="info-label">Contacto</span><span class="info-value">' + escapeHtml(contacto) + '</span></div>' +
                  '<div class="referidos-detail-item referidos-detail-wide"><span class="info-label">Especialidades</span><span class="info-value">' + escapeHtml(esp) + '</span></div>'
                : '') +
            '</div>' +
            invitadorHtml +
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

        this._nodosMap = {};
        this._invitadoresMap = {};
        this._childrenCache = {};
        this._expanded = {};
        this._selectedCodigo = null;
        this._totalNodos = 0;
    }

    RuanaReferidosTree.prototype._fetchJson = function (url) {
        return fetch(url, Object.assign({ credentials: 'same-origin' }, this.fetchOptions))
            .then(function (r) { return r.json(); });
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

    RuanaReferidosTree.prototype._buildCardHtml = function (nodo, opts) {
        opts = opts || {};
        var depth = opts.depth || 0;
        var selected = this._selectedCodigo === nodo.codigo;
        var expanded = !!this._expanded[nodo.codigo];
        var referidosCount = nodo.referidos_count != null ? nodo.referidos_count : 0;
        var hasChildren = referidosCount > 0;
        var loading = !!opts.loading;
        var zona = nodo.zona || nodo.codigo_postal || '—';
        var badgeCount = referidosCount > 0
            ? referidosCount + ' referido' + (referidosCount !== 1 ? 's' : '')
            : 'Sin referidos';

        return (
            '<div class="referidos-row" data-codigo="' + escapeHtml(nodo.codigo) + '" data-depth="' + depth + '">' +
            '<div class="referidos-node-card' + (selected ? ' selected' : '') + (opts.isRoot ? ' is-root' : '') + (nodo.estado === 'sistema' ? ' is-admin' : '') + '" role="button" tabindex="0" data-codigo="' + escapeHtml(nodo.codigo) + '">' +
            (hasChildren
                ? '<button type="button" class="referidos-expand-btn' + (expanded ? ' expanded' : '') + (loading ? ' loading' : '') + '" data-codigo="' + escapeHtml(nodo.codigo) + '" aria-label="' + (expanded ? 'Contraer' : 'Expandir') + ' referidos">' +
                  (loading ? '<span class="referidos-expand-spinner"></span>' : '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>') +
                  '</button>'
                : '<span class="referidos-expand-spacer" aria-hidden="true"></span>') +
            '<div class="referidos-node-avatar" aria-hidden="true">' + escapeHtml(getIniciales(nodo.nombre)) + '</div>' +
            '<div class="referidos-node-body">' +
            '<div class="referidos-node-top">' +
            '<div class="referidos-node-nombre" title="' + escapeHtml(nodo.nombre || '') + '">' + escapeHtml(nodo.nombre || '(sin nombre)') + '</div>' +
            '<span class="referidos-node-estado ' + estadoClass(nodo.estado) + '">' + escapeHtml(estadoLabel(nodo.estado)) + '</span>' +
            '</div>' +
            '<div class="referidos-node-meta"><span class="referidos-node-codigo">' + escapeHtml(nodo.codigo || '') + '</span> · ' + escapeHtml(nodo.oficio || '—') + ' · ' + escapeHtml(zona) + '</div>' +
            '<div class="referidos-node-meta">Marca: ' + escapeHtml(nodo.marca || '—') + ' · Score: ' + escapeHtml(String(nodo.score != null ? nodo.score : '—')) + '</div>' +
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
            onCentrarArbol: this.onCentrarArbol
        });

        var nodeEl = this.treeContainer && this.treeContainer.querySelector('.referidos-node-card[data-codigo="' + codigo + '"]');
        if (nodeEl && nodeEl.scrollIntoView) {
            nodeEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
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

        if (this._childrenCache[codigo]) {
            var parentRow = this.treeContainer.querySelector('.referidos-row[data-codigo="' + codigo + '"]');
            var depth = parentRow ? parseInt(parentRow.dataset.depth || '0', 10) + 1 : 1;
            this._renderChildren(codigo, this._childrenCache[codigo], depth);
            if (expandBtn) expandBtn.classList.remove('loading');
            return Promise.resolve();
        }

        return this._fetchJson(this.apiHijos + encodeURIComponent(codigo))
            .then(function (data) {
                if (data.status !== 'success') throw new Error(data.message || 'Error');
                if (data.invitador && data.nodo) {
                    self._invitadoresMap[data.nodo.codigo] = data.invitador;
                }
                var hijos = data.hijos || [];
                self._childrenCache[codigo] = hijos;
                hijos.forEach(function (h) { indexarNodo(h, self._nodosMap, self._invitadoresMap, data.nodo); });
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
        this._setLoading();
        return this._fetchJson(this.apiRaices).then(function (data) {
            if (data.status !== 'success') throw new Error(data.message || 'Error');
            self._expanded = {};
            self._childrenCache = {};
            self._nodosMap = {};
            self._invitadoresMap = {};
            self._totalNodos = data.total_nodos || 0;
            (data.raices || []).forEach(function (n) { indexarNodo(n, self._nodosMap, self._invitadoresMap, null); });
            self.treeContainer.innerHTML = '<div class="referidos-lazy-tree"></div>';
            var inner = self.treeContainer.querySelector('.referidos-lazy-tree');
            self._renderSubtree(data.raices || [], inner, 0);
            self._updateMeta(
                (data.total_raices || 0) + ' raíz' + ((data.total_raices || 0) !== 1 ? 'es' : '') +
                ' · ' + (data.total_nodos || 0) + ' aliado' + ((data.total_nodos || 0) !== 1 ? 's' : '') +
                ' en la red · Clic para expandir referidos'
            );
            if (data.raices && data.raices.length) {
                self.selectNode(data.raices[0].codigo);
            } else {
                renderDetailPanel(self.detailContainer, null);
            }
            return data;
        }).catch(function (err) {
            self.treeContainer.innerHTML = '<div class="referidos-empty-state">' + escapeHtml(err.message || 'Error de conexión') + '</div>';
            renderDetailPanel(self.detailContainer, null);
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
            var nodo = data.nodo;
            indexarNodo(nodo, self._nodosMap, self._invitadoresMap, data.invitador);
            self.treeContainer.innerHTML = '<div class="referidos-lazy-tree"></div>';
            var inner = self.treeContainer.querySelector('.referidos-lazy-tree');
            self._renderSubtree([nodo], inner, 0);
            self._updateMeta(
                (nodo.referidos_count || 0) + ' referido' + ((nodo.referidos_count || 0) !== 1 ? 's' : '') +
                ' directo' + ((nodo.referidos_count || 0) !== 1 ? 's' : '') +
                ' · Clic en un aliado para ver a quién invitó'
            );
            self.selectNode(nodo.codigo, data.invitador);
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
