"""Servicio de dominio competencia (Campamento Base).

Extracción progresiva desde DBManager. Las fachadas permanecen en DBManager.
SQL de competencia vía CompetenciaRepo.
"""
from __future__ import annotations

from core.db_constants import RUANA_ROOT, MAX_GRUPOS_POR_CP

import json
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from core.repositories.competencia_repo import CompetenciaRepo

_repo = CompetenciaRepo()

# --- Extraído de DBManager (competencia) ---

def _get_umbral_competencia(db) -> Optional[int]:
    """Lee umbral_competencia desde config/ruana_reglas_v1.json. Por defecto 15."""
    try:
        config_path = RUANA_ROOT / 'config' / 'ruana_reglas_v1.json'
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return int(data.get('umbral_competencia', 15))
    except Exception:
        pass
    return 15

def _get_duracion_competencia_dias(db) -> int:
    """Lee duracion_competencia_dias desde config. Por defecto 30."""
    try:
        config_path = RUANA_ROOT / 'config' / 'ruana_reglas_v1.json'
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return int(data.get('duracion_competencia_dias', 30))
    except Exception:
        pass
    return 30

def _get_score_reinicio_competencia(db) -> int:
    """Score asignado al perdedor de una competencia (grupo en formación). Por defecto 50."""
    try:
        config_path = RUANA_ROOT / 'config' / 'ruana_reglas_v1.json'
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return int(data.get('score_reinicio_competencia', 50))
    except Exception:
        pass
    return 50

def procesar_competencia_automatica(db) -> Dict[str, Any]:
    """
    Orquestador sin intervención admin: finaliza vencidas, resuelve abandonos
    e intenta iniciar competencias pendientes de retador.
    """
    finalizadas = db.finalizar_competencia_activas_vencidas()
    abandonos = db._sanear_competencias_participantes_ausentes()
    pendientes = db._procesar_competencias_pendientes()
    return {
        'finalizadas': len(finalizadas),
        'abandonos_resueltos': len(abandonos),
        'pendientes_iniciadas': len(pendientes),
    }

def _solicitar_competencia_por_score(db, codigo_aliado: str) -> Optional[Dict[str, Any]]:
    """Intenta iniciar competencia; si no hay retador, encola pendiente."""
    if db.aliado_en_competencia_activa(codigo_aliado):
        return None
    if db.tiene_competencia_pendiente(codigo_aliado):
        return None
    result = db._iniciar_competencia_si_procede(codigo_aliado)
    if result:
        db._marcar_competencia_pendiente_resuelta(codigo_aliado, 'iniciada')
        return result
    db._registrar_competencia_pendiente(codigo_aliado)
    return None

def _cancelar_competencia_pendiente(db, codigo_aliado: str, motivo: str = 'score_recuperado') -> None:
    codigo = (codigo_aliado or '').strip()
    if not codigo:
        return
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            rowcount = _repo.cancelar_pendiente(cursor, codigo)
            conn.commit()
            if rowcount:
                try:
                    db.registrar_evento_sistema(
                        'competencia_pendiente_cancelada',
                        f'Pendiente cancelada para {codigo}: {motivo}',
                        actor_tipo='sistema',
                        metadata={'aliado_codigo': codigo, 'motivo': motivo},
                    )
                except Exception:
                    pass
        except Exception:
            pass
        finally:
            conn.close()

def tiene_competencia_pendiente(db, codigo_aliado: str) -> bool:
    codigo = (codigo_aliado or '').strip()
    if not codigo:
        return False
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            return _repo.tiene_pendiente(cursor, codigo)
        except Exception:
            return False
        finally:
            conn.close()

def _procesar_competencias_pendientes(db, codigo_postal: Optional[str] = None, oficio: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Intenta iniciar competencias en cola cuando ya hay retador y el titular sigue bajo umbral."""
    umbral = db._get_umbral_competencia() or 15
    iniciadas: List[Dict[str, Any]] = []
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            pendientes = [dict(r) for r in _repo.listar_pendientes(cursor, codigo_postal, oficio)]
        except Exception:
            return []
        finally:
            conn.close()
    for p in pendientes:
        codigo = p.get('aliado_codigo')
        aliado = db.obtener_aliado_por_codigo(codigo)
        if not aliado or (aliado.get('estado') or '') != 'activo':
            db._cancelar_competencia_pendiente(codigo, 'titular_no_activo')
            continue
        score = int(aliado.get('score') or 0)
        if score >= umbral:
            db._cancelar_competencia_pendiente(codigo, 'score_recuperado')
            continue
        if db.aliado_en_competencia_activa(codigo):
            db._marcar_competencia_pendiente_resuelta(codigo, 'iniciada')
            continue
        retador = db._buscar_retador(
            codigo, p.get('grupo_id'), p.get('oficio', ''), score, p.get('codigo_postal', '')
        )
        if not retador:
            continue
        result = db._iniciar_competencia_si_procede(codigo)
        if result:
            db._marcar_competencia_pendiente_resuelta(codigo, 'iniciada')
            iniciadas.append({'aliado_codigo': codigo, **result})
    return iniciadas

def aliado_en_competencia_activa(db, codigo_aliado: str) -> bool:
    codigo = (codigo_aliado or '').strip()
    if not codigo:
        return False
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            col = db._columna_retador_competencia(cursor)
            return _repo.en_competencia_activa(cursor, col, codigo)
        except Exception:
            return False
        finally:
            conn.close()

def _dias_restantes_competencia(fecha_fin_prevista: Any) -> int:
    if not fecha_fin_prevista:
        return 0
    try:
        fi_str = str(fecha_fin_prevista)[:19].replace('T', ' ')
        fin = datetime.strptime(fi_str, '%Y-%m-%d %H:%M:%S')
    except Exception:
        try:
            fin = datetime.fromisoformat(str(fecha_fin_prevista)[:19])
        except Exception:
            return 0
    delta = fin - datetime.now()
    return max(0, int(delta.total_seconds() // 86400))

def listar_competencias_pendientes_admin(db) -> List[Dict[str, Any]]:
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            return [dict(row) for row in _repo.listar_pendientes_admin(cursor)]
        except Exception:
            return []
        finally:
            conn.close()

def listar_competencias_historial_admin(db, limite: int = 50) -> List[Dict[str, Any]]:
    limite = max(1, min(int(limite or 50), 200))
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            col_ret = db._columna_retador_competencia(cursor)
            return [dict(row) for row in _repo.listar_historial_admin(cursor, col_ret, limite)]
        except Exception:
            return []
        finally:
            conn.close()

def listar_competencias_activas_admin(db) -> List[Dict[str, Any]]:
    """
    Lista competencias activas para el panel admin.
    Incluye datos de titular, suplente, grupo origen, scores y tiempo en competencia.
    Ordenado por fecha_inicio ascendente (más antiguas arriba).
    """
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cols = db._columnas_compat_competencia(cursor)
            rows = _repo.listar_activas_admin(cursor, cols)
            now = datetime.now()
            resultado = []
            for row in rows:
                r = dict(row)
                fecha_inicio = r.get('fecha_inicio')
                tiempo_horas = 0.0
                if fecha_inicio:
                    try:
                        fi_str = str(fecha_inicio)[:19].replace('T', ' ')
                        fi = datetime.strptime(fi_str, '%Y-%m-%d %H:%M:%S')
                        delta = now - fi
                        tiempo_horas = delta.total_seconds() / 3600.0
                    except Exception:
                        try:
                            fi = datetime.fromisoformat(str(fecha_inicio)[:19])
                            delta = now - fi
                            tiempo_horas = delta.total_seconds() / 3600.0
                        except Exception:
                            pass
                score_tit_actual = r.get('titular_score_actual')
                if score_tit_actual is not None:
                    score_tit_actual = int(score_tit_actual)
                else:
                    score_tit_actual = r.get('score_titular_actual')
                    if score_tit_actual is not None:
                        score_tit_actual = int(score_tit_actual)
                    else:
                        score_tit_actual = r.get('score_titular_inicio', 0)
                score_ret_actual = r.get('retador_score_actual')
                if score_ret_actual is not None:
                    score_ret_actual = int(score_ret_actual)
                else:
                    score_ret_actual = r.get('score_retador_actual')
                    if score_ret_actual is not None:
                        score_ret_actual = int(score_ret_actual)
                    else:
                        score_ret_actual = r.get('score_retador_inicio', 0)
                score_tit_inicio = int(r.get('score_titular_inicio') or 0)
                score_ret_inicio = int(r.get('score_retador_inicio') or 0)
                resultado.append({
                    'id': r.get('id'),
                    'grupo': r.get('grupo_nombre') or f"Grupo {r.get('grupo_id')}",
                    'oficio': r.get('oficio') or '',
                    'titular': {
                        'id': r.get('titular_id'),
                        'codigo': r.get('aliado_original_codigo'),
                        'nombre': r.get('titular_nombre') or '',
                        'score_actual': score_tit_actual,
                        'score_inicio': score_tit_inicio,
                    },
                    'retador': {
                        'id': r.get('retador_id'),
                        'codigo': r.get('retador_codigo'),
                        'nombre': r.get('retador_nombre') or '',
                        'grupo_origen': r.get('grupo_origen_nombre') or f"Grupo {r.get('retador_grupo_anterior_id')}" if r.get('retador_grupo_anterior_id') else '—',
                        'score_actual': score_ret_actual,
                        'score_inicio': score_ret_inicio,
                    },
                    # alias para compatibilidad con frontend existente
                    'suplente': {
                        'id': r.get('retador_id'),
                        'codigo': r.get('retador_codigo'),
                        'nombre': r.get('retador_nombre') or '',
                        'grupo_origen': r.get('grupo_origen_nombre') or f"Grupo {r.get('retador_grupo_anterior_id')}" if r.get('retador_grupo_anterior_id') else '—',
                        'score_actual': score_ret_actual,
                        'score_inicio': score_ret_inicio,
                    },
                    'fecha_inicio': fecha_inicio,
                    'fecha_fin_prevista': r.get('fecha_fin_prevista'),
                    'dias_restantes': db._dias_restantes_competencia(r.get('fecha_fin_prevista')),
                    'tiempo_en_competencia_horas': round(tiempo_horas, 1),
                    'estado': 'activa',
                    'motivo': r.get('motivo') or 'score bajo',
                })
            return resultado
        except Exception as e:
            print(f"[RUANA] Error listando competencias activas: {e}")
            return []
        finally:
            conn.close()

def _iniciar_competencia_si_procede(db, codigo_aliado: str) -> Optional[Dict[str, Any]]:
    """Inicia competencia si el aliado tiene grupo, oficio y existe un suplente. No mostrar scores individuales."""
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            row = _repo.select_aliado_activo_con_grupo(cursor, codigo_aliado)
            if not row or not row[0]:
                return None
            grupo_id, oficio, score_actual, codigo_postal = row[0], row[1], int(row[2] or 0), row[3] or ''
            ciudad, provincia = row[4], row[5]
            if not oficio or not codigo_postal:
                return None
            if db.competencia_activa_para_grupo_oficio(grupo_id, oficio):
                return None
            retador = db._buscar_retador(codigo_aliado, grupo_id, oficio, score_actual, codigo_postal)
            if not retador:
                return None
            retador_codigo = retador['codigo']
            retador_estado = (retador.get('estado') or 'activo').strip()
            retador_grupo_anterior_id = retador.get('grupo_id') if retador_estado != 'en_espera' else None
            score_titular_inicio = int(score_actual)
            score_retador_inicio = int(retador.get('score', 0) or 0)
            duracion_dias = db._get_duracion_competencia_dias()
            from datetime import timedelta
            fecha_fin = (datetime.now() + timedelta(days=duracion_dias)).strftime('%Y-%m-%d %H:%M:%S')
            competencia_id = _repo.insertar_competencia(
                cursor, grupo_id, oficio.strip(), codigo_aliado, retador_codigo,
                retador_grupo_anterior_id, score_titular_inicio, score_retador_inicio, fecha_fin,
            )
            if retador_estado == 'en_espera':
                _repo.activar_retador_en_grupo(cursor, grupo_id, retador_codigo)
            else:
                _repo.mover_retador_a_grupo(cursor, grupo_id, retador_codigo)
            _repo.marcar_grupo_en_competencia(cursor, grupo_id)
            db._avisar_grupos_cp_competencia(codigo_postal, oficio.strip(), cursor)
            db._notificar_retador_competencia_iniciada(
                retador_codigo=retador_codigo,
                titular_codigo=codigo_aliado,
                oficio=oficio.strip(),
                grupo_id=grupo_id,
                competencia_id=competencia_id,
                duracion_dias=duracion_dias,
                codigo_postal=codigo_postal,
                cursor=cursor,
            )
            db._notificar_titular_competencia_iniciada(
                titular_codigo=codigo_aliado,
                retador_codigo=retador_codigo,
                oficio=oficio.strip(),
                competencia_id=competencia_id,
                duracion_dias=duracion_dias,
                fecha_fin_prevista=fecha_fin,
                cursor=cursor,
            )
            conn.commit()
            try:
                db.registrar_evento_sistema(
                    'competencia_iniciada',
                    f'Competencia iniciada: titular {codigo_aliado} vs retador {retador_codigo} en grupo {grupo_id}',
                    actor_tipo='sistema',
                    metadata={'grupo_id': grupo_id, 'oficio': oficio.strip(), 'titular_codigo': codigo_aliado, 'retador_codigo': retador_codigo}
                )
            except Exception:
                pass
            # Penalización 4: -2 a padre/abuelo si un hijo/nieto entra en competencia
            try:
                db.aplicar_penalizacion_descendiente_en_competencia(codigo_aliado, competencia_id)
            except Exception:
                pass
            return {
                'grupo_id': grupo_id,
                'retador_codigo': retador_codigo,
                'suplente_codigo': retador_codigo,  # alias compatibilidad
                'oficio': oficio,
                'competencia_id': competencia_id,
            }
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            return None
        finally:
            conn.close()

def finalizar_competencia_activas_vencidas(db) -> List[Dict[str, Any]]:
    """Finaliza competencias cuya fecha_fin_prevista ha pasado. Mayor score permanece, el otro sale del grupo."""
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            filas = _repo.listar_vencidas(cursor)
        except Exception:
            return []
        finally:
            conn.close()
    resultados = []
    for row in filas:
        cid, grupo_id, oficio, orig, supl, prev_id = row[0], row[1], row[2], row[3], row[4], row[5]
        r = db._finalizar_una_competencia(cid, grupo_id, orig, supl, prev_id)
        resultados.append({'competencia_id': cid, **r})
    return resultados

def _finalizar_una_competencia(db,
    competencia_id: int,
    grupo_id: int,
    aliado_original_codigo: str,
    retador_codigo: str,
    retador_grupo_anterior_id: Optional[int],
    ganador_forzado: Optional[str] = None,
    motivo_cierre: str = 'plazo_vencido',
) -> Dict[str, Any]:
    """
    Compara scores al cierre; el mayor permanece en el grupo principal.
    El perdedor pasa a grupo en formación con score reiniciado (50).
    Segunda derrota acumulada → expulsado.
    """
    score_reinicio = db._get_score_reinicio_competencia()
    perdedor_expulsado = False
    ganador = ganador_forzado
    score_orig = score_ret = 0
    oficio = ''
    try:
        conn = db._connect()
        cursor = conn.cursor()
        s1 = _repo.select_score_oficio(cursor, aliado_original_codigo)
        s2 = _repo.select_score(cursor, retador_codigo)
        score_orig = int(s1[0]) if s1 and s1[0] is not None else 0
        score_ret = int(s2[0]) if s2 and s2[0] is not None else 0
        oficio = (s1[1] or '').strip() if s1 and len(s1) > 1 else ''
        if not ganador:
            ganador = aliado_original_codigo if score_orig >= score_ret else retador_codigo
        perdedor = retador_codigo if ganador == aliado_original_codigo else aliado_original_codigo

        g = _repo.select_grupo_ubicacion(cursor, grupo_id)
        codigo_postal = (g[0] or '') if g else ''
        ciudad = (g[1] or '') if g and len(g) > 1 else ''
        provincia = (g[2] or '') if g and len(g) > 2 else ''

        _repo.set_grupo_aliado(cursor, grupo_id, ganador)
        derrotas_prev = _repo.select_derrotas(cursor, perdedor)

        grupo_formacion = None
        if codigo_postal and oficio:
            grupo_formacion = db.buscar_grupo_formacion_en_cp(codigo_postal, oficio)
            if not grupo_formacion and db.contar_grupos_activos_por_cp(codigo_postal) < MAX_GRUPOS_POR_CP:
                grupo_formacion = db.crear_grupo_en_cp(codigo_postal, ciudad, provincia)

        if grupo_formacion and isinstance(grupo_formacion, dict) and grupo_formacion.get('id'):
            gid_perdedor = grupo_formacion['id']
            if gid_perdedor == grupo_id:
                grupo_alt = db.buscar_grupo_formacion_en_cp(codigo_postal, oficio)
                gid_perdedor = grupo_alt['id'] if grupo_alt and grupo_alt.get('id') != grupo_id else None
            if gid_perdedor and gid_perdedor != grupo_id:
                _repo.mover_perdedor_con_reinicio(cursor, gid_perdedor, score_reinicio, perdedor)
            else:
                _repo.sacar_perdedor_con_reinicio(cursor, score_reinicio, perdedor)
        else:
            _repo.sacar_perdedor_con_reinicio(cursor, score_reinicio, perdedor)

        _repo.expulsar_si_dos_derrotas(cursor, perdedor)
        perdedor_expulsado = derrotas_prev + 1 >= 2

        db._notificar_derrota_competencia(
            aliado_codigo=perdedor,
            oficio=oficio,
            competencia_id=competencia_id,
            score_reinicio=score_reinicio,
            expulsado=perdedor_expulsado,
            cursor=cursor,
        )
        db._notificar_ganador_competencia(ganador, oficio, competencia_id, cursor=cursor)

        _repo.finalizar_competencia(cursor, ganador, score_orig, score_ret, competencia_id)
        _repo.marcar_grupo_activo(cursor, grupo_id)
        conn.commit()

        if retador_grupo_anterior_id and perdedor == retador_codigo:
            db.procesar_viabilidad_grupo(retador_grupo_anterior_id)
        db.procesar_viabilidad_grupo(grupo_id)

        try:
            db.registrar_evento_sistema(
                'competencia_finalizada',
                f'Competencia {competencia_id} cerrada ({motivo_cierre}): ganador {ganador}',
                actor_tipo='sistema',
                metadata={
                    'competencia_id': competencia_id,
                    'ganador': ganador,
                    'perdedor': perdedor,
                    'motivo_cierre': motivo_cierre,
                    'score_titular': score_orig,
                    'score_retador': score_ret,
                },
            )
        except Exception:
            pass

        return {
            'status': 'ok',
            'ganador_codigo': ganador,
            'perdedor_codigo': perdedor,
            'perdedor_expulsado': perdedor_expulsado,
            'score_reinicio': score_reinicio,
            'motivo_cierre': motivo_cierre,
        }
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {'status': 'error', 'message': str(e)}
    finally:
        try:
            conn.close()
        except Exception:
            pass

def forzar_competencia(db,
    grupo_id: int,
    oficio: str,
    aliado_original_codigo: str,
    retador_codigo: str,
    admin_codigo: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Crea manualmente una competencia: retador compite por la plaza del titular en el grupo.
    """
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            oficio_s = (oficio or '').strip()
            if not oficio_s:
                return {'status': 'error', 'message': 'Oficio obligatorio'}
            if db.competencia_activa_para_grupo_oficio(grupo_id, oficio_s):
                return {'status': 'error', 'message': 'Ya existe una competencia activa para este grupo y oficio'}
            if not _repo.existe_grupo_activo(cursor, grupo_id):
                return {'status': 'error', 'message': 'Grupo no encontrado o no activo'}
            for cod, label in [(aliado_original_codigo, 'titular'), (retador_codigo, 'retador')]:
                if not _repo.existe_aliado(cursor, cod):
                    return {'status': 'error', 'message': f'Aliado {label} no encontrado'}
            duracion = db._get_duracion_competencia_dias()
            from datetime import timedelta
            fecha_fin = (datetime.now() + timedelta(days=duracion)).strftime('%Y-%m-%d %H:%M:%S')
            last_id = _repo.insertar_competencia_forzada(
                cursor, grupo_id, oficio_s, aliado_original_codigo, retador_codigo, fecha_fin
            )
            conn.commit()
            try:
                db.registrar_evento_sistema(
                    'forzar_competencia',
                    f'Competencia forzada: grupo {grupo_id}, oficio {oficio_s}',
                    actor_tipo='admin',
                    metadata={'grupo_id': grupo_id, 'oficio': oficio_s, 'original': aliado_original_codigo, 'retador': retador_codigo},
                )
            except Exception:
                pass
            return {'status': 'success', 'message': 'Competencia forzada correctamente', 'competencia_id': last_id}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
        finally:
            try:
                conn.close()
            except Exception:
                pass
# --- Extraído de DBManager (competencia) ---

def _get_purga_meses_sin_ganar(db) -> int:
    """Lee purga_mensual_meses_sin_ganar desde config. Por defecto 3."""
    try:
        config_path = RUANA_ROOT / 'config' / 'ruana_reglas_v1.json'
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return int(data.get('purga_mensual_meses_sin_ganar', 3))
    except Exception:
        pass
    return 3

def _get_purga_score_bajo_umbral(db) -> int:
    """Lee purga_score_bajo_umbral desde config. Por defecto 40."""
    try:
        config_path = RUANA_ROOT / 'config' / 'ruana_reglas_v1.json'
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return int(data.get('purga_score_bajo_umbral', 40))
    except Exception:
        pass
    return 40

def obtener_competencia_info_aliado(db, codigo_aliado: str) -> Optional[Dict[str, Any]]:
    """Info de competencia activa para el panel aliado (rol, fechas, días restantes)."""
    codigo = (codigo_aliado or '').strip()
    if not codigo:
        return None
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            col_ret = db._columna_retador_competencia(cursor)
            row = _repo.select_info_aliado(cursor, col_ret, codigo)
            if not row:
                if db.tiene_competencia_pendiente(codigo):
                    return {
                        'en_competencia': False,
                        'competencia_pendiente': True,
                        'rol': 'titular_pendiente',
                        'mensaje': 'Esperando retador para iniciar la competencia.',
                    }
                return None
            r = dict(row)
            rol = 'titular' if r.get('aliado_original_codigo') == codigo else 'retador'
            dias = db._dias_restantes_competencia(r.get('fecha_fin_prevista'))
            return {
                'en_competencia': True,
                'competencia_pendiente': False,
                'competencia_id': r.get('id'),
                'rol': rol,
                'oficio': r.get('oficio') or '',
                'grupo_id': r.get('grupo_id'),
                'grupo_nombre': r.get('grupo_nombre') or '',
                'fecha_inicio': r.get('fecha_inicio'),
                'fecha_fin_prevista': r.get('fecha_fin_prevista'),
                'dias_restantes': dias,
                'contrincante_codigo': r.get('retador_codigo') if rol == 'titular' else r.get('aliado_original_codigo'),
            }
        except Exception:
            return None
        finally:
            conn.close()

def competencia_activa_para_grupo_oficio(db, grupo_id: int, oficio: str) -> Optional[Dict[str, Any]]:
    """Devuelve la competencia activa para ese grupo y oficio, o None."""
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cols = db._columnas_compat_competencia(cursor)
            row = _repo.select_activa_grupo_oficio(cursor, cols, grupo_id, oficio)
            return dict(row) if row else None
        except Exception:
            return None
        finally:
            conn.close()

def _buscar_retador(db, codigo_aliado_en_riesgo: str, grupo_id: int, oficio: str,
                    score_actual: int, codigo_postal: str,
                    ciudad: Optional[str] = None, provincia: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Retador: mismo CP y mismo oficio. Prioridad:
    1) Aliado en lista de suplentes (estado en_espera)
    2) Aliado activo en un grupo del CP con menos profesionales
    Excluye al titular y a quien ya esté en el grupo en competencia.
    """
    del score_actual, ciudad, provincia  # compatibilidad de firma; reglas actuales no los usan
    if not oficio or not codigo_postal:
        return None
    oficio = oficio.strip()
    codigo_postal = codigo_postal.strip()
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            # 1) Suplentes en espera (mismo CP, mismo oficio)
            row = _repo.buscar_retador_en_espera(cursor, oficio, codigo_postal, codigo_aliado_en_riesgo)
            if row:
                return dict(row)
            # 2) Activos en el CP, mismo oficio, grupo con menos profesionales
            row = _repo.buscar_retador_activo(
                cursor, oficio, codigo_postal, codigo_aliado_en_riesgo, grupo_id
            )
            return dict(row) if row else None
        except Exception:
            return None
        finally:
            conn.close()

def _gano_competencia_ultimos_meses(db, codigo_aliado: str, meses: int) -> bool:
    """True si el aliado ganó al menos una competencia en los últimos N meses (por fecha_fin_prevista)."""
    if not codigo_aliado or meses < 1:
        return False
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            return _repo.gano_ultimos_meses(cursor, codigo_aliado, meses)
        except Exception:
            return False
        finally:
            conn.close()

def purga_mensual(db) -> Dict[str, Any]:
    """
    Purga mensual de calidad: 1) Finaliza competencias vencidas. 2) Aliados en pool que no ganan en N meses
    o mantienen score persistentemente bajo → expulsión temporal (estado = suspendido_temporal).
    No permite acumulación indefinida en el pool.
    """
    resultados_finalizar = db.finalizar_competencia_activas_vencidas()
    meses_sin_ganar = db._get_purga_meses_sin_ganar()
    umbral_score_bajo = db._get_purga_score_bajo_umbral()
    pool = db.listar_aliados_en_pool()
    expulsados_temporal = []
    for aliado in pool:
        codigo = aliado.get('codigo')
        if not codigo:
            continue
        score = int(aliado.get('score') or 0)
        gano_reciente = db._gano_competencia_ultimos_meses(codigo, meses_sin_ganar)
        score_bajo_persistente = score < umbral_score_bajo
        if not gano_reciente or score_bajo_persistente:
            expulsados_temporal.append({
                'codigo': codigo,
                'motivo': 'sin_ganar_3_meses' if not gano_reciente else 'score_bajo_persistente',
                'score': score,
            })
    if expulsados_temporal:
        with db._lock:
            try:
                conn = db._connect()
                cursor = conn.cursor()
                for item in expulsados_temporal:
                    _repo.suspender_temporal(cursor, item['codigo'])
                conn.commit()
            except Exception as e:
                try:
                    conn.rollback()
                except Exception:
                    pass
                return {
                    'status': 'error',
                    'message': str(e),
                    'competencias_finalizadas': len(resultados_finalizar),
                    'detalle_competencias': resultados_finalizar,
                    'pool_revisado': len(pool),
                    'expulsados_temporal': 0,
                    'detalle_expulsados': [],
                }
            finally:
                conn.close()
    return {
        'status': 'ok',
        'competencias_finalizadas': len(resultados_finalizar),
        'detalle_competencias': resultados_finalizar,
        'pool_revisado': len(pool),
        'expulsados_temporal': len(expulsados_temporal),
        'detalle_expulsados': expulsados_temporal,
    }

def _purga_datos_aliado_completa(db, cursor, codigo: str, aliado_id: int) -> None:
    """
    Elimina todos los registros relacionados con un aliado antes del borrado físico.
    Libera restricciones UNIQUE y referencias en tablas hijas.
    """
    codigo = (codigo or '').strip()
    if not codigo:
        return
    col_retador = db._columna_retador_competencia(cursor)
    _repo.purga_datos_aliado(cursor, codigo, aliado_id, col_retador, db.backend)


def _columna_retador_competencia(db, cursor) -> str:
    """
    Devuelve la columna vigente para el retador en `competencia`.
    Compatibilidad lectura: algunas BDs reales siguen con esquema legacy `suplente_codigo`.
    """
    try:
        if db.backend == "postgres":
            cursor.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'competencia'
                  AND column_name IN ('retador_codigo', 'suplente_codigo')
                """
            )
            cols = {str(r[0]) for r in (cursor.fetchall() or [])}
        else:
            cursor.execute("PRAGMA table_info(competencia)")
            cols = {str(r[1]) for r in (cursor.fetchall() or [])}
    except Exception:
        cols = set()
    return "retador_codigo" if "retador_codigo" in cols else "suplente_codigo"


def _columnas_compat_competencia(db, cursor) -> Dict[str, str]:
    """Mapea columnas de competencia entre esquema nuevo (retador_*) y legacy (suplente_*)."""
    try:
        if db.backend == "postgres":
            cursor.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'competencia'
                """
            )
            cols = {str(r[0]) for r in (cursor.fetchall() or [])}
        else:
            cursor.execute("PRAGMA table_info(competencia)")
            cols = {str(r[1]) for r in (cursor.fetchall() or [])}
    except Exception:
        cols = set()
    return {
        "retador_codigo": "retador_codigo" if "retador_codigo" in cols else "suplente_codigo",
        "retador_grupo_anterior_id": "retador_grupo_anterior_id" if "retador_grupo_anterior_id" in cols else "suplente_grupo_anterior_id",
        "score_retador_inicio": "score_retador_inicio" if "score_retador_inicio" in cols else "score_suplente_inicio",
        "score_retador_actual": "score_retador_actual" if "score_retador_actual" in cols else "score_suplente_actual",
    }


def _notificar_retador_competencia_iniciada(
    db,
    retador_codigo: str,
    titular_codigo: str,
    oficio: str,
    grupo_id: int,
    competencia_id: int,
    duracion_dias: int,
    codigo_postal: str,
    cursor=None,
) -> None:
    """Informa al retador/suplente que entra en competencia y la regla de los 30 días."""
    oficio_txt = (oficio or '').strip()
    mensaje = (
        f"Has sido activado como retador en el CP {codigo_postal} por el oficio {oficio_txt}. "
        f"Durante {duracion_dias} días tú y el titular acumularéis score; al finalizar, "
        f"quien tenga mayor score permanece en el grupo."
    )
    db._crear_notificacion_aliado(
        retador_codigo,
        'competencia_inicio',
        'Competencia iniciada',
        mensaje,
        metadata={
            'competencia_id': competencia_id,
            'grupo_id': grupo_id,
            'oficio': oficio_txt,
            'titular_codigo': titular_codigo,
            'duracion_dias': duracion_dias,
            'codigo_postal': codigo_postal,
        },
        cursor=cursor,
    )


def _avisar_grupos_cp_competencia(
    db,
    codigo_postal: str,
    oficio: str,
    cursor,
) -> None:
    """Informa a todos los grupos activos del CP que hay un oficio en competencia."""
    cp = (codigo_postal or '').strip()
    oficio_txt = (oficio or '').strip()
    if not cp or not oficio_txt or cursor is None:
        return
    texto = f"El profesional de {oficio_txt} está en competencia en este código postal."
    try:
        cursor.execute(
            "SELECT id FROM grupos WHERE codigo_postal = ? AND estado IN ('activo', 'en_competencia')",
            (cp,),
        )
        for row in cursor.fetchall():
            gid = row[0]
            cursor.execute(
                "INSERT INTO avisos_grupo (grupo_id, tipo, texto) VALUES (?, 'competencia', ?)",
                (gid, texto),
            )
    except Exception:
        return


def _notificar_derrota_competencia(
    db,
    aliado_codigo: str,
    oficio: str,
    competencia_id: int,
    score_reinicio: int,
    expulsado: bool,
    cursor=None,
) -> None:
    """Informa al perdedor el resultado de la competencia (primera o segunda derrota)."""
    oficio_txt = (oficio or '').strip()
    if expulsado:
        titulo = 'Has perdido tu lugar en RUANA'
        mensaje = (
            'Has perdido tu lugar en RUANA tras una segunda derrota en competencia. '
            'Para volver debes registrarte de nuevo como usuario nuevo con un código de invitación nuevo.'
        )
        tipo = 'competencia_expulsion'
    else:
        titulo = 'Has perdido la competencia'
        mensaje = (
            f'Has perdido la competencia por el oficio {oficio_txt}. '
            f'Tu score se reinicia a {score_reinicio} puntos y pasas a un grupo en formación '
            f'con menos profesionales.'
        )
        tipo = 'competencia_derrota'
    db._crear_notificacion_aliado(
        aliado_codigo,
        tipo,
        titulo,
        mensaje,
        metadata={
            'competencia_id': competencia_id,
            'oficio': oficio_txt,
            'score_reinicio': score_reinicio,
            'expulsado': expulsado,
        },
        cursor=cursor,
    )


def _notificar_titular_competencia_iniciada(
    db,
    titular_codigo: str,
    retador_codigo: str,
    oficio: str,
    competencia_id: int,
    duracion_dias: int,
    fecha_fin_prevista: str,
    cursor=None,
) -> None:
    """Informa al titular que ha entrado en competencia por permanencia."""
    oficio_txt = (oficio or '').strip()
    mensaje = (
        f'Has entrado en competencia por el oficio {oficio_txt}. '
        f'Durante {duracion_dias} días competirás con otro profesional; al finalizar, '
        f'quien tenga mayor score permanece en la plaza del grupo principal.'
    )
    db._crear_notificacion_aliado(
        titular_codigo,
        'competencia_titular',
        'Estás en competencia',
        mensaje,
        metadata={
            'competencia_id': competencia_id,
            'oficio': oficio_txt,
            'retador_codigo': retador_codigo,
            'duracion_dias': duracion_dias,
            'fecha_fin_prevista': fecha_fin_prevista,
        },
        cursor=cursor,
    )


def _notificar_ganador_competencia(
    db,
    ganador_codigo: str,
    oficio: str,
    competencia_id: int,
    cursor=None,
) -> None:
    mensaje = (
        f'Has ganado la competencia por el oficio {(oficio or "").strip()}. '
        f'Permaneces en la plaza del grupo principal.'
    )
    db._crear_notificacion_aliado(
        ganador_codigo,
        'competencia_victoria',
        'Competencia ganada',
        mensaje,
        metadata={'competencia_id': competencia_id, 'oficio': (oficio or '').strip()},
        cursor=cursor,
    )


def _registrar_competencia_pendiente(db, codigo_aliado: str) -> None:
    codigo = (codigo_aliado or '').strip()
    if not codigo or db.tiene_competencia_pendiente(codigo):
        return
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT a.grupo_id, a.oficio, a.score, g.codigo_postal
                FROM aliados a
                LEFT JOIN grupos g ON g.id = a.grupo_id
                WHERE a.codigo = ? AND a.estado = 'activo'
            """, (codigo,))
            row = cursor.fetchone()
            if not row or not row[0] or not row[1] or not row[3]:
                return
            umbral = db._get_umbral_competencia() or 15
            if int(row[2] or 0) >= umbral:
                return
            cursor.execute("""
                INSERT INTO competencia_pendiente
                (aliado_codigo, grupo_id, oficio, codigo_postal, score_al_crear, estado)
                VALUES (?, ?, ?, ?, ?, 'pendiente')
            """, (codigo, row[0], (row[1] or '').strip(), row[3], int(row[2] or 0)))
            conn.commit()
            try:
                db.registrar_evento_sistema(
                    'competencia_pendiente',
                    f'Competencia pendiente de retador para {codigo}',
                    actor_tipo='sistema',
                    metadata={'aliado_codigo': codigo, 'oficio': row[1], 'codigo_postal': row[3]},
                )
            except Exception:
                pass
        except Exception:
            pass
        finally:
            conn.close()


def _marcar_competencia_pendiente_resuelta(db, codigo_aliado: str, estado: str = 'iniciada') -> None:
    codigo = (codigo_aliado or '').strip()
    if not codigo:
        return
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE competencia_pendiente SET estado = ? "
                "WHERE aliado_codigo = ? AND estado = 'pendiente'",
                (estado, codigo),
            )
            conn.commit()
        except Exception:
            pass
        finally:
            conn.close()


def _sanear_competencias_participantes_ausentes(db) -> List[Dict[str, Any]]:
    """Si un participante abandona RUANA durante la competencia, el otro gana por walkover."""
    resueltos: List[Dict[str, Any]] = []
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            col_ret = db._columna_retador_competencia(cursor)
            cols = db._columnas_compat_competencia(cursor)
            col_prev = cols.get('retador_grupo_anterior_id', 'retador_grupo_anterior_id')
            cursor.execute(
                f"SELECT id, grupo_id, oficio, aliado_original_codigo, {col_ret} AS retador_codigo, "
                f"{col_prev} AS retador_grupo_anterior_id FROM competencia WHERE estado = 'activa'"
            )
            activas = [dict(r) for r in cursor.fetchall()]
        except Exception:
            return []
        finally:
            conn.close()
    estados_validos = ('activo',)
    for c in activas:
        tit = db.obtener_aliado_por_codigo(c.get('aliado_original_codigo'))
        ret = db.obtener_aliado_por_codigo(c.get('retador_codigo'))
        tit_ok = tit and (tit.get('estado') or '') in estados_validos
        ret_ok = ret and (ret.get('estado') or '') in estados_validos
        if tit_ok and ret_ok:
            continue
        if not tit_ok and not ret_ok:
            db._cancelar_competencia_sin_participantes(c.get('id'), c.get('grupo_id'))
            resueltos.append({'competencia_id': c.get('id'), 'motivo': 'ambos_ausentes'})
            continue
        ganador = c.get('retador_codigo') if not tit_ok else c.get('aliado_original_codigo')
        r = db._finalizar_una_competencia(
            c.get('id'), c.get('grupo_id'), c.get('aliado_original_codigo'),
            c.get('retador_codigo'), c.get('retador_grupo_anterior_id'),
            ganador_forzado=ganador, motivo_cierre='abandono_participante',
        )
        resueltos.append({'competencia_id': c.get('id'), 'ganador_codigo': ganador, **r})
    return resueltos


def _cancelar_competencia_sin_participantes(db, competencia_id: int, grupo_id: int) -> None:
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE competencia SET estado = 'finalizada', fecha_cierre = CURRENT_TIMESTAMP WHERE id = ?",
                (competencia_id,),
            )
            cursor.execute("UPDATE grupos SET estado = 'activo' WHERE id = ?", (grupo_id,))
            conn.commit()
        except Exception:
            pass
        finally:
            conn.close()


def grupo_tiene_competencia_activa(db, grupo_id: int) -> bool:
    """True si el grupo tiene al menos una competencia activa."""
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM competencia WHERE grupo_id = ? AND estado = 'activa' LIMIT 1", (grupo_id,))
            return cursor.fetchone() is not None
        except Exception:
            return False
        finally:
            conn.close()

