/**
 * Módulos del AdminPanel (Campamento Base).
 * Extracción progresiva desde admin.html — alineado al admin-shell.
 * `resumen` → admin-resumen-module.js (estado global / movimiento 24h / métricas)
 * `operaciones` → admin-operaciones-module.js (conflictos pago / pagos Apoyo / en revisión)
 * `red` → admin-red-module.js (jerarquía CP→grupo→tarjetas, linaje, detalle)
 * `sistema` → admin-sistema-module.js (campañas, códigos, reglas, métodos pago, plazas)
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
