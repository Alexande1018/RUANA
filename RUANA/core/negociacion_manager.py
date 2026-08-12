"""Fachada de compatibilidad — negociación guiada.

Campamento Base: la implementación vive en
`core.services.negociacion_domain`. Este módulo reexporta la API pública
para no romper imports existentes (tests, services, blueprints, scripts).
"""
from core.services.negociacion_domain import *  # noqa: F401,F403
from core.services import negociacion_domain as _domain

# Reexport explícito de símbolos usados frecuentemente (ayuda a IDEs/grep).
CAMPOS_SOLICITANTE = _domain.CAMPOS_SOLICITANTE
CAMPOS_ORDEN = _domain.CAMPOS_ORDEN
CAMPOS_LABELS = _domain.CAMPOS_LABELS
ESTADO_PENDIENTE = _domain.ESTADO_PENDIENTE
ESTADO_EN_NEGOCIACION = _domain.ESTADO_EN_NEGOCIACION
ESTADO_CONFIRMADO = _domain.ESTADO_CONFIRMADO
ESTADO_LABELS = _domain.ESTADO_LABELS
TIPO_SISTEMA = _domain.TIPO_SISTEMA
TIPO_PROPUESTA = _domain.TIPO_PROPUESTA
TIPO_ACEPTACION = _domain.TIPO_ACEPTACION
TIPO_CONTRAOFERTA = _domain.TIPO_CONTRAOFERTA

parse_precio_catalogo = _domain.parse_precio_catalogo
estado_inicial = _domain.estado_inicial
parse_negociacion = _domain.parse_negociacion
normalizar_estado = _domain.normalizar_estado
serializar_negociacion = _domain.serializar_negociacion
resumen_acuerdo = _domain.resumen_acuerdo
meta_negociacion = _domain.meta_negociacion
accion_disponible = _domain.accion_disponible
proponer_campo = _domain.proponer_campo
proponer_propuesta_completa = _domain.proponer_propuesta_completa
contraoferta_campo = _domain.contraoferta_campo
aceptar_campo = _domain.aceptar_campo
reabrir_campo_negociacion = _domain.reabrir_campo_negociacion
construir_payload = _domain.construir_payload
