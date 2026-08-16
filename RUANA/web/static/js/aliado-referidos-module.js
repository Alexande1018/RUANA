/**
 * Módulo PrivatePanel `referidos` (Campamento Base).
 * Árbol genealógico lazy del aliado (/api/aliado/referidos/raiz + hijos).
 * PrivatePanel conserva fachadas delgadas que delegan aquí.
 */
(function (global) {
  'use strict';

  var modules = global.RuanaAliadoModules = global.RuanaAliadoModules || {
    inicio: null,
    directorio: null,
    solicitudes: null,
    conexiones: null,
    perfil: null,
    referidos: null,
  };

  var _treeInstance = null;

  function getApiBaseSafe() {
    if (typeof global.getApiBase === 'function') return global.getApiBase();
    return '';
  }

  function getAuthHeadersSafe(extra) {
    if (typeof global.getRuanaAuthHeaders === 'function') {
      return global.getRuanaAuthHeaders(extra || {});
    }
    return extra || {};
  }

  function _ensureTree() {
    if (_treeInstance) return _treeInstance;
    if (!global.RuanaReferidos || !global.RuanaReferidos.RuanaReferidosTree) {
      return null;
    }
    var treeEl = document.getElementById('referidos-tree-aliado');
    var detailEl = document.getElementById('referidos-detail-aliado');
    var metaEl = document.getElementById('modal-linaje-hijos-meta');
    if (!treeEl || !detailEl) return null;
    _treeInstance = new global.RuanaReferidos.RuanaReferidosTree({
      mode: 'aliado',
      treeContainer: treeEl,
      detailContainer: detailEl,
      metaContainer: metaEl,
      fetchOptions: {
        credentials: 'same-origin',
        headers: getAuthHeadersSafe(),
      },
      pollIntervalMs: 20000,
    });
    return _treeInstance;
  }

  /**
   * Abre el modal del árbol genealógico y carga la red del aliado autenticado.
   * @param {object} host PrivatePanel (escapeHtml opcional)
   */
  function abrirModalLinajeHijos(host) {
    var modal = document.getElementById('modal-linaje-hijos');
    if (!modal) return Promise.resolve();
    modal.style.display = 'flex';

    var tree = _ensureTree();
    if (!tree) {
      var list = document.getElementById('modal-linaje-hijos-list');
      if (list) {
        list.innerHTML = '<p style="color:#f87171;">No se pudo cargar el árbol genealógico.</p>';
      }
      return Promise.resolve();
    }

    return tree.loadAliado().catch(function () {
      var treeEl = document.getElementById('referidos-tree-aliado');
      if (treeEl && !treeEl.querySelector('.referidos-empty-state')) {
        treeEl.innerHTML = '<div class="referidos-empty-state">No se pudo cargar tu red de referidos.</div>';
      }
    });
  }

  function cerrarModalLinajeHijos() {
    var modal = document.getElementById('modal-linaje-hijos');
    if (modal) modal.style.display = 'none';
    if (_treeInstance && typeof _treeInstance.stopPolling === 'function') {
      _treeInstance.stopPolling();
    }
  }

  modules.referidos = {
    abrirModalLinajeHijos: abrirModalLinajeHijos,
    cerrarModalLinajeHijos: cerrarModalLinajeHijos,
    getTreeInstance: function () { return _treeInstance; },
  };
})(typeof window !== 'undefined' ? window : globalThis);
