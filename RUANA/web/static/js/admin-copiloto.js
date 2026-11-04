/**
 * Copiloto RUANA — versión del panel de administración.
 *
 * Mismo panel que el del aliado, pero aquí las preguntas son sobre la red:
 * altas pendientes, soporte sin responder, conflictos de pago, riesgo y
 * territorio. Todo sale de /api/admin/copiloto/*, que construye el backend con
 * datos reales. Este fichero solo pinta y navega.
 */
(function (global) {
    'use strict';

    var CLAVE_HISTORIAL = 'ruana_copiloto_admin_hist';
    var MAX_HISTORIAL = 8;

    var estado = {
        montado: false,
        abierto: false,
        cargado: false,
        enviando: false,
        ia: null,
        historial: []
    };

    var dom = {};

    // ---------------------------------------------------------------- utils

    function getApiBase() {
        try {
            if (typeof global.getApiBase === 'function') {
                return String(global.getApiBase() || '').replace(/\/$/, '');
            }
        } catch (e) { /* ignore */ }
        var base = global.RUANA_API_BASE
            || (typeof global.location !== 'undefined' ? global.location.origin : '');
        return String(base || '').replace(/\/$/, '');
    }

    function authHeaders(extra) {
        var cabeceras = Object.assign({ 'Content-Type': 'application/json' }, extra || {});
        try {
            if (typeof global.getRuanaAuthHeaders === 'function') {
                return global.getRuanaAuthHeaders(cabeceras);
            }
        } catch (e) { /* ignore */ }
        try {
            var sid = global.sessionStorage && (
                sessionStorage.getItem('admin_session_id') ||
                sessionStorage.getItem('ruana_session_id')
            );
            if (sid) cabeceras['X-Ruana-Session-Id'] = sid;
        } catch (e) { /* ignore */ }
        return cabeceras;
    }

    function esc(texto) {
        return String(texto == null ? '' : texto)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function conSaltos(texto) {
        return esc(texto).replace(/\n/g, '<br>');
    }

    function cargarHistorial() {
        try {
            var crudo = global.sessionStorage && sessionStorage.getItem(CLAVE_HISTORIAL);
            var datos = crudo ? JSON.parse(crudo) : [];
            if (Array.isArray(datos)) estado.historial = datos.slice(-MAX_HISTORIAL);
        } catch (e) {
            estado.historial = [];
        }
    }

    function guardarHistorial() {
        try {
            if (global.sessionStorage) {
                sessionStorage.setItem(
                    CLAVE_HISTORIAL,
                    JSON.stringify(estado.historial.slice(-MAX_HISTORIAL))
                );
            }
        } catch (e) { /* ignore */ }
    }

    function anotar(rol, texto) {
        estado.historial.push({ rol: rol, texto: String(texto || '').slice(0, 1200) });
        estado.historial = estado.historial.slice(-MAX_HISTORIAL);
        guardarHistorial();
    }

    // ------------------------------------------------------------------ DOM

    // Nodi: la mascota. Si no está cargada, cae al icono de siempre.
    function iconoMascota() {
        try {
            if (global.RuanaMascota && typeof global.RuanaMascota.svg === 'function') {
                return global.RuanaMascota.svg({ clase: 'es-fab', titulo: false });
            }
        } catch (e) { /* ignore */ }
        return ICONO;
    }

    var ICONO =
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" ' +
        'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
        '<path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z"/>' +
        '<path d="M18 15.5l.9 2.1 2.1.9-2.1.9-.9 2.1-.9-2.1-2.1-.9 2.1-.9z"/></svg>';

    var ICONO_ENVIAR =
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" ' +
        'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
        '<path d="M22 2L11 13"/><path d="M22 2l-7 20-4-9-9-4z"/></svg>';

    function crearEstructura() {
        var fab = document.createElement('button');
        fab.type = 'button';
        fab.className = 'ruana-copiloto-fab';
        fab.id = 'ruana-copiloto-admin-fab';
        fab.setAttribute('aria-label', 'Abrir el copiloto de RUANA');
        fab.setAttribute('aria-expanded', 'false');
        fab.innerHTML = iconoMascota() + '<span>Copiloto</span>' +
            '<span class="ruana-copiloto-fab-dot" id="ruana-copiloto-admin-dot" hidden></span>';

        var panel = document.createElement('section');
        panel.className = 'ruana-copiloto-panel';
        panel.id = 'ruana-copiloto-admin-panel';
        panel.setAttribute('role', 'dialog');
        panel.setAttribute('aria-labelledby', 'ruana-copiloto-admin-titulo');
        panel.setAttribute('aria-hidden', 'true');
        panel.innerHTML = [
            '<div class="ruana-copiloto-head">',
            '  <div class="ruana-copiloto-avatar">', iconoMascota(), '</div>',
            '  <div class="ruana-copiloto-titulos">',
            '    <h2 class="ruana-copiloto-titulo" id="ruana-copiloto-admin-titulo">Copiloto · Admin</h2>',
            '    <p class="ruana-copiloto-sub">',
            '      <span class="ruana-copiloto-live" id="ruana-copiloto-admin-live"></span>',
            '      <span id="ruana-copiloto-admin-modo">Asistente de la red</span>',
            '    </p>',
            '  </div>',
            '  <button type="button" class="ruana-copiloto-cerrar" id="ruana-copiloto-admin-cerrar" aria-label="Cerrar">✕</button>',
            '</div>',
            '<div class="ruana-copiloto-scroll" id="ruana-copiloto-admin-scroll" role="log" aria-live="polite"></div>',
            '<div class="ruana-copiloto-chips" id="ruana-copiloto-admin-chips"></div>',
            '<div class="ruana-copiloto-entrada">',
            '  <textarea class="ruana-copiloto-input" id="ruana-copiloto-admin-input" rows="1" maxlength="600"',
            '    placeholder="Pregúntame por la red…" aria-label="Escribe tu pregunta"></textarea>',
            '  <button type="button" class="ruana-copiloto-enviar" id="ruana-copiloto-admin-enviar" aria-label="Enviar">',
            ICONO_ENVIAR,
            '  </button>',
            '</div>',
            '<div class="ruana-copiloto-pie">',
            '  <span id="ruana-copiloto-admin-pie">Datos reales de la red</span>',
            '</div>'
        ].join('');

        document.body.appendChild(fab);
        document.body.appendChild(panel);

        dom.fab = fab;
        dom.panel = panel;
        dom.scroll = panel.querySelector('#ruana-copiloto-admin-scroll');
        dom.chips = panel.querySelector('#ruana-copiloto-admin-chips');
        dom.input = panel.querySelector('#ruana-copiloto-admin-input');
        dom.enviar = panel.querySelector('#ruana-copiloto-admin-enviar');
        dom.modo = panel.querySelector('#ruana-copiloto-admin-modo');
        dom.live = panel.querySelector('#ruana-copiloto-admin-live');
        dom.dot = fab.querySelector('#ruana-copiloto-admin-dot');
        dom.pie = panel.querySelector('#ruana-copiloto-admin-pie');
    }

    function enlazar() {
        dom.fab.addEventListener('click', alternar);
        dom.panel.querySelector('#ruana-copiloto-admin-cerrar').addEventListener('click', cerrar);
        dom.enviar.addEventListener('click', function () { enviar(dom.input.value); });
        dom.input.addEventListener('keydown', function (ev) {
            if (ev.key === 'Enter' && !ev.shiftKey) {
                ev.preventDefault();
                enviar(dom.input.value);
            }
        });
        dom.input.addEventListener('input', function () {
            dom.input.style.height = 'auto';
            dom.input.style.height = Math.min(110, dom.input.scrollHeight) + 'px';
        });
        document.addEventListener('keydown', function (ev) {
            if (ev.key === 'Escape' && estado.abierto) cerrar();
        });
    }

    // ---------------------------------------------------------- pintar UI

    function irArriba() {
        if (dom.scroll) dom.scroll.scrollTop = 0;
    }

    function desplazar() {
        if (dom.scroll) dom.scroll.scrollTop = dom.scroll.scrollHeight;
    }

    function burbuja(texto, clase) {
        var div = document.createElement('div');
        div.className = 'ruana-copiloto-burbuja ' + (clase || 'es-bot');
        div.innerHTML = conSaltos(texto);
        dom.scroll.appendChild(div);
        desplazar();
    }

    function mostrarEscribiendo() {
        var div = document.createElement('div');
        div.className = 'ruana-copiloto-typing';
        div.id = 'ruana-copiloto-admin-typing';
        div.innerHTML = '<span></span><span></span><span></span>';
        dom.scroll.appendChild(div);
        desplazar();
    }

    function quitarEscribiendo() {
        var el = document.getElementById('ruana-copiloto-admin-typing');
        if (el && el.parentNode) el.parentNode.removeChild(el);
    }

    function pintarJugadas(jugadas) {
        if (!Array.isArray(jugadas) || !jugadas.length) return;
        var caja = document.createElement('div');
        caja.className = 'ruana-copiloto-jugadas';
        jugadas.forEach(function (jugada) {
            var card = document.createElement('div');
            card.className = 'ruana-copiloto-jugada' +
                (jugada.urgencia === 'alta' ? ' es-urgente' : '');

            var titulo = document.createElement('p');
            titulo.className = 'ruana-copiloto-jugada-titulo';
            titulo.textContent = jugada.titulo || '';
            card.appendChild(titulo);

            var detalle = document.createElement('p');
            detalle.className = 'ruana-copiloto-jugada-detalle';
            detalle.textContent = jugada.detalle || '';
            card.appendChild(detalle);

            if (jugada.accion) {
                var cta = document.createElement('button');
                cta.type = 'button';
                cta.className = 'ruana-copiloto-cta';
                cta.textContent = jugada.cta || 'Abrir';
                cta.addEventListener('click', function () { ejecutarAccion(jugada.accion); });
                card.appendChild(cta);
            }
            caja.appendChild(card);
        });
        dom.scroll.appendChild(caja);
        desplazar();
    }

    function pintarChips(sugerencias) {
        if (!dom.chips) return;
        dom.chips.innerHTML = '';
        (sugerencias || []).slice(0, 4).forEach(function (texto) {
            var chip = document.createElement('button');
            chip.type = 'button';
            chip.className = 'ruana-copiloto-chip';
            chip.textContent = texto;
            chip.addEventListener('click', function () { enviar(texto); });
            dom.chips.appendChild(chip);
        });
    }

    function actualizarModo(ia, restantes) {
        estado.ia = ia || null;
        var activa = !!(ia && ia.activa);
        if (dom.live) dom.live.className = 'ruana-copiloto-live' + (activa ? '' : ' is-off');
        if (dom.modo) {
            dom.modo.textContent = activa
                ? 'IA conectada · ' + (ia.modelo || 'modelo')
                : 'Asistente de la red';
        }
        if (dom.pie) {
            dom.pie.textContent = (activa && typeof restantes === 'number')
                ? restantes + ' mensajes hoy'
                : 'Datos reales de la red';
        }
    }

    // -------------------------------------------------------------- acciones

    function ejecutarAccion(accion) {
        if (!accion || !accion.tipo) return;
        if (accion.tipo === 'nav_admin') navegar(accion.destino);
    }

    function navegar(destino) {
        if (!destino) return;
        var boton = document.querySelector('[data-nav-target="' + destino + '"]') ||
            document.querySelector('[data-nav-target="#' + destino + '"]');
        cerrar();
        if (boton) {
            setTimeout(function () { boton.click(); }, 120);
            return;
        }
        var ancla = document.getElementById(destino);
        if (ancla && ancla.scrollIntoView) ancla.scrollIntoView({ behavior: 'smooth' });
    }

    // ------------------------------------------------------------ peticiones

    function pedir(ruta, opciones) {
        var conf = Object.assign(
            { credentials: 'same-origin', headers: authHeaders() },
            opciones || {}
        );
        return fetch(getApiBase() + ruta, conf).then(function (resp) {
            return resp.json().catch(function () { return {}; }).then(function (datos) {
                if (!resp.ok) {
                    var error = new Error((datos && datos.message) || 'No se pudo conectar');
                    error.datos = datos;
                    throw error;
                }
                return datos;
            });
        });
    }

    function cargarEstado(conSaludo) {
        return pedir('/api/admin/copiloto/estado', { method: 'GET' })
            .then(function (datos) {
                estado.cargado = true;
                actualizarModo(datos.ia, datos.mensajes_restantes_hoy);
                pintarChips(datos.sugerencias);
                if (conSaludo && datos.saludo) burbuja(datos.saludo, 'es-bot');
                if (Array.isArray(datos.jugadas) && datos.jugadas.length) {
                    pintarJugadas(datos.jugadas);
                }
                var urgente = (datos.jugadas || []).some(function (j) {
                    return j.urgencia === 'alta';
                });
                if (dom.dot) dom.dot.hidden = !urgente;
                return datos;
            })
            .catch(function (error) {
                burbuja(
                    'No he podido cargar los datos de la red. Recarga el panel y vuelve a probar.',
                    'es-error'
                );
                throw error;
            });
    }

    function enviar(texto) {
        var mensaje = String(texto || '').trim();
        if (!mensaje || estado.enviando) return;

        estado.enviando = true;
        if (dom.enviar) dom.enviar.disabled = true;
        dom.input.value = '';
        dom.input.style.height = 'auto';

        burbuja(mensaje, 'es-user');
        anotar('admin', mensaje);
        mostrarEscribiendo();

        pedir('/api/admin/copiloto/mensaje', {
            method: 'POST',
            body: JSON.stringify({ mensaje: mensaje, historial: estado.historial.slice(0, -1) })
        })
            .then(function (datos) {
                quitarEscribiendo();
                actualizarModo(datos.ia, datos.mensajes_restantes_hoy);
                burbuja(datos.texto || 'No he sabido qué contestar.', 'es-bot');
                anotar('copiloto', datos.texto || '');
                if (datos.accion) {
                    var btn = document.createElement('button');
                    btn.type = 'button';
                    btn.className = 'ruana-copiloto-cta es-suave';
                    btn.textContent = 'Abrir en el panel';
                    btn.addEventListener('click', function () { ejecutarAccion(datos.accion); });
                    dom.scroll.appendChild(btn);
                    desplazar();
                }
            })
            .catch(function (error) {
                quitarEscribiendo();
                var detalle = (error && error.datos && error.datos.message) || '';
                burbuja(detalle || 'No he podido contestar. Prueba otra vez.', 'es-error');
            })
            .then(function () {
                estado.enviando = false;
                if (dom.enviar) dom.enviar.disabled = false;
                if (dom.input) dom.input.focus();
            });
    }

    // -------------------------------------------------------------- abrir

    function abrir() {
        if (!estado.montado) return;
        estado.abierto = true;
        dom.panel.classList.add('is-open');
        dom.panel.setAttribute('aria-hidden', 'false');
        dom.fab.classList.add('is-open');
        dom.fab.setAttribute('aria-expanded', 'true');
        if (dom.dot) dom.dot.hidden = true;

        if (!estado.cargado) {
            mostrarEscribiendo();
            cargarEstado(true)
                .then(function () { quitarEscribiendo(); irArriba(); })
                .catch(quitarEscribiendo);
        }
        setTimeout(function () { if (dom.input) dom.input.focus(); }, 160);
    }

    function cerrar() {
        if (!estado.montado) return;
        estado.abierto = false;
        dom.panel.classList.remove('is-open');
        dom.panel.setAttribute('aria-hidden', 'true');
        dom.fab.classList.remove('is-open');
        dom.fab.setAttribute('aria-expanded', 'false');
    }

    function alternar() {
        if (estado.abierto) cerrar(); else abrir();
    }

    // ------------------------------------------------------------- arranque

    function esPanelAdmin() {
        if (!document.body) return false;
        if (document.getElementById('ruana-copiloto-admin-fab')) return false;
        return !!(
            document.getElementById('adminBrandHome') ||
            document.getElementById('command-center-wrap') ||
            /\badmin-/.test(String(document.body.className || ''))
        );
    }

    /** Nodi asoma con un pendiente real de la red. */
    function arrancarMascota() {
        if (!global.RuanaMascota || typeof global.RuanaMascota.arrancarConsejos !== 'function') {
            return;
        }
        global.RuanaMascota.arrancarConsejos({
            obtenerMensajes: function () {
                return pedir('/api/admin/copiloto/estado', { method: 'GET' })
                    .then(function (d) {
                        return ((d && d.jugadas) || [])
                            .filter(function (j) { return j && j.urgencia !== 'baja'; })
                            .map(function (j) {
                                return {
                                    id: j.id,
                                    texto: j.titulo,
                                    accion: (j.cta || 'Abrir') + ' \u2192',
                                    jugada: j
                                };
                            });
                    });
            },
            alPulsar: function (mensaje) {
                if (mensaje && mensaje.jugada) {
                    ejecutarAccion(mensaje.jugada.accion || { tipo: 'nav_admin', destino: 'overview' });
                }
            }
        });
    }

    function iniciar() {
        if (estado.montado) return;
        if (!esPanelAdmin()) return;
        cargarHistorial();
        crearEstructura();
        enlazar();
        estado.montado = true;
        arrancarMascota();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', iniciar);
    } else {
        iniciar();
    }

    var intentos = 0;
    var temporizador = setInterval(function () {
        intentos += 1;
        if (estado.montado || intentos > 24) {
            clearInterval(temporizador);
            return;
        }
        iniciar();
    }, 500);

    global.RuanaCopilotoAdmin = {
        abrir: abrir,
        cerrar: cerrar,
        alternar: alternar,
        enviar: enviar,
        estado: estado
    };
})(typeof window !== 'undefined' ? window : globalThis);
