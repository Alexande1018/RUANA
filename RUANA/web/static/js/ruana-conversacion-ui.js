/**
 * Utilidades visuales para conversación de encargo (negociación guiada).
 * Sin estado propio: funciones puras reutilizables desde Perfil y negociación.
 */
(function (global) {
    'use strict';

    const PASO_LABELS = {
        servicio: 'Servicio',
        fecha: 'Fecha',
        hora: 'Hora',
        direccion: 'Dirección',
        precio: 'Precio',
        observaciones: 'Observaciones',
    };

    function escapeHtml(str) {
        if (str == null || str === '') return '';
        const d = document.createElement('div');
        d.textContent = String(str);
        return d.innerHTML;
    }

    function formatValor(campo, valor) {
        if (campo === 'fecha' && valor) {
            try {
                const d = new Date(valor + 'T12:00:00');
                return d.toLocaleDateString('es-ES', {
                    weekday: 'short', day: 'numeric', month: 'short', year: 'numeric',
                });
            } catch (e) { /* fallthrough */ }
        }
        if (campo === 'precio' && valor != null && valor !== '') {
            const n = Number(valor);
            if (Number.isFinite(n)) return n.toFixed(2).replace(/\.00$/, '') + ' €';
        }
        return valor;
    }

    function formatTimeShort(date) {
        if (!date || isNaN(date.getTime())) return '';
        return date.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' });
    }

    function formatRelativeTime(isoOrDate) {
        if (!isoOrDate) return '';
        const d = isoOrDate instanceof Date ? isoOrDate : new Date(isoOrDate);
        if (isNaN(d.getTime())) return '';
        const now = new Date();
        const diffMs = now - d;
        const diffMin = Math.floor(diffMs / 60000);
        if (diffMin < 1) return 'ahora';
        if (diffMin < 60) return diffMin + ' min';
        const diffH = Math.floor(diffMin / 60);
        if (diffH < 24) return diffH + ' h';
        const diffD = Math.floor(diffH / 24);
        if (diffD < 7) return diffD + ' d';
        return d.toLocaleDateString('es-ES', { day: 'numeric', month: 'short' });
    }

    function dayKey(date) {
        return date.getFullYear() + '-' + date.getMonth() + '-' + date.getDate();
    }

    function formatDaySeparator(date) {
        const now = new Date();
        const today = dayKey(now);
        const yesterday = new Date(now);
        yesterday.setDate(yesterday.getDate() - 1);
        const key = dayKey(date);
        if (key === today) return 'Hoy';
        if (key === dayKey(yesterday)) return 'Ayer';
        return date.toLocaleDateString('es-ES', {
            weekday: 'long', day: 'numeric', month: 'long',
        });
    }

    function findProfesional(host, codigo) {
        const cod = String(codigo || '').trim();
        if (!cod || !host) return null;
        const list = Array.isArray(host.profesionales) ? host.profesionales : [];
        return list.find(function (p) {
            return String(p.codigo || '').trim() === cod
                || String(p.id || '').padStart(5, '0') === cod;
        }) || null;
    }

    function resolveContraparte(host, contacto) {
        const miCodigo = String(
            (host && (host.codigoAliado || (host.aliado && host.aliado.codigo))) || ''
        ).trim();
        const sol = String(contacto.solicitante_codigo || '').trim();
        const pro = String(contacto.profesional_codigo || '').trim();
        const otroCodigo = miCodigo === sol ? pro : (miCodigo === pro ? sol : (pro || sol));
        const prof = findProfesional(host, otroCodigo);
        const nombre = (prof && prof.nombre) || ('Aliado ' + otroCodigo);
        const oficio = (prof && prof.oficio) || (contacto.servicio || 'Profesional');
        const fotoUrl = (prof && (prof.foto_perfil_url || prof.foto_perfil)) || '';
        return {
            codigo: otroCodigo,
            nombre: nombre,
            oficio: oficio,
            fotoUrl: fotoUrl,
        };
    }

    function renderAvatarHtml(host, fotoUrl, nombre, className) {
        if (host && typeof host.renderAvatarHtml === 'function') {
            return host.renderAvatarHtml(fotoUrl, nombre, className || 'ruana-msg-avatar', 'estable');
        }
        const iniciales = (nombre || '?').split(/\s+/).filter(Boolean).slice(0, 2)
            .map(function (p) { return p[0]; }).join('').toUpperCase().slice(0, 2) || '?';
        if (fotoUrl) {
            return '<div class="' + escapeHtml(className || 'ruana-msg-avatar') + ' avatar-has-photo">' +
                '<img src="' + escapeHtml(fotoUrl) + '" alt="" class="ruana-avatar-photo"></div>';
        }
        return '<div class="' + escapeHtml(className || 'ruana-msg-avatar') + '" aria-hidden="true">' +
            '<span class="ruana-avatar-iniciales">' + escapeHtml(iniciales) + '</span></div>';
    }

    function previewFromContacto(host, contacto) {
        const meta = contacto.negociacion_meta || {};
        const eventos = contacto._preview_eventos;
        let texto = '';
        if (Array.isArray(eventos) && eventos.length) {
            const last = eventos[eventos.length - 1];
            texto = (last && last.mensaje) ? String(last.mensaje) : '';
        }
        if (!texto) {
            texto = meta.siguiente_accion || meta.contexto || contacto.servicio || 'Encargo activo';
        }
        texto = texto.replace(/[«»]/g, '').trim();
        if (texto.length > 72) texto = texto.slice(0, 72) + '…';
        const ts = contacto.actualizado_en || contacto.creado_en;
        return { texto: texto, tiempo: formatRelativeTime(ts) };
    }

    function countMensajesPendientes(contactos) {
        const list = Array.isArray(contactos) ? contactos : [];
        return list.filter(function (c) { return c && c.negociacion_requiere_mi_respuesta; }).length;
    }

    function sortContactosParaMensajes(contactos) {
        return (Array.isArray(contactos) ? contactos.slice() : []).sort(function (a, b) {
            const ra = a.negociacion_requiere_mi_respuesta ? 1 : 0;
            const rb = b.negociacion_requiere_mi_respuesta ? 1 : 0;
            if (rb !== ra) return rb - ra;
            const ta = new Date(a.actualizado_en || a.creado_en || 0).getTime();
            const tb = new Date(b.actualizado_en || b.creado_en || 0).getTime();
            return tb - ta;
        });
    }

    function eventTypeLabel(tipo) {
        const map = {
            propuesta: 'Propuesta',
            contraoferta: 'Contraoferta',
            aceptacion: 'Confirmado',
            sistema: 'RUANA',
        };
        return map[tipo] || 'Evento';
    }

    function htmlEventCard(ev, opts) {
        const o = opts || {};
        const tipo = ev.tipo || 'sistema';
        const campo = ev.campo || '';
        const label = PASO_LABELS[campo] || campo;
        const valor = formatValor(campo, ev.valor || '');
        const fecha = ev.creado_en ? new Date(ev.creado_en) : null;
        const time = fecha ? formatTimeShort(fecha) : '';
        const tipoCls = 'neg-event-card--' + tipo;

        if (tipo === 'aceptacion') {
            return '<div class="neg-ruana-event neg-ruana-event--aceptacion" role="status">' +
                '<span class="neg-ruana-event-icon" aria-hidden="true">✓</span>' +
                '<div class="neg-ruana-event-body">' +
                '<span class="neg-ruana-event-title">Acuerdo en ' + escapeHtml(label.toLowerCase()) + '</span>' +
                (valor ? '<span class="neg-ruana-event-valor">' + escapeHtml(String(valor)) + '</span>' : '') +
                (time ? '<span class="neg-ruana-event-time">' + escapeHtml(time) + '</span>' : '') +
                '</div></div>';
        }

        if (tipo === 'propuesta' || tipo === 'contraoferta') {
            return '<article class="neg-event-card ' + tipoCls + '" aria-label="' + escapeHtml(eventTypeLabel(tipo)) + '">' +
                '<header class="neg-event-card-head">' +
                '<span class="neg-event-card-kicker">' + escapeHtml(eventTypeLabel(tipo)) + '</span>' +
                (time ? '<time class="neg-event-card-time" datetime="' + escapeHtml(ev.creado_en || '') + '">' + escapeHtml(time) + '</time>' : '') +
                '</header>' +
                '<dl class="neg-event-card-dl">' +
                (label ? '<div class="neg-event-card-row"><dt>' + escapeHtml(label) + '</dt><dd>' + escapeHtml(String(valor || '—')) + '</dd></div>' : '') +
                '</dl>' +
                (ev.mensaje && !valor ? '<p class="neg-event-card-msg">' + escapeHtml(ev.mensaje) + '</p>' : '') +
                '</article>';
        }

        return '<div class="neg-ruana-event neg-ruana-event--sistema" role="status">' +
            '<span class="neg-ruana-event-line" aria-hidden="true"></span>' +
            '<span class="neg-ruana-event-text">' + escapeHtml(ev.mensaje || 'RUANA') + '</span>' +
            (time ? '<span class="neg-ruana-event-time">' + escapeHtml(time) + '</span>' : '') +
            '<span class="neg-ruana-event-line" aria-hidden="true"></span>' +
            '</div>';
    }

    function htmlMessageGroup(group, escapeFn) {
        const esc = escapeFn || escapeHtml;
        const side = group.side;
        const cls = 'neg-msg-group neg-msg-group--' + side;
        const showHeader = group.showHeader !== false;
        const nameHtml = showHeader && group.name
            ? '<span class="neg-msg-name">' + esc(group.name) + '</span>' : '';
        const avatarHtml = showHeader && group.avatarHtml
            ? group.avatarHtml : '';
        const bubbles = group.messages.map(function (m) {
            return '<div class="neg-msg-bubble"><p class="neg-msg-text">' + esc(m.text) + '</p></div>';
        }).join('');
        const timeHtml = group.time
            ? '<time class="neg-msg-time">' + esc(group.time) + '</time>' : '';
        return '<div class="' + cls + '">' +
            (showHeader ? '<div class="neg-msg-group-head">' + avatarHtml + nameHtml + '</div>' : '') +
            '<div class="neg-msg-stack">' + bubbles + '</div>' +
            timeHtml +
            '</div>';
    }

    function htmlDaySeparator(label) {
        return '<div class="neg-day-sep" role="separator"><span>' + escapeHtml(label) + '</span></div>';
    }

    /**
     * Construye HTML del timeline con agrupación y separadores temporales.
     */
    function buildTimelineHtml(config) {
        const items = config.items || [];
        const escapeFn = config.escapeHtml || escapeHtml;
        const parts = [];
        let lastDay = '';
        let currentGroup = null;

        function flushGroup() {
            if (currentGroup && currentGroup.messages.length) {
                parts.push(htmlMessageGroup(currentGroup, escapeFn));
            }
            currentGroup = null;
        }

        function pushMessage(side, name, avatarHtml, text, time, date) {
            const dk = date ? dayKey(date) : '';
            if (dk && dk !== lastDay) {
                flushGroup();
                parts.push(htmlDaySeparator(formatDaySeparator(date)));
                lastDay = dk;
            }
            if (currentGroup && currentGroup.side === side && currentGroup.name === name) {
                currentGroup.messages.push({ text: text });
            } else {
                flushGroup();
                currentGroup = {
                    side: side,
                    name: name,
                    avatarHtml: avatarHtml,
                    messages: [{ text: text }],
                    time: time,
                    showHeader: true,
                };
            }
        }

        items.forEach(function (item) {
            if (item.kind === 'day') {
                flushGroup();
                if (item.label !== lastDay) {
                    parts.push(htmlDaySeparator(item.label));
                    lastDay = item.dayKey || item.label;
                }
                return;
            }
            if (item.kind === 'event') {
                flushGroup();
                parts.push(htmlEventCard(item.event, config));
                if (item.event && item.event.creado_en) {
                    lastDay = dayKey(new Date(item.event.creado_en));
                }
                return;
            }
            if (item.kind === 'message') {
                pushMessage(
                    item.side,
                    item.name,
                    item.avatarHtml,
                    item.text,
                    item.time,
                    item.date
                );
            }
        });
        flushGroup();
        return parts.join('');
    }

    const api = {
        PASO_LABELS: PASO_LABELS,
        escapeHtml: escapeHtml,
        formatValor: formatValor,
        formatTimeShort: formatTimeShort,
        formatRelativeTime: formatRelativeTime,
        formatDaySeparator: formatDaySeparator,
        dayKey: dayKey,
        findProfesional: findProfesional,
        resolveContraparte: resolveContraparte,
        renderAvatarHtml: renderAvatarHtml,
        previewFromContacto: previewFromContacto,
        countMensajesPendientes: countMensajesPendientes,
        sortContactosParaMensajes: sortContactosParaMensajes,
        htmlEventCard: htmlEventCard,
        htmlMessageGroup: htmlMessageGroup,
        htmlDaySeparator: htmlDaySeparator,
        buildTimelineHtml: buildTimelineHtml,
        eventTypeLabel: eventTypeLabel,
    };

    global.RuanaConversacionUI = api;
})(typeof window !== 'undefined' ? window : globalThis);
