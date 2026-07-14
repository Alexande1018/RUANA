"""
Database Manager para RUANA - SQLite
Maneja toda la persistencia de datos usando SQLite
"""

import sqlite3
import json
import os
import random
import string
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any, Tuple
import threading

from core.postgres_compat import connect as pg_compat_connect
from core.settings import get_settings


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
            self._init_postgres_invitation_campaigns()

    def _connect(self):
        """Open a database connection for the configured backend."""
        if self.backend == "postgres":
            return pg_compat_connect(self.settings.database_url)
        return sqlite3.connect(self.db_path)

    def _init_postgres_invitation_campaigns(self):
        """Crea las tablas nuevas de campanas cuando el backend es Supabase/Postgres."""
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
            conn.commit()
        except Exception as e:
            print(f"[RUANA][DB] Error inicializando campanas en Postgres: {e}")
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
                
                # Invitaciones: quién invitó a cada código (para recompensa +5 al referir)
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

                # Competencia: suplente temporal cuando score < umbral; 1 mes, mayor score permanece
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS competencia (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        grupo_id INTEGER NOT NULL,
                        oficio TEXT NOT NULL,
                        aliado_original_codigo TEXT NOT NULL,
                        suplente_codigo TEXT NOT NULL,
                        suplente_grupo_anterior_id INTEGER,
                        fecha_inicio TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        fecha_fin_prevista TIMESTAMP NOT NULL,
                        estado TEXT DEFAULT 'activa' CHECK(estado IN ('activa', 'finalizada')),
                        ganador_codigo TEXT,
                        creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY(grupo_id) REFERENCES grupos(id),
                        FOREIGN KEY(aliado_original_codigo) REFERENCES aliados(codigo),
                        FOREIGN KEY(suplente_codigo) REFERENCES aliados(codigo)
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
                self._migrar_contactos_posponer_recordatorio(conn, cursor)
                self._migrar_contactos_fecha_pospuesto_hasta(conn, cursor)
                self._migrar_chat_mensajes(conn, cursor)
                self._migrar_contactos_motivo_contacto(conn, cursor)
                self._migrar_drop_chat_messages(conn, cursor)
                self._migrar_competencia_scores(conn, cursor)
                self._migrar_payment_conflicts(conn, cursor)
                self._migrar_contactos_validacion_pago(conn, cursor)
                self._migrar_solicitudes_unificado(conn, cursor)
                self._migrar_contacto_panel_oculto(conn, cursor)
                self._migrar_referidos_origen(conn, cursor)
                self._migrar_invitaciones_oficio_codigo_referido(conn, cursor)

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

    def _migrar_contactos_motivo_contacto(self, conn, cursor) -> None:
        """Añade motivo_contacto al contacto (obligatorio antes de iniciar chat)."""
        cursor.execute("PRAGMA table_info(contactos_ruana)")
        columnas = [row[1] for row in cursor.fetchall()]
        if 'motivo_contacto' in columnas:
            return
        cursor.execute("ALTER TABLE contactos_ruana ADD COLUMN motivo_contacto TEXT")

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
            ('score_suplente_inicio', 'INTEGER'),
            ('score_titular_actual', 'INTEGER'),
            ('score_suplente_actual', 'INTEGER'),
            ('motivo', 'TEXT'),
        ]:
            if col not in columnas:
                cursor.execute(f"ALTER TABLE competencia ADD COLUMN {col} {def_sql}")

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

    ORIGEN_REFERIDO_LABELS: Dict[str, str] = {
        'aliado': 'Invitación de aliado',
        'oficio': 'Invitación por oficio',
        'campana': 'Campaña del administrador',
        'admin_invitacion': 'Código del administrador',
        'huerfano': 'Registro directo · asignado al admin',
    }

    def etiqueta_origen_referido(self, origen: str) -> str:
        return self.ORIGEN_REFERIDO_LABELS.get((origen or '').strip(), '')

    def obtener_codigo_admin_referidos(self) -> str:
        """Código del aliado sistema que actúa como raíz admin en la red."""
        codigo = self.obtener_o_crear_invitador_admin('RUANA-ADMIN')
        return codigo or 'RUANA-ADMIN'

    def _insert_referido(self, codigo_referido: str, codigo_invitador: str, origen: str = '') -> bool:
        """Inserta vínculo invitador→referido (idempotente) con origen opcional."""
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
                cursor.execute("""
                    INSERT OR IGNORE INTO referidos (codigo_referido, codigo_invitador, origen)
                    VALUES (?, ?, ?)
                """, (codigo_referido, codigo_invitador, origen))
                inserted = cursor.rowcount > 0
                if origen and not inserted:
                    cursor.execute("""
                        UPDATE referidos
                        SET origen = ?
                        WHERE codigo_referido = ?
                          AND (origen IS NULL OR origen = '')
                    """, (origen, codigo_referido))
                conn.commit()
                return inserted or cursor.rowcount > 0
            except Exception:
                return False
            finally:
                if conn:
                    conn.close()

    def _origen_por_invitador(self, codigo_invitador: str, default: str = 'aliado') -> str:
        invitador = self.obtener_aliado_por_codigo(codigo_invitador)
        if invitador and (invitador.get('estado') or '').strip() == 'sistema':
            return 'admin_invitacion'
        return default

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
                return 'aliado'
            except Exception:
                return ''
            finally:
                if conn:
                    conn.close()

    def oficio_en_catalogo(self, oficio: str) -> bool:
        """True si el oficio está en el catálogo oficial RUANA (comparación normalizada)."""
        if not oficio or not str(oficio).strip():
            return False
        catalogo = self.get_catalogo_oficios_ruana()
        oficio_norm = str(oficio).strip()
        return oficio_norm in [str(o).strip() for o in catalogo if o]

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

    def _grupo_tiene_plaza(self, cursor, grupo_id: int, oficio_principal: str, especializacion: Optional[str]) -> bool:
        """True si la plaza (oficio_principal, especializacion) ya está ocupada en el grupo. Una plaza por especialización por grupo."""
        if not grupo_id or not oficio_principal:
            return False
        oficio_principal = oficio_principal.strip()
        esp_efectiva = (especializacion or oficio_principal).strip()
        # En BD: efectivo = COALESCE(NULLIF(TRIM(especializacion),''), oficio)
        cursor.execute(
            """SELECT 1 FROM aliados WHERE grupo_id = ? AND oficio = ? AND estado = 'activo'
               AND COALESCE(NULLIF(TRIM(COALESCE(especializacion,'')),''), oficio) = ? LIMIT 1""",
            (grupo_id, oficio_principal, esp_efectiva),
        )
        return cursor.fetchone() is not None

    def plaza_ocupada_en_grupo(self, grupo_id: int, oficio_principal: str, especializacion: Optional[str]) -> bool:
        """True si la plaza (oficio_principal, especializacion) ya está ocupada en el grupo. Thread-safe."""
        if not grupo_id or not oficio_principal:
            return False
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                return self._grupo_tiene_plaza(cursor, grupo_id, oficio_principal.strip(), (especializacion or '').strip() or None)
            except Exception:
                return True
            finally:
                conn.close()

    def obtener_especializaciones_ocupadas(self, grupo_id: int, oficio_principal: str) -> set:
        """Devuelve el conjunto de especializaciones ya ocupadas en el grupo para ese oficio (plaza única por especialización)."""
        if not grupo_id or not oficio_principal:
            return set()
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute(
                    """SELECT COALESCE(NULLIF(TRIM(especializacion), ''), oficio) AS esp
                       FROM aliados WHERE grupo_id = ? AND oficio = ? AND estado = 'activo'""",
                    (grupo_id, oficio_principal.strip()),
                )
                return {row[0].strip() for row in cursor.fetchall() if row[0]}
            except Exception:
                return set()
            finally:
                conn.close()

    def buscar_grupo_sin_oficio(self, codigo_postal: str, oficio: str, especializacion: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Devuelve un grupo activo en ese CP donde la plaza (oficio, especializacion) esté libre. Si especializacion es None, busca grupo sin ese oficio."""
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
                    if especializacion and especializacion.strip():
                        if not self._grupo_tiene_plaza(cursor, g['id'], oficio, especializacion.strip()):
                            return g
                    else:
                        if not self._grupo_tiene_oficio(cursor, g['id'], oficio):
                            return g
                return None
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
        Catálogo oficial: oficio principal obligatorio; si no está en catálogo → estado pendiente_validacion.
        Si grupo_id_invitacion está definido (registro con código "Conozco a alguien") y el oficio está en catálogo
        y ese grupo no tiene ese oficio, se asigna al grupo del invitador y estado = activo.
        Especializaciones opcionales (solo oficios del catálogo, no ocupan plaza en grupo).
        """
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                
                # Verificar unicidad del código
                cursor.execute("SELECT id FROM aliados WHERE codigo = ?", (codigo,))
                if cursor.fetchone():
                    return {
                        'status': 'error',
                        'message': f'Código {codigo} ya existe'
                    }
                
                # F07: Validación de unicidad mejorada - mensajes específicos
                # Buscar email duplicado
                cursor.execute("SELECT id FROM aliados WHERE email = ?", (email,))
                if cursor.fetchone():
                    return {
                        'status': 'error',
                        'message': f'El email {email} ya está registrado'
                    }
                
                # Buscar teléfono duplicado
                cursor.execute("SELECT id FROM aliados WHERE telefono = ?", (telefono,))
                if cursor.fetchone():
                    return {
                        'status': 'error',
                        'message': f'El teléfono {telefono} ya está registrado'
                    }
                
                # F07: Validaciones defensivas (app.py ya validó, pero aseguramos integridad).
                # Estos checks nunca deberían fallar si app.py hace su trabajo.
                # Para el flujo normal de alta de aliados exigimos 5 dígitos numéricos.
                if not codigo or len(codigo) != 5 or not codigo.isdigit():
                    return {
                        'status': 'error',
                        'message': 'El código debe ser un número de 5 dígitos (error de validación backend)'
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

                # Validar teléfono: debe tener al menos 7 dígitos (sin contar símbolos)
                import re
                digitos_telefono = re.sub(r'\D', '', telefono)
                if not telefono or len(digitos_telefono) < 7:
                    return {
                        'status': 'error',
                        'message': 'El teléfono es obligatorio y debe tener al menos 7 dígitos (error de validación backend)'
                    }

                # Catálogo oficial: oficio fuera de catálogo → pendiente_validacion (requiere validación manual)
                # Placeholder de invitación ("Conozco a alguien") mantiene pendiente_completar para que el código lleve a registro
                oficio_stripped = str(oficio).strip() if oficio else ''
                en_catalogo = self.oficio_en_catalogo(oficio_stripped) if oficio_stripped else False
                estado_final = estado
                if oficio_stripped and not en_catalogo and estado != 'pendiente_completar':
                    estado_final = 'pendiente_validacion'

                # Especializaciones: solo especialidades del mismo oficio (catálogo jerárquico), máx. 3 en total (plaza + lista)
                esp_plaza = (especializacion or '').strip() or oficio_stripped
                catalogo_jer = self.get_catalogo_oficios_jerarquico()
                oficio_info = next((o for o in catalogo_jer if (o.get('nombre') or '').strip() == oficio_stripped), None)
                allowed_esp = set()
                if oficio_info and oficio_info.get('especializaciones'):
                    allowed_esp = {str(e).strip() for e in oficio_info['especializaciones'] if str(e).strip()}
                # Si eligió "Otro" en suboficio (especialización no está en catálogo) → pendiente de validación
                if en_catalogo and oficio_stripped and estado_final != 'pendiente_completar' and esp_plaza:
                    if esp_plaza not in allowed_esp:
                        estado_final = 'pendiente_validacion'
                esp_list = list(especializaciones) if especializaciones is not None else []
                # Filtrar solo las que pertenecen a este oficio y no repetir la plaza; máx. 2 adicionales (total 3)
                esp_filtradas = []
                for e in esp_list:
                    s = str(e).strip()
                    if s and s in allowed_esp and s != esp_plaza and s not in esp_filtradas:
                        esp_filtradas.append(s)
                        if len(esp_filtradas) >= 2:  # plaza + 2 = 3 total
                            break
                especializaciones_json = json.dumps(esp_filtradas, ensure_ascii=False) if esp_filtradas else None

                # Asignación automática de grupo solo si oficio está en catálogo (no para pendiente_validacion)
                grupo_preferido_id = None
                if en_catalogo and oficio_stripped:
                    if grupo_id_invitacion:
                        # Registro con invitación: asignar al grupo del invitador si la plaza (oficio, especializacion) está libre
                        if not self._grupo_tiene_plaza(cursor, grupo_id_invitacion, oficio_stripped, esp_plaza or None):
                            grupo_pref = self.obtener_grupo_por_id(grupo_id_invitacion)
                            if grupo_pref and (grupo_pref.get('estado') or '') == 'activo':
                                grupo_preferido_id = grupo_id_invitacion
                    if grupo_preferido_id is None and codigo_postal:
                        grupos_activos = self.obtener_grupos_activos_por_cp(codigo_postal)
                        grupo_sin_oficio = self.buscar_grupo_sin_oficio(codigo_postal, oficio_stripped, esp_plaza or None)
                        if grupo_sin_oficio is None and len(grupos_activos) >= MAX_GRUPOS_POR_CP:
                            cp_adyacente = self.sugerir_cp_adyacente(codigo_postal)
                            msg = 'Límite de 5 grupos alcanzado para este código postal. Por favor use un código postal adyacente.'
                            if cp_adyacente:
                                msg += f' Sugerencia: {cp_adyacente}'
                            return {
                                'status': 'error',
                                'message': msg,
                                'redirect_to_codigo_postal': cp_adyacente or ''
                            }

                # Insertar aliado (oficio = principal; especializacion = plaza por grupo; especializaciones opcionales, no ocupan plaza)
                cursor.execute("""
                    INSERT INTO aliados 
                    (codigo, nombre, marca, oficio, codigo_postal, email, telefono, estado, score, especializaciones, especializacion)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (codigo, nombre, marca, oficio_stripped or oficio, codigo_postal, email, telefono, estado_final, score, especializaciones_json, esp_plaza or None))

                aliado_id = cursor.lastrowid
                conn.commit()

                # Asignar grupo solo si oficio en catálogo (pendiente_validacion no asigna grupo)
                if en_catalogo and oficio_stripped:
                    if grupo_preferido_id:
                        cursor.execute("UPDATE aliados SET grupo_id = ? WHERE id = ?", (grupo_preferido_id, aliado_id))
                        conn.commit()
                    elif codigo_postal:
                        grupo_asignar = self.buscar_grupo_sin_oficio(codigo_postal, oficio_stripped, esp_plaza or None)
                        if grupo_asignar:
                            cursor.execute("UPDATE aliados SET grupo_id = ? WHERE id = ?", (grupo_asignar['id'], aliado_id))
                        elif self.contar_grupos_activos_por_cp(codigo_postal) < MAX_GRUPOS_POR_CP:
                            nuevo_grupo = self.crear_grupo_en_cp(codigo_postal)
                            if isinstance(nuevo_grupo, dict) and 'id' in nuevo_grupo:
                                cursor.execute("UPDATE aliados SET grupo_id = ? WHERE id = ?", (nuevo_grupo['id'], aliado_id))
                        if cursor.rowcount:
                            conn.commit()

                # Leer fila recién insertada para devolver valores reales (incl. grupo_id, especializacion, descripcion_servicio)
                cursor.execute(
                    "SELECT id, codigo, nombre, marca, oficio, codigo_postal, grupo_id, email, telefono, estado, score, descripcion_servicio, especializacion, creado_en, actualizado_en FROM aliados WHERE id = ?",
                    (aliado_id,)
                )
                row = cursor.fetchone()
                if row and hasattr(row, 'keys'):
                    aliado_row = dict(row)
                elif row and isinstance(row, (list, tuple)):
                    cols = ('id', 'codigo', 'nombre', 'marca', 'oficio', 'codigo_postal', 'grupo_id', 'email', 'telefono', 'estado', 'score', 'descripcion_servicio', 'especializacion', 'creado_en', 'actualizado_en')
                    aliado_row = dict(zip(cols, row))
                else:
                    aliado_row = {
                        'id': aliado_id, 'codigo': codigo, 'nombre': nombre, 'marca': marca, 'oficio': oficio,
                        'codigo_postal': codigo_postal, 'grupo_id': None, 'email': email, 'telefono': telefono,
                        'estado': estado, 'score': score, 'creado_en': datetime.now().isoformat(), 'actualizado_en': None
                    }

                # Incluir especializaciones en la respuesta (lista, no JSON)
                out = {'status': 'success', **aliado_row}
                out['especializaciones'] = esp_filtradas
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
        """Completa un aliado placeholder creado por invitacion y conserva su codigo."""
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
                en_catalogo = self.oficio_en_catalogo(oficio_stripped) if oficio_stripped else False
                estado_final = estado
                if oficio_stripped and not en_catalogo:
                    estado_final = 'pendiente_validacion'

                esp_plaza = (especializacion or '').strip() or oficio_stripped
                catalogo_jer = self.get_catalogo_oficios_jerarquico()
                oficio_info = next((o for o in catalogo_jer if (o.get('nombre') or '').strip() == oficio_stripped), None)
                allowed_esp = set()
                if oficio_info and oficio_info.get('especializaciones'):
                    allowed_esp = {str(e).strip() for e in oficio_info['especializaciones'] if str(e).strip()}
                if en_catalogo and oficio_stripped and esp_plaza and esp_plaza not in allowed_esp:
                    estado_final = 'pendiente_validacion'

                esp_list = list(especializaciones) if especializaciones is not None else []
                esp_filtradas = []
                for e in esp_list:
                    s = str(e).strip()
                    if s and s in allowed_esp and s != esp_plaza and s not in esp_filtradas:
                        esp_filtradas.append(s)
                        if len(esp_filtradas) >= 2:
                            break
                especializaciones_json = json.dumps(esp_filtradas, ensure_ascii=False) if esp_filtradas else None

                grupo_preferido_id = None
                if en_catalogo and oficio_stripped:
                    if grupo_id_invitacion:
                        if not self._grupo_tiene_plaza(cursor, grupo_id_invitacion, oficio_stripped, esp_plaza or None):
                            grupo_pref = self.obtener_grupo_por_id(grupo_id_invitacion)
                            if grupo_pref and (grupo_pref.get('estado') or '') == 'activo':
                                grupo_preferido_id = grupo_id_invitacion
                    if grupo_preferido_id is None and codigo_postal:
                        grupos_activos = self.obtener_grupos_activos_por_cp(codigo_postal)
                        grupo_sin_oficio = self.buscar_grupo_sin_oficio(codigo_postal, oficio_stripped, esp_plaza or None)
                        if grupo_sin_oficio is None and len(grupos_activos) >= MAX_GRUPOS_POR_CP:
                            cp_adyacente = self.sugerir_cp_adyacente(codigo_postal)
                            msg = 'Limite de 5 grupos alcanzado para este codigo postal. Por favor use un codigo postal adyacente.'
                            if cp_adyacente:
                                msg += f' Sugerencia: {cp_adyacente}'
                            return {
                                'status': 'error',
                                'message': msg,
                                'redirect_to_codigo_postal': cp_adyacente or ''
                            }

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
                        especializaciones = ?,
                        especializacion = ?,
                        descripcion_servicio = ?,
                        actualizado_en = CURRENT_TIMESTAMP
                    WHERE id = ? AND estado = 'pendiente_completar'
                """, (
                    nombre, marca, oficio_stripped or oficio, codigo_postal, email, telefono,
                    estado_final, score, especializaciones_json, esp_plaza or None,
                    descripcion_servicio, aliado_id
                ))
                if cursor.rowcount != 1:
                    conn.rollback()
                    return {'status': 'error', 'message': 'Codigo de invitacion ya usado'}
                conn.commit()

                if en_catalogo and oficio_stripped:
                    if grupo_preferido_id:
                        cursor.execute("UPDATE aliados SET grupo_id = ? WHERE id = ?", (grupo_preferido_id, aliado_id))
                        conn.commit()
                    elif codigo_postal:
                        grupo_asignar = self.buscar_grupo_sin_oficio(codigo_postal, oficio_stripped, esp_plaza or None)
                        if grupo_asignar:
                            cursor.execute("UPDATE aliados SET grupo_id = ? WHERE id = ?", (grupo_asignar['id'], aliado_id))
                        elif self.contar_grupos_activos_por_cp(codigo_postal) < MAX_GRUPOS_POR_CP:
                            nuevo_grupo = self.crear_grupo_en_cp(codigo_postal)
                            if isinstance(nuevo_grupo, dict) and 'id' in nuevo_grupo:
                                cursor.execute("UPDATE aliados SET grupo_id = ? WHERE id = ?", (nuevo_grupo['id'], aliado_id))
                        if cursor.rowcount:
                            conn.commit()

                cursor.execute(
                    "SELECT id, codigo, nombre, marca, oficio, codigo_postal, grupo_id, email, telefono, estado, score, descripcion_servicio, especializacion, creado_en, actualizado_en FROM aliados WHERE id = ?",
                    (aliado_id,)
                )
                row = cursor.fetchone()
                if row and hasattr(row, 'keys'):
                    aliado_row = dict(row)
                elif row and isinstance(row, (list, tuple)):
                    cols = ('id', 'codigo', 'nombre', 'marca', 'oficio', 'codigo_postal', 'grupo_id', 'email', 'telefono', 'estado', 'score', 'descripcion_servicio', 'especializacion', 'creado_en', 'actualizado_en')
                    aliado_row = dict(zip(cols, row))
                else:
                    aliado_row = {
                        'id': aliado_id, 'codigo': codigo, 'nombre': nombre, 'marca': marca, 'oficio': oficio,
                        'codigo_postal': codigo_postal, 'grupo_id': None, 'email': email, 'telefono': telefono,
                        'estado': estado_final, 'score': score, 'creado_en': datetime.now().isoformat(), 'actualizado_en': None
                    }

                out = {'status': 'success', **aliado_row}
                out['especializaciones'] = esp_filtradas
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
                'qr_paypal_path', 'bizum_num'
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
    
    # ===============================================
    # SCORE RUANA (0-100, estado derivado, límites ±10/día)
    # ===============================================
    
    @staticmethod
    def score_a_estado(score: Any) -> str:
        """
        Calcula el estado RUANA a partir del score (siempre derivado, sin almacenar).
        PRIORITARIO 85-100, ESTABLE 60-84, EN RIESGO 35-59, COMPETENCIA 0-34.
        """
        try:
            s = int(score) if score is not None else 0
        except (TypeError, ValueError):
            s = 0
        if s >= 85:
            return 'PRIORITARIO'
        if s >= 60:
            return 'ESTABLE'
        if s >= 35:
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
        Aplica un cambio de score respetando: score en [0, 100], máximo ±10 por día.
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
                # Limitar score final a [0, 100]
                score_nuevo = max(0, min(100, score_actual + delta_aplicar))
                delta_real = score_nuevo - score_actual
                if delta_real == 0:
                    conn.close()
                    return {'status': 'success', 'aplicado': 0, 'score_final': score_actual}
                cursor.execute("""
                    INSERT INTO score_movimientos (codigo_aliado, delta, motivo)
                    VALUES (?, ?, ?)
                """, (codigo_aliado, delta_real, motivo))
                cursor.execute("""
                    UPDATE aliados SET score = ?, actualizado_en = CURRENT_TIMESTAMP
                    WHERE codigo = ?
                """, (score_nuevo, codigo_aliado))
                conn.commit()
                # Si el score cruza por debajo del umbral de competencia, iniciar proceso de competencia
                umbral = self._get_umbral_competencia()
                if umbral is not None and score_nuevo < umbral and score_actual >= umbral:
                    self._iniciar_competencia_si_procede(codigo_aliado)
                return {'status': 'success', 'aplicado': delta_real, 'score_final': score_nuevo}
            except Exception as e:
                return {'status': 'error', 'message': str(e)}
            finally:
                conn.close()
    
    def _get_umbral_competencia(self) -> Optional[int]:
        """Lee umbral_competencia desde config/ruana_reglas_v1.json. Por defecto 35."""
        try:
            config_path = Path(__file__).resolve().parent.parent / 'config' / 'ruana_reglas_v1.json'
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return int(data.get('umbral_competencia', 35))
        except Exception:
            pass
        return 35

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

    def competencia_activa_para_grupo_oficio(self, grupo_id: int, oficio: str) -> Optional[Dict[str, Any]]:
        """Devuelve la competencia activa para ese grupo y oficio, o None."""
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, grupo_id, oficio, aliado_original_codigo, suplente_codigo, suplente_grupo_anterior_id,
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
                cursor.execute("""
                    SELECT c.id, c.grupo_id, c.oficio, c.aliado_original_codigo, c.suplente_codigo,
                           c.suplente_grupo_anterior_id, c.fecha_inicio, c.fecha_fin_prevista,
                           c.score_titular_inicio, c.score_suplente_inicio,
                           c.score_titular_actual, c.score_suplente_actual, c.motivo,
                           t.id AS titular_id, t.nombre AS titular_nombre, t.score AS titular_score_actual,
                           s.id AS suplente_id, s.nombre AS suplente_nombre, s.score AS suplente_score_actual,
                           g.nombre AS grupo_nombre, g_origen.nombre AS grupo_origen_nombre
                    FROM competencia c
                    JOIN aliados t ON t.codigo = c.aliado_original_codigo
                    JOIN aliados s ON s.codigo = c.suplente_codigo
                    JOIN grupos g ON g.id = c.grupo_id
                    LEFT JOIN grupos g_origen ON g_origen.id = c.suplente_grupo_anterior_id
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
                    score_supl_actual = r.get('suplente_score_actual')
                    if score_supl_actual is not None:
                        score_supl_actual = int(score_supl_actual)
                    else:
                        score_supl_actual = r.get('score_suplente_actual')
                        if score_supl_actual is not None:
                            score_supl_actual = int(score_supl_actual)
                        else:
                            score_supl_actual = r.get('score_suplente_inicio', 0)
                    score_tit_inicio = int(r.get('score_titular_inicio') or 0)
                    score_supl_inicio = int(r.get('score_suplente_inicio') or 0)
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
                        'suplente': {
                            'id': r.get('suplente_id'),
                            'codigo': r.get('suplente_codigo'),
                            'nombre': r.get('suplente_nombre') or '',
                            'grupo_origen': r.get('grupo_origen_nombre') or f"Grupo {r.get('suplente_grupo_anterior_id')}" if r.get('suplente_grupo_anterior_id') else '—',
                            'score_actual': score_supl_actual,
                            'score_inicio': score_supl_inicio,
                        },
                        'fecha_inicio': fecha_inicio,
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

    def _buscar_suplente(self, codigo_aliado_en_riesgo: str, grupo_id: int, oficio: str,
                         score_actual: int, ciudad: Optional[str], provincia: Optional[str],
                         codigo_postal: str) -> Optional[Dict[str, Any]]:
        """
        Suplente: mismo oficio, mayor score, misma ciudad/provincia (o mismo CP si no hay),
        prioridad grupos con <3 aliados, luego lista territorial (mismo CP).
        Excluye al aliado en riesgo y a quien ya esté en ese grupo.
        """
        if not oficio or not codigo_postal:
            return None
        oficio = oficio.strip()
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                # Aliados activos, mismo oficio, score > score_actual, no sea él ni esté ya en este grupo
                if ciudad or provincia:
                    c, p = (ciudad or '').strip() or None, (provincia or '').strip() or None
                    cursor.execute("""
                        SELECT a.codigo, a.score, a.grupo_id, g.ciudad, g.provincia, g.codigo_postal,
                               (SELECT COUNT(*) FROM aliados a2 WHERE a2.grupo_id = a.grupo_id AND a2.estado = 'activo') as n_aliados
                        FROM aliados a
                        JOIN grupos g ON g.id = a.grupo_id AND g.estado = 'activo'
                        WHERE a.estado = 'activo' AND a.oficio = ? AND a.score > ?
                          AND a.codigo != ? AND (a.grupo_id IS NULL OR a.grupo_id != ?)
                          AND (? IS NULL OR g.ciudad = ?) AND (? IS NULL OR g.provincia = ?)
                        ORDER BY n_aliados ASC, a.score DESC, (CASE WHEN g.codigo_postal = ? THEN 0 ELSE 1 END), g.codigo_postal
                        LIMIT 1
                    """, (oficio, score_actual, codigo_aliado_en_riesgo, grupo_id, c, c, p, p, codigo_postal))
                else:
                    cursor.execute("""
                        SELECT a.codigo, a.score, a.grupo_id, g.ciudad, g.provincia, g.codigo_postal,
                               (SELECT COUNT(*) FROM aliados a2 WHERE a2.grupo_id = a.grupo_id AND a2.estado = 'activo') as n_aliados
                        FROM aliados a
                        JOIN grupos g ON g.id = a.grupo_id AND g.estado = 'activo'
                        WHERE a.estado = 'activo' AND a.oficio = ? AND a.score > ?
                          AND a.codigo != ? AND (a.grupo_id IS NULL OR a.grupo_id != ?)
                          AND g.codigo_postal = ?
                        ORDER BY n_aliados ASC, a.score DESC
                        LIMIT 1
                    """, (oficio, score_actual, codigo_aliado_en_riesgo, grupo_id, codigo_postal))
                row = cursor.fetchone()
                if row:
                    return dict(row)
                # Sin ciudad/provincia: intentar mismo CP
                if not ciudad and not provincia:
                    return None
                cursor.execute("""
                    SELECT a.codigo, a.score, a.grupo_id, g.codigo_postal,
                           (SELECT COUNT(*) FROM aliados a2 WHERE a2.grupo_id = a.grupo_id AND a2.estado = 'activo') as n_aliados
                    FROM aliados a
                    JOIN grupos g ON g.id = a.grupo_id AND g.estado = 'activo'
                    WHERE a.estado = 'activo' AND a.oficio = ? AND a.score > ?
                      AND a.codigo != ? AND (a.grupo_id IS NULL OR a.grupo_id != ?)
                      AND g.codigo_postal = ?
                    ORDER BY n_aliados ASC, a.score DESC
                    LIMIT 1
                """, (oficio, score_actual, codigo_aliado_en_riesgo, grupo_id, codigo_postal))
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
                suplente = self._buscar_suplente(codigo_aliado, grupo_id, oficio, score_actual, ciudad, provincia, codigo_postal)
                if not suplente:
                    return None
                suplente_codigo = suplente['codigo']
                suplente_grupo_anterior_id = suplente.get('grupo_id')
                score_titular_inicio = int(score_actual)
                score_suplente_inicio = int(suplente.get('score', 0) or 0)
                duracion_dias = self._get_duracion_competencia_dias()
                from datetime import timedelta
                fecha_fin = (datetime.now() + timedelta(days=duracion_dias)).strftime('%Y-%m-%d %H:%M:%S')
                cursor.execute("""
                    INSERT INTO competencia (grupo_id, oficio, aliado_original_codigo, suplente_codigo, suplente_grupo_anterior_id,
                        score_titular_inicio, score_suplente_inicio, score_titular_actual, score_suplente_actual,
                        fecha_fin_prevista, estado, motivo)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'activa', 'score bajo')
                """, (grupo_id, oficio.strip(), codigo_aliado, suplente_codigo, suplente_grupo_anterior_id,
                      score_titular_inicio, score_suplente_inicio, score_titular_inicio, score_suplente_inicio,
                      fecha_fin))
                cursor.execute("UPDATE aliados SET grupo_id = ? WHERE codigo = ?", (grupo_id, suplente_codigo))
                cursor.execute("UPDATE grupos SET estado = 'en_competencia' WHERE id = ?", (grupo_id,))
                texto_aviso = f"Este mes tenemos {oficio.strip()} en competencia dentro del grupo."
                cursor.execute("INSERT INTO avisos_grupo (grupo_id, tipo, texto) VALUES (?, 'competencia', ?)", (grupo_id, texto_aviso))
                conn.commit()
                try:
                    self.registrar_evento_sistema(
                        'competencia_iniciada',
                        f'Competencia iniciada: titular {codigo_aliado} vs suplente {suplente_codigo} en grupo {grupo_id}',
                        actor_tipo='sistema',
                        metadata={'grupo_id': grupo_id, 'oficio': oficio.strip(), 'titular_codigo': codigo_aliado, 'suplente_codigo': suplente_codigo}
                    )
                except Exception:
                    pass
                return {'grupo_id': grupo_id, 'suplente_codigo': suplente_codigo, 'oficio': oficio}
            except Exception as e:
                try:
                    conn.rollback()
                except Exception:
                    pass
                return None
            finally:
                conn.close()

    def finalizar_competencia_activas_vencidas(self) -> List[Dict[str, Any]]:
        """Finaliza competencias cuya fecha_fin_prevista ha pasado. Mayor score permanece, el otro sale del grupo."""
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, grupo_id, oficio, aliado_original_codigo, suplente_codigo, suplente_grupo_anterior_id
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

    def _finalizar_una_competencia(self, competencia_id: int, grupo_id: int, aliado_original_codigo: str,
                                   suplente_codigo: str, suplente_grupo_anterior_id: Optional[int]) -> Dict[str, Any]:
        """
        Compara scores (sin exponerlos); el mayor permanece, el otro sale.
        Primera derrota (original pierde): no eliminar perfil, no desactivar código;
        crear o asignar a un grupo REAL (RUANA-XXX), reiniciar score a 50. Grupo normal: solicitudes, score, 1 oficio.
        """
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute("SELECT score FROM aliados WHERE codigo = ?", (aliado_original_codigo,))
                s1 = cursor.fetchone()
                cursor.execute("SELECT score FROM aliados WHERE codigo = ?", (suplente_codigo,))
                s2 = cursor.fetchone()
                score_orig = int(s1[0]) if s1 and s1[0] is not None else 0
                score_supl = int(s2[0]) if s2 and s2[0] is not None else 0
                ganador = aliado_original_codigo if score_orig >= score_supl else suplente_codigo
                if ganador == suplente_codigo:
                    cursor.execute("SELECT codigo_postal, ciudad, provincia FROM grupos WHERE id = ?", (grupo_id,))
                    g = cursor.fetchone()
                    codigo_postal = (g[0] or '') if g else ''
                    ciudad = (g[1] or '') if g and len(g) > 1 else ''
                    provincia = (g[2] or '') if g and len(g) > 2 else ''
                    cursor.execute("SELECT oficio FROM aliados WHERE codigo = ?", (aliado_original_codigo,))
                    oficio_row = cursor.fetchone()
                    oficio = (oficio_row[0] or '').strip() if oficio_row else ''
                    conn.commit()
                    conn.close()
                    grupo_nuevo = None
                    if codigo_postal and oficio:
                        grupo_nuevo = self.buscar_grupo_sin_oficio(codigo_postal, oficio)
                        if not grupo_nuevo and self.contar_grupos_activos_por_cp(codigo_postal) < MAX_GRUPOS_POR_CP:
                            grupo_nuevo = self.crear_grupo_en_cp(codigo_postal, ciudad, provincia)
                    conn2 = self._connect()
                    cur2 = conn2.cursor()
                    if grupo_nuevo and isinstance(grupo_nuevo, dict) and grupo_nuevo.get('id'):
                        cur2.execute(
                            """UPDATE aliados SET grupo_id = ?, score = 50,
                               derrotas_competencia = COALESCE(derrotas_competencia, 0) + 1,
                               actualizado_en = CURRENT_TIMESTAMP WHERE codigo = ?""",
                            (grupo_nuevo['id'], aliado_original_codigo)
                        )
                    else:
                        cur2.execute(
                            """UPDATE aliados SET grupo_id = NULL, score = 50,
                               derrotas_competencia = COALESCE(derrotas_competencia, 0) + 1,
                               actualizado_en = CURRENT_TIMESTAMP WHERE codigo = ?""",
                            (aliado_original_codigo,)
                        )
                    cur2.execute(
                        "UPDATE aliados SET estado = 'expulsado' WHERE codigo = ? AND COALESCE(derrotas_competencia, 0) >= 2",
                        (aliado_original_codigo,)
                    )
                    conn2.commit()
                    conn2.close()
                    self.procesar_viabilidad_grupo(grupo_id)
                    conn = self._connect()
                    cursor = conn.cursor()
                else:
                    cursor.execute("UPDATE aliados SET grupo_id = ? WHERE codigo = ?", (suplente_grupo_anterior_id, suplente_codigo))
                    if suplente_grupo_anterior_id:
                        self.procesar_viabilidad_grupo(suplente_grupo_anterior_id)
                cursor.execute("UPDATE competencia SET estado = 'finalizada', ganador_codigo = ? WHERE id = ?", (ganador, competencia_id))
                cursor.execute("UPDATE grupos SET estado = 'activo' WHERE id = ?", (grupo_id,))
                conn.commit()
                return {'status': 'ok', 'ganador_codigo': ganador}
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
    
    def contar_referidos_por_codigo(self, codigo_aliado: str) -> int:
        """Cuenta aliados referidos válidos por este aliado (para métrica 'Aliados referidos por mí')."""
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT COUNT(*) FROM referidos WHERE codigo_invitador = ?",
                    (codigo_aliado,)
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
        esp_raw = aliado.get('especializaciones')
        especializaciones: List[str] = []
        if esp_raw:
            try:
                especializaciones = json.loads(esp_raw) if isinstance(esp_raw, str) else list(esp_raw)
            except Exception:
                especializaciones = []
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
        """Sincroniza referidos: campañas, invitaciones aliado, oficio y huérfanos bajo admin."""
        campanas = self.sincronizar_referidos_campanas_admin()
        invitaciones = self.sincronizar_referidos_invitaciones_usadas()
        oficio = self.sincronizar_referidos_invitaciones_oficio_usadas()
        huerfanos = self.sincronizar_referidos_huerfanos_admin()
        return {
            'campanas': campanas,
            'invitaciones': invitaciones,
            'oficio': oficio,
            'huerfanos': huerfanos,
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
                           a.especializaciones,
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
                    esp_raw = item.get('especializaciones')
                    if esp_raw:
                        try:
                            item['especializaciones'] = json.loads(esp_raw) if isinstance(esp_raw, str) else list(esp_raw)
                        except Exception:
                            item['especializaciones'] = []
                    else:
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

    def _registrar_invitacion(self, codigo_invitacion: str, invitador_aliado_id: int) -> None:
        """Registra que este código de invitación fue creado por el aliado invitador (para +5 al completar)."""
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO invitaciones (codigo, invitador_aliado_id, usado)
                    VALUES (?, ?, 0)
                """, (codigo_invitacion, invitador_aliado_id))
                conn.commit()
            finally:
                conn.close()

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
        Registra el referido y da +5 al invitador si la invitación aún no estaba usada.
        Idempotente: si ya estaba usada pero faltaba el vínculo en referidos, lo crea sin duplicar score.
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
                cursor.execute(
                    "SELECT 1 FROM referidos WHERE codigo_referido = ?",
                    (nuevo_aliado_codigo,),
                )
                ya_registrado = cursor.fetchone() is not None
                if not ya_registrado:
                    if usado == 0:
                        self.aplicar_cambio_score(codigo_invitador, 5, 'aliado_referido_registro_valido')
                    cursor.execute("""
                        INSERT OR IGNORE INTO referidos (codigo_referido, codigo_invitador, origen)
                        VALUES (?, ?, ?)
                    """, (nuevo_aliado_codigo, codigo_invitador, origen))
                if usado == 0:
                    cursor.execute(
                        "UPDATE invitaciones SET usado = 1 WHERE codigo = ?",
                        (codigo_invitacion,),
                    )
                conn.commit()
                return True
            except Exception:
                return False
            finally:
                if conn:
                    conn.close()

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
        Marca una invitación por oficio como usada, registra referido y da +5 al generador.
        Idempotente si ya estaba usada pero faltaba el vínculo en referidos.
        """
        codigo = (codigo or '').strip().upper()
        nuevo_aliado_codigo = (nuevo_aliado_codigo or '').strip()
        if not codigo or not nuevo_aliado_codigo:
            return False
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
                        self.aplicar_cambio_score(codigo_invitador, 5, 'invitacion_oficio_usada')
                        cursor.execute("""
                            INSERT OR IGNORE INTO referidos (codigo_referido, codigo_invitador, origen)
                            VALUES (?, ?, 'oficio')
                        """, (nuevo_aliado_codigo, codigo_invitador))
                elif estado == 'usado' and not ya_registrado:
                    cursor.execute(
                        "UPDATE invitaciones_oficio SET codigo_referido = ? WHERE id = ? AND COALESCE(codigo_referido, '') = ''",
                        (nuevo_aliado_codigo, invitacion_id),
                    )
                    cursor.execute("""
                        INSERT OR IGNORE INTO referidos (codigo_referido, codigo_invitador, origen)
                        VALUES (?, ?, 'oficio')
                    """, (nuevo_aliado_codigo, codigo_invitador))
                conn.commit()
                return True
            except Exception:
                return False
            finally:
                if conn:
                    conn.close()

    def listar_aliados(self, filtro_postal: str = None) -> List[Dict[str, Any]]:
        """
        Lista todos los aliados, opcionalmente filtrados por código postal
        
        Args:
            filtro_postal: Código postal para filtrar (opcional)
            
        Returns:
            Lista de aliados
        """
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                base_query = """
                    SELECT
                        a.*,
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
                            WHERE c.suplente_codigo = a.codigo AND c.estado = 'activa' LIMIT 1
                        ) AS es_suplente_activo,
                        (
                            SELECT 1 FROM competencia c
                            WHERE c.aliado_original_codigo = a.codigo AND c.estado = 'activa' LIMIT 1
                        ) AS es_titular_en_competencia
                    FROM aliados a
                    LEFT JOIN evaluaciones e ON e.codigo_aliado = a.codigo
                    WHERE (a.estado IS NULL OR (a.estado != 'expulsado' AND a.estado != 'suspendido_temporal' AND a.estado != 'sistema'))
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

                    # Parsear especializaciones JSON a lista
                    esp_raw = item.get('especializaciones')
                    if esp_raw:
                        try:
                            item['especializaciones'] = json.loads(esp_raw)
                        except Exception:
                            item['especializaciones'] = []
                    else:
                        item['especializaciones'] = []

                    # Zona legible para el panel (usa código postal por ahora)
                    item['zona'] = item.get('codigo_postal') or ''

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

                    # Estado derivado desde score de evaluación para filtros del panel
                    estado_bd = item.get('estado') or 'activo'
                    estado_panel = 'activos'
                    if estado_bd in ('expulsado', 'suspendido_temporal'):
                        estado_panel = estado_bd
                    else:
                        if eval_score is not None:
                            try:
                                s = float(eval_score)
                            except Exception:
                                s = float(item.get('score') or 0)
                        else:
                            s = float(item.get('score') or 0)

                        if s < 35:
                            estado_panel = 'riesgo'
                        elif s < 60:
                            estado_panel = 'observacion'
                        else:
                            estado_panel = 'activos'

                    item['estado_panel'] = estado_panel

                    # Suplente activo: 1 si está en competencia como suplente, 0/None si no
                    item['es_suplente_activo'] = bool(item.get('es_suplente_activo'))
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
        Lista todos los profesionales del mismo grupo que el aliado (para el directorio).
        Excluye al propio aliado. Solo activos. Garantiza mostrar siempre todos los del grupo.
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
                # Incluir activo y pendiente_validacion para mostrar a todos los del grupo/zona
                estados_ok = ('activo', 'pendiente_validacion')
                if grupo_id is not None and codigo_postal:
                    # Mismo grupo O mismo código postal (incluye aliados con grupo_id NULL en la zona)
                    cursor.execute("""
                        SELECT id, codigo, nombre, marca, oficio, codigo_postal, grupo_id, estado, score, descripcion_servicio, creado_en
                        FROM aliados
                        WHERE estado IN (?, ?) AND codigo != ?
                        AND (grupo_id = ? OR codigo_postal = ?)
                        ORDER BY nombre
                    """, (estados_ok[0], estados_ok[1], codigo_excluir, grupo_id, codigo_postal))
                elif grupo_id is not None:
                    cursor.execute("""
                        SELECT id, codigo, nombre, marca, oficio, codigo_postal, grupo_id, estado, score, descripcion_servicio, creado_en
                        FROM aliados
                        WHERE grupo_id = ? AND estado IN (?, ?) AND codigo != ?
                        ORDER BY nombre
                    """, (grupo_id, estados_ok[0], estados_ok[1], codigo_excluir))
                else:
                    # Sin grupo: mismo código postal (fallback)
                    cursor.execute("""
                        SELECT id, codigo, nombre, marca, oficio, codigo_postal, grupo_id, estado, score, descripcion_servicio, creado_en
                        FROM aliados
                        WHERE codigo_postal = ? AND estado IN (?, ?) AND codigo != ?
                        ORDER BY nombre
                    """, (codigo_postal or '', estados_ok[0], estados_ok[1], codigo_excluir))
                rows = cursor.fetchall()
                result = []
                for row in rows:
                    item = dict(row)
                    item['zona'] = item.get('codigo_postal') or ''
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
        """Verifica si un código ya existe"""
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                
                cursor.execute("SELECT 1 FROM aliados WHERE codigo = ?", (codigo,))
                return cursor.fetchone() is not None
                
            except Exception as e:
                print(f"Error verificando código: {e}")
                return False
            finally:
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

    def activar_aliado_por_id(self, aliado_id: int) -> Dict[str, Any]:
        """Activa aliado por ID numérico (pendiente_validacion → activo)."""
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE aliados SET estado = 'activo', actualizado_en = CURRENT_TIMESTAMP WHERE id = ? AND LOWER(TRIM(COALESCE(estado, ''))) = 'pendiente_validacion'",
                    (int(aliado_id),)
                )
                conn.commit()
                if cursor.rowcount > 0:
                    cursor.execute("SELECT codigo FROM aliados WHERE id = ?", (int(aliado_id),))
                    row = cursor.fetchone()
                    codigo = row[0] if row else ''
                    return {'status': 'success', 'message': f'Aliado {codigo} activado correctamente'}
                return {'status': 'error', 'message': f'Aliado con ID {aliado_id} no encontrado o no está pendiente de validación'}
            except Exception as e:
                return {'status': 'error', 'message': str(e)}
            finally:
                conn.close()

    def activar_aliado_pendiente(self, codigo: str) -> Dict[str, Any]:
        """Cambia estado de pendiente_validacion a activo. Requiere que el aliado exista y esté pendiente."""
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE aliados SET estado = 'activo', actualizado_en = CURRENT_TIMESTAMP WHERE codigo = ? AND estado = 'pendiente_validacion'",
                    (codigo.strip(),)
                )
                conn.commit()
                if cursor.rowcount > 0:
                    return {'status': 'success', 'message': f'Aliado {codigo} activado correctamente'}
                return {'status': 'error', 'message': f'Aliado {codigo} no encontrado o no está pendiente de validación'}
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
        """Solo mismo grupo, estado pendiente, excluye las propias. GET /api/solicitudes?codigo=."""
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
                cursor.execute("""
                    SELECT id, grupo_id, solicitante_codigo, solicitante_nombre, oficio, descripcion, estado, created_at
                    FROM solicitudes
                    WHERE grupo_id = ? AND estado = 'pendiente' AND solicitante_codigo != ?
                    ORDER BY created_at DESC
                """, (grupo_id, codigo.strip()))
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
                cursor.execute("""
                    SELECT id, grupo_id, solicitante_codigo, solicitante_nombre, oficio, descripcion, estado, created_at,
                           atendido_por_codigo, atendido_por_nombre, atendido_at
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
                cursor.execute("""
                    SELECT id, grupo_id, solicitante_codigo, solicitante_nombre, oficio, descripcion, estado, created_at,
                           atendido_por_codigo, atendido_por_nombre, atendido_at
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

    # Limites chat RUANA: 30 mensajes totales por conversacion, 48h de vigencia.
    CHAT_MAX_MENSAJES_TOTAL = 30
    CHAT_MAX_MENSAJES_POR_USUARIO = CHAT_MAX_MENSAJES_TOTAL
    CHAT_HORAS_VIGENCIA = 48

    def crear_contacto_ruana(self, solicitante_codigo: str, profesional_codigo: str,
                             servicio: str = "", motivo_contacto: str = "") -> Dict[str, Any]:
        """
        Crea un nuevo contacto RUANA en estado 'iniciado'.
        motivo_contacto: obligatorio para el flujo de chat (quién contactó a quién y por qué).
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
                if 'motivo_contacto' in columnas:
                    cursor.execute("""
                        INSERT INTO contactos_ruana (
                            solicitante_codigo, profesional_codigo, servicio, motivo_contacto,
                            estado, pendiente_resolucion, contacto_externo_habilitado
                        ) VALUES (?, ?, ?, ?, 'iniciado', 1, 0)
                    """, (solicitante_codigo, profesional_codigo, servicio or '', (motivo_contacto or '').strip() or None))
                else:
                    cursor.execute("""
                        INSERT INTO contactos_ruana (
                            solicitante_codigo, profesional_codigo, servicio,
                            estado, pendiente_resolucion, contacto_externo_habilitado
                        ) VALUES (?, ?, ?, 'iniciado', 1, 0)
                    """, (solicitante_codigo, profesional_codigo, servicio or ''))

                contacto_id = cursor.lastrowid
                conn.commit()

                return {
                    'status': 'success',
                    'id': contacto_id,
                    'estado': 'iniciado',
                    'solicitante_codigo': solicitante_codigo,
                    'profesional_codigo': profesional_codigo,
                    'servicio': servicio or '',
                    'motivo_contacto': (motivo_contacto or '').strip() or None,
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
        Ver marcar_cerrado_no_concretado para el flujo con -2 y audit.
        """
        return self.marcar_cerrado_no_concretado(contacto_id, motivo=motivo)

    def marcar_cerrado_no_concretado(self, contacto_id: int, motivo: str = "",
                                     actor_codigo: str = "") -> Dict[str, Any]:
        """
        Cierra el contacto como no concretado. Transacción atómica:
        - Estado → cerrado_no_concretado, pendiente_resolucion = 0.
        - -2 puntos Score RUANA a cada aliado.
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
            self.aplicar_cambio_score(sol, -2, 'contacto_cerrado_no_concretado')
        if prof:
            self.aplicar_cambio_score(prof, -2, 'contacto_cerrado_no_concretado')
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
                if count_total + 1 >= self.CHAT_MAX_MENSAJES_TOTAL:
                    cursor.execute(
                        """UPDATE contactos_ruana SET estado = 'chat_agotado', actualizado_en = CURRENT_TIMESTAMP
                           WHERE id = ? AND estado IN ('iniciado', 'aceptado', 'trabajo_en_progreso', 'en_conversacion')""",
                        (contacto_id,)
                    )

                conn.commit()

                # --- 8. Retorno: mensaje insertado (ambos aliados lo verán en GET /api/chat_mensajes) ---
                cursor.execute(
                    "SELECT id, contacto_id, emisor_codigo, texto, creado_en FROM chat_mensajes WHERE id = ?",
                    (msg_id,)
                )
                msg_row = cursor.fetchone()
                return {'status': 'success', 'mensaje': dict(msg_row)}

            except Exception as e:
                return {'status': 'error', 'message': str(e)}
            finally:
                conn.close()

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
                cursor.execute(f"""
                    SELECT c.id, c.solicitante_codigo, c.profesional_codigo, c.servicio, c.estado, c.creado_en,
                           c.fecha_cierre, c.fecha_no_concretado, c.importe_final, c.comision, {motivo_col}
                           (SELECT COUNT(*) FROM chat_mensajes m WHERE m.contacto_id = c.id) AS num_mensajes,
                           (SELECT MAX(m.creado_en) FROM chat_mensajes m WHERE m.contacto_id = c.id) AS ultimo_mensaje_en
                    FROM contactos_ruana c
                    ORDER BY c.creado_en DESC
                    LIMIT ?
                """, (limite,))
                return [dict(row) for row in cursor.fetchall()]
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
        - Apoyo RUANA segun apoyo_pct configurado. +8 / -1 segun coincidencia.
        - Coinciden → trabajo_cerrado, ingresos_ruana, audit_log.
        - No coinciden → importe_en_disputa, audit_log.
        """
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
                return {'status': 'success', 'id': contacto_id, 'estado': resultado_estado}
            except Exception as e:
                return {'status': 'error', 'message': str(e)}
            finally:
                conn.close()

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
        Contactos RUANA abiertos para un aliado que deben mostrarse como alerta activa.
        Se excluyen: posponer_recordatorio=1 y fecha_pospuesto_hasta > now; y contactos con chat expirado
        (más de CHAT_HORAS_VIGENCIA desde última actividad: último mensaje o max(fecha_aceptacion, creado_en)).
        Comparación con TRIM para evitar fallos por espacios en solicitante_codigo/profesional_codigo.
        """
        codigo_aliado = (codigo_aliado or "").strip()
        if not codigo_aliado:
            return []
        horas_vigencia = self.CHAT_HORAS_VIGENCIA
        with self._lock:
            try:
                conn = self._connect()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                if self.backend == "postgres":
                    cutoff = datetime.now(timezone.utc) - timedelta(hours=horas_vigencia)
                    cursor.execute("""
                    SELECT *
                    FROM (
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
                            (SELECT COUNT(*) FROM chat_mensajes m WHERE m.contacto_id = c.id) AS num_mensajes,
                            (SELECT 1 FROM confirmaciones_trabajo ct INNER JOIN aliados a ON a.id = ct.aliado_id WHERE ct.contacto_id = c.id AND TRIM(CAST(a.codigo AS TEXT)) = ?) AS ya_declaraste_importe,
                            COALESCE(
                                (SELECT MAX(m.creado_en) FROM chat_mensajes m WHERE m.contacto_id = c.id),
                                (SELECT MAX(ts) FROM (VALUES (c.fecha_aceptacion), (c.creado_en)) AS refs(ts) WHERE ts IS NOT NULL)
                            ) AS chat_ref
                        FROM contactos_ruana c
                        WHERE (TRIM(COALESCE(c.solicitante_codigo, '')) = ? OR TRIM(COALESCE(c.profesional_codigo, '')) = ?)
                          AND c.estado IN ('iniciado', 'aceptado', 'trabajo_en_progreso', 'importe_en_disputa', 'en_conversacion', 'chat_agotado')
                          AND (
                              (COALESCE(c.posponer_recordatorio, 0) = 0)
                              OR (c.fecha_pospuesto_hasta IS NOT NULL AND c.fecha_pospuesto_hasta <= now())
                          )
                          AND NOT EXISTS (
                              SELECT 1 FROM contacto_panel_oculto o
                              WHERE o.contacto_id = c.id AND TRIM(COALESCE(o.codigo_aliado, '')) = ?
                          )
                    ) abierto
                    WHERE abierto.chat_ref IS NULL OR abierto.chat_ref >= ?
                    ORDER BY CASE WHEN abierto.num_mensajes > 0 THEN 0 ELSE 1 END,
                             abierto.chat_ref DESC,
                             abierto.creado_en DESC
                    """, (codigo_aliado, codigo_aliado, codigo_aliado, codigo_aliado, cutoff))

                    rows = cursor.fetchall()
                    result = []
                    for row in rows:
                        d = dict(row)
                        d['num_mensajes'] = d.get('num_mensajes') or 0
                        d['ya_declaraste_importe'] = d.get('ya_declaraste_importe') is not None
                        result.append(d)
                    return result

                # Referencia de vigencia: último mensaje del chat o, si no hay mensajes, el más reciente de fecha_aceptacion/creado_en
                cursor.execute("""
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
                        (SELECT COUNT(*) FROM chat_mensajes m WHERE m.contacto_id = c.id) AS num_mensajes,
                        (SELECT 1 FROM confirmaciones_trabajo ct INNER JOIN aliados a ON a.id = ct.aliado_id WHERE ct.contacto_id = c.id AND TRIM(CAST(a.codigo AS TEXT)) = ?) AS ya_declaraste_importe
                    FROM contactos_ruana c
                    WHERE (TRIM(COALESCE(c.solicitante_codigo, '')) = ? OR TRIM(COALESCE(c.profesional_codigo, '')) = ?)
                      AND c.estado IN ('iniciado', 'aceptado', 'trabajo_en_progreso', 'importe_en_disputa', 'en_conversacion', 'chat_agotado')
                      AND (
                          (COALESCE(c.posponer_recordatorio, 0) = 0)
                          OR (c.fecha_pospuesto_hasta IS NOT NULL AND datetime(c.fecha_pospuesto_hasta) <= datetime('now'))
                      )
                      AND (
                          COALESCE(
                              (SELECT MAX(m.creado_en) FROM chat_mensajes m WHERE m.contacto_id = c.id),
                              (SELECT MAX(ts) FROM (SELECT c.fecha_aceptacion AS ts UNION ALL SELECT c.creado_en) WHERE ts IS NOT NULL)
                          ) IS NULL
                          OR datetime(COALESCE(
                              (SELECT MAX(m.creado_en) FROM chat_mensajes m WHERE m.contacto_id = c.id),
                              (SELECT MAX(ts) FROM (SELECT c.fecha_aceptacion AS ts UNION ALL SELECT c.creado_en) WHERE ts IS NOT NULL)
                          )) >= datetime('now', ?)
                      )
                      AND NOT EXISTS (
                          SELECT 1 FROM contacto_panel_oculto o
                          WHERE o.contacto_id = c.id AND TRIM(COALESCE(o.codigo_aliado, '')) = ?
                      )
                    ORDER BY CASE WHEN num_mensajes > 0 THEN 0 ELSE 1 END,
                             COALESCE(
                                 (SELECT MAX(m.creado_en) FROM chat_mensajes m WHERE m.contacto_id = c.id),
                                 (SELECT MAX(ts) FROM (SELECT c.fecha_aceptacion AS ts UNION ALL SELECT c.creado_en) WHERE ts IS NOT NULL)
                             ) DESC,
                             c.creado_en DESC
                """, (codigo_aliado, codigo_aliado, codigo_aliado, f'-{horas_vigencia} hours', codigo_aliado))

                rows = cursor.fetchall()
                result = []
                for row in rows:
                    d = dict(row)
                    d['num_mensajes'] = d.get('num_mensajes') or 0
                    d['ya_declaraste_importe'] = d.get('ya_declaraste_importe') is not None
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
                cursor.execute(f"""
                    SELECT
                        id, solicitante_codigo, profesional_codigo, servicio, estado,
                        importe_final, comision, comision_porcentaje, estado_pago, pendiente_pago,
                        fecha_cierre, fecha_no_concretado, creado_en, actualizado_en
                        {apoyo_col}
                        {motivo_col}
                    FROM contactos_ruana
                    WHERE id = ?
                """, (contacto_id,))

                row = cursor.fetchone()
                if not row:
                    return None
                d = dict(row)
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
        scores_aplicar = []
        resultado = {'status': 'error', 'message': 'unknown'}
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
                        if d.get('solicitante_codigo'):
                            scores_aplicar.append(d['solicitante_codigo'])
                        if d.get('profesional_codigo'):
                            scores_aplicar.append(d['profesional_codigo'])
                conn.commit()
                resultado = {'status': 'success', 'conflict_id': conflict_id, 'estado': nuevo_estado,
                             'importe_final': importe_valido}
            except Exception as e:
                resultado = {'status': 'error', 'message': str(e)}
            finally:
                conn.close()
        for codigo in scores_aplicar:
            try:
                self.aplicar_cambio_score(codigo, 8, 'contacto_cerrado_resolucion_admin')
            except Exception:
                pass
        return resultado

    def resolver_conflicto_pago(self, contacto_id: int, importe_valido: float,
                                admin_codigo: str = "") -> Dict[str, Any]:
        """
        Admin resuelve conflicto: define importe valido, se aplica apoyo_pct, cierra contacto, +8 a ambos, audit.
        """
        sol = prof = None
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
                sol = contacto.get('solicitante_codigo')
                prof = contacto.get('profesional_codigo')
            except Exception as e:
                return {'status': 'error', 'message': str(e)}
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

        if sol:
            self.aplicar_cambio_score(sol, 8, 'contacto_cerrado_resolucion_admin')
        if prof:
            self.aplicar_cambio_score(prof, 8, 'contacto_cerrado_resolucion_admin')
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

    def actualizar_estado_pago_contacto(self, contacto_id: int, nuevo_estado: str,
                                        admin_codigo: str = "",
                                        motivo_rechazo: Optional[str] = None) -> Dict[str, Any]:
        """
        Admin actualiza estado_pago de un contacto (trabajo_cerrado con Apoyo RUANA).
        Estados permitidos: en_revision, pagado, rechazado.
        - pagado: pendiente_pago = 0, fecha_validacion_pago y admin_validacion_codigo.
        - rechazado: estado_pago → pendiente_pago, pendiente_pago = 1, motivo_rechazo_pago, comprobante_ruta=NULL;
          motivo_rechazo obligatorio; notifica al profesional.
        """
        nuevo_estado = (nuevo_estado or "").strip().lower()
        if nuevo_estado not in self.ESTADOS_PAGO_PERMITIDOS_ADMIN:
            return {'status': 'error', 'message': f'estado_pago debe ser uno de: {", ".join(self.ESTADOS_PAGO_PERMITIDOS_ADMIN)}'}
        if nuevo_estado == 'rechazado' and not (motivo_rechazo or "").strip():
            return {'status': 'error', 'message': 'El motivo de rechazo es obligatorio'}
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, estado, importe_final, estado_pago, pendiente_pago, profesional_codigo
                    FROM contactos_ruana WHERE id = ?
                """, (contacto_id,))
                row = cursor.fetchone()
                if not row:
                    return {'status': 'error', 'message': 'Contacto no encontrado'}
                r = dict(row)
                if r['estado'] != 'trabajo_cerrado' or r['importe_final'] is None:
                    return {'status': 'error', 'message': 'El contacto no tiene Apoyo RUANA generado'}
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
                return {'status': 'success', 'contacto_id': contacto_id, 'estado_pago': nuevo_estado}
            except Exception as e:
                return {'status': 'error', 'message': str(e)}
            finally:
                conn.close()

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
            score: Score de 0-100
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

    def forzar_suplencia(
        self,
        grupo_id: int,
        oficio: str,
        aliado_original_codigo: str,
        suplente_codigo: str,
        admin_codigo: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Crea manualmente una competencia: suplente compite por la plaza del titular en el grupo.
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
                for cod, label in [(aliado_original_codigo, 'titular'), (suplente_codigo, 'suplente')]:
                    cursor.execute("SELECT 1 FROM aliados WHERE codigo = ?", (cod,))
                    if not cursor.fetchone():
                        return {'status': 'error', 'message': f'Aliado {label} no encontrado'}
                duracion = self._get_duracion_competencia_dias()
                from datetime import timedelta
                fecha_fin = (datetime.now() + timedelta(days=duracion)).strftime('%Y-%m-%d %H:%M:%S')
                cursor.execute("""
                    INSERT INTO competencia (grupo_id, oficio, aliado_original_codigo, suplente_codigo, fecha_fin_prevista, estado)
                    VALUES (?, ?, ?, ?, ?, 'activa')
                """, (grupo_id, oficio_s, aliado_original_codigo, suplente_codigo, fecha_fin))
                conn.commit()
                try:
                    self.registrar_evento_sistema(
                        'forzar_suplencia',
                        f'Competencia forzada: grupo {grupo_id}, oficio {oficio_s}',
                        actor_tipo='admin',
                        metadata={'grupo_id': grupo_id, 'oficio': oficio_s, 'original': aliado_original_codigo, 'suplente': suplente_codigo},
                    )
                except Exception:
                    pass
                return {'status': 'success', 'message': 'Suplencia forzada correctamente', 'competencia_id': cursor.lastrowid}
            except Exception as e:
                return {'status': 'error', 'message': str(e)}
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

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

    def contar_suplentes_activos(self) -> int:
        """Cuenta aliados que están actuando como suplente en una competencia activa."""
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT COUNT(DISTINCT suplente_codigo) FROM competencia WHERE estado = 'activa'"
                )
                return cursor.fetchone()[0] or 0
            except Exception:
                return 0
            finally:
                conn.close()

    def contar_aliados_en_riesgo(self) -> int:
        """Cuenta aliados activos con estado RUANA 'EN RIESGO' (35 <= score < 60)."""
        with self._lock:
            try:
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT COUNT(*) FROM aliados
                    WHERE estado = 'activo' AND score IS NOT NULL
                    AND CAST(score AS INTEGER) >= 35 AND CAST(score AS INTEGER) < 60
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

                # Oficios saturados: oficios con más de X suplentes en competencia activa
                cursor.execute("""
                    SELECT oficio, COUNT(DISTINCT suplente_codigo) as n
                    FROM competencia WHERE estado = 'activa'
                    GROUP BY oficio
                    HAVING COUNT(DISTINCT suplente_codigo) > ?
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
