/**
 * Módulo AdminPanel Stripe Connect (solo lectura).
 * Onboarding de aliados, transferencias y importe en tránsito.
 */
(function (global) {
  'use strict';

  var modules = global.RuanaAdminModules = global.RuanaAdminModules || {
    resumen: null,
    operaciones: null,
    red: null,
    sistema: null,
    stripe: null,
  };

  function escapeHtmlSafe(host, str) {
    if (host && typeof host.escapeHtml === 'function') {
      return host.escapeHtml(str);
    }
    if (str == null || str === '') return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function estadoOnboardingLabel(estado) {
    switch (estado) {
      case 'listo':
        return 'Conectado';
      case 'onboarding_pendiente':
        return 'Onboarding pendiente';
      case 'sin_cuenta':
        return 'Sin cuenta';
      default:
        return estado || '—';
    }
  }

  function estadoOnboardingStyle(estado) {
    switch (estado) {
      case 'listo':
        return 'color: var(--ruana-estado-estable)';
      case 'onboarding_pendiente':
        return 'color: var(--ruana-estado-prioritario)';
      case 'sin_cuenta':
        return 'color: var(--ruana-estado-riesgo)';
      default:
        return '';
    }
  }

  function transferenciaStyle(estado) {
    switch (estado) {
      case 'completada':
        return 'color: var(--ruana-estado-estable)';
      case 'pendiente':
        return 'color: var(--ruana-estado-prioritario)';
      case 'esperando_cobro':
        return 'color: var(--ruana-estado-competencia)';
      case 'revision':
        return 'color: var(--ruana-estado-riesgo)';
      default:
        return '';
    }
  }

  function transferenciaLabel(estado) {
    switch (estado) {
      case 'completada':
        return 'Completada';
      case 'pendiente':
        return 'Pendiente de transferencia';
      case 'esperando_cobro':
        return 'Esperando cobro';
      case 'revision':
        return 'En revisión admin';
      default:
        return estado || '—';
    }
  }

  function transferenciaClass(estado) {
    return '';
  }

  function formatEuro(val) {
    var n = Number(val);
    if (!Number.isFinite(n)) return '—';
    return n.toFixed(2) + ' €';
  }

  function renderStripeResumen(host, data) {
    var wrap = document.getElementById('stripe-admin-wrap');
    var totalesEl = document.getElementById('stripe-admin-totales');
    var tbodyAliados = document.getElementById('tbody-stripe-onboarding');
    var tbodyTransfer = document.getElementById('tbody-stripe-transferencias');
    var emptyAliados = document.getElementById('stripe-onboarding-empty');
    var emptyTransfer = document.getElementById('stripe-transferencias-empty');
    var habilitadoEl = document.getElementById('stripe-admin-habilitado');
    if (!wrap || !tbodyAliados || !tbodyTransfer) return;

    var payload = data || {};
    var totales = payload.totales || {};
    var aliados = Array.isArray(payload.aliados) ? payload.aliados : [];
    var transferencias = Array.isArray(payload.transferencias) ? payload.transferencias : [];

    if (habilitadoEl) {
      habilitadoEl.textContent = payload.stripe_habilitado
        ? 'Stripe activo en servidor'
        : 'Stripe no configurado en servidor (datos locales)';
      habilitadoEl.style.cssText = payload.stripe_habilitado
        ? 'color: var(--ruana-estado-estable)'
        : 'color: var(--ruana-estado-prioritario)';
    }

    if (totalesEl) {
      totalesEl.innerHTML = `
        <div class="indicador-card">
          <div class="indicador-numero">${formatEuro(totales.importe_en_transito)}</div>
          <div class="indicador-label">Neto en tránsito (cobro confirmado)</div>
        </div>
        <div class="indicador-card">
          <div class="indicador-numero">${totales.transferencias_pendientes || 0}</div>
          <div class="indicador-label">Transferencias pendientes</div>
        </div>
        <div class="indicador-card">
          <div class="indicador-numero">${totales.transferencias_completadas || 0}</div>
          <div class="indicador-label">Transferencias completadas</div>
        </div>
      `;
    }

    tbodyAliados.innerHTML = '';
    if (!aliados.length) {
      if (emptyAliados) emptyAliados.style.display = 'block';
    } else {
      if (emptyAliados) emptyAliados.style.display = 'none';
      aliados.forEach(function (a) {
        var tr = document.createElement('tr');
        var estado = a.onboarding_estado || '';
        tr.innerHTML = `
          <td>${escapeHtmlSafe(host, a.codigo)}</td>
          <td>${escapeHtmlSafe(host, a.nombre || '—')}</td>
          <td style="${estadoOnboardingStyle(estado)}">${escapeHtmlSafe(host, estadoOnboardingLabel(estado))}</td>
          <td>${escapeHtmlSafe(host, (a.stripe_account_id || '').slice(0, 18))}${(a.stripe_account_id || '').length > 18 ? '…' : ''}</td>
        `;
        tbodyAliados.appendChild(tr);
      });
    }

    tbodyTransfer.innerHTML = '';
    if (!transferencias.length) {
      if (emptyTransfer) emptyTransfer.style.display = 'block';
    } else {
      if (emptyTransfer) emptyTransfer.style.display = 'none';
      transferencias.forEach(function (t) {
        var tr = document.createElement('tr');
        var est = t.transferencia_estado || '';
        tr.innerHTML = `
          <td>${escapeHtmlSafe(host, t.id)}</td>
          <td>${escapeHtmlSafe(host, t.profesional_codigo)}</td>
          <td>${escapeHtmlSafe(host, t.solicitante_codigo)}</td>
          <td>${formatEuro(t.importe_final)}</td>
          <td>${formatEuro(t.importe_neto_profesional)}</td>
          <td style="${transferenciaStyle(est)}">${escapeHtmlSafe(host, transferenciaLabel(est))}</td>
          <td>${escapeHtmlSafe(host, t.estado_pago || '—')}</td>
        `;
        tbodyTransfer.appendChild(tr);
      });
    }
  }

  modules.stripe = {
    renderStripeResumen: renderStripeResumen,
  };
})(typeof window !== 'undefined' ? window : globalThis);
