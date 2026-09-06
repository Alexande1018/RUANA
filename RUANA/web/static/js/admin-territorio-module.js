/**
 * RUANA Admin — Grupo Madre e independización territorial.
 */
(function (global) {
  'use strict';

  var modules = global.RuanaAdminModules = global.RuanaAdminModules || {};

  function esc(s) {
    if (global.RuanaUi && typeof global.RuanaUi.escapeHtml === 'function') {
      return global.RuanaUi.escapeHtml(s);
    }
    var d = document.createElement('div');
    d.textContent = s == null ? '' : String(s);
    return d.innerHTML;
  }

  function authHeaders() {
    if (global.AdminAuthenticator && typeof global.AdminAuthenticator.getAdminAuthHeaders === 'function') {
      return global.AdminAuthenticator.getAdminAuthHeaders();
    }
    return {};
  }

  function renderIndependenciaPendientes(solicitudes) {
    var tbody = document.getElementById('tbody-independencia-pendientes');
    if (!tbody) return;
    var list = solicitudes || [];
    if (!list.length) {
      tbody.innerHTML = '<tr><td colspan="6" style="color:#94a3b8;">No hay solicitudes pendientes.</td></tr>';
      return;
    }
    tbody.innerHTML = list.map(function (s) {
      return '<tr>' +
        '<td>' + esc(s.codigo_postal) + '</td>' +
        '<td>' + esc(s.ciudad) + '</td>' +
        '<td>' + esc(s.aliados_activos) + '</td>' +
        '<td>' + esc(s.encargos_validos) + '</td>' +
        '<td>' + esc((s.creado_en || '').toString().slice(0, 16)) + '</td>' +
        '<td class="territorio-acciones">' +
          '<button type="button" class="ruana-btn-primario btn-aprobar-independencia" data-cp="' + esc(s.codigo_postal) + '">Aprobar</button> ' +
          '<button type="button" class="btn-admin-action btn-posponer-independencia" data-cp="' + esc(s.codigo_postal) + '">Posponer</button>' +
        '</td></tr>';
    }).join('');
    tbody.querySelectorAll('.btn-aprobar-independencia').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var cp = btn.getAttribute('data-cp');
        if (!cp || !confirm('¿Aprobar independización territorial del CP ' + cp + '?')) return;
        btn.disabled = true;
        fetch('/api/admin/cp-independencia/aprobar', {
          method: 'POST',
          credentials: 'same-origin',
          headers: Object.assign({ 'Content-Type': 'application/json' }, authHeaders()),
          body: JSON.stringify({ codigo_postal: cp })
        }).then(function (r) { return r.json(); })
          .then(function (data) {
            if (data.status === 'success') {
              if (global.AdminPanel && typeof global.AdminPanel.showToast === 'function') {
                global.AdminPanel.showToast('CP ' + cp + ' independizado.', 'success');
              }
              refresh();
            } else {
              alert(data.message || 'No se pudo aprobar');
            }
          })
          .catch(function () { alert('Error de red'); })
          .finally(function () { btn.disabled = false; });
      });
    });
    tbody.querySelectorAll('.btn-posponer-independencia').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var cp = btn.getAttribute('data-cp');
        var notas = prompt('Notas (opcional) para posponer CP ' + cp + ':', '');
        if (notas === null) return;
        btn.disabled = true;
        fetch('/api/admin/cp-independencia/posponer', {
          method: 'POST',
          credentials: 'same-origin',
          headers: Object.assign({ 'Content-Type': 'application/json' }, authHeaders()),
          body: JSON.stringify({ codigo_postal: cp, notas: notas })
        }).then(function (r) { return r.json(); })
          .then(function (data) {
            if (data.status === 'success') refresh();
            else alert(data.message || 'No se pudo posponer');
          })
          .catch(function () { alert('Error de red'); })
          .finally(function () { btn.disabled = false; });
      });
    });
  }

  function renderGruposMadre(grupos) {
    var wrap = document.getElementById('grupos-madre-overview');
    if (!wrap) return;
    var list = grupos || [];
    if (!list.length) {
      wrap.innerHTML = '<p style="color:#94a3b8;">No hay grupos madre activos.</p>';
      return;
    }
    wrap.innerHTML = list.map(function (g) {
      return '<div class="grupos-cp-card">' +
        '<h4>' + esc(g.nombre) + '</h4>' +
        '<div class="grupos-cp-meta">' + esc(g.ciudad) + ' · ' + esc(g.n_aliados || 0) + ' aliados activos</div></div>';
    }).join('');
  }

  function refresh() {
    return Promise.all([
      fetch('/api/admin/cp-independencia/pendientes', { credentials: 'same-origin', headers: authHeaders() })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (d) { if (d && d.status === 'success') renderIndependenciaPendientes(d.solicitudes); }),
      fetch('/api/admin/grupos-madre', { credentials: 'same-origin', headers: authHeaders() })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (d) { if (d && d.status === 'success') renderGruposMadre(d.grupos); })
    ]);
  }

  modules.territorio = {
    refresh: refresh,
    renderIndependenciaPendientes: renderIndependenciaPendientes,
    renderGruposMadre: renderGruposMadre
  };
})(typeof window !== 'undefined' ? window : globalThis);
