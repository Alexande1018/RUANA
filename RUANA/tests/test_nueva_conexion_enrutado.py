"""Nueva conexión: oficio en grupo, cercano o buscando ayuda. Nunca a todos los aliados."""
from types import SimpleNamespace

import pytest

from core import db_manager as db_module
from core.services import notificacion_service, solicitud_service
from RUANA.web import app as app_module


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    return db_module.DBManager(str(tmp_path / "ruana_nueva_conexion.db"))


def _crear(db, codigo, oficio="Electricidad", cp="03001", estado="activo"):
    r = db.crear_aliado(
        codigo=codigo,
        nombre=f"Aliado {codigo}",
        marca="Marca",
        oficio=oficio,
        codigo_postal=cp,
        email=f"{codigo}@example.com",
        telefono=f"+34600{codigo}",
        estado=estado,
        score=50,
    )
    assert r.get("status") == "success", r
    conn = db._connect()
    conn.execute("UPDATE aliados SET estado = ? WHERE codigo = ?", (estado, codigo))
    conn.commit()
    conn.close()
    return r


def _tipos(db, codigo):
    return {n.get("tipo") for n in notificacion_service.listar_notificaciones_aliado(db, codigo)}


def _ids_entrantes(db, codigo):
    return {s.get("id") for s in solicitud_service.listar_solicitudes_activas_por_codigo(db, codigo)}


def _insertar_grupo_territorial(db, codigo_postal, nombre):
    conn = db._connect()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO grupos (nombre, codigo_postal, ciudad, provincia, estado, tipo)
        VALUES (?, ?, ?, ?, 'activo', 'territorial')
        """,
        (nombre, codigo_postal, "Alicante", "Alicante"),
    )
    gid = cur.lastrowid
    conn.commit()
    conn.close()
    return gid


def _forzar_grupo(db, codigo, grupo_id, codigo_postal=None):
    conn = db._connect()
    if codigo_postal is None:
        conn.execute("UPDATE aliados SET grupo_id = ? WHERE codigo = ?", (grupo_id, codigo))
    else:
        conn.execute(
            "UPDATE aliados SET grupo_id = ?, codigo_postal = ? WHERE codigo = ?",
            (grupo_id, codigo_postal, codigo),
        )
    conn.commit()
    conn.close()


def test_oficio_idiomas_mismo_cp_otro_grupo_recomienda_con_aprobacion(sqlite_db):
    """Sin el oficio en el grupo: se recomienda al más cercano del CP, sin entregarla aún."""
    _crear(sqlite_db, "91201", oficio="Electricidad", cp="03001")
    _crear(sqlite_db, "91202", oficio="Idiomas", cp="03001")
    extra_gid = _insertar_grupo_territorial(sqlite_db, "03001", "Grupo 03001 B")
    _forzar_grupo(sqlite_db, "91202", extra_gid, codigo_postal="03001")
    assert sqlite_db.obtener_aliado_por_codigo("91201")["grupo_id"] != extra_gid

    creada = solicitud_service.crear_solicitud_por_codigo(
        sqlite_db, "91201", "Idiomas", "Necesito clases de idiomas"
    )
    assert creada["status"] == "success"
    sid = creada["id"]
    assert creada["enrutamiento"] == "proximidad"
    assert creada["proximidad"]["codigo"] == "91202"
    assert creada.get("requiere_aprobacion_proximidad") is True
    assert creada.get("opciones_solicitante", {}).get("aceptar_proximidad") is True
    assert creada.get("opciones_solicitante", {}).get("pedir_recomendacion_grupo") is True
    assert "Te recomendamos" in (creada.get("mensaje") or "")
    assert "más cercano a tu código postal" in (creada.get("mensaje") or "")

    assert sid not in _ids_entrantes(sqlite_db, "91202")
    assert "solicitud_asignada" not in _tipos(sqlite_db, "91202")
    assert "proximidad_solicitud" not in _tipos(sqlite_db, "91202")

    propias = solicitud_service.listar_solicitudes_propias_por_codigo(sqlite_db, "91201")
    mia = next(s for s in propias if s.get("id") == sid)
    assert mia["requiere_aprobacion_proximidad"] is True
    assert mia["mensaje_solicitante"]
    assert mia["opciones_solicitante"]["aceptar_proximidad"] is True


def test_oficio_idiomas_en_grupo_entrega_inmediata(sqlite_db):
    """Caso de la prueba fallida: Idiomas existe en el grupo → llega al profesional."""
    _crear(sqlite_db, "91101", oficio="Electricidad", cp="03001")
    _crear(sqlite_db, "91102", oficio="Idiomas", cp="03001")

    creada = solicitud_service.crear_solicitud_por_codigo(
        sqlite_db, "91101", "Idiomas", "Clases de inglés de prueba"
    )
    assert creada["status"] == "success"
    sid = creada["id"]
    assert creada["enrutamiento"] == "profesional_grupo"
    assert creada["profesional"]["codigo"] == "91102"
    assert creada.get("requiere_aprobacion_proximidad") is not True
    assert "enviada a" in (creada.get("mensaje") or "").lower()

    assert sid in _ids_entrantes(sqlite_db, "91102")
    assert sid not in _ids_entrantes(sqlite_db, "91101")
    assert "solicitud_asignada" in _tipos(sqlite_db, "91102")
    assert "proximidad_solicitud" not in _tipos(sqlite_db, "91102")


def test_fontanero_mismo_grupo_aparece_en_recibidas_del_profesional(sqlite_db):
    """Carolina 58848 envía a Carlos 66803 (mismo grupo): él debe verla en recibidas."""
    _crear(sqlite_db, "58848", oficio="Electricidad", cp="03001")
    _crear(sqlite_db, "66803", oficio="Fontanería y fontanería-gas", cp="03001")

    creada = solicitud_service.crear_solicitud_por_codigo(
        sqlite_db, "58848", "Fontanería", "Fuga en casa, prueba Carolina"
    )
    assert creada["status"] == "success"
    sid = creada["id"]
    assert creada["enrutamiento"] == "profesional_grupo"
    assert creada["profesional"]["codigo"] == "66803"
    assert "enviada a" in (creada.get("mensaje") or "").lower()

    assert sid in _ids_entrantes(sqlite_db, "66803")
    assert sid not in _ids_entrantes(sqlite_db, "58848")
    propias = solicitud_service.listar_solicitudes_propias_por_codigo(sqlite_db, "58848")
    assert sid in {s.get("id") for s in propias}


def test_listar_recibidas_sigue_si_expirar_candidatos_falla(sqlite_db, monkeypatch):
    """Un fallo al caducar candidatos no puede dejar la bandeja del profesional vacía."""
    _crear(sqlite_db, "58848", oficio="Electricidad", cp="03001")
    _crear(sqlite_db, "66803", oficio="Fontanería y fontanería-gas", cp="03001")
    creada = solicitud_service.crear_solicitud_por_codigo(
        sqlite_db, "58848", "Fontanería", "No debe perderse si caduca mal"
    )
    assert creada["status"] == "success"
    sid = creada["id"]

    def boom(*_a, **_k):
        raise RuntimeError("datetime('now', ?) no vale en Postgres")

    monkeypatch.setattr(solicitud_service, "_expirar_candidatos_vencidos_lazy", boom)
    assert sid in _ids_entrantes(sqlite_db, "66803")


def test_oficio_idiomas_pendiente_validacion_en_grupo_entrega(sqlite_db):
    """El directorio muestra pendiente_validacion; Nueva conexión también debe entregarle."""
    _crear(sqlite_db, "91301", oficio="Electricidad", cp="03001")
    _crear(sqlite_db, "91302", oficio="Idiomas", cp="03001", estado="pendiente_validacion")
    grupo_id = sqlite_db.obtener_aliado_por_codigo("91301")["grupo_id"]
    _forzar_grupo(sqlite_db, "91302", grupo_id, codigo_postal="03001")

    creada = solicitud_service.crear_solicitud_por_codigo(
        sqlite_db, "91301", "Idiomas", "Prueba con aliado aún en validación"
    )
    assert creada["status"] == "success"
    sid = creada["id"]
    assert creada["enrutamiento"] == "profesional_grupo"
    assert creada["profesional"]["codigo"] == "91302"
    assert sid in _ids_entrantes(sqlite_db, "91302")
    assert "solicitud_asignada" in _tipos(sqlite_db, "91302")


def test_oficio_disponible_en_grupo_solo_ese_profesional(sqlite_db):
    _crear(sqlite_db, "91001", oficio="Electricidad", cp="03001")
    _crear(sqlite_db, "91002", oficio="Cerrajería", cp="03001")
    _crear(sqlite_db, "91003", oficio="Fontanería y fontanería-gas", cp="03001")

    creada = solicitud_service.crear_solicitud_por_codigo(
        sqlite_db, "91001", "Fontanería", "Fuga urgente en cocina"
    )
    assert creada["status"] == "success"
    sid = creada["id"]
    assert creada["enrutamiento"] == "profesional_grupo"
    assert creada["profesional"]["codigo"] == "91003"
    assert creada.get("proximidad_notificado") is False
    assert "todos los aliados" not in (creada.get("mensaje") or "").lower()

    assert sid in _ids_entrantes(sqlite_db, "91003")
    assert sid not in _ids_entrantes(sqlite_db, "91002")
    assert sid not in _ids_entrantes(sqlite_db, "91001")

    assert "solicitud_asignada" in _tipos(sqlite_db, "91003")
    assert "solicitud_nueva" not in _tipos(sqlite_db, "91002")
    assert "solicitud_buscando_ayuda" not in _tipos(sqlite_db, "91002")
    assert "proximidad_solicitud" not in _tipos(sqlite_db, "91002")
    assert "proximidad_solicitud" not in _tipos(sqlite_db, "91003")


def test_oficio_ausente_con_profesional_cercano_requiere_aprobacion(sqlite_db):
    _crear(sqlite_db, "92001", oficio="Electricidad", cp="03001")
    _crear(sqlite_db, "92002", oficio="Cerrajería", cp="03001")
    _crear(sqlite_db, "92003", oficio="Fontanería y fontanería-gas", cp="03003")

    creada = solicitud_service.crear_solicitud_por_codigo(
        sqlite_db, "92001", "Fontanería", "Necesito fontanero"
    )
    assert creada["status"] == "success"
    sid = creada["id"]
    assert creada["enrutamiento"] == "proximidad"
    assert creada["proximidad"]["codigo"] == "92003"
    assert creada["requiere_aprobacion_proximidad"] is True
    assert creada["proximidad_notificado"] is False
    assert "No hay fontanero en tu grupo" in creada["mensaje"]
    assert "Aliado 92003" in creada["mensaje"]
    assert "más cercano a tu código postal" in creada["mensaje"]
    assert creada["opciones_solicitante"]["aceptar_proximidad"] is True
    assert creada["opciones_solicitante"]["pedir_recomendacion_grupo"] is True

    assert sid not in _ids_entrantes(sqlite_db, "92002")
    assert sid not in _ids_entrantes(sqlite_db, "92003")
    assert "proximidad_solicitud" not in _tipos(sqlite_db, "92003")
    assert "solicitud_buscando_ayuda" not in _tipos(sqlite_db, "92002")
    assert "solicitud_nueva" not in _tipos(sqlite_db, "92002")

    propias = solicitud_service.listar_solicitudes_propias_por_codigo(sqlite_db, "92001")
    assert propias[0]["requiere_aprobacion_proximidad"] is True
    assert propias[0]["opciones_solicitante"]["aceptar_proximidad"] is True
    assert propias[0]["opciones_solicitante"]["pedir_recomendacion_grupo"] is True
    assert "Te recomendamos a" in (propias[0].get("mensaje_solicitante") or "")

    aceptada = solicitud_service.aceptar_proximidad_solicitud(sqlite_db, sid, "92001")
    assert aceptada["status"] == "success"
    assert aceptada.get("proximidad_notificado") is True

    assert sid in _ids_entrantes(sqlite_db, "92003")
    assert sid not in _ids_entrantes(sqlite_db, "92002")
    assert "proximidad_solicitud" in _tipos(sqlite_db, "92003")
    assert "proximidad_contactada" in _tipos(sqlite_db, "92002")
    assert "solicitud_nueva" not in _tipos(sqlite_db, "92002")


def test_pedir_recomendacion_al_grupo_tras_cercano(sqlite_db):
    _crear(sqlite_db, "92101", oficio="Electricidad", cp="03001")
    _crear(sqlite_db, "92102", oficio="Cerrajería", cp="03001")
    _crear(sqlite_db, "92103", oficio="Fontanería y fontanería-gas", cp="03003")

    creada = solicitud_service.crear_solicitud_por_codigo(
        sqlite_db, "92101", "Fontanería", "Fuga en baño"
    )
    sid = creada["id"]
    pedida = solicitud_service.pedir_recomendacion_grupo_solicitud(sqlite_db, sid, "92101")
    assert pedida["status"] == "success"
    assert pedida["enrutamiento"] == "buscando_ayuda"
    assert "recomendar a alguien que entre al grupo" in (pedida.get("mensaje") or "")

    assert sid in _ids_entrantes(sqlite_db, "92102")
    assert sid not in _ids_entrantes(sqlite_db, "92103")
    assert "solicitud_buscando_ayuda" in _tipos(sqlite_db, "92102")
    assert "proximidad_solicitud" not in _tipos(sqlite_db, "92103")


def test_oficio_sin_profesional_cercano_queda_buscando_ayuda(sqlite_db):
    _crear(sqlite_db, "93001", oficio="Electricidad", cp="03001")
    _crear(sqlite_db, "93002", oficio="Cerrajería", cp="03001")

    creada = solicitud_service.crear_solicitud_por_codigo(
        sqlite_db, "93001", "Fontanería", "No hay nadie cerca"
    )
    assert creada["status"] == "success"
    sid = creada["id"]
    assert creada["enrutamiento"] == "buscando_ayuda"
    assert creada.get("proximidad") is None
    assert "Buscando ayuda" in (creada.get("mensaje") or "")

    propias = solicitud_service.listar_solicitudes_propias_por_codigo(sqlite_db, "93001")
    assert propias[0]["destino"] == "buscando_ayuda"
    assert propias[0]["etiqueta_busqueda"] == "Buscando ayuda"

    assert sid in _ids_entrantes(sqlite_db, "93002")
    assert "solicitud_buscando_ayuda" in _tipos(sqlite_db, "93002")
    assert "solicitud_asignada" not in _tipos(sqlite_db, "93002")


def test_nunca_se_envia_la_solicitud_a_todos_los_aliados(sqlite_db):
    _crear(sqlite_db, "94001", oficio="Electricidad", cp="04001")
    _crear(sqlite_db, "94002", oficio="Cerrajería", cp="04001")
    _crear(sqlite_db, "94003", oficio="Pintura y decoración", cp="04001")
    _crear(sqlite_db, "94004", oficio="Fontanería y fontanería-gas", cp="04001")

    creada = solicitud_service.crear_solicitud_por_codigo(
        sqlite_db, "94001", "Fontanería", "Solo el fontanero"
    )
    sid = creada["id"]
    assert creada["enrutamiento"] == "profesional_grupo"

    for codigo in ("94002", "94003"):
        assert sid not in _ids_entrantes(sqlite_db, codigo)
        tipos = _tipos(sqlite_db, codigo)
        assert "solicitud_nueva" not in tipos
        assert "solicitud_asignada" not in tipos
        assert "solicitud_buscando_ayuda" not in tipos

    assert sid in _ids_entrantes(sqlite_db, "94004")
    assert "solicitud_asignada" in _tipos(sqlite_db, "94004")


def test_api_nueva_conexion_enruta_y_acepta_proximidad(
    client, sqlite_db, monkeypatch, session_headers
):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    _crear(sqlite_db, "95001", oficio="Electricidad", cp="03001")
    _crear(sqlite_db, "95002", oficio="Cerrajería", cp="03001")
    _crear(sqlite_db, "95003", oficio="Fontanería y fontanería-gas", cp="03003")

    headers = session_headers("aliado", "95001")
    created = client.post(
        "/api/solicitudes",
        json={"oficio": "Fontanería", "descripcion": "Fuga en la cocina de casa"},
        headers=headers,
    )
    assert created.status_code == 200
    body = created.get_json()
    assert body["ok"] is True
    assert body["enrutamiento"] == "proximidad"
    assert "No hay fontanero en tu grupo" in body["mensaje"]
    assert body["requiere_aprobacion_proximidad"] is True
    assert body.get("opciones_solicitante", {}).get("aceptar_proximidad") is True
    sid = body["id"]

    listed = client.get("/api/solicitudes", headers=headers)
    assert listed.status_code == 200
    payload = listed.get_json()
    propias = payload.get("propias") or []
    mia = next(s for s in propias if s.get("id") == sid)
    assert mia["requiere_aprobacion_proximidad"] is True
    assert "Te recomendamos" in (mia.get("mensaje_solicitante") or "")
    assert mia["opciones_solicitante"]["pedir_recomendacion_grupo"] is True

    acepta = client.post(
        f"/api/solicitudes/{sid}/aceptar-proximidad",
        headers=headers,
    )
    assert acepta.status_code == 200
    assert acepta.get_json()["ok"] is True
    assert sid in _ids_entrantes(sqlite_db, "95003")
    assert "proximidad_contactada" in _tipos(sqlite_db, "95002")


def test_api_idiomas_en_grupo_aparece_en_recibidas(
    client, sqlite_db, monkeypatch, session_headers
):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    _crear(sqlite_db, "95101", oficio="Electricidad", cp="03001")
    _crear(sqlite_db, "95102", oficio="Idiomas", cp="03001")

    headers = session_headers("aliado", "95101")
    created = client.post(
        "/api/solicitudes",
        json={"oficio": "Idiomas", "descripcion": "Clases de prueba de idiomas"},
        headers=headers,
    )
    assert created.status_code == 200
    body = created.get_json()
    assert body["ok"] is True
    assert body["enrutamiento"] == "profesional_grupo"
    assert "enviada a" in (body.get("mensaje") or "").lower()
    sid = body["id"]

    prof_headers = session_headers("aliado", "95102")
    listed = client.get("/api/solicitudes", headers=prof_headers)
    assert listed.status_code == 200
    payload = listed.get_json()
    ids = {s.get("id") for s in (payload.get("entrantes") or [])}
    assert sid in ids
    assert "solicitud_asignada" in _tipos(sqlite_db, "95102")


def test_fontaneria_desde_03014_recomienda_fontanero_de_03001(sqlite_db):
    """Sandra (03014) pide Fontanería: el fontanero activo de Alicante 03001 es cercano."""
    conn = sqlite_db._connect()
    conn.execute(
        "INSERT OR REPLACE INTO cp_ciudad (codigo_postal, ciudad, provincia) "
        "VALUES ('03014', 'San Blas', 'Alicante')"
    )
    conn.commit()
    conn.close()

    _crear(sqlite_db, "96101", oficio="Electricidad", cp="03014")
    _crear(sqlite_db, "96102", oficio="Cerrajería", cp="03014")
    _crear(sqlite_db, "96103", oficio="Fontanería y fontanería-gas", cp="03001")

    creada = solicitud_service.crear_solicitud_por_codigo(
        sqlite_db, "96101", "Fontanería", "Fuga en el baño, prueba Sandra"
    )
    assert creada["status"] == "success"
    assert creada["enrutamiento"] == "proximidad"
    assert creada["proximidad"]["codigo"] == "96103"
    assert creada["requiere_aprobacion_proximidad"] is True
    assert creada["proximidad_notificado"] is False
    mensaje = creada.get("mensaje") or ""
    assert "Buscando ayuda" not in mensaje
    assert "Te recomendamos" in mensaje
    assert "03001" in mensaje


def test_fontaneria_corta_en_03001_tambien_es_cercana_desde_03014(sqlite_db):
    """Si el oficio está guardado como Fontanería (forma corta), sigue siendo el mismo oficio."""
    _crear(sqlite_db, "96201", oficio="Electricidad", cp="03014")
    _crear(sqlite_db, "96202", oficio="Fontanería", cp="03001")
    gid = _insertar_grupo_territorial(sqlite_db, "03001", "Grupo fontanero 03001")
    _forzar_grupo(sqlite_db, "96202", gid, codigo_postal="03001")

    creada = solicitud_service.crear_solicitud_por_codigo(
        sqlite_db, "96201", "Fontanería", "Necesito fontanero cercano"
    )
    assert creada["status"] == "success"
    assert creada["enrutamiento"] == "proximidad"
    assert creada["proximidad"]["codigo"] == "96202"
    assert creada["requiere_aprobacion_proximidad"] is True


def test_fontanero_de_madrid_no_es_cercano_desde_alicante(sqlite_db):
    _crear(sqlite_db, "96301", oficio="Electricidad", cp="03014")
    _crear(sqlite_db, "96302", oficio="Fontanería y fontanería-gas", cp="28001")

    creada = solicitud_service.crear_solicitud_por_codigo(
        sqlite_db, "96301", "Fontanería", "No debe saltar a Madrid"
    )
    assert creada["status"] == "success"
    assert creada["enrutamiento"] == "buscando_ayuda"
    assert creada.get("proximidad") is None


def test_crear_solicitud_proximidad_no_abre_conexion_anidada(sqlite_db):
    """El POST no debe abrir una 2ª conexión mientras sostiene la primera (cuelga en Postgres)."""
    _crear(sqlite_db, "96401", oficio="Electricidad", cp="03014")
    _crear(sqlite_db, "96402", oficio="Fontanería y fontanería-gas", cp="03001")

    original = sqlite_db._connect
    opens = {"n": 0}

    def wrapped():
        opens["n"] += 1
        return original()

    sqlite_db._connect = wrapped
    try:
        creada = solicitud_service.crear_solicitud_por_codigo(
            sqlite_db, "96401", "Fontanería", "Fuga, prueba de conexión única"
        )
    finally:
        sqlite_db._connect = original

    assert creada.get("status") == "success", creada
    assert creada["enrutamiento"] == "proximidad"
    assert creada["proximidad"]["codigo"] == "96402"
    assert opens["n"] == 1
