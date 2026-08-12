"""
Repositorio de Solicitudes (Campamento Base).

Acceso a datos de solicitudes (y lecturas auxiliares de aliados/invitaciones/grupos
ligadas al ciclo de solicitud).
Sin reglas de negocio: solo lectura/escritura.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple


class SolicitudRepo:
    """Operaciones de persistencia del dominio solicitud."""

    def columnas_solicitudes(self, cursor) -> List[str]:
        cursor.execute("PRAGMA table_info(solicitudes)")
        return [r[1] for r in cursor.fetchall()]

    def select_grupo_estado(self, cursor, solicitud_id: int) -> Optional[Tuple[Any, Any]]:
        cursor.execute(
            "SELECT grupo_id, estado FROM solicitudes WHERE id = ?",
            (int(solicitud_id),),
        )
        row = cursor.fetchone()
        return (row[0], row[1]) if row else None

    def select_aliado_grupo_nombre(
        self, cursor, codigo: str
    ) -> Optional[Tuple[Any, Any]]:
        cursor.execute(
            "SELECT grupo_id, nombre FROM aliados WHERE codigo = ?",
            (codigo,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return (row[0], row[1] or "")

    def select_aliado_grupo_id(self, cursor, codigo: str) -> Optional[Any]:
        cursor.execute("SELECT grupo_id FROM aliados WHERE codigo = ?", (codigo,))
        row = cursor.fetchone()
        return row[0] if row else None

    def select_aliado_codigo_nombre_por_id(
        self, cursor, aliado_id: int
    ) -> Optional[Tuple[Any, Any]]:
        cursor.execute(
            "SELECT codigo, nombre FROM aliados WHERE id = ?",
            (int(aliado_id),),
        )
        row = cursor.fetchone()
        return (row[0], row[1] or "") if row else None

    def select_aliado_codigo_nombre(
        self, cursor, codigo: str
    ) -> Optional[Any]:
        cursor.execute(
            "SELECT codigo, nombre FROM aliados WHERE codigo = ?",
            (codigo,),
        )
        return cursor.fetchone()

    def update_candidato_pendiente(
        self, cursor, solicitud_id: int, codigo_proponente: str, nombre: str
    ) -> int:
        cursor.execute(
            """
            UPDATE solicitudes
            SET estado = 'candidato_pendiente',
                candidato_por_codigo = ?,
                candidato_por_nombre = ?,
                candidato_at = CURRENT_TIMESTAMP
            WHERE id = ? AND estado = 'pendiente'
            """,
            (codigo_proponente, nombre, int(solicitud_id)),
        )
        return cursor.rowcount

    def select_invitacion_solicitud_id(
        self, cursor, codigo_invitacion: str
    ) -> Optional[Any]:
        cursor.execute(
            """
            SELECT i.solicitud_id, i.codigo
            FROM invitaciones i
            WHERE i.codigo = ?
            """,
            (codigo_invitacion,),
        )
        return cursor.fetchone()

    def select_solicitud_basica(self, cursor, solicitud_id: int) -> Optional[Any]:
        cursor.execute(
            """
            SELECT id, oficio, descripcion, estado, solicitante_codigo
            FROM solicitudes WHERE id = ?
            """,
            (int(solicitud_id),),
        )
        return cursor.fetchone()

    def update_asignar_y_pendiente(
        self,
        cursor,
        solicitud_id: int,
        codigo: str,
        nombre: str,
    ) -> None:
        cursor.execute(
            """
            UPDATE solicitudes
            SET estado = 'pendiente',
                asignada_a_codigo = ?,
                asignada_a_nombre = ?
            WHERE id = ?
            """,
            (codigo, nombre or "", int(solicitud_id)),
        )

    def update_asignar_si_vacio(
        self,
        cursor,
        solicitud_id: int,
        codigo: str,
        nombre: str,
    ) -> None:
        cursor.execute(
            """
            UPDATE solicitudes
            SET asignada_a_codigo = COALESCE(asignada_a_codigo, ?),
                asignada_a_nombre = COALESCE(asignada_a_nombre, ?)
            WHERE id = ?
            """,
            (codigo, nombre or "", int(solicitud_id)),
        )

    def insertar_pendiente(
        self,
        cursor,
        grupo_id: Any,
        codigo: str,
        nombre: str,
        oficio: str,
        descripcion: str,
    ) -> Any:
        cursor.execute(
            """
            INSERT INTO solicitudes (grupo_id, solicitante_codigo, solicitante_nombre, oficio, descripcion, estado)
            VALUES (?, ?, ?, ?, ?, 'pendiente')
            """,
            (grupo_id, codigo, nombre, oficio, descripcion),
        )
        return cursor.lastrowid

    def listar_activas_grupo_o_asignada(
        self, cursor, codigo: str, grupo_id: Any
    ) -> List[Dict[str, Any]]:
        cursor.execute(
            """
            SELECT id, grupo_id, solicitante_codigo, solicitante_nombre, oficio, descripcion, estado, created_at,
                   asignada_a_codigo, asignada_a_nombre
            FROM solicitudes
            WHERE estado = 'pendiente'
              AND solicitante_codigo != ?
              AND (grupo_id = ? OR asignada_a_codigo = ?)
            ORDER BY created_at DESC
            """,
            (codigo, grupo_id, codigo),
        )
        return [dict(r) for r in cursor.fetchall()]

    def listar_activas_grupo(
        self, cursor, codigo: str, grupo_id: Any
    ) -> List[Dict[str, Any]]:
        cursor.execute(
            """
            SELECT id, grupo_id, solicitante_codigo, solicitante_nombre, oficio, descripcion, estado, created_at
            FROM solicitudes
            WHERE grupo_id = ? AND estado = 'pendiente' AND solicitante_codigo != ?
            ORDER BY created_at DESC
            """,
            (grupo_id, codigo),
        )
        return [dict(r) for r in cursor.fetchall()]

    def listar_activas_asignadas(
        self, cursor, codigo: str
    ) -> List[Dict[str, Any]]:
        cursor.execute(
            """
            SELECT id, grupo_id, solicitante_codigo, solicitante_nombre, oficio, descripcion, estado, created_at,
                   asignada_a_codigo, asignada_a_nombre
            FROM solicitudes
            WHERE estado = 'pendiente' AND asignada_a_codigo = ?
            ORDER BY created_at DESC
            """,
            (codigo,),
        )
        return [dict(r) for r in cursor.fetchall()]

    def listar_propias(
        self, cursor, grupo_id: Any, codigo: str, extra_cols: str = ""
    ) -> List[Dict[str, Any]]:
        cursor.execute(
            f"""
            SELECT id, grupo_id, solicitante_codigo, solicitante_nombre, oficio, descripcion, estado, created_at,
                   atendido_por_codigo, atendido_por_nombre, atendido_at{extra_cols}
            FROM solicitudes
            WHERE grupo_id = ? AND solicitante_codigo = ?
            ORDER BY created_at DESC
            """,
            (grupo_id, codigo),
        )
        return [dict(r) for r in cursor.fetchall()]

    def listar_historial_grupo(
        self, cursor, grupo_id: Any, limite: int, extra_cols: str = ""
    ) -> List[Dict[str, Any]]:
        cursor.execute(
            f"""
            SELECT id, grupo_id, solicitante_codigo, solicitante_nombre, oficio, descripcion, estado, created_at,
                   atendido_por_codigo, atendido_por_nombre, atendido_at{extra_cols}
            FROM solicitudes
            WHERE grupo_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (grupo_id, limite),
        )
        return [dict(r) for r in cursor.fetchall()]

    def listar_pendientes_por_cp(
        self, cursor, codigo_postal: str
    ) -> List[Dict[str, Any]]:
        cursor.execute(
            """
            SELECT s.id, s.grupo_id, s.solicitante_codigo, s.solicitante_nombre, s.oficio, s.descripcion,
                   s.estado, s.created_at, g.nombre AS grupo_nombre
            FROM solicitudes s
            JOIN grupos g ON g.id = s.grupo_id
            WHERE g.codigo_postal = ? AND g.estado = 'activo' AND s.estado = 'pendiente'
            ORDER BY s.created_at DESC
            """,
            (codigo_postal,),
        )
        return [dict(r) for r in cursor.fetchall()]

    def update_atendida(
        self, cursor, solicitud_id: int, codigo: str, nombre: str
    ) -> int:
        cursor.execute(
            """
            UPDATE solicitudes
            SET estado = 'atendida', atendido_por_codigo = ?, atendido_por_nombre = ?, atendido_at = CURRENT_TIMESTAMP
            WHERE id = ? AND estado = 'pendiente'
            """,
            (codigo, nombre, solicitud_id),
        )
        return cursor.rowcount

    def select_atendido_info(
        self, cursor, solicitud_id: int
    ) -> Optional[Tuple[Any, Any, Any, Any]]:
        cursor.execute(
            "SELECT id, estado, atendido_por_codigo, atendido_at FROM solicitudes WHERE id = ?",
            (solicitud_id,),
        )
        row = cursor.fetchone()
        return (row[0], row[1], row[2], row[3]) if row else None

    def update_atendida_admin(
        self, cursor, solicitud_id: int, codigo: str, nombre: str
    ) -> None:
        cursor.execute(
            """
            UPDATE solicitudes
            SET estado = 'atendida', atendido_por_codigo = ?, atendido_por_nombre = ?, atendido_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (codigo, nombre, solicitud_id),
        )

    def update_rellenar_atendido_admin(
        self, cursor, solicitud_id: int, codigo: str, nombre: str
    ) -> None:
        cursor.execute(
            """
            UPDATE solicitudes
            SET atendido_por_codigo = ?, atendido_por_nombre = ?, atendido_at = COALESCE(atendido_at, CURRENT_TIMESTAMP)
            WHERE id = ?
            """,
            (codigo, nombre, solicitud_id),
        )

    def listar_admin_todas(self, cursor) -> List[Dict[str, Any]]:
        cursor.execute(
            """
            SELECT s.id, s.grupo_id, s.solicitante_codigo, s.solicitante_nombre, s.oficio, s.descripcion,
                   s.estado, s.atendido_por_codigo, s.atendido_por_nombre, s.created_at, s.atendido_at,
                   g.nombre AS grupo_nombre
            FROM solicitudes s
            LEFT JOIN grupos g ON g.id = s.grupo_id
            ORDER BY s.created_at DESC
            """
        )
        return [dict(r) for r in cursor.fetchall()]

    def contar_pendientes(self, cursor) -> int:
        cursor.execute(
            "SELECT COUNT(*) FROM solicitudes WHERE estado = 'pendiente'"
        )
        return cursor.fetchone()[0] or 0

    def contar_enviadas_por_estado(
        self, cursor, codigo: str, estado: str
    ) -> int:
        cursor.execute(
            "SELECT COUNT(*) FROM solicitudes WHERE solicitante_codigo = ? AND estado = ?",
            (codigo, estado),
        )
        return cursor.fetchone()[0] or 0
