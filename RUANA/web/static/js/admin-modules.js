/**
 * Módulos del AdminPanel (Campamento Base).
 * Extracción progresiva desde admin.html — alineado al admin-shell.
 * `resumen` → admin-resumen-module.js (estado global / movimiento 24h / métricas)
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
