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
from core.repositories.score_repo import ScoreRepo


# Reexport / compat: constantes viven en core.db_constants


def _email_liberado_aliado(codigo: str) -> str:
    return f'liberado+{codigo}@ruana.invalid'


def _telefono_liberado_aliado(codigo: str) -> str:
    return f'LIBERADO-{codigo}'


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
        """Crea tablas/migraciones pendientes en Supabase/Postgres al arrancar."""
        conn = None
        try:
            conn = self._connect()
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS invitacion_campanas (
                    codigo TEXT PRIMARY KEY,
                    nombre TEXT NOT NULL,
                    codigo_postal TEXT DEFAULT '',
                    max_usos INTEGER NOT NULL,
                    usos_actuales INTEGER DEFAULT 0,
                    activo INTEGER DEFAULT 1,
                    creado_por_admin_codigo TEXT DEFAULT '',
                    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    desactivado_en TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS invitacion_campana_usos (
                    id SERIAL PRIMARY KEY,
                    codigo_campana TEXT NOT NULL REFERENCES invitacion_campanas(codigo),
                    codigo_aliado TEXT NOT NULL REFERENCES aliados(codigo),
                    usado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(codigo_campana, codigo_aliado)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS catalogo_servicios_aliado (
                    id SERIAL PRIMARY KEY,
                    aliado_codigo TEXT NOT NULL REFERENCES aliados(codigo) ON DELETE CASCADE,
                    posicion INTEGER NOT NULL CHECK(posicion BETWEEN 1 AND 10),
                    descripcion TEXT,
                    precio TEXT,
                    actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(aliado_codigo, posicion)
                )
            """)
            self._migrar_aliados_foto_perfil(conn, cursor)
            self._migrar_aliados_invitado_por(conn, cursor)
            self._migrar_invitaciones_solicitud_id(conn, cursor)
            self._migrar_solicitudes_candidato(conn, cursor)
            self._migrar_contactos_es_urgente(conn, cursor)
            self._migrar_negociacion_guiada(conn, cursor)
            self._migrar_acuerdo_cierre_bilateral(conn, cursor)
            self._migrar_importe_acordado(conn, cursor)
            self._migrar_aliado_accesos_dia(conn, cursor)
            self._migrar_centro_comunicacion_ruana(conn, cursor)
            self._migrar_aliados_eliminados(conn, cursor)
            conn.commit()
            print("[RUANA][DB] Esquema Postgres verificado (incl. foto de perfil + linaje + urgente + negociación guiada + accesos día + retador + aliados eliminados)")
        except Exception as e:
            print(f"[RUANA][DB] Error inicializando esquema Postgres: {e}")
        finally:
            if conn:
                conn.close()
    
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
        """
        Devuelve la columna vigente para el retador en `competencia`.
        Compatibilidad lectura: algunas BDs reales siguen con esquema legacy `suplente_codigo`.
        """
        try:
            if self.backend == "postgres":
                cursor.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'competencia'
                      AND column_name IN ('retador_codigo', 'suplente_codigo')
                    """
                )
                cols = {str(r[0]) for r in (cursor.fetchall() or [])}
            else:
                cursor.execute("PRAGMA table_info(competencia)")
                cols = {str(r[1]) for r in (cursor.fetchall() or [])}
        except Exception:
            cols = set()
        return "retador_codigo" if "retador_codigo" in cols else "suplente_codigo"

    def _columnas_compat_competencia(self, cursor) -> Dict[str, str]:
        """Mapea columnas de competencia entre esquema nuevo (retador_*) y legacy (suplente_*)."""
        try:
            if self.backend == "postgres":
                cursor.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'competencia'
                    """
                )
                cols = {str(r[0]) for r in (cursor.fetchall() or [])}
            else:
                cursor.execute("PRAGMA table_info(competencia)")
                cols = {str(r[1]) for r in (cursor.fetchall() or [])}
        except Exception:
            cols = set()
        return {
            "retador_codigo": "retador_codigo" if "retador_codigo" in cols else "suplente_codigo",
            "retador_grupo_anterior_id": "retador_grupo_anterior_id" if "retador_grupo_anterior_id" in cols else "suplente_grupo_anterior_id",
            "score_retador_inicio": "score_retador_inicio" if "score_retador_inicio" in cols else "score_suplente_inicio",
            "score_retador_actual": "score_retador_actual" if "score_retador_actual" in cols else "score_suplente_actual",
        }

    def _es_condicion_aliado_placeholder_sql(self) -> str:
        """Condición SQL (sin WHERE) para detectar placeholders reales de invitación."""
        return """(
            LOWER(TRIM(COALESCE(estado, ''))) = 'pendiente_completar'
        )"""

    def _purgar_placeholders_control_aliados(self, conn, cursor) -> None:
        """Compatibilidad: ya no se purgan placeholders automáticamente."""
        cursor.execute("SELECT 1 FROM migraciones WHERE nombre = 'purgar_placeholders_control_v1'")
        if cursor.fetchone():
            return
        cursor.execute("INSERT INTO migraciones (nombre) VALUES ('purgar_placeholders_control_v1')")

    def _ejecutar_purga_placeholders(self, cursor) -> int:
        """Compatibilidad: no elimina placeholders de BD."""
        return 0

    def purgar_aliados_placeholder(self) -> Dict[str, Any]:
        """Compatibilidad: no elimina filas; placeholders se ocultan en listados."""
        return {'status': 'success', 'eliminados': 0}

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
        'oficio': 'Invitación por oficio',
        'campana': 'Campaña del administrador',
        'admin_invitacion': 'Código del administrador',
        'admin': 'Código del administrador',
        'huerfano': 'Registro directo · asignado al admin',
    }

    def etiqueta_origen_referido(self, origen: str) -> str:
        return self.ORIGEN_REFERIDO_LABELS.get((origen or '').strip(), '')

    def obtener_codigo_admin_referidos(self) -> str:
        """Código del aliado sistema que actúa como raíz admin en la red."""
        codigo = self.obtener_o_crear_invitador_admin('RUANA-ADMIN')
        return codigo or 'RUANA-ADMIN'

    def _referidos_tiene_origen(self, cursor) -> bool:
        try:
            cursor.execute("PRAGMA table_info(referidos)")
            return 'origen' in [row[1] for row in cursor.fetchall()]
        except Exception:
            return False

    def _aliados_tiene_invitado_por(self, cursor) -> bool:
        try:
            cursor.execute("PRAGMA table_info(aliados)")
            return 'invitado_por_codigo' in [row[1] for row in cursor.fetchall()]
        except Exception:
            return False

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
        """Compatibilidad: delega en asignar_invitado_por (linaje en aliados + referidos)."""
        return self.asignar_invitado_por(codigo_referido, codigo_invitador, origen=origen)

    def _origen_por_invitador(self, codigo_invitador: str, default: str = 'aliado') -> str:
        invitador = self.obtener_aliado_por_codigo(codigo_invitador)
        if invitador and (invitador.get('estado') or '').strip() == 'sistema':
            return 'admin_invitacion'
        return default

    def backfill_invitado_por_linaje(self) -> Dict[str, int]:
        """Fachada Campamento Base → referido_service.backfill_invitado_por_linaje."""
        return referido_service.backfill_invitado_por_linaje(self)


    def listar_hijos_directos_linaje(self, codigo_invitador: str) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → referido_service.listar_hijos_directos_linaje."""
        return referido_service.listar_hijos_directos_linaje(self, codigo_invitador)


    def obtener_ruta_linaje_hacia_arriba(self, codigo: str) -> List[Dict[str, Any]]:
        """Cadena desde raíz hasta codigo usando invitado_por_codigo."""
        codigo = (codigo or '').strip()
        if not codigo:
            return []
        cadena = []
        actual = codigo
        visitados = set()
        while actual and actual not in visitados:
            nodo = self._nodo_referido_resumen(actual)
            if nodo:
                cadena.insert(0, nodo)
            visitados.add(actual)
            padre_codigo = None
            with self._lock:
                conn = None
                try:
                    conn = self._connect()
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT invitado_por_codigo FROM aliados WHERE codigo = ?",
                        (actual,),
                    )
                    row = cursor.fetchone()
                    if row and row[0]:
                        padre_codigo = str(row[0]).strip()
                except Exception:
                    padre_codigo = None
                finally:
                    if conn:
                        conn.close()
            if not padre_codigo:
                invitador = self.obtener_invitador_de(actual)
                padre_codigo = (invitador or {}).get('codigo')
            if not padre_codigo or padre_codigo in visitados:
                break
            actual = padre_codigo
        return cadena

    def obtener_linaje_aliado(self, codigo: str) -> Optional[Dict[str, Any]]:
        """Padre, nodo, hijos directos y ruta hacia la raíz para Control de Aliados."""
        codigo = (codigo or '').strip()
        if not codigo:
            return None
        self.backfill_invitado_por_linaje()
        nodo = self._nodo_referido_resumen(codigo)
        if not nodo:
            return None
        padre = None
        with self._lock:
            conn = None
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT invitado_por_codigo, COALESCE(invitado_origen, '') AS origen FROM aliados WHERE codigo = ?",
                    (codigo,),
                )
                row = cursor.fetchone()
                if row and (row['invitado_por_codigo'] or '').strip():
                    padre_codigo = (row['invitado_por_codigo'] or '').strip()
                    padre = self._nodo_referido_resumen(padre_codigo)
                    if padre:
                        padre['origen'] = (row['origen'] or '').strip()
                        padre['origen_label'] = self.etiqueta_origen_referido(padre['origen'])
            except Exception:
                padre = None
            finally:
                if conn:
                    conn.close()
        if not padre:
            padre = self.obtener_invitador_de(codigo)
        hijos = self.listar_hijos_directos_linaje(codigo)
        ruta = self.obtener_ruta_linaje_hacia_arriba(codigo)
        return {
            'aliado': nodo,
            'padre': padre,
            'hijos': hijos,
            'ruta': ruta,
            'hijos_count': len(hijos),
        }

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
        """Devuelve los oficios ya ocupados en el grupo (deprecado: solo devuelve el oficio si está ocupado)."""
        if not grupo_id or not oficio_principal:
            return set()
        if self.plaza_ocupada_en_grupo(grupo_id, oficio_principal):
            return {oficio_principal.strip()}
        return set()

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
        """Sugiere un CP alternativo desde la BD (misma zona: dos primeros dígitos). No usa listas abstractas."""
        if not codigo_postal or len(codigo_postal) < 2:
            return None
        prefijo = codigo_postal[:2]
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT codigo_postal FROM grupos
                    WHERE codigo_postal != ? AND codigo_postal LIKE ?
                    GROUP BY codigo_postal
                    ORDER BY codigo_postal LIMIT 1
                """, (codigo_postal, prefijo + '%'))
                row = cursor.fetchone()
                return row[0] if row else None
            except Exception:
                return None
            finally:
                conn.close()

    def obtener_o_crear_grupo(self, codigo_postal: str, ciudad: str = "", provincia: str = "") -> Dict[str, Any]:
        """
        Obtiene el primer grupo activo del CP o crea uno si no hay ninguno.
        Nombre generado: RUANA-<ID_UNICO>-<SUFIJO>. Estado por defecto: activo.
        """
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, nombre, codigo_postal, ciudad, provincia, estado, fecha_creacion FROM grupos WHERE codigo_postal = ? AND estado = 'activo' ORDER BY id LIMIT 1",
                    (codigo_postal,),
                )
                row = cursor.fetchone()
                if row:
                    return dict(row)
                nombre = self._generar_nombre_grupo(cursor)
                cursor.execute("""
                    INSERT INTO grupos (nombre, codigo_postal, ciudad, provincia, estado, fecha_creacion)
                    VALUES (?, ?, ?, ?, 'activo', CURRENT_TIMESTAMP)
                """, (nombre, codigo_postal, ciudad or None, provincia or None))
                gid = cursor.lastrowid
                conn.commit()
                cursor.execute(
                    "SELECT id, nombre, codigo_postal, ciudad, provincia, estado, fecha_creacion FROM grupos WHERE id = ?",
                    (gid,),
                )
                return dict(cursor.fetchone())
            except Exception as e:
                return {'status': 'error', 'message': str(e)}
            finally:
                conn.close()

    def obtener_grupo_por_codigo_postal(self, codigo_postal: str) -> Optional[Dict[str, Any]]:
        """Obtiene el primer grupo activo por código postal."""
        grupos = self.obtener_grupos_activos_por_cp(codigo_postal)
        return grupos[0] if grupos else None

    def obtener_grupo_por_id(self, grupo_id: int) -> Optional[Dict[str, Any]]:
        """Obtiene un grupo por su id."""
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, nombre, codigo_postal, ciudad, provincia, estado, fecha_creacion FROM grupos WHERE id = ?",
                    (grupo_id,),
                )
                row = cursor.fetchone()
                return dict(row) if row else None
            except Exception:
                return None
            finally:
                conn.close()

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
        """
        Busca otro grupo activo en el mismo CP con <3 aliados activos y sin ese oficio.
        Solo fusionar si no hay oficios repetidos. Devuelve el grupo candidato (el que podría absorber o ser absorbido).
        """
        cursor.execute(
            """SELECT id, nombre, codigo_postal, ciudad, provincia, estado, fecha_creacion
               FROM grupos WHERE codigo_postal = ? AND estado = 'activo' AND id != ? ORDER BY fecha_creacion, id""",
            (codigo_postal, grupo_id),
        )
        for row in cursor.fetchall():
            g = dict(row)
            if self._grupo_tiene_oficio(cursor, g['id'], oficio_aliado_solo):
                continue
            cursor.execute(
                "SELECT COUNT(*) FROM aliados WHERE grupo_id = ? AND estado = 'activo'",
                (g['id'],),
            )
            n = cursor.fetchone()[0] or 0
            if n < 3:
                return g
        return None

    def _fusionar_grupos_mas_antiguo_absorbe(self, conn, cursor, grupo_absorbedor_id: int, grupo_a_disolver_id: int) -> None:
        """Mueve todos los aliados activos del grupo a disolver al absorbedor y marca el grupo como disuelto. No reutiliza nombres."""
        cursor.execute(
            "UPDATE aliados SET grupo_id = ? WHERE grupo_id = ? AND estado = 'activo'",
            (grupo_absorbedor_id, grupo_a_disolver_id),
        )
        cursor.execute("UPDATE grupos SET estado = 'disuelto' WHERE id = ?", (grupo_a_disolver_id,))

    def _buscar_grupo_compatible_mismo_cp(self, cursor, codigo_postal: str, oficio: str, excluir_grupo_id: int) -> Optional[Dict[str, Any]]:
        """Grupo activo en el mismo CP que no tiene ese oficio y no es el excluido."""
        cursor.execute(
            """SELECT id, nombre, codigo_postal, ciudad, provincia, estado, fecha_creacion
               FROM grupos WHERE codigo_postal = ? AND estado = 'activo' AND id != ? ORDER BY id""",
            (codigo_postal, excluir_grupo_id),
        )
        for row in cursor.fetchall():
            g = dict(row)
            if not self._grupo_tiene_oficio(cursor, g['id'], oficio):
                return g
        return None

    def procesar_viabilidad_grupo(self, grupo_id: int) -> Dict[str, Any]:
        """Fachada Campamento Base → grupo_service.procesar_viabilidad_grupo."""
        return grupo_service.procesar_viabilidad_grupo(self, grupo_id)


    def procesar_grupos_no_viables(self) -> List[Dict[str, Any]]:
        """Ejecuta procesar_viabilidad_grupo para todos los grupos activos con exactamente 1 aliado activo."""
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute(
                    """SELECT g.id FROM grupos g
                       WHERE g.estado = 'activo'
                       AND (SELECT COUNT(*) FROM aliados a WHERE a.grupo_id = g.id AND a.estado = 'activo') = 1"""
                )
                ids = [row[0] for row in cursor.fetchall()]
                conn.close()
            except Exception:
                return []
        resultados = []
        for gid in ids:
            r = self.procesar_viabilidad_grupo(gid)
            resultados.append({'grupo_id': gid, **r})
        return resultados

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
        """Solo posiciones con descripción y precio (para elegir al contactar)."""
        return [s for s in self.listar_catalogo_servicios_aliado(codigo_aliado) if s.get('configurado')]

    def puede_ver_catalogo_aliado(self, visor_codigo: str, objetivo_codigo: str) -> bool:
        """Catálogo privado visible al propio aliado, directorio o contacto activo."""
        visor = (visor_codigo or '').strip()
        objetivo = (objetivo_codigo or '').strip()
        if not visor or not objetivo:
            return False
        if visor == objetivo:
            return True
        for aliado in self.listar_aliados_directorio_grupo(visor):
            if (aliado.get('codigo') or '').strip() == objetivo:
                return True
        with self._lock:
            conn = None
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT 1 FROM contactos_ruana
                    WHERE ((solicitante_codigo = ? AND profesional_codigo = ?)
                        OR (solicitante_codigo = ? AND profesional_codigo = ?))
                      AND estado NOT IN ('trabajo_cerrado', 'no_concretado', 'cerrado_no_concretado')
                    LIMIT 1
                    """,
                    (visor, objetivo, objetivo, visor),
                )
                return cursor.fetchone() is not None
            except Exception:
                return False
            finally:
                if conn:
                    conn.close()

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
        """
        Aplica un cambio de score respetando: score en [0, 500], máximo ±10 por día.
        Inserta en score_movimientos y actualiza aliados.score.

        Fachada Campamento Base: la mutación vive en score_service + score_repo.
        Los side-effects de competencia por umbral permanecen aquí.
        """
        if not codigo_aliado or delta == 0:
            return {'status': 'success', 'aplicado': 0, 'score_final': None}
        with self._lock:
            conn = None
            try:
                conn = self._connect()
                cursor = conn.cursor()
                result = score_service.aplicar_cambio_score(
                    cursor,
                    codigo_aliado=codigo_aliado,
                    delta=delta,
                    motivo=motivo,
                )
                if result.get('status') == 'error':
                    return {'status': 'error', 'message': result.get('message', 'error')}
                delta_real = int(result.get('aplicado') or 0)
                score_nuevo = result.get('score_final')
                score_actual = result.get('score_anterior')
                if delta_real == 0:
                    return {
                        'status': 'success',
                        'aplicado': 0,
                        'score_final': score_nuevo,
                    }
                conn.commit()
                umbral = self._get_umbral_competencia()
                if umbral is not None and score_nuevo is not None and score_actual is not None:
                    if score_nuevo < umbral:
                        if score_actual >= umbral:
                            self._solicitar_competencia_por_score(codigo_aliado)
                        elif not self.aliado_en_competencia_activa(codigo_aliado) and not self.tiene_competencia_pendiente(codigo_aliado):
                            self._solicitar_competencia_por_score(codigo_aliado)
                    elif score_nuevo >= umbral:
                        self._cancelar_competencia_pendiente(codigo_aliado, 'score_recuperado')
                return {
                    'status': 'success',
                    'aplicado': delta_real,
                    'score_final': score_nuevo,
                }
            except Exception as e:
                return {'status': 'error', 'message': str(e)}
            finally:
                if conn is not None:
                    conn.close()

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
        """Inserta una notificación persistente para un aliado."""
        codigo = (aliado_codigo or '').strip()
        if not codigo:
            return
        meta_json = json.dumps(metadata or {}, ensure_ascii=False)
        sql = """
            INSERT INTO notificaciones_aliado (aliado_codigo, tipo, titulo, mensaje, metadata, leida)
            VALUES (?, ?, ?, ?, ?, 0)
        """
        params = (codigo, tipo, titulo, mensaje, meta_json)
        try:
            if cursor is not None:
                cursor.execute(sql, params)
                return
            with self._lock:
                conn = self._connect()
                try:
                    cur = conn.cursor()
                    cur.execute(sql, params)
                    conn.commit()
                finally:
                    conn.close()
        except Exception:
            return

    def _notificar_retador_competencia_iniciada(
        self,
        retador_codigo: str,
        titular_codigo: str,
        oficio: str,
        grupo_id: int,
        competencia_id: int,
        duracion_dias: int,
        codigo_postal: str,
        cursor=None,
    ) -> None:
        """Informa al retador/suplente que entra en competencia y la regla de los 30 días."""
        oficio_txt = (oficio or '').strip()
        mensaje = (
            f"Has sido activado como retador en el CP {codigo_postal} por el oficio {oficio_txt}. "
            f"Durante {duracion_dias} días tú y el titular acumularéis score; al finalizar, "
            f"quien tenga mayor score permanece en el grupo."
        )
        self._crear_notificacion_aliado(
            retador_codigo,
            'competencia_inicio',
            'Competencia iniciada',
            mensaje,
            metadata={
                'competencia_id': competencia_id,
                'grupo_id': grupo_id,
                'oficio': oficio_txt,
                'titular_codigo': titular_codigo,
                'duracion_dias': duracion_dias,
                'codigo_postal': codigo_postal,
            },
            cursor=cursor,
        )

    def _avisar_grupos_cp_competencia(
        self,
        codigo_postal: str,
        oficio: str,
        cursor,
    ) -> None:
        """Informa a todos los grupos activos del CP que hay un oficio en competencia."""
        cp = (codigo_postal or '').strip()
        oficio_txt = (oficio or '').strip()
        if not cp or not oficio_txt or cursor is None:
            return
        texto = f"El profesional de {oficio_txt} está en competencia en este código postal."
        try:
            cursor.execute(
                "SELECT id FROM grupos WHERE codigo_postal = ? AND estado IN ('activo', 'en_competencia')",
                (cp,),
            )
            for row in cursor.fetchall():
                gid = row[0]
                cursor.execute(
                    "INSERT INTO avisos_grupo (grupo_id, tipo, texto) VALUES (?, 'competencia', ?)",
                    (gid, texto),
                )
        except Exception:
            return

    def _notificar_derrota_competencia(
        self,
        aliado_codigo: str,
        oficio: str,
        competencia_id: int,
        score_reinicio: int,
        expulsado: bool,
        cursor=None,
    ) -> None:
        """Informa al perdedor el resultado de la competencia (primera o segunda derrota)."""
        oficio_txt = (oficio or '').strip()
        if expulsado:
            titulo = 'Has perdido tu lugar en RUANA'
            mensaje = (
                'Has perdido tu lugar en RUANA tras una segunda derrota en competencia. '
                'Para volver debes registrarte de nuevo como usuario nuevo con un código de invitación nuevo.'
            )
            tipo = 'competencia_expulsion'
        else:
            titulo = 'Has perdido la competencia'
            mensaje = (
                f'Has perdido la competencia por el oficio {oficio_txt}. '
                f'Tu score se reinicia a {score_reinicio} puntos y pasas a un grupo en formación '
                f'con menos profesionales.'
            )
            tipo = 'competencia_derrota'
        self._crear_notificacion_aliado(
            aliado_codigo,
            tipo,
            titulo,
            mensaje,
            metadata={
                'competencia_id': competencia_id,
                'oficio': oficio_txt,
                'score_reinicio': score_reinicio,
                'expulsado': expulsado,
            },
            cursor=cursor,
        )

    def _notificar_titular_competencia_iniciada(
        self,
        titular_codigo: str,
        retador_codigo: str,
        oficio: str,
        competencia_id: int,
        duracion_dias: int,
        fecha_fin_prevista: str,
        cursor=None,
    ) -> None:
        """Informa al titular que ha entrado en competencia por permanencia."""
        oficio_txt = (oficio or '').strip()
        mensaje = (
            f'Has entrado en competencia por el oficio {oficio_txt}. '
            f'Durante {duracion_dias} días competirás con otro profesional; al finalizar, '
            f'quien tenga mayor score permanece en la plaza del grupo principal.'
        )
        self._crear_notificacion_aliado(
            titular_codigo,
            'competencia_titular',
            'Estás en competencia',
            mensaje,
            metadata={
                'competencia_id': competencia_id,
                'oficio': oficio_txt,
                'retador_codigo': retador_codigo,
                'duracion_dias': duracion_dias,
                'fecha_fin_prevista': fecha_fin_prevista,
            },
            cursor=cursor,
        )

    def _notificar_ganador_competencia(
        self,
        ganador_codigo: str,
        oficio: str,
        competencia_id: int,
        cursor=None,
    ) -> None:
        mensaje = (
            f'Has ganado la competencia por el oficio {(oficio or "").strip()}. '
            f'Permaneces en la plaza del grupo principal.'
        )
        self._crear_notificacion_aliado(
            ganador_codigo,
            'competencia_victoria',
            'Competencia ganada',
            mensaje,
            metadata={'competencia_id': competencia_id, 'oficio': (oficio or '').strip()},
            cursor=cursor,
        )
    
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
        """Lee posponer_horas desde config (horas que la alerta se oculta al 'Sigue en conversación'). Por defecto 24."""
        try:
            config_path = Path(__file__).resolve().parent.parent / 'config' / 'ruana_reglas_v1.json'
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return int(data.get('posponer_horas', 24))
        except Exception:
            pass
        return 24

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
        codigo = (codigo_aliado or '').strip()
        if not codigo or self.tiene_competencia_pendiente(codigo):
            return
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT a.grupo_id, a.oficio, a.score, g.codigo_postal
                    FROM aliados a
                    LEFT JOIN grupos g ON g.id = a.grupo_id
                    WHERE a.codigo = ? AND a.estado = 'activo'
                """, (codigo,))
                row = cursor.fetchone()
                if not row or not row[0] or not row[1] or not row[3]:
                    return
                umbral = self._get_umbral_competencia() or 15
                if int(row[2] or 0) >= umbral:
                    return
                cursor.execute("""
                    INSERT INTO competencia_pendiente
                    (aliado_codigo, grupo_id, oficio, codigo_postal, score_al_crear, estado)
                    VALUES (?, ?, ?, ?, ?, 'pendiente')
                """, (codigo, row[0], (row[1] or '').strip(), row[3], int(row[2] or 0)))
                conn.commit()
                try:
                    self.registrar_evento_sistema(
                        'competencia_pendiente',
                        f'Competencia pendiente de retador para {codigo}',
                        actor_tipo='sistema',
                        metadata={'aliado_codigo': codigo, 'oficio': row[1], 'codigo_postal': row[3]},
                    )
                except Exception:
                    pass
            except Exception:
                pass
            finally:
                conn.close()

    def _cancelar_competencia_pendiente(self, codigo_aliado: str, motivo: str = 'score_recuperado') -> None:
        """Fachada Campamento Base → competencia_service._cancelar_competencia_pendiente."""
        return competencia_service._cancelar_competencia_pendiente(self, codigo_aliado, motivo)


    def _marcar_competencia_pendiente_resuelta(self, codigo_aliado: str, estado: str = 'iniciada') -> None:
        codigo = (codigo_aliado or '').strip()
        if not codigo:
            return
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE competencia_pendiente SET estado = ? "
                    "WHERE aliado_codigo = ? AND estado = 'pendiente'",
                    (estado, codigo),
                )
                conn.commit()
            except Exception:
                pass
            finally:
                conn.close()

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
        """Si un participante abandona RUANA durante la competencia, el otro gana por walkover."""
        resueltos: List[Dict[str, Any]] = []
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                col_ret = self._columna_retador_competencia(cursor)
                cols = self._columnas_compat_competencia(cursor)
                col_prev = cols.get('retador_grupo_anterior_id', 'retador_grupo_anterior_id')
                cursor.execute(
                    f"SELECT id, grupo_id, oficio, aliado_original_codigo, {col_ret} AS retador_codigo, "
                    f"{col_prev} AS retador_grupo_anterior_id FROM competencia WHERE estado = 'activa'"
                )
                activas = [dict(r) for r in cursor.fetchall()]
            except Exception:
                return []
            finally:
                conn.close()
        estados_validos = ('activo',)
        for c in activas:
            tit = self.obtener_aliado_por_codigo(c.get('aliado_original_codigo'))
            ret = self.obtener_aliado_por_codigo(c.get('retador_codigo'))
            tit_ok = tit and (tit.get('estado') or '') in estados_validos
            ret_ok = ret and (ret.get('estado') or '') in estados_validos
            if tit_ok and ret_ok:
                continue
            if not tit_ok and not ret_ok:
                self._cancelar_competencia_sin_participantes(c.get('id'), c.get('grupo_id'))
                resueltos.append({'competencia_id': c.get('id'), 'motivo': 'ambos_ausentes'})
                continue
            ganador = c.get('retador_codigo') if not tit_ok else c.get('aliado_original_codigo')
            r = self._finalizar_una_competencia(
                c.get('id'), c.get('grupo_id'), c.get('aliado_original_codigo'),
                c.get('retador_codigo'), c.get('retador_grupo_anterior_id'),
                ganador_forzado=ganador, motivo_cierre='abandono_participante',
            )
            resueltos.append({'competencia_id': c.get('id'), 'ganador_codigo': ganador, **r})
        return resueltos

    def _cancelar_competencia_sin_participantes(self, competencia_id: int, grupo_id: int) -> None:
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE competencia SET estado = 'finalizada', fecha_cierre = CURRENT_TIMESTAMP WHERE id = ?",
                    (competencia_id,),
                )
                cursor.execute("UPDATE grupos SET estado = 'activo' WHERE id = ?", (grupo_id,))
                conn.commit()
            except Exception:
                pass
            finally:
                conn.close()

    def competencia_activa_para_grupo_oficio(self, grupo_id: int, oficio: str) -> Optional[Dict[str, Any]]:
        """Fachada Campamento Base → competencia_service.competencia_activa_para_grupo_oficio."""
        return competencia_service.competencia_activa_para_grupo_oficio(self, grupo_id, oficio)


    def grupo_tiene_competencia_activa(self, grupo_id: int) -> bool:
        """True si el grupo tiene al menos una competencia activa."""
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM competencia WHERE grupo_id = ? AND estado = 'activa' LIMIT 1", (grupo_id,))
                return cursor.fetchone() is not None
            except Exception:
                return False
            finally:
                conn.close()

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
        """Sincroniza referidos legacy + backfill de linaje en aliados.invitado_por_codigo."""
        campanas = self.sincronizar_referidos_campanas_admin()
        invitaciones = self.sincronizar_referidos_invitaciones_usadas()
        oficio = self.sincronizar_referidos_invitaciones_oficio_usadas()
        huerfanos = self.sincronizar_referidos_huerfanos_admin()
        linaje = self.backfill_invitado_por_linaje()
        return {
            'campanas': campanas,
            'invitaciones': invitaciones,
            'oficio': oficio,
            'huerfanos': huerfanos,
            'linaje': linaje,
        }

    def sincronizar_referidos_invitaciones_usadas(self) -> int:
        """Fachada Campamento Base → referido_service.sincronizar_referidos_invitaciones_usadas."""
        return referido_service.sincronizar_referidos_invitaciones_usadas(self)


    def sincronizar_referidos_invitaciones_oficio_usadas(self) -> int:
        """Fachada Campamento Base → referido_service.sincronizar_referidos_invitaciones_oficio_usadas."""
        return referido_service.sincronizar_referidos_invitaciones_oficio_usadas(self)


    def sincronizar_referidos_huerfanos_admin(self) -> int:
        """
        Asigna al administrador como invitador a aliados registrados sin vínculo previo.
        Garantiza que todos los aliados activos aparezcan en el árbol genealógico.
        """
        admin_codigo = self.obtener_codigo_admin_referidos()
        if not admin_codigo:
            return 0
        with self._lock:
            conn = None
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT a.codigo
                    FROM aliados a
                    WHERE COALESCE(a.estado, '') NOT IN (
                        'pendiente_completar', 'sistema', 'rechazado', 'expulsado'
                    )
                      AND a.codigo != ?
                      AND NOT EXISTS (
                          SELECT 1 FROM referidos r WHERE r.codigo_referido = a.codigo
                      )
                """, (admin_codigo,))
                huerfanos = [row['codigo'] for row in cursor.fetchall() if row and row['codigo']]
            except Exception:
                return 0
            finally:
                if conn:
                    conn.close()
        sincronizados = 0
        for codigo in huerfanos:
            if self._insert_referido(codigo, admin_codigo, 'huerfano'):
                sincronizados += 1
        return sincronizados

    def asegurar_referido_desde_invitacion(self, codigo_invitacion: str, nuevo_aliado_codigo: str) -> bool:
        """Fachada Campamento Base → referido_service.asegurar_referido_desde_invitacion."""
        return referido_service.asegurar_referido_desde_invitacion(self, codigo_invitacion, nuevo_aliado_codigo)


    def contar_total_nodos_referidos_red(self) -> int:
        """Total de aliados que participan en la red (como referido o invitador)."""
        return self.obtener_resumen_referidos_red().get('total_nodos', 0)

    def obtener_resumen_referidos_red(self) -> Dict[str, int]:
        """Fachada Campamento Base → referido_service.obtener_resumen_referidos_red."""
        return referido_service.obtener_resumen_referidos_red(self)


    def aliado_puede_ver_nodo_referidos(self, codigo_sesion: str, codigo_nodo: str) -> bool:
        """Fachada Campamento Base → referido_service.aliado_puede_ver_nodo_referidos."""
        return referido_service.aliado_puede_ver_nodo_referidos(self, codigo_sesion, codigo_nodo)


    def obtener_ruta_referidos_hacia_arriba(self, codigo: str) -> List[Dict[str, Any]]:
        """Cadena desde la raíz hasta codigo (inclusive)."""
        codigo = (codigo or '').strip()
        if not codigo:
            return []
        cadena: List[Dict[str, Any]] = []
        actual = codigo
        visitados: set = set()
        while actual and actual not in visitados:
            nodo = self._nodo_referido_resumen(actual)
            if nodo:
                cadena.insert(0, nodo)
            invitador = self.obtener_invitador_de(actual)
            if not invitador:
                break
            actual = (invitador.get('codigo') or '').strip()
            visitados.add(actual)
        return cadena

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
        """Nodo individual con metadatos para el árbol."""
        self.sincronizar_referidos_completo()
        return self._nodo_referido_resumen(codigo)

    def listar_referidos_directos(self, codigo_invitador: str) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → referido_service.listar_referidos_directos."""
        return referido_service.listar_referidos_directos(self, codigo_invitador)


    def obtener_invitador_de(self, codigo_aliado: str) -> Optional[Dict[str, Any]]:
        """Obtiene el aliado invitador de codigo_aliado, si existe en referidos."""
        codigo_aliado = (codigo_aliado or '').strip()
        if not codigo_aliado:
            return None
        with self._lock:
            conn = None
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT a.codigo, a.nombre, a.oficio, a.codigo_postal, a.marca,
                           a.estado, a.score, r.creado_en AS referido_en
                    FROM referidos r
                    JOIN aliados a ON a.codigo = r.codigo_invitador
                    WHERE r.codigo_referido = ?
                """, (codigo_aliado,))
                row = cursor.fetchone()
                if not row:
                    return None
                item = dict(row)
                item['zona'] = item.get('codigo_postal') or ''
                item['referidos_count'] = self.contar_referidos_por_codigo(item['codigo'])
                try:
                    item['score'] = float(item.get('score') or 0)
                except (TypeError, ValueError):
                    item['score'] = 0.0
                return item
            except Exception:
                return None
            finally:
                if conn:
                    conn.close()

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
        """Lista árboles raíz de toda la red de referidos."""
        self.sincronizar_referidos_completo()
        max_depth = max(1, min(int(max_depth or 8), 50))
        raices = self.listar_raices_referidos()
        bosques: List[Dict[str, Any]] = []
        for codigo in raices:
            arbol = self.obtener_arbol_referidos(codigo, max_depth=max_depth)
            if arbol:
                bosques.append(arbol)
        return bosques
    
    def obtener_o_crear_invitador_admin(self, admin_codigo: str, nombre: str = "") -> Optional[str]:
        """Fachada Campamento Base → admin_service.obtener_o_crear_invitador_admin."""
        return admin_service.obtener_o_crear_invitador_admin(self, admin_codigo, nombre)


    def _registrar_referido_campana_admin(self, codigo_campana: str, codigo_aliado: str) -> bool:
        """Registra en referidos un aliado registrado por campaña admin."""
        codigo_campana = (codigo_campana or "").strip().upper()
        codigo_aliado = (codigo_aliado or "").strip()
        if not codigo_campana or not codigo_aliado:
            return False
        campana = self.obtener_campana_invitacion(codigo_campana)
        if not campana:
            return False
        admin_codigo = (campana.get('creado_por_admin_codigo') or "").strip() or "RUANA-ADMIN"
        invitador = self.obtener_o_crear_invitador_admin(admin_codigo)
        if not invitador:
            return False
        return self._insert_referido(codigo_aliado, invitador, 'campana')

    def sincronizar_referidos_campanas_admin(self) -> int:
        """
        Backfill: crea filas referidos para usos de campaña admin que aún no están en referidos.
        """
        with self._lock:
            conn = None
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT u.codigo_aliado, u.codigo_campana, c.creado_por_admin_codigo
                    FROM invitacion_campana_usos u
                    JOIN invitacion_campanas c ON c.codigo = u.codigo_campana
                    WHERE NOT EXISTS (
                        SELECT 1 FROM referidos r WHERE r.codigo_referido = u.codigo_aliado
                    )
                """)
                pendientes = cursor.fetchall()
            except Exception:
                return 0
            finally:
                if conn:
                    conn.close()
        sincronizados = 0
        for row in pendientes:
            admin_codigo = (row['creado_por_admin_codigo'] or "").strip() or "RUANA-ADMIN"
            invitador = self.obtener_o_crear_invitador_admin(admin_codigo)
            if not invitador:
                continue
            codigo_aliado = row['codigo_aliado']
            if self._insert_referido(codigo_aliado, invitador, 'campana'):
                sincronizados += 1
        return sincronizados

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
        """
        Devuelve el grupo del invitador para un código de invitación (tabla invitaciones).
        Usado al registrarse con código "Conozco a alguien" para asignar al nuevo aliado al mismo grupo si cumple reglas.
        """
        codigo = (codigo_invitacion or '').strip()
        if not codigo:
            return None
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT invitador_aliado_id FROM invitaciones WHERE codigo = ?",
                    (codigo,)
                )
                row = cursor.fetchone()
                if not row:
                    return None
                invitador_id = row[0] if hasattr(row, '__getitem__') else row['invitador_aliado_id']
                cursor.execute(
                    "SELECT grupo_id, codigo_postal FROM aliados WHERE id = ?",
                    (invitador_id,)
                )
                r2 = cursor.fetchone()
                if not r2 or not r2[0]:
                    return None
                grupo_id = r2[0] if hasattr(r2, '__getitem__') else r2['grupo_id']
                codigo_postal = r2[1] if hasattr(r2, '__getitem__') else r2['codigo_postal']
                return {'grupo_id': grupo_id, 'codigo_postal': codigo_postal or ''}
            except Exception:
                return None
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

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
        """Lista notificaciones del aliado (ej. Apoyo RUANA) para mostrar en su panel. metadata es JSON con qr_paypal_path, bizum_num, etc."""
        codigo_norm = str(aliado_codigo or '').strip()
        if not codigo_norm:
            return []
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, aliado_codigo, tipo, titulo, mensaje, metadata, leida, creado_en
                    FROM notificaciones_aliado
                    WHERE TRIM(CAST(aliado_codigo AS TEXT)) = ?
                    ORDER BY creado_en DESC
                    LIMIT ?
                """, (codigo_norm, max(1, min(limite, 200))))
                rows = cursor.fetchall()
                out = []
                for r in rows:
                    item = dict(r)
                    if item.get('metadata'):
                        try:
                            item['metadata'] = json.loads(item['metadata'])
                        except Exception:
                            pass
                    out.append(item)
                return out
            except Exception as e:
                print(f"Error listando notificaciones aliado: {e}")
                return []
            finally:
                conn.close()

    def marcar_notificacion_leida(self, notificacion_id: int, aliado_codigo: str) -> Dict[str, Any]:
        """Marca una notificación como leída solo si pertenece al aliado."""
        codigo_norm = str(aliado_codigo or '').strip()
        if not codigo_norm:
            return {'status': 'error', 'message': 'Código requerido'}
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE notificaciones_aliado SET leida = 1 WHERE id = ? AND TRIM(CAST(aliado_codigo AS TEXT)) = ?",
                    (notificacion_id, codigo_norm)
                )
                conn.commit()
                if cursor.rowcount > 0:
                    return {'status': 'success'}
                return {'status': 'error', 'message': 'Notificación no encontrada o no pertenece al aliado'}
            except Exception as e:
                return {'status': 'error', 'message': str(e)}
            finally:
                conn.close()

    def marcar_todas_notificaciones_leidas(self, aliado_codigo: str) -> Dict[str, Any]:
        """Marca todas las notificaciones del aliado como leídas (para cerrar alertas ya resueltas)."""
        codigo_norm = str(aliado_codigo or '').strip()
        if not codigo_norm:
            return {'status': 'error', 'message': 'Código requerido'}
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE notificaciones_aliado SET leida = 1 WHERE TRIM(CAST(aliado_codigo AS TEXT)) = ? AND leida = 0",
                    (codigo_norm,)
                )
                conn.commit()
                return {'status': 'success', 'actualizadas': cursor.rowcount}
            except Exception as e:
                return {'status': 'error', 'message': str(e)}
            finally:
                conn.close()

    def _marcar_notificaciones_contacto_leidas(self, cursor, aliado_codigo: str,
                                               contacto_id: int,
                                               tipos: Optional[List[str]] = None) -> int:
        """Marca como leidas las notificaciones de un aliado ligadas a un contacto."""
        codigo_norm = str(aliado_codigo or '').strip()
        if not codigo_norm or not contacto_id:
            return 0

        condiciones = [
            "TRIM(CAST(aliado_codigo AS TEXT)) = ?",
            "leida = 0",
            "(metadata LIKE ? OR metadata LIKE ?)"
        ]
        params = [
            codigo_norm,
            f'%"contacto_id": {int(contacto_id)}%',
            f'%"contacto_id":{int(contacto_id)}%'
        ]
        tipos_norm = [str(t or '').strip() for t in (tipos or []) if str(t or '').strip()]
        if tipos_norm:
            condiciones.append("tipo IN (" + ",".join(["?"] * len(tipos_norm)) + ")")
            params.extend(tipos_norm)

        cursor.execute(
            "UPDATE notificaciones_aliado SET leida = 1 WHERE " + " AND ".join(condiciones),
            params
        )
        return cursor.rowcount

    def crear_conversacion_soporte_aliado(self, aliado_codigo: str, asunto: str, mensaje: str,
                                          categoria: str = 'consulta') -> Dict[str, Any]:
        codigo = str(aliado_codigo or '').strip()
        asunto_txt = str(asunto or '').strip()
        mensaje_txt = str(mensaje or '').strip()
        categoria_txt = str(categoria or 'consulta').strip().lower() or 'consulta'
        if not codigo:
            return {'status': 'error', 'message': 'Código de aliado requerido'}
        if not asunto_txt:
            return {'status': 'error', 'message': 'Asunto requerido'}
        if not mensaje_txt:
            return {'status': 'error', 'message': 'Mensaje requerido'}
        with self._lock:
            conn = None
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO ruana_soporte_conversaciones
                        (aliado_codigo, asunto, categoria, estado, ultimo_mensaje_preview, tiene_no_leido_admin, tiene_no_leido_aliado)
                    VALUES (?, ?, ?, 'pendiente', ?, 1, 0)
                """, (codigo, asunto_txt[:160], categoria_txt[:40], mensaje_txt[:220]))
                conv_id = cursor.lastrowid
                cursor.execute("""
                    INSERT INTO ruana_soporte_mensajes
                        (conversacion_id, emisor_tipo, emisor_codigo, mensaje, leido_por_aliado, leido_por_admin)
                    VALUES (?, 'aliado', ?, ?, 1, 0)
                """, (conv_id, codigo, mensaje_txt))
                cursor.execute("""
                    UPDATE ruana_soporte_conversaciones
                    SET ultimo_mensaje_en = CURRENT_TIMESTAMP, actualizado_en = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (conv_id,))
                conn.commit()
                return {'status': 'success', 'conversacion_id': int(conv_id)}
            except Exception as e:
                return {'status': 'error', 'message': str(e)}
            finally:
                if conn:
                    conn.close()

    def listar_conversaciones_soporte_aliado(self, aliado_codigo: str, limite: int = 50) -> List[Dict[str, Any]]:
        codigo = str(aliado_codigo or '').strip()
        if not codigo:
            return []
        with self._lock:
            conn = None
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, aliado_codigo, asunto, categoria, estado, ultimo_mensaje_preview, ultimo_mensaje_en,
                           tiene_no_leido_aliado, creado_en, actualizado_en
                    FROM ruana_soporte_conversaciones
                    WHERE TRIM(CAST(aliado_codigo AS TEXT)) = ? AND COALESCE(eliminada_por_aliado, 0) = 0
                    ORDER BY ultimo_mensaje_en DESC, id DESC
                    LIMIT ?
                """, (codigo, max(1, min(int(limite or 50), 200))))
                return [dict(r) for r in cursor.fetchall()]
            except Exception:
                return []
            finally:
                if conn:
                    conn.close()

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
        codigo = str(aliado_codigo or '').strip()
        if not codigo:
            return {'status': 'error', 'message': 'Código requerido'}
        with self._lock:
            conn = None
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE ruana_soporte_conversaciones
                    SET tiene_no_leido_aliado = 0, actualizado_en = CURRENT_TIMESTAMP
                    WHERE id = ? AND TRIM(CAST(aliado_codigo AS TEXT)) = ?
                """, (int(conversacion_id), codigo))
                cursor.execute("""
                    UPDATE ruana_soporte_mensajes
                    SET leido_por_aliado = 1
                    WHERE conversacion_id = ? AND emisor_tipo = 'admin'
                """, (int(conversacion_id),))
                conn.commit()
                return {'status': 'success'}
            except Exception as e:
                return {'status': 'error', 'message': str(e)}
            finally:
                if conn:
                    conn.close()

    def listar_conversaciones_soporte_admin(self, aliado_codigo: str = '', estado: str = '',
                                            solo_no_leidas: bool = False, limite: int = 100,
                                            offset: int = 0) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → admin_service.listar_conversaciones_soporte_admin."""
        return admin_service.listar_conversaciones_soporte_admin(self, aliado_codigo, estado, solo_no_leidas, limite, offset)


    def responder_soporte_admin(self, conversacion_id: int, admin_codigo: str, mensaje: str,
                                nuevo_estado: Optional[str] = None) -> Dict[str, Any]:
        msg = str(mensaje or '').strip()
        if not msg:
            return {'status': 'error', 'message': 'Mensaje requerido'}
        with self._lock:
            conn = None
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT aliado_codigo, asunto FROM ruana_soporte_conversaciones WHERE id = ? AND COALESCE(eliminada_por_admin, 0) = 0", (int(conversacion_id),))
                conv = cursor.fetchone()
                if not conv:
                    return {'status': 'error', 'message': 'Conversación no encontrada'}
                estado = (nuevo_estado or '').strip().lower()
                if estado not in ('pendiente', 'en_revision', 'respondido', 'cerrado', 'reabierto'):
                    estado = 'respondido'
                admin_code = (admin_codigo or '').strip() or 'admin'
                cursor.execute("""
                    INSERT INTO ruana_soporte_mensajes
                        (conversacion_id, emisor_tipo, emisor_codigo, mensaje, leido_por_aliado, leido_por_admin)
                    VALUES (?, 'admin', ?, ?, 0, 1)
                """, (int(conversacion_id), admin_code, msg))
                cursor.execute("""
                    UPDATE ruana_soporte_conversaciones
                    SET estado = ?, ultimo_mensaje_preview = ?, ultimo_mensaje_en = CURRENT_TIMESTAMP,
                        actualizado_en = CURRENT_TIMESTAMP, tiene_no_leido_aliado = 1, tiene_no_leido_admin = 0
                    WHERE id = ?
                """, (estado, msg[:220], int(conversacion_id)))
                cursor.execute("""
                    INSERT INTO notificaciones_aliado (aliado_codigo, tipo, titulo, mensaje, metadata, leida)
                    VALUES (?, 'ruana_soporte', '📩 Respuesta del equipo RUANA', ?, ?, 0)
                """, (
                    (conv['aliado_codigo'] or '').strip(),
                    f"Tu conversación #{int(conversacion_id)} tiene una respuesta nueva.",
                    json.dumps({'conversacion_id': int(conversacion_id), 'estado': estado, 'origen': 'centro_soporte'})
                ))
                conn.commit()
                return {'status': 'success'}
            except Exception as e:
                return {'status': 'error', 'message': str(e)}
            finally:
                if conn:
                    conn.close()

    def actualizar_estado_soporte_admin(self, conversacion_id: int, nuevo_estado: str, admin_codigo: str = '') -> Dict[str, Any]:
        """Fachada Campamento Base → admin_service.actualizar_estado_soporte_admin."""
        return admin_service.actualizar_estado_soporte_admin(self, conversacion_id, nuevo_estado, admin_codigo)


    def eliminar_conversacion_soporte_admin(self, conversacion_id: int, admin_codigo: str = '') -> Dict[str, Any]:
        """Fachada Campamento Base → admin_service.eliminar_conversacion_soporte_admin."""
        return admin_service.eliminar_conversacion_soporte_admin(self, conversacion_id, admin_codigo)


    def _obtener_grupo_activacion_pendiente(self, cursor, aliado: Dict[str, Any]) -> Optional[int]:
        """
        Resuelve grupo al activar un aliado pendiente_validacion.
        Prioridad: grupo del invitador (si hay plaza) → otro grupo del CP → nuevo grupo.
        """
        oficio = (aliado.get('oficio') or '').strip()
        codigo_postal = (aliado.get('codigo_postal') or '').strip()
        if not oficio or not codigo_postal:
            return None

        invitador_codigo = (aliado.get('invitado_por_codigo') or '').strip()
        if invitador_codigo:
            cursor.execute(
                "SELECT grupo_id FROM aliados WHERE codigo = ?",
                (invitador_codigo,),
            )
            inv_row = cursor.fetchone()
            if inv_row and inv_row[0]:
                grupo_id = int(inv_row[0])
                cursor.execute("SELECT estado FROM grupos WHERE id = ?", (grupo_id,))
                g_row = cursor.fetchone()
                if g_row and (g_row[0] or '').strip().lower() == 'activo':
                    if not self._grupo_tiene_oficio(cursor, grupo_id, oficio):
                        return grupo_id

        cursor.execute(
            """SELECT id FROM grupos
               WHERE codigo_postal = ? AND estado = 'activo'
               ORDER BY id""",
            (codigo_postal,),
        )
        for row in cursor.fetchall():
            grupo_id = int(row[0])
            if not self._grupo_tiene_oficio(cursor, grupo_id, oficio):
                return grupo_id

        cursor.execute(
            "SELECT COUNT(*) FROM grupos WHERE codigo_postal = ? AND estado = 'activo'",
            (codigo_postal,),
        )
        n_grupos = cursor.fetchone()[0] or 0
        if n_grupos < MAX_GRUPOS_POR_CP:
            nombre = self._generar_nombre_grupo(cursor)
            cursor.execute(
                """INSERT INTO grupos (nombre, codigo_postal, estado, fecha_creacion)
                   VALUES (?, ?, 'activo', CURRENT_TIMESTAMP)""",
                (nombre, codigo_postal),
            )
            return int(cursor.lastrowid)
        return None

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
        """Rechaza un aliado en pendiente_validacion: estado pasa a rechazado. No podrá entrar al panel."""
        codigo = (codigo or '').strip()
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute(
                    f"""
                    UPDATE aliados
                    SET estado = 'rechazado',
                        email = ?,
                        telefono = ?,
                        qr_paypal_path = NULL,
                        bizum_num = NULL,
                        {ALIADO_FOTO_PERFIL_COLUMN} = NULL,
                        actualizado_en = CURRENT_TIMESTAMP
                    WHERE codigo = ? AND estado = 'pendiente_validacion'
                    """,
                    (
                        _email_liberado_aliado(codigo),
                        _telefono_liberado_aliado(codigo),
                        codigo,
                    ),
                )
                conn.commit()
                if cursor.rowcount > 0:
                    return {'status': 'success', 'message': f'Aliado {codigo} rechazado. No podrá acceder al panel.'}
                return {'status': 'error', 'message': f'Aliado {codigo} no encontrado o no está pendiente de validación'}
            except Exception as e:
                return {'status': 'error', 'message': str(e)}
            finally:
                conn.close()

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
        """Extrae un importe numérico > 0 del valor acordado en negociación (p. ej. «150», «150€»)."""
        if valor is None:
            return None
        if isinstance(valor, (int, float)) and not isinstance(valor, bool):
            return float(valor) if float(valor) > 0 else None
        texto = str(valor).strip()
        if not texto:
            return None
        texto = texto.replace(',', '.').replace('€', ' ').replace('EUR', ' ').replace('eur', ' ')
        match = re.search(r'(\d+(?:\.\d+)?)', texto)
        if not match:
            return None
        try:
            importe = float(match.group(1))
        except (TypeError, ValueError):
            return None
        return importe if importe > 0 else None

    def _precio_valor_desde_contacto(self, contacto: Dict[str, Any]) -> Any:
        """Fachada Campamento Base → negociacion_service._precio_valor_desde_contacto."""
        return negociacion_service._precio_valor_desde_contacto(self, contacto)


    def _importe_oficial_contacto(self, contacto: Dict[str, Any]) -> Optional[float]:
        """Importe oficial del encargo (precio negociado)."""
        return self._parse_importe_acuerdo(self._precio_valor_desde_contacto(contacto))

    def _construir_acuerdo_resumen_json(
        self,
        estado: Dict[str, Any],
        contacto: Dict[str, Any],
    ) -> str:
        """Fachada Campamento Base → negociacion_service._construir_acuerdo_resumen_json."""
        return negociacion_service._construir_acuerdo_resumen_json(self, estado, contacto)


    def _flags_cierre_acuerdo(self, contacto: Dict[str, Any], rol: str) -> Dict[str, Any]:
        conf_sol = bool(contacto.get('cierre_confirmado_solicitante_en'))
        conf_pro = bool(contacto.get('cierre_confirmado_profesional_en'))
        yo = conf_sol if rol == 'solicitante' else conf_pro
        dismiss = bool(
            contacto.get('resumen_dismiss_solicitante_en')
            if rol == 'solicitante'
            else contacto.get('resumen_dismiss_profesional_en')
        )
        return {
            'cierre_confirmado_solicitante': conf_sol,
            'cierre_confirmado_profesional': conf_pro,
            'yo_confirme_cierre': yo,
            'ambos_confirmaron_cierre': conf_sol and conf_pro,
            'resumen_dismissed': dismiss,
        }

    def _parse_acuerdo_resumen_campo(self, raw: Any) -> Optional[Dict[str, Any]]:
        if raw is None or raw == '':
            return None
        if isinstance(raw, dict):
            return raw
        try:
            data = json.loads(raw) if isinstance(raw, str) else None
            return data if isinstance(data, dict) else None
        except Exception:
            return None

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
        """
        Marca el contacto como 'no_concretado' (compatibilidad legacy).
        Ver marcar_cerrado_no_concretado para el flujo con -1 y audit.
        """
        return self.marcar_cerrado_no_concretado(contacto_id, motivo=motivo)

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
        """Ahora UTC naive para comparar timestamps SQLite y Postgres normalizados."""
        return datetime.now(timezone.utc).replace(tzinfo=None)

    def _parse_timestamp(self, value) -> Optional[datetime]:
        """Convierte valor SQLite (str/datetime) a datetime para cálculos de vigencia."""
        if not value:
            return None
        try:
            dt = None
            if isinstance(value, datetime):
                dt = value
            elif isinstance(value, str):
                raw = value.strip()
                if not raw:
                    return None
                normalized = raw.replace("Z", "+00:00")
                try:
                    dt = datetime.fromisoformat(normalized)
                except ValueError:
                    dt = datetime.strptime(raw[:19].replace("T", " "), '%Y-%m-%d %H:%M:%S')
            if not isinstance(dt, datetime):
                return None
            if dt.tzinfo is not None:
                return dt.astimezone(timezone.utc).replace(tzinfo=None)
            return dt
        except Exception:
            return None

    def _chat_expiry_metadata(self, ref: Optional[datetime]) -> Dict[str, Any]:
        """Fachada Campamento Base → chat_service._chat_expiry_metadata."""
        return chat_service._chat_expiry_metadata(self, ref)


    def _chat_esta_expirado(self, ref: Optional[datetime]) -> bool:
        """Fachada Campamento Base → chat_service._chat_esta_expirado."""
        return chat_service._chat_esta_expirado(self, ref)


    def _chat_estado_cerrado(self) -> Dict[str, Any]:
        return {
            'chat_expirado': True,
            'mensajes_restantes': 0,
            'chat_referencia_en': None,
            'chat_expira_en': None,
            'chat_horas_restantes': 0,
            'chat_horas_vigencia': self.CHAT_HORAS_VIGENCIA,
            'chat_max_mensajes': self.CHAT_MAX_MENSAJES_TOTAL,
        }

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


    def _audit_log(self, cursor, entidad: str, entidad_id: int, accion: str,
                   actor_tipo: str = "", actor_codigo: str = "", detalles: str = "") -> None:
        """Registra una acción en audit_log."""
        cursor.execute("""
            INSERT INTO audit_log (entidad, entidad_id, accion, actor_tipo, actor_codigo, detalles)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (entidad, entidad_id, accion, actor_tipo or None, actor_codigo or None, detalles or None))

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
        """Lista los códigos de todos los aliados con estado activo (para motor de evaluación)."""
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT codigo FROM aliados WHERE estado = 'activo' AND codigo IS NOT NULL AND TRIM(codigo) != '' ORDER BY id"
                )
                return [row[0] for row in cursor.fetchall()]
            except Exception:
                return []
            finally:
                conn.close()

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
        """Normaliza timestamp/fecha a 'YYYY-MM-DD' (calendario del servidor)."""
        if fecha_val is None:
            return None
        if isinstance(fecha_val, datetime):
            dt = fecha_val
            if dt.tzinfo is not None:
                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
            return dt.strftime('%Y-%m-%d')
        s = str(fecha_val).strip()
        if len(s) >= 10 and s[4] == '-' and s[7] == '-':
            return s[:10]
        return None

    def _dia_hoy_servidor(self) -> str:
        """Fachada Campamento Base → score_service._dia_hoy_servidor."""
        return score_service._dia_hoy_servidor(self)


    def _motivo_regla8(self, dia_fin: str) -> str:
        return f'regla8_racha_7dias_{dia_fin}'

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
        """Último día de login o fecha de alta (YYYY-MM-DD)."""
        codigo_aliado = (codigo_aliado or '').strip()
        if not codigo_aliado:
            return None
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT MAX(dia) FROM aliado_accesos_dia WHERE codigo_aliado = ?
                    """,
                    (codigo_aliado,),
                )
                row = cursor.fetchone()
                ultimo = (row[0] if row else None) or None
                if ultimo and len(str(ultimo)) >= 10:
                    return str(ultimo)[:10]
                cursor.execute(
                    "SELECT creado_en FROM aliados WHERE codigo = ?",
                    (codigo_aliado,),
                )
                row = cursor.fetchone()
                if not row or not row[0]:
                    return None
                return self._fecha_dia_servidor(row[0]) or self._dia_hoy_servidor()
            except Exception:
                return None
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

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
        """Normaliza timestamp/fecha a 'YYYY-MM'."""
        if fecha_val is None:
            return None
        if isinstance(fecha_val, datetime):
            return fecha_val.strftime('%Y-%m')
        s = str(fecha_val).strip()
        if len(s) >= 7 and s[4] == '-':
            return s[:7]
        return None

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


    # ===============================================
    # UTILIDADES
    # ===============================================
    
    def exportar_a_json(self) -> Dict[str, Any]:
        """Exporta toda la BD a JSON (para respaldos o migraciones)"""
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                # Obtener todas las tablas
                cursor.execute("SELECT * FROM aliados")
                aliados = [dict(row) for row in cursor.fetchall()]
                
                cursor.execute("SELECT * FROM grupos")
                grupos = [dict(row) for row in cursor.fetchall()]
                
                cursor.execute("SELECT * FROM solicitudes")
                solicitudes = [dict(row) for row in cursor.fetchall()]
                
                return {
                    'aliados': aliados,
                    'grupos': grupos,
                    'solicitudes': solicitudes,
                    'exportado_en': datetime.now().isoformat()
                }
                
            except Exception as e:
                print(f"Error exportando: {e}")
                return {}
            finally:
                conn.close()
    
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


    def forzar_suplencia(
        self,
        grupo_id: int,
        oficio: str,
        aliado_original_codigo: str,
        suplente_codigo: str,
        admin_codigo: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Alias de forzar_competencia para compatibilidad con código existente."""
        return self.forzar_competencia(grupo_id, oficio, aliado_original_codigo, suplente_codigo, admin_codigo=admin_codigo)

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
        """Genera un resumen para el panel admin (conteos y datos agregados)."""
        conn = None
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM aliados")
                total_aliados = cursor.fetchone()[0] or 0
                cursor.execute("SELECT COUNT(*) FROM aliados WHERE estado = 'activo'")
                aliados_activos = cursor.fetchone()[0] or 0
                cursor.execute("SELECT COUNT(*) FROM solicitudes")
                total_solicitudes = cursor.fetchone()[0] or 0
                cursor.execute("SELECT COUNT(*) FROM contactos_ruana")
                total_contactos = cursor.fetchone()[0] or 0
                cursor.execute("SELECT COUNT(*) FROM grupos WHERE estado = 'activo'")
                grupos_activos = cursor.fetchone()[0] or 0
                cursor.execute("SELECT COUNT(*) FROM competencia WHERE estado = 'activa'")
                competencias_activas = cursor.fetchone()[0] or 0
                cursor.execute("SELECT COUNT(*) FROM grupo_oficio_cerrado")
                plazas_cerradas = cursor.fetchone()[0] or 0
                reporte = {
                    'total_aliados': total_aliados,
                    'aliados_activos': aliados_activos,
                    'total_solicitudes': total_solicitudes,
                    'total_contactos': total_contactos,
                    'grupos_activos': grupos_activos,
                    'competencias_activas': competencias_activas,
                    'plazas_cerradas': plazas_cerradas,
                    'generado_en': datetime.now().isoformat(),
                }
                try:
                    self.registrar_evento_sistema('generar_reporte', 'Reporte administrativo generado', actor_tipo='admin', metadata=reporte)
                except Exception:
                    pass
                return {'status': 'success', 'reporte': reporte}
            except Exception as e:
                return {'status': 'error', 'message': str(e)}
            finally:
                try:
                    if conn is not None:
                        conn.close()
                except Exception:
                    pass

    def cambiar_regla(self, clave: str, valor: Any, admin_codigo: Optional[str] = None) -> Dict[str, Any]:
        """
        Actualiza una clave en config/ruana_reglas_v1.json.
        Claves permitidas: umbral_competencia, duracion_competencia_dias, purga_mensual_meses_sin_ganar, purga_score_bajo_umbral, apoyo_pct, posponer_horas.
        """
        permitidas = {'umbral_competencia', 'duracion_competencia_dias', 'purga_mensual_meses_sin_ganar', 'purga_score_bajo_umbral', 'apoyo_pct', 'posponer_horas'}
        if clave not in permitidas:
            return {'status': 'error', 'message': f'Clave no permitida. Permitidas: {", ".join(sorted(permitidas))}'}
        try:
            config_path = Path(__file__).resolve().parent.parent / 'config' / 'ruana_reglas_v1.json'
            if not config_path.exists():
                return {'status': 'error', 'message': 'Archivo de reglas no encontrado'}
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if clave == 'umbral_competencia':
                data[clave] = int(valor)
            elif clave == 'duracion_competencia_dias':
                data[clave] = int(valor)
            elif clave == 'purga_mensual_meses_sin_ganar':
                data[clave] = int(valor)
            elif clave == 'purga_score_bajo_umbral':
                data[clave] = int(valor)
            elif clave == 'apoyo_pct':
                data[clave] = float(valor)
            elif clave == 'posponer_horas':
                data[clave] = int(valor)
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=0, ensure_ascii=False)
            self.registrar_evento_sistema(
                'cambiar_reglas',
                f'Regla actualizada: {clave} = {valor}',
                actor_tipo='admin',
                actor_codigo=admin_codigo,
                metadata={'clave': clave, 'valor': valor},
            )
            return {'status': 'success', 'message': f'Regla {clave} actualizada', 'clave': clave, 'valor': data[clave]}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

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
        """Cuenta aliados que están actuando como retador en una competencia activa."""
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                col_retador = self._columna_retador_competencia(cursor)
                cursor.execute(
                    f"SELECT COUNT(DISTINCT {col_retador}) FROM competencia WHERE estado = 'activa'"
                )
                return cursor.fetchone()[0] or 0
            except Exception:
                return 0
            finally:
                conn.close()

    def contar_suplentes_activos(self) -> int:
        """Alias de contar_retadores_activos para compatibilidad."""
        return self.contar_retadores_activos()

    def contar_aliados_en_espera(self) -> int:
        """Cuenta aliados en lista de espera (estado en_espera)."""
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM aliados WHERE estado = 'en_espera'")
                return cursor.fetchone()[0] or 0
            except Exception:
                return 0
            finally:
                conn.close()

    def listar_aliados_en_espera(self) -> List[Dict[str, Any]]:
        """Fachada Campamento Base → aliado_service.listar_aliados_en_espera."""
        return aliado_service.listar_aliados_en_espera(self)


    def incorporar_aliado_espera(self, codigo: str, grupo_id: Optional[int] = None,
                                  admin_codigo: Optional[str] = None) -> Dict[str, Any]:
        """Fachada Campamento Base → aliado_service.incorporar_aliado_espera."""
        return aliado_service.incorporar_aliado_espera(self, codigo, grupo_id, admin_codigo)


    def contar_aliados_en_riesgo(self) -> int:
        """Cuenta aliados activos con estado RUANA 'EN RIESGO' (15 <= score < 50)."""
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT COUNT(*) FROM aliados
                    WHERE estado = 'activo' AND score IS NOT NULL
                    AND CAST(score AS INTEGER) >= 15 AND CAST(score AS INTEGER) < 50
                """)
                return cursor.fetchone()[0] or 0
            except Exception:
                return 0
            finally:
                conn.close()

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
        """⚠️ PELIGRO: Limpia completamente la BD (solo para testing)"""
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                
                cursor.execute("DELETE FROM evaluaciones_historico")
                cursor.execute("DELETE FROM evaluaciones")
                cursor.execute("DELETE FROM solicitudes")
                cursor.execute("DELETE FROM aliados")
                cursor.execute("DELETE FROM grupos")
                
                conn.commit()
                print("⚠️ Base de datos limpiada")
                
            except Exception as e:
                print(f"Error limpiando BD: {e}")
            finally:
                conn.close()


# Instancia global (singleton)
_db_instance: Optional[DBManager] = None


def get_db() -> DBManager:
    """Obtiene la instancia global del gestor de BD"""
    global _db_instance
    if _db_instance is None:
        _db_instance = DBManager()
    return _db_instance
