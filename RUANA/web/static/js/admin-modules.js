/**
 * Módulos del AdminPanel (Campamento Base).
 * Extracción progresiva desde admin.html — alineado al admin-shell.
 */
(function (global) {
  'use strict';
  global.RuanaAdminModules = global.RuanaAdminModules || {
    resumen: null,
    operaciones: null,
    red: null,
    sistema: null,
  };
})(typeof window !== 'undefined' ? window : globalThis);
