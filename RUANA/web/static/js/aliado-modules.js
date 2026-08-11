/**
 * Módulos del PrivatePanel (Campamento Base).
 * Extracción progresiva desde aliado.html — el shell ya define estas secciones.
 * Las implementaciones se migrarán aquí manteniendo PrivatePanel como fachada.
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
