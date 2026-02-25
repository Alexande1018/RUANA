#!/usr/bin/env python3
"""
Prueba: enviar una solicitud y verificar que todos los aliados del grupo la reciben.
- Crea una solicitud con un aliado (remitente).
- Comprueba que cada otro aliado del mismo grupo la ve por GET /api/solicitudes?codigo=X
- Comprueba que cada otro aliado la ve en GET /api/aliado/datos (campo solicitudes).
"""
import sqlite3
import requests
import sys
from pathlib import Path

BASE_URL = "http://127.0.0.1:5000"
DB_PATH = Path(__file__).parent / "ruana.db"


def get_aliados_del_grupo(grupo_id: int):
    """Devuelve lista de dict con codigo, nombre para el grupo_id."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        "SELECT codigo, nombre, grupo_id, codigo_postal FROM aliados WHERE grupo_id = ? AND estado = 'activo'",
        (grupo_id,),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def main():
    # 1) Elegir un grupo con al menos 2 aliados
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("""
        SELECT a.grupo_id, g.nombre AS grupo_nombre, COUNT(*) AS n
        FROM aliados a
        JOIN grupos g ON g.id = a.grupo_id
        WHERE a.grupo_id IS NOT NULL AND a.estado = 'activo' AND g.estado = 'activo'
        GROUP BY a.grupo_id
        HAVING n >= 2
        LIMIT 1
    """)
    row = cur.fetchone()
    conn.close()
    if not row:
        print("No hay ningún grupo con al menos 2 aliados activos. Crea grupos y aliados primero.")
        sys.exit(1)
    grupo_id, grupo_nombre, n_aliados = row[0], row[1], row[2]
    aliados = get_aliados_del_grupo(grupo_id)
    print(f"Grupo elegido: id={grupo_id}, nombre={grupo_nombre}, aliados={n_aliados}")
    print("Aliados:", [a["codigo"] for a in aliados])

    # 2) Enviar solicitud con el primer aliado
    remitente = aliados[0]
    codigo_remitente = remitente["codigo"]
    payload = {
        "codigo": codigo_remitente,
        "oficio": "Fontanería",
        "descripcion": "Prueba automática: solicitud para verificar que todos la reciben.",
    }
    try:
        r = requests.post(f"{BASE_URL}/api/solicitudes", json=payload, timeout=10)
    except requests.exceptions.ConnectionError:
        print("Error: no se pudo conectar a", BASE_URL, "- ¿está el servidor en marcha?")
        sys.exit(1)
    if r.status_code != 200:
        print("Error al crear solicitud:", r.status_code, r.text)
        sys.exit(1)
    data = r.json()
    if not data.get("ok"):
        print("Error respuesta:", data)
        sys.exit(1)
    solicitud_id = data.get("id")
    print(f"✓ Solicitud creada: id={solicitud_id} (remitente={codigo_remitente})")

    # 3) Para cada OTRO aliado del grupo, comprobar que la recibe
    receptores = [a for a in aliados if a["codigo"] != codigo_remitente]
    if not receptores:
        print("Solo hay un aliado en el grupo; no hay otros a los que verificar recepción.")
        sys.exit(0)

    errores = []
    for aliado in receptores:
        codigo = aliado["codigo"]
        # 3a) GET /api/solicitudes?codigo=X
        r = requests.get(f"{BASE_URL}/api/solicitudes", params={"codigo": codigo}, timeout=10)
        if r.status_code != 200:
            errores.append(f"Aliado {codigo}: GET /api/solicitudes devolvió {r.status_code}")
            continue
        data = r.json()
        lista = data.get("entrantes", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
        ids = [s.get("id") for s in lista if s.get("id")]
        if solicitud_id not in ids:
            errores.append(f"Aliado {codigo}: la solicitud {solicitud_id} NO está en GET /api/solicitudes (ids: {ids})")
        else:
            print(f"  ✓ {codigo}: ve la solicitud en GET /api/solicitudes")

        # 3b) GET /api/aliado/datos (POST con codigo) → campo solicitudes
        r2 = requests.post(f"{BASE_URL}/api/aliado/datos", json={"codigo": codigo}, timeout=10)
        if r2.status_code != 200:
            errores.append(f"Aliado {codigo}: GET /api/aliado/datos devolvió {r2.status_code}")
            continue
        body = r2.json()
        if body.get("status") != "success":
            errores.append(f"Aliado {codigo}: /api/aliado/datos status != success")
            continue
        solicitudes_panel = body.get("solicitudes") or []
        ids_panel = [s.get("id") for s in solicitudes_panel if s.get("id")]
        if solicitud_id not in ids_panel:
            errores.append(f"Aliado {codigo}: la solicitud {solicitud_id} NO está en /api/aliado/datos solicitudes (ids: {ids_panel})")
        else:
            print(f"  ✓ {codigo}: ve la solicitud en /api/aliado/datos (panel)")

    if errores:
        print("\nErrores:")
        for e in errores:
            print("  -", e)
        sys.exit(1)
    print("\n✓ Todos los aliados del grupo reciben la solicitud correctamente.")


if __name__ == "__main__":
    main()
