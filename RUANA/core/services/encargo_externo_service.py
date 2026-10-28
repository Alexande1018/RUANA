"""Encargos externos («Encargo de RUANA»).

Clientes que llegan por anuncios externos y que el admin asigna a un aliado
concreto. Es un flujo aparte: tabla propia, sin Stripe, sin comisión y sin
puntos de reputación. No toca solicitudes, contactos, pagos ni score.

Comisión: preparada pero DESACTIVADA. Cada encargo guarda ``comision_activada``
(0) y ``comision_pct`` (5.0) para poder activarla más adelante sin migrar datos.
Mientras ``COMISION_ENCARGOS_EXTERNOS_ACTIVADA`` sea False no se cobra nada.
"""

from __future__ import annotations

import logging
import re
import smtplib
import sqlite3
from datetime import date, datetime
from decimal import Decimal
from email.message import EmailMessage
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# --- Comisión (gancho para el futuro; hoy apagado) -------------------------
COMISION_ENCARGOS_EXTERNOS_ACTIVADA = False
COMISION_PCT_POR_DEFECTO = 5.0

# --- Estados y transiciones -------------------------------------------------
ESTADO_CREADO = "creado"
ESTADO_ACEPTADO = "aceptado"
ESTADO_RECHAZADO = "rechazado"
ESTADO_HECHO = "hecho"
ESTADOS = (ESTADO_CREADO, ESTADO_ACEPTADO, ESTADO_HECHO, ESTADO_RECHAZADO)

TRANSICIONES = {
    ESTADO_CREADO: {ESTADO_ACEPTADO, ESTADO_RECHAZADO},
    ESTADO_ACEPTADO: {ESTADO_HECHO},
    ESTADO_RECHAZADO: set(),
    ESTADO_HECHO: set(),
}

ACCION_A_ESTADO = {
    "aceptar": ESTADO_ACEPTADO,
    "rechazar": ESTADO_RECHAZADO,
    "hecho": ESTADO_HECHO,
}

_COLUMNA_FECHA = {
    ESTADO_ACEPTADO: "aceptado_at",
    ESTADO_RECHAZADO: "rechazado_at",
    ESTADO_HECHO: "hecho_at",
}

TIPO_NOTIFICACION = "encargo_externo_asignado"

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_CP_RE = re.compile(r"^\d{5}$")

_COLUMNAS = (
    "id, aliado_codigo, cliente_nombre, cliente_telefono, cliente_email, "
    "codigo_postal, descripcion, origen_anuncio, precio_orientativo, estado, "
    "motivo_rechazo, comision_activada, comision_pct, creado_por, "
    "created_at, aceptado_at, rechazado_at, hecho_at, updated_at"
)


def comision_activada() -> bool:
    """True solo cuando se decida cobrar comisión en encargos externos."""
    return bool(COMISION_ENCARGOS_EXTERNOS_ACTIVADA)


def calcular_comision(encargo: Dict[str, Any], importe: Optional[float] = None) -> float:
    """Comisión que correspondería a un encargo externo.

    Hoy siempre devuelve 0.0: el cobro está desactivado. Cuando se active,
    bastará con poner ``COMISION_ENCARGOS_EXTERNOS_ACTIVADA = True`` y marcar
    ``comision_activada`` en los encargos que deban cobrar.
    """
    if not comision_activada():
        return 0.0
    if not encargo or not int(encargo.get("comision_activada") or 0):
        return 0.0
    base = importe if importe is not None else encargo.get("precio_orientativo")
    try:
        base_f = float(base or 0)
        pct = float(encargo.get("comision_pct") or COMISION_PCT_POR_DEFECTO)
    except (TypeError, ValueError):
        return 0.0
    return round(base_f * pct / 100.0, 2)


# --- Esquema -----------------------------------------------------------------

_ESQUEMA_LISTO: set = set()


def asegurar_esquema(db, cursor) -> None:
    """Crea la tabla encargos_externos si no existe (una vez por proceso y BD)."""
    _crear_esquema(db, cursor)


def _clave_esquema(db):
    return (getattr(db, "backend", None), str(getattr(db, "db_path", "") or id(db)))


def _crear_esquema(db, cursor) -> None:
    if getattr(db, "backend", None) == "postgres":
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS encargos_externos (
                id BIGSERIAL PRIMARY KEY,
                aliado_codigo TEXT NOT NULL,
                cliente_nombre TEXT NOT NULL,
                cliente_telefono TEXT,
                cliente_email TEXT,
                codigo_postal TEXT NOT NULL,
                descripcion TEXT NOT NULL,
                origen_anuncio TEXT DEFAULT '',
                precio_orientativo NUMERIC(10,2),
                estado TEXT NOT NULL DEFAULT 'creado',
                motivo_rechazo TEXT,
                comision_activada INTEGER NOT NULL DEFAULT 0,
                comision_pct NUMERIC(5,2) NOT NULL DEFAULT 5.0,
                creado_por TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                aceptado_at TIMESTAMPTZ,
                rechazado_at TIMESTAMPTZ,
                hecho_at TIMESTAMPTZ,
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
            """
        )
        try:
            cursor.execute(
                "SELECT relrowsecurity FROM pg_class "
                "WHERE oid = to_regclass('public.encargos_externos')"
            )
            row = cursor.fetchone()
            rls = dict(row).get("relrowsecurity") if row else True
            if rls is False:
                # Sin FORCE: Flask (dueño) no se ve afectado; anon queda denegado.
                cursor.execute("ALTER TABLE encargos_externos ENABLE ROW LEVEL SECURITY")
        except Exception:
            logger.warning("[RUANA][ENCARGO_EXTERNO] No se pudo comprobar/activar RLS")
    else:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS encargos_externos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                aliado_codigo TEXT NOT NULL,
                cliente_nombre TEXT NOT NULL,
                cliente_telefono TEXT,
                cliente_email TEXT,
                codigo_postal TEXT NOT NULL,
                descripcion TEXT NOT NULL,
                origen_anuncio TEXT DEFAULT '',
                precio_orientativo REAL,
                estado TEXT NOT NULL DEFAULT 'creado',
                motivo_rechazo TEXT,
                comision_activada INTEGER NOT NULL DEFAULT 0,
                comision_pct REAL NOT NULL DEFAULT 5.0,
                creado_por TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                aceptado_at DATETIME,
                rechazado_at DATETIME,
                hecho_at DATETIME,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_encargos_externos_aliado "
        "ON encargos_externos(aliado_codigo, estado)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_encargos_externos_estado "
        "ON encargos_externos(estado, created_at)"
    )


# --- Utilidades --------------------------------------------------------------

def _json_safe(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _fila(row: Any) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    d = dict(row)
    return {k: _json_safe(v) for k, v in d.items()}


def _con_conexion(db, fn):
    """Ejecuta fn(conn, cursor) con el esquema asegurado y commit al final."""
    with db._lock:
        conn = db._connect()
        try:
            if getattr(db, "backend", None) != "postgres":
                conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            clave = _clave_esquema(db)
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


def _limpiar(valor: Any, maximo: int) -> str:
    return str(valor or "").strip()[:maximo]


def _normalizar_telefono(valor: Any) -> str:
    tel = re.sub(r"[^\d+]", "", str(valor or "").strip())
    return tel[:20]


def _parse_precio(valor: Any):
    if valor is None or str(valor).strip() == "":
        return None, None
    try:
        precio = float(str(valor).replace("€", "").replace(",", ".").strip())
    except (TypeError, ValueError):
        return None, "El precio orientativo debe ser un número."
    if precio < 0 or precio > 1_000_000:
        return None, "El precio orientativo no es válido."
    return round(precio, 2), None


def validar_datos(data: Dict[str, Any]) -> Dict[str, Any]:
    """Valida y normaliza los datos de alta. Devuelve {'error': ...} o {'datos': ...}."""
    data = data or {}
    aliado = _limpiar(data.get("aliado_codigo"), 40).upper()
    nombre = _limpiar(data.get("cliente_nombre"), 120)
    telefono = _normalizar_telefono(data.get("cliente_telefono"))
    email = _limpiar(data.get("cliente_email"), 160).lower()
    cp = _limpiar(data.get("codigo_postal"), 10)
    descripcion = _limpiar(data.get("descripcion"), 2000)
    origen = _limpiar(data.get("origen_anuncio"), 120)
    precio, error_precio = _parse_precio(data.get("precio_orientativo"))

    if not aliado:
        return {"error": "Indica el código del aliado."}
    if not nombre:
        return {"error": "Indica el nombre del cliente."}
    if not telefono and not email:
        return {"error": "Indica al menos un teléfono o un email del cliente."}
    if telefono and len(re.sub(r"\D", "", telefono)) < 9:
        return {"error": "El teléfono del cliente no es válido."}
    if email and not _EMAIL_RE.match(email):
        return {"error": "El email del cliente no es válido."}
    if not _CP_RE.match(cp):
        return {"error": "El código postal debe tener 5 cifras."}
    if not descripcion:
        return {"error": "Describe brevemente el encargo."}
    if error_precio:
        return {"error": error_precio}
    return {
        "datos": {
            "aliado_codigo": aliado,
            "cliente_nombre": nombre,
            "cliente_telefono": telefono or None,
            "cliente_email": email or None,
            "codigo_postal": cp,
            "descripcion": descripcion,
            "origen_anuncio": origen,
            "precio_orientativo": precio,
        }
    }


def _buscar_aliado(cursor, codigo: str) -> Optional[Dict[str, Any]]:
    cursor.execute(
        "SELECT codigo, nombre, email, estado FROM aliados "
        "WHERE UPPER(TRIM(CAST(codigo AS TEXT))) = ?",
        (codigo.upper(),),
    )
    row = cursor.fetchone()
    return dict(row) if row else None


# --- Notificación (best effort) ---------------------------------------------

def _mensaje_notificacion(encargo: Dict[str, Any]) -> str:
    return (
        f"RUANA te ha pasado un cliente de la zona {encargo.get('codigo_postal')}: "
        f"{encargo.get('cliente_nombre')}. Entra en la app para ver sus datos "
        "y decirnos si lo coges."
    )


def _cuerpo_email(nombre_aliado: str, encargo: Dict[str, Any]) -> str:
    return (
        f"Hola, {nombre_aliado or 'aliado'}.\n\n"
        "RUANA te ha pasado un encargo nuevo.\n\n"
        f"Cliente: {encargo.get('cliente_nombre')}\n"
        f"Código postal: {encargo.get('codigo_postal')}\n"
        f"Qué necesita: {encargo.get('descripcion')}\n\n"
        "Entra en tu app de RUANA (apartado «Encargos de RUANA», en Inicio) para ver "
        "cómo contactar con el cliente y aceptarlo o rechazarlo.\n\n"
        "https://ruana-4293f.web.app/aliado\n\n"
        "Equipo RUANA."
    )


def _enviar_email_aliado(email: str, nombre: str, encargo: Dict[str, Any]) -> bool:
    email = (email or "").strip()
    if not email:
        return False
    from core import email_service
    from core.settings import get_settings

    if not email_service._smtp_configurado():
        logger.warning("[RUANA][ENCARGO_EXTERNO] SMTP no configurado; sin email al aliado")
        return False
    settings = get_settings()
    msg = EmailMessage()
    msg["Subject"] = "Tienes un encargo nuevo de RUANA"
    msg["From"] = settings.smtp_from_email or settings.smtp_user
    msg["To"] = email
    msg.set_content(_cuerpo_email(nombre, encargo))
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(msg)
    return True


def notificar_aliado(db, aliado: Dict[str, Any], encargo: Dict[str, Any]) -> Dict[str, bool]:
    """Aviso en la app + email. Nunca lanza: un fallo no rompe el alta."""
    resultado = {"app": False, "email": False}
    try:
        from core.services import notificacion_service

        notificacion_service.crear_notificacion_aliado(
            db,
            aliado.get("codigo"),
            tipo=TIPO_NOTIFICACION,
            titulo="Tienes un encargo de RUANA",
            mensaje=_mensaje_notificacion(encargo),
            metadata={"encargo_externo_id": encargo.get("id")},
        )
        resultado["app"] = True
    except Exception:
        logger.exception("[RUANA][ENCARGO_EXTERNO] Fallo aviso en app (encargo=%s)", encargo.get("id"))
    try:
        resultado["email"] = bool(
            _enviar_email_aliado(aliado.get("email"), aliado.get("nombre"), encargo)
        )
    except Exception:
        logger.exception("[RUANA][ENCARGO_EXTERNO] Fallo email (encargo=%s)", encargo.get("id"))
    return resultado


# --- Casos de uso -------------------------------------------------------------

def crear_encargo_externo(db, data: Dict[str, Any], admin_codigo: str = "") -> Dict[str, Any]:
    validado = validar_datos(data)
    if "error" in validado:
        return {"status": "error", "message": validado["error"], "http": 400}
    datos = validado["datos"]

    def _crear(conn, cursor):
        aliado = _buscar_aliado(cursor, datos["aliado_codigo"])
        if not aliado:
            return {"status": "error", "message": "No existe ningún aliado con ese código.", "http": 404}
        if str(aliado.get("estado") or "").strip().lower() != "activo":
            return {"status": "error", "message": "Ese aliado no está activo.", "http": 400}
        cursor.execute(
            """
            INSERT INTO encargos_externos (
                aliado_codigo, cliente_nombre, cliente_telefono, cliente_email,
                codigo_postal, descripcion, origen_anuncio, precio_orientativo,
                estado, comision_activada, comision_pct, creado_por
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'creado', 0, ?, ?)
            """,
            (
                str(aliado["codigo"]).strip(),
                datos["cliente_nombre"],
                datos["cliente_telefono"],
                datos["cliente_email"],
                datos["codigo_postal"],
                datos["descripcion"],
                datos["origen_anuncio"],
                datos["precio_orientativo"],
                COMISION_PCT_POR_DEFECTO,
                (admin_codigo or "").strip() or None,
            ),
        )
        nuevo_id = cursor.lastrowid
        cursor.execute(f"SELECT {_COLUMNAS} FROM encargos_externos WHERE id = ?", (nuevo_id,))
        return {"status": "success", "encargo": _fila(cursor.fetchone()), "aliado": aliado}

    try:
        result = _con_conexion(db, _crear)
    except Exception:
        logger.exception("[RUANA][ENCARGO_EXTERNO] Error creando encargo externo")
        return {"status": "error", "message": "No se pudo crear el encargo.", "http": 500}
    if result.get("status") != "success":
        return result
    aviso = notificar_aliado(db, result.pop("aliado"), result["encargo"])
    result["notificacion"] = aviso
    return result


def listar_admin(db, estado: str = "", limite: int = 300) -> Dict[str, Any]:
    estado = (estado or "").strip().lower()
    if estado and estado not in ESTADOS:
        return {"status": "error", "message": "Estado no válido.", "http": 400}
    limite = max(1, min(int(limite or 300), 1000))

    def _listar(conn, cursor):
        sql = (
            f"SELECT e.{_COLUMNAS.replace(', ', ', e.')}, a.nombre AS aliado_nombre "
            "FROM encargos_externos e "
            "LEFT JOIN aliados a ON TRIM(CAST(a.codigo AS TEXT)) = TRIM(e.aliado_codigo) "
        )
        params: List[Any] = []
        if estado:
            sql += "WHERE e.estado = ? "
            params.append(estado)
        sql += "ORDER BY e.id DESC LIMIT ?"
        params.append(limite)
        cursor.execute(sql, tuple(params))
        encargos = [_fila(r) for r in cursor.fetchall()]
        cursor.execute("SELECT estado, COUNT(*) AS n FROM encargos_externos GROUP BY estado")
        conteos = {e: 0 for e in ESTADOS}
        for r in cursor.fetchall():
            d = dict(r)
            if d.get("estado") in conteos:
                conteos[d["estado"]] = int(d.get("n") or 0)
        return {
            "status": "success",
            "encargos": encargos,
            "conteos": conteos,
            "total": sum(conteos.values()),
            "comision_activada": comision_activada(),
        }

    try:
        return _con_conexion(db, _listar)
    except Exception:
        logger.exception("[RUANA][ENCARGO_EXTERNO] Error listando encargos externos")
        return {"status": "error", "message": "No se pudo cargar la lista.", "http": 500}


def listar_para_aliado(db, aliado_codigo: str) -> Dict[str, Any]:
    codigo = (aliado_codigo or "").strip()
    if not codigo:
        return {"status": "error", "message": "Sesión expirada", "http": 401}

    def _listar(conn, cursor):
        cursor.execute(
            f"SELECT {_COLUMNAS} FROM encargos_externos "
            "WHERE UPPER(TRIM(aliado_codigo)) = ? ORDER BY id DESC LIMIT 100",
            (codigo.upper(),),
        )
        encargos = []
        for r in cursor.fetchall():
            fila = _fila(r)
            # Datos internos que el aliado no necesita ver.
            for k in ("creado_por", "comision_activada", "comision_pct", "origen_anuncio"):
                fila.pop(k, None)
            encargos.append(fila)
        return {"status": "success", "encargos": encargos}

    try:
        return _con_conexion(db, _listar)
    except Exception:
        logger.exception("[RUANA][ENCARGO_EXTERNO] Error listando encargos del aliado")
        return {"status": "error", "message": "No se pudieron cargar tus encargos.", "http": 500}


def cambiar_estado(
    db, encargo_id: int, aliado_codigo: str, accion: str, motivo: str = ""
) -> Dict[str, Any]:
    codigo = (aliado_codigo or "").strip()
    nuevo = ACCION_A_ESTADO.get((accion or "").strip().lower())
    if not codigo:
        return {"status": "error", "message": "Sesión expirada", "http": 401}
    if not nuevo:
        return {"status": "error", "message": "Acción no válida.", "http": 400}
    motivo = _limpiar(motivo, 500)

    def _cambiar(conn, cursor):
        cursor.execute(f"SELECT {_COLUMNAS} FROM encargos_externos WHERE id = ?", (int(encargo_id),))
        actual = _fila(cursor.fetchone())
        if not actual:
            return {"status": "error", "message": "Encargo no encontrado.", "http": 404}
        if str(actual.get("aliado_codigo") or "").strip().upper() != codigo.upper():
            return {"status": "error", "message": "Este encargo no es tuyo.", "http": 403}
        estado_actual = actual.get("estado")
        if nuevo not in TRANSICIONES.get(estado_actual, set()):
            return {
                "status": "error",
                "message": f"No se puede pasar de «{estado_actual}» a «{nuevo}».",
                "http": 409,
            }
        col = _COLUMNA_FECHA[nuevo]
        cursor.execute(
            f"UPDATE encargos_externos SET estado = ?, {col} = CURRENT_TIMESTAMP, "
            "updated_at = CURRENT_TIMESTAMP, motivo_rechazo = COALESCE(?, motivo_rechazo) "
            "WHERE id = ? AND estado = ?",
            (
                nuevo,
                motivo if (nuevo == ESTADO_RECHAZADO and motivo) else None,
                int(encargo_id),
                estado_actual,
            ),
        )
        if getattr(cursor, "rowcount", 1) == 0:
            return {"status": "error", "message": "El encargo ha cambiado; recarga.", "http": 409}
        cursor.execute(f"SELECT {_COLUMNAS} FROM encargos_externos WHERE id = ?", (int(encargo_id),))
        return {"status": "success", "encargo": _fila(cursor.fetchone())}

    try:
        return _con_conexion(db, _cambiar)
    except Exception:
        logger.exception("[RUANA][ENCARGO_EXTERNO] Error cambiando estado (encargo=%s)", encargo_id)
        return {"status": "error", "message": "No se pudo actualizar el encargo.", "http": 500}
