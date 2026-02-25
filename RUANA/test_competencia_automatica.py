#!/usr/bin/env python3
"""
TEST COMPLETO DE COMPETENCIA AUTOMÁTICA (RUANA v1)

Prueba controlada para verificar activación automática de competencia e ingreso de suplente.

NOTA: Miguel Castaño (55745) NO cumple requisitos para competencia:
  - Sin grupo asignado (grupo_id NULL)
  - Único Gestor Inmobiliario (no hay suplente candidato)

Se usa 11111 (Electricista, grupo 17, CP 28001) que SÍ cumple:
  - Grupo con CP
  - Suplente: 22222 (Electricista, score 75, mismo CP)
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from core.db_manager import get_db, DB_PATH
import sqlite3

# Configuración: usar 11111 para la prueba (cumple requisitos)
ALIADO_EN_RIESGO = '11111'
SCORE_OBJETIVO = 30
UMBRAL = 35


def verificar_precondiciones(db) -> bool:
    """Verifica que el aliado cumple requisitos para competencia."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT a.codigo, a.nombre, a.oficio, a.score, a.grupo_id, a.estado,
               g.codigo_postal, g.ciudad, g.provincia, g.estado as grupo_estado
        FROM aliados a
        LEFT JOIN grupos g ON g.id = a.grupo_id
        WHERE a.codigo = ?
    """, (ALIADO_EN_RIESGO,))
    row = cur.fetchone()
    conn.close()
    if not row:
        print(f"❌ Aliado {ALIADO_EN_RIESGO} no encontrado")
        return False
    r = dict(row)
    print(f"📋 Aliado: {r['nombre']} ({r['codigo']})")
    print(f"   Oficio: {r['oficio']} | Score: {r['score']} | Estado: {r['estado']}")
    print(f"   Grupo: {r['grupo_id']} | CP: {r['codigo_postal']} | Ciudad: {r['ciudad']}")
    ok = True
    if r['estado'] != 'activo':
        print("   ❌ Debe estar activo")
        ok = False
    if not r['grupo_id']:
        print("   ❌ Debe tener grupo asignado")
        ok = False
    if not r['oficio']:
        print("   ❌ Debe tener oficio definido")
        ok = False
    if not r['codigo_postal']:
        print("   ❌ El grupo debe tener código postal")
        ok = False
    if ok:
        print("   ✅ Precondiciones OK")
    return ok


def forzar_score_y_disparar_competencia(db):
    """Aplica cambio de score para cruzar umbral. Bypass límite ±10/día para test."""
    # Añadir bypass temporal: llamar a _iniciar_competencia_si_procede tras forzar score
    # porque aplicar_cambio_score limita a ±10/día
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT score FROM aliados WHERE codigo = ?", (ALIADO_EN_RIESGO,))
    row = cur.fetchone()
    if not row:
        conn.close()
        print("❌ Aliado no encontrado")
        return False
    score_actual = int(row[0] or 0)
    delta_necesario = SCORE_OBJETIVO - score_actual
    conn.close()

    # Aplicar con límite: varias llamadas de -10
    aplicado_total = 0
    for _ in range(10):  # máximo 10 iteraciones
        r = db.aplicar_cambio_score(ALIADO_EN_RIESGO, -10, motivo="TEST competencia automática")
        if r.get('status') != 'success':
            print(f"❌ Error: {r.get('message')}")
            break
        a = r.get('aplicado', 0)
        if a == 0:
            print("   (Límite diario alcanzado, no se puede bajar más hoy)")
            break
        aplicado_total += a
        print(f"   Aplicado delta {a}, score ahora: {r.get('score_final')}")
        if r.get('score_final', 100) < UMBRAL:
            print(f"✅ Score bajo umbral ({UMBRAL}). Competencia debería haberse iniciado.")
            return True
    print(f"⚠️ Tras {aplicado_total} puntos de bajada, no se cruzó umbral en este día.")
    print("   (Límite ±10/día: ejecutar mañana o añadir bypass para test)")
    return False


def forzar_score_directo_y_disparar(db):
    """Alternativa: forzar score vía SQL y llamar _iniciar_competencia manualmente para test."""
    print("\n--- Alternativa: forzar score directo para test ---")
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT score, grupo_id FROM aliados WHERE codigo = ?", (ALIADO_EN_RIESGO,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return False
    score_ant = int(row[0] or 0)
    # Solo si ya está >= umbral, bajamos directo (bypass límite para test)
    if score_ant < UMBRAL:
        print(f"   Score ya es {score_ant} (< {UMBRAL})")
        conn.close()
        return True
    cur.execute("UPDATE aliados SET score = ? WHERE codigo = ?", (SCORE_OBJETIVO, ALIADO_EN_RIESGO))
    cur.execute("INSERT INTO score_movimientos (codigo_aliado, delta, motivo) VALUES (?, ?, ?)",
                (ALIADO_EN_RIESGO, SCORE_OBJETIVO - score_ant, "TEST forzado competencia"))
    conn.commit()
    conn.close()
    print(f"   Score forzado: {score_ant} → {SCORE_OBJETIVO}")
    # Disparar competencia manualmente (simula lo que haría aplicar_cambio_score)
    result = db._iniciar_competencia_si_procede(ALIADO_EN_RIESGO)
    if result:
        print(f"✅ Competencia iniciada: {result}")
        return True
    print("❌ _iniciar_competencia_si_procede no retornó resultado (¿no hay suplente?)")
    return False


def verificar_competencia(db):
    """Verifica registro en tabla competencia."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT * FROM competencia WHERE estado = 'activa' ORDER BY id DESC LIMIT 5")
    rows = cur.fetchall()
    cur.execute("PRAGMA table_info(competencia)")
    cols = [c[1] for c in cur.fetchall()]
    cur.close()
    conn.close()
    if not rows:
        print("❌ No hay competencias activas en tabla competencia")
        return False
    print("\n✅ Competencias activas:")
    for row in rows:
        d = dict(zip(cols, row))
        print(f"   id={d.get('id')} grupo_id={d.get('grupo_id')} oficio={d.get('oficio')}")
        print(f"   titular={d.get('aliado_original_codigo')} suplente={d.get('suplente_codigo')}")
        print(f"   estado={d.get('estado')} fin_prevista={d.get('fecha_fin_prevista')}")
    return True


def verificar_grupo_en_competencia(db):
    """Verifica que el grupo pasó a en_competencia."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT g.id, g.codigo_postal, g.estado
        FROM grupos g
        JOIN competencia c ON c.grupo_id = g.id
        WHERE c.estado = 'activa'
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    if not rows:
        return False
    for r in rows:
        print(f"   Grupo {r[0]} (CP {r[1]}): estado = {r[2]}")
        if r[2] != 'en_competencia':
            print("   ❌ Grupo debería estar en_competencia")
            return False
    print("   ✅ Grupos en competencia")
    return True


def verificar_metricas(db):
    """Verifica contar_suplentes_activos y grupos en competencia."""
    n_supl = db.contar_suplentes_activos()
    g = db.contar_grupos()
    print(f"\n📊 Métricas: suplentes activos = {n_supl}")
    print(f"   Grupos: total={g.get('total')} activos={g.get('activos')} en_competencia={g.get('en_competencia')}")


def main():
    print("=" * 60)
    print("TEST COMPETENCIA AUTOMÁTICA RUANA")
    print("=" * 60)
    db = get_db()

    if not verificar_precondiciones(db):
        print("\n⚠️ Usar aliado que cumpla: grupo + CP + oficio con suplente elegible.")
        print("   Ej: 11111 (Electricista, grupo 17, CP 28001)")
        return 1

    # Intentar vía aplicar_cambio_score (respetando límite)
    print("\n1️⃣ Aplicar cambio de score (vía aplicar_cambio_score)")
    exito = forzar_score_y_disparar_competencia(db)
    if not exito:
        # Si límite impidió, usar forzado directo para completar test
        exito = forzar_score_directo_y_disparar(db)

    if not exito:
        print("\n❌ No se pudo disparar competencia")
        return 1

    print("\n2️⃣ Verificar tabla competencia")
    verificar_competencia(db)

    print("\n3️⃣ Verificar estado grupo")
    verificar_grupo_en_competencia(db)

    print("\n4️⃣ Métricas")
    verificar_metricas(db)

    print("\n" + "=" * 60)
    print("✅ TEST COMPLETADO")
    print("   Comprobar panel admin: Suplentes, Grupos en competencia")
    print("=" * 60)
    return 0


if __name__ == '__main__':
    sys.exit(main())
