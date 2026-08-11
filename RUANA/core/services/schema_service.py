"""Servicio de dominio schema (Campamento Base).

Extracción progresiva desde DBManager. Las fachadas permanecen en DBManager.
"""
from __future__ import annotations

from core.db_constants import RUANA_ROOT, ALIADO_FOTO_PERFIL_COLUMN, ESTADOS_GRUPO

import json
import sqlite3
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
from core.db_constants import ALIADO_FOTO_PERFIL_COLUMN, ESTADOS_GRUPO
# --- Extraído de DBManager (schema) ---

def _init_db(db):
    """Inicializa la base de datos con tablas si no existen"""
    with db._lock:
        Path(db.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = db._connect()
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
            db._migrar_grupos_si_procede(conn, cursor)
            db._migrar_grupos_multi_cp_si_procede(conn, cursor)
            db._migrar_aliados_grupo_id(conn, cursor)
            db._migrar_aliados_derrotas_competencia(conn, cursor)
            db._migrar_aliados_especializaciones(conn, cursor)
            db._migrar_aliados_descripcion_servicio(conn, cursor)
            db._migrar_aliados_especializacion_singular(conn, cursor)
            db._migrar_aliados_foto_perfil(conn, cursor)

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

            db._migrar_contactos_comprobante(conn, cursor)
            db._migrar_contactos_apoyo_ruana(conn, cursor)
            db._migrar_contactos_ruana_idx_contacto_aliado(conn, cursor)
            db._migrar_aliados_pago(conn, cursor)
            db._migrar_notificaciones_aliado(conn, cursor)
            db._migrar_centro_comunicacion_ruana(conn, cursor)
            db._migrar_contactos_posponer_recordatorio(conn, cursor)
            db._migrar_contactos_fecha_pospuesto_hasta(conn, cursor)
            db._migrar_chat_mensajes(conn, cursor)
            db._migrar_negociacion_guiada(conn, cursor)
            db._migrar_acuerdo_cierre_bilateral(conn, cursor)
            db._migrar_importe_acordado(conn, cursor)
            db._migrar_contactos_motivo_contacto(conn, cursor)
            db._migrar_contactos_es_urgente(conn, cursor)
            db._migrar_drop_chat_messages(conn, cursor)
            db._migrar_competencia_scores(conn, cursor)
            db._migrar_payment_conflicts(conn, cursor)
            db._migrar_contactos_validacion_pago(conn, cursor)
            db._migrar_solicitudes_unificado(conn, cursor)
            db._migrar_contacto_panel_oculto(conn, cursor)
            db._migrar_referidos_origen(conn, cursor)
            db._migrar_invitaciones_oficio_codigo_referido(conn, cursor)
            db._migrar_aliados_invitado_por(conn, cursor)
            db._migrar_invitaciones_solicitud_id(conn, cursor)
            db._migrar_solicitudes_candidato(conn, cursor)
            db._migrar_aliado_accesos_dia(conn, cursor)
            db._migrar_datos_plaza_oficio(conn, cursor)
            db._migrar_drop_especializaciones(conn, cursor)
            db._migrar_retador_rename(conn, cursor)
            db._migrar_competencia_permanencia(conn, cursor)
            db._migrar_aliados_eliminados(conn, cursor)

            conn.commit()
            print(f"[RUANA][DB] Base de datos inicializada en: {db.db_path}")
            
        except Exception as e:
            print(f"[RUANA][DB] Error inicializando BD: {e}")
            conn.rollback()
            raise
        finally:
            conn.close()

def _migrar_grupos_si_procede(db, conn, cursor) -> None:
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
        nombre = db._generar_nombre_grupo(cursor)
        cursor.execute("UPDATE grupos SET nombre = ?, estado = COALESCE(estado, 'activo') WHERE id = ?", (nombre, gid))

def _migrar_grupos_multi_cp_si_procede(db, conn, cursor) -> None:
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

def _migrar_aliados_grupo_id(db, conn, cursor) -> None:
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

def _migrar_aliados_derrotas_competencia(db, conn, cursor) -> None:
    """Añade derrotas_competencia a aliados (solo derrotas en competencia cuentan; expulsión en 2ª)."""
    cursor.execute("PRAGMA table_info(aliados)")
    columnas = [row[1] for row in cursor.fetchall()]
    if 'derrotas_competencia' in columnas:
        return
    cursor.execute("ALTER TABLE aliados ADD COLUMN derrotas_competencia INTEGER DEFAULT 0")

def _migrar_aliados_especializaciones(db, conn, cursor) -> None:
    """Añade especializaciones (JSON array de oficios del catálogo; no ocupan plaza en grupo)."""
    cursor.execute("PRAGMA table_info(aliados)")
    columnas = [row[1] for row in cursor.fetchall()]
    if 'especializaciones' in columnas:
        return
    cursor.execute("ALTER TABLE aliados ADD COLUMN especializaciones TEXT")

def _migrar_aliados_descripcion_servicio(db, conn, cursor) -> None:
    """Añade descripcion_servicio (texto que el aliado escribe al registrarse o completa después)."""
    cursor.execute("PRAGMA table_info(aliados)")
    columnas = [row[1] for row in cursor.fetchall()]
    if 'descripcion_servicio' in columnas:
        return
    cursor.execute("ALTER TABLE aliados ADD COLUMN descripcion_servicio TEXT")

def _migrar_aliados_foto_perfil(db, conn, cursor) -> None:
    """Añade foto_perfil_url (foto pública del aliado, editable solo por el propio aliado)."""
    col = ALIADO_FOTO_PERFIL_COLUMN
    cursor.execute("PRAGMA table_info(aliados)")
    columnas = [row[1] for row in cursor.fetchall()]
    if col in columnas:
        return
    cursor.execute(f"ALTER TABLE aliados ADD COLUMN {col} TEXT")

def _migrar_aliados_especializacion_singular(db, conn, cursor) -> None:
    """Añade especializacion (una plaza por especialización por grupo; sub-oficio elegido)."""
    cursor.execute("PRAGMA table_info(aliados)")
    columnas = [row[1] for row in cursor.fetchall()]
    if 'especializacion' in columnas:
        return
    cursor.execute("ALTER TABLE aliados ADD COLUMN especializacion TEXT")

def _migrar_contactos_comprobante(db, conn, cursor) -> None:
    """Añade comprobante_ruta a contactos_ruana para conflictos de pago."""
    cursor.execute("PRAGMA table_info(contactos_ruana)")
    columnas = [row[1] for row in cursor.fetchall()]
    if 'comprobante_ruta' in columnas:
        return
    cursor.execute("ALTER TABLE contactos_ruana ADD COLUMN comprobante_ruta TEXT")

def _migrar_contactos_apoyo_ruana(db, conn, cursor) -> None:
    """Añade apoyo_ruana a contactos_ruana (importe Apoyo RUANA % por trabajo cerrado, config apoyo_pct)."""
    cursor.execute("PRAGMA table_info(contactos_ruana)")
    columnas = [row[1] for row in cursor.fetchall()]
    if 'apoyo_ruana' in columnas:
        return
    cursor.execute("ALTER TABLE contactos_ruana ADD COLUMN apoyo_ruana REAL")

def _migrar_contactos_ruana_idx_contacto_aliado(db, conn, cursor) -> None:
    """Índice para búsquedas por contacto y aliado (profesional que abona el apoyo)."""
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_contacto_aliado'"
    )
    if cursor.fetchone():
        return
    cursor.execute(
        "CREATE INDEX idx_contacto_aliado ON contactos_ruana(id, profesional_codigo)"
    )

def _migrar_aliados_pago(db, conn, cursor) -> None:
    """Añade qr_paypal_path y bizum_num a aliados para notificaciones de Apoyo RUANA."""
    cursor.execute("PRAGMA table_info(aliados)")
    columnas = [row[1] for row in cursor.fetchall()]
    if 'qr_paypal_path' not in columnas:
        cursor.execute("ALTER TABLE aliados ADD COLUMN qr_paypal_path TEXT")
    if 'bizum_num' not in columnas:
        cursor.execute("ALTER TABLE aliados ADD COLUMN bizum_num TEXT")

def _migrar_notificaciones_aliado(db, conn, cursor) -> None:
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

def _migrar_centro_comunicacion_ruana(db, conn, cursor) -> None:
    """Centro de comunicación entre aliados y equipo RUANA."""
    id_conv = "SERIAL PRIMARY KEY" if db.backend == "postgres" else "INTEGER PRIMARY KEY AUTOINCREMENT"
    id_msg = "SERIAL PRIMARY KEY" if db.backend == "postgres" else "INTEGER PRIMARY KEY AUTOINCREMENT"
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

def _migrar_contactos_posponer_recordatorio(db, conn, cursor) -> None:
    """Añade posponer_recordatorio para 'Sigue en conversación' (ocultar alerta en sesión)."""
    cursor.execute("PRAGMA table_info(contactos_ruana)")
    columnas = [row[1] for row in cursor.fetchall()]
    if 'posponer_recordatorio' in columnas:
        return
    cursor.execute("ALTER TABLE contactos_ruana ADD COLUMN posponer_recordatorio INTEGER DEFAULT 0")

def _migrar_contactos_fecha_pospuesto_hasta(db, conn, cursor) -> None:
    """Añade fecha_pospuesto_hasta: hasta cuándo la alerta queda oculta (límite temporal)."""
    cursor.execute("PRAGMA table_info(contactos_ruana)")
    columnas = [row[1] for row in cursor.fetchall()]
    if 'fecha_pospuesto_hasta' in columnas:
        return
    cursor.execute("ALTER TABLE contactos_ruana ADD COLUMN fecha_pospuesto_hasta TIMESTAMP")

def _migrar_chat_mensajes(db, conn, cursor) -> None:
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

def _migrar_negociacion_guiada(db, conn, cursor) -> None:
    """Tabla de eventos y columna negociacion_json para negociación guiada (sustituye chat libre)."""
    id_col = "SERIAL PRIMARY KEY" if db.backend == "postgres" else "INTEGER PRIMARY KEY AUTOINCREMENT"
    if db.backend == "postgres":
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

def _migrar_acuerdo_cierre_bilateral(db, conn, cursor) -> None:
    """
    Columnas para snapshot del acuerdo, confirmación bilateral de cierre
    y dismiss del resumen flotante por cada parte.
    """
    columnas_nuevas = [
        ('acuerdo_resumen_json', 'TEXT', 'JSONB'),
        ('acuerdo_alcanzado_en', 'TIMESTAMP', 'TIMESTAMP'),
        ('cierre_confirmado_solicitante_en', 'TIMESTAMP', 'TIMESTAMP'),
        ('cierre_confirmado_profesional_en', 'TIMESTAMP', 'TIMESTAMP'),
        ('resumen_dismiss_solicitante_en', 'TIMESTAMP', 'TIMESTAMP'),
        ('resumen_dismiss_profesional_en', 'TIMESTAMP', 'TIMESTAMP'),
    ]
    if db.backend == "postgres":
        for nombre, _sqlite_t, pg_t in columnas_nuevas:
            cursor.execute(
                f"ALTER TABLE contactos_ruana ADD COLUMN IF NOT EXISTS {nombre} {pg_t}"
            )
        return
    cursor.execute("PRAGMA table_info(contactos_ruana)")
    columnas = [row[1] for row in cursor.fetchall()]
    for nombre, sqlite_t, _pg_t in columnas_nuevas:
        if nombre not in columnas:
            cursor.execute(f"ALTER TABLE contactos_ruana ADD COLUMN {nombre} {sqlite_t}")

def _migrar_importe_acordado(db, conn, cursor) -> None:
    """Importe oficial del encargo = precio confirmado en la negociación."""
    if db.backend == "postgres":
        cursor.execute(
            "ALTER TABLE contactos_ruana ADD COLUMN IF NOT EXISTS importe_acordado REAL"
        )
        return
    cursor.execute("PRAGMA table_info(contactos_ruana)")
    columnas = [row[1] for row in cursor.fetchall()]
    if 'importe_acordado' not in columnas:
        cursor.execute("ALTER TABLE contactos_ruana ADD COLUMN importe_acordado REAL")

def _migrar_contactos_motivo_contacto(db, conn, cursor) -> None:
    """Añade motivo_contacto al contacto (obligatorio antes de iniciar chat)."""
    cursor.execute("PRAGMA table_info(contactos_ruana)")
    columnas = [row[1] for row in cursor.fetchall()]
    if 'motivo_contacto' in columnas:
        return
    cursor.execute("ALTER TABLE contactos_ruana ADD COLUMN motivo_contacto TEXT")

def _migrar_contactos_es_urgente(db, conn, cursor) -> None:
    """Añade es_urgente y urgente_marcado_en (solo al iniciar chat, Regla 6)."""
    if db.backend == "postgres":
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

def _migrar_aliado_accesos_dia(db, conn, cursor) -> None:
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

def _migrar_drop_chat_messages(db, conn, cursor) -> None:
    """Elimina la tabla redundante chat_messages. Admin lee desde chat_mensajes + JOIN aliados."""
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='chat_messages'")
    if cursor.fetchone():
        cursor.execute("DROP TABLE IF EXISTS chat_messages")

def _migrar_payment_conflicts(db, conn, cursor) -> None:
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

def _migrar_contactos_validacion_pago(db, conn, cursor) -> None:
    """Añade fecha_validacion_pago, admin_validacion_codigo y motivo_rechazo_pago a contactos_ruana."""
    cursor.execute("PRAGMA table_info(contactos_ruana)")
    columnas = [row[1] for row in cursor.fetchall()]
    if 'fecha_validacion_pago' not in columnas:
        cursor.execute("ALTER TABLE contactos_ruana ADD COLUMN fecha_validacion_pago TIMESTAMP")
    if 'admin_validacion_codigo' not in columnas:
        cursor.execute("ALTER TABLE contactos_ruana ADD COLUMN admin_validacion_codigo TEXT")
    if 'motivo_rechazo_pago' not in columnas:
        cursor.execute("ALTER TABLE contactos_ruana ADD COLUMN motivo_rechazo_pago TEXT")

def _migrar_solicitudes_unificado(db, conn, cursor) -> None:
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

def _migrar_contacto_panel_oculto(db, conn, cursor) -> None:
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

def _migrar_competencia_scores(db, conn, cursor) -> None:
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

def _migrar_retador_rename(db, conn, cursor) -> None:
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

def _migrar_competencia_permanencia(db, conn, cursor) -> None:
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

def _migrar_datos_plaza_oficio(db, conn, cursor) -> None:
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
                    nombre = db._generar_nombre_grupo(cursor)
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

def _migrar_drop_especializaciones(db, conn, cursor) -> None:
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

def _migrar_referidos_origen(db, conn, cursor) -> None:
    """Añade columna origen a referidos (trazabilidad del vínculo invitador→referido)."""
    cursor.execute("PRAGMA table_info(referidos)")
    columnas = [row[1] for row in cursor.fetchall()]
    if 'origen' not in columnas:
        cursor.execute("ALTER TABLE referidos ADD COLUMN origen TEXT DEFAULT ''")

def _migrar_invitaciones_oficio_codigo_referido(db, conn, cursor) -> None:
    """Añade codigo_referido a invitaciones_oficio para backfill del árbol."""
    cursor.execute("PRAGMA table_info(invitaciones_oficio)")
    columnas = [row[1] for row in cursor.fetchall()]
    if 'codigo_referido' not in columnas:
        cursor.execute("ALTER TABLE invitaciones_oficio ADD COLUMN codigo_referido TEXT DEFAULT ''")

def _migrar_aliados_invitado_por(db, conn, cursor) -> None:
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

def _migrar_invitaciones_solicitud_id(db, conn, cursor) -> None:
    """Vincula invitaciones «Conozco a alguien» con la solicitud de origen."""
    try:
        if db.backend == "postgres":
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

def _migrar_solicitudes_candidato(db, conn, cursor) -> None:
    """Campos para candidato pendiente e incorporación del aliado invitado."""
    try:
        if db.backend == "postgres":
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

def _migrar_aliados_eliminados(db, conn, cursor) -> None:
    """Tabla de archivo: un único registro por aliado eliminado definitivamente."""
    id_col = "SERIAL PRIMARY KEY" if db.backend == "postgres" else "INTEGER PRIMARY KEY AUTOINCREMENT"
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS aliados_eliminados (
            id {id_col},
            codigo TEXT NOT NULL,
            nombre TEXT,
            marca TEXT,
            oficio TEXT,
            codigo_postal TEXT,
            email TEXT,
            telefono TEXT,
            estado_anterior TEXT,
            motivo TEXT,
            admin_codigo TEXT,
            eliminado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_aliados_eliminados_codigo ON aliados_eliminados(codigo)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_aliados_eliminados_fecha ON aliados_eliminados(eliminado_en DESC)"
    )

