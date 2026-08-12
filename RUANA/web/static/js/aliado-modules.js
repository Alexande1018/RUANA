/**
 * Módulos del PrivatePanel (Campamento Base).
 * Extracción progresiva desde aliado.html — el shell ya define estas secciones.
 * Las implementaciones se migrarán aquí (o en aliado-*-module.js) manteniendo
 * PrivatePanel como fachada.
 * `inicio` → aliado-inicio-module.js
 * `perfil` → aliado-perfil-module.js (foto/avatar/detalles/edición básica)
 * `referidos` → aliado-referidos-module.js (modal linaje; árbol en referidos-module.js)
 * `directorio` → aliado-directorio-module.js (lista profesionales / score etiqueta)
 * `solicitudes` → aliado-solicitudes-module.js (entrantes / propias / historial)
 * `acuerdos` → aliado-acuerdos-module.js (Mis acuerdos)
 * `conexiones` → aliado-conexiones-module.js (enviar solicitud de conexión)
 * `centroComunicacion` → aliado-centro-comunicacion-module.js (FAB soporte)
 */
(function (global) {
  'use strict';
  global.RuanaAliadoModules = global.RuanaAliadoModules || {
    inicio: null,
    directorio: null,
    solicitudes: null,
    conexiones: null,
    perfil: null,
    referidos: null,
    acuerdos: null,
    centroComunicacion: null,
  };
})(typeof window !== 'undefined' ? window : globalThis);
