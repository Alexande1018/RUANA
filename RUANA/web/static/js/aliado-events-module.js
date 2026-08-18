/**
 * Módulo PrivatePanel `events` (Campamento Base).
 * Orquestación de event listeners del panel aliado.
 * PrivatePanel conserva fachada delgada setupEventListeners.
 */
(function (global) {
  'use strict';

  var modules = global.RuanaAliadoModules = global.RuanaAliadoModules || {
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
    events: null,
  };

  function setupEventListeners(host) {
      document.addEventListener('ruana:abrir-negociacion', (e) => {
          const id = e.detail && e.detail.contactoId;
          if (id) host.abrirNegociacionContacto(id, null);
      });
      // Botón de logout (F04)
      const btnLogout = document.getElementById('btn-logout');
      if (btnLogout) {
          btnLogout.addEventListener('click', () => host.handleLogout());
      }

      document.querySelectorAll('[data-action="invitar-aliado"]').forEach((btn) => {
          btn.addEventListener('click', () => host.generarCodigoInvitacionPerfil());
      });
      document.querySelectorAll('[data-action="invitar-crecimiento-grupo"]').forEach((btn) => {
          btn.addEventListener('click', () => host.generarCodigoInvitacionCrecimientoGrupo());
      });
      const filtrosAcuerdos = document.getElementById('mis-acuerdos-filtros');
      if (filtrosAcuerdos) {
          filtrosAcuerdos.addEventListener('click', (e) => {
              const btn = e.target.closest('.mis-acuerdos-filtro');
              if (!btn) return;
              host.misAcuerdosFiltro = btn.getAttribute('data-filtro') || 'todos';
              host.cargarMisAcuerdos();
          });
      }
      const listaAcuerdos = document.getElementById('mis-acuerdos-lista');
      if (listaAcuerdos) {
          listaAcuerdos.addEventListener('click', (e) => {
              const mas = e.target.closest('[data-acuerdo-mas]');
              if (mas) {
                  e.preventDefault();
                  host.mostrarMasMisAcuerdos();
                  return;
              }
              const toggle = e.target.closest('[data-acuerdo-toggle]');
              if (!toggle) return;
              e.preventDefault();
              host.toggleMisAcuerdoExpandido(toggle.getAttribute('data-acuerdo-toggle'));
          });
      }
      const btnAplicarAcuerdos = document.getElementById('mis-acuerdos-aplicar-filtros');
      if (btnAplicarAcuerdos) {
          btnAplicarAcuerdos.addEventListener('click', () => {
              const sel = document.getElementById('mis-acuerdos-filtro-estado');
              const desde = document.getElementById('mis-acuerdos-filtro-desde');
              const hasta = document.getElementById('mis-acuerdos-filtro-hasta');
              host.misAcuerdosFiltroEstado = (sel && sel.value) || '';
              host.misAcuerdosFiltroDesde = (desde && desde.value) || '';
              host.misAcuerdosFiltroHasta = (hasta && hasta.value) || '';
              host.cargarMisAcuerdos();
          });
      }
      const btnLimpiarAcuerdos = document.getElementById('mis-acuerdos-limpiar-filtros');
      if (btnLimpiarAcuerdos) {
          btnLimpiarAcuerdos.addEventListener('click', () => {
              host.misAcuerdosFiltroEstado = '';
              host.misAcuerdosFiltroDesde = '';
              host.misAcuerdosFiltroHasta = '';
              host.misAcuerdosFiltro = 'todos';
              host.cargarMisAcuerdos();
          });
      }
      ['mis-acuerdos-filtro-estado', 'mis-acuerdos-filtro-desde', 'mis-acuerdos-filtro-hasta'].forEach((id) => {
          const el = document.getElementById(id);
          if (!el) return;
          el.addEventListener('change', () => {
              const sel = document.getElementById('mis-acuerdos-filtro-estado');
              const desde = document.getElementById('mis-acuerdos-filtro-desde');
              const hasta = document.getElementById('mis-acuerdos-filtro-hasta');
              host.misAcuerdosFiltroEstado = (sel && sel.value) || '';
              host.misAcuerdosFiltroDesde = (desde && desde.value) || '';
              host.misAcuerdosFiltroHasta = (hasta && hasta.value) || '';
              host.cargarMisAcuerdos();
          });
      });
      const btnFlotanteDismiss = document.getElementById('acuerdo-flotante-dismiss');
      if (btnFlotanteDismiss) {
          btnFlotanteDismiss.addEventListener('click', () => host.dismissAcuerdoFlotante());
      }
      const btnFlotanteAbrir = document.getElementById('acuerdo-flotante-abrir');
      if (btnFlotanteAbrir) {
          btnFlotanteAbrir.addEventListener('click', () => {
              const item = host.acuerdoFlotanteActual;
              if (!item || !item.contacto_id || !host.negociacionGuiada) return;
              host.negociacionGuiada.abrir(item.contacto_id, item.servicio || 'Acuerdo alcanzado');
          });
      }
      const btnFlotanteConfirmar = document.getElementById('acuerdo-flotante-confirmar');
      if (btnFlotanteConfirmar) {
          btnFlotanteConfirmar.addEventListener('click', () => host.confirmarAcuerdoDesdeFlotante());
      }
      const btnSoporteEnviar = document.getElementById('ruana-help-send-btn');
      if (btnSoporteEnviar) btnSoporteEnviar.addEventListener('click', () => host.enviarNuevoMensajeSoporte());
      const btnSoporteResponder = document.getElementById('ruana-help-reply-btn');
      if (btnSoporteResponder) btnSoporteResponder.addEventListener('click', () => host.responderConversacionSoporte());
      const fabSoporte = document.getElementById('ruana-help-fab');
      if (fabSoporte) fabSoporte.addEventListener('click', () => host.toggleCentroComunicacion());
      const closeSoporte = document.getElementById('ruana-help-close');
      if (closeSoporte) closeSoporte.addEventListener('click', () => host.cerrarCentroComunicacion());
      const overlaySoporte = document.getElementById('ruana-help-overlay');
      if (overlaySoporte) {
          overlaySoporte.addEventListener('click', (e) => {
              if (e.target === overlaySoporte) host.cerrarCentroComunicacion();
          });
      }
      document.addEventListener('keydown', (e) => {
          if (e.key === 'Escape') host.cerrarCentroComunicacion();
      });

      const metricReferidos = document.getElementById('metrica-card-referidos');
      if (metricReferidos) {
          metricReferidos.addEventListener('click', () => host.abrirModalLinajeHijos());
          metricReferidos.style.cursor = 'pointer';
      }
      const btnCerrarLinaje = document.getElementById('btn-cerrar-linaje-hijos');
      const modalLinaje = document.getElementById('modal-linaje-hijos');
      if (btnCerrarLinaje) {
          btnCerrarLinaje.addEventListener('click', () => host.cerrarModalLinajeHijos());
      }
      if (modalLinaje) {
          modalLinaje.addEventListener('click', (e) => {
              if (e.target === modalLinaje) host.cerrarModalLinajeHijos();
          });
      }

      // Botones de modal de código
      if (host.btnEnviar) {
          host.btnEnviar.addEventListener('click', () => host.handleEnviarSolicitud());
      }
      if (host.btnCopyCode) {
          host.btnCopyCode.addEventListener('click', () => host.copyCode());
      }
      if (host.btnCloseCode) {
          host.btnCloseCode.addEventListener('click', () => host.closeCodeModal());
      }

      // Cerrar modales al hacer click fuera
      if (host.modalCode) {
          host.modalCode.addEventListener('click', (e) => {
              if (e.target === host.modalCode) {
                  host.closeCodeModal();
              }
          });
      }

      // Aviso persistente de contactos
      const btnAbrirChat = document.getElementById('btn-contacto-abrir-negociacion')
          || document.getElementById('btn-contacto-abrir-chat');
      const btnSiTrabajo = document.getElementById('btn-contacto-si-trabajo');
      const btnNoConcreto = document.getElementById('btn-contacto-no-concreto');
      const btnSigue = document.getElementById('btn-contacto-sigue');
      if (btnAbrirChat) {
          btnAbrirChat.addEventListener('click', () => host.abrirNegociacionDesdeContactoActual());
      }
      if (btnSiTrabajo) {
          btnSiTrabajo.addEventListener('click', () => host.handleAvisoSiHuboTrabajo());
      }
      if (btnNoConcreto) {
          btnNoConcreto.addEventListener('click', () => host.handleAvisoNoSeConcreto());
      }
      if (btnSigue) {
          btnSigue.addEventListener('click', () => host.handleAvisoSigueEnConversacion());
      }
      const btnSubirPrueba = document.getElementById('btn-subir-prueba-conflicto');
      if (btnSubirPrueba) {
          btnSubirPrueba.addEventListener('click', () => host.subirPruebaConflicto());
      }

      // Modal no concretado (confirmar cierre sin trabajo)
      const modalNoConcreto = document.getElementById('modal-no-concretado');
      const btnNoConcretoConfirm = document.getElementById('btn-no-concretado-confirm');
      const btnNoConcretoCancel = document.getElementById('btn-no-concretado-cancel');
      if (btnNoConcretoConfirm) {
          btnNoConcretoConfirm.addEventListener('click', () => host.confirmarNoConcretado());
      }
      if (btnNoConcretoCancel && modalNoConcreto) {
          btnNoConcretoCancel.addEventListener('click', () => modalNoConcreto.classList.remove('show'));
      }
      // El modal "No se concretó" solo se cierra con "Confirmar" o "Cancelar", no al hacer clic fuera
      if (modalNoConcreto) {
          modalNoConcreto.addEventListener('click', (e) => {
              if (e.target === modalNoConcreto) {
                  e.preventDefault();
                  e.stopPropagation();
              }
          });
      }

      // Modal comprobante Apoyo RUANA (profesional sube comprobante de pago)
      const modalComprobante = document.getElementById('modal-comprobante-apoyo');
      const modalComprobanteContent = document.getElementById('modal-comprobante-apoyo-content');
      const inputComprobanteApoyo = document.getElementById('input-comprobante-apoyo');
      const btnComprobanteEnviar = document.getElementById('btn-comprobante-apoyo-enviar');
      const btnComprobanteCancel = document.getElementById('btn-comprobante-apoyo-cancel');
      if (inputComprobanteApoyo) {
          inputComprobanteApoyo.addEventListener('change', () => {
              const nombreEl = document.getElementById('comprobante-apoyo-nombre');
              if (nombreEl) nombreEl.textContent = inputComprobanteApoyo.files && inputComprobanteApoyo.files[0] ? inputComprobanteApoyo.files[0].name : '';
          });
      }
      if (modalComprobanteContent) {
          modalComprobanteContent.addEventListener('click', (e) => e.stopPropagation());
      }
      if (btnComprobanteEnviar) btnComprobanteEnviar.addEventListener('click', () => host.enviarComprobanteApoyo());
      if (btnComprobanteCancel && modalComprobante) {
          btnComprobanteCancel.addEventListener('click', () => modalComprobante.classList.remove('show'));
      }
      if (modalComprobante) {
          modalComprobante.addEventListener('click', (e) => {
              if (e.target === modalComprobante) {
                  e.preventDefault();
                  e.stopPropagation();
                  modalComprobante.classList.remove('show');
              }
          });
      }

      // Modal pago manual Apoyo RUANA (Bizum, QR Revolut y transferencia)
      const modalPagoApoyo = document.getElementById('modal-pago-apoyo');
      const modalPagoApoyoContent = document.getElementById('modal-pago-apoyo-content');
      const btnPagoApoyoCerrar = document.getElementById('btn-pago-apoyo-cerrar');
      const btnPagoApoyoComprobante = document.getElementById('btn-pago-apoyo-comprobante');
      const btnPagoTabBizum = document.getElementById('btn-pago-apoyo-tab-bizum');
      const btnPagoTabRevolut = document.getElementById('btn-pago-apoyo-tab-revolut');
      const btnPagoTabTransferencia = document.getElementById('btn-pago-apoyo-tab-transferencia');
      if (modalPagoApoyoContent) {
          modalPagoApoyoContent.addEventListener('click', (e) => e.stopPropagation());
      }
      if (btnPagoApoyoCerrar && modalPagoApoyo) {
          btnPagoApoyoCerrar.addEventListener('click', () => modalPagoApoyo.classList.remove('show'));
      }
      if (btnPagoApoyoComprobante && modalPagoApoyo) {
          btnPagoApoyoComprobante.addEventListener('click', () => {
              modalPagoApoyo.classList.remove('show');
              if (host._contactoIdPagoActual) host.abrirModalComprobanteApoyo(host._contactoIdPagoActual);
          });
      }
      if (btnPagoTabBizum) btnPagoTabBizum.addEventListener('click', () => host.setPagoApoyoMetodo('bizum'));
      if (btnPagoTabRevolut) btnPagoTabRevolut.addEventListener('click', () => host.setPagoApoyoMetodo('revolut'));
      if (btnPagoTabTransferencia) btnPagoTabTransferencia.addEventListener('click', () => host.setPagoApoyoMetodo('transferencia'));
      if (modalPagoApoyo) {
          modalPagoApoyo.addEventListener('click', (e) => {
              if (e.target === modalPagoApoyo) {
                  e.preventDefault();
                  e.stopPropagation();
                  modalPagoApoyo.classList.remove('show');
              }
          });
      }

      const modalImpugnarApoyo = document.getElementById('modal-impugnar-apoyo');
      const modalImpugnarContent = document.getElementById('modal-impugnar-apoyo-content');
      const btnImpugnarConfirmar = document.getElementById('btn-impugnar-apoyo-confirmar');
      const btnImpugnarCancelar = document.getElementById('btn-impugnar-apoyo-cancelar');
      if (modalImpugnarContent) {
          modalImpugnarContent.addEventListener('click', (e) => e.stopPropagation());
      }
      if (btnImpugnarConfirmar) {
          btnImpugnarConfirmar.addEventListener('click', () => host.impugnarApoyoRuana(host._contactoIdImpugnarApoyo));
      }
      if (btnImpugnarCancelar && modalImpugnarApoyo) {
          btnImpugnarCancelar.addEventListener('click', () => modalImpugnarApoyo.classList.remove('show'));
      }
      if (modalImpugnarApoyo) {
          modalImpugnarApoyo.addEventListener('click', (e) => {
              if (e.target === modalImpugnarApoyo) {
                  e.preventDefault();
                  e.stopPropagation();
                  modalImpugnarApoyo.classList.remove('show');
              }
          });
      }

      // Modal previo a contactar
      const modalPrevio = document.getElementById('modal-contacto-previo');
      const btnPrevioConfirm = document.getElementById('btn-contacto-previo-confirm');
      const btnPrevioCancel = document.getElementById('btn-contacto-previo-cancel');
      if (btnPrevioConfirm) {
          btnPrevioConfirm.addEventListener('click', () => host.crearContactoYAbrirNegociacion());
      }
      if (btnPrevioCancel && modalPrevio) {
          btnPrevioCancel.addEventListener('click', () => {
              modalPrevio.classList.remove('show');
              host.profesionalSeleccionado = null;
          });
      }


      // Modal importe
      const modalImporte = document.getElementById('modal-contacto-importe');
      const btnImporteConfirm = document.getElementById('btn-contacto-importe-confirm');
      const btnImporteCancel = document.getElementById('btn-contacto-importe-cancel');
      if (btnImporteConfirm) {
          btnImporteConfirm.addEventListener('click', () => host.confirmarImporteContacto());
      }
      if (btnImporteCancel && modalImporte) {
          btnImporteCancel.addEventListener('click', () => {
              modalImporte.classList.remove('show');
              const input = document.getElementById('contacto-importe-input');
              if (input) input.value = '';
          });
      }
      // El modal "Sí, hubo trabajo" solo se cierra con "Confirmar importe" o "Volver", no al hacer clic fuera
      if (modalImporte) {
          modalImporte.addEventListener('click', (e) => {
              if (e.target === modalImporte) {
                  e.preventDefault();
                  e.stopPropagation();
              }
          });
      }

      const modalProfesionales = document.getElementById('modal-profesionales');
      if (modalProfesionales) {
          modalProfesionales.addEventListener('click', (e) => {
              if (e.target === modalProfesionales) {
                  host.cerrarBuscarProfesional();
              }
          });
      }

      // Edición de datos faltantes en perfil (descripción del servicio)
      const btnEditarDesc = document.getElementById('btn-editar-descripcion');
      const btnGuardarDesc = document.getElementById('btn-guardar-descripcion');
      const btnCancelarDesc = document.getElementById('btn-cancelar-descripcion');
      if (btnEditarDesc) btnEditarDesc.addEventListener('click', () => host.iniciarEditarDescripcion());
      if (btnGuardarDesc) btnGuardarDesc.addEventListener('click', () => host.guardarDescripcion());
      if (btnCancelarDesc) btnCancelarDesc.addEventListener('click', () => host.cancelarEditarDescripcion());
      const formCambiarPin = document.getElementById('form-cambiar-pin');
      if (formCambiarPin) {
          formCambiarPin.addEventListener('submit', (e) => {
              e.preventDefault();
              host.guardarPin();
          });
      }
      const catalogoGrid = document.getElementById('catalogo-servicios-grid');
      if (catalogoGrid) {
          catalogoGrid.addEventListener('click', (e) => {
              const btnSave = e.target.closest('[data-servicio-save]');
              if (btnSave) {
                  const pos = Number(btnSave.getAttribute('data-servicio-save'));
                  if (Number.isInteger(pos)) host.guardarCatalogoServicio(pos);
                  return;
              }
              const btnCancel = e.target.closest('[data-servicio-cancel]');
              if (btnCancel) {
                  const pos = Number(btnCancel.getAttribute('data-servicio-cancel'));
                  if (Number.isInteger(pos)) host.cancelarEdicionCatalogo(pos);
                  return;
              }
              const btnEdit = e.target.closest('[data-servicio-edit]');
              if (btnEdit) {
                  e.preventDefault();
                  e.stopPropagation();
                  const pos = Number(btnEdit.getAttribute('data-servicio-edit'));
                  if (Number.isInteger(pos)) host.abrirCatalogoEdicion(pos);
                  return;
              }
              const card = e.target.closest('[data-catalogo-toggle]');
              if (card) {
                  const pos = Number(card.getAttribute('data-catalogo-toggle'));
                  if (Number.isInteger(pos)) host.abrirCatalogoEdicion(pos);
              }
          });
          catalogoGrid.addEventListener('keydown', (e) => {
              if (e.key !== 'Enter' && e.key !== ' ') return;
              const card = e.target.closest('[data-catalogo-toggle]');
              if (!card) return;
              e.preventDefault();
              const pos = Number(card.getAttribute('data-catalogo-toggle'));
              if (Number.isInteger(pos)) host.abrirCatalogoEdicion(pos);
          });
      }
      const btnCatalogoAnadir = document.getElementById('btn-catalogo-anadir');
      if (btnCatalogoAnadir) {
          btnCatalogoAnadir.addEventListener('click', () => host.anadirEspecializacionCatalogo());
      }

      const inputFotoPerfil = document.getElementById('input-foto-perfil');
      const btnQuitarFotoPerfil = document.getElementById('btn-quitar-foto-perfil');
      if (inputFotoPerfil) {
          inputFotoPerfil.addEventListener('change', (e) => {
              const file = e.target.files && e.target.files[0];
              if (file) host.subirFotoPerfil(file);
          });
      }
      if (btnQuitarFotoPerfil) {
          btnQuitarFotoPerfil.addEventListener('click', () => host.quitarFotoPerfil());
      }

      // Oficios faltantes: Ver todos / Ocultar / Buscador
      const btnVerTodosOficios = document.getElementById('btn-ver-todos-oficios');
      const btnOcultarOficios = document.getElementById('btn-ocultar-oficios');
      const oficiosFaltantesSearch = document.getElementById('oficios-faltantes-search');
      if (btnVerTodosOficios) btnVerTodosOficios.addEventListener('click', () => host.expandirOficiosFaltantes());
      if (btnOcultarOficios) btnOcultarOficios.addEventListener('click', () => host.ocultarOficiosFaltantes());
      if (oficiosFaltantesSearch) oficiosFaltantesSearch.addEventListener('input', () => host.filtrarOficiosFaltantes());

      const directorioSearch = document.getElementById('directorio-search');
      if (directorioSearch) directorioSearch.addEventListener('input', () => host.renderProfesionales());

      // Delegación: clic en oficio faltante → generar invitación
      const oficiosWrap = document.getElementById('grupo-oficios-faltantes-wrap');
      if (oficiosWrap) oficiosWrap.addEventListener('click', (e) => {
          const tag = e.target.closest('.oficios-faltantes-tag, .oficio-item');
          if (tag && tag.dataset.oficio) host.generarInvitacionOficio(tag.dataset.oficio);
      });

      // Modal invitación oficio
      const btnCopiarInv = document.getElementById('btn-copiar-invitacion-oficio');
      const btnCerrarInv = document.getElementById('btn-cerrar-invitacion-oficio');
      const modalInv = document.getElementById('modal-invitacion-oficio');
      if (btnCopiarInv) btnCopiarInv.addEventListener('click', () => host.copiarCodigoInvitacionOficio());
      if (btnCerrarInv) btnCerrarInv.addEventListener('click', () => host.cerrarModalInvitacionOficio());
      if (modalInv) modalInv.addEventListener('click', (e) => { if (e.target === modalInv) host.cerrarModalInvitacionOficio(); });

      // Al volver a la pestaña: recargar datos de alertas y re-evaluar banners
      document.addEventListener('visibilitychange', () => {
          if (document.visibilityState !== 'visible' || !host.codigoAliado) return;
          host.refreshAfterAction(['perfil', 'metricas', 'solicitudes', 'directorio', 'alertas', 'contactos']);
      });
  }

modules.events = {

    setupEventListeners: setupEventListeners,
};
})(typeof window !== 'undefined' ? window : globalThis);
