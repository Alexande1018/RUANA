/**
 * FASE 09 — Panel administrativo financiero interno.
 * Solo consume APIs agregadas; no duplica reglas de dominio.
 */
(function (global) {
  'use strict';

  var modules = global.RuanaAdminModules = global.RuanaAdminModules || {};
  var currentSection = 'resumen';
  var permisosEfectivos = [];

  var SECTIONS = [
    { id: 'resumen', label: 'Resumen', endpoint: '/api/admin/financial/dashboard' },
    { id: 'pagos', label: 'Pagos', list: '/api/admin/financial/payments' },
    { id: 'transferencias', label: 'Transferencias', list: '/api/admin/financial/transfers' },
    { id: 'refunds', label: 'Refunds', list: '/api/admin/financial/refunds' },
    { id: 'disputas', label: 'Disputas', list: '/api/admin/financial/disputes' },
    { id: 'conflictos', label: 'Conflictos', list: '/api/admin/financial/conflicts' },
    { id: 'reconciliacion', label: 'Reconciliación', list: '/api/admin/financial/reconciliation' },
    { id: 'ledger', label: 'Ledger', list: '/api/admin/financial/ledger' },
    { id: 'webhooks', label: 'Webhooks', list: '/api/admin/financial/webhooks' },
    { id: 'auditoria', label: 'Auditoría', list: '/api/admin/financial/audit' },
    { id: 'acciones', label: 'Acciones pendientes', alerts: true }
  ];

  function esc(s) {
    if (global.RuanaUi && global.RuanaUi.escapeHtml) return global.RuanaUi.escapeHtml(s);
    var d = document.createElement('div');
    d.textContent = s == null ? '' : String(s);
    return d.innerHTML;
  }

  function authHeaders() {
    if (global.AdminAuthenticator && global.AdminAuthenticator.getAdminAuthHeaders) {
      return global.AdminAuthenticator.getAdminAuthHeaders();
    }
    return { credentials: 'same-origin' };
  }

  function fetchJson(url, opts) {
    var base = authHeaders();
    var headers = Object.assign({}, base.headers || {}, (opts && opts.headers) || {});
    return fetch(url, Object.assign({ credentials: 'same-origin' }, opts || {}, { headers: headers }))
      .then(function (r) { return r.json().then(function (j) { return { status: r.status, data: j }; }); });
  }

  function centsToEuros(cents) {
    if (cents == null || cents === '') return '—';
    return (Number(cents) / 100).toFixed(2) + ' €';
  }

  function freshnessBadge(meta) {
    if (!meta || !meta.data_freshness) return '';
    var cls = meta.data_freshness === 'stale' ? ' is-stale' : '';
    return '<p class="fin-meta' + cls + '">Actualizado: ' + esc(meta.generated_at || '—') +
      ' · Frescura: ' + esc(meta.data_freshness) + '</p>';
  }

  function renderNav(container) {
    container.innerHTML = '<nav class="fin-nav" role="tablist">' + SECTIONS.map(function (s) {
      return '<button type="button" class="fin-nav-btn' + (s.id === currentSection ? ' is-active' : '') +
        '" data-fin-nav="' + esc(s.id) + '">' + esc(s.label) + '</button>';
    }).join('') + '</nav>';
    container.querySelectorAll('[data-fin-nav]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        showSection(btn.getAttribute('data-fin-nav'));
      });
    });
  }

  function showSection(id) {
    currentSection = id || 'resumen';
    var wrap = document.getElementById('financial-admin-wrap');
    if (!wrap) return;
    wrap.hidden = false;
    wrap.querySelectorAll('.fin-section').forEach(function (el) {
      var active = el.getAttribute('data-fin-section') === currentSection;
      el.hidden = !active;
    });
    var navHost = document.getElementById('finanzas-resumen');
    if (navHost && !navHost.querySelector('.fin-nav')) {
      renderNav(navHost);
    } else if (wrap.querySelector('.fin-nav')) {
      wrap.querySelectorAll('.fin-nav-btn').forEach(function (b) {
        b.classList.toggle('is-active', b.getAttribute('data-fin-nav') === currentSection);
      });
    }
    loadSection(currentSection);
  }

  function renderLoading(host) {
    host.innerHTML = '<div class="fin-state is-loading">Cargando…</div>';
  }

  function renderError(host, msg) {
    host.innerHTML = '<div class="fin-state is-error">' + esc(msg || 'Error al cargar') + '</div>';
  }

  function renderTable(host, items, columns) {
    if (!items || !items.length) {
      host.innerHTML = '<div class="fin-state is-empty">Sin registros.</div>';
      return;
    }
    var table = '<div class="fin-table-wrap"><table class="fin-table"><thead><tr>' +
      columns.map(function (c) { return '<th>' + esc(c.label) + '</th>'; }).join('') +
      '</tr></thead><tbody>' +
      items.map(function (row) {
        return '<tr>' + columns.map(function (c) {
          var val = typeof c.render === 'function' ? c.render(row) : row[c.key];
          return '<td>' + (c.raw ? val : esc(val)) + '</td>';
        }).join('') + '</tr>';
      }).join('') + '</tbody></table></div>';
    var cards = '<div class="fin-cards">' + items.map(function (row) {
      return '<div class="fin-card-row">' + columns.map(function (c) {
        var val = typeof c.render === 'function' ? c.render(row) : row[c.key];
        return '<div><strong>' + esc(c.label) + ':</strong> ' + (c.raw ? val : esc(val)) + '</div>';
      }).join('') + '</div>';
    }).join('') + '</div>';
    host.innerHTML = table + cards;
  }

  function loadDashboard(host) {
    renderLoading(host);
    fetchJson('/api/admin/financial/dashboard').then(function (res) {
      if (res.status === 403) {
        host.innerHTML = '<div class="fin-state is-error">Sin permiso para ver el panel financiero.</div>';
        return;
      }
      if (res.status === 401) {
        host.innerHTML = '<div class="fin-state is-error">Sesión admin requerida.</div>';
        return;
      }
      var d = res.data || {};
      if (d.status !== 'success') {
        renderError(host, d.message);
        return;
      }
      var kpis = d.kpis || [];
      var html = freshnessBadge(d) +
        '<div class="fin-kpi-grid">' + kpis.map(function (k) {
          var val = k.id && k.id.indexOf('cents') >= 0 ? centsToEuros(k.valor) : esc(k.valor);
          return '<article class="fin-kpi' + (d.data_freshness === 'stale' ? ' is-stale' : '') + '">' +
            '<div class="fin-kpi-value">' + val + '</div>' +
            '<div class="fin-kpi-label">' + esc(k.id) + '</div>' +
            '<div class="fin-meta">Fuente: ' + esc(k.fuente) + '</div></article>';
        }).join('') + '</div>';
      host.insertAdjacentHTML('beforeend', html);
      loadAlerts(document.getElementById('finanzas-acciones'));
    }).catch(function () { renderError(host, 'Error de red'); });
  }

  function loadAlerts(host) {
    if (!host) return;
    renderLoading(host);
    fetchJson('/api/admin/financial/alerts?limit=50').then(function (res) {
      if (res.status !== 200 || res.data.status !== 'success') {
        renderError(host, (res.data && res.data.message) || 'No se pudieron cargar alertas');
        return;
      }
      var items = res.data.items || [];
      if (!items.length) {
        host.innerHTML = freshnessBadge(res.data) + '<div class="fin-state is-empty">No hay alertas críticas abiertas.</div>';
        return;
      }
      host.innerHTML = freshnessBadge(res.data) + items.map(function (a) {
        return '<article class="fin-alert is-' + esc(a.severidad || 'medium') + '">' +
          '<strong>' + esc(a.tipo) + '</strong> · ' + esc(a.estado) +
          '<div>Operación: ' + esc(a.contacto_id || a.object_id || '—') + '</div>' +
          '<div class="fin-meta">' + esc(a.accion_recomendada) + '</div>' +
          '<button type="button" class="fin-nav-btn" data-fin-resolve="' + esc(a.alert_key) + '">Resolver con comentario</button>' +
          '</article>';
      }).join('');
      host.querySelectorAll('[data-fin-resolve]').forEach(function (btn) {
        btn.addEventListener('click', function () {
          var motivo = global.prompt('Motivo de resolución (obligatorio, mín. 5 caracteres):');
          if (!motivo || motivo.trim().length < 5) {
            global.alert('Debe indicar un motivo válido.');
            return;
          }
          if (!global.confirm('¿Confirmar cierre de alerta con este motivo?')) return;
          var key = btn.getAttribute('data-fin-resolve');
          fetchJson('/api/admin/financial/alerts/' + encodeURIComponent(key) + '/resolve', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ motivo: motivo.trim() })
          }).then(function (r) {
            if (r.status === 200 && r.data.status === 'success') loadAlerts(host);
            else global.alert((r.data && r.data.message) || 'No se pudo resolver');
          });
        });
      });
    });
  }

  function loadList(sectionId, host, url) {
    renderLoading(host);
    fetchJson(url + '?limit=50&offset=0').then(function (res) {
      if (res.status === 403) {
        host.innerHTML = '<div class="fin-state is-error">Sin permiso.</div>';
        return;
      }
      if (res.status !== 200 || res.data.status !== 'success') {
        renderError(host, (res.data && res.data.message) || 'Error');
        return;
      }
      var cols = [
        { key: 'id', label: 'ID' },
        { key: 'contacto_id', label: 'Contacto' },
        { key: 'estado', label: 'Estado', render: function (r) {
          return r.estado || r.estado_financiero || r.estado_interno || r.estado_conflicto || '—';
        }},
        { key: 'importe', label: 'Importe', render: function (r) {
          if (r.amount_cents != null) return centsToEuros(r.amount_cents);
          if (r.importe_confirmado_cents != null) return centsToEuros(r.importe_confirmado_cents);
          if (r.importe_acordado != null) return esc(r.importe_acordado) + ' €';
          return '—';
        }, raw: true },
        { key: 'fecha', label: 'Fecha', render: function (r) {
          return r.creado_en || r.actualizado_en || r.fecha_cobro_confirmado || '—';
        }},
        { key: 'link', label: '', render: function (r) {
          var cid = r.contacto_id || r.id || r.trabajo_id;
          if (!cid) return '—';
          return '<button type="button" class="fin-nav-btn" data-fin-detail="' + esc(cid) + '">Detalle</button>';
        }, raw: true }
      ];
      host.innerHTML = freshnessBadge(res.data);
      var listHost = document.createElement('div');
      host.appendChild(listHost);
      renderTable(listHost, res.data.items, cols);
      host.querySelectorAll('[data-fin-detail]').forEach(function (btn) {
        btn.addEventListener('click', function () {
          loadOperation(btn.getAttribute('data-fin-detail'));
        });
      });
    }).catch(function () { renderError(host, 'Error de red'); });
  }

  function loadOperation(contactoId) {
    currentSection = 'detalle';
    showSection('detalle');
    var host = document.getElementById('finanzas-detalle');
    if (!host) return;
    renderLoading(host);
    fetchJson('/api/admin/financial/operation/' + encodeURIComponent(contactoId)).then(function (res) {
      if (res.status === 404) {
        renderError(host, 'Operación no encontrada');
        return;
      }
      if (res.status !== 200) {
        renderError(host, (res.data && res.data.message) || 'Error');
        return;
      }
      var op = (res.data.operacion) || {};
      var c = op.contacto || {};
      host.innerHTML = freshnessBadge(res.data) +
        '<div class="fin-detail-grid">' +
        '<section class="fin-detail-block"><h3>Contacto #' + esc(c.id) + '</h3>' +
        '<p>Estado: ' + esc(c.estado_financiero) + ' · PI: ' + esc(c.stripe_payment_intent_id) + '</p></section>' +
        '<section class="fin-detail-block"><h3>Línea temporal</h3><pre>' + esc(JSON.stringify(op.timeline || [], null, 2)) + '</pre></section>' +
        '</div>';
    });
  }

  function loadSection(id) {
    var host = document.getElementById('finanzas-' + id);
    if (!host) return;
    if (id === 'resumen') {
      if (!host.querySelector('.fin-nav')) renderNav(host);
      var body = host.querySelector('.fin-dashboard-body');
      if (!body) {
        body = document.createElement('div');
        body.className = 'fin-dashboard-body';
        host.appendChild(body);
      }
      loadDashboard(body);
      return;
    }
    if (id === 'acciones') {
      loadAlerts(host);
      return;
    }
    if (id === 'detalle') return;
    var sec = SECTIONS.find(function (s) { return s.id === id; });
    if (sec && sec.list) loadList(id, host, sec.list);
  }

  function onFinanzasActivated() {
    var wrap = document.getElementById('financial-admin-wrap');
    if (wrap) wrap.hidden = false;
    showSection(currentSection);
  }

  modules.financial = {
    setup: function () {
      fetchJson('/api/admin/me').then(function (res) {
        if (res.data && res.data.permisos) permisosEfectivos = res.data.permisos;
      });
    },
    onModuleActivated: onFinanzasActivated,
    showSection: showSection,
    loadOperation: loadOperation
  };
})(typeof window !== 'undefined' ? window : globalThis);
