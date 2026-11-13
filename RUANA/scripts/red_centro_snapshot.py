#!/usr/bin/env python3
"""Instantánea verificable de la organización de producción para Red Centro.

SOLO LECTURA: usa los GET de admin (/api/aliados/listar, /api/admin/grupos,
/api/admin/territorio/estado). No escribe nada en producción.

Guarda solo campos organizativos (sin email, teléfono, PIN, bizum ni nombres de
persona). El fichero resultante NO se versiona: contiene códigos de aliado.

Uso:
  RUANA_ADMIN_PASSWORD=... python RUANA/scripts/red_centro_snapshot.py snapshot --out snap.json
  RUANA_ADMIN_PASSWORD=... python RUANA/scripts/red_centro_snapshot.py verify --snapshot snap.json
  python RUANA/scripts/red_centro_snapshot.py check --snapshot snap.json   # solo integridad local

Variables: RUANA_BASE_URL (def. https://ruana-4293f.web.app), RUANA_ADMIN_CODIGO,
RUANA_ADMIN_PASSWORD.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import sys
import urllib.request

CAMPOS_ALIADO = [
    "codigo", "oficio", "especializacion", "especializaciones", "codigo_postal", "zona",
    "grupo_id", "grupo_nombre", "estado", "estado_panel", "score", "score_panel",
    "es_titular_en_competencia", "es_suplente_activo", "es_retador_activo",
    "derrotas_competencia", "ciclos_consecutivos", "invitado_por_codigo",
    "total_contactos", "contactos_30d", "meses_sin_trabajo",
    "stripe_onboarding_completo", "creado_en",
]
CAMPOS_GRUPO = ["id", "nombre", "codigo_postal", "ciudad", "provincia", "estado", "tipo",
                "aliados_activos", "aliados_total", "fecha_creacion"]
CAMPOS_TERR = ["codigo", "codigo_postal", "estado", "grupo_cp", "grupo_estado", "grupo_id",
               "grupo_nombre", "grupo_tipo", "oficio"]
# Campos que pueden moverse por actividad normal (no por el piloto).
CAMPOS_VOLATILES = {"score_panel", "estado_panel", "total_contactos", "contactos_30d",
                    "meses_sin_trabajo", "aliados_activos", "aliados_total"}
CP_RED = re.compile(r"^(28|45)\d{3}$")


def canon(o) -> str:
    return json.dumps(o, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def sha(o) -> str:
    return hashlib.sha256(canon(o).encode("utf-8")).hexdigest()


def _req(url, token=None, data=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method="POST" if body else "GET")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def leer_produccion() -> dict:
    base = os.environ.get("RUANA_BASE_URL", "https://ruana-4293f.web.app").rstrip("/")
    pwd = os.environ.get("RUANA_ADMIN_PASSWORD")
    if not pwd:
        sys.exit("Falta RUANA_ADMIN_PASSWORD")
    codigo = os.environ.get("RUANA_ADMIN_CODIGO", "7772735")
    token = _req(f"{base}/api/admin/validar", data={"codigo": codigo, "password": pwd}).get("token")
    if not token:
        sys.exit("Login admin fallido")
    al = _req(f"{base}/api/aliados/listar", token)["aliados"]
    gr = _req(f"{base}/api/admin/grupos", token)["grupos"]
    te = _req(f"{base}/api/admin/territorio/estado", token)["aliados"]
    return organizar(al, gr, te)


def organizar(al, gr, te) -> dict:
    return {
        "aliados": sorted(({k: a.get(k) for k in CAMPOS_ALIADO} for a in al), key=lambda x: str(x["codigo"])),
        "grupos": sorted(({k: g.get(k) for k in CAMPOS_GRUPO} for g in gr), key=lambda x: x["id"]),
        "territorio": sorted(({k: t.get(k) for k in CAMPOS_TERR} for t in te), key=lambda x: str(x["codigo"])),
    }


def elegibles(org: dict) -> list:
    return sorted(
        str(a["codigo"]) for a in org["aliados"]
        if str(a.get("estado") or "").lower() == "activo" and a.get("grupo_id")
        and CP_RED.match(str(a.get("codigo_postal") or ""))
    )


def comparar(orig: dict, actual: dict, estricto: bool = False) -> list:
    dif = []
    for clave, idk in (("aliados", "codigo"), ("grupos", "id"), ("territorio", "codigo")):
        act = {str(x[idk]): x for x in actual.get(clave, [])}
        for x in orig.get(clave, []):
            cur = act.get(str(x[idk]))
            if cur is None:
                dif.append(f"{clave}:{x[idk]} ausente")
                continue
            for k, v in x.items():
                if not estricto and k in CAMPOS_VOLATILES:
                    continue
                if cur.get(k) != v:
                    dif.append(f"{clave}:{x[idk]}.{k}: {v!r} -> {cur.get(k)!r}")
    return dif


def cmd_snapshot(args):
    org = leer_produccion()
    snap = {
        "kind": "red_centro_snapshot_produccion",
        "version": 1,
        "tomada_en": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "fuente": "GET /api/aliados/listar, /api/admin/grupos, /api/admin/territorio/estado (solo lectura)",
        "nota": "Solo campos organizativos; sin email, telefono, PIN, bizum ni nombres de persona.",
        "checksum_organizacion_sha256": sha(org),
        "elegibles_red_centro": elegibles(org),
        **org,
    }
    txt = json.dumps(snap, ensure_ascii=False, indent=2, sort_keys=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(txt)
    fsha = hashlib.sha256(txt.encode("utf-8")).hexdigest()
    with open(args.out + ".sha256", "w", encoding="utf-8") as f:
        f.write(f"{fsha}  {os.path.basename(args.out)}\n")
    print(json.dumps({"fichero": args.out, "sha256_fichero": fsha,
                      "checksum_organizacion_sha256": snap["checksum_organizacion_sha256"],
                      "elegibles": snap["elegibles_red_centro"]}, ensure_ascii=False, indent=2))


def _cargar(path):
    with open(path, encoding="utf-8") as f:
        snap = json.load(f)
    org = {k: snap[k] for k in ("aliados", "grupos", "territorio")}
    if sha(org) != snap["checksum_organizacion_sha256"]:
        sys.exit("ERROR: la instantánea no cuadra con su checksum interno (alterada)")
    return snap, org


def cmd_check(args):
    snap, _ = _cargar(args.snapshot)
    print(f"OK integridad: {snap['checksum_organizacion_sha256']}")


def cmd_verify(args):
    snap, org = _cargar(args.snapshot)
    actual = leer_produccion()
    dif = comparar(org, actual, estricto=args.estricto)
    altas = sorted({str(a["codigo"]) for a in actual["aliados"]} - {str(a["codigo"]) for a in org["aliados"]})
    print(json.dumps({"identica": not dif, "diferencias": dif, "altas_nuevas_conservadas": altas,
                      "checksum_original": snap["checksum_organizacion_sha256"]},
                     ensure_ascii=False, indent=2))
    sys.exit(0 if not dif else 2)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("snapshot"); s.add_argument("--out", required=True); s.set_defaults(fn=cmd_snapshot)
    c = sub.add_parser("check"); c.add_argument("--snapshot", required=True); c.set_defaults(fn=cmd_check)
    v = sub.add_parser("verify"); v.add_argument("--snapshot", required=True)
    v.add_argument("--estricto", action="store_true", help="Incluye campos volátiles (score_panel, contadores)")
    v.set_defaults(fn=cmd_verify)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
