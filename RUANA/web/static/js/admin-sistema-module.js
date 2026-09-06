/**
 * Módulo AdminPanel `sistema` (Campamento Base).
 * Campañas de invitación, códigos aliado, reglas y métodos de pago.
 * AdminPanel conserva fachadas delgadas que delegan aquí.
 */

(function (global) {
  'use strict';

  var modules = global.RuanaAdminModules = global.RuanaAdminModules || {
    resumen: null,
    operaciones: null,
    red: null,
    sistema: null,
  };

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

  function accionCrearCampanaInvitacion(host) {
    host._abrirModalAccionAdmin({
        title: 'Crear invitacion multiuso',
        bodyHtml: `
            <label class="modal-importe-label" style="display:block; margin-bottom:6px;">Nombre interno</label>
            <input type="text" id="accion-campana-nombre" placeholder="Ej: Campana barrio norte" style="width:100%; padding:8px; margin-bottom:12px; box-sizing:border-box;" />
            <label class="modal-importe-label" style="display:block; margin-bottom:6px;">Codigo publico (opcional)</label>
            <input type="text" id="accion-campana-codigo" placeholder="Ej: RUANA-NORTE" style="width:100%; padding:8px; margin-bottom:12px; box-sizing:border-box;" />
            <label class="modal-importe-label" style="display:block; margin-bottom:6px;">Codigo postal inicial (opcional)</label>
            <input type="text" id="accion-campana-zona" placeholder="Ej: 03014" style="width:100%; padding:8px; margin-bottom:12px; box-sizing:border-box;" />
            <label class="modal-importe-label" style="display:block; margin-bottom:6px;">Maximo de usos</label>
            <input type="number" id="accion-campana-max-usos" value="25" min="1" max="10000" style="width:100%; padding:8px; box-sizing:border-box;" />
        `,
        getPayload: () => ({
            nombre: (document.getElementById('accion-campana-nombre')?.value || '').trim(),
            codigo: (document.getElementById('accion-campana-codigo')?.value || '').trim(),
            codigo_postal: (document.getElementById('accion-campana-zona')?.value || '').trim(),
            max_usos: parseInt(document.getElementById('accion-campana-max-usos')?.value || '25', 10)
        }),
        validate: (p) => {
            if (!p.max_usos || p.max_usos < 1) return 'Indica un maximo de usos valido.';
            return null;
        },
        getConfirmSummary: (p) => {
            const codigo = p.codigo ? ` con codigo <strong>${host.escapeHtml(p.codigo.toUpperCase())}</strong>` : ' con codigo generado automaticamente';
            const zona = p.codigo_postal ? ` para codigo postal <strong>${host.escapeHtml(p.codigo_postal)}</strong>` : '';
            return `Se creara una invitacion multiuso${codigo}${zona}, limitada a <strong>${p.max_usos}</strong> registros.`;
        },
        execute: async (p) => {
            const r = await fetch('/api/admin/invitacion-campanas', {
                method: 'POST',
                credentials: 'same-origin',
                headers: host.getAuthHeaders(),
                body: JSON.stringify(p)
            });
            if (r.status === 401) { host._adminSessionExpired(); return; }
            if (r.status === 403) { host.showToast('Sin permiso de escritura (solo lectura).', 'error'); return; }
            const data = await r.json().catch(() => ({}));
            if (r.ok && data.status === 'success' && data.campana) {
                host.renderCampanaInvitacionCreada(data);
                host.showToast('Invitacion multiuso creada.', 'success');
                host.cargarCampanasInvitacion();
            } else {
                host.showToast(data.message || 'Error al crear invitacion multiuso.', 'error');
            }
        }
    });
  }

  function renderCampanaInvitacionCreada(host, data) {
    const result = document.getElementById('admin-campana-invitacion-result');
    if (!result) return;
    const campana = data.campana || {};
    const codigo = campana.codigo || '';
    const registroUrl = data.registro_url || '';
    const qrUrl = data.qr_url || '';
    const usosActuales = Number(campana.usos_actuales || 0);
    const maxUsos = campana.max_usos || '';
    const titulo = data.modo === 'detalle' ? 'Informacion del codigo multiuso' : 'Invitacion multiuso creada';
    result.style.display = 'block';
    result.innerHTML = `
        <div style="display:grid; gap:14px; grid-template-columns:minmax(0,1fr) auto; align-items:center;">
            <div>
                <div style="font-size:0.78rem; color:#a7f3d0; text-transform:uppercase; letter-spacing:0.04em;">${titulo}</div>
                <div style="font-size:1.8rem; font-weight:700; color:#ffffff; margin-top:2px;">${host.escapeHtml(codigo)}</div>
                <div style="font-size:0.86rem; color:#cbd5e1; margin-top:8px; overflow-wrap:anywhere;">${host.escapeHtml(registroUrl)}</div>
                <div style="font-size:0.82rem; color:#94a3b8; margin-top:6px;">Usos: ${usosActuales}/${host.escapeHtml(String(maxUsos))}</div>
            </div>
            ${qrUrl ? `<img src="${host.escapeHtml(qrUrl)}" alt="QR invitacion" style="width:112px; height:112px; border-radius:8px; background:#fff; padding:6px;">` : ''}
        </div>
        <div style="display:flex; gap:10px; flex-wrap:wrap; margin-top:14px;">
            <button type="button" class="btn-admin-action" id="admin-copiar-campana-codigo">Copiar codigo</button>
            <button type="button" class="btn-admin-action" id="admin-copiar-campana-url">Copiar enlace</button>
        </div>
    `;
    document.getElementById('admin-copiar-campana-codigo')?.addEventListener('click', async () => {
        try { await navigator.clipboard.writeText(codigo); host.showToast('Codigo copiado.', 'success'); }
        catch (_) { host.showToast('No se pudo copiar automaticamente.', 'error'); }
    });
    document.getElementById('admin-copiar-campana-url')?.addEventListener('click', async () => {
        try { await navigator.clipboard.writeText(registroUrl); host.showToast('Enlace copiado.', 'success'); }
        catch (_) { host.showToast('No se pudo copiar automaticamente.', 'error'); }
    });
  }

  function accionCrearCodigoAliado(host) {
    host._abrirModalAccionAdmin({
        title: 'Crear codigo de aliado',
        bodyHtml: `
            <label class="modal-importe-label" style="display:block; margin-bottom:6px;">Codigo postal inicial (opcional)</label>
            <input type="text" id="accion-crear-codigo-zona" placeholder="Ej: 03014" style="width:100%; padding:8px; box-sizing:border-box;" />
        `,
        getPayload: () => ({
            zona: (document.getElementById('accion-crear-codigo-zona')?.value || '').trim()
        }),
        validate: () => null,
        getConfirmSummary: (p) => {
            const zona = p.zona ? ` para codigo postal <strong>${host.escapeHtml(p.zona)}</strong>` : '';
            return `Se creara un codigo de aliado pendiente de completar${zona}.`;
        },
        execute: async (p) => {
            const r = await fetch('/api/admin/invitaciones/crear', {
                method: 'POST',
                credentials: 'same-origin',
                headers: host.getAuthHeaders(),
                body: JSON.stringify({ zona: p.zona })
            });
            if (r.status === 401) { host._adminSessionExpired(); return; }
            if (r.status === 403) { host.showToast('Sin permiso de escritura (solo lectura).', 'error'); return; }
            const data = await r.json().catch(() => ({}));
            if (r.ok && data.status === 'success' && data.codigo) {
                host.renderCodigoAliadoCreado(data.codigo);
                host.showToast('Codigo de aliado creado.', 'success');
                host.cargarDesdeApi();
            } else {
                host.showToast(data.message || 'Error al crear codigo.', 'error');
            }
        }
    });
  }

  function renderCodigoAliadoCreado(host, codigo) {
    const result = document.getElementById('admin-codigo-aliado-result');
    if (!result) return;
    const safeCodigo = host.escapeHtml(codigo || '');
    result.style.display = 'block';
    result.innerHTML = `
        <div style="display:flex; gap:12px; align-items:center; justify-content:space-between; flex-wrap:wrap;">
            <div>
                <div style="font-size:0.78rem; color:#a7f3d0; text-transform:uppercase; letter-spacing:0.04em;">Codigo creado</div>
                <div style="font-size:1.9rem; font-weight:700; color:#ffffff; margin-top:2px;">${safeCodigo}</div>
            </div>
            <button type="button" class="btn-admin-action" id="admin-copiar-codigo-aliado">Copiar</button>
        </div>
    `;
    const btn = document.getElementById('admin-copiar-codigo-aliado');
    if (btn) {
        btn.addEventListener('click', async () => {
            try {
                await navigator.clipboard.writeText(codigo);
                host.showToast('Codigo copiado.', 'success');
            } catch (_) {
                host.showToast('No se pudo copiar automaticamente.', 'error');
            }
        });
    }
  }

  function accionCambiarReglas(host) {
    host._abrirModalAccionAdmin({
        title: 'Cambiar reglas',
        bodyHtml: `
            <label class="modal-importe-label" style="display:block; margin-bottom:6px;">Clave *</label>
            <select id="accion-cr-clave" style="width:100%; padding:8px; margin-bottom:12px; box-sizing:border-box;">
                <option value="umbral_competencia">umbral_competencia</option>
                <option value="duracion_competencia_dias">duracion_competencia_dias</option>
                <option value="purga_mensual_meses_sin_ganar">purga_mensual_meses_sin_ganar</option>
                <option value="purga_score_bajo_umbral">purga_score_bajo_umbral</option>
                <option value="apoyo_pct">apoyo_pct</option>
                <option value="posponer_horas">posponer_horas</option>
            </select>
            <label class="modal-importe-label" style="display:block; margin-bottom:6px;">Valor numérico *</label>
            <input type="number" id="accion-cr-valor" placeholder="Ej: 35" style="width:100%; padding:8px; box-sizing:border-box;" />
        `,
        getPayload: () => ({
            clave: (document.getElementById('accion-cr-clave')?.value || '').trim(),
            valorStr: (document.getElementById('accion-cr-valor')?.value || '').trim()
        }),
        validate: (p) => {
            if (!p.clave) return 'La clave es obligatoria.';
            const v = parseInt(p.valorStr, 10);
            if (p.valorStr === '' || isNaN(v)) return 'El valor debe ser un número.';
            return null;
        },
        getConfirmSummary: (p) => `¿Confirmar <strong>cambiar regla</strong> "${p.clave}" a valor <strong>${p.valorStr}</strong>?`,
        execute: async (p) => {
            const valor = parseInt(p.valorStr, 10);
            const r = await fetch('/api/admin/cambiar-reglas', { method: 'POST', credentials: 'same-origin', headers: host.getAuthHeaders(), body: JSON.stringify({ clave: p.clave, valor }) });
            if (r.status === 401) { host._adminSessionExpired(); return; }
            if (r.status === 403) { host.showToast('Sin permiso de escritura (solo lectura).', 'error'); return; }
            const data = await r.json().catch(() => ({}));
            if (data.status === 'success') { host.showToast(data.message || 'Regla actualizada.', 'success'); host.cargarDesdeApi(); }
            else { host.showToast(data.message || 'Error.', 'error'); }
        }
    });
  }

  function renderMetodosPago(host, metodos) {
    host._metodosPago = metodos || host._metodosPago || {};
    const bizumEl = document.getElementById('admin-metodo-bizum');
    const ibanEl = document.getElementById('admin-metodo-iban');
    const qrEl = document.getElementById('admin-metodo-qr');
    if (bizumEl) bizumEl.textContent = host._metodosPago.bizum_num || '-';
    if (ibanEl) ibanEl.textContent = host._metodosPago.iban || '-';
    if (qrEl) {
        qrEl.innerHTML = host._metodosPago.qr_revolut_path
            ? `<a href="${host.escapeHtml(host._metodosPago.qr_revolut_path)}" target="_blank" rel="noopener">Ver QR</a>`
            : '-';
    }
    cargarAllowlistPagoManual(host);
    bindPagoManualAllowlist(host);
  }

  async function cargarAllowlistPagoManual(host) {
    const tbody = document.getElementById('admin-pago-manual-aliados-tbody');
    if (!tbody) return;
    try {
        const r = await fetch('/api/admin/metodos-pago/aliados', {
            credentials: 'same-origin',
            headers: host.getAuthHeaders(),
        });
        if (r.status === 401) { host._adminSessionExpired(); return; }
        const data = await r.json().catch(() => ({}));
        const lista = (data.status === 'success' && Array.isArray(data.aliados)) ? data.aliados : [];
        host._pagoManualAllowlist = lista;
        tbody.innerHTML = '';
        lista.forEach((a) => {
            const tr = document.createElement('tr');
            const codigo = host.escapeHtml(a.aliado_codigo || '');
            const nombre = host.escapeHtml(a.nombre || '');
            const por = host.escapeHtml(a.habilitado_por || '-');
            tr.innerHTML =
                `<td>${codigo}</td><td>${nombre}</td><td>${por}</td>` +
                `<td><button type="button" class="btn-admin-action" data-deshabilitar-pago="${host.escapeHtml(a.aliado_codigo || '')}">Quitar</button></td>`;
            tbody.appendChild(tr);
        });
        tbody.querySelectorAll('[data-deshabilitar-pago]').forEach((btn) => {
            btn.addEventListener('click', () => deshabilitarPagoManualAliado(host, btn.getAttribute('data-deshabilitar-pago')));
        });
    } catch (e) {
        console.error('Error cargando allowlist pago manual:', e);
    }
  }

  function resolverAliadoPagoManual(host, query) {
    const q = (query || '').trim().toLowerCase();
    if (!q) return null;
    const lista = Array.isArray(host._aliadosData) ? host._aliadosData : [];
    const exacto = lista.find((a) => String(a.codigo || '').toLowerCase() === q);
    if (exacto) return exacto;
    const parciales = lista.filter((a) =>
        String(a.codigo || '').toLowerCase().includes(q) ||
        String(a.nombre || '').toLowerCase().includes(q)
    );
    return parciales.length === 1 ? parciales[0] : (parciales[0] || null);
  }

  async function habilitarPagoManualAliado(host) {
    const input = document.getElementById('admin-pago-manual-buscar');
    const aliado = resolverAliadoPagoManual(host, input && input.value);
    if (!aliado || !aliado.codigo) {
        host.showToast('Indica un código o nombre de aliado existente.', 'error');
        return;
    }
    const r = await fetch('/api/admin/metodos-pago/aliados/' + encodeURIComponent(aliado.codigo) + '/habilitar', {
        method: 'POST',
        credentials: 'same-origin',
        headers: host.getAuthHeaders(),
        body: '{}',
    });
    if (r.status === 401) { host._adminSessionExpired(); return; }
    if (r.status === 403) { host.showToast('Sin permiso de escritura (solo lectura).', 'error'); return; }
    const data = await r.json().catch(() => ({}));
    if (data.status === 'success') {
        host.showToast(data.message || 'Pago manual habilitado.', 'success');
        if (input) input.value = '';
        await cargarAllowlistPagoManual(host);
    } else {
        host.showToast(data.message || 'No se pudo habilitar.', 'error');
    }
  }

  async function deshabilitarPagoManualAliado(host, codigo) {
    if (!codigo) return;
    const r = await fetch('/api/admin/metodos-pago/aliados/' + encodeURIComponent(codigo) + '/deshabilitar', {
        method: 'POST',
        credentials: 'same-origin',
        headers: host.getAuthHeaders(),
        body: '{}',
    });
    if (r.status === 401) { host._adminSessionExpired(); return; }
    if (r.status === 403) { host.showToast('Sin permiso de escritura (solo lectura).', 'error'); return; }
    const data = await r.json().catch(() => ({}));
    if (data.status === 'success') {
        host.showToast(data.message || 'Pago manual deshabilitado.', 'success');
        await cargarAllowlistPagoManual(host);
    } else {
        host.showToast(data.message || 'No se pudo deshabilitar.', 'error');
    }
  }

  function bindPagoManualAllowlist(host) {
    const btn = document.getElementById('btn-habilitar-pago-manual');
    if (btn && !btn.dataset.boundPagoManual) {
        btn.dataset.boundPagoManual = '1';
        btn.addEventListener('click', () => habilitarPagoManualAliado(host));
    }
  }

  function accionEditarMetodosPago(host) {
    const metodos = host._metodosPago || {};
    host._abrirModalAccionAdmin({
        title: 'Editar metodos de pago',
        bodyHtml: `
            <label class="modal-importe-label" style="display:block; margin-bottom:6px;">Telefono Bizum *</label>
            <input type="text" id="accion-mp-bizum" value="${host.escapeHtml(metodos.bizum_num || '')}" style="width:100%; padding:8px; margin-bottom:12px; box-sizing:border-box;" />
            <label class="modal-importe-label" style="display:block; margin-bottom:6px;">IBAN *</label>
            <input type="text" id="accion-mp-iban" value="${host.escapeHtml(metodos.iban || '')}" style="width:100%; padding:8px; margin-bottom:12px; box-sizing:border-box;" />
            <label class="modal-importe-label" style="display:block; margin-bottom:6px;">QR Revolut</label>
            <input type="file" id="accion-mp-qr" accept=".jpg,.jpeg,.png,.webp" style="width:100%; padding:8px; box-sizing:border-box;" />
            <p style="margin-top:8px; color:#aaa; font-size:0.85rem;">Maximo 2 MB. Si no eliges archivo, se mantiene el QR actual.</p>
        `,
        getPayload: () => ({
            bizum_num: (document.getElementById('accion-mp-bizum')?.value || '').trim(),
            iban: (document.getElementById('accion-mp-iban')?.value || '').replace(/\s+/g, '').trim().toUpperCase(),
            qrFile: document.getElementById('accion-mp-qr')?.files?.[0] || null
        }),
        validate: (p) => {
            if (!p.bizum_num) return 'El telefono Bizum es obligatorio.';
            if (!p.iban || !p.iban.startsWith('ES') || p.iban.length !== 24) return 'El IBAN espanol debe tener 24 caracteres y empezar por ES.';
            if (p.qrFile && p.qrFile.size > 2 * 1024 * 1024) return 'El QR no puede superar 2 MB.';
            return null;
        },
        getConfirmSummary: (p) => `Confirmar metodos de pago: Bizum <strong>${host.escapeHtml(p.bizum_num)}</strong>, IBAN <strong>${host.escapeHtml(p.iban)}</strong>${p.qrFile ? ', con nuevo QR Revolut' : ''}.`,
        execute: async (p) => {
            const r = await fetch('/api/admin/metodos-pago', {
                method: 'POST',
                credentials: 'same-origin',
                headers: host.getAuthHeaders(),
                body: JSON.stringify({ bizum_num: p.bizum_num, iban: p.iban })
            });
            if (r.status === 401) { host._adminSessionExpired(); return; }
            if (r.status === 403) { host.showToast('Sin permiso de escritura (solo lectura).', 'error'); return; }
            const data = await r.json().catch(() => ({}));
            if (data.status !== 'success') { host.showToast(data.message || 'Error actualizando metodos.', 'error'); return; }
            if (p.qrFile) {
                const fd = new FormData();
                fd.append('archivo', p.qrFile);
                const qrResp = await fetch('/api/admin/metodos-pago/qr-revolut', {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: AdminAuthenticator.getAdminAuthHeaders({ _skipContentType: true }),
                    body: fd
                });
                if (qrResp.status === 401) { host._adminSessionExpired(); return; }
                if (qrResp.status === 403) { host.showToast('Sin permiso de escritura (solo lectura).', 'error'); return; }
                const qrData = await qrResp.json().catch(() => ({}));
                if (qrData.status !== 'success') { host.showToast(qrData.message || 'Error subiendo QR.', 'error'); return; }
            }
            host.showToast('Metodos de pago actualizados. Esto no activa el pago manual: habilita aliados en la allowlist.', 'success');
            host.cargarDesdeApi();
        }
    });
  }

  function accionForzarSuplencia(host) {
    host._abrirModalAccionAdmin({
        title: 'Forzar competencia (Retador)',
        bodyHtml: `
            <label class="modal-importe-label" style="display:block; margin-bottom:6px;">ID del grupo *</label>
            <input type="number" id="accion-fs-grupo" placeholder="Ej: 1" style="width:100%; padding:8px; margin-bottom:12px; box-sizing:border-box;" />
            <label class="modal-importe-label" style="display:block; margin-bottom:6px;">Oficio *</label>
            <input type="text" id="accion-fs-oficio" placeholder="Ej: Fontanería" style="width:100%; padding:8px; margin-bottom:12px; box-sizing:border-box;" />
            <label class="modal-importe-label" style="display:block; margin-bottom:6px;">Código del aliado titular *</label>
            <input type="text" id="accion-fs-original" placeholder="Ej: A0001" style="width:100%; padding:8px; margin-bottom:12px; box-sizing:border-box;" />
            <label class="modal-importe-label" style="display:block; margin-bottom:6px;">Código del aliado Retador *</label>
            <input type="text" id="accion-fs-suplente" placeholder="Ej: A0002" style="width:100%; padding:8px; box-sizing:border-box;" />
        `,
        getPayload: () => ({
            grupo_id: document.getElementById('accion-fs-grupo')?.value?.trim(),
            oficio: (document.getElementById('accion-fs-oficio')?.value || '').trim(),
            aliado_original_codigo: (document.getElementById('accion-fs-original')?.value || '').trim(),
            retador_codigo: (document.getElementById('accion-fs-suplente')?.value || '').trim()
        }),
        validate: (p) => !p.grupo_id || !p.oficio || !p.aliado_original_codigo || !p.retador_codigo ? 'Todos los campos son obligatorios.' : null,
        getConfirmSummary: (p) => `¿Confirmar <strong>forzar competencia</strong>? Grupo ${p.grupo_id}, oficio ${p.oficio}. Titular: ${p.aliado_original_codigo} → Retador: ${p.retador_codigo}.`,
        execute: async (p) => {
            const r = await fetch('/api/admin/forzar-competencia', { method: 'POST', credentials: 'same-origin', headers: host.getAuthHeaders(), body: JSON.stringify({ grupo_id: parseInt(p.grupo_id, 10), oficio: p.oficio, aliado_original_codigo: p.aliado_original_codigo, retador_codigo: p.retador_codigo }) });
            if (r.status === 401) { host._adminSessionExpired(); return; }
            if (r.status === 403) { host.showToast('Sin permiso de escritura (solo lectura).', 'error'); return; }
            const data = await r.json().catch(() => ({}));
            if (data.status === 'success') { host.showToast(data.message || 'Competencia forzada.', 'success'); host.cargarDesdeApi(); }
            else { host.showToast(data.message || 'Error.', 'error'); }
        }
    });
  }

  function accionAbrirPlaza(host) {
    const self = this;
    host._abrirModalAccionAdmin({
        title: 'Abrir plaza',
        bodyHtml: `
            <label class="modal-importe-label" style="display:block; margin-bottom:6px;">ID del grupo *</label>
            <input type="number" id="accion-ap-grupo" placeholder="Ej: 1" style="width:100%; padding:8px; margin-bottom:12px; box-sizing:border-box;" />
            <label class="modal-importe-label" style="display:block; margin-bottom:8px;">Tipo</label>
            <div style="margin-bottom:12px;">
                <label style="display:inline-flex; align-items:center; gap:6px; margin-right:16px; cursor:pointer;">
                    <input type="radio" name="accion-ap-tipo" value="nueva" checked /> Nueva profesión (oficio del catálogo)
                </label>
                <label style="display:inline-flex; align-items:center; gap:6px; cursor:pointer;">
                    <input type="radio" name="accion-ap-tipo" value="reabrir" /> Reabrir plaza cerrada (oficio ya cerrado en el grupo)
                </label>
            </div>
            <label class="modal-importe-label" style="display:block; margin-bottom:6px;">Oficio *</label>
            <select id="accion-ap-oficio" style="width:100%; padding:8px; box-sizing:border-box; background:#222; color:#eee; border:1px solid #444;">
                <option value="">— Elige tipo y grupo primero —</option>
            </select>
        `,
        getPayload: () => ({
            grupo_id: document.getElementById('accion-ap-grupo')?.value?.trim(),
            oficio: (document.getElementById('accion-ap-oficio')?.value || '').trim()
        }),
        validate: (p) => !p.grupo_id || !p.oficio ? 'Grupo y oficio son obligatorios.' : null,
        getConfirmSummary: (p) => {
            const tipo = document.querySelector('input[name="accion-ap-tipo"]:checked')?.value || 'nueva';
            const texto = tipo === 'reabrir' ? 'reabrir la plaza cerrada' : 'abrir nueva profesión';
            return `¿Confirmar <strong>${texto}</strong> del oficio "${p.oficio}" en el grupo ${p.grupo_id}?`;
        },
        execute: async (p) => {
            const r = await fetch('/api/admin/abrir-plaza', { method: 'POST', credentials: 'same-origin', headers: host.getAuthHeaders(), body: JSON.stringify({ grupo_id: parseInt(p.grupo_id, 10), oficio: p.oficio }) });
            if (r.status === 401) { host._adminSessionExpired(); return; }
            const data = await r.json().catch(() => ({}));
            if (data.status === 'success') { host.showToast(data.message || 'Plaza abierta.', 'success'); host.cargarDesdeApi(); }
            else { host.showToast(data.message || 'Error.', 'error'); }
        },
        onShow: async (bodyEl) => {
            const grupoInput = bodyEl.querySelector('#accion-ap-grupo');
            const tipoRadios = bodyEl.querySelectorAll('input[name="accion-ap-tipo"]');
            const oficioSelect = bodyEl.querySelector('#accion-ap-oficio');
            if (!oficioSelect) return;
            let catalogNombres = [];
            try {
                const r = await fetch('/api/catalogo/oficios', { credentials: 'same-origin' });
                const d = await r.json();
                if (d.status === 'success' && Array.isArray(d.oficios))
                    catalogNombres = d.oficios.map(o => (o && o.nombre != null ? String(o.nombre) : (typeof o === 'string' ? o : ''))).filter(Boolean);
            } catch (_) {}
            function fillOficioSelect(opts, placeholder) {
                oficioSelect.innerHTML = '';
                const ph = document.createElement('option');
                ph.value = '';
                ph.textContent = placeholder || '— Elige —';
                oficioSelect.appendChild(ph);
                (opts || []).forEach(n => {
                    const texto = typeof n === 'object' && n && n.nombre != null ? String(n.nombre) : String(n || '');
                    if (!texto) return;
                    const o = document.createElement('option');
                    o.value = texto;
                    o.textContent = texto;
                    oficioSelect.appendChild(o);
                });
            }
            async function updateOficioOptions() {
                const tipo = bodyEl.querySelector('input[name="accion-ap-tipo"]:checked')?.value || 'nueva';
                const gid = (grupoInput && grupoInput.value) ? grupoInput.value.trim() : '';
                if (tipo === 'nueva') {
                    fillOficioSelect(catalogNombres, '— Elige oficio (nueva profesión) —');
                } else {
                    if (!gid) {
                        fillOficioSelect([], '— Indica ID del grupo —');
                        return;
                    }
                    try {
                        const r = await fetch('/api/admin/grupos/' + gid + '/oficios-cerrados', { credentials: 'same-origin', headers: self.getAuthHeaders() });
                        const d = await r.json();
                        const list = (d.oficios || []);
                        fillOficioSelect(list, list.length ? '— Elige oficio a reabrir —' : '— No hay plazas cerradas en este grupo —');
                    } catch (_) {
                        fillOficioSelect([], '— Error al cargar —');
                    }
                }
            }
            if (grupoInput) {
                grupoInput.addEventListener('change', updateOficioOptions);
                grupoInput.addEventListener('input', updateOficioOptions);
            }
            tipoRadios.forEach(radio => radio.addEventListener('change', updateOficioOptions));
            await updateOficioOptions();
        }
    });
  }

  function renderSolicitudesAdmin(host, solicitudes) {
    const tbody = document.getElementById('tbody-solicitudes-admin');
    const emptyEl = document.getElementById('solicitudes-admin-empty');
    if (!tbody) return;
    tbody.innerHTML = '';
    if (emptyEl) emptyEl.style.display = 'none';
    const list = Array.isArray(solicitudes) ? solicitudes : [];
    if (list.length === 0) {
        if (emptyEl) emptyEl.style.display = 'block';
        return;
    }
    list.forEach(s => {
        const tr = document.createElement('tr');
        const descCorta = (s.descripcion || '').substring(0, 60) + ((s.descripcion || '').length > 60 ? '…' : '');
        let tiempoResp = '—';
        if (s.created_at && s.atendido_at) {
            try {
                const c = new Date(s.created_at.replace('Z', ''));
                const a = new Date(s.atendido_at.replace('Z', ''));
                const seg = Math.floor((a - c) / 1000);
                if (seg >= 60) tiempoResp = Math.floor(seg / 60) + ' min'; else tiempoResp = seg + ' s';
            } catch (e) {}
        }
        const puedeMarcarAtendida = (s.estado === 'pendiente' || s.estado === 'candidato_pendiente') || (s.estado === 'atendida' && !(s.atendido_por_nombre || s.atendido_por_codigo) && !s.atendido_at);
        const btnAtender = puedeMarcarAtendida
            ? `<button type="button" class="btn-accion btn-marcar-atendida" data-solicitud-id="${s.id}" title="Registrar como atendida (Atendido por / Atendido at)">Marcar atendida</button>`
            : '';
        tr.innerHTML = `
            <td>${s.id || '—'}</td>
            <td>${host.escapeHtml((s.grupo_nombre || '') || ('#' + (s.grupo_id || '')))}</td>
            <td>${host.escapeHtml(s.solicitante_nombre || s.solicitante_codigo || '—')}</td>
            <td>${host.escapeHtml(s.oficio || '—')}</td>
            <td title="${host.escapeHtml(s.descripcion || '')}">${host.escapeHtml(descCorta)}</td>
            <td>${host.escapeHtml(s.estado || '—')}</td>
            <td>${s.created_at ? host.formatearHora(s.created_at) : '—'}</td>
            <td>${host.escapeHtml(s.atendido_por_nombre || s.atendido_por_codigo || '—')}</td>
            <td>${s.atendido_at ? host.formatearHora(s.atendido_at) : '—'}</td>
            <td>${tiempoResp}</td>
            <td>${btnAtender}</td>
        `;
        const btn = tr.querySelector('.btn-marcar-atendida');
        if (btn) btn.addEventListener('click', () => host.marcarSolicitudAtendidaAdmin(Number(btn.getAttribute('data-solicitud-id')), tr));
        tbody.appendChild(tr);
    });
  }

  function nombresRespuestaSemanal(s, tipo) {
    return (s.respuestas || [])
      .filter((r) => (r.tipo_respuesta || '') === tipo)
      .map((r) => r.aliado_nombre || r.aliado_codigo)
      .filter(Boolean);
  }

  function celdaRespuestasSemanales(host, s, tipo, countKey) {
    const count = Number(s[countKey]) || 0;
    const names = nombresRespuestaSemanal(s, tipo);
    if (!count) return '—';
    const label = names.join(', ');
    return `<span title="${host.escapeHtml(label)}">${count}${names.length ? ' · ' + host.escapeHtml(label) : ''}</span>`;
  }

  function renderSolicitudesSemanalesAdmin(host, payload) {
    const tbody = document.getElementById('tbody-solicitudes-semanales-admin');
    const emptyEl = document.getElementById('solicitudes-semanales-admin-empty');
    if (!tbody) return;
    let data = payload && typeof payload === 'object' && !Array.isArray(payload) ? payload : {};
    if (Array.isArray(payload)) data = { solicitudes: payload };
    if (payload && Array.isArray(payload.solicitudes)) host._solicitudesSemanalesAdmin = data;
    const cached = host._solicitudesSemanalesAdmin || data;
    const alcanceEl = document.getElementById('filtro-solicitudes-semanales-alcance');
    const alcance = alcanceEl ? alcanceEl.value : 'semana';
    let list = Array.isArray(cached.solicitudes) ? cached.solicitudes.slice() : [];
    if (alcance !== 'todas') {
      list = list.filter((s) => s.es_semana_actual);
    }
    tbody.innerHTML = '';
    if (emptyEl) emptyEl.style.display = list.length ? 'none' : 'block';
    list.forEach((s) => {
      const tr = document.createElement('tr');
      if (s.es_semana_actual) tr.classList.add('is-semana-actual');
      const desc = s.descripcion || '';
      const descCorta = desc.substring(0, 60) + (desc.length > 60 ? '…' : '');
      tr.innerHTML = `
            <td>${host.escapeHtml(s.semana_inicio || '—')}</td>
            <td>${host.escapeHtml((s.grupo_nombre || '') || ('#' + (s.grupo_id || '')))}</td>
            <td>${host.escapeHtml(s.solicitante_nombre || s.solicitante_codigo || '—')}</td>
            <td>${host.escapeHtml(s.oficio || '—')}</td>
            <td title="${host.escapeHtml(desc)}">${host.escapeHtml(descCorta || '—')}</td>
            <td>${host.escapeHtml(s.estado || '—')}</td>
            <td>${celdaRespuestasSemanales(host, s, 'puedo_ayudar', 'interesados_count')}</td>
            <td>${celdaRespuestasSemanales(host, s, 'conozco_alguien', 'recomendaciones_count')}</td>
            <td>${celdaRespuestasSemanales(host, s, 'no_puedo_ayudar', 'no_pueden_count')}</td>
            <td>${s.created_at ? host.formatearHora(s.created_at) : '—'}</td>
        `;
      tbody.appendChild(tr);
    });
  }

  function renderEventos(host, eventosData) {
    /**
     * Renderiza las últimas acciones relevantes del sistema (trazabilidad).
     */
    const lista = document.getElementById('eventos-list');
    if (!lista) return;

    lista.innerHTML = '';

    const eventos = Array.isArray(eventosData) ? eventosData : [];
    if (!eventos.length) {
        const empty = document.createElement('div');
        empty.className = 'evento-item';
        empty.textContent = 'Sin eventos recientes.';
        lista.appendChild(empty);
        return;
    }

    eventos.slice(0, 10).forEach(ev => {
        const item = document.createElement('div');
        item.className = 'evento-item';

        const tipo = document.createElement('div');
        tipo.className = 'evento-tipo';
        tipo.textContent = (ev.tipo || '').toUpperCase();

        const descripcion = document.createElement('div');
        descripcion.className = 'evento-descripcion';
        const actorTipo = ev.actor_tipo || 'sistema';
        const actorCodigo = ev.actor_codigo || '';
        const actorLabel = actorCodigo ? `${actorTipo.toUpperCase()} ${actorCodigo}` : actorTipo.toUpperCase();
        descripcion.textContent = `${ev.descripcion || ''} · ${actorLabel}`;

        const hora = document.createElement('div');
        hora.className = 'evento-hora';
        hora.textContent = ev.creado_en ? host.formatearHora(ev.creado_en) : '—';

        item.appendChild(tipo);
        item.appendChild(descripcion);
        item.appendChild(hora);

        lista.appendChild(item);
    });
  }

  function renderCompetenciasActivas(host, competencias) {
    const tbody = document.getElementById('tbody-competencias-activas');
    const emptyEl = document.getElementById('competencias-activas-empty');
    const wrap = document.getElementById('competencias-activas-wrap');
    if (!tbody) return;
    tbody.innerHTML = '';
    const lista = Array.isArray(competencias) ? competencias : [];
    if (emptyEl) emptyEl.style.display = lista.length ? 'none' : 'block';
    if (wrap) wrap.style.display = 'block';
    // Ordenar por tiempo descendente (más antiguas arriba)
    lista.sort((a, b) => {
        const ta = parseFloat(a.tiempo_en_competencia_horas) || 0;
        const tb = parseFloat(b.tiempo_en_competencia_horas) || 0;
        return tb - ta;
    });
    lista.forEach(c => {
        const grupo = host.escapeHtml(c.grupo || '—');
        const oficio = host.escapeHtml(c.oficio || '—');
        const titularNombre = host.escapeHtml((c.titular && c.titular.nombre) ? c.titular.nombre : '—');
        const titularScore = (c.titular && (c.titular.score_actual != null)) ? Number(c.titular.score_actual).toFixed(1) : '—';
        // Soporte para ambos nombres: retador (nuevo) y suplente (alias backward-compat)
        const retadorData = c.retador || c.suplente || null;
        const retadorNombre = host.escapeHtml((retadorData && retadorData.nombre) ? retadorData.nombre : '—');
        const retadorOrigen = host.escapeHtml((retadorData && retadorData.grupo_origen) ? retadorData.grupo_origen : '—');
        const retadorScore = (retadorData && (retadorData.score_actual != null)) ? Number(retadorData.score_actual).toFixed(1) : '—';
        const diasRest = (c.dias_restantes != null) ? String(c.dias_restantes) : '—';
        const tiempoHoras = (c.tiempo_en_competencia_horas != null) ? Number(c.tiempo_en_competencia_horas).toFixed(1) + ' h' : '—';
        const estado = host.escapeHtml((c.estado || 'activa').toLowerCase());
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${grupo}</td>
            <td>${oficio}</td>
            <td>${titularNombre}</td>
            <td>${titularScore}</td>
            <td>${retadorNombre}</td>
            <td>${retadorOrigen}</td>
            <td>${retadorScore}</td>
            <td>${diasRest}</td>
            <td>${tiempoHoras}</td>
            <td>${estado}</td>
        `;
        tbody.appendChild(tr);
    });
  }

  function renderCompetenciasPendientes(host, pendientes) {
    const tbody = document.getElementById('tbody-competencias-pendientes');
    const emptyEl = document.getElementById('competencias-pendientes-empty');
    const wrap = document.getElementById('competencias-pendientes-wrap');
    if (!tbody) return;
    tbody.innerHTML = '';
    const lista = Array.isArray(pendientes) ? pendientes : [];
    if (wrap) wrap.style.display = 'block';
    if (emptyEl) emptyEl.style.display = lista.length ? 'none' : 'block';
    lista.forEach(p => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${host.escapeHtml(p.aliado_nombre || p.aliado_codigo || '—')}</td>
            <td>${host.escapeHtml(p.oficio || '—')}</td>
            <td>${host.escapeHtml(p.codigo_postal || '—')}</td>
            <td>${host.escapeHtml(p.grupo_nombre || '—')}</td>
            <td>${p.score_al_crear != null ? p.score_al_crear : '—'}</td>
            <td>${p.creado_en ? new Date(p.creado_en).toLocaleString('es-ES') : '—'}</td>
        `;
        tbody.appendChild(tr);
    });
  }

  function renderCompetenciasHistorial(host, historial) {
    const tbody = document.getElementById('tbody-competencias-historial');
    const emptyEl = document.getElementById('competencias-historial-empty');
    const wrap = document.getElementById('competencias-historial-wrap');
    if (!tbody) return;
    tbody.innerHTML = '';
    const lista = Array.isArray(historial) ? historial : [];
    if (wrap) wrap.style.display = 'block';
    if (emptyEl) emptyEl.style.display = lista.length ? 'none' : 'block';
    lista.forEach(h => {
        const tr = document.createElement('tr');
        const cierre = h.fecha_cierre || h.fecha_fin_prevista;
        tr.innerHTML = `
            <td>${host.escapeHtml(h.grupo_nombre || '—')}</td>
            <td>${host.escapeHtml(h.oficio || '—')}</td>
            <td>${host.escapeHtml(h.titular_nombre || h.aliado_original_codigo || '—')}</td>
            <td>${host.escapeHtml(h.retador_nombre || h.retador_codigo || '—')}</td>
            <td>${host.escapeHtml(h.ganador_codigo || '—')}</td>
            <td>${h.score_titular_final != null ? h.score_titular_final : '—'}</td>
            <td>${h.score_retador_final != null ? h.score_retador_final : '—'}</td>
            <td>${cierre ? new Date(cierre).toLocaleString('es-ES') : '—'}</td>
        `;
        tbody.appendChild(tr);
    });
  }

  function renderInvitacionesRecientes(host, invitaciones) {
      const tbody = document.getElementById('admin-invitaciones-recientes-tbody');
      if (!tbody) return;
      const n = (v) => (v == null || v === '') ? '—' : String(v);
      const fmtFecha = (creadoEn) => {
          if (!creadoEn) return '—';
          try {
              const d = new Date(creadoEn);
              return isNaN(d.getTime()) ? creadoEn : d.toLocaleString('es-ES', { dateStyle: 'short', timeStyle: 'short' });
          } catch (_) { return creadoEn; }
      };
      if (!Array.isArray(invitaciones) || invitaciones.length === 0) {
          tbody.innerHTML = '<tr><td colspan="4">No hay invitaciones recientes</td></tr>';
          return;
      }
      tbody.innerHTML = invitaciones.map(inv => {
          const estado = inv.usado ? 'Usada' : 'Pendiente';
          const invitador = n(inv.invitador_nombre) + (inv.invitador_codigo ? ' (' + inv.invitador_codigo + ')' : '');
          return `<tr><td>${n(inv.codigo)}</td><td>${invitador}</td><td>${fmtFecha(inv.creado_en)}</td><td>${estado}</td></tr>`;
      }).join('');
}

function renderCampanasInvitacion(host, campanas) {
      const tbody = document.getElementById('admin-campanas-invitacion-tbody');
      if (!tbody) return;
      host._campanasInvitacion = Array.isArray(campanas) ? campanas : [];
      const n = (v) => (v == null || v === '') ? '—' : String(v);
      if (!Array.isArray(campanas) || campanas.length === 0) {
          tbody.innerHTML = '<tr><td colspan="5">No hay códigos multiuso creados</td></tr>';
          return;
      }
      tbody.innerHTML = campanas.map(campana => {
          const codigoValor = n(campana.codigo);
          const codigoSeguro = host.escapeHtml(codigoValor);
          const codigo = `<button type="button" class="btn-admin-action btn-ver-campana" data-codigo="${codigoSeguro}">${codigoSeguro}</button>`;
          const maxUsos = Number(campana.max_usos || 0);
          const usosActuales = Number(campana.usos_actuales || 0);
          const activo = Number(campana.activo || 0) === 1 && (!maxUsos || usosActuales < maxUsos);
          const estado = Number(campana.activo || 0) !== 1 ? 'Desactivado' : (maxUsos && usosActuales >= maxUsos ? 'Agotado' : 'Activo');
          const accion = activo
              ? `<button type="button" class="btn-admin-action danger btn-desactivar-campana" data-codigo="${codigoSeguro}">Desactivar</button>`
              : '<span style="color:#94a3b8;">—</span>';
          return `<tr><td>${codigo}</td><td>${n(campana.codigo_postal)}</td><td>${usosActuales}/${maxUsos || '∞'}</td><td>${estado}</td><td>${accion}</td></tr>`;
      }).join('');
}

async function cargarCampanasInvitacion(host) {
      try {
          const r = await fetch('/api/admin/invitacion-campanas?limite=30', {
              method: 'GET',
              credentials: 'same-origin',
              headers: AdminAuthenticator.getAdminAuthHeaders()
          });
          if (r.status === 401) { host._adminSessionExpired(); return; }
          const data = await (r.ok ? r.json().catch(() => null) : null);
          host.renderCampanasInvitacion(data && data.status === 'success' && Array.isArray(data.campanas) ? data.campanas : []);
      } catch (_) {
          host.showToast('No se pudieron recargar los codigos multiuso.', 'error');
      }
}

function buildCampanaRegistroUrl(host, codigo) {
      const origin = window.RUANA_PUBLIC_APP_URL || 'https://ruana-4293f.web.app';
      return `${origin}/invite.html?codigo=${encodeURIComponent(codigo || '')}`;
}

function buildCampanaQrUrl(host, registroUrl) {
      return 'https://api.qrserver.com/v1/create-qr-code/?size=220x220&data=' + encodeURIComponent(registroUrl || '');
}

function verDetalleCampanaInvitacion(host, codigo) {
      const campana = (host._campanasInvitacion || []).find(c => String(c.codigo || '') === String(codigo || ''));
      if (!campana) {
          host.showToast('No se encontro el codigo multiuso.', 'error');
          return;
      }
      const registroUrl = campana.registro_url || host.buildCampanaRegistroUrl(campana.codigo || codigo);
      host.renderCampanaInvitacionCreada({
          campana,
          registro_url: registroUrl,
          qr_url: campana.qr_url || host.buildCampanaQrUrl(registroUrl),
          modo: 'detalle'
      });
}

async function desactivarCampanaInvitacion(host, codigo) {
      if (!codigo) return;
      if (!confirm(`¿Desactivar el código multiuso ${codigo}? Dejará de validar inmediatamente.`)) return;
      try {
          const r = await fetch('/api/admin/invitacion-campanas/' + encodeURIComponent(codigo) + '/desactivar', {
              method: 'POST',
              credentials: 'same-origin',
              headers: host.getAuthHeaders()
          });
          if (r.status === 401) { host._adminSessionExpired(); return; }
          if (r.status === 403) { host.showToast('Sin permiso de escritura (solo lectura).', 'error'); return; }
          const data = await r.json().catch(() => ({}));
          if (r.ok && data.status === 'success') {
              host.showToast('Código multiuso desactivado.', 'success');
              host.cargarDesdeApi();
          } else {
              host.showToast(data.message || 'No se pudo desactivar el código.', 'error');
          }
      } catch (_) {
          host.showToast('Error de conexión al desactivar el código.', 'error');
      }
}

async function accionGenerarReporte(host) {
      try {
          const r = await fetch('/api/admin/generar-reporte', {
              method: 'POST',
              credentials: 'same-origin',
              headers: host.getAuthHeaders()
          });
          const data = await r.json().catch(() => ({}));
          if (data.status === 'success' && data.reporte) {
              const rep = data.reporte;
              const texto = `Aliados: ${rep.total_aliados} (activos: ${rep.aliados_activos}) · Solicitudes: ${rep.total_solicitudes} · Contactos: ${rep.total_contactos} · Grupos: ${rep.grupos_activos} · Competencias activas: ${rep.competencias_activas} · Plazas cerradas: ${rep.plazas_cerradas}`;
              host.showToast('Reporte generado. ' + texto, 'success');
              host.cargarDesdeApi();
          } else {
              host.showToast(data.message || 'Error al generar reporte.', 'error');
          }
      } catch (e) {
          host.showToast('Error de conexión.', 'error');
      }
}

async function cargarSolicitudesAdminConFiltros(host) {
      const estado = document.getElementById('filtro-solicitudes-estado')?.value || '';
      const grupoId = document.getElementById('filtro-solicitudes-grupo')?.value?.trim() || '';
      const desde = document.getElementById('filtro-solicitudes-desde')?.value || '';
      const hasta = document.getElementById('filtro-solicitudes-hasta')?.value || '';
      const authHeaders = AdminAuthenticator.getAdminAuthHeaders();
      try {
          const r = await fetch('/api/admin/solicitudes', { credentials: 'same-origin', headers: authHeaders });
          if (r.status === 401) { host._adminSessionExpired(); return; }
          const data = await r.json();
          const list = Array.isArray(data) ? data : [];
          let filtered = list;
          if (estado) filtered = filtered.filter(s => (s.estado || '') === estado);
          if (grupoId) filtered = filtered.filter(s => String(s.grupo_id) === grupoId);
          if (desde) filtered = filtered.filter(s => (s.created_at || '').slice(0, 10) >= desde);
          if (hasta) filtered = filtered.filter(s => (s.created_at || '').slice(0, 10) <= hasta);
          host.renderSolicitudesAdmin(filtered);
      } catch (e) {
          host.showToast('Error al cargar solicitudes', 'error');
      }
}

function accionFinalizarCompetenciasVencidas(host) {
    host._abrirModalAccionAdmin({
        title: 'Finalizar competencias vencidas',
        bodyHtml: '<p class="admin-subtitle" style="color:#fca5a5;">Cierra competencias cuya fecha de fin ya pasó. El aliado con mayor score permanece; el otro sale del grupo. <strong>Esta acción no se puede deshacer.</strong></p>',
        getPayload: () => ({}),
        validate: () => null,
        getConfirmSummary: () => 'Se ejecutará <strong>finalizar competencias vencidas</strong> sobre todas las competencias activas fuera de plazo. Los cambios en plazas y estados de aliados son permanentes.',
        execute: async () => {
            const r = await fetch('/api/competencia/finalizar-vencidas', {
                method: 'POST',
                credentials: 'same-origin',
                headers: host.getAuthHeaders(),
                body: '{}',
            });
            if (r.status === 401) { host._adminSessionExpired(); return; }
            if (r.status === 403) { host.showToast('Sin permiso de escritura (solo lectura).', 'error'); return; }
            const data = await r.json().catch(() => ({}));
            if (r.ok && data.status === 'success') {
                const n = data.finalizadas != null ? data.finalizadas : 0;
                host.showToast('Competencias finalizadas: ' + n, 'success');
                await host.cargarDesdeApi();
            } else {
                host.showToast(data.message || 'Error al finalizar competencias.', 'error');
            }
        },
    });
}

function accionPurgaMensual(host) {
    host._abrirModalAccionAdmin({
        title: 'Purgar aliados inactivos (purga mensual)',
        bodyHtml: '<p class="admin-subtitle" style="color:#fca5a5;">Ejecuta la purga de calidad: finaliza competencias vencidas y puede <strong>suspender temporalmente</strong> aliados en pool según reglas de score y meses sin ganar. <strong>No es reversible.</strong></p>',
        getPayload: () => ({}),
        validate: () => null,
        getConfirmSummary: () => 'Vas a ejecutar la <strong>purga mensual</strong>. Aliados suspendidos requieren acción admin para recuperar acceso. Confirma solo en el ciclo operativo correcto.',
        execute: async () => {
            const r = await fetch('/api/purga/mensual', {
                method: 'POST',
                credentials: 'same-origin',
                headers: host.getAuthHeaders(),
                body: '{}',
            });
            if (r.status === 401) { host._adminSessionExpired(); return; }
            if (r.status === 403) { host.showToast('Sin permiso de escritura (solo lectura).', 'error'); return; }
            const data = await r.json().catch(() => ({}));
            if (r.ok && (data.status === 'success' || data.expulsados_temporal != null)) {
                const exp = Array.isArray(data.expulsados_temporal) ? data.expulsados_temporal.length : 0;
                host.showToast('Purga completada. Suspendidos: ' + exp, 'success');
                await host.cargarDesdeApi();
            } else {
                host.showToast(data.message || 'Error en purga mensual.', 'error');
            }
        },
    });
}

async function marcarSolicitudAtendidaAdmin(host, solicitudId, tr) {
      const authHeaders = AdminAuthenticator.getAdminAuthHeaders();
      try {
          const r = await fetch(`/api/admin/solicitudes/${solicitudId}/atender`, {
              method: 'POST',
              credentials: 'same-origin',
              headers: { ...authHeaders, 'Content-Type': 'application/json' }
          });
          const data = await r.json().catch(() => ({}));
          if (r.ok && data.status === 'success') {
              host.showToast('Solicitud marcada como atendida');
              await host.cargarSolicitudesAdminConFiltros();
          } else {
              host.showToast(data.message || 'Error al marcar atendida', 'error');
          }
      } catch (e) {
          host.showToast('Error de conexión', 'error');
      }
}

modules.sistema = {
    accionCrearCampanaInvitacion: accionCrearCampanaInvitacion,
    renderCampanaInvitacionCreada: renderCampanaInvitacionCreada,
    accionCrearCodigoAliado: accionCrearCodigoAliado,
    renderCodigoAliadoCreado: renderCodigoAliadoCreado,
    accionCambiarReglas: accionCambiarReglas,
    renderMetodosPago: renderMetodosPago,
    bindPagoManualAllowlist: bindPagoManualAllowlist,
    accionEditarMetodosPago: accionEditarMetodosPago,
    accionForzarSuplencia: accionForzarSuplencia,
    accionAbrirPlaza: accionAbrirPlaza,
    renderSolicitudesAdmin: renderSolicitudesAdmin,
    renderSolicitudesSemanalesAdmin: renderSolicitudesSemanalesAdmin,
    renderEventos: renderEventos,
    renderCompetenciasActivas: renderCompetenciasActivas,
    renderCompetenciasPendientes: renderCompetenciasPendientes,
    renderCompetenciasHistorial: renderCompetenciasHistorial,
  
    renderInvitacionesRecientes: renderInvitacionesRecientes,
    renderCampanasInvitacion: renderCampanasInvitacion,
    cargarCampanasInvitacion: cargarCampanasInvitacion,
    buildCampanaRegistroUrl: buildCampanaRegistroUrl,
    buildCampanaQrUrl: buildCampanaQrUrl,
    verDetalleCampanaInvitacion: verDetalleCampanaInvitacion,
    desactivarCampanaInvitacion: desactivarCampanaInvitacion,
    accionGenerarReporte: accionGenerarReporte,
    accionPurgaMensual: accionPurgaMensual,
    accionFinalizarCompetenciasVencidas: accionFinalizarCompetenciasVencidas,
    cargarSolicitudesAdminConFiltros: cargarSolicitudesAdminConFiltros,
    marcarSolicitudAtendidaAdmin: marcarSolicitudAtendidaAdmin,
};
})(typeof window !== 'undefined' ? window : globalThis);
