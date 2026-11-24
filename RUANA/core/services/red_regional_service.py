"""Redes regionales reversibles, parametrizadas por prefijos de CP.

Capa NUEVA y aislada, a imagen de Red Centro, pensada para que una provincia
nueva sea solo una entrada de configuración (no otro servicio). En este PR
solo está definida y activable Red Huesca (CP 22xxx).

Red Centro (Madrid 28xxx + Toledo 45xxx) se deja intacta: ya está en
producción. Esta capa reutiliza las tablas ``red_piloto`` / ``red_piloto_miembros``
(aisladas por ``slug``) y no modifica ``aliados``, ``grupos``, plazas, score,
competencia, pagos, comisiones, negociación ni historial.

Garantías (cubiertas por ``tests/test_red_huesca_piloto.py``):

* Flag maestro apagado por defecto (p. ej. ``RED_HUESCA_ENABLED=0``).
* Incorporación automática e idempotente (UNIQUE red_id + aliado_codigo).
* Reparto: solo si el grupo propio y la cercanía no encuentran a nadie.
* Sin notificaciones masivas. Modal de bienvenida opcional, una vez, fail-open.
* Reversión: desactiva la red y borra SOLO sus miembros; verifica la instantánea.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

logger = logging.getLogger(__name__)

ESTADO_ACTIVA = "activa"
ESTADO_REVERTIDA = "revertida"
ESTADOS_GRUPO_OPERATIVOS = ("activo", "en_competencia")
ACCIONES_AVISO = ("cerrar", "aceptar", "recomendar", "invitar")

_CP_RE = re.compile(r"^\d{5}$")
_PREFIJO_RE = re.compile(r"^\d{2}$")


@dataclass(frozen=True)
class RedRegional:
    """Configuración de una red regional. Añadir una entrada a ``REDES`` basta
    para la próxima provincia (flag apagado hasta que se active)."""

    slug: str
    nombre: str
    prefijos_cp: Tuple[str, ...]
    zona_descriptiva: str
    env_enabled: str
    env_aviso: str
    env_max: str
    etiqueta_proximidad: str
    tipo_notificacion: str
    titulo_notificacion: str
    mensaje_notificacion: str
    # Si la variable de entorno del flag maestro no existe, ¿la red está encendida?
    # Red Huesca: False (su flag va en el workflow). Redes provinciales: True, para
    # no depender de editar el workflow; siguen sin hacer nada hasta que un admin
    # llama a /activar, y /revertir las neutraliza aunque el flag siga a 1.
    habilitada_por_defecto: bool = False

    def __post_init__(self) -> None:
        prefs = tuple(str(p).strip() for p in self.prefijos_cp)
        if not prefs or any(not _PREFIJO_RE.match(p) for p in prefs):
            raise ValueError(f"Prefijos de CP no válidos para {self.slug}: {self.prefijos_cp}")
        object.__setattr__(self, "prefijos_cp", prefs)


def _plantilla_mensaje(zona: str) -> str:
    return (
        f"Desde hoy los aliados de {zona} estáis conectados en una red de oficios. "
        "Si te entra un encargo que no es de tu oficio, pásaselo a un compañero desde "
        "«Nueva conexión» o con «Conozco a alguien»; cuando a él le llegue algo de lo tuyo, "
        "te lo pasará a ti. Y si conoces a un buen profesional de otro oficio, invítalo con "
        "«Ampliar mi red»: cuantos más seamos, más encargos se mueven. Tu oficio, tu zona y "
        "tus condiciones no cambian."
    )


# Registro de redes. Para una provincia nueva, copia una entrada, cambia slug,
# nombre, prefijos_cp, zona y nombres de flags. No hace falta otro PR de lógica.
# Ejemplo futuro (NO activar en este PR):
#   slug="red_zaragoza", prefijos_cp=("50",), env_enabled="RED_ZARAGOZA_ENABLED", ...
REDES: Dict[str, RedRegional] = {}


def _registrar(red: RedRegional) -> RedRegional:
    if red.slug in REDES:
        raise ValueError(f"Red duplicada: {red.slug}")
    REDES[red.slug] = red
    return red


RED_HUESCA = _registrar(RedRegional(
    slug="red_huesca",
    nombre="Red Huesca",
    prefijos_cp=("22",),
    zona_descriptiva="Huesca",
    env_enabled="RED_HUESCA_ENABLED",
    env_aviso="RED_HUESCA_AVISO_ENABLED",
    env_max="RED_HUESCA_MAX_CANDIDATOS",
    etiqueta_proximidad="Red Huesca",
    tipo_notificacion="red_huesca_bienvenida",
    titulo_notificacion="Red Huesca: os pasáis los encargos entre oficios",
    mensaje_notificacion=_plantilla_mensaje("Huesca"),
))


# --- Redes provinciales (24 nov 2026) ------------------------------------------
# Una red por provincia (prefijo de CP = código INE). Madrid (28) y Toledo (45)
# siguen en Red Centro y Huesca (22) en RED_HUESCA: no se duplican aquí.
# Flag maestro: RED_<SLUG>_ENABLED (encendido si no existe la variable).
PROVINCIAS: Tuple[Tuple[str, str, str], ...] = (
    ("01", "alava", "Álava"), ("02", "albacete", "Albacete"), ("03", "alicante", "Alicante"),
    ("04", "almeria", "Almería"), ("05", "avila", "Ávila"), ("06", "badajoz", "Badajoz"),
    ("07", "baleares", "Illes Balears"), ("08", "barcelona", "Barcelona"), ("09", "burgos", "Burgos"),
    ("10", "caceres", "Cáceres"), ("11", "cadiz", "Cádiz"), ("12", "castellon", "Castellón"),
    ("13", "ciudad_real", "Ciudad Real"), ("14", "cordoba", "Córdoba"), ("15", "a_coruna", "A Coruña"),
    ("16", "cuenca", "Cuenca"), ("17", "girona", "Girona"), ("18", "granada", "Granada"),
    ("19", "guadalajara", "Guadalajara"), ("20", "gipuzkoa", "Gipuzkoa"), ("21", "huelva", "Huelva"),
    ("23", "jaen", "Jaén"), ("24", "leon", "León"), ("25", "lleida", "Lleida"),
    ("26", "la_rioja", "La Rioja"), ("27", "lugo", "Lugo"), ("29", "malaga", "Málaga"),
    ("30", "murcia", "Murcia"), ("31", "navarra", "Navarra"), ("32", "ourense", "Ourense"),
    ("33", "asturias", "Asturias"), ("34", "palencia", "Palencia"), ("35", "las_palmas", "Las Palmas"),
    ("36", "pontevedra", "Pontevedra"), ("37", "salamanca", "Salamanca"),
    ("38", "tenerife", "Santa Cruz de Tenerife"), ("39", "cantabria", "Cantabria"),
    ("40", "segovia", "Segovia"), ("41", "sevilla", "Sevilla"), ("42", "soria", "Soria"),
    ("43", "tarragona", "Tarragona"), ("44", "teruel", "Teruel"), ("46", "valencia", "Valencia"),
    ("47", "valladolid", "Valladolid"), ("48", "bizkaia", "Bizkaia"), ("49", "zamora", "Zamora"),
    ("50", "zaragoza", "Zaragoza"), ("51", "ceuta", "Ceuta"), ("52", "melilla", "Melilla"),
)

for _pref, _slug, _zona in PROVINCIAS:
    _env = "RED_" + _slug.upper()
    _registrar(RedRegional(
        slug=f"red_{_slug}",
        nombre=f"Red {_zona}",
        prefijos_cp=(_pref,),
        zona_descriptiva=_zona,
        env_enabled=f"{_env}_ENABLED",
        env_aviso=f"{_env}_AVISO_ENABLED",
        env_max=f"{_env}_MAX_CANDIDATOS",
        etiqueta_proximidad=f"Red {_zona}",
        tipo_notificacion=f"red_{_slug}_bienvenida",
        titulo_notificacion=f"Red {_zona}: os pasáis los encargos entre oficios",
        mensaje_notificacion=_plantilla_mensaje(_zona),
        habilitada_por_defecto=True,
    ))


def redes_para_cp(codigo_postal: Any) -> List[RedRegional]:
    """Redes cuyo prefijo encaja con el CP (normalmente 0 o 1). Evita recorrer
    las ~50 redes, cada una con su conexión, en cada apertura del panel."""
    return [cfg for cfg in REDES.values() if cp_elegible(codigo_postal, cfg)]


def _cp_de_aliado(db, codigo: str) -> str:
    def _q(conn, cursor):
        cursor.execute(
            "SELECT codigo_postal FROM aliados WHERE TRIM(CAST(codigo AS TEXT)) = ?",
            ((codigo or "").strip(),),
        )
        return str(_dict(cursor.fetchone()).get("codigo_postal") or "").strip()
    return _con_conexion(db, _q)


def red_por_slug(slug: str) -> Optional[RedRegional]:
    return REDES.get((slug or "").strip())


def resolver_red(red: Union[str, RedRegional]) -> RedRegional:
    if isinstance(red, RedRegional):
        return red
    found = red_por_slug(str(red or ""))
    if not found:
        raise KeyError(f"Red regional desconocida: {red!r}")
    return found


# --- Flags ---------------------------------------------------------------------

def _env_bool(nombre: str, defecto: bool) -> bool:
    val = os.environ.get(nombre)
    if val is None or str(val).strip() == "":
        return defecto
    return str(val).strip().lower() in ("1", "true", "yes", "si", "sí", "on")


def piloto_habilitado(red: Union[str, RedRegional]) -> bool:
    """Flag maestro. Por defecto APAGADO."""
    cfg = resolver_red(red)
    return _env_bool(cfg.env_enabled, cfg.habilitada_por_defecto)


def aviso_habilitado(red: Union[str, RedRegional]) -> bool:
    cfg = resolver_red(red)
    return piloto_habilitado(cfg) and _env_bool(cfg.env_aviso, True)


def max_candidatos(red: Union[str, RedRegional]) -> int:
    cfg = resolver_red(red)
    try:
        n = int(os.environ.get(cfg.env_max, "3"))
    except (TypeError, ValueError):
        n = 3
    return max(1, min(n, 10))


def cp_elegible(codigo_postal: Any, red: Union[str, RedRegional]) -> bool:
    cfg = resolver_red(red)
    cp = str(codigo_postal or "").strip()
    if not _CP_RE.match(cp):
        return False
    return any(cp.startswith(p) for p in cfg.prefijos_cp)


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --- Esquema (reutiliza las tablas de red_piloto, aisladas por slug) ------------

_ESQUEMA_LISTO: set = set()


def _es_pg(db) -> bool:
    return getattr(db, "backend", None) == "postgres"


def _con_conexion(db, fn):
    from core.services import red_centro_service

    with db._lock:
        conn = db._connect()
        try:
            if not _es_pg(db):
                conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            clave = (getattr(db, "backend", None), str(getattr(db, "db_path", "") or id(db)))
            if clave not in _ESQUEMA_LISTO:
                red_centro_service.asegurar_esquema(db, cursor)
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


def _fila_elegible(d: Dict[str, Any], red: RedRegional) -> bool:
    if str(d.get("estado") or "").strip().lower() != "activo":
        return False
    if not d.get("grupo_id"):
        return False
    return cp_elegible(d.get("codigo_postal"), red)


def listar_elegibles(cursor, red: Union[str, RedRegional]) -> List[Dict[str, Any]]:
    cfg = resolver_red(red)
    cursor.execute(_sql_elegibles())
    out = []
    for r in cursor.fetchall() or []:
        d = _dict(r)
        d["codigo"] = str(d.get("codigo") or "").strip()
        if d["codigo"] and _fila_elegible(d, cfg):
            out.append(d)
    out.sort(key=lambda x: x["codigo"])
    return out


def es_elegible(cursor, codigo: str, red: Union[str, RedRegional]) -> bool:
    cfg = resolver_red(red)
    codigo = (codigo or "").strip()
    if not codigo:
        return False
    cursor.execute(_sql_elegibles() + " AND TRIM(CAST(a.codigo AS TEXT)) = ?", (codigo,))
    row = cursor.fetchone()
    return bool(row) and _fila_elegible(_dict(row), cfg)


def red_activa(cursor, red: Union[str, RedRegional]) -> Optional[Dict[str, Any]]:
    cfg = resolver_red(red)
    cursor.execute(
        "SELECT id, slug, nombre, estado, snapshot_sha256, activado_at, activado_por "
        "FROM red_piloto WHERE slug = ? AND estado = ? ORDER BY id DESC LIMIT 1",
        (cfg.slug, ESTADO_ACTIVA),
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


def sincronizar_miembros(cursor, red_id: int, red: Union[str, RedRegional], origen: str = "auto") -> Dict[str, Any]:
    """Incorpora a todos los elegibles que falten. Idempotente."""
    nuevos = []
    for d in listar_elegibles(cursor, red):
        if _insertar_miembro(cursor, red_id, d["codigo"], origen):
            nuevos.append(d["codigo"])
    cursor.execute("SELECT COUNT(*) AS n FROM red_piloto_miembros WHERE red_id = ?", (int(red_id),))
    total = int(_dict(cursor.fetchone()).get("n") or 0)
    return {"nuevos": nuevos, "total": total}


def incorporar_si_elegible(cursor, codigo: str, red: Union[str, RedRegional]) -> bool:
    cfg = resolver_red(red)
    if not piloto_habilitado(cfg):
        return False
    activa = red_activa(cursor, cfg)
    if not activa or not es_elegible(cursor, codigo, cfg):
        return False
    _insertar_miembro(cursor, int(activa["id"]), (codigo or "").strip(), "auto")
    return miembro(cursor, int(activa["id"]), codigo) is not None


def incorporar_tras_alta(db, codigo: str, red: Optional[Union[str, RedRegional]] = None) -> bool:
    """Hook best-effort tras el registro. Nunca lanza ni bloquea el alta.

    Si ``red`` es None, recorre todas las redes configuradas (no-op si el flag
    está apagado o el CP no encaja).
    """
    if not (codigo or "").strip():
        return False
    if red is not None:
        redes: Iterable[RedRegional] = (resolver_red(red),)
    else:
        try:
            redes = redes_para_cp(_cp_de_aliado(db, codigo))
        except Exception:
            logger.exception("[RUANA][RED_REGIONAL] No se pudo leer el CP tras alta")
            redes = ()
    ok = False
    for cfg in redes:
        if not piloto_habilitado(cfg):
            continue
        try:
            if _con_conexion(db, lambda conn, cur, c=cfg: incorporar_si_elegible(cur, codigo, c)):
                ok = True
        except Exception:
            logger.exception("[RUANA][RED_REGIONAL] Fallo incorporando tras alta (%s)", cfg.slug)
    return ok


# --- Activación / estado / reversión -----------------------------------------------

def activar(db, admin_codigo: str = "", red: Union[str, RedRegional] = RED_HUESCA) -> Dict[str, Any]:
    from core.services import red_centro_service as rc

    cfg = resolver_red(red)
    if not piloto_habilitado(cfg):
        return {"status": "error", "http": 409,
                "message": f"{cfg.env_enabled} está apagado; no se activa nada."}

    def _act(conn, cursor):
        activa = red_activa(cursor, cfg)
        if activa:
            sync = sincronizar_miembros(cursor, int(activa["id"]), cfg, origen="auto")
            return {"status": "success", "ya_activa": True, "red": activa, **sync}
        org = rc.capturar_organizacion(db, cursor)
        sha = rc.checksum(org)
        cursor.execute(
            "INSERT INTO red_piloto (slug, nombre, estado, snapshot_json, snapshot_sha256, "
            "activado_por, activado_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (cfg.slug, cfg.nombre, ESTADO_ACTIVA,
             json.dumps(org, sort_keys=True, ensure_ascii=False), sha,
             (admin_codigo or "").strip() or None, _ahora()),
        )
        activa = red_activa(cursor, cfg)
        sync = sincronizar_miembros(cursor, int(activa["id"]), cfg, origen="inicial")
        return {"status": "success", "ya_activa": False, "red": activa, **sync}

    return _con_conexion(db, _act)


def estado(db, red: Union[str, RedRegional] = RED_HUESCA) -> Dict[str, Any]:
    cfg = resolver_red(red)

    def _est(conn, cursor):
        activa = red_activa(cursor, cfg)
        elegibles = [d["codigo"] for d in listar_elegibles(cursor, cfg)]
        miembros: List[str] = []
        if activa:
            if piloto_habilitado(cfg):
                sincronizar_miembros(cursor, int(activa["id"]), cfg)
            cursor.execute(
                "SELECT aliado_codigo FROM red_piloto_miembros WHERE red_id = ? ORDER BY aliado_codigo",
                (int(activa["id"]),),
            )
            miembros = [str(_dict(r).get("aliado_codigo")) for r in cursor.fetchall() or []]
        return {
            "status": "success",
            "slug": cfg.slug,
            "nombre": cfg.nombre,
            "prefijos_cp": list(cfg.prefijos_cp),
            "flags": {
                cfg.env_enabled: piloto_habilitado(cfg),
                cfg.env_aviso: aviso_habilitado(cfg),
                cfg.env_max: max_candidatos(cfg),
            },
            "operativa": bool(activa) and piloto_habilitado(cfg),
            "red": activa,
            "elegibles": elegibles,
            "miembros": miembros,
        }

    return _con_conexion(db, _est)


def estado_todas(db) -> Dict[str, Any]:
    redes = [estado(db, cfg) for cfg in REDES.values()]
    return {"status": "success", "redes": redes}


def revertir(db, admin_codigo: str = "", red: Union[str, RedRegional] = RED_HUESCA) -> Dict[str, Any]:
    """Desactiva la red y borra SOLO sus miembros. Verifica contra la instantánea."""
    from core.services import red_centro_service as rc

    cfg = resolver_red(red)

    def _rev(conn, cursor):
        cursor.execute(
            "SELECT id, snapshot_json, snapshot_sha256 FROM red_piloto "
            "WHERE slug = ? AND estado = ? ORDER BY id DESC LIMIT 1",
            (cfg.slug, ESTADO_ACTIVA),
        )
        row = _dict(cursor.fetchone())
        if not row:
            return {"status": "error", "http": 404, "message": f"No hay una {cfg.nombre} activa."}
        original = json.loads(row["snapshot_json"])
        if rc.checksum(original) != row["snapshot_sha256"]:
            return {"status": "error", "http": 409,
                    "message": "La instantánea guardada no cuadra con su sha256; no se revierte."}
        cursor.execute("DELETE FROM red_piloto_miembros WHERE red_id = ?", (int(row["id"]),))
        borrados = int(getattr(cursor, "rowcount", 0) or 0)
        verif = rc.comparar_organizacion(original, rc.capturar_organizacion(db, cursor))
        verif["miembros_borrados"] = borrados
        cursor.execute(
            "UPDATE red_piloto SET estado = ?, desactivado_por = ?, desactivado_at = ?, "
            "verificacion_json = ? WHERE id = ?",
            (ESTADO_REVERTIDA, (admin_codigo or "").strip() or None, _ahora(),
             json.dumps(verif, ensure_ascii=False, default=str), int(row["id"])),
        )
        return {"status": "success", "red_id": int(row["id"]), "slug": cfg.slug, "verificacion": verif}

    return _con_conexion(db, _rev)


# --- Reparto de encargos --------------------------------------------------------

def candidatos_red(
    db,
    cursor,
    solicitante_codigo: str,
    oficio: str,
    red: Union[str, RedRegional] = RED_HUESCA,
    *,
    solicitante: Optional[Dict[str, Any]] = None,
    limite: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Hasta N aliados de la red del oficio pedido, fuera del grupo del solicitante,
    ordenados por proximidad. Lista vacía si el piloto está apagado, no hay red
    o el solicitante no es elegible. Fail-closed; SAVEPOINT en Postgres."""
    cfg = resolver_red(red)
    if not piloto_habilitado(cfg):
        return []
    codigo = (solicitante_codigo or "").strip()
    of = (oficio or "").strip()
    if not codigo or not of:
        return []
    pg = _es_pg(db)
    sp = f"red_reg_{cfg.slug}_cands"
    if pg:
        try:
            cursor.execute(f"SAVEPOINT {sp}")
        except Exception:
            return []
    try:
        res = _candidatos_red_impl(db, cursor, codigo, of, solicitante, limite, cfg)
        if pg:
            cursor.execute(f"RELEASE SAVEPOINT {sp}")
        return res
    except Exception:
        logger.exception("[RUANA][RED_REGIONAL] Fallo buscando candidatos (%s)", cfg.slug)
        if pg:
            try:
                cursor.execute(f"ROLLBACK TO SAVEPOINT {sp}")
            except Exception:
                pass
        return []


def _candidatos_red_impl(db, cursor, codigo, of, solicitante, limite, cfg: RedRegional):
    from core.services import catalogo_service
    from core.services import red_centro_service as rc

    if not _tabla_existe(db, cursor, "red_piloto") or not red_activa(cursor, cfg):
        return []
    if not es_elegible(cursor, codigo, cfg):
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
        if not _fila_elegible(d, cfg):
            continue
        if not catalogo_service.oficios_equivalentes(db, of, d.get("oficio") or ""):
            continue
        d["codigo"] = str(d.get("codigo") or "").strip()
        d["_orden"] = rc.distancia_cp(cp_sol, d.get("codigo_postal") or "")
        cands.append(d)
    cands.sort(key=lambda x: (x["_orden"], x["codigo"]))
    n = limite if limite is not None else max_candidatos(cfg)
    out = []
    for d in cands[: max(1, int(n))]:
        out.append({
            "codigo": d["codigo"],
            "nombre": d.get("nombre"),
            "oficio": d.get("oficio"),
            "codigo_postal": d.get("codigo_postal"),
            "etiqueta_proximidad": cfg.etiqueta_proximidad,
            "nivel_proximidad": 3,
            "mismo_grupo": False,
            "red_regional": True,
            "red_slug": cfg.slug,
        })
    return out


def candidatos_cualquier_red(
    db,
    cursor,
    solicitante_codigo: str,
    oficio: str,
    *,
    solicitante: Optional[Dict[str, Any]] = None,
    limite: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Prueba las redes configuradas (hoy solo Huesca). La primera que devuelva
    candidatos gana. Red Centro se evalúa aparte, antes, en proximidad_service."""
    cp_sol = str((solicitante or {}).get("codigo_postal") or "").strip()
    redes: Iterable[RedRegional] = redes_para_cp(cp_sol) if cp_sol else REDES.values()
    for cfg in redes:
        cands = candidatos_red(
            db, cursor, solicitante_codigo, oficio, cfg,
            solicitante=solicitante, limite=limite,
        )
        if cands:
            return cands
    return []


# --- Notificación (plantilla; NO se envía de forma masiva) --------------------------

def plantilla_notificacion(red: Union[str, RedRegional] = RED_HUESCA) -> Dict[str, str]:
    cfg = resolver_red(red)
    return {"tipo": cfg.tipo_notificacion, "titulo": cfg.titulo_notificacion,
            "mensaje": cfg.mensaje_notificacion, "zona": cfg.zona_descriptiva}


def entregar_notificacion_verificada(db, aliado_codigo: str, red: Union[str, RedRegional] = RED_HUESCA) -> Dict[str, Any]:
    """Inserta la notificación in-app y SOLO devuelve entregada=True si la fila
    se puede leer de vuelta. No hay envío masivo cableado a rutas ni cron."""
    cfg = resolver_red(red)
    codigo = (aliado_codigo or "").strip()
    if not codigo:
        return {"entregada": False, "motivo": "sin_codigo"}
    marca = f"{cfg.slug}-{codigo}-{_ahora()}"
    meta = json.dumps({"red_regional": cfg.slug, "marca": marca}, ensure_ascii=False)

    def _ins(conn, cursor):
        cursor.execute(
            "INSERT INTO notificaciones_aliado (aliado_codigo, tipo, titulo, mensaje, metadata, leida) "
            "VALUES (?, ?, ?, ?, ?, 0)",
            (codigo, cfg.tipo_notificacion, cfg.titulo_notificacion, cfg.mensaje_notificacion, meta),
        )
        conn.commit()
        cursor.execute(
            "SELECT id FROM notificaciones_aliado WHERE TRIM(CAST(aliado_codigo AS TEXT)) = ? "
            "AND tipo = ? AND metadata = ?",
            (codigo, cfg.tipo_notificacion, meta),
        )
        row = _dict(cursor.fetchone())
        return row.get("id")

    try:
        nid = _con_conexion(db, _ins)
    except Exception as exc:
        logger.exception("[RUANA][RED_REGIONAL] Fallo entregando notificación (%s)", cfg.slug)
        return {"entregada": False, "motivo": f"error: {type(exc).__name__}"}
    if not nid:
        return {"entregada": False, "motivo": "no_verificada"}
    return {"entregada": True, "canal": "in_app", "notificacion_id": nid,
            "nota": "Entregada a la bandeja in-app; 'leida' solo cambia cuando el aliado la abre."}


# --- Aviso de bienvenida (modal) ------------------------------------------------

def aviso_para_aliado(db, codigo: str, red: Union[str, RedRegional] = RED_HUESCA) -> Dict[str, Any]:
    """¿Hay que mostrar el modal? Fail-open = no mostrar ante cualquier fallo."""
    cfg = resolver_red(red)
    base = {"status": "success", "mostrar": False, "slug": cfg.slug}
    if not aviso_habilitado(cfg) or not (codigo or "").strip():
        return base

    def _av(conn, cursor):
        activa = red_activa(cursor, cfg)
        if not activa:
            return base
        if not incorporar_si_elegible(cursor, codigo, cfg):
            return base
        m = miembro(cursor, int(activa["id"]), codigo) or {}
        if m.get("aviso_red_centro_visto_at"):
            return {**base, "visto": True}
        return {
            "status": "success",
            "mostrar": True,
            "red": cfg.nombre,
            "slug": cfg.slug,
            "zona": cfg.zona_descriptiva,
        }

    try:
        return _con_conexion(db, _av)
    except Exception:
        logger.exception("[RUANA][RED_REGIONAL] Fallo leyendo aviso (%s)", cfg.slug)
        return base


def aviso_para_aliado_cualquier_red(db, codigo: str) -> Dict[str, Any]:
    """Primera red configurada que deba mostrar el modal a este aliado."""
    base = {"status": "success", "mostrar": False}
    if not (codigo or "").strip():
        return base
    try:
        for cfg in redes_para_cp(_cp_de_aliado(db, codigo)):
            r = aviso_para_aliado(db, codigo, cfg)
            if r.get("mostrar") is True:
                return r
        return base
    except Exception:
        logger.exception("[RUANA][RED_REGIONAL] Fallo leyendo aviso (cualquier red)")
        return base


def registrar_accion_aviso(db, codigo: str, accion: str, red: Union[str, RedRegional] = RED_HUESCA) -> Dict[str, Any]:
    cfg = resolver_red(red)
    acc = (accion or "").strip().lower()
    if acc not in ACCIONES_AVISO:
        return {"status": "error", "http": 400, "message": "Acción no válida."}
    if not aviso_habilitado(cfg):
        return {"status": "success", "registrado": False}

    def _reg(conn, cursor):
        activa = red_activa(cursor, cfg)
        if not activa:
            return {"status": "success", "registrado": False}
        m = miembro(cursor, int(activa["id"]), codigo)
        if not m:
            return {"status": "success", "registrado": False}
        cursor.execute(
            "UPDATE red_piloto_miembros SET aviso_red_centro_visto_at = ?, "
            "aviso_red_centro_accion = ? WHERE red_id = ? AND aliado_codigo = ? "
            "AND aviso_red_centro_visto_at IS NULL",
            (_ahora(), acc, int(activa["id"]), (codigo or "").strip()),
        )
        return {"status": "success", "registrado": bool(getattr(cursor, "rowcount", 0)), "accion": acc}

    try:
        return _con_conexion(db, _reg)
    except Exception:
        logger.exception("[RUANA][RED_REGIONAL] Fallo guardando acción del aviso (%s)", cfg.slug)
        return {"status": "error", "http": 500, "message": "No se pudo guardar."}
