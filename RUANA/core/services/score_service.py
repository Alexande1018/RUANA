"""
Servicio de Score RUANA.

Reglas de mutación de score: rango [0, 500], tope ±10 por día.
La orquestación de competencia por umbral permanece en la fachada DBManager.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from core.repositories.score_repo import ScoreRepo

_SCORE_MIN = 0
_SCORE_MAX = 500
_DELTA_DIA_MAX = 10


def calcular_delta_aplicar(delta: int, delta_hoy: int) -> int:
    """Aplica el tope diario ±10 al delta solicitado."""
    if delta > 0:
        techo_dia = _DELTA_DIA_MAX - delta_hoy
        return min(delta, max(0, techo_dia))
    piso_dia = -_DELTA_DIA_MAX - delta_hoy
    return max(delta, min(0, piso_dia))


def calcular_score_nuevo(score_actual: int, delta_aplicar: int) -> tuple[int, int]:
    """Devuelve (score_nuevo, delta_real) respetando [0, 500]."""
    score_nuevo = max(_SCORE_MIN, min(_SCORE_MAX, score_actual + delta_aplicar))
    delta_real = score_nuevo - score_actual
    return score_nuevo, delta_real


def aplicar_cambio_score(
    cursor,
    codigo_aliado: str,
    delta: int,
    motivo: str = "",
    repo: Optional[ScoreRepo] = None,
) -> Dict[str, Any]:
    """
    Aplica un cambio de score en el cursor dado (sin commit ni side-effects externos).

    Returns:
        Dict con status, aplicado, score_final y, si hubo cambio o no-op con aliado,
        score_anterior. No dispara competencia.
    """
    if not codigo_aliado or delta == 0:
        return {"status": "success", "aplicado": 0, "score_final": None}

    repo = repo or ScoreRepo()
    score_actual = repo.obtener_score(cursor, codigo_aliado)
    if score_actual is None:
        return {
            "status": "error",
            "message": f"Aliado {codigo_aliado} no encontrado",
        }

    delta_hoy = repo.delta_score_hoy(cursor, codigo_aliado)
    delta_aplicar = calcular_delta_aplicar(delta, delta_hoy)
    score_nuevo, delta_real = calcular_score_nuevo(score_actual, delta_aplicar)

    if delta_real == 0:
        return {
            "status": "success",
            "aplicado": 0,
            "score_final": score_actual,
            "score_anterior": score_actual,
        }

    movimiento_id = repo.insertar_movimiento(cursor, codigo_aliado, delta_real, motivo)
    repo.actualizar_score_aliado(cursor, codigo_aliado, score_nuevo)
    repo.registrar_notificacion_cambio_score(
        cursor=cursor,
        codigo_aliado=codigo_aliado,
        delta_real=delta_real,
        score_nuevo=score_nuevo,
        motivo=motivo,
        movimiento_id=movimiento_id,
    )
    return {
        "status": "success",
        "aplicado": delta_real,
        "score_final": score_nuevo,
        "score_anterior": score_actual,
    }

# --- Reglas y penalizaciones (fase 3, extraídas de DBManager) ---

def score_a_estado(score: Any) -> str:
    """
    Calcula el estado RUANA a partir del score (siempre derivado, sin almacenar).
    ÉLITE 350-500, DESTACADO 200-349, ESTABLE 50-199, EN RIESGO 15-49, COMPETENCIA 0-14.
    """
    try:
        s = int(score) if score is not None else 0
    except (TypeError, ValueError):
        s = 0
    if s >= 350:
        return 'ÉLITE'
    if s >= 200:
        return 'DESTACADO'
    if s >= 50:
        return 'ESTABLE'
    if s >= 15:
        return 'EN RIESGO'
    return 'COMPETENCIA'

def aplicar_penalizacion_descendiente_en_competencia(db, codigo_titular: str, competencia_id: int
) -> List[Dict[str, Any]]:
    """
    Penalización 4: si un hijo o nieto (linaje via invitado_por_codigo) entra en
    competencia, -2 al padre (gen1) y -2 al abuelo (gen2). Una vez por competencia.
    No aplica a admin/sistema. El suplente no dispara esta regla.
    """
    codigo_titular = (codigo_titular or '').strip()
    if not codigo_titular or not competencia_id:
        return []
    aplicados: List[Dict[str, Any]] = []
    for ancestro, gen in db.ancestros_referidos_para_score(codigo_titular, max_generaciones=2):
        motivo = f'descendiente_entra_competencia_gen{gen}_{int(competencia_id)}'
        if db._ya_aplicado_motivo_score(ancestro, motivo):
            continue
        result = db.aplicar_cambio_score(ancestro, -2, motivo)
        aplicados.append({
            'codigo': ancestro,
            'generacion': gen,
            'motivo': motivo,
            'result': result,
        })
    return aplicados

def aplicar_penalizaciones_contactos_abiertos(db, codigo_aliado: str) -> None:
    """
    Aplica penalizaciones por contactos sin cerrar: 7 días -2, 21 días -5.
    Solo aplica una vez por contacto y por tipo (registrado en contacto_penalizaciones_aplicadas).
    """
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            # Contactos abiertos donde el aliado es solicitante o profesional
            cursor.execute("""
                SELECT id, solicitante_codigo, profesional_codigo,
                       COALESCE(creado_en, actualizado_en) as ref_fecha
                FROM contactos_ruana
                WHERE estado IN ('iniciado', 'aceptado', 'trabajo_en_progreso')
                  AND (solicitante_codigo = ? OR profesional_codigo = ?)
            """, (codigo_aliado, codigo_aliado))
            for row in cursor.fetchall():
                cid, sol, prof, ref = row
                ref_ts = ref or datetime.now().isoformat()
                try:
                    from datetime import datetime as dt
                    d = dt.fromisoformat(ref_ts.replace('Z', '+00:00'))
                    if d.tzinfo:
                        d = d.replace(tzinfo=None)
                except Exception:
                    d = datetime.now()
                dias = (datetime.now() - d).days
                repo = ScoreRepo()
                for tipo, umbral, penalizacion in [('21d', 21, -5), ('7d', 7, -2)]:
                    if dias < umbral:
                        continue
                    if repo.existe_penalizacion_aplicada(cursor, cid, tipo):
                        continue
                    db.aplicar_cambio_score(codigo_aliado, penalizacion, f'contacto_sin_cerrar_{tipo}')
                    repo.insertar_penalizacion_aplicada(cursor, cid, tipo)
                    conn.commit()
        except Exception as e:
            pass
        finally:
            conn.close()
    # Penalización 5: chat sin respuesta ≥ 48 h
    try:
        db.aplicar_penalizacion_chat_sin_respuesta_48h(codigo_aliado)
    except Exception:
        pass
    # Penalización 6: semana(s) sin acceso a la app
    try:
        db.aplicar_penalizacion_sin_acceso_semanal(codigo_aliado)
    except Exception:
        pass
    # Penalización 9: sin comprobante de Apoyo ≥ 3 días
    try:
        db.aplicar_penalizacion_comprobante_apoyo_3d(codigo_aliado)
    except Exception:
        pass

def aplicar_penalizacion_comprobante_apoyo_3d(db, codigo_aliado: str) -> None:
    """
    Penalización 9: Apoyo RUANA generado sin subir comprobante ≥ 3 días → -3
    al profesional. Reloj desde fecha_cierre. Solo estado_pago=pendiente_pago
    sin comprobante_ruta. Una vez por contacto (tipo comprobante_3d).
    """
    codigo_aliado = (codigo_aliado or '').strip()
    if not codigo_aliado:
        return
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, fecha_cierre
                FROM contactos_ruana
                WHERE profesional_codigo = ?
                  AND estado = 'trabajo_cerrado'
                  AND COALESCE(apoyo_ruana, 0) > 0
                  AND estado_pago = 'pendiente_pago'
                  AND (comprobante_ruta IS NULL OR TRIM(COALESCE(comprobante_ruta, '')) = '')
                  AND fecha_cierre IS NOT NULL
            """, (codigo_aliado,))
            filas = cursor.fetchall()
            for row in filas:
                cid, fecha_cierre = row[0], row[1]
                ref = db._parse_timestamp(fecha_cierre)
                if not ref:
                    continue
                dias = (datetime.now() - ref).days
                if dias < 3:
                    continue
                repo = ScoreRepo()
                if repo.existe_penalizacion_aplicada(cursor, cid, 'comprobante_3d'):
                    continue
                motivo = f'comprobante_apoyo_3d_{int(cid)}'
                if db._ya_aplicado_motivo_score(codigo_aliado, motivo):
                    continue
                result = db.aplicar_cambio_score(codigo_aliado, -3, motivo)
                if result.get('status') != 'success' or int(result.get('aplicado') or 0) == 0:
                    continue
                repo.insertar_penalizacion_aplicada(cursor, cid, 'comprobante_3d')
                conn.commit()
        except Exception:
            pass
        finally:
            try:
                conn.close()
            except Exception:
                pass

def aplicar_penalizacion_chat_sin_respuesta_48h(db, codigo_aliado: str) -> None:
    """
    Penalización 5: conversación con mensajes dejada sin respuesta ≥ 48 h → -2
    al aliado que no respondió (el que no es el último emisor).

    No se aplica si el encargo/chat se cerró de forma adecuada:
    - estado en trabajo_cerrado / no_concretado / cerrado_no_concretado
    - o ambas partes dieron por terminado el chat (contacto_panel_oculto)
    Sin mensajes no aplica. Una vez por contacto (tipo chat_48h).
    """
    codigo_aliado = (codigo_aliado or '').strip()
    if not codigo_aliado:
        return
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT c.id, c.solicitante_codigo, c.profesional_codigo, c.estado
                FROM contactos_ruana c
                WHERE (c.solicitante_codigo = ? OR c.profesional_codigo = ?)
                  AND c.estado IN ('iniciado', 'aceptado', 'trabajo_en_progreso', 'en_conversacion')
            """, (codigo_aliado, codigo_aliado))
            filas = cursor.fetchall()
            for row in filas:
                cid, sol, prof, estado = row[0], row[1], row[2], (row[3] or '').strip()
                if estado in db._ESTADOS_CIERRE_ADECUADO_CHAT:
                    continue
                # Ambas partes dieron por terminado el chat → no penalizar
                cursor.execute(
                    "SELECT COUNT(*) FROM contacto_panel_oculto WHERE contacto_id = ?",
                    (cid,),
                )
                if int((cursor.fetchone() or [0])[0] or 0) >= 2:
                    continue
                cursor.execute("""
                    SELECT emisor_codigo, creado_en FROM chat_mensajes
                    WHERE contacto_id = ?
                    ORDER BY creado_en DESC, id DESC LIMIT 1
                """, (cid,))
                ultimo = cursor.fetchone()
                if not ultimo:
                    continue  # sin mensajes → no hay "quién debía responder"
                emisor_ultimo = str(ultimo[0] or '').strip()
                if not emisor_ultimo or emisor_ultimo == codigo_aliado:
                    continue  # este aliado respondió el último (o vacío)
                # Debe ser la otra parte del contacto
                partes = {str(sol or '').strip(), str(prof or '').strip()}
                if codigo_aliado not in partes or emisor_ultimo not in partes:
                    continue
                ref = db._parse_timestamp(ultimo[1])
                if not ref or not db._chat_esta_expirado(ref):
                    continue  # aún dentro de las 48 h
                repo = ScoreRepo()
                if repo.existe_penalizacion_aplicada(cursor, cid, 'chat_48h'):
                    continue
                motivo = f'chat_sin_respuesta_48h_{int(cid)}'
                if db._ya_aplicado_motivo_score(codigo_aliado, motivo):
                    continue
                db.aplicar_cambio_score(codigo_aliado, -2, motivo)
                repo.insertar_penalizacion_aplicada(cursor, cid, 'chat_48h')
                conn.commit()
        except Exception:
            pass
        finally:
            try:
                conn.close()
            except Exception:
                pass

def _es_invitador_elegible_score(db, codigo: str, excluir: Optional[set] = None) -> bool:
    """False para vacío, autoexclusión, códigos sistema/admin o aliados inexistentes."""
    codigo = (codigo or '').strip()
    if not codigo:
        return False
    if excluir and codigo in excluir:
        return False
    if codigo.upper().startswith('RUANA-ADMIN'):
        return False
    aliado = db.obtener_aliado_por_codigo(codigo)
    if not aliado:
        return False
    if (aliado.get('estado') or '').strip() == 'sistema':
        return False
    return True

def ancestros_referidos_para_score(db,
    codigo_aliado: str,
    max_generaciones: int = 2,
    excluir: Optional[set] = None,
) -> List[Tuple[str, int]]:
    """
    Sube por aliados.invitado_por_codigo hasta max_generaciones.
    Devuelve [(codigo_ancestro, generacion), ...] (1 = padre, 2 = abuelo).
    Omite sistema/admin y códigos en excluir (p. ej. participantes del contacto).
    """
    codigo_aliado = (codigo_aliado or '').strip()
    if not codigo_aliado or max_generaciones < 1:
        return []
    excluir_set = set(excluir or set())
    excluir_set.add(codigo_aliado)
    resultado: List[Tuple[str, int]] = []
    actual = codigo_aliado
    vistos = {codigo_aliado}
    for generacion in range(1, max_generaciones + 1):
        aliado = db.obtener_aliado_por_codigo(actual)
        if not aliado:
            break
        padre = (aliado.get('invitado_por_codigo') or '').strip()
        if not padre or padre in vistos:
            break
        vistos.add(padre)
        if db._es_invitador_elegible_score(padre, excluir_set):
            resultado.append((padre, generacion))
        actual = padre
    return resultado

def aplicar_penalizacion_chat_agotado_sin_resultado(db, contacto_id: int, codigo_aliado: str
) -> Optional[Dict[str, Any]]:
    """
    Penalización 7: al agotar el chat (30 mensajes) sin declarar resultado → -2
    solo a quien envió el mensaje que agotó el cupo.
    No aplica si el encargo ya está en cierre adecuado.
    Motivo: chat_agotado_sin_resultado_{contacto_id} (una vez).
    """
    codigo_aliado = (codigo_aliado or '').strip()
    if not codigo_aliado or not contacto_id:
        return None
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT estado, solicitante_codigo, profesional_codigo FROM contactos_ruana WHERE id = ?",
                (int(contacto_id),),
            )
            row = cursor.fetchone()
            if not row:
                return None
            estado = (row[0] or '').strip()
            sol = str(row[1] or '').strip()
            prof = str(row[2] or '').strip()
            if estado in db._ESTADOS_CIERRE_ADECUADO_CHAT:
                return None
            if codigo_aliado not in (sol, prof):
                return None
        except Exception:
            return None
        finally:
            try:
                conn.close()
            except Exception:
                pass
    motivo = f'chat_agotado_sin_resultado_{int(contacto_id)}'
    if db._ya_aplicado_motivo_score(codigo_aliado, motivo):
        return None
    # También registrar tipo en contacto_penalizaciones_aplicadas
    repo = ScoreRepo()
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            if repo.existe_penalizacion_aplicada(cursor, int(contacto_id), 'chat_agotado'):
                return None
        except Exception:
            return None
        finally:
            try:
                conn.close()
            except Exception:
                pass
    result = db.aplicar_cambio_score(codigo_aliado, -2, motivo)
    if result.get('status') == 'success' and int(result.get('aplicado') or 0) != 0:
        with db._lock:
            try:
                conn = db._connect()
                cursor = conn.cursor()
                repo.insertar_penalizacion_aplicada(cursor, int(contacto_id), 'chat_agotado')
                conn.commit()
            except Exception:
                pass
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
        return {'codigo': codigo_aliado, 'motivo': motivo, 'result': result}
    return None

def _ya_aplicado_motivo_score(db, codigo_aliado: str, motivo: str) -> bool:
    codigo_aliado = (codigo_aliado or '').strip()
    motivo = (motivo or '').strip()
    if not codigo_aliado or not motivo:
        return True
    repo = ScoreRepo()
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            return repo.existe_movimiento_motivo(cursor, codigo_aliado, motivo)
        except Exception:
            return True
        finally:
            try:
                conn.close()
            except Exception:
                pass

def listar_respuestas_rapidas_regla5(db, codigo_profesional: str) -> List[Dict[str, Any]]:
    """
    Respuestas válidas Regla 5: primer mensaje de chat del cliente (solicitante)
    y primer mensaje posterior del profesional en el mismo contacto, con delta ≤ 1 h.
    Devuelve una entrada por solicitante (la respuesta válida más temprana).
    """
    codigo_profesional = (codigo_profesional or '').strip()
    if not codigo_profesional:
        return []
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT c.id AS contacto_id, c.solicitante_codigo,
                       m.id AS msg_id, m.emisor_codigo, m.creado_en
                FROM contactos_ruana c
                JOIN chat_mensajes m ON m.contacto_id = c.id
                WHERE c.profesional_codigo = ?
                ORDER BY c.id ASC, m.creado_en ASC, m.id ASC
                """,
                (codigo_profesional,),
            )
            rows = [dict(r) for r in cursor.fetchall()]
        except Exception:
            return []
        finally:
            try:
                conn.close()
            except Exception:
                pass

    por_contacto: Dict[int, Dict[str, Any]] = {}
    for row in rows:
        cid = int(row['contacto_id'])
        bucket = por_contacto.setdefault(cid, {
            'solicitante_codigo': str(row.get('solicitante_codigo') or '').strip(),
            'msgs': [],
        })
        bucket['msgs'].append(row)

    por_cliente: Dict[str, Dict[str, Any]] = {}
    for cid, data in por_contacto.items():
        sol = data['solicitante_codigo']
        pro = codigo_profesional
        if not sol or sol == pro:
            continue
        primer_cliente = None
        for msg in data['msgs']:
            if str(msg.get('emisor_codigo') or '').strip() == sol:
                primer_cliente = msg
                break
        if not primer_cliente:
            continue
        ts_cliente = db._parse_timestamp(primer_cliente.get('creado_en'))
        if not ts_cliente:
            continue
        primer_pro = None
        for msg in data['msgs']:
            if str(msg.get('emisor_codigo') or '').strip() != pro:
                continue
            ts_pro = db._parse_timestamp(msg.get('creado_en'))
            if not ts_pro or ts_pro < ts_cliente:
                continue
            if ts_pro == ts_cliente and int(msg.get('msg_id') or 0) <= int(primer_cliente.get('msg_id') or 0):
                continue
            primer_pro = msg
            ts_respuesta = ts_pro
            break
        if not primer_pro:
            continue
        delta = (ts_respuesta - ts_cliente).total_seconds()
        if delta < 0 or delta > db.REGLA5_SEGUNDOS_RESPUESTA:
            continue
        candidato = {
            'contacto_id': cid,
            'solicitante_codigo': sol,
            'cliente_msg_id': int(primer_cliente.get('msg_id') or 0),
            'respuesta_msg_id': int(primer_pro.get('msg_id') or 0),
            'cliente_msg_en': ts_cliente,
            'respuesta_en': ts_respuesta,
        }
        prev = por_cliente.get(sol)
        if prev is None or candidato['respuesta_en'] < prev['respuesta_en']:
            por_cliente[sol] = candidato

    return sorted(
        por_cliente.values(),
        key=lambda x: (x['respuesta_en'], x['contacto_id']),
    )

def evaluar_regla5_respuestas_chat(db,
    codigo_profesional: str,
) -> Optional[Tuple[str, int, str]]:
    """
    Regla 5: el profesional responde (<1 h) al primer mensaje de chat de 3 clientes
    distintos → +3. Cada lote de 3 clientes otorga el bonus una vez
    (motivo único por conjunto de códigos de cliente).
    """
    codigo_profesional = (codigo_profesional or '').strip()
    if not codigo_profesional:
        return None
    respuestas = db.listar_respuestas_rapidas_regla5(codigo_profesional)
    if len(respuestas) < db.REGLA5_CLIENTES_UMBRAL:
        return None
    for i in range(0, len(respuestas) - db.REGLA5_CLIENTES_UMBRAL + 1, db.REGLA5_CLIENTES_UMBRAL):
        lote = respuestas[i:i + db.REGLA5_CLIENTES_UMBRAL]
        if len(lote) < db.REGLA5_CLIENTES_UMBRAL:
            break
        codes = sorted(item['solicitante_codigo'] for item in lote)
        motivo = f"regla5_3_clientes_respuesta_1h_{'_'.join(codes)}"
        if not db._ya_aplicado_motivo_score(codigo_profesional, motivo):
            return (codigo_profesional, db.REGLA5_DELTA, motivo)
    return None

def aplicar_penalizacion_disputa_perdida(db, contacto_id: int, decision: str
) -> Optional[Dict[str, Any]]:
    """
    Penalización 8: perder una disputa resuelta por admin → -3 al perdedor.
    decision=contratante → pierde el profesional; decision=profesional → pierde el solicitante.
    No aplica si decision=rechazado. Motivo: disputa_perdida_{contacto_id}.
    """
    decision = (decision or '').strip().lower()
    if decision not in ('contratante', 'profesional') or not contacto_id:
        return None
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT solicitante_codigo, profesional_codigo FROM contactos_ruana WHERE id = ?",
                (int(contacto_id),),
            )
            row = cursor.fetchone()
            if not row:
                return None
            sol = str(row[0] or '').strip()
            prof = str(row[1] or '').strip()
        except Exception:
            return None
        finally:
            try:
                conn.close()
            except Exception:
                pass
    perdedor = prof if decision == 'contratante' else sol
    if not perdedor:
        return None
    motivo = f'disputa_perdida_{int(contacto_id)}'
    if db._ya_aplicado_motivo_score(perdedor, motivo):
        return None
    repo = ScoreRepo()
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            if repo.existe_penalizacion_aplicada(cursor, int(contacto_id), 'disputa_perdida'):
                return None
        except Exception:
            return None
        finally:
            try:
                conn.close()
            except Exception:
                pass
    result = db.aplicar_cambio_score(perdedor, -3, motivo)
    if result.get('status') == 'success' and int(result.get('aplicado') or 0) != 0:
        with db._lock:
            try:
                conn = db._connect()
                cursor = conn.cursor()
                repo.insertar_penalizacion_aplicada(cursor, int(contacto_id), 'disputa_perdida')
                conn.commit()
            except Exception:
                pass
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
        return {'codigo': perdedor, 'motivo': motivo, 'result': result}
    return None

def evaluar_regla7_declaracion_24h(db,
    contacto_id: int,
    fecha_declaracion: Optional[Any] = None,
) -> Optional[Tuple[str, int, str]]:
    """
    Regla 7: el contratante declara el importe antes de 24 h desde contactos_ruana.creado_en
    → +2 al solicitante. Una vez por contacto (motivo regla7_declaracion_24h_{id}).
    """
    try:
        contacto_id = int(contacto_id)
    except (TypeError, ValueError):
        return None
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, solicitante_codigo, creado_en, fecha_declaracion_solicitante
                FROM contactos_ruana WHERE id = ?
            """, (contacto_id,))
            row = cursor.fetchone()
            if not row:
                return None
            d = dict(row)
        except Exception:
            return None
        finally:
            try:
                conn.close()
            except Exception:
                pass
    sol = str(d.get('solicitante_codigo') or '').strip()
    if not sol or not db._es_invitador_elegible_score(sol):
        return None
    ts_inicio = db._parse_timestamp(d.get('creado_en'))
    ts_decl = db._parse_timestamp(
        fecha_declaracion if fecha_declaracion is not None else d.get('fecha_declaracion_solicitante')
    )
    if not ts_inicio or not ts_decl:
        return None
    if ts_decl < ts_inicio:
        return None
    if (ts_decl - ts_inicio) >= timedelta(hours=db.REGLA7_HORAS_LIMITE):
        return None
    motivo = f'regla7_declaracion_24h_{contacto_id}'
    if db._ya_aplicado_motivo_score(sol, motivo):
        return None
    return (sol, db.REGLA7_DELTA, motivo)

def _dia_hoy_servidor(db) -> str:
    """Día calendario del servidor (local) en YYYY-MM-DD."""
    return datetime.now().strftime('%Y-%m-%d')

def _tiene_premio_regla8_reciente(db, codigo_aliado: str, dia_fin: str) -> bool:
    """
    True si ya hay un premio Regla 8 cuyo día de cierre está en [dia_fin-6, dia_fin].
    Evita +3 diario tras la 1ª racha; la siguiente racha completa puede premiarse.
    """
    codigo_aliado = (codigo_aliado or '').strip()
    dia_fin = (dia_fin or '').strip()
    if not codigo_aliado or not dia_fin:
        return True
    try:
        fin = datetime.strptime(dia_fin, '%Y-%m-%d')
    except ValueError:
        return True
    dia_min = (fin - timedelta(days=db.REGLA8_DIAS_RACHA - 1)).strftime('%Y-%m-%d')
    prefijo = 'regla8_racha_7dias_'
    repo = ScoreRepo()
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            motivos = repo.listar_motivos_score_con_prefijo(cursor, codigo_aliado, prefijo)
        except Exception:
            return True
        finally:
            try:
                conn.close()
            except Exception:
                pass
    for motivo in motivos:
        motivo = str(motivo or '')
        if not motivo.startswith(prefijo):
            continue
        dia_motivo = motivo[len(prefijo):]
        if len(dia_motivo) == 10 and dia_min <= dia_motivo <= dia_fin:
            return True
    return False

def aplicar_penalizacion_sin_acceso_semanal(db,
    codigo_aliado: str,
    dia_ref: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Penalización 6: sin entrar a la app (login) durante 7 días de calendario → -1.
    Repetible: un -1 por cada bloque completo de 7 días sin acceso desde el último login
    (o desde creado_en si nunca entró). Motivo: sin_acceso_7d_{YYYY-MM-DD}.
    """
    codigo_aliado = (codigo_aliado or '').strip()
    if not codigo_aliado:
        return []
    aliado = db.obtener_aliado_por_codigo(codigo_aliado)
    if not aliado:
        return []
    estado = (aliado.get('estado') or '').strip()
    if estado != 'activo':
        return []
    if not db._es_invitador_elegible_score(codigo_aliado):
        return []
    dia_hoy = (dia_ref or '').strip() or db._dia_hoy_servidor()
    try:
        hoy_dt = datetime.strptime(dia_hoy[:10], '%Y-%m-%d')
    except ValueError:
        return []
    baseline = db._baseline_acceso_dia(codigo_aliado)
    if not baseline:
        return []
    try:
        base_dt = datetime.strptime(baseline[:10], '%Y-%m-%d')
    except ValueError:
        return []
    dias_ausente = (hoy_dt - base_dt).days
    if dias_ausente < db.PENAL6_DIAS_SIN_ACCESO:
        return []
    semanas = dias_ausente // db.PENAL6_DIAS_SIN_ACCESO
    aplicados: List[Dict[str, Any]] = []
    for k in range(1, semanas + 1):
        dia_fin = (base_dt + timedelta(days=k * db.PENAL6_DIAS_SIN_ACCESO)).strftime('%Y-%m-%d')
        motivo = f'sin_acceso_7d_{dia_fin}'
        if db._ya_aplicado_motivo_score(codigo_aliado, motivo):
            continue
        result = db.aplicar_cambio_score(codigo_aliado, db.PENAL6_DELTA, motivo)
        if result.get('status') == 'success' and int(result.get('aplicado') or 0) != 0:
            aplicados.append({'motivo': motivo, 'result': result})
    return aplicados

def evaluar_regla8_racha_7dias(db,
    codigo_aliado: str,
    dia_fin: Optional[str] = None,
) -> Optional[Tuple[str, int, str]]:
    """
    Regla 8: login todos los días durante 7 días consecutivos (calendario servidor)
    → +3. Repetible: una vez por ventana de 7 días (motivo regla8_racha_7dias_{dia_fin}).
    """
    codigo_aliado = (codigo_aliado or '').strip()
    if not codigo_aliado:
        return None
    if not db._es_invitador_elegible_score(codigo_aliado):
        return None
    dia_fin_val = (dia_fin or '').strip() or db._dia_hoy_servidor()
    try:
        fin = datetime.strptime(dia_fin_val, '%Y-%m-%d')
    except ValueError:
        return None
    dias_requeridos = [
        (fin - timedelta(days=i)).strftime('%Y-%m-%d')
        for i in range(db.REGLA8_DIAS_RACHA)
    ]
    repo = ScoreRepo()
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            presentes = set(repo.listar_dias_acceso(cursor, codigo_aliado, dias=dias_requeridos))
        except Exception:
            return None
        finally:
            try:
                conn.close()
            except Exception:
                pass
    if set(dias_requeridos) != presentes:
        return None
    motivo = db._motivo_regla8(dia_fin_val)
    if db._ya_aplicado_motivo_score(codigo_aliado, motivo):
        return None
    if db._tiene_premio_regla8_reciente(codigo_aliado, dia_fin_val):
        return None
    return (codigo_aliado, db.REGLA8_DELTA, motivo)

def evaluar_regla6_urgente_mismo_dia(db,
    contacto_id: int,
    fecha_pago: Optional[Any] = None,
) -> Optional[Tuple[str, int, str]]:
    """
    Regla 6: contacto urgente pagado el mismo día → +3 al profesional.
    """
    try:
        contacto_id = int(contacto_id)
    except (TypeError, ValueError):
        return None
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, profesional_codigo, COALESCE(es_urgente, 0) AS es_urgente,
                       urgente_marcado_en, creado_en, fecha_validacion_pago, estado_pago
                FROM contactos_ruana WHERE id = ?
            """, (contacto_id,))
            row = cursor.fetchone()
            if not row:
                return None
            d = dict(row)
        except Exception:
            return None
        finally:
            try:
                conn.close()
            except Exception:
                pass
    if not bool(int(d.get('es_urgente') or 0)):
        return None
    prof = str(d.get('profesional_codigo') or '').strip()
    if not prof:
        return None
    inicio = d.get('urgente_marcado_en') or d.get('creado_en')
    pago = fecha_pago if fecha_pago is not None else d.get('fecha_validacion_pago')
    if pago is None:
        pago = datetime.now()
    dia_inicio = db._fecha_dia_servidor(inicio)
    dia_pago = db._fecha_dia_servidor(pago)
    if not dia_inicio or not dia_pago or dia_inicio != dia_pago:
        return None
    motivo = f'regla6_urgente_mismo_dia_{contacto_id}'
    if db._ya_aplicado_motivo_score(prof, motivo):
        return None
    return (prof, db.REGLA6_DELTA, motivo)

def _motivo_regla4_mes(db, anio_mes: str) -> str:
    return f'regla4_4_encargos_mes_limpio_{anio_mes}'

def _ya_aplicada_regla4_mes(db, codigo_aliado: str, anio_mes: str) -> bool:
    codigo_aliado = (codigo_aliado or '').strip()
    anio_mes = (anio_mes or '').strip()
    if not codigo_aliado or not anio_mes:
        return True
    motivo = db._motivo_regla4_mes(anio_mes)
    repo = ScoreRepo()
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            return repo.existe_movimiento_motivo(cursor, codigo_aliado, motivo)
        except Exception:
            return True
        finally:
            try:
                conn.close()
            except Exception:
                pass

def contacto_tiene_incidencia_pago(db, contacto_id: int) -> bool:
    """
    True si el contacto tuvo disputa/reclamación o rechazo de comprobante Apoyo,
    aunque luego se resolviera y quedara pagado.
    """
    try:
        contacto_id = int(contacto_id)
    except (TypeError, ValueError):
        return False
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, fecha_disputa FROM contactos_ruana WHERE id = ?",
                (contacto_id,),
            )
            row = cursor.fetchone()
            if not row:
                return False
            if row['fecha_disputa'] is not None:
                return True
            try:
                cursor.execute(
                    "SELECT 1 FROM payment_conflicts WHERE trabajo_id = ? LIMIT 1",
                    (contacto_id,),
                )
                if cursor.fetchone() is not None:
                    return True
            except Exception:
                pass
            cursor.execute(
                """
                SELECT 1 FROM audit_log
                WHERE entidad = 'contacto' AND entidad_id = ?
                  AND accion IN ('pago_apoyo_rechazado', 'conflicto_importe', 'apoyo_impugnado')
                LIMIT 1
                """,
                (contacto_id,),
            )
            return cursor.fetchone() is not None
        except Exception:
            return False
        finally:
            try:
                conn.close()
            except Exception:
                pass

def listar_encargos_pagados_mes(db, codigo_aliado: str, anio_mes: str) -> List[Dict[str, Any]]:
    """
    Contactos Pagos Apoyo RUANA del aliado (solicitante o profesional)
    con estado_pago=pagado en el mes YYYY-MM (fecha_validacion_pago).
    """
    codigo_aliado = (codigo_aliado or '').strip()
    anio_mes = (anio_mes or '').strip()
    if not codigo_aliado or not anio_mes:
        return []
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, solicitante_codigo, profesional_codigo, estado_pago,
                       fecha_validacion_pago, fecha_disputa
                FROM contactos_ruana
                WHERE estado = 'trabajo_cerrado'
                  AND estado_pago = 'pagado'
                  AND COALESCE(apoyo_ruana, 0) > 0
                  AND (solicitante_codigo = ? OR profesional_codigo = ?)
                  AND fecha_validacion_pago IS NOT NULL
                ORDER BY id ASC
                """,
                (codigo_aliado, codigo_aliado),
            )
            out = []
            for row in cursor.fetchall():
                item = dict(row)
                if db._anio_mes_de(item.get('fecha_validacion_pago')) == anio_mes:
                    out.append(item)
            return out
        except Exception:
            return []
        finally:
            try:
                conn.close()
            except Exception:
                pass

def evaluar_regla4_encargos_mes_limpio(db,
    codigo_aliado: str,
    anio_mes: Optional[str] = None,
) -> Optional[Tuple[str, int, str]]:
    """
    Regla 4: 4 encargos pagados en el mismo mes sin incidencias de pago → +3 una vez.
    Devuelve (codigo, delta, motivo) si debe aplicarse; None si no.
    """
    codigo_aliado = (codigo_aliado or '').strip()
    if not codigo_aliado:
        return None
    anio_mes = (anio_mes or datetime.now().strftime('%Y-%m')).strip()
    if db._ya_aplicada_regla4_mes(codigo_aliado, anio_mes):
        return None
    pagados = db.listar_encargos_pagados_mes(codigo_aliado, anio_mes)
    if len(pagados) < db.REGLA4_ENCARGOS_MES_UMBRAL:
        return None
    for item in pagados:
        if db.contacto_tiene_incidencia_pago(item['id']):
            return None
    return (
        codigo_aliado,
        db.REGLA4_ENCARGOS_MES_DELTA,
        db._motivo_regla4_mes(anio_mes),
    )

