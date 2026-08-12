/**
 * Módulos del PrivatePanel (Campamento Base).
 * Extracción progresiva desde aliado.html — el shell ya define estas secciones.
 * Las implementaciones se migrarán aquí (o en aliado-*-module.js) manteniendo
 * PrivatePanel como fachada.
 * `inicio` → aliado-inicio-module.js
 * `perfil` → aliado-perfil-module.js (foto/avatar/detalles/edición básica)
 * `referidos` → aliado-referidos-module.js (modal linaje; árbol en referidos-module.js)
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
  };
})(typeof window !== 'undefined' ? window : globalThis);
