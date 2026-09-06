"""Constantes compartidas de persistencia RUANA (extraídas de db_manager)."""

from __future__ import annotations

import os
from pathlib import Path

RUANA_ROOT = Path(__file__).resolve().parent.parent

ESTADOS_GRUPO = ("activo", "en_competencia", "disuelto")
SUFIJOS_GRUPO = (
    "PUENTE",
    "FARO",
    "NEXO",
    "RAÍZ",
    "PLAZA",
    "RED",
    "HOGAR",
    "IMPULSO",
    "ORIGEN",
    "ENLACE",
)
MAX_GRUPOS_POR_CP = 5

# Grupo Madre por ciudad (incubación territorial)
TIPO_GRUPO_TERRITORIAL = "territorial"
TIPO_GRUPO_MADRE = "madre"
CP_POSTAL_SENTINEL_MADRE = "__MADRE__"
CP_MODO_INCUBACION = "incubacion"
CP_MODO_TERRITORIAL = "territorial"
CP_MADUREZ_MIN_ALIADOS = 10
CP_MADUREZ_MIN_ENCARGOS = 3
AVISO_GRUPO_MADRE = "grupo_madre_bienvenida"
AVISO_CP_INDEPENDIZADO = "cp_independizado"

# Encargos válidos para madurez de CP (flujo real contactos_ruana):
# Cuentan desde que el profesional acepta (aceptado) o estados posteriores de trabajo real.
# NO cuentan: iniciado, en_conversacion (posible sin aceptar), chat_agotado, cierres sin encargo.
ESTADOS_ENCARGO_VALIDO_MADUREZ = (
    "aceptado",
    "trabajo_en_progreso",
    "acuerdo_alcanzado",
    "pendiente_de_pago",
    "trabajo_cerrado",
    "importe_en_disputa",
)
ALIADO_FOTO_PERFIL_COLUMN = "foto_perfil_url"
ESTADOS_ALIADO_CONTACTO_LIBERADO = ("expulsado", "rechazado")
SQL_ESTADO_CONTACTO_OCUPADO = (
    "LOWER(TRIM(COALESCE(estado, ''))) NOT IN ('expulsado', 'rechazado')"
)
DB_PATH = str(
    Path(
        os.environ.get(
            "RUANA_DB_PATH",
            Path(__file__).resolve().parent.parent / "ruana.db",
        )
    ).resolve()
)
RUANA_CODIGO_INVITACION_REGEX = r"^RUANA-\d+-[A-Z0-9]+-[A-Z0-9]{4}$"

# Crecimiento orgánico de grupos profesionales
GRUPO_EN_CREACION_MAX_ALIADOS = 10
CRECIMIENTO_GRUPO_MAX_RECOMPENSAS = 10
CRECIMIENTO_GRUPO_SCORE_DELTA = 5
INVITACION_TIPO_CRECIMIENTO_GRUPO = "crecimiento_grupo"
SCORE_MOTIVO_ALIADO_INVITADO_REGISTRADO = "aliado_invitado_registrado"


def email_liberado_aliado(codigo: str) -> str:
    return f'liberado+{codigo}@ruana.invalid'


def telefono_liberado_aliado(codigo: str) -> str:
    return f'LIBERADO-{codigo}'


# Compat aliases (nombres históricos usados en DBManager)
_email_liberado_aliado = email_liberado_aliado
_telefono_liberado_aliado = telefono_liberado_aliado
