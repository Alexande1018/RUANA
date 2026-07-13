/**
 * RUANA — Módulo compartido de árbol genealógico de referidos
 * Reutilizado en panel admin y panel del aliado.
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
        const parts = String(nombre || '').split(/\s+/).filter(Boolean).slice(0, 2);
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

    function contarDescendientes(nodo) {
        if (!nodo) return 0;
        var count = 0;
        var hijos = nodo.referidos || [];
        for (var i = 0; i < hijos.length; i++) {
            count += 1 + contarDescendientes(hijos[i]);
        }
        return count;
    }

    function indexarNodos(nodo, map) {
        if (!nodo || !nodo.codigo) return;
        map[nodo.codigo] = nodo;
        var hijos = nodo.referidos || [];
        for (var i = 0; i < hijos.length; i++) {
            indexarNodos(hijos[i], map);
        }
    }

    function buildNodeElement(nodo, options) {
        options = options || {};
        var isRoot = !!options.isRoot;
        var referidosCount = typeof nodo.referidos_count === 'number'
            ? nodo.referidos_count
            : (nodo.referidos || []).length;
        var hijos = nodo.referidos || [];
        var badgeText = referidosCount > 0
            ? referidosCount + ' referido' + (referidosCount !== 1 ? 's' : '')
            : 'Sin referidos';

        var el = document.createElement('div');
        el.className = 'referidos-node' + (isRoot ? ' is-root' : '');
        el.dataset.codigo = nodo.codigo || '';
        el.setAttribute('role', 'button');
        el.setAttribute('tabindex', '0');
        el.innerHTML =
            '<div class="referidos-node-avatar" aria-hidden="true">' + escapeHtml(getIniciales(nodo.nombre)) + '</div>' +
            '<div class="referidos-node-nombre" title="' + escapeHtml(nodo.nombre || '') + '">' + escapeHtml(nodo.nombre || '(sin nombre)') + '</div>' +
            '<div class="referidos-node-oficio">' + escapeHtml(nodo.oficio || '') + '</div>' +
            '<span class="referidos-node-badge' + (referidosCount === 0 ? ' empty' : '') + '">' + escapeHtml(badgeText) + '</span>';

        var li = document.createElement('li');
        li.className = 'referidos-tree-li';
        li.appendChild(el);

        if (hijos.length > 0) {
            var childrenWrap = document.createElement('div');
            childrenWrap.className = 'referidos-tree-children';
            var ul = document.createElement('ul');
            ul.className = 'referidos-tree-ul';
            for (var i = 0; i < hijos.length; i++) {
                ul.appendChild(buildNodeElement(hijos[i], {}));
            }
            childrenWrap.appendChild(ul);
            li.appendChild(childrenWrap);
        } else if (nodo.truncado && referidosCount > 0) {
            var trunc = document.createElement('div');
            trunc.className = 'referidos-node-badge empty';
            trunc.style.marginTop = '8px';
            trunc.textContent = '… más niveles';
            li.appendChild(trunc);
        }

        return li;
    }

    function buildTreeElement(arbol, options) {
        options = options || {};
        if (!arbol) return null;
        var root = document.createElement('div');
        root.className = 'referidos-tree referidos-tree-root';
        var ul = document.createElement('ul');
        ul.className = 'referidos-tree-ul';
        ul.appendChild(buildNodeElement(arbol, { isRoot: true }));
        root.appendChild(ul);
        return root;
    }

    function buildBosqueElement(bosques) {
        var wrap = document.createElement('div');
        wrap.className = 'referidos-bosque';
        if (!bosques || bosques.length === 0) {
            wrap.innerHTML = '<div class="referidos-empty-state">No hay cadenas de referidos registradas.</div>';
            return wrap;
        }
        for (var i = 0; i < bosques.length; i++) {
            var item = document.createElement('div');
            item.className = 'referidos-bosque-item';
            var label = document.createElement('div');
            label.className = 'referidos-bosque-label';
            label.textContent = 'Cadena ' + (i + 1);
            item.appendChild(label);
            var tree = buildTreeElement(bosques[i]);
            if (tree) item.appendChild(tree);
            wrap.appendChild(item);
        }
        return wrap;
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
        var referidosCount = typeof nodo.referidos_count === 'number'
            ? nodo.referidos_count
            : contarDescendientes(nodo);

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
                '<div style="margin-top:16px;display:flex;gap:8px;flex-wrap:wrap;">' +
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
            '<div class="referidos-detail-item"><span class="info-label">Estado</span><span class="info-value">' + escapeHtml(nodo.estado || '—') + '</span></div>' +
            '<div class="referidos-detail-item"><span class="info-label">Referidos directos</span><span class="info-value">' + escapeHtml(String(referidosCount)) + '</span></div>' +
            '<div class="referidos-detail-item"><span class="info-label">Registro</span><span class="info-value">' + escapeHtml(formatFecha(nodo.creado_en || nodo.referido_en)) + '</span></div>' +
            (options.mode === 'admin'
                ? '<div class="referidos-detail-item" style="grid-column:1/-1"><span class="info-label">Contacto</span><span class="info-value">' + escapeHtml(contacto) + '</span></div>' +
                  '<div class="referidos-detail-item" style="grid-column:1/-1"><span class="info-label">Especialidades</span><span class="info-value">' + escapeHtml(esp) + '</span></div>'
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
        this.fetchUrl = config.fetchUrl;
        this.fetchOptions = config.fetchOptions || {};
        this.mode = config.mode || 'aliado';
        this.onVerDetalleCompleto = config.onVerDetalleCompleto || null;
        this.onCentrarArbol = config.onCentrarArbol || null;
        this._nodosMap = {};
        this._invitadoresMap = {};
        this._selectedCodigo = null;
        this._currentInvitador = null;
        this._arbol = null;
        this._bosques = null;
    }

    RuanaReferidosTree.prototype._setLoading = function (loading) {
        if (!this.treeContainer) return;
        if (loading) {
            this.treeContainer.innerHTML =
                '<div class="referidos-loading"><div class="referidos-loading-spinner"></div>Cargando red de referidos…</div>';
        }
    };

    RuanaReferidosTree.prototype._bindTreeClicks = function (rootEl) {
        var self = this;
        if (!rootEl) return;
        rootEl.querySelectorAll('.referidos-node').forEach(function (nodeEl) {
            nodeEl.addEventListener('click', function (e) {
                e.stopPropagation();
                var codigo = nodeEl.dataset.codigo;
                self.selectNode(codigo);
            });
            nodeEl.addEventListener('keydown', function (e) {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    self.selectNode(nodeEl.dataset.codigo);
                }
            });
        });
    };

    RuanaReferidosTree.prototype.selectNode = function (codigo, invitadorOverride) {
        if (!codigo) return;
        var nodo = this._nodosMap[codigo];
        if (!nodo) return;
        this._selectedCodigo = codigo;
        var invitador = invitadorOverride != null ? invitadorOverride : this._invitadoresMap[codigo] || null;

        if (this.treeContainer) {
            this.treeContainer.querySelectorAll('.referidos-node').forEach(function (el) {
                el.classList.toggle('selected', el.dataset.codigo === codigo);
            });
        }

        var self = this;
        renderDetailPanel(this.detailContainer, nodo, invitador, {
            mode: this.mode,
            onSelectCodigo: function (c) { self.selectNode(c); },
            onVerDetalleCompleto: this.onVerDetalleCompleto,
            onCentrarArbol: this.onCentrarArbol
        });

        var nodeEl = this.treeContainer && this.treeContainer.querySelector('.referidos-node[data-codigo="' + codigo + '"]');
        if (nodeEl && typeof nodeEl.scrollIntoView === 'function') {
            nodeEl.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
        }
    };

    RuanaReferidosTree.prototype._indexData = function (data) {
        this._nodosMap = {};
        this._invitadoresMap = {};
        if (data.modo === 'bosque' && Array.isArray(data.bosques)) {
            this._bosques = data.bosques;
            for (var i = 0; i < data.bosques.length; i++) {
                indexarNodos(data.bosques[i], this._nodosMap);
            }
        } else if (data.arbol) {
            this._arbol = data.arbol;
            indexarNodos(data.arbol, this._nodosMap);
            if (data.invitador && data.arbol.codigo) {
                this._invitadoresMap[data.arbol.codigo] = data.invitador;
            }
        }
    };

    RuanaReferidosTree.prototype.render = function (data) {
        if (!this.treeContainer) return;
        this._indexData(data);

        var fragment;
        if (data.modo === 'bosque' && Array.isArray(data.bosques)) {
            fragment = buildBosqueElement(data.bosques);
        } else if (data.arbol) {
            fragment = buildTreeElement(data.arbol);
        } else {
            this.treeContainer.innerHTML = '<div class="referidos-empty-state">No hay referidos para mostrar.</div>';
            renderDetailPanel(this.detailContainer, null);
            return;
        }

        this.treeContainer.innerHTML = '';
        this.treeContainer.appendChild(fragment);
        this._bindTreeClicks(this.treeContainer);

        if (this.metaContainer) {
            var total = data.total_nodos != null ? data.total_nodos : (data.total_descendientes != null ? data.total_descendientes + 1 : Object.keys(this._nodosMap).length);
            var raices = data.total_raices != null ? data.total_raices : 1;
            this.metaContainer.textContent = data.modo === 'bosque'
                ? raices + ' cadena' + (raices !== 1 ? 's' : '') + ' · ' + total + ' aliado' + (total !== 1 ? 's' : '') + ' en la red'
                : total + ' aliado' + (total !== 1 ? 's' : '') + ' en este árbol';
        }

        var defaultCodigo = data.arbol && data.arbol.codigo ? data.arbol.codigo : null;
        if (defaultCodigo) {
            this.selectNode(defaultCodigo, data.invitador || null);
        } else if (data.bosques && data.bosques[0] && data.bosques[0].codigo) {
            this.selectNode(data.bosques[0].codigo);
        } else {
            renderDetailPanel(this.detailContainer, null);
        }
    };

    RuanaReferidosTree.prototype.load = function (urlOverride) {
        var self = this;
        var url = urlOverride || this.fetchUrl;
        if (!url) return Promise.reject(new Error('URL no definida'));
        this._setLoading(true);
        return fetch(url, Object.assign({ credentials: 'same-origin' }, this.fetchOptions))
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.status !== 'success') {
                    throw new Error(data.message || 'Error cargando referidos');
                }
                self.render(data);
                return data;
            })
            .catch(function (err) {
                if (self.treeContainer) {
                    self.treeContainer.innerHTML = '<div class="referidos-empty-state">' + escapeHtml(err.message || 'Error de conexión') + '</div>';
                }
                renderDetailPanel(self.detailContainer, null);
                throw err;
            });
    };

    RuanaReferidosTree.prototype.findNodeBySearch = function (query) {
        query = (query || '').trim().toLowerCase();
        if (!query) return null;
        var codigos = Object.keys(this._nodosMap);
        for (var i = 0; i < codigos.length; i++) {
            var n = this._nodosMap[codigos[i]];
            var nombre = (n.nombre || '').toLowerCase();
            var codigo = (n.codigo || '').toLowerCase();
            var oficio = (n.oficio || '').toLowerCase();
            if (codigo.includes(query) || nombre.includes(query) || oficio.includes(query)) {
                return n;
            }
        }
        return null;
    };

    global.RuanaReferidos = {
        escapeHtml: escapeHtml,
        getIniciales: getIniciales,
        buildTreeElement: buildTreeElement,
        buildBosqueElement: buildBosqueElement,
        renderDetailPanel: renderDetailPanel,
        RuanaReferidosTree: RuanaReferidosTree,
        contarDescendientes: contarDescendientes
    };
})(typeof window !== 'undefined' ? window : this);
