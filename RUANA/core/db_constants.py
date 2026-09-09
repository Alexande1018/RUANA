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

# Territorio directo: hasta 5 grupos independientes por código postal.
TIPO_GRUPO_TERRITORIAL = "territorial"
CP_MODO_TERRITORIAL = "territorial"
CP_NUEVO_GRUPO_MIN_ALIADOS = 10

# Históricos: se conservan para detectar y migrar datos de Grupo Madre. No se crean grupos madre.
TIPO_GRUPO_MADRE = "madre"
CP_POSTAL_SENTINEL_MADRE = "__MADRE__"
CP_MODO_INCUBACION = "incubacion"

# Proximidad: un único profesional cercano; no abre el directorio de otros grupos.
# nivel 1 = mismo CP, 2 = misma ciudad (territorio_service.proximidad_territorial).
PROXIMIDAD_NIVEL_MAX = 2
PROXIMIDAD_DISTANCIA_MAX = 2000
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
