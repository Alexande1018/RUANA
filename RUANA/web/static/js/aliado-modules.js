/**
 * Módulos del PrivatePanel (Campamento Base).
 * Extracción progresiva desde aliado.html — el shell ya define estas secciones.
 * Las implementaciones se migrarán aquí (o en aliado-*-module.js) manteniendo
 * PrivatePanel como fachada. `inicio` → aliado-inicio-module.js
 */
(function (global) {
  'use strict';
  global.RuanaAliadoModules = global.RuanaAliadoModules || {
    inicio: null,
    directorio: null,
    solicitudes: null,
    conexiones: null,
    perfil: null,
  };
})(typeof window !== 'undefined' ? window : globalThis);
