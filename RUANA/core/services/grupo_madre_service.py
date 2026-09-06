"""Lógica de Grupo Madre por ciudad (incubación territorial)."""
from __future__ import annotations

import re
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from core.db_constants import (
    AVISO_CP_INDEPENDIZADO,
    AVISO_GRUPO_MADRE,
    CP_MADUREZ_MIN_ALIADOS,
    CP_MADUREZ_MIN_ENCARGOS,
    CP_MODO_INCUBACION,
    CP_MODO_TERRITORIAL,
    MAX_GRUPOS_POR_CP,
    TIPO_GRUPO_MADRE,
)
from core.repositories.grupo_madre_repo import GrupoMadreRepo
from core.services import territorio_service

_madre_repo = GrupoMadreRepo()


def cp_en_modo_territorial(db, codigo_postal: str) -> bool:
    """True si el CP ya tiene estructura territorial → reglas actuales sin cambios."""
    cp = (codigo_postal or "").strip()
    if not cp:
        return False
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            if _madre_repo.contar_territoriales_activos_por_cp(cursor, cp) > 0:
                return True
            row = _madre_repo.select_cp_estado(cursor, cp)
            if row:
                data = dict(row) if hasattr(row, "keys") else {"modo": row[2] if len(row) > 2 else ""}
                return (data.get("modo") or "") == CP_MODO_TERRITORIAL
            return False
        except Exception:
            return _madre_repo.contar_territoriales_activos_por_cp(cursor, cp) > 0 if cp else False
        finally:
            conn.close()


def contar_grupos_territoriales_activos_por_cp(db, codigo_postal: str) -> int:
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            return _madre_repo.contar_territoriales_activos_por_cp(cursor, codigo_postal)
        except Exception:
            return 0
        finally:
            conn.close()


def _nombre_grupo_madre(ciudad: str) -> str:
    base = re.sub(r"[^A-Za-z0-9]+", "-", (ciudad or "").strip().upper()).strip("-")
    return f"RUANA-{base or 'CIUDAD'}-MADRE"


def obtener_o_crear_grupo_madre(
    db, ciudad: str, provincia: str = ""
) -> Optional[Dict[str, Any]]:
    ciudad_n = territorio_service.normalizar_ciudad(ciudad)
    if not ciudad_n:
        return None
    from core.repositories.grupo_repo import GrupoRepo

    _grupo_repo = GrupoRepo()
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            row = _madre_repo.select_grupo_madre_por_ciudad(cursor, ciudad_n)
            if row:
                return dict(row)
            nombre = _nombre_grupo_madre(ciudad_n)
            if _grupo_repo.existe_nombre(cursor, nombre):
                cursor.execute(
                    "SELECT id FROM grupos WHERE TRIM(nombre) = ? COLLATE NOCASE LIMIT 1",
                    (nombre,),
                )
                existing = cursor.fetchone()
                if existing:
                    gid = existing[0]
                    cursor.execute(
                        "SELECT id, nombre, codigo_postal, ciudad, provincia, estado, fecha_creacion, tipo FROM grupos WHERE id = ?",
                        (gid,),
                    )
                    r2 = cursor.fetchone()
                    return dict(r2) if r2 else None
            gid = _madre_repo.insertar_grupo_madre(cursor, nombre, ciudad_n, provincia)
            conn.commit()
            row = _madre_repo.select_grupo_row(cursor, gid)
            return dict(row) if row else None
        except Exception:
            return None
        finally:
            conn.close()


def plaza_disponible_en_madre(
    db, cursor, grupo_madre_id: int, oficio: str, codigo_postal: str
) -> bool:
    """1 oficio por CP dentro del madre; máx. 5 CP distintos con ese oficio."""
    if not grupo_madre_id or not oficio or not codigo_postal:
        return False
    if _madre_repo.tiene_oficio_en_madre_por_cp(cursor, grupo_madre_id, oficio, codigo_postal):
        return False
    if _madre_repo.contar_oficio_en_madre(cursor, grupo_madre_id, oficio) >= MAX_GRUPOS_POR_CP:
        return False
    return True


def plaza_ocupada_contexto(
    db, grupo_id: int, oficio: str, codigo_postal_aliado: str = "", cursor=None
) -> bool:
    """Dispatcher: territorial estándar vs madre."""
    from core.services import grupo_service

    own_cursor = cursor is None
    if own_cursor:
        conn = db._connect()
        cursor = conn.cursor()
    try:
        row = _madre_repo.select_grupo_row(cursor, grupo_id)
        if not row:
            return True
        data = dict(row) if hasattr(row, "keys") else {"tipo": TIPO_GRUPO_MADRE}
        if (data.get("tipo") or TIPO_GRUPO_MADRE) == TIPO_GRUPO_MADRE:
            return not plaza_disponible_en_madre(
                db, cursor, grupo_id, oficio, codigo_postal_aliado
            )
        return grupo_service._grupo_tiene_oficio(db, cursor, grupo_id, oficio)
    finally:
        if own_cursor:
            conn.close()


def asignar_aliado_territorial_estandar(
    db,
    cursor,
    codigo_postal: str,
    oficio: str,
    grupo_id_invitacion: Optional[int] = None,
) -> Tuple[Optional[int], str, Optional[str]]:
    """
    Lógica territorial existente (sin cambios).
    Devuelve (grupo_id, estado_final, mensaje_lista_espera).
    """
    from core.services import grupo_service

    estado_final = "activo"
    mensaje = None
    grupo_preferido_id = None
    if grupo_id_invitacion:
        if not grupo_service._grupo_tiene_oficio(db, cursor, grupo_id_invitacion, oficio):
            grupo_pref = db.obtener_grupo_por_id(grupo_id_invitacion)
            if grupo_pref and (grupo_pref.get("estado") or "") == "activo":
                if (grupo_pref.get("tipo") or "territorial") != TIPO_GRUPO_MADRE:
                    grupo_preferido_id = grupo_id_invitacion
        if grupo_preferido_id is None and codigo_postal:
            g = db.buscar_grupo_sin_oficio(codigo_postal, oficio)
            if g:
                grupo_preferido_id = g["id"]
    if grupo_preferido_id is None and codigo_postal:
        g = db.buscar_grupo_sin_oficio(codigo_postal, oficio)
        if g:
            grupo_preferido_id = g["id"]
        elif contar_grupos_territoriales_activos_por_cp(db, codigo_postal) >= MAX_GRUPOS_POR_CP:
            estado_final = "en_espera"
            mensaje = db.MENSAJE_LISTA_ESPERA
    return grupo_preferido_id, estado_final, mensaje


def asignar_aliado_incubacion(
    db,
    cursor,
    codigo_postal: str,
    oficio: str,
    grupo_id_invitacion: Optional[int] = None,
) -> Tuple[Optional[int], str, Optional[str]]:
    """Asignación al Grupo Madre de la ciudad."""
    ubic = territorio_service.resolver_ciudad(db, codigo_postal)
    if not ubic or not ubic.get("ciudad"):
        return None, "en_espera", db.MENSAJE_LISTA_ESPERA
    madre = obtener_o_crear_grupo_madre(
        db, ubic["ciudad"], ubic.get("provincia") or ""
    )
    if not madre:
        return None, "en_espera", db.MENSAJE_LISTA_ESPERA

    # Invitador en madre con plaza compatible
    if grupo_id_invitacion:
        inv = db.obtener_grupo_por_id(grupo_id_invitacion)
        if inv and (inv.get("tipo") or "") == TIPO_GRUPO_MADRE:
            if plaza_disponible_en_madre(db, cursor, inv["id"], oficio, codigo_postal):
                return inv["id"], "activo", None

    if plaza_disponible_en_madre(db, cursor, madre["id"], oficio, codigo_postal):
        _madre_repo.upsert_cp_estado(
            cursor,
            codigo_postal,
            ubic["ciudad"],
            CP_MODO_INCUBACION,
            madre["id"],
            _madre_repo.contar_aliados_activos_cp(cursor, codigo_postal),
            _madre_repo.contar_encargos_validos_cp_profesional(cursor, codigo_postal),
            False,
        )
        return madre["id"], "activo", None
    return None, "en_espera", db.MENSAJE_LISTA_ESPERA_MADRE


def resolver_asignacion_registro(
    db,
    cursor,
    codigo_postal: str,
    oficio: str,
    grupo_id_invitacion: Optional[int] = None,
) -> Tuple[Optional[int], str, Optional[str]]:
    if cp_en_modo_territorial(db, codigo_postal):
        return asignar_aliado_territorial_estandar(
            db, cursor, codigo_postal, oficio, grupo_id_invitacion
        )
    ubic = territorio_service.resolver_ciudad(db, codigo_postal)
    if not ubic or not ubic.get("ciudad"):
        return asignar_aliado_territorial_estandar(
            db, cursor, codigo_postal, oficio, grupo_id_invitacion
        )
    return asignar_aliado_incubacion(
        db, cursor, codigo_postal, oficio, grupo_id_invitacion
    )


def asignar_territorial_post_insert(
    db, cursor, aliado_id: int, codigo_postal: str, oficio: str, ciudad: str = "", provincia: str = ""
) -> None:
    """Tras INSERT: asignar grupo territorial (crear si cabe) — lógica estándar."""
    from core.repositories.aliado_repo import AliadoRepo

    _aliado_repo = AliadoRepo()
    grupo_asignar = db.buscar_grupo_sin_oficio(codigo_postal, oficio)
    if grupo_asignar:
        _aliado_repo.update_grupo_id(cursor, grupo_asignar["id"], aliado_id)
    elif contar_grupos_territoriales_activos_por_cp(db, codigo_postal) < MAX_GRUPOS_POR_CP:
        nuevo = db.crear_grupo_en_cp(codigo_postal, ciudad, provincia)
        if isinstance(nuevo, dict) and nuevo.get("id"):
            _aliado_repo.update_grupo_id(cursor, nuevo["id"], aliado_id)


def actualizar_madurez_cp(db, codigo_postal: str) -> Dict[str, Any]:
    cp = (codigo_postal or "").strip()
    if not cp or cp_en_modo_territorial(db, cp):
        return {"status": "skip", "motivo": "territorial"}
    ubic = territorio_service.resolver_ciudad(db, cp)
    if not ubic or not ubic.get("ciudad"):
        return {"status": "skip", "motivo": "sin_ciudad"}
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            n_aliados = _madre_repo.contar_aliados_activos_cp(cursor, cp)
            n_encargos = _madre_repo.contar_encargos_validos_cp_profesional(cursor, cp)
            listo = n_aliados >= CP_MADUREZ_MIN_ALIADOS and n_encargos >= CP_MADUREZ_MIN_ENCARGOS
            madre = _madre_repo.select_grupo_madre_por_ciudad(cursor, ubic["ciudad"])
            madre_id = madre["id"] if madre and hasattr(madre, "keys") else (madre[0] if madre else None)
            _madre_repo.upsert_cp_estado(
                cursor, cp, ubic["ciudad"], CP_MODO_INCUBACION, madre_id,
                n_aliados, n_encargos, listo,
            )
            if listo and not _madre_repo.existe_solicitud_pendiente_cp(cursor, cp):
                _madre_repo.insertar_solicitud_independencia(
                    cursor, cp, ubic["ciudad"], n_aliados, n_encargos
                )
            conn.commit()
            return {
                "status": "ok",
                "aliados_activos": n_aliados,
                "encargos_validos": n_encargos,
                "listo_independizar": listo,
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}
        finally:
            conn.close()


def info_madurez_cp(db, codigo_postal: str) -> Optional[Dict[str, Any]]:
    cp = (codigo_postal or "").strip()
    if not cp:
        return None
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            row = _madre_repo.select_cp_estado(cursor, cp)
            if row:
                d = dict(row)
            else:
                n_a = _madre_repo.contar_aliados_activos_cp(cursor, cp)
                n_e = _madre_repo.contar_encargos_validos_cp_profesional(cursor, cp)
                d = {
                    "aliados_activos": n_a,
                    "encargos_validos": n_e,
                    "listo_independizar": int(
                        n_a >= CP_MADUREZ_MIN_ALIADOS and n_e >= CP_MADUREZ_MIN_ENCARGOS
                    ),
                }
            return {
                "aliados": int(d.get("aliados_activos") or 0),
                "aliados_requeridos": CP_MADUREZ_MIN_ALIADOS,
                "encargos": int(d.get("encargos_validos") or 0),
                "encargos_requeridos": CP_MADUREZ_MIN_ENCARGOS,
                "listo_independizar": bool(d.get("listo_independizar")),
            }
        except Exception:
            return None
        finally:
            conn.close()


def debe_mostrar_aviso_madre(db, codigo_aliado: str, grupo_id: Optional[int]) -> bool:
    if not grupo_id:
        return False
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            row = _madre_repo.select_grupo_row(cursor, grupo_id)
            if not row:
                return False
            tipo = row["tipo"] if hasattr(row, "keys") else row[7]
            if tipo != TIPO_GRUPO_MADRE:
                return False
            return not _madre_repo.tiene_aviso_visto(cursor, codigo_aliado, AVISO_GRUPO_MADRE)
        except Exception:
            return False
        finally:
            conn.close()


def marcar_aviso_visto(db, codigo_aliado: str, aviso_tipo: str) -> Dict[str, Any]:
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            _madre_repo.aviso_visto(cursor, codigo_aliado, aviso_tipo)
            conn.commit()
            return {"status": "success"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
        finally:
            conn.close()


def territorio_modo_aliado(db, codigo_postal: str, grupo_id: Optional[int]) -> str:
    if cp_en_modo_territorial(db, codigo_postal or ""):
        return CP_MODO_TERRITORIAL
    if grupo_id:
        g = db.obtener_grupo_por_id(grupo_id)
        if g and (g.get("tipo") or "") == TIPO_GRUPO_MADRE:
            return CP_MODO_INCUBACION
    return CP_MODO_TERRITORIAL if cp_en_modo_territorial(db, codigo_postal or "") else CP_MODO_INCUBACION


def aprobar_independencia_cp(
    db, codigo_postal: str, admin_codigo: str = "admin"
) -> Dict[str, Any]:
    """
    Crea estructura territorial estándar y migra aliados del madre
    usando la misma lógica de plazas/grupos que el registro territorial.
    """
    from core.repositories.aliado_repo import AliadoRepo
    from core.services import notificacion_service

    cp = (codigo_postal or "").strip()
    ubic = territorio_service.resolver_ciudad(db, cp)
    if not ubic:
        return {"status": "error", "message": "No se pudo resolver la ciudad del CP"}

    _aliado_repo = AliadoRepo()
    migrados: List[str] = []
    en_espera: List[str] = []

    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            madre = _madre_repo.select_grupo_madre_por_ciudad(cursor, ubic["ciudad"])
            if not madre:
                return {"status": "error", "message": "No hay Grupo Madre para esta ciudad"}
            madre_id = madre["id"] if hasattr(madre, "keys") else madre[0]
            filas = _madre_repo.listar_aliados_activos_madre_por_cp(cursor, madre_id, cp)
            if not filas:
                return {"status": "error", "message": "No hay aliados activos de ese CP en incubación"}

            for row in filas:
                data = dict(row) if hasattr(row, "keys") else {
                    "id": row[0], "codigo": row[1], "oficio": row[2],
                }
                aid = data["id"]
                cod = data["codigo"]
                oficio = (data.get("oficio") or "").strip()
                g_pref, estado, _ = asignar_aliado_territorial_estandar(
                    db, cursor, cp, oficio, None
                )
                if estado == "en_espera" or not g_pref:
                    if contar_grupos_territoriales_activos_por_cp(db, cp) < MAX_GRUPOS_POR_CP:
                        asignar_territorial_post_insert(
                            db, cursor, aid, cp, oficio,
                            ubic["ciudad"], ubic.get("provincia") or "",
                        )
                        cursor.execute("SELECT grupo_id FROM aliados WHERE id = ?", (aid,))
                        r = cursor.fetchone()
                        if r and r[0]:
                            migrados.append(cod)
                        else:
                            cursor.execute(
                                "UPDATE aliados SET estado = 'en_espera', grupo_id = NULL WHERE id = ?",
                                (aid,),
                            )
                            en_espera.append(cod)
                    else:
                        cursor.execute(
                            "UPDATE aliados SET estado = 'en_espera', grupo_id = NULL WHERE id = ?",
                            (aid,),
                        )
                        en_espera.append(cod)
                else:
                    _aliado_repo.update_grupo_id(cursor, g_pref, aid)
                    migrados.append(cod)

            _madre_repo.marcar_cp_territorial(cursor, cp)
            cursor.execute(
                """
                UPDATE cp_independencia_solicitudes
                SET estado = 'aprobada', resuelto_en = CURRENT_TIMESTAMP, resuelto_por = ?
                WHERE codigo_postal = ? AND estado = 'pendiente'
                """,
                (admin_codigo, cp),
            )
            conn.commit()
        except Exception as e:
            if conn:
                conn.rollback()
            return {"status": "error", "message": str(e)}
        finally:
            if conn:
                conn.close()

    for cod in migrados:
        notificacion_service.crear_notificacion_aliado(
            db,
            cod,
            tipo="cp_independizado",
            titulo="Tu zona ha crecido",
            mensaje=(
                f"Tu código postal {cp} ya tiene su propio Grupo RUANA. "
                "A partir de ahora formas parte de la red territorial de tu zona."
            ),
            metadata={"codigo_postal": cp},
        )
        marcar_aviso_visto(db, cod, AVISO_CP_INDEPENDIZADO)

    return {
        "status": "success",
        "migrados": migrados,
        "en_espera": en_espera,
        "codigo_postal": cp,
    }


def posponer_independencia_cp(
    db, codigo_postal: str, admin_codigo: str = "admin", notas: str = ""
) -> Dict[str, Any]:
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE cp_independencia_solicitudes
                SET estado = 'pospuesta', resuelto_en = CURRENT_TIMESTAMP,
                    resuelto_por = ?, notas_admin = ?
                WHERE codigo_postal = ? AND estado = 'pendiente'
                """,
                (admin_codigo, notas, codigo_postal.strip()),
            )
            conn.commit()
            return {"status": "success"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
        finally:
            conn.close()


def listar_grupos_madre_admin(db) -> List[Dict[str, Any]]:
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            return [dict(r) for r in _madre_repo.listar_grupos_madre(cursor)]
        except Exception:
            return []
        finally:
            conn.close()


def listar_cp_madurez_admin(db, modo: Optional[str] = None) -> List[Dict[str, Any]]:
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            return [dict(r) for r in _madre_repo.listar_cp_madurez(cursor, modo)]
        except Exception:
            return []
        finally:
            conn.close()


def listar_independencia_pendientes(db) -> List[Dict[str, Any]]:
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            return [dict(r) for r in _madre_repo.listar_solicitudes_pendientes(cursor)]
        except Exception:
            return []
        finally:
            conn.close()
