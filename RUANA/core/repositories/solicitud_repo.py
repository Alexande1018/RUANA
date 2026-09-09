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
        asignada_a_codigo: Optional[str] = None,
        asignada_a_nombre: Optional[str] = None,
        destino: Optional[str] = None,
        proximidad_codigo: Optional[str] = None,
        proximidad_nombre: Optional[str] = None,
        proximidad_cp: Optional[str] = None,
        proximidad_zona: Optional[str] = None,
        proximidad_estado: Optional[str] = None,
    ) -> Any:
        cursor.execute(
            """
            INSERT INTO solicitudes (
                grupo_id, solicitante_codigo, solicitante_nombre, oficio, descripcion, estado,
                asignada_a_codigo, asignada_a_nombre, destino,
                proximidad_codigo, proximidad_nombre, proximidad_cp, proximidad_zona, proximidad_estado
            )
            VALUES (?, ?, ?, ?, ?, 'pendiente', ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                grupo_id,
                codigo,
                nombre,
                oficio,
                descripcion,
                asignada_a_codigo,
                asignada_a_nombre or "",
                destino,
                proximidad_codigo,
                proximidad_nombre,
                proximidad_cp,
                proximidad_zona,
                proximidad_estado,
            ),
        )
        return cursor.lastrowid

    def select_enrutamiento(self, cursor, solicitud_id: int) -> Optional[Dict[str, Any]]:
        cursor.execute(
            """
            SELECT id, grupo_id, estado, oficio, descripcion,
                   solicitante_codigo, solicitante_nombre,
                   asignada_a_codigo, asignada_a_nombre, destino,
                   proximidad_codigo, proximidad_nombre, proximidad_cp,
                   proximidad_zona, proximidad_estado
            FROM solicitudes
            WHERE id = ?
            """,
            (int(solicitud_id),),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def select_profesional_grupo_oficio(
        self, cursor, grupo_id: Any, excluir_codigo: str
    ) -> List[Dict[str, Any]]:
        cursor.execute(
            """
            SELECT codigo, nombre, oficio, codigo_postal
            FROM aliados
            WHERE grupo_id = ? AND estado = 'activo' AND codigo != ?
            ORDER BY id
            """,
            (grupo_id, excluir_codigo),
        )
        out = []
        for r in cursor.fetchall():
            if hasattr(r, "keys"):
                out.append(dict(r))
            else:
                out.append(
                    {
                        "codigo": r[0],
                        "nombre": r[1],
                        "oficio": r[2],
                        "codigo_postal": r[3],
                    }
                )
        return out

    def listar_codigos_activos_grupo(
        self, cursor, grupo_id: Any, excluir_codigo: Optional[str] = None
    ) -> List[str]:
        if excluir_codigo:
            cursor.execute(
                """
                SELECT codigo FROM aliados
                WHERE grupo_id = ? AND estado = 'activo' AND codigo != ?
                """,
                (grupo_id, excluir_codigo),
            )
        else:
            cursor.execute(
                """
                SELECT codigo FROM aliados
                WHERE grupo_id = ? AND estado = 'activo'
                """,
                (grupo_id,),
            )
        return [str(r[0]).strip() for r in cursor.fetchall() if r[0]]

    def aceptar_proximidad(
        self,
        cursor,
        solicitud_id: int,
        profesional_codigo: str,
        profesional_nombre: str,
    ) -> int:
        cursor.execute(
            """
            UPDATE solicitudes
            SET asignada_a_codigo = ?,
                asignada_a_nombre = ?,
                destino = 'proximidad',
                proximidad_estado = 'aceptada'
            WHERE id = ?
              AND estado = 'pendiente'
              AND COALESCE(proximidad_estado, '') = 'pendiente_aprobacion'
            """,
            (profesional_codigo, profesional_nombre or "", int(solicitud_id)),
        )
        return cursor.rowcount

    def pedir_recomendacion_grupo(self, cursor, solicitud_id: int) -> int:
        cursor.execute(
            """
            UPDATE solicitudes
            SET asignada_a_codigo = NULL,
                asignada_a_nombre = NULL,
                destino = 'buscando_ayuda',
                proximidad_estado = 'rechazada'
            WHERE id = ?
              AND estado = 'pendiente'
              AND COALESCE(proximidad_estado, '') = 'pendiente_aprobacion'
            """,
            (int(solicitud_id),),
        )
        return cursor.rowcount

    def listar_activas_grupo_o_asignada(
        self, cursor, codigo: str, grupo_id: Any
    ) -> List[Dict[str, Any]]:
        cursor.execute(
            """
            SELECT id, grupo_id, solicitante_codigo, solicitante_nombre, oficio, descripcion, estado, created_at,
                   asignada_a_codigo, asignada_a_nombre, destino,
                   proximidad_codigo, proximidad_nombre, proximidad_cp, proximidad_zona, proximidad_estado
            FROM solicitudes
            WHERE estado = 'pendiente'
              AND solicitante_codigo != ?
              AND COALESCE(proximidad_estado, '') != 'pendiente_aprobacion'
              AND (
                asignada_a_codigo = ?
                OR (
                  COALESCE(asignada_a_codigo, '') = ''
                  AND grupo_id = ?
                )
              )
            ORDER BY created_at DESC
            """,
            (codigo, codigo, grupo_id),
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
                   asignada_a_codigo, asignada_a_nombre, destino,
                   proximidad_codigo, proximidad_nombre, proximidad_cp, proximidad_zona, proximidad_estado
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
              AND estado IN ('atendida', 'candidato_pendiente', 'contestada')
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
            WHERE g.codigo_postal = ? AND g.estado = 'activo'
              AND COALESCE(g.tipo, 'territorial') = 'territorial'
              AND s.estado = 'pendiente'
            ORDER BY s.created_at DESC
            """,
            (codigo_postal,),
        )
        return [dict(r) for r in cursor.fetchall()]

    def listar_pendientes_por_grupo(
        self, cursor, grupo_id: int
    ) -> List[Dict[str, Any]]:
        cursor.execute(
            """
            SELECT s.id, s.grupo_id, s.solicitante_codigo, s.solicitante_nombre, s.oficio, s.descripcion,
                   s.estado, s.created_at, g.nombre AS grupo_nombre
            FROM solicitudes s
            JOIN grupos g ON g.id = s.grupo_id
            WHERE s.grupo_id = ? AND g.estado = 'activo' AND s.estado = 'pendiente'
            ORDER BY s.created_at DESC
            """,
            (int(grupo_id),),
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

    def listar_ids_candidatos_vencidos(self, cursor, horas: int) -> List[int]:
        cursor.execute(
            """
            SELECT id FROM solicitudes
            WHERE estado = 'candidato_pendiente'
              AND candidato_at IS NOT NULL
              AND datetime(candidato_at) <= datetime('now', ?)
            """,
            (f"-{int(horas)} hours",),
        )
        return [int(r[0]) for r in cursor.fetchall()]

    def revertir_candidato_a_pendiente(self, cursor, solicitud_id: int) -> int:
        cursor.execute(
            """
            UPDATE solicitudes
            SET estado = 'pendiente',
                candidato_por_codigo = NULL,
                candidato_por_nombre = NULL,
                candidato_at = NULL
            WHERE id = ? AND estado = 'candidato_pendiente'
            """,
            (int(solicitud_id),),
        )
        return cursor.rowcount
