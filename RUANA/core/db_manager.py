"""
Database Manager para RUANA - SQLite
Maneja toda la persistencia de datos usando SQLite
"""

import sqlite3
import json
import os
import random
import re
import string
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any, Tuple
import threading

from core.postgres_compat import connect as pg_compat_connect
from core.settings import get_settings
from core import negociacion_manager as neg_mgr
from core.db_constants import (
    ALIADO_FOTO_PERFIL_COLUMN,
    DB_PATH,
    ESTADOS_ALIADO_CONTACTO_LIBERADO,
    ESTADOS_GRUPO,
    MAX_GRUPOS_POR_CP,
    RUANA_CODIGO_INVITACION_REGEX,
    SQL_ESTADO_CONTACTO_OCUPADO,
    SUFIJOS_GRUPO,
    _email_liberado_aliado,
    _telefono_liberado_aliado,
)
from core.services import score_service
from core.services import schema_service
from core.services import admin_service
from core.services import aliado_service
from core.services import catalogo_service
from core.services import chat_service
from core.services import solicitud_service
from core.services import grupo_service
from core.services import competencia_service
from core.services import pago_service
from core.services import invitacion_service
from core.services import referido_service
from core.services import negociacion_service
from core.services import contacto_service
from core.services import evaluacion_service
from core.services import notificacion_service
from core.repositories.score_repo import ScoreRepo

# Reexport / compat: constantes viven en core.db_constants

class DBManager:
    """Gestor de base de datos SQLite para RUANA"""
    
    def __init__(self, db_path: Optional[str] = None):
        """
        Inicializa el gestor de BD
        
        Args:
            db_path: Ruta a la BD. Si es None, usa la ruta global DB_PATH.
        """
        # Obligar a usar una ruta única y absoluta salvo que se pase
        # explícitamente otra (por ejemplo, en tests muy controlados).
        if db_path is None:
            db_path = Path(DB_PATH)
        else:
            db_path = Path(db_path).resolve()
        
        self.db_path = str(db_path)
        self._lock = threading.RLock()  # Para operaciones thread-safe
        self.settings = get_settings()
        self.backend = "postgres" if self.settings.postgres_configured else "sqlite"
        
        # Inicializar base de datos
        if self.backend == "sqlite":
            self._init_db()
        else:
            self._init_postgres_schema()

    def _connect(self):
        """Open a database connection for the configured backend."""
        if self.backend == "postgres":
            return pg_compat_connect(self.settings.database_url)
        return sqlite3.connect(self.db_path)

    def _init_postgres_schema(self):
        """Fachada Campamento Base → schema_service._init_postgres_schema."""
        return schema_service._init_postgres_schema(self)

    
    def _init_db(self):
        """Fachada Campamento Base → schema_service._init_db."""
        return schema_service._init_db(self)

    def _generar_id_unico_grupo(self) -> str:
        """Fachada Campamento Base → grupo_service._generar_id_unico_grupo."""
        return grupo_service._generar_id_unico_grupo(self)

    def _generar_nombre_grupo(self, cursor) -> str:
        """Fachada Campamento Base → grupo_service._generar_nombre_grupo."""
        return grupo_service._generar_nombre_grupo(self, cursor)

    def _migrar_grupos_si_procede(self, conn, cursor) -> None:
        """Fachada Campamento Base → schema_service._migrar_grupos_si_procede."""
        return schema_service._migrar_grupos_si_procede(self, conn, cursor)

        # No hacer commit aquí; lo hace _init_db al final

    def _migrar_grupos_multi_cp_si_procede(self, conn, cursor) -> None:
        """Fachada Campamento Base → schema_service._migrar_grupos_multi_cp_si_procede."""
        return schema_service._migrar_grupos_multi_cp_si_procede(self, conn, cursor)

    def _migrar_aliados_grupo_id(self, conn, cursor) -> None:
        """Fachada Campamento Base → schema_service._migrar_aliados_grupo_id."""
        return schema_service._migrar_aliados_grupo_id(self, conn, cursor)

    def _migrar_aliados_derrotas_competencia(self, conn, cursor) -> None:
        """Fachada Campamento Base → schema_service._migrar_aliados_derrotas_competencia."""
        return schema_service._migrar_aliados_derrotas_competencia(self, conn, cursor)

    def _migrar_aliados_especializaciones(self, conn, cursor) -> None:
        """Fachada Campamento Base → schema_service._migrar_aliados_especializaciones."""
        return schema_service._migrar_aliados_especializaciones(self, conn, cursor)

    def _migrar_aliados_descripcion_servicio(self, conn, cursor) -> None:
        """Fachada Campamento Base → schema_service._migrar_aliados_descripcion_servicio."""
        return schema_service._migrar_aliados_descripcion_servicio(self, conn, cursor)

    def _migrar_aliados_foto_perfil(self, conn, cursor) -> None:
        """Fachada Campamento Base → schema_service._migrar_aliados_foto_perfil."""
        return schema_service._migrar_aliados_foto_perfil(self, conn, cursor)

    def _migrar_aliados_especializacion_singular(self, conn, cursor) -> None:
        """Fachada Campamento Base → schema_service._migrar_aliados_especializacion_singular."""
        return schema_service._migrar_aliados_especializacion_singular(self, conn, cursor)

    def _migrar_contactos_comprobante(self, conn, cursor) -> None:
        """Fachada Campamento Base → schema_service._migrar_contactos_comprobante."""
        return schema_service._migrar_contactos_comprobante(self, conn, cursor)

    def _migrar_contactos_apoyo_ruana(self, conn, cursor) -> None:
        """Fachada Campamento Base → schema_service._migrar_contactos_apoyo_ruana."""
        return schema_service._migrar_contactos_apoyo_ruana(self, conn, cursor)

    def _migrar_contactos_ruana_idx_contacto_aliado(self, conn, cursor) -> None:
        """Fachada Campamento Base → schema_service._migrar_contactos_ruana_idx_contacto_aliado."""
        return schema_service._migrar_contactos_ruana_idx_contacto_aliado(self, conn, cursor)

    def _migrar_aliados_pago(self, conn, cursor) -> None:
        """Fachada Campamento Base → schema_service._migrar_aliados_pago."""
        return schema_service._migrar_aliados_pago(self, conn, cursor)

    def _migrar_notificaciones_aliado(self, conn, cursor) -> None:
        """Fachada Campamento Base → schema_service._migrar_notificaciones_aliado."""
        return schema_service._migrar_notificaciones_aliado(self, conn, cursor)

    def _migrar_centro_comunicacion_ruana(self, conn, cursor) -> None:
        """Fachada Campamento Base → schema_service._migrar_centro_comunicacion_ruana."""
        return schema_service._migrar_centro_comunicacion_ruana(self, conn, cursor)

    def _migrar_contactos_posponer_recordatorio(self, conn, cursor) -> None:
        """Fachada Campamento Base → schema_service._migrar_contactos_posponer_recordatorio."""
        return schema_service._migrar_contactos_posponer_recordatorio(self, conn, cursor)

    def _migrar_contactos_fecha_pospuesto_hasta(self, conn, cursor) -> None:
        """Fachada Campamento Base → schema_service._migrar_contactos_fecha_pospuesto_hasta."""
        return schema_service._migrar_contactos_fecha_pospuesto_hasta(self, conn, cursor)

    def _migrar_chat_mensajes(self, conn, cursor) -> None:
        """Fachada Campamento Base → schema_service._migrar_chat_mensajes."""
        return schema_service._migrar_chat_mensajes(self, conn, cursor)

    def _migrar_negociacion_guiada(self, conn, cursor) -> None:
        """Fachada Campamento Base → schema_service._migrar_negociacion_guiada."""
        return schema_service._migrar_negociacion_guiada(self, conn, cursor)

    def _migrar_acuerdo_cierre_bilateral(self, conn, cursor) -> None:
        """Fachada Campamento Base → schema_service._migrar_acuerdo_cierre_bilateral."""
        return schema_service._migrar_acuerdo_cierre_bilateral(self, conn, cursor)

    def _migrar_importe_acordado(self, conn, cursor) -> None:
        """Fachada Campamento Base → schema_service._migrar_importe_acordado."""
        return schema_service._migrar_importe_acordado(self, conn, cursor)

    def _migrar_contactos_motivo_contacto(self, conn, cursor) -> None:
        """Fachada Campamento Base → schema_service._migrar_contactos_motivo_contacto."""
        return schema_service._migrar_contactos_motivo_contacto(self, conn, cursor)

    def _migrar_contactos_es_urgente(self, conn, cursor) -> None:
        """Fachada Campamento Base → schema_service._migrar_contactos_es_urgente."""
        return schema_service._migrar_contactos_es_urgente(self, conn, cursor)

    def _migrar_aliado_accesos_dia(self, conn, cursor) -> None:
        """Fachada Campamento Base → schema_service._migrar_aliado_accesos_dia."""
        return schema_service._migrar_aliado_accesos_dia(self, conn, cursor)

    def _migrar_drop_chat_messages(self, conn, cursor) -> None:
        """Fachada Campamento Base → schema_service._migrar_drop_chat_messages."""
        return schema_service._migrar_drop_chat_messages(self, conn, cursor)

    def _migrar_payment_conflicts(self, conn, cursor) -> None:
        """Fachada Campamento Base → schema_service._migrar_payment_conflicts."""
        return schema_service._migrar_payment_conflicts(self, conn, cursor)

    def _migrar_stripe_pagos(self, conn, cursor) -> None:
        """Fachada Campamento Base → schema_service._migrar_stripe_pagos."""
        return schema_service._migrar_stripe_pagos(self, conn, cursor)

    def _migrar_contactos_validacion_pago(self, conn, cursor) -> None:
        """Fachada Campamento Base → schema_service._migrar_contactos_validacion_pago."""
        return schema_service._migrar_contactos_validacion_pago(self, conn, cursor)

    def _migrar_solicitudes_unificado(self, conn, cursor) -> None:
        """Fachada Campamento Base → schema_service._migrar_solicitudes_unificado."""
        return schema_service._migrar_solicitudes_unificado(self, conn, cursor)

    def _migrar_contacto_panel_oculto(self, conn, cursor) -> None:
        """Fachada Campamento Base → schema_service._migrar_contacto_panel_oculto."""
        return schema_service._migrar_contacto_panel_oculto(self, conn, cursor)

    def _migrar_competencia_scores(self, conn, cursor) -> None:
        """Fachada Campamento Base → schema_service._migrar_competencia_scores."""
        return schema_service._migrar_competencia_scores(self, conn, cursor)

    def _migrar_retador_rename(self, conn, cursor) -> None:
        """Fachada Campamento Base → schema_service._migrar_retador_rename."""
        return schema_service._migrar_retador_rename(self, conn, cursor)

    def _migrar_competencia_permanencia(self, conn, cursor) -> None:
        """Fachada Campamento Base → schema_service._migrar_competencia_permanencia."""
        return schema_service._migrar_competencia_permanencia(self, conn, cursor)

    def _columna_retador_competencia(self, cursor) -> str:
        """Fachada Campamento Base → competencia_service._columna_retador_competencia."""
        return competencia_service._columna_retador_competencia(self, cursor)

    def _columnas_compat_competencia(self, cursor) -> Dict[str, str]:
        """Fachada Campamento Base → competencia_service._columnas_compat_competencia."""
        return competencia_service._columnas_compat_competencia(self, cursor)

    def _es_condicion_aliado_placeholder_sql(self) -> str:
        """Fachada Campamento Base → admin_service._es_condicion_aliado_placeholder_sql."""
        return admin_service._es_condicion_aliado_placeholder_sql(self)

    def _purgar_placeholders_control_aliados(self, conn, cursor) -> None:
        """Fachada Campamento Base → admin_service._purgar_placeholders_control_aliados."""
        return admin_service._purgar_placeholders_control_aliados(self, conn, cursor)

    def _ejecutar_purga_placeholders(self, cursor) -> int:
        """Fachada Campamento Base → admin_service._ejecutar_purga_placeholders."""
        return admin_service._ejecutar_purga_placeholders(self, cursor)

    def purgar_aliados_placeholder(self) -> Dict[str, Any]:
        """Fachada Campamento Base → admin_service.purgar_aliados_placeholder."""
        return admin_service.purgar_aliados_placeholder(self)

    def _migrar_datos_plaza_oficio(self, conn, cursor) -> None:
        """Fachada Campamento Base → schema_service._migrar_datos_plaza_oficio."""
        return schema_service._migrar_datos_plaza_oficio(self, conn, cursor)

    def _migrar_drop_especializaciones(self, conn, cursor) -> None:
        """Fachada Campamento Base → schema_service._migrar_drop_especializaciones."""
        return schema_service._migrar_drop_especializaciones(self, conn, cursor)

    def _migrar_referidos_origen(self, conn, cursor) -> None:
        """Fachada Campamento Base → schema_service._migrar_referidos_origen."""
        return schema_service._migrar_referidos_origen(self, conn, cursor)

    def _migrar_invitaciones_oficio_codigo_referido(self, conn, cursor) -> None:
        """Fachada Campamento Base → schema_service._migrar_invitaciones_oficio_codigo_referido."""
        return schema_service._migrar_invitaciones_oficio_codigo_referido(self, conn, cursor)

    def _migrar_aliados_invitado_por(self, conn, cursor) -> None:
        """Fachada Campamento Base → schema_service._migrar_aliados_invitado_por."""
        return schema_service._migrar_aliados_invitado_por(self, conn, cursor)

    def _migrar_invitaciones_solicitud_id(self, conn, cursor) -> None:
        """Fachada Campamento Base → schema_service._migrar_invitaciones_solicitud_id."""
        return schema_service._migrar_invitaciones_solicitud_id(self, conn, cursor)

    def _migrar_solicitudes_candidato(self, conn, cursor) -> None:
        """Fachada Campamento Base → schema_service._migrar_solicitudes_candidato."""
        return schema_service._migrar_solicitudes_candidato(self, conn, cursor)

    ORIGEN_REFERIDO_LABELS: Dict[str, str] = {
        'aliado': 'Invitación de aliado',
        'ampliar_red': 'Ampliar mi red',
        'yo_conozco_a_alguien': 'Conozco a alguien',
        'oficio': 'Invitación por oficio',
        'campana': 'Campaña del administrador',
        'admin_invitacion': 'Código del administrador',
        'admin': 'Código del administrador',
        'organico': 'Registro orgánico',
        'huerfano': 'Registro directo · sin atribución',
        'sin_atribucion': 'Sin atribución',
    }

    def etiqueta_origen_referido(self, origen: str) -> str:
        """Fachada Campamento Base → referido_service.etiqueta_origen_referido."""
        return referido_service.etiqueta_origen_referido(self, origen)

    def obtener_codigo_admin_referidos(self) -> str:
        """Fachada Campamento Base → referido_service.obtener_codigo_admin_referidos."""
        return referido_service.obtener_codigo_admin_referidos(self)

    def _referidos_tiene_origen(self, cursor) -> bool:
        """Fachada Campamento Base → referido_service._referidos_tiene_origen."""
        return referido_service._referidos_tiene_origen(self, cursor)

    def _aliados_tiene_invitado_por(self, cursor) -> bool:
        """Fachada Campamento Base → referido_service._aliados_tiene_invitado_por."""
        return referido_service._aliados_tiene_invitado_por(self, cursor)

    def asignar_invitado_por(
        self,
        codigo_referido: str,
        codigo_invitador: str,
        origen: str = '',
        overwrite: bool = False,
    ) -> bool:
        """Fachada Campamento Base → referido_service.asignar_invitado_por."""
        return referido_service.asignar_invitado_por(self, codigo_referido, codigo_invitador, origen, overwrite)

    def _insert_referido(self, codigo_referido: str, codigo_invitador: str, origen: str = '') -> bool:
        """Fachada Campamento Base → referido_service._insert_referido."""
        return referido_service._insert_referido(self, codigo_referido, codigo_invitador, origen)

    def _origen_por_invitador(self, codigo_invitador: str, default: str = 'aliado') -> str:
        """Fachada Campamento Base → referido_service._origen_por_invitador."""
        return referido_service._origen_por_invitador(self, codigo_invitador, default)

    def backfill_invitado_por_linaje(self) -> Dict[str, int]:
        """Fachada Campamento Base → referido_service.backfill_invitado_por_linaje."""
        return referido_service.backfill_invitado_por_linaje(self)

    def listar_hijos_directos_linaje(self, codigo_invitador: str) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → referido_service.listar_hijos_directos_linaje."""
        return referido_service.listar_hijos_directos_linaje(self, codigo_invitador)

    def obtener_ruta_linaje_hacia_arriba(self, codigo: str) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → referido_service.obtener_ruta_linaje_hacia_arriba."""
        return referido_service.obtener_ruta_linaje_hacia_arriba(self, codigo)

    def obtener_linaje_aliado(self, codigo: str) -> Optional[Dict[str, Any]]:
        """Fachada Campamento Base → referido_service.obtener_linaje_aliado."""
        return referido_service.obtener_linaje_aliado(self, codigo)

    def _obtener_origen_referido(self, codigo_referido: str) -> str:
        """Fachada Campamento Base → referido_service._obtener_origen_referido."""
        return referido_service._obtener_origen_referido(self, codigo_referido)

    @staticmethod
    def _normalizar_texto_catalogo(texto: str) -> str:
        """Fachada Campamento Base → catalogo_service._normalizar_texto_catalogo."""
        return catalogo_service._normalizar_texto_catalogo(texto)

    def _resolver_en_conjunto_catalogo(self, valor: str, permitidos: set) -> Optional[str]:
        """Fachada Campamento Base → catalogo_service._resolver_en_conjunto_catalogo."""
        return catalogo_service._resolver_en_conjunto_catalogo(self, valor, permitidos)

    def oficio_en_catalogo(self, oficio: str) -> bool:
        """Fachada Campamento Base → catalogo_service.oficio_en_catalogo."""
        return catalogo_service.oficio_en_catalogo(self, oficio)

    # ===============================================
    # OPERACIONES GRUPOS TERRITORIALES
    # ===============================================

    def obtener_grupos_activos_por_cp(self, codigo_postal: str) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → grupo_service.obtener_grupos_activos_por_cp."""
        return grupo_service.obtener_grupos_activos_por_cp(self, codigo_postal)

    def _grupo_tiene_oficio(self, cursor, grupo_id: int, oficio: str) -> bool:
        """Fachada Campamento Base → grupo_service._grupo_tiene_oficio."""
        return grupo_service._grupo_tiene_oficio(self, cursor, grupo_id, oficio)

    def _grupo_tiene_plaza(self, cursor, grupo_id: int, oficio_principal: str, especializacion: Optional[str] = None) -> bool:
        """Fachada Campamento Base → grupo_service._grupo_tiene_plaza."""
        return grupo_service._grupo_tiene_plaza(self, cursor, grupo_id, oficio_principal, especializacion)

    def plaza_ocupada_en_grupo(self, grupo_id: int, oficio_principal: str, especializacion: Optional[str] = None) -> bool:
        """Fachada Campamento Base → grupo_service.plaza_ocupada_en_grupo."""
        return grupo_service.plaza_ocupada_en_grupo(self, grupo_id, oficio_principal, especializacion)

    def obtener_especializaciones_ocupadas(self, grupo_id: int, oficio_principal: str) -> set:
        """Fachada Campamento Base → grupo_service.obtener_especializaciones_ocupadas."""
        return grupo_service.obtener_especializaciones_ocupadas(self, grupo_id, oficio_principal)

    def buscar_grupo_sin_oficio(self, codigo_postal: str, oficio: str, especializacion: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Fachada Campamento Base → grupo_service.buscar_grupo_sin_oficio."""
        return grupo_service.buscar_grupo_sin_oficio(self, codigo_postal, oficio, especializacion)

    def buscar_grupo_formacion_en_cp(self, codigo_postal: str, oficio: str) -> Optional[Dict[str, Any]]:
        """Fachada Campamento Base → grupo_service.buscar_grupo_formacion_en_cp."""
        return grupo_service.buscar_grupo_formacion_en_cp(self, codigo_postal, oficio)

    def contar_grupos_activos_por_cp(self, codigo_postal: str) -> int:
        """Fachada Campamento Base → grupo_service.contar_grupos_activos_por_cp."""
        return grupo_service.contar_grupos_activos_por_cp(self, codigo_postal)

    def crear_grupo_en_cp(self, codigo_postal: str, ciudad: str = "", provincia: str = "") -> Dict[str, Any]:
        """Fachada Campamento Base → grupo_service.crear_grupo_en_cp."""
        return grupo_service.crear_grupo_en_cp(self, codigo_postal, ciudad, provincia)

    def sugerir_cp_adyacente(self, codigo_postal: str) -> Optional[str]:
        """Fachada Campamento Base → grupo_service.sugerir_cp_adyacente."""
        return grupo_service.sugerir_cp_adyacente(self, codigo_postal)

    def obtener_o_crear_grupo(self, codigo_postal: str, ciudad: str = "", provincia: str = "") -> Dict[str, Any]:
        """Fachada Campamento Base → grupo_service.obtener_o_crear_grupo."""
        return grupo_service.obtener_o_crear_grupo(self, codigo_postal, ciudad, provincia)

    def obtener_grupo_por_codigo_postal(self, codigo_postal: str) -> Optional[Dict[str, Any]]:
        """Fachada Campamento Base → grupo_service.obtener_grupo_por_codigo_postal."""
        return grupo_service.obtener_grupo_por_codigo_postal(self, codigo_postal)

    def obtener_grupo_por_id(self, grupo_id: int) -> Optional[Dict[str, Any]]:
        """Fachada Campamento Base → grupo_service.obtener_grupo_por_id."""
        return grupo_service.obtener_grupo_por_id(self, grupo_id)

    def contar_aliados_activos_grupo(self, grupo_id: int) -> int:
        """Fachada Campamento Base → grupo_service.contar_aliados_activos_grupo."""
        return grupo_service.contar_aliados_activos_grupo(self, grupo_id)

    def obtener_oficios_grupo(self, grupo_id: int) -> set:
        """Fachada Campamento Base → catalogo_service.obtener_oficios_grupo."""
        return catalogo_service.obtener_oficios_grupo(self, grupo_id)

    def get_catalogo_oficios_ruana(self) -> List[str]:
        """Fachada Campamento Base → catalogo_service.get_catalogo_oficios_ruana."""
        return catalogo_service.get_catalogo_oficios_ruana(self)

    def get_catalogo_oficios_jerarquico(self) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → catalogo_service.get_catalogo_oficios_jerarquico."""
        return catalogo_service.get_catalogo_oficios_jerarquico(self)

    def info_grupo_para_panel(self, grupo_id: int) -> Optional[Dict[str, Any]]:
        """Fachada Campamento Base → grupo_service.info_grupo_para_panel."""
        return grupo_service.info_grupo_para_panel(self, grupo_id)

    def _buscar_candidato_fusion(self, cursor, grupo_id: int, codigo_postal: str, oficio_aliado_solo: str) -> Optional[Dict[str, Any]]:
        """Fachada Campamento Base → grupo_service._buscar_candidato_fusion."""
        return grupo_service._buscar_candidato_fusion(self, cursor, grupo_id, codigo_postal, oficio_aliado_solo)

    def _fusionar_grupos_mas_antiguo_absorbe(self, conn, cursor, grupo_absorbedor_id: int, grupo_a_disolver_id: int) -> None:
        """Fachada Campamento Base → grupo_service._fusionar_grupos_mas_antiguo_absorbe."""
        return grupo_service._fusionar_grupos_mas_antiguo_absorbe(self, conn, cursor, grupo_absorbedor_id, grupo_a_disolver_id)

    def _buscar_grupo_compatible_mismo_cp(self, cursor, codigo_postal: str, oficio: str, excluir_grupo_id: int) -> Optional[Dict[str, Any]]:
        """Fachada Campamento Base → grupo_service._buscar_grupo_compatible_mismo_cp."""
        return grupo_service._buscar_grupo_compatible_mismo_cp(self, cursor, codigo_postal, oficio, excluir_grupo_id)

    def procesar_viabilidad_grupo(self, grupo_id: int) -> Dict[str, Any]:
        """Fachada Campamento Base → grupo_service.procesar_viabilidad_grupo."""
        return grupo_service.procesar_viabilidad_grupo(self, grupo_id)

    def procesar_grupos_no_viables(self) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → grupo_service.procesar_grupos_no_viables."""
        return grupo_service.procesar_grupos_no_viables(self)

    # ===============================================
    # OPERACIONES ALIADOS
    # ===============================================
    
    MENSAJE_LISTA_ESPERA = (
        "¡Bienvenido a RUANA! 🎉\n\n"
        "Tu registro se ha completado correctamente.\n\n"
        "En este momento, los grupos de tu Código Postal ya han alcanzado su capacidad máxima "
        "para tu oficio, por lo que has sido incluido en la lista de Suplentes.\n\n"
        "Esto significa que ya formas parte de RUANA y tendrás prioridad para ocupar la siguiente "
        "plaza disponible en tu zona. En cuanto se libere una vacante, nuestro equipo revisará tu "
        "incorporación y te lo notificaremos.\n\n"
        "Mientras tanto, no tienes que hacer nada más. Gracias por confiar en RUANA."
    )

    def crear_aliado(self, codigo: str, nombre: str, marca: str = "",
                    oficio: str = "", codigo_postal: str = "",
                    email: str = "", telefono: str = "",
                    estado: str = "activo", score: int = 50,
                    especializaciones: Optional[List[str]] = None,
                    especializacion: Optional[str] = None,
                    descripcion_servicio: Optional[str] = None,
                    grupo_id_invitacion: Optional[int] = None) -> Dict[str, Any]:
        """Fachada Campamento Base → aliado_service.crear_aliado."""
        return aliado_service.crear_aliado(self, codigo, nombre, marca, oficio, codigo_postal, email, telefono, estado, score, especializaciones, especializacion, descripcion_servicio, grupo_id_invitacion)

    def completar_aliado_pendiente(self, codigo: str, nombre: str, marca: str = "",
                                   oficio: str = "", codigo_postal: str = "",
                                   email: str = "", telefono: str = "",
                                   estado: str = "activo", score: int = 50,
                                   especializaciones: Optional[List[str]] = None,
                                   especializacion: Optional[str] = None,
                                   descripcion_servicio: Optional[str] = None,
                                   grupo_id_invitacion: Optional[int] = None) -> Dict[str, Any]:
        """Fachada Campamento Base → aliado_service.completar_aliado_pendiente."""
        return aliado_service.completar_aliado_pendiente(self, codigo, nombre, marca, oficio, codigo_postal, email, telefono, estado, score, especializaciones, especializacion, descripcion_servicio, grupo_id_invitacion)

    def crear_aliado_seed(self, codigo: str, nombre: str, marca: str = "",
                          oficio: str = "", codigo_postal: str = "",
                          email: str = "", telefono: str = "",
                          estado: str = "activo", score: int = 50) -> Dict[str, Any]:
        """Fachada Campamento Base → aliado_service.crear_aliado_seed."""
        return aliado_service.crear_aliado_seed(self, codigo, nombre, marca, oficio, codigo_postal, email, telefono, estado, score)

    
    def obtener_aliado_por_codigo(self, codigo: str) -> Optional[Dict[str, Any]]:
        """Fachada Campamento Base → aliado_service.obtener_aliado_por_codigo."""
        return aliado_service.obtener_aliado_por_codigo(self, codigo)

    
    def obtener_aliado_por_id(self, aliado_id: int) -> Optional[Dict[str, Any]]:
        """Fachada Campamento Base → aliado_service.obtener_aliado_por_id."""
        return aliado_service.obtener_aliado_por_id(self, aliado_id)

    
    def actualizar_aliado(self, codigo: str, **kwargs) -> Dict[str, Any]:
        """Fachada Campamento Base → aliado_service.actualizar_aliado."""
        return aliado_service.actualizar_aliado(self, codigo, **kwargs)

    def listar_catalogo_servicios_aliado(self, codigo_aliado: str) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → catalogo_service.listar_catalogo_servicios_aliado."""
        return catalogo_service.listar_catalogo_servicios_aliado(self, codigo_aliado)

    def listar_catalogo_servicios_configurados(self, codigo_aliado: str) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → catalogo_service.listar_catalogo_servicios_configurados."""
        return catalogo_service.listar_catalogo_servicios_configurados(self, codigo_aliado)

    def puede_ver_catalogo_aliado(self, visor_codigo: str, objetivo_codigo: str) -> bool:
        """Fachada Campamento Base → catalogo_service.puede_ver_catalogo_aliado."""
        return catalogo_service.puede_ver_catalogo_aliado(self, visor_codigo, objetivo_codigo)

    def guardar_catalogo_servicio_aliado(
        self,
        codigo_aliado: str,
        posicion: int,
        descripcion: Optional[str],
        precio: Optional[str],
    ) -> Dict[str, Any]:
        """Fachada Campamento Base → catalogo_service.guardar_catalogo_servicio_aliado."""
        return catalogo_service.guardar_catalogo_servicio_aliado(self, codigo_aliado, posicion, descripcion, precio)

    
    # ===============================================
    # SCORE RUANA (0-500, estado derivado, límites ±10/día)
    # ===============================================
    
    @staticmethod
    def score_a_estado(score: Any) -> str:
        """Fachada Campamento Base → score_service.score_a_estado."""
        return score_service.score_a_estado(score)

    
    def _delta_score_hoy(self, cursor, codigo_aliado: str) -> int:
        """Suma de deltas aplicados hoy al aliado (para límite ±10/día)."""
        return ScoreRepo().delta_score_hoy(cursor, codigo_aliado)

    def aplicar_cambio_score(self, codigo_aliado: str, delta: int, motivo: str = "") -> Dict[str, Any]:
        """Fachada Campamento Base → score_service.aplicar_cambio_score_db."""
        return score_service.aplicar_cambio_score_db(self, codigo_aliado, delta, motivo)

    def _registrar_notificacion_cambio_score(
        self,
        cursor,
        codigo_aliado: str,
        delta_real: int,
        score_nuevo: int,
        motivo: str,
        movimiento_id: Optional[int] = None
    ) -> None:
        """Fachada: delega en ScoreRepo."""
        ScoreRepo().registrar_notificacion_cambio_score(
            cursor=cursor,
            codigo_aliado=codigo_aliado,
            delta_real=delta_real,
            score_nuevo=score_nuevo,
            motivo=motivo,
            movimiento_id=movimiento_id,
        )

    def _crear_notificacion_aliado(
        self,
        aliado_codigo: str,
        tipo: str,
        titulo: str,
        mensaje: str,
        metadata: Optional[Dict[str, Any]] = None,
        cursor=None,
    ) -> None:
        """Fachada Campamento Base → notificacion_service.crear_notificacion_aliado."""
        return notificacion_service.crear_notificacion_aliado(
            self, aliado_codigo, tipo, titulo, mensaje, metadata=metadata, cursor=cursor
        )

    def _notificar_retador_competencia_iniciada(self, retador_codigo: str, titular_codigo: str, oficio: str, grupo_id: int, competencia_id: int, duracion_dias: int, codigo_postal: str, cursor=None,) -> None:
        """Fachada Campamento Base → competencia_service._notificar_retador_competencia_iniciada."""
        return competencia_service._notificar_retador_competencia_iniciada(self, retador_codigo, titular_codigo, oficio, grupo_id, competencia_id, duracion_dias, codigo_postal, cursor)

    def _avisar_grupos_cp_competencia(self, codigo_postal: str, oficio: str, cursor,) -> None:
        """Fachada Campamento Base → competencia_service._avisar_grupos_cp_competencia."""
        return competencia_service._avisar_grupos_cp_competencia(self, codigo_postal, oficio, cursor)

    def _notificar_derrota_competencia(self, aliado_codigo: str, oficio: str, competencia_id: int, score_reinicio: int, expulsado: bool, cursor=None,) -> None:
        """Fachada Campamento Base → competencia_service._notificar_derrota_competencia."""
        return competencia_service._notificar_derrota_competencia(self, aliado_codigo, oficio, competencia_id, score_reinicio, expulsado, cursor)

    def _notificar_titular_competencia_iniciada(self, titular_codigo: str, retador_codigo: str, oficio: str, competencia_id: int, duracion_dias: int, fecha_fin_prevista: str, cursor=None,) -> None:
        """Fachada Campamento Base → competencia_service._notificar_titular_competencia_iniciada."""
        return competencia_service._notificar_titular_competencia_iniciada(self, titular_codigo, retador_codigo, oficio, competencia_id, duracion_dias, fecha_fin_prevista, cursor)

    def _notificar_ganador_competencia(self, ganador_codigo: str, oficio: str, competencia_id: int, cursor=None,) -> None:
        """Fachada Campamento Base → competencia_service._notificar_ganador_competencia."""
        return competencia_service._notificar_ganador_competencia(self, ganador_codigo, oficio, competencia_id, cursor)

    
    def _get_umbral_competencia(self) -> Optional[int]:
        """Fachada Campamento Base → competencia_service._get_umbral_competencia."""
        return competencia_service._get_umbral_competencia(self)

    def _get_duracion_competencia_dias(self) -> int:
        """Fachada Campamento Base → competencia_service._get_duracion_competencia_dias."""
        return competencia_service._get_duracion_competencia_dias(self)

    def _get_score_reinicio_competencia(self) -> int:
        """Fachada Campamento Base → competencia_service._get_score_reinicio_competencia."""
        return competencia_service._get_score_reinicio_competencia(self)

    def _get_purga_meses_sin_ganar(self) -> int:
        """Fachada Campamento Base → competencia_service._get_purga_meses_sin_ganar."""
        return competencia_service._get_purga_meses_sin_ganar(self)

    def _get_purga_score_bajo_umbral(self) -> int:
        """Fachada Campamento Base → competencia_service._get_purga_score_bajo_umbral."""
        return competencia_service._get_purga_score_bajo_umbral(self)

    def _get_apoyo_pct(self) -> float:
        """Fachada Campamento Base → pago_service._get_apoyo_pct."""
        return pago_service._get_apoyo_pct(self)

    def _get_ruana_pago_defaults(self) -> Tuple[Optional[str], Optional[str]]:
        """Fachada Campamento Base → pago_service._get_ruana_pago_defaults."""
        return pago_service._get_ruana_pago_defaults(self)

    def obtener_metodos_pago_ruana(self) -> Dict[str, Any]:
        """Fachada Campamento Base → pago_service.obtener_metodos_pago_ruana."""
        return pago_service.obtener_metodos_pago_ruana(self)

    def actualizar_metodos_pago_ruana(self, valores: Dict[str, Any], admin_codigo: Optional[str] = None) -> Dict[str, Any]:
        """Fachada Campamento Base → pago_service.actualizar_metodos_pago_ruana."""
        return pago_service.actualizar_metodos_pago_ruana(self, valores, admin_codigo)

    def _get_posponer_horas(self) -> int:
        """Fachada Campamento Base → contacto_service._get_posponer_horas."""
        return contacto_service._get_posponer_horas(self)

    # ===============================================
    # COMPETENCIA POR PERMANENCIA (orquestación, pendientes, info panel)
    # ===============================================

    def procesar_competencia_automatica(self) -> Dict[str, Any]:
        """Fachada Campamento Base → competencia_service.procesar_competencia_automatica."""
        return competencia_service.procesar_competencia_automatica(self)

    def _solicitar_competencia_por_score(self, codigo_aliado: str) -> Optional[Dict[str, Any]]:
        """Fachada Campamento Base → competencia_service._solicitar_competencia_por_score."""
        return competencia_service._solicitar_competencia_por_score(self, codigo_aliado)

    def _registrar_competencia_pendiente(self, codigo_aliado: str) -> None:
        """Fachada Campamento Base → competencia_service._registrar_competencia_pendiente."""
        return competencia_service._registrar_competencia_pendiente(self, codigo_aliado)

    def _cancelar_competencia_pendiente(self, codigo_aliado: str, motivo: str = 'score_recuperado') -> None:
        """Fachada Campamento Base → competencia_service._cancelar_competencia_pendiente."""
        return competencia_service._cancelar_competencia_pendiente(self, codigo_aliado, motivo)

    def _marcar_competencia_pendiente_resuelta(self, codigo_aliado: str, estado: str = 'iniciada') -> None:
        """Fachada Campamento Base → competencia_service._marcar_competencia_pendiente_resuelta."""
        return competencia_service._marcar_competencia_pendiente_resuelta(self, codigo_aliado, estado)

    def tiene_competencia_pendiente(self, codigo_aliado: str) -> bool:
        """Fachada Campamento Base → competencia_service.tiene_competencia_pendiente."""
        return competencia_service.tiene_competencia_pendiente(self, codigo_aliado)

    def _procesar_competencias_pendientes(
        self, codigo_postal: Optional[str] = None, oficio: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → competencia_service._procesar_competencias_pendientes."""
        return competencia_service._procesar_competencias_pendientes(self, codigo_postal, oficio)

    def aliado_en_competencia_activa(self, codigo_aliado: str) -> bool:
        """Fachada Campamento Base → competencia_service.aliado_en_competencia_activa."""
        return competencia_service.aliado_en_competencia_activa(self, codigo_aliado)

    @staticmethod
    def _dias_restantes_competencia(fecha_fin_prevista: Any) -> int:
        """Fachada Campamento Base → competencia_service._dias_restantes_competencia."""
        return competencia_service._dias_restantes_competencia(fecha_fin_prevista)

    def obtener_competencia_info_aliado(self, codigo_aliado: str) -> Optional[Dict[str, Any]]:
        """Fachada Campamento Base → competencia_service.obtener_competencia_info_aliado."""
        return competencia_service.obtener_competencia_info_aliado(self, codigo_aliado)

    def listar_competencias_pendientes_admin(self) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → competencia_service.listar_competencias_pendientes_admin."""
        return competencia_service.listar_competencias_pendientes_admin(self)

    def listar_competencias_historial_admin(self, limite: int = 50) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → competencia_service.listar_competencias_historial_admin."""
        return competencia_service.listar_competencias_historial_admin(self, limite)

    def _sanear_competencias_participantes_ausentes(self) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → competencia_service._sanear_competencias_participantes_ausentes."""
        return competencia_service._sanear_competencias_participantes_ausentes(self)

    def _cancelar_competencia_sin_participantes(self, competencia_id: int, grupo_id: int) -> None:
        """Fachada Campamento Base → competencia_service._cancelar_competencia_sin_participantes."""
        return competencia_service._cancelar_competencia_sin_participantes(self, competencia_id, grupo_id)

    def competencia_activa_para_grupo_oficio(self, grupo_id: int, oficio: str) -> Optional[Dict[str, Any]]:
        """Fachada Campamento Base → competencia_service.competencia_activa_para_grupo_oficio."""
        return competencia_service.competencia_activa_para_grupo_oficio(self, grupo_id, oficio)

    def grupo_tiene_competencia_activa(self, grupo_id: int) -> bool:
        """Fachada Campamento Base → competencia_service.grupo_tiene_competencia_activa."""
        return competencia_service.grupo_tiene_competencia_activa(self, grupo_id)

    def listar_competencias_activas_admin(self) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → competencia_service.listar_competencias_activas_admin."""
        return competencia_service.listar_competencias_activas_admin(self)

    def _buscar_retador(self, codigo_aliado_en_riesgo: str, grupo_id: int, oficio: str,
                        score_actual: int, codigo_postal: str,
                        ciudad: Optional[str] = None, provincia: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Fachada Campamento Base → competencia_service._buscar_retador."""
        return competencia_service._buscar_retador(self, codigo_aliado_en_riesgo, grupo_id, oficio, score_actual, codigo_postal, ciudad, provincia)

    def _iniciar_competencia_si_procede(self, codigo_aliado: str) -> Optional[Dict[str, Any]]:
        """Fachada Campamento Base → competencia_service._iniciar_competencia_si_procede."""
        return competencia_service._iniciar_competencia_si_procede(self, codigo_aliado)

    def aplicar_penalizacion_descendiente_en_competencia(
        self, codigo_titular: str, competencia_id: int
    ) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → score_service.aplicar_penalizacion_descendiente_en_competencia."""
        return score_service.aplicar_penalizacion_descendiente_en_competencia(self, codigo_titular, competencia_id)

    def finalizar_competencia_activas_vencidas(self) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → competencia_service.finalizar_competencia_activas_vencidas."""
        return competencia_service.finalizar_competencia_activas_vencidas(self)

    def _finalizar_una_competencia(
        self,
        competencia_id: int,
        grupo_id: int,
        aliado_original_codigo: str,
        retador_codigo: str,
        retador_grupo_anterior_id: Optional[int],
        ganador_forzado: Optional[str] = None,
        motivo_cierre: str = 'plazo_vencido',
    ) -> Dict[str, Any]:
        """Fachada Campamento Base → competencia_service._finalizar_una_competencia."""
        return competencia_service._finalizar_una_competencia(self, competencia_id, grupo_id, aliado_original_codigo, retador_codigo, retador_grupo_anterior_id, ganador_forzado, motivo_cierre)

    def obtener_avisos_grupo(self, grupo_id: int, tipo: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → grupo_service.obtener_avisos_grupo."""
        return grupo_service.obtener_avisos_grupo(self, grupo_id, tipo)

    def listar_aliados_en_pool(self) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → aliado_service.listar_aliados_en_pool."""
        return aliado_service.listar_aliados_en_pool(self)

    def _gano_competencia_ultimos_meses(self, codigo_aliado: str, meses: int) -> bool:
        """Fachada Campamento Base → competencia_service._gano_competencia_ultimos_meses."""
        return competencia_service._gano_competencia_ultimos_meses(self, codigo_aliado, meses)

    def purga_mensual(self) -> Dict[str, Any]:
        """Fachada Campamento Base → competencia_service.purga_mensual."""
        return competencia_service.purga_mensual(self)

    def aplicar_penalizaciones_contactos_abiertos(self, codigo_aliado: str) -> None:
        """Fachada Campamento Base → score_service.aplicar_penalizaciones_contactos_abiertos."""
        return score_service.aplicar_penalizaciones_contactos_abiertos(self, codigo_aliado)

    def aplicar_penalizacion_comprobante_apoyo_3d(self, codigo_aliado: str) -> None:
        """Fachada Campamento Base → score_service.aplicar_penalizacion_comprobante_apoyo_3d."""
        return score_service.aplicar_penalizacion_comprobante_apoyo_3d(self, codigo_aliado)

    # Estados de cierre adecuado: no aplicar penalización 5 (chat 48h)
    _ESTADOS_CIERRE_ADECUADO_CHAT = (
        'trabajo_cerrado', 'no_concretado', 'cerrado_no_concretado',
    )

    def aplicar_penalizacion_chat_sin_respuesta_48h(self, codigo_aliado: str) -> None:
        """Fachada Campamento Base → score_service.aplicar_penalizacion_chat_sin_respuesta_48h."""
        return score_service.aplicar_penalizacion_chat_sin_respuesta_48h(self, codigo_aliado)

    def contar_referidos_por_codigo(self, codigo_aliado: str) -> int:
        """Fachada Campamento Base → referido_service.contar_referidos_por_codigo."""
        return referido_service.contar_referidos_por_codigo(self, codigo_aliado)

    def _nodo_referido_resumen(self, codigo: str) -> Optional[Dict[str, Any]]:
        """Fachada Campamento Base → referido_service._nodo_referido_resumen."""
        return referido_service._nodo_referido_resumen(self, codigo)

    def sincronizar_referidos_completo(self) -> Dict[str, int]:
        """Fachada Campamento Base → referido_service.sincronizar_referidos_completo."""
        return referido_service.sincronizar_referidos_completo(self)

    def sincronizar_referidos_invitaciones_usadas(self) -> int:
        """Fachada Campamento Base → referido_service.sincronizar_referidos_invitaciones_usadas."""
        return referido_service.sincronizar_referidos_invitaciones_usadas(self)

    def sincronizar_referidos_invitaciones_oficio_usadas(self) -> int:
        """Fachada Campamento Base → referido_service.sincronizar_referidos_invitaciones_oficio_usadas."""
        return referido_service.sincronizar_referidos_invitaciones_oficio_usadas(self)

    def sincronizar_referidos_huerfanos_admin(self) -> int:
        """Fachada Campamento Base → referido_service.sincronizar_referidos_huerfanos_admin."""
        return referido_service.sincronizar_referidos_huerfanos_admin(self)

    def asegurar_referido_desde_invitacion(self, codigo_invitacion: str, nuevo_aliado_codigo: str) -> bool:
        """Fachada Campamento Base → referido_service.asegurar_referido_desde_invitacion."""
        return referido_service.asegurar_referido_desde_invitacion(self, codigo_invitacion, nuevo_aliado_codigo)

    def contar_total_nodos_referidos_red(self) -> int:
        """Fachada Campamento Base → referido_service.contar_total_nodos_referidos_red."""
        return referido_service.contar_total_nodos_referidos_red(self)

    def obtener_resumen_referidos_red(self) -> Dict[str, int]:
        """Fachada Campamento Base → referido_service.obtener_resumen_referidos_red."""
        return referido_service.obtener_resumen_referidos_red(self)

    def aliado_puede_ver_nodo_referidos(self, codigo_sesion: str, codigo_nodo: str) -> bool:
        """Fachada Campamento Base → referido_service.aliado_puede_ver_nodo_referidos."""
        return referido_service.aliado_puede_ver_nodo_referidos(self, codigo_sesion, codigo_nodo)

    def obtener_ruta_referidos_hacia_arriba(self, codigo: str) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → referido_service.obtener_ruta_referidos_hacia_arriba."""
        return referido_service.obtener_ruta_referidos_hacia_arriba(self, codigo)

    def buscar_en_red_referidos(self, query: str, limite: int = 20) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → referido_service.buscar_en_red_referidos."""
        return referido_service.buscar_en_red_referidos(self, query, limite)

    def listar_referidos_desde(self, desde: str) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → referido_service.listar_referidos_desde."""
        return referido_service.listar_referidos_desde(self, desde)

    def listar_nodos_raiz_referidos(self) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → referido_service.listar_nodos_raiz_referidos."""
        return referido_service.listar_nodos_raiz_referidos(self)

    def obtener_nodo_referidos(self, codigo: str) -> Optional[Dict[str, Any]]:
        """Fachada Campamento Base → referido_service.obtener_nodo_referidos."""
        return referido_service.obtener_nodo_referidos(self, codigo)

    def listar_referidos_directos(self, codigo_invitador: str) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → referido_service.listar_referidos_directos."""
        return referido_service.listar_referidos_directos(self, codigo_invitador)

    def obtener_invitador_de(self, codigo_aliado: str) -> Optional[Dict[str, Any]]:
        """Fachada Campamento Base → referido_service.obtener_invitador_de."""
        return referido_service.obtener_invitador_de(self, codigo_aliado)

    def _es_invitador_elegible_score(self, codigo: str, excluir: Optional[set] = None) -> bool:
        """Fachada Campamento Base → score_service._es_invitador_elegible_score."""
        return score_service._es_invitador_elegible_score(self, codigo, excluir)

    def ancestros_referidos_para_score(
        self,
        codigo_aliado: str,
        max_generaciones: int = 2,
        excluir: Optional[set] = None,
    ) -> List[Tuple[str, int]]:
        """Fachada Campamento Base → score_service.ancestros_referidos_para_score."""
        return score_service.ancestros_referidos_para_score(self, codigo_aliado, max_generaciones, excluir)

    def listar_raices_referidos(self) -> List[str]:
        """Fachada Campamento Base → referido_service.listar_raices_referidos."""
        return referido_service.listar_raices_referidos(self)

    def obtener_arbol_referidos(self, codigo_raiz: str, max_depth: int = 8) -> Optional[Dict[str, Any]]:
        """Fachada Campamento Base → referido_service.obtener_arbol_referidos."""
        return referido_service.obtener_arbol_referidos(self, codigo_raiz, max_depth)

    def obtener_bosques_referidos(self, max_depth: int = 5) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → referido_service.obtener_bosques_referidos."""
        return referido_service.obtener_bosques_referidos(self, max_depth)

    def obtener_o_crear_invitador_admin(self, admin_codigo: str, nombre: str = "") -> Optional[str]:
        """Fachada Campamento Base → admin_service.obtener_o_crear_invitador_admin."""
        return admin_service.obtener_o_crear_invitador_admin(self, admin_codigo, nombre)

    def _registrar_referido_campana_admin(self, codigo_campana: str, codigo_aliado: str) -> bool:
        """Fachada Campamento Base → referido_service._registrar_referido_campana_admin."""
        return referido_service._registrar_referido_campana_admin(self, codigo_campana, codigo_aliado)

    def sincronizar_referidos_campanas_admin(self) -> int:
        """Fachada Campamento Base → referido_service.sincronizar_referidos_campanas_admin."""
        return referido_service.sincronizar_referidos_campanas_admin(self)

    def _registrar_invitacion(
        self,
        codigo_invitacion: str,
        invitador_aliado_id: int,
        solicitud_id: Optional[int] = None,
    ) -> None:
        """Fachada Campamento Base → invitacion_service._registrar_invitacion."""
        return invitacion_service._registrar_invitacion(self, codigo_invitacion, invitador_aliado_id, solicitud_id)

    def marcar_solicitud_candidato_pendiente(self, solicitud_id: int, codigo_proponente: str) -> Dict[str, Any]:
        """Fachada Campamento Base → solicitud_service.marcar_solicitud_candidato_pendiente."""
        return solicitud_service.marcar_solicitud_candidato_pendiente(self, solicitud_id, codigo_proponente)

    def vincular_solicitud_a_aliado_incorporado(
        self,
        codigo_invitacion: str,
        nuevo_aliado_codigo: str,
    ) -> Dict[str, Any]:
        """Fachada Campamento Base → solicitud_service.vincular_solicitud_a_aliado_incorporado."""
        return solicitud_service.vincular_solicitud_a_aliado_incorporado(self, codigo_invitacion, nuevo_aliado_codigo)

    def crear_campana_invitacion(self, codigo: str = "", nombre: str = "",
                                  codigo_postal: str = "", max_usos: int = 100,
                                  creado_por_admin_codigo: str = "") -> Dict[str, Any]:
        """Fachada Campamento Base → invitacion_service.crear_campana_invitacion."""
        return invitacion_service.crear_campana_invitacion(self, codigo, nombre, codigo_postal, max_usos, creado_por_admin_codigo)

    def listar_campanas_invitacion(self, limite: int = 50) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → invitacion_service.listar_campanas_invitacion."""
        return invitacion_service.listar_campanas_invitacion(self, limite)

    def validar_campana_invitacion(self, codigo: str) -> Optional[Dict[str, Any]]:
        """Fachada Campamento Base → invitacion_service.validar_campana_invitacion."""
        return invitacion_service.validar_campana_invitacion(self, codigo)

    def obtener_campana_invitacion(self, codigo: str) -> Optional[Dict[str, Any]]:
        """Fachada Campamento Base → invitacion_service.obtener_campana_invitacion."""
        return invitacion_service.obtener_campana_invitacion(self, codigo)

    def consumir_campana_invitacion(self, codigo: str, nuevo_aliado_codigo: str) -> bool:
        """Fachada Campamento Base → invitacion_service.consumir_campana_invitacion."""
        return invitacion_service.consumir_campana_invitacion(self, codigo, nuevo_aliado_codigo)

    def desactivar_campana_invitacion(self, codigo: str) -> Dict[str, Any]:
        """Fachada Campamento Base → invitacion_service.desactivar_campana_invitacion."""
        return invitacion_service.desactivar_campana_invitacion(self, codigo)

    def listar_invitaciones_recientes(self, limite: int = 20) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → invitacion_service.listar_invitaciones_recientes."""
        return invitacion_service.listar_invitaciones_recientes(self, limite)

    def obtener_grupo_invitador_por_codigo_invitacion(self, codigo_invitacion: str) -> Optional[Dict[str, Any]]:
        """Fachada Campamento Base → grupo_service.obtener_grupo_invitador_por_codigo_invitacion."""
        return grupo_service.obtener_grupo_invitador_por_codigo_invitacion(self, codigo_invitacion)

    def consumir_invitacion_y_recompensar(self, codigo_invitacion: str, nuevo_aliado_codigo: str) -> bool:
        """Fachada Campamento Base → invitacion_service.consumir_invitacion_y_recompensar."""
        return invitacion_service.consumir_invitacion_y_recompensar(self, codigo_invitacion, nuevo_aliado_codigo)

    def generar_invitacion_oficio(self, codigo_aliado: str, oficio: str) -> Dict[str, Any]:
        """Fachada Campamento Base → invitacion_service.generar_invitacion_oficio."""
        return invitacion_service.generar_invitacion_oficio(self, codigo_aliado, oficio)

    def validar_invitacion_oficio(self, codigo: str) -> Optional[Dict[str, Any]]:
        """Fachada Campamento Base → invitacion_service.validar_invitacion_oficio."""
        return invitacion_service.validar_invitacion_oficio(self, codigo)

    def consumir_invitacion_oficio(self, codigo: str, nuevo_aliado_codigo: str) -> bool:
        """Fachada Campamento Base → invitacion_service.consumir_invitacion_oficio."""
        return invitacion_service.consumir_invitacion_oficio(self, codigo, nuevo_aliado_codigo)

    def listar_aliados(self, filtro_postal: str = None) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → aliado_service.listar_aliados."""
        return aliado_service.listar_aliados(self, filtro_postal)

    
    def listar_aliados_directorio_grupo(self, codigo_aliado: str) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → aliado_service.listar_aliados_directorio_grupo."""
        return aliado_service.listar_aliados_directorio_grupo(self, codigo_aliado)

    def codigo_existe(self, codigo: str) -> bool:
        """Fachada Campamento Base → aliado_service.codigo_existe."""
        return aliado_service.codigo_existe(self, codigo)

    def invitacion_codigo_existe(self, codigo: str) -> bool:
        """Fachada Campamento Base → invitacion_service.invitacion_codigo_existe."""
        return invitacion_service.invitacion_codigo_existe(self, codigo)

    def codigo_disponible_para_asignar(self, codigo: str) -> bool:
        """Fachada Campamento Base → aliado_service.codigo_disponible_para_asignar."""
        return aliado_service.codigo_disponible_para_asignar(self, codigo)

    def obtener_invitacion_pendiente(self, codigo: str) -> Optional[Dict[str, Any]]:
        """Fachada Campamento Base → invitacion_service.obtener_invitacion_pendiente."""
        return invitacion_service.obtener_invitacion_pendiente(self, codigo)

    def eliminar_aliado_placeholder(self, codigo: str) -> bool:
        """Fachada Campamento Base → invitacion_service.eliminar_aliado_placeholder."""
        return invitacion_service.eliminar_aliado_placeholder(self, codigo)

    def listar_aliados_pendiente_validacion(self) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → aliado_service.listar_aliados_pendiente_validacion."""
        return aliado_service.listar_aliados_pendiente_validacion(self)

    def listar_notificaciones_aliado(self, aliado_codigo: str, limite: int = 50) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → notificacion_service.listar_notificaciones_aliado."""
        return notificacion_service.listar_notificaciones_aliado(self, aliado_codigo, limite)

    def marcar_notificacion_leida(self, notificacion_id: int, aliado_codigo: str) -> Dict[str, Any]:
        """Fachada Campamento Base → notificacion_service.marcar_notificacion_leida."""
        return notificacion_service.marcar_notificacion_leida(self, notificacion_id, aliado_codigo)

    def marcar_todas_notificaciones_leidas(self, aliado_codigo: str) -> Dict[str, Any]:
        """Fachada Campamento Base → notificacion_service.marcar_todas_notificaciones_leidas."""
        return notificacion_service.marcar_todas_notificaciones_leidas(self, aliado_codigo)

    def _marcar_notificaciones_contacto_leidas(self, cursor, aliado_codigo: str,
                                               contacto_id: int,
                                               tipos: Optional[List[str]] = None) -> int:
        """Fachada Campamento Base → notificacion_service.marcar_notificaciones_contacto_leidas."""
        return notificacion_service.marcar_notificaciones_contacto_leidas(
            self, cursor, aliado_codigo, contacto_id, tipos
        )

    def crear_conversacion_soporte_aliado(self, aliado_codigo: str, asunto: str, mensaje: str,
                                          categoria: str = 'consulta') -> Dict[str, Any]:
        """Fachada Campamento Base → chat_service.crear_conversacion_soporte_aliado."""
        return chat_service.crear_conversacion_soporte_aliado(
            self, aliado_codigo, asunto, mensaje, categoria
        )

    def listar_conversaciones_soporte_aliado(self, aliado_codigo: str, limite: int = 50) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → chat_service.listar_conversaciones_soporte_aliado."""
        return chat_service.listar_conversaciones_soporte_aliado(self, aliado_codigo, limite)

    def listar_mensajes_soporte_aliado(self, conversacion_id: int, aliado_codigo: str) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → chat_service.listar_mensajes_soporte_aliado."""
        return chat_service.listar_mensajes_soporte_aliado(self, conversacion_id, aliado_codigo)

    def listar_mensajes_soporte_admin(self, conversacion_id: int) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → chat_service.listar_mensajes_soporte_admin."""
        return chat_service.listar_mensajes_soporte_admin(self, conversacion_id)

    def enviar_mensaje_soporte_aliado(self, conversacion_id: int, aliado_codigo: str, mensaje: str) -> Dict[str, Any]:
        """Fachada Campamento Base → chat_service.enviar_mensaje_soporte_aliado."""
        return chat_service.enviar_mensaje_soporte_aliado(self, conversacion_id, aliado_codigo, mensaje)

    def marcar_soporte_leido_aliado(self, conversacion_id: int, aliado_codigo: str) -> Dict[str, Any]:
        """Fachada Campamento Base → chat_service.marcar_soporte_leido_aliado."""
        return chat_service.marcar_soporte_leido_aliado(self, conversacion_id, aliado_codigo)

    def listar_conversaciones_soporte_admin(self, aliado_codigo: str = '', estado: str = '',
                                            solo_no_leidas: bool = False, limite: int = 100,
                                            offset: int = 0) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → admin_service.listar_conversaciones_soporte_admin."""
        return admin_service.listar_conversaciones_soporte_admin(self, aliado_codigo, estado, solo_no_leidas, limite, offset)

    def responder_soporte_admin(self, conversacion_id: int, admin_codigo: str, mensaje: str,
                                nuevo_estado: Optional[str] = None) -> Dict[str, Any]:
        """Fachada Campamento Base → admin_service.responder_soporte_admin."""
        return admin_service.responder_soporte_admin(
            self, conversacion_id, admin_codigo, mensaje, nuevo_estado
        )

    def actualizar_estado_soporte_admin(self, conversacion_id: int, nuevo_estado: str, admin_codigo: str = '') -> Dict[str, Any]:
        """Fachada Campamento Base → admin_service.actualizar_estado_soporte_admin."""
        return admin_service.actualizar_estado_soporte_admin(self, conversacion_id, nuevo_estado, admin_codigo)

    def eliminar_conversacion_soporte_admin(self, conversacion_id: int, admin_codigo: str = '') -> Dict[str, Any]:
        """Fachada Campamento Base → admin_service.eliminar_conversacion_soporte_admin."""
        return admin_service.eliminar_conversacion_soporte_admin(self, conversacion_id, admin_codigo)

    def _obtener_grupo_activacion_pendiente(self, cursor, aliado: Dict[str, Any]) -> Optional[int]:
        """Fachada Campamento Base → grupo_service._obtener_grupo_activacion_pendiente."""
        return grupo_service._obtener_grupo_activacion_pendiente(self, cursor, aliado)

    def _activar_aliado_pendiente_interno(self, cursor, aliado: Dict[str, Any]) -> Dict[str, Any]:
        """Fachada Campamento Base → aliado_service._activar_aliado_pendiente_interno."""
        return aliado_service._activar_aliado_pendiente_interno(self, cursor, aliado)

    def activar_aliado_por_id(self, aliado_id: int) -> Dict[str, Any]:
        """Fachada Campamento Base → aliado_service.activar_aliado_por_id."""
        return aliado_service.activar_aliado_por_id(self, aliado_id)

    def activar_aliado_pendiente(self, codigo: str) -> Dict[str, Any]:
        """Fachada Campamento Base → aliado_service.activar_aliado_pendiente."""
        return aliado_service.activar_aliado_pendiente(self, codigo)

    def rechazar_aliado_pendiente(self, codigo: str) -> Dict[str, Any]:
        """Fachada Campamento Base → aliado_service.rechazar_aliado_pendiente."""
        return aliado_service.rechazar_aliado_pendiente(self, codigo)

    # ===============================================
    # SOLICITUDES (tabla única solicitudes)
    # ===============================================

    def crear_solicitud_por_codigo(self, codigo: str, oficio: str, descripcion: str) -> Dict[str, Any]:
        """Fachada Campamento Base → solicitud_service.crear_solicitud_por_codigo."""
        return solicitud_service.crear_solicitud_por_codigo(self, codigo, oficio, descripcion)

    def listar_solicitudes_activas_por_codigo(self, codigo: str) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → solicitud_service.listar_solicitudes_activas_por_codigo."""
        return solicitud_service.listar_solicitudes_activas_por_codigo(self, codigo)

    def listar_solicitudes_propias_por_codigo(self, codigo: str) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → solicitud_service.listar_solicitudes_propias_por_codigo."""
        return solicitud_service.listar_solicitudes_propias_por_codigo(self, codigo)

    def listar_solicitudes_historial_grupo_por_codigo(self, codigo: str, limite: int = 50) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → solicitud_service.listar_solicitudes_historial_grupo_por_codigo."""
        return solicitud_service.listar_solicitudes_historial_grupo_por_codigo(self, codigo, limite)

    def obtener_solicitudes_grupo(self, codigo_postal: str) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → solicitud_service.obtener_solicitudes_grupo."""
        return solicitud_service.obtener_solicitudes_grupo(self, codigo_postal)

    def atender_solicitud_por_id(self, solicitud_id: int, codigo: str) -> Dict[str, Any]:
        """Fachada Campamento Base → solicitud_service.atender_solicitud_por_id."""
        return solicitud_service.atender_solicitud_por_id(self, solicitud_id, codigo)

    def marcar_solicitud_atendida_por_admin(self, solicitud_id: int, admin_codigo: str) -> Dict[str, Any]:
        """Fachada Campamento Base → solicitud_service.marcar_solicitud_atendida_por_admin."""
        return solicitud_service.marcar_solicitud_atendida_por_admin(self, solicitud_id, admin_codigo)

    def marcar_solicitud_contestada(self, solicitud_id: int, invitador_aliado_id: Optional[int] = None) -> None:
        """Fachada Campamento Base → solicitud_service.marcar_solicitud_contestada."""
        return solicitud_service.marcar_solicitud_contestada(self, solicitud_id, invitador_aliado_id)

    def listar_solicitudes_admin_todas(self) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → solicitud_service.listar_solicitudes_admin_todas."""
        return solicitud_service.listar_solicitudes_admin_todas(self)

    # ===============================================
    # OPERACIONES CONTACTOS RUANA
    # ===============================================

    # ===============================================
    # NEGOCIACIÓN GUIADA (sustituye chat libre)
    # ===============================================

    def _iniciar_negociacion_en_cursor(self, cursor, contacto_id: int, servicio: str,
                                        solicitante_codigo: str, precio_referencia: str = '') -> None:
        """Fachada Campamento Base → negociacion_service._iniciar_negociacion_en_cursor."""
        return negociacion_service._iniciar_negociacion_en_cursor(self, cursor, contacto_id, servicio, solicitante_codigo, precio_referencia)

    def _insertar_evento_negociacion(self, cursor, contacto_id: int, tipo: str, campo: str,
                                      valor: str, emisor_codigo: str, mensaje: str) -> None:
        """Fachada Campamento Base → negociacion_service._insertar_evento_negociacion."""
        return negociacion_service._insertar_evento_negociacion(self, cursor, contacto_id, tipo, campo, valor, emisor_codigo, mensaje)

    def _cargar_contacto_negociacion(self, cursor, contacto_id: int) -> Optional[Dict[str, Any]]:
        """Fachada Campamento Base → negociacion_service._cargar_contacto_negociacion."""
        return negociacion_service._cargar_contacto_negociacion(self, cursor, contacto_id)

    def listar_eventos_negociacion(self, contacto_id: int) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → negociacion_service.listar_eventos_negociacion."""
        return negociacion_service.listar_eventos_negociacion(self, contacto_id)

    def obtener_negociacion_contacto(self, contacto_id: int, codigo_aliado: str) -> Dict[str, Any]:
        """Fachada Campamento Base → negociacion_service.obtener_negociacion_contacto."""
        return negociacion_service.obtener_negociacion_contacto(self, contacto_id, codigo_aliado)

    def proponer_negociacion(self, contacto_id: int, codigo_aliado: str,
                             campo: str, valor: str) -> Dict[str, Any]:
        """Fachada Campamento Base → negociacion_service.proponer_negociacion."""
        return negociacion_service.proponer_negociacion(self, contacto_id, codigo_aliado, campo, valor)

    def proponer_propuesta_completa_negociacion(
        self, contacto_id: int, codigo_aliado: str, valores: Dict[str, str],
        precio_catalogo: str = '',
    ) -> Dict[str, Any]:
        """Fachada Campamento Base → negociacion_service.proponer_propuesta_completa_negociacion."""
        return negociacion_service.proponer_propuesta_completa_negociacion(self, contacto_id, codigo_aliado, valores, precio_catalogo)

    def contraoferta_negociacion(self, contacto_id: int, codigo_aliado: str,
                                  campo: str, valor: str, renegociar: bool = False) -> Dict[str, Any]:
        """Fachada Campamento Base → negociacion_service.contraoferta_negociacion."""
        return negociacion_service.contraoferta_negociacion(self, contacto_id, codigo_aliado, campo, valor, renegociar)

    def _parse_importe_acuerdo(self, valor: Any) -> Optional[float]:
        """Fachada Campamento Base → negociacion_service._parse_importe_acuerdo."""
        return negociacion_service._parse_importe_acuerdo(self, valor)

    def _precio_valor_desde_contacto(self, contacto: Dict[str, Any]) -> Any:
        """Fachada Campamento Base → negociacion_service._precio_valor_desde_contacto."""
        return negociacion_service._precio_valor_desde_contacto(self, contacto)

    def _importe_oficial_contacto(self, contacto: Dict[str, Any]) -> Optional[float]:
        """Fachada Campamento Base → negociacion_service._importe_oficial_contacto."""
        return negociacion_service._importe_oficial_contacto(self, contacto)

    def _construir_acuerdo_resumen_json(
        self,
        estado: Dict[str, Any],
        contacto: Dict[str, Any],
    ) -> str:
        """Fachada Campamento Base → negociacion_service._construir_acuerdo_resumen_json."""
        return negociacion_service._construir_acuerdo_resumen_json(self, estado, contacto)

    def _flags_cierre_acuerdo(self, contacto: Dict[str, Any], rol: str) -> Dict[str, Any]:
        """Fachada Campamento Base → negociacion_service._flags_cierre_acuerdo."""
        return negociacion_service._flags_cierre_acuerdo(self, contacto, rol)

    def _parse_acuerdo_resumen_campo(self, raw: Any) -> Optional[Dict[str, Any]]:
        """Fachada Campamento Base → negociacion_service._parse_acuerdo_resumen_campo."""
        return negociacion_service._parse_acuerdo_resumen_campo(self, raw)

    def _cerrar_encargo_tras_acuerdo(
        self,
        contacto_id: int,
        solicitante_codigo: str,
        precio_valor: Any,
        codigo_viewer: str,
        mensaje_acuerdo: str,
        payload_base: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Fachada Campamento Base → negociacion_service._cerrar_encargo_tras_acuerdo."""
        return negociacion_service._cerrar_encargo_tras_acuerdo(self, contacto_id, solicitante_codigo, precio_valor, codigo_viewer, mensaje_acuerdo, payload_base)

    def aceptar_negociacion(self, contacto_id: int, codigo_aliado: str, campo: str,
                            observaciones_profesional: str = '') -> Dict[str, Any]:
        """Fachada Campamento Base → negociacion_service.aceptar_negociacion."""
        return negociacion_service.aceptar_negociacion(self, contacto_id, codigo_aliado, campo, observaciones_profesional)

    def cerrar_negociacion(self, contacto_id: int, actor_codigo: str,
                           motivo: str = '') -> Dict[str, Any]:
        """Fachada Campamento Base → negociacion_service.cerrar_negociacion."""
        return negociacion_service.cerrar_negociacion(self, contacto_id, actor_codigo, motivo)

    def dismiss_resumen_acuerdo(self, contacto_id: int, actor_codigo: str) -> Dict[str, Any]:
        """Fachada Campamento Base → negociacion_service.dismiss_resumen_acuerdo."""
        return negociacion_service.dismiss_resumen_acuerdo(self, contacto_id, actor_codigo)

    # Etiquetas legibles de estado de contacto para «Mis acuerdos»
    CONTACTO_ESTADO_LABELS = {
        'iniciado': 'Iniciado',
        'aceptado': 'Aceptado',
        'en_conversacion': 'En conversación',
        'trabajo_en_progreso': 'En curso',
        'acuerdo_alcanzado': 'Acuerdo confirmado',
        'pendiente_de_pago': 'Pendiente de pago',
        'trabajo_cerrado': 'Finalizado',
        'no_concretado': 'No concretado',
        'cerrado_no_concretado': 'Cancelado',
        'importe_en_disputa': 'Importe en disputa',
    }

    def listar_acuerdos_aliado(
        self,
        codigo_aliado: str,
        limite: int = 100,
        estado: Optional[str] = None,
        desde: Optional[str] = None,
        hasta: Optional[str] = None,
        rol: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → negociacion_service.listar_acuerdos_aliado."""
        return negociacion_service.listar_acuerdos_aliado(self, codigo_aliado, limite, estado, desde, hasta, rol)

    def listar_resumenes_acuerdo_visibles(self, codigo_aliado: str) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → negociacion_service.listar_resumenes_acuerdo_visibles."""
        return negociacion_service.listar_resumenes_acuerdo_visibles(self, codigo_aliado)

    def listar_negociaciones_admin(self, limite: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → negociacion_service.listar_negociaciones_admin."""
        return negociacion_service.listar_negociaciones_admin(self, limite, offset)

    def eliminar_negociacion_admin(self, contacto_id: int, admin_codigo: str = '') -> Dict[str, Any]:
        """Fachada Campamento Base → negociacion_service.eliminar_negociacion_admin."""
        return negociacion_service.eliminar_negociacion_admin(self, contacto_id, admin_codigo)

    # Limites chat RUANA (legacy — chat libre deshabilitado; negociación guiada activa).
    CHAT_MAX_MENSAJES_TOTAL = 30
    CHAT_MAX_MENSAJES_POR_USUARIO = CHAT_MAX_MENSAJES_TOTAL
    CHAT_HORAS_VIGENCIA = 48
    REGLA5_CLIENTES_UMBRAL = 3
    REGLA5_DELTA = 3
    REGLA5_SEGUNDOS_RESPUESTA = 3600

    def crear_contacto_ruana(self, solicitante_codigo: str, profesional_codigo: str,
                             servicio: str = "", motivo_contacto: str = "",
                             es_urgente: bool = False, precio_catalogo: str = "") -> Dict[str, Any]:
        """Fachada Campamento Base → contacto_service.crear_contacto_ruana."""
        return contacto_service.crear_contacto_ruana(
            self, solicitante_codigo, profesional_codigo, servicio, motivo_contacto,
            es_urgente, precio_catalogo,
        )

    def obtener_contacto_por_id(self, contacto_id: int) -> Optional[Dict[str, Any]]:
        """Fachada Campamento Base → contacto_service.obtener_contacto_por_id."""
        return contacto_service.obtener_contacto_por_id(self, contacto_id)

    def aceptar_contacto_ruana(self, contacto_id: int, profesional_codigo: str) -> Dict[str, Any]:
        """Fachada Campamento Base → contacto_service.aceptar_contacto_ruana."""
        return contacto_service.aceptar_contacto_ruana(self, contacto_id, profesional_codigo)

    def marcar_trabajo_en_progreso(self, contacto_id: int) -> Dict[str, Any]:
        """Fachada Campamento Base → contacto_service.marcar_trabajo_en_progreso."""
        return contacto_service.marcar_trabajo_en_progreso(self, contacto_id)

    # Estados finales: no permitir transiciones (múltiples cierres, reapertura)
    _ESTADOS_FINALES_CONTACTO = (
        'trabajo_cerrado', 'no_concretado', 'cerrado_no_concretado',
        'importe_en_disputa',  # conflicto; resolución vía admin
    )

    def marcar_no_concretado(self, contacto_id: int, motivo: str = "") -> Dict[str, Any]:
        """Fachada Campamento Base → contacto_service.marcar_no_concretado."""
        return contacto_service.marcar_no_concretado(self, contacto_id, motivo)

    def marcar_cerrado_no_concretado(self, contacto_id: int, motivo: str = "",
                                     actor_codigo: str = "") -> Dict[str, Any]:
        """Fachada Campamento Base → contacto_service.marcar_cerrado_no_concretado."""
        return contacto_service.marcar_cerrado_no_concretado(
            self, contacto_id, motivo, actor_codigo,
        )

    def marcar_en_conversacion(self, contacto_id: int, actor_codigo: str = "") -> Dict[str, Any]:
        """Fachada Campamento Base → contacto_service.marcar_en_conversacion."""
        return contacto_service.marcar_en_conversacion(self, contacto_id, actor_codigo)

    def ocultar_contacto_del_panel(self, contacto_id: int, codigo_aliado: str) -> Dict[str, Any]:
        """Fachada Campamento Base → contacto_service.ocultar_contacto_del_panel."""
        return contacto_service.ocultar_contacto_del_panel(self, contacto_id, codigo_aliado)

    def listar_mensajes_contacto(self, contacto_id: int) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → chat_service.listar_mensajes_contacto."""
        return chat_service.listar_mensajes_contacto(self, contacto_id)

    def _chat_now(self) -> datetime:
        """Fachada Campamento Base → chat_service._chat_now."""
        return chat_service._chat_now(self)

    def _parse_timestamp(self, value) -> Optional[datetime]:
        """Fachada Campamento Base → chat_service._parse_timestamp."""
        return chat_service._parse_timestamp(self, value)

    def _chat_expiry_metadata(self, ref: Optional[datetime]) -> Dict[str, Any]:
        """Fachada Campamento Base → chat_service._chat_expiry_metadata."""
        return chat_service._chat_expiry_metadata(self, ref)

    def _chat_esta_expirado(self, ref: Optional[datetime]) -> bool:
        """Fachada Campamento Base → chat_service._chat_esta_expirado."""
        return chat_service._chat_esta_expirado(self, ref)

    def _chat_estado_cerrado(self) -> Dict[str, Any]:
        """Fachada Campamento Base → chat_service._chat_estado_cerrado."""
        return chat_service._chat_estado_cerrado(self)

    def _chat_referencia_ts(self, cursor, contacto_id: int) -> Optional[datetime]:
        """Fachada Campamento Base → chat_service._chat_referencia_ts."""
        return chat_service._chat_referencia_ts(self, cursor, contacto_id)

    def estado_chat_contacto(self, contacto_id: int, codigo: str) -> Dict[str, Any]:
        """Fachada Campamento Base → chat_service.estado_chat_contacto."""
        return chat_service.estado_chat_contacto(self, contacto_id, codigo)

    def enviar_mensaje_chat(self, contacto_id: int, emisor_codigo: str, texto: str) -> Dict[str, Any]:
        """Fachada Campamento Base → chat_service.enviar_mensaje_chat."""
        return chat_service.enviar_mensaje_chat(self, contacto_id, emisor_codigo, texto)

    def aplicar_penalizacion_chat_agotado_sin_resultado(
        self, contacto_id: int, codigo_aliado: str
    ) -> Optional[Dict[str, Any]]:
        """Fachada Campamento Base → score_service.aplicar_penalizacion_chat_agotado_sin_resultado."""
        return score_service.aplicar_penalizacion_chat_agotado_sin_resultado(self, contacto_id, codigo_aliado)

    def _ya_aplicado_motivo_score(self, codigo_aliado: str, motivo: str) -> bool:
        """Fachada Campamento Base → score_service._ya_aplicado_motivo_score."""
        return score_service._ya_aplicado_motivo_score(self, codigo_aliado, motivo)

    def listar_respuestas_rapidas_regla5(self, codigo_profesional: str) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → score_service.listar_respuestas_rapidas_regla5."""
        return score_service.listar_respuestas_rapidas_regla5(self, codigo_profesional)

    def evaluar_regla5_respuestas_chat(
        self,
        codigo_profesional: str,
    ) -> Optional[Tuple[str, int, str]]:
        """Fachada Campamento Base → score_service.evaluar_regla5_respuestas_chat."""
        return score_service.evaluar_regla5_respuestas_chat(self, codigo_profesional)

    def listar_contactos_recientes_con_chat(self, limite: int = 100) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → chat_service.listar_contactos_recientes_con_chat."""
        return chat_service.listar_contactos_recientes_con_chat(self, limite)

    def listar_conversaciones_admin(self, limite: int = 500, offset: int = 0) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → admin_service.listar_conversaciones_admin."""
        return admin_service.listar_conversaciones_admin(self, limite, offset)

    def listar_chat_messages(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → chat_service.listar_chat_messages."""
        return chat_service.listar_chat_messages(self, limit, offset)

    def _audit_log(self, cursor, entidad: str, entidad_id: int, accion: str, actor_tipo: str = "", actor_codigo: str = "", detalles: str = "") -> None:
        """Fachada Campamento Base → admin_service._audit_log."""
        return admin_service._audit_log(self, cursor, entidad, entidad_id, accion, actor_tipo, actor_codigo, detalles)

    def registrar_importe_contacto(self, contacto_id: int, parte: str,
                                   importe: float = None, moneda: str = "EUR",
                                   usuario: str = "",
                                   usar_precio_acordado: bool = False) -> Dict[str, Any]:
        """Fachada Campamento Base → contacto_service.registrar_importe_contacto."""
        return contacto_service.registrar_importe_contacto(
            self, contacto_id, parte, importe, moneda, usuario, usar_precio_acordado,
        )

    def obtener_metricas_contactos(self) -> Dict[str, Any]:
        """Fachada Campamento Base → admin_service.obtener_metricas_contactos."""
        return admin_service.obtener_metricas_contactos(self)

    def listar_codigos_aliados_activos(self) -> List[str]:
        """Fachada Campamento Base → admin_service.listar_codigos_aliados_activos."""
        return admin_service.listar_codigos_aliados_activos(self)

    def obtener_metricas_motor_por_aliado(self, codigo_aliado: str) -> Dict[str, Any]:
        """Fachada Campamento Base → admin_service.obtener_metricas_motor_por_aliado."""
        return admin_service.obtener_metricas_motor_por_aliado(self, codigo_aliado)

    
    def obtener_contactos_abiertos_por_codigo(self, codigo_aliado: str) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → contacto_service.obtener_contactos_abiertos_por_codigo."""
        return contacto_service.obtener_contactos_abiertos_por_codigo(self, codigo_aliado)

    def obtener_contacto_resumen(self, contacto_id: int) -> Optional[Dict[str, Any]]:
        """Fachada Campamento Base → contacto_service.obtener_contacto_resumen."""
        return contacto_service.obtener_contacto_resumen(self, contacto_id)

    def listar_contactos_conflicto_pago(self) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → pago_service.listar_contactos_conflicto_pago."""
        return pago_service.listar_contactos_conflicto_pago(self)

    def listar_payment_conflicts_admin(self) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → pago_service.listar_payment_conflicts_admin."""
        return pago_service.listar_payment_conflicts_admin(self)

    def obtener_payment_conflict_por_trabajo(self, trabajo_id: int, codigo_aliado: str) -> Optional[Dict[str, Any]]:
        """Fachada Campamento Base → pago_service.obtener_payment_conflict_por_trabajo."""
        return pago_service.obtener_payment_conflict_por_trabajo(self, trabajo_id, codigo_aliado)

    def obtener_payment_conflict(self, conflict_id: int) -> Optional[Dict[str, Any]]:
        """Fachada Campamento Base → pago_service.obtener_payment_conflict."""
        return pago_service.obtener_payment_conflict(self, conflict_id)

    def subir_prueba_conflicto(self, conflict_id: int, contratante_codigo: str, prueba_url: str) -> Dict[str, Any]:
        """Fachada Campamento Base → pago_service.subir_prueba_conflicto."""
        return pago_service.subir_prueba_conflicto(self, conflict_id, contratante_codigo, prueba_url)

    def resolver_payment_conflict_admin(self, conflict_id: int, decision: str, comentario: str,
                                        admin_codigo: str = "") -> Dict[str, Any]:
        """Fachada Campamento Base → pago_service.resolver_payment_conflict_admin."""
        return pago_service.resolver_payment_conflict_admin(self, conflict_id, decision, comentario, admin_codigo)

    def aplicar_penalizacion_disputa_perdida(
        self, contacto_id: int, decision: str
    ) -> Optional[Dict[str, Any]]:
        """Fachada Campamento Base → score_service.aplicar_penalizacion_disputa_perdida."""
        return score_service.aplicar_penalizacion_disputa_perdida(self, contacto_id, decision)

    def resolver_conflicto_pago(self, contacto_id: int, importe_valido: float,
                                admin_codigo: str = "") -> Dict[str, Any]:
        """Fachada Campamento Base → pago_service.resolver_conflicto_pago."""
        return pago_service.resolver_conflicto_pago(self, contacto_id, importe_valido, admin_codigo)

    def listar_contactos_pagos_apoyo(self) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → pago_service.listar_contactos_pagos_apoyo."""
        return pago_service.listar_contactos_pagos_apoyo(self)

    def listar_contactos_pagos_en_revision(self) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → pago_service.listar_contactos_pagos_en_revision."""
        return pago_service.listar_contactos_pagos_en_revision(self)

    ESTADOS_PAGO_PERMITIDOS_ADMIN = ('en_revision', 'pagado', 'rechazado')
    REGLA4_ENCARGOS_MES_UMBRAL = 4
    REGLA4_ENCARGOS_MES_DELTA = 3
    REGLA6_DELTA = 3
    REGLA7_DELTA = 2
    REGLA7_HORAS_LIMITE = 24
    REGLA8_DIAS_RACHA = 7
    REGLA8_DELTA = 3
    # Penalización 6: semana sin login → -1 (repetible)
    PENAL6_DIAS_SIN_ACCESO = 7
    PENAL6_DELTA = -1
    REGLA9_DELTA = 5  # Invitación por oficio usada

    def evaluar_regla7_declaracion_24h(
        self,
        contacto_id: int,
        fecha_declaracion: Optional[Any] = None,
    ) -> Optional[Tuple[str, int, str]]:
        """Fachada Campamento Base → score_service.evaluar_regla7_declaracion_24h."""
        return score_service.evaluar_regla7_declaracion_24h(self, contacto_id, fecha_declaracion)

    @staticmethod
    def _fecha_dia_servidor(fecha_val: Any) -> Optional[str]:
        """Fachada Campamento Base → score_service._fecha_dia_servidor."""
        return score_service._fecha_dia_servidor(fecha_val)

    def _dia_hoy_servidor(self) -> str:
        """Fachada Campamento Base → score_service._dia_hoy_servidor."""
        return score_service._dia_hoy_servidor(self)

    def _motivo_regla8(self, dia_fin: str) -> str:
        """Fachada Campamento Base → score_service._motivo_regla8."""
        return score_service._motivo_regla8(self, dia_fin)

    def _tiene_premio_regla8_reciente(self, codigo_aliado: str, dia_fin: str) -> bool:
        """Fachada Campamento Base → score_service._tiene_premio_regla8_reciente."""
        return score_service._tiene_premio_regla8_reciente(self, codigo_aliado, dia_fin)

    def registrar_acceso_login(
        self,
        codigo_aliado: str,
        dia: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Fachada Campamento Base → aliado_service.registrar_acceso_login."""
        return aliado_service.registrar_acceso_login(self, codigo_aliado, dia)

    def _baseline_acceso_dia(self, codigo_aliado: str) -> Optional[str]:
        """Fachada Campamento Base → score_service._baseline_acceso_dia."""
        return score_service._baseline_acceso_dia(self, codigo_aliado)

    def aplicar_penalizacion_sin_acceso_semanal(
        self,
        codigo_aliado: str,
        dia_ref: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → score_service.aplicar_penalizacion_sin_acceso_semanal."""
        return score_service.aplicar_penalizacion_sin_acceso_semanal(self, codigo_aliado, dia_ref)

    def evaluar_regla8_racha_7dias(
        self,
        codigo_aliado: str,
        dia_fin: Optional[str] = None,
    ) -> Optional[Tuple[str, int, str]]:
        """Fachada Campamento Base → score_service.evaluar_regla8_racha_7dias."""
        return score_service.evaluar_regla8_racha_7dias(self, codigo_aliado, dia_fin)

    def evaluar_regla6_urgente_mismo_dia(
        self,
        contacto_id: int,
        fecha_pago: Optional[Any] = None,
    ) -> Optional[Tuple[str, int, str]]:
        """Fachada Campamento Base → score_service.evaluar_regla6_urgente_mismo_dia."""
        return score_service.evaluar_regla6_urgente_mismo_dia(self, contacto_id, fecha_pago)

    @staticmethod
    def _anio_mes_de(fecha_val: Any) -> Optional[str]:
        """Fachada Campamento Base → score_service._anio_mes_de."""
        return score_service._anio_mes_de(fecha_val)

    def _motivo_regla4_mes(self, anio_mes: str) -> str:
        """Fachada Campamento Base → score_service._motivo_regla4_mes."""
        return score_service._motivo_regla4_mes(self, anio_mes)

    def _ya_aplicada_regla4_mes(self, codigo_aliado: str, anio_mes: str) -> bool:
        """Fachada Campamento Base → score_service._ya_aplicada_regla4_mes."""
        return score_service._ya_aplicada_regla4_mes(self, codigo_aliado, anio_mes)

    def contacto_tiene_incidencia_pago(self, contacto_id: int) -> bool:
        """Fachada Campamento Base → score_service.contacto_tiene_incidencia_pago."""
        return score_service.contacto_tiene_incidencia_pago(self, contacto_id)

    def listar_encargos_pagados_mes(self, codigo_aliado: str, anio_mes: str) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → score_service.listar_encargos_pagados_mes."""
        return score_service.listar_encargos_pagados_mes(self, codigo_aliado, anio_mes)

    def evaluar_regla4_encargos_mes_limpio(
        self,
        codigo_aliado: str,
        anio_mes: Optional[str] = None,
    ) -> Optional[Tuple[str, int, str]]:
        """Fachada Campamento Base → score_service.evaluar_regla4_encargos_mes_limpio."""
        return score_service.evaluar_regla4_encargos_mes_limpio(self, codigo_aliado, anio_mes)

    def actualizar_estado_pago_contacto(self, contacto_id: int, nuevo_estado: str,
                                        admin_codigo: str = "",
                                        motivo_rechazo: Optional[str] = None) -> Dict[str, Any]:
        """Fachada Campamento Base → pago_service.actualizar_estado_pago_contacto."""
        return pago_service.actualizar_estado_pago_contacto(self, contacto_id, nuevo_estado, admin_codigo, motivo_rechazo)

    def tiene_pagos_ruana_pendientes(self, codigo_profesional: str) -> bool:
        """Fachada Campamento Base → pago_service.tiene_pagos_ruana_pendientes."""
        return pago_service.tiene_pagos_ruana_pendientes(self, codigo_profesional)

    def impugnar_apoyo_ruana(self, contacto_id: int, profesional_codigo: str,
                             motivo: str = "") -> Dict[str, Any]:
        """Fachada Campamento Base → pago_service.impugnar_apoyo_ruana."""
        return pago_service.impugnar_apoyo_ruana(self, contacto_id, profesional_codigo, motivo)

    def listar_contactos_pago_pendiente_profesional(self, codigo_aliado: str) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → pago_service.listar_contactos_pago_pendiente_profesional."""
        return pago_service.listar_contactos_pago_pendiente_profesional(self, codigo_aliado)

    def subir_comprobante_apoyo_ruana(self, contacto_id: int, profesional_codigo: str,
                                       comprobante_ruta: str, comentario: Optional[str] = None) -> Dict[str, Any]:
        """Fachada Campamento Base → pago_service.subir_comprobante_apoyo_ruana."""
        return pago_service.subir_comprobante_apoyo_ruana(self, contacto_id, profesional_codigo, comprobante_ruta, comentario)

    def crear_checkout_stripe(self, contacto_id: int, solicitante_codigo: str) -> Dict[str, Any]:
        """Fachada Campamento Base → pago_service.crear_checkout_stripe."""
        return pago_service.crear_checkout_stripe(self, contacto_id, solicitante_codigo)

    def confirmar_trabajo_y_transferir(self, contacto_id: int, contratante_codigo: str) -> Dict[str, Any]:
        """Fachada Campamento Base → pago_service.confirmar_trabajo_y_transferir."""
        return pago_service.confirmar_trabajo_y_transferir(self, contacto_id, contratante_codigo)

    def procesar_webhook_stripe(self, payload: bytes, sig_header: str) -> Dict[str, Any]:
        """Fachada Campamento Base → pago_service.procesar_webhook_stripe."""
        return pago_service.procesar_webhook_stripe(self, payload, sig_header)

    def procesar_timeouts_sin_confirmacion_stripe(self) -> int:
        """Fachada Campamento Base → pago_service.procesar_timeouts_sin_confirmacion_stripe."""
        return pago_service.procesar_timeouts_sin_confirmacion_stripe(self)

    def iniciar_onboarding_stripe_profesional(self, codigo_profesional: str) -> Dict[str, Any]:
        """Fachada Campamento Base → pago_service.iniciar_onboarding_stripe_profesional."""
        return pago_service.iniciar_onboarding_stripe_profesional(self, codigo_profesional)

    def estado_pago_stripe_contacto(self, contacto_id: int, codigo_aliado: str) -> Dict[str, Any]:
        """Fachada Campamento Base → pago_service.estado_pago_stripe_contacto."""
        return pago_service.estado_pago_stripe_contacto(self, contacto_id, codigo_aliado)

    # ===============================================
    # UTILIDADES
    # ===============================================
    
    def exportar_a_json(self) -> Dict[str, Any]:
        """Fachada Campamento Base → admin_service.exportar_a_json."""
        return admin_service.exportar_a_json(self)

    
    # ===============================================
    # OPERACIONES EVALUACIONES (Motor RUANA)
    # ===============================================

    def guardar_evaluacion(self, codigo_aliado: str, estado: str, score: float,
                          intencion: str = "", tasa_respuesta: float = 0.0,
                          tasa_confirmacion: float = 0.0, meses_sin_trabajo: int = 0,
                          ciclos_consecutivos: int = 1, razones: list = None,
                          severidad: str = "normal") -> Dict[str, Any]:
        """Fachada Campamento Base → evaluacion_service.guardar_evaluacion."""
        return evaluacion_service.guardar_evaluacion(
            self, codigo_aliado, estado, score,
            intencion=intencion, tasa_respuesta=tasa_respuesta,
            tasa_confirmacion=tasa_confirmacion, meses_sin_trabajo=meses_sin_trabajo,
            ciclos_consecutivos=ciclos_consecutivos, razones=razones,
            severidad=severidad,
        )

    def obtener_evaluacion(self, codigo_aliado: str) -> Optional[Dict[str, Any]]:
        """Fachada Campamento Base → evaluacion_service.obtener_evaluacion."""
        return evaluacion_service.obtener_evaluacion(self, codigo_aliado)

    def listar_evaluaciones(self, estado: str = None) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → evaluacion_service.listar_evaluaciones."""
        return evaluacion_service.listar_evaluaciones(self, estado)

    def obtener_historico_evaluaciones(self, codigo_aliado: str) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → evaluacion_service.obtener_historico_evaluaciones."""
        return evaluacion_service.obtener_historico_evaluaciones(self, codigo_aliado)

    def obtener_estadisticas_evaluaciones(self) -> Dict[str, Any]:
        """Fachada Campamento Base → evaluacion_service.obtener_estadisticas_evaluaciones."""
        return evaluacion_service.obtener_estadisticas_evaluaciones(self)

    # ===============================================
    # EVENTOS DEL SISTEMA (TRAZABILIDAD)
    # ===============================================

    def _insert_evento_sistema(
        self,
        cursor,
        tipo: str,
        descripcion: str,
        actor_tipo: Optional[str] = None,
        actor_codigo: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Fachada Campamento Base → admin_service._insert_evento_sistema."""
        return admin_service._insert_evento_sistema(self, cursor, tipo, descripcion, actor_tipo, actor_codigo, metadata)

    def registrar_evento_sistema(
        self,
        tipo: str,
        descripcion: str,
        actor_tipo: Optional[str] = None,
        actor_codigo: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Fachada Campamento Base → admin_service.registrar_evento_sistema."""
        return admin_service.registrar_evento_sistema(self, tipo, descripcion, actor_tipo, actor_codigo, metadata)

    def obtener_eventos_recientes(self, limite: int = 10) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → admin_service.obtener_eventos_recientes."""
        return admin_service.obtener_eventos_recientes(self, limite)

    # ===============================================
    # ACCIONES ADMIN (FORZAR SUPLENCIA, CERRAR/ABRIR PLAZA, REPORTE, REGLAS)
    # ===============================================

    def forzar_competencia(
        self,
        grupo_id: int,
        oficio: str,
        aliado_original_codigo: str,
        retador_codigo: str,
        admin_codigo: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Fachada Campamento Base → competencia_service.forzar_competencia."""
        return competencia_service.forzar_competencia(self, grupo_id, oficio, aliado_original_codigo, retador_codigo, admin_codigo)

    def forzar_suplencia(self, grupo_id: int, oficio: str, aliado_original_codigo: str, suplente_codigo: str, admin_codigo: Optional[str] = None,) -> Dict[str, Any]:
        """Fachada Campamento Base → admin_service.forzar_suplencia."""
        return admin_service.forzar_suplencia(self, grupo_id, oficio, aliado_original_codigo, suplente_codigo, admin_codigo)

    def cerrar_oficio_grupo(self, grupo_id: int, oficio: str, admin_codigo: Optional[str] = None) -> Dict[str, Any]:
        """Fachada Campamento Base → grupo_service.cerrar_oficio_grupo."""
        return grupo_service.cerrar_oficio_grupo(self, grupo_id, oficio, admin_codigo)

    def abrir_plaza_grupo(self, grupo_id: int, oficio: str, admin_codigo: Optional[str] = None) -> Dict[str, Any]:
        """Fachada Campamento Base → grupo_service.abrir_plaza_grupo."""
        return grupo_service.abrir_plaza_grupo(self, grupo_id, oficio, admin_codigo)

    def listar_oficios_cerrados_grupo(self, grupo_id: int) -> List[str]:
        """Fachada Campamento Base → grupo_service.listar_oficios_cerrados_grupo."""
        return grupo_service.listar_oficios_cerrados_grupo(self, grupo_id)

    def generar_reporte(self) -> Dict[str, Any]:
        """Fachada Campamento Base → admin_service.generar_reporte."""
        return admin_service.generar_reporte(self)

    def cambiar_regla(self, clave: str, valor: Any, admin_codigo: Optional[str] = None) -> Dict[str, Any]:
        """Fachada Campamento Base → admin_service.cambiar_regla."""
        return admin_service.cambiar_regla(self, clave, valor, admin_codigo)

    def pausar_aliado(self, codigo_aliado: str, razon: Optional[str] = None, admin_codigo: Optional[str] = None) -> Dict[str, Any]:
        """Fachada Campamento Base → aliado_service.pausar_aliado."""
        return aliado_service.pausar_aliado(self, codigo_aliado, razon, admin_codigo)

    def _migrar_aliados_eliminados(self, conn, cursor) -> None:
        """Fachada Campamento Base → schema_service._migrar_aliados_eliminados."""
        return schema_service._migrar_aliados_eliminados(self, conn, cursor)

    def _purga_datos_aliado_completa(self, cursor, codigo: str, aliado_id: int) -> None:
        """Fachada Campamento Base → competencia_service._purga_datos_aliado_completa."""
        return competencia_service._purga_datos_aliado_completa(self, cursor, codigo, aliado_id)

    def listar_aliados_eliminados(self, limite: int = 200) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → aliado_service.listar_aliados_eliminados."""
        return aliado_service.listar_aliados_eliminados(self, limite)

    def eliminar_perfil_aliado_admin(
        self,
        codigo_aliado: str,
        motivo: Optional[str] = None,
        admin_codigo: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Fachada Campamento Base → aliado_service.eliminar_perfil_aliado_admin."""
        return aliado_service.eliminar_perfil_aliado_admin(self, codigo_aliado, motivo, admin_codigo)

    def contar_retadores_activos(self) -> int:
        """Fachada Campamento Base → admin_service.contar_retadores_activos."""
        return admin_service.contar_retadores_activos(self)

    def contar_suplentes_activos(self) -> int:
        """Fachada Campamento Base → admin_service.contar_suplentes_activos."""
        return admin_service.contar_suplentes_activos(self)

    def contar_aliados_en_espera(self) -> int:
        """Fachada Campamento Base → admin_service.contar_aliados_en_espera."""
        return admin_service.contar_aliados_en_espera(self)

    def listar_aliados_en_espera(self) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → aliado_service.listar_aliados_en_espera."""
        return aliado_service.listar_aliados_en_espera(self)

    def incorporar_aliado_espera(self, codigo: str, grupo_id: Optional[int] = None,
                                  admin_codigo: Optional[str] = None) -> Dict[str, Any]:
        """Fachada Campamento Base → aliado_service.incorporar_aliado_espera."""
        return aliado_service.incorporar_aliado_espera(self, codigo, grupo_id, admin_codigo)

    def contar_aliados_en_riesgo(self) -> int:
        """Fachada Campamento Base → admin_service.contar_aliados_en_riesgo."""
        return admin_service.contar_aliados_en_riesgo(self)

    def contar_solicitudes_activas(self) -> int:
        """Fachada Campamento Base → solicitud_service.contar_solicitudes_activas."""
        return solicitud_service.contar_solicitudes_activas(self)

    def contar_solicitudes_enviadas_contestadas(self, codigo: str) -> int:
        """Fachada Campamento Base → solicitud_service.contar_solicitudes_enviadas_contestadas."""
        return solicitud_service.contar_solicitudes_enviadas_contestadas(self, codigo)

    def contar_grupos(self) -> Dict[str, int]:
        """Fachada Campamento Base → grupo_service.contar_grupos."""
        return grupo_service.contar_grupos(self)

    def contar_oficios_ocupados(self) -> int:
        """Fachada Campamento Base → catalogo_service.contar_oficios_ocupados."""
        return catalogo_service.contar_oficios_ocupados(self)

    def obtener_stats_24h_admin(self) -> Dict[str, Any]:
        """Fachada Campamento Base → admin_service.obtener_stats_24h_admin."""
        return admin_service.obtener_stats_24h_admin(self)

    def obtener_stats_24h_panel(self) -> Dict[str, Any]:
        """Fachada Campamento Base → admin_service.obtener_stats_24h_panel."""
        return admin_service.obtener_stats_24h_panel(self)

    def obtener_movimiento_24h(self) -> Dict[str, Any]:
        """Fachada Campamento Base → admin_service.obtener_movimiento_24h."""
        return admin_service.obtener_movimiento_24h(self)

    def obtener_movimiento_24h_por_hora(self) -> Dict[str, Dict[str, int]]:
        """Fachada Campamento Base → admin_service.obtener_movimiento_24h_por_hora."""
        return admin_service.obtener_movimiento_24h_por_hora(self)

    def obtener_metricas_salud(self) -> Dict[str, Any]:
        """Fachada Campamento Base → admin_service.obtener_metricas_salud."""
        return admin_service.obtener_metricas_salud(self)

    def obtener_health_metrics_admin(self, umbral_suplentes: int = 1) -> Dict[str, Any]:
        """Fachada Campamento Base → admin_service.obtener_health_metrics_admin."""
        return admin_service.obtener_health_metrics_admin(self, umbral_suplentes)

    def limpiar_bd(self):
        """Fachada Campamento Base → admin_service.limpiar_bd."""
        return admin_service.limpiar_bd(self)

# Instancia global (singleton)
_db_instance: Optional[DBManager] = None

def get_db() -> DBManager:
    """Obtiene la instancia global del gestor de BD"""
    global _db_instance
    if _db_instance is None:
        _db_instance = DBManager()
    return _db_instance
