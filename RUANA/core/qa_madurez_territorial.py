"""Herramienta TEMPORAL de QA para madurez territorial de un CP.

No altera las reglas reales de madurez. Solo inspecciona el estado y, si se
autoriza después, completa los datos de prueba identificables que falten.

Fase 1: inspección + dry-run. La inserción exige autorización explícita y
nunca se ejecuta en producción sin un segundo candado.
"""
from __future__ import annotations

import os
import sqlite3
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.db_constants import (
    CP_MADUREZ_MIN_ALIADOS,
    CP_MADUREZ_MIN_ENCARGOS,
    ESTADOS_ENCARGO_VALIDO_MADUREZ,
)
from core.repositories.grupo_madre_repo import GrupoMadreRepo
from core.repositories.schema_repo import SchemaRepo
from core.runtime_environment import is_production
from core.services import grupo_madre_service

PREFIX = "QA-MADUREZ-03001-2026"
CP_OBJETIVO_DEFAULT = "03001"
EMAIL_DOMINIO_QA = "ruana.invalid"
CODIGO_QA_INICIO = 39101
ENV_APPLY = "RUANA_QA_MADUREZ_APPLY"
ENV_ALLOW_PRODUCTION = "RUANA_QA_MADUREZ_ALLOW_PRODUCTION"
CONFIRM_TOKEN = PREFIX

_FINANCIAL_TABLES = (
    "financial_transfers",
    "financial_transfer_attempts",
    "financial_refunds",
    "financial_refund_attempts",
    "stripe_refunds",
    "stripe_disputes",
    "payment_conflicts",
    "payment_conflict_evidence",
    "ledger_transactions",
    "ledger_entries",
)

_madre_repo = GrupoMadreRepo()
_schema_repo = SchemaRepo()


class QaMadurezError(RuntimeError):
    """Error controlado de la herramienta de QA (sin inserción parcial opaca)."""


@dataclass
class AliadoVista:
    codigo: str
    nombre: str
    oficio: str
    estado: str
    marca: str
    email: str
    telefono: str
    score: Any
    grupo_id: Any
    descripcion_servicio: str = ""
    es_qa: bool = False
    stripe_account_id: str = ""


@dataclass
class EncargoVista:
    id: Any
    solicitante_codigo: str
    profesional_codigo: str
    estado: str
    servicio: str
    motivo_contacto: str
    es_qa: bool = False


@dataclass
class PlanAliado:
    codigo_propuesto: str
    nombre: str
    marca: str
    oficio: str
    email: str
    telefono: str
    descripcion_servicio: str
    codigo_postal: str


@dataclass
class PlanEncargo:
    solicitante_codigo: str
    profesional_codigo: str
    servicio: str
    motivo_contacto: str
    estado_objetivo: str = "aceptado"


@dataclass
class InspeccionCP:
    codigo_postal: str
    ciudad: str
    modo: str
    listo_independizar: bool
    backend: str
    aliados_activos: List[AliadoVista]
    aliados_qa_existentes: List[AliadoVista]
    oficios_ocupados: List[str]
    oficios_catalogo: List[str]
    oficios_disponibles: List[str]
    encargos_validos: List[EncargoVista]
    grupos_territoriales_activos: int
    min_aliados: int = CP_MADUREZ_MIN_ALIADOS
    min_encargos: int = CP_MADUREZ_MIN_ENCARGOS
    bloqueos: List[str] = field(default_factory=list)

    @property
    def n_aliados_activos(self) -> int:
        return len(self.aliados_activos)

    @property
    def n_encargos_validos(self) -> int:
        return len(self.encargos_validos)

    @property
    def aliados_faltan(self) -> int:
        return max(0, self.min_aliados - self.n_aliados_activos)

    @property
    def encargos_faltan(self) -> int:
        return max(0, self.min_encargos - self.n_encargos_validos)


@dataclass
class PlanQA:
    codigo_postal: str
    prefix: str
    aliados_a_crear: List[PlanAliado]
    encargos_a_crear: List[PlanEncargo]
    aliados_qa_reutilizados: List[str]
    bloqueos: List[str]
    riesgos: List[str]
    acciones_prohibidas: List[str]


def es_marcador_qa(valor: Any) -> bool:
    texto = str(valor or "")
    return PREFIX in texto


def aliado_es_qa(aliado: Dict[str, Any] | AliadoVista) -> bool:
    if isinstance(aliado, AliadoVista):
        return any(
            es_marcador_qa(v)
            for v in (
                aliado.nombre,
                aliado.marca,
                aliado.email,
                aliado.descripcion_servicio,
            )
        )
    return any(
        es_marcador_qa(aliado.get(k))
        for k in ("nombre", "marca", "email", "descripcion_servicio")
    )


def apply_autorizado(permitir_produccion: bool = False) -> Tuple[bool, str]:
    if os.environ.get(ENV_APPLY, "").strip() != "1":
        return False, (
            "Inserción bloqueada (fase 1). Falta autorización explícita "
            f"({ENV_APPLY}=1). No se ha escrito nada."
        )
    if is_production() and os.environ.get(ENV_ALLOW_PRODUCTION, "").strip() != "1":
        return False, (
            "Inserción en producción bloqueada. No ejecutar el seed todavía. "
            f"Hace falta {ENV_ALLOW_PRODUCTION}=1 además de {ENV_APPLY}=1."
        )
    if is_production() and not permitir_produccion:
        return False, "Inserción en producción bloqueada por candado de invocación."
    return True, "ok"


def _row_get(row: Any, key: str, idx: int, default: Any = "") -> Any:
    if row is None:
        return default
    if hasattr(row, "keys"):
        try:
            val = row[key]
            return default if val is None else val
        except Exception:
            pass
    try:
        val = row[idx]
        return default if val is None else val
    except Exception:
        return default


def _detectar_backend(db) -> str:
    try:
        from core.settings import get_settings

        settings = get_settings()
        if getattr(settings, "database_url", ""):
            return "postgres"
    except Exception:
        pass
    path = getattr(db, "db_path", None) or getattr(db, "path", None)
    return f"sqlite:{path}" if path else "sqlite"


def _listar_columnas(cursor, tabla: str) -> List[str]:
    try:
        return list(_schema_repo.columnas_tabla(cursor, tabla) or [])
    except Exception:
        return []


def _oficio_canonico(db, oficio: str, catalogo: Sequence[str]) -> Optional[str]:
    valor = (oficio or "").strip()
    if not valor:
        return None
    permitidos = {str(o).strip() for o in catalogo if o and str(o).strip()}
    resolver = getattr(db, "_resolver_en_conjunto_catalogo", None)
    if callable(resolver):
        return resolver(valor, permitidos)
    if valor in permitidos:
        return valor
    return None


def inspeccionar_cp(db, codigo_postal: str = CP_OBJETIVO_DEFAULT) -> InspeccionCP:
    """Consulta el estado real del CP usando las mismas reglas de madurez."""
    cp = (codigo_postal or "").strip()
    if not cp:
        raise QaMadurezError("Código postal vacío")

    catalogo = [
        str(o).strip()
        for o in (db.get_catalogo_oficios_ruana() or [])
        if o and str(o).strip()
    ]
    ciudad = ""
    modo = "desconocido"
    listo = False
    aliados: List[AliadoVista] = []
    encargos: List[EncargoVista] = []
    n_terr = 0
    bloqueos: List[str] = []

    with db._lock:
        conn = db._connect()
        try:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cols_aliados = _listar_columnas(cursor, "aliados")
            extra_desc = "descripcion_servicio" in cols_aliados
            extra_stripe = "stripe_account_id" in cols_aliados
            select_extra = ""
            if extra_desc:
                select_extra += ", descripcion_servicio"
            if extra_stripe:
                select_extra += ", stripe_account_id"
            cursor.execute(
                f"""
                SELECT codigo, nombre, marca, oficio, estado, email, telefono,
                       score, grupo_id{select_extra}
                FROM aliados
                WHERE TRIM(codigo_postal) = ?
                ORDER BY codigo
                """,
                (cp,),
            )
            for row in cursor.fetchall():
                estado = str(_row_get(row, "estado", 4, "") or "").strip()
                desc = str(_row_get(row, "descripcion_servicio", 9, "") or "") if extra_desc else ""
                stripe_id = (
                    str(_row_get(row, "stripe_account_id", 10 if extra_desc else 9, "") or "")
                    if extra_stripe
                    else ""
                )
                vista = AliadoVista(
                    codigo=str(_row_get(row, "codigo", 0, "") or ""),
                    nombre=str(_row_get(row, "nombre", 1, "") or ""),
                    marca=str(_row_get(row, "marca", 2, "") or ""),
                    oficio=str(_row_get(row, "oficio", 3, "") or "").strip(),
                    estado=estado,
                    email=str(_row_get(row, "email", 5, "") or ""),
                    telefono=str(_row_get(row, "telefono", 6, "") or ""),
                    score=_row_get(row, "score", 7, None),
                    grupo_id=_row_get(row, "grupo_id", 8, None),
                    descripcion_servicio=desc,
                    stripe_account_id=stripe_id,
                )
                vista.es_qa = aliado_es_qa(vista)
                if estado == "activo":
                    aliados.append(vista)

            placeholders = ",".join("?" for _ in ESTADOS_ENCARGO_VALIDO_MADUREZ)
            cursor.execute(
                f"""
                SELECT c.id, c.solicitante_codigo, c.profesional_codigo, c.estado,
                       c.servicio, c.motivo_contacto
                FROM contactos_ruana c
                INNER JOIN aliados a ON a.codigo = c.profesional_codigo
                WHERE TRIM(a.codigo_postal) = ?
                  AND a.estado = 'activo'
                  AND c.estado IN ({placeholders})
                ORDER BY c.id
                """,
                (cp, *ESTADOS_ENCARGO_VALIDO_MADUREZ),
            )
            for row in cursor.fetchall():
                enc = EncargoVista(
                    id=_row_get(row, "id", 0, None),
                    solicitante_codigo=str(_row_get(row, "solicitante_codigo", 1, "") or ""),
                    profesional_codigo=str(_row_get(row, "profesional_codigo", 2, "") or ""),
                    estado=str(_row_get(row, "estado", 3, "") or ""),
                    servicio=str(_row_get(row, "servicio", 4, "") or ""),
                    motivo_contacto=str(_row_get(row, "motivo_contacto", 5, "") or ""),
                )
                enc.es_qa = es_marcador_qa(enc.motivo_contacto) or es_marcador_qa(enc.servicio)
                encargos.append(enc)

            n_repo_aliados = _madre_repo.contar_aliados_activos_cp(cursor, cp)
            n_repo_encargos = _madre_repo.contar_encargos_validos_cp_profesional(cursor, cp)
            if n_repo_aliados != len(aliados):
                bloqueos.append(
                    f"Discrepancia de conteo de aliados activos: listado={len(aliados)} "
                    f"regla_real={n_repo_aliados}"
                )
            if n_repo_encargos != len(encargos):
                bloqueos.append(
                    f"Discrepancia de conteo de encargos válidos: listado={len(encargos)} "
                    f"regla_real={n_repo_encargos}"
                )

            n_terr = _madre_repo.contar_territoriales_activos_por_cp(cursor, cp)
            row_estado = _madre_repo.select_cp_estado(cursor, cp)
            if row_estado:
                ciudad = str(_row_get(row_estado, "ciudad", 1, "") or "")
                modo = str(_row_get(row_estado, "modo", 2, "") or "")
                listo = bool(_row_get(row_estado, "listo_independizar", 6, False))
        finally:
            conn.close()

    if not ciudad:
        try:
            from core.services import territorio_service

            ubic = territorio_service.resolver_ciudad(db, cp)
            ciudad = (ubic or {}).get("ciudad") or ""
        except Exception:
            ciudad = ""

    if not modo or modo == "desconocido":
        modo = "territorial" if grupo_madre_service.cp_en_modo_territorial(db, cp) else "incubacion"

    ocupados: List[str] = []
    vistos = set()
    for aliado in aliados:
        canon = _oficio_canonico(db, aliado.oficio, catalogo) or aliado.oficio
        if canon and canon not in vistos:
            ocupados.append(canon)
            vistos.add(canon)

    disponibles = [o for o in catalogo if o not in vistos]
    qa_existentes = [a for a in aliados if a.es_qa]

    if n_terr > 0 or modo == "territorial":
        bloqueos.append(
            "El CP ya está en modo territorial o tiene grupos territoriales activos. "
            "No se deben insertar aliados QA: podrían crear o rellenar grupos territoriales."
        )
    if not catalogo:
        bloqueos.append("No se pudo leer el catálogo de oficios.")

    return InspeccionCP(
        codigo_postal=cp,
        ciudad=ciudad,
        modo=modo,
        listo_independizar=listo,
        backend=_detectar_backend(db),
        aliados_activos=aliados,
        aliados_qa_existentes=qa_existentes,
        oficios_ocupados=ocupados,
        oficios_catalogo=catalogo,
        oficios_disponibles=disponibles,
        encargos_validos=encargos,
        grupos_territoriales_activos=n_terr,
        bloqueos=bloqueos,
    )


def _codigos_ocupados(db) -> set:
    ocupados = set()
    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT codigo FROM aliados")
            for row in cursor.fetchall():
                ocupados.add(str(row[0]).strip())
        finally:
            conn.close()
    return ocupados


def _proponer_codigo(ocupados: set, usados_plan: set, inicio: int = CODIGO_QA_INICIO) -> str:
    codigo_n = inicio
    while True:
        codigo = str(codigo_n)
        if (
            len(codigo) == 5
            and codigo.isdigit()
            and codigo not in ocupados
            and codigo not in usados_plan
        ):
            return codigo
        codigo_n += 1
        if codigo_n > 99999:
            raise QaMadurezError("No hay códigos de 5 dígitos libres para aliados QA")


def _riesgos_base(inspeccion: InspeccionCP) -> List[str]:
    return [
        "Al aplicar, los aliados reales del Grupo Madre pueden recibir avisos de cinta/actividad por nuevos registros. No se modifican sus perfiles.",
        "actualizar_madurez_cp (regla real) puede marcar el CP como listo_independizar y crear una solicitud pendiente de Admin. No se aprueba la independencia.",
        "Los códigos propuestos se reservan en el momento de aplicar; si hay colisión se elige el siguiente libre.",
        "No hay credenciales de producción en este entorno de desarrollo: el dry-run contra prod requiere DATABASE_URL.",
        f"Backend consultado: {inspeccion.backend}.",
    ]


def _acciones_prohibidas() -> List[str]:
    return [
        "No se modifican las constantes CP_MADUREZ_MIN_ALIADOS / CP_MADUREZ_MIN_ENCARGOS.",
        "No se modifican, borran ni reasignan aliados reales.",
        "No se crean grupos territoriales.",
        "No se crean pagos, cargos Stripe, cuentas Stripe ni transferencias.",
        "No se modifican scores de aliados existentes ni se ajustan scores a mano.",
        "No se aprueba la independencia territorial (queda para Admin).",
        "No se ejecuta el seed en producción en esta fase.",
    ]


def calcular_plan(db, inspeccion: InspeccionCP) -> PlanQA:
    """Calcula exactamente qué datos QA faltarían, sin escribir."""
    bloqueos = list(inspeccion.bloqueos)
    aliados_crear: List[PlanAliado] = []
    encargos_crear: List[PlanEncargo] = []

    if inspeccion.aliados_faltan > len(inspeccion.oficios_disponibles):
        bloqueos.append(
            f"No hay oficios libres suficientes: faltan {inspeccion.aliados_faltan} "
            f"aliados y solo hay {len(inspeccion.oficios_disponibles)} profesiones libres."
        )

    ocupados_codigos = _codigos_ocupados(db)
    usados = set()
    oficios_para_nuevos = inspeccion.oficios_disponibles[: inspeccion.aliados_faltan]

    for idx, oficio in enumerate(oficios_para_nuevos, start=1):
        codigo = _proponer_codigo(ocupados_codigos, usados)
        usados.add(codigo)
        aliados_crear.append(
            PlanAliado(
                codigo_propuesto=codigo,
                nombre=f"{PREFIX} Aliado {idx} ({oficio})",
                marca=PREFIX,
                oficio=oficio,
                email=f"qa-madurez-03001-2026-{codigo}@{EMAIL_DOMINIO_QA}",
                telefono=f"+34639{codigo}",
                descripcion_servicio=(
                    f"{PREFIX} dato de prueba temporal, ficticio y reversible. "
                    "No es un profesional real."
                ),
                codigo_postal=inspeccion.codigo_postal,
            )
        )

    pool_qa = [a.codigo for a in inspeccion.aliados_qa_existentes] + [
        p.codigo_propuesto for p in aliados_crear
    ]
    if inspeccion.encargos_faltan and len(pool_qa) < 2:
        bloqueos.append(
            "Hacen falta al menos 2 aliados QA para crear encargos sin usar aliados reales. "
            "No se crearán encargos que involucren profesionales existentes no-QA."
        )

    if not bloqueos and inspeccion.encargos_faltan:
        for i in range(inspeccion.encargos_faltan):
            solicitante = pool_qa[i % len(pool_qa)]
            profesional = pool_qa[(i + 1) % len(pool_qa)]
            if solicitante == profesional:
                bloqueos.append("No se pudo emparejar encargos QA con profesionales distintos.")
                break
            encargos_crear.append(
                PlanEncargo(
                    solicitante_codigo=solicitante,
                    profesional_codigo=profesional,
                    servicio=f"{PREFIX} servicio de prueba",
                    motivo_contacto=f"{PREFIX} encargo de prueba aceptado por el profesional",
                    estado_objetivo="aceptado",
                )
            )

    if bloqueos:
        aliados_crear = []
        encargos_crear = []

    return PlanQA(
        codigo_postal=inspeccion.codigo_postal,
        prefix=PREFIX,
        aliados_a_crear=aliados_crear,
        encargos_a_crear=encargos_crear,
        aliados_qa_reutilizados=[a.codigo for a in inspeccion.aliados_qa_existentes],
        bloqueos=bloqueos,
        riesgos=_riesgos_base(inspeccion),
        acciones_prohibidas=_acciones_prohibidas(),
    )


def _aliado_publico(a: AliadoVista) -> Dict[str, Any]:
    return {
        "codigo": a.codigo,
        "nombre": a.nombre,
        "oficio": a.oficio,
        "estado": a.estado,
        "es_qa": a.es_qa,
        "grupo_id": a.grupo_id,
        "score": a.score,
    }


def plan_a_dict(inspeccion: InspeccionCP, plan: PlanQA) -> Dict[str, Any]:
    return {
        "fase": "dry-run",
        "insercion": False,
        "codigo_postal": inspeccion.codigo_postal,
        "ciudad": inspeccion.ciudad,
        "backend": inspeccion.backend,
        "modo": inspeccion.modo,
        "listo_independizar": inspeccion.listo_independizar,
        "regla_real": {
            "min_aliados_activos": inspeccion.min_aliados,
            "min_encargos_aceptados": inspeccion.min_encargos,
            "profesiones_distintas": True,
            "independencia": "solo Admin, no automática",
        },
        "estado_actual": {
            "aliados_activos": inspeccion.n_aliados_activos,
            "aliados_faltan": inspeccion.aliados_faltan,
            "oficios_ocupados": inspeccion.oficios_ocupados,
            "oficios_disponibles": inspeccion.oficios_disponibles,
            "encargos_validos": inspeccion.n_encargos_validos,
            "encargos_faltan": inspeccion.encargos_faltan,
            "grupos_territoriales_activos": inspeccion.grupos_territoriales_activos,
            "aliados": [_aliado_publico(a) for a in inspeccion.aliados_activos],
            "encargos": [asdict(e) for e in inspeccion.encargos_validos],
            "aliados_qa_existentes": [a.codigo for a in inspeccion.aliados_qa_existentes],
        },
        "plan": {
            "prefix": plan.prefix,
            "aliados_a_crear": [asdict(a) for a in plan.aliados_a_crear],
            "encargos_a_crear": [asdict(e) for e in plan.encargos_a_crear],
            "aliados_qa_reutilizados": plan.aliados_qa_reutilizados,
        },
        "bloqueos": plan.bloqueos,
        "riesgos": plan.riesgos,
        "acciones_prohibidas": plan.acciones_prohibidas,
    }


def formatear_dry_run(inspeccion: InspeccionCP, plan: PlanQA) -> str:
    lineas = [
        "=== DRY-RUN QA madurez territorial ===",
        f"CP: {inspeccion.codigo_postal}  ciudad: {inspeccion.ciudad or '(sin resolver)'}",
        f"Backend: {inspeccion.backend}",
        f"Modo: {inspeccion.modo}  listo_independizar: {inspeccion.listo_independizar}",
        f"Grupos territoriales activos: {inspeccion.grupos_territoriales_activos}",
        "",
        "Regla real (NO se modifica):",
        f"  - mínimo {inspeccion.min_aliados} aliados activos del mismo CP, profesión distinta",
        f"  - mínimo {inspeccion.min_encargos} encargos en estado aceptado (o posterior válido)",
        "  - independencia territorial: solo Admin, después",
        "",
        "Estado actual:",
        f"  - Aliados activos: {inspeccion.n_aliados_activos} / {inspeccion.min_aliados}",
        f"  - Aliados que faltan: {inspeccion.aliados_faltan}",
        f"  - Encargos válidos: {inspeccion.n_encargos_validos} / {inspeccion.min_encargos}",
        f"  - Encargos aceptados adicionales necesarios: {inspeccion.encargos_faltan}",
        f"  - Aliados QA ya existentes: {len(inspeccion.aliados_qa_existentes)}",
        "",
        "Profesiones del catálogo ya ocupadas en el CP:",
    ]
    if inspeccion.oficios_ocupados:
        for oficio in inspeccion.oficios_ocupados:
            lineas.append(f"  - {oficio}")
    else:
        lineas.append("  - (ninguna)")
    lineas.append("Profesiones distintas disponibles que se usarían:")
    usados = [a.oficio for a in plan.aliados_a_crear]
    if usados:
        for oficio in usados:
            lineas.append(f"  - {oficio}")
    else:
        lineas.append("  - (ninguna; no hace falta crear aliados o hay bloqueo)")
    lineas.append("")
    lineas.append("Aliados activos actuales:")
    for aliado in inspeccion.aliados_activos:
        marca = "QA" if aliado.es_qa else "real"
        lineas.append(f"  - [{marca}] {aliado.codigo}  oficio={aliado.oficio}  estado={aliado.estado}")
    if not inspeccion.aliados_activos:
        lineas.append("  - (ninguno)")
    lineas.append("Encargos válidos actuales:")
    for enc in inspeccion.encargos_validos:
        marca = "QA" if enc.es_qa else "existente"
        lineas.append(
            f"  - [{marca}] id={enc.id} {enc.solicitante_codigo} -> {enc.profesional_codigo} "
            f"estado={enc.estado}"
        )
    if not inspeccion.encargos_validos:
        lineas.append("  - (ninguno)")
    lineas += ["", "Se CREARÍA (solo tras autorización):"]
    if plan.aliados_a_crear:
        for aliado in plan.aliados_a_crear:
            lineas.append(
                f"  - Aliado {aliado.codigo_propuesto} oficio={aliado.oficio} "
                f"email={aliado.email} marca={aliado.marca}"
            )
    else:
        lineas.append("  - Ningún aliado nuevo")
    if plan.encargos_a_crear:
        for enc in plan.encargos_a_crear:
            lineas.append(
                f"  - Encargo {enc.solicitante_codigo} -> {enc.profesional_codigo} "
                f"estado_objetivo={enc.estado_objetivo}"
            )
    else:
        lineas.append("  - Ningún encargo nuevo")
    lineas += ["", "NO se hará:"]
    for item in plan.acciones_prohibidas:
        lineas.append(f"  - {item}")
    if plan.bloqueos:
        lineas += ["", "BLOQUEOS (no se puede aplicar):"]
        for item in plan.bloqueos:
            lineas.append(f"  - {item}")
    lineas += ["", "Riesgos:"]
    for item in plan.riesgos:
        lineas.append(f"  - {item}")
    lineas += [
        "",
        "Inserción: BLOQUEADA hasta autorización.",
        f"Tras autorizar: {ENV_APPLY}=1 python RUANA/scripts/qa_madurez_cp.py --apply "
        f"--confirm {CONFIRM_TOKEN}",
    ]
    return "\n".join(lineas)


def _snapshot_aliados_no_qa(inspeccion: InspeccionCP) -> Dict[str, Dict[str, Any]]:
    out = {}
    for a in inspeccion.aliados_activos:
        if a.es_qa:
            continue
        out[a.codigo] = {
            "oficio": a.oficio,
            "estado": a.estado,
            "email": a.email,
            "telefono": a.telefono,
            "score": a.score,
            "grupo_id": a.grupo_id,
            "nombre": a.nombre,
            "marca": a.marca,
        }
    return out


def _contar_filas_tabla(cursor, tabla: str) -> Optional[int]:
    if not _schema_repo.tabla_existe(cursor, tabla):
        return None
    cursor.execute(f"SELECT COUNT(*) FROM {tabla}")
    row = cursor.fetchone()
    return int(row[0] if row else 0)


def _huella_financiera(db) -> Dict[str, int]:
    out: Dict[str, int] = {}
    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            for tabla in _FINANCIAL_TABLES:
                try:
                    n = _contar_filas_tabla(cursor, tabla)
                except Exception:
                    n = None
                if n is not None:
                    out[tabla] = n
        finally:
            conn.close()
    return out


def validar_integridad(
    db,
    codigo_postal: str,
    snapshot_reales: Dict[str, Dict[str, Any]],
    snapshot_financiero: Dict[str, int],
    n_territoriales_antes: int,
    codigos_qa_nuevos: Sequence[str],
    ids_encargos_nuevos: Sequence[Any],
) -> Dict[str, Any]:
    """Confirma que no hay duplicados, huérfanos ni cambios en aliados reales."""
    errores: List[str] = []
    inspeccion = inspeccionar_cp(db, codigo_postal)
    por_codigo = {a.codigo: a for a in inspeccion.aliados_activos}

    for codigo, antes in snapshot_reales.items():
        ahora = por_codigo.get(codigo)
        if ahora is None:
            errores.append(f"Aliado real {codigo} ya no está activo o no existe")
            continue
        for campo in ("oficio", "estado", "email", "telefono", "score", "grupo_id", "nombre", "marca"):
            actual = getattr(ahora, campo)
            esperado = antes.get(campo)
            if actual == esperado:
                continue
            try:
                if float(actual) == float(esperado):
                    continue
            except (TypeError, ValueError):
                pass
            if str(actual) != str(esperado):
                errores.append(f"Aliado real {codigo} cambió el campo {campo}")

    oficios_activos = [a.oficio for a in inspeccion.aliados_activos]
    if len(oficios_activos) != len(set(oficios_activos)):
        errores.append("Hay profesiones duplicadas entre aliados activos del CP")

    for codigo in codigos_qa_nuevos:
        aliado = db.obtener_aliado_por_codigo(codigo)
        if not aliado:
            errores.append(f"Aliado QA {codigo} no encontrado tras crear")
            continue
        if (aliado.get("estado") or "") != "activo":
            errores.append(f"Aliado QA {codigo} no está activo ({aliado.get('estado')})")
        if str(aliado.get("codigo_postal") or "").strip() != codigo_postal:
            errores.append(f"Aliado QA {codigo} no pertenece al CP {codigo_postal}")
        if not aliado_es_qa(aliado):
            errores.append(f"Aliado QA {codigo} no lleva el marcador {PREFIX}")
        if aliado.get("stripe_account_id"):
            errores.append(f"Aliado QA {codigo} tiene stripe_account_id; no debería")

    for enc_id in ids_encargos_nuevos:
        enc = db.obtener_contacto_por_id(enc_id)
        if not enc:
            errores.append(f"Encargo {enc_id} huérfano o inexistente")
            continue
        if enc.get("estado") not in ESTADOS_ENCARGO_VALIDO_MADUREZ:
            errores.append(f"Encargo {enc_id} no está en estado válido de madurez: {enc.get('estado')}")
        sol = db.obtener_aliado_por_codigo(enc.get("solicitante_codigo"))
        pro = db.obtener_aliado_por_codigo(enc.get("profesional_codigo"))
        if not sol or not pro:
            errores.append(f"Encargo {enc_id} tiene participantes inexistentes")
        elif not aliado_es_qa(sol) or not aliado_es_qa(pro):
            errores.append(f"Encargo {enc_id} involucra a un aliado que no es QA")

    financiero_despues = _huella_financiera(db)
    for tabla, n_antes in snapshot_financiero.items():
        n_despues = financiero_despues.get(tabla, n_antes)
        if n_despues != n_antes:
            errores.append(f"La tabla financiera {tabla} cambió ({n_antes} -> {n_despues})")

    n_terr = grupo_madre_service.contar_grupos_territoriales_activos_por_cp(db, codigo_postal)
    if n_terr != n_territoriales_antes:
        errores.append(
            f"Se crearon o alteraron grupos territoriales ({n_territoriales_antes} -> {n_terr})"
        )

    return {
        "ok": not errores,
        "errores": errores,
        "aliados_activos": inspeccion.n_aliados_activos,
        "encargos_validos": inspeccion.n_encargos_validos,
        "listo_independizar": inspeccion.listo_independizar,
    }


def aplicar_plan(
    db,
    codigo_postal: str = CP_OBJETIVO_DEFAULT,
    *,
    confirm_token: str = "",
    permitir_produccion: bool = False,
) -> Dict[str, Any]:
    """Inserta SOLO los datos faltantes calculados. Exige autorización explícita."""
    ok, motivo = apply_autorizado(permitir_produccion=permitir_produccion)
    if not ok:
        return {"status": "blocked", "message": motivo, "insercion": False}
    if (confirm_token or "").strip() != CONFIRM_TOKEN:
        return {
            "status": "blocked",
            "message": f"Falta --confirm {CONFIRM_TOKEN}",
            "insercion": False,
        }

    inspeccion = inspeccionar_cp(db, codigo_postal)
    plan = calcular_plan(db, inspeccion)
    if plan.bloqueos:
        return {
            "status": "blocked",
            "message": "Hay bloqueos; no se insertó nada",
            "bloqueos": plan.bloqueos,
            "insercion": False,
            "dry_run": plan_a_dict(inspeccion, plan),
        }
    if not plan.aliados_a_crear and not plan.encargos_a_crear:
        return {
            "status": "noop",
            "message": "No faltan datos de prueba",
            "insercion": False,
            "dry_run": plan_a_dict(inspeccion, plan),
        }

    snapshot_reales = _snapshot_aliados_no_qa(inspeccion)
    snapshot_fin = _huella_financiera(db)
    n_terr = inspeccion.grupos_territoriales_activos
    creados: List[str] = []
    encargos_ids: List[Any] = []

    try:
        for item in plan.aliados_a_crear:
            if not db.codigo_disponible_para_asignar(item.codigo_propuesto):
                raise QaMadurezError(
                    f"El código propuesto {item.codigo_propuesto} dejó de estar libre"
                )
            resultado = db.crear_aliado(
                codigo=item.codigo_propuesto,
                nombre=item.nombre,
                marca=item.marca,
                oficio=item.oficio,
                codigo_postal=item.codigo_postal,
                email=item.email,
                telefono=item.telefono,
                estado="activo",
                descripcion_servicio=item.descripcion_servicio,
            )
            if resultado.get("status") != "success":
                raise QaMadurezError(
                    f"No se pudo crear aliado {item.codigo_propuesto}: {resultado.get('message')}"
                )
            if (resultado.get("estado") or "") != "activo":
                raise QaMadurezError(
                    f"Aliado {item.codigo_propuesto} no quedó activo ({resultado.get('estado')}). "
                    "No se continúa para no dejar datos a medias."
                )
            creados.append(item.codigo_propuesto)

        mapa_codigos = {p.codigo_propuesto: p.codigo_propuesto for p in plan.aliados_a_crear}
        for enc in plan.encargos_a_crear:
            sol = mapa_codigos.get(enc.solicitante_codigo, enc.solicitante_codigo)
            pro = mapa_codigos.get(enc.profesional_codigo, enc.profesional_codigo)
            creado = db.crear_contacto_ruana(
                sol,
                pro,
                servicio=enc.servicio,
                motivo_contacto=enc.motivo_contacto,
            )
            if creado.get("status") != "success":
                raise QaMadurezError(
                    f"No se pudo crear encargo {sol}->{pro}: {creado.get('message')}"
                )
            aceptado = db.aceptar_contacto_ruana(creado["id"], pro)
            if aceptado.get("status") != "success":
                raise QaMadurezError(
                    f"No se pudo aceptar encargo {creado['id']}: {aceptado.get('message')}"
                )
            if aceptado.get("estado") != "aceptado":
                raise QaMadurezError(
                    f"Encargo {creado['id']} no quedó aceptado ({aceptado.get('estado')})"
                )
            encargos_ids.append(creado["id"])
    except Exception as exc:
        return {
            "status": "error",
            "message": str(exc),
            "insercion": True,
            "aliados_qa_creados": creados,
            "encargos_ids": encargos_ids,
            "parcial": True,
        }

    integridad = validar_integridad(
        db,
        codigo_postal,
        snapshot_reales,
        snapshot_fin,
        n_terr,
        creados,
        encargos_ids,
    )
    return {
        "status": "success" if integridad["ok"] else "integrity_error",
        "insercion": True,
        "aliados_qa_creados": creados,
        "encargos_ids": encargos_ids,
        "integridad": integridad,
        "dry_run_aplicado": plan_a_dict(inspeccion, plan),
    }


def dry_run(db, codigo_postal: str = CP_OBJETIVO_DEFAULT) -> Dict[str, Any]:
    inspeccion = inspeccionar_cp(db, codigo_postal)
    plan = calcular_plan(db, inspeccion)
    payload = plan_a_dict(inspeccion, plan)
    payload["reporte"] = formatear_dry_run(inspeccion, plan)
    return payload
