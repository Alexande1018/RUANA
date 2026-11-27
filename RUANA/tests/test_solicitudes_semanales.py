"""Tests solicitudes semanales — aislamiento por grupo, varias por semana y autorización."""

from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from core import db_manager as db_module
from core.services import solicitud_semanal_service


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    return db_module.DBManager(str(tmp_path / "ruana_sol_sem.db"))


def _semana_actual():
    d = date.today()
    lunes = d - timedelta(days=d.weekday())
    return lunes.isoformat()


def _crear_grupo(db, nombre, cp, codigos_oficios):
    conn = db._connect()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO grupos (nombre, codigo_postal, estado) VALUES (?, ?, ?)",
        (nombre, cp, "activo"),
    )
    grupo_id = cursor.lastrowid
    for item in codigos_oficios:
        if len(item) == 4:
            codigo, nombre_aliado, oficio, aliado_cp = item
        else:
            codigo, nombre_aliado, oficio = item
            aliado_cp = cp
        cursor.execute(
            """
            INSERT INTO aliados (codigo, nombre, oficio, codigo_postal, grupo_id, estado)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (codigo, nombre_aliado, oficio, aliado_cp, grupo_id, "activo"),
        )
    conn.commit()
    conn.close()
    return grupo_id


def test_crear_solicitud_valida(sqlite_db):
    _crear_grupo(
        sqlite_db,
        "Grupo 25",
        "03014",
        [
            ("JAIME", "Jaime", "Electricidad"),
            ("MARTA", "Marta", "Fontanería y fontanería-gas"),
        ],
    )
    r = solicitud_semanal_service.crear_solicitud_semanal(
        sqlite_db,
        "JAIME",
        "Electricidad",
        "Necesito fotos de producto",
        es_oficio_personalizado=False,
    )
    assert r["status"] == "success"
    assert r["id"]


def test_panel_incluye_oficios_del_grupo_y_catalogo(sqlite_db):
    _crear_grupo(
        sqlite_db,
        "Grupo oficios",
        "03014",
        [("JAIME", "Jaime", "Electricidad")],
    )
    panel = solicitud_semanal_service.obtener_panel_por_codigo(sqlite_db, "JAIME")
    assert panel["status"] == "success"
    assert "Electricidad" in panel["oficios_grupo"]
    assert isinstance(panel["oficios_catalogo"], list)
    assert len(panel["oficios_catalogo"]) > 0


def test_varias_solicitudes_misma_semana(sqlite_db):
    _crear_grupo(
        sqlite_db,
        "Grupo dup",
        "03014",
        [
            ("JAIME", "Jaime", "Electricidad"),
            ("MARTA", "Marta", "Fontanería y fontanería-gas"),
        ],
    )
    r1 = solicitud_semanal_service.crear_solicitud_semanal(
        sqlite_db, "JAIME", "Electricidad", "Primera", False
    )
    assert r1["status"] == "success"
    r2 = solicitud_semanal_service.crear_solicitud_semanal(
        sqlite_db, "JAIME", "Carpintería de madera e interior", "Segunda", False
    )
    assert r2["status"] == "success"
    assert r2.get("already_existed") is not True
    assert r2["id"] != r1["id"]
    assert "semana" not in (r2.get("message") or "").lower()

    panel = solicitud_semanal_service.obtener_panel_por_codigo(sqlite_db, "JAIME")
    assert [p["id"] for p in panel["propias"]] == [r2["id"], r1["id"]]
    panel_marta = solicitud_semanal_service.obtener_panel_por_codigo(sqlite_db, "MARTA")
    assert {s["id"] for s in panel_marta["activas_grupo"]} == {r1["id"], r2["id"]}


def test_solicitud_vinculada_al_grupo_correcto(sqlite_db):
    gid = _crear_grupo(
        sqlite_db,
        "Grupo 25",
        "03014",
        [("JAIME", "Jaime", "Electricidad")],
    )
    solicitud_semanal_service.crear_solicitud_semanal(
        sqlite_db, "JAIME", "Electricidad", "", False
    )
    conn = sqlite_db._connect()
    cursor = conn.cursor()
    cursor.execute("SELECT grupo_id FROM solicitudes_semanales WHERE solicitante_codigo = ?", ("JAIME",))
    row = cursor.fetchone()
    conn.close()
    assert row[0] == gid


def test_mismo_grupo_ve_solicitud_otro_grupo_no(sqlite_db):
    _crear_grupo(
        sqlite_db,
        "Grupo 25",
        "03014",
        [
            ("JAIME", "Jaime", "Electricidad"),
            ("MARTA", "Marta", "Fontanería y fontanería-gas"),
        ],
    )
    _crear_grupo(
        sqlite_db,
        "Grupo 26",
        "46015",
        # Otra provincia: no debe ver la solicitud (la visibilidad es provincial).
        [("PEDRO", "Pedro", "Carpintería de madera e interior")],
    )
    solicitud_semanal_service.crear_solicitud_semanal(
        sqlite_db, "JAIME", "Electricidad", "", False
    )

    panel_marta = solicitud_semanal_service.obtener_panel_por_codigo(sqlite_db, "MARTA")
    assert panel_marta["status"] == "success"
    assert len(panel_marta["activas_grupo"]) == 1
    assert panel_marta["activas_grupo"][0]["solicitante_codigo"] == "JAIME"
    assert panel_marta["activas_grupo"][0].get("de_grupo_cercano") is not True

    panel_pedro = solicitud_semanal_service.obtener_panel_por_codigo(sqlite_db, "PEDRO")
    assert panel_pedro["status"] == "success"
    assert panel_pedro["activas_grupo"] == []


def test_mismo_oficio_misma_provincia_grupo_sin_cobertura_ve_solicitud(sqlite_db):
    """Si el grupo no cubre el oficio pedido, un aliado del mismo oficio y provincia lo ve."""
    _crear_grupo(
        sqlite_db,
        "Grupo 2",
        "28100",
        [
            ("92979", "Juan Pablo", "Electricidad"),
        ],
    )
    _crear_grupo(
        sqlite_db,
        "Grupo 9",
        "28770",
        [
            ("75658", "Stop Fugas", "Fontanería y fontanería-gas"),
        ],
    )
    creada = solicitud_semanal_service.crear_solicitud_semanal(
        sqlite_db, "92979", "Fontanería y fontanería-gas", "Fuga en casa", False
    )
    assert creada["status"] == "success"
    sid = creada["id"]

    panel = solicitud_semanal_service.obtener_panel_por_codigo(sqlite_db, "75658")
    assert panel["status"] == "success"
    assert len(panel["activas_grupo"]) == 1
    item = panel["activas_grupo"][0]
    assert item["id"] == sid
    assert item["solicitante_codigo"] == "92979"
    # El oficio pedido vive en solicitudes_semanales.oficio
    assert item["oficio"] == "Fontanería y fontanería-gas"
    assert item["de_grupo_cercano"] is True
    assert item["etiqueta"] == "De tu provincia"

    ayuda = solicitud_semanal_service.responder_puedo_ayudar(sqlite_db, sid, "75658")
    assert ayuda["status"] == "success"
    assert ayuda["contacto_id"]
    assert ayuda["solicitante_codigo"] == "92979"


def test_misma_provincia_ve_aunque_el_grupo_cubra_el_oficio(sqlite_db):
    """24 nov 2026: la solicitud llega a toda la provincia aunque el grupo cubra el oficio."""
    _crear_grupo(
        sqlite_db,
        "Grupo 2 cubierto",
        "28100",
        [
            ("92979", "Juan Pablo", "Electricidad"),
            ("FONT2", "Fontanero del grupo", "Fontanería y fontanería-gas"),
        ],
    )
    _crear_grupo(
        sqlite_db,
        "Grupo 9",
        "28770",
        [
            ("75658", "Stop Fugas", "Fontanería y fontanería-gas"),
        ],
    )
    creada = solicitud_semanal_service.crear_solicitud_semanal(
        sqlite_db, "92979", "Fontanería y fontanería-gas", "", False
    )
    assert creada["status"] == "success"

    panel = solicitud_semanal_service.obtener_panel_por_codigo(sqlite_db, "75658")
    assert panel["status"] == "success"
    assert [x["id"] for x in panel["activas_grupo"]] == [creada["id"]]
    assert panel["activas_grupo"][0]["de_grupo_cercano"] is True

    ok = solicitud_semanal_service.responder_puedo_ayudar(sqlite_db, creada["id"], "75658")
    assert ok["status"] == "success"


def test_misma_provincia_otro_oficio_ve_y_recibe_aviso(sqlite_db, monkeypatch):
    """Todos los activos de la provincia (cualquier oficio, otro grupo) la ven y reciben aviso;
    los de otra provincia y los no activos, no."""
    from core.services import notificacion_service

    avisados = []
    monkeypatch.setattr(
        notificacion_service, "crear_notificacion_aliado",
        lambda db, codigo, tipo, *a, **k: avisados.append((codigo, tipo)),
    )
    _crear_grupo(sqlite_db, "G Claudio", "28012", [("11048", "Claudio", "Pintura y decoración"),
                                                    ("MISMO", "Del grupo", "Electricidad")])
    _crear_grupo(sqlite_db, "G Mostafa", "28022", [("45415", "Mostafa", "Pintura y decoración")])
    _crear_grupo(sqlite_db, "G Tudor", "28021", [("54234", "Tudor", "Albañilería y obra")])
    _crear_grupo(sqlite_db, "G Toledo", "45007", [("86761", "Andres", "Electricidad")])
    gid_val = _crear_grupo(sqlite_db, "G Val", "46009", [("88277", "Rafael", "Electricidad")])
    conn = sqlite_db._connect()
    conn.execute(
        "INSERT INTO aliados (codigo, nombre, oficio, codigo_postal, grupo_id, estado) "
        "VALUES ('BAJA1', 'Baja', 'Pintura y decoración', '28013', ?, 'baja')", (gid_val,))
    conn.commit()
    conn.close()

    creada = solicitud_semanal_service.crear_solicitud_semanal(
        sqlite_db, "11048", "Pintura y decoración", "Piso", False
    )
    assert creada["status"] == "success"
    sid = creada["id"]
    for cod in ("MISMO", "45415", "54234"):
        panel = solicitud_semanal_service.obtener_panel_por_codigo(sqlite_db, cod)
        assert sid in [x["id"] for x in panel["activas_grupo"]], cod
    for cod in ("86761", "88277"):
        panel = solicitud_semanal_service.obtener_panel_por_codigo(sqlite_db, cod)
        assert sid not in [x["id"] for x in panel["activas_grupo"]], cod
    cods = sorted(c for c, t in avisados if t == "solicitud_semanal_nueva")
    assert cods == ["45415", "54234", "MISMO"]

def test_mismo_oficio_otra_provincia_no_ve(sqlite_db):
    """Mismo oficio, pero otra provincia (otros 2 dígitos de CP), no la ve."""
    _crear_grupo(
        sqlite_db,
        "Grupo 2",
        "28100",
        [
            ("92979", "Juan Pablo", "Electricidad"),
        ],
    )
    _crear_grupo(
        sqlite_db,
        "Grupo 25 Huesca",
        "22003",
        [
            ("HUESCA", "Aliado Huesca", "Fontanería y fontanería-gas"),
        ],
    )
    creada = solicitud_semanal_service.crear_solicitud_semanal(
        sqlite_db, "92979", "Fontanería y fontanería-gas", "", False
    )
    assert creada["status"] == "success"

    panel = solicitud_semanal_service.obtener_panel_por_codigo(sqlite_db, "HUESCA")
    assert panel["status"] == "success"
    assert panel["activas_grupo"] == []

    denegado = solicitud_semanal_service.responder_puedo_ayudar(
        sqlite_db, creada["id"], "HUESCA"
    )
    assert denegado["status"] == "error"


def test_puedo_ayudar_y_listar_interesados(sqlite_db):
    _crear_grupo(
        sqlite_db,
        "Grupo ayuda",
        "03014",
        [
            ("JAIME", "Jaime", "Electricidad"),
            ("MARTA", "Marta", "Electricidad"),
        ],
    )
    creada = solicitud_semanal_service.crear_solicitud_semanal(
        sqlite_db, "JAIME", "Electricidad", "", False
    )
    sid = creada["id"]
    ayuda = solicitud_semanal_service.responder_puedo_ayudar(sqlite_db, sid, "MARTA")
    assert ayuda["status"] == "success"
    assert ayuda["contacto_id"]

    inter = solicitud_semanal_service.listar_interesados(sqlite_db, sid, "JAIME")
    assert inter["status"] == "success"
    assert inter["total"] == 1
    assert inter["interesados"][0]["aliado_codigo"] == "MARTA"

    denegado = solicitud_semanal_service.listar_interesados(sqlite_db, sid, "MARTA")
    assert denegado["status"] == "error"


def test_panel_sin_solucion_tras_no_puedo_ayudar(sqlite_db):
    """Si solo hay 'no puedo ayudar', la solicitud sigue sin ayuda ni recomendaciones."""
    _crear_grupo(
        sqlite_db,
        "Grupo sin solucion",
        "03014",
        [
            ("JAIME", "Jaime", "Electricidad"),
            ("MARTA", "Marta", "Fontanería y fontanería-gas"),
        ],
    )
    creada = solicitud_semanal_service.crear_solicitud_semanal(
        sqlite_db, "JAIME", "Electricidad", "", False
    )
    sid = creada["id"]
    r = solicitud_semanal_service.responder_no_puedo_ayudar(sqlite_db, sid, "MARTA")
    assert r["status"] == "success"

    panel = solicitud_semanal_service.obtener_panel_por_codigo(sqlite_db, "MARTA")
    assert panel["status"] == "success"
    assert len(panel["activas_grupo"]) == 1
    activa = panel["activas_grupo"][0]
    assert activa["mi_respuesta"] == "no_puedo_ayudar"
    assert activa["interesados_count"] == 0
    assert activa["recomendaciones_count"] == 0


def test_panel_recomendaciones_count_despues_conozco(sqlite_db):
    _crear_grupo(
        sqlite_db,
        "Grupo recomiendo",
        "03014",
        [
            ("JAIME", "Jaime", "Electricidad"),
            ("MARTA", "Marta", "Fontanería y fontanería-gas"),
        ],
    )
    creada = solicitud_semanal_service.crear_solicitud_semanal(
        sqlite_db, "JAIME", "Fotografía", "", True
    )
    sid = creada["id"]
    n = {"i": 0}

    def _codigo(_db):
        n["i"] += 1
        return "INV%05d" % n["i"]

    r = solicitud_semanal_service.responder_conozco_alguien(
        sqlite_db, sid, "MARTA", _codigo
    )
    assert r["status"] == "success"
    assert r.get("codigo")

    panel = solicitud_semanal_service.obtener_panel_por_codigo(sqlite_db, "MARTA")
    activa = panel["activas_grupo"][0]
    assert activa["mi_respuesta"] == "conozco_alguien"
    assert activa["interesados_count"] == 0
    assert activa["recomendaciones_count"] == 1


def test_panel_otro_aliado_ya_puede_ayudar(sqlite_db):
    """Si alguien ya puede ayudar, la solicitud deja de estar sin solución."""
    _crear_grupo(
        sqlite_db,
        "Grupo ya ayuda",
        "03014",
        [
            ("JAIME", "Jaime", "Electricidad"),
            ("MARTA", "Marta", "Fontanería y fontanería-gas"),
            ("PEDRO", "Pedro", "Electricidad"),
        ],
    )
    creada = solicitud_semanal_service.crear_solicitud_semanal(
        sqlite_db, "JAIME", "Electricidad", "", False
    )
    sid = creada["id"]
    r_no = solicitud_semanal_service.responder_no_puedo_ayudar(sqlite_db, sid, "MARTA")
    assert r_no["status"] == "success"
    r_si = solicitud_semanal_service.responder_puedo_ayudar(sqlite_db, sid, "PEDRO")
    assert r_si["status"] == "success"

    panel = solicitud_semanal_service.obtener_panel_por_codigo(sqlite_db, "MARTA")
    activa = panel["activas_grupo"][0]
    assert activa["mi_respuesta"] == "no_puedo_ayudar"
    assert activa["interesados_count"] == 1
    assert activa["recomendaciones_count"] == 0


def test_no_puedo_ayudar_otro_grupo_fallido(sqlite_db):
    gid25 = _crear_grupo(
        sqlite_db,
        "Grupo 25",
        "03014",
        [("JAIME", "Jaime", "Electricidad")],
    )
    _crear_grupo(
        sqlite_db,
        "Grupo 26",
        "46015",
        [("PEDRO", "Pedro", "Carpintería de madera e interior")],
    )
    creada = solicitud_semanal_service.crear_solicitud_semanal(
        sqlite_db, "JAIME", "Electricidad", "", False
    )
    sid = creada["id"]
    r = solicitud_semanal_service.responder_no_puedo_ayudar(sqlite_db, sid, "PEDRO")
    assert r["status"] == "error"


def test_expirada_deja_de_estar_activa_conserva_historial(sqlite_db):
    gid = _crear_grupo(
        sqlite_db,
        "Grupo exp",
        "03014",
        [("JAIME", "Jaime", "Electricidad")],
    )
    semana_pasada = (date.today() - timedelta(days=7)).isoformat()
    conn = sqlite_db._connect()
    cursor = conn.cursor()
    sqlite_db._migrar_solicitudes_semanales(conn, cursor)
    cursor.execute(
        """
        INSERT INTO solicitudes_semanales (
            grupo_id, solicitante_codigo, solicitante_nombre, oficio, descripcion,
            es_oficio_personalizado, semana_inicio, estado, expira_at
        ) VALUES (?, ?, ?, ?, ?, 0, ?, 'activa', ?)
        """,
        (gid, "JAIME", "Jaime", "Electricidad", "vieja", semana_pasada, semana_pasada),
    )
    conn.commit()
    conn.close()

    solicitud_semanal_service.expirar_solicitudes_vencidas(sqlite_db)
    panel = solicitud_semanal_service.obtener_panel_por_codigo(sqlite_db, "JAIME")
    assert panel["propia"] is None

    conn = sqlite_db._connect()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT estado FROM solicitudes_semanales WHERE semana_inicio = ?",
        (semana_pasada,),
    )
    estado = cursor.fetchone()[0]
    conn.close()
    assert estado == "expirada"


def test_oficio_personalizado_otro(sqlite_db):
    _crear_grupo(
        sqlite_db,
        "Grupo otro",
        "03014",
        [("JAIME", "Jaime", "Electricidad")],
    )
    r = solicitud_semanal_service.crear_solicitud_semanal(
        sqlite_db,
        "JAIME",
        "Fotógrafo especializado en producto",
        "",
        es_oficio_personalizado=True,
    )
    assert r["status"] == "success"
    panel = solicitud_semanal_service.obtener_panel_por_codigo(sqlite_db, "JAIME")
    assert panel["propia"]["es_oficio_personalizado"] == 1


def test_api_crear_y_aislamiento(client, sqlite_db, monkeypatch, session_headers):
    from RUANA.web import app as app_module

    _crear_grupo(
        sqlite_db,
        "Grupo API 25",
        "03014",
        [
            ("JAIME", "Jaime", "Electricidad"),
            ("MARTA", "Marta", "Fontanería y fontanería-gas"),
        ],
    )
    _crear_grupo(
        sqlite_db,
        "Grupo API 26",
        "46015",
        [("PEDRO", "Pedro", "Carpintería de madera e interior")],
    )
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)

    h_jaime = session_headers("aliado", "JAIME")
    h_marta = session_headers("aliado", "MARTA")
    h_pedro = session_headers("aliado", "PEDRO")

    create = client.post(
        "/api/solicitudes-semanales",
        json={"oficio": "Electricidad", "descripcion": "Producto"},
        headers=h_jaime,
    )
    assert create.status_code == 201

    get_marta = client.get("/api/solicitudes-semanales", headers=h_marta)
    assert get_marta.status_code == 200
    data_m = get_marta.get_json()
    assert len(data_m["activas_grupo"]) == 1

    get_pedro = client.get("/api/solicitudes-semanales", headers=h_pedro)
    assert get_pedro.status_code == 200
    assert get_pedro.get_json()["activas_grupo"] == []

    dup = client.post(
        "/api/solicitudes-semanales",
        json={"oficio": "Carpintería de madera e interior"},
        headers=h_jaime,
    )
    assert dup.status_code == 201
    dup_body = dup.get_json()
    assert dup_body.get("already_existed") is False
    assert dup_body.get("id") != create.get_json()["id"]
    assert "semana" not in (dup_body.get("error") or "").lower()


def test_manipulacion_id_otro_grupo(client, sqlite_db, monkeypatch, session_headers):
    from RUANA.web import app as app_module

    _crear_grupo(
        sqlite_db,
        "G1",
        "03014",
        [("JAIME", "Jaime", "Electricidad")],
    )
    _crear_grupo(
        sqlite_db,
        "G2",
        "46015",
        [("PEDRO", "Pedro", "Carpintería de madera e interior")],
    )
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    creada = solicitud_semanal_service.crear_solicitud_semanal(
        sqlite_db, "JAIME", "Electricidad", "", False
    )
    sid = creada["id"]
    resp = client.post(
        f"/api/solicitudes-semanales/{sid}/puedo-ayudar",
        headers=session_headers("aliado", "PEDRO"),
    )
    assert resp.status_code == 400


def test_migrar_solicitudes_semanales_postgres_crea_tablas():
    from core.services import schema_service

    calls = []

    class FakeCursor:
        def execute(self, sql, params=None):
            calls.append(str(sql).strip())

    db = db_module.DBManager.__new__(db_module.DBManager)
    db.backend = "postgres"

    schema_service._migrar_solicitudes_semanales(db, None, FakeCursor())

    joined = "\n".join(calls)
    assert "CREATE TABLE IF NOT EXISTS solicitudes_semanales" in joined
    assert "CREATE TABLE IF NOT EXISTS solicitudes_semanales_respuestas" in joined
    assert "DROP INDEX IF EXISTS idx_sol_sem_solicitante_semana" in joined
    assert "CREATE INDEX IF NOT EXISTS idx_sol_sem_solicitante_semana" in joined
    assert "CREATE UNIQUE INDEX IF NOT EXISTS idx_sol_sem_solicitante_semana" not in joined


def test_asegurar_esquema_sol_sem_postgres_invoca_migracion(monkeypatch):
    calls = []

    class FakeCursor:
        pass

    class FakeConn:
        def rollback(self):
            pass

    db = db_module.DBManager.__new__(db_module.DBManager)
    db.backend = "postgres"
    monkeypatch.setattr(
        db,
        "_migrar_solicitudes_semanales",
        lambda conn, cursor: calls.append("migrar"),
    )

    from core.services.solicitud_semanal_service import _asegurar_esquema_sol_sem

    _asegurar_esquema_sol_sem(db, FakeConn(), FakeCursor())
    assert calls == ["migrar"]


def test_init_postgres_schema_incluye_solicitudes_semanales():
    import inspect
    from core.services import schema_service

    source = inspect.getsource(schema_service._init_postgres_schema_unlocked)
    assert "_migrar_solicitudes_semanales" in source


def test_listar_admin_incluye_grupo_y_respuestas(sqlite_db):
    _crear_grupo(
        sqlite_db,
        "Grupo admin sem",
        "03014",
        [
            ("JAIME", "Jaime", "Electricidad"),
            ("MARTA", "Marta", "Fontanería y fontanería-gas"),
        ],
    )
    creada = solicitud_semanal_service.crear_solicitud_semanal(
        sqlite_db, "JAIME", "Electricidad", "Necesito revisión", False
    )
    sid = creada["id"]
    r_no = solicitud_semanal_service.responder_no_puedo_ayudar(sqlite_db, sid, "MARTA")
    assert r_no["status"] == "success"

    panel = solicitud_semanal_service.listar_admin(sqlite_db)
    assert panel["status"] == "success"
    assert panel["activas_semana_count"] == 1
    assert len(panel["solicitudes"]) == 1
    item = panel["solicitudes"][0]
    assert item["id"] == sid
    assert item["solicitante_codigo"] == "JAIME"
    assert item["grupo_nombre"] == "Grupo admin sem"
    assert item["es_semana_actual"] is True
    assert item["no_pueden_count"] == 1
    assert item["interesados_count"] == 0
    assert item["recomendaciones_count"] == 0
    assert item["respuestas"][0]["aliado_codigo"] == "MARTA"
    assert item["respuestas"][0]["tipo_respuesta"] == "no_puedo_ayudar"


def test_api_admin_solicitudes_semanales(client, sqlite_db, monkeypatch, session_headers):
    from RUANA.web import app as app_module

    _crear_grupo(
        sqlite_db,
        "Grupo API admin",
        "03014",
        [("JAIME", "Jaime", "Electricidad")],
    )
    solicitud_semanal_service.crear_solicitud_semanal(
        sqlite_db, "JAIME", "Electricidad", "", False
    )
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)

    sin_sesion = client.get("/api/admin/solicitudes-semanales")
    assert sin_sesion.status_code == 401

    aliado = client.get(
        "/api/admin/solicitudes-semanales",
        headers=session_headers("aliado", "JAIME"),
    )
    assert aliado.status_code == 401

    admin = client.get(
        "/api/admin/solicitudes-semanales",
        headers=session_headers("admin", "ADMIN1", permisos=["leer"]),
    )
    assert admin.status_code == 200
    data = admin.get_json()
    assert data["status"] == "success"
    assert data["activas_semana_count"] == 1
    assert data["solicitudes"][0]["solicitante_codigo"] == "JAIME"


def test_mensaje_solicitud_semanal_grupo_usa_profesional_de():
    """El aviso evita «necesita un Pintura y decoración»; usa «profesional de»."""
    texto = solicitud_semanal_service._mensaje_solicitud_semanal_grupo(
        "Nico", "Pintura y decoración"
    )
    assert texto == "Esta semana Nico necesita un profesional de Pintura y decoración."
    vacio = solicitud_semanal_service._mensaje_solicitud_semanal_grupo("Ana", "")
    assert vacio == "Esta semana Ana necesita un profesional de profesional."
