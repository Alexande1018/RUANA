/**
 * Módulos del PrivatePanel (Campamento Base).
 * Extracción progresiva desde aliado.html — el shell ya define estas secciones.
 * Las implementaciones viven en aliado-*-module.js; PrivatePanel es fachada.
 * `inicio` → aliado-inicio-module.js
 * `perfil` → aliado-perfil-module.js
 * `referidos` → aliado-referidos-module.js
 * `directorio` → aliado-directorio-module.js
 * `solicitudes` → aliado-solicitudes-module.js
 * `acuerdos` → aliado-acuerdos-module.js
 * `conexiones` → aliado-conexiones-module.js
 * `centroComunicacion` → aliado-centro-comunicacion-module.js
 * `invitaciones` → aliado-invitaciones-module.js
 * `alertas` → aliado-alertas-module.js (hub + pagos Apoyo + impugnación)
 * `catalogo` → aliado-catalogo-module.js
 * `contactos` → aliado-contactos-module.js
 * `grupo` → aliado-grupo-module.js
 * `sync` → aliado-sync-module.js (warmup / loadData / refresh)
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
    invitaciones: null,
    alertas: null,
    catalogo: null,
    contactos: null,
    grupo: null,
    sync: null,
  };
})(typeof window !== 'undefined' ? window : globalThis);
