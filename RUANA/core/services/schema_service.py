"""Servicio de dominio schema (Campamento Base).

Extracción progresiva desde DBManager. Las fachadas permanecen en DBManager.
Helpers PRAGMA/execute vía SchemaRepo; DDL y migraciones multi-paso permanecen
aquí (riesgo alto de romper el orden de migraciones si se mueven al repo).
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

from core.repositories.schema_repo import SchemaRepo

_repo = SchemaRepo()

# --- Extraído de DBManager (schema) ---
# NOTA: el DDL de _init_db y las migraciones *_si_procede se ejecutan vía
# _repo.execute / helpers de pragma; no se reubica el SQL de migración completo.

def _init_db(db):
    """Inicializa la base de datos con tablas si no existen"""
    with db._lock:
        Path(db.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = db._connect()
        cursor = conn.cursor()
        
        try:
            # Tabla de control de migraciones (para migraciones que se ejecutan una sola vez)
            _repo.execute(cursor, """
                CREATE TABLE IF NOT EXISTS migraciones (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nombre TEXT UNIQUE NOT NULL,
                    aplicada_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Tabla de aliados (grupo_id se añade por migración; ver _migrar_aliados_grupo_id)
            _repo.execute(cursor, """
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
            _repo.execute(cursor, """
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
            db._migrar_grupos_nombre_unique_si_procede(conn, cursor)
            db._migrar_aliados_grupo_id(conn, cursor)
            db._migrar_aliados_derrotas_competencia(conn, cursor)
            db._migrar_aliados_especializaciones(conn, cursor)
            db._migrar_aliados_descripcion_servicio(conn, cursor)
            db._migrar_aliados_especializacion_singular(conn, cursor)
            db._migrar_aliados_foto_perfil(conn, cursor)

            # Tabla de solicitudes (schema unificado aplicado por _migrar_solicitudes_unificado)
            _repo.execute(cursor, """
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
            _repo.execute(cursor, """
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
                    comision_porcentaje REAL DEFAULT 0.12, -- sincronizar con apoyo_pct en config/ruana_reglas_v1.json (12% → 0.12); inserts vía pago_service usan _get_apoyo_pct()
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
            _repo.execute(cursor, """
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
            _repo.execute(cursor, """
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
            _repo.execute(cursor, "CREATE INDEX IF NOT EXISTS idx_aliados_codigo ON aliados(codigo)")
            _repo.execute(cursor, "CREATE INDEX IF NOT EXISTS idx_aliados_postal ON aliados(codigo_postal)")
            _repo.execute(cursor, "CREATE INDEX IF NOT EXISTS idx_grupos_nombre ON grupos(nombre)")
            _repo.execute(cursor, "CREATE INDEX IF NOT EXISTS idx_solicitudes_grupo ON solicitudes(grupo_id)")
            _repo.execute(cursor, "CREATE INDEX IF NOT EXISTS idx_solicitudes_codigo ON solicitudes(creado_por_codigo)")
            _repo.execute(cursor, "CREATE INDEX IF NOT EXISTS idx_contactos_profesional ON contactos_ruana(profesional_codigo)")
            _repo.execute(cursor, "CREATE INDEX IF NOT EXISTS idx_contactos_estado ON contactos_ruana(estado)")
            _repo.execute(cursor, "CREATE INDEX IF NOT EXISTS idx_contactos_pendiente ON contactos_ruana(pendiente_resolucion)")
            _repo.execute(cursor, "CREATE INDEX IF NOT EXISTS idx_evaluaciones_codigo ON evaluaciones(codigo_aliado)")
            _repo.execute(cursor, "CREATE INDEX IF NOT EXISTS idx_evaluaciones_historico_codigo ON evaluaciones_historico(codigo_aliado)")
            
            # Score RUANA: movimientos para límite ±10/día y auditoría
            _repo.execute(cursor, """
                CREATE TABLE IF NOT EXISTS score_movimientos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    codigo_aliado TEXT NOT NULL,
                    delta INTEGER NOT NULL,
                    motivo TEXT,
                    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(codigo_aliado) REFERENCES aliados(codigo)
                )
            """)
            _repo.execute(cursor, "CREATE INDEX IF NOT EXISTS idx_score_movimientos_codigo ON score_movimientos(codigo_aliado)")
            _repo.execute(cursor, "CREATE INDEX IF NOT EXISTS idx_score_movimientos_creado ON score_movimientos(creado_en)")
            
            # Penalizaciones por contacto abierto ya aplicadas (7d / 21d)
            _repo.execute(cursor, """
                CREATE TABLE IF NOT EXISTS contacto_penalizaciones_aplicadas (
                    contacto_id INTEGER NOT NULL,
                    tipo TEXT NOT NULL,
                    aplicado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY(contacto_id, tipo),
                    FOREIGN KEY(contacto_id) REFERENCES contactos_ruana(id)
                )
            """)
            
            # Invitaciones: quién invitó a cada código (para recompensa +3 al referir)
            _repo.execute(cursor, """
                CREATE TABLE IF NOT EXISTS invitaciones (
                    codigo TEXT PRIMARY KEY,
                    invitador_aliado_id INTEGER NOT NULL,
                    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    usado INTEGER DEFAULT 0,
                    FOREIGN KEY(invitador_aliado_id) REFERENCES aliados(id)
                )
            """)
            _repo.execute(cursor, """
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
            _repo.execute(cursor, "CREATE INDEX IF NOT EXISTS idx_catalogo_servicios_codigo ON catalogo_servicios_aliado(aliado_codigo)")
            _repo.execute(cursor, """
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
            _repo.execute(cursor, """
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
            _repo.execute(cursor, """
                CREATE TABLE IF NOT EXISTS referidos (
                    codigo_referido TEXT NOT NULL,
                    codigo_invitador TEXT NOT NULL,
                    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY(codigo_referido),
                    FOREIGN KEY(codigo_invitador) REFERENCES aliados(codigo)
                )
            """)

            # Invitaciones por oficio: códigos para invitar a profesionales de oficios faltantes en el grupo
            _repo.execute(cursor, """
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
            _repo.execute(cursor, """
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
            _repo.execute(cursor, "CREATE INDEX IF NOT EXISTS idx_eventos_sistema_creado ON eventos_sistema(creado_en DESC)")

            # Competencia: retador temporal cuando score < umbral; 1 mes, mayor score permanece
            _repo.execute(cursor, """
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
            _repo.execute(cursor, "CREATE INDEX IF NOT EXISTS idx_competencia_grupo_estado ON competencia(grupo_id, estado)")
            _repo.execute(cursor, "CREATE INDEX IF NOT EXISTS idx_competencia_fin ON competencia(fecha_fin_prevista, estado)")

            # Avisos al grupo (ej. "Este mes tenemos X en competencia dentro del grupo")
            _repo.execute(cursor, """
                CREATE TABLE IF NOT EXISTS avisos_grupo (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    grupo_id INTEGER NOT NULL,
                    tipo TEXT NOT NULL,
                    texto TEXT NOT NULL,
                    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(grupo_id) REFERENCES grupos(id)
                )
            """)
            _repo.execute(cursor, "CREATE INDEX IF NOT EXISTS idx_avisos_grupo ON avisos_grupo(grupo_id)")

            # Plaza cerrada por admin (grupo + oficio): Cerrar Oficio / Abrir Plaza
            _repo.execute(cursor, """
                CREATE TABLE IF NOT EXISTS grupo_oficio_cerrado (
                    grupo_id INTEGER NOT NULL,
                    oficio TEXT NOT NULL,
                    cerrado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (grupo_id, oficio),
                    FOREIGN KEY (grupo_id) REFERENCES grupos(id)
                )
            """)

            # Confirmaciones de trabajo: una fila por declaración (evita doble declaración por aliado)
            _repo.execute(cursor, """
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
            _repo.execute(cursor, "CREATE INDEX IF NOT EXISTS idx_confirmaciones_contacto ON confirmaciones_trabajo(contacto_id)")

            # Ingresos RUANA: apoyo configurado cuando contacto se cierra con importes coincidentes.
            _repo.execute(cursor, """
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
            _repo.execute(cursor, """
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
            _repo.execute(cursor, "CREATE INDEX IF NOT EXISTS idx_audit_log_entidad ON audit_log(entidad, entidad_id)")

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
            db._migrar_aliados_pin_personal(conn, cursor)
            db._migrar_invitaciones_solicitud_id(conn, cursor)
            db._migrar_invitaciones_crecimiento_grupo(conn, cursor)
            db._migrar_grupo_crecimiento_recompensas(conn, cursor)
            db._migrar_solicitudes_candidato(conn, cursor)
            db._migrar_solicitudes_semanales(conn, cursor)
            db._migrar_aliado_accesos_dia(conn, cursor)
            db._migrar_datos_plaza_oficio(conn, cursor)
            db._migrar_drop_especializaciones(conn, cursor)
            db._migrar_retador_rename(conn, cursor)
            db._migrar_competencia_permanencia(conn, cursor)
            db._migrar_aliados_eliminados(conn, cursor)
            db._migrar_privacidad_rgpd_aliado(conn, cursor)
            db._migrar_stripe_pagos(conn, cursor)
            db._migrar_estado_financiero(conn, cursor)
            db._migrar_financial_fase02(conn, cursor)
            db._migrar_financial_fase03(conn, cursor)
            db._migrar_financial_fase03_1(conn, cursor)
            db._migrar_financial_fase03_2(conn, cursor)
            db._migrar_financial_fase04_conflicts(conn, cursor)
            db._migrar_financial_fase05_refunds(conn, cursor)
            db._migrar_financial_fase06_disputes(conn, cursor)
            db._migrar_financial_fase07_reconciliation(conn, cursor)
            db._migrar_financial_fase08_ledger(conn, cursor)
            db._migrar_financial_fase09_admin_panel(conn, cursor)
            db._migrar_financial_fase10_security(conn, cursor)
            db._migrar_financial_fase11_automation(conn, cursor)
            db._migrar_financial_fase13_p0_ledger_immutability(conn, cursor)

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
    columnas = _repo.columnas_tabla(cursor, "grupos")
    # Añadir cada columna del nuevo esquema si falta (SQLite: ADD COLUMN solo con constantes)
    for col, def_sql in [
        ('nombre', 'TEXT'),
        ('ciudad', 'TEXT'),
        ('provincia', 'TEXT'),
        ('estado', 'TEXT'),
        ('fecha_creacion', 'TIMESTAMP'),
    ]:
        if col not in columnas:
            _repo.execute(cursor, f"ALTER TABLE grupos ADD COLUMN {col} {def_sql}")
            columnas.append(col)
    _repo.execute(cursor, "UPDATE grupos SET estado = COALESCE(estado, 'activo') WHERE estado IS NULL OR estado = ''")
    if 'creado_en' in columnas:
        _repo.execute(cursor, "UPDATE grupos SET fecha_creacion = creado_en WHERE creado_en IS NOT NULL AND (fecha_creacion IS NULL OR fecha_creacion = '')")
    _repo.execute(cursor, "UPDATE grupos SET fecha_creacion = datetime('now') WHERE fecha_creacion IS NULL OR fecha_creacion = ''")
    # Rellenar nombre único para cada fila que no lo tenga
    _repo.execute(cursor, "SELECT id FROM grupos WHERE nombre IS NULL OR nombre = ''")
    for (gid,) in cursor.fetchall():
        nombre = db._generar_nombre_grupo(cursor)
        _repo.execute(cursor, "UPDATE grupos SET nombre = ?, estado = COALESCE(estado, 'activo') WHERE id = ?", (nombre, gid))

def _migrar_grupos_multi_cp_si_procede(db, conn, cursor) -> None:
    """Permite varios grupos por mismo código postal (máx. MAX_GRUPOS_POR_CP). Se ejecuta una sola vez."""
    if _repo.migracion_aplicada(cursor, 'grupos_multi_cp'):
        return
    _repo.foreign_keys_off(cursor)
    try:
        _repo.execute(cursor, """
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
        _repo.execute(cursor, """
            INSERT INTO grupos_new (id, nombre, codigo_postal, ciudad, provincia, estado, fecha_creacion)
            SELECT id, nombre, codigo_postal, ciudad, provincia, estado, fecha_creacion FROM grupos
        """)
        _repo.execute(cursor, "DROP TABLE grupos")
        _repo.execute(cursor, "ALTER TABLE grupos_new RENAME TO grupos")
        _repo.registrar_migracion(cursor, 'grupos_multi_cp')
    finally:
        _repo.foreign_keys_on(cursor)

def _migrar_grupos_nombre_unique_si_procede(db, conn, cursor) -> None:
    """
    Garantiza unicidad global de grupos.nombre: corrige duplicados legacy y crea índice UNIQUE.
    Los nombres de grupos disueltos no se reutilizan (comparación sobre toda la tabla).
    """
    if _repo.migracion_aplicada(cursor, 'grupos_nombre_unique_v1'):
        return
    cursor.execute(
        "SELECT TRIM(nombre) AS n, COUNT(*) AS c FROM grupos "
        "WHERE nombre IS NOT NULL AND TRIM(nombre) != '' GROUP BY TRIM(nombre) COLLATE NOCASE HAVING c > 1"
    )
    for row in cursor.fetchall():
        dup_name = row[0]
        cursor.execute(
            "SELECT id FROM grupos WHERE TRIM(nombre) = ? COLLATE NOCASE ORDER BY id",
            (dup_name,),
        )
        ids = [r[0] for r in cursor.fetchall()]
        for gid in ids[1:]:
            nuevo = db._generar_nombre_grupo(cursor)
            _repo.execute(cursor, "UPDATE grupos SET nombre = ? WHERE id = ?", (nuevo, gid))
    try:
        _repo.execute(
            cursor,
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_grupos_nombre_unique ON grupos(nombre COLLATE NOCASE)",
        )
    except Exception as ex:
        print(f"[RUANA][DB] Aviso al crear índice único grupos.nombre: {ex}")
    _repo.registrar_migracion(cursor, 'grupos_nombre_unique_v1')

def _migrar_aliados_grupo_id(db, conn, cursor) -> None:
    """Añade grupo_id a aliados si falta y rellena con el primer grupo activo del CP."""
    columnas = _repo.columnas_tabla(cursor, "aliados")
    if 'grupo_id' in columnas:
        return
    _repo.execute(cursor, "ALTER TABLE aliados ADD COLUMN grupo_id INTEGER REFERENCES grupos(id)")
    _repo.execute(cursor, """
        UPDATE aliados SET grupo_id = (
            SELECT g.id FROM grupos g
            WHERE g.codigo_postal = aliados.codigo_postal AND g.estado = 'activo'
            ORDER BY g.id LIMIT 1
        ) WHERE aliados.codigo_postal IS NOT NULL AND aliados.codigo_postal != ''
    """)

def _migrar_aliados_derrotas_competencia(db, conn, cursor) -> None:
    """Añade derrotas_competencia a aliados (solo derrotas en competencia cuentan; expulsión en 2ª)."""
    columnas = _repo.columnas_tabla(cursor, "aliados")
    if 'derrotas_competencia' in columnas:
        return
    _repo.execute(cursor, "ALTER TABLE aliados ADD COLUMN derrotas_competencia INTEGER DEFAULT 0")

def _migrar_aliados_especializaciones(db, conn, cursor) -> None:
    """Añade especializaciones (JSON array de oficios del catálogo; no ocupan plaza en grupo)."""
    columnas = _repo.columnas_tabla(cursor, "aliados")
    if 'especializaciones' in columnas:
        return
    _repo.execute(cursor, "ALTER TABLE aliados ADD COLUMN especializaciones TEXT")

def _migrar_aliados_descripcion_servicio(db, conn, cursor) -> None:
    """Añade descripcion_servicio (texto que el aliado escribe al registrarse o completa después)."""
    columnas = _repo.columnas_tabla(cursor, "aliados")
    if 'descripcion_servicio' in columnas:
        return
    _repo.execute(cursor, "ALTER TABLE aliados ADD COLUMN descripcion_servicio TEXT")

def _migrar_aliados_foto_perfil(db, conn, cursor) -> None:
    """Añade foto_perfil_url (foto pública del aliado, editable solo por el propio aliado)."""
    col = ALIADO_FOTO_PERFIL_COLUMN
    if db.backend == "postgres":
        _repo.execute(cursor, f"ALTER TABLE aliados ADD COLUMN IF NOT EXISTS {col} TEXT")
        return
    columnas = _repo.columnas_tabla(cursor, "aliados")
    if col in columnas:
        return
    _repo.execute(cursor, f"ALTER TABLE aliados ADD COLUMN {col} TEXT")

def _migrar_aliados_especializacion_singular(db, conn, cursor) -> None:
    """Añade especializacion (una plaza por especialización por grupo; sub-oficio elegido)."""
    columnas = _repo.columnas_tabla(cursor, "aliados")
    if 'especializacion' in columnas:
        return
    _repo.execute(cursor, "ALTER TABLE aliados ADD COLUMN especializacion TEXT")

def _migrar_contactos_comprobante(db, conn, cursor) -> None:
    """Añade comprobante_ruta a contactos_ruana para conflictos de pago."""
    columnas = _repo.columnas_tabla(cursor, "contactos_ruana")
    if 'comprobante_ruta' in columnas:
        return
    _repo.execute(cursor, "ALTER TABLE contactos_ruana ADD COLUMN comprobante_ruta TEXT")

def _migrar_contactos_apoyo_ruana(db, conn, cursor) -> None:
    """Añade apoyo_ruana a contactos_ruana (importe Apoyo RUANA % por trabajo cerrado, config apoyo_pct)."""
    columnas = _repo.columnas_tabla(cursor, "contactos_ruana")
    if 'apoyo_ruana' in columnas:
        return
    _repo.execute(cursor, "ALTER TABLE contactos_ruana ADD COLUMN apoyo_ruana REAL")

def _migrar_contactos_ruana_idx_contacto_aliado(db, conn, cursor) -> None:
    """Índice para búsquedas por contacto y aliado (profesional que abona el apoyo)."""
    _repo.execute(cursor, 
        "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_contacto_aliado'"
    )
    if cursor.fetchone():
        return
    _repo.execute(cursor, 
        "CREATE INDEX idx_contacto_aliado ON contactos_ruana(id, profesional_codigo)"
    )

def _migrar_aliados_pago(db, conn, cursor) -> None:
    """Añade qr_paypal_path y bizum_num a aliados para notificaciones de Apoyo RUANA."""
    columnas = _repo.columnas_tabla(cursor, "aliados")
    if 'qr_paypal_path' not in columnas:
        _repo.execute(cursor, "ALTER TABLE aliados ADD COLUMN qr_paypal_path TEXT")
    if 'bizum_num' not in columnas:
        _repo.execute(cursor, "ALTER TABLE aliados ADD COLUMN bizum_num TEXT")

def _migrar_notificaciones_aliado(db, conn, cursor) -> None:
    """Tabla de notificaciones al aliado (ej. Apoyo RUANA generado, con QR/Bizum)."""
    _repo.execute(cursor, 
        "SELECT name FROM sqlite_master WHERE type='table' AND name='notificaciones_aliado'"
    )
    if cursor.fetchone():
        return
    _repo.execute(cursor, """
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
    _repo.execute(cursor, 
        "CREATE INDEX IF NOT EXISTS idx_notificaciones_aliado_codigo ON notificaciones_aliado(aliado_codigo)"
    )
    _repo.execute(cursor, 
        "CREATE INDEX IF NOT EXISTS idx_notificaciones_aliado_creado ON notificaciones_aliado(creado_en DESC)"
    )

def _migrar_centro_comunicacion_ruana(db, conn, cursor) -> None:
    """Centro de comunicación entre aliados y equipo RUANA."""
    id_conv = "SERIAL PRIMARY KEY" if db.backend == "postgres" else "INTEGER PRIMARY KEY AUTOINCREMENT"
    id_msg = "SERIAL PRIMARY KEY" if db.backend == "postgres" else "INTEGER PRIMARY KEY AUTOINCREMENT"
    _repo.execute(cursor, """
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
    _repo.execute(cursor, """
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
    _repo.execute(cursor, "CREATE INDEX IF NOT EXISTS idx_soporte_conv_aliado ON ruana_soporte_conversaciones(aliado_codigo)")
    _repo.execute(cursor, "CREATE INDEX IF NOT EXISTS idx_soporte_conv_estado ON ruana_soporte_conversaciones(estado)")
    _repo.execute(cursor, "CREATE INDEX IF NOT EXISTS idx_soporte_conv_ultimo ON ruana_soporte_conversaciones(ultimo_mensaje_en DESC)")
    _repo.execute(cursor, "CREATE INDEX IF NOT EXISTS idx_soporte_msg_conv ON ruana_soporte_mensajes(conversacion_id)")
    _repo.execute(cursor, "CREATE INDEX IF NOT EXISTS idx_soporte_msg_fecha ON ruana_soporte_mensajes(creado_en DESC)")

def _migrar_contactos_posponer_recordatorio(db, conn, cursor) -> None:
    """Añade posponer_recordatorio para 'Sigue en conversación' (ocultar alerta en sesión)."""
    columnas = _repo.columnas_tabla(cursor, "contactos_ruana")
    if 'posponer_recordatorio' in columnas:
        return
    _repo.execute(cursor, "ALTER TABLE contactos_ruana ADD COLUMN posponer_recordatorio INTEGER DEFAULT 0")

def _migrar_contactos_fecha_pospuesto_hasta(db, conn, cursor) -> None:
    """Añade fecha_pospuesto_hasta: hasta cuándo la alerta queda oculta (límite temporal)."""
    columnas = _repo.columnas_tabla(cursor, "contactos_ruana")
    if 'fecha_pospuesto_hasta' in columnas:
        return
    _repo.execute(cursor, "ALTER TABLE contactos_ruana ADD COLUMN fecha_pospuesto_hasta TIMESTAMP")

def _migrar_chat_mensajes(db, conn, cursor) -> None:
    """Crea la tabla chat_mensajes para el chat interno RUANA entre solicitante y profesional."""
    _repo.execute(cursor, """
        CREATE TABLE IF NOT EXISTS chat_mensajes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contacto_id INTEGER NOT NULL,
            emisor_codigo TEXT NOT NULL,
            texto TEXT NOT NULL,
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(contacto_id) REFERENCES contactos_ruana(id)
        )
    """)
    _repo.execute(cursor, "CREATE INDEX IF NOT EXISTS idx_chat_mensajes_contacto ON chat_mensajes(contacto_id)")

def _migrar_negociacion_guiada(db, conn, cursor) -> None:
    """Tabla de eventos y columna negociacion_json para negociación guiada (sustituye chat libre)."""
    id_col = "SERIAL PRIMARY KEY" if db.backend == "postgres" else "INTEGER PRIMARY KEY AUTOINCREMENT"
    if db.backend == "postgres":
        _repo.execute(cursor, """
            ALTER TABLE contactos_ruana
            ADD COLUMN IF NOT EXISTS negociacion_json JSONB DEFAULT '{}'::jsonb
        """)
    else:
        columnas = _repo.columnas_tabla(cursor, "contactos_ruana")
        if 'negociacion_json' not in columnas:
            _repo.execute(cursor, "ALTER TABLE contactos_ruana ADD COLUMN negociacion_json TEXT")
    _repo.execute(cursor, """
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
    _repo.execute(cursor, 
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
            _repo.execute(cursor, 
                f"ALTER TABLE contactos_ruana ADD COLUMN IF NOT EXISTS {nombre} {pg_t}"
            )
        return
    columnas = _repo.columnas_tabla(cursor, "contactos_ruana")
    for nombre, sqlite_t, _pg_t in columnas_nuevas:
        if nombre not in columnas:
            _repo.execute(cursor, f"ALTER TABLE contactos_ruana ADD COLUMN {nombre} {sqlite_t}")

def _migrar_importe_acordado(db, conn, cursor) -> None:
    """Importe oficial del encargo = precio confirmado en la negociación."""
    if db.backend == "postgres":
        _repo.execute(cursor, 
            "ALTER TABLE contactos_ruana ADD COLUMN IF NOT EXISTS importe_acordado REAL"
        )
        return
    columnas = _repo.columnas_tabla(cursor, "contactos_ruana")
    if 'importe_acordado' not in columnas:
        _repo.execute(cursor, "ALTER TABLE contactos_ruana ADD COLUMN importe_acordado REAL")

def _migrar_contactos_motivo_contacto(db, conn, cursor) -> None:
    """Añade motivo_contacto al contacto (obligatorio antes de iniciar chat)."""
    columnas = _repo.columnas_tabla(cursor, "contactos_ruana")
    if 'motivo_contacto' in columnas:
        return
    _repo.execute(cursor, "ALTER TABLE contactos_ruana ADD COLUMN motivo_contacto TEXT")

def _migrar_contactos_es_urgente(db, conn, cursor) -> None:
    """Añade es_urgente y urgente_marcado_en (solo al iniciar chat, Regla 6)."""
    if db.backend == "postgres":
        _repo.execute(cursor, """
            ALTER TABLE contactos_ruana
            ADD COLUMN IF NOT EXISTS es_urgente INTEGER DEFAULT 0
        """)
        _repo.execute(cursor, """
            ALTER TABLE contactos_ruana
            ADD COLUMN IF NOT EXISTS urgente_marcado_en TIMESTAMP
        """)
        return
    columnas = _repo.columnas_tabla(cursor, "contactos_ruana")
    if 'es_urgente' not in columnas:
        _repo.execute(cursor, "ALTER TABLE contactos_ruana ADD COLUMN es_urgente INTEGER DEFAULT 0")
    if 'urgente_marcado_en' not in columnas:
        _repo.execute(cursor, "ALTER TABLE contactos_ruana ADD COLUMN urgente_marcado_en TIMESTAMP")

def _migrar_aliado_accesos_dia(db, conn, cursor) -> None:
    """Tabla de días con login (Regla 8: racha de 7 días consecutivos)."""
    _repo.execute(cursor, """
        CREATE TABLE IF NOT EXISTS aliado_accesos_dia (
            codigo_aliado TEXT NOT NULL,
            dia TEXT NOT NULL,
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (codigo_aliado, dia),
            FOREIGN KEY (codigo_aliado) REFERENCES aliados(codigo)
        )
    """)
    _repo.execute(cursor, 
        "CREATE INDEX IF NOT EXISTS idx_aliado_accesos_dia_codigo ON aliado_accesos_dia(codigo_aliado)"
    )
    _repo.execute(cursor, 
        "CREATE INDEX IF NOT EXISTS idx_aliado_accesos_dia_dia ON aliado_accesos_dia(dia)"
    )

def _migrar_drop_chat_messages(db, conn, cursor) -> None:
    """Elimina la tabla redundante chat_messages. Admin lee desde chat_mensajes + JOIN aliados."""
    if _repo.tabla_existe(cursor, "chat_messages"):
        _repo.execute(cursor, "DROP TABLE IF EXISTS chat_messages")

def _migrar_payment_conflicts(db, conn, cursor) -> None:
    """Tabla de conflictos de pago cuando importe contratante != importe profesional."""
    _repo.execute(cursor, """
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
    _repo.execute(cursor, "CREATE INDEX IF NOT EXISTS idx_payment_conflicts_trabajo ON payment_conflicts(trabajo_id)")
    _repo.execute(cursor, "CREATE INDEX IF NOT EXISTS idx_payment_conflicts_created ON payment_conflicts(created_at DESC)")

def _migrar_stripe_pagos(db, conn, cursor) -> None:
    """Columnas y tablas para pagos Stripe Connect (separate charges and transfers)."""
    contacto_cols_sqlite = [
        ("modo_pago", "TEXT DEFAULT 'manual'"),
        ("precio_congelado", "INTEGER DEFAULT 0"),
        ("precio_congelado_en", "TIMESTAMP"),
        ("stripe_checkout_session_id", "TEXT"),
        ("stripe_payment_intent_id", "TEXT"),
        ("stripe_transfer_id", "TEXT"),
        ("importe_neto_profesional", "REAL"),
        ("fecha_cobro_confirmado", "TIMESTAMP"),
        ("fecha_confirmacion_trabajo", "TIMESTAMP"),
        ("fecha_transferencia", "TIMESTAMP"),
        ("stripe_cobro_estado", "TEXT"),
    ]
    columnas_contacto = _repo.columnas_tabla(cursor, "contactos_ruana")
    for nombre, sqlite_def in contacto_cols_sqlite:
        if nombre not in columnas_contacto:
            _repo.execute(cursor, f"ALTER TABLE contactos_ruana ADD COLUMN {nombre} {sqlite_def}")

    aliado_cols_sqlite = [
        ("stripe_account_id", "TEXT"),
        ("stripe_onboarding_completo", "INTEGER DEFAULT 0"),
        ("stripe_charges_enabled", "INTEGER DEFAULT 0"),
        ("stripe_payouts_enabled", "INTEGER DEFAULT 0"),
    ]
    columnas_aliado = _repo.columnas_tabla(cursor, "aliados")
    for nombre, sqlite_def in aliado_cols_sqlite:
        if nombre not in columnas_aliado:
            _repo.execute(cursor, f"ALTER TABLE aliados ADD COLUMN {nombre} {sqlite_def}")

    columnas_pc = _repo.columnas_tabla(cursor, "payment_conflicts")
    if columnas_pc and "tipo" not in columnas_pc:
        _repo.execute(cursor, "ALTER TABLE payment_conflicts ADD COLUMN tipo TEXT DEFAULT 'importe_discrepante'")
    if columnas_pc and "stripe_payment_intent_id" not in columnas_pc:
        _repo.execute(cursor, "ALTER TABLE payment_conflicts ADD COLUMN stripe_payment_intent_id TEXT")

    _repo.execute(cursor, """
        CREATE TABLE IF NOT EXISTS stripe_webhook_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stripe_event_id TEXT NOT NULL UNIQUE,
            tipo TEXT NOT NULL,
            contacto_id INTEGER,
            procesado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            resultado TEXT,
            FOREIGN KEY (contacto_id) REFERENCES contactos_ruana(id)
        )
    """)
    _repo.execute(cursor, "CREATE INDEX IF NOT EXISTS idx_stripe_webhook_contacto ON stripe_webhook_events(contacto_id)")


def _migrar_estado_financiero(db, conn, cursor) -> None:
    """Columnas y backfill para máquina de estados financiera (FASE 01)."""
    from core.financial.mapeo_legacy import inferir_estado_financiero_desde_legacy
    from core.financial.state_machine import FinancialStateMachine

    columnas_contacto = _repo.columnas_tabla(cursor, "contactos_ruana")
    nuevas_columnas = [
        ("estado_financiero", "TEXT"),
        ("estado_transferencia", "TEXT DEFAULT 'NO_APLICA'"),
    ]
    for nombre, sqlite_def in nuevas_columnas:
        if nombre not in columnas_contacto:
            _repo.execute(cursor, f"ALTER TABLE contactos_ruana ADD COLUMN {nombre} {sqlite_def}")

    _repo.execute(cursor, """
        CREATE TABLE IF NOT EXISTS financial_idempotency_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            clave TEXT NOT NULL UNIQUE,
            contacto_id INTEGER NOT NULL,
            operacion TEXT NOT NULL,
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (contacto_id) REFERENCES contactos_ruana(id)
        )
    """)
    _repo.execute(cursor, """
        CREATE INDEX IF NOT EXISTS idx_financial_idempotency_contacto
        ON financial_idempotency_keys(contacto_id)
    """)

    sm = FinancialStateMachine()
    cursor.execute(
        """
        SELECT id, modo_pago, estado, estado_pago, stripe_transfer_id,
               stripe_payment_intent_id, fecha_confirmacion_trabajo
        FROM contactos_ruana
        WHERE estado_financiero IS NULL OR estado_financiero = ''
        """
    )
    for row in cursor.fetchall():
        contacto = {
            "id": row[0],
            "modo_pago": row[1],
            "estado": row[2],
            "estado_pago": row[3],
            "stripe_transfer_id": row[4],
            "stripe_payment_intent_id": row[5],
            "fecha_confirmacion_trabajo": row[6],
        }
        inferido = inferir_estado_financiero_desde_legacy(contacto)
        estado_transferencia = sm.estado_transferencia_para(inferido).value
        cursor.execute(
            """
            UPDATE contactos_ruana
            SET estado_financiero = ?, estado_transferencia = ?
            WHERE id = ? AND (estado_financiero IS NULL OR estado_financiero = '')
            """,
            (inferido.value, estado_transferencia, contacto["id"]),
        )


def _migrar_financial_fase02(db, conn, cursor) -> None:
    """FASE 02: webhooks robustos, refunds/disputes, reconciliación."""
    columnas_wh = _repo.columnas_tabla(cursor, "stripe_webhook_events")
    for nombre, sqlite_def in [
        ("object_id", "TEXT"),
        ("estado_anterior", "TEXT"),
        ("estado_nuevo", "TEXT"),
        ("error_message", "TEXT"),
        ("estado_procesamiento", "TEXT DEFAULT 'completed'"),
    ]:
        if columnas_wh and nombre not in columnas_wh:
            _repo.execute(cursor, f"ALTER TABLE stripe_webhook_events ADD COLUMN {nombre} {sqlite_def}")

    columnas_contacto = _repo.columnas_tabla(cursor, "contactos_ruana")
    for nombre, sqlite_def in [
        ("stripe_charge_id", "TEXT"),
        ("stripe_refund_id", "TEXT"),
        ("stripe_refund_amount", "REAL DEFAULT 0"),
        ("stripe_dispute_id", "TEXT"),
        ("stripe_dispute_amount", "REAL"),
        ("stripe_dispute_reason", "TEXT"),
        ("stripe_dispute_status", "TEXT"),
        ("stripe_dispute_evidence_due", "TIMESTAMP"),
        ("reembolsos_acumulados", "REAL DEFAULT 0"),
    ]:
        if nombre not in columnas_contacto:
            _repo.execute(cursor, f"ALTER TABLE contactos_ruana ADD COLUMN {nombre} {sqlite_def}")

    _repo.execute(cursor, """
        CREATE TABLE IF NOT EXISTS stripe_refunds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contacto_id INTEGER NOT NULL,
            stripe_refund_id TEXT NOT NULL UNIQUE,
            stripe_charge_id TEXT,
            amount REAL NOT NULL,
            currency TEXT DEFAULT 'eur',
            stripe_event_id TEXT,
            es_total INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (contacto_id) REFERENCES contactos_ruana(id)
        )
    """)
    _repo.execute(cursor, """
        CREATE INDEX IF NOT EXISTS idx_stripe_refunds_contacto ON stripe_refunds(contacto_id)
    """)

    _repo.execute(cursor, """
        CREATE TABLE IF NOT EXISTS stripe_disputes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contacto_id INTEGER NOT NULL,
            stripe_dispute_id TEXT NOT NULL UNIQUE,
            stripe_charge_id TEXT,
            amount REAL,
            currency TEXT DEFAULT 'eur',
            reason TEXT,
            status TEXT,
            evidence_due_by TIMESTAMP,
            stripe_event_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (contacto_id) REFERENCES contactos_ruana(id)
        )
    """)
    _repo.execute(cursor, """
        CREATE INDEX IF NOT EXISTS idx_stripe_disputes_contacto ON stripe_disputes(contacto_id)
    """)

    _repo.execute(cursor, """
        CREATE TABLE IF NOT EXISTS financial_reconciliation (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contacto_id INTEGER NOT NULL,
            stripe_payment_intent_id TEXT,
            stripe_transfer_id TEXT,
            ruana_estado TEXT,
            stripe_estado TEXT,
            tipo_discrepancia TEXT NOT NULL,
            importe_ruana REAL,
            importe_stripe REAL,
            estado_reconciliacion TEXT DEFAULT 'open',
            detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            resolved_at TIMESTAMP,
            resolution TEXT,
            metadata TEXT,
            FOREIGN KEY (contacto_id) REFERENCES contactos_ruana(id)
        )
    """)
    _repo.execute(cursor, """
        CREATE INDEX IF NOT EXISTS idx_fin_recon_contacto ON financial_reconciliation(contacto_id)
    """)
    _repo.execute(cursor, """
        CREATE INDEX IF NOT EXISTS idx_fin_recon_abierta
        ON financial_reconciliation(contacto_id, tipo_discrepancia, estado_reconciliacion)
    """)


def _migrar_financial_fase03(db, conn, cursor) -> None:
    """FASE 03: transferencias blindadas — una operación → una transferencia Stripe."""
    _repo.execute(cursor, """
        CREATE TABLE IF NOT EXISTS financial_transfers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contacto_id INTEGER NOT NULL UNIQUE,
            idempotency_key TEXT NOT NULL UNIQUE,
            stripe_transfer_id TEXT UNIQUE,
            amount_cents INTEGER NOT NULL,
            currency TEXT NOT NULL DEFAULT 'eur',
            destination_account_id TEXT NOT NULL,
            professional_codigo TEXT NOT NULL,
            stripe_payment_intent_id TEXT,
            estado TEXT NOT NULL DEFAULT 'RECLAMADA',
            actor_codigo TEXT,
            error_message TEXT,
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (contacto_id) REFERENCES contactos_ruana(id)
        )
    """)
    _repo.execute(cursor, """
        CREATE INDEX IF NOT EXISTS idx_fin_transfers_stripe_id
        ON financial_transfers(stripe_transfer_id)
    """)
    _repo.execute(cursor, """
        CREATE TABLE IF NOT EXISTS financial_transfer_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contacto_id INTEGER NOT NULL,
            financial_transfer_id INTEGER,
            actor_codigo TEXT,
            resultado TEXT NOT NULL,
            motivo_bloqueo TEXT,
            estado_anterior TEXT,
            estado_nuevo TEXT,
            stripe_transfer_id TEXT,
            metadata TEXT,
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (contacto_id) REFERENCES contactos_ruana(id),
            FOREIGN KEY (financial_transfer_id) REFERENCES financial_transfers(id)
        )
    """)
    _repo.execute(cursor, """
        CREATE INDEX IF NOT EXISTS idx_fin_transfer_attempts_contacto
        ON financial_transfer_attempts(contacto_id)
    """)


def _migrar_financial_fase03_1(db, conn, cursor) -> None:
    """FASE 03.1: referencias Stripe Connect en financial_transfers."""
    columnas = _repo.columnas_tabla(cursor, "financial_transfers")
    if not columnas:
        return
    for nombre, sqlite_def in [
        ("stripe_balance_transaction_id", "TEXT"),
        ("stripe_destination_payment_id", "TEXT"),
    ]:
        if nombre not in columnas:
            _repo.execute(cursor, f"ALTER TABLE financial_transfers ADD COLUMN {nombre} {sqlite_def}")


def _migrar_financial_fase03_2(db, conn, cursor) -> None:
    """FASE 03.2: reconciliación explícita y snapshots de transferencias."""
    columnas = _repo.columnas_tabla(cursor, "financial_transfers")
    if columnas:
        for nombre, sqlite_def in [
            ("reconciliacion_estado", "TEXT"),
            ("stripe_snapshot_json", "TEXT"),
            ("efectos_post_transfer_aplicados", "INTEGER DEFAULT 0"),
            ("bloqueada", "INTEGER DEFAULT 0"),
        ]:
            if nombre not in columnas:
                _repo.execute(cursor, f"ALTER TABLE financial_transfers ADD COLUMN {nombre} {sqlite_def}")

    _repo.execute(cursor, """
        CREATE TABLE IF NOT EXISTS financial_transfer_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contacto_id INTEGER NOT NULL,
            stripe_transfer_id TEXT,
            stripe_event_id TEXT,
            event_type TEXT NOT NULL,
            snapshot_json TEXT NOT NULL,
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (contacto_id) REFERENCES contactos_ruana(id)
        )
    """)
    _repo.execute(cursor, """
        CREATE INDEX IF NOT EXISTS idx_fin_transfer_snapshots_contacto
        ON financial_transfer_snapshots(contacto_id, creado_en DESC)
    """)


def _migrar_financial_fase04_conflicts(db, conn, cursor) -> None:
    """FASE 04: conflictos financieros formales."""
    if not _repo.tabla_existe(cursor, "payment_conflicts"):
        return

    columnas = _repo.columnas_tabla(cursor, "payment_conflicts")
    nuevas = [
        ("estado_conflicto", "TEXT"),
        ("tipo_conflicto", "TEXT"),
        ("motivo", "TEXT"),
        ("importe_reclamado_cents", "INTEGER"),
        ("moneda", "TEXT DEFAULT 'eur'"),
        ("abierto_por", "TEXT"),
        ("responsable_codigo", "TEXT"),
        ("prioridad", "TEXT DEFAULT 'normal'"),
        ("fecha_apertura", "TIMESTAMP"),
        ("fecha_asignacion", "TIMESTAMP"),
        ("fecha_resolucion", "TIMESTAMP"),
        ("resolucion", "TEXT"),
        ("importe_liberar_cents", "INTEGER"),
        ("importe_reembolsar_cents", "INTEGER"),
        ("importe_profesional_cents", "INTEGER"),
        ("importe_contratante_cents", "INTEGER"),
        ("bloqueo_financiero", "INTEGER DEFAULT 1"),
        ("version", "INTEGER DEFAULT 1"),
        ("idempotency_key_apertura", "TEXT"),
    ]
    for nombre, sqlite_def in nuevas:
        if nombre not in columnas:
            _repo.execute(cursor, f"ALTER TABLE payment_conflicts ADD COLUMN {nombre} {sqlite_def}")

    _repo.execute(cursor, """
        CREATE TABLE IF NOT EXISTS payment_conflict_evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conflicto_id INTEGER NOT NULL,
            tipo TEXT NOT NULL,
            nombre TEXT NOT NULL,
            referencia_segura TEXT NOT NULL,
            hash_sha256 TEXT,
            subido_por TEXT NOT NULL,
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            metadata_json TEXT,
            eliminado_en TIMESTAMP,
            FOREIGN KEY (conflicto_id) REFERENCES payment_conflicts(id)
        )
    """)
    _repo.execute(cursor, """
        CREATE INDEX IF NOT EXISTS idx_pce_conflicto
        ON payment_conflict_evidence(conflicto_id, creado_en)
    """)
    _repo.execute(cursor, """
        CREATE TABLE IF NOT EXISTS payment_conflict_comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conflicto_id INTEGER NOT NULL,
            autor_codigo TEXT NOT NULL,
            texto TEXT NOT NULL,
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            visible_para_contratante INTEGER DEFAULT 1,
            visible_para_profesional INTEGER DEFAULT 1,
            FOREIGN KEY (conflicto_id) REFERENCES payment_conflicts(id)
        )
    """)
    _repo.execute(cursor, """
        CREATE INDEX IF NOT EXISTS idx_pcc_conflicto
        ON payment_conflict_comments(conflicto_id, creado_en)
    """)
    _repo.execute(cursor, """
        CREATE TABLE IF NOT EXISTS payment_conflict_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conflicto_id INTEGER NOT NULL,
            operacion TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,
            actor_codigo TEXT NOT NULL,
            resultado TEXT NOT NULL DEFAULT 'en_proceso',
            metadata_json TEXT,
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(conflicto_id, operacion, idempotency_key),
            FOREIGN KEY (conflicto_id) REFERENCES payment_conflicts(id)
        )
    """)
    _repo.execute(cursor, """
        CREATE TABLE IF NOT EXISTS payment_conflict_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conflicto_id INTEGER NOT NULL,
            accion TEXT NOT NULL,
            actor_codigo TEXT NOT NULL,
            estado_anterior TEXT,
            estado_nuevo TEXT,
            metadata_json TEXT,
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (conflicto_id) REFERENCES payment_conflicts(id)
        )
    """)
    _repo.execute(cursor, """
        CREATE INDEX IF NOT EXISTS idx_pca_conflicto
        ON payment_conflict_audit(conflicto_id, creado_en DESC)
    """)
    _repo.execute(cursor, """
        CREATE INDEX IF NOT EXISTS idx_pc_estado_conflicto
        ON payment_conflicts(estado_conflicto)
    """)
    _repo.execute(cursor, """
        CREATE INDEX IF NOT EXISTS idx_pc_bloqueo ON payment_conflicts(bloqueo_financiero)
    """)
    _repo.execute(cursor, """
        CREATE INDEX IF NOT EXISTS idx_pc_responsable ON payment_conflicts(responsable_codigo)
    """)

    _repo.execute(cursor, """
        UPDATE payment_conflicts SET estado_conflicto = 'ABIERTO'
        WHERE estado_conflicto IS NULL AND estado = 'PENDIENTE_PRUEBA'
    """)
    _repo.execute(cursor, """
        UPDATE payment_conflicts SET estado_conflicto = 'EN_INVESTIGACION'
        WHERE estado_conflicto IS NULL AND estado = 'EN_REVISION'
    """)
    _repo.execute(cursor, """
        UPDATE payment_conflicts SET estado_conflicto = 'CERRADO', bloqueo_financiero = 0
        WHERE estado_conflicto IS NULL AND estado IN ('RESUELTO', 'RECHAZADO')
    """)
    _repo.execute(cursor, """
        UPDATE payment_conflicts SET tipo_conflicto = 'IMPORTE_DISPUTADO'
        WHERE tipo_conflicto IS NULL AND tipo = 'importe_discrepante'
    """)
    _repo.execute(cursor, """
        UPDATE payment_conflicts SET tipo_conflicto = 'PLAZO_DISPUTADO'
        WHERE tipo_conflicto IS NULL AND tipo = 'sin_confirmacion_trabajo'
    """)
    _repo.execute(cursor, """
        UPDATE payment_conflicts SET bloqueo_financiero = 1
        WHERE bloqueo_financiero IS NULL AND estado_conflicto IN (
            'ABIERTO', 'EN_INVESTIGACION', 'PENDIENTE_DE_EVIDENCIA', 'ESCALADO'
        )
    """)


def _migrar_financial_fase05_refunds(db, conn, cursor) -> None:
    """FASE 05: reembolsos Stripe blindados."""
    _repo.execute(cursor, """
        CREATE TABLE IF NOT EXISTS financial_refunds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contacto_id INTEGER NOT NULL,
            conflicto_id INTEGER,
            payment_intent_id TEXT,
            charge_id TEXT,
            stripe_refund_id TEXT UNIQUE,
            importe_solicitado_cents INTEGER NOT NULL,
            importe_confirmado_cents INTEGER NOT NULL DEFAULT 0,
            moneda TEXT NOT NULL DEFAULT 'eur',
            estado TEXT NOT NULL DEFAULT 'REQUESTED',
            motivo_stripe TEXT,
            causa_ruana TEXT NOT NULL,
            comision_total_cents INTEGER NOT NULL DEFAULT 0,
            comision_conservada_cents INTEGER NOT NULL DEFAULT 0,
            comision_devuelta_cents INTEGER NOT NULL DEFAULT 0,
            parte_ejecutada_cents INTEGER NOT NULL DEFAULT 0,
            parte_no_ejecutada_cents INTEGER NOT NULL DEFAULT 0,
            actor_codigo TEXT NOT NULL,
            permiso_usado TEXT,
            idempotency_key TEXT NOT NULL UNIQUE,
            error_stripe TEXT,
            metadata_json TEXT,
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (contacto_id) REFERENCES contactos_ruana(id),
            FOREIGN KEY (conflicto_id) REFERENCES payment_conflicts(id)
        )
    """)
    _repo.execute(cursor, """
        CREATE INDEX IF NOT EXISTS idx_financial_refunds_contacto ON financial_refunds(contacto_id)
    """)
    _repo.execute(cursor, """
        CREATE INDEX IF NOT EXISTS idx_financial_refunds_estado ON financial_refunds(estado)
    """)
    _repo.execute(cursor, """
        CREATE TABLE IF NOT EXISTS financial_refund_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            refund_id INTEGER NOT NULL,
            operacion TEXT NOT NULL,
            actor_codigo TEXT NOT NULL,
            resultado TEXT NOT NULL,
            metadata_json TEXT,
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (refund_id) REFERENCES financial_refunds(id)
        )
    """)
    columnas_sr = _repo.columnas_tabla(cursor, "stripe_refunds")
    for nombre, sqlite_def in (
        ("financial_refund_id", "INTEGER"),
        ("amount_cents", "INTEGER"),
        ("payment_intent_id", "TEXT"),
        ("updated_at", "TIMESTAMP"),
    ):
        if nombre not in columnas_sr:
            _repo.execute(cursor, f"ALTER TABLE stripe_refunds ADD COLUMN {nombre} {sqlite_def}")


def _migrar_financial_fase06_disputes(db, conn, cursor) -> None:
    """FASE 06: disputas Stripe formales."""
    _repo.execute(cursor, """
        CREATE TABLE IF NOT EXISTS financial_disputes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contacto_id INTEGER NOT NULL,
            stripe_dispute_id TEXT NOT NULL UNIQUE,
            charge_id TEXT,
            payment_intent_id TEXT,
            amount_cents INTEGER NOT NULL,
            currency TEXT NOT NULL DEFAULT 'eur',
            reason TEXT,
            status_stripe TEXT,
            estado_interno TEXT NOT NULL DEFAULT 'ABIERTO',
            evidence_due_by TIMESTAMP,
            has_evidence INTEGER NOT NULL DEFAULT 0,
            evidence_submitted INTEGER NOT NULL DEFAULT 0,
            network_reason_code TEXT,
            balance_transaction_id TEXT,
            funds_withdrawn_cents INTEGER NOT NULL DEFAULT 0,
            funds_reinstated_cents INTEGER NOT NULL DEFAULT 0,
            resolution TEXT,
            resolution_reason TEXT,
            responsable_codigo TEXT,
            conflicto_id INTEGER,
            idempotency_key TEXT UNIQUE,
            bloqueo_financiero INTEGER NOT NULL DEFAULT 1,
            estado_financiero_historico TEXT,
            metadata_json TEXT,
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            cerrado_en TIMESTAMP,
            FOREIGN KEY (contacto_id) REFERENCES contactos_ruana(id),
            FOREIGN KEY (conflicto_id) REFERENCES payment_conflicts(id)
        )
    """)
    _repo.execute(cursor, """
        CREATE INDEX IF NOT EXISTS idx_financial_disputes_contacto ON financial_disputes(contacto_id)
    """)
    _repo.execute(cursor, """
        CREATE INDEX IF NOT EXISTS idx_financial_disputes_estado ON financial_disputes(estado_interno)
    """)
    _repo.execute(cursor, """
        CREATE TABLE IF NOT EXISTS financial_dispute_evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dispute_id INTEGER NOT NULL,
            tipo TEXT NOT NULL,
            referencia TEXT,
            content_hash TEXT,
            autor_codigo TEXT NOT NULL,
            estado TEXT NOT NULL DEFAULT 'BORRADOR',
            enviada_a_stripe INTEGER NOT NULL DEFAULT 0,
            fecha_envio TIMESTAMP,
            metadata_json TEXT,
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (dispute_id) REFERENCES financial_disputes(id)
        )
    """)
    _repo.execute(cursor, """
        CREATE TABLE IF NOT EXISTS financial_dispute_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dispute_id INTEGER NOT NULL,
            operacion TEXT NOT NULL,
            actor_codigo TEXT NOT NULL,
            permiso_usado TEXT,
            resultado TEXT NOT NULL,
            metadata_json TEXT,
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (dispute_id) REFERENCES financial_disputes(id)
        )
    """)
    columnas_sd = _repo.columnas_tabla(cursor, "stripe_disputes")
    for nombre, sqlite_def in (
        ("financial_dispute_id", "INTEGER"),
        ("amount_cents", "INTEGER"),
        ("updated_at", "TIMESTAMP"),
    ):
        if nombre not in columnas_sd:
            _repo.execute(cursor, f"ALTER TABLE stripe_disputes ADD COLUMN {nombre} {sqlite_def}")


def _migrar_financial_fase07_reconciliation(db, conn, cursor) -> None:
    """FASE 07: reconciliación financiera avanzada."""
    _repo.execute(cursor, """
        CREATE TABLE IF NOT EXISTS financial_reconciliation_executions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contacto_id INTEGER,
            payment_intent_id TEXT,
            transfer_id TEXT,
            operacion TEXT NOT NULL,
            estado TEXT NOT NULL DEFAULT 'NOT_STARTED',
            reconciler_version TEXT NOT NULL DEFAULT 'fase07-1',
            idempotency_key TEXT UNIQUE,
            actor_codigo TEXT,
            permiso_usado TEXT,
            motivo TEXT,
            metricas_json TEXT,
            error_stripe TEXT,
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            finalizado_en TIMESTAMP,
            FOREIGN KEY (contacto_id) REFERENCES contactos_ruana(id)
        )
    """)
    _repo.execute(cursor, """
        CREATE INDEX IF NOT EXISTS idx_fin_recon_exec_contacto
        ON financial_reconciliation_executions(contacto_id)
    """)
    _repo.execute(cursor, """
        CREATE INDEX IF NOT EXISTS idx_fin_recon_exec_pi
        ON financial_reconciliation_executions(payment_intent_id)
    """)
    _repo.execute(cursor, """
        CREATE INDEX IF NOT EXISTS idx_fin_recon_exec_transfer
        ON financial_reconciliation_executions(transfer_id)
    """)
    _repo.execute(cursor, """
        CREATE INDEX IF NOT EXISTS idx_fin_recon_exec_estado
        ON financial_reconciliation_executions(estado)
    """)
    _repo.execute(cursor, """
        CREATE INDEX IF NOT EXISTS idx_fin_recon_exec_idem
        ON financial_reconciliation_executions(idempotency_key)
    """)
    _repo.execute(cursor, """
        CREATE TABLE IF NOT EXISTS financial_reconciliation_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            execution_id INTEGER NOT NULL,
            contacto_id INTEGER NOT NULL,
            payment_intent_id TEXT,
            charge_id TEXT,
            balance_transaction_id TEXT,
            transfer_id TEXT,
            connected_account_id TEXT,
            moneda TEXT NOT NULL DEFAULT 'eur',
            importe_bruto_cents INTEGER NOT NULL DEFAULT 0,
            importe_cobrado_cents INTEGER NOT NULL DEFAULT 0,
            fee_stripe_cents INTEGER NOT NULL DEFAULT 0,
            neto_ruana_cents INTEGER NOT NULL DEFAULT 0,
            importe_transferido_cents INTEGER NOT NULL DEFAULT 0,
            total_reembolsado_cents INTEGER NOT NULL DEFAULT 0,
            importe_disputado_cents INTEGER NOT NULL DEFAULT 0,
            comision_ruana_cents INTEGER NOT NULL DEFAULT 0,
            obligacion_profesional_cents INTEGER NOT NULL DEFAULT 0,
            estado_ruana TEXT,
            estado_stripe TEXT,
            origen TEXT NOT NULL DEFAULT 'stripe_api',
            reconciler_version TEXT NOT NULL DEFAULT 'fase07-1',
            snapshot_json TEXT NOT NULL,
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (execution_id) REFERENCES financial_reconciliation_executions(id),
            FOREIGN KEY (contacto_id) REFERENCES contactos_ruana(id)
        )
    """)
    _repo.execute(cursor, """
        CREATE INDEX IF NOT EXISTS idx_fin_recon_snap_exec
        ON financial_reconciliation_snapshots(execution_id)
    """)
    _repo.execute(cursor, """
        CREATE INDEX IF NOT EXISTS idx_fin_recon_snap_contacto
        ON financial_reconciliation_snapshots(contacto_id)
    """)
    _repo.execute(cursor, """
        CREATE TABLE IF NOT EXISTS financial_reconciliation_resource_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            execution_id INTEGER NOT NULL,
            resource_type TEXT NOT NULL,
            resource_id TEXT,
            fetch_status TEXT NOT NULL,
            error_code TEXT,
            http_status INTEGER,
            metadata_json TEXT,
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (execution_id) REFERENCES financial_reconciliation_executions(id)
        )
    """)
    _repo.execute(cursor, """
        CREATE INDEX IF NOT EXISTS idx_fin_recon_res_exec
        ON financial_reconciliation_resource_results(execution_id, resource_type)
    """)


def _migrar_financial_fase08_ledger(db, conn, cursor) -> None:
    """FASE 08: ledger financiero interno."""
    _repo.execute(cursor, """
        CREATE TABLE IF NOT EXISTS ledger_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_key TEXT NOT NULL UNIQUE,
            contacto_id INTEGER,
            tipo TEXT NOT NULL,
            moneda TEXT NOT NULL DEFAULT 'eur',
            estado TEXT NOT NULL DEFAULT 'DRAFT',
            actor_origen TEXT,
            evento_origen TEXT,
            referencia_stripe TEXT,
            idempotency_key TEXT NOT NULL UNIQUE,
            reversa_de_id INTEGER,
            fecha_efectiva TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            fecha_publicacion TIMESTAMP,
            metadata_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (contacto_id) REFERENCES contactos_ruana(id),
            FOREIGN KEY (reversa_de_id) REFERENCES ledger_transactions(id)
        )
    """)
    _repo.execute(cursor, """
        CREATE INDEX IF NOT EXISTS idx_ledger_tx_contacto ON ledger_transactions(contacto_id)
    """)
    _repo.execute(cursor, """
        CREATE INDEX IF NOT EXISTS idx_ledger_tx_tipo ON ledger_transactions(tipo)
    """)
    _repo.execute(cursor, """
        CREATE INDEX IF NOT EXISTS idx_ledger_tx_estado ON ledger_transactions(estado)
    """)
    _repo.execute(cursor, """
        CREATE INDEX IF NOT EXISTS idx_ledger_tx_idem ON ledger_transactions(idempotency_key)
    """)
    _repo.execute(cursor, """
        CREATE TABLE IF NOT EXISTS ledger_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ledger_transaction_id INTEGER NOT NULL,
            account_code TEXT NOT NULL,
            debit_cents INTEGER NOT NULL DEFAULT 0 CHECK (debit_cents >= 0),
            credit_cents INTEGER NOT NULL DEFAULT 0 CHECK (credit_cents >= 0),
            currency TEXT NOT NULL DEFAULT 'eur',
            descripcion TEXT,
            referencia TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (ledger_transaction_id) REFERENCES ledger_transactions(id),
            CHECK (NOT (debit_cents > 0 AND credit_cents > 0)),
            CHECK (debit_cents + credit_cents > 0)
        )
    """)
    _repo.execute(cursor, """
        CREATE INDEX IF NOT EXISTS idx_ledger_entries_tx ON ledger_entries(ledger_transaction_id)
    """)
    _repo.execute(cursor, """
        CREATE INDEX IF NOT EXISTS idx_ledger_entries_account ON ledger_entries(account_code)
    """)
    _repo.execute(cursor, """
        CREATE TABLE IF NOT EXISTS ledger_event_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ledger_transaction_id INTEGER NOT NULL,
            resource_type TEXT NOT NULL,
            resource_id TEXT NOT NULL,
            metadata_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (ledger_transaction_id) REFERENCES ledger_transactions(id),
            UNIQUE (ledger_transaction_id, resource_type, resource_id)
        )
    """)
    _repo.execute(cursor, """
        CREATE INDEX IF NOT EXISTS idx_ledger_links_resource
        ON ledger_event_links(resource_type, resource_id)
    """)
    _repo.execute(cursor, """
        CREATE TABLE IF NOT EXISTS ledger_account_balances (
            account_code TEXT NOT NULL,
            contacto_id INTEGER NOT NULL DEFAULT 0,
            currency TEXT NOT NULL DEFAULT 'eur',
            debit_total_cents INTEGER NOT NULL DEFAULT 0,
            credit_total_cents INTEGER NOT NULL DEFAULT 0,
            saldo_neto_cents INTEGER NOT NULL DEFAULT 0,
            actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (account_code, contacto_id, currency)
        )
    """)


def _migrar_financial_fase09_admin_panel(db, conn, cursor) -> None:
    """FASE 09: panel administrativo financiero — resoluciones de alertas."""
    _repo.execute(cursor, """
        CREATE TABLE IF NOT EXISTS financial_admin_alert_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_key TEXT NOT NULL,
            contacto_id INTEGER,
            accion TEXT NOT NULL DEFAULT 'resolved',
            motivo TEXT NOT NULL,
            actor_codigo TEXT NOT NULL,
            permiso_usado TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (alert_key, accion)
        )
    """)
    _repo.execute(cursor, """
        CREATE INDEX IF NOT EXISTS idx_fin_admin_alert_key
        ON financial_admin_alert_actions(alert_key)
    """)
    _repo.execute(cursor, """
        CREATE INDEX IF NOT EXISTS idx_fin_admin_alert_contacto
        ON financial_admin_alert_actions(contacto_id)
    """)
    _repo.execute(cursor, """
        CREATE INDEX IF NOT EXISTS idx_contactos_stripe_estado
        ON contactos_ruana(modo_pago, estado_financiero)
    """)


def _migrar_financial_fase10_security(db, conn, cursor) -> None:
    """FASE 10: aprobaciones de acciones sensibles + auditoría financiera unificada."""
    _repo.execute(cursor, """
        CREATE TABLE IF NOT EXISTS financial_action_approvals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action_id TEXT NOT NULL,
            action_type TEXT NOT NULL,
            contacto_id INTEGER,
            actor_solicitante TEXT NOT NULL,
            actor_autorizador TEXT,
            importe_cents INTEGER NOT NULL DEFAULT 0,
            currency TEXT NOT NULL DEFAULT 'eur',
            motivo TEXT NOT NULL,
            estado TEXT NOT NULL DEFAULT 'REQUESTED',
            version INTEGER NOT NULL DEFAULT 1,
            idempotency_key TEXT NOT NULL,
            expires_at TIMESTAMP,
            metadata_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            approved_at TIMESTAMP,
            executed_at TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (action_id, estado)
        )
    """)
    _repo.execute(cursor, """
        CREATE INDEX IF NOT EXISTS idx_fin_approval_estado
        ON financial_action_approvals(estado)
    """)
    _repo.execute(cursor, """
        CREATE INDEX IF NOT EXISTS idx_fin_approval_contacto
        ON financial_action_approvals(contacto_id)
    """)
    _repo.execute(cursor, """
        CREATE INDEX IF NOT EXISTS idx_fin_approval_idem
        ON financial_action_approvals(idempotency_key)
    """)
    _repo.execute(cursor, """
        CREATE TABLE IF NOT EXISTS financial_audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT NOT NULL,
            actor_codigo TEXT NOT NULL,
            permiso_usado TEXT,
            rol_capacidad TEXT,
            accion TEXT NOT NULL,
            recurso_tipo TEXT NOT NULL,
            recurso_id TEXT NOT NULL,
            importe_cents INTEGER,
            moneda TEXT DEFAULT 'eur',
            version_recursos INTEGER,
            idempotency_key TEXT,
            motivo TEXT,
            resultado TEXT NOT NULL DEFAULT 'success',
            error_sanitizado TEXT,
            metadata_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    _repo.execute(cursor, """
        CREATE INDEX IF NOT EXISTS idx_fin_audit_actor ON financial_audit_log(actor_codigo)
    """)
    _repo.execute(cursor, """
        CREATE INDEX IF NOT EXISTS idx_fin_audit_recurso
        ON financial_audit_log(recurso_tipo, recurso_id)
    """)
    _repo.execute(cursor, """
        CREATE INDEX IF NOT EXISTS idx_fin_audit_created ON financial_audit_log(created_at DESC)
    """)


def _migrar_financial_fase11_automation(db, conn, cursor) -> None:
    """FASE 11: leases persistentes, ejecuciones de automatización y alertas financieras."""
    _repo.execute(cursor, """
        CREATE TABLE IF NOT EXISTS financial_job_leases (
            job_name TEXT PRIMARY KEY,
            holder TEXT NOT NULL,
            acquired_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            metadata_json TEXT
        )
    """)
    _repo.execute(cursor, """
        CREATE TABLE IF NOT EXISTS financial_automation_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL UNIQUE,
            job_name TEXT NOT NULL,
            estado TEXT NOT NULL DEFAULT 'RUNNING',
            actor TEXT NOT NULL,
            iniciado_en TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            finalizado_en TIMESTAMP,
            metricas_json TEXT,
            errores_json TEXT,
            alertas_nuevas INTEGER NOT NULL DEFAULT 0,
            alertas_actualizadas INTEGER NOT NULL DEFAULT 0,
            detalle_json TEXT
        )
    """)
    _repo.execute(cursor, """
        CREATE INDEX IF NOT EXISTS idx_fin_auto_runs_job
        ON financial_automation_runs(job_name, iniciado_en DESC)
    """)
    _repo.execute(cursor, """
        CREATE INDEX IF NOT EXISTS idx_fin_auto_runs_estado
        ON financial_automation_runs(estado)
    """)
    _repo.execute(cursor, """
        CREATE TABLE IF NOT EXISTS financial_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_key TEXT NOT NULL UNIQUE,
            tipo TEXT NOT NULL,
            severidad TEXT NOT NULL,
            contacto_id INTEGER,
            estado TEXT NOT NULL DEFAULT 'OPEN',
            fecha_primera_deteccion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            fecha_ultima_deteccion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            antiguedad_horas INTEGER,
            accion_recomendada TEXT,
            accion_disponible TEXT,
            fuente TEXT,
            metadata_json TEXT,
            run_id_primera TEXT,
            run_id_ultima TEXT,
            resuelto_en TIMESTAMP,
            resuelto_por TEXT
        )
    """)
    _repo.execute(cursor, """
        CREATE INDEX IF NOT EXISTS idx_fin_alerts_estado
        ON financial_alerts(estado, severidad)
    """)
    _repo.execute(cursor, """
        CREATE INDEX IF NOT EXISTS idx_fin_alerts_tipo ON financial_alerts(tipo)
    """)
    _repo.execute(cursor, """
        CREATE INDEX IF NOT EXISTS idx_fin_alerts_contacto ON financial_alerts(contacto_id)
    """)


def _migrar_financial_fase13_p0_ledger_immutability(db, conn, cursor) -> None:
    """FASE 13A P0-4: triggers idempotentes — ledger POSTED inmutable en BD."""
    if getattr(db, "backend", None) == "postgres":
        cursor.execute(
            """
            CREATE OR REPLACE FUNCTION ruana_ledger_guard_tx_update()
            RETURNS TRIGGER AS $$
            BEGIN
              IF OLD.estado = 'POSTED' THEN
                IF NEW.estado = 'VOIDED' THEN
                  RETURN NEW;
                END IF;
                RAISE EXCEPTION 'ledger_transactions POSTED es inmutable (solo POSTED→VOIDED)';
              END IF;
              IF OLD.estado = 'VOIDED' THEN
                RAISE EXCEPTION 'ledger_transactions VOIDED es inmutable';
              END IF;
              RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
            """
        )
        cursor.execute("DROP TRIGGER IF EXISTS trg_ledger_tx_immutable ON ledger_transactions")
        cursor.execute(
            """
            CREATE TRIGGER trg_ledger_tx_immutable
              BEFORE UPDATE ON ledger_transactions
              FOR EACH ROW
              EXECUTE FUNCTION ruana_ledger_guard_tx_update()
            """
        )
        cursor.execute(
            """
            CREATE OR REPLACE FUNCTION ruana_ledger_guard_tx_delete()
            RETURNS TRIGGER AS $$
            BEGIN
              IF OLD.estado IN ('POSTED', 'VOIDED') THEN
                RAISE EXCEPTION 'No se puede eliminar ledger_transactions POSTED/VOIDED';
              END IF;
              RETURN OLD;
            END;
            $$ LANGUAGE plpgsql
            """
        )
        cursor.execute("DROP TRIGGER IF EXISTS trg_ledger_tx_no_delete ON ledger_transactions")
        cursor.execute(
            """
            CREATE TRIGGER trg_ledger_tx_no_delete
              BEFORE DELETE ON ledger_transactions
              FOR EACH ROW
              EXECUTE FUNCTION ruana_ledger_guard_tx_delete()
            """
        )
        cursor.execute(
            """
            CREATE OR REPLACE FUNCTION ruana_ledger_guard_entry_mutate()
            RETURNS TRIGGER AS $$
            DECLARE
              tx_estado TEXT;
              tx_id INTEGER;
            BEGIN
              IF TG_OP = 'DELETE' THEN
                tx_id := OLD.ledger_transaction_id;
              ELSE
                tx_id := NEW.ledger_transaction_id;
              END IF;
              SELECT estado INTO tx_estado FROM ledger_transactions WHERE id = tx_id;
              IF tx_estado IN ('POSTED', 'VOIDED') THEN
                RAISE EXCEPTION 'ledger_entries de transacciones POSTED/VOIDED son inmutables';
              END IF;
              IF TG_OP = 'DELETE' THEN
                RETURN OLD;
              END IF;
              RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
            """
        )
        cursor.execute("DROP TRIGGER IF EXISTS trg_ledger_entry_no_update ON ledger_entries")
        cursor.execute(
            """
            CREATE TRIGGER trg_ledger_entry_no_update
              BEFORE UPDATE ON ledger_entries
              FOR EACH ROW
              EXECUTE FUNCTION ruana_ledger_guard_entry_mutate()
            """
        )
        cursor.execute("DROP TRIGGER IF EXISTS trg_ledger_entry_no_delete ON ledger_entries")
        cursor.execute(
            """
            CREATE TRIGGER trg_ledger_entry_no_delete
              BEFORE DELETE ON ledger_entries
              FOR EACH ROW
              EXECUTE FUNCTION ruana_ledger_guard_entry_mutate()
            """
        )
        return

    _repo.execute(
        cursor,
        """
        CREATE TRIGGER IF NOT EXISTS trg_ruana_ledger_tx_guard_update
        BEFORE UPDATE ON ledger_transactions
        FOR EACH ROW
        WHEN OLD.estado = 'POSTED' AND NEW.estado != 'VOIDED'
        BEGIN
            SELECT RAISE(ABORT, 'ledger_transactions POSTED inmutables');
        END
        """,
    )
    _repo.execute(
        cursor,
        """
        CREATE TRIGGER IF NOT EXISTS trg_ruana_ledger_tx_guard_downgrade
        BEFORE UPDATE ON ledger_transactions
        FOR EACH ROW
        WHEN OLD.estado = 'POSTED' AND NEW.estado = 'DRAFT'
        BEGIN
            SELECT RAISE(ABORT, 'no downgrade POSTED a DRAFT');
        END
        """,
    )
    _repo.execute(
        cursor,
        """
        CREATE TRIGGER IF NOT EXISTS trg_ruana_ledger_tx_guard_delete
        BEFORE DELETE ON ledger_transactions
        FOR EACH ROW
        WHEN OLD.estado = 'POSTED'
        BEGIN
            SELECT RAISE(ABORT, 'ledger_transactions POSTED no se pueden eliminar');
        END
        """,
    )
    _repo.execute(
        cursor,
        """
        CREATE TRIGGER IF NOT EXISTS trg_ruana_ledger_tx_guard_voided
        BEFORE UPDATE ON ledger_transactions
        FOR EACH ROW
        WHEN OLD.estado = 'VOIDED'
        BEGIN
            SELECT RAISE(ABORT, 'ledger_transactions VOIDED inmutables');
        END
        """,
    )
    _repo.execute(
        cursor,
        """
        CREATE TRIGGER IF NOT EXISTS trg_ruana_ledger_entry_guard_update
        BEFORE UPDATE ON ledger_entries
        FOR EACH ROW
        WHEN (SELECT estado FROM ledger_transactions WHERE id = OLD.ledger_transaction_id) IN ('POSTED', 'VOIDED')
        BEGIN
            SELECT RAISE(ABORT, 'ledger_entries inmutables si tx POSTED/VOIDED');
        END
        """,
    )
    _repo.execute(
        cursor,
        """
        CREATE TRIGGER IF NOT EXISTS trg_ruana_ledger_entry_guard_delete
        BEFORE DELETE ON ledger_entries
        FOR EACH ROW
        WHEN (SELECT estado FROM ledger_transactions WHERE id = OLD.ledger_transaction_id) = 'POSTED'
        BEGIN
            SELECT RAISE(ABORT, 'ledger_entries de POSTED no se pueden eliminar');
        END
        """,
    )


def _migrar_contactos_validacion_pago(db, conn, cursor) -> None:
    """Añade fecha_validacion_pago, admin_validacion_codigo y motivo_rechazo_pago a contactos_ruana."""
    columnas = _repo.columnas_tabla(cursor, "contactos_ruana")
    if 'fecha_validacion_pago' not in columnas:
        _repo.execute(cursor, "ALTER TABLE contactos_ruana ADD COLUMN fecha_validacion_pago TIMESTAMP")
    if 'admin_validacion_codigo' not in columnas:
        _repo.execute(cursor, "ALTER TABLE contactos_ruana ADD COLUMN admin_validacion_codigo TEXT")
    if 'motivo_rechazo_pago' not in columnas:
        _repo.execute(cursor, "ALTER TABLE contactos_ruana ADD COLUMN motivo_rechazo_pago TEXT")

def _migrar_solicitudes_unificado(db, conn, cursor) -> None:
    """Una sola tabla solicitudes: grupo_id, solicitante_codigo/nombre, oficio, descripcion, estado (pendiente/atendida), atendido_por_*, created_at, atendido_at."""
    if _repo.tabla_existe(cursor, "solicitudes"):
        columnas = _repo.columnas_tabla(cursor, "solicitudes")
        if 'solicitante_codigo' in columnas:
            return
        if 'texto' in columnas:
            _repo.execute(cursor, "ALTER TABLE solicitudes RENAME TO solicitudes_legacy")
    _repo.execute(cursor, """
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
    _repo.execute(cursor, "CREATE INDEX IF NOT EXISTS idx_solicitudes_grupo ON solicitudes(grupo_id)")
    _repo.execute(cursor, "CREATE INDEX IF NOT EXISTS idx_solicitudes_estado ON solicitudes(estado)")
    _repo.execute(cursor, "CREATE INDEX IF NOT EXISTS idx_solicitudes_created ON solicitudes(created_at DESC)")

def _migrar_contacto_panel_oculto(db, conn, cursor) -> None:
    """Tabla para que un aliado pueda ocultar un contacto de su panel (Finalizar chat)."""
    if _repo.migracion_aplicada(cursor, 'contacto_panel_oculto'):
        return
    _repo.execute(cursor, """
        CREATE TABLE IF NOT EXISTS contacto_panel_oculto (
            contacto_id INTEGER NOT NULL,
            codigo_aliado TEXT NOT NULL,
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (contacto_id, codigo_aliado),
            FOREIGN KEY (contacto_id) REFERENCES contactos_ruana(id)
        )
    """)
    _repo.execute(cursor, "CREATE INDEX IF NOT EXISTS idx_contacto_panel_oculto_aliado ON contacto_panel_oculto(codigo_aliado)")
    _repo.registrar_migracion(cursor, 'contacto_panel_oculto')

def _migrar_competencia_scores(db, conn, cursor) -> None:
    """Añade columnas de scores a competencia para snapshot y tracking."""
    columnas = _repo.columnas_tabla(cursor, "competencia")
    for col, def_sql in [
        ('score_titular_inicio', 'INTEGER'),
        ('score_titular_actual', 'INTEGER'),
        ('motivo', 'TEXT'),
    ]:
        if col not in columnas:
            _repo.execute(cursor, f"ALTER TABLE competencia ADD COLUMN {col} {def_sql}")
    # Preferir nombres retador; si solo existen los legacy suplente, el rename posterior los migra
    if 'score_retador_inicio' not in columnas and 'score_suplente_inicio' not in columnas:
        _repo.execute(cursor, "ALTER TABLE competencia ADD COLUMN score_retador_inicio INTEGER")
    if 'score_retador_actual' not in columnas and 'score_suplente_actual' not in columnas:
        _repo.execute(cursor, "ALTER TABLE competencia ADD COLUMN score_retador_actual INTEGER")

def _migrar_retador_rename(db, conn, cursor) -> None:
    """Renombra columnas suplente→retador en la tabla competencia (SQLite 3.25+)."""
    if _repo.migracion_aplicada(cursor, 'retador_rename_v1'):
        return
    cols = _repo.columnas_tabla(cursor, "competencia")
    renames = [
        ('suplente_codigo', 'retador_codigo'),
        ('suplente_grupo_anterior_id', 'retador_grupo_anterior_id'),
        ('score_suplente_inicio', 'score_retador_inicio'),
        ('score_suplente_actual', 'score_retador_actual'),
    ]
    for old_name, new_name in renames:
        if old_name in cols:
            try:
                _repo.execute(cursor, f"ALTER TABLE competencia RENAME COLUMN {old_name} TO {new_name}")
            except Exception as ex:
                print(f"[RUANA][DB] Aviso al renombrar {old_name}→{new_name}: {ex}")
    _repo.registrar_migracion(cursor, 'retador_rename_v1')

def _migrar_competencia_permanencia(db, conn, cursor) -> None:
    """Cola de competencias pendientes de retador + columnas de auditoría en competencia."""
    if _repo.migracion_aplicada(cursor, 'competencia_permanencia_v1'):
        return
    _repo.execute(cursor, """
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
    _repo.execute(cursor, 
        "CREATE INDEX IF NOT EXISTS idx_comp_pend_cp_oficio "
        "ON competencia_pendiente(codigo_postal, oficio, estado)"
    )
    cols = _repo.columnas_tabla(cursor, "competencia")
    for col, def_sql in (
        ('fecha_cierre', 'TIMESTAMP'),
        ('score_titular_final', 'INTEGER'),
        ('score_retador_final', 'INTEGER'),
    ):
        if col not in cols:
            _repo.execute(cursor, f"ALTER TABLE competencia ADD COLUMN {col} {def_sql}")
    _repo.registrar_migracion(cursor, 'competencia_permanencia_v1')

def _migrar_datos_plaza_oficio(db, conn, cursor) -> None:
    """Resuelve conflictos de plaza: si un grupo tiene varios activos del mismo oficio,
    conserva el de mayor score (más antiguo en empate); reasigna el resto o pone en_espera."""
    if _repo.migracion_aplicada(cursor, 'plaza_oficio_v1'):
        return
    _repo.execute(cursor, """
        SELECT grupo_id, oficio, COUNT(*) as cnt
        FROM aliados
        WHERE estado = 'activo' AND grupo_id IS NOT NULL AND oficio IS NOT NULL AND oficio != ''
        GROUP BY grupo_id, oficio
        HAVING COUNT(*) > 1
    """)
    conflictos = cursor.fetchall()
    for grupo_id, oficio, cnt in conflictos:
        _repo.execute(cursor, """
            SELECT id, codigo, score, codigo_postal
            FROM aliados
            WHERE grupo_id = ? AND oficio = ? AND estado = 'activo'
            ORDER BY score DESC, creado_en ASC
        """, (grupo_id, oficio))
        aliados_conflicto = cursor.fetchall()
        for aliado in aliados_conflicto[1:]:
            aliado_id, aliado_codigo, aliado_score, codigo_postal = aliado
            _repo.execute(cursor, """
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
                _repo.execute(cursor, "UPDATE aliados SET grupo_id = ? WHERE id = ?", (alt_row[0], aliado_id))
            else:
                _repo.execute(cursor, 
                    "SELECT COUNT(*) FROM grupos WHERE codigo_postal = ? AND estado = 'activo'",
                    (codigo_postal,)
                )
                n_grupos = cursor.fetchone()[0] or 0
                if n_grupos < MAX_GRUPOS_POR_CP:
                    from core.services import grupo_service
                    new_grupo_id = grupo_service._insertar_grupo_nombre_unico(
                        db, cursor, codigo_postal
                    )
                    _repo.execute(cursor, "UPDATE aliados SET grupo_id = ? WHERE id = ?", (new_grupo_id, aliado_id))
                else:
                    _repo.execute(cursor, 
                        "UPDATE aliados SET grupo_id = NULL, estado = 'en_espera' WHERE id = ?",
                        (aliado_id,)
                    )
    _repo.registrar_migracion(cursor, 'plaza_oficio_v1')

def _migrar_drop_especializaciones(db, conn, cursor) -> None:
    """Elimina las columnas especializacion y especializaciones de aliados (ya no se usan)."""
    if _repo.migracion_aplicada(cursor, 'drop_especializaciones_v1'):
        return
    cols = _repo.columnas_tabla(cursor, "aliados")
    for col in ('especializacion', 'especializaciones'):
        if col in cols:
            try:
                _repo.execute(cursor, f"ALTER TABLE aliados DROP COLUMN {col}")
            except Exception as ex:
                print(f"[RUANA][DB] Aviso al eliminar columna {col}: {ex}")
    _repo.registrar_migracion(cursor, 'drop_especializaciones_v1')

def _migrar_referidos_origen(db, conn, cursor) -> None:
    """Añade columna origen a referidos (trazabilidad del vínculo invitador→referido)."""
    columnas = _repo.columnas_tabla(cursor, "referidos")
    if 'origen' not in columnas:
        _repo.execute(cursor, "ALTER TABLE referidos ADD COLUMN origen TEXT DEFAULT ''")

def _migrar_invitaciones_oficio_codigo_referido(db, conn, cursor) -> None:
    """Añade codigo_referido a invitaciones_oficio para backfill del árbol."""
    columnas = _repo.columnas_tabla(cursor, "invitaciones_oficio")
    if 'codigo_referido' not in columnas:
        _repo.execute(cursor, "ALTER TABLE invitaciones_oficio ADD COLUMN codigo_referido TEXT DEFAULT ''")

def _migrar_aliados_invitado_por(db, conn, cursor) -> None:
    """Añade invitado_por_codigo e invitado_origen en aliados (fuente del linaje)."""
    if db.backend == "postgres":
        _repo.execute(cursor, "ALTER TABLE aliados ADD COLUMN IF NOT EXISTS invitado_por_codigo TEXT DEFAULT NULL")
        _repo.execute(cursor, "ALTER TABLE aliados ADD COLUMN IF NOT EXISTS invitado_origen TEXT DEFAULT ''")
    else:
        columnas = _repo.columnas_tabla(cursor, "aliados")
        if 'invitado_por_codigo' not in columnas:
            _repo.execute(cursor, "ALTER TABLE aliados ADD COLUMN invitado_por_codigo TEXT DEFAULT NULL")
        if 'invitado_origen' not in columnas:
            _repo.execute(cursor, "ALTER TABLE aliados ADD COLUMN invitado_origen TEXT DEFAULT ''")
    try:
        _repo.execute(cursor, 
            "CREATE INDEX IF NOT EXISTS idx_aliados_invitado_por ON aliados(invitado_por_codigo)"
        )
    except Exception:
        pass

def _migrar_invitaciones_solicitud_id(db, conn, cursor) -> None:
    """Vincula invitaciones «Conozco a alguien» con la solicitud de origen."""
    try:
        if db.backend == "postgres":
            _repo.execute(cursor, 
                "ALTER TABLE invitaciones ADD COLUMN IF NOT EXISTS solicitud_id INTEGER"
            )
        else:
            columnas = _repo.columnas_tabla(cursor, "invitaciones")
            if 'solicitud_id' not in columnas:
                _repo.execute(cursor, "ALTER TABLE invitaciones ADD COLUMN solicitud_id INTEGER")
        _repo.execute(cursor, 
            "CREATE INDEX IF NOT EXISTS idx_invitaciones_solicitud_id ON invitaciones(solicitud_id)"
        )
    except Exception as ex:
        print(f"[RUANA][DB] Aviso migrar invitaciones.solicitud_id: {ex}")

def _migrar_invitaciones_crecimiento_grupo(db, conn, cursor) -> None:
    """Campos para invitaciones de crecimiento orgánico de grupo."""
    try:
        if db.backend == "postgres":
            _repo.execute(cursor,
                "ALTER TABLE invitaciones ADD COLUMN IF NOT EXISTS grupo_id BIGINT"
            )
            _repo.execute(cursor,
                "ALTER TABLE invitaciones ADD COLUMN IF NOT EXISTS tipo TEXT DEFAULT 'ampliar_red'"
            )
        else:
            columnas = _repo.columnas_tabla(cursor, "invitaciones")
            if 'grupo_id' not in columnas:
                _repo.execute(cursor, "ALTER TABLE invitaciones ADD COLUMN grupo_id INTEGER")
            if 'tipo' not in columnas:
                _repo.execute(cursor,
                    "ALTER TABLE invitaciones ADD COLUMN tipo TEXT DEFAULT 'ampliar_red'"
                )
        _repo.execute(cursor,
            "CREATE INDEX IF NOT EXISTS idx_invitaciones_grupo_id ON invitaciones(grupo_id)"
        )
        _repo.execute(cursor,
            "CREATE INDEX IF NOT EXISTS idx_invitaciones_tipo ON invitaciones(tipo)"
        )
    except Exception as ex:
        print(f"[RUANA][DB] Aviso migrar invitaciones crecimiento grupo: {ex}")

def _migrar_grupo_crecimiento_recompensas(db, conn, cursor) -> None:
    """Tabla de auditoría para recompensas de crecimiento de grupo."""
    try:
        _repo.execute(cursor, """
            CREATE TABLE IF NOT EXISTS grupo_crecimiento_recompensas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invitador_codigo TEXT NOT NULL,
                invitado_codigo TEXT NOT NULL,
                invitacion_codigo TEXT,
                grupo_id INTEGER,
                score_delta INTEGER NOT NULL DEFAULT 5,
                creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(invitador_codigo, invitado_codigo)
            )
        """)
        _repo.execute(cursor,
            "CREATE INDEX IF NOT EXISTS idx_gcr_invitador ON grupo_crecimiento_recompensas(invitador_codigo)"
        )
    except Exception as ex:
        print(f"[RUANA][DB] Aviso migrar grupo_crecimiento_recompensas: {ex}")

def _migrar_solicitudes_candidato(db, conn, cursor) -> None:
    """Campos para candidato pendiente e incorporación del aliado invitado."""
    try:
        if db.backend == "postgres":
            _repo.execute(cursor, 
                "ALTER TABLE solicitudes ADD COLUMN IF NOT EXISTS candidato_por_codigo TEXT"
            )
            _repo.execute(cursor, 
                "ALTER TABLE solicitudes ADD COLUMN IF NOT EXISTS candidato_por_nombre TEXT"
            )
            _repo.execute(cursor, 
                "ALTER TABLE solicitudes ADD COLUMN IF NOT EXISTS candidato_at TIMESTAMP"
            )
            _repo.execute(cursor, 
                "ALTER TABLE solicitudes ADD COLUMN IF NOT EXISTS asignada_a_codigo TEXT"
            )
            _repo.execute(cursor, 
                "ALTER TABLE solicitudes ADD COLUMN IF NOT EXISTS asignada_a_nombre TEXT"
            )
        else:
            columnas = _repo.columnas_tabla(cursor, "solicitudes")
            for col, def_sql in [
                ('candidato_por_codigo', 'TEXT'),
                ('candidato_por_nombre', 'TEXT'),
                ('candidato_at', 'DATETIME'),
                ('asignada_a_codigo', 'TEXT'),
                ('asignada_a_nombre', 'TEXT'),
            ]:
                if col not in columnas:
                    _repo.execute(cursor, f"ALTER TABLE solicitudes ADD COLUMN {col} {def_sql}")
    except Exception as ex:
        print(f"[RUANA][DB] Aviso migrar solicitudes candidato: {ex}")

def _migrar_solicitudes_semanales(db, conn, cursor) -> None:
    """Tablas solicitudes_semanales y solicitudes_semanales_respuestas."""
    if getattr(db, "backend", None) == "postgres":
        return
    try:
        _repo.execute(cursor, """
            CREATE TABLE IF NOT EXISTS solicitudes_semanales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                grupo_id INTEGER NOT NULL,
                solicitante_codigo TEXT NOT NULL,
                solicitante_nombre TEXT NOT NULL,
                oficio TEXT NOT NULL,
                descripcion TEXT DEFAULT '',
                es_oficio_personalizado INTEGER NOT NULL DEFAULT 0,
                semana_inicio TEXT NOT NULL,
                estado TEXT NOT NULL DEFAULT 'activa',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                expira_at TEXT,
                FOREIGN KEY (grupo_id) REFERENCES grupos(id)
            )
        """)
        _repo.execute(cursor, """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_sol_sem_solicitante_semana
            ON solicitudes_semanales(solicitante_codigo, semana_inicio)
        """)
        _repo.execute(cursor, """
            CREATE INDEX IF NOT EXISTS idx_sol_sem_grupo_semana
            ON solicitudes_semanales(grupo_id, semana_inicio, estado)
        """)
        _repo.execute(cursor, """
            CREATE TABLE IF NOT EXISTS solicitudes_semanales_respuestas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                solicitud_semanal_id INTEGER NOT NULL,
                aliado_codigo TEXT NOT NULL,
                aliado_nombre TEXT NOT NULL,
                tipo_respuesta TEXT NOT NULL,
                contacto_id INTEGER,
                invitacion_codigo TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (solicitud_semanal_id) REFERENCES solicitudes_semanales(id),
                UNIQUE(solicitud_semanal_id, aliado_codigo)
            )
        """)
        _repo.execute(cursor, """
            CREATE INDEX IF NOT EXISTS idx_sol_sem_resp_solicitud
            ON solicitudes_semanales_respuestas(solicitud_semanal_id)
        """)
    except Exception as ex:
        print(f"[RUANA][DB] Aviso migrar solicitudes_semanales: {ex}")

def _aplicar_esquema_pin_personal(db, cursor) -> None:
    """DDL de PIN personal en aliados y tabla de recuperación (sin capturar errores)."""
    if db.backend == "postgres":
        _repo.execute(cursor, "ALTER TABLE aliados ADD COLUMN IF NOT EXISTS pin_hash TEXT")
        _repo.execute(cursor, "ALTER TABLE aliados ADD COLUMN IF NOT EXISTS pin_intentos_fallidos INTEGER DEFAULT 0")
        _repo.execute(cursor, "ALTER TABLE aliados ADD COLUMN IF NOT EXISTS pin_bloqueado_hasta TIMESTAMP")
    else:
        if _repo.migracion_aplicada(cursor, 'aliados_pin_personal_v1'):
            return
        columnas = _repo.columnas_tabla(cursor, "aliados")
        if 'pin_hash' not in columnas:
            _repo.execute(cursor, "ALTER TABLE aliados ADD COLUMN pin_hash TEXT")
        if 'pin_intentos_fallidos' not in columnas:
            _repo.execute(cursor, "ALTER TABLE aliados ADD COLUMN pin_intentos_fallidos INTEGER DEFAULT 0")
        if 'pin_bloqueado_hasta' not in columnas:
            _repo.execute(cursor, "ALTER TABLE aliados ADD COLUMN pin_bloqueado_hasta TIMESTAMP")

    id_col = "SERIAL PRIMARY KEY" if db.backend == "postgres" else "INTEGER PRIMARY KEY AUTOINCREMENT"
    _repo.execute(cursor, f"""
        CREATE TABLE IF NOT EXISTS aliado_recuperacion_acceso (
            id {id_col},
            email TEXT NOT NULL,
            codigo_aliado TEXT,
            tipo TEXT NOT NULL,
            otp_hash TEXT NOT NULL,
            otp_salt TEXT NOT NULL,
            expira_en TIMESTAMP NOT NULL,
            usado_en TIMESTAMP,
            intentos_fallidos INTEGER DEFAULT 0,
            verificado INTEGER DEFAULT 0,
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    _repo.execute(cursor, "CREATE INDEX IF NOT EXISTS idx_recuperacion_email ON aliado_recuperacion_acceso(email)")
    _repo.execute(cursor, "CREATE INDEX IF NOT EXISTS idx_recuperacion_codigo ON aliado_recuperacion_acceso(codigo_aliado)")

    if db.backend != "postgres":
        _repo.registrar_migracion(cursor, 'aliados_pin_personal_v1')


def ensure_aliados_pin_schema(db) -> None:
    """Garantiza columnas PIN en Postgres aunque falle el init de esquema al arranque."""
    if db.backend != "postgres":
        return
    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            _aplicar_esquema_pin_personal(db, cursor)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def _migrar_aliados_pin_personal(db, conn, cursor) -> None:
    """Añade PIN personal hasheado y tabla de recuperación de acceso."""
    try:
        _aplicar_esquema_pin_personal(db, cursor)
    except Exception as ex:
        print(f"[RUANA][DB] Aviso migrar aliados_pin_personal: {ex}")

def _migrar_aliados_eliminados(db, conn, cursor) -> None:
    """Tabla de archivo: un único registro por aliado eliminado definitivamente."""
    id_col = "SERIAL PRIMARY KEY" if db.backend == "postgres" else "INTEGER PRIMARY KEY AUTOINCREMENT"
    _repo.execute(cursor, f"""
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
    _repo.execute(cursor, 
        "CREATE INDEX IF NOT EXISTS idx_aliados_eliminados_codigo ON aliados_eliminados(codigo)"
    )
    _repo.execute(cursor, 
        "CREATE INDEX IF NOT EXISTS idx_aliados_eliminados_fecha ON aliados_eliminados(eliminado_en DESC)"
    )


def _migrar_privacidad_rgpd_aliado(db, conn, cursor) -> None:
    """Consentimientos de alta (RGPD) y solicitudes de baja/borrado gestionadas por admin."""
    id_col = "SERIAL PRIMARY KEY" if db.backend == "postgres" else "INTEGER PRIMARY KEY AUTOINCREMENT"
    _repo.execute(cursor, f"""
        CREATE TABLE IF NOT EXISTS consentimientos_aliado (
            id {id_col},
            codigo_aliado TEXT NOT NULL,
            version_documento TEXT NOT NULL,
            aceptado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(codigo_aliado) REFERENCES aliados(codigo)
        )
    """)
    _repo.execute(
        cursor,
        "CREATE INDEX IF NOT EXISTS idx_consentimientos_aliado_codigo ON consentimientos_aliado(codigo_aliado)",
    )
    _repo.execute(cursor, f"""
        CREATE TABLE IF NOT EXISTS solicitudes_baja_aliado (
            id {id_col},
            codigo_aliado TEXT NOT NULL,
            motivo TEXT,
            estado TEXT NOT NULL DEFAULT 'pendiente',
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            admin_codigo TEXT,
            notas_admin TEXT,
            FOREIGN KEY(codigo_aliado) REFERENCES aliados(codigo)
        )
    """)
    _repo.execute(
        cursor,
        "CREATE INDEX IF NOT EXISTS idx_solicitudes_baja_aliado_codigo ON solicitudes_baja_aliado(codigo_aliado)",
    )
    _repo.execute(
        cursor,
        "CREATE INDEX IF NOT EXISTS idx_solicitudes_baja_aliado_estado ON solicitudes_baja_aliado(estado)",
    )


def _init_postgres_schema(db):
    """Crea tablas/migraciones pendientes en Supabase/Postgres al arrancar."""
    conn = None
    try:
        conn = db._connect()
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
        db._migrar_aliados_pin_personal(conn, cursor)
        db._migrar_aliados_foto_perfil(conn, cursor)
        db._migrar_aliados_invitado_por(conn, cursor)
        db._migrar_invitaciones_solicitud_id(conn, cursor)
        db._migrar_solicitudes_candidato(conn, cursor)
        db._migrar_solicitudes_semanales(conn, cursor)
        db._migrar_contactos_es_urgente(conn, cursor)
        db._migrar_negociacion_guiada(conn, cursor)
        db._migrar_acuerdo_cierre_bilateral(conn, cursor)
        db._migrar_importe_acordado(conn, cursor)
        db._migrar_aliado_accesos_dia(conn, cursor)
        db._migrar_centro_comunicacion_ruana(conn, cursor)
        db._migrar_aliados_eliminados(conn, cursor)
        db._migrar_privacidad_rgpd_aliado(conn, cursor)
        db._migrar_stripe_pagos(conn, cursor)
        db._migrar_payment_conflicts(conn, cursor)
        db._migrar_estado_financiero(conn, cursor)
        db._migrar_financial_fase02(conn, cursor)
        db._migrar_financial_fase03(conn, cursor)
        db._migrar_financial_fase03_1(conn, cursor)
        db._migrar_financial_fase03_2(conn, cursor)
        db._migrar_financial_fase04_conflicts(conn, cursor)
        db._migrar_financial_fase05_refunds(conn, cursor)
        db._migrar_financial_fase06_disputes(conn, cursor)
        db._migrar_financial_fase07_reconciliation(conn, cursor)
        db._migrar_financial_fase08_ledger(conn, cursor)
        db._migrar_financial_fase09_admin_panel(conn, cursor)
        db._migrar_financial_fase10_security(conn, cursor)
        db._migrar_financial_fase11_automation(conn, cursor)
        db._migrar_financial_fase13_p0_ledger_immutability(conn, cursor)
        conn.commit()
        print("[RUANA][DB] Esquema Postgres verificado (core + triggers ledger FASE 13A)")
    except Exception as e:
        print(f"[RUANA][DB] Error inicializando esquema Postgres: {e}")
    finally:
        if conn:
            conn.close()

