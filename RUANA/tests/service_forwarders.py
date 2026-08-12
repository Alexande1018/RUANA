"""Helpers de test: reenvían llamadas service.fn(db, ...) → db.fn(...) para FakeDB."""

from __future__ import annotations

from typing import Iterable, Mapping

from core.services import (
    admin_service,
    aliado_service,
    catalogo_service,
    competencia_service,
    contacto_service,
    evaluacion_service,
    invitacion_service,
    negociacion_service,
    pago_service,
    solicitud_service,
)


# Métodos de dominio que FakeDB suele implementar y los BPs llaman vía service.
_DEFAULT_FORWARDERS: Mapping[object, Iterable[str]] = {
    aliado_service: (
        "obtener_aliado_por_codigo",
        "codigo_disponible_para_asignar",
        "codigo_existe",
        "listar_aliados",
        "obtener_aliado_por_id",
        "actualizar_aliado",
        "registrar_acceso_login",
    ),
    invitacion_service: (
        "_registrar_invitacion",
        "invitacion_codigo_existe",
        "generar_invitacion_oficio",
        "crear_campana_invitacion",
        "desactivar_campana_invitacion",
        "validar_campana_invitacion",
        "obtener_campana_invitacion",
        "obtener_invitacion_pendiente",
        "listar_campanas_invitacion",
        "eliminar_aliado_placeholder",
    ),
    solicitud_service: (
        "marcar_solicitud_candidato_pendiente",
        "atender_solicitud_por_id",
        "marcar_solicitud_contestada",
        "vincular_solicitud_a_aliado_incorporado",
    ),
    admin_service: (
        "obtener_o_crear_invitador_admin",
    ),
    competencia_service: (
        "finalizar_competencia_activas_vencidas",
        "purga_mensual",
    ),
    negociacion_service: (
        "obtener_negociacion_contacto",
        "proponer_negociacion",
        "aceptar_negociacion",
        "contraoferta_negociacion",
        "cerrar_negociacion",
        "listar_acuerdos_aliado",
    ),
    evaluacion_service: (
        "obtener_evaluacion",
        "listar_evaluaciones",
        "obtener_historico_evaluaciones",
        "obtener_estadisticas_evaluaciones",
    ),
    pago_service: (
        "obtener_metodos_pago_ruana",
        "actualizar_metodos_pago_ruana",
        "subir_prueba_conflicto",
        "subir_comprobante_apoyo_ruana",
    ),
    catalogo_service: (
        "listar_catalogo_servicios_aliado",
        "guardar_catalogo_servicio_aliado",
    ),
    contacto_service: (
        "obtener_contacto_resumen",
    ),
}


def install_service_db_forwarders(monkeypatch, extra: Mapping[object, Iterable[str]] | None = None):
    """
    Instala forwarders service → db para tests con FakeDB.
    service.method(db, *args, **kwargs) delega en db.method(*args, **kwargs).
    Si el FakeDB no define el método, se deja el original del service.
    """
    mapping = dict(_DEFAULT_FORWARDERS)
    if extra:
        for svc, names in extra.items():
            mapping[svc] = tuple(dict.fromkeys(tuple(mapping.get(svc, ())) + tuple(names)))

    for service_mod, names in mapping.items():
        for name in names:
            if not hasattr(service_mod, name):
                continue

            def _make(method_name: str):
                def _forward(db, *args, **kwargs):
                    fn = getattr(db, method_name, None)
                    if fn is None or not callable(fn):
                        raise AttributeError(
                            f"FakeDB no implementa {method_name} (requerido por forwarder de test)"
                        )
                    return fn(*args, **kwargs)

                return _forward

            monkeypatch.setattr(service_mod, name, _make(name))
