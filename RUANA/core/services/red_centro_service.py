"""Piloto reversible «Red Centro» (Madrid + Toledo).

Capa NUEVA y aislada que conecta operativamente a los aliados validados de la
Comunidad de Madrid (CP 28xxx) y de la provincia de Toledo (CP 45xxx) para que
se pasen encargos entre oficios cuando su grupo territorial no tiene el oficio
pedido ni hay nadie «cercano» según la lógica de proximidad existente.

Garantías de diseño (cubiertas por tests en ``tests/test_red_centro_piloto.py``):

* Solo escribe en sus propias tablas: ``red_piloto`` y ``red_piloto_miembros``.
  Nunca modifica ``aliados``, ``grupos``, plazas, score, competencia, pagos,
  comisiones, negociación ni historial.
* Apagado por defecto: sin ``RED_CENTRO_ENABLED=1`` no hace nada aunque haya
  una red activa en BD.
* Reparto: el encargo sigue yendo primero al profesional del oficio dentro del
  grupo y después al cercano de la lógica actual. Red Centro solo actúa como
  último recurso y devuelve como máximo ``RED_CENTRO_MAX_CANDIDATOS`` del
  oficio pedido, ordenados por proximidad de CP. Nunca reparte a todos.
* Incorporación automática e idempotente (UNIQUE red_id + aliado_codigo).
* Reversión: desactiva la red y borra SOLO sus miembros; verifica contra la
  instantánea tomada al activar que la organización original sigue idéntica.
* Aviso de bienvenida (modal) una sola vez por aliado, persistido en backend.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

NOMBRE_RED = "Red Centro"
SLUG_RED = "red_centro"
ESTADO_ACTIVA = "activa"
ESTADO_REVERTIDA = "revertida"

CP_ELEGIBLE_RE = re.compile(r"^(28|45)\d{3}$")
ESTADOS_GRUPO_OPERATIVOS = ("activo", "en_competencia")
TIPO_GRUPO_TERRITORIAL = "territorial"

ACCIONES_AVISO = ("cerrar", "aceptar", "recomendar", "invitar")
ETIQUETA_PROXIMIDAD_RED = "Red Centro (Madrid y Toledo)"

# Campos que definen la «organización» de un aliado / grupo. La reversión
# compara exactamente estos campos contra la instantánea.
CAMPOS_ORG_ALIADO = (
    "codigo", "oficio", "especializacion", "especializaciones", "codigo_postal",
    "grupo_id", "estado", "score", "derrotas_competencia", "ciclos_consecutivos",
)
CAMPOS_ORG_GRUPO = ("id", "nombre", "codigo_postal", "ciudad", "provincia", "estado", "tipo")


# --- Flags ---------------------------------------------------------------------

def _env_bool(nombre: str, defecto: bool) -> bool:
    val = os.environ.get(nombre)
    if val is None or str(val).strip() == "":
        return defecto
    return str(val).strip().lower() in ("1", "true", "yes", "si", "sí", "on")


def piloto_habilitado() -> bool:
    """Flag maestro. Por defecto APAGADO."""
    return _env_bool("RED_CENTRO_ENABLED", False)


def aviso_habilitado() -> bool:
    """Modal de bienvenida: ligado al piloto y desactivable por separado."""
    return piloto_habilitado() and _env_bool("RED_CENTRO_AVISO_ENABLED", True)


def max_candidatos() -> int:
    try:
        n = int(os.environ.get("RED_CENTRO_MAX_CANDIDATOS", "3"))
    except (TypeError, ValueError):
        n = 3
    return max(1, min(n, 10))


def cp_elegible(codigo_postal: Any) -> bool:
    return bool(CP_ELEGIBLE_RE.match(str(codigo_postal or "").strip()))


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --- Esquema -------------------------------------------------------------------

_ESQUEMA_LISTO: set = set()


def _es_pg(db) -> bool:
    return getattr(db, "backend", None) == "postgres"


def asegurar_esquema(db, cursor) -> None:
    """Crea las tablas del piloto si no existen (aditivo, no toca otras tablas)."""
    id_col = "BIGSERIAL PRIMARY KEY" if _es_pg(db) else "INTEGER PRIMARY KEY AUTOINCREMENT"
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS red_piloto (
            id {id_col},
            slug TEXT NOT NULL,
            nombre TEXT NOT NULL,
            estado TEXT NOT NULL DEFAULT 'activa',
            snapshot_json TEXT NOT NULL,
            snapshot_sha256 TEXT NOT NULL,
            activado_por TEXT,
            activado_at TEXT NOT NULL,
            desactivado_por TEXT,
            desactivado_at TEXT,
            verificacion_json TEXT
        )
        """
    )
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS red_piloto_miembros (
            id {id_col},
            red_id INTEGER NOT NULL,
            aliado_codigo TEXT NOT NULL,
            origen TEXT NOT NULL DEFAULT 'inicial',
            incorporado_at TEXT NOT NULL,
            aviso_red_centro_visto_at TEXT,
            aviso_red_centro_accion TEXT,
            UNIQUE (red_id, aliado_codigo)
        )
        """
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_red_piloto_estado ON red_piloto(slug, estado)"
    )
    if _es_pg(db):
        for tabla in ("red_piloto", "red_piloto_miembros"):
            try:
                cursor.execute(f"ALTER TABLE {tabla} ENABLE ROW LEVEL SECURITY")
            except Exception:
                logger.warning("[RUANA][RED_CENTRO] No se pudo activar RLS en %s", tabla)


def _con_conexion(db, fn):
    with db._lock:
        conn = db._connect()
        try:
            if not _es_pg(db):
                conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            clave = (getattr(db, "backend", None), str(getattr(db, "db_path", "") or id(db)))
            if clave not in _ESQUEMA_LISTO:
                asegurar_esquema(db, cursor)
                conn.commit()
                _ESQUEMA_LISTO.add(clave)
            result = fn(conn, cursor)
            conn.commit()
            return result
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        finally:
            try:
                conn.close()
            except Exception:
                pass


def _dict(row: Any) -> Dict[str, Any]:
    if row is None:
        return {}
    return dict(row) if not isinstance(row, dict) else row


def _tabla_existe(db, cursor, tabla: str) -> bool:
    try:
        if _es_pg(db):
            cursor.execute("SELECT to_regclass(?) AS t", (f"public.{tabla}",))
            row = _dict(cursor.fetchone())
            return bool(row.get("t"))
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (tabla,))
        return cursor.fetchone() is not None
    except Exception:
        return False


# --- Instantánea de organización --------------------------------------------------

def _normalizar(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, (int, float, bool)):
        return v
    try:
        from decimal import Decimal
        if isinstance(v, Decimal):
            return float(v)
    except Exception:
        pass
    return str(v)


def capturar_organizacion(db, cursor) -> Dict[str, Any]:
    """Foto canónica (ordenada) de aliados, grupos y plazas cerradas. Solo lectura."""
    cursor.execute("SELECT * FROM aliados")
    aliados = []
    for r in cursor.fetchall() or []:
        d = _dict(r)
        aliados.append({k: _normalizar(d.get(k)) for k in CAMPOS_ORG_ALIADO if k in d})
    aliados.sort(key=lambda x: str(x.get("codigo")))
    cursor.execute("SELECT * FROM grupos")
    grupos = []
    for r in cursor.fetchall() or []:
        d = _dict(r)
        grupos.append({k: _normalizar(d.get(k)) for k in CAMPOS_ORG_GRUPO if k in d})
    grupos.sort(key=lambda x: int(x.get("id") or 0))
    cerrados: List[Dict[str, Any]] = []
    if _tabla_existe(db, cursor, "grupo_oficio_cerrado"):
        cursor.execute("SELECT * FROM grupo_oficio_cerrado")
        for r in cursor.fetchall() or []:
            d = _dict(r)
            d.pop("id", None)
            cerrados.append({k: _normalizar(v) for k, v in sorted(d.items())})
        cerrados.sort(key=lambda x: json.dumps(x, sort_keys=True, ensure_ascii=False))
    return {"aliados": aliados, "grupos": grupos, "grupo_oficio_cerrado": cerrados}


def checksum(org: Dict[str, Any]) -> str:
    canon = json.dumps(org, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def comparar_organizacion(original: Dict[str, Any], actual: Dict[str, Any]) -> Dict[str, Any]:
    """Compara solo lo que existía en la instantánea. Las altas nuevas no cuentan
    como diferencia (no se borran ni se tocan)."""
    dif: List[Dict[str, Any]] = []
    act_al = {str(a.get("codigo")): a for a in actual.get("aliados") or []}
    for a in original.get("aliados") or []:
        cod = str(a.get("codigo"))
        cur = act_al.get(cod)
        if cur is None:
            dif.append({"tipo": "aliado_ausente", "codigo": cod})
            continue
        for k, v in a.items():
            if cur.get(k) != v:
                dif.append({"tipo": "aliado_campo", "codigo": cod, "campo": k,
                            "antes": v, "ahora": cur.get(k)})
    act_gr = {str(g.get("id")): g for g in actual.get("grupos") or []}
    for g in original.get("grupos") or []:
        gid = str(g.get("id"))
        cur = act_gr.get(gid)
        if cur is None:
            dif.append({"tipo": "grupo_ausente", "grupo_id": gid})
            continue
        for k, v in g.items():
            if cur.get(k) != v:
                dif.append({"tipo": "grupo_campo", "grupo_id": gid, "campo": k,
                            "antes": v, "ahora": cur.get(k)})
    orig_c = {json.dumps(x, sort_keys=True) for x in original.get("grupo_oficio_cerrado") or []}
    act_c = {json.dumps(x, sort_keys=True) for x in actual.get("grupo_oficio_cerrado") or []}
    for x in sorted(orig_c - act_c):
        dif.append({"tipo": "plaza_cerrada_ausente", "fila": json.loads(x)})
    # Subconjunto actual restringido a lo que había → mismo checksum si idéntico.
    cods = {str(a.get("codigo")) for a in original.get("aliados") or []}
    gids = {str(g.get("id")) for g in original.get("grupos") or []}
    sub = {
        "aliados": [{k: act_al[c].get(k) for k in a} for a in original.get("aliados") or []
                    for c in [str(a.get("codigo"))] if c in act_al],
        "grupos": [{k: act_gr[i].get(k) for k in g} for g in original.get("grupos") or []
                   for i in [str(g.get("id"))] if i in act_gr],
        "grupo_oficio_cerrado": sorted(
            [json.loads(x) for x in (orig_c & act_c)],
            key=lambda x: json.dumps(x, sort_keys=True, ensure_ascii=False),
        ),
    }
    altas = sorted(c for c in act_al if c not in cods)
    grupos_nuevos = sorted(i for i in act_gr if i not in gids)
    return {
        "identica": not dif,
        "diferencias": dif,
        "checksum_original": checksum(original),
        "checksum_actual_subconjunto": checksum(sub),
        "altas_conservadas": altas,
        "grupos_nuevos_conservados": grupos_nuevos,
    }


# --- Elegibilidad y miembros -------------------------------------------------------

def _sql_elegibles() -> str:
    return (
        "SELECT a.codigo, a.oficio, a.codigo_postal, a.grupo_id, a.estado, "
        "TRIM(COALESCE(g.codigo_postal, a.codigo_postal, '')) AS grupo_cp "
        "FROM aliados a INNER JOIN grupos g ON g.id = a.grupo_id "
        "WHERE LOWER(TRIM(COALESCE(a.estado, ''))) = 'activo' "
        "AND COALESCE(g.tipo, 'territorial') = 'territorial' "
        "AND COALESCE(g.estado, 'activo') IN ('activo', 'en_competencia')"
    )


def _fila_elegible(d: Dict[str, Any]) -> bool:
    if str(d.get("estado") or "").strip().lower() != "activo":
        return False
    if not d.get("grupo_id"):
        return False
    return cp_elegible(d.get("codigo_postal"))


def listar_elegibles(cursor) -> List[Dict[str, Any]]:
    cursor.execute(_sql_elegibles())
    out = []
    for r in cursor.fetchall() or []:
        d = _dict(r)
        d["codigo"] = str(d.get("codigo") or "").strip()
        if d["codigo"] and _fila_elegible(d):
            out.append(d)
    out.sort(key=lambda x: x["codigo"])
    return out


def es_elegible(cursor, codigo: str) -> bool:
    codigo = (codigo or "").strip()
    if not codigo:
        return False
    cursor.execute(_sql_elegibles() + " AND TRIM(CAST(a.codigo AS TEXT)) = ?", (codigo,))
    row = cursor.fetchone()
    return bool(row) and _fila_elegible(_dict(row))


def red_activa(cursor) -> Optional[Dict[str, Any]]:
    cursor.execute(
        "SELECT id, slug, nombre, estado, snapshot_sha256, activado_at, activado_por "
        "FROM red_piloto WHERE slug = ? AND estado = ? ORDER BY id DESC LIMIT 1",
        (SLUG_RED, ESTADO_ACTIVA),
    )
    row = cursor.fetchone()
    return _dict(row) if row else None


def _insertar_miembro(cursor, red_id: int, codigo: str, origen: str) -> bool:
    cursor.execute(
        "INSERT INTO red_piloto_miembros (red_id, aliado_codigo, origen, incorporado_at) "
        "VALUES (?, ?, ?, ?) ON CONFLICT (red_id, aliado_codigo) DO NOTHING",
        (int(red_id), codigo, origen, _ahora()),
    )
    return bool(getattr(cursor, "rowcount", 0))


def miembro(cursor, red_id: int, codigo: str) -> Optional[Dict[str, Any]]:
    cursor.execute(
        "SELECT aliado_codigo, origen, incorporado_at, aviso_red_centro_visto_at, "
        "aviso_red_centro_accion FROM red_piloto_miembros WHERE red_id = ? AND aliado_codigo = ?",
        (int(red_id), (codigo or "").strip()),
    )
    row = cursor.fetchone()
    return _dict(row) if row else None


def sincronizar_miembros(cursor, red_id: int, origen: str = "auto") -> Dict[str, Any]:
    """Incorpora a todos los elegibles que falten. Idempotente."""
    nuevos = []
    for d in listar_elegibles(cursor):
        if _insertar_miembro(cursor, red_id, d["codigo"], origen):
            nuevos.append(d["codigo"])
    cursor.execute("SELECT COUNT(*) AS n FROM red_piloto_miembros WHERE red_id = ?", (int(red_id),))
    total = int(_dict(cursor.fetchone()).get("n") or 0)
    return {"nuevos": nuevos, "total": total}


def incorporar_si_elegible(cursor, codigo: str) -> bool:
    """Alta automática durante el piloto. Devuelve True si queda como miembro."""
    if not piloto_habilitado():
        return False
    red = red_activa(cursor)
    if not red or not es_elegible(cursor, codigo):
        return False
    _insertar_miembro(cursor, int(red["id"]), (codigo or "").strip(), "auto")
    return miembro(cursor, int(red["id"]), codigo) is not None


def incorporar_tras_alta(db, codigo: str) -> bool:
    """Hook best-effort tras el registro. Nunca lanza ni bloquea el alta."""
    if not piloto_habilitado() or not (codigo or "").strip():
        return False
    try:
        return bool(_con_conexion(db, lambda conn, cur: incorporar_si_elegible(cur, codigo)))
    except Exception:
        logger.exception("[RUANA][RED_CENTRO] Fallo incorporando tras alta")
        return False


# --- Activación / estado / reversión -----------------------------------------------

def activar(db, admin_codigo: str = "") -> Dict[str, Any]:
    if not piloto_habilitado():
        return {"status": "error", "http": 409,
                "message": "RED_CENTRO_ENABLED está apagado; no se activa nada."}

    def _act(conn, cursor):
        red = red_activa(cursor)
        if red:
            sync = sincronizar_miembros(cursor, int(red["id"]), origen="auto")
            return {"status": "success", "ya_activa": True, "red": red, **sync}
        org = capturar_organizacion(db, cursor)
        sha = checksum(org)
        cursor.execute(
            "INSERT INTO red_piloto (slug, nombre, estado, snapshot_json, snapshot_sha256, "
            "activado_por, activado_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (SLUG_RED, NOMBRE_RED, ESTADO_ACTIVA,
             json.dumps(org, sort_keys=True, ensure_ascii=False), sha,
             (admin_codigo or "").strip() or None, _ahora()),
        )
        red = red_activa(cursor)
        sync = sincronizar_miembros(cursor, int(red["id"]), origen="inicial")
        return {"status": "success", "ya_activa": False, "red": red, **sync}

    return _con_conexion(db, _act)


def estado(db) -> Dict[str, Any]:
    def _est(conn, cursor):
        red = red_activa(cursor)
        elegibles = [d["codigo"] for d in listar_elegibles(cursor)]
        miembros: List[str] = []
        if red:
            if piloto_habilitado():
                sincronizar_miembros(cursor, int(red["id"]))
            cursor.execute(
                "SELECT aliado_codigo FROM red_piloto_miembros WHERE red_id = ? ORDER BY aliado_codigo",
                (int(red["id"]),),
            )
            miembros = [str(_dict(r).get("aliado_codigo")) for r in cursor.fetchall() or []]
        return {
            "status": "success",
            "flags": {
                "RED_CENTRO_ENABLED": piloto_habilitado(),
                "RED_CENTRO_AVISO_ENABLED": aviso_habilitado(),
                "RED_CENTRO_MAX_CANDIDATOS": max_candidatos(),
            },
            "operativa": bool(red) and piloto_habilitado(),
            "red": red,
            "elegibles": elegibles,
            "miembros": miembros,
        }

    return _con_conexion(db, _est)


def revertir(db, admin_codigo: str = "") -> Dict[str, Any]:
    """Desactiva la red y borra SOLO sus miembros. Verifica contra la instantánea."""

    def _rev(conn, cursor):
        cursor.execute(
            "SELECT id, snapshot_json, snapshot_sha256 FROM red_piloto "
            "WHERE slug = ? AND estado = ? ORDER BY id DESC LIMIT 1",
            (SLUG_RED, ESTADO_ACTIVA),
        )
        row = _dict(cursor.fetchone())
        if not row:
            return {"status": "error", "http": 404, "message": "No hay una Red Centro activa."}
        original = json.loads(row["snapshot_json"])
        if checksum(original) != row["snapshot_sha256"]:
            return {"status": "error", "http": 409,
                    "message": "La instantánea guardada no cuadra con su sha256; no se revierte."}
        cursor.execute("DELETE FROM red_piloto_miembros WHERE red_id = ?", (int(row["id"]),))
        borrados = int(getattr(cursor, "rowcount", 0) or 0)
        verif = comparar_organizacion(original, capturar_organizacion(db, cursor))
        verif["miembros_borrados"] = borrados
        cursor.execute(
            "UPDATE red_piloto SET estado = ?, desactivado_por = ?, desactivado_at = ?, "
            "verificacion_json = ? WHERE id = ?",
            (ESTADO_REVERTIDA, (admin_codigo or "").strip() or None, _ahora(),
             json.dumps(verif, ensure_ascii=False, default=str), int(row["id"])),
        )
        return {"status": "success", "red_id": int(row["id"]), "verificacion": verif}

    return _con_conexion(db, _rev)


# --- Reparto de encargos --------------------------------------------------------

def distancia_cp(cp_a: str, cp_b: str) -> Tuple[int, int]:
    """Orden de proximidad entre CPs de la red: (misma provincia?0:1, heurística)."""
    from core.services import territorio_service

    a = (cp_a or "").strip()
    b = (cp_b or "").strip()
    misma_prov = 0 if a[:2] == b[:2] else 1
    return (misma_prov, territorio_service.distancia_cp_heuristica(a, b))


def candidatos_red(
    db,
    cursor,
    solicitante_codigo: str,
    oficio: str,
    *,
    solicitante: Optional[Dict[str, Any]] = None,
    limite: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Hasta N aliados de la red del oficio pedido, fuera del grupo del solicitante,
    ordenados por proximidad. Solo lectura: usa el cursor del caller (sin conexión
    anidada). Lista vacía si el piloto está apagado, no hay red o el solicitante
    no es elegible."""
    if not piloto_habilitado():
        return []
    codigo = (solicitante_codigo or "").strip()
    of = (oficio or "").strip()
    if not codigo or not of:
        return []
    # En Postgres un error aborta la transacción del caller (crear solicitud):
    # aislamos la búsqueda en un SAVEPOINT para que un fallo del piloto no rompa nada.
    pg = _es_pg(db)
    if pg:
        try:
            cursor.execute("SAVEPOINT red_centro_cands")
        except Exception:
            return []
    try:
        res = _candidatos_red_impl(db, cursor, codigo, of, solicitante, limite)
        if pg:
            cursor.execute("RELEASE SAVEPOINT red_centro_cands")
        return res
    except Exception:
        logger.exception("[RUANA][RED_CENTRO] Fallo buscando candidatos (fail-closed)")
        if pg:
            try:
                cursor.execute("ROLLBACK TO SAVEPOINT red_centro_cands")
            except Exception:
                pass
        return []


def _candidatos_red_impl(db, cursor, codigo, of, solicitante, limite):
    from core.services import catalogo_service

    if not _tabla_existe(db, cursor, "red_piloto") or not red_activa(cursor):
        return []
    if not es_elegible(cursor, codigo):
        return []
    ctx = solicitante or {}
    grupo_sol = ctx.get("grupo_id")
    cp_sol = (ctx.get("codigo_postal") or "").strip()
    if grupo_sol is None or not cp_sol:
        cursor.execute(
            "SELECT grupo_id, codigo_postal FROM aliados WHERE TRIM(CAST(codigo AS TEXT)) = ?",
            (codigo,),
        )
        r = _dict(cursor.fetchone())
        grupo_sol = r.get("grupo_id")
        cp_sol = (r.get("codigo_postal") or "").strip()
    cursor.execute(
        "SELECT a.codigo, a.nombre, a.oficio, a.codigo_postal, a.grupo_id, a.estado "
        "FROM aliados a INNER JOIN grupos g ON g.id = a.grupo_id "
        "WHERE LOWER(TRIM(COALESCE(a.estado, ''))) = 'activo' "
        "AND COALESCE(g.tipo, 'territorial') = 'territorial' "
        "AND COALESCE(g.estado, 'activo') IN ('activo', 'en_competencia') "
        "AND a.grupo_id != ? AND TRIM(CAST(a.codigo AS TEXT)) != ?",
        (int(grupo_sol), codigo),
    )
    cands = []
    for raw in cursor.fetchall() or []:
        d = _dict(raw)
        if not _fila_elegible(d):
            continue
        if not catalogo_service.oficios_equivalentes(db, of, d.get("oficio") or ""):
            continue
        d["codigo"] = str(d.get("codigo") or "").strip()
        d["_orden"] = distancia_cp(cp_sol, d.get("codigo_postal") or "")
        cands.append(d)
    cands.sort(key=lambda x: (x["_orden"], x["codigo"]))
    n = limite if limite is not None else max_candidatos()
    out = []
    for d in cands[: max(1, int(n))]:
        out.append({
            "codigo": d["codigo"],
            "nombre": d.get("nombre"),
            "oficio": d.get("oficio"),
            "codigo_postal": d.get("codigo_postal"),
            "etiqueta_proximidad": ETIQUETA_PROXIMIDAD_RED,
            "nivel_proximidad": 3,
            "mismo_grupo": False,
            "red_centro": True,
        })
    return out


# --- Notificación (plantilla; NO se envía de forma masiva) --------------------------

TIPO_NOTIFICACION = "red_centro_bienvenida"
TITULO_NOTIFICACION = "Red Centro: os pasáis los encargos entre oficios"
# Nombres reales de los botones en la app (verificados en aliado.html):
#   «Conozco a alguien» / «Nueva conexión»  → recomendar un encargo de otro oficio
#   «Ampliar mi red» / «Invitar a un profesional» → invitar
MENSAJE_NOTIFICACION = (
    "Desde hoy los aliados de Madrid y Toledo estáis conectados en Red Centro. "
    "Si te entra un encargo que no es de tu oficio, pásaselo a un compañero desde "
    "«Nueva conexión» o con «Conozco a alguien»; cuando a él le llegue algo de lo tuyo, "
    "te lo pasará a ti. Y si conoces a un buen profesional de otro oficio, invítalo con "
    "«Ampliar mi red»: cuantos más seamos, más encargos se mueven. Tu oficio, tu zona y "
    "tus condiciones no cambian."
)


def plantilla_notificacion() -> Dict[str, str]:
    return {"tipo": TIPO_NOTIFICACION, "titulo": TITULO_NOTIFICACION, "mensaje": MENSAJE_NOTIFICACION}


def entregar_notificacion_verificada(db, aliado_codigo: str) -> Dict[str, Any]:
    """Inserta la notificación in-app y SOLO devuelve entregada=True si la fila
    se puede leer de vuelta en la bandeja del aliado. (La función existente
    ``notificacion_service.crear_notificacion_aliado`` traga excepciones y no
    devuelve nada, así que no sirve como confirmación.)

    No hay ningún envío masivo cableado a rutas ni cron: esto solo se usa en
    pruebas o de forma manual y controlada.
    """
    codigo = (aliado_codigo or "").strip()
    if not codigo:
        return {"entregada": False, "motivo": "sin_codigo"}
    marca = f"rc-{codigo}-{_ahora()}"
    meta = json.dumps({"red_centro": True, "marca": marca}, ensure_ascii=False)

    def _ins(conn, cursor):
        cursor.execute(
            "INSERT INTO notificaciones_aliado (aliado_codigo, tipo, titulo, mensaje, metadata, leida) "
            "VALUES (?, ?, ?, ?, ?, 0)",
            (codigo, TIPO_NOTIFICACION, TITULO_NOTIFICACION, MENSAJE_NOTIFICACION, meta),
        )
        conn.commit()
        cursor.execute(
            "SELECT id FROM notificaciones_aliado WHERE TRIM(CAST(aliado_codigo AS TEXT)) = ? "
            "AND tipo = ? AND metadata = ?",
            (codigo, TIPO_NOTIFICACION, meta),
        )
        row = _dict(cursor.fetchone())
        return row.get("id")

    try:
        nid = _con_conexion(db, _ins)
    except Exception as exc:
        logger.exception("[RUANA][RED_CENTRO] Fallo entregando notificación")
        return {"entregada": False, "motivo": f"error: {type(exc).__name__}"}
    if not nid:
        return {"entregada": False, "motivo": "no_verificada"}
    return {"entregada": True, "canal": "in_app", "notificacion_id": nid,
            "nota": "Entregada a la bandeja in-app; 'leida' solo cambia cuando el aliado la abre."}


# --- Aviso de bienvenida (modal) ------------------------------------------------

def aviso_para_aliado(db, codigo: str) -> Dict[str, Any]:
    """¿Hay que mostrar el modal? Fail-open = no mostrar ante cualquier fallo.
    Incorpora automáticamente al aliado si es elegible (punto 3)."""
    base = {"status": "success", "mostrar": False}
    if not aviso_habilitado() or not (codigo or "").strip():
        return base

    def _av(conn, cursor):
        red = red_activa(cursor)
        if not red:
            return base
        if not incorporar_si_elegible(cursor, codigo):
            return base
        m = miembro(cursor, int(red["id"]), codigo) or {}
        if m.get("aviso_red_centro_visto_at"):
            return {**base, "visto": True}
        return {"status": "success", "mostrar": True, "red": NOMBRE_RED}

    try:
        return _con_conexion(db, _av)
    except Exception:
        logger.exception("[RUANA][RED_CENTRO] Fallo leyendo aviso (no se muestra)")
        return base


def registrar_accion_aviso(db, codigo: str, accion: str) -> Dict[str, Any]:
    """Marca el aviso como visto (una sola vez) y guarda la acción. No cambia
    estado, permisos ni nada del aliado fuera de la capa del piloto."""
    acc = (accion or "").strip().lower()
    if acc not in ACCIONES_AVISO:
        return {"status": "error", "http": 400, "message": "Acción no válida."}
    if not aviso_habilitado():
        return {"status": "success", "registrado": False}

    def _reg(conn, cursor):
        red = red_activa(cursor)
        if not red:
            return {"status": "success", "registrado": False}
        m = miembro(cursor, int(red["id"]), codigo)
        if not m:
            return {"status": "success", "registrado": False}
        cursor.execute(
            "UPDATE red_piloto_miembros SET aviso_red_centro_visto_at = ?, "
            "aviso_red_centro_accion = ? WHERE red_id = ? AND aliado_codigo = ? "
            "AND aviso_red_centro_visto_at IS NULL",
            (_ahora(), acc, int(red["id"]), (codigo or "").strip()),
        )
        return {"status": "success", "registrado": bool(getattr(cursor, "rowcount", 0)), "accion": acc}

    try:
        return _con_conexion(db, _reg)
    except Exception:
        logger.exception("[RUANA][RED_CENTRO] Fallo guardando acción del aviso")
        return {"status": "error", "http": 500, "message": "No se pudo guardar."}
