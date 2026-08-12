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


def email_liberado_aliado(codigo: str) -> str:
    return f'liberado+{codigo}@ruana.invalid'


def telefono_liberado_aliado(codigo: str) -> str:
    return f'LIBERADO-{codigo}'


# Compat aliases (nombres históricos usados en DBManager)
_email_liberado_aliado = email_liberado_aliado
_telefono_liberado_aliado = telefono_liberado_aliado
