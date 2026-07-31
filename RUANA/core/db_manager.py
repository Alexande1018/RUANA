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


# Ruta ABSOLUTA única a la base de datos de RUANA.
# Estados permitidos para grupos territoriales (nunca "completo").
ESTADOS_GRUPO = ('activo', 'en_competencia', 'disuelto')
# Sufijos temática comunidad para nombre automático (no participan en lógica).
SUFIJOS_GRUPO = (
    'PUENTE', 'FARO', 'NEXO', 'RAÍZ', 'PLAZA', 'RED',
    'HOGAR', 'IMPULSO', 'ORIGEN', 'ENLACE',
)
# Máximo de grupos activos por código postal (no crear más de este límite).
MAX_GRUPOS_POR_CP = 5
# Columna de foto pública de perfil en aliados (SQLite y Postgres deben mantenerla sincronizada).
ALIADO_FOTO_PERFIL_COLUMN = "foto_perfil_url"
# IMPORTANTE: Todos los componentes (Flask, scripts, motores) deben usar
# EXCLUSIVAMENTE este valor como fuente de verdad para `ruana.db`.
DB_PATH = str(
    Path(
        os.environ.get(
            "RUANA_DB_PATH",
            Path(__file__).resolve().parent.parent / "ruana.db",
        )
    ).resolve()
)

# Formato de código RUANA invitación oficio: RUANA-{grupo_id}-{OFICIO_NORM}-{4chars}
# Usado por generar_invitacion_oficio y validar_invitacion_oficio para consistencia.
RUANA_CODIGO_INVITACION_REGEX = r'^RUANA-\d+-[A-Z0-9]+-[A-Z0-9]{4}$'


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
            self._migrar_aliado_accesos_dia(conn, cursor)
            self._migrar_centro_comunicacion_ruana(conn, cursor)
            conn.commit()
            print("[RUANA][DB] Esquema Postgres verificado (incl. foto de perfil + linaje + urgente + negociación guiada + accesos día + retador)")
        except Exception as e:
            print(f"[RUANA][DB] Error inicializando esquema Postgres: {e}")
        finally:
            if conn:
                conn.close()
    
    def _init_db(self):
        """Inicializa la base de datos con tablas si no existen"""
        with self._lock:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            conn = self._connect()
            cursor = conn.cursor()
            
            try:
                # Tabla de control de migraciones (para migraciones que se ejecutan una sola vez)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS migraciones (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        nombre TEXT UNIQUE NOT NULL,
                        aplicada_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                # Tabla de aliados (grupo_id se añade por migración; ver _migrar_aliados_grupo_id)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS aliados (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        codigo TEXT UNIQUE NOT NULL,
                        nombre TEXT NOT NULL,
                        marca TEXT,
                        oficio TEXT,
                        codigo_postal TEXT,
                        email TEXT,
                        telefono TEXT,
                        estado TEXT DEFAULT 'activo',
                        score INTEGER DEFAULT 0,
                        creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Tabla de grupos territoriales RUANA (varios grupos por CP, máximo MAX_GRUPOS_POR_CP)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS grupos (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        nombre TEXT UNIQUE NOT NULL,
                        codigo_postal TEXT NOT NULL,
                        ciudad TEXT,
                        provincia TEXT,
                        estado TEXT DEFAULT 'activo' CHECK(estado IN ('activo', 'en_competencia', 'disuelto')),
                        fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                self._migrar_grupos_si_procede(conn, cursor)
                self._migrar_grupos_multi_cp_si_procede(conn, cursor)
                self._migrar_aliados_grupo_id(conn, cursor)
                self._migrar_aliados_derrotas_competencia(conn, cursor)
                self._migrar_aliados_especializaciones(conn, cursor)
                self._migrar_aliados_descripcion_servicio(conn, cursor)
                self._migrar_aliados_especializacion_singular(conn, cursor)
                self._migrar_aliados_foto_perfil(conn, cursor)

                # Tabla de solicitudes (schema unificado aplicado por _migrar_solicitudes_unificado)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS solicitudes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        grupo_id INTEGER,
                        texto TEXT NOT NULL,
                        creado_por_codigo TEXT NOT NULL,
                        estado TEXT DEFAULT 'pendiente',
                        creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY(grupo_id) REFERENCES grupos(id)
                    )
                """)

                # Tabla de contactos RUANA (flujo de contacto, importe y antifraude)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS contactos_ruana (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        solicitante_codigo TEXT NOT NULL,
                        profesional_codigo TEXT NOT NULL,
                        servicio TEXT,
                        estado TEXT NOT NULL,
                        pendiente_resolucion INTEGER DEFAULT 1,
                        contacto_externo_habilitado INTEGER DEFAULT 0,
                        -- Declaraciones de importe (selladas por parte)
                        importe_solicitante REAL,
                        importe_solicitante_moneda TEXT,
                        declarado_por_solicitante TEXT,
                        fecha_declaracion_solicitante TIMESTAMP,
                        importe_profesional REAL,
                        importe_profesional_moneda TEXT,
                        declarado_por_profesional TEXT,
                        fecha_declaracion_profesional TIMESTAMP,
                        -- Resultado consolidado
                        importe_final REAL,
                        comision REAL,
                        comision_porcentaje REAL DEFAULT 0.05,
                        estado_pago TEXT DEFAULT 'no_generado',
                        pendiente_pago INTEGER DEFAULT 0,
                        -- Flags antifraude
                        fraude_sospechado INTEGER DEFAULT 0,
                        fraude_confirmado INTEGER DEFAULT 0,
                        fraude_motivo TEXT,
                        -- Trazabilidad temporal
                        creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        fecha_aceptacion TIMESTAMP,
                        fecha_trabajo_en_progreso TIMESTAMP,
                        fecha_cierre TIMESTAMP,
                        fecha_no_concretado TIMESTAMP,
                        fecha_disputa TIMESTAMP,
                        -- Campo libre para auditoría adicional en JSON
                        metadata TEXT,
                        FOREIGN KEY(solicitante_codigo) REFERENCES aliados(codigo),
                        FOREIGN KEY(profesional_codigo) REFERENCES aliados(codigo)
                    )
                """)
                
                # Tabla de evaluaciones (reemplaza estado_aliados.json)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS evaluaciones (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        codigo_aliado TEXT NOT NULL,
                        estado TEXT NOT NULL,
                        score REAL DEFAULT 0.0,
                        intencion TEXT,
                        tasa_respuesta REAL DEFAULT 0.0,
                        tasa_confirmacion REAL DEFAULT 0.0,
                        meses_sin_trabajo INTEGER DEFAULT 0,
                        ciclos_consecutivos INTEGER DEFAULT 1,
                        razones TEXT,
                        severidad TEXT DEFAULT 'normal',
                        evaluado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY(codigo_aliado) REFERENCES aliados(codigo),
                        UNIQUE(codigo_aliado)
                    )
                """)
                
                # Tabla de histórico de evaluaciones
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS evaluaciones_historico (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        codigo_aliado TEXT NOT NULL,
                        estado_anterior TEXT,
                        estado_nuevo TEXT NOT NULL,
                        score_anterior REAL,
                        score_nuevo REAL,
                        razon_cambio TEXT,
                        registrado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY(codigo_aliado) REFERENCES aliados(codigo)
                    )
                """)
                
                # Crear índices para búsquedas rápidas
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_aliados_codigo ON aliados(codigo)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_aliados_postal ON aliados(codigo_postal)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_grupos_nombre ON grupos(nombre)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_solicitudes_grupo ON solicitudes(grupo_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_solicitudes_codigo ON solicitudes(creado_por_codigo)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_contactos_profesional ON contactos_ruana(profesional_codigo)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_contactos_estado ON contactos_ruana(estado)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_contactos_pendiente ON contactos_ruana(pendiente_resolucion)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_evaluaciones_codigo ON evaluaciones(codigo_aliado)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_evaluaciones_historico_codigo ON evaluaciones_historico(codigo_aliado)")
                
                # Score RUANA: movimientos para límite ±10/día y auditoría
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS score_movimientos (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        codigo_aliado TEXT NOT NULL,
                        delta INTEGER NOT NULL,
                        motivo TEXT,
                        creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY(codigo_aliado) REFERENCES aliados(codigo)
                    )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_score_movimientos_codigo ON score_movimientos(codigo_aliado)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_score_movimientos_creado ON score_movimientos(creado_en)")
                
                # Penalizaciones por contacto abierto ya aplicadas (7d / 21d)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS contacto_penalizaciones_aplicadas (
                        contacto_id INTEGER NOT NULL,
                        tipo TEXT NOT NULL,
                        aplicado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY(contacto_id, tipo),
                        FOREIGN KEY(contacto_id) REFERENCES contactos_ruana(id)
                    )
                """)
                
                # Invitaciones: quién invitó a cada código (para recompensa +3 al referir)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS invitaciones (
                        codigo TEXT PRIMARY KEY,
                        invitador_aliado_id INTEGER NOT NULL,
                        creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        usado INTEGER DEFAULT 0,
                        FOREIGN KEY(invitador_aliado_id) REFERENCES aliados(id)
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS catalogo_servicios_aliado (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        aliado_codigo TEXT NOT NULL,
                        posicion INTEGER NOT NULL CHECK(posicion BETWEEN 1 AND 10),
                        descripcion TEXT,
                        precio TEXT,
                        actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(aliado_codigo, posicion),
                        FOREIGN KEY(aliado_codigo) REFERENCES aliados(codigo)
                    )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_catalogo_servicios_codigo ON catalogo_servicios_aliado(aliado_codigo)")
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
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        codigo_campana TEXT NOT NULL,
                        codigo_aliado TEXT NOT NULL,
                        usado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(codigo_campana, codigo_aliado),
                        FOREIGN KEY(codigo_campana) REFERENCES invitacion_campanas(codigo),
                        FOREIGN KEY(codigo_aliado) REFERENCES aliados(codigo)
                    )
                """)
                # Referidos: aliado referido por otro (para métrica "Aliados referidos por mí")
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS referidos (
                        codigo_referido TEXT NOT NULL,
                        codigo_invitador TEXT NOT NULL,
                        creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY(codigo_referido),
                        FOREIGN KEY(codigo_invitador) REFERENCES aliados(codigo)
                    )
                """)

                # Invitaciones por oficio: códigos para invitar a profesionales de oficios faltantes en el grupo
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS invitaciones_oficio (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        codigo TEXT UNIQUE NOT NULL,
                        grupo_id INTEGER NOT NULL,
                        oficio TEXT NOT NULL,
                        aliado_id INTEGER NOT NULL,
                        estado TEXT DEFAULT 'pendiente',
                        fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY(grupo_id) REFERENCES grupos(id),
                        FOREIGN KEY(aliado_id) REFERENCES aliados(id)
                    )
                """)
                # Eventos de sistema: trazabilidad de acciones administrativas y cambios clave
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS eventos_sistema (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        tipo TEXT NOT NULL,
                        descripcion TEXT NOT NULL,
                        actor_tipo TEXT,
                        actor_codigo TEXT,
                        metadata TEXT,
                        creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_eventos_sistema_creado ON eventos_sistema(creado_en DESC)")

                # Competencia: retador temporal cuando score < umbral; 1 mes, mayor score permanece
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS competencia (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        grupo_id INTEGER NOT NULL,
                        oficio TEXT NOT NULL,
                        aliado_original_codigo TEXT NOT NULL,
                        retador_codigo TEXT NOT NULL,
                        retador_grupo_anterior_id INTEGER,
                        fecha_inicio TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        fecha_fin_prevista TIMESTAMP NOT NULL,
                        estado TEXT DEFAULT 'activa' CHECK(estado IN ('activa', 'finalizada')),
                        ganador_codigo TEXT,
                        creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY(grupo_id) REFERENCES grupos(id),
                        FOREIGN KEY(aliado_original_codigo) REFERENCES aliados(codigo),
                        FOREIGN KEY(retador_codigo) REFERENCES aliados(codigo)
                    )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_competencia_grupo_estado ON competencia(grupo_id, estado)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_competencia_fin ON competencia(fecha_fin_prevista, estado)")

                # Avisos al grupo (ej. "Este mes tenemos X en competencia dentro del grupo")
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS avisos_grupo (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        grupo_id INTEGER NOT NULL,
                        tipo TEXT NOT NULL,
                        texto TEXT NOT NULL,
                        creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY(grupo_id) REFERENCES grupos(id)
                    )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_avisos_grupo ON avisos_grupo(grupo_id)")

                # Plaza cerrada por admin (grupo + oficio): Cerrar Oficio / Abrir Plaza
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS grupo_oficio_cerrado (
                        grupo_id INTEGER NOT NULL,
                        oficio TEXT NOT NULL,
                        cerrado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (grupo_id, oficio),
                        FOREIGN KEY (grupo_id) REFERENCES grupos(id)
                    )
                """)

                # Confirmaciones de trabajo: una fila por declaración (evita doble declaración por aliado)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS confirmaciones_trabajo (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        contacto_id INTEGER NOT NULL,
                        aliado_id INTEGER NOT NULL,
                        importe_declarado REAL NOT NULL,
                        fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(contacto_id, aliado_id),
                        FOREIGN KEY (contacto_id) REFERENCES contactos_ruana(id),
                        FOREIGN KEY (aliado_id) REFERENCES aliados(id)
                    )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_confirmaciones_contacto ON confirmaciones_trabajo(contacto_id)")

                # Ingresos RUANA: apoyo configurado cuando contacto se cierra con importes coincidentes.
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS ingresos_ruana (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        contacto_id INTEGER NOT NULL,
                        importe_final REAL NOT NULL,
                        apoyo_ruana_2pct REAL NOT NULL,
                        fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (contacto_id) REFERENCES contactos_ruana(id)
                    )
                """)

                # Auditoría de acciones relevantes
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS audit_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        entidad TEXT NOT NULL,
                        entidad_id INTEGER,
                        accion TEXT NOT NULL,
                        actor_tipo TEXT,
                        actor_codigo TEXT,
                        detalles TEXT,
                        creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_entidad ON audit_log(entidad, entidad_id)")

                self._migrar_contactos_comprobante(conn, cursor)
                self._migrar_contactos_apoyo_ruana(conn, cursor)
                self._migrar_contactos_ruana_idx_contacto_aliado(conn, cursor)
                self._migrar_aliados_pago(conn, cursor)
                self._migrar_notificaciones_aliado(conn, cursor)
                self._migrar_centro_comunicacion_ruana(conn, cursor)
                self._migrar_contactos_posponer_recordatorio(conn, cursor)
                self._migrar_contactos_fecha_pospuesto_hasta(conn, cursor)
                self._migrar_chat_mensajes(conn, cursor)
                self._migrar_negociacion_guiada(conn, cursor)
                self._migrar_contactos_motivo_contacto(conn, cursor)
                self._migrar_contactos_es_urgente(conn, cursor)
                self._migrar_drop_chat_messages(conn, cursor)
                self._migrar_competencia_scores(conn, cursor)
                self._migrar_payment_conflicts(conn, cursor)
                self._migrar_contactos_validacion_pago(conn, cursor)
                self._migrar_solicitudes_unificado(conn, cursor)
                self._migrar_contacto_panel_oculto(conn, cursor)
                self._migrar_referidos_origen(conn, cursor)
                self._migrar_invitaciones_oficio_codigo_referido(conn, cursor)
                self._migrar_aliados_invitado_por(conn, cursor)
                self._migrar_invitaciones_solicitud_id(conn, cursor)
                self._migrar_solicitudes_candidato(conn, cursor)
                self._migrar_aliado_accesos_dia(conn, cursor)
                self._migrar_datos_plaza_oficio(conn, cursor)
                self._migrar_drop_especializaciones(conn, cursor)
                self._migrar_retador_rename(conn, cursor)
                self._migrar_competencia_permanencia(conn, cursor)

                conn.commit()
                print(f"[RUANA][DB] Base de datos inicializada en: {self.db_path}")
                
            except Exception as e:
                print(f"[RUANA][DB] Error inicializando BD: {e}")
                conn.rollback()
                raise
            finally:
                conn.close()

    def _generar_id_unico_grupo(self) -> str:
        """Genera un ID alfanumérico no secuencial (8 caracteres) para el nombre del grupo."""
        caracteres = string.ascii_uppercase + string.digits
        return ''.join(random.choices(caracteres, k=8))

    def _generar_nombre_grupo(self, cursor) -> str:
        """
        Genera nombre único en BD con formato RUANA-<ID_UNICO>-<SUFIJO>.
        Valida unicidad en base de datos; reintenta si hay colisión.
        """
        intentos_max = 50
        for _ in range(intentos_max):
            id_part = self._generar_id_unico_grupo()
            sufijo = random.choice(SUFIJOS_GRUPO)
            nombre = f"RUANA-{id_part}-{sufijo}"
            cursor.execute("SELECT 1 FROM grupos WHERE nombre = ?", (nombre,))
            if not cursor.fetchone():
                return nombre
        raise RuntimeError("No se pudo generar nombre único para el grupo tras varios intentos")

    def _migrar_grupos_si_procede(self, conn, cursor) -> None:
        """Si la tabla grupos tiene esquema antiguo o incompleto, añade columnas faltantes y rellena nombres."""
        cursor.execute("PRAGMA table_info(grupos)")
        columnas = [row[1] for row in cursor.fetchall()]
        # Añadir cada columna del nuevo esquema si falta (SQLite: ADD COLUMN solo con constantes)
        for col, def_sql in [
            ('nombre', 'TEXT'),
            ('ciudad', 'TEXT'),
            ('provincia', 'TEXT'),
            ('estado', 'TEXT'),
            ('fecha_creacion', 'TIMESTAMP'),
        ]:
            if col not in columnas:
                cursor.execute(f"ALTER TABLE grupos ADD COLUMN {col} {def_sql}")
                columnas.append(col)
        cursor.execute("UPDATE grupos SET estado = COALESCE(estado, 'activo') WHERE estado IS NULL OR estado = ''")
        if 'creado_en' in columnas:
            cursor.execute("UPDATE grupos SET fecha_creacion = creado_en WHERE creado_en IS NOT NULL AND (fecha_creacion IS NULL OR fecha_creacion = '')")
        cursor.execute("UPDATE grupos SET fecha_creacion = datetime('now') WHERE fecha_creacion IS NULL OR fecha_creacion = ''")
        # Rellenar nombre único para cada fila que no lo tenga
        cursor.execute("SELECT id FROM grupos WHERE nombre IS NULL OR nombre = ''")
        for (gid,) in cursor.fetchall():
            nombre = self._generar_nombre_grupo(cursor)
            cursor.execute("UPDATE grupos SET nombre = ?, estado = COALESCE(estado, 'activo') WHERE id = ?", (nombre, gid))
        # No hacer commit aquí; lo hace _init_db al final

    def _migrar_grupos_multi_cp_si_procede(self, conn, cursor) -> None:
        """Permite varios grupos por mismo código postal (máx. MAX_GRUPOS_POR_CP). Se ejecuta una sola vez."""
        cursor.execute("SELECT 1 FROM migraciones WHERE nombre = 'grupos_multi_cp'")
        if cursor.fetchone():
            return
        cursor.execute("PRAGMA foreign_keys=OFF")
        try:
            cursor.execute("""
                CREATE TABLE grupos_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nombre TEXT UNIQUE NOT NULL,
                    codigo_postal TEXT NOT NULL,
                    ciudad TEXT,
                    provincia TEXT,
                    estado TEXT DEFAULT 'activo' CHECK(estado IN ('activo', 'en_competencia', 'disuelto')),
                    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                INSERT INTO grupos_new (id, nombre, codigo_postal, ciudad, provincia, estado, fecha_creacion)
                SELECT id, nombre, codigo_postal, ciudad, provincia, estado, fecha_creacion FROM grupos
            """)
            cursor.execute("DROP TABLE grupos")
            cursor.execute("ALTER TABLE grupos_new RENAME TO grupos")
            cursor.execute("INSERT INTO migraciones (nombre) VALUES ('grupos_multi_cp')")
        finally:
            cursor.execute("PRAGMA foreign_keys=ON")

    def _migrar_aliados_grupo_id(self, conn, cursor) -> None:
        """Añade grupo_id a aliados si falta y rellena con el primer grupo activo del CP."""
        cursor.execute("PRAGMA table_info(aliados)")
        columnas = [row[1] for row in cursor.fetchall()]
        if 'grupo_id' in columnas:
            return
        cursor.execute("ALTER TABLE aliados ADD COLUMN grupo_id INTEGER REFERENCES grupos(id)")
        cursor.execute("""
            UPDATE aliados SET grupo_id = (
                SELECT g.id FROM grupos g
                WHERE g.codigo_postal = aliados.codigo_postal AND g.estado = 'activo'
                ORDER BY g.id LIMIT 1
            ) WHERE aliados.codigo_postal IS NOT NULL AND aliados.codigo_postal != ''
        """)

    def _migrar_aliados_derrotas_competencia(self, conn, cursor) -> None:
        """Añade derrotas_competencia a aliados (solo derrotas en competencia cuentan; expulsión en 2ª)."""
        cursor.execute("PRAGMA table_info(aliados)")
        columnas = [row[1] for row in cursor.fetchall()]
        if 'derrotas_competencia' in columnas:
            return
        cursor.execute("ALTER TABLE aliados ADD COLUMN derrotas_competencia INTEGER DEFAULT 0")

    def _migrar_aliados_especializaciones(self, conn, cursor) -> None:
        """Añade especializaciones (JSON array de oficios del catálogo; no ocupan plaza en grupo)."""
        cursor.execute("PRAGMA table_info(aliados)")
        columnas = [row[1] for row in cursor.fetchall()]
        if 'especializaciones' in columnas:
            return
        cursor.execute("ALTER TABLE aliados ADD COLUMN especializaciones TEXT")

    def _migrar_aliados_descripcion_servicio(self, conn, cursor) -> None:
        """Añade descripcion_servicio (texto que el aliado escribe al registrarse o completa después)."""
        cursor.execute("PRAGMA table_info(aliados)")
        columnas = [row[1] for row in cursor.fetchall()]
        if 'descripcion_servicio' in columnas:
            return
        cursor.execute("ALTER TABLE aliados ADD COLUMN descripcion_servicio TEXT")

    def _migrar_aliados_foto_perfil(self, conn, cursor) -> None:
        """Añade foto_perfil_url (foto pública del aliado, editable solo por el propio aliado)."""
        col = ALIADO_FOTO_PERFIL_COLUMN
        cursor.execute("PRAGMA table_info(aliados)")
        columnas = [row[1] for row in cursor.fetchall()]
        if col in columnas:
            return
        cursor.execute(f"ALTER TABLE aliados ADD COLUMN {col} TEXT")

    def _migrar_aliados_especializacion_singular(self, conn, cursor) -> None:
        """Añade especializacion (una plaza por especialización por grupo; sub-oficio elegido)."""
        cursor.execute("PRAGMA table_info(aliados)")
        columnas = [row[1] for row in cursor.fetchall()]
        if 'especializacion' in columnas:
            return
        cursor.execute("ALTER TABLE aliados ADD COLUMN especializacion TEXT")

    def _migrar_contactos_comprobante(self, conn, cursor) -> None:
        """Añade comprobante_ruta a contactos_ruana para conflictos de pago."""
        cursor.execute("PRAGMA table_info(contactos_ruana)")
        columnas = [row[1] for row in cursor.fetchall()]
        if 'comprobante_ruta' in columnas:
            return
        cursor.execute("ALTER TABLE contactos_ruana ADD COLUMN comprobante_ruta TEXT")

    def _migrar_contactos_apoyo_ruana(self, conn, cursor) -> None:
        """Añade apoyo_ruana a contactos_ruana (importe Apoyo RUANA % por trabajo cerrado, config apoyo_pct)."""
        cursor.execute("PRAGMA table_info(contactos_ruana)")
        columnas = [row[1] for row in cursor.fetchall()]
        if 'apoyo_ruana' in columnas:
            return
        cursor.execute("ALTER TABLE contactos_ruana ADD COLUMN apoyo_ruana REAL")

    def _migrar_contactos_ruana_idx_contacto_aliado(self, conn, cursor) -> None:
        """Índice para búsquedas por contacto y aliado (profesional que abona el apoyo)."""
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_contacto_aliado'"
        )
        if cursor.fetchone():
            return
        cursor.execute(
            "CREATE INDEX idx_contacto_aliado ON contactos_ruana(id, profesional_codigo)"
        )

    def _migrar_aliados_pago(self, conn, cursor) -> None:
        """Añade qr_paypal_path y bizum_num a aliados para notificaciones de Apoyo RUANA."""
        cursor.execute("PRAGMA table_info(aliados)")
        columnas = [row[1] for row in cursor.fetchall()]
        if 'qr_paypal_path' not in columnas:
            cursor.execute("ALTER TABLE aliados ADD COLUMN qr_paypal_path TEXT")
        if 'bizum_num' not in columnas:
            cursor.execute("ALTER TABLE aliados ADD COLUMN bizum_num TEXT")

    def _migrar_notificaciones_aliado(self, conn, cursor) -> None:
        """Tabla de notificaciones al aliado (ej. Apoyo RUANA generado, con QR/Bizum)."""
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='notificaciones_aliado'"
        )
        if cursor.fetchone():
            return
        cursor.execute("""
            CREATE TABLE notificaciones_aliado (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                aliado_codigo TEXT NOT NULL,
                tipo TEXT NOT NULL,
                titulo TEXT,
                mensaje TEXT NOT NULL,
                metadata TEXT,
                leida INTEGER DEFAULT 0,
                creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(aliado_codigo) REFERENCES aliados(codigo)
            )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_notificaciones_aliado_codigo ON notificaciones_aliado(aliado_codigo)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_notificaciones_aliado_creado ON notificaciones_aliado(creado_en DESC)"
        )

    def _migrar_centro_comunicacion_ruana(self, conn, cursor) -> None:
        """Centro de comunicación entre aliados y equipo RUANA."""
        id_conv = "SERIAL PRIMARY KEY" if self.backend == "postgres" else "INTEGER PRIMARY KEY AUTOINCREMENT"
        id_msg = "SERIAL PRIMARY KEY" if self.backend == "postgres" else "INTEGER PRIMARY KEY AUTOINCREMENT"
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ruana_soporte_conversaciones (
                id %s,
                aliado_codigo TEXT NOT NULL,
                asunto TEXT NOT NULL,
                categoria TEXT DEFAULT 'consulta',
                estado TEXT DEFAULT 'pendiente',
                ultimo_mensaje_preview TEXT,
                ultimo_mensaje_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                tiene_no_leido_aliado INTEGER DEFAULT 0,
                tiene_no_leido_admin INTEGER DEFAULT 1,
                eliminada_por_aliado INTEGER DEFAULT 0,
                eliminada_por_admin INTEGER DEFAULT 0,
                creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(aliado_codigo) REFERENCES aliados(codigo)
            )
        """ % id_conv)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ruana_soporte_mensajes (
                id %s,
                conversacion_id INTEGER NOT NULL,
                emisor_tipo TEXT NOT NULL,
                emisor_codigo TEXT,
                mensaje TEXT NOT NULL,
                leido_por_aliado INTEGER DEFAULT 0,
                leido_por_admin INTEGER DEFAULT 0,
                creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(conversacion_id) REFERENCES ruana_soporte_conversaciones(id)
            )
        """ % id_msg)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_soporte_conv_aliado ON ruana_soporte_conversaciones(aliado_codigo)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_soporte_conv_estado ON ruana_soporte_conversaciones(estado)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_soporte_conv_ultimo ON ruana_soporte_conversaciones(ultimo_mensaje_en DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_soporte_msg_conv ON ruana_soporte_mensajes(conversacion_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_soporte_msg_fecha ON ruana_soporte_mensajes(creado_en DESC)")

    def _migrar_contactos_posponer_recordatorio(self, conn, cursor) -> None:
        """Añade posponer_recordatorio para 'Sigue en conversación' (ocultar alerta en sesión)."""
        cursor.execute("PRAGMA table_info(contactos_ruana)")
        columnas = [row[1] for row in cursor.fetchall()]
        if 'posponer_recordatorio' in columnas:
            return
        cursor.execute("ALTER TABLE contactos_ruana ADD COLUMN posponer_recordatorio INTEGER DEFAULT 0")

    def _migrar_contactos_fecha_pospuesto_hasta(self, conn, cursor) -> None:
        """Añade fecha_pospuesto_hasta: hasta cuándo la alerta queda oculta (límite temporal)."""
        cursor.execute("PRAGMA table_info(contactos_ruana)")
        columnas = [row[1] for row in cursor.fetchall()]
        if 'fecha_pospuesto_hasta' in columnas:
            return
        cursor.execute("ALTER TABLE contactos_ruana ADD COLUMN fecha_pospuesto_hasta TIMESTAMP")

    def _migrar_chat_mensajes(self, conn, cursor) -> None:
        """Crea la tabla chat_mensajes para el chat interno RUANA entre solicitante y profesional."""
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_mensajes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contacto_id INTEGER NOT NULL,
                emisor_codigo TEXT NOT NULL,
                texto TEXT NOT NULL,
                creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(contacto_id) REFERENCES contactos_ruana(id)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chat_mensajes_contacto ON chat_mensajes(contacto_id)")

    def _migrar_negociacion_guiada(self, conn, cursor) -> None:
        """Tabla de eventos y columna negociacion_json para negociación guiada (sustituye chat libre)."""
        id_col = "SERIAL PRIMARY KEY" if self.backend == "postgres" else "INTEGER PRIMARY KEY AUTOINCREMENT"
        if self.backend == "postgres":
            cursor.execute("""
                ALTER TABLE contactos_ruana
                ADD COLUMN IF NOT EXISTS negociacion_json JSONB DEFAULT '{}'::jsonb
            """)
        else:
            cursor.execute("PRAGMA table_info(contactos_ruana)")
            columnas = [row[1] for row in cursor.fetchall()]
            if 'negociacion_json' not in columnas:
                cursor.execute("ALTER TABLE contactos_ruana ADD COLUMN negociacion_json TEXT")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS negociacion_eventos (
                id %s,
                contacto_id INTEGER NOT NULL,
                tipo TEXT NOT NULL,
                campo TEXT,
                valor TEXT,
                emisor_codigo TEXT,
                mensaje TEXT NOT NULL,
                creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(contacto_id) REFERENCES contactos_ruana(id)
            )
        """ % id_col)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_negociacion_eventos_contacto ON negociacion_eventos(contacto_id)"
        )

    def _migrar_contactos_motivo_contacto(self, conn, cursor) -> None:
        """Añade motivo_contacto al contacto (obligatorio antes de iniciar chat)."""
        cursor.execute("PRAGMA table_info(contactos_ruana)")
        columnas = [row[1] for row in cursor.fetchall()]
        if 'motivo_contacto' in columnas:
            return
        cursor.execute("ALTER TABLE contactos_ruana ADD COLUMN motivo_contacto TEXT")

    def _migrar_contactos_es_urgente(self, conn, cursor) -> None:
        """Añade es_urgente y urgente_marcado_en (solo al iniciar chat, Regla 6)."""
        if self.backend == "postgres":
            cursor.execute("""
                ALTER TABLE contactos_ruana
                ADD COLUMN IF NOT EXISTS es_urgente INTEGER DEFAULT 0
            """)
            cursor.execute("""
                ALTER TABLE contactos_ruana
                ADD COLUMN IF NOT EXISTS urgente_marcado_en TIMESTAMP
            """)
            return
        cursor.execute("PRAGMA table_info(contactos_ruana)")
        columnas = [row[1] for row in cursor.fetchall()]
        if 'es_urgente' not in columnas:
            cursor.execute("ALTER TABLE contactos_ruana ADD COLUMN es_urgente INTEGER DEFAULT 0")
        if 'urgente_marcado_en' not in columnas:
            cursor.execute("ALTER TABLE contactos_ruana ADD COLUMN urgente_marcado_en TIMESTAMP")

    def _migrar_aliado_accesos_dia(self, conn, cursor) -> None:
        """Tabla de días con login (Regla 8: racha de 7 días consecutivos)."""
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS aliado_accesos_dia (
                codigo_aliado TEXT NOT NULL,
                dia TEXT NOT NULL,
                creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (codigo_aliado, dia),
                FOREIGN KEY (codigo_aliado) REFERENCES aliados(codigo)
            )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_aliado_accesos_dia_codigo ON aliado_accesos_dia(codigo_aliado)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_aliado_accesos_dia_dia ON aliado_accesos_dia(dia)"
        )

    def _migrar_drop_chat_messages(self, conn, cursor) -> None:
        """Elimina la tabla redundante chat_messages. Admin lee desde chat_mensajes + JOIN aliados."""
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='chat_messages'")
        if cursor.fetchone():
            cursor.execute("DROP TABLE IF EXISTS chat_messages")

    def _migrar_payment_conflicts(self, conn, cursor) -> None:
        """Tabla de conflictos de pago cuando importe contratante != importe profesional."""
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS payment_conflicts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trabajo_id INTEGER NOT NULL,
                contratante_id INTEGER NOT NULL,
                profesional_id INTEGER NOT NULL,
                importe_contratante REAL NOT NULL,
                importe_profesional REAL NOT NULL,
                estado TEXT NOT NULL DEFAULT 'PENDIENTE_PRUEBA',
                prueba_url TEXT,
                comentario_admin TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (trabajo_id) REFERENCES contactos_ruana(id),
                FOREIGN KEY (contratante_id) REFERENCES aliados(id),
                FOREIGN KEY (profesional_id) REFERENCES aliados(id)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_payment_conflicts_trabajo ON payment_conflicts(trabajo_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_payment_conflicts_created ON payment_conflicts(created_at DESC)")

    def _migrar_contactos_validacion_pago(self, conn, cursor) -> None:
        """Añade fecha_validacion_pago, admin_validacion_codigo y motivo_rechazo_pago a contactos_ruana."""
        cursor.execute("PRAGMA table_info(contactos_ruana)")
        columnas = [row[1] for row in cursor.fetchall()]
        if 'fecha_validacion_pago' not in columnas:
            cursor.execute("ALTER TABLE contactos_ruana ADD COLUMN fecha_validacion_pago TIMESTAMP")
        if 'admin_validacion_codigo' not in columnas:
            cursor.execute("ALTER TABLE contactos_ruana ADD COLUMN admin_validacion_codigo TEXT")
        if 'motivo_rechazo_pago' not in columnas:
            cursor.execute("ALTER TABLE contactos_ruana ADD COLUMN motivo_rechazo_pago TEXT")

    def _migrar_solicitudes_unificado(self, conn, cursor) -> None:
        """Una sola tabla solicitudes: grupo_id, solicitante_codigo/nombre, oficio, descripcion, estado (pendiente/atendida), atendido_por_*, created_at, atendido_at."""
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='solicitudes'")
        if cursor.fetchone():
            cursor.execute("PRAGMA table_info(solicitudes)")
            columnas = [row[1] for row in cursor.fetchall()]
            if 'solicitante_codigo' in columnas:
                return
            if 'texto' in columnas:
                cursor.execute("ALTER TABLE solicitudes RENAME TO solicitudes_legacy")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS solicitudes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                grupo_id INTEGER NOT NULL,
                solicitante_codigo TEXT NOT NULL,
                solicitante_nombre TEXT NOT NULL,
                oficio TEXT NOT NULL,
                descripcion TEXT,
                estado TEXT NOT NULL DEFAULT 'pendiente',
                atendido_por_codigo TEXT,
                atendido_por_nombre TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                atendido_at DATETIME,
                FOREIGN KEY (grupo_id) REFERENCES grupos(id)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_solicitudes_grupo ON solicitudes(grupo_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_solicitudes_estado ON solicitudes(estado)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_solicitudes_created ON solicitudes(created_at DESC)")

    def _migrar_contacto_panel_oculto(self, conn, cursor) -> None:
        """Tabla para que un aliado pueda ocultar un contacto de su panel (Finalizar chat)."""
        cursor.execute("SELECT 1 FROM migraciones WHERE nombre = 'contacto_panel_oculto'")
        if cursor.fetchone():
            return
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS contacto_panel_oculto (
                contacto_id INTEGER NOT NULL,
                codigo_aliado TEXT NOT NULL,
                creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (contacto_id, codigo_aliado),
                FOREIGN KEY (contacto_id) REFERENCES contactos_ruana(id)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_contacto_panel_oculto_aliado ON contacto_panel_oculto(codigo_aliado)")
        cursor.execute("INSERT INTO migraciones (nombre) VALUES ('contacto_panel_oculto')")

    def _migrar_competencia_scores(self, conn, cursor) -> None:
        """Añade columnas de scores a competencia para snapshot y tracking."""
        cursor.execute("PRAGMA table_info(competencia)")
        columnas = [row[1] for row in cursor.fetchall()]
        for col, def_sql in [
            ('score_titular_inicio', 'INTEGER'),
            ('score_titular_actual', 'INTEGER'),
            ('motivo', 'TEXT'),
        ]:
            if col not in columnas:
                cursor.execute(f"ALTER TABLE competencia ADD COLUMN {col} {def_sql}")
        # Preferir nombres retador; si solo existen los legacy suplente, el rename posterior los migra
        if 'score_retador_inicio' not in columnas and 'score_suplente_inicio' not in columnas:
            cursor.execute("ALTER TABLE competencia ADD COLUMN score_retador_inicio INTEGER")
        if 'score_retador_actual' not in columnas and 'score_suplente_actual' not in columnas:
            cursor.execute("ALTER TABLE competencia ADD COLUMN score_retador_actual INTEGER")

    def _migrar_retador_rename(self, conn, cursor) -> None:
        """Renombra columnas suplente→retador en la tabla competencia (SQLite 3.25+)."""
        cursor.execute("SELECT 1 FROM migraciones WHERE nombre = 'retador_rename_v1'")
        if cursor.fetchone():
            return
        cursor.execute("PRAGMA table_info(competencia)")
        cols = [row[1] for row in cursor.fetchall()]
        renames = [
            ('suplente_codigo', 'retador_codigo'),
            ('suplente_grupo_anterior_id', 'retador_grupo_anterior_id'),
            ('score_suplente_inicio', 'score_retador_inicio'),
            ('score_suplente_actual', 'score_retador_actual'),
        ]
        for old_name, new_name in renames:
            if old_name in cols:
                try:
                    cursor.execute(f"ALTER TABLE competencia RENAME COLUMN {old_name} TO {new_name}")
                except Exception as ex:
                    print(f"[RUANA][DB] Aviso al renombrar {old_name}→{new_name}: {ex}")
        cursor.execute("INSERT INTO migraciones (nombre) VALUES ('retador_rename_v1')")

    def _migrar_competencia_permanencia(self, conn, cursor) -> None:
        """Cola de competencias pendientes de retador + columnas de auditoría en competencia."""
        cursor.execute("SELECT 1 FROM migraciones WHERE nombre = 'competencia_permanencia_v1'")
        if cursor.fetchone():
            return
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS competencia_pendiente (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                aliado_codigo TEXT NOT NULL,
                grupo_id INTEGER NOT NULL,
                oficio TEXT NOT NULL,
                codigo_postal TEXT NOT NULL,
                score_al_crear INTEGER,
                estado TEXT DEFAULT 'pendiente',
                creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(aliado_codigo) REFERENCES aliados(codigo),
                FOREIGN KEY(grupo_id) REFERENCES grupos(id)
            )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_comp_pend_cp_oficio "
            "ON competencia_pendiente(codigo_postal, oficio, estado)"
        )
        cursor.execute("PRAGMA table_info(competencia)")
        cols = [row[1] for row in cursor.fetchall()]
        for col, def_sql in (
            ('fecha_cierre', 'TIMESTAMP'),
            ('score_titular_final', 'INTEGER'),
            ('score_retador_final', 'INTEGER'),
        ):
            if col not in cols:
                cursor.execute(f"ALTER TABLE competencia ADD COLUMN {col} {def_sql}")
        cursor.execute("INSERT INTO migraciones (nombre) VALUES ('competencia_permanencia_v1')")

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
        """Resuelve conflictos de plaza: si un grupo tiene varios activos del mismo oficio,
        conserva el de mayor score (más antiguo en empate); reasigna el resto o pone en_espera."""
        cursor.execute("SELECT 1 FROM migraciones WHERE nombre = 'plaza_oficio_v1'")
        if cursor.fetchone():
            return
        cursor.execute("""
            SELECT grupo_id, oficio, COUNT(*) as cnt
            FROM aliados
            WHERE estado = 'activo' AND grupo_id IS NOT NULL AND oficio IS NOT NULL AND oficio != ''
            GROUP BY grupo_id, oficio
            HAVING COUNT(*) > 1
        """)
        conflictos = cursor.fetchall()
        for grupo_id, oficio, cnt in conflictos:
            cursor.execute("""
                SELECT id, codigo, score, codigo_postal
                FROM aliados
                WHERE grupo_id = ? AND oficio = ? AND estado = 'activo'
                ORDER BY score DESC, creado_en ASC
            """, (grupo_id, oficio))
            aliados_conflicto = cursor.fetchall()
            for aliado in aliados_conflicto[1:]:
                aliado_id, aliado_codigo, aliado_score, codigo_postal = aliado
                cursor.execute("""
                    SELECT g.id FROM grupos g
                    WHERE g.codigo_postal = ? AND g.estado = 'activo' AND g.id != ?
                      AND NOT EXISTS (
                        SELECT 1 FROM aliados a2
                        WHERE a2.grupo_id = g.id AND a2.oficio = ? AND a2.estado = 'activo'
                      )
                    ORDER BY g.id LIMIT 1
                """, (codigo_postal, grupo_id, oficio))
                alt_row = cursor.fetchone()
                if alt_row:
                    cursor.execute("UPDATE aliados SET grupo_id = ? WHERE id = ?", (alt_row[0], aliado_id))
                else:
                    cursor.execute(
                        "SELECT COUNT(*) FROM grupos WHERE codigo_postal = ? AND estado = 'activo'",
                        (codigo_postal,)
                    )
                    n_grupos = cursor.fetchone()[0] or 0
                    if n_grupos < MAX_GRUPOS_POR_CP:
                        nombre = self._generar_nombre_grupo(cursor)
                        cursor.execute(
                            "INSERT INTO grupos (nombre, codigo_postal, estado, fecha_creacion) VALUES (?, ?, 'activo', CURRENT_TIMESTAMP)",
                            (nombre, codigo_postal)
                        )
                        new_grupo_id = cursor.lastrowid
                        cursor.execute("UPDATE aliados SET grupo_id = ? WHERE id = ?", (new_grupo_id, aliado_id))
                    else:
                        cursor.execute(
                            "UPDATE aliados SET grupo_id = NULL, estado = 'en_espera' WHERE id = ?",
                            (aliado_id,)
                        )
        cursor.execute("INSERT INTO migraciones (nombre) VALUES ('plaza_oficio_v1')")

    def _migrar_drop_especializaciones(self, conn, cursor) -> None:
        """Elimina las columnas especializacion y especializaciones de aliados (ya no se usan)."""
        cursor.execute("SELECT 1 FROM migraciones WHERE nombre = 'drop_especializaciones_v1'")
        if cursor.fetchone():
            return
        cursor.execute("PRAGMA table_info(aliados)")
        cols = [row[1] for row in cursor.fetchall()]
        for col in ('especializacion', 'especializaciones'):
            if col in cols:
                try:
                    cursor.execute(f"ALTER TABLE aliados DROP COLUMN {col}")
                except Exception as ex:
                    print(f"[RUANA][DB] Aviso al eliminar columna {col}: {ex}")
        cursor.execute("INSERT INTO migraciones (nombre) VALUES ('drop_especializaciones_v1')")

    def _migrar_referidos_origen(self, conn, cursor) -> None:
        """Añade columna origen a referidos (trazabilidad del vínculo invitador→referido)."""
        cursor.execute("PRAGMA table_info(referidos)")
        columnas = [row[1] for row in cursor.fetchall()]
        if 'origen' not in columnas:
            cursor.execute("ALTER TABLE referidos ADD COLUMN origen TEXT DEFAULT ''")

    def _migrar_invitaciones_oficio_codigo_referido(self, conn, cursor) -> None:
        """Añade codigo_referido a invitaciones_oficio para backfill del árbol."""
        cursor.execute("PRAGMA table_info(invitaciones_oficio)")
        columnas = [row[1] for row in cursor.fetchall()]
        if 'codigo_referido' not in columnas:
            cursor.execute("ALTER TABLE invitaciones_oficio ADD COLUMN codigo_referido TEXT DEFAULT ''")

    def _migrar_aliados_invitado_por(self, conn, cursor) -> None:
        """Añade invitado_por_codigo e invitado_origen en aliados (fuente del linaje)."""
        cursor.execute("PRAGMA table_info(aliados)")
        columnas = [row[1] for row in cursor.fetchall()]
        if 'invitado_por_codigo' not in columnas:
            cursor.execute("ALTER TABLE aliados ADD COLUMN invitado_por_codigo TEXT DEFAULT NULL")
        if 'invitado_origen' not in columnas:
            cursor.execute("ALTER TABLE aliados ADD COLUMN invitado_origen TEXT DEFAULT ''")
        try:
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_aliados_invitado_por ON aliados(invitado_por_codigo)"
            )
        except Exception:
            pass

    def _migrar_invitaciones_solicitud_id(self, conn, cursor) -> None:
        """Vincula invitaciones «Conozco a alguien» con la solicitud de origen."""
        try:
            if self.backend == "postgres":
                cursor.execute(
                    "ALTER TABLE invitaciones ADD COLUMN IF NOT EXISTS solicitud_id INTEGER"
                )
            else:
                cursor.execute("PRAGMA table_info(invitaciones)")
                columnas = [row[1] for row in cursor.fetchall()]
                if 'solicitud_id' not in columnas:
                    cursor.execute("ALTER TABLE invitaciones ADD COLUMN solicitud_id INTEGER")
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_invitaciones_solicitud_id ON invitaciones(solicitud_id)"
            )
        except Exception as ex:
            print(f"[RUANA][DB] Aviso migrar invitaciones.solicitud_id: {ex}")

    def _migrar_solicitudes_candidato(self, conn, cursor) -> None:
        """Campos para candidato pendiente e incorporación del aliado invitado."""
        try:
            if self.backend == "postgres":
                cursor.execute(
                    "ALTER TABLE solicitudes ADD COLUMN IF NOT EXISTS candidato_por_codigo TEXT"
                )
                cursor.execute(
                    "ALTER TABLE solicitudes ADD COLUMN IF NOT EXISTS candidato_por_nombre TEXT"
                )
                cursor.execute(
                    "ALTER TABLE solicitudes ADD COLUMN IF NOT EXISTS candidato_at TIMESTAMP"
                )
                cursor.execute(
                    "ALTER TABLE solicitudes ADD COLUMN IF NOT EXISTS asignada_a_codigo TEXT"
                )
                cursor.execute(
                    "ALTER TABLE solicitudes ADD COLUMN IF NOT EXISTS asignada_a_nombre TEXT"
                )
            else:
                cursor.execute("PRAGMA table_info(solicitudes)")
                columnas = [row[1] for row in cursor.fetchall()]
                for col, def_sql in [
                    ('candidato_por_codigo', 'TEXT'),
                    ('candidato_por_nombre', 'TEXT'),
                    ('candidato_at', 'DATETIME'),
                    ('asignada_a_codigo', 'TEXT'),
                    ('asignada_a_nombre', 'TEXT'),
                ]:
                    if col not in columnas:
                        cursor.execute(f"ALTER TABLE solicitudes ADD COLUMN {col} {def_sql}")
        except Exception as ex:
            print(f"[RUANA][DB] Aviso migrar solicitudes candidato: {ex}")

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
        """
        Fuente de verdad del linaje: escribe aliados.invitado_por_codigo
        y mantiene referidos en paralelo por compatibilidad.
        """
        codigo_referido = (codigo_referido or '').strip()
        codigo_invitador = (codigo_invitador or '').strip()
        origen = (origen or '').strip()
        if not codigo_referido or not codigo_invitador or codigo_referido == codigo_invitador:
            return False
        with self._lock:
            conn = None
            try:
                conn = self._connect()
                cursor = conn.cursor()
                if not self._aliados_tiene_invitado_por(cursor):
                    return False
                if overwrite:
                    cursor.execute("""
                        UPDATE aliados
                        SET invitado_por_codigo = ?,
                            invitado_origen = COALESCE(NULLIF(?, ''), invitado_origen),
                            actualizado_en = CURRENT_TIMESTAMP
                        WHERE codigo = ?
                    """, (codigo_invitador, origen, codigo_referido))
                else:
                    cursor.execute("""
                        UPDATE aliados
                        SET invitado_por_codigo = ?,
                            invitado_origen = CASE
                                WHEN COALESCE(invitado_origen, '') = '' THEN ?
                                ELSE invitado_origen
                            END,
                            actualizado_en = CURRENT_TIMESTAMP
                        WHERE codigo = ?
                          AND (invitado_por_codigo IS NULL OR TRIM(COALESCE(invitado_por_codigo, '')) = '')
                    """, (codigo_invitador, origen, codigo_referido))
                updated = cursor.rowcount > 0
                if self._referidos_tiene_origen(cursor):
                    cursor.execute("""
                        INSERT OR IGNORE INTO referidos (codigo_referido, codigo_invitador, origen)
                        VALUES (?, ?, ?)
                    """, (codigo_referido, codigo_invitador, origen))
                    if origen:
                        cursor.execute("""
                            UPDATE referidos
                            SET origen = ?
                            WHERE codigo_referido = ?
                              AND (origen IS NULL OR origen = '')
                        """, (origen, codigo_referido))
                else:
                    cursor.execute("""
                        INSERT OR IGNORE INTO referidos (codigo_referido, codigo_invitador)
                        VALUES (?, ?)
                    """, (codigo_referido, codigo_invitador))
                conn.commit()
                return updated or cursor.rowcount > 0
            except Exception:
                return False
            finally:
                if conn:
                    conn.close()

    def _insert_referido(self, codigo_referido: str, codigo_invitador: str, origen: str = '') -> bool:
        """Compatibilidad: delega en asignar_invitado_por (linaje en aliados + referidos)."""
        return self.asignar_invitado_por(codigo_referido, codigo_invitador, origen=origen)

    def _origen_por_invitador(self, codigo_invitador: str, default: str = 'aliado') -> str:
        invitador = self.obtener_aliado_por_codigo(codigo_invitador)
        if invitador and (invitador.get('estado') or '').strip() == 'sistema':
            return 'admin_invitacion'
        return default

    def backfill_invitado_por_linaje(self) -> Dict[str, int]:
        """Rellena invitado_por_codigo desde referidos/invitaciones y huérfanos bajo admin."""
        admin_codigo = self.obtener_codigo_admin_referidos()
        stats = {'desde_referidos': 0, 'desde_invitaciones': 0, 'huerfanos': 0}
        with self._lock:
            conn = None
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                if not self._aliados_tiene_invitado_por(cursor):
                    return stats
                has_origen = self._referidos_tiene_origen(cursor)
                if has_origen:
                    cursor.execute("""
                        SELECT r.codigo_referido, r.codigo_invitador,
                               COALESCE(r.origen, '') AS origen
                        FROM referidos r
                        JOIN aliados a ON a.codigo = r.codigo_referido
                        WHERE a.invitado_por_codigo IS NULL OR TRIM(COALESCE(a.invitado_por_codigo, '')) = ''
                    """)
                else:
                    cursor.execute("""
                        SELECT r.codigo_referido, r.codigo_invitador, '' AS origen
                        FROM referidos r
                        JOIN aliados a ON a.codigo = r.codigo_referido
                        WHERE a.invitado_por_codigo IS NULL OR TRIM(COALESCE(a.invitado_por_codigo, '')) = ''
                    """)
                rows = cursor.fetchall()
            except Exception:
                rows = []
            finally:
                if conn:
                    try:
                        conn.close()
                    except Exception:
                        pass
        for row in rows:
            if self.asignar_invitado_por(row['codigo_referido'], row['codigo_invitador'], (row['origen'] or 'aliado')):
                stats['desde_referidos'] += 1

        with self._lock:
            conn = None
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT i.codigo AS codigo_referido, inv.codigo AS codigo_invitador,
                           inv.estado AS invitador_estado
                    FROM invitaciones i
                    JOIN aliados inv ON inv.id = i.invitador_aliado_id
                    JOIN aliados ref ON ref.codigo = i.codigo
                    WHERE COALESCE(ref.estado, '') NOT IN ('pendiente_completar', 'sistema')
                      AND (ref.invitado_por_codigo IS NULL OR TRIM(COALESCE(ref.invitado_por_codigo, '')) = '')
                """)
                pendientes = cursor.fetchall()
            except Exception:
                pendientes = []
            finally:
                if conn:
                    conn.close()
        for row in pendientes:
            origen = 'admin_invitacion' if (row['invitador_estado'] or '').strip() == 'sistema' else 'aliado'
            if self.asignar_invitado_por(row['codigo_referido'], row['codigo_invitador'], origen):
                stats['desde_invitaciones'] += 1

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
                      AND (a.invitado_por_codigo IS NULL OR TRIM(COALESCE(a.invitado_por_codigo, '')) = '')
                """, (admin_codigo,))
                huerfanos = [r['codigo'] for r in cursor.fetchall() if r and r['codigo']]
            except Exception:
                huerfanos = []
            finally:
                if conn:
                    conn.close()
        for codigo in huerfanos:
            if self.asignar_invitado_por(codigo, admin_codigo, 'huerfano'):
                stats['huerfanos'] += 1
        return stats

    def listar_hijos_directos_linaje(self, codigo_invitador: str) -> List[Dict[str, Any]]:
        """Hijos directos según aliados.invitado_por_codigo."""
        codigo_invitador = (codigo_invitador or '').strip()
        if not codigo_invitador:
            return []
        self.backfill_invitado_por_linaje()
        with self._lock:
            conn = None
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT a.codigo, a.nombre, a.oficio, a.codigo_postal, a.marca,
                           a.estado, a.score, a.telefono, a.email,
                           a.creado_en, a.invitado_origen AS origen,
                           (
                               SELECT COUNT(*) FROM aliados h
                               WHERE h.invitado_por_codigo = a.codigo
                                 AND COALESCE(h.estado, '') NOT IN (
                                     'pendiente_completar', 'sistema', 'rechazado', 'expulsado'
                                 )
                           ) AS referidos_count
                    FROM aliados a
                    WHERE a.invitado_por_codigo = ?
                      AND COALESCE(a.estado, '') NOT IN (
                          'pendiente_completar', 'sistema', 'rechazado', 'expulsado'
                      )
                    ORDER BY a.creado_en ASC
                """, (codigo_invitador,))
                result = []
                for row in cursor.fetchall():
                    item = dict(row)
                    item['zona'] = item.get('codigo_postal') or ''
                    item['especializaciones'] = []
                    try:
                        item['score'] = float(item.get('score') or 0)
                    except (TypeError, ValueError):
                        item['score'] = 0.0
                    origen = (item.get('origen') or '').strip()
                    item['origen'] = origen
                    item['origen_label'] = self.etiqueta_origen_referido(origen)
                    result.append(item)
                return result
            except Exception:
                return []
            finally:
                if conn:
                    conn.close()

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
        codigo_referido = (codigo_referido or '').strip()
        if not codigo_referido:
            return ''
        with self._lock:
            conn = None
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                if self._aliados_tiene_invitado_por(cursor):
                    cursor.execute(
                        "SELECT COALESCE(invitado_origen, '') AS origen FROM aliados WHERE codigo = ?",
                        (codigo_referido,),
                    )
                    row = cursor.fetchone()
                    if row and (row['origen'] or '').strip():
                        return (row['origen'] or '').strip()
                if self._referidos_tiene_origen(cursor):
                    cursor.execute(
                        "SELECT origen FROM referidos WHERE codigo_referido = ?",
                        (codigo_referido,),
                    )
                    row = cursor.fetchone()
                    if row and (row['origen'] or '').strip():
                        return (row['origen'] or '').strip()
                cursor.execute(
                    "SELECT 1 FROM invitacion_campana_usos WHERE codigo_aliado = ? LIMIT 1",
                    (codigo_referido,),
                )
                if cursor.fetchone():
                    return 'campana'
                cursor.execute("""
                    SELECT 1 FROM invitaciones_oficio
                    WHERE codigo_referido = ? AND estado = 'usado'
                    LIMIT 1
                """, (codigo_referido,))
                if cursor.fetchone():
                    return 'oficio'
                cursor.execute("""
                    SELECT inv.estado AS invitador_estado
                    FROM referidos r
                    JOIN aliados inv ON inv.codigo = r.codigo_invitador
                    WHERE r.codigo_referido = ?
                """, (codigo_referido,))
                inv_row = cursor.fetchone()
                if inv_row and (inv_row['invitador_estado'] or '').strip() == 'sistema':
                    return 'huerfano'
                if inv_row:
                    return 'aliado'
                return ''
            except Exception:
                return ''
            finally:
                if conn:
                    conn.close()

    @staticmethod
    def _normalizar_texto_catalogo(texto: str) -> str:
        """Normaliza texto de catálogo: minúsculas, sin acentos ni espacios duplicados."""
        import re
        import unicodedata
        raw = unicodedata.normalize("NFD", str(texto or "").strip().lower())
        sin_acentos = "".join(c for c in raw if unicodedata.category(c) != "Mn")
        return re.sub(r"\s+", " ", sin_acentos).strip()

    def _resolver_en_conjunto_catalogo(self, valor: str, permitidos: set) -> Optional[str]:
        """Devuelve la forma canónica del catálogo si valor coincide (exacto o sin acentos)."""
        valor = (valor or "").strip()
        if not valor or not permitidos:
            return None
        if valor in permitidos:
            return valor
        objetivo = self._normalizar_texto_catalogo(valor)
        for item in permitidos:
            if self._normalizar_texto_catalogo(item) == objetivo:
                return item
        return None

    def oficio_en_catalogo(self, oficio: str) -> bool:
        """True si el oficio está en el catálogo oficial RUANA (comparación normalizada)."""
        if not oficio or not str(oficio).strip():
            return False
        catalogo = self.get_catalogo_oficios_ruana()
        permitidos = {str(o).strip() for o in catalogo if o and str(o).strip()}
        return self._resolver_en_conjunto_catalogo(str(oficio).strip(), permitidos) is not None

    # ===============================================
    # OPERACIONES GRUPOS TERRITORIALES
    # ===============================================

    def obtener_grupos_activos_por_cp(self, codigo_postal: str) -> List[Dict[str, Any]]:
        """Lista grupos activos en el código postal (datos desde BD, sin listas abstractas)."""
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    """SELECT id, nombre, codigo_postal, ciudad, provincia, estado, fecha_creacion
                       FROM grupos WHERE codigo_postal = ? AND estado = 'activo' ORDER BY id""",
                    (codigo_postal,),
                )
                return [dict(row) for row in cursor.fetchall()]
            except Exception:
                return []
            finally:
                conn.close()

    def _grupo_tiene_oficio(self, cursor, grupo_id: int, oficio: str) -> bool:
        """True si ya existe un aliado activo en el grupo con ese oficio. Compatible con plaza (oficio, especializacion)."""
        if not oficio or not grupo_id:
            return False
        cursor.execute(
            "SELECT 1 FROM aliados WHERE grupo_id = ? AND oficio = ? AND estado = 'activo' LIMIT 1",
            (grupo_id, oficio.strip()),
        )
        return cursor.fetchone() is not None

    def _grupo_tiene_plaza(self, cursor, grupo_id: int, oficio_principal: str, especializacion: Optional[str] = None) -> bool:
        """True si la plaza (oficio_principal) ya está ocupada en el grupo. Plaza por oficio principal únicamente."""
        if not grupo_id or not oficio_principal:
            return False
        return self._grupo_tiene_oficio(cursor, grupo_id, oficio_principal.strip())

    def plaza_ocupada_en_grupo(self, grupo_id: int, oficio_principal: str, especializacion: Optional[str] = None) -> bool:
        """True si la plaza (oficio_principal) ya está ocupada en el grupo. Thread-safe. especializacion ignorado."""
        if not grupo_id or not oficio_principal:
            return False
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                return self._grupo_tiene_oficio(cursor, grupo_id, oficio_principal.strip())
            except Exception:
                return True
            finally:
                conn.close()

    def obtener_especializaciones_ocupadas(self, grupo_id: int, oficio_principal: str) -> set:
        """Devuelve los oficios ya ocupados en el grupo (deprecado: solo devuelve el oficio si está ocupado)."""
        if not grupo_id or not oficio_principal:
            return set()
        if self.plaza_ocupada_en_grupo(grupo_id, oficio_principal):
            return {oficio_principal.strip()}
        return set()

    def buscar_grupo_sin_oficio(self, codigo_postal: str, oficio: str, especializacion: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Devuelve un grupo activo en ese CP donde el oficio esté libre. especializacion ignorado."""
        if not codigo_postal or not oficio:
            return None
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    """SELECT id, nombre, codigo_postal, ciudad, provincia, estado, fecha_creacion
                       FROM grupos WHERE codigo_postal = ? AND estado = 'activo' ORDER BY id""",
                    (codigo_postal,),
                )
                for row in cursor.fetchall():
                    g = dict(row)
                    if not self._grupo_tiene_oficio(cursor, g['id'], oficio):
                        return g
                return None
            except Exception:
                return None
            finally:
                conn.close()

    def buscar_grupo_formacion_en_cp(self, codigo_postal: str, oficio: str) -> Optional[Dict[str, Any]]:
        """
        Grupo activo en el CP con menos aliados activos donde la plaza del oficio esté libre.
        Usado para reubicar al perdedor de una competencia (grupo en formación).
        """
        if not codigo_postal or not oficio:
            return None
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    """SELECT g.id, g.nombre, g.codigo_postal, g.ciudad, g.provincia, g.estado, g.fecha_creacion,
                              (SELECT COUNT(*) FROM aliados a2
                               WHERE a2.grupo_id = g.id AND a2.estado = 'activo') AS n_aliados
                       FROM grupos g
                       WHERE g.codigo_postal = ? AND g.estado = 'activo'
                       ORDER BY n_aliados ASC, g.id ASC""",
                    (codigo_postal,),
                )
                candidatos = []
                for row in cursor.fetchall():
                    g = dict(row)
                    if not self._grupo_tiene_oficio(cursor, g['id'], oficio):
                        candidatos.append(g)
                return candidatos[0] if candidatos else None
            except Exception:
                return None
            finally:
                conn.close()

    def contar_grupos_activos_por_cp(self, codigo_postal: str) -> int:
        """Cuenta grupos activos en el código postal (límite máximo MAX_GRUPOS_POR_CP)."""
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT COUNT(*) FROM grupos WHERE codigo_postal = ? AND estado = 'activo'",
                    (codigo_postal,),
                )
                return cursor.fetchone()[0] or 0
            except Exception:
                return 0
            finally:
                conn.close()

    def crear_grupo_en_cp(self, codigo_postal: str, ciudad: str = "", provincia: str = "") -> Dict[str, Any]:
        """Crea siempre un nuevo grupo en el CP (nombre automático). No comprueba límite; llamador debe asegurar < MAX_GRUPOS_POR_CP."""
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
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
        """Cuenta aliados activos en el grupo. Grupo viable = mínimo 2."""
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT COUNT(*) FROM aliados WHERE grupo_id = ? AND estado = 'activo'",
                    (grupo_id,),
                )
                return cursor.fetchone()[0] or 0
            except Exception:
                return 0
            finally:
                conn.close()

    def obtener_oficios_grupo(self, grupo_id: int) -> set:
        """Devuelve el conjunto de oficios presentes en el grupo (aliados activos)."""
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT DISTINCT oficio FROM aliados WHERE grupo_id = ? AND estado = 'activo' AND oficio IS NOT NULL AND oficio != ''",
                    (grupo_id,),
                )
                return {row[0].strip() for row in cursor.fetchall() if row[0]}
            except Exception:
                return set()
            finally:
                conn.close()

    def get_catalogo_oficios_ruana(self) -> List[str]:
        """Devuelve el catálogo de oficios RUANA (nombres de oficio principal). Compatible con formato jerárquico o lista plana."""
        try:
            config_path = Path(__file__).resolve().parent.parent / 'config' / 'oficios_ruana.json'
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                oficios = data.get('oficios', [])
                if isinstance(oficios, list) and oficios:
                    out = []
                    for o in oficios:
                        if isinstance(o, dict) and o.get('nombre'):
                            out.append(str(o['nombre']).strip())
                        elif isinstance(o, str) and o.strip():
                            out.append(str(o).strip())
                    if out:
                        return out
        except Exception:
            pass
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT DISTINCT oficio FROM aliados WHERE oficio IS NOT NULL AND oficio != '' ORDER BY oficio"
                )
                return [row[0].strip() for row in cursor.fetchall() if row[0]]
            except Exception:
                return []
            finally:
                conn.close()

    def get_catalogo_oficios_jerarquico(self) -> List[Dict[str, Any]]:
        """Devuelve el catálogo jerárquico: lista de { nombre, especializaciones: [] }. Compatible con lista plana (una esp = nombre)."""
        try:
            config_path = Path(__file__).resolve().parent.parent / 'config' / 'oficios_ruana.json'
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                oficios = data.get('oficios', [])
                if isinstance(oficios, list) and oficios:
                    out = []
                    for o in oficios:
                        if isinstance(o, dict) and o.get('nombre'):
                            esp = o.get('especializaciones') or [o['nombre']]
                            if isinstance(esp, list):
                                esp = [str(e).strip() for e in esp if str(e).strip()]
                            else:
                                esp = [str(o['nombre']).strip()]
                            out.append({'nombre': str(o['nombre']).strip(), 'especializaciones': esp})
                        elif isinstance(o, str) and o.strip():
                            n = str(o).strip()
                            out.append({'nombre': n, 'especializaciones': [n]})
                    if out:
                        return out
        except Exception:
            pass
        # Fallback: desde BD solo tenemos nombres
        nombres = self.get_catalogo_oficios_ruana()
        return [{'nombre': n, 'especializaciones': [n]} for n in nombres]

    def info_grupo_para_panel(self, grupo_id: int) -> Optional[Dict[str, Any]]:
        """
        Información del grupo para el panel del aliado (sin scores ni métricas de otros).
        Devuelve: nombre, estado, num_oficios, oficios_faltantes (según catálogo RUANA).
        """
        grupo = self.obtener_grupo_por_id(grupo_id)
        if not grupo:
            return None
        oficios_en_grupo = self.obtener_oficios_grupo(grupo_id)
        catalogo = self.get_catalogo_oficios_ruana()
        oficios_faltantes = sorted([o for o in catalogo if o and o not in oficios_en_grupo])
        return {
            'nombre': grupo.get('nombre') or '---',
            'estado': grupo.get('estado') or 'activo',
            'num_oficios': len(oficios_en_grupo),
            'oficios_faltantes': oficios_faltantes,
        }

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
        """
        Viabilidad mínima: grupo viable = mínimo 2 aliados activos.
        Si el grupo baja a 1 aliado:
        - Intenta fusión con otro grupo del mismo CP con <3 aliados y sin oficios repetidos; el más antiguo absorbe.
        - Si no es posible fusionar: reasigna el aliado a un grupo compatible, o crea uno nuevo; marca grupo como DISUELTO.
        El nombre del grupo disuelto queda retirado permanentemente (no se reutiliza).
        """
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                grupo = self.obtener_grupo_por_id(grupo_id)
                if not grupo:
                    return {'status': 'error', 'message': 'Grupo no encontrado'}

                if grupo.get('estado') == 'disuelto':
                    return {'status': 'ok', 'message': 'Grupo ya disuelto'}

                n = self.contar_aliados_activos_grupo(grupo_id)
                if n >= 2:
                    return {'status': 'ok', 'message': 'Grupo viable', 'aliados_activos': n}
                if n == 0:
                    cursor.execute("UPDATE grupos SET estado = 'disuelto' WHERE id = ?", (grupo_id,))
                    conn.commit()
                    return {'status': 'ok', 'accion': 'disuelto', 'motivo': 'sin aliados activos'}

                # 1 aliado activo: obtener su oficio y CP
                cursor.execute(
                    "SELECT id, codigo, oficio, codigo_postal FROM aliados WHERE grupo_id = ? AND estado = 'activo' LIMIT 1",
                    (grupo_id,),
                )
                row = cursor.fetchone()
                if not row:
                    cursor.execute("UPDATE grupos SET estado = 'disuelto' WHERE id = ?", (grupo_id,))
                    conn.commit()
                    return {'status': 'ok', 'accion': 'disuelto'}

                aliado_id, codigo_aliado, oficio_aliado, codigo_postal = row[0], row[1], (row[2] or '').strip(), (row[3] or '')
                if not codigo_postal:
                    cursor.execute("UPDATE grupos SET estado = 'disuelto' WHERE id = ?", (grupo_id,))
                    conn.commit()
                    return {'status': 'ok', 'accion': 'disuelto', 'motivo': 'sin cp'}

                # Intentar fusión: candidato mismo CP, <3 aliados, sin ese oficio
                candidato = self._buscar_candidato_fusion(cursor, grupo_id, codigo_postal, oficio_aliado)
                if candidato:
                    # Grupo más antiguo absorbe (comparar fecha_creacion o id)
                    try:
                        t_our = grupo.get('fecha_creacion') or ''
                        t_oth = candidato.get('fecha_creacion') or ''
                        id_our = grupo.get('id')
                        id_oth = candidato.get('id')
                    except Exception:
                        id_our, id_oth = grupo.get('id'), candidato.get('id')
                    if (t_oth < t_our) or (t_oth == t_our and id_oth < id_our):
                        absorbedor_id, disolver_id = candidato['id'], grupo_id
                    else:
                        absorbedor_id, disolver_id = grupo_id, candidato['id']
                    self._fusionar_grupos_mas_antiguo_absorbe(conn, cursor, absorbedor_id, disolver_id)
                    conn.commit()
                    return {'status': 'ok', 'accion': 'fusionado', 'absorbedor_id': absorbedor_id, 'disuelto_id': disolver_id}

                # No fusión: reasignar a grupo compatible o crear nuevo
                compatible = self._buscar_grupo_compatible_mismo_cp(cursor, codigo_postal, oficio_aliado, grupo_id)
                if compatible:
                    cursor.execute("UPDATE aliados SET grupo_id = ? WHERE id = ?", (compatible['id'], aliado_id))
                    cursor.execute("UPDATE grupos SET estado = 'disuelto' WHERE id = ?", (grupo_id,))
                    conn.commit()
                    return {'status': 'ok', 'accion': 'reasignado', 'nuevo_grupo_id': compatible['id'], 'disuelto_id': grupo_id}

                # Sin grupo compatible: crear nuevo grupo y asignar aliado
                cursor.execute("SELECT ciudad, provincia FROM grupos WHERE id = ?", (grupo_id,))
                r = cursor.fetchone()
                ciudad = r[0] if r and r[0] else ''
                provincia = r[1] if r and r[1] else ''
                conn.commit()
                conn.close()

                nuevo = self.crear_grupo_en_cp(codigo_postal, ciudad, provincia)
                if isinstance(nuevo, dict) and nuevo.get('id'):
                    with self._lock:
                        conn2 = self._connect()
                        cursor2 = conn2.cursor()
                        cursor2.execute("UPDATE aliados SET grupo_id = ? WHERE id = ?", (nuevo['id'], aliado_id))
                        cursor2.execute("UPDATE grupos SET estado = 'disuelto' WHERE id = ?", (grupo_id,))
                        conn2.commit()
                        conn2.close()
                    return {'status': 'ok', 'accion': 'reasignado_nuevo_grupo', 'nuevo_grupo_id': nuevo['id'], 'disuelto_id': grupo_id}

                with self._lock:
                    conn2 = self._connect()
                    cursor2 = conn2.cursor()
                    cursor2.execute("UPDATE grupos SET estado = 'disuelto' WHERE id = ?", (grupo_id,))
                    conn2.commit()
                    conn2.close()
                return {'status': 'ok', 'accion': 'disuelto', 'motivo': 'sin fusion ni compatible'}

            except Exception as e:
                return {'status': 'error', 'message': str(e)}
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

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
        """
        Crea un nuevo aliado en la BD.
        Plaza por oficio principal (especializacion ignorada).
        Si CP lleno y oficio ocupado en todos → estado en_espera (lista de Suplentes).
        """
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()

                cursor.execute("SELECT id FROM aliados WHERE codigo = ?", (codigo,))
                if cursor.fetchone():
                    return {'status': 'error', 'message': f'Código {codigo} ya existe'}

                cursor.execute("SELECT id FROM aliados WHERE email = ?", (email,))
                if cursor.fetchone():
                    return {'status': 'error', 'message': f'El email {email} ya está registrado'}

                cursor.execute("SELECT id FROM aliados WHERE telefono = ?", (telefono,))
                if cursor.fetchone():
                    return {'status': 'error', 'message': f'El teléfono {telefono} ya está registrado'}

                if not codigo or len(codigo) != 5 or not codigo.isdigit():
                    return {'status': 'error', 'message': 'El código debe ser un número de 5 dígitos (error de validación backend)'}

                if not nombre or len(nombre) < 3:
                    return {'status': 'error', 'message': 'El nombre es obligatorio y debe tener al menos 3 caracteres (error de validación backend)'}

                if not email or '@' not in email:
                    return {'status': 'error', 'message': 'El email es obligatorio y debe ser válido (error de validación backend)'}

                import re
                digitos_telefono = re.sub(r'\D', '', telefono)
                if not telefono or len(digitos_telefono) < 7:
                    return {'status': 'error', 'message': 'El teléfono es obligatorio y debe tener al menos 7 dígitos (error de validación backend)'}

                oficio_stripped = str(oficio).strip() if oficio else ''
                catalogo_oficial = {str(o).strip() for o in self.get_catalogo_oficios_ruana() if o and str(o).strip()}
                oficio_canonico = self._resolver_en_conjunto_catalogo(oficio_stripped, catalogo_oficial) if oficio_stripped else None
                en_catalogo = oficio_canonico is not None
                if oficio_canonico:
                    oficio_stripped = oficio_canonico
                estado_final = estado
                if oficio_stripped and not en_catalogo and estado != 'pendiente_completar':
                    estado_final = 'pendiente_validacion'

                # Asignación de grupo: solo si oficio en catálogo
                grupo_preferido_id = None
                mensaje_lista_espera = None
                if en_catalogo and oficio_stripped and estado_final not in ('pendiente_validacion', 'pendiente_completar'):
                    if grupo_id_invitacion:
                        if not self._grupo_tiene_oficio(cursor, grupo_id_invitacion, oficio_stripped):
                            grupo_pref = self.obtener_grupo_por_id(grupo_id_invitacion)
                            if grupo_pref and (grupo_pref.get('estado') or '') == 'activo':
                                grupo_preferido_id = grupo_id_invitacion
                        # Si invitador tiene oficio ocupado, buscar otro grupo del CP
                        if grupo_preferido_id is None and codigo_postal:
                            grupo_sin_oficio = self.buscar_grupo_sin_oficio(codigo_postal, oficio_stripped)
                            if grupo_sin_oficio:
                                grupo_preferido_id = grupo_sin_oficio['id']
                    if grupo_preferido_id is None and codigo_postal:
                        grupo_sin_oficio = self.buscar_grupo_sin_oficio(codigo_postal, oficio_stripped)
                        if grupo_sin_oficio:
                            grupo_preferido_id = grupo_sin_oficio['id']
                        elif self.contar_grupos_activos_por_cp(codigo_postal) < MAX_GRUPOS_POR_CP:
                            pass  # Se creará el grupo después del INSERT
                        else:
                            # CP lleno y oficio ocupado en todos → en_espera
                            estado_final = 'en_espera'
                            mensaje_lista_espera = self.MENSAJE_LISTA_ESPERA

                cursor.execute("""
                    INSERT INTO aliados
                    (codigo, nombre, marca, oficio, codigo_postal, email, telefono, estado, score, descripcion_servicio)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (codigo, nombre, marca, oficio_stripped or oficio, codigo_postal, email, telefono,
                      estado_final, score, descripcion_servicio))

                aliado_id = cursor.lastrowid
                conn.commit()

                # Asignar grupo
                if estado_final not in ('pendiente_validacion', 'pendiente_completar', 'en_espera'):
                    if grupo_preferido_id:
                        cursor.execute("UPDATE aliados SET grupo_id = ? WHERE id = ?", (grupo_preferido_id, aliado_id))
                        conn.commit()
                    elif codigo_postal and en_catalogo and oficio_stripped:
                        grupo_asignar = self.buscar_grupo_sin_oficio(codigo_postal, oficio_stripped)
                        if grupo_asignar:
                            cursor.execute("UPDATE aliados SET grupo_id = ? WHERE id = ?", (grupo_asignar['id'], aliado_id))
                        elif self.contar_grupos_activos_por_cp(codigo_postal) < MAX_GRUPOS_POR_CP:
                            nuevo_grupo = self.crear_grupo_en_cp(codigo_postal)
                            if isinstance(nuevo_grupo, dict) and 'id' in nuevo_grupo:
                                cursor.execute("UPDATE aliados SET grupo_id = ? WHERE id = ?", (nuevo_grupo['id'], aliado_id))
                        if cursor.rowcount:
                            conn.commit()

                cursor.execute(
                    "SELECT id, codigo, nombre, marca, oficio, codigo_postal, grupo_id, email, telefono, estado, score, descripcion_servicio, creado_en, actualizado_en FROM aliados WHERE id = ?",
                    (aliado_id,)
                )
                row = cursor.fetchone()
                if row and hasattr(row, 'keys'):
                    aliado_row = dict(row)
                elif row and isinstance(row, (list, tuple)):
                    cols = ('id', 'codigo', 'nombre', 'marca', 'oficio', 'codigo_postal', 'grupo_id', 'email', 'telefono', 'estado', 'score', 'descripcion_servicio', 'creado_en', 'actualizado_en')
                    aliado_row = dict(zip(cols, row))
                else:
                    aliado_row = {
                        'id': aliado_id, 'codigo': codigo, 'nombre': nombre, 'marca': marca, 'oficio': oficio,
                        'codigo_postal': codigo_postal, 'grupo_id': None, 'email': email, 'telefono': telefono,
                        'estado': estado_final, 'score': score, 'creado_en': datetime.now().isoformat(), 'actualizado_en': None
                    }

                out = {'status': 'success', **aliado_row}
                if mensaje_lista_espera:
                    out['mensaje_lista_espera'] = mensaje_lista_espera
                    try:
                        self._procesar_competencias_pendientes(codigo_postal, oficio_stripped)
                    except Exception:
                        pass
                return out

            except sqlite3.IntegrityError as e:
                return {'status': 'error', 'message': f'Error de integridad: {e}'}
            except Exception as e:
                return {'status': 'error', 'message': str(e)}
            finally:
                conn.close()

    def completar_aliado_pendiente(self, codigo: str, nombre: str, marca: str = "",
                                   oficio: str = "", codigo_postal: str = "",
                                   email: str = "", telefono: str = "",
                                   estado: str = "activo", score: int = 50,
                                   especializaciones: Optional[List[str]] = None,
                                   especializacion: Optional[str] = None,
                                   descripcion_servicio: Optional[str] = None,
                                   grupo_id_invitacion: Optional[int] = None) -> Dict[str, Any]:
        """Completa un aliado placeholder creado por invitacion y conserva su codigo.
        especializaciones y especializacion ignorados (plaza solo por oficio).
        """
        codigo = (codigo or "").strip()
        with self._lock:
            conn = None
            try:
                conn = self._connect()
                cursor = conn.cursor()

                cursor.execute("SELECT id, estado FROM aliados WHERE codigo = ?", (codigo,))
                row = cursor.fetchone()
                if not row:
                    return {'status': 'error', 'message': 'Codigo de invitacion no encontrado'}
                aliado_id = row[0]
                estado_actual = (row[1] or '').strip()
                if estado_actual != 'pendiente_completar':
                    return {'status': 'error', 'message': 'Codigo de invitacion ya usado'}

                cursor.execute("SELECT id FROM aliados WHERE email = ? AND codigo != ?", (email, codigo))
                if cursor.fetchone():
                    return {'status': 'error', 'message': f'El email {email} ya esta registrado'}

                cursor.execute("SELECT id FROM aliados WHERE telefono = ? AND codigo != ?", (telefono, codigo))
                if cursor.fetchone():
                    return {'status': 'error', 'message': f'El telefono {telefono} ya esta registrado'}

                if not codigo or len(codigo) != 5 or not codigo.isdigit():
                    return {'status': 'error', 'message': 'El codigo de invitacion debe ser un numero de 5 digitos'}
                if not nombre or len(nombre) < 3:
                    return {'status': 'error', 'message': 'El nombre es obligatorio y debe tener al menos 3 caracteres'}
                if not email or '@' not in email:
                    return {'status': 'error', 'message': 'El email es obligatorio y debe ser valido'}

                import re
                digitos_telefono = re.sub(r'\D', '', telefono)
                if not telefono or len(digitos_telefono) < 7:
                    return {'status': 'error', 'message': 'El telefono es obligatorio y debe tener al menos 7 digitos'}

                oficio_stripped = str(oficio).strip() if oficio else ''
                catalogo_oficial = {str(o).strip() for o in self.get_catalogo_oficios_ruana() if o and str(o).strip()}
                oficio_canonico = self._resolver_en_conjunto_catalogo(oficio_stripped, catalogo_oficial) if oficio_stripped else None
                en_catalogo = oficio_canonico is not None
                if oficio_canonico:
                    oficio_stripped = oficio_canonico
                estado_final = estado
                if oficio_stripped and not en_catalogo:
                    estado_final = 'pendiente_validacion'

                # Asignación de grupo
                grupo_preferido_id = None
                mensaje_lista_espera = None
                if en_catalogo and oficio_stripped and estado_final not in ('pendiente_validacion',):
                    if grupo_id_invitacion:
                        if not self._grupo_tiene_oficio(cursor, grupo_id_invitacion, oficio_stripped):
                            grupo_pref = self.obtener_grupo_por_id(grupo_id_invitacion)
                            if grupo_pref and (grupo_pref.get('estado') or '') == 'activo':
                                grupo_preferido_id = grupo_id_invitacion
                        if grupo_preferido_id is None and codigo_postal:
                            grupo_sin_oficio = self.buscar_grupo_sin_oficio(codigo_postal, oficio_stripped)
                            if grupo_sin_oficio:
                                grupo_preferido_id = grupo_sin_oficio['id']
                    if grupo_preferido_id is None and codigo_postal:
                        grupo_sin_oficio = self.buscar_grupo_sin_oficio(codigo_postal, oficio_stripped)
                        if grupo_sin_oficio:
                            grupo_preferido_id = grupo_sin_oficio['id']
                        elif self.contar_grupos_activos_por_cp(codigo_postal) >= MAX_GRUPOS_POR_CP:
                            estado_final = 'en_espera'
                            mensaje_lista_espera = self.MENSAJE_LISTA_ESPERA

                cursor.execute("""
                    UPDATE aliados
                    SET nombre = ?,
                        marca = ?,
                        oficio = ?,
                        codigo_postal = ?,
                        email = ?,
                        telefono = ?,
                        estado = ?,
                        score = ?,
                        grupo_id = NULL,
                        descripcion_servicio = ?,
                        actualizado_en = CURRENT_TIMESTAMP
                    WHERE id = ? AND estado = 'pendiente_completar'
                """, (
                    nombre, marca, oficio_stripped or oficio, codigo_postal, email, telefono,
                    estado_final, score, descripcion_servicio, aliado_id
                ))
                if cursor.rowcount != 1:
                    conn.rollback()
                    return {'status': 'error', 'message': 'Codigo de invitacion ya usado'}
                conn.commit()

                if en_catalogo and oficio_stripped and estado_final not in ('pendiente_validacion', 'en_espera'):
                    if grupo_preferido_id:
                        cursor.execute("UPDATE aliados SET grupo_id = ? WHERE id = ?", (grupo_preferido_id, aliado_id))
                        conn.commit()
                    elif codigo_postal:
                        grupo_asignar = self.buscar_grupo_sin_oficio(codigo_postal, oficio_stripped)
                        if grupo_asignar:
                            cursor.execute("UPDATE aliados SET grupo_id = ? WHERE id = ?", (grupo_asignar['id'], aliado_id))
                        elif self.contar_grupos_activos_por_cp(codigo_postal) < MAX_GRUPOS_POR_CP:
                            nuevo_grupo = self.crear_grupo_en_cp(codigo_postal)
                            if isinstance(nuevo_grupo, dict) and 'id' in nuevo_grupo:
                                cursor.execute("UPDATE aliados SET grupo_id = ? WHERE id = ?", (nuevo_grupo['id'], aliado_id))
                        if cursor.rowcount:
                            conn.commit()

                cursor.execute(
                    "SELECT id, codigo, nombre, marca, oficio, codigo_postal, grupo_id, email, telefono, estado, score, descripcion_servicio, creado_en, actualizado_en FROM aliados WHERE id = ?",
                    (aliado_id,)
                )
                row = cursor.fetchone()
                if row and hasattr(row, 'keys'):
                    aliado_row = dict(row)
                elif row and isinstance(row, (list, tuple)):
                    cols = ('id', 'codigo', 'nombre', 'marca', 'oficio', 'codigo_postal', 'grupo_id', 'email', 'telefono', 'estado', 'score', 'descripcion_servicio', 'creado_en', 'actualizado_en')
                    aliado_row = dict(zip(cols, row))
                else:
                    aliado_row = {
                        'id': aliado_id, 'codigo': codigo, 'nombre': nombre, 'marca': marca, 'oficio': oficio,
                        'codigo_postal': codigo_postal, 'grupo_id': None, 'email': email, 'telefono': telefono,
                        'estado': estado_final, 'score': score, 'creado_en': datetime.now().isoformat(), 'actualizado_en': None
                    }

                out = {'status': 'success', **aliado_row}
                if mensaje_lista_espera:
                    out['mensaje_lista_espera'] = mensaje_lista_espera
                    try:
                        self._procesar_competencias_pendientes(codigo_postal, oficio_stripped)
                    except Exception:
                        pass
                return out
            except sqlite3.IntegrityError as e:
                return {'status': 'error', 'message': f'Error de integridad: {e}'}
            except Exception as e:
                return {'status': 'error', 'message': str(e)}
            finally:
                if conn:
                    conn.close()

    def crear_aliado_seed(self, codigo: str, nombre: str, marca: str = "",
                          oficio: str = "", codigo_postal: str = "",
                          email: str = "", telefono: str = "",
                          estado: str = "activo", score: int = 50) -> Dict[str, Any]:
        """
        Crea un aliado de *semilla* en la BD.

        Uso previsto:
        - Scripts de inicialización de datos (por ejemplo, aliados ALFA01/BETA02/GAMA03/DELTA04).
        - Permite códigos no numéricos (legacy o alfanuméricos) siempre que sean únicos.

        Importante:
        - Mantiene TODAS las validaciones de unicidad y formato de email/teléfono.
        - No se usa en el flujo normal de registro; sólo para seeds controlados.

        Args:
            codigo: Código único (puede ser alfanumérico).
            nombre: Nombre completo del aliado.
            marca: Marca personal o comercial.
            oficio: Oficio/profesión.
            codigo_postal: Código postal.
            email: Correo electrónico.
            telefono: Teléfono de contacto.
            estado: Estado del aliado (activo, inactivo, etc.).
            score: Score inicial.

        Returns:
            Dict con datos del aliado creado o error.
        """
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()

                # Verificar unicidad del código (independiente de su formato)
                cursor.execute("SELECT id FROM aliados WHERE codigo = ?", (codigo,))
                if cursor.fetchone():
                    return {
                        'status': 'error',
                        'message': f'Código {codigo} ya existe'
                    }

                # Reutilizar las mismas validaciones de email/teléfono que crear_aliado
                cursor.execute("SELECT id FROM aliados WHERE email = ?", (email,))
                if cursor.fetchone():
                    return {
                        'status': 'error',
                        'message': f'El email {email} ya está registrado'
                    }

                cursor.execute("SELECT id FROM aliados WHERE telefono = ?", (telefono,))
                if cursor.fetchone():
                    return {
                        'status': 'error',
                        'message': f'El teléfono {telefono} ya está registrado'
                    }

                if not nombre or len(nombre) < 3:
                    return {
                        'status': 'error',
                        'message': 'El nombre es obligatorio y debe tener al menos 3 caracteres (error de validación backend)'
                    }

                if not email or '@' not in email:
                    return {
                        'status': 'error',
                        'message': 'El email es obligatorio y debe ser válido (error de validación backend)'
                    }

                import re
                digitos_telefono = re.sub(r'\\D', '', telefono)
                if not telefono or len(digitos_telefono) < 7:
                    return {
                        'status': 'error',
                        'message': 'El teléfono es obligatorio y debe tener al menos 7 dígitos (error de validación backend)'
                    }

                cursor.execute("""
                    INSERT INTO aliados
                    (codigo, nombre, marca, oficio, codigo_postal, email, telefono, estado, score)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (codigo, nombre, marca, oficio, codigo_postal, email, telefono, estado, score))

                aliado_id = cursor.lastrowid
                conn.commit()

                # Asignación automática de grupo (misma lógica que registro; seeds no rechazan por límite 5)
                grupo_id_final = None
                if codigo_postal and oficio and str(oficio).strip():
                    grupo_asignar = self.buscar_grupo_sin_oficio(codigo_postal, oficio)
                    if grupo_asignar:
                        cursor.execute("UPDATE aliados SET grupo_id = ? WHERE id = ?", (grupo_asignar['id'], aliado_id))
                        grupo_id_final = grupo_asignar['id']
                    elif self.contar_grupos_activos_por_cp(codigo_postal) < MAX_GRUPOS_POR_CP:
                        nuevo_grupo = self.crear_grupo_en_cp(codigo_postal)
                        if isinstance(nuevo_grupo, dict) and 'id' in nuevo_grupo:
                            cursor.execute("UPDATE aliados SET grupo_id = ? WHERE id = ?", (nuevo_grupo['id'], aliado_id))
                            grupo_id_final = nuevo_grupo['id']
                    if grupo_id_final is not None:
                        conn.commit()

                return {
                    'status': 'success',
                    'id': aliado_id,
                    'codigo': codigo,
                    'nombre': nombre,
                    'marca': marca,
                    'oficio': oficio,
                    'codigo_postal': codigo_postal,
                    'grupo_id': grupo_id_final,
                    'email': email,
                    'telefono': telefono,
                    'estado': estado,
                    'score': score,
                    'creado_en': datetime.now().isoformat()
                }
            except sqlite3.IntegrityError as e:
                return {'status': 'error', 'message': f'Error de integridad: {e}'}
            except Exception as e:
                return {'status': 'error', 'message': str(e)}
            finally:
                conn.close()
    
    def obtener_aliado_por_codigo(self, codigo: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene datos de un aliado por su código
        
        Args:
            codigo: Código del aliado (str o int; se normaliza a string para búsqueda)
            
        Returns:
            Dict con datos del aliado o None si no existe
        """
        codigo_str = str(codigo or "").strip() if codigo is not None else ""
        if not codigo_str:
            return None
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                # Comparar como string para que 85776 y "85776" coincidan (codigo en BD suele ser TEXT)
                cursor.execute("""
                    SELECT * FROM aliados WHERE TRIM(CAST(codigo AS TEXT)) = ?
                """, (codigo_str,))
                
                row = cursor.fetchone()
                
                if not row:
                    return None
                
                return dict(row)
                
            except Exception as e:
                print(f"Error obteniendo aliado: {e}")
                return None
            finally:
                conn.close()
    
    def obtener_aliado_por_id(self, aliado_id: int) -> Optional[Dict[str, Any]]:
        """Obtiene aliado por ID interno"""
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute("SELECT * FROM aliados WHERE id = ?", (aliado_id,))
                row = cursor.fetchone()
                
                return dict(row) if row else None
                
            except Exception as e:
                print(f"Error obteniendo aliado por ID: {e}")
                return None
            finally:
                conn.close()
    
    def actualizar_aliado(self, codigo: str, **kwargs) -> Dict[str, Any]:
        """
        Actualiza datos de un aliado
        
        Args:
            codigo: Código del aliado
            **kwargs: Campos a actualizar (nombre, oficio, estado, score, etc.)
            
        Returns:
            Dict con resultado de la operación
        """
        with self._lock:
            # Campos permitidos para actualizar (qr_paypal_path, bizum_num para notificaciones Apoyo RUANA)
            campos_permitidos = {
                'nombre', 'marca', 'oficio', 'codigo_postal', 'email',
                'telefono', 'descripcion_servicio',
                'qr_paypal_path', 'bizum_num', ALIADO_FOTO_PERFIL_COLUMN,
            }
            campos_update = {k: v for k, v in kwargs.items()
                           if k in campos_permitidos}
            if not campos_update:
                return {'status': 'error', 'message': 'No fields to update'}

            try:
                with self._connect() as conn:
                    cursor = conn.cursor()
                    # Obtener grupo_id anterior por si hay que revisar viabilidad
                    cursor.execute("SELECT grupo_id FROM aliados WHERE codigo = ?", (codigo,))
                    row_prev = cursor.fetchone()
                    grupo_id_anterior = row_prev[0] if row_prev and row_prev[0] else None

                    set_clause = ", ".join([f"{k} = ?" for k in campos_update.keys()])
                    values = list(campos_update.values()) + [codigo]

                    cursor.execute(f"""
                        UPDATE aliados
                        SET {set_clause}, actualizado_en = CURRENT_TIMESTAMP
                        WHERE codigo = ?
                    """, values)

                    conn.commit()

                    if cursor.rowcount == 0:
                        return {'status': 'error', 'message': f'Aliado {codigo} no encontrado'}

                # Si el aliado salió del grupo (estado inactivo o cambio de grupo), revisar viabilidad
                if grupo_id_anterior and ('estado' in campos_update or 'grupo_id' in campos_update):
                    self.procesar_viabilidad_grupo(grupo_id_anterior)

                return {
                    'status': 'success',
                    'message': 'Aliado actualizado'
                }

            except Exception as e:
                return {'status': 'error', 'message': str(e)}

    def listar_catalogo_servicios_aliado(self, codigo_aliado: str) -> List[Dict[str, Any]]:
        """
        Devuelve hasta 10 posiciones del catálogo privado del aliado.
        Siempre retorna 10 elementos (1..10), configurados o vacíos.
        """
        codigo = (codigo_aliado or '').strip()
        if not codigo:
            return [{'posicion': i, 'descripcion': None, 'precio': None, 'configurado': False} for i in range(1, 11)]
        with self._lock:
            conn = None
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT posicion, descripcion, precio, actualizado_en
                    FROM catalogo_servicios_aliado
                    WHERE aliado_codigo = ?
                    ORDER BY posicion ASC
                    """,
                    (codigo,)
                )
                rows = cursor.fetchall()
                by_pos = {}
                for row in rows:
                    item = dict(row)
                    pos = int(item.get('posicion') or 0)
                    desc = (item.get('descripcion') or '').strip() or None
                    price = (item.get('precio') or '').strip() or None
                    by_pos[pos] = {
                        'posicion': pos,
                        'descripcion': desc,
                        'precio': price,
                        'configurado': bool(desc and price),
                        'actualizado_en': item.get('actualizado_en'),
                    }
                out: List[Dict[str, Any]] = []
                for pos in range(1, 11):
                    out.append(by_pos.get(pos) or {
                        'posicion': pos,
                        'descripcion': None,
                        'precio': None,
                        'configurado': False,
                        'actualizado_en': None,
                    })
                return out
            except Exception:
                return [{'posicion': i, 'descripcion': None, 'precio': None, 'configurado': False} for i in range(1, 11)]
            finally:
                if conn:
                    conn.close()

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
        """
        Guarda una posición (1..10) del catálogo privado del aliado.
        """
        codigo = (codigo_aliado or '').strip()
        if not codigo:
            return {'status': 'error', 'message': 'Código de aliado requerido'}
        try:
            pos = int(posicion)
        except Exception:
            return {'status': 'error', 'message': 'Posición inválida'}
        if pos < 1 or pos > 10:
            return {'status': 'error', 'message': 'Posición inválida'}

        desc = (descripcion or '').strip()
        pr = (precio or '').strip()
        if len(desc) > 1000:
            return {'status': 'error', 'message': 'La descripción supera el límite de 1000 caracteres'}
        if len(pr) > 120:
            return {'status': 'error', 'message': 'El precio supera el límite permitido'}

        # Permitir guardar vacío como "no configurado"
        desc_db = desc if desc else None
        pr_db = pr if pr else None
        with self._lock:
            conn = None
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM aliados WHERE codigo = ?", (codigo,))
                if not cursor.fetchone():
                    return {'status': 'error', 'message': f'Aliado {codigo} no encontrado'}
                cursor.execute(
                    """
                    INSERT INTO catalogo_servicios_aliado (aliado_codigo, posicion, descripcion, precio, actualizado_en)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(aliado_codigo, posicion)
                    DO UPDATE SET
                        descripcion = excluded.descripcion,
                        precio = excluded.precio,
                        actualizado_en = CURRENT_TIMESTAMP
                    """,
                    (codigo, pos, desc_db, pr_db),
                )
                conn.commit()
                return {
                    'status': 'success',
                    'message': 'Servicio guardado',
                    'servicio': {
                        'posicion': pos,
                        'descripcion': desc_db,
                        'precio': pr_db,
                        'configurado': bool(desc_db and pr_db),
                    }
                }
            except Exception as e:
                return {'status': 'error', 'message': str(e)}
            finally:
                if conn:
                    conn.close()
    
    # ===============================================
    # SCORE RUANA (0-500, estado derivado, límites ±10/día)
    # ===============================================
    
    @staticmethod
    def score_a_estado(score: Any) -> str:
        """
        Calcula el estado RUANA a partir del score (siempre derivado, sin almacenar).
        ÉLITE 350-500, DESTACADO 200-349, ESTABLE 50-199, EN RIESGO 15-49, COMPETENCIA 0-14.
        """
        try:
            s = int(score) if score is not None else 0
        except (TypeError, ValueError):
            s = 0
        if s >= 350:
            return 'ÉLITE'
        if s >= 200:
            return 'DESTACADO'
        if s >= 50:
            return 'ESTABLE'
        if s >= 15:
            return 'EN RIESGO'
        return 'COMPETENCIA'
    
    def _delta_score_hoy(self, cursor, codigo_aliado: str) -> int:
        """Suma de deltas aplicados hoy al aliado (para límite ±10/día)."""
        cursor.execute("""
            SELECT COALESCE(SUM(delta), 0) FROM score_movimientos
            WHERE codigo_aliado = ? AND date(creado_en) = date('now', 'localtime')
        """, (codigo_aliado,))
        row = cursor.fetchone()
        return int(row[0]) if row else 0
    
    def aplicar_cambio_score(self, codigo_aliado: str, delta: int, motivo: str = "") -> Dict[str, Any]:
        """
        Aplica un cambio de score respetando: score en [0, 500], máximo ±10 por día.
        Inserta en score_movimientos y actualiza aliados.score.
        """
        if not codigo_aliado or delta == 0:
            return {'status': 'success', 'aplicado': 0, 'score_final': None}
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute("SELECT score FROM aliados WHERE codigo = ?", (codigo_aliado,))
                row = cursor.fetchone()
                if not row:
                    return {'status': 'error', 'message': f'Aliado {codigo_aliado} no encontrado'}
                score_actual = int(row[0]) if row[0] is not None else 0
                delta_hoy = self._delta_score_hoy(cursor, codigo_aliado)
                # Limitar delta del día a ±10
                delta_aplicar = delta
                if delta > 0:
                    techo_dia = 10 - delta_hoy
                    delta_aplicar = min(delta, max(0, techo_dia))
                else:
                    piso_dia = -10 - delta_hoy
                    delta_aplicar = max(delta, min(0, piso_dia))
                # Limitar score final a [0, 500]
                score_nuevo = max(0, min(500, score_actual + delta_aplicar))
                delta_real = score_nuevo - score_actual
                if delta_real == 0:
                    conn.close()
                    return {'status': 'success', 'aplicado': 0, 'score_final': score_actual}
                cursor.execute("""
                    INSERT INTO score_movimientos (codigo_aliado, delta, motivo)
                    VALUES (?, ?, ?)
                """, (codigo_aliado, delta_real, motivo))
                movimiento_id = cursor.lastrowid
                cursor.execute("""
                    UPDATE aliados SET score = ?, actualizado_en = CURRENT_TIMESTAMP
                    WHERE codigo = ?
                """, (score_nuevo, codigo_aliado))
                self._registrar_notificacion_cambio_score(
                    cursor=cursor,
                    codigo_aliado=codigo_aliado,
                    delta_real=delta_real,
                    score_nuevo=score_nuevo,
                    motivo=motivo,
                    movimiento_id=movimiento_id
                )
                conn.commit()
                umbral = self._get_umbral_competencia()
                if umbral is not None and score_nuevo < umbral:
                    if score_actual >= umbral:
                        self._solicitar_competencia_por_score(codigo_aliado)
                    elif not self.aliado_en_competencia_activa(codigo_aliado) and not self.tiene_competencia_pendiente(codigo_aliado):
                        self._solicitar_competencia_por_score(codigo_aliado)
                elif umbral is not None and score_nuevo >= umbral:
                    self._cancelar_competencia_pendiente(codigo_aliado, 'score_recuperado')
                return {'status': 'success', 'aplicado': delta_real, 'score_final': score_nuevo}
            except Exception as e:
                return {'status': 'error', 'message': str(e)}
            finally:
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
        """Crea una notificación persistente por cada cambio real de score."""
        if not codigo_aliado or not delta_real:
            return
        try:
            direccion = 'subió' if delta_real > 0 else 'bajó'
            puntos = f"{delta_real:+d}"
            motivo_txt = (motivo or 'actualización de reglas RUANA').strip()
            titulo = "Cambio en tu Score RUANA"
            mensaje = f"Tu score {direccion} {puntos} puntos. Motivo: {motivo_txt}."
            metadata = json.dumps({
                'delta': delta_real,
                'score_final': int(score_nuevo),
                'motivo': motivo_txt,
                'movimiento_id': movimiento_id
            }, ensure_ascii=False)
            cursor.execute("""
                INSERT INTO notificaciones_aliado (aliado_codigo, tipo, titulo, mensaje, metadata, leida)
                VALUES (?, 'score_change', ?, ?, ?, 0)
            """, (codigo_aliado, titulo, mensaje, metadata))
        except Exception:
            # No romper el flujo principal de score si falla la notificación
            return

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
        """Lee umbral_competencia desde config/ruana_reglas_v1.json. Por defecto 15."""
        try:
            config_path = Path(__file__).resolve().parent.parent / 'config' / 'ruana_reglas_v1.json'
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return int(data.get('umbral_competencia', 15))
        except Exception:
            pass
        return 15

    def _get_duracion_competencia_dias(self) -> int:
        """Lee duracion_competencia_dias desde config. Por defecto 30."""
        try:
            config_path = Path(__file__).resolve().parent.parent / 'config' / 'ruana_reglas_v1.json'
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return int(data.get('duracion_competencia_dias', 30))
        except Exception:
            pass
        return 30

    def _get_score_reinicio_competencia(self) -> int:
        """Score asignado al perdedor de una competencia (grupo en formación). Por defecto 50."""
        try:
            config_path = Path(__file__).resolve().parent.parent / 'config' / 'ruana_reglas_v1.json'
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return int(data.get('score_reinicio_competencia', 50))
        except Exception:
            pass
        return 50

    def _get_purga_meses_sin_ganar(self) -> int:
        """Lee purga_mensual_meses_sin_ganar desde config. Por defecto 3."""
        try:
            config_path = Path(__file__).resolve().parent.parent / 'config' / 'ruana_reglas_v1.json'
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return int(data.get('purga_mensual_meses_sin_ganar', 3))
        except Exception:
            pass
        return 3

    def _get_purga_score_bajo_umbral(self) -> int:
        """Lee purga_score_bajo_umbral desde config. Por defecto 40."""
        try:
            config_path = Path(__file__).resolve().parent.parent / 'config' / 'ruana_reglas_v1.json'
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return int(data.get('purga_score_bajo_umbral', 40))
        except Exception:
            pass
        return 40

    def _get_apoyo_pct(self) -> float:
        """Lee apoyo_pct desde config/ruana_reglas_v1.json. Por defecto 12.0 (%)."""
        try:
            config_path = Path(__file__).resolve().parent.parent / 'config' / 'ruana_reglas_v1.json'
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return float(data.get('apoyo_pct', 12.0))
        except Exception:
            pass
        return 12.0

    def _get_ruana_pago_defaults(self) -> Tuple[Optional[str], Optional[str]]:
        """Lee qr_paypal_path y bizum_num por defecto de RUANA desde config (para notificaciones Apoyo RUANA)."""
        try:
            config_path = Path(__file__).resolve().parent.parent / 'config' / 'ruana_reglas_v1.json'
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                qr = (data.get('qr_paypal_path') or '').strip() or None
                bizum = (data.get('bizum_num') or '').strip() or None
                return (qr, bizum)
        except Exception:
            pass
        return (None, None)

    def obtener_metodos_pago_ruana(self) -> Dict[str, Any]:
        """Devuelve los metodos de pago configurados para cobrar Apoyo RUANA."""
        defaults = {
            'bizum_num': '642868261',
            'iban': 'ES8915830001119028625152',
            'qr_revolut_path': '',
        }
        try:
            config_path = Path(__file__).resolve().parent.parent / 'config' / 'ruana_reglas_v1.json'
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                defaults['bizum_num'] = (data.get('bizum_num') or defaults['bizum_num']).strip()
                defaults['iban'] = (data.get('iban') or defaults['iban']).strip()
                defaults['qr_revolut_path'] = (data.get('qr_revolut_path') or data.get('qr_paypal_path') or '').strip()
        except Exception:
            pass
        return defaults

    def actualizar_metodos_pago_ruana(self, valores: Dict[str, Any], admin_codigo: Optional[str] = None) -> Dict[str, Any]:
        """Actualiza Bizum, IBAN y/o QR Revolut en config/ruana_reglas_v1.json."""
        permitidas = {'bizum_num', 'iban', 'qr_revolut_path'}
        cambios = {k: (v or '').strip() for k, v in (valores or {}).items() if k in permitidas}
        if not cambios:
            return {'status': 'error', 'message': 'No hay metodos de pago validos para actualizar'}
        try:
            config_path = Path(__file__).resolve().parent.parent / 'config' / 'ruana_reglas_v1.json'
            if not config_path.exists():
                return {'status': 'error', 'message': 'Archivo de reglas no encontrado'}
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            data.update(cambios)
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            self.registrar_evento_sistema(
                'actualizar_metodos_pago',
                'Metodos de pago RUANA actualizados',
                actor_tipo='admin',
                actor_codigo=admin_codigo,
                metadata={'claves': sorted(cambios.keys())},
            )
            return {'status': 'success', 'message': 'Metodos de pago actualizados', 'metodos': self.obtener_metodos_pago_ruana()}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

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
        """
        Orquestador sin intervención admin: finaliza vencidas, resuelve abandonos
        e intenta iniciar competencias pendientes de retador.
        """
        finalizadas = self.finalizar_competencia_activas_vencidas()
        abandonos = self._sanear_competencias_participantes_ausentes()
        pendientes = self._procesar_competencias_pendientes()
        return {
            'finalizadas': len(finalizadas),
            'abandonos_resueltos': len(abandonos),
            'pendientes_iniciadas': len(pendientes),
        }

    def _solicitar_competencia_por_score(self, codigo_aliado: str) -> Optional[Dict[str, Any]]:
        """Intenta iniciar competencia; si no hay retador, encola pendiente."""
        if self.aliado_en_competencia_activa(codigo_aliado):
            return None
        if self.tiene_competencia_pendiente(codigo_aliado):
            return None
        result = self._iniciar_competencia_si_procede(codigo_aliado)
        if result:
            self._marcar_competencia_pendiente_resuelta(codigo_aliado, 'iniciada')
            return result
        self._registrar_competencia_pendiente(codigo_aliado)
        return None

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
        codigo = (codigo_aliado or '').strip()
        if not codigo:
            return
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE competencia_pendiente SET estado = 'cancelada' "
                    "WHERE aliado_codigo = ? AND estado = 'pendiente'",
                    (codigo,),
                )
                conn.commit()
                if cursor.rowcount:
                    try:
                        self.registrar_evento_sistema(
                            'competencia_pendiente_cancelada',
                            f'Pendiente cancelada para {codigo}: {motivo}',
                            actor_tipo='sistema',
                            metadata={'aliado_codigo': codigo, 'motivo': motivo},
                        )
                    except Exception:
                        pass
            except Exception:
                pass
            finally:
                conn.close()

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
        codigo = (codigo_aliado or '').strip()
        if not codigo:
            return False
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT 1 FROM competencia_pendiente WHERE aliado_codigo = ? AND estado = 'pendiente' LIMIT 1",
                    (codigo,),
                )
                return cursor.fetchone() is not None
            except Exception:
                return False
            finally:
                conn.close()

    def _procesar_competencias_pendientes(
        self, codigo_postal: Optional[str] = None, oficio: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Intenta iniciar competencias en cola cuando ya hay retador y el titular sigue bajo umbral."""
        umbral = self._get_umbral_competencia() or 15
        iniciadas: List[Dict[str, Any]] = []
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                q = "SELECT id, aliado_codigo, grupo_id, oficio, codigo_postal FROM competencia_pendiente WHERE estado = 'pendiente'"
                params: List[Any] = []
                if codigo_postal:
                    q += " AND codigo_postal = ?"
                    params.append(codigo_postal.strip())
                if oficio:
                    q += " AND oficio = ?"
                    params.append(oficio.strip())
                q += " ORDER BY creado_en ASC"
                cursor.execute(q, params)
                pendientes = [dict(r) for r in cursor.fetchall()]
            except Exception:
                return []
            finally:
                conn.close()
        for p in pendientes:
            codigo = p.get('aliado_codigo')
            aliado = self.obtener_aliado_por_codigo(codigo)
            if not aliado or (aliado.get('estado') or '') != 'activo':
                self._cancelar_competencia_pendiente(codigo, 'titular_no_activo')
                continue
            score = int(aliado.get('score') or 0)
            if score >= umbral:
                self._cancelar_competencia_pendiente(codigo, 'score_recuperado')
                continue
            if self.aliado_en_competencia_activa(codigo):
                self._marcar_competencia_pendiente_resuelta(codigo, 'iniciada')
                continue
            retador = self._buscar_retador(
                codigo, p.get('grupo_id'), p.get('oficio', ''), score, p.get('codigo_postal', '')
            )
            if not retador:
                continue
            result = self._iniciar_competencia_si_procede(codigo)
            if result:
                self._marcar_competencia_pendiente_resuelta(codigo, 'iniciada')
                iniciadas.append({'aliado_codigo': codigo, **result})
        return iniciadas

    def aliado_en_competencia_activa(self, codigo_aliado: str) -> bool:
        codigo = (codigo_aliado or '').strip()
        if not codigo:
            return False
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                col = self._columna_retador_competencia(cursor)
                cursor.execute(
                    f"SELECT 1 FROM competencia WHERE estado = 'activa' "
                    f"AND (aliado_original_codigo = ? OR {col} = ?) LIMIT 1",
                    (codigo, codigo),
                )
                return cursor.fetchone() is not None
            except Exception:
                return False
            finally:
                conn.close()

    @staticmethod
    def _dias_restantes_competencia(fecha_fin_prevista: Any) -> int:
        if not fecha_fin_prevista:
            return 0
        try:
            fi_str = str(fecha_fin_prevista)[:19].replace('T', ' ')
            fin = datetime.strptime(fi_str, '%Y-%m-%d %H:%M:%S')
        except Exception:
            try:
                fin = datetime.fromisoformat(str(fecha_fin_prevista)[:19])
            except Exception:
                return 0
        delta = fin - datetime.now()
        return max(0, int(delta.total_seconds() // 86400))

    def obtener_competencia_info_aliado(self, codigo_aliado: str) -> Optional[Dict[str, Any]]:
        """Info de competencia activa para el panel aliado (rol, fechas, días restantes)."""
        codigo = (codigo_aliado or '').strip()
        if not codigo:
            return None
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                col_ret = self._columna_retador_competencia(cursor)
                cursor.execute(
                    f"""
                    SELECT c.id, c.grupo_id, c.oficio, c.aliado_original_codigo, c.{col_ret} AS retador_codigo,
                           c.fecha_inicio, c.fecha_fin_prevista, c.estado, g.nombre AS grupo_nombre
                    FROM competencia c
                    LEFT JOIN grupos g ON g.id = c.grupo_id
                    WHERE c.estado = 'activa'
                      AND (c.aliado_original_codigo = ? OR c.{col_ret} = ?)
                    LIMIT 1
                    """,
                    (codigo, codigo),
                )
                row = cursor.fetchone()
                if not row:
                    if self.tiene_competencia_pendiente(codigo):
                        return {
                            'en_competencia': False,
                            'competencia_pendiente': True,
                            'rol': 'titular_pendiente',
                            'mensaje': 'Esperando retador para iniciar la competencia.',
                        }
                    return None
                r = dict(row)
                rol = 'titular' if r.get('aliado_original_codigo') == codigo else 'retador'
                dias = self._dias_restantes_competencia(r.get('fecha_fin_prevista'))
                return {
                    'en_competencia': True,
                    'competencia_pendiente': False,
                    'competencia_id': r.get('id'),
                    'rol': rol,
                    'oficio': r.get('oficio') or '',
                    'grupo_id': r.get('grupo_id'),
                    'grupo_nombre': r.get('grupo_nombre') or '',
                    'fecha_inicio': r.get('fecha_inicio'),
                    'fecha_fin_prevista': r.get('fecha_fin_prevista'),
                    'dias_restantes': dias,
                    'contrincante_codigo': r.get('retador_codigo') if rol == 'titular' else r.get('aliado_original_codigo'),
                }
            except Exception:
                return None
            finally:
                conn.close()

    def listar_competencias_pendientes_admin(self) -> List[Dict[str, Any]]:
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT p.id, p.aliado_codigo, p.grupo_id, p.oficio, p.codigo_postal,
                           p.score_al_crear, p.creado_en, a.nombre AS aliado_nombre, g.nombre AS grupo_nombre
                    FROM competencia_pendiente p
                    JOIN aliados a ON a.codigo = p.aliado_codigo
                    LEFT JOIN grupos g ON g.id = p.grupo_id
                    WHERE p.estado = 'pendiente'
                    ORDER BY p.creado_en ASC
                """)
                return [dict(row) for row in cursor.fetchall()]
            except Exception:
                return []
            finally:
                conn.close()

    def listar_competencias_historial_admin(self, limite: int = 50) -> List[Dict[str, Any]]:
        limite = max(1, min(int(limite or 50), 200))
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                col_ret = self._columna_retador_competencia(cursor)
                cursor.execute(
                    f"""
                    SELECT c.id, c.grupo_id, c.oficio, c.aliado_original_codigo, c.{col_ret} AS retador_codigo,
                           c.fecha_inicio, c.fecha_fin_prevista, c.fecha_cierre, c.ganador_codigo,
                           c.score_titular_inicio, c.score_retador_inicio,
                           c.score_titular_final, c.score_retador_final,
                           t.nombre AS titular_nombre, r.nombre AS retador_nombre, g.nombre AS grupo_nombre
                    FROM competencia c
                    JOIN aliados t ON t.codigo = c.aliado_original_codigo
                    JOIN aliados r ON r.codigo = c.{col_ret}
                    LEFT JOIN grupos g ON g.id = c.grupo_id
                    WHERE c.estado = 'finalizada'
                    ORDER BY COALESCE(c.fecha_cierre, c.fecha_fin_prevista) DESC
                    LIMIT ?
                    """,
                    (limite,),
                )
                return [dict(row) for row in cursor.fetchall()]
            except Exception:
                return []
            finally:
                conn.close()

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
        """Devuelve la competencia activa para ese grupo y oficio, o None."""
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cols = self._columnas_compat_competencia(cursor)
                cursor.execute("""
                    SELECT id, grupo_id, oficio, aliado_original_codigo,
                           """ + cols["retador_codigo"] + """ AS retador_codigo,
                           """ + cols["retador_grupo_anterior_id"] + """ AS retador_grupo_anterior_id,
                           fecha_inicio, fecha_fin_prevista, estado
                    FROM competencia WHERE grupo_id = ? AND oficio = ? AND estado = 'activa' LIMIT 1
                """, (grupo_id, (oficio or '').strip()))
                row = cursor.fetchone()
                return dict(row) if row else None
            except Exception:
                return None
            finally:
                conn.close()

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
        """
        Lista competencias activas para el panel admin.
        Incluye datos de titular, suplente, grupo origen, scores y tiempo en competencia.
        Ordenado por fecha_inicio ascendente (más antiguas arriba).
        """
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cols = self._columnas_compat_competencia(cursor)
                cursor.execute("""
                    SELECT c.id, c.grupo_id, c.oficio, c.aliado_original_codigo,
                           c.""" + cols["retador_codigo"] + """ AS retador_codigo,
                           c.""" + cols["retador_grupo_anterior_id"] + """ AS retador_grupo_anterior_id,
                           c.fecha_inicio, c.fecha_fin_prevista,
                           c.score_titular_inicio, c.""" + cols["score_retador_inicio"] + """ AS score_retador_inicio,
                           c.score_titular_actual, c.""" + cols["score_retador_actual"] + """ AS score_retador_actual, c.motivo,
                           t.id AS titular_id, t.nombre AS titular_nombre, t.score AS titular_score_actual,
                           s.id AS retador_id, s.nombre AS retador_nombre, s.score AS retador_score_actual,
                           g.nombre AS grupo_nombre, g_origen.nombre AS grupo_origen_nombre
                    FROM competencia c
                    JOIN aliados t ON t.codigo = c.aliado_original_codigo
                    JOIN aliados s ON s.codigo = c.""" + cols["retador_codigo"] + """
                    JOIN grupos g ON g.id = c.grupo_id
                    LEFT JOIN grupos g_origen ON g_origen.id = c.""" + cols["retador_grupo_anterior_id"] + """
                    WHERE c.estado = 'activa'
                    ORDER BY c.fecha_inicio ASC
                """)
                rows = cursor.fetchall()
                now = datetime.now()
                resultado = []
                for row in rows:
                    r = dict(row)
                    fecha_inicio = r.get('fecha_inicio')
                    tiempo_horas = 0.0
                    if fecha_inicio:
                        try:
                            fi_str = str(fecha_inicio)[:19].replace('T', ' ')
                            fi = datetime.strptime(fi_str, '%Y-%m-%d %H:%M:%S')
                            delta = now - fi
                            tiempo_horas = delta.total_seconds() / 3600.0
                        except Exception:
                            try:
                                fi = datetime.fromisoformat(str(fecha_inicio)[:19])
                                delta = now - fi
                                tiempo_horas = delta.total_seconds() / 3600.0
                            except Exception:
                                pass
                    score_tit_actual = r.get('titular_score_actual')
                    if score_tit_actual is not None:
                        score_tit_actual = int(score_tit_actual)
                    else:
                        score_tit_actual = r.get('score_titular_actual')
                        if score_tit_actual is not None:
                            score_tit_actual = int(score_tit_actual)
                        else:
                            score_tit_actual = r.get('score_titular_inicio', 0)
                    score_ret_actual = r.get('retador_score_actual')
                    if score_ret_actual is not None:
                        score_ret_actual = int(score_ret_actual)
                    else:
                        score_ret_actual = r.get('score_retador_actual')
                        if score_ret_actual is not None:
                            score_ret_actual = int(score_ret_actual)
                        else:
                            score_ret_actual = r.get('score_retador_inicio', 0)
                    score_tit_inicio = int(r.get('score_titular_inicio') or 0)
                    score_ret_inicio = int(r.get('score_retador_inicio') or 0)
                    resultado.append({
                        'id': r.get('id'),
                        'grupo': r.get('grupo_nombre') or f"Grupo {r.get('grupo_id')}",
                        'oficio': r.get('oficio') or '',
                        'titular': {
                            'id': r.get('titular_id'),
                            'codigo': r.get('aliado_original_codigo'),
                            'nombre': r.get('titular_nombre') or '',
                            'score_actual': score_tit_actual,
                            'score_inicio': score_tit_inicio,
                        },
                        'retador': {
                            'id': r.get('retador_id'),
                            'codigo': r.get('retador_codigo'),
                            'nombre': r.get('retador_nombre') or '',
                            'grupo_origen': r.get('grupo_origen_nombre') or f"Grupo {r.get('retador_grupo_anterior_id')}" if r.get('retador_grupo_anterior_id') else '—',
                            'score_actual': score_ret_actual,
                            'score_inicio': score_ret_inicio,
                        },
                        # alias para compatibilidad con frontend existente
                        'suplente': {
                            'id': r.get('retador_id'),
                            'codigo': r.get('retador_codigo'),
                            'nombre': r.get('retador_nombre') or '',
                            'grupo_origen': r.get('grupo_origen_nombre') or f"Grupo {r.get('retador_grupo_anterior_id')}" if r.get('retador_grupo_anterior_id') else '—',
                            'score_actual': score_ret_actual,
                            'score_inicio': score_ret_inicio,
                        },
                        'fecha_inicio': fecha_inicio,
                        'fecha_fin_prevista': r.get('fecha_fin_prevista'),
                        'dias_restantes': self._dias_restantes_competencia(r.get('fecha_fin_prevista')),
                        'tiempo_en_competencia_horas': round(tiempo_horas, 1),
                        'estado': 'activa',
                        'motivo': r.get('motivo') or 'score bajo',
                    })
                return resultado
            except Exception as e:
                print(f"[RUANA] Error listando competencias activas: {e}")
                return []
            finally:
                conn.close()

    def _buscar_retador(self, codigo_aliado_en_riesgo: str, grupo_id: int, oficio: str,
                        score_actual: int, codigo_postal: str,
                        ciudad: Optional[str] = None, provincia: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Retador: mismo CP y mismo oficio. Prioridad:
        1) Aliado en lista de suplentes (estado en_espera)
        2) Aliado activo en un grupo del CP con menos profesionales
        Excluye al titular y a quien ya esté en el grupo en competencia.
        """
        del score_actual, ciudad, provincia  # compatibilidad de firma; reglas actuales no los usan
        if not oficio or not codigo_postal:
            return None
        oficio = oficio.strip()
        codigo_postal = codigo_postal.strip()
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                # 1) Suplentes en espera (mismo CP, mismo oficio)
                cursor.execute("""
                    SELECT a.codigo, a.score, a.grupo_id, a.estado, a.codigo_postal,
                           0 AS n_aliados
                    FROM aliados a
                    WHERE a.estado = 'en_espera' AND a.oficio = ? AND a.codigo_postal = ?
                      AND a.codigo != ?
                    ORDER BY a.creado_en ASC
                    LIMIT 1
                """, (oficio, codigo_postal, codigo_aliado_en_riesgo))
                row = cursor.fetchone()
                if row:
                    return dict(row)
                # 2) Activos en el CP, mismo oficio, grupo con menos profesionales
                cursor.execute("""
                    SELECT a.codigo, a.score, a.grupo_id, a.estado, g.codigo_postal,
                           (SELECT COUNT(*) FROM aliados a2
                            WHERE a2.grupo_id = a.grupo_id AND a2.estado = 'activo') AS n_aliados
                    FROM aliados a
                    JOIN grupos g ON g.id = a.grupo_id AND g.estado = 'activo'
                    WHERE a.estado = 'activo' AND a.oficio = ? AND g.codigo_postal = ?
                      AND a.codigo != ? AND (a.grupo_id IS NULL OR a.grupo_id != ?)
                    ORDER BY n_aliados ASC, a.score DESC, a.codigo
                    LIMIT 1
                """, (oficio, codigo_postal, codigo_aliado_en_riesgo, grupo_id))
                row = cursor.fetchone()
                return dict(row) if row else None
            except Exception:
                return None
            finally:
                conn.close()

    def _iniciar_competencia_si_procede(self, codigo_aliado: str) -> Optional[Dict[str, Any]]:
        """Inicia competencia si el aliado tiene grupo, oficio y existe un suplente. No mostrar scores individuales."""
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT a.grupo_id, a.oficio, a.score, g.codigo_postal, g.ciudad, g.provincia
                    FROM aliados a
                    LEFT JOIN grupos g ON g.id = a.grupo_id
                    WHERE a.codigo = ? AND a.estado = 'activo'
                """, (codigo_aliado,))
                row = cursor.fetchone()
                if not row or not row[0]:
                    return None
                grupo_id, oficio, score_actual, codigo_postal = row[0], row[1], int(row[2] or 0), row[3] or ''
                ciudad, provincia = row[4], row[5]
                if not oficio or not codigo_postal:
                    return None
                if self.competencia_activa_para_grupo_oficio(grupo_id, oficio):
                    return None
                retador = self._buscar_retador(codigo_aliado, grupo_id, oficio, score_actual, codigo_postal)
                if not retador:
                    return None
                retador_codigo = retador['codigo']
                retador_estado = (retador.get('estado') or 'activo').strip()
                retador_grupo_anterior_id = retador.get('grupo_id') if retador_estado != 'en_espera' else None
                score_titular_inicio = int(score_actual)
                score_retador_inicio = int(retador.get('score', 0) or 0)
                duracion_dias = self._get_duracion_competencia_dias()
                from datetime import timedelta
                fecha_fin = (datetime.now() + timedelta(days=duracion_dias)).strftime('%Y-%m-%d %H:%M:%S')
                cursor.execute("""
                    INSERT INTO competencia (grupo_id, oficio, aliado_original_codigo, retador_codigo, retador_grupo_anterior_id,
                        score_titular_inicio, score_retador_inicio, score_titular_actual, score_retador_actual,
                        fecha_fin_prevista, estado, motivo)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'activa', 'score bajo')
                """, (grupo_id, oficio.strip(), codigo_aliado, retador_codigo, retador_grupo_anterior_id,
                      score_titular_inicio, score_retador_inicio, score_titular_inicio, score_retador_inicio,
                      fecha_fin))
                competencia_id = int(cursor.lastrowid)
                if retador_estado == 'en_espera':
                    cursor.execute(
                        "UPDATE aliados SET estado = 'activo', grupo_id = ? WHERE codigo = ?",
                        (grupo_id, retador_codigo),
                    )
                else:
                    cursor.execute("UPDATE aliados SET grupo_id = ? WHERE codigo = ?", (grupo_id, retador_codigo))
                cursor.execute("UPDATE grupos SET estado = 'en_competencia' WHERE id = ?", (grupo_id,))
                self._avisar_grupos_cp_competencia(codigo_postal, oficio.strip(), cursor)
                self._notificar_retador_competencia_iniciada(
                    retador_codigo=retador_codigo,
                    titular_codigo=codigo_aliado,
                    oficio=oficio.strip(),
                    grupo_id=grupo_id,
                    competencia_id=competencia_id,
                    duracion_dias=duracion_dias,
                    codigo_postal=codigo_postal,
                    cursor=cursor,
                )
                self._notificar_titular_competencia_iniciada(
                    titular_codigo=codigo_aliado,
                    retador_codigo=retador_codigo,
                    oficio=oficio.strip(),
                    competencia_id=competencia_id,
                    duracion_dias=duracion_dias,
                    fecha_fin_prevista=fecha_fin,
                    cursor=cursor,
                )
                conn.commit()
                try:
                    self.registrar_evento_sistema(
                        'competencia_iniciada',
                        f'Competencia iniciada: titular {codigo_aliado} vs retador {retador_codigo} en grupo {grupo_id}',
                        actor_tipo='sistema',
                        metadata={'grupo_id': grupo_id, 'oficio': oficio.strip(), 'titular_codigo': codigo_aliado, 'retador_codigo': retador_codigo}
                    )
                except Exception:
                    pass
                # Penalización 4: -2 a padre/abuelo si un hijo/nieto entra en competencia
                try:
                    self.aplicar_penalizacion_descendiente_en_competencia(codigo_aliado, competencia_id)
                except Exception:
                    pass
                return {
                    'grupo_id': grupo_id,
                    'retador_codigo': retador_codigo,
                    'suplente_codigo': retador_codigo,  # alias compatibilidad
                    'oficio': oficio,
                    'competencia_id': competencia_id,
                }
            except Exception as e:
                try:
                    conn.rollback()
                except Exception:
                    pass
                return None
            finally:
                conn.close()

    def aplicar_penalizacion_descendiente_en_competencia(
        self, codigo_titular: str, competencia_id: int
    ) -> List[Dict[str, Any]]:
        """
        Penalización 4: si un hijo o nieto (linaje via invitado_por_codigo) entra en
        competencia, -2 al padre (gen1) y -2 al abuelo (gen2). Una vez por competencia.
        No aplica a admin/sistema. El suplente no dispara esta regla.
        """
        codigo_titular = (codigo_titular or '').strip()
        if not codigo_titular or not competencia_id:
            return []
        aplicados: List[Dict[str, Any]] = []
        for ancestro, gen in self.ancestros_referidos_para_score(codigo_titular, max_generaciones=2):
            motivo = f'descendiente_entra_competencia_gen{gen}_{int(competencia_id)}'
            if self._ya_aplicado_motivo_score(ancestro, motivo):
                continue
            result = self.aplicar_cambio_score(ancestro, -2, motivo)
            aplicados.append({
                'codigo': ancestro,
                'generacion': gen,
                'motivo': motivo,
                'result': result,
            })
        return aplicados

    def finalizar_competencia_activas_vencidas(self) -> List[Dict[str, Any]]:
        """Finaliza competencias cuya fecha_fin_prevista ha pasado. Mayor score permanece, el otro sale del grupo."""
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, grupo_id, oficio, aliado_original_codigo, retador_codigo, retador_grupo_anterior_id
                    FROM competencia WHERE estado = 'activa' AND fecha_fin_prevista <= datetime('now')
                """)
                filas = cursor.fetchall()
            except Exception:
                return []
            finally:
                conn.close()
        resultados = []
        for row in filas:
            cid, grupo_id, oficio, orig, supl, prev_id = row[0], row[1], row[2], row[3], row[4], row[5]
            r = self._finalizar_una_competencia(cid, grupo_id, orig, supl, prev_id)
            resultados.append({'competencia_id': cid, **r})
        return resultados

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
        """
        Compara scores al cierre; el mayor permanece en el grupo principal.
        El perdedor pasa a grupo en formación con score reiniciado (50).
        Segunda derrota acumulada → expulsado.
        """
        score_reinicio = self._get_score_reinicio_competencia()
        perdedor_expulsado = False
        ganador = ganador_forzado
        score_orig = score_ret = 0
        oficio = ''
        try:
            conn = self._connect()
            cursor = conn.cursor()
            cursor.execute("SELECT score, oficio FROM aliados WHERE codigo = ?", (aliado_original_codigo,))
            s1 = cursor.fetchone()
            cursor.execute("SELECT score FROM aliados WHERE codigo = ?", (retador_codigo,))
            s2 = cursor.fetchone()
            score_orig = int(s1[0]) if s1 and s1[0] is not None else 0
            score_ret = int(s2[0]) if s2 and s2[0] is not None else 0
            oficio = (s1[1] or '').strip() if s1 and len(s1) > 1 else ''
            if not ganador:
                ganador = aliado_original_codigo if score_orig >= score_ret else retador_codigo
            perdedor = retador_codigo if ganador == aliado_original_codigo else aliado_original_codigo

            cursor.execute("SELECT codigo_postal, ciudad, provincia FROM grupos WHERE id = ?", (grupo_id,))
            g = cursor.fetchone()
            codigo_postal = (g[0] or '') if g else ''
            ciudad = (g[1] or '') if g and len(g) > 1 else ''
            provincia = (g[2] or '') if g and len(g) > 2 else ''

            cursor.execute(
                "UPDATE aliados SET grupo_id = ? WHERE codigo = ?",
                (grupo_id, ganador),
            )

            cursor.execute(
                "SELECT COALESCE(derrotas_competencia, 0) FROM aliados WHERE codigo = ?",
                (perdedor,),
            )
            derrotas_prev = int((cursor.fetchone() or [0])[0] or 0)

            grupo_formacion = None
            if codigo_postal and oficio:
                grupo_formacion = self.buscar_grupo_formacion_en_cp(codigo_postal, oficio)
                if not grupo_formacion and self.contar_grupos_activos_por_cp(codigo_postal) < MAX_GRUPOS_POR_CP:
                    grupo_formacion = self.crear_grupo_en_cp(codigo_postal, ciudad, provincia)

            if grupo_formacion and isinstance(grupo_formacion, dict) and grupo_formacion.get('id'):
                gid_perdedor = grupo_formacion['id']
                if gid_perdedor == grupo_id:
                    grupo_alt = self.buscar_grupo_formacion_en_cp(codigo_postal, oficio)
                    gid_perdedor = grupo_alt['id'] if grupo_alt and grupo_alt.get('id') != grupo_id else None
                if gid_perdedor and gid_perdedor != grupo_id:
                    cursor.execute(
                        """UPDATE aliados SET grupo_id = ?, score = ?,
                           derrotas_competencia = COALESCE(derrotas_competencia, 0) + 1,
                           actualizado_en = CURRENT_TIMESTAMP WHERE codigo = ?""",
                        (gid_perdedor, score_reinicio, perdedor),
                    )
                else:
                    cursor.execute(
                        """UPDATE aliados SET grupo_id = NULL, score = ?,
                           derrotas_competencia = COALESCE(derrotas_competencia, 0) + 1,
                           actualizado_en = CURRENT_TIMESTAMP WHERE codigo = ?""",
                        (score_reinicio, perdedor),
                    )
            else:
                cursor.execute(
                    """UPDATE aliados SET grupo_id = NULL, score = ?,
                       derrotas_competencia = COALESCE(derrotas_competencia, 0) + 1,
                       actualizado_en = CURRENT_TIMESTAMP WHERE codigo = ?""",
                    (score_reinicio, perdedor),
                )

            cursor.execute(
                "UPDATE aliados SET estado = 'expulsado' WHERE codigo = ? AND COALESCE(derrotas_competencia, 0) >= 2",
                (perdedor,),
            )
            perdedor_expulsado = derrotas_prev + 1 >= 2

            self._notificar_derrota_competencia(
                aliado_codigo=perdedor,
                oficio=oficio,
                competencia_id=competencia_id,
                score_reinicio=score_reinicio,
                expulsado=perdedor_expulsado,
                cursor=cursor,
            )
            self._notificar_ganador_competencia(ganador, oficio, competencia_id, cursor=cursor)

            cursor.execute(
                """UPDATE competencia SET estado = 'finalizada', ganador_codigo = ?,
                   score_titular_final = ?, score_retador_final = ?,
                   score_titular_actual = ?, score_retador_actual = ?,
                   fecha_cierre = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (ganador, score_orig, score_ret, score_orig, score_ret, competencia_id),
            )
            cursor.execute("UPDATE grupos SET estado = 'activo' WHERE id = ?", (grupo_id,))
            conn.commit()

            if retador_grupo_anterior_id and perdedor == retador_codigo:
                self.procesar_viabilidad_grupo(retador_grupo_anterior_id)
            self.procesar_viabilidad_grupo(grupo_id)

            try:
                self.registrar_evento_sistema(
                    'competencia_finalizada',
                    f'Competencia {competencia_id} cerrada ({motivo_cierre}): ganador {ganador}',
                    actor_tipo='sistema',
                    metadata={
                        'competencia_id': competencia_id,
                        'ganador': ganador,
                        'perdedor': perdedor,
                        'motivo_cierre': motivo_cierre,
                        'score_titular': score_orig,
                        'score_retador': score_ret,
                    },
                )
            except Exception:
                pass

            return {
                'status': 'ok',
                'ganador_codigo': ganador,
                'perdedor_codigo': perdedor,
                'perdedor_expulsado': perdedor_expulsado,
                'score_reinicio': score_reinicio,
                'motivo_cierre': motivo_cierre,
            }
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            return {'status': 'error', 'message': str(e)}
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def obtener_avisos_grupo(self, grupo_id: int, tipo: Optional[str] = None) -> List[Dict[str, Any]]:
        """Avisos del grupo (ej. competencia). No incluye scores individuales."""
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                if tipo:
                    cursor.execute("SELECT id, grupo_id, tipo, texto, creado_en FROM avisos_grupo WHERE grupo_id = ? AND tipo = ? ORDER BY creado_en DESC", (grupo_id, tipo))
                else:
                    cursor.execute("SELECT id, grupo_id, tipo, texto, creado_en FROM avisos_grupo WHERE grupo_id = ? ORDER BY creado_en DESC", (grupo_id,))
                return [dict(row) for row in cursor.fetchall()]
            except Exception:
                return []
            finally:
                conn.close()

    def listar_aliados_en_pool(self) -> List[Dict[str, Any]]:
        """Aliados en pool = activos con exactamente 1 derrota en competencia (segunda oportunidad)."""
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, codigo, nombre, marca, oficio, codigo_postal, grupo_id, email, telefono, estado, score,
                           COALESCE(derrotas_competencia, 0) AS derrotas_competencia, creado_en, actualizado_en
                    FROM aliados
                    WHERE estado = 'activo' AND COALESCE(derrotas_competencia, 0) = 1
                    ORDER BY codigo
                """)
                return [dict(row) for row in cursor.fetchall()]
            except Exception:
                return []
            finally:
                conn.close()

    def _gano_competencia_ultimos_meses(self, codigo_aliado: str, meses: int) -> bool:
        """True si el aliado ganó al menos una competencia en los últimos N meses (por fecha_fin_prevista)."""
        if not codigo_aliado or meses < 1:
            return False
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT 1 FROM competencia
                    WHERE estado = 'finalizada' AND ganador_codigo = ?
                    AND date(fecha_fin_prevista) >= date('now', ?)
                    LIMIT 1
                """, (codigo_aliado, f'-{meses} months'))
                return cursor.fetchone() is not None
            except Exception:
                return False
            finally:
                conn.close()

    def purga_mensual(self) -> Dict[str, Any]:
        """
        Purga mensual de calidad: 1) Finaliza competencias vencidas. 2) Aliados en pool que no ganan en N meses
        o mantienen score persistentemente bajo → expulsión temporal (estado = suspendido_temporal).
        No permite acumulación indefinida en el pool.
        """
        resultados_finalizar = self.finalizar_competencia_activas_vencidas()
        meses_sin_ganar = self._get_purga_meses_sin_ganar()
        umbral_score_bajo = self._get_purga_score_bajo_umbral()
        pool = self.listar_aliados_en_pool()
        expulsados_temporal = []
        for aliado in pool:
            codigo = aliado.get('codigo')
            if not codigo:
                continue
            score = int(aliado.get('score') or 0)
            gano_reciente = self._gano_competencia_ultimos_meses(codigo, meses_sin_ganar)
            score_bajo_persistente = score < umbral_score_bajo
            if not gano_reciente or score_bajo_persistente:
                expulsados_temporal.append({
                    'codigo': codigo,
                    'motivo': 'sin_ganar_3_meses' if not gano_reciente else 'score_bajo_persistente',
                    'score': score,
                })
        if expulsados_temporal:
            with self._lock:
                try:
                    conn = self._connect()
                    cursor = conn.cursor()
                    for item in expulsados_temporal:
                        cursor.execute(
                            "UPDATE aliados SET estado = 'suspendido_temporal', actualizado_en = CURRENT_TIMESTAMP WHERE codigo = ?",
                            (item['codigo'],)
                        )
                    conn.commit()
                except Exception as e:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    return {
                        'status': 'error',
                        'message': str(e),
                        'competencias_finalizadas': len(resultados_finalizar),
                        'detalle_competencias': resultados_finalizar,
                        'pool_revisado': len(pool),
                        'expulsados_temporal': 0,
                        'detalle_expulsados': [],
                    }
                finally:
                    conn.close()
        return {
            'status': 'ok',
            'competencias_finalizadas': len(resultados_finalizar),
            'detalle_competencias': resultados_finalizar,
            'pool_revisado': len(pool),
            'expulsados_temporal': len(expulsados_temporal),
            'detalle_expulsados': expulsados_temporal,
        }

    def aplicar_penalizaciones_contactos_abiertos(self, codigo_aliado: str) -> None:
        """
        Aplica penalizaciones por contactos sin cerrar: 7 días -2, 21 días -5.
        Solo aplica una vez por contacto y por tipo (registrado en contacto_penalizaciones_aplicadas).
        """
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                # Contactos abiertos donde el aliado es solicitante o profesional
                cursor.execute("""
                    SELECT id, solicitante_codigo, profesional_codigo,
                           COALESCE(creado_en, actualizado_en) as ref_fecha
                    FROM contactos_ruana
                    WHERE estado IN ('iniciado', 'aceptado', 'trabajo_en_progreso')
                      AND (solicitante_codigo = ? OR profesional_codigo = ?)
                """, (codigo_aliado, codigo_aliado))
                for row in cursor.fetchall():
                    cid, sol, prof, ref = row
                    ref_ts = ref or datetime.now().isoformat()
                    try:
                        from datetime import datetime as dt
                        d = dt.fromisoformat(ref_ts.replace('Z', '+00:00'))
                        if d.tzinfo:
                            d = d.replace(tzinfo=None)
                    except Exception:
                        d = datetime.now()
                    dias = (datetime.now() - d).days
                    for tipo, umbral, penalizacion in [('21d', 21, -5), ('7d', 7, -2)]:
                        if dias < umbral:
                            continue
                        cursor.execute("""
                            SELECT 1 FROM contacto_penalizaciones_aplicadas
                            WHERE contacto_id = ? AND tipo = ?
                        """, (cid, tipo))
                        if cursor.fetchone():
                            continue
                        self.aplicar_cambio_score(codigo_aliado, penalizacion, f'contacto_sin_cerrar_{tipo}')
                        cursor.execute("""
                            INSERT OR IGNORE INTO contacto_penalizaciones_aplicadas (contacto_id, tipo)
                            VALUES (?, ?)
                        """, (cid, tipo))
                        conn.commit()
            except Exception as e:
                pass
            finally:
                conn.close()
        # Penalización 5: chat sin respuesta ≥ 48 h
        try:
            self.aplicar_penalizacion_chat_sin_respuesta_48h(codigo_aliado)
        except Exception:
            pass
        # Penalización 6: semana(s) sin acceso a la app
        try:
            self.aplicar_penalizacion_sin_acceso_semanal(codigo_aliado)
        except Exception:
            pass
        # Penalización 9: sin comprobante de Apoyo ≥ 3 días
        try:
            self.aplicar_penalizacion_comprobante_apoyo_3d(codigo_aliado)
        except Exception:
            pass

    def aplicar_penalizacion_comprobante_apoyo_3d(self, codigo_aliado: str) -> None:
        """
        Penalización 9: Apoyo RUANA generado sin subir comprobante ≥ 3 días → -3
        al profesional. Reloj desde fecha_cierre. Solo estado_pago=pendiente_pago
        sin comprobante_ruta. Una vez por contacto (tipo comprobante_3d).
        """
        codigo_aliado = (codigo_aliado or '').strip()
        if not codigo_aliado:
            return
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, fecha_cierre
                    FROM contactos_ruana
                    WHERE profesional_codigo = ?
                      AND estado = 'trabajo_cerrado'
                      AND COALESCE(apoyo_ruana, 0) > 0
                      AND estado_pago = 'pendiente_pago'
                      AND (comprobante_ruta IS NULL OR TRIM(COALESCE(comprobante_ruta, '')) = '')
                      AND fecha_cierre IS NOT NULL
                """, (codigo_aliado,))
                filas = cursor.fetchall()
                for row in filas:
                    cid, fecha_cierre = row[0], row[1]
                    ref = self._parse_timestamp(fecha_cierre)
                    if not ref:
                        continue
                    dias = (datetime.now() - ref).days
                    if dias < 3:
                        continue
                    cursor.execute("""
                        SELECT 1 FROM contacto_penalizaciones_aplicadas
                        WHERE contacto_id = ? AND tipo = 'comprobante_3d'
                    """, (cid,))
                    if cursor.fetchone():
                        continue
                    motivo = f'comprobante_apoyo_3d_{int(cid)}'
                    if self._ya_aplicado_motivo_score(codigo_aliado, motivo):
                        continue
                    result = self.aplicar_cambio_score(codigo_aliado, -3, motivo)
                    if result.get('status') != 'success' or int(result.get('aplicado') or 0) == 0:
                        continue
                    cursor.execute("""
                        INSERT OR IGNORE INTO contacto_penalizaciones_aplicadas (contacto_id, tipo)
                        VALUES (?, 'comprobante_3d')
                    """, (cid,))
                    conn.commit()
            except Exception:
                pass
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

    # Estados de cierre adecuado: no aplicar penalización 5 (chat 48h)
    _ESTADOS_CIERRE_ADECUADO_CHAT = (
        'trabajo_cerrado', 'no_concretado', 'cerrado_no_concretado',
    )

    def aplicar_penalizacion_chat_sin_respuesta_48h(self, codigo_aliado: str) -> None:
        """
        Penalización 5: conversación con mensajes dejada sin respuesta ≥ 48 h → -2
        al aliado que no respondió (el que no es el último emisor).

        No se aplica si el encargo/chat se cerró de forma adecuada:
        - estado en trabajo_cerrado / no_concretado / cerrado_no_concretado
        - o ambas partes dieron por terminado el chat (contacto_panel_oculto)
        Sin mensajes no aplica. Una vez por contacto (tipo chat_48h).
        """
        codigo_aliado = (codigo_aliado or '').strip()
        if not codigo_aliado:
            return
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT c.id, c.solicitante_codigo, c.profesional_codigo, c.estado
                    FROM contactos_ruana c
                    WHERE (c.solicitante_codigo = ? OR c.profesional_codigo = ?)
                      AND c.estado IN ('iniciado', 'aceptado', 'trabajo_en_progreso', 'en_conversacion')
                """, (codigo_aliado, codigo_aliado))
                filas = cursor.fetchall()
                for row in filas:
                    cid, sol, prof, estado = row[0], row[1], row[2], (row[3] or '').strip()
                    if estado in self._ESTADOS_CIERRE_ADECUADO_CHAT:
                        continue
                    # Ambas partes dieron por terminado el chat → no penalizar
                    cursor.execute(
                        "SELECT COUNT(*) FROM contacto_panel_oculto WHERE contacto_id = ?",
                        (cid,),
                    )
                    if int((cursor.fetchone() or [0])[0] or 0) >= 2:
                        continue
                    cursor.execute("""
                        SELECT emisor_codigo, creado_en FROM chat_mensajes
                        WHERE contacto_id = ?
                        ORDER BY creado_en DESC, id DESC LIMIT 1
                    """, (cid,))
                    ultimo = cursor.fetchone()
                    if not ultimo:
                        continue  # sin mensajes → no hay "quién debía responder"
                    emisor_ultimo = str(ultimo[0] or '').strip()
                    if not emisor_ultimo or emisor_ultimo == codigo_aliado:
                        continue  # este aliado respondió el último (o vacío)
                    # Debe ser la otra parte del contacto
                    partes = {str(sol or '').strip(), str(prof or '').strip()}
                    if codigo_aliado not in partes or emisor_ultimo not in partes:
                        continue
                    ref = self._parse_timestamp(ultimo[1])
                    if not ref or not self._chat_esta_expirado(ref):
                        continue  # aún dentro de las 48 h
                    cursor.execute("""
                        SELECT 1 FROM contacto_penalizaciones_aplicadas
                        WHERE contacto_id = ? AND tipo = 'chat_48h'
                    """, (cid,))
                    if cursor.fetchone():
                        continue
                    motivo = f'chat_sin_respuesta_48h_{int(cid)}'
                    if self._ya_aplicado_motivo_score(codigo_aliado, motivo):
                        continue
                    self.aplicar_cambio_score(codigo_aliado, -2, motivo)
                    cursor.execute("""
                        INSERT OR IGNORE INTO contacto_penalizaciones_aplicadas (contacto_id, tipo)
                        VALUES (?, 'chat_48h')
                    """, (cid,))
                    conn.commit()
            except Exception:
                pass
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

    def contar_referidos_por_codigo(self, codigo_aliado: str) -> int:
        """Cuenta hijos directos del linaje (invitado_por_codigo; une referidos por compatibilidad)."""
        codigo_aliado = (codigo_aliado or '').strip()
        if not codigo_aliado:
            return 0
        try:
            self.backfill_invitado_por_linaje()
        except Exception:
            pass
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                if self._aliados_tiene_invitado_por(cursor):
                    cursor.execute("""
                        SELECT COUNT(*) FROM (
                            SELECT a.codigo AS codigo
                            FROM aliados a
                            WHERE a.invitado_por_codigo = ?
                              AND COALESCE(a.estado, '') NOT IN (
                                  'pendiente_completar', 'sistema', 'rechazado', 'expulsado'
                              )
                            UNION
                            SELECT r.codigo_referido AS codigo
                            FROM referidos r
                            JOIN aliados a ON a.codigo = r.codigo_referido
                            WHERE r.codigo_invitador = ?
                              AND COALESCE(a.estado, '') NOT IN (
                                  'pendiente_completar', 'sistema', 'rechazado', 'expulsado'
                              )
                        )
                    """, (codigo_aliado, codigo_aliado))
                    return cursor.fetchone()[0] or 0
                cursor.execute(
                    """
                    SELECT COUNT(*)
                    FROM referidos r
                    JOIN aliados a ON a.codigo = r.codigo_referido
                    WHERE r.codigo_invitador = ?
                      AND COALESCE(a.estado, '') NOT IN (
                          'pendiente_completar', 'sistema', 'rechazado', 'expulsado'
                      )
                    """,
                    (codigo_aliado,),
                )
                return cursor.fetchone()[0] or 0
            except Exception:
                return 0
            finally:
                conn.close()

    def _nodo_referido_resumen(self, codigo: str) -> Optional[Dict[str, Any]]:
        """Resumen de aliado para nodos del árbol de referidos."""
        aliado = self.obtener_aliado_por_codigo(codigo)
        if not aliado:
            return None
        referidos_count = self.contar_referidos_por_codigo(codigo)
        origen = self._obtener_origen_referido(codigo)
        invitador = self.obtener_invitador_de(codigo)
        especializaciones: List[str] = []
        score = aliado.get('score')
        try:
            score_val = float(score) if score is not None else 0.0
        except (TypeError, ValueError):
            score_val = 0.0
        return {
            'codigo': aliado.get('codigo') or codigo,
            'nombre': aliado.get('nombre') or '',
            'oficio': aliado.get('oficio') or '',
            'zona': aliado.get('codigo_postal') or '',
            'codigo_postal': aliado.get('codigo_postal') or '',
            'marca': aliado.get('marca') or '',
            'estado': aliado.get('estado') or 'activo',
            'score': score_val,
            'telefono': aliado.get('telefono') or '',
            'email': aliado.get('email') or '',
            'especializaciones': especializaciones,
            'referidos_count': referidos_count,
            'creado_en': aliado.get('creado_en') or '',
            'origen': origen,
            'origen_label': self.etiqueta_origen_referido(origen),
            'invitador_nombre': (invitador or {}).get('nombre') or '',
            'invitador_codigo': (invitador or {}).get('codigo') or '',
        }

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
        """Backfill: referidos desde invitaciones 5 dígitos (aliado o admin) ya completadas."""
        with self._lock:
            conn = None
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT i.codigo AS codigo_referido,
                           inv.codigo AS codigo_invitador,
                           inv.estado AS invitador_estado
                    FROM invitaciones i
                    JOIN aliados inv ON inv.id = i.invitador_aliado_id
                    JOIN aliados ref ON ref.codigo = i.codigo
                    WHERE i.invitador_aliado_id IS NOT NULL
                      AND COALESCE(ref.estado, '') NOT IN ('pendiente_completar', 'sistema')
                      AND NOT EXISTS (
                          SELECT 1 FROM referidos r WHERE r.codigo_referido = i.codigo
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
            codigo_referido = row['codigo_referido']
            codigo_invitador = row['codigo_invitador']
            if not codigo_referido or not codigo_invitador:
                continue
            origen = 'admin_invitacion' if (row['invitador_estado'] or '').strip() == 'sistema' else 'aliado'
            if self._insert_referido(codigo_referido, codigo_invitador, origen):
                sincronizados += 1
        return sincronizados

    def sincronizar_referidos_invitaciones_oficio_usadas(self) -> int:
        """Backfill: referidos desde invitaciones por oficio consumidas."""
        with self._lock:
            conn = None
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT io.codigo_referido, inv.codigo AS codigo_invitador
                    FROM invitaciones_oficio io
                    JOIN aliados inv ON inv.id = io.aliado_id
                    WHERE io.estado = 'usado'
                      AND COALESCE(io.codigo_referido, '') != ''
                      AND EXISTS (
                          SELECT 1 FROM aliados a WHERE a.codigo = io.codigo_referido
                      )
                      AND NOT EXISTS (
                          SELECT 1 FROM referidos r WHERE r.codigo_referido = io.codigo_referido
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
            if self._insert_referido(row['codigo_referido'], row['codigo_invitador'], 'oficio'):
                sincronizados += 1
        return sincronizados

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
        """
        Registra el vínculo desde invitaciones aunque la invitación ya esté marcada como usada.
        No duplica la recompensa de score.
        """
        codigo_invitacion = (codigo_invitacion or '').strip()
        nuevo_aliado_codigo = (nuevo_aliado_codigo or '').strip()
        if not codigo_invitacion or not nuevo_aliado_codigo:
            return False
        with self._lock:
            conn = None
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT i.invitador_aliado_id, inv.codigo AS codigo_invitador, inv.estado AS invitador_estado
                    FROM invitaciones i
                    JOIN aliados inv ON inv.id = i.invitador_aliado_id
                    WHERE i.codigo = ?
                """, (codigo_invitacion,))
                row = cursor.fetchone()
                if not row:
                    return False
                origen = 'admin_invitacion' if (row['invitador_estado'] or '').strip() == 'sistema' else 'aliado'
                registrado = self._insert_referido(
                    nuevo_aliado_codigo,
                    row['codigo_invitador'],
                    origen,
                )
                cursor.execute(
                    "UPDATE invitaciones SET usado = 1 WHERE codigo = ?",
                    (codigo_invitacion,),
                )
                conn.commit()
                return registrado or True
            except Exception:
                return False
            finally:
                if conn:
                    conn.close()

    def contar_total_nodos_referidos_red(self) -> int:
        """Total de aliados que participan en la red (como referido o invitador)."""
        return self.obtener_resumen_referidos_red().get('total_nodos', 0)

    def obtener_resumen_referidos_red(self) -> Dict[str, int]:
        """Resumen de la red: nodos vinculados vs aliados activos fuera de la red."""
        self.sincronizar_referidos_completo()
        with self._lock:
            conn = None
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT COUNT(DISTINCT codigo) FROM (
                        SELECT codigo_referido AS codigo FROM referidos
                        UNION
                        SELECT codigo_invitador AS codigo FROM referidos
                    )
                """)
                total_nodos = cursor.fetchone()[0] or 0
                cursor.execute("""
                    SELECT COUNT(*) FROM aliados
                    WHERE COALESCE(estado, '') NOT IN (
                        'pendiente_completar', 'sistema', 'rechazado', 'expulsado'
                    )
                """)
                total_aliados_activos = cursor.fetchone()[0] or 0
                cursor.execute("""
                    SELECT COUNT(*) FROM aliados a
                    WHERE COALESCE(a.estado, '') = 'pendiente_completar'
                       OR (
                           COALESCE(a.estado, '') NOT IN ('sistema', 'rechazado', 'expulsado')
                           AND NOT EXISTS (
                               SELECT 1 FROM referidos r
                               WHERE r.codigo_referido = a.codigo
                                  OR r.codigo_invitador = a.codigo
                           )
                       )
                """)
                aliados_fuera_red = cursor.fetchone()[0] or 0
                return {
                    'total_nodos': total_nodos,
                    'total_aliados_activos': total_aliados_activos,
                    'aliados_fuera_red': aliados_fuera_red,
                }
            except Exception:
                return {
                    'total_nodos': 0,
                    'total_aliados_activos': 0,
                    'aliados_fuera_red': 0,
                }
            finally:
                if conn:
                    conn.close()

    def aliado_puede_ver_nodo_referidos(self, codigo_sesion: str, codigo_nodo: str) -> bool:
        """True si el aliado de sesión es el nodo o un ancestro invitador suyo."""
        codigo_sesion = (codigo_sesion or '').strip()
        codigo_nodo = (codigo_nodo or '').strip()
        if not codigo_sesion or not codigo_nodo:
            return False
        if codigo_sesion == codigo_nodo:
            return True
        current = codigo_nodo
        visitados: set = set()
        while current and current not in visitados:
            invitador = self.obtener_invitador_de(current)
            if not invitador:
                return False
            current = (invitador.get('codigo') or '').strip()
            if current == codigo_sesion:
                return True
            visitados.add(current)
        return False

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
        """Busca aliados presentes en la red de referidos."""
        query = (query or '').strip()
        if not query:
            return []
        self.sincronizar_referidos_completo()
        like = f'%{query}%'
        with self._lock:
            conn = None
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT DISTINCT a.codigo
                    FROM aliados a
                    WHERE a.codigo IN (
                        SELECT codigo_referido FROM referidos
                        UNION
                        SELECT codigo_invitador FROM referidos
                    )
                    AND (
                        a.codigo LIKE ? OR a.nombre LIKE ? OR a.oficio LIKE ?
                        OR a.marca LIKE ? OR a.codigo_postal LIKE ?
                    )
                    ORDER BY a.nombre
                    LIMIT ?
                """, (like, like, like, like, like, limite))
                codigos = [row['codigo'] for row in cursor.fetchall() if row and row['codigo']]
            except Exception:
                return []
            finally:
                if conn:
                    conn.close()
        return [self._nodo_referido_resumen(c) for c in codigos if self._nodo_referido_resumen(c)]

    def listar_referidos_desde(self, desde: str) -> List[Dict[str, Any]]:
        """Referidos registrados después de un timestamp ISO (para actualización en vivo del árbol)."""
        self.sincronizar_referidos_completo()
        desde = (desde or '').strip()
        with self._lock:
            conn = None
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                if desde:
                    cursor.execute("""
                        SELECT r.codigo_referido, r.codigo_invitador, r.creado_en
                        FROM referidos r
                        WHERE datetime(r.creado_en) > datetime(?)
                        ORDER BY r.creado_en ASC
                    """, (desde,))
                else:
                    cursor.execute("""
                        SELECT r.codigo_referido, r.codigo_invitador, r.creado_en
                        FROM referidos r
                        ORDER BY r.creado_en ASC
                    """)
                rows = cursor.fetchall()
            except Exception:
                return []
            finally:
                if conn:
                    conn.close()
        cambios: List[Dict[str, Any]] = []
        for row in rows:
            codigo_referido = row['codigo_referido']
            codigo_invitador = row['codigo_invitador']
            nodo = self._nodo_referido_resumen(codigo_referido)
            if not nodo:
                nodo = {
                    'codigo': codigo_referido,
                    'nombre': codigo_referido,
                    'oficio': '—',
                    'referidos_count': 0,
                }
            invitador = self._nodo_referido_resumen(codigo_invitador)
            cambios.append({
                'codigo_referido': codigo_referido,
                'codigo_invitador': codigo_invitador,
                'referido_en': row['creado_en'],
                'nodo': nodo,
                'invitador': invitador,
            })
        return cambios

    def listar_nodos_raiz_referidos(self) -> List[Dict[str, Any]]:
        """Nodos raíz de la red (invitadores que no fueron referidos)."""
        self.sincronizar_referidos_completo()
        raices = self.listar_raices_referidos()
        nodos: List[Dict[str, Any]] = []
        for codigo in raices:
            nodo = self._nodo_referido_resumen(codigo)
            if nodo:
                nodos.append(nodo)
        return nodos

    def obtener_nodo_referidos(self, codigo: str) -> Optional[Dict[str, Any]]:
        """Nodo individual con metadatos para el árbol."""
        self.sincronizar_referidos_completo()
        return self._nodo_referido_resumen(codigo)

    def listar_referidos_directos(self, codigo_invitador: str) -> List[Dict[str, Any]]:
        """Lista aliados referidos directamente por codigo_invitador."""
        codigo_invitador = (codigo_invitador or '').strip()
        if not codigo_invitador:
            return []
        with self._lock:
            conn = None
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT COALESCE(a.codigo, r.codigo_referido) AS codigo,
                           COALESCE(a.nombre, r.codigo_referido) AS nombre,
                           COALESCE(a.oficio, '—') AS oficio,
                           COALESCE(a.codigo_postal, '') AS codigo_postal,
                           COALESCE(a.marca, '') AS marca,
                           COALESCE(a.estado, 'desconocido') AS estado,
                           COALESCE(a.score, 0) AS score,
                           COALESCE(a.telefono, '') AS telefono,
                           COALESCE(a.email, '') AS email,
                           COALESCE(a.creado_en, r.creado_en) AS creado_en,
                           r.creado_en AS referido_en,
                           COALESCE(r.origen, '') AS origen
                    FROM referidos r
                    LEFT JOIN aliados a ON a.codigo = r.codigo_referido
                    WHERE r.codigo_invitador = ?
                    ORDER BY r.creado_en ASC
                """, (codigo_invitador,))
                rows = cursor.fetchall()
                result: List[Dict[str, Any]] = []
                for row in rows:
                    item = dict(row)
                    item['zona'] = item.get('codigo_postal') or ''
                    item['referidos_count'] = self.contar_referidos_por_codigo(item['codigo'])
                    item['especializaciones'] = []
                    try:
                        item['score'] = float(item.get('score') or 0)
                    except (TypeError, ValueError):
                        item['score'] = 0.0
                    origen = (item.get('origen') or '').strip() or self._obtener_origen_referido(item['codigo'])
                    item['origen'] = origen
                    item['origen_label'] = self.etiqueta_origen_referido(origen)
                    result.append(item)
                return result
            except Exception:
                return []
            finally:
                if conn:
                    conn.close()

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
        """False para vacío, autoexclusión, códigos sistema/admin o aliados inexistentes."""
        codigo = (codigo or '').strip()
        if not codigo:
            return False
        if excluir and codigo in excluir:
            return False
        if codigo.upper().startswith('RUANA-ADMIN'):
            return False
        aliado = self.obtener_aliado_por_codigo(codigo)
        if not aliado:
            return False
        if (aliado.get('estado') or '').strip() == 'sistema':
            return False
        return True

    def ancestros_referidos_para_score(
        self,
        codigo_aliado: str,
        max_generaciones: int = 2,
        excluir: Optional[set] = None,
    ) -> List[Tuple[str, int]]:
        """
        Sube por aliados.invitado_por_codigo hasta max_generaciones.
        Devuelve [(codigo_ancestro, generacion), ...] (1 = padre, 2 = abuelo).
        Omite sistema/admin y códigos en excluir (p. ej. participantes del contacto).
        """
        codigo_aliado = (codigo_aliado or '').strip()
        if not codigo_aliado or max_generaciones < 1:
            return []
        excluir_set = set(excluir or set())
        excluir_set.add(codigo_aliado)
        resultado: List[Tuple[str, int]] = []
        actual = codigo_aliado
        vistos = {codigo_aliado}
        for generacion in range(1, max_generaciones + 1):
            aliado = self.obtener_aliado_por_codigo(actual)
            if not aliado:
                break
            padre = (aliado.get('invitado_por_codigo') or '').strip()
            if not padre or padre in vistos:
                break
            vistos.add(padre)
            if self._es_invitador_elegible_score(padre, excluir_set):
                resultado.append((padre, generacion))
            actual = padre
        return resultado

    def listar_raices_referidos(self) -> List[str]:
        """Códigos de aliados raíz: invitaron a alguien pero no fueron referidos."""
        with self._lock:
            conn = None
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT DISTINCT r.codigo_invitador
                    FROM referidos r
                    WHERE r.codigo_invitador NOT IN (SELECT codigo_referido FROM referidos)
                    ORDER BY r.codigo_invitador
                """)
                return [row[0] for row in cursor.fetchall() if row and row[0]]
            except Exception:
                return []
            finally:
                if conn:
                    conn.close()

    def obtener_arbol_referidos(self, codigo_raiz: str, max_depth: int = 8) -> Optional[Dict[str, Any]]:
        """Construye árbol recursivo de referidos desde codigo_raiz."""
        self.sincronizar_referidos_completo()
        codigo_raiz = (codigo_raiz or '').strip()
        if not codigo_raiz:
            return None
        max_depth = max(1, min(int(max_depth or 8), 50))

        def _build(codigo: str, depth: int) -> Optional[Dict[str, Any]]:
            nodo = self._nodo_referido_resumen(codigo)
            if not nodo:
                return None
            if depth >= max_depth:
                nodo['referidos'] = []
                nodo['truncado'] = True
                return nodo
            hijos = self.listar_referidos_directos(codigo)
            nodo['referidos'] = []
            for hijo in hijos:
                hijo_codigo = hijo.get('codigo')
                if not hijo_codigo:
                    continue
                sub = _build(hijo_codigo, depth + 1)
                if sub:
                    sub['referido_en'] = hijo.get('referido_en') or ''
                    nodo['referidos'].append(sub)
                else:
                    hoja = dict(hijo)
                    hoja['referidos'] = []
                    hoja['referido_en'] = hijo.get('referido_en') or ''
                    nodo['referidos'].append(hoja)
            return nodo

        return _build(codigo_raiz, 0)

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
        """
        Garantiza un aliado 'sistema' para representar al admin como invitador en referidos.
        Necesario porque referidos.codigo_invitador tiene FK a aliados(codigo).
        """
        admin_codigo = (admin_codigo or "").strip() or "RUANA-ADMIN"
        existente = self.obtener_aliado_por_codigo(admin_codigo)
        if existente:
            return admin_codigo
        nombre_final = (nombre or "").strip() or f"Administrador ({admin_codigo})"
        with self._lock:
            conn = None
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR IGNORE INTO aliados (codigo, nombre, marca, oficio, estado, score)
                    VALUES (?, ?, 'RUANA', 'Administración', 'sistema', 0)
                """, (admin_codigo, nombre_final))
                conn.commit()
                return admin_codigo
            except Exception:
                return None
            finally:
                if conn:
                    conn.close()

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
        """Registra que este código de invitación fue creado por el aliado invitador (para +3 al completar)."""
        codigo_invitacion = (codigo_invitacion or "").strip()
        if not codigo_invitacion or invitador_aliado_id is None:
            raise ValueError("codigo_invitacion e invitador_aliado_id son obligatorios")
        sid = None
        if solicitud_id is not None:
            try:
                sid = int(solicitud_id)
            except (TypeError, ValueError):
                sid = None
        with self._lock:
            conn = None
            try:
                conn = self._connect()
                cursor = conn.cursor()
                # Asegurar columna solicitud_id en instalaciones antiguas
                try:
                    self._migrar_invitaciones_solicitud_id(conn, cursor)
                except Exception:
                    pass
                if self.backend == "postgres":
                    cursor.execute(
                        """
                        INSERT INTO invitaciones (codigo, invitador_aliado_id, usado, solicitud_id)
                        VALUES (?, ?, 0, ?)
                        ON CONFLICT (codigo) DO UPDATE SET
                            invitador_aliado_id = EXCLUDED.invitador_aliado_id,
                            usado = 0,
                            solicitud_id = COALESCE(EXCLUDED.solicitud_id, invitaciones.solicitud_id)
                        """,
                        (codigo_invitacion, int(invitador_aliado_id), sid),
                    )
                else:
                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO invitaciones (codigo, invitador_aliado_id, usado, solicitud_id)
                        VALUES (?, ?, 0, ?)
                        """,
                        (codigo_invitacion, int(invitador_aliado_id), sid),
                    )
                conn.commit()
            finally:
                if conn:
                    conn.close()

    def marcar_solicitud_candidato_pendiente(self, solicitud_id: int, codigo_proponente: str) -> Dict[str, Any]:
        """
        «Conozco a alguien»: la solicitud no se cierra; pasa a candidato_pendiente
        mientras el invitado no se registre.
        """
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                try:
                    self._migrar_solicitudes_candidato(conn, cursor)
                except Exception:
                    pass
                cursor.execute(
                    "SELECT grupo_id, estado FROM solicitudes WHERE id = ?",
                    (int(solicitud_id),),
                )
                row = cursor.fetchone()
                if not row:
                    return {'status': 'error', 'message': 'Solicitud no encontrada'}
                grupo_id, estado = row[0], (row[1] or '').strip().lower()
                if estado != 'pendiente':
                    return {
                        'status': 'error',
                        'message': 'La solicitud ya no está pendiente de candidato',
                    }
                cursor.execute(
                    "SELECT grupo_id, nombre FROM aliados WHERE codigo = ?",
                    (codigo_proponente.strip(),),
                )
                r2 = cursor.fetchone()
                if not r2:
                    return {'status': 'error', 'message': 'Aliado no encontrado'}
                if r2[0] != grupo_id:
                    return {
                        'status': 'error',
                        'message': 'Solo un aliado del mismo grupo puede proponer candidato',
                    }
                nombre = r2[1] or ''
                cursor.execute(
                    """
                    UPDATE solicitudes
                    SET estado = 'candidato_pendiente',
                        candidato_por_codigo = ?,
                        candidato_por_nombre = ?,
                        candidato_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND estado = 'pendiente'
                    """,
                    (codigo_proponente.strip(), nombre, int(solicitud_id)),
                )
                conn.commit()
                if cursor.rowcount == 0:
                    return {
                        'status': 'error',
                        'message': 'La solicitud ya no está pendiente de candidato',
                    }
                return {'status': 'success', 'ok': True, 'estado': 'candidato_pendiente'}
            except Exception as e:
                return {'status': 'error', 'message': str(e)}
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

    def vincular_solicitud_a_aliado_incorporado(
        self,
        codigo_invitacion: str,
        nuevo_aliado_codigo: str,
    ) -> Dict[str, Any]:
        """
        Tras registrarse con el código de «Conozco a alguien», vincula la solicitud
        al nuevo aliado, la deja disponible (pendiente) y le notifica.
        """
        codigo_invitacion = (codigo_invitacion or '').strip()
        nuevo_aliado_codigo = (nuevo_aliado_codigo or '').strip()
        if not codigo_invitacion or not nuevo_aliado_codigo:
            return {'status': 'error', 'message': 'Código requerido'}

        notif_payload = None
        with self._lock:
            conn = None
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                try:
                    self._migrar_invitaciones_solicitud_id(conn, cursor)
                    self._migrar_solicitudes_candidato(conn, cursor)
                except Exception:
                    pass
                cursor.execute(
                    """
                    SELECT i.solicitud_id, i.codigo
                    FROM invitaciones i
                    WHERE i.codigo = ?
                    """,
                    (codigo_invitacion,),
                )
                inv = cursor.fetchone()
                if not inv:
                    return {'status': 'error', 'message': 'Invitación no encontrada'}
                solicitud_id = inv['solicitud_id'] if hasattr(inv, 'keys') else inv[0]
                if solicitud_id is None:
                    return {'status': 'success', 'ok': True, 'vinculada': False}
                cursor.execute(
                    "SELECT codigo, nombre FROM aliados WHERE codigo = ?",
                    (nuevo_aliado_codigo,),
                )
                aliado = cursor.fetchone()
                if not aliado:
                    return {'status': 'error', 'message': 'Aliado no encontrado'}
                nombre_nuevo = aliado['nombre'] if hasattr(aliado, 'keys') else aliado[1]
                cursor.execute(
                    """
                    SELECT id, oficio, descripcion, estado, solicitante_codigo
                    FROM solicitudes WHERE id = ?
                    """,
                    (int(solicitud_id),),
                )
                sol = cursor.fetchone()
                if not sol:
                    return {'status': 'error', 'message': 'Solicitud no encontrada'}
                estado = (sol['estado'] if hasattr(sol, 'keys') else sol[3] or '').strip().lower()
                oficio = (sol['oficio'] if hasattr(sol, 'keys') else sol[1]) or ''
                descripcion = (sol['descripcion'] if hasattr(sol, 'keys') else sol[2]) or ''
                if estado in ('candidato_pendiente', 'pendiente'):
                    cursor.execute(
                        """
                        UPDATE solicitudes
                        SET estado = 'pendiente',
                            asignada_a_codigo = ?,
                            asignada_a_nombre = ?
                        WHERE id = ?
                        """,
                        (nuevo_aliado_codigo, nombre_nuevo or '', int(solicitud_id)),
                    )
                else:
                    cursor.execute(
                        """
                        UPDATE solicitudes
                        SET asignada_a_codigo = COALESCE(asignada_a_codigo, ?),
                            asignada_a_nombre = COALESCE(asignada_a_nombre, ?)
                        WHERE id = ?
                        """,
                        (nuevo_aliado_codigo, nombre_nuevo or '', int(solicitud_id)),
                    )
                conn.commit()
                oficio_txt = oficio.strip() or 'una solicitud'
                desc_corta = (descripcion or '').strip()
                if len(desc_corta) > 120:
                    desc_corta = desc_corta[:117] + '…'
                mensaje = (
                    f"Tienes una solicitud disponible para atender"
                    f"{(' · ' + oficio_txt) if oficio_txt else ''}."
                )
                if desc_corta:
                    mensaje += f" {desc_corta}"
                notif_payload = {
                    'codigo': nuevo_aliado_codigo,
                    'mensaje': mensaje,
                    'solicitud_id': int(solicitud_id),
                    'oficio': oficio,
                }
            except Exception as e:
                return {'status': 'error', 'message': str(e)}
            finally:
                if conn:
                    conn.close()

        if notif_payload:
            self._crear_notificacion_aliado(
                notif_payload['codigo'],
                'solicitud_asignada',
                'Solicitud disponible',
                notif_payload['mensaje'],
                metadata={
                    'solicitud_id': notif_payload['solicitud_id'],
                    'oficio': notif_payload['oficio'],
                    'origen': 'conozco_alguien',
                },
            )
            return {
                'status': 'success',
                'ok': True,
                'vinculada': True,
                'solicitud_id': notif_payload['solicitud_id'],
            }
        return {'status': 'success', 'ok': True, 'vinculada': False}
    def crear_campana_invitacion(self, codigo: str = "", nombre: str = "",
                                  codigo_postal: str = "", max_usos: int = 100,
                                  creado_por_admin_codigo: str = "") -> Dict[str, Any]:
        """Crea un codigo multiuso administrado para registros por invitacion."""
        import random
        import re
        codigo = (codigo or "").strip().upper()
        nombre = (nombre or "").strip() or "Campana de invitacion"
        codigo_postal = (codigo_postal or "").strip()
        try:
            max_usos_int = int(max_usos)
        except (TypeError, ValueError):
            max_usos_int = 100
        max_usos_int = max(1, min(max_usos_int, 10000))

        with self._lock:
            conn = None
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                if not codigo:
                    for _ in range(100):
                        codigo = "RUANA-" + "".join(random.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(6))
                        cursor.execute("SELECT codigo FROM invitacion_campanas WHERE codigo = ?", (codigo,))
                        if not cursor.fetchone():
                            break
                    else:
                        return {'status': 'error', 'message': 'No se pudo generar codigo de campana unico'}

                if not re.match(r'^[A-Z0-9][A-Z0-9_-]{3,39}$', codigo):
                    return {'status': 'error', 'message': 'El codigo debe tener 4-40 caracteres alfanumericos, guion o guion bajo'}

                cursor.execute("SELECT codigo FROM invitacion_campanas WHERE codigo = ?", (codigo,))
                if cursor.fetchone():
                    return {'status': 'error', 'message': f'El codigo {codigo} ya existe'}

                cursor.execute("""
                    INSERT INTO invitacion_campanas
                    (codigo, nombre, codigo_postal, max_usos, usos_actuales, activo, creado_por_admin_codigo)
                    VALUES (?, ?, ?, ?, 0, 1, ?)
                """, (codigo, nombre, codigo_postal, max_usos_int, (creado_por_admin_codigo or "").strip()))
                conn.commit()

                cursor.execute("SELECT * FROM invitacion_campanas WHERE codigo = ?", (codigo,))
                row = cursor.fetchone()
                return {'status': 'success', 'campana': dict(row)}
            except Exception as e:
                return {'status': 'error', 'message': str(e)}
            finally:
                if conn:
                    conn.close()

    def listar_campanas_invitacion(self, limite: int = 50) -> List[Dict[str, Any]]:
        """Lista campanas de invitacion multiuso para el panel admin."""
        with self._lock:
            conn = None
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                limite = max(1, min(int(limite or 50), 200))
                cursor.execute("""
                    SELECT codigo, nombre, codigo_postal, max_usos, usos_actuales, activo,
                           creado_por_admin_codigo, creado_en, desactivado_en
                    FROM invitacion_campanas
                    ORDER BY creado_en DESC
                    LIMIT ?
                """, (limite,))
                return [dict(r) for r in cursor.fetchall()]
            except Exception:
                return []
            finally:
                if conn:
                    conn.close()

    def validar_campana_invitacion(self, codigo: str) -> Optional[Dict[str, Any]]:
        """Devuelve la campana si existe, esta activa y aun tiene usos disponibles."""
        codigo = (codigo or "").strip().upper()
        if not codigo:
            return None
        with self._lock:
            conn = None
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM invitacion_campanas WHERE codigo = ?", (codigo,))
                row = cursor.fetchone()
                if not row:
                    return None
                campana = dict(row)
                if int(campana.get('activo') or 0) != 1:
                    return None
                max_usos = int(campana.get('max_usos') or 0)
                usos_actuales = int(campana.get('usos_actuales') or 0)
                if max_usos > 0 and usos_actuales >= max_usos:
                    return None
                campana['usos_restantes'] = max(0, max_usos - usos_actuales)
                return campana
            except Exception:
                return None
            finally:
                if conn:
                    conn.close()

    def obtener_campana_invitacion(self, codigo: str) -> Optional[Dict[str, Any]]:
        """Devuelve una campana por codigo aunque este agotada o desactivada."""
        codigo = (codigo or "").strip().upper()
        if not codigo:
            return None
        with self._lock:
            conn = None
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM invitacion_campanas WHERE codigo = ?", (codigo,))
                row = cursor.fetchone()
                return dict(row) if row else None
            except Exception:
                return None
            finally:
                if conn:
                    conn.close()

    def consumir_campana_invitacion(self, codigo: str, nuevo_aliado_codigo: str) -> bool:
        """Marca un uso de campana si aun queda cupo disponible."""
        codigo = (codigo or "").strip().upper()
        nuevo_aliado_codigo = (nuevo_aliado_codigo or "").strip()
        if not codigo or not nuevo_aliado_codigo:
            return False
        with self._lock:
            conn = None
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE invitacion_campanas
                    SET usos_actuales = usos_actuales + 1
                    WHERE codigo = ?
                      AND activo = 1
                      AND usos_actuales < max_usos
                """, (codigo,))
                if cursor.rowcount != 1:
                    conn.rollback()
                    return False
                cursor.execute("""
                    INSERT OR IGNORE INTO invitacion_campana_usos (codigo_campana, codigo_aliado)
                    VALUES (?, ?)
                """, (codigo, nuevo_aliado_codigo))
                conn.commit()
                self._registrar_referido_campana_admin(codigo, nuevo_aliado_codigo)
                return True
            except Exception:
                return False
            finally:
                if conn:
                    conn.close()

    def desactivar_campana_invitacion(self, codigo: str) -> Dict[str, Any]:
        """Desactiva una campana multiuso para que deje de validar."""
        codigo = (codigo or "").strip().upper()
        with self._lock:
            conn = None
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE invitacion_campanas
                    SET activo = 0, desactivado_en = CURRENT_TIMESTAMP
                    WHERE codigo = ?
                """, (codigo,))
                conn.commit()
                if cursor.rowcount != 1:
                    return {'status': 'error', 'message': 'Campana no encontrada'}
                return {'status': 'success', 'codigo': codigo}
            except Exception as e:
                return {'status': 'error', 'message': str(e)}
            finally:
                if conn:
                    conn.close()

    def listar_invitaciones_recientes(self, limite: int = 20) -> List[Dict[str, Any]]:
        """Lista las últimas invitaciones generadas (para panel admin). Incluye código, invitador, fecha, usado."""
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("PRAGMA table_info(invitaciones)")
                cols = [r[1] for r in cursor.fetchall()]
                if 'creado_en' not in cols:
                    return []
                cursor.execute("""
                    SELECT i.codigo, i.invitador_aliado_id, i.creado_en, i.usado,
                           a.codigo AS invitador_codigo, a.nombre AS invitador_nombre
                    FROM invitaciones i
                    LEFT JOIN aliados a ON a.id = i.invitador_aliado_id
                    ORDER BY i.creado_en DESC
                    LIMIT ?
                """, (limite,))
                return [dict(r) for r in cursor.fetchall()]
            except Exception:
                return []
            finally:
                conn.close()

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
        """
        Registra el referido y da +3 al invitador si la invitación aún no estaba usada.
        Idempotente: si ya estaba usada pero faltaba el vínculo en referidos, lo crea sin duplicar score.
        """
        codigo_invitacion = (codigo_invitacion or '').strip()
        nuevo_aliado_codigo = (nuevo_aliado_codigo or '').strip()
        if not codigo_invitacion or not nuevo_aliado_codigo:
            return False
        codigo_invitador = None
        origen = 'aliado'
        with self._lock:
            conn = None
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT i.usado, i.invitador_aliado_id, inv.codigo AS codigo_invitador,
                           inv.estado AS invitador_estado
                    FROM invitaciones i
                    JOIN aliados inv ON inv.id = i.invitador_aliado_id
                    WHERE i.codigo = ?
                """, (codigo_invitacion,))
                row = cursor.fetchone()
                if not row:
                    return False
                usado = int(row['usado'] or 0)
                codigo_invitador = row['codigo_invitador']
                origen = 'admin_invitacion' if (row['invitador_estado'] or '').strip() == 'sistema' else 'aliado'
                ya_registrado = False
                cursor.execute(
                    "SELECT invitado_por_codigo FROM aliados WHERE codigo = ?",
                    (nuevo_aliado_codigo,),
                )
                row_aliado = cursor.fetchone()
                if row_aliado and (row_aliado[0] or '').strip():
                    ya_registrado = True
                if not ya_registrado:
                    cursor.execute(
                        "SELECT 1 FROM referidos WHERE codigo_referido = ?",
                        (nuevo_aliado_codigo,),
                    )
                    ya_registrado = cursor.fetchone() is not None
                if not ya_registrado and usado == 0:
                    self.aplicar_cambio_score(codigo_invitador, 3, 'aliado_referido_registro_valido')
                if usado == 0:
                    cursor.execute(
                        "UPDATE invitaciones SET usado = 1 WHERE codigo = ?",
                        (codigo_invitacion,),
                    )
                conn.commit()
            except Exception:
                return False
            finally:
                if conn:
                    conn.close()
        if not codigo_invitador:
            return False
        return self.asignar_invitado_por(nuevo_aliado_codigo, codigo_invitador, origen) or True

    def generar_invitacion_oficio(self, codigo_aliado: str, oficio: str) -> Dict[str, Any]:
        """
        Genera o devuelve una invitación por oficio para el grupo del aliado.
        Formato código: RUANA-{grupo_id}-{OFICIO_NORM}-{4 chars}
        Si ya existe una invitación pendiente para grupo+oficio, devuelve la existente.
        """
        import re
        oficio = (oficio or '').strip()
        if not oficio:
            return {'status': 'error', 'message': 'Oficio requerido'}

        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                aliado = self.obtener_aliado_por_codigo(codigo_aliado)
                if not aliado:
                    return {'status': 'error', 'message': 'Aliado no encontrado'}
                grupo_id = aliado.get('grupo_id')
                aliado_id = aliado.get('id')
                if not grupo_id or not aliado_id:
                    return {'status': 'error', 'message': 'El aliado no pertenece a un grupo'}

                oficios_faltantes = self.info_grupo_para_panel(grupo_id)
                if not oficios_faltantes or oficio not in (oficios_faltantes.get('oficios_faltantes') or []):
                    return {'status': 'error', 'message': 'El oficio no está en la lista de oficios faltantes'}

                cursor.execute(
                    "SELECT codigo FROM invitaciones_oficio WHERE grupo_id = ? AND oficio = ? AND estado = 'pendiente' LIMIT 1",
                    (grupo_id, oficio)
                )
                row = cursor.fetchone()
                if row:
                    return {'status': 'success', 'codigo': row[0]}

                # Normalizar oficio: solo A-Z0-9, máx 20 chars (formato aceptado por validación)
                oficio_norm = re.sub(r'[^A-Za-z0-9]', '', oficio).upper() or 'OFICIO'
                oficio_norm = (oficio_norm[:20] if len(oficio_norm) > 20 else oficio_norm)
                # Sufijo: exactamente 4 caracteres A-Z o 0-9 (formato aceptado)
                suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
                codigo = f"RUANA-{grupo_id}-{oficio_norm}-{suffix}"
                # Verificar que el código generado cumple el formato aceptado
                if not re.match(RUANA_CODIGO_INVITACION_REGEX, codigo):
                    # Fallback si hay inconsistencia
                    codigo = f"RUANA-{grupo_id}-OFICIO-{suffix}"

                cursor.execute(
                    "INSERT INTO invitaciones_oficio (codigo, grupo_id, oficio, aliado_id, estado) VALUES (?, ?, ?, ?, 'pendiente')",
                    (codigo, grupo_id, oficio, aliado_id)
                )
                conn.commit()
                return {'status': 'success', 'codigo': codigo}
            except Exception as e:
                return {'status': 'error', 'message': str(e)}
            finally:
                conn.close()

    def validar_invitacion_oficio(self, codigo: str) -> Optional[Dict[str, Any]]:
        """
        Valida si un código de invitación por oficio (RUANA-{grupo_id}-{OFICIO}-{4chars})
        existe y está pendiente. Devuelve la invitación con grupo_id, oficio, zona, etc.
        Si ya fue usada (estado='usado') o no existe, devuelve None.
        """
        import re
        codigo = (codigo or '').strip().upper()
        if not codigo or not re.match(RUANA_CODIGO_INVITACION_REGEX, codigo):
            return None
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, codigo, grupo_id, oficio, aliado_id, estado FROM invitaciones_oficio WHERE codigo = ?",
                    (codigo,)
                )
                row = cursor.fetchone()
                conn.close()
                if not row or (row[5] or '').lower() != 'pendiente':
                    return None
                inv = dict(row)
                grupo = self.obtener_grupo_por_id(inv['grupo_id'])
                if not grupo:
                    return None
                return {
                    'codigo': inv['codigo'],
                    'grupo_id': inv['grupo_id'],
                    'oficio': inv['oficio'],
                    'aliado_id': inv['aliado_id'],
                    'zona': grupo.get('codigo_postal') or '',
                    'grupo': grupo.get('nombre') or '',
                    'codigo_postal': grupo.get('codigo_postal') or '',
                }
            except Exception:
                return None

    def consumir_invitacion_oficio(self, codigo: str, nuevo_aliado_codigo: str) -> bool:
        """
        Marca una invitación por oficio como usada, registra referido y da +5 al generador
        (Regla 9 del score operativo). Idempotente si ya estaba usada pero faltaba el vínculo.
        """
        codigo = (codigo or '').strip().upper()
        nuevo_aliado_codigo = (nuevo_aliado_codigo or '').strip()
        if not codigo or not nuevo_aliado_codigo:
            return False
        codigo_invitador = None
        with self._lock:
            conn = None
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, aliado_id, estado FROM invitaciones_oficio WHERE codigo = ?",
                    (codigo,),
                )
                row = cursor.fetchone()
                if not row:
                    return False
                invitacion_id = row['id']
                aliado_id = row['aliado_id']
                estado = (row['estado'] or '').strip()
                cursor.execute("SELECT codigo FROM aliados WHERE id = ?", (aliado_id,))
                r2 = cursor.fetchone()
                if not r2:
                    return False
                codigo_invitador = r2[0]
                ya_registrado = False
                cursor.execute(
                    "SELECT invitado_por_codigo FROM aliados WHERE codigo = ?",
                    (nuevo_aliado_codigo,),
                )
                row_aliado = cursor.fetchone()
                if row_aliado and (row_aliado[0] or '').strip():
                    ya_registrado = True
                if not ya_registrado:
                    cursor.execute(
                        "SELECT 1 FROM referidos WHERE codigo_referido = ?",
                        (nuevo_aliado_codigo,),
                    )
                    ya_registrado = cursor.fetchone() is not None
                if estado == 'pendiente':
                    cursor.execute(
                        "UPDATE invitaciones_oficio SET estado = 'usado', codigo_referido = ? WHERE id = ?",
                        (nuevo_aliado_codigo, invitacion_id),
                    )
                    if not ya_registrado:
                        self.aplicar_cambio_score(
                            codigo_invitador, self.REGLA9_DELTA, 'invitacion_oficio_usada'
                        )
                elif estado == 'usado' and not ya_registrado:
                    cursor.execute(
                        "UPDATE invitaciones_oficio SET codigo_referido = ? WHERE id = ? AND COALESCE(codigo_referido, '') = ''",
                        (nuevo_aliado_codigo, invitacion_id),
                    )
                conn.commit()
            except Exception:
                return False
            finally:
                if conn:
                    conn.close()
        if not codigo_invitador:
            return False
        return self.asignar_invitado_por(nuevo_aliado_codigo, codigo_invitador, 'oficio') or True

    def listar_aliados(self, filtro_postal: str = None) -> List[Dict[str, Any]]:
        """
        Lista todos los aliados, opcionalmente filtrados por código postal
        
        Args:
            filtro_postal: Código postal para filtrar (opcional)
            
        Returns:
            Lista de aliados
        """
        try:
            self.backfill_invitado_por_linaje()
        except Exception:
            pass
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                col_retador = self._columna_retador_competencia(cursor)

                base_query = """
                    SELECT
                        a.*,
                        g.nombre AS grupo_nombre,
                        e.estado AS eval_estado,
                        e.score AS eval_score,
                        e.intencion AS eval_intencion,
                        e.tasa_respuesta,
                        e.tasa_confirmacion,
                        e.meses_sin_trabajo,
                        e.ciclos_consecutivos,
                        e.razones AS eval_razones,
                        e.severidad AS eval_severidad,
                        e.actualizado_en AS eval_actualizado_en,
                        inv.nombre AS invitado_por_nombre,
                        inv.codigo AS invitado_por_codigo_join,
                        (
                            SELECT COUNT(*)
                            FROM aliados h
                            WHERE h.invitado_por_codigo = a.codigo
                              AND COALESCE(h.estado, '') NOT IN (
                                  'pendiente_completar', 'sistema', 'rechazado', 'expulsado'
                              )
                        ) AS hijos_directos_count,
                        (
                            SELECT COUNT(*)
                            FROM contactos_ruana c
                            WHERE c.solicitante_codigo = a.codigo OR c.profesional_codigo = a.codigo
                        ) AS total_contactos,
                        (
                            SELECT COUNT(*)
                            FROM contactos_ruana c
                            WHERE (c.solicitante_codigo = a.codigo OR c.profesional_codigo = a.codigo)
                              AND datetime(c.creado_en) >= datetime('now', '-30 day')
                        ) AS contactos_30d,
                        (
                            SELECT 1 FROM competencia c
                            WHERE c.""" + col_retador + """ = a.codigo AND c.estado = 'activa' LIMIT 1
                        ) AS es_retador_activo,
                        (
                            SELECT 1 FROM competencia c
                            WHERE c.aliado_original_codigo = a.codigo AND c.estado = 'activa' LIMIT 1
                        ) AS es_titular_en_competencia
                    FROM aliados a
                    LEFT JOIN grupos g ON g.id = a.grupo_id
                    LEFT JOIN evaluaciones e ON e.codigo_aliado = a.codigo
                    LEFT JOIN aliados inv ON inv.codigo = a.invitado_por_codigo
                    WHERE (a.estado IS NULL OR (
                        a.estado != 'expulsado'
                        AND a.estado != 'suspendido_temporal'
                        AND a.estado != 'sistema'
                        AND a.estado != 'pendiente_completar'
                    ))
                """

                params: Tuple[Any, ...] = ()
                if filtro_postal:
                    base_query += " AND a.codigo_postal = ?"
                    params = (filtro_postal,)

                base_query += " ORDER BY a.creado_en DESC"

                cursor.execute(base_query, params)
                rows = cursor.fetchall()

                aliados: List[Dict[str, Any]] = []
                for row in rows:
                    item = dict(row)

                    # Zona legible para el panel (usa código postal por ahora)
                    item['zona'] = item.get('codigo_postal') or ''

                    # Linaje (padre / hijos) para Control de Aliados
                    invitado_por = (item.get('invitado_por_codigo') or item.get('invitado_por_codigo_join') or '').strip()
                    item['invitado_por_codigo'] = invitado_por or None
                    item['invitado_por_nombre'] = (item.get('invitado_por_nombre') or '').strip()
                    origen = (item.get('invitado_origen') or '').strip()
                    item['invitado_origen'] = origen
                    item['invitado_origen_label'] = self.etiqueta_origen_referido(origen)
                    try:
                        item['hijos_directos_count'] = int(item.get('hijos_directos_count') or 0)
                    except (TypeError, ValueError):
                        item['hijos_directos_count'] = 0

                    # Score de referencia para el panel (evaluación > aliado.score)
                    eval_score = item.get('eval_score')
                    if eval_score is not None:
                        try:
                            score_panel = float(eval_score)
                        except Exception:
                            score_panel = float(item.get('score') or 0)
                    else:
                        score_panel = float(item.get('score') or 0)
                    item['score_panel'] = score_panel

                    # Estado de panel: prioriza estado real de BD (activo / pendiente_validacion / en_espera).
                    # El score de evaluación solo reclasifica a observación/riesgo cuando existe evaluación.
                    # pendiente_completar no se lista (placeholders de invitación se excluyen arriba).
                    estado_bd = (item.get('estado') or 'activo').strip().lower()
                    estado_panel = 'activos'
                    if estado_bd == 'pendiente_validacion':
                        estado_panel = 'pendientes'
                    elif estado_bd == 'en_espera':
                        estado_panel = 'suplentes_espera'
                    elif estado_bd in ('expulsado', 'suspendido_temporal', 'rechazado'):
                        estado_panel = estado_bd
                    elif estado_bd == 'activo' and eval_score is None:
                        estado_panel = 'activos'
                    else:
                        if eval_score is not None:
                            try:
                                s = float(eval_score)
                            except Exception:
                                s = float(item.get('score') or 0)
                        else:
                            s = float(item.get('score') or 0)

                        if s < 15:
                            estado_panel = 'riesgo'
                        elif s < 50:
                            estado_panel = 'observacion'
                        else:
                            estado_panel = 'activos'

                    item['estado_panel'] = estado_panel

                    # Retador activo: en competencia como retador; alias es_suplente_activo para compat
                    item['es_retador_activo'] = bool(item.get('es_retador_activo'))
                    item['es_suplente_activo'] = item['es_retador_activo']  # alias compatibilidad
                    # Titular en competencia: 1 si es el aliado original en competencia
                    item['es_titular_en_competencia'] = bool(item.get('es_titular_en_competencia'))

                    aliados.append(item)

                return aliados
                
            except Exception as e:
                print(f"Error listando aliados: {e}")
                return []
            finally:
                conn.close()
    
    def listar_aliados_directorio_grupo(self, codigo_aliado: str) -> List[Dict[str, Any]]:
        """
        Lista profesionales del mismo grupo y código postal que el aliado (directorio).
        Excluye al propio aliado. Solo activos / pendiente_validacion.
        Nunca mezcla aliados de otros CP aunque compartan grupo_id por error de datos.
        """
        codigo_busqueda = (codigo_aliado or '').strip()
        aliado = self.obtener_aliado_por_codigo(codigo_busqueda)
        if not aliado:
            return []
        grupo_id = aliado.get('grupo_id')
        codigo_postal = (aliado.get('codigo_postal') or '').strip()
        codigo_excluir = (aliado.get('codigo') or codigo_busqueda or '').strip()

        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                estados_ok = ('activo', 'pendiente_validacion')
                select_cols = (
                    f"a.id, a.codigo, a.nombre, a.marca, a.oficio, a.codigo_postal, a.grupo_id, "
                    f"a.estado, a.score, a.descripcion_servicio, a.{ALIADO_FOTO_PERFIL_COLUMN}, a.creado_en"
                )

                cp_filtro = codigo_postal
                if grupo_id is not None:
                    cursor.execute(
                        "SELECT codigo_postal FROM grupos WHERE id = ?",
                        (grupo_id,),
                    )
                    row_grupo = cursor.fetchone()
                    if row_grupo and (row_grupo[0] or '').strip():
                        cp_filtro = (row_grupo[0] or '').strip()

                if grupo_id is not None and cp_filtro:
                    cursor.execute(
                        f"""
                        SELECT {select_cols}
                        FROM aliados a
                        INNER JOIN grupos g ON g.id = a.grupo_id
                        WHERE a.estado IN (?, ?) AND a.codigo != ?
                          AND a.grupo_id = ?
                          AND TRIM(COALESCE(g.codigo_postal, '')) = ?
                          AND TRIM(COALESCE(a.codigo_postal, '')) = ?
                        ORDER BY a.nombre
                        """,
                        (estados_ok[0], estados_ok[1], codigo_excluir, grupo_id, cp_filtro, cp_filtro),
                    )
                elif grupo_id is not None:
                    cursor.execute(
                        f"""
                        SELECT id, codigo, nombre, marca, oficio, codigo_postal, grupo_id, estado, score,
                               descripcion_servicio, {ALIADO_FOTO_PERFIL_COLUMN}, creado_en
                        FROM aliados
                        WHERE grupo_id = ? AND estado IN (?, ?) AND codigo != ?
                        ORDER BY nombre
                        """,
                        (grupo_id, estados_ok[0], estados_ok[1], codigo_excluir),
                    )
                elif cp_filtro:
                    cursor.execute(
                        f"""
                        SELECT id, codigo, nombre, marca, oficio, codigo_postal, grupo_id, estado, score,
                               descripcion_servicio, {ALIADO_FOTO_PERFIL_COLUMN}, creado_en
                        FROM aliados
                        WHERE TRIM(COALESCE(codigo_postal, '')) = ?
                          AND estado IN (?, ?) AND codigo != ?
                        ORDER BY nombre
                        """,
                        (cp_filtro, estados_ok[0], estados_ok[1], codigo_excluir),
                    )
                else:
                    return []
                rows = cursor.fetchall()
                result = []
                for row in rows:
                    item = dict(row)
                    item['zona'] = item.get('codigo_postal') or ''
                    item['estado_ruana'] = self.score_a_estado(item.get('score'))
                    # M-06: marcar perfiles incompletos (placeholder o datos sin completar)
                    nombre = (item.get('nombre') or '').strip()
                    oficio = (item.get('oficio') or '').strip()
                    estado = (item.get('estado') or '').strip()
                    item['perfil_incompleto'] = (
                        estado == 'pendiente_completar'
                        or nombre.startswith('Nuevo Aliado -')
                        or not nombre
                        or oficio.lower() == 'pendiente'
                        or not oficio
                    )
                    result.append(item)
                return result
            except Exception as e:
                print(f"Error listar_aliados_directorio_grupo: {e}")
                return []
            finally:
                conn.close()

    def codigo_existe(self, codigo: str) -> bool:
        """Verifica si un código ya existe como aliado."""
        with self._lock:
            conn = None
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM aliados WHERE codigo = ?", (codigo,))
                return cursor.fetchone() is not None
            except Exception as e:
                print(f"Error verificando código: {e}")
                return False
            finally:
                if conn:
                    conn.close()

    def invitacion_codigo_existe(self, codigo: str) -> bool:
        """True si el código ya está registrado en la tabla invitaciones."""
        codigo = (codigo or '').strip()
        if not codigo:
            return False
        with self._lock:
            conn = None
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM invitaciones WHERE codigo = ?", (codigo,))
                return cursor.fetchone() is not None
            except Exception as e:
                print(f"Error verificando codigo invitacion: {e}")
                return False
            finally:
                if conn:
                    conn.close()

    def codigo_disponible_para_asignar(self, codigo: str) -> bool:
        """True si el código no choca con aliados ni con invitaciones existentes."""
        codigo = (codigo or '').strip()
        if not codigo:
            return False
        return (not self.codigo_existe(codigo)) and (not self.invitacion_codigo_existe(codigo))

    def obtener_invitacion_pendiente(self, codigo: str) -> Optional[Dict[str, Any]]:
        """
        Devuelve una invitación aliado/admin aún no usada (tabla invitaciones).
        No incluye campañas ni invitaciones por oficio.
        """
        codigo = (codigo or '').strip()
        if not codigo:
            return None
        with self._lock:
            conn = None
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT i.codigo, i.invitador_aliado_id, i.usado, i.creado_en,
                           i.solicitud_id,
                           inv.codigo AS codigo_invitador,
                           inv.codigo_postal AS zona_invitador,
                           inv.id AS invitador_id
                    FROM invitaciones i
                    JOIN aliados inv ON inv.id = i.invitador_aliado_id
                    WHERE i.codigo = ? AND COALESCE(i.usado, 0) = 0
                    """,
                    (codigo,),
                )
                row = cursor.fetchone()
                if not row:
                    return None
                return dict(row)
            except Exception as e:
                print(f"Error obtener_invitacion_pendiente: {e}")
                return None
            finally:
                if conn:
                    conn.close()

    def eliminar_aliado_placeholder(self, codigo: str) -> bool:
        """
        Elimina un aliado placeholder (pendiente_completar) tras usar su código de invitación.
        Evita duplicados inútiles en el panel de control de aliados.
        """
        codigo = (codigo or '').strip()
        if not codigo:
            return False
        with self._lock:
            conn = None
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute(
                    """
                    DELETE FROM aliados
                    WHERE codigo = ?
                      AND LOWER(TRIM(COALESCE(estado, ''))) = 'pendiente_completar'
                    """,
                    (codigo,),
                )
                deleted = cursor.rowcount > 0
                conn.commit()
                return deleted
            except Exception as e:
                print(f"Error eliminar_aliado_placeholder: {e}")
                if conn:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                return False
            finally:
                if conn:
                    conn.close()

    def listar_aliados_pendiente_validacion(self) -> List[Dict[str, Any]]:
        """Lista aliados con estado pendiente_validacion (oficio fuera de catálogo, requieren activación manual)."""
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, codigo, nombre, marca, oficio, codigo_postal, email, telefono, creado_en
                    FROM aliados WHERE LOWER(TRIM(COALESCE(estado, ''))) = 'pendiente_validacion'
                    ORDER BY creado_en DESC
                """)
                rows = cursor.fetchall()
                return [dict(r) for r in rows] if rows else []
            except Exception as e:
                print(f"Error listando aliados pendientes: {e}")
                return []
            finally:
                conn.close()

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
                    SELECT 1 FROM ruana_soporte_conversaciones
                    WHERE id = ? AND TRIM(CAST(aliado_codigo AS TEXT)) = ? AND COALESCE(eliminada_por_aliado, 0) = 0
                """, (int(conversacion_id), codigo))
                if not cursor.fetchone():
                    return []
                cursor.execute("""
                    SELECT id, conversacion_id, emisor_tipo, emisor_codigo, mensaje, creado_en, leido_por_aliado, leido_por_admin
                    FROM ruana_soporte_mensajes
                    WHERE conversacion_id = ?
                    ORDER BY creado_en ASC, id ASC
                """, (int(conversacion_id),))
                return [dict(r) for r in cursor.fetchall()]
            except Exception:
                return []
            finally:
                if conn:
                    conn.close()

    def listar_mensajes_soporte_admin(self, conversacion_id: int) -> List[Dict[str, Any]]:
        with self._lock:
            conn = None
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, conversacion_id, emisor_tipo, emisor_codigo, mensaje, creado_en, leido_por_aliado, leido_por_admin
                    FROM ruana_soporte_mensajes
                    WHERE conversacion_id = ?
                    ORDER BY creado_en ASC, id ASC
                """, (int(conversacion_id),))
                return [dict(r) for r in cursor.fetchall()]
            except Exception:
                return []
            finally:
                if conn:
                    conn.close()

    def enviar_mensaje_soporte_aliado(self, conversacion_id: int, aliado_codigo: str, mensaje: str) -> Dict[str, Any]:
        codigo = str(aliado_codigo or '').strip()
        msg = str(mensaje or '').strip()
        if not codigo or not msg:
            return {'status': 'error', 'message': 'Datos incompletos'}
        with self._lock:
            conn = None
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id FROM ruana_soporte_conversaciones
                    WHERE id = ? AND TRIM(CAST(aliado_codigo AS TEXT)) = ? AND COALESCE(eliminada_por_aliado, 0) = 0
                """, (int(conversacion_id), codigo))
                if not cursor.fetchone():
                    return {'status': 'error', 'message': 'Conversación no encontrada'}
                cursor.execute("""
                    INSERT INTO ruana_soporte_mensajes
                        (conversacion_id, emisor_tipo, emisor_codigo, mensaje, leido_por_aliado, leido_por_admin)
                    VALUES (?, 'aliado', ?, ?, 1, 0)
                """, (int(conversacion_id), codigo, msg))
                cursor.execute("""
                    UPDATE ruana_soporte_conversaciones
                    SET estado = CASE WHEN estado = 'cerrado' THEN 'reabierto' ELSE estado END,
                        ultimo_mensaje_preview = ?, ultimo_mensaje_en = CURRENT_TIMESTAMP, actualizado_en = CURRENT_TIMESTAMP,
                        tiene_no_leido_admin = 1, tiene_no_leido_aliado = 0
                    WHERE id = ?
                """, (msg[:220], int(conversacion_id)))
                conn.commit()
                return {'status': 'success'}
            except Exception as e:
                return {'status': 'error', 'message': str(e)}
            finally:
                if conn:
                    conn.close()

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
        aliado_f = str(aliado_codigo or '').strip()
        estado_f = str(estado or '').strip().lower()
        with self._lock:
            conn = None
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                where = ["COALESCE(c.eliminada_por_admin, 0) = 0"]
                params: List[Any] = []
                if aliado_f:
                    where.append("LOWER(TRIM(CAST(c.aliado_codigo AS TEXT))) LIKE ?")
                    params.append(f"%{aliado_f.lower()}%")
                if estado_f:
                    where.append("LOWER(TRIM(COALESCE(c.estado, ''))) = ?")
                    params.append(estado_f)
                if solo_no_leidas:
                    where.append("COALESCE(c.tiene_no_leido_admin, 0) = 1")
                params.extend([max(1, min(int(limite or 100), 300)), max(0, int(offset or 0))])
                cursor.execute(f"""
                    SELECT c.id, c.aliado_codigo, a.nombre AS aliado_nombre, c.asunto, c.categoria, c.estado,
                           c.ultimo_mensaje_preview, c.ultimo_mensaje_en, c.tiene_no_leido_admin, c.tiene_no_leido_aliado,
                           c.creado_en, c.actualizado_en,
                           (SELECT COUNT(1) FROM ruana_soporte_mensajes m WHERE m.conversacion_id = c.id) AS total_mensajes
                    FROM ruana_soporte_conversaciones c
                    LEFT JOIN aliados a ON TRIM(CAST(a.codigo AS TEXT)) = TRIM(CAST(c.aliado_codigo AS TEXT))
                    WHERE {' AND '.join(where)}
                    ORDER BY c.ultimo_mensaje_en DESC, c.id DESC
                    LIMIT ? OFFSET ?
                """, params)
                return [dict(r) for r in cursor.fetchall()]
            except Exception:
                return []
            finally:
                if conn:
                    conn.close()

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
        estado = (nuevo_estado or '').strip().lower()
        if estado not in ('pendiente', 'en_revision', 'respondido', 'cerrado', 'reabierto'):
            return {'status': 'error', 'message': 'Estado inválido'}
        with self._lock:
            conn = None
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT aliado_codigo FROM ruana_soporte_conversaciones WHERE id = ? AND COALESCE(eliminada_por_admin, 0) = 0", (int(conversacion_id),))
                conv = cursor.fetchone()
                if not conv:
                    return {'status': 'error', 'message': 'Conversación no encontrada'}
                cursor.execute("""
                    UPDATE ruana_soporte_conversaciones
                    SET estado = ?, actualizado_en = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (estado, int(conversacion_id)))
                cursor.execute("""
                    INSERT INTO notificaciones_aliado (aliado_codigo, tipo, titulo, mensaje, metadata, leida)
                    VALUES (?, 'ruana_soporte_estado', '✅ Estado de tu consulta actualizado', ?, ?, 0)
                """, (
                    (conv['aliado_codigo'] or '').strip(),
                    f"La conversación #{int(conversacion_id)} ahora está en estado: {estado.replace('_', ' ')}.",
                    json.dumps({'conversacion_id': int(conversacion_id), 'estado': estado, 'origen': 'centro_soporte'})
                ))
                conn.commit()
                return {'status': 'success'}
            except Exception as e:
                return {'status': 'error', 'message': str(e)}
            finally:
                if conn:
                    conn.close()

    def eliminar_conversacion_soporte_admin(self, conversacion_id: int, admin_codigo: str = '') -> Dict[str, Any]:
        with self._lock:
            conn = None
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE ruana_soporte_conversaciones
                    SET eliminada_por_admin = 1, actualizado_en = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (int(conversacion_id),))
                conn.commit()
                return {'status': 'success'}
            except Exception as e:
                return {'status': 'error', 'message': str(e)}
            finally:
                if conn:
                    conn.close()

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
        """Activa pendiente_validacion y asigna grupo (priorizando el del invitador)."""
        codigo = (aliado.get('codigo') or '').strip()
        aliado_id = aliado.get('id')
        if not codigo or aliado_id is None:
            return {'status': 'error', 'message': 'Aliado no válido'}

        grupo_id = self._obtener_grupo_activacion_pendiente(cursor, aliado)
        if grupo_id:
            cursor.execute(
                """UPDATE aliados
                   SET estado = 'activo', grupo_id = ?, actualizado_en = CURRENT_TIMESTAMP
                   WHERE id = ? AND LOWER(TRIM(COALESCE(estado, ''))) = 'pendiente_validacion'""",
                (grupo_id, int(aliado_id)),
            )
        else:
            cursor.execute(
                """UPDATE aliados
                   SET estado = 'activo', actualizado_en = CURRENT_TIMESTAMP
                   WHERE id = ? AND LOWER(TRIM(COALESCE(estado, ''))) = 'pendiente_validacion'""",
                (int(aliado_id),),
            )

        if cursor.rowcount == 0:
            return {
                'status': 'error',
                'message': f'Aliado {codigo} no encontrado o no está pendiente de validación',
            }

        if grupo_id:
            cursor.execute("SELECT nombre FROM grupos WHERE id = ?", (grupo_id,))
            g_row = cursor.fetchone()
            grupo_nombre = (g_row[0] if g_row else None) or f'#{grupo_id}'
            return {
                'status': 'success',
                'message': f'Aliado {codigo} activado e incorporado al grupo {grupo_nombre}',
                'grupo_id': grupo_id,
            }

        return {
            'status': 'success',
            'message': (
                f'Aliado {codigo} activado correctamente. '
                'No había plaza disponible en ningún grupo del CP.'
            ),
            'grupo_id': None,
        }

    def activar_aliado_por_id(self, aliado_id: int) -> Dict[str, Any]:
        """Activa aliado por ID numérico (pendiente_validacion → activo) y asigna grupo."""
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    """SELECT id, codigo, oficio, codigo_postal, invitado_por_codigo, estado
                       FROM aliados WHERE id = ?""",
                    (int(aliado_id),),
                )
                row = cursor.fetchone()
                if not row:
                    return {'status': 'error', 'message': f'Aliado con ID {aliado_id} no encontrado'}
                if (row['estado'] or '').strip().lower() != 'pendiente_validacion':
                    return {
                        'status': 'error',
                        'message': f'Aliado con ID {aliado_id} no está pendiente de validación',
                    }
                result = self._activar_aliado_pendiente_interno(cursor, dict(row))
                conn.commit()
                return result
            except Exception as e:
                return {'status': 'error', 'message': str(e)}
            finally:
                conn.close()

    def activar_aliado_pendiente(self, codigo: str) -> Dict[str, Any]:
        """Cambia pendiente_validacion → activo y asigna grupo del invitador si hay plaza."""
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    """SELECT id, codigo, oficio, codigo_postal, invitado_por_codigo, estado
                       FROM aliados WHERE codigo = ?""",
                    (codigo.strip(),),
                )
                row = cursor.fetchone()
                if not row:
                    return {'status': 'error', 'message': f'Aliado {codigo} no encontrado'}
                if (row['estado'] or '').strip().lower() != 'pendiente_validacion':
                    return {
                        'status': 'error',
                        'message': f'Aliado {codigo} no está pendiente de validación',
                    }
                result = self._activar_aliado_pendiente_interno(cursor, dict(row))
                conn.commit()
                return result
            except Exception as e:
                return {'status': 'error', 'message': str(e)}
            finally:
                conn.close()

    def rechazar_aliado_pendiente(self, codigo: str) -> Dict[str, Any]:
        """Rechaza un aliado en pendiente_validacion: estado pasa a rechazado. No podrá entrar al panel."""
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE aliados SET estado = 'rechazado', actualizado_en = CURRENT_TIMESTAMP WHERE codigo = ? AND estado = 'pendiente_validacion'",
                    (codigo.strip(),)
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
        """Crea solicitud: obtiene aliado por código, inserta en solicitudes con estado pendiente."""
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute("SELECT grupo_id, nombre FROM aliados WHERE codigo = ?", (codigo.strip(),))
                row = cursor.fetchone()
                if not row:
                    return {'status': 'error', 'message': 'Aliado no válido'}
                grupo_id, nombre = row[0], row[1] or ''
                if grupo_id is None:
                    return {'status': 'error', 'message': 'No perteneces a un grupo'}
                oficio = (oficio or '').strip()
                descripcion = (descripcion or '').strip()
                if not oficio:
                    return {'status': 'error', 'message': 'Oficio requerido'}
                cursor.execute("PRAGMA table_info(solicitudes)")
                cols = [r[1] for r in cursor.fetchall()]
                if 'solicitante_codigo' not in cols:
                    return {'status': 'error', 'message': 'Tabla solicitudes no migrada'}
                cursor.execute("""
                    INSERT INTO solicitudes (grupo_id, solicitante_codigo, solicitante_nombre, oficio, descripcion, estado)
                    VALUES (?, ?, ?, ?, ?, 'pendiente')
                """, (grupo_id, codigo.strip(), nombre, oficio, descripcion))
                sid = cursor.lastrowid
                conn.commit()
                return {'status': 'success', 'ok': True, 'id': sid}
            except Exception as e:
                return {'status': 'error', 'message': str(e)}
            finally:
                conn.close()

    def listar_solicitudes_activas_por_codigo(self, codigo: str) -> List[Dict[str, Any]]:
        """Solo mismo grupo, estado pendiente, excluye las propias. GET /api/solicitudes?codigo=.
        También incluye solicitudes pendientes asignadas a este aliado (p. ej. tras «Conozco a alguien»).
        """
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                codigo = codigo.strip()
                cursor.execute("SELECT grupo_id FROM aliados WHERE codigo = ?", (codigo,))
                row = cursor.fetchone()
                if not row:
                    return []
                grupo_id = row[0]
                cursor.execute("PRAGMA table_info(solicitudes)")
                cols = [r[1] for r in cursor.fetchall()]
                if 'solicitante_codigo' not in cols:
                    return []
                has_asignada = 'asignada_a_codigo' in cols
                if grupo_id is None and not has_asignada:
                    return []
                if grupo_id is not None and has_asignada:
                    cursor.execute("""
                        SELECT id, grupo_id, solicitante_codigo, solicitante_nombre, oficio, descripcion, estado, created_at,
                               asignada_a_codigo, asignada_a_nombre
                        FROM solicitudes
                        WHERE estado = 'pendiente'
                          AND solicitante_codigo != ?
                          AND (grupo_id = ? OR asignada_a_codigo = ?)
                        ORDER BY created_at DESC
                    """, (codigo, grupo_id, codigo))
                elif grupo_id is not None:
                    cursor.execute("""
                        SELECT id, grupo_id, solicitante_codigo, solicitante_nombre, oficio, descripcion, estado, created_at
                        FROM solicitudes
                        WHERE grupo_id = ? AND estado = 'pendiente' AND solicitante_codigo != ?
                        ORDER BY created_at DESC
                    """, (grupo_id, codigo))
                else:
                    cursor.execute("""
                        SELECT id, grupo_id, solicitante_codigo, solicitante_nombre, oficio, descripcion, estado, created_at,
                               asignada_a_codigo, asignada_a_nombre
                        FROM solicitudes
                        WHERE estado = 'pendiente' AND asignada_a_codigo = ?
                        ORDER BY created_at DESC
                    """, (codigo,))
                return [dict(r) for r in cursor.fetchall()]
            except Exception as e:
                return []
            finally:
                conn.close()

    def listar_solicitudes_propias_por_codigo(self, codigo: str) -> List[Dict[str, Any]]:
        """Solicitudes creadas por el aliado (sus propias solicitudes). Mismo grupo, cualquier estado (pendiente/atendida)."""
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT grupo_id FROM aliados WHERE codigo = ?", (codigo.strip(),))
                row = cursor.fetchone()
                if not row or row[0] is None:
                    return []
                grupo_id = row[0]
                cursor.execute("PRAGMA table_info(solicitudes)")
                cols = [r[1] for r in cursor.fetchall()]
                if 'solicitante_codigo' not in cols:
                    return []
                extra = ''
                if 'candidato_por_codigo' in cols:
                    extra += ', candidato_por_codigo, candidato_por_nombre, candidato_at'
                if 'asignada_a_codigo' in cols:
                    extra += ', asignada_a_codigo, asignada_a_nombre'
                cursor.execute(f"""
                    SELECT id, grupo_id, solicitante_codigo, solicitante_nombre, oficio, descripcion, estado, created_at,
                           atendido_por_codigo, atendido_por_nombre, atendido_at{extra}
                    FROM solicitudes
                    WHERE grupo_id = ? AND solicitante_codigo = ?
                    ORDER BY created_at DESC
                """, (grupo_id, codigo.strip()))
                return [dict(r) for r in cursor.fetchall()]
            except Exception as e:
                return []
            finally:
                conn.close()

    def listar_solicitudes_historial_grupo_por_codigo(self, codigo: str, limite: int = 50) -> List[Dict[str, Any]]:
        """Historial de solicitudes del grupo (todas: pendiente y atendidas). Ordenado por fecha descendente."""
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT grupo_id FROM aliados WHERE codigo = ?", (codigo.strip(),))
                row = cursor.fetchone()
                if not row or row[0] is None:
                    return []
                grupo_id = row[0]
                cursor.execute("PRAGMA table_info(solicitudes)")
                cols = [r[1] for r in cursor.fetchall()]
                if 'solicitante_codigo' not in cols:
                    return []
                extra = ''
                if 'candidato_por_codigo' in cols:
                    extra += ', candidato_por_codigo, candidato_por_nombre, candidato_at'
                if 'asignada_a_codigo' in cols:
                    extra += ', asignada_a_codigo, asignada_a_nombre'
                cursor.execute(f"""
                    SELECT id, grupo_id, solicitante_codigo, solicitante_nombre, oficio, descripcion, estado, created_at,
                           atendido_por_codigo, atendido_por_nombre, atendido_at{extra}
                    FROM solicitudes
                    WHERE grupo_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (grupo_id, limite))
                return [dict(r) for r in cursor.fetchall()]
            except Exception as e:
                return []
            finally:
                conn.close()

    def obtener_solicitudes_grupo(self, codigo_postal: str) -> List[Dict[str, Any]]:
        """Obtiene solicitudes pendientes de todos los grupos activos en el código postal."""
        if not codigo_postal or not str(codigo_postal).strip():
            return []
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("PRAGMA table_info(solicitudes)")
                cols = [r[1] for r in cursor.fetchall()]
                if 'solicitante_codigo' not in cols:
                    return []
                cursor.execute("""
                    SELECT s.id, s.grupo_id, s.solicitante_codigo, s.solicitante_nombre, s.oficio, s.descripcion,
                           s.estado, s.created_at, g.nombre AS grupo_nombre
                    FROM solicitudes s
                    JOIN grupos g ON g.id = s.grupo_id
                    WHERE g.codigo_postal = ? AND g.estado = 'activo' AND s.estado = 'pendiente'
                    ORDER BY s.created_at DESC
                """, (codigo_postal.strip(),))
                return [dict(r) for r in cursor.fetchall()]
            except Exception as e:
                return []
            finally:
                conn.close()

    def atender_solicitud_por_id(self, solicitud_id: int, codigo: str) -> Dict[str, Any]:
        """Marca solicitud como atendida y registra quién atendió. Solo mismo grupo."""
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute("SELECT grupo_id, estado FROM solicitudes WHERE id = ?", (solicitud_id,))
                row = cursor.fetchone()
                if not row:
                    return {'status': 'error', 'message': 'Solicitud no encontrada'}
                grupo_id, estado = row[0], row[1]
                if estado != 'pendiente':
                    return {'status': 'error', 'message': 'La solicitud ya fue atendida'}
                cursor.execute("SELECT grupo_id, nombre FROM aliados WHERE codigo = ?", (codigo.strip(),))
                r2 = cursor.fetchone()
                if not r2:
                    return {'status': 'error', 'message': 'Aliado no encontrado'}
                if r2[0] != grupo_id:
                    return {'status': 'error', 'message': 'Solo un aliado del mismo grupo puede atender'}
                nombre_atendido = r2[1] or ''
                cursor.execute("""
                    UPDATE solicitudes
                    SET estado = 'atendida', atendido_por_codigo = ?, atendido_por_nombre = ?, atendido_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND estado = 'pendiente'
                """, (codigo.strip(), nombre_atendido, solicitud_id))
                conn.commit()
                if cursor.rowcount == 0:
                    return {'status': 'error', 'message': 'La solicitud ya fue atendida'}
                return {'status': 'success', 'ok': True}
            except Exception as e:
                return {'status': 'error', 'message': str(e)}
            finally:
                conn.close()

    def marcar_solicitud_atendida_por_admin(self, solicitud_id: int, admin_codigo: str) -> Dict[str, Any]:
        """Marca la solicitud como atendida y registra al admin como 'Atendido por' y 'Atendido at'. Si ya estaba atendida pero con columnas vacías, las rellena."""
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute("PRAGMA table_info(solicitudes)")
                cols = [r[1] for r in cursor.fetchall()]
                if 'atendido_por_codigo' not in cols or 'atendido_at' not in cols:
                    return {'status': 'error', 'message': 'Tabla solicitudes sin columnas atendido_por/atendido_at'}
                cursor.execute("SELECT id, estado, atendido_por_codigo, atendido_at FROM solicitudes WHERE id = ?", (solicitud_id,))
                row = cursor.fetchone()
                if not row:
                    return {'status': 'error', 'message': 'Solicitud no encontrada'}
                estado = row[1]
                atendido_por = row[2]
                atendido_at = row[3]
                nombre_admin = (admin_codigo or '').strip() or 'Admin'
                codigo_str = (admin_codigo or '').strip()
                if estado == 'pendiente':
                    cursor.execute("""
                        UPDATE solicitudes
                        SET estado = 'atendida', atendido_por_codigo = ?, atendido_por_nombre = ?, atendido_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """, (codigo_str, nombre_admin, solicitud_id))
                elif not atendido_por and not atendido_at:
                    cursor.execute("""
                        UPDATE solicitudes
                        SET atendido_por_codigo = ?, atendido_por_nombre = ?, atendido_at = COALESCE(atendido_at, CURRENT_TIMESTAMP)
                        WHERE id = ?
                    """, (codigo_str, nombre_admin, solicitud_id))
                else:
                    return {'status': 'success', 'ok': True}
                conn.commit()
                return {'status': 'success', 'ok': True}
            except Exception as e:
                return {'status': 'error', 'message': str(e)}
            finally:
                conn.close()

    def marcar_solicitud_contestada(self, solicitud_id: int, invitador_aliado_id: Optional[int] = None) -> None:
        """Marca la solicitud como atendida/contestada (p. ej. desde 'Conozco a alguien'). Opcional: invitador_aliado_id para registrar quién contestó."""
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute("PRAGMA table_info(solicitudes)")
                cols = [r[1] for r in cursor.fetchall()]
                if 'solicitante_codigo' not in cols:
                    return
                codigo_atendido = None
                nombre_atendido = None
                if invitador_aliado_id is not None:
                    cursor.execute("SELECT codigo, nombre FROM aliados WHERE id = ?", (int(invitador_aliado_id),))
                    row = cursor.fetchone()
                    if row:
                        codigo_atendido, nombre_atendido = row[0], row[1] or ''
                if codigo_atendido is None:
                    codigo_atendido = ''
                    nombre_atendido = ''
                cursor.execute("""
                    UPDATE solicitudes
                    SET estado = 'atendida', atendido_por_codigo = ?, atendido_por_nombre = ?, atendido_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND estado = 'pendiente'
                """, (codigo_atendido, nombre_atendido, solicitud_id))
                conn.commit()
            except Exception:
                pass
            finally:
                conn.close()

    def listar_solicitudes_admin_todas(self) -> List[Dict[str, Any]]:
        """Todas las solicitudes para el panel admin. Orden created_at DESC."""
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("PRAGMA table_info(solicitudes)")
                cols = [r[1] for r in cursor.fetchall()]
                if 'solicitante_codigo' not in cols:
                    return []
                cursor.execute("""
                    SELECT s.id, s.grupo_id, s.solicitante_codigo, s.solicitante_nombre, s.oficio, s.descripcion,
                           s.estado, s.atendido_por_codigo, s.atendido_por_nombre, s.created_at, s.atendido_at,
                           g.nombre AS grupo_nombre
                    FROM solicitudes s
                    LEFT JOIN grupos g ON g.id = s.grupo_id
                    ORDER BY s.created_at DESC
                """)
                return [dict(r) for r in cursor.fetchall()]
            except Exception as e:
                return []
            finally:
                conn.close()

    # ===============================================
    # OPERACIONES CONTACTOS RUANA
    # ===============================================

    # ===============================================
    # NEGOCIACIÓN GUIADA (sustituye chat libre)
    # ===============================================

    def _iniciar_negociacion_en_cursor(self, cursor, contacto_id: int, servicio: str,
                                        solicitante_codigo: str) -> None:
        estado = neg_mgr.estado_inicial()
        neg_json = neg_mgr.serializar_negociacion(estado)
        cursor.execute(
            "UPDATE contactos_ruana SET negociacion_json = ?, actualizado_en = CURRENT_TIMESTAMP WHERE id = ?",
            (neg_json, contacto_id),
        )

    def _insertar_evento_negociacion(self, cursor, contacto_id: int, tipo: str, campo: str,
                                      valor: str, emisor_codigo: str, mensaje: str) -> None:
        cursor.execute("""
            INSERT INTO negociacion_eventos (contacto_id, tipo, campo, valor, emisor_codigo, mensaje)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (contacto_id, tipo, campo or None, valor or None, emisor_codigo or None, mensaje))

    def _cargar_contacto_negociacion(self, cursor, contacto_id: int) -> Optional[Dict[str, Any]]:
        cursor.execute("SELECT * FROM contactos_ruana WHERE id = ?", (contacto_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def listar_eventos_negociacion(self, contacto_id: int) -> List[Dict[str, Any]]:
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, contacto_id, tipo, campo, valor, emisor_codigo, mensaje, creado_en
                    FROM negociacion_eventos
                    WHERE contacto_id = ?
                    ORDER BY id ASC
                """, (contacto_id,))
                return [dict(r) for r in cursor.fetchall()]
            except Exception as e:
                print(f"Error listar_eventos_negociacion: {e}")
                return []
            finally:
                conn.close()

    def obtener_negociacion_contacto(self, contacto_id: int, codigo_aliado: str) -> Dict[str, Any]:
        codigo = (codigo_aliado or '').strip()
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                contacto = self._cargar_contacto_negociacion(cursor, contacto_id)
                if not contacto:
                    return {'status': 'error', 'message': 'Contacto no encontrado'}
                sol = str(contacto.get('solicitante_codigo') or '').strip()
                pro = str(contacto.get('profesional_codigo') or '').strip()
                rol = neg_mgr._rol_en_contacto(codigo, sol, pro)
                if not rol:
                    return {'status': 'error', 'message': 'No autorizado'}
                eventos = self.listar_eventos_negociacion(contacto_id)
                payload = neg_mgr.construir_payload(contacto, eventos, rol)
                return {'status': 'success', **payload}
            except Exception as e:
                return {'status': 'error', 'message': str(e)}
            finally:
                conn.close()

    def proponer_negociacion(self, contacto_id: int, codigo_aliado: str,
                             campo: str, valor: str) -> Dict[str, Any]:
        with self._lock:
            conn = None
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                contacto = self._cargar_contacto_negociacion(cursor, contacto_id)
                if not contacto:
                    return {'status': 'error', 'message': 'Contacto no encontrado'}
                if contacto.get('estado') in ('trabajo_cerrado', 'no_concretado', 'cerrado_no_concretado', 'acuerdo_alcanzado'):
                    return {'status': 'error', 'message': 'Este contacto ya no admite cambios en la negociación'}
                sol = str(contacto.get('solicitante_codigo') or '').strip()
                pro = str(contacto.get('profesional_codigo') or '').strip()
                rol = neg_mgr._rol_en_contacto(codigo_aliado, sol, pro)
                if not rol:
                    return {'status': 'error', 'message': 'No autorizado'}
                estado = neg_mgr.parse_negociacion(contacto.get('negociacion_json'))
                estado, msg, tipo = neg_mgr.proponer_campo(estado, rol, campo, valor)
                neg_json = neg_mgr.serializar_negociacion(estado)
                cursor.execute(
                    "UPDATE contactos_ruana SET negociacion_json = ?, actualizado_en = CURRENT_TIMESTAMP WHERE id = ?",
                    (neg_json, contacto_id),
                )
                self._insertar_evento_negociacion(cursor, contacto_id, tipo, campo, valor, codigo_aliado, msg)
                conn.commit()
                eventos = self.listar_eventos_negociacion(contacto_id)
                contacto = self._cargar_contacto_negociacion(cursor, contacto_id)
                payload = neg_mgr.construir_payload(contacto, eventos, rol)
                return {'status': 'success', 'message': msg, **payload}
            except ValueError as ve:
                if conn:
                    conn.rollback()
                return {'status': 'error', 'message': str(ve)}
            except Exception as e:
                if conn:
                    conn.rollback()
                return {'status': 'error', 'message': str(e)}
            finally:
                if conn:
                    conn.close()

    def proponer_propuesta_completa_negociacion(
        self, contacto_id: int, codigo_aliado: str, valores: Dict[str, str],
    ) -> Dict[str, Any]:
        with self._lock:
            conn = None
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                contacto = self._cargar_contacto_negociacion(cursor, contacto_id)
                if not contacto:
                    return {'status': 'error', 'message': 'Contacto no encontrado'}
                if contacto.get('estado') in ('trabajo_cerrado', 'no_concretado', 'cerrado_no_concretado', 'acuerdo_alcanzado'):
                    return {'status': 'error', 'message': 'Este contacto ya no admite cambios en la negociación'}
                sol = str(contacto.get('solicitante_codigo') or '').strip()
                pro = str(contacto.get('profesional_codigo') or '').strip()
                rol = neg_mgr._rol_en_contacto(codigo_aliado, sol, pro)
                if not rol:
                    return {'status': 'error', 'message': 'No autorizado'}
                estado = neg_mgr.parse_negociacion(contacto.get('negociacion_json'))
                estado, msg_resumen, eventos = neg_mgr.proponer_propuesta_completa(estado, rol, valores)
                neg_json = neg_mgr.serializar_negociacion(estado)
                cursor.execute(
                    "UPDATE contactos_ruana SET negociacion_json = ?, actualizado_en = CURRENT_TIMESTAMP WHERE id = ?",
                    (neg_json, contacto_id),
                )
                self._insertar_evento_negociacion(
                    cursor, contacto_id, neg_mgr.TIPO_SISTEMA, None, None, codigo_aliado, msg_resumen,
                )
                for campo, valor, msg in eventos:
                    self._insertar_evento_negociacion(
                        cursor, contacto_id, neg_mgr.TIPO_PROPUESTA, campo, valor, codigo_aliado, msg,
                    )
                conn.commit()
                eventos_list = self.listar_eventos_negociacion(contacto_id)
                contacto = self._cargar_contacto_negociacion(cursor, contacto_id)
                payload = neg_mgr.construir_payload(contacto, eventos_list, rol)
                return {'status': 'success', 'message': msg_resumen, **payload}
            except ValueError as ve:
                if conn:
                    conn.rollback()
                return {'status': 'error', 'message': str(ve)}
            except Exception as e:
                if conn:
                    conn.rollback()
                return {'status': 'error', 'message': str(e)}
            finally:
                if conn:
                    conn.close()

    def contraoferta_negociacion(self, contacto_id: int, codigo_aliado: str,
                                  campo: str, valor: str, renegociar: bool = False) -> Dict[str, Any]:
        with self._lock:
            conn = None
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                contacto = self._cargar_contacto_negociacion(cursor, contacto_id)
                if not contacto:
                    return {'status': 'error', 'message': 'Contacto no encontrado'}
                if contacto.get('estado') in ('trabajo_cerrado', 'no_concretado', 'cerrado_no_concretado'):
                    return {'status': 'error', 'message': 'Este contacto ya está cerrado'}
                sol = str(contacto.get('solicitante_codigo') or '').strip()
                pro = str(contacto.get('profesional_codigo') or '').strip()
                rol = neg_mgr._rol_en_contacto(codigo_aliado, sol, pro)
                if not rol:
                    return {'status': 'error', 'message': 'No autorizado'}
                estado = neg_mgr.parse_negociacion(contacto.get('negociacion_json'))
                if renegociar:
                    estado, msg = neg_mgr.reabrir_campo_negociacion(estado, rol, campo, valor)
                    tipo = neg_mgr.TIPO_CONTRAOFERTA
                else:
                    estado, msg, tipo = neg_mgr.contraoferta_campo(estado, rol, campo, valor)
                neg_json = neg_mgr.serializar_negociacion(estado)
                nuevo_estado_contacto = contacto.get('estado')
                if contacto.get('estado') == 'acuerdo_alcanzado':
                    nuevo_estado_contacto = 'iniciado'
                cursor.execute("""
                    UPDATE contactos_ruana
                    SET negociacion_json = ?, estado = ?, actualizado_en = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (neg_json, nuevo_estado_contacto, contacto_id))
                self._insertar_evento_negociacion(cursor, contacto_id, tipo, campo, valor, codigo_aliado, msg)
                conn.commit()
                eventos = self.listar_eventos_negociacion(contacto_id)
                contacto = self._cargar_contacto_negociacion(cursor, contacto_id)
                payload = neg_mgr.construir_payload(contacto, eventos, rol)
                return {'status': 'success', 'message': msg, **payload}
            except ValueError as ve:
                if conn:
                    conn.rollback()
                return {'status': 'error', 'message': str(ve)}
            except Exception as e:
                if conn:
                    conn.rollback()
                return {'status': 'error', 'message': str(e)}
            finally:
                if conn:
                    conn.close()

    def _parse_importe_acuerdo(self, valor: Any) -> Optional[float]:
        """Extrae un importe numérico > 0 del valor acordado en negociación (p. ej. «150», «150€»)."""
        if valor is None:
            return None
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

    def _cerrar_encargo_tras_acuerdo(
        self,
        contacto_id: int,
        solicitante_codigo: str,
        precio_valor: Any,
        codigo_viewer: str,
        mensaje_acuerdo: str,
        payload_base: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Tras «Acuerdo alcanzado», aplica la misma lógica que «Sí hubo trabajo»
        (declarar importe del contratante → trabajo_cerrado + Apoyo RUANA).
        """
        importe = self._parse_importe_acuerdo(precio_valor)
        if importe is None:
            out = dict(payload_base)
            out['cierre_automatico'] = False
            out['cierre_aviso'] = (
                'Acuerdo alcanzado, pero no se pudo leer el precio acordado. '
                'Confirma el importe con «Sí, hubo trabajo».'
            )
            return out

        cierre = self.registrar_importe_contacto(
            contacto_id,
            'solicitante',
            importe,
            'EUR',
            usuario=(solicitante_codigo or '').strip(),
        )
        if not cierre or cierre.get('status') != 'success':
            out = dict(payload_base)
            out['cierre_automatico'] = False
            out['cierre_aviso'] = (cierre or {}).get('message') or (
                'Acuerdo alcanzado. Confirma el importe con «Sí, hubo trabajo».'
            )
            return out

        refreshed = self.obtener_negociacion_contacto(contacto_id, codigo_viewer)
        if refreshed.get('status') == 'success':
            refreshed['completo'] = True
            refreshed['cierre_automatico'] = True
            refreshed['message'] = (
                (mensaje_acuerdo or 'Acuerdo alcanzado.')
                + ' Encargo registrado como trabajo realizado.'
            )
            refreshed['estado_cierre'] = cierre.get('estado')
            return refreshed

        out = dict(payload_base)
        out['cierre_automatico'] = True
        out['estado_contacto'] = cierre.get('estado') or 'trabajo_cerrado'
        out['estado_cierre'] = cierre.get('estado')
        return out

    def aceptar_negociacion(self, contacto_id: int, codigo_aliado: str, campo: str,
                            observaciones_profesional: str = '') -> Dict[str, Any]:
        completo = False
        solicitante_codigo = ''
        precio_valor = None
        mensaje_acuerdo = ''
        payload = None
        with self._lock:
            conn = None
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                contacto = self._cargar_contacto_negociacion(cursor, contacto_id)
                if not contacto:
                    return {'status': 'error', 'message': 'Contacto no encontrado'}
                sol = str(contacto.get('solicitante_codigo') or '').strip()
                pro = str(contacto.get('profesional_codigo') or '').strip()
                rol = neg_mgr._rol_en_contacto(codigo_aliado, sol, pro)
                if not rol:
                    return {'status': 'error', 'message': 'No autorizado'}
                estado = neg_mgr.parse_negociacion(contacto.get('negociacion_json'))
                estado, msg, tipo, completo = neg_mgr.aceptar_campo(
                    estado, rol, campo, observaciones_profesional
                )
                neg_json = neg_mgr.serializar_negociacion(estado)
                nuevo_estado = contacto.get('estado') or 'iniciado'
                solicitante_codigo = sol
                if completo:
                    nuevo_estado = 'acuerdo_alcanzado'
                    cursor.execute(
                        "UPDATE contactos_ruana SET fecha_trabajo_en_progreso = COALESCE(fecha_trabajo_en_progreso, CURRENT_TIMESTAMP) WHERE id = ?",
                        (contacto_id,),
                    )
                    msg_sistema = (
                        'Acuerdo alcanzado. Resumen: '
                        + ', '.join(
                            f"{neg_mgr.CAMPOS_LABELS[c]}: {estado['campos'][c]['valor']}"
                            for c in neg_mgr.CAMPOS_ORDEN
                        )
                    )
                    mensaje_acuerdo = msg_sistema
                    self._insertar_evento_negociacion(
                        cursor, contacto_id, neg_mgr.TIPO_SISTEMA, None, '', None, msg_sistema
                    )
                    try:
                        precio_valor = estado['campos']['precio']['valor']
                    except Exception:
                        precio_valor = None
                cursor.execute("""
                    UPDATE contactos_ruana
                    SET negociacion_json = ?, estado = ?, actualizado_en = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (neg_json, nuevo_estado, contacto_id))
                self._insertar_evento_negociacion(cursor, contacto_id, tipo, campo,
                    estado['campos'][campo]['valor'], codigo_aliado, msg)
                conn.commit()
                eventos = self.listar_eventos_negociacion(contacto_id)
                contacto = self._cargar_contacto_negociacion(cursor, contacto_id)
                payload = neg_mgr.construir_payload(contacto, eventos, rol)
                payload = {'status': 'success', 'message': msg, 'completo': completo, **payload}
            except ValueError as ve:
                if conn:
                    conn.rollback()
                return {'status': 'error', 'message': str(ve)}
            except Exception as e:
                if conn:
                    conn.rollback()
                return {'status': 'error', 'message': str(e)}
            finally:
                if conn:
                    conn.close()

        if not payload:
            return {'status': 'error', 'message': 'No se pudo aceptar el punto'}

        if completo:
            return self._cerrar_encargo_tras_acuerdo(
                contacto_id,
                solicitante_codigo,
                precio_valor,
                codigo_aliado,
                mensaje_acuerdo or payload.get('message') or '',
                payload,
            )
        return payload

    def cerrar_negociacion(self, contacto_id: int, actor_codigo: str,
                           motivo: str = '') -> Dict[str, Any]:
        """
        Cierra la negociación para ambas partes (no concretado).
        Solo solicitante o profesional del contacto. Registra evento en timeline.
        """
        codigo = (actor_codigo or '').strip()
        sol = prof = None
        with self._lock:
            conn = None
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                contacto = self._cargar_contacto_negociacion(cursor, contacto_id)
                if not contacto:
                    return {'status': 'error', 'message': 'Contacto no encontrado'}
                sol = str(contacto.get('solicitante_codigo') or '').strip()
                pro = str(contacto.get('profesional_codigo') or '').strip()
                rol = neg_mgr._rol_en_contacto(codigo, sol, pro)
                if not rol:
                    return {'status': 'error', 'message': 'No autorizado'}
                estado_actual = (contacto.get('estado') or '').strip()
                if estado_actual in self._ESTADOS_FINALES_CONTACTO:
                    return {
                        'status': 'error',
                        'message': f'El contacto ya está cerrado ({estado_actual}).',
                    }
                quien = 'contratante' if rol == 'solicitante' else 'profesional'
                msg_evento = (
                    f'La negociación ha sido cerrada por el {quien}. '
                    'El contacto queda finalizado sin acuerdo.'
                )
                self._insertar_evento_negociacion(
                    cursor, contacto_id, neg_mgr.TIPO_SISTEMA, None, None, codigo, msg_evento,
                )
                cursor.execute("""
                    UPDATE contactos_ruana
                    SET estado = 'cerrado_no_concretado',
                        pendiente_resolucion = 0,
                        fecha_no_concretado = CURRENT_TIMESTAMP,
                        actualizado_en = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (contacto_id,))
                detalles = f'aliados={sol},{pro} motivo={motivo or "cerrar_negociacion"} actor={codigo}'
                self._audit_log(cursor, 'contacto', contacto_id, 'cerrar_negociacion',
                                'aliado', codigo, detalles)
                conn.commit()
            except Exception as e:
                if conn:
                    conn.rollback()
                return {'status': 'error', 'message': str(e)}
            finally:
                if conn:
                    conn.close()

        if sol:
            self.aplicar_cambio_score(sol, -1, 'contacto_cerrado_no_concretado')
        if prof:
            self.aplicar_cambio_score(prof, -1, 'contacto_cerrado_no_concretado')
        return {'status': 'success', 'id': contacto_id, 'estado': 'cerrado_no_concretado'}

    def listar_negociaciones_admin(self, limite: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT c.id AS contacto_id, c.solicitante_codigo, c.profesional_codigo,
                           c.servicio, c.estado, COALESCE(c.es_urgente, 0) AS es_urgente,
                           c.negociacion_json, c.creado_en, c.actualizado_en,
                           (SELECT mensaje FROM negociacion_eventos e
                            WHERE e.contacto_id = c.id ORDER BY e.id DESC LIMIT 1) AS ultimo_evento,
                           (SELECT creado_en FROM negociacion_eventos e
                            WHERE e.contacto_id = c.id ORDER BY e.id DESC LIMIT 1) AS fecha_ultimo,
                           (SELECT COUNT(*) FROM negociacion_eventos e WHERE e.contacto_id = c.id) AS num_eventos
                    FROM contactos_ruana c
                    WHERE EXISTS (SELECT 1 FROM negociacion_eventos e WHERE e.contacto_id = c.id)
                      AND c.estado NOT IN ('cerrado_no_concretado', 'no_concretado', 'trabajo_cerrado')
                    ORDER BY c.actualizado_en DESC
                    LIMIT ? OFFSET ?
                """, (limite, offset))
                rows = cursor.fetchall()
                result = []
                for row in rows:
                    d = dict(row)
                    neg = neg_mgr.parse_negociacion(d.get('negociacion_json'))
                    d['paso_actual'] = neg.get('paso_actual')
                    d['acuerdo_completo'] = bool(neg.get('completo')) or d.get('estado') == 'acuerdo_alcanzado'
                    d['es_urgente'] = bool(int(d.get('es_urgente') or 0))
                    precio = neg.get('campos', {}).get('precio', {}).get('valor') or ''
                    d['precio_acordado'] = precio
                    result.append(d)
                return result
            except Exception as e:
                print(f"Error listar_negociaciones_admin: {e}")
                return []
            finally:
                conn.close()

    def eliminar_negociacion_admin(self, contacto_id: int, admin_codigo: str = '') -> Dict[str, Any]:
        """Elimina contacto y toda su negociación (solo admin)."""
        with self._lock:
            conn = None
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM contactos_ruana WHERE id = ?", (contacto_id,))
                if not cursor.fetchone():
                    return {'status': 'error', 'message': 'Contacto no encontrado'}
                for tabla in (
                    'negociacion_eventos', 'chat_mensajes', 'confirmaciones_trabajo',
                    'contacto_panel_oculto', 'contacto_penalizaciones_aplicadas',
                    'chat_mensajes', 'ingresos_ruana', 'payment_conflicts',
                ):
                    try:
                        cursor.execute(f"DELETE FROM {tabla} WHERE contacto_id = ?", (contacto_id,))
                    except Exception:
                        pass
                try:
                    cursor.execute("DELETE FROM notificaciones_aliado WHERE metadata LIKE ?",
                                   (f'%"contacto_id": {contacto_id}%',))
                except Exception:
                    pass
                cursor.execute("DELETE FROM contactos_ruana WHERE id = ?", (contacto_id,))
                self._audit_log(cursor, 'contacto', contacto_id, 'negociacion_eliminada_admin',
                                'admin', admin_codigo or '', f'contacto_id={contacto_id}')
                conn.commit()
                return {'status': 'success', 'message': 'Negociación eliminada', 'contacto_id': contacto_id}
            except Exception as e:
                if conn:
                    conn.rollback()
                return {'status': 'error', 'message': str(e)}
            finally:
                if conn:
                    conn.close()

    # Limites chat RUANA (legacy — chat libre deshabilitado; negociación guiada activa).
    CHAT_MAX_MENSAJES_TOTAL = 30
    CHAT_MAX_MENSAJES_POR_USUARIO = CHAT_MAX_MENSAJES_TOTAL
    CHAT_HORAS_VIGENCIA = 48
    REGLA5_CLIENTES_UMBRAL = 3
    REGLA5_DELTA = 3
    REGLA5_SEGUNDOS_RESPUESTA = 3600

    def crear_contacto_ruana(self, solicitante_codigo: str, profesional_codigo: str,
                             servicio: str = "", motivo_contacto: str = "",
                             es_urgente: bool = False) -> Dict[str, Any]:
        """
        Crea un nuevo contacto RUANA en estado 'iniciado'.
        motivo_contacto: obligatorio para el flujo de chat (quién contactó a quién y por qué).
        es_urgente: solo el solicitante puede marcarlo al iniciar el chat (Regla 6).
        """
        with self._lock:
            try:
                if not solicitante_codigo or not profesional_codigo:
                    return {
                        'status': 'error',
                        'message': 'Solicitante y profesional son obligatorios'
                    }

                conn = self._connect()
                cursor = conn.cursor()

                cursor.execute("SELECT codigo FROM aliados WHERE codigo = ?", (solicitante_codigo,))
                if not cursor.fetchone():
                    return {
                        'status': 'error',
                        'message': f'Solicitante {solicitante_codigo} no existe como aliado'
                    }
                cursor.execute("SELECT codigo FROM aliados WHERE codigo = ?", (profesional_codigo,))
                if not cursor.fetchone():
                    return {
                        'status': 'error',
                        'message': f'Profesional {profesional_codigo} no existe como aliado'
                    }
                if self.tiene_pagos_ruana_pendientes(profesional_codigo):
                    return {
                        'status': 'error',
                        'message': 'El profesional tiene pagos pendientes con RUANA y no puede recibir nuevos encargos hasta regularizar la situación.'
                    }

                cursor.execute("PRAGMA table_info(contactos_ruana)")
                columnas = [row[1] for row in cursor.fetchall()]
                motivo_val = (motivo_contacto or '').strip() or None
                urgente_flag = 1 if es_urgente else 0
                tiene_motivo = 'motivo_contacto' in columnas
                tiene_urgente = 'es_urgente' in columnas

                if tiene_motivo and tiene_urgente:
                    cursor.execute("""
                        INSERT INTO contactos_ruana (
                            solicitante_codigo, profesional_codigo, servicio, motivo_contacto,
                            es_urgente, urgente_marcado_en,
                            estado, pendiente_resolucion, contacto_externo_habilitado
                        ) VALUES (?, ?, ?, ?, ?, CASE WHEN ? = 1 THEN CURRENT_TIMESTAMP ELSE NULL END,
                                  'iniciado', 1, 0)
                    """, (solicitante_codigo, profesional_codigo, servicio or '', motivo_val,
                          urgente_flag, urgente_flag))
                elif tiene_motivo:
                    cursor.execute("""
                        INSERT INTO contactos_ruana (
                            solicitante_codigo, profesional_codigo, servicio, motivo_contacto,
                            estado, pendiente_resolucion, contacto_externo_habilitado
                        ) VALUES (?, ?, ?, ?, 'iniciado', 1, 0)
                    """, (solicitante_codigo, profesional_codigo, servicio or '', motivo_val))
                else:
                    cursor.execute("""
                        INSERT INTO contactos_ruana (
                            solicitante_codigo, profesional_codigo, servicio,
                            estado, pendiente_resolucion, contacto_externo_habilitado
                        ) VALUES (?, ?, ?, 'iniciado', 1, 0)
                    """, (solicitante_codigo, profesional_codigo, servicio or ''))

                contacto_id = cursor.lastrowid

                # Iniciar negociación guiada con servicio propuesto por el contratante
                self._iniciar_negociacion_en_cursor(
                    cursor, contacto_id, servicio or '', solicitante_codigo
                )

                conn.commit()

                return {
                    'status': 'success',
                    'id': contacto_id,
                    'estado': 'iniciado',
                    'solicitante_codigo': solicitante_codigo,
                    'profesional_codigo': profesional_codigo,
                    'servicio': servicio or '',
                    'motivo_contacto': motivo_val,
                    'es_urgente': bool(urgente_flag) if tiene_urgente else False,
                    'creado_en': datetime.now().isoformat()
                }
            except Exception as e:
                return {'status': 'error', 'message': str(e)}
            finally:
                conn.close()

    def obtener_contacto_por_id(self, contacto_id: int) -> Optional[Dict[str, Any]]:
        """Obtiene un contacto RUANA por su ID interno"""
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                cursor.execute(
                    "SELECT * FROM contactos_ruana WHERE id = ?",
                    (contacto_id,)
                )
                row = cursor.fetchone()
                return dict(row) if row else None
            except Exception as e:
                print(f"Error obteniendo contacto RUANA: {e}")
                return None
            finally:
                conn.close()

    def aceptar_contacto_ruana(self, contacto_id: int, profesional_codigo: str) -> Dict[str, Any]:
        """
        Marca un contacto como 'aceptado' por el profesional y habilita contacto externo.
        Solo permite la transición desde estado 'iniciado'.
        """
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                cursor.execute(
                    "SELECT * FROM contactos_ruana WHERE id = ?",
                    (contacto_id,)
                )
                row = cursor.fetchone()
                if not row:
                    return {'status': 'error', 'message': f'Contacto {contacto_id} no encontrado'}

                contacto = dict(row)
                if contacto['profesional_codigo'] != profesional_codigo:
                    return {
                        'status': 'error',
                        'message': 'El profesional no coincide con el contacto'
                    }

                if contacto['estado'] != 'iniciado':
                    return {
                        'status': 'error',
                        'message': f"Transición inválida desde estado {contacto['estado']}"
                    }

                cursor.execute("""
                    UPDATE contactos_ruana
                    SET estado = 'aceptado',
                        contacto_externo_habilitado = 1,
                        pendiente_resolucion = 1,
                        fecha_aceptacion = CURRENT_TIMESTAMP,
                        actualizado_en = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (contacto_id,))

                conn.commit()
                return {
                    'status': 'success',
                    'id': contacto_id,
                    'estado': 'aceptado'
                }
            except Exception as e:
                return {'status': 'error', 'message': str(e)}
            finally:
                conn.close()

    def marcar_trabajo_en_progreso(self, contacto_id: int) -> Dict[str, Any]:
        """Transición a estado 'trabajo_en_progreso' desde 'aceptado' o 'iniciado'."""
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                cursor.execute(
                    "SELECT estado FROM contactos_ruana WHERE id = ?",
                    (contacto_id,)
                )
                row = cursor.fetchone()
                if not row:
                    return {'status': 'error', 'message': f'Contacto {contacto_id} no encontrado'}

                estado_actual = row[0]
                if estado_actual not in ('iniciado', 'aceptado'):
                    return {
                        'status': 'error',
                        'message': f"Transición inválida desde estado {estado_actual}"
                    }

                cursor.execute("""
                    UPDATE contactos_ruana
                    SET estado = 'trabajo_en_progreso',
                        pendiente_resolucion = 1,
                        fecha_trabajo_en_progreso = CURRENT_TIMESTAMP,
                        actualizado_en = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (contacto_id,))

                conn.commit()
                return {
                    'status': 'success',
                    'id': contacto_id,
                    'estado': 'trabajo_en_progreso'
                }
            except Exception as e:
                return {'status': 'error', 'message': str(e)}
            finally:
                conn.close()

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
        """
        Cierra el contacto como no concretado. Transacción atómica:
        - Estado → cerrado_no_concretado, pendiente_resolucion = 0.
        - -1 punto Score RUANA a cada aliado.
        - audit_log. No permitir si ya está en estado final.
        """
        sol = prof = None
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, estado, solicitante_codigo, profesional_codigo FROM contactos_ruana WHERE id = ?",
                    (contacto_id,)
                )
                row = cursor.fetchone()
                if not row:
                    return {'status': 'error', 'message': f'Contacto {contacto_id} no encontrado'}
                contacto = dict(row)
                estado_actual = (contacto.get('estado') or '').strip()
                if estado_actual in self._ESTADOS_FINALES_CONTACTO:
                    return {
                        'status': 'error',
                        'message': f'El contacto ya está cerrado o en estado final ({estado_actual}).'
                    }

                sol = contacto.get('solicitante_codigo')
                prof = contacto.get('profesional_codigo')

                cursor.execute("""
                    UPDATE contactos_ruana
                    SET estado = 'cerrado_no_concretado',
                        pendiente_resolucion = 0,
                        fecha_no_concretado = CURRENT_TIMESTAMP,
                        actualizado_en = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (contacto_id,))

                detalles = f'aliados={sol},{prof} motivo={motivo or "cierre sin trabajo"}'
                self._audit_log(cursor, 'contacto', contacto_id, 'no_concretado',
                                'aliado', actor_codigo, detalles)
                conn.commit()
            except Exception as e:
                return {'status': 'error', 'message': str(e)}
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

        if sol:
            self.aplicar_cambio_score(sol, -1, 'contacto_cerrado_no_concretado')
        if prof:
            self.aplicar_cambio_score(prof, -1, 'contacto_cerrado_no_concretado')
        return {'status': 'success', 'id': contacto_id, 'estado': 'cerrado_no_concretado'}

    def marcar_en_conversacion(self, contacto_id: int, actor_codigo: str = "") -> Dict[str, Any]:
        """
        Marca el contacto como 'en_conversacion', posponer_recordatorio = 1 y fecha_pospuesto_hasta = now + posponer_horas.
        La alerta se oculta solo hasta esa fecha (límite temporal configurable).
        """
        with self._lock:
            conn = None
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, estado FROM contactos_ruana WHERE id = ?",
                    (contacto_id,)
                )
                row = cursor.fetchone()
                if not row:
                    return {'status': 'error', 'message': f'Contacto {contacto_id} no encontrado'}
                estado_actual = (row[1] or '').strip()
                if estado_actual in self._ESTADOS_FINALES_CONTACTO:
                    return {
                        'status': 'error',
                        'message': f'El contacto ya está en estado final ({estado_actual}).'
                    }

                horas = self._get_posponer_horas()
                hasta = (datetime.now() + timedelta(hours=horas)).strftime('%Y-%m-%d %H:%M:%S')
                cursor.execute("PRAGMA table_info(contactos_ruana)")
                columnas = [r[1] for r in cursor.fetchall()]
                if 'fecha_pospuesto_hasta' in columnas:
                    cursor.execute("""
                        UPDATE contactos_ruana
                        SET estado = 'en_conversacion',
                            posponer_recordatorio = 1,
                            fecha_pospuesto_hasta = ?,
                            actualizado_en = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """, (hasta, contacto_id))
                else:
                    cursor.execute("""
                        UPDATE contactos_ruana
                        SET estado = 'en_conversacion',
                            posponer_recordatorio = 1,
                            actualizado_en = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """, (contacto_id,))

                self._audit_log(cursor, 'contacto', contacto_id, 'en_conversacion',
                                'aliado', actor_codigo, f'posponer_recordatorio=1,hasta={hasta}')
                conn.commit()
                return {'status': 'success', 'id': contacto_id, 'estado': 'en_conversacion'}
            except Exception as e:
                return {'status': 'error', 'message': str(e)}
            finally:
                if conn:
                    try:
                        conn.close()
                    except Exception:
                        pass

    def ocultar_contacto_del_panel(self, contacto_id: int, codigo_aliado: str) -> Dict[str, Any]:
        """
        Marca el contacto como oculto en el panel personal de este aliado (Finalizar chat).
        El contacto deja de mostrarse en contactos abiertos para ese codigo_aliado.
        """
        codigo_aliado = (codigo_aliado or "").strip()
        if not codigo_aliado:
            return {'status': 'error', 'message': 'Código de aliado obligatorio'}
        with self._lock:
            conn = None
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute("SELECT id, solicitante_codigo, profesional_codigo FROM contactos_ruana WHERE id = ?", (contacto_id,))
                row = cursor.fetchone()
                if not row:
                    return {'status': 'error', 'message': f'Contacto {contacto_id} no encontrado'}
                sol, prof = row[1], row[2]
                if codigo_aliado not in (str(sol or '').strip(), str(prof or '').strip()):
                    return {'status': 'error', 'message': 'No tienes permiso para finalizar este chat'}
                cursor.execute("""
                    INSERT OR IGNORE INTO contacto_panel_oculto (contacto_id, codigo_aliado) VALUES (?, ?)
                """, (contacto_id, codigo_aliado))
                conn.commit()
                return {'status': 'success', 'id': contacto_id}
            except Exception as e:
                return {'status': 'error', 'message': str(e)}
            finally:
                if conn:
                    try:
                        conn.close()
                    except Exception:
                        pass

    def listar_mensajes_contacto(self, contacto_id: int) -> List[Dict[str, Any]]:
        """
        Lista TODOS los mensajes del chat interno RUANA para un contacto.
        No filtra por emisor_codigo ni receptor_codigo; devuelve la conversación completa.
        La validación de permisos (solo solicitante y profesional pueden ver) se realiza
        en la capa API antes de invocar este método.
        Campos devueltos: id, contacto_id, emisor_codigo, texto, creado_en.
        Orden: creado_en ASC.
        """
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT m.id, m.contacto_id, m.emisor_codigo, m.texto, m.creado_en,
                           COALESCE(a.nombre, m.emisor_codigo) AS emisor_nombre
                    FROM chat_mensajes m
                    LEFT JOIN aliados a ON a.codigo = m.emisor_codigo
                    WHERE m.contacto_id = ?
                    ORDER BY m.creado_en ASC
                    """,
                    (contacto_id,)
                )
                return [dict(row) for row in cursor.fetchall()]
            except Exception as e:
                print(f"Error listar_mensajes_contacto: {e}")
                return []
            finally:
                conn.close()

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
        ref = self._parse_timestamp(ref)
        if not ref:
            return {
                'chat_referencia_en': None,
                'chat_expira_en': None,
                'chat_horas_restantes': self.CHAT_HORAS_VIGENCIA,
                'chat_horas_vigencia': self.CHAT_HORAS_VIGENCIA,
            }
        expira_en = ref + timedelta(hours=self.CHAT_HORAS_VIGENCIA)
        segundos_restantes = (expira_en - self._chat_now()).total_seconds()
        horas_restantes = max(0, int((segundos_restantes + 3599) // 3600))
        return {
            'chat_referencia_en': ref.isoformat(),
            'chat_expira_en': expira_en.isoformat(),
            'chat_horas_restantes': horas_restantes,
            'chat_horas_vigencia': self.CHAT_HORAS_VIGENCIA,
        }

    def _chat_esta_expirado(self, ref: Optional[datetime]) -> bool:
        ref = self._parse_timestamp(ref)
        if not ref:
            return False
        return (self._chat_now() - ref).total_seconds() > self.CHAT_HORAS_VIGENCIA * 3600

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
        """
        Timestamp de referencia para vigencia del chat: última actividad.
        A) Si hay mensajes → último mensaje. B) Si no → fecha_aceptacion o creado_en del contacto.
        """
        cursor.execute(
            "SELECT MAX(creado_en) FROM chat_mensajes WHERE contacto_id = ?",
            (contacto_id,)
        )
        ultimo_msg = (cursor.fetchone() or [None])[0]
        if ultimo_msg:
            return self._parse_timestamp(ultimo_msg)
        cursor.execute(
            "SELECT fecha_aceptacion, creado_en FROM contactos_ruana WHERE id = ?",
            (contacto_id,)
        )
        row = cursor.fetchone()
        if not row:
            return None
        fa, ce = row[0], row[1]
        dt_fa = self._parse_timestamp(fa)
        dt_ce = self._parse_timestamp(ce)
        if dt_fa and dt_ce:
            return max(dt_fa, dt_ce)
        return dt_fa or dt_ce

    def estado_chat_contacto(self, contacto_id: int, codigo: str) -> Dict[str, Any]:
        """Devuelve chat_expirado (bool) y mensajes_restantes (int). Vigencia 48h desde última actividad.
        También se considera expirado si el contacto está en estado final (p. ej. trabajo_cerrado cuando
        las dos partes confirmaron el valor y se envió la alerta de pago)."""
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT id, estado FROM contactos_ruana WHERE id = ?", (contacto_id,))
                row = cursor.fetchone()
                if not row:
                    return self._chat_estado_cerrado()
                estado = (row[1] or '').strip()
                if estado in self._ESTADOS_FINALES_CONTACTO:
                    return self._chat_estado_cerrado()
                ref = self._parse_timestamp(self._chat_referencia_ts(cursor, contacto_id))
                expirado = self._chat_esta_expirado(ref)
                cursor.execute("SELECT COUNT(*) FROM chat_mensajes WHERE contacto_id = ?", (contacto_id,))
                count = (cursor.fetchone() or [0])[0]
                restantes = max(0, self.CHAT_MAX_MENSAJES_TOTAL - count)
                estado_chat = {
                    'chat_expirado': expirado,
                    'mensajes_restantes': restantes,
                    'chat_max_mensajes': self.CHAT_MAX_MENSAJES_TOTAL,
                }
                estado_chat.update(self._chat_expiry_metadata(ref))
                if expirado:
                    estado_chat['mensajes_restantes'] = 0
                    estado_chat['chat_horas_restantes'] = 0
                return estado_chat
            except Exception as e:
                print(f"Error estado_chat_contacto: {e}")
                estado_chat = {
                    'chat_expirado': False,
                    'mensajes_restantes': self.CHAT_MAX_MENSAJES_TOTAL,
                    'chat_max_mensajes': self.CHAT_MAX_MENSAJES_TOTAL,
                }
                estado_chat.update(self._chat_expiry_metadata(None))
                return estado_chat
            finally:
                conn.close()

    def enviar_mensaje_chat(self, contacto_id: int, emisor_codigo: str, texto: str) -> Dict[str, Any]:
        """
        Envía un mensaje al chat interno RUANA. Confiable y bilateral: emisor y receptor
        lo ven inmediatamente vía GET /api/chat_mensajes (listar_mensajes_contacto devuelve todos).
        Limites: 30 mensajes totales por conversacion, 48h de vigencia desde ultima actividad.
        """
        # --- Validación previa: texto no vacío ---
        texto_clean = (texto or "").strip()
        if not texto_clean:
            return {'status': 'error', 'message': 'El mensaje no puede estar vacío'}

        emisor_norm = str(emisor_codigo or "").strip()
        if not emisor_norm:
            return {'status': 'error', 'message': 'emisor_codigo es obligatorio'}

        resultado: Dict[str, Any] = {'status': 'error', 'message': 'unknown'}
        profesional_para_regla5: Optional[str] = None
        codigo_penal_agotado: Optional[str] = None
        contacto_penal_agotado: Optional[int] = None

        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                # --- 1. Validar que el contacto existe ---
                cursor.execute(
                    "SELECT id, solicitante_codigo, profesional_codigo, estado FROM contactos_ruana WHERE id = ?",
                    (contacto_id,)
                )
                row = cursor.fetchone()
                if not row:
                    return {'status': 'error', 'message': 'Contacto no encontrado'}
                contacto = dict(row)

                # --- 2. Validar que emisor es solicitante o profesional (normalizar tipos) ---
                sol = str(contacto.get('solicitante_codigo') or '').strip()
                pro = str(contacto.get('profesional_codigo') or '').strip()
                if emisor_norm not in (sol, pro):
                    return {'status': 'error', 'message': 'No tienes permiso para escribir en este chat'}

                # --- 3. Validar que el contacto NO está en estado final ---
                estado = (contacto.get('estado') or '').strip()
                if estado in self._ESTADOS_FINALES_CONTACTO:
                    return {'status': 'error', 'message': 'Contacto cerrado; no se pueden enviar más mensajes.'}

                # --- 4. Validar vigencia: no expirado (48h desde último mensaje o aceptación/creación) ---
                ref = self._parse_timestamp(self._chat_referencia_ts(cursor, contacto_id))
                if self._chat_esta_expirado(ref):
                    return {
                        'status': 'error',
                        'message': 'Este chat ha expirado (48h desde la última actividad). Cierra el contacto desde el panel para resolver.'
                    }

                # --- 5. Validar que el chat no supera el limite total de mensajes ---
                cursor.execute(
                    "SELECT COUNT(*) FROM chat_mensajes WHERE contacto_id = ?",
                    (contacto_id,)
                )
                count_total = (cursor.fetchone() or [0])[0]
                if count_total >= self.CHAT_MAX_MENSAJES_TOTAL:
                    return {
                        'status': 'error',
                        'message': 'Este chat ha llegado al limite de 30 mensajes. Usa el panel para cerrar el contacto o resolverlo.'
                    }

                # --- 6. Inserción: guardar mensaje (visible para ambos aliados vía listar_mensajes_contacto) ---
                receptor_codigo = pro if emisor_norm == sol else sol
                cursor.execute("PRAGMA table_info(chat_mensajes)")
                cols_msg = [r[1] for r in cursor.fetchall()]
                if 'receptor_codigo' in cols_msg:
                    cursor.execute(
                        "INSERT INTO chat_mensajes (contacto_id, emisor_codigo, receptor_codigo, texto) VALUES (?, ?, ?, ?)",
                        (contacto_id, emisor_norm, receptor_codigo or None, texto_clean)
                    )
                else:
                    cursor.execute(
                        "INSERT INTO chat_mensajes (contacto_id, emisor_codigo, texto) VALUES (?, ?, ?)",
                        (contacto_id, emisor_norm, texto_clean)
                    )
                msg_id = cursor.lastrowid

                # --- 7. Actualizacion de estado: si el chat llega al limite total -> chat_agotado ---
                chat_agotado_ahora = False
                if count_total + 1 >= self.CHAT_MAX_MENSAJES_TOTAL:
                    cursor.execute(
                        """UPDATE contactos_ruana SET estado = 'chat_agotado', actualizado_en = CURRENT_TIMESTAMP
                           WHERE id = ? AND estado IN ('iniciado', 'aceptado', 'trabajo_en_progreso', 'en_conversacion')""",
                        (contacto_id,)
                    )
                    chat_agotado_ahora = (cursor.rowcount or 0) > 0

                conn.commit()

                # --- 8. Retorno: mensaje insertado (ambos aliados lo verán en GET /api/chat_mensajes) ---
                cursor.execute(
                    "SELECT id, contacto_id, emisor_codigo, texto, creado_en FROM chat_mensajes WHERE id = ?",
                    (msg_id,)
                )
                msg_row = cursor.fetchone()
                resultado = {'status': 'success', 'mensaje': dict(msg_row)}
                # Regla 5 solo si quien escribe es el profesional
                if emisor_norm == pro:
                    profesional_para_regla5 = pro
                # Penalización 7: quien agota el chat (mensaje 30) sin resultado declarado → -2
                if chat_agotado_ahora:
                    codigo_penal_agotado = emisor_norm
                    contacto_penal_agotado = int(contacto_id)
            except Exception as e:
                return {'status': 'error', 'message': str(e)}
            finally:
                conn.close()

        if profesional_para_regla5:
            try:
                hito = self.evaluar_regla5_respuestas_chat(profesional_para_regla5)
                if hito:
                    self.aplicar_cambio_score(hito[0], hito[1], hito[2])
            except Exception:
                pass
        if codigo_penal_agotado and contacto_penal_agotado:
            try:
                self.aplicar_penalizacion_chat_agotado_sin_resultado(
                    contacto_penal_agotado, codigo_penal_agotado
                )
            except Exception:
                pass
        return resultado

    def aplicar_penalizacion_chat_agotado_sin_resultado(
        self, contacto_id: int, codigo_aliado: str
    ) -> Optional[Dict[str, Any]]:
        """
        Penalización 7: al agotar el chat (30 mensajes) sin declarar resultado → -2
        solo a quien envió el mensaje que agotó el cupo.
        No aplica si el encargo ya está en cierre adecuado.
        Motivo: chat_agotado_sin_resultado_{contacto_id} (una vez).
        """
        codigo_aliado = (codigo_aliado or '').strip()
        if not codigo_aliado or not contacto_id:
            return None
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT estado, solicitante_codigo, profesional_codigo FROM contactos_ruana WHERE id = ?",
                    (int(contacto_id),),
                )
                row = cursor.fetchone()
                if not row:
                    return None
                estado = (row[0] or '').strip()
                sol = str(row[1] or '').strip()
                prof = str(row[2] or '').strip()
                if estado in self._ESTADOS_CIERRE_ADECUADO_CHAT:
                    return None
                if codigo_aliado not in (sol, prof):
                    return None
            except Exception:
                return None
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
        motivo = f'chat_agotado_sin_resultado_{int(contacto_id)}'
        if self._ya_aplicado_motivo_score(codigo_aliado, motivo):
            return None
        # También registrar tipo en contacto_penalizaciones_aplicadas
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT 1 FROM contacto_penalizaciones_aplicadas
                    WHERE contacto_id = ? AND tipo = 'chat_agotado'
                    """,
                    (int(contacto_id),),
                )
                if cursor.fetchone():
                    return None
            except Exception:
                return None
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
        result = self.aplicar_cambio_score(codigo_aliado, -2, motivo)
        if result.get('status') == 'success' and int(result.get('aplicado') or 0) != 0:
            with self._lock:
                try:
                    conn = self._connect()
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        INSERT OR IGNORE INTO contacto_penalizaciones_aplicadas (contacto_id, tipo)
                        VALUES (?, 'chat_agotado')
                        """,
                        (int(contacto_id),),
                    )
                    conn.commit()
                except Exception:
                    pass
                finally:
                    try:
                        conn.close()
                    except Exception:
                        pass
            return {'codigo': codigo_aliado, 'motivo': motivo, 'result': result}
        return None

    def _ya_aplicado_motivo_score(self, codigo_aliado: str, motivo: str) -> bool:
        codigo_aliado = (codigo_aliado or '').strip()
        motivo = (motivo or '').strip()
        if not codigo_aliado or not motivo:
            return True
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT 1 FROM score_movimientos WHERE codigo_aliado = ? AND motivo = ? LIMIT 1",
                    (codigo_aliado, motivo),
                )
                return cursor.fetchone() is not None
            except Exception:
                return True
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

    def listar_respuestas_rapidas_regla5(self, codigo_profesional: str) -> List[Dict[str, Any]]:
        """
        Respuestas válidas Regla 5: primer mensaje de chat del cliente (solicitante)
        y primer mensaje posterior del profesional en el mismo contacto, con delta ≤ 1 h.
        Devuelve una entrada por solicitante (la respuesta válida más temprana).
        """
        codigo_profesional = (codigo_profesional or '').strip()
        if not codigo_profesional:
            return []
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT c.id AS contacto_id, c.solicitante_codigo,
                           m.id AS msg_id, m.emisor_codigo, m.creado_en
                    FROM contactos_ruana c
                    JOIN chat_mensajes m ON m.contacto_id = c.id
                    WHERE c.profesional_codigo = ?
                    ORDER BY c.id ASC, m.creado_en ASC, m.id ASC
                    """,
                    (codigo_profesional,),
                )
                rows = [dict(r) for r in cursor.fetchall()]
            except Exception:
                return []
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

        por_contacto: Dict[int, Dict[str, Any]] = {}
        for row in rows:
            cid = int(row['contacto_id'])
            bucket = por_contacto.setdefault(cid, {
                'solicitante_codigo': str(row.get('solicitante_codigo') or '').strip(),
                'msgs': [],
            })
            bucket['msgs'].append(row)

        por_cliente: Dict[str, Dict[str, Any]] = {}
        for cid, data in por_contacto.items():
            sol = data['solicitante_codigo']
            pro = codigo_profesional
            if not sol or sol == pro:
                continue
            primer_cliente = None
            for msg in data['msgs']:
                if str(msg.get('emisor_codigo') or '').strip() == sol:
                    primer_cliente = msg
                    break
            if not primer_cliente:
                continue
            ts_cliente = self._parse_timestamp(primer_cliente.get('creado_en'))
            if not ts_cliente:
                continue
            primer_pro = None
            for msg in data['msgs']:
                if str(msg.get('emisor_codigo') or '').strip() != pro:
                    continue
                ts_pro = self._parse_timestamp(msg.get('creado_en'))
                if not ts_pro or ts_pro < ts_cliente:
                    continue
                if ts_pro == ts_cliente and int(msg.get('msg_id') or 0) <= int(primer_cliente.get('msg_id') or 0):
                    continue
                primer_pro = msg
                ts_respuesta = ts_pro
                break
            if not primer_pro:
                continue
            delta = (ts_respuesta - ts_cliente).total_seconds()
            if delta < 0 or delta > self.REGLA5_SEGUNDOS_RESPUESTA:
                continue
            candidato = {
                'contacto_id': cid,
                'solicitante_codigo': sol,
                'cliente_msg_id': int(primer_cliente.get('msg_id') or 0),
                'respuesta_msg_id': int(primer_pro.get('msg_id') or 0),
                'cliente_msg_en': ts_cliente,
                'respuesta_en': ts_respuesta,
            }
            prev = por_cliente.get(sol)
            if prev is None or candidato['respuesta_en'] < prev['respuesta_en']:
                por_cliente[sol] = candidato

        return sorted(
            por_cliente.values(),
            key=lambda x: (x['respuesta_en'], x['contacto_id']),
        )

    def evaluar_regla5_respuestas_chat(
        self,
        codigo_profesional: str,
    ) -> Optional[Tuple[str, int, str]]:
        """
        Regla 5: el profesional responde (<1 h) al primer mensaje de chat de 3 clientes
        distintos → +3. Cada lote de 3 clientes otorga el bonus una vez
        (motivo único por conjunto de códigos de cliente).
        """
        codigo_profesional = (codigo_profesional or '').strip()
        if not codigo_profesional:
            return None
        respuestas = self.listar_respuestas_rapidas_regla5(codigo_profesional)
        if len(respuestas) < self.REGLA5_CLIENTES_UMBRAL:
            return None
        for i in range(0, len(respuestas) - self.REGLA5_CLIENTES_UMBRAL + 1, self.REGLA5_CLIENTES_UMBRAL):
            lote = respuestas[i:i + self.REGLA5_CLIENTES_UMBRAL]
            if len(lote) < self.REGLA5_CLIENTES_UMBRAL:
                break
            codes = sorted(item['solicitante_codigo'] for item in lote)
            motivo = f"regla5_3_clientes_respuesta_1h_{'_'.join(codes)}"
            if not self._ya_aplicado_motivo_score(codigo_profesional, motivo):
                return (codigo_profesional, self.REGLA5_DELTA, motivo)
        return None

    def listar_contactos_recientes_con_chat(self, limite: int = 100) -> List[Dict[str, Any]]:
        """Lista contactos recientes con número de mensajes y fecha del último mensaje (para admin)."""
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("PRAGMA table_info(contactos_ruana)")
                cols = [r[1] for r in cursor.fetchall()]
                motivo_col = 'c.motivo_contacto, ' if 'motivo_contacto' in cols else ''
                urgente_col = 'COALESCE(c.es_urgente, 0) AS es_urgente, c.urgente_marcado_en, ' if 'es_urgente' in cols else ''
                cursor.execute(f"""
                    SELECT c.id, c.solicitante_codigo, c.profesional_codigo, c.servicio, c.estado, c.creado_en,
                           c.fecha_cierre, c.fecha_no_concretado, c.importe_final, c.comision, {motivo_col}{urgente_col}
                           (SELECT COUNT(*) FROM chat_mensajes m WHERE m.contacto_id = c.id) AS num_mensajes,
                           (SELECT MAX(m.creado_en) FROM chat_mensajes m WHERE m.contacto_id = c.id) AS ultimo_mensaje_en
                    FROM contactos_ruana c
                    ORDER BY c.creado_en DESC
                    LIMIT ?
                """, (limite,))
                lista = [dict(row) for row in cursor.fetchall()]
                for d in lista:
                    if 'es_urgente' in d:
                        d['es_urgente'] = bool(int(d.get('es_urgente') or 0))
                return lista
            except Exception as e:
                print(f"Error listar_contactos_recientes_con_chat: {e}")
                return []
            finally:
                conn.close()

    def listar_conversaciones_admin(self, limite: int = 500, offset: int = 0) -> List[Dict[str, Any]]:
        """
        Lista contactos con sus mensajes para GET /api/admin/chats (paginado).
        Orden: más recientes primero. LIMIT y OFFSET para carga progresiva.
        """
        offset = max(0, offset)
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT c.id AS contacto_id,
                           c.creado_en AS contacto_creado_en,
                           COALESCE(sol.nombre, c.solicitante_codigo) AS solicitante,
                           COALESCE(prof.nombre, c.profesional_codigo) AS profesional,
                           c.solicitante_codigo,
                           c.profesional_codigo,
                           COALESCE(c.es_urgente, 0) AS es_urgente,
                           c.urgente_marcado_en,
                           c.motivo_contacto,
                           (SELECT m.texto FROM chat_mensajes m WHERE m.contacto_id = c.id ORDER BY m.creado_en DESC LIMIT 1) AS ultimo_mensaje,
                           (SELECT MAX(m.creado_en) FROM chat_mensajes m WHERE m.contacto_id = c.id) AS fecha_ultimo,
                           (SELECT COUNT(*) FROM chat_mensajes m WHERE m.contacto_id = c.id) AS num_mensajes
                    FROM contactos_ruana c
                    LEFT JOIN aliados sol ON sol.codigo = c.solicitante_codigo
                    LEFT JOIN aliados prof ON prof.codigo = c.profesional_codigo
                    ORDER BY COALESCE((SELECT MAX(m.creado_en) FROM chat_mensajes m WHERE m.contacto_id = c.id), c.creado_en) DESC,
                             c.id DESC
                    LIMIT ? OFFSET ?
                """, (limite, offset))
                contactos = [dict(row) for row in cursor.fetchall()]
                for c in contactos:
                    c['es_urgente'] = bool(int(c.get('es_urgente') or 0))
                if not contactos:
                    return []
                ids = [c["contacto_id"] for c in contactos]
                placeholders = ",".join("?" * len(ids))
                # Solo mensajes con contacto_id válido (siempre en chat_mensajes)
                cursor.execute(f"""
                    SELECT m.id, m.contacto_id, m.emisor_codigo, m.texto, m.creado_en
                    FROM chat_mensajes m
                    WHERE m.contacto_id IS NOT NULL AND m.contacto_id IN ({placeholders})
                    ORDER BY m.contacto_id, m.creado_en ASC
                """, ids)
                filas_msg = cursor.fetchall()
                mensajes_por_contacto = {}
                for c in contactos:
                    mensajes_por_contacto[c["contacto_id"]] = []
                for row in filas_msg:
                    r = dict(row)
                    cid = r["contacto_id"]
                    if cid not in mensajes_por_contacto:
                        continue
                    contacto = next((x for x in contactos if x["contacto_id"] == cid), None)
                    sol = (contacto.get("solicitante_codigo") or "").strip()
                    pro = (contacto.get("profesional_codigo") or "").strip()
                    emisor = (r.get("emisor_codigo") or "").strip()
                    remitente = "solicitante" if emisor == sol else ("profesional" if emisor == pro else "aliado")
                    mensajes_por_contacto[cid].append({
                        "id": r.get("id"),
                        "texto": r.get("texto"),
                        "fecha": r.get("creado_en"),
                        "remitente": remitente,
                        "emisor_codigo": emisor,
                    })
                out = []
                for c in contactos:
                    cid = c["contacto_id"]
                    num_m = c.get("num_mensajes") or 0
                    ultimo = (c.get("ultimo_mensaje") or "").strip()
                    fecha_ultimo = c.get("fecha_ultimo")
                    if not ultimo and num_m == 0:
                        ultimo = "Sin mensajes aún"
                    if not fecha_ultimo:
                        fecha_ultimo = c.get("contacto_creado_en")
                    out.append({
                        "contacto_id": cid,
                        "solicitante": c.get("solicitante") or c.get("solicitante_codigo") or "",
                        "profesional": c.get("profesional") or c.get("profesional_codigo") or "",
                        "ultimo_mensaje": ultimo,
                        "fecha_ultimo": fecha_ultimo,
                        "num_mensajes": num_m,
                        "es_urgente": bool(c.get("es_urgente")),
                        "urgente_marcado_en": c.get("urgente_marcado_en"),
                        "motivo_contacto": c.get("motivo_contacto"),
                        "mensajes": mensajes_por_contacto.get(cid, []),
                    })
                return out
            except Exception as e:
                print(f"Error listar_conversaciones_admin: {e}")
                return []
            finally:
                conn.close()

    def listar_chat_messages(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """Lista mensajes de chat para admin. Un solo source of truth: chat_mensajes + JOIN aliados."""
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT cm.id, cm.texto AS content, cm.creado_en AS created_at,
                           s.codigo AS sender_codigo, s.nombre AS sender_nombre,
                           r.codigo AS receiver_codigo, r.nombre AS receiver_nombre
                    FROM chat_mensajes cm
                    JOIN contactos_ruana c ON c.id = cm.contacto_id
                    JOIN aliados s ON s.codigo = cm.emisor_codigo
                    LEFT JOIN aliados r ON r.codigo = (
                        CASE WHEN cm.emisor_codigo = c.solicitante_codigo THEN c.profesional_codigo
                             ELSE c.solicitante_codigo END
                    )
                    ORDER BY cm.creado_en DESC
                    LIMIT ? OFFSET ?
                """, (limit, offset))
                return [dict(row) for row in cursor.fetchall()]
            except Exception as e:
                print(f"Error listar_chat_messages: {e}")
                return []
            finally:
                conn.close()

    def _audit_log(self, cursor, entidad: str, entidad_id: int, accion: str,
                   actor_tipo: str = "", actor_codigo: str = "", detalles: str = "") -> None:
        """Registra una acción en audit_log."""
        cursor.execute("""
            INSERT INTO audit_log (entidad, entidad_id, accion, actor_tipo, actor_codigo, detalles)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (entidad, entidad_id, accion, actor_tipo or None, actor_codigo or None, detalles or None))

    def registrar_importe_contacto(self, contacto_id: int, parte: str,
                                   importe: float, moneda: str = "EUR",
                                   usuario: str = "") -> Dict[str, Any]:
        """
        Registra la declaración de importe por parte de solicitante o profesional.
        - Evita doble declaración (tabla confirmaciones_trabajo).
        - Apoyo RUANA segun apoyo_pct configurado. Disputa → -1; cierre no da score.
        - Coinciden → trabajo_cerrado, ingresos_ruana, audit_log (score al marcar Apoyo pagado).
        - No coinciden → importe_en_disputa, audit_log.
        - Regla 7: si el contratante declara en <24 h desde creado_en → +2 (una vez).
        """
        resultado = None
        evaluar_regla7 = False
        with self._lock:
            conn = None
            try:
                if importe is None:
                    return {'status': 'error', 'message': 'Importe obligatorio'}
                try:
                    importe_val = float(importe)
                except (TypeError, ValueError):
                    return {'status': 'error', 'message': 'Importe debe ser numérico'}
                if importe_val <= 0:
                    return {'status': 'error', 'message': 'Importe debe ser mayor que cero'}

                parte = (parte or "").strip().lower()
                if parte not in ("solicitante", "profesional"):
                    return {'status': 'error', 'message': "Parte debe ser 'solicitante' o 'profesional'"}

                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                cursor.execute("SELECT * FROM contactos_ruana WHERE id = ?", (contacto_id,))
                row = cursor.fetchone()
                if not row:
                    conn.close()
                    return {'status': 'error', 'message': f'Contacto {contacto_id} no encontrado'}
                contacto = dict(row)
                estado_actual = contacto['estado']

                if estado_actual in ('trabajo_cerrado', 'no_concretado', 'cerrado_no_concretado'):
                    conn.close()
                    msg = 'Este contacto ya está cerrado. Ambas partes han confirmado el importe.' if estado_actual == 'trabajo_cerrado' else f'Contacto ya cerrado con estado {estado_actual}'
                    return {'status': 'error', 'message': msg, 'estado': estado_actual}

                # Resolver aliado_id desde usuario (código); normalizar a string para búsqueda
                usuario_str = str(usuario or "").strip()
                aliado = self.obtener_aliado_por_codigo(usuario_str)
                if not aliado:
                    conn.close()
                    return {'status': 'error', 'message': 'Aliado no encontrado'}
                aliado_id = aliado.get('id')
                if not aliado_id:
                    conn.close()
                    return {'status': 'error', 'message': 'Aliado no encontrado'}

                solicitante_codigo = str(contacto.get('solicitante_codigo') or '').strip()
                if usuario_str != solicitante_codigo or parte != 'solicitante':
                    conn.close()
                    return {
                        'status': 'error',
                        'message': 'El importe solo puede confirmarlo el aliado que contrató el encargo.'
                    }

                # No permitir doble declaración por el mismo aliado
                cursor.execute(
                    "SELECT 1 FROM confirmaciones_trabajo WHERE contacto_id = ? AND aliado_id = ?",
                    (contacto_id, aliado_id)
                )
                if cursor.fetchone():
                    cursor.execute("SELECT estado FROM contactos_ruana WHERE id = ?", (contacto_id,))
                    row_estado = cursor.fetchone()
                    estado_ahora = dict(row_estado).get('estado', '') if row_estado else ''
                    conn.close()
                    if estado_ahora == 'trabajo_cerrado':
                        return {'status': 'error', 'message': 'Este contacto ya está cerrado. Ambas partes han confirmado el importe.', 'estado': 'trabajo_cerrado'}
                    return {'status': 'error', 'message': 'Ya has declarado el importe para este contacto. Solo puedes declarar una vez; la otra parte debe declarar el suyo con su propia cuenta.'}

                if parte == 'solicitante':
                    cursor.execute("""
                        UPDATE contactos_ruana
                        SET importe_solicitante = ?, importe_solicitante_moneda = ?,
                            declarado_por_solicitante = ?, fecha_declaracion_solicitante = CURRENT_TIMESTAMP,
                            actualizado_en = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """, (importe_val, moneda, usuario_str, contacto_id))
                else:
                    cursor.execute("""
                        UPDATE contactos_ruana
                        SET importe_profesional = ?, importe_profesional_moneda = ?,
                            declarado_por_profesional = ?, fecha_declaracion_profesional = CURRENT_TIMESTAMP,
                            actualizado_en = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """, (importe_val, moneda, usuario_str, contacto_id))

                cursor.execute("INSERT INTO confirmaciones_trabajo (contacto_id, aliado_id, importe_declarado) VALUES (?, ?, ?)",
                               (contacto_id, aliado_id, importe_val))
                self._audit_log(cursor, 'contacto', contacto_id, 'declaracion_importe', 'aliado', usuario_str,
                                f'parte={parte} importe={importe_val}')

                cursor.execute("SELECT * FROM contactos_ruana WHERE id = ?", (contacto_id,))
                contacto = dict(cursor.fetchone())
                importe_sol = contacto.get('importe_solicitante')
                importe_prof = contacto.get('importe_profesional')

                if importe_sol is not None:
                    # Comparar con redondeo a 2 decimales para evitar diferencias de precisión (100.0 vs 100.00)
                    if importe_prof is None or round(float(importe_sol), 2) == round(float(importe_prof), 2):
                        pct = self._get_apoyo_pct()
                        apoyo_ruana = round(float(importe_sol) * pct / 100.0, 2)
                        comision_pct = pct / 100.0
                        cursor.execute("""
                            UPDATE contactos_ruana
                            SET estado = 'trabajo_cerrado', pendiente_resolucion = 0,
                                importe_final = ?, comision = ?, comision_porcentaje = ?,
                                apoyo_ruana = ?, estado_pago = 'pendiente_pago', pendiente_pago = 1,
                                fecha_cierre = CURRENT_TIMESTAMP, actualizado_en = CURRENT_TIMESTAMP
                            WHERE id = ?
                        """, (importe_sol, apoyo_ruana, comision_pct, apoyo_ruana, contacto_id))
                        cursor.execute(
                            "INSERT INTO ingresos_ruana (contacto_id, importe_final, apoyo_ruana_2pct) VALUES (?, ?, ?)",
                            (contacto_id, importe_sol, apoyo_ruana)
                        )
                        self._audit_log(cursor, 'contacto', contacto_id, 'cierre_confirmado', 'sistema', '',
                                        f'importe={importe_sol} apoyo_ruana={apoyo_ruana}')
                        prof_codigo = (contacto.get('profesional_codigo') or '').strip() or str(contacto.get('profesional_codigo') or '')
                        self._insert_evento_sistema(
                            cursor, 'apoyo_generado',
                            f'Apoyo RUANA de {apoyo_ruana}€ generado por trabajo cerrado (contacto {contacto_id})',
                            actor_tipo='sistema', actor_codigo=prof_codigo or None,
                            metadata={'contacto_id': contacto_id, 'importe_final': float(importe_sol), 'apoyo_ruana': apoyo_ruana}
                        )
                        # Alerta de cobro: notificación al profesional (Apoyo RUANA, QR/Bizum)
                        if not prof_codigo:
                            cursor.execute("SELECT profesional_codigo FROM contactos_ruana WHERE id = ?", (contacto_id,))
                            row_prof = cursor.fetchone()
                            if row_prof and row_prof[0]:
                                prof_codigo = (row_prof[0] or '').strip() if isinstance(row_prof[0], str) else str(row_prof[0] or '')
                        try:
                            if prof_codigo:
                                cursor.execute(
                                    "SELECT qr_paypal_path, bizum_num FROM aliados WHERE codigo = ?",
                                    (prof_codigo,)
                                )
                                row_aliado = cursor.fetchone()
                                qr_path = row_aliado[0] if row_aliado and row_aliado[0] else None
                                bizum = row_aliado[1] if row_aliado and row_aliado[1] else None
                                default_qr, default_bizum = self._get_ruana_pago_defaults()
                                qr_path = qr_path or default_qr
                                bizum = bizum or default_bizum
                                mensaje = (
                                    f"Se ha generado un Apoyo a RUANA de {apoyo_ruana}€ por tu trabajo cerrado. "
                                    "Escanea el QR de PayPal o usa el número de Bizum para abonar el pago."
                                )
                                meta = json.dumps({
                                    'contacto_id': contacto_id, 'apoyo_ruana': apoyo_ruana,
                                    'qr_paypal_path': qr_path, 'bizum_num': bizum
                                }, ensure_ascii=False)
                                cursor.execute("""
                                    INSERT INTO notificaciones_aliado (aliado_codigo, tipo, titulo, mensaje, metadata, leida)
                                    VALUES (?, 'apoyo_ruana', 'Apoyo a RUANA', ?, ?, 0)
                                """, (prof_codigo, mensaje, meta))
                                print(f"[RUANA] Lógica de cobro: contacto {contacto_id} → trabajo_cerrado, apoyo_ruana={apoyo_ruana}€, notificación de cobro enviada al profesional {prof_codigo}")
                            else:
                                print(f"[RUANA] registrar_importe_contacto: contacto {contacto_id} trabajo_cerrado pero profesional_codigo vacío, no se pudo crear notificación de cobro.")
                        except Exception as notif_err:
                            print(f"[RUANA] Error creando notificación de cobro (contacto {contacto_id}): {notif_err}")
                        resultado_estado = 'trabajo_cerrado'
                    else:
                        cursor.execute("""
                            UPDATE contactos_ruana
                            SET estado = 'importe_en_disputa', pendiente_resolucion = 1,
                                importe_final = NULL, comision = NULL, estado_pago = 'no_generado',
                                pendiente_pago = 0, fecha_disputa = COALESCE(fecha_disputa, CURRENT_TIMESTAMP),
                                actualizado_en = CURRENT_TIMESTAMP
                            WHERE id = ?
                        """, (contacto_id,))
                        self._audit_log(cursor, 'contacto', contacto_id, 'conflicto_importe', 'sistema', '', 'discrepancia')
                        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='payment_conflicts'")
                        if cursor.fetchone():
                            cursor.execute("SELECT id FROM aliados WHERE codigo = ?", (contacto.get('solicitante_codigo'),))
                            r_sol = cursor.fetchone()
                            cursor.execute("SELECT id FROM aliados WHERE codigo = ?", (contacto.get('profesional_codigo'),))
                            r_prof = cursor.fetchone()
                            if r_sol and r_prof:
                                cursor.execute("""
                                    INSERT INTO payment_conflicts (trabajo_id, contratante_id, profesional_id,
                                        importe_contratante, importe_profesional, estado, created_at, updated_at)
                                    VALUES (?, ?, ?, ?, ?, 'PENDIENTE_PRUEBA', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                                """, (contacto_id, r_sol[0], r_prof[0], float(importe_sol), float(importe_prof)))
                        resultado_estado = 'importe_en_disputa'
                else:
                    resultado_estado = estado_actual

                conn.commit()
                resultado = {'status': 'success', 'id': contacto_id, 'estado': resultado_estado}
                evaluar_regla7 = True
            except Exception as e:
                return {'status': 'error', 'message': str(e)}
            finally:
                if conn is not None:
                    try:
                        conn.close()
                    except Exception:
                        pass

        if evaluar_regla7 and resultado and resultado.get('status') == 'success':
            try:
                hito = self.evaluar_regla7_declaracion_24h(contacto_id)
                if hito:
                    self.aplicar_cambio_score(hito[0], hito[1], hito[2])
            except Exception:
                pass
        return resultado if resultado is not None else {'status': 'error', 'message': 'Error desconocido'}

    def obtener_metricas_contactos(self) -> Dict[str, Any]:
        """
        Calcula métricas agregadas de contactos RUANA para usar en dashboards y motor de riesgo.
        - contactos_abiertos: en estados iniciado/aceptado/trabajo_en_progreso
        - contactos_no_resueltos: pendientes de resolución (flag)
        - contactos_en_disputa: estado importe_en_disputa
        """
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT COUNT(*) FROM contactos_ruana
                    WHERE estado IN ('iniciado', 'aceptado', 'trabajo_en_progreso')
                """)
                abiertos = cursor.fetchone()[0] or 0

                cursor.execute("""
                    SELECT COUNT(*) FROM contactos_ruana
                    WHERE pendiente_resolucion = 1
                """)
                no_resueltos = cursor.fetchone()[0] or 0

                cursor.execute("""
                    SELECT COUNT(*) FROM contactos_ruana
                    WHERE estado = 'importe_en_disputa'
                """)
                en_disputa = cursor.fetchone()[0] or 0

                # Contactos en disputa "prolongada": más de 7 días desde fecha_disputa
                cursor.execute("""
                    SELECT COUNT(*) FROM contactos_ruana
                    WHERE estado = 'importe_en_disputa'
                      AND fecha_disputa IS NOT NULL
                      AND julianday('now') - julianday(fecha_disputa) >= 7
                """)
                disputa_prolongada = cursor.fetchone()[0] or 0

                return {
                    'status': 'success',
                    'contactos_abiertos': abiertos,
                    'contactos_no_resueltos': no_resueltos,
                    'contactos_en_disputa': en_disputa,
                    'contactos_en_disputa_prolongada': disputa_prolongada
                }
            except Exception as e:
                print(f"Error obteniendo métricas de contactos: {e}")
                return {
                    'status': 'error',
                    'message': str(e)
                }
            finally:
                conn.close()

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
        """
        Métricas desde contactos_ruana para el motor de evaluación (tasa_respuesta, tasa_confirmacion, meses_sin_trabajo).
        - tasa_respuesta: como profesional, proporción de contactos que salieron de 'iniciado' (aceptó o más).
        - tasa_confirmacion: como profesional, proporción de contactos aceptados que llegaron a trabajo_cerrado o no_concretado.
        - meses_sin_trabajo: meses desde el último trabajo_cerrado (como profesional o solicitante); si no hay ninguno, 24.
        """
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                codigo = (codigo_aliado or '').strip()
                if not codigo:
                    return {"tasa_respuesta": 0.0, "tasa_confirmacion": 0.0, "meses_sin_trabajo": 24}

                # Contactos donde es profesional
                cursor.execute("""
                    SELECT estado FROM contactos_ruana WHERE profesional_codigo = ?
                """, (codigo,))
                rows_pro = cursor.fetchall()
                total_pro = len(rows_pro)
                estados_pro = [r[0] for r in rows_pro if r[0]]

                responded = sum(1 for e in estados_pro if e and e != 'iniciado')
                tasa_respuesta = (responded / total_pro) if total_pro > 0 else 1.0

                total_aceptados = sum(1 for e in estados_pro if e in (
                    'aceptado', 'trabajo_en_progreso', 'trabajo_cerrado', 'no_concretado', 'importe_en_disputa'))
                cerrados = sum(1 for e in estados_pro if e in ('trabajo_cerrado', 'no_concretado'))
                tasa_confirmacion = (cerrados / total_aceptados) if total_aceptados > 0 else 1.0

                # Meses desde último trabajo_cerrado (como profesional o solicitante); SQLite julianday
                cursor.execute("""
                    SELECT (julianday('now', 'localtime') - julianday(MAX(fecha_cierre))) / 30.44 AS meses
                    FROM contactos_ruana
                    WHERE (profesional_codigo = ? OR solicitante_codigo = ?) AND estado = 'trabajo_cerrado' AND fecha_cierre IS NOT NULL
                """, (codigo, codigo))
                row = cursor.fetchone()
                meses_sin_trabajo = 24
                if row and row[0] is not None:
                    try:
                        m = float(row[0])
                        meses_sin_trabajo = max(0, int(round(m)))
                    except (TypeError, ValueError):
                        meses_sin_trabajo = 24

                return {
                    "tasa_respuesta": round(tasa_respuesta, 4),
                    "tasa_confirmacion": round(tasa_confirmacion, 4),
                    "meses_sin_trabajo": meses_sin_trabajo,
                }
            except Exception:
                return {"tasa_respuesta": 0.0, "tasa_confirmacion": 0.0, "meses_sin_trabajo": 24}
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
    
    def obtener_contactos_abiertos_por_codigo(self, codigo_aliado: str) -> List[Dict[str, Any]]:
        """
        Contactos RUANA abiertos para alerta activa (negociación guiada + seguimiento post-servicio).
        Excluye posponer_recordatorio activo y contactos ocultos del panel.
        """
        codigo_aliado = (codigo_aliado or "").strip()
        if not codigo_aliado:
            return []
        estados_abiertos = (
            'iniciado', 'aceptado', 'trabajo_en_progreso', 'importe_en_disputa',
            'en_conversacion', 'acuerdo_alcanzado',
        )
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                placeholders = ','.join('?' for _ in estados_abiertos)
                posponer_sql = (
                    "(COALESCE(c.posponer_recordatorio, 0) = 0) OR "
                    "(c.fecha_pospuesto_hasta IS NOT NULL AND datetime(c.fecha_pospuesto_hasta) <= datetime('now'))"
                )
                if self.backend == "postgres":
                    posponer_sql = (
                        "(COALESCE(c.posponer_recordatorio, 0) = 0) OR "
                        "(c.fecha_pospuesto_hasta IS NOT NULL AND c.fecha_pospuesto_hasta <= now())"
                    )
                cursor.execute(f"""
                    SELECT
                        c.id,
                        c.solicitante_codigo,
                        c.profesional_codigo,
                        c.servicio,
                        c.estado,
                        c.pendiente_resolucion,
                        COALESCE(c.posponer_recordatorio, 0) AS posponer_recordatorio,
                        c.fecha_pospuesto_hasta,
                        c.fecha_aceptacion,
                        c.fecha_trabajo_en_progreso,
                        c.fecha_cierre,
                        c.fecha_disputa,
                        c.creado_en,
                        c.actualizado_en,
                        COALESCE(c.es_urgente, 0) AS es_urgente,
                        c.urgente_marcado_en,
                        c.motivo_contacto,
                        c.negociacion_json,
                        (SELECT 1 FROM confirmaciones_trabajo ct
                         INNER JOIN aliados a ON a.id = ct.aliado_id
                         WHERE ct.contacto_id = c.id AND TRIM(CAST(a.codigo AS TEXT)) = ?) AS ya_declaraste_importe
                    FROM contactos_ruana c
                    WHERE (TRIM(COALESCE(c.solicitante_codigo, '')) = ? OR TRIM(COALESCE(c.profesional_codigo, '')) = ?)
                      AND c.estado IN ({placeholders})
                      AND ({posponer_sql})
                      AND NOT EXISTS (
                          SELECT 1 FROM contacto_panel_oculto o
                          WHERE o.contacto_id = c.id AND TRIM(COALESCE(o.codigo_aliado, '')) = ?
                      )
                    ORDER BY c.actualizado_en DESC, c.creado_en DESC
                """, (codigo_aliado, codigo_aliado, codigo_aliado, *estados_abiertos, codigo_aliado))

                rows = cursor.fetchall()
                result = []
                for row in rows:
                    d = dict(row)
                    d['ya_declaraste_importe'] = d.get('ya_declaraste_importe') is not None
                    d['es_urgente'] = bool(int(d.get('es_urgente') or 0))
                    neg = neg_mgr.parse_negociacion(d.get('negociacion_json'))
                    d['negociacion_completa'] = bool(neg.get('completo')) or d.get('estado') == 'acuerdo_alcanzado'
                    d['paso_negociacion'] = neg.get('paso_actual')
                    paso = neg.get('paso_actual') or 'servicio'
                    campo = (neg.get('campos') or {}).get(paso, {})
                    rol_viewer = neg_mgr._rol_en_contacto(
                        codigo_aliado,
                        d.get('solicitante_codigo') or '',
                        d.get('profesional_codigo') or '',
                    ) or 'solicitante'
                    meta = neg_mgr.meta_negociacion(neg, rol_viewer, d.get('estado') or '')
                    d['negociacion_paso_label'] = neg_mgr.CAMPOS_LABELS.get(paso, paso)
                    d['negociacion_paso_estado'] = campo.get('estado') or neg_mgr.ESTADO_PENDIENTE
                    d['negociacion_paso_estado_label'] = neg_mgr.ESTADO_LABELS.get(
                        d['negociacion_paso_estado'], d['negociacion_paso_estado']
                    )
                    d['negociacion_propuesto_por'] = campo.get('propuesto_por')
                    d['negociacion_requiere_mi_respuesta'] = meta.get('requiere_mi_respuesta', False)
                    d['negociacion_meta'] = meta
                    result.append(d)
                return result
            except Exception as e:
                print(f"Error obteniendo contactos abiertos: {e}")
                return []
            finally:
                conn.close()

    def obtener_contacto_resumen(self, contacto_id: int) -> Optional[Dict[str, Any]]:
        """
        Obtiene un resumen seguro de un contacto:
        - No expone importes declarados por cada parte.
        - Expone solo el importe_final (si existe) y la comisión.
        """
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                cursor.execute("PRAGMA table_info(contactos_ruana)")
                cols = [r[1] for r in cursor.fetchall()]
                motivo_col = ', motivo_contacto' if 'motivo_contacto' in cols else ''
                apoyo_col = ', apoyo_ruana' if 'apoyo_ruana' in cols else ''
                urgente_col = ', COALESCE(es_urgente, 0) AS es_urgente, urgente_marcado_en' if 'es_urgente' in cols else ''
                neg_col = ', negociacion_json' if 'negociacion_json' in cols else ''
                cursor.execute(f"""
                    SELECT
                        id, solicitante_codigo, profesional_codigo, servicio, estado,
                        importe_final, comision, comision_porcentaje, estado_pago, pendiente_pago,
                        fecha_cierre, fecha_no_concretado, creado_en, actualizado_en
                        {apoyo_col}
                        {motivo_col}
                        {urgente_col}
                        {neg_col}
                    FROM contactos_ruana
                    WHERE id = ?
                """, (contacto_id,))

                row = cursor.fetchone()
                if not row:
                    return None
                d = dict(row)
                if 'es_urgente' in d:
                    d['es_urgente'] = bool(int(d.get('es_urgente') or 0))
                # Reparación: si trabajo cerrado con importe_final pero apoyo_ruana/comision faltan, calcular
                if d.get('estado') == 'trabajo_cerrado' and d.get('importe_final') is not None:
                    imp = float(d['importe_final'])
                    ap = d.get('apoyo_ruana') if 'apoyo_ruana' in d else None
                    com = d.get('comision')
                    if ap is None or com is None:
                        pct = self._get_apoyo_pct()
                        calculado = round(imp * pct / 100.0, 2)
                        if 'apoyo_ruana' in d:
                            d['apoyo_ruana'] = calculado
                        d['comision'] = calculado
                return d
            except Exception as e:
                print(f"Error obteniendo resumen de contacto: {e}")
                return None
            finally:
                conn.close()

    def listar_contactos_conflicto_pago(self) -> List[Dict[str, Any]]:
        """Lista contactos donde importe_A != importe_B (estado importe_en_disputa)."""
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, solicitante_codigo, profesional_codigo, servicio,
                           importe_solicitante, importe_profesional, comprobante_ruta,
                           estado, fecha_disputa, creado_en
                    FROM contactos_ruana
                    WHERE estado = 'importe_en_disputa'
                      AND importe_solicitante IS NOT NULL AND importe_profesional IS NOT NULL
                      AND importe_solicitante != importe_profesional
                    ORDER BY fecha_disputa DESC, id DESC
                """)
                return [dict(row) for row in cursor.fetchall()]
            except Exception:
                return []
            finally:
                conn.close()

    def listar_payment_conflicts_admin(self) -> List[Dict[str, Any]]:
        """Lista conflictos de payment_conflicts con nombres, orden created_at DESC."""
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='payment_conflicts'")
                if not cursor.fetchone():
                    conn.close()
                    return []
                cursor.execute("""
                    SELECT pc.id, pc.trabajo_id, pc.contratante_id, pc.profesional_id,
                           pc.importe_contratante, pc.importe_profesional, pc.estado,
                           pc.prueba_url, pc.comentario_admin, pc.created_at, pc.updated_at,
                           a_cont.nombre AS contratante_nombre, a_cont.codigo AS contratante_codigo,
                           a_prof.nombre AS profesional_nombre, a_prof.codigo AS profesional_codigo
                    FROM payment_conflicts pc
                    JOIN aliados a_cont ON a_cont.id = pc.contratante_id
                    JOIN aliados a_prof ON a_prof.id = pc.profesional_id
                    WHERE pc.estado IN ('PENDIENTE_PRUEBA', 'EN_REVISION')
                    ORDER BY pc.created_at DESC
                """)
                return [dict(row) for row in cursor.fetchall()]
            except Exception as e:
                print(f"Error listar_payment_conflicts_admin: {e}")
                return []
            finally:
                conn.close()

    def obtener_payment_conflict_por_trabajo(self, trabajo_id: int, codigo_aliado: str) -> Optional[Dict[str, Any]]:
        """Obtiene el conflicto abierto para un trabajo; codigo_aliado debe ser contratante o profesional."""
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='payment_conflicts'")
                if not cursor.fetchone():
                    conn.close()
                    return None
                cursor.execute(
                    "SELECT id FROM aliados WHERE codigo = ?", (codigo_aliado,)
                )
                r = cursor.fetchone()
                if not r:
                    conn.close()
                    return None
                aliado_id = r[0]
                cursor.execute("""
                    SELECT id, trabajo_id, contratante_id, profesional_id, importe_contratante, importe_profesional,
                           estado, prueba_url, comentario_admin, created_at, updated_at
                    FROM payment_conflicts
                    WHERE trabajo_id = ? AND (contratante_id = ? OR profesional_id = ?)
                """, (trabajo_id, aliado_id, aliado_id))
                row = cursor.fetchone()
                return dict(row) if row else None
            except Exception:
                return None
            finally:
                conn.close()

    def obtener_payment_conflict(self, conflict_id: int) -> Optional[Dict[str, Any]]:
        """Detalle de un conflicto por id."""
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='payment_conflicts'")
                if not cursor.fetchone():
                    conn.close()
                    return None
                cursor.execute("""
                    SELECT pc.id, pc.trabajo_id, pc.contratante_id, pc.profesional_id,
                           pc.importe_contratante, pc.importe_profesional, pc.estado,
                           pc.prueba_url, pc.comentario_admin, pc.created_at, pc.updated_at,
                           a_cont.nombre AS contratante_nombre, a_cont.codigo AS contratante_codigo,
                           a_prof.nombre AS profesional_nombre, a_prof.codigo AS profesional_codigo
                    FROM payment_conflicts pc
                    JOIN aliados a_cont ON a_cont.id = pc.contratante_id
                    JOIN aliados a_prof ON a_prof.id = pc.profesional_id
                    WHERE pc.id = ?
                """, (conflict_id,))
                row = cursor.fetchone()
                return dict(row) if row else None
            except Exception as e:
                print(f"Error obtener_payment_conflict: {e}")
                return None
            finally:
                conn.close()

    def subir_prueba_conflicto(self, conflict_id: int, contratante_codigo: str, prueba_url: str) -> Dict[str, Any]:
        """Solo contratante: guarda prueba_url y pasa estado a EN_REVISION."""
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT pc.id, pc.trabajo_id, pc.contratante_id, a.codigo AS contratante_codigo
                    FROM payment_conflicts pc
                    JOIN aliados a ON a.id = pc.contratante_id
                    WHERE pc.id = ?
                """, (conflict_id,))
                row = cursor.fetchone()
                if not row:
                    return {'status': 'error', 'message': 'Conflicto no encontrado'}
                conflicto = dict(row)
                cursor.execute("SELECT id FROM aliados WHERE codigo = ?", (contratante_codigo,))
                r_aliado = cursor.fetchone()
                if not r_aliado or r_aliado[0] != conflicto['contratante_id']:
                    return {'status': 'error', 'message': 'Solo el contratante puede subir la prueba'}
                cursor.execute("""
                    UPDATE payment_conflicts SET estado = 'EN_REVISION', prueba_url = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (prueba_url, conflict_id))
                trabajo_id = int(conflicto['trabajo_id'])
                contratante_norm = str(conflicto.get('contratante_codigo') or contratante_codigo or '').strip()
                self._marcar_notificaciones_contacto_leidas(
                    cursor, contratante_norm, trabajo_id,
                    tipos=['importe_impugnado', 'prueba_conflicto_en_revision']
                )
                mensaje = (
                    f"Documentacion enviada para el contacto #{trabajo_id}; "
                    "queda pendiente de revision por RUANA."
                )
                meta = json.dumps({
                    'contacto_id': trabajo_id,
                    'conflict_id': conflict_id,
                    'prueba_url': prueba_url
                }, ensure_ascii=False)
                cursor.execute("""
                    INSERT INTO notificaciones_aliado (aliado_codigo, tipo, titulo, mensaje, metadata, leida)
                    VALUES (?, 'prueba_conflicto_en_revision', 'Documentacion en revision', ?, ?, 0)
                """, (contratante_norm, mensaje, meta))
                conn.commit()
                return {'status': 'success', 'id': conflict_id, 'estado': 'EN_REVISION'}
            except Exception as e:
                return {'status': 'error', 'message': str(e)}
            finally:
                conn.close()

    def resolver_payment_conflict_admin(self, conflict_id: int, decision: str, comentario: str,
                                        admin_codigo: str = "") -> Dict[str, Any]:
        """Admin resuelve: decision in (contratante, profesional, rechazado). comentario obligatorio."""
        decision = (decision or "").strip().lower()
        if decision not in ("contratante", "profesional", "rechazado"):
            return {'status': 'error', 'message': 'decision debe ser contratante, profesional o rechazado'}
        if not (comentario or "").strip():
            return {'status': 'error', 'message': 'comentario es obligatorio'}
        resultado = {'status': 'error', 'message': 'unknown'}
        decision_penal_disputa: Optional[str] = None
        contacto_penal_disputa: Optional[int] = None
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, trabajo_id, importe_contratante, importe_profesional, estado
                    FROM payment_conflicts WHERE id = ?
                """, (conflict_id,))
                row = cursor.fetchone()
                if not row:
                    return {'status': 'error', 'message': 'Conflicto no encontrado'}
                pc = dict(row)
                if pc.get('estado') not in ('PENDIENTE_PRUEBA', 'EN_REVISION'):
                    return {'status': 'error', 'message': 'Este conflicto ya esta resuelto o cerrado'}
                trabajo_id = pc['trabajo_id']
                nuevo_estado = 'RECHAZADO' if decision == 'rechazado' else 'RESUELTO'
                importe_valido = None
                cerro_contacto_disputa = False
                if decision == 'contratante':
                    importe_valido = float(pc['importe_contratante'])
                elif decision in ('profesional', 'rechazado'):
                    importe_valido = float(pc['importe_profesional'])
                cursor.execute("""
                    UPDATE payment_conflicts SET estado = ?, comentario_admin = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (nuevo_estado, (comentario or "").strip()[:2000], conflict_id))
                if importe_valido is not None and trabajo_id:
                    cursor.execute(
                        "SELECT id, solicitante_codigo, profesional_codigo, estado FROM contactos_ruana WHERE id = ?",
                        (trabajo_id,)
                    )
                    c = cursor.fetchone()
                    if c and dict(c).get('estado') == 'importe_en_disputa':
                        d = dict(c)
                        pct = self._get_apoyo_pct()
                        apoyo = round(importe_valido * pct / 100.0, 2)
                        comision_pct = pct / 100.0
                        estado_pago_final = 'pendiente_pago' if apoyo > 0 else 'no_generado'
                        pendiente_pago_final = 1 if apoyo > 0 else 0
                        cursor.execute("""
                            UPDATE contactos_ruana
                            SET estado = 'trabajo_cerrado', pendiente_resolucion = 0,
                                importe_final = ?, comision = ?, comision_porcentaje = ?,
                                apoyo_ruana = ?, estado_pago = ?, pendiente_pago = ?,
                                fecha_cierre = CURRENT_TIMESTAMP, actualizado_en = CURRENT_TIMESTAMP
                            WHERE id = ?
                        """, (importe_valido, apoyo, comision_pct, apoyo, estado_pago_final, pendiente_pago_final, trabajo_id))
                        cerro_contacto_disputa = True
                        if apoyo > 0:
                            cursor.execute(
                                "INSERT INTO ingresos_ruana (contacto_id, importe_final, apoyo_ruana_2pct) VALUES (?, ?, ?)",
                                (trabajo_id, importe_valido, apoyo)
                            )
                        self._audit_log(cursor, 'contacto', trabajo_id, 'conflicto_resuelto_admin',
                                        'admin', admin_codigo, f'payment_conflict_id={conflict_id} decision={decision} importe={importe_valido}')
                        self._insert_evento_sistema(
                            cursor, 'apoyo_generado',
                            f'Apoyo RUANA de {apoyo}€ generado (payment_conflict {conflict_id} resuelto)',
                            actor_tipo='admin', actor_codigo=admin_codigo or None,
                            metadata={'contacto_id': trabajo_id, 'importe_final': importe_valido, 'apoyo_ruana': apoyo}
                        )
                        sol_codigo = (d.get('solicitante_codigo') or '').strip()
                        if sol_codigo:
                            self._marcar_notificaciones_contacto_leidas(
                                cursor, sol_codigo, trabajo_id,
                                tipos=['importe_impugnado', 'prueba_conflicto_en_revision']
                            )
                        prof_codigo = (d.get('profesional_codigo') or '').strip()
                        if prof_codigo:
                            self._marcar_notificaciones_contacto_leidas(
                                cursor, prof_codigo, trabajo_id,
                                tipos=['apoyo_ruana', 'pago_rechazado']
                            )
                        if prof_codigo and apoyo > 0:
                            cursor.execute(
                                "SELECT qr_paypal_path, bizum_num FROM aliados WHERE codigo = ?",
                                (prof_codigo,)
                            )
                            row_aliado = cursor.fetchone()
                            qr_path = row_aliado[0] if row_aliado and row_aliado[0] else None
                            bizum = row_aliado[1] if row_aliado and row_aliado[1] else None
                            default_qr, default_bizum = self._get_ruana_pago_defaults()
                            qr_path = qr_path or default_qr
                            bizum = bizum or default_bizum
                            mensaje = (
                                f"Se ha generado un Apoyo a RUANA de {apoyo}€ por tu trabajo cerrado. "
                                "Escanea el QR de PayPal o usa el número de Bizum para abonar el pago."
                            )
                            meta = json.dumps({
                                'contacto_id': trabajo_id, 'apoyo_ruana': apoyo,
                                'qr_paypal_path': qr_path, 'bizum_num': bizum
                            }, ensure_ascii=False)
                            cursor.execute("""
                                INSERT INTO notificaciones_aliado (aliado_codigo, tipo, titulo, mensaje, metadata, leida)
                                VALUES (?, 'apoyo_ruana', 'Apoyo a RUANA', ?, ?, 0)
                            """, (prof_codigo, mensaje, meta))
                conn.commit()
                resultado = {'status': 'success', 'conflict_id': conflict_id, 'estado': nuevo_estado,
                             'importe_final': importe_valido}
                # Penalización 8: -3 al perdedor si admin da la razón a una parte
                if (
                    cerro_contacto_disputa
                    and decision in ('contratante', 'profesional')
                    and trabajo_id
                ):
                    decision_penal_disputa = decision
                    contacto_penal_disputa = int(trabajo_id)
            except Exception as e:
                resultado = {'status': 'error', 'message': str(e)}
            finally:
                conn.close()
        if (
            resultado.get('status') == 'success'
            and decision_penal_disputa in ('contratante', 'profesional')
            and contacto_penal_disputa
        ):
            try:
                self.aplicar_penalizacion_disputa_perdida(
                    contacto_penal_disputa, decision_penal_disputa
                )
            except Exception:
                pass
        return resultado

    def aplicar_penalizacion_disputa_perdida(
        self, contacto_id: int, decision: str
    ) -> Optional[Dict[str, Any]]:
        """
        Penalización 8: perder una disputa resuelta por admin → -3 al perdedor.
        decision=contratante → pierde el profesional; decision=profesional → pierde el solicitante.
        No aplica si decision=rechazado. Motivo: disputa_perdida_{contacto_id}.
        """
        decision = (decision or '').strip().lower()
        if decision not in ('contratante', 'profesional') or not contacto_id:
            return None
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT solicitante_codigo, profesional_codigo FROM contactos_ruana WHERE id = ?",
                    (int(contacto_id),),
                )
                row = cursor.fetchone()
                if not row:
                    return None
                sol = str(row[0] or '').strip()
                prof = str(row[1] or '').strip()
            except Exception:
                return None
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
        perdedor = prof if decision == 'contratante' else sol
        if not perdedor:
            return None
        motivo = f'disputa_perdida_{int(contacto_id)}'
        if self._ya_aplicado_motivo_score(perdedor, motivo):
            return None
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT 1 FROM contacto_penalizaciones_aplicadas
                    WHERE contacto_id = ? AND tipo = 'disputa_perdida'
                    """,
                    (int(contacto_id),),
                )
                if cursor.fetchone():
                    return None
            except Exception:
                return None
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
        result = self.aplicar_cambio_score(perdedor, -3, motivo)
        if result.get('status') == 'success' and int(result.get('aplicado') or 0) != 0:
            with self._lock:
                try:
                    conn = self._connect()
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        INSERT OR IGNORE INTO contacto_penalizaciones_aplicadas (contacto_id, tipo)
                        VALUES (?, 'disputa_perdida')
                        """,
                        (int(contacto_id),),
                    )
                    conn.commit()
                except Exception:
                    pass
                finally:
                    try:
                        conn.close()
                    except Exception:
                        pass
            return {'codigo': perdedor, 'motivo': motivo, 'result': result}
        return None

    def resolver_conflicto_pago(self, contacto_id: int, importe_valido: float,
                                admin_codigo: str = "") -> Dict[str, Any]:
        """
        Admin resuelve conflicto: define importe valido, se aplica apoyo_pct, cierra contacto, audit.
        El score por encargo completado se aplica al marcar Apoyo como pagado (Regla 2).
        """
        imp = apoyo = 0.0
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, solicitante_codigo, profesional_codigo, estado FROM contactos_ruana WHERE id = ?",
                    (contacto_id,)
                )
                row = cursor.fetchone()
                if not row:
                    return {'status': 'error', 'message': 'Contacto no encontrado'}
                contacto = dict(row)
                if contacto['estado'] != 'importe_en_disputa':
                    return {'status': 'error', 'message': 'El contacto no está en conflicto de pago'}

                try:
                    imp = float(importe_valido)
                except (TypeError, ValueError):
                    return {'status': 'error', 'message': 'Importe válido debe ser numérico'}
                if imp <= 0:
                    return {'status': 'error', 'message': 'Importe debe ser mayor que cero'}

                pct = self._get_apoyo_pct()
                apoyo = round(imp * pct / 100.0, 2)
                comision_pct = pct / 100.0
                cursor.execute("""
                    UPDATE contactos_ruana
                    SET estado = 'trabajo_cerrado', pendiente_resolucion = 0,
                        importe_final = ?, comision = ?, comision_porcentaje = ?,
                        apoyo_ruana = ?, estado_pago = 'pendiente_pago', pendiente_pago = 1,
                        fecha_cierre = CURRENT_TIMESTAMP, actualizado_en = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (imp, apoyo, comision_pct, apoyo, contacto_id))
                cursor.execute(
                    "INSERT INTO ingresos_ruana (contacto_id, importe_final, apoyo_ruana_2pct) VALUES (?, ?, ?)",
                    (contacto_id, imp, apoyo)
                )
                self._audit_log(cursor, 'contacto', contacto_id, 'conflicto_resuelto_admin',
                                'admin', admin_codigo, f'importe_valido={imp} apoyo_ruana={apoyo}')
                self._insert_evento_sistema(
                    cursor, 'apoyo_generado',
                    f'Apoyo RUANA de {apoyo}€ generado (resolución admin contacto {contacto_id})',
                    actor_tipo='admin', actor_codigo=admin_codigo or None,
                    metadata={'contacto_id': contacto_id, 'importe_final': imp, 'apoyo_ruana': apoyo}
                )
                prof_codigo = (contacto.get('profesional_codigo') or '').strip()
                if prof_codigo:
                    cursor.execute(
                        "SELECT qr_paypal_path, bizum_num FROM aliados WHERE codigo = ?",
                        (prof_codigo,)
                    )
                    row_aliado = cursor.fetchone()
                    qr_path = row_aliado[0] if row_aliado and row_aliado[0] else None
                    bizum = row_aliado[1] if row_aliado and row_aliado[1] else None
                    default_qr, default_bizum = self._get_ruana_pago_defaults()
                    qr_path = qr_path or default_qr
                    bizum = bizum or default_bizum
                    mensaje = (
                        f"Se ha generado un Apoyo a RUANA de {apoyo}€ por tu trabajo cerrado. "
                        "Escanea el QR de PayPal o usa el número de Bizum para abonar el pago."
                    )
                    meta = json.dumps({
                        'contacto_id': contacto_id, 'apoyo_ruana': apoyo,
                        'qr_paypal_path': qr_path, 'bizum_num': bizum
                    }, ensure_ascii=False)
                    cursor.execute("""
                        INSERT INTO notificaciones_aliado (aliado_codigo, tipo, titulo, mensaje, metadata, leida)
                        VALUES (?, 'apoyo_ruana', 'Apoyo a RUANA', ?, ?, 0)
                    """, (prof_codigo, mensaje, meta))
                conn.commit()
            except Exception as e:
                return {'status': 'error', 'message': str(e)}
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

        return {'status': 'success', 'contacto_id': contacto_id, 'importe_final': imp, 'apoyo_ruana': apoyo}

    def listar_contactos_pagos_apoyo(self) -> List[Dict[str, Any]]:
        """Lista contactos con trabajo_cerrado e importe_final (Apoyo RUANA generado) para gestión de estado de pago."""
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT c.id, c.solicitante_codigo, c.profesional_codigo, c.servicio,
                           c.importe_final, c.apoyo_ruana, c.estado_pago, c.pendiente_pago, c.fecha_cierre,
                           c.comprobante_ruta,
                           COALESCE(c.es_urgente, 0) AS es_urgente, c.urgente_marcado_en, c.creado_en,
                           a_sol.nombre AS solicitante_nombre, a_prof.nombre AS profesional_nombre
                    FROM contactos_ruana c
                    LEFT JOIN aliados a_sol ON a_sol.codigo = c.solicitante_codigo
                    LEFT JOIN aliados a_prof ON a_prof.codigo = c.profesional_codigo
                    WHERE c.estado = 'trabajo_cerrado' AND c.importe_final IS NOT NULL
                      AND COALESCE(c.apoyo_ruana, 0) > 0
                    ORDER BY c.fecha_cierre IS NULL, c.fecha_cierre DESC, c.id DESC
                """)
                lista = [dict(row) for row in cursor.fetchall()]
                for d in lista:
                    d['es_urgente'] = bool(int(d.get('es_urgente') or 0))
                    if d.get('importe_final') is not None and d.get('apoyo_ruana') is None:
                        try:
                            d['apoyo_ruana'] = round(float(d['importe_final']) * self._get_apoyo_pct() / 100.0, 2)
                        except (TypeError, ValueError):
                            pass
                return lista
            except Exception as e:
                print(f"Error listar_contactos_pagos_apoyo: {e}")
                return []
            finally:
                conn.close()

    def listar_contactos_pagos_en_revision(self) -> List[Dict[str, Any]]:
        """Lista contactos con estado_pago = 'en_revision' (comprobante subido, pendiente de aprobar/rechazar)."""
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT c.id, c.solicitante_codigo, c.profesional_codigo, c.servicio,
                           c.importe_final, c.apoyo_ruana, c.estado_pago, c.comprobante_ruta, c.fecha_cierre,
                           a_prof.nombre AS profesional_nombre
                    FROM contactos_ruana c
                    LEFT JOIN aliados a_prof ON a_prof.codigo = c.profesional_codigo
                    WHERE c.estado = 'trabajo_cerrado' AND c.importe_final IS NOT NULL
                      AND c.estado_pago = 'en_revision'
                      AND COALESCE(c.apoyo_ruana, 0) > 0
                    ORDER BY c.fecha_cierre IS NULL, c.fecha_cierre DESC, c.id DESC
                """)
                lista = [dict(row) for row in cursor.fetchall()]
                for d in lista:
                    if d.get('importe_final') is not None and d.get('apoyo_ruana') is None:
                        try:
                            d['apoyo_ruana'] = round(float(d['importe_final']) * self._get_apoyo_pct() / 100.0, 2)
                        except (TypeError, ValueError):
                            pass
                return lista
            except Exception as e:
                print(f"Error listar_contactos_pagos_en_revision: {e}")
                return []
            finally:
                conn.close()

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
        """
        Regla 7: el contratante declara el importe antes de 24 h desde contactos_ruana.creado_en
        → +2 al solicitante. Una vez por contacto (motivo regla7_declaracion_24h_{id}).
        """
        try:
            contacto_id = int(contacto_id)
        except (TypeError, ValueError):
            return None
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, solicitante_codigo, creado_en, fecha_declaracion_solicitante
                    FROM contactos_ruana WHERE id = ?
                """, (contacto_id,))
                row = cursor.fetchone()
                if not row:
                    return None
                d = dict(row)
            except Exception:
                return None
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
        sol = str(d.get('solicitante_codigo') or '').strip()
        if not sol or not self._es_invitador_elegible_score(sol):
            return None
        ts_inicio = self._parse_timestamp(d.get('creado_en'))
        ts_decl = self._parse_timestamp(
            fecha_declaracion if fecha_declaracion is not None else d.get('fecha_declaracion_solicitante')
        )
        if not ts_inicio or not ts_decl:
            return None
        if ts_decl < ts_inicio:
            return None
        if (ts_decl - ts_inicio) >= timedelta(hours=self.REGLA7_HORAS_LIMITE):
            return None
        motivo = f'regla7_declaracion_24h_{contacto_id}'
        if self._ya_aplicado_motivo_score(sol, motivo):
            return None
        return (sol, self.REGLA7_DELTA, motivo)

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
        """Día calendario del servidor (local) en YYYY-MM-DD."""
        return datetime.now().strftime('%Y-%m-%d')

    def _motivo_regla8(self, dia_fin: str) -> str:
        return f'regla8_racha_7dias_{dia_fin}'

    def _tiene_premio_regla8_reciente(self, codigo_aliado: str, dia_fin: str) -> bool:
        """
        True si ya hay un premio Regla 8 cuyo día de cierre está en [dia_fin-6, dia_fin].
        Evita +3 diario tras la 1ª racha; la siguiente racha completa puede premiarse.
        """
        codigo_aliado = (codigo_aliado or '').strip()
        dia_fin = (dia_fin or '').strip()
        if not codigo_aliado or not dia_fin:
            return True
        try:
            fin = datetime.strptime(dia_fin, '%Y-%m-%d')
        except ValueError:
            return True
        dia_min = (fin - timedelta(days=self.REGLA8_DIAS_RACHA - 1)).strftime('%Y-%m-%d')
        prefijo = 'regla8_racha_7dias_'
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT motivo FROM score_movimientos
                    WHERE codigo_aliado = ? AND motivo LIKE ?
                    """,
                    (codigo_aliado, prefijo + '%'),
                )
                rows = cursor.fetchall()
            except Exception:
                return True
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
        for row in rows:
            motivo = row[0] if not isinstance(row, dict) else row.get('motivo')
            motivo = str(motivo or '')
            if not motivo.startswith(prefijo):
                continue
            dia_motivo = motivo[len(prefijo):]
            if len(dia_motivo) == 10 and dia_min <= dia_motivo <= dia_fin:
                return True
        return False

    def registrar_acceso_login(
        self,
        codigo_aliado: str,
        dia: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Registra un día de login (máx. 1 fila/día) y evalúa Regla 8.
        Antes de insertar el acceso de hoy aplica Penalización 6 (semanas sin entrar).
        Solo debe llamarse desde POST /api/aliado/login.
        """
        codigo_aliado = (codigo_aliado or '').strip()
        if not codigo_aliado:
            return {'status': 'error', 'message': 'Código obligatorio'}
        dia_val = (dia or '').strip() or self._dia_hoy_servidor()
        if len(dia_val) != 10 or dia_val[4] != '-' or dia_val[7] != '-':
            return {'status': 'error', 'message': 'Día inválido'}

        # Penalización 6 ANTES de registrar el acceso de hoy (si no, MAX(dia)=hoy y no penaliza)
        try:
            self.aplicar_penalizacion_sin_acceso_semanal(codigo_aliado, dia_ref=dia_val)
        except Exception:
            pass

        with self._lock:
            conn = None
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT 1 FROM aliados WHERE codigo = ? LIMIT 1",
                    (codigo_aliado,),
                )
                if not cursor.fetchone():
                    return {'status': 'error', 'message': 'Aliado no encontrado'}
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO aliado_accesos_dia (codigo_aliado, dia)
                    VALUES (?, ?)
                    """,
                    (codigo_aliado, dia_val),
                )
                conn.commit()
            except Exception as e:
                return {'status': 'error', 'message': str(e)}
            finally:
                if conn is not None:
                    try:
                        conn.close()
                    except Exception:
                        pass

        aplicado = False
        motivo = None
        try:
            hito = self.evaluar_regla8_racha_7dias(codigo_aliado, dia_fin=dia_val)
            if hito:
                self.aplicar_cambio_score(hito[0], hito[1], hito[2])
                aplicado = True
                motivo = hito[2]
        except Exception:
            pass
        return {
            'status': 'success',
            'codigo': codigo_aliado,
            'dia': dia_val,
            'regla8_aplicada': aplicado,
            'motivo': motivo,
        }

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
        """
        Penalización 6: sin entrar a la app (login) durante 7 días de calendario → -1.
        Repetible: un -1 por cada bloque completo de 7 días sin acceso desde el último login
        (o desde creado_en si nunca entró). Motivo: sin_acceso_7d_{YYYY-MM-DD}.
        """
        codigo_aliado = (codigo_aliado or '').strip()
        if not codigo_aliado:
            return []
        aliado = self.obtener_aliado_por_codigo(codigo_aliado)
        if not aliado:
            return []
        estado = (aliado.get('estado') or '').strip()
        if estado != 'activo':
            return []
        if not self._es_invitador_elegible_score(codigo_aliado):
            return []
        dia_hoy = (dia_ref or '').strip() or self._dia_hoy_servidor()
        try:
            hoy_dt = datetime.strptime(dia_hoy[:10], '%Y-%m-%d')
        except ValueError:
            return []
        baseline = self._baseline_acceso_dia(codigo_aliado)
        if not baseline:
            return []
        try:
            base_dt = datetime.strptime(baseline[:10], '%Y-%m-%d')
        except ValueError:
            return []
        dias_ausente = (hoy_dt - base_dt).days
        if dias_ausente < self.PENAL6_DIAS_SIN_ACCESO:
            return []
        semanas = dias_ausente // self.PENAL6_DIAS_SIN_ACCESO
        aplicados: List[Dict[str, Any]] = []
        for k in range(1, semanas + 1):
            dia_fin = (base_dt + timedelta(days=k * self.PENAL6_DIAS_SIN_ACCESO)).strftime('%Y-%m-%d')
            motivo = f'sin_acceso_7d_{dia_fin}'
            if self._ya_aplicado_motivo_score(codigo_aliado, motivo):
                continue
            result = self.aplicar_cambio_score(codigo_aliado, self.PENAL6_DELTA, motivo)
            if result.get('status') == 'success' and int(result.get('aplicado') or 0) != 0:
                aplicados.append({'motivo': motivo, 'result': result})
        return aplicados

    def evaluar_regla8_racha_7dias(
        self,
        codigo_aliado: str,
        dia_fin: Optional[str] = None,
    ) -> Optional[Tuple[str, int, str]]:
        """
        Regla 8: login todos los días durante 7 días consecutivos (calendario servidor)
        → +3. Repetible: una vez por ventana de 7 días (motivo regla8_racha_7dias_{dia_fin}).
        """
        codigo_aliado = (codigo_aliado or '').strip()
        if not codigo_aliado:
            return None
        if not self._es_invitador_elegible_score(codigo_aliado):
            return None
        dia_fin_val = (dia_fin or '').strip() or self._dia_hoy_servidor()
        try:
            fin = datetime.strptime(dia_fin_val, '%Y-%m-%d')
        except ValueError:
            return None
        dias_requeridos = [
            (fin - timedelta(days=i)).strftime('%Y-%m-%d')
            for i in range(self.REGLA8_DIAS_RACHA)
        ]
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                placeholders = ','.join('?' * len(dias_requeridos))
                cursor.execute(
                    f"""
                    SELECT dia FROM aliado_accesos_dia
                    WHERE codigo_aliado = ? AND dia IN ({placeholders})
                    """,
                    (codigo_aliado, *dias_requeridos),
                )
                presentes = {str(r[0]) for r in cursor.fetchall()}
            except Exception:
                return None
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
        if set(dias_requeridos) != presentes:
            return None
        motivo = self._motivo_regla8(dia_fin_val)
        if self._ya_aplicado_motivo_score(codigo_aliado, motivo):
            return None
        if self._tiene_premio_regla8_reciente(codigo_aliado, dia_fin_val):
            return None
        return (codigo_aliado, self.REGLA8_DELTA, motivo)

    def evaluar_regla6_urgente_mismo_dia(
        self,
        contacto_id: int,
        fecha_pago: Optional[Any] = None,
    ) -> Optional[Tuple[str, int, str]]:
        """
        Regla 6: contacto urgente pagado el mismo día → +3 al profesional.
        """
        try:
            contacto_id = int(contacto_id)
        except (TypeError, ValueError):
            return None
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, profesional_codigo, COALESCE(es_urgente, 0) AS es_urgente,
                           urgente_marcado_en, creado_en, fecha_validacion_pago, estado_pago
                    FROM contactos_ruana WHERE id = ?
                """, (contacto_id,))
                row = cursor.fetchone()
                if not row:
                    return None
                d = dict(row)
            except Exception:
                return None
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
        if not bool(int(d.get('es_urgente') or 0)):
            return None
        prof = str(d.get('profesional_codigo') or '').strip()
        if not prof:
            return None
        inicio = d.get('urgente_marcado_en') or d.get('creado_en')
        pago = fecha_pago if fecha_pago is not None else d.get('fecha_validacion_pago')
        if pago is None:
            pago = datetime.now()
        dia_inicio = self._fecha_dia_servidor(inicio)
        dia_pago = self._fecha_dia_servidor(pago)
        if not dia_inicio or not dia_pago or dia_inicio != dia_pago:
            return None
        motivo = f'regla6_urgente_mismo_dia_{contacto_id}'
        if self._ya_aplicado_motivo_score(prof, motivo):
            return None
        return (prof, self.REGLA6_DELTA, motivo)

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
        return f'regla4_4_encargos_mes_limpio_{anio_mes}'

    def _ya_aplicada_regla4_mes(self, codigo_aliado: str, anio_mes: str) -> bool:
        codigo_aliado = (codigo_aliado or '').strip()
        anio_mes = (anio_mes or '').strip()
        if not codigo_aliado or not anio_mes:
            return True
        motivo = self._motivo_regla4_mes(anio_mes)
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT 1 FROM score_movimientos WHERE codigo_aliado = ? AND motivo = ? LIMIT 1",
                    (codigo_aliado, motivo),
                )
                return cursor.fetchone() is not None
            except Exception:
                return True
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

    def contacto_tiene_incidencia_pago(self, contacto_id: int) -> bool:
        """
        True si el contacto tuvo disputa/reclamación o rechazo de comprobante Apoyo,
        aunque luego se resolviera y quedara pagado.
        """
        try:
            contacto_id = int(contacto_id)
        except (TypeError, ValueError):
            return False
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, fecha_disputa FROM contactos_ruana WHERE id = ?",
                    (contacto_id,),
                )
                row = cursor.fetchone()
                if not row:
                    return False
                if row['fecha_disputa'] is not None:
                    return True
                try:
                    cursor.execute(
                        "SELECT 1 FROM payment_conflicts WHERE trabajo_id = ? LIMIT 1",
                        (contacto_id,),
                    )
                    if cursor.fetchone() is not None:
                        return True
                except Exception:
                    pass
                cursor.execute(
                    """
                    SELECT 1 FROM audit_log
                    WHERE entidad = 'contacto' AND entidad_id = ?
                      AND accion IN ('pago_apoyo_rechazado', 'conflicto_importe', 'apoyo_impugnado')
                    LIMIT 1
                    """,
                    (contacto_id,),
                )
                return cursor.fetchone() is not None
            except Exception:
                return False
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

    def listar_encargos_pagados_mes(self, codigo_aliado: str, anio_mes: str) -> List[Dict[str, Any]]:
        """
        Contactos Pagos Apoyo RUANA del aliado (solicitante o profesional)
        con estado_pago=pagado en el mes YYYY-MM (fecha_validacion_pago).
        """
        codigo_aliado = (codigo_aliado or '').strip()
        anio_mes = (anio_mes or '').strip()
        if not codigo_aliado or not anio_mes:
            return []
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT id, solicitante_codigo, profesional_codigo, estado_pago,
                           fecha_validacion_pago, fecha_disputa
                    FROM contactos_ruana
                    WHERE estado = 'trabajo_cerrado'
                      AND estado_pago = 'pagado'
                      AND COALESCE(apoyo_ruana, 0) > 0
                      AND (solicitante_codigo = ? OR profesional_codigo = ?)
                      AND fecha_validacion_pago IS NOT NULL
                    ORDER BY id ASC
                    """,
                    (codigo_aliado, codigo_aliado),
                )
                out = []
                for row in cursor.fetchall():
                    item = dict(row)
                    if self._anio_mes_de(item.get('fecha_validacion_pago')) == anio_mes:
                        out.append(item)
                return out
            except Exception:
                return []
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

    def evaluar_regla4_encargos_mes_limpio(
        self,
        codigo_aliado: str,
        anio_mes: Optional[str] = None,
    ) -> Optional[Tuple[str, int, str]]:
        """
        Regla 4: 4 encargos pagados en el mismo mes sin incidencias de pago → +3 una vez.
        Devuelve (codigo, delta, motivo) si debe aplicarse; None si no.
        """
        codigo_aliado = (codigo_aliado or '').strip()
        if not codigo_aliado:
            return None
        anio_mes = (anio_mes or datetime.now().strftime('%Y-%m')).strip()
        if self._ya_aplicada_regla4_mes(codigo_aliado, anio_mes):
            return None
        pagados = self.listar_encargos_pagados_mes(codigo_aliado, anio_mes)
        if len(pagados) < self.REGLA4_ENCARGOS_MES_UMBRAL:
            return None
        for item in pagados:
            if self.contacto_tiene_incidencia_pago(item['id']):
                return None
        return (
            codigo_aliado,
            self.REGLA4_ENCARGOS_MES_DELTA,
            self._motivo_regla4_mes(anio_mes),
        )

    def actualizar_estado_pago_contacto(self, contacto_id: int, nuevo_estado: str,
                                        admin_codigo: str = "",
                                        motivo_rechazo: Optional[str] = None) -> Dict[str, Any]:
        """
        Admin actualiza estado_pago de un contacto (trabajo_cerrado con Apoyo RUANA).
        Estados permitidos: en_revision, pagado, rechazado.
        - pagado: pendiente_pago = 0, fecha_validacion_pago y admin_validacion_codigo;
          Regla 2: +2 score al solicitante y al profesional (encargo completado);
          Regla 3: +1 a ancestros 1ª/2ª generación de cada participante (linaje referidos);
          Regla 4: +3 si el aliado completa 4 encargos pagados limpios en el mismo mes;
          Regla 6: +3 al profesional si el contacto era urgente y se paga el mismo día.
        - rechazado: estado_pago → pendiente_pago, pendiente_pago = 1, motivo_rechazo_pago, comprobante_ruta=NULL;
          motivo_rechazo obligatorio; notifica al profesional.
        """
        nuevo_estado = (nuevo_estado or "").strip().lower()
        if nuevo_estado not in self.ESTADOS_PAGO_PERMITIDOS_ADMIN:
            return {'status': 'error', 'message': f'estado_pago debe ser uno de: {", ".join(self.ESTADOS_PAGO_PERMITIDOS_ADMIN)}'}
        if nuevo_estado == 'rechazado' and not (motivo_rechazo or "").strip():
            return {'status': 'error', 'message': 'El motivo de rechazo es obligatorio'}
        # (codigo, delta, motivo)
        scores_aplicar: List[Tuple[str, int, str]] = []
        participantes_regla2: List[str] = []
        resultado = {'status': 'error', 'message': 'unknown'}
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, estado, importe_final, estado_pago, pendiente_pago,
                           solicitante_codigo, profesional_codigo
                    FROM contactos_ruana WHERE id = ?
                """, (contacto_id,))
                row = cursor.fetchone()
                if not row:
                    return {'status': 'error', 'message': 'Contacto no encontrado'}
                r = dict(row)
                if r['estado'] != 'trabajo_cerrado' or r['importe_final'] is None:
                    return {'status': 'error', 'message': 'El contacto no tiene Apoyo RUANA generado'}
                estado_anterior = (r.get('estado_pago') or '').strip().lower()
                if nuevo_estado == 'pagado':
                    cursor.execute("""
                        UPDATE contactos_ruana
                        SET estado_pago = 'pagado', pendiente_pago = 0,
                            fecha_validacion_pago = CURRENT_TIMESTAMP,
                            admin_validacion_codigo = ?,
                            actualizado_en = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """, (admin_codigo or None, contacto_id))
                    self._audit_log(cursor, 'contacto', contacto_id, 'pago_apoyo_confirmado',
                                    'admin', admin_codigo or '', f'admin={admin_codigo or ""}')
                    prof_codigo = str(r.get('profesional_codigo') or '').strip()
                    if prof_codigo:
                        self._marcar_notificaciones_contacto_leidas(
                            cursor, prof_codigo, contacto_id,
                            tipos=['apoyo_ruana', 'pago_rechazado', 'pago_aceptado']
                        )
                        mensaje = f"RUANA ha aceptado tu comprobante de pago. El Apoyo RUANA del contacto #{contacto_id} ha sido confirmado."
                        meta = json.dumps({'contacto_id': contacto_id, 'estado_pago': 'pagado'}, ensure_ascii=False)
                        cursor.execute("""
                            INSERT INTO notificaciones_aliado (aliado_codigo, tipo, titulo, mensaje, metadata, leida)
                            VALUES (?, 'pago_aceptado', 'Pago aceptado', ?, ?, 1)
                        """, (prof_codigo, mensaje, meta))
                    # Regla 2: encargo completado al confirmar Apoyo pagado (+2 a ambos)
                    if estado_anterior != 'pagado':
                        sol_codigo = str(r.get('solicitante_codigo') or '').strip()
                        if sol_codigo:
                            participantes_regla2.append(sol_codigo)
                        if prof_codigo:
                            participantes_regla2.append(prof_codigo)
                elif nuevo_estado == 'rechazado':
                    motivo = (motivo_rechazo or "").strip()[:2000]
                    cursor.execute("""
                        UPDATE contactos_ruana
                        SET estado_pago = 'pendiente_pago', pendiente_pago = 1,
                            motivo_rechazo_pago = ?, comprobante_ruta = NULL,
                            actualizado_en = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """, (motivo, contacto_id))
                    self._audit_log(cursor, 'contacto', contacto_id, 'pago_apoyo_rechazado',
                                    'admin', admin_codigo or '', f'motivo={motivo[:500]}')
                    prof_codigo = str(r.get('profesional_codigo') or '').strip()
                    if prof_codigo:
                        self._marcar_notificaciones_contacto_leidas(
                            cursor, prof_codigo, contacto_id,
                            tipos=['apoyo_ruana', 'pago_rechazado', 'pago_aceptado']
                        )
                        mensaje = f"RUANA ha rechazado el comprobante de pago del Apoyo RUANA (contacto #{contacto_id}). Motivo: {motivo}"
                        meta = json.dumps({'contacto_id': contacto_id, 'motivo': motivo}, ensure_ascii=False)
                        cursor.execute("""
                            INSERT INTO notificaciones_aliado (aliado_codigo, tipo, titulo, mensaje, metadata, leida)
                            VALUES (?, 'pago_rechazado', 'Comprobante de pago rechazado', ?, ?, 0)
                        """, (prof_codigo, mensaje, meta))
                else:
                    cursor.execute("""
                        UPDATE contactos_ruana
                        SET estado_pago = ?, pendiente_pago = ?,
                            actualizado_en = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """, (nuevo_estado, 1 if nuevo_estado != 'pagado' else 0, contacto_id))
                self._audit_log(cursor, 'contacto', contacto_id, 'estado_pago_actualizado',
                                'admin', admin_codigo, f'estado_pago={nuevo_estado}')
                conn.commit()
                resultado = {'status': 'success', 'contacto_id': contacto_id, 'estado_pago': nuevo_estado}
            except Exception as e:
                return {'status': 'error', 'message': str(e)}
            finally:
                conn.close()
        excluir_participantes = set(participantes_regla2)
        anio_mes_actual = datetime.now().strftime('%Y-%m')
        for codigo in participantes_regla2:
            scores_aplicar.append((codigo, 2, 'encargo_completado_apoyo_pagado'))
            # Regla 3: +1 a padre (gen1) y abuelo (gen2) del participante
            for ancestro, generacion in self.ancestros_referidos_para_score(
                codigo, max_generaciones=2, excluir=excluir_participantes
            ):
                scores_aplicar.append((
                    ancestro,
                    1,
                    f'referido_encargo_completado_gen{generacion}',
                ))
            # Regla 4: 4 encargos pagados limpios en el mes → +3
            hito_regla4 = self.evaluar_regla4_encargos_mes_limpio(codigo, anio_mes_actual)
            if hito_regla4:
                scores_aplicar.append(hito_regla4)
        # Regla 6: urgente pagado el mismo día → +3 al profesional
        if participantes_regla2:
            hito_regla6 = self.evaluar_regla6_urgente_mismo_dia(contacto_id)
            if hito_regla6:
                scores_aplicar.append(hito_regla6)
        for codigo, delta, motivo in scores_aplicar:
            try:
                self.aplicar_cambio_score(codigo, delta, motivo)
            except Exception:
                pass
        return resultado
    def tiene_pagos_ruana_pendientes(self, codigo_profesional: str) -> bool:
        """True si el profesional tiene al menos un contacto con Apoyo RUANA pendiente de pago (estado_pago = pendiente_pago)."""
        if not (codigo_profesional or "").strip():
            return False
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT 1 FROM contactos_ruana
                    WHERE profesional_codigo = ? AND estado = 'trabajo_cerrado'
                      AND importe_final IS NOT NULL AND estado_pago = 'pendiente_pago'
                      AND COALESCE(apoyo_ruana, 0) > 0
                    LIMIT 1
                """, (codigo_profesional.strip(),))
                return cursor.fetchone() is not None
            except Exception:
                return False
            finally:
                conn.close()

    def impugnar_apoyo_ruana(self, contacto_id: int, profesional_codigo: str,
                             motivo: str = "") -> Dict[str, Any]:
        """El profesional impugna el importe declarado por el contratante y solicita prueba."""
        prof_norm = str(profesional_codigo or "").strip()
        if not prof_norm:
            return {'status': 'error', 'message': 'Código de profesional requerido'}
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, solicitante_codigo, profesional_codigo, estado, importe_final,
                           estado_pago, pendiente_pago
                    FROM contactos_ruana
                    WHERE id = ?
                """, (contacto_id,))
                row = cursor.fetchone()
                if not row:
                    return {'status': 'error', 'message': 'Contacto no encontrado'}
                contacto = dict(row)
                if str(contacto.get('profesional_codigo') or '').strip() != prof_norm:
                    return {'status': 'error', 'message': 'Solo el profesional del contacto puede impugnar este Apoyo RUANA'}
                if contacto.get('estado') != 'trabajo_cerrado' or contacto.get('importe_final') is None:
                    return {'status': 'error', 'message': 'Este contacto no tiene un Apoyo RUANA pendiente impugnable'}
                if (contacto.get('estado_pago') or '') != 'pendiente_pago':
                    return {'status': 'error', 'message': 'Este Apoyo RUANA no está pendiente de pago'}

                importe_final = float(contacto['importe_final'])
                solicitante_codigo = str(contacto.get('solicitante_codigo') or '').strip()
                cursor.execute("SELECT id FROM aliados WHERE codigo = ?", (solicitante_codigo,))
                r_sol = cursor.fetchone()
                cursor.execute("SELECT id FROM aliados WHERE codigo = ?", (prof_norm,))
                r_prof = cursor.fetchone()
                if not r_sol or not r_prof:
                    return {'status': 'error', 'message': 'No se pudo identificar a las partes del contacto'}

                cursor.execute("""
                    UPDATE contactos_ruana
                    SET estado = 'importe_en_disputa', pendiente_resolucion = 1,
                        estado_pago = 'no_generado', pendiente_pago = 0,
                        fecha_disputa = COALESCE(fecha_disputa, CURRENT_TIMESTAMP),
                        actualizado_en = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (contacto_id,))
                self._marcar_notificaciones_contacto_leidas(
                    cursor, prof_norm, contacto_id, tipos=['apoyo_ruana', 'pago_rechazado']
                )
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='payment_conflicts'")
                if cursor.fetchone():
                    cursor.execute("SELECT id FROM payment_conflicts WHERE trabajo_id = ?", (contacto_id,))
                    existing = cursor.fetchone()
                    if existing:
                        cursor.execute("""
                            UPDATE payment_conflicts
                            SET contratante_id = ?, profesional_id = ?, importe_contratante = ?,
                                importe_profesional = 0, estado = 'PENDIENTE_PRUEBA',
                                prueba_url = NULL, comentario_admin = ?, updated_at = CURRENT_TIMESTAMP
                            WHERE id = ?
                        """, (r_sol[0], r_prof[0], importe_final, (motivo or "").strip()[:2000] or None, existing[0]))
                    else:
                        cursor.execute("""
                            INSERT INTO payment_conflicts (trabajo_id, contratante_id, profesional_id,
                                importe_contratante, importe_profesional, estado, comentario_admin,
                                created_at, updated_at)
                            VALUES (?, ?, ?, ?, 0, 'PENDIENTE_PRUEBA', ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                        """, (contacto_id, r_sol[0], r_prof[0], importe_final, (motivo or "").strip()[:2000] or None))

                self._audit_log(cursor, 'contacto', contacto_id, 'apoyo_impugnado',
                                'aliado', prof_norm, (motivo or 'importe impugnado')[:500])
                mensaje = (
                    f"El profesional ha impugnado el importe declarado para el contacto #{contacto_id}. "
                    "Adjunta documentación o comprobantes para que RUANA pueda validarlo."
                )
                meta = json.dumps({'contacto_id': contacto_id, 'importe_declarado': importe_final}, ensure_ascii=False)
                cursor.execute("""
                    INSERT INTO notificaciones_aliado (aliado_codigo, tipo, titulo, mensaje, metadata, leida)
                    VALUES (?, 'importe_impugnado', 'Importe impugnado', ?, ?, 0)
                """, (solicitante_codigo, mensaje, meta))
                conn.commit()
                return {'status': 'success', 'contacto_id': contacto_id, 'estado': 'importe_en_disputa'}
            except Exception as e:
                return {'status': 'error', 'message': str(e)}
            finally:
                if conn:
                    conn.close()

    def listar_contactos_pago_pendiente_profesional(self, codigo_aliado: str) -> List[Dict[str, Any]]:
        """Contactos donde el aliado es profesional y tiene Apoyo RUANA pendiente de pago (estado_pago = pendiente_pago)."""
        codigo_norm = str(codigo_aliado or '').strip()
        if not codigo_norm:
            return []
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT c.id, c.servicio, c.importe_final, c.apoyo_ruana, c.estado_pago, c.pendiente_pago,
                           c.fecha_cierre, c.solicitante_codigo,
                           a_sol.nombre AS solicitante_nombre
                    FROM contactos_ruana c
                    LEFT JOIN aliados a_sol ON a_sol.codigo = c.solicitante_codigo
                    WHERE TRIM(CAST(c.profesional_codigo AS TEXT)) = ? AND c.estado = 'trabajo_cerrado'
                      AND c.importe_final IS NOT NULL AND c.estado_pago = 'pendiente_pago'
                      AND COALESCE(c.apoyo_ruana, 0) > 0
                    ORDER BY c.fecha_cierre IS NULL, c.fecha_cierre DESC, c.id DESC
                """, (codigo_norm,))
                lista = [dict(row) for row in cursor.fetchall()]
                for d in lista:
                    if d.get('importe_final') is not None and d.get('apoyo_ruana') is None:
                        try:
                            d['apoyo_ruana'] = round(float(d['importe_final']) * self._get_apoyo_pct() / 100.0, 2)
                        except (TypeError, ValueError):
                            pass
                return lista
            except Exception as e:
                print(f"Error listar_contactos_pago_pendiente_profesional: {e}")
                return []
            finally:
                conn.close()

    def subir_comprobante_apoyo_ruana(self, contacto_id: int, profesional_codigo: str,
                                       comprobante_ruta: str, comentario: Optional[str] = None) -> Dict[str, Any]:
        """
        El profesional sube comprobante de pago del Apoyo RUANA.
        Requiere: contacto con estado_pago = pendiente_pago y profesional_codigo = profesional_codigo.
        Actualiza: comprobante_ruta, estado_pago = 'en_revision', pendiente_pago = 1 (sin cambio).
        Notifica al administrador vía eventos_sistema.
        """
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, profesional_codigo, estado_pago, apoyo_ruana
                    FROM contactos_ruana
                    WHERE id = ? AND estado = 'trabajo_cerrado' AND importe_final IS NOT NULL
                """, (contacto_id,))
                row = cursor.fetchone()
                if not row:
                    return {'status': 'error', 'message': 'Contacto no encontrado'}
                r = dict(row)
                if (r['profesional_codigo'] or '').strip() != (profesional_codigo or '').strip():
                    return {'status': 'error', 'message': 'Solo el profesional del contacto puede subir el comprobante'}
                if (r['estado_pago'] or '') != 'pendiente_pago':
                    return {'status': 'error', 'message': 'Este contacto no tiene el pago en estado pendiente'}
                cursor.execute("""
                    UPDATE contactos_ruana
                    SET comprobante_ruta = ?, estado_pago = 'en_revision', actualizado_en = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (comprobante_ruta, contacto_id))
                self._marcar_notificaciones_contacto_leidas(
                    cursor, profesional_codigo, contacto_id,
                    tipos=['apoyo_ruana', 'pago_rechazado']
                )
                self._audit_log(cursor, 'contacto', contacto_id, 'comprobante_apoyo_subido',
                                'aliado', profesional_codigo, f'ruta={comprobante_ruta}')
                self._insert_evento_sistema(
                    cursor, 'comprobante_apoyo_subido',
                    f'Comprobante de pago Apoyo RUANA subido por profesional (contacto {contacto_id}, {r.get("apoyo_ruana")} €)',
                    actor_tipo='aliado', actor_codigo=profesional_codigo,
                    metadata={'contacto_id': contacto_id, 'comprobante_ruta': comprobante_ruta, 'comentario': (comentario or '')[:500]}
                )
                conn.commit()
                return {'status': 'success', 'contacto_id': contacto_id, 'estado_pago': 'en_revision'}
            except Exception as e:
                return {'status': 'error', 'message': str(e)}
            finally:
                conn.close()

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
        """
        Guarda o actualiza la evaluación de un aliado
        
        Args:
            codigo_aliado: Código del aliado
            estado: Estado (verde, amarillo, rojo)
            score: Score de 0-500
            intencion: Intención (mantener, vigilar, evaluar_suplencia)
            tasa_respuesta: Métrica de respuesta (0-1)
            tasa_confirmacion: Métrica de confirmación (0-1)
            meses_sin_trabajo: Meses sin trabajo
            ciclos_consecutivos: Ciclos consecutivos en este estado
            razones: Lista de razones del estado
            severidad: normal, alerta, critico
            
        Returns:
            Dict con resultado de la operación
        """
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                
                # Verificar si ya existe evaluación
                cursor.execute(
                    "SELECT estado, score FROM evaluaciones WHERE codigo_aliado = ?",
                    (codigo_aliado,)
                )
                resultado = cursor.fetchone()
                
                razones_str = json.dumps(razones or [], ensure_ascii=False)
                
                if resultado:
                    # Actualizar - registrar cambio en histórico
                    estado_anterior, score_anterior = resultado
                    
                    if estado_anterior != estado or score_anterior != score:
                        cursor.execute("""
                            INSERT INTO evaluaciones_historico
                            (codigo_aliado, estado_anterior, estado_nuevo, score_anterior, score_nuevo)
                            VALUES (?, ?, ?, ?, ?)
                        """, (codigo_aliado, estado_anterior, estado, score_anterior, score))
                    
                    cursor.execute("""
                        UPDATE evaluaciones
                        SET estado = ?, score = ?, intencion = ?, tasa_respuesta = ?,
                            tasa_confirmacion = ?, meses_sin_trabajo = ?, ciclos_consecutivos = ?,
                            razones = ?, severidad = ?, actualizado_en = CURRENT_TIMESTAMP
                        WHERE codigo_aliado = ?
                    """, (estado, score, intencion, tasa_respuesta, tasa_confirmacion,
                          meses_sin_trabajo, ciclos_consecutivos, razones_str, severidad,
                          codigo_aliado))
                else:
                    # Crear nueva evaluación
                    cursor.execute("""
                        INSERT INTO evaluaciones
                        (codigo_aliado, estado, score, intencion, tasa_respuesta,
                         tasa_confirmacion, meses_sin_trabajo, ciclos_consecutivos, razones, severidad)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (codigo_aliado, estado, score, intencion, tasa_respuesta,
                          tasa_confirmacion, meses_sin_trabajo, ciclos_consecutivos, razones_str, severidad))
                
                conn.commit()
                
                return {
                    'status': 'success',
                    'codigo_aliado': codigo_aliado,
                    'estado': estado,
                    'score': score
                }
                
            except Exception as e:
                return {'status': 'error', 'message': str(e)}
            finally:
                conn.close()
    
    def obtener_evaluacion(self, codigo_aliado: str) -> Optional[Dict[str, Any]]:
        """Obtiene la evaluación más reciente de un aliado"""
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute(
                    "SELECT * FROM evaluaciones WHERE codigo_aliado = ?",
                    (codigo_aliado,)
                )
                
                row = cursor.fetchone()
                if not row:
                    return None
                
                # Parsear razones JSON
                resultado = dict(row)
                if resultado.get('razones'):
                    try:
                        resultado['razones'] = json.loads(resultado['razones'])
                    except:
                        resultado['razones'] = []
                
                return resultado
                
            except Exception as e:
                print(f"Error obteniendo evaluación: {e}")
                return None
            finally:
                conn.close()
    
    def listar_evaluaciones(self, estado: str = None) -> List[Dict[str, Any]]:
        """
        Lista evaluaciones, opcionalmente filtradas por estado
        
        Args:
            estado: Estado a filtrar (verde, amarillo, rojo) - opcional
            
        Returns:
            Lista de evaluaciones
        """
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                if estado:
                    cursor.execute(
                        "SELECT * FROM evaluaciones WHERE estado = ? ORDER BY actualizado_en DESC",
                        (estado,)
                    )
                else:
                    cursor.execute("SELECT * FROM evaluaciones ORDER BY actualizado_en DESC")
                
                rows = cursor.fetchall()
                
                resultado = []
                for row in rows:
                    item = dict(row)
                    if item.get('razones'):
                        try:
                            item['razones'] = json.loads(item['razones'])
                        except:
                            item['razones'] = []
                    resultado.append(item)
                
                return resultado
                
            except Exception as e:
                print(f"Error listando evaluaciones: {e}")
                return []
            finally:
                conn.close()
    
    def obtener_historico_evaluaciones(self, codigo_aliado: str) -> List[Dict[str, Any]]:
        """Obtiene el histórico de cambios de evaluación de un aliado"""
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT * FROM evaluaciones_historico
                    WHERE codigo_aliado = ?
                    ORDER BY registrado_en DESC
                    LIMIT 100
                """, (codigo_aliado,))
                
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
                
            except Exception as e:
                print(f"Error obteniendo histórico: {e}")
                return []
            finally:
                conn.close()
    
    def obtener_estadisticas_evaluaciones(self) -> Dict[str, Any]:
        """Obtiene estadísticas generales de las evaluaciones"""
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                
                # Contar por estado
                cursor.execute("SELECT estado, COUNT(*) as cantidad FROM evaluaciones GROUP BY estado")
                por_estado = {row[0]: row[1] for row in cursor.fetchall()}
                
                # Contar por severidad
                cursor.execute("SELECT severidad, COUNT(*) as cantidad FROM evaluaciones GROUP BY severidad")
                por_severidad = {row[0]: row[1] for row in cursor.fetchall()}
                
                # Score promedio
                cursor.execute("SELECT AVG(score) FROM evaluaciones")
                score_promedio = cursor.fetchone()[0] or 0.0
                
                # Total de aliados evaluados
                cursor.execute("SELECT COUNT(*) FROM evaluaciones")
                total_evaluados = cursor.fetchone()[0]
                
                return {
                    'total_evaluados': total_evaluados,
                    'por_estado': por_estado,
                    'por_severidad': por_severidad,
                    'score_promedio': round(score_promedio, 2)
                }
                
            except Exception as e:
                print(f"Error obteniendo estadísticas: {e}")
                return {}
            finally:
                conn.close()

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
        """Inserta un evento de sistema usando un cursor ya abierto. Idempotencia: no inserta si el mismo evento (tipo, descripcion, actor_codigo) ya existe en los últimos 30 segundos."""
        import time as _time
        cursor.execute(
            """
            SELECT creado_en FROM eventos_sistema
            WHERE tipo = ? AND descripcion = ?
              AND ((CAST(? AS TEXT) IS NULL AND actor_codigo IS NULL) OR (actor_codigo = ?))
            ORDER BY id DESC LIMIT 1
            """,
            (tipo, descripcion, actor_codigo, actor_codigo),
        )
        row = cursor.fetchone()
        if row:
            try:
                from datetime import datetime
                ultimo = row[0]
                if ultimo:
                    s = str(ultimo).replace("Z", "").replace("+00:00", "").strip()[:19]
                    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
                        try:
                            dt = datetime.strptime(s, fmt)
                            ts = dt.timestamp()
                            if (_time.time() - ts) < 30:
                                return
                            break
                        except ValueError:
                            continue
            except Exception:
                pass
        meta_json = json.dumps(metadata, ensure_ascii=False) if metadata is not None else None
        cursor.execute(
            """
            INSERT INTO eventos_sistema (tipo, descripcion, actor_tipo, actor_codigo, metadata)
            VALUES (?, ?, ?, ?, ?)
            """,
            (tipo, descripcion, actor_tipo, actor_codigo, meta_json),
        )

    def registrar_evento_sistema(
        self,
        tipo: str,
        descripcion: str,
        actor_tipo: Optional[str] = None,
        actor_codigo: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Registra un evento de sistema (acción relevante para trazabilidad/auditoría).
        Uso genérico cuando no estamos ya dentro de otra transacción.
        """
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                self._insert_evento_sistema(cursor, tipo, descripcion, actor_tipo, actor_codigo, metadata)
                conn.commit()
            except Exception as e:
                print(f"Error registrando evento de sistema: {e}")
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

    def obtener_eventos_recientes(self, limite: int = 10) -> List[Dict[str, Any]]:
        """Obtiene los últimos N eventos de sistema para el panel admin."""
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                try:
                    limite_int = int(limite)
                except Exception:
                    limite_int = 10
                if limite_int <= 0:
                    limite_int = 10

                cursor.execute(
                    """
                    SELECT id, tipo, descripcion, actor_tipo, actor_codigo, metadata, creado_en
                    FROM eventos_sistema
                    ORDER BY datetime(creado_en) DESC, id DESC
                    LIMIT ?
                    """,
                    (limite_int,),
                )
                rows = cursor.fetchall()
                eventos: List[Dict[str, Any]] = []
                for row in rows:
                    item = dict(row)
                    meta_raw = item.get('metadata')
                    if meta_raw:
                        try:
                            item['metadata'] = json.loads(meta_raw)
                        except Exception:
                            item['metadata'] = None
                    else:
                        item['metadata'] = None
                    eventos.append(item)
                return eventos
            except Exception as e:
                print(f"Error obteniendo eventos recientes: {e}")
                return []
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

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
        """
        Crea manualmente una competencia: retador compite por la plaza del titular en el grupo.
        """
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                oficio_s = (oficio or '').strip()
                if not oficio_s:
                    return {'status': 'error', 'message': 'Oficio obligatorio'}
                if self.competencia_activa_para_grupo_oficio(grupo_id, oficio_s):
                    return {'status': 'error', 'message': 'Ya existe una competencia activa para este grupo y oficio'}
                cursor.execute("SELECT id FROM grupos WHERE id = ? AND estado = 'activo'", (grupo_id,))
                if not cursor.fetchone():
                    return {'status': 'error', 'message': 'Grupo no encontrado o no activo'}
                for cod, label in [(aliado_original_codigo, 'titular'), (retador_codigo, 'retador')]:
                    cursor.execute("SELECT 1 FROM aliados WHERE codigo = ?", (cod,))
                    if not cursor.fetchone():
                        return {'status': 'error', 'message': f'Aliado {label} no encontrado'}
                duracion = self._get_duracion_competencia_dias()
                from datetime import timedelta
                fecha_fin = (datetime.now() + timedelta(days=duracion)).strftime('%Y-%m-%d %H:%M:%S')
                cursor.execute("""
                    INSERT INTO competencia (grupo_id, oficio, aliado_original_codigo, retador_codigo, fecha_fin_prevista, estado)
                    VALUES (?, ?, ?, ?, ?, 'activa')
                """, (grupo_id, oficio_s, aliado_original_codigo, retador_codigo, fecha_fin))
                conn.commit()
                try:
                    self.registrar_evento_sistema(
                        'forzar_competencia',
                        f'Competencia forzada: grupo {grupo_id}, oficio {oficio_s}',
                        actor_tipo='admin',
                        metadata={'grupo_id': grupo_id, 'oficio': oficio_s, 'original': aliado_original_codigo, 'retador': retador_codigo},
                    )
                except Exception:
                    pass
                return {'status': 'success', 'message': 'Competencia forzada correctamente', 'competencia_id': cursor.lastrowid}
            except Exception as e:
                return {'status': 'error', 'message': str(e)}
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

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
        """Marca la plaza (grupo + oficio) como cerrada; no se asignan nuevos aliados a esa plaza."""
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                oficio_s = (oficio or '').strip()
                if not oficio_s:
                    return {'status': 'error', 'message': 'Oficio obligatorio'}
                cursor.execute("SELECT 1 FROM grupos WHERE id = ? AND estado = 'activo'", (grupo_id,))
                if not cursor.fetchone():
                    return {'status': 'error', 'message': 'Grupo no encontrado o no activo'}
                cursor.execute(
                    "INSERT OR IGNORE INTO grupo_oficio_cerrado (grupo_id, oficio) VALUES (?, ?)",
                    (grupo_id, oficio_s),
                )
                conn.commit()
                try:
                    self.registrar_evento_sistema(
                        'cerrar_oficio',
                        f'Oficio {oficio_s} cerrado en grupo {grupo_id}',
                        actor_tipo='admin',
                        actor_codigo=admin_codigo,
                        metadata={'grupo_id': grupo_id, 'oficio': oficio_s},
                    )
                except Exception:
                    pass
                return {'status': 'success', 'message': f'Oficio {oficio_s} cerrado en el grupo'}
            except Exception as e:
                return {'status': 'error', 'message': str(e)}
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

    def abrir_plaza_grupo(self, grupo_id: int, oficio: str, admin_codigo: Optional[str] = None) -> Dict[str, Any]:
        """Reabre la plaza (quita el cierre de grupo + oficio)."""
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                oficio_s = (oficio or '').strip()
                if not oficio_s:
                    return {'status': 'error', 'message': 'Oficio obligatorio'}
                cursor.execute("DELETE FROM grupo_oficio_cerrado WHERE grupo_id = ? AND oficio = ?", (grupo_id, oficio_s))
                conn.commit()
                try:
                    self.registrar_evento_sistema(
                        'abrir_plaza',
                        f'Plaza reabierta: grupo {grupo_id}, oficio {oficio_s}',
                        actor_tipo='admin',
                        actor_codigo=admin_codigo,
                        metadata={'grupo_id': grupo_id, 'oficio': oficio_s},
                    )
                except Exception:
                    pass
                return {'status': 'success', 'message': f'Plaza abierta para oficio {oficio_s} en el grupo'}
            except Exception as e:
                return {'status': 'error', 'message': str(e)}
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

    def listar_oficios_cerrados_grupo(self, grupo_id: int) -> List[str]:
        """Lista los oficios cerrados (en grupo_oficio_cerrado) para un grupo. Para uso en admin «Reabrir plaza»."""
        if not grupo_id:
            return []
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT oficio FROM grupo_oficio_cerrado WHERE grupo_id = ? ORDER BY oficio",
                    (grupo_id,),
                )
                return [row[0].strip() for row in cursor.fetchall() if row[0]]
            except Exception:
                return []
            finally:
                conn.close()

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
        """
        Pausa manualmente un aliado (lo saca temporalmente del pool).
        Implementación: marca estado = 'suspendido_temporal' en la tabla aliados.
        """
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()

                cursor.execute(
                    "SELECT id, estado FROM aliados WHERE codigo = ?",
                    (codigo_aliado,),
                )
                row = cursor.fetchone()
                if not row:
                    return {'status': 'error', 'message': f'Aliado {codigo_aliado} no encontrado'}

                # Si ya está expulsado, no tiene sentido pausar
                estado_actual = row[1]
                if estado_actual == 'expulsado':
                    return {
                        'status': 'error',
                        'message': f'Aliado {codigo_aliado} ya está expulsado y no se puede pausar'
                    }

                cursor.execute(
                    "UPDATE aliados SET estado = 'suspendido_temporal', actualizado_en = CURRENT_TIMESTAMP WHERE codigo = ?",
                    (codigo_aliado,),
                )

                # Opcional: registrar en histórico de evaluaciones si existe alguna
                if razon:
                    try:
                        cursor.execute(
                            """
                            INSERT INTO evaluaciones_historico
                            (codigo_aliado, estado_anterior, estado_nuevo, score_anterior, score_nuevo, razon_cambio)
                            SELECT
                                a.codigo,
                                e.estado AS estado_anterior,
                                'pausado_manual' AS estado_nuevo,
                                e.score AS score_anterior,
                                e.score AS score_nuevo,
                                ?
                            FROM aliados a
                            LEFT JOIN evaluaciones e ON e.codigo_aliado = a.codigo
                            WHERE a.codigo = ?
                            """,
                            (razon, codigo_aliado),
                        )
                    except Exception:
                        # No romper por fallos en histórico
                        pass

                # Registrar evento de sistema dentro de la misma transacción
                try:
                    self._insert_evento_sistema(
                        cursor,
                        tipo="aliado_pausado",
                        descripcion=f"Aliado {codigo_aliado} pausado manualmente",
                        actor_tipo="admin",
                        actor_codigo=admin_codigo,
                        metadata={"codigo_aliado": codigo_aliado, "razon": razon},
                    )
                except Exception:
                    # No romper operación principal por fallo en log
                    pass

                conn.commit()

                return {
                    'status': 'success',
                    'codigo_aliado': codigo_aliado,
                    'nuevo_estado': 'suspendido_temporal',
                }
            except Exception as e:
                print(f"Error pausando aliado {codigo_aliado}: {e}")
                return {'status': 'error', 'message': str(e)}
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

    def eliminar_perfil_aliado_admin(
        self,
        codigo_aliado: str,
        motivo: Optional[str] = None,
        admin_codigo: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Elimina el perfil de un aliado desde el panel admin.
        - pendiente_completar: borrado físico (placeholder).
        - pendiente_validacion: pasa a rechazado.
        - resto de estados operativos: pasa a expulsado (código desactivado).
        """
        codigo = (codigo_aliado or '').strip()
        if not codigo:
            return {'status': 'error', 'message': 'Código de aliado obligatorio'}

        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, estado, nombre FROM aliados WHERE codigo = ?",
                    (codigo,),
                )
                row = cursor.fetchone()
                if not row:
                    return {'status': 'error', 'message': f'Aliado {codigo} no encontrado'}

                estado_actual = (row[1] or '').strip().lower()
                nombre = row[2] or ''

                if estado_actual == 'sistema':
                    return {'status': 'error', 'message': 'No se puede eliminar un aliado del sistema'}
                if estado_actual == 'expulsado':
                    return {'status': 'error', 'message': f'El aliado {codigo} ya está expulsado'}
                if estado_actual == 'rechazado':
                    return {'status': 'error', 'message': f'El aliado {codigo} ya está rechazado'}

                motivo_txt = (motivo or '').strip() or 'Eliminado desde panel de administración'

                if estado_actual == 'pendiente_completar':
                    cursor.execute(
                        """
                        DELETE FROM aliados
                        WHERE codigo = ?
                          AND LOWER(TRIM(COALESCE(estado, ''))) = 'pendiente_completar'
                        """,
                        (codigo,),
                    )
                    accion = 'eliminado'
                    nuevo_estado = None
                elif estado_actual == 'pendiente_validacion':
                    cursor.execute(
                        """
                        UPDATE aliados
                        SET estado = 'rechazado', actualizado_en = CURRENT_TIMESTAMP
                        WHERE codigo = ?
                        """,
                        (codigo,),
                    )
                    accion = 'rechazado'
                    nuevo_estado = 'rechazado'
                else:
                    cursor.execute(
                        """
                        UPDATE aliados
                        SET estado = 'expulsado', actualizado_en = CURRENT_TIMESTAMP
                        WHERE codigo = ?
                        """,
                        (codigo,),
                    )
                    accion = 'expulsado'
                    nuevo_estado = 'expulsado'

                if cursor.rowcount <= 0:
                    return {'status': 'error', 'message': f'No se pudo eliminar el perfil de {codigo}'}

                try:
                    self._insert_evento_sistema(
                        cursor,
                        tipo="aliado_perfil_eliminado",
                        descripcion=f"Perfil de aliado {codigo} ({nombre}) eliminado por admin",
                        actor_tipo="admin",
                        actor_codigo=admin_codigo,
                        metadata={
                            "codigo_aliado": codigo,
                            "estado_anterior": estado_actual,
                            "accion": accion,
                            "motivo": motivo_txt,
                        },
                    )
                except Exception:
                    pass

                conn.commit()
                return {
                    'status': 'success',
                    'message': f'Perfil de {codigo} eliminado correctamente',
                    'codigo_aliado': codigo,
                    'accion': accion,
                    'nuevo_estado': nuevo_estado,
                }
            except Exception as e:
                return {'status': 'error', 'message': str(e)}
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

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
        """Lista aliados con estado en_espera (Suplentes). Para panel admin."""
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, codigo, nombre, marca, oficio, codigo_postal, email, telefono,
                           estado, score, descripcion_servicio, creado_en, actualizado_en
                    FROM aliados WHERE estado = 'en_espera'
                    ORDER BY creado_en ASC
                """)
                return [dict(row) for row in cursor.fetchall()]
            except Exception as e:
                print(f"[RUANA][DB] Error listar_aliados_en_espera: {e}")
                return []
            finally:
                conn.close()

    def incorporar_aliado_espera(self, codigo: str, grupo_id: Optional[int] = None,
                                  admin_codigo: Optional[str] = None) -> Dict[str, Any]:
        """Incorpora un aliado en_espera a un grupo: estado → activo, asigna grupo."""
        codigo = (codigo or '').strip()
        if not codigo:
            return {'status': 'error', 'message': 'Código obligatorio'}
        with self._lock:
            conn = None
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, codigo, oficio, codigo_postal, estado FROM aliados WHERE codigo = ?",
                    (codigo,)
                )
                row = cursor.fetchone()
                if not row:
                    return {'status': 'error', 'message': 'Aliado no encontrado'}
                aliado = dict(row)
                if aliado['estado'] != 'en_espera':
                    return {'status': 'error', 'message': 'El aliado no está en lista de espera'}
                aliado_id = aliado['id']
                oficio = (aliado.get('oficio') or '').strip()
                codigo_postal = (aliado.get('codigo_postal') or '').strip()
                grupo_asignado = None
                if grupo_id:
                    cursor.execute("SELECT id, estado FROM grupos WHERE id = ? AND estado = 'activo'", (grupo_id,))
                    g = cursor.fetchone()
                    if not g:
                        return {'status': 'error', 'message': 'Grupo no encontrado o no activo'}
                    if oficio and self._grupo_tiene_oficio(cursor, grupo_id, oficio):
                        return {'status': 'error', 'message': f'El grupo ya tiene un aliado con oficio {oficio}'}
                    grupo_asignado = grupo_id
                elif oficio and codigo_postal:
                    g = self.buscar_grupo_sin_oficio(codigo_postal, oficio)
                    if g:
                        grupo_asignado = g['id']
                    elif self.contar_grupos_activos_por_cp(codigo_postal) < MAX_GRUPOS_POR_CP:
                        nuevo = self.crear_grupo_en_cp(codigo_postal)
                        if isinstance(nuevo, dict) and nuevo.get('id'):
                            grupo_asignado = nuevo['id']
                if grupo_asignado is None:
                    return {'status': 'error', 'message': 'No hay plaza disponible. Especifica grupo_id o espera a que se libere una plaza.'}
                cursor.execute(
                    "UPDATE aliados SET estado = 'activo', grupo_id = ?, actualizado_en = CURRENT_TIMESTAMP WHERE id = ?",
                    (grupo_asignado, aliado_id)
                )
                conn.commit()
                try:
                    self.registrar_evento_sistema(
                        'incorporar_espera',
                        f'Aliado {codigo} incorporado desde lista de espera al grupo {grupo_asignado}',
                        actor_tipo='admin',
                        actor_codigo=admin_codigo,
                        metadata={'codigo': codigo, 'grupo_id': grupo_asignado},
                    )
                except Exception:
                    pass
                try:
                    aliado_row = self.obtener_aliado_por_codigo(codigo)
                    if aliado_row:
                        cp = (aliado_row.get('codigo_postal') or '').strip()
                        of = (aliado_row.get('oficio') or '').strip()
                        if cp and of:
                            self._procesar_competencias_pendientes(cp, of)
                except Exception:
                    pass
                return {'status': 'success', 'message': 'Aliado incorporado correctamente', 'grupo_id': grupo_asignado}
            except Exception as e:
                return {'status': 'error', 'message': str(e)}
            finally:
                if conn:
                    conn.close()

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
        """Cuenta solicitudes en estado pendiente (activas)."""
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT COUNT(*) FROM solicitudes WHERE estado = 'pendiente'"
                )
                return cursor.fetchone()[0] or 0
            except Exception:
                return 0
            finally:
                conn.close()

    def contar_solicitudes_enviadas_contestadas(self, codigo: str) -> int:
        """Cuenta solicitudes enviadas por el aliado (solicitante) que fueron atendidas/contestadas."""
        if not codigo or not str(codigo).strip():
            return 0
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute("PRAGMA table_info(solicitudes)")
                cols = [r[1] for r in cursor.fetchall()]
                if 'solicitante_codigo' not in cols:
                    return 0
                estado_atendida = "atendida" if 'atendido_por_codigo' in cols else "contestada"
                cursor.execute(
                    "SELECT COUNT(*) FROM solicitudes WHERE solicitante_codigo = ? AND estado = ?",
                    (codigo.strip(), estado_atendida),
                )
                return cursor.fetchone()[0] or 0
            except Exception:
                return 0
            finally:
                conn.close()

    def contar_grupos(self) -> Dict[str, int]:
        """
        Cuenta grupos territoriales: total (todos), activos, en_competencia, disueltos.
        Dinámico según se creen o disuelvan.
        """
        conn = None
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM grupos")
                total = cursor.fetchone()[0] or 0
                cursor.execute("SELECT COUNT(*) FROM grupos WHERE estado = 'activo'")
                activos = cursor.fetchone()[0] or 0
                cursor.execute("SELECT COUNT(*) FROM grupos WHERE estado = 'en_competencia'")
                en_competencia = cursor.fetchone()[0] or 0
                cursor.execute("SELECT COUNT(*) FROM grupos WHERE estado = 'disuelto'")
                disueltos = cursor.fetchone()[0] or 0
                return {
                    'total': total,
                    'activos': activos,
                    'en_competencia': en_competencia,
                    'disueltos': disueltos,
                }
            except Exception:
                return {'total': 0, 'activos': 0, 'en_competencia': 0, 'disueltos': 0}
            finally:
                try:
                    if conn is not None:
                        conn.close()
                except Exception:
                    pass

    def contar_oficios_ocupados(self) -> int:
        """Cuenta oficios distintos cubiertos por aliados activos (oficio principal)."""
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT COUNT(DISTINCT oficio) FROM aliados
                    WHERE estado = 'activo' AND oficio IS NOT NULL AND TRIM(oficio) != ''
                """)
                return cursor.fetchone()[0] or 0
            except Exception:
                return 0
            finally:
                conn.close()

    def obtener_stats_24h_admin(self) -> Dict[str, Any]:
        """
        Stats 24h para GET /api/admin/stats-24h.
        Sin datos simulados. Calcula:
        - solicitudes_nuevas: creadas en últimas 24h
        - solicitudes_atendidas: contestadas creadas en 24h
        - solicitudes_sin_respuesta: pendientes creadas en 24h (sin atender aún)
        - invitaciones_generadas: creadas en 24h (invitaciones + invitaciones_oficio)
        - invitaciones_usadas: usadas en 24h (referidos + invitaciones_oficio usadas)
        - invitaciones_expiradas: no usadas y creadas hace >30 días (umbral por defecto)
        """
        conn = None
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                col_ts_sol = "created_at"
                try:
                    cursor.execute("PRAGMA table_info(solicitudes)")
                    if not any(r[1] == 'created_at' for r in cursor.fetchall()):
                        col_ts_sol = "creado_en"
                except Exception:
                    pass
                filtro_24h_sol = f"datetime({col_ts_sol}) >= datetime('now', '-1 day')"
                estado_atendida = "atendida"
                try:
                    cursor.execute("PRAGMA table_info(solicitudes)")
                    if not any(r[1] == 'atendido_por_codigo' for r in cursor.fetchall()):
                        estado_atendida = "contestada"
                except Exception:
                    pass

                cursor.execute(f"SELECT COUNT(*) FROM solicitudes WHERE {filtro_24h_sol}")
                solicitudes_nuevas = cursor.fetchone()[0] or 0
                cursor.execute(f"SELECT COUNT(*) FROM solicitudes WHERE estado = ? AND {filtro_24h_sol}", (estado_atendida,))
                solicitudes_atendidas = cursor.fetchone()[0] or 0
                cursor.execute(f"SELECT COUNT(*) FROM solicitudes WHERE estado = 'pendiente' AND {filtro_24h_sol}")
                solicitudes_sin_respuesta = cursor.fetchone()[0] or 0

                # Invitaciones generadas 24h: invitaciones (aliado) + invitaciones_oficio
                filtro_24h = "datetime(creado_en) >= datetime('now', '-1 day')"
                cursor.execute(f"""
                    SELECT COUNT(*) FROM invitaciones
                    WHERE {filtro_24h}
                """)
                inv_aliado_gen = cursor.fetchone()[0] or 0
                cursor.execute("""
                    SELECT COUNT(*) FROM invitaciones_oficio
                    WHERE datetime(fecha_creacion) >= datetime('now', '-1 day')
                """)
                inv_oficio_gen = cursor.fetchone()[0] or 0
                invitaciones_generadas = inv_aliado_gen + inv_oficio_gen

                # Invitaciones usadas 24h: referidos.creado_en + invitaciones_oficio marcadas usado en 24h
                cursor.execute("""
                    SELECT COUNT(*) FROM referidos
                    WHERE datetime(creado_en) >= datetime('now', '-1 day')
                """)
                invitaciones_usadas = cursor.fetchone()[0] or 0
                # invitaciones_oficio no tiene timestamp de uso; contar por alias: no hay tabla de uso
                # Solo referidos refleja invitación aliado usada. invitaciones_oficio: al consumir se cambia estado
                # sin timestamp. Por simplicidad, invitaciones_usadas = referidos en 24h.
                # invitaciones_oficio usadas: no hay created_at del uso. Omitir por ahora.

                # Invitaciones expiradas: no usadas, creadas hace >30 días (regla de negocio)
                cursor.execute("""
                    SELECT COUNT(*) FROM invitaciones
                    WHERE usado = 0 AND datetime(creado_en) < datetime('now', '-30 day')
                """)
                exp_aliado = cursor.fetchone()[0] or 0
                cursor.execute("""
                    SELECT COUNT(*) FROM invitaciones_oficio
                    WHERE estado = 'pendiente' AND datetime(fecha_creacion) < datetime('now', '-30 day')
                """)
                exp_oficio = cursor.fetchone()[0] or 0
                invitaciones_expiradas = exp_aliado + exp_oficio

                return {
                    'solicitudes_nuevas': solicitudes_nuevas,
                    'solicitudes_atendidas': solicitudes_atendidas,
                    'solicitudes_sin_respuesta': solicitudes_sin_respuesta,
                    'invitaciones_generadas': invitaciones_generadas,
                    'invitaciones_usadas': invitaciones_usadas,
                    'invitaciones_expiradas': invitaciones_expiradas,
                }
            except Exception as e:
                print(f"Error obtener_stats_24h_admin: {e}")
                return {
                    'solicitudes_nuevas': 0,
                    'solicitudes_atendidas': 0,
                    'solicitudes_sin_respuesta': 0,
                    'invitaciones_generadas': 0,
                    'invitaciones_usadas': 0,
                    'invitaciones_expiradas': 0,
                }
            finally:
                try:
                    if conn is not None:
                        conn.close()
                except Exception:
                    pass

    def obtener_stats_24h_panel(self) -> Dict[str, Any]:
        """
        Métricas 24h en formato para el panel admin (endpoint único GET /api/admin/stats-24h).
        limite = now - 24 hours. Devuelve: solicitudes, invitaciones, top_invitadores.
        """
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                limite = "datetime('now', '-1 day')"

                # Solicitudes: nuevas, atendidas, sin_respuesta (compatible con tabla unificada)
                try:
                    cursor.execute("PRAGMA table_info(solicitudes)")
                    info_sol = cursor.fetchall()
                    col_ts_s = "created_at" if any(r[1] == 'created_at' for r in info_sol) else "creado_en"
                    estado_at = "atendida" if any(r[1] == 'atendido_por_codigo' for r in info_sol) else "contestada"
                except Exception:
                    col_ts_s, estado_at = "creado_en", "contestada"
                cursor.execute(f"SELECT COUNT(*) FROM solicitudes WHERE datetime({col_ts_s}) >= {limite}")
                nuevas = cursor.fetchone()[0] or 0
                cursor.execute(f"SELECT COUNT(*) FROM solicitudes WHERE estado = ? AND datetime({col_ts_s}) >= {limite}", (estado_at,))
                atendidas = cursor.fetchone()[0] or 0
                cursor.execute(f"SELECT COUNT(*) FROM solicitudes WHERE estado = 'pendiente' AND datetime({col_ts_s}) >= {limite}")
                sin_respuesta = cursor.fetchone()[0] or 0

                # Invitaciones: generadas (invitaciones + invitaciones_oficio), usadas (referidos 24h), expiradas
                cursor.execute(f"""
                    SELECT COUNT(*) FROM invitaciones
                    WHERE datetime(creado_en) >= {limite}
                """)
                inv_gen = cursor.fetchone()[0] or 0
                cursor.execute("""
                    SELECT COUNT(*) FROM invitaciones_oficio
                    WHERE datetime(fecha_creacion) >= datetime('now', '-1 day')
                """)
                inv_oficio = cursor.fetchone()[0] or 0
                generadas = inv_gen + inv_oficio

                cursor.execute(f"""
                    SELECT COUNT(*) FROM referidos
                    WHERE datetime(creado_en) >= {limite}
                """)
                usadas = cursor.fetchone()[0] or 0

                cursor.execute("""
                    SELECT COUNT(*) FROM invitaciones
                    WHERE usado = 0 AND datetime(creado_en) < datetime('now', '-30 day')
                """)
                exp_a = cursor.fetchone()[0] or 0
                cursor.execute("""
                    SELECT COUNT(*) FROM invitaciones_oficio
                    WHERE estado = 'pendiente' AND datetime(fecha_creacion) < datetime('now', '-30 day')
                """)
                exp_o = cursor.fetchone()[0] or 0
                expiradas = exp_a + exp_o

                # Top invitadores 24h: por referidos en 24h, agrupar por codigo_invitador
                cursor.execute(f"""
                    SELECT r.codigo_invitador, COUNT(*) AS total
                    FROM referidos r
                    WHERE datetime(r.creado_en) >= {limite}
                    GROUP BY r.codigo_invitador
                    ORDER BY total DESC
                    LIMIT 3
                """)
                rows = cursor.fetchall()
                top_invitadores = []
                for (codigo_inv, total) in rows:
                    cursor.execute("SELECT nombre FROM aliados WHERE codigo = ?", (codigo_inv or '',))
                    rn = cursor.fetchone()
                    nombre = (rn[0] or codigo_inv or '—') if rn else (codigo_inv or '—')
                    top_invitadores.append({'nombre': nombre, 'total': total})

                return {
                    'solicitudes': {'nuevas': nuevas, 'atendidas': atendidas, 'sin_respuesta': sin_respuesta},
                    'invitaciones': {'generadas': generadas, 'usadas': usadas, 'expiradas': expiradas},
                    'top_invitadores': top_invitadores,
                }
            except Exception as e:
                print(f"Error obtener_stats_24h_panel: {e}")
                return {
                    'solicitudes': {'nuevas': 0, 'atendidas': 0, 'sin_respuesta': 0},
                    'invitaciones': {'generadas': 0, 'usadas': 0, 'expiradas': 0},
                    'top_invitadores': [],
                }
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

    def obtener_movimiento_24h(self) -> Dict[str, Any]:
        """
        Movimiento del sistema en las últimas 24 horas: contactos recientes, invitaciones, solicitudes.
        Para el panel admin (GET /api/movimiento-24h).
        """
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                # Ventana 24h (solicitudes: compatible tabla unificada)
                try:
                    cursor.execute("PRAGMA table_info(solicitudes)")
                    info_s = cursor.fetchall()
                    col_s = "created_at" if any(r[1] == 'created_at' for r in info_s) else "creado_en"
                    est_s = "atendida" if any(r[1] == 'atendido_por_codigo' for r in info_s) else "contestada"
                except Exception:
                    col_s, est_s = "creado_en", "contestada"
                cursor.execute(f"SELECT COUNT(*) FROM solicitudes WHERE datetime({col_s}) >= datetime('now', '-1 day')")
                solicitudes_nuevas = cursor.fetchone()[0] or 0
                cursor.execute(f"SELECT COUNT(*) FROM solicitudes WHERE estado = ? AND datetime({col_s}) >= datetime('now', '-1 day')", (est_s,))
                solicitudes_atendidas = cursor.fetchone()[0] or 0
                cursor.execute("SELECT COUNT(*) FROM solicitudes WHERE estado = 'pendiente'")
                solicitudes_sin_respuesta = cursor.fetchone()[0] or 0

                # Invitaciones: generadas y usadas en 24h (invitaciones.creado_en, referidos.creado_en)
                cursor.execute("""
                    SELECT COUNT(*) FROM invitaciones
                    WHERE datetime(creado_en) >= datetime('now', '-1 day')
                """)
                invitaciones_generadas = cursor.fetchone()[0] or 0

                cursor.execute("""
                    SELECT COUNT(*) FROM referidos
                    WHERE datetime(creado_en) >= datetime('now', '-1 day')
                """)
                invitaciones_usadas = cursor.fetchone()[0] or 0

                # Contactos RUANA recientes
                cursor.execute("""
                    SELECT COUNT(*) FROM contactos_ruana
                    WHERE datetime(creado_en) >= datetime('now', '-1 day')
                """)
                contactos_nuevos = cursor.fetchone()[0] or 0

                cursor.execute("""
                    SELECT COUNT(*) FROM contactos_ruana
                    WHERE fecha_aceptacion IS NOT NULL AND datetime(fecha_aceptacion) >= datetime('now', '-1 day')
                """)
                contactos_aceptados = cursor.fetchone()[0] or 0

                cursor.execute("""
                    SELECT COUNT(*) FROM contactos_ruana
                    WHERE (fecha_cierre IS NOT NULL OR fecha_no_concretado IS NOT NULL)
                    AND (datetime(fecha_cierre) >= datetime('now', '-1 day') OR datetime(fecha_no_concretado) >= datetime('now', '-1 day'))
                """)
                contactos_cerrados = cursor.fetchone()[0] or 0

                # Top invitadores (últimas 24h): por referidos.creado_en
                cursor.execute("""
                    SELECT r.codigo_invitador, COUNT(*) as total
                    FROM referidos r
                    WHERE datetime(r.creado_en) >= datetime('now', '-1 day')
                    GROUP BY r.codigo_invitador
                    ORDER BY total DESC
                    LIMIT 5
                """)
                rows = cursor.fetchall()
                top_invitadores = []
                for codigo_inv, total in rows:
                    cursor.execute("SELECT nombre FROM aliados WHERE codigo = ?", (codigo_inv,))
                    rn = cursor.fetchone()
                    nombre = (rn[0] or codigo_inv) if rn else codigo_inv
                    top_invitadores.append({'nombre': nombre, 'total': total})

                return {
                    'solicitudes': {
                        'nuevas': solicitudes_nuevas,
                        'atendidas': solicitudes_atendidas,
                        'sin_respuesta': solicitudes_sin_respuesta,
                    },
                    'invitaciones': {
                        'generadas': invitaciones_generadas,
                        'usadas': invitaciones_usadas,
                        'expiradas': 0,
                    },
                    'contactos': {
                        'nuevos': contactos_nuevos,
                        'aceptados': contactos_aceptados,
                        'cerrados': contactos_cerrados,
                    },
                    'top_invitadores': top_invitadores,
                }
            except Exception as e:
                print(f"Error obtener_movimiento_24h: {e}")
                return {
                    'solicitudes': {'nuevas': 0, 'atendidas': 0, 'sin_respuesta': 0},
                    'invitaciones': {'generadas': 0, 'usadas': 0, 'expiradas': 0},
                    'contactos': {'nuevos': 0, 'aceptados': 0, 'cerrados': 0},
                    'top_invitadores': [],
                }
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

    def obtener_movimiento_24h_por_hora(self) -> Dict[str, Dict[str, int]]:
        """
        Movimiento del sistema en las últimas 24 horas, agrupado por hora (00-23).
        Cada clave es "00".."23" con: nuevas, atendidas, sin_respuesta, invitaciones_generadas,
        invitaciones_usadas, invitaciones_expiradas. Siempre devuelve 24 entradas (0 si no hay datos).
        """
        horas = [f"{h:02d}" for h in range(24)]
        vacio = {
            'nuevas': 0,
            'atendidas': 0,
            'sin_respuesta': 0,
            'invitaciones_generadas': 0,
            'invitaciones_usadas': 0,
            'invitaciones_expiradas': 0,
            'contactos_creados': 0,
        }
        resultado = {h: dict(vacio) for h in horas}

        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                try:
                    cursor.execute("PRAGMA table_info(solicitudes)")
                    info_s2 = cursor.fetchall()
                    col_sol = "created_at" if any(r[1] == 'created_at' for r in info_s2) else "creado_en"
                    est_sol = "atendida" if any(r[1] == 'atendido_por_codigo' for r in info_s2) else "contestada"
                except Exception:
                    col_sol, est_sol = "creado_en", "contestada"
                filtro_24h_sol = f"datetime({col_sol}) >= datetime('now', '-1 day')"
                filtro_24h = "datetime(creado_en) >= datetime('now', '-1 day')"

                cursor.execute(f"SELECT strftime('%H', {col_sol}) AS hora, COUNT(*) AS total FROM solicitudes WHERE {filtro_24h_sol} GROUP BY strftime('%H', {col_sol})")
                for row in cursor.fetchall():
                    h = row[0] if row[0] and len(row[0]) == 2 else (f"0{row[0]}" if row[0] and len(row[0]) == 1 else row[0])
                    if h in resultado:
                        resultado[h]['nuevas'] = row[1]
                cursor.execute(f"SELECT strftime('%H', {col_sol}) AS hora, COUNT(*) AS total FROM solicitudes WHERE estado = ? AND {filtro_24h_sol} GROUP BY strftime('%H', {col_sol})", (est_sol,))
                for row in cursor.fetchall():
                    h = row[0] if row[0] and len(row[0]) == 2 else (f"0{row[0]}" if row[0] and len(row[0]) == 1 else row[0])
                    if h in resultado:
                        resultado[h]['atendidas'] = row[1]
                cursor.execute(f"SELECT strftime('%H', {col_sol}) AS hora, COUNT(*) AS total FROM solicitudes WHERE estado = 'pendiente' AND {filtro_24h_sol} GROUP BY strftime('%H', {col_sol})")
                for row in cursor.fetchall():
                    h = row[0] if len(row[0]) == 2 else f"0{row[0]}" if row[0] and len(row[0]) == 1 else row[0]
                    if h in resultado:
                        resultado[h]['sin_respuesta'] = row[1]

                # Invitaciones generadas por hora
                cursor.execute(f"""
                    SELECT strftime('%H', creado_en) AS hora, COUNT(*) AS total
                    FROM invitaciones
                    WHERE {filtro_24h}
                    GROUP BY strftime('%H', creado_en)
                """)
                for row in cursor.fetchall():
                    h = row[0] if len(row[0]) == 2 else f"0{row[0]}" if row[0] and len(row[0]) == 1 else row[0]
                    if h in resultado:
                        resultado[h]['invitaciones_generadas'] = row[1]

                # Invitaciones usadas (referidos) por hora
                cursor.execute(f"""
                    SELECT strftime('%H', creado_en) AS hora, COUNT(*) AS total
                    FROM referidos
                    WHERE {filtro_24h}
                    GROUP BY strftime('%H', creado_en)
                """)
                for row in cursor.fetchall():
                    h = row[0] if len(row[0]) == 2 else f"0{row[0]}" if row[0] and len(row[0]) == 1 else row[0]
                    if h in resultado:
                        resultado[h]['invitaciones_usadas'] = row[1]

                # Contactos creados por hora
                cursor.execute(f"""
                    SELECT strftime('%H', creado_en) AS hora, COUNT(*) AS total
                    FROM contactos_ruana
                    WHERE {filtro_24h}
                    GROUP BY strftime('%H', creado_en)
                """)
                for row in cursor.fetchall():
                    h = row[0] if len(row[0]) == 2 else f"0{row[0]}" if row[0] and len(row[0]) == 1 else row[0]
                    if h in resultado:
                        resultado[h]['contactos_creados'] = row[1]

                return resultado
            except Exception as e:
                print(f"Error obtener_movimiento_24h_por_hora: {e}")
                return resultado
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

    def obtener_metricas_salud(self) -> Dict[str, Any]:
        """
        Cruce aliados, contactos, evaluaciones, invitaciones para métricas de salud del panel admin.
        Devuelve, usando datos reales de la BD:
        - Ratio Solicitud → Invitación  = solicitudes que generaron invitación / total solicitudes
        - Ratio Invitación → Registro   = invitaciones usadas (usado=1) / total invitaciones
        - Oficios Saturados            = nº oficios cuyo nº de aliados activos supera umbral (p.ej. ≥3)
        - Oficios Disponibles          = total oficios catálogo − oficios saturados
        - Zona Mayor Demanda           = código postal con más solicitudes pendientes
        - Tasa Retención Aliados       = aliados con ≥1 trabajo completado / total aliados (en %)
        """
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()

                # Totales básicos
                total_aliados = cursor.execute("SELECT COUNT(*) FROM aliados").fetchone()[0] or 0
                total_solicitudes = cursor.execute("SELECT COUNT(*) FROM solicitudes").fetchone()[0] or 0
                total_invitaciones = cursor.execute("SELECT COUNT(*) FROM invitaciones").fetchone()[0] or 0
                cursor.execute("SELECT COUNT(*) FROM invitaciones WHERE usado = 1")
                invitaciones_usadas = cursor.fetchone()[0] or 0

                # Solicitudes que "generaron" invitación:
                # aproximación: solicitudes cuyo solicitante es un aliado que ha generado al menos una invitación.
                cursor.execute("""
                    SELECT COUNT(DISTINCT s.id)
                    FROM solicitudes s
                    JOIN aliados a ON s.solicitante_codigo = a.codigo
                    JOIN invitaciones i ON i.invitador_aliado_id = a.id
                """)
                solicitudes_con_invitacion = cursor.fetchone()[0] or 0

                ratio_solicitud_invitacion = round(solicitudes_con_invitacion / max(total_solicitudes, 1), 2)
                ratio_invitacion_registro = round(invitaciones_usadas / max(total_invitaciones, 1), 2)

                # Oficios saturados / disponibles
                catalogo = self.get_catalogo_oficios_ruana()
                total_oficios_catalogo = len(catalogo) if catalogo else 0

                # Oficio saturado: >= 3 aliados activos con ese oficio (a nivel global)
                cursor.execute("""
                    SELECT COUNT(*) FROM (
                        SELECT oficio
                        FROM aliados
                        WHERE estado = 'activo' AND oficio IS NOT NULL AND TRIM(oficio) != ''
                        GROUP BY oficio
                        HAVING COUNT(*) >= 3
                    )
                """)
                num_oficios_saturados = cursor.fetchone()[0] or 0

                oficios_disponibles = 0
                if total_oficios_catalogo > 0:
                    oficios_disponibles = max(total_oficios_catalogo - num_oficios_saturados, 0)

                # Zona mayor demanda: CP con más solicitudes pendientes
                cursor.execute("""
                    SELECT g.codigo_postal, COUNT(*) as c
                    FROM solicitudes s
                    JOIN grupos g ON s.grupo_id = g.id
                    WHERE s.estado = 'pendiente' AND g.codigo_postal IS NOT NULL AND g.codigo_postal != ''
                    GROUP BY codigo_postal
                    ORDER BY c DESC
                    LIMIT 1
                """)
                row = cursor.fetchone()
                zona_mayor_demanda = (row[0] or '—') if row else '—'

                # Retención: aliados que han completado al menos 1 trabajo (contacto con cierre/no_concretado)
                cursor.execute("""
                    SELECT COUNT(DISTINCT codigo) FROM aliados
                    WHERE codigo IN (
                        SELECT solicitante_codigo
                        FROM contactos_ruana
                        WHERE (fecha_cierre IS NOT NULL OR fecha_no_concretado IS NOT NULL)
                        UNION
                        SELECT profesional_codigo
                        FROM contactos_ruana
                        WHERE (fecha_cierre IS NOT NULL OR fecha_no_concretado IS NOT NULL)
                    )
                """)
                aliados_con_trabajo = cursor.fetchone()[0] or 0

                tasa_retencion = round(100.0 * aliados_con_trabajo / max(total_aliados, 1), 1)

                return {
                    'ratio_solicitud_invitacion': ratio_solicitud_invitacion,
                    'ratio_invitacion_registro': ratio_invitacion_registro,
                    'oficios_saturados': num_oficios_saturados,
                    'oficios_disponibles': oficios_disponibles,
                    'zona_mayor_demanda': zona_mayor_demanda,
                    'tasa_retencion': tasa_retencion,
                }
            except Exception as e:
                print(f"Error obtener_metricas_salud: {e}")
                return {
                    'ratio_solicitud_invitacion': 0,
                    'ratio_invitacion_registro': 0,
                    'oficios_saturados': 0,
                    'oficios_disponibles': 0,
                    'zona_mayor_demanda': '—',
                    'tasa_retencion': 0,
                }
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

    def obtener_health_metrics_admin(self, umbral_suplentes: int = 1) -> Dict[str, Any]:
        """
        Métricas de salud para GET /api/admin/health-metrics.
        - ratio_solicitud_invitacion: solicitudes que generaron invitación / total solicitudes
        - ratio_invitacion_registro: invitaciones usadas / total invitaciones
        - oficios_saturados: oficios con más de X suplentes en competencia activa (X=umbral_suplentes)
        - oficios_disponibles: plazas sin titular (grupo+oficio sin aliado, no cerrada)
        - zona_mayor_demanda: código postal con más solicitudes pendientes
        - tasa_retencion: usuarios activos / total usuarios (en %)
        """
        conn = None
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()

                # Totales
                total_aliados = cursor.execute("SELECT COUNT(*) FROM aliados").fetchone()[0] or 0
                cursor.execute("SELECT COUNT(*) FROM aliados WHERE estado = 'activo'")
                aliados_activos = cursor.fetchone()[0] or 0
                total_solicitudes = cursor.execute("SELECT COUNT(*) FROM solicitudes").fetchone()[0] or 0
                total_invitaciones = cursor.execute("SELECT COUNT(*) FROM invitaciones").fetchone()[0] or 0
                cursor.execute("SELECT COUNT(*) FROM invitaciones WHERE usado = 1")
                invitaciones_usadas = cursor.fetchone()[0] or 0

                # Ratio solicitud → invitación
                cursor.execute("""
                    SELECT COUNT(DISTINCT s.id) FROM solicitudes s
                    JOIN aliados a ON s.solicitante_codigo = a.codigo
                    JOIN invitaciones i ON i.invitador_aliado_id = a.id
                """)
                solicitudes_con_invitacion = cursor.fetchone()[0] or 0
                ratio_solicitud_invitacion = round(solicitudes_con_invitacion / max(total_solicitudes, 1), 2)

                # Ratio invitación → registro
                ratio_invitacion_registro = round(invitaciones_usadas / max(total_invitaciones, 1), 2)

                # Oficios saturados: oficios con más de X retadores en competencia activa
                col_retador = self._columna_retador_competencia(cursor)
                cursor.execute("""
                    SELECT oficio, COUNT(DISTINCT """ + col_retador + """) as n
                    FROM competencia WHERE estado = 'activa'
                    GROUP BY oficio
                    HAVING COUNT(DISTINCT """ + col_retador + """) > ?
                """, (umbral_suplentes,))
                oficios_saturados = len(cursor.fetchall())

                # Oficios disponibles (sin titular): plazas vacías en grupos activos, no cerradas
                catalogo = self.get_catalogo_oficios_ruana()
                if not catalogo:
                    oficios_disponibles = 0
                else:
                    cursor.execute("""
                        SELECT g.id, g.codigo_postal FROM grupos g
                        WHERE g.estado = 'activo'
                    """)
                    grupos_activos = cursor.fetchall()
                    plazas_sin_titular = 0
                    for (gid, _) in grupos_activos:
                        cursor.execute(
                            "SELECT oficio FROM aliados WHERE grupo_id = ? AND estado = 'activo' AND oficio IS NOT NULL",
                            (gid,)
                        )
                        oficios_en_grupo = {r[0].strip() for r in cursor.fetchall() if r[0]}
                        cursor.execute(
                            "SELECT oficio FROM grupo_oficio_cerrado WHERE grupo_id = ?",
                            (gid,)
                        )
                        cerrados = {r[0].strip() for r in cursor.fetchall() if r[0]}
                        for oficio in catalogo:
                            if oficio and oficio not in oficios_en_grupo and oficio not in cerrados:
                                plazas_sin_titular += 1
                    oficios_disponibles = plazas_sin_titular

                # Zona mayor demanda: CP con más solicitudes pendientes
                cursor.execute("""
                    SELECT g.codigo_postal, COUNT(*) as c
                    FROM solicitudes s
                    JOIN grupos g ON s.grupo_id = g.id
                    WHERE s.estado = 'pendiente' AND g.codigo_postal IS NOT NULL AND g.codigo_postal != ''
                    GROUP BY g.codigo_postal
                    ORDER BY c DESC
                    LIMIT 1
                """)
                row = cursor.fetchone()
                zona_mayor_demanda = (row[0] or '—') if row else '—'

                # Tasa retención: activos / total
                tasa_retencion = round(100.0 * aliados_activos / max(total_aliados, 1), 1)

                return {
                    'ratio_solicitud_invitacion': ratio_solicitud_invitacion,
                    'ratio_invitacion_registro': ratio_invitacion_registro,
                    'oficios_saturados': oficios_saturados,
                    'oficios_disponibles': oficios_disponibles,
                    'zona_mayor_demanda': zona_mayor_demanda,
                    'tasa_retencion': tasa_retencion,
                }
            except Exception as e:
                print(f"Error obtener_health_metrics_admin: {e}")
                return {
                    'ratio_solicitud_invitacion': 0,
                    'ratio_invitacion_registro': 0,
                    'oficios_saturados': 0,
                    'oficios_disponibles': 0,
                    'zona_mayor_demanda': '—',
                    'tasa_retencion': 0,
                }
            finally:
                try:
                    if conn is not None:
                        conn.close()
                except Exception:
                    pass

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
