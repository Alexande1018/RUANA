/**
 * Módulo PrivatePanel `grupo` (Campamento Base).
 * Render de competencia activa y estado del grupo territorial.
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
    acuerdos: null,
    centroComunicacion: null,
    invitaciones: null,
    alertas: null,
    catalogo: null,
    contactos: null,
    grupo: null,
    sync: null,
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

  function renderCompetencia(host) {
    const wrap = document.getElementById('competencia-banner-wrap');
    const tituloEl = document.getElementById('competencia-banner-titulo');
    const textoEl = document.getElementById('competencia-banner-texto');
    const metaEl = document.getElementById('competencia-banner-meta');
    if (!wrap || !tituloEl || !textoEl || !metaEl) return;

    const info = (host.aliado && host.aliado.competencia_info) ? host.aliado.competencia_info : null;
    wrap.classList.remove('pendiente', 'retador');
    wrap.style.display = 'none';
    if (!info || (!info.en_competencia && !info.competencia_pendiente)) {
        if (typeof host.renderAlertHub === 'function') host.renderAlertHub();
        return;
    }

    wrap.style.display = 'block';
    const oficio = info.oficio || (host.aliado && host.aliado.oficio) || 'tu oficio';
    const dias = info.dias_restantes != null ? info.dias_restantes : null;

    if (info.competencia_pendiente) {
        wrap.classList.add('pendiente');
        tituloEl.innerHTML = '<strong>Competencia pendiente</strong>';
        textoEl.textContent = info.mensaje || 'Esperando retador para iniciar la competencia por permanencia.';
        metaEl.textContent = 'Cuando haya un profesional disponible del mismo oficio y código postal, comenzará un periodo de 30 días.';
        if (typeof host.renderAlertHub === 'function') host.renderAlertHub();
        return;
    }

    const rol = info.rol || 'titular';
    if (rol === 'retador') wrap.classList.add('retador');

    if (rol === 'retador') {
        tituloEl.innerHTML = '<strong>Oportunidad de plaza</strong>';
        textoEl.textContent = 'Compites por la plaza del grupo principal. Durante 30 días, quien acumule mayor score permanece en la plaza.';
    } else {
        tituloEl.innerHTML = '<strong>En competencia</strong>';
        textoEl.textContent = `Compites por la permanencia en la plaza de ${oficio}. Al finalizar el periodo, gana quien tenga mayor score.`;
    }

    const partes = [];
    if (dias != null) partes.push(`${dias} día${dias === 1 ? '' : 's'} restante${dias === 1 ? '' : 's'}`);
    if (info.fecha_fin_prevista) {
        const fin = new Date(String(info.fecha_fin_prevista).replace(' ', 'T'));
        if (!isNaN(fin.getTime())) {
            partes.push('Fin previsto: ' + fin.toLocaleDateString('es-ES'));
        }
    }
    if (info.contrincante_codigo) {
        partes.push('Contrincante: ' + info.contrincante_codigo);
    }
    metaEl.textContent = partes.join(' · ');
    if (typeof host.renderAlertHub === 'function') host.renderAlertHub();
  }

  function renderGrupo(host) {
    const block = document.getElementById('grupo-panel-block');
    const grupoInfo = (host.aliado && host.aliado.grupo_info) ? host.aliado.grupo_info : null;

    if (!grupoInfo) {
        if (block) block.style.display = 'none';
        const nombreEl = document.getElementById('grupo-nombre');
        if (nombreEl) nombreEl.textContent = '---';
        ocultarTarjetasCrecimiento();
        if (window.AliadoShell && typeof window.AliadoShell.refresh === 'function') {
            window.AliadoShell.refresh();
        }
        return;
    }

    renderGrupoCrecimiento(host, grupoInfo);

    if (!block) return;

    block.style.display = 'block';
    const nombreEl = document.getElementById('grupo-nombre');
    const estadoEl = document.getElementById('grupo-estado');
    const numEl = document.getElementById('grupo-num-oficios');
    if (nombreEl) nombreEl.textContent = grupoInfo.nombre || '---';
    if (estadoEl) {
        if (grupoInfo.en_creacion) {
            estadoEl.textContent = 'En creación';
        } else {
            const estadoLabels = { 'activo': 'Activo', 'en_competencia': 'En competencia', 'disuelto': 'Disuelto' };
            estadoEl.textContent = estadoLabels[grupoInfo.estado] || grupoInfo.estado || '---';
        }
    }
    if (numEl) numEl.textContent = String(grupoInfo.num_oficios != null ? grupoInfo.num_oficios : 0);

    if (window.AliadoShell && typeof window.AliadoShell.refresh === 'function') {
        window.AliadoShell.refresh();
    }

    const faltantes = Array.isArray(grupoInfo.oficios_faltantes) ? [...grupoInfo.oficios_faltantes] : [];
    const LIMIT_PREVIEW = 5;
    const container = document.getElementById('grupo-oficios-faltantes-wrap');
    const preview = document.getElementById('oficios-faltantes-preview');
    const shortList = document.getElementById('oficios-faltantes-short');
    const btnVerTodos = document.getElementById('btn-ver-todos-oficios');
    const expanded = document.getElementById('oficios-faltantes-expanded');
    const fullListEl = document.getElementById('oficios-faltantes-full-list');
    const searchInput = document.getElementById('oficios-faltantes-search');
    const emptyMsg = document.getElementById('oficios-faltantes-empty');

    if (!container) return;

    if (faltantes.length === 0) {
        if (preview) preview.style.display = 'none';
        if (expanded) expanded.style.display = 'none';
        if (emptyMsg) { emptyMsg.style.display = 'block'; emptyMsg.textContent = 'Ninguno'; }
        container.removeAttribute('data-oficios-faltantes');
        return;
    }

    container.setAttribute('data-oficios-faltantes', JSON.stringify(faltantes));
    if (emptyMsg) emptyMsg.style.display = 'none';

    const previewItems = faltantes.slice(0, LIMIT_PREVIEW);
    if (shortList) {
        shortList.innerHTML = previewItems.map(o => {
            const texto = typeof o === 'object' && o && o.nombre != null ? String(o.nombre) : String(o || '');
            return `<span class="oficios-faltantes-tag" data-oficio="${texto.replace(/"/g, '&quot;')}" title="Generar código de invitación">${host.escapeHtml(texto)}</span>`;
        }).join('');
    }
    if (btnVerTodos) {
        btnVerTodos.style.display = faltantes.length > LIMIT_PREVIEW ? 'inline-block' : 'none';
        btnVerTodos.textContent = `+ Ver todos (${faltantes.length})`;
    }
    if (preview) preview.style.display = 'flex';
    if (expanded) expanded.style.display = 'none';
    if (searchInput) searchInput.value = '';
    host.renderOficiosFaltantesFullList(faltantes);
  }

  function ocultarTarjetasCrecimiento() {
    document.querySelectorAll('[data-grupo-crecimiento-card]').forEach((card) => {
      card.style.display = 'none';
    });
  }

  function renderGrupoCrecimiento(host, grupoInfo) {
    const cards = document.querySelectorAll('[data-grupo-crecimiento-card]');
    const enCreacion = !!(grupoInfo && grupoInfo.en_creacion);

    if (!cards.length) return;

    if (!enCreacion) {
      ocultarTarjetasCrecimiento();
      return;
    }

    const numAliados = grupoInfo.num_aliados != null ? grupoInfo.num_aliados : 0;
    const crecimiento = grupoInfo.crecimiento || {};
    const obtenidas = crecimiento.recompensas_obtenidas != null ? crecimiento.recompensas_obtenidas : 0;
    const maxRecompensas = crecimiento.recompensas_max != null ? crecimiento.recompensas_max : 10;
    const scoreObtenido = crecimiento.score_obtenido != null ? crecimiento.score_obtenido : 0;
    const limiteAlcanzado = !!crecimiento.limite_alcanzado;

    cards.forEach((card) => {
      const textoEl = card.querySelector('.grupo-crecimiento-texto');
      const recompensaEl = card.querySelector('.grupo-crecimiento-recompensa');
      const progresoEl = card.querySelector('.grupo-crecimiento-progreso');
      const btn = card.querySelector('.btn-invitar-crecimiento-grupo');

      card.style.display = 'block';
      if (textoEl) {
        textoEl.textContent = 'Somos ' + numAliados + ' profesional' + (numAliados === 1 ? '' : 'es') +
          ' en este grupo. Invita a un profesional de cualquier oficio que conozcas para ampliar nuestra red y aumentar las posibilidades de encontrar nuevas oportunidades.';
      }
      if (recompensaEl) {
        if (limiteAlcanzado) {
          recompensaEl.style.display = 'none';
          recompensaEl.textContent = '';
        } else {
          recompensaEl.style.display = 'block';
          recompensaEl.textContent = 'Además, por cada aliado que invites y se registre correctamente en RUANA recibirás +5 puntos de Score. Puedes conseguir hasta 50 puntos.';
        }
      }
      if (progresoEl) {
        if (obtenidas > 0) {
          progresoEl.style.display = 'block';
          progresoEl.textContent = obtenidas + ' de ' + maxRecompensas + ' recompensas · Has conseguido +' + scoreObtenido + ' Score';
        } else {
          progresoEl.style.display = 'none';
          progresoEl.textContent = '';
        }
      }
      if (btn) btn.disabled = false;
    });
  }

  function renderOficiosFaltantesFullList(host, oficios) {
      const fullListEl = document.getElementById('oficios-faltantes-full-list');
      if (!fullListEl) return;
      const query = (document.getElementById('oficios-faltantes-search') || {}).value || '';
      const q = query.trim().toLowerCase();
      const toText = (o) => (typeof o === 'object' && o && o.nombre != null ? String(o.nombre) : String(o || ''));
      const list = q ? oficios.filter(o => toText(o).toLowerCase().includes(q)) : oficios;
      fullListEl.innerHTML = list.map(o => {
          const texto = toText(o);
          return `<span class="oficio-item" data-oficio="${texto.replace(/"/g, '&quot;')}" title="Generar código de invitación">${host.escapeHtml(texto)}</span>`;
      }).join('');
  }

  function expandirOficiosFaltantes(host) {
      const preview = document.getElementById('oficios-faltantes-preview');
      const expanded = document.getElementById('oficios-faltantes-expanded');
      const searchInput = document.getElementById('oficios-faltantes-search');
      if (preview) preview.style.display = 'none';
      if (expanded) expanded.style.display = 'block';
      if (searchInput) { searchInput.value = ''; searchInput.focus(); }
      const container = document.getElementById('grupo-oficios-faltantes-wrap');
      const data = container && container.getAttribute('data-oficios-faltantes');
      const oficios = data ? JSON.parse(data) : [];
      host.renderOficiosFaltantesFullList(oficios);
  }

  function ocultarOficiosFaltantes(host) {
      const preview = document.getElementById('oficios-faltantes-preview');
      const expanded = document.getElementById('oficios-faltantes-expanded');
      const searchInput = document.getElementById('oficios-faltantes-search');
      if (preview) preview.style.display = 'flex';
      if (expanded) expanded.style.display = 'none';
      if (searchInput) searchInput.value = '';
  }

  function filtrarOficiosFaltantes(host) {
      const container = document.getElementById('grupo-oficios-faltantes-wrap');
      const data = container && container.getAttribute('data-oficios-faltantes');
      const oficios = data ? JSON.parse(data) : [];
      host.renderOficiosFaltantesFullList(oficios);
  }

modules.grupo = {
    renderCompetencia: renderCompetencia,
    renderGrupo: renderGrupo,
  
    renderOficiosFaltantesFullList: renderOficiosFaltantesFullList,
    expandirOficiosFaltantes: expandirOficiosFaltantes,
    ocultarOficiosFaltantes: ocultarOficiosFaltantes,
    filtrarOficiosFaltantes: filtrarOficiosFaltantes,
};
})(typeof window !== 'undefined' ? window : globalThis);
