/**
 * Copiloto RUANA — asistente del aliado.
 *
 * Habla con el aliado dentro del panel: explica la app, dice qué le conviene
 * hacer con su score, le ayuda a invitar al oficio que falta y a cerrar
 * encargos. Todo lo que dice sale de /api/aliado/copiloto/*, que construye el
 * backend con datos reales. El frontend no inventa nada: pinta y ejecuta.
 */
(function (global) {
    'use strict';

    var CLAVE_HISTORIAL = 'ruana_copiloto_hist';
    var MAX_HISTORIAL = 8;

    var estado = {
        montado: false,
        abierto: false,
        cargado: false,
        enviando: false,
        ia: null,
        historial: [],
        sugerencias: []
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
            var sid = global.sessionStorage && sessionStorage.getItem('ruana_session_id');
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

    function host() {
        return global.__ruanaPanel || null;
    }

    function moduloInvitaciones() {
        var mods = global.RuanaAliadoModules || {};
        return mods.invitaciones || null;
    }

    // ------------------------------------------------------------ historial

    function cargarHistorial() {
        try {
            var crudo = global.sessionStorage && sessionStorage.getItem(CLAVE_HISTORIAL);
            var datos = crudo ? JSON.parse(crudo) : [];
            if (Array.isArray(datos)) {
                estado.historial = datos.slice(-MAX_HISTORIAL);
            }
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
        return ICONO_CHISPA;
    }

    var ICONO_CHISPA =
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
        fab.id = 'ruana-copiloto-fab';
        fab.setAttribute('aria-label', 'Abrir el copiloto de RUANA');
        fab.setAttribute('aria-expanded', 'false');
        fab.innerHTML =
            iconoMascota() +
            '<span>Copiloto</span>' +
            '<span class="ruana-copiloto-fab-dot" id="ruana-copiloto-dot" hidden></span>';

        var panel = document.createElement('section');
        panel.className = 'ruana-copiloto-panel';
        panel.id = 'ruana-copiloto-panel';
        panel.setAttribute('role', 'dialog');
        panel.setAttribute('aria-modal', 'false');
        panel.setAttribute('aria-labelledby', 'ruana-copiloto-titulo');
        panel.setAttribute('aria-hidden', 'true');
        panel.innerHTML = [
            '<div class="ruana-copiloto-head">',
            '  <div class="ruana-copiloto-avatar">', iconoMascota(), '</div>',
            '  <div class="ruana-copiloto-titulos">',
            '    <h2 class="ruana-copiloto-titulo" id="ruana-copiloto-titulo">Copiloto RUANA</h2>',
            '    <p class="ruana-copiloto-sub">',
            '      <span class="ruana-copiloto-live" id="ruana-copiloto-live"></span>',
            '      <span id="ruana-copiloto-modo">Asistente de tu red</span>',
            '    </p>',
            '  </div>',
            '  <button type="button" class="ruana-copiloto-cerrar" id="ruana-copiloto-cerrar" aria-label="Cerrar el copiloto">✕</button>',
            '</div>',
            '<div class="ruana-copiloto-scroll" id="ruana-copiloto-scroll" role="log" aria-live="polite"></div>',
            '<div class="ruana-copiloto-chips" id="ruana-copiloto-chips"></div>',
            '<div class="ruana-copiloto-entrada">',
            '  <textarea class="ruana-copiloto-input" id="ruana-copiloto-input" rows="1" maxlength="600"',
            '    placeholder="Pregúntame lo que quieras…" aria-label="Escribe tu pregunta"></textarea>',
            '  <button type="button" class="ruana-copiloto-enviar" id="ruana-copiloto-enviar" aria-label="Enviar">',
            ICONO_ENVIAR,
            '  </button>',
            '</div>',
            '<div class="ruana-copiloto-pie">',
            '  <span id="ruana-copiloto-pie-texto">Con datos reales de tu cuenta</span>',
            '  <button type="button" id="ruana-copiloto-equipo">Hablar con el equipo</button>',
            '</div>'
        ].join('');

        document.body.appendChild(fab);
        document.body.appendChild(panel);

        dom.fab = fab;
        dom.panel = panel;
        dom.scroll = panel.querySelector('#ruana-copiloto-scroll');
        dom.chips = panel.querySelector('#ruana-copiloto-chips');
        dom.input = panel.querySelector('#ruana-copiloto-input');
        dom.enviar = panel.querySelector('#ruana-copiloto-enviar');
        dom.modo = panel.querySelector('#ruana-copiloto-modo');
        dom.live = panel.querySelector('#ruana-copiloto-live');
        dom.dot = fab.querySelector('#ruana-copiloto-dot');
        dom.pie = panel.querySelector('#ruana-copiloto-pie-texto');
    }

    function enlazar() {
        dom.fab.addEventListener('click', alternar);
        dom.panel.querySelector('#ruana-copiloto-cerrar').addEventListener('click', cerrar);
        dom.enviar.addEventListener('click', function () {
            enviar(dom.input.value);
        });
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
        dom.panel.querySelector('#ruana-copiloto-equipo').addEventListener('click', irASoporte);
        document.addEventListener('keydown', function (ev) {
            if (ev.key === 'Escape' && estado.abierto) cerrar();
        });
    }

    // ---------------------------------------------------------- pintar UI

    function burbuja(texto, clase) {
        var div = document.createElement('div');
        div.className = 'ruana-copiloto-burbuja ' + (clase || 'es-bot');
        div.innerHTML = conSaltos(texto);
        dom.scroll.appendChild(div);
        desplazar();
        return div;
    }

    function desplazar() {
        if (!dom.scroll) return;
        dom.scroll.scrollTop = dom.scroll.scrollHeight;
    }

    function irArriba() {
        if (dom.scroll) dom.scroll.scrollTop = 0;
    }

    function mostrarEscribiendo() {
        var div = document.createElement('div');
        div.className = 'ruana-copiloto-typing';
        div.id = 'ruana-copiloto-typing';
        div.innerHTML = '<span></span><span></span><span></span>';
        dom.scroll.appendChild(div);
        desplazar();
    }

    function quitarEscribiendo() {
        var el = document.getElementById('ruana-copiloto-typing');
        if (el && el.parentNode) el.parentNode.removeChild(el);
    }

    function pintarAccion(accion, contenedor) {
        if (!accion || !accion.tipo) return;
        var etiqueta = accion.etiqueta || 'Abrir';
        var boton = document.createElement('button');
        boton.type = 'button';
        boton.className = 'ruana-copiloto-cta';
        boton.textContent = etiqueta;
        boton.addEventListener('click', function () {
            ejecutarAccion(accion);
        });
        (contenedor || dom.scroll).appendChild(boton);
        desplazar();
    }

    function pintarJugadas(jugadas, conAccion) {
        if (!Array.isArray(jugadas) || !jugadas.length) return;
        var caja = document.createElement('div');
        caja.className = 'ruana-copiloto-jugadas';

        jugadas.forEach(function (jugada) {
            var card = document.createElement('div');
            card.className = 'ruana-copiloto-jugada' +
                (jugada.urgencia === 'alta' ? ' es-urgente' : '');

            var top = document.createElement('div');
            top.className = 'ruana-copiloto-jugada-top';
            var titulo = document.createElement('p');
            titulo.className = 'ruana-copiloto-jugada-titulo';
            titulo.textContent = jugada.titulo || '';
            top.appendChild(titulo);
            card.appendChild(top);

            var detalle = document.createElement('p');
            detalle.className = 'ruana-copiloto-jugada-detalle';
            detalle.textContent = jugada.detalle || '';
            card.appendChild(detalle);

            if (jugada.impacto) {
                var impacto = document.createElement('span');
                impacto.className = 'ruana-copiloto-impacto';
                impacto.textContent = jugada.impacto;
                card.appendChild(impacto);
            }

            if (conAccion !== false && jugada.accion) {
                var cta = document.createElement('button');
                cta.type = 'button';
                cta.className = 'ruana-copiloto-cta';
                cta.textContent = jugada.cta || 'Hacerlo';
                cta.addEventListener('click', function () {
                    ejecutarAccion(jugada.accion);
                });
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
            chip.addEventListener('click', function () {
                enviar(texto);
            });
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
                : 'Asistente de tu red';
        }
        if (!dom.pie) return;
        if (activa && typeof restantes === 'number') {
            dom.pie.textContent = restantes + ' mensajes hoy';
        } else {
            dom.pie.textContent = 'Con datos reales de tu cuenta';
        }
    }

    // -------------------------------------------------------------- acciones

    function ejecutarAccion(accion) {
        if (!accion || !accion.tipo) return;
        switch (accion.tipo) {
            case 'nav':
                navegar(accion.destino);
                break;
            case 'invitar':
                invitar(accion.oficio);
                break;
            case 'soporte':
                irASoporte();
                break;
            case 'copiar':
                copiar(accion.texto);
                break;
            default:
                break;
        }
    }

    function navegar(destino) {
        var boton = document.querySelector('[data-aliado-nav="' + destino + '"]');
        cerrar();
        if (boton) {
            setTimeout(function () { boton.click(); }, 120);
            return;
        }
        var ancla = document.getElementById('module-' + destino);
        if (ancla && ancla.scrollIntoView) ancla.scrollIntoView({ behavior: 'smooth' });
    }

    function invitar(oficio) {
        var mods = moduloInvitaciones();
        var panelHost = host();
        if (!mods) {
            navegar('perfil');
            return;
        }
        cerrar();
        setTimeout(function () {
            if (oficio && typeof mods.generarInvitacionOficio === 'function') {
                mods.generarInvitacionOficio(panelHost, oficio);
                return;
            }
            if (typeof mods.generarCodigoInvitacionCrecimientoGrupo === 'function') {
                mods.generarCodigoInvitacionCrecimientoGrupo(panelHost);
                return;
            }
            if (typeof mods.generarCodigoInvitacionPerfil === 'function') {
                mods.generarCodigoInvitacionPerfil(panelHost);
            }
        }, 140);
    }

    function irASoporte() {
        cerrar();
        setTimeout(function () {
            var fab = document.getElementById('ruana-help-fab');
            if (fab) fab.click();
        }, 120);
    }

    function copiar(texto) {
        var contenido = String(texto || '');
        if (!contenido) return;
        var aviso = function () {
            burbuja('Copiado. Mándalo por WhatsApp a esa persona concreta: funciona mejor que una difusión.', 'es-bot');
        };
        try {
            if (global.navigator && navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(contenido).then(aviso).catch(function () {
                    window.prompt('Copia el mensaje:', contenido);
                });
                return;
            }
        } catch (e) { /* ignore */ }
        window.prompt('Copia el mensaje:', contenido);
    }

    // ------------------------------------------------------------ peticiones

    function pedir(ruta, opciones) {
        var url = getApiBase() + ruta;
        var conf = Object.assign(
            { credentials: 'same-origin', headers: authHeaders() },
            opciones || {}
        );
        return fetch(url, conf).then(function (resp) {
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
        return pedir('/api/aliado/copiloto/estado', { method: 'GET' })
            .then(function (datos) {
                estado.cargado = true;
                actualizarModo(datos.ia, datos.mensajes_restantes_hoy);
                estado.sugerencias = datos.sugerencias || [];
                pintarChips(estado.sugerencias);
                if (conSaludo && datos.saludo) {
                    burbuja(datos.saludo, 'es-bot');
                }
                if (Array.isArray(datos.jugadas) && datos.jugadas.length) {
                    pintarJugadas(datos.jugadas, true);
                }
                var urgente = (datos.jugadas || []).some(function (j) {
                    return j.urgencia === 'alta';
                });
                if (dom.dot) dom.dot.hidden = !urgente;
                return datos;
            })
            .catch(function (error) {
                burbuja(
                    'No he podido cargar tu ficha ahora mismo. Si sigue así, escribe al equipo de RUANA desde aquí abajo.',
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
        anotar('aliado', mensaje);
        mostrarEscribiendo();

        pedir('/api/aliado/copiloto/mensaje', {
            method: 'POST',
            body: JSON.stringify({
                mensaje: mensaje,
                historial: estado.historial.slice(0, -1)
            })
        })
            .then(function (datos) {
                quitarEscribiendo();
                actualizarModo(datos.ia, datos.mensajes_restantes_hoy);
                burbuja(datos.texto || 'No he sabido qué contestar.', 'es-bot');
                anotar('copiloto', datos.texto || '');
                if (datos.accion) pintarAccion(datos.accion);
            })
            .catch(function (error) {
                quitarEscribiendo();
                var detalle = (error && error.datos && error.datos.message) || '';
                burbuja(
                    detalle || 'No he podido contestar. Prueba otra vez en un momento.',
                    'es-error'
                );
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

        try {
            global.localStorage && localStorage.setItem('ruana_copiloto_abierto', '1');
        } catch (e) { /* ignore */ }

        if (!estado.cargado) {
            mostrarEscribiendo();
            cargarEstado(true)
                .then(function () {
                    quitarEscribiendo();
                    irArriba();
                })
                .catch(quitarEscribiendo);
        }
        setTimeout(function () {
            if (dom.input) dom.input.focus();
        }, 160);
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
        if (estado.abierto) cerrar();
        else abrir();
    }

    // ------------------------------------------------------------- arranque

    function esPanelAliado() {
        if (!document.body) return false;
        var clases = ' ' + String(document.body.className || '') + ' ';
        if (clases.indexOf(' admin-') !== -1) return false;
        if (document.getElementById('module-admin')) return false;
        if (document.getElementById('adminBrandHome')) return false;
        return !!(
            document.getElementById('module-inicio') ||
            document.querySelector('[data-aliado-nav]') ||
            document.getElementById('aliado-shell')
        );
    }

    // Nodi también pregunta si hay dudas: así el aliado sabe que puede hablarle.
    var INVITACIONES = [
        '¿Tienes alguna duda de RUANA? Pregúntame lo que quieras.',
        '¿Aún no sabes cómo funciona algo? Te lo explico en un momento.',
        'Aquí estoy si te surge una duda de la app. Pregúntame.'
    ];

    function invitacionDelDia() {
        var hoy = new Date();
        var indice = (hoy.getDate() + hoy.getMonth() * 31) % INVITACIONES.length;
        return {
            id: 'invitacion_' + indice,
            texto: INVITACIONES[indice],
            accion: 'Preguntar →'
        };
    }

    function yaHabloConCopiloto() {
        try {
            return !!global.localStorage && localStorage.getItem('ruana_copiloto_abierto') === '1';
        } catch (e) {
            return false;
        }
    }

    /** Nodi asoma cuando el panel ya está cargado: primero invita, luego avisa. */
    function arrancarMascota() {
        if (!global.RuanaMascota || typeof global.RuanaMascota.arrancarConsejos !== 'function') {
            return;
        }
        global.RuanaMascota.arrancarConsejos({
            obtenerMensajes: function () {
                var invitacion = invitacionDelDia();
                // Si nunca ha abierto el copiloto, primero se presenta.
                if (!yaHabloConCopiloto()) return [invitacion];
                return pedir('/api/aliado/copiloto/jugadas', { method: 'GET' })
                    .then(function (d) {
                        var lista = ((d && d.jugadas) || [])
                            .filter(function (j) { return j && j.urgencia !== 'baja'; })
                            .map(function (j) {
                                return {
                                    id: j.id,
                                    texto: j.titulo,
                                    accion: (j.cta || 'Ver') + ' →',
                                    jugada: j
                                };
                            });
                        lista.push(invitacion);
                        return lista;
                    })
                    .catch(function () { return [invitacion]; });
            },
            alPulsar: function (mensaje) {
                if (mensaje && mensaje.jugada) {
                    ejecutarAccion(mensaje.jugada.accion || { tipo: 'nav', destino: 'inicio' });
                    return;
                }
                abrir();
            }
        });
    }

    function iniciar() {
        if (estado.montado) return;
        if (!esPanelAliado()) return;
        if (document.getElementById('ruana-copiloto-fab')) return;

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

    // El panel se pinta dinámicamente en algunos flujos: reintento suave.
    var intentos = 0;
    var temporizador = setInterval(function () {
        intentos += 1;
        if (estado.montado || intentos > 20) {
            clearInterval(temporizador);
            return;
        }
        iniciar();
    }, 500);

    global.RuanaCopiloto = {
        abrir: abrir,
        cerrar: cerrar,
        alternar: alternar,
        enviar: enviar,
        cargarEstado: cargarEstado,
        estado: estado
    };
})(typeof window !== 'undefined' ? window : globalThis);
