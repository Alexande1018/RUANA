from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from core import db_manager as db_module


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    return db_module.DBManager(str(tmp_path / "ruana_score_penalizaciones.db"))


def _crear_activo(db, codigo, nombre, score=50):
    result = db.crear_aliado(
        codigo=codigo,
        nombre=nombre,
        marca="Marca",
        oficio="Electricidad",
        codigo_postal="28001",
        email=f"{codigo}@example.com",
        telefono=f"+34600{codigo[-5:]}",
        estado="activo",
        score=score,
        especializacion="Averías",
    )
    assert result["status"] == "success"
    return result


def _score(db, codigo):
    return int(db.obtener_aliado_por_codigo(codigo)["score"])


def _motivos(db, codigo):
    conn = db._connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT delta, motivo FROM score_movimientos WHERE codigo_aliado = ? ORDER BY id",
        (codigo,),
    )
    rows = cur.fetchall()
    conn.close()
    return [(int(r[0]), r[1]) for r in rows]


def test_no_concretado_resta_1_a_cada_uno(sqlite_db):
    _crear_activo(sqlite_db, "95001", "SolNC")
    _crear_activo(sqlite_db, "95002", "ProfNC")
    created = sqlite_db.crear_contacto_ruana("95001", "95002", "Servicio", "Motivo")
    cid = created["id"]
    assert sqlite_db.marcar_cerrado_no_concretado(cid, actor_codigo="95001")["status"] == "success"
    assert _score(sqlite_db, "95001") == 49
    assert _score(sqlite_db, "95002") == 49
    assert (-1, "contacto_cerrado_no_concretado") in _motivos(sqlite_db, "95001")
    assert (-1, "contacto_cerrado_no_concretado") in _motivos(sqlite_db, "95002")


def test_penalizacion_contacto_abierto_7d_y_21d(sqlite_db):
    """Confirma Regla/penalización #6: -2 a 7d y -5 a 21d, una vez cada una."""
    _crear_activo(sqlite_db, "96001", "SolAb")
    _crear_activo(sqlite_db, "96002", "ProfAb")
    created = sqlite_db.crear_contacto_ruana("96001", "96002", "Servicio", "Abierto")
    cid = created["id"]

    hace_8d = (datetime.now() - timedelta(days=8)).strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute(
        "UPDATE contactos_ruana SET estado = 'iniciado', creado_en = ?, actualizado_en = ? WHERE id = ?",
        (hace_8d, hace_8d, cid),
    )
    conn.commit()
    conn.close()

    sqlite_db.aplicar_penalizaciones_contactos_abiertos("96001")
    assert (-2, "contacto_sin_cerrar_7d") in _motivos(sqlite_db, "96001")
    assert _score(sqlite_db, "96001") == 48
    # Idempotente: no vuelve a aplicar 7d
    sqlite_db.aplicar_penalizaciones_contactos_abiertos("96001")
    assert sum(1 for _, m in _motivos(sqlite_db, "96001") if m == "contacto_sin_cerrar_7d") == 1

    hace_22d = (datetime.now() - timedelta(days=22)).strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute(
        "UPDATE contactos_ruana SET creado_en = ?, actualizado_en = ? WHERE id = ?",
        (hace_22d, hace_22d, cid),
    )
    conn.commit()
    conn.close()

    sqlite_db.aplicar_penalizaciones_contactos_abiertos("96001")
    assert (-5, "contacto_sin_cerrar_21d") in _motivos(sqlite_db, "96001")
    assert _score(sqlite_db, "96001") == 43  # 50 -2 -5
    sqlite_db.aplicar_penalizaciones_contactos_abiertos("96001")
    assert sum(1 for _, m in _motivos(sqlite_db, "96001") if m == "contacto_sin_cerrar_21d") == 1


def test_disputa_ya_no_resta_score_en_registrar_importe(sqlite_db):
    """Solo el solicitante declara; el cierre no aplica -1 de disputa (eliminado)."""
    _crear_activo(sqlite_db, "97001", "SolDisp")
    _crear_activo(sqlite_db, "97002", "ProfDisp")
    created = sqlite_db.crear_contacto_ruana("97001", "97002", "Servicio", "Disp")
    cid = created["id"]
    # Flujo actual: solo solicitante puede declarar → cierra sin disputa
    r = sqlite_db.registrar_importe_contacto(cid, "solicitante", 100.0, usuario="97001")
    assert r["status"] == "success"
    assert not any(m == "declaracion_discrepante" for _, m in _motivos(sqlite_db, "97001"))
    assert not any(m == "declaracion_discrepante" for _, m in _motivos(sqlite_db, "97002"))


def test_penalizacion4_descendiente_en_competencia_resta_2_a_padre_y_abuelo(sqlite_db):
    """Penalización 4: hijo/nieto entra en competencia → -2 a padre (gen1) y abuelo (gen2)."""
    _crear_activo(sqlite_db, "98001", "Abuelo")
    _crear_activo(sqlite_db, "98002", "Padre")
    _crear_activo(sqlite_db, "98003", "Nieto")
    assert sqlite_db.asignar_invitado_por("98002", "98001", "aliado")
    assert sqlite_db.asignar_invitado_por("98003", "98002", "aliado")

    aplicados = sqlite_db.aplicar_penalizacion_descendiente_en_competencia("98003", competencia_id=42)
    assert len(aplicados) == 2
    assert _score(sqlite_db, "98001") == 48
    assert _score(sqlite_db, "98002") == 48
    assert _score(sqlite_db, "98003") == 50
    assert (-2, "descendiente_entra_competencia_gen1_42") in _motivos(sqlite_db, "98002")
    assert (-2, "descendiente_entra_competencia_gen2_42") in _motivos(sqlite_db, "98001")

    # Idempotente por competencia_id
    de_nuevo = sqlite_db.aplicar_penalizacion_descendiente_en_competencia("98003", competencia_id=42)
    assert de_nuevo == []
    assert sum(1 for _, m in _motivos(sqlite_db, "98002") if m.startswith("descendiente_entra_competencia_")) == 1
    assert sum(1 for _, m in _motivos(sqlite_db, "98001") if m.startswith("descendiente_entra_competencia_")) == 1


def test_penalizacion4_omite_admin_y_sin_linaje(sqlite_db):
    sqlite_db.obtener_o_crear_invitador_admin("RUANA-ADMIN")
    _crear_activo(sqlite_db, "98101", "HijoAdmin")
    assert sqlite_db.asignar_invitado_por("98101", "RUANA-ADMIN", "admin_invitacion")
    assert sqlite_db.aplicar_penalizacion_descendiente_en_competencia("98101", 7) == []

    _crear_activo(sqlite_db, "98102", "SinPadre")
    assert sqlite_db.aplicar_penalizacion_descendiente_en_competencia("98102", 8) == []


def test_penalizacion4_al_iniciar_competencia_real(sqlite_db):
    """Al arrancar competencia del nieto, padre y abuelo reciben -2."""
    _crear_activo(sqlite_db, "98201", "AbueloComp", score=60)
    _crear_activo(sqlite_db, "98202", "PadreComp", score=60)
    _crear_activo(sqlite_db, "98203", "NietoTitular", score=30)
    _crear_activo(sqlite_db, "98204", "Suplente", score=80)
    assert sqlite_db.asignar_invitado_por("98202", "98201", "aliado")
    assert sqlite_db.asignar_invitado_por("98203", "98202", "aliado")

    g1 = sqlite_db.crear_grupo_en_cp("28099", ciudad="Madrid", provincia="Madrid")
    g2 = sqlite_db.crear_grupo_en_cp("28099", ciudad="Madrid", provincia="Madrid")
    assert "id" in g1 and "id" in g2

    conn = sqlite_db._connect()
    cur = conn.cursor()
    # crear_aliado puede dejar pendiente_validacion; competencia exige activo
    cur.execute("UPDATE aliados SET estado = 'activo' WHERE codigo IN ('98203', '98204')")
    cur.execute("UPDATE aliados SET grupo_id = ? WHERE codigo = ?", (g1["id"], "98203"))
    cur.execute("UPDATE aliados SET grupo_id = ? WHERE codigo = ?", (g2["id"], "98204"))
    conn.commit()
    conn.close()

    result = sqlite_db._iniciar_competencia_si_procede("98203")
    assert result is not None
    cid = result["competencia_id"]
    assert _score(sqlite_db, "98201") == 58
    assert _score(sqlite_db, "98202") == 58
    assert (-2, f"descendiente_entra_competencia_gen1_{cid}") in _motivos(sqlite_db, "98202")
    assert (-2, f"descendiente_entra_competencia_gen2_{cid}") in _motivos(sqlite_db, "98201")


def _insertar_mensaje_antiguo(db, contacto_id, emisor, horas_atras=49):
    hace = (datetime.now() - timedelta(hours=horas_atras)).strftime("%Y-%m-%d %H:%M:%S")
    conn = db._connect()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO chat_mensajes (contacto_id, emisor_codigo, texto, creado_en) VALUES (?, ?, ?, ?)",
        (contacto_id, emisor, "msg test", hace),
    )
    conn.commit()
    conn.close()


def test_penalizacion5_chat_48h_resta_2_al_que_no_respondio(sqlite_db):
    """Penalización 5: último mensaje del solicitante hace ≥48h → -2 al profesional."""
    _crear_activo(sqlite_db, "99001", "SolChat")
    _crear_activo(sqlite_db, "99002", "ProfChat")
    created = sqlite_db.crear_contacto_ruana("99001", "99002", "Servicio", "Chat48")
    cid = created["id"]
    _insertar_mensaje_antiguo(sqlite_db, cid, "99001", horas_atras=49)

    sqlite_db.aplicar_penalizacion_chat_sin_respuesta_48h("99002")
    assert _score(sqlite_db, "99002") == 48
    assert (-2, f"chat_sin_respuesta_48h_{cid}") in _motivos(sqlite_db, "99002")
    # El que escribió el último no se penaliza
    sqlite_db.aplicar_penalizacion_chat_sin_respuesta_48h("99001")
    assert _score(sqlite_db, "99001") == 50
    assert not any(m.startswith("chat_sin_respuesta_48h_") for _, m in _motivos(sqlite_db, "99001"))
    # Idempotente
    sqlite_db.aplicar_penalizacion_chat_sin_respuesta_48h("99002")
    assert sum(1 for _, m in _motivos(sqlite_db, "99002") if m.startswith("chat_sin_respuesta_48h_")) == 1


def test_penalizacion5_no_aplica_si_encargo_cerrado(sqlite_db):
    """Cierre adecuado (trabajo_cerrado / no_concretado) → nadie pierde por chat 48h."""
    _crear_activo(sqlite_db, "99101", "SolCerrado")
    _crear_activo(sqlite_db, "99102", "ProfCerrado")
    created = sqlite_db.crear_contacto_ruana("99101", "99102", "Servicio", "Cerrado")
    cid = created["id"]
    _insertar_mensaje_antiguo(sqlite_db, cid, "99101", horas_atras=50)

    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute(
        "UPDATE contactos_ruana SET estado = 'trabajo_cerrado' WHERE id = ?",
        (cid,),
    )
    conn.commit()
    conn.close()

    sqlite_db.aplicar_penalizacion_chat_sin_respuesta_48h("99102")
    assert _score(sqlite_db, "99102") == 50
    assert not any(m.startswith("chat_sin_respuesta_48h_") for _, m in _motivos(sqlite_db, "99102"))

    # no_concretado también exime
    created2 = sqlite_db.crear_contacto_ruana("99101", "99102", "Otro", "NC")
    cid2 = created2["id"]
    _insertar_mensaje_antiguo(sqlite_db, cid2, "99101", horas_atras=50)
    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute(
        "UPDATE contactos_ruana SET estado = 'cerrado_no_concretado' WHERE id = ?",
        (cid2,),
    )
    conn.commit()
    conn.close()
    sqlite_db.aplicar_penalizacion_chat_sin_respuesta_48h("99102")
    assert not any(m.startswith("chat_sin_respuesta_48h_") for _, m in _motivos(sqlite_db, "99102"))


def test_penalizacion5_no_aplica_si_ambos_finalizan_chat(sqlite_db):
    """Si ambas partes dan por terminado el chat, no hay -2 por silencio."""
    _crear_activo(sqlite_db, "99201", "SolFin")
    _crear_activo(sqlite_db, "99202", "ProfFin")
    created = sqlite_db.crear_contacto_ruana("99201", "99202", "Servicio", "FinChat")
    cid = created["id"]
    _insertar_mensaje_antiguo(sqlite_db, cid, "99201", horas_atras=50)
    assert sqlite_db.ocultar_contacto_del_panel(cid, "99201")["status"] == "success"
    assert sqlite_db.ocultar_contacto_del_panel(cid, "99202")["status"] == "success"

    sqlite_db.aplicar_penalizacion_chat_sin_respuesta_48h("99202")
    assert _score(sqlite_db, "99202") == 50
    assert not any(m.startswith("chat_sin_respuesta_48h_") for _, m in _motivos(sqlite_db, "99202"))


def test_penalizacion5_sin_mensajes_no_aplica(sqlite_db):
    _crear_activo(sqlite_db, "99301", "SolVacio")
    _crear_activo(sqlite_db, "99302", "ProfVacio")
    created = sqlite_db.crear_contacto_ruana("99301", "99302", "Servicio", "Vacio")
    cid = created["id"]
    # Contacto viejo pero sin mensajes
    hace = (datetime.now() - timedelta(hours=72)).strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute(
        "UPDATE contactos_ruana SET creado_en = ?, actualizado_en = ? WHERE id = ?",
        (hace, hace, cid),
    )
    conn.commit()
    conn.close()
    sqlite_db.aplicar_penalizacion_chat_sin_respuesta_48h("99302")
    assert _score(sqlite_db, "99302") == 50
