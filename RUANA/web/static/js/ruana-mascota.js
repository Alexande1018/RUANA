/**
 * Nodi — la mascota de RUANA.
 *
 * Un nodo de la red con cara: redondo, verde lima, con su hilo de conexión y una
 * antena que hace de chispa. Acompaña al aliado en el panel, aparece en el botón
 * del copiloto, y de vez en cuando asoma con un recordatorio corto y real
 * (sale de las jugadas del copiloto, no de texto inventado).
 *
 * Reglas de convivencia:
 *  - nunca más de un consejo por sesión y dos al día;
 *  - nunca mientras el copiloto está abierto;
 *  - nunca el mismo consejo dos veces;
 *  - si el aliado lo aparta, se queda apartado hasta mañana.
 */
(function (global) {
    'use strict';

    var CLAVE_VISTOS = 'ruana_mascota_vistos';
    var CLAVE_APARTADO = 'ruana_mascota_apartado';
    var MAX_DIA = 2;
    var RETRASO_CONSEJO_MS = 15000;

    var PREFIJO_ID = 'ruanaMascota';

    // ------------------------------------------------------------------ SVG

    var defsInyectadas = false;

    function inyectarDefs() {
        if (defsInyectadas || !document.body) return;
        defsInyectadas = true;
        var host = document.createElement('div');
        host.setAttribute('aria-hidden', 'true');
        host.style.cssText = 'position:absolute;width:0;height:0;overflow:hidden';
        host.innerHTML =
            '<svg xmlns="http://www.w3.org/2000/svg" width="0" height="0">' +
            '  <defs>' +
            '    <radialGradient id="' + PREFIJO_ID + 'Cuerpo" cx="34%" cy="28%" r="78%">' +
            '      <stop offset="0%" stop-color="#e4ffb8"/>' +
            '      <stop offset="52%" stop-color="#a2ff00"/>' +
            '      <stop offset="100%" stop-color="#57a002"/>' +
            '    </radialGradient>' +
            '    <linearGradient id="' + PREFIJO_ID + 'Hilo" x1="0" y1="0" x2="1" y2="0">' +
            '      <stop offset="0%" stop-color="#a2ff00" stop-opacity="0.05"/>' +
            '      <stop offset="100%" stop-color="#a2ff00" stop-opacity="0.75"/>' +
            '    </linearGradient>' +
            '  </defs>' +
            '</svg>';
        document.body.appendChild(host);
    }

    /**
     * Devuelve el SVG de Nodi.
     * @param {Object} opciones { clase, titulo, animado }
     */
    function svg(opciones) {
        var o = opciones || {};
        var clase = 'ruana-mascota' + (o.clase ? ' ' + o.clase : '') +
            (o.animado === false ? ' sin-animo' : '');
        var titulo = o.titulo === false ? '' :
            '<title>' + (o.titulo || 'Nodi, el compañero de RUANA') + '</title>';
        inyectarDefs();
        return (
            '<svg class="' + clase + '" viewBox="0 0 48 48" role="img" aria-hidden="' +
            (o.titulo === false ? 'true' : 'false') + '" focusable="false">' +
            titulo +
            // hilo de conexión: es un nodo de la red, no un bicho suelto
            '<path class="ruana-mascota-hilo" d="M35.5 15.5 C42 12.5 43 9.5 45.5 6.5" ' +
            'fill="none" stroke="url(#' + PREFIJO_ID + 'Hilo)" stroke-width="1.5" ' +
            'stroke-linecap="round" stroke-dasharray="2.4 3.2"/>' +
            '<circle class="ruana-mascota-amigo" cx="45.4" cy="6.2" r="1.9" ' +
            'fill="#a2ff00" opacity="0.65"/>' +
            // cuerpo
            '<ellipse cx="23.5" cy="26.5" rx="14" ry="13.2" fill="url(#' + PREFIJO_ID + 'Cuerpo)"/>' +
            '<ellipse cx="18.5" cy="20.5" rx="5" ry="3.2" fill="#ffffff" opacity="0.32" ' +
            'transform="rotate(-20 18.5 20.5)"/>' +
            // ojos (parpadean)
            '<g class="ruana-mascota-ojos">' +
            '  <ellipse cx="18.8" cy="25.4" rx="2.1" ry="2.7" fill="#0a2110"/>' +
            '  <ellipse cx="28.4" cy="25.4" rx="2.1" ry="2.7" fill="#0a2110"/>' +
            '  <circle cx="19.5" cy="24.5" r="0.7" fill="#ffffff" opacity="0.85"/>' +
            '  <circle cx="29.1" cy="24.5" r="0.7" fill="#ffffff" opacity="0.85"/>' +
            '</g>' +
            // sonrisa
            '<path class="ruana-mascota-boca" d="M19.6 31.2 Q23.6 34.6 27.6 31.2" ' +
            'stroke="#0a2110" stroke-width="1.7" fill="none" stroke-linecap="round"/>' +
            // mejillas
            '<ellipse cx="14.7" cy="29.9" rx="2.1" ry="1.2" fill="#ffffff" opacity="0.16"/>' +
            '<ellipse cx="32.4" cy="29.9" rx="2.1" ry="1.2" fill="#ffffff" opacity="0.16"/>' +
            // antena
            '<path d="M23.5 13.4 L23.5 9.2" stroke="#57a002" stroke-width="1.5" stroke-linecap="round"/>' +
            '<circle class="ruana-mascota-luz" cx="23.5" cy="7.6" r="2.2" fill="#e4ffb8"/>' +
            '</svg>'
        );
    }

    /** Sustituye el contenido de un elemento por la mascota. */
    function pintarEn(el, opciones) {
        if (!el) return;
        el.innerHTML = svg(opciones);
    }

    // ------------------------------------------------------------- consejos

    function hoy() {
        var d = new Date();
        return d.getFullYear() + '-' + (d.getMonth() + 1) + '-' + d.getDate();
    }

    function leer(almacen, clave, defecto) {
        try {
            var crudo = global[almacen] && global[almacen].getItem(clave);
            return crudo ? JSON.parse(crudo) : defecto;
        } catch (e) {
            return defecto;
        }
    }

    function escribir(almacen, clave, valor) {
        try {
            global[almacen] && global[almacen].setItem(clave, JSON.stringify(valor));
        } catch (e) { /* modo privado o sin cuota */ }
    }

    function estadoDiario() {
        var datos = leer('localStorage', CLAVE_VISTOS, null);
        if (!datos || datos.dia !== hoy()) {
            datos = { dia: hoy(), ids: [], n: 0 };
            escribir('localStorage', CLAVE_VISTOS, datos);
        }
        return datos;
    }

    function apartadoHoy() {
        return leer('localStorage', CLAVE_APARTADO, '') === hoy();
    }

    function puedeMostrar() {
        if (apartadoHoy()) return false;
        var datos = estadoDiario();
        if (datos.n >= MAX_DIA) return false;
        if (global.sessionStorage && sessionStorage.getItem('ruana_mascota_sesion')) return false;
        return true;
    }

    function marcarVisto(id) {
        var datos = estadoDiario();
        datos.ids.push(id);
        datos.n += 1;
        escribir('localStorage', CLAVE_VISTOS, datos);
        try {
            global.sessionStorage && sessionStorage.setItem('ruana_mascota_sesion', '1');
        } catch (e) { /* ignore */ }
    }

    // ------------------------------------------------------------- burbuja

    var dom = {};

    function crearBurbuja() {
        var caja = document.createElement('aside');
        caja.className = 'ruana-mascota-consejo';
        caja.id = 'ruana-mascota-consejo';
        caja.setAttribute('role', 'status');
        caja.setAttribute('aria-live', 'polite');
        caja.innerHTML =
            '<div class="ruana-mascota-consejo-cara" aria-hidden="true">' + svg({ animado: true }) + '</div>' +
            '<div class="ruana-mascota-consejo-texto">' +
            '  <p class="ruana-mascota-consejo-linea" id="ruana-mascota-linea"></p>' +
            '</div>' +
            '<div class="ruana-mascota-consejo-acciones">' +
            '  <button type="button" class="ruana-mascota-btn" id="ruana-mascota-ver">Ver</button>' +
            '  <button type="button" class="ruana-mascota-apartar" id="ruana-mascota-apartar" ' +
            '    aria-label="Ahora no">Ahora no</button>' +
            '</div>';
        document.body.appendChild(caja);
        dom.burbuja = caja;
        dom.linea = caja.querySelector('#ruana-mascota-linea');
        dom.ver = caja.querySelector('#ruana-mascota-ver');
        dom.apartar = caja.querySelector('#ruana-mascota-apartar');
    }

    function cerrarBurbuja() {
        if (!dom.burbuja) return;
        dom.burbuja.classList.remove('is-visible');
        setTimeout(function () {
            if (dom.burbuja) dom.burbuja.hidden = true;
        }, 260);
    }

    /**
     * Coloca la burbuja al lado del menú lateral, no encima. La barra es fija y
     * en el panel del aliado ocupa 232 px: sin esto, Nodi tapaba el pie legal.
     */
    function colocarBurbuja() {
        if (!dom.burbuja) return;
        if (global.innerWidth <= 720) {
            dom.burbuja.style.left = '';
            return;
        }
        var carriles = ['.aliado-shell-nav', '.admin-sidebar', '.admin-shell-nav', '.ruana-sidebar'];
        var izquierda = 22;
        for (var i = 0; i < carriles.length; i++) {
            var el = document.querySelector(carriles[i]);
            if (!el) continue;
            var r = el.getBoundingClientRect();
            if (getComputedStyle(el).position === 'fixed' && r.left < 40 && r.width > 120) {
                izquierda = Math.round(r.right + 16);
                break;
            }
        }
        dom.burbuja.style.left = izquierda + 'px';
    }

    function mostrarConsejo(jugada, alPulsarVer) {
        if (!dom.burbuja) return;
        colocarBurbuja();
        dom.linea.textContent = jugada.titulo || '¿Le echamos un ojo a tu panel?';
        dom.ver.textContent = jugada.cta || 'Ver';
        dom.ver.onclick = function () {
            marcarVisto(jugada.id);
            cerrarBurbuja();
            if (typeof alPulsarVer === 'function') alPulsarVer(jugada);
        };
        dom.apartar.onclick = function () {
            escribir('localStorage', CLAVE_APARTADO, hoy());
            cerrarBurbuja();
        };
        dom.burbuja.hidden = false;
        if (!dom.escuchaResize) {
            dom.escuchaResize = true;
            global.addEventListener('resize', colocarBurbuja);
        }
        // dos frames para que la transición se note
        requestAnimationFrame(function () {
            requestAnimationFrame(function () {
                dom.burbuja.classList.add('is-visible');
            });
        });
        marcarVisto(jugada.id);
    }

    /**
     * Arranca el acompañante. Pide las jugadas al copiloto una sola vez, tarde
     * y sin bloquear nada: si falla, Nodi simplemente no dice nada.
     */
    function arrancarConsejos(opciones) {
        var o = opciones || {};
        if (!puedeMostrar()) return;
        crearBurbuja();

        setTimeout(function () {
            if (document.hidden) return;
            if (document.querySelector('#ruana-copiloto-panel.is-open')) return;

            var pedir = o.obtenerJugadas;
            if (typeof pedir !== 'function') return;

            Promise.resolve(pedir()).then(function (jugadas) {
                if (!Array.isArray(jugadas) || !jugadas.length) return;
                var vistas = estadoDiario().ids;
                var candidata = jugadas.filter(function (j) {
                    return j && j.id && vistas.indexOf(j.id) === -1 && j.urgencia !== 'baja';
                })[0];
                if (!candidata) return;
                if (!puedeMostrar()) return;
                mostrarConsejo(candidata, o.alPulsarVer);
            }).catch(function () { /* silencio: es un adorno, no una función */ });
        }, RETRASO_CONSEJO_MS);
    }

    global.RuanaMascota = {
        svg: svg,
        pintarEn: pintarEn,
        arrancarConsejos: arrancarConsejos,
        cerrar: cerrarBurbuja
    };
})(typeof window !== 'undefined' ? window : globalThis);
