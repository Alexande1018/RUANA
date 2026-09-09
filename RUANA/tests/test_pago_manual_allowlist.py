from types import SimpleNamespace

import pytest

from core import db_manager as db_module
from RUANA.web import app as app_module

_IBAN_FAKE = "ES0000000000000000000000"
_BIZUM_FAKE = "600000000"


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    db = db_module.DBManager(str(tmp_path / "pago_manual_allowlist.db"))
    monkeypatch.setattr(app_module, "get_db", lambda: db)
    conn = db._connect()
    conn.execute(
        "INSERT INTO aliados (codigo, nombre, email, estado) VALUES (?, ?, ?, ?)",
        ("A0001", "Aliado Uno", "a1@test.com", "activo"),
    )
    conn.execute(
        "INSERT INTO aliados (codigo, nombre, email, estado) VALUES (?, ?, ?, ?)",
        ("77357", "Aliado Numerico", "n77357@test.com", "activo"),
    )
    conn.commit()
    conn.close()
    return db


def _admin_headers(session_headers, escritura=True):
    permisos = ["leer", "configurar"] if escritura else ["leer"]
    return session_headers("admin", "ADMIN001", permisos=permisos)


def test_metodos_pago_aliado_no_habilitado_oculta_datos(client, sqlite_db, session_headers):
    sqlite_db.actualizar_metodos_pago_ruana(
        {"bizum_num": _BIZUM_FAKE, "iban": _IBAN_FAKE},
        admin_codigo="ADMIN001",
    )
    resp = client.get("/api/metodos-pago", headers=session_headers("aliado", "A0001"))
    assert resp.status_code == 200
    metodos = resp.get_json()["metodos"]
    assert metodos["habilitado"] is False
    assert metodos["bizum_num"] is None
    assert metodos["iban"] is None
    assert metodos["qr_revolut_path"] is None


def test_metodos_pago_aliado_habilitado_devuelve_datos(client, sqlite_db, session_headers):
    sqlite_db.actualizar_metodos_pago_ruana(
        {"bizum_num": _BIZUM_FAKE, "iban": _IBAN_FAKE},
        admin_codigo="ADMIN001",
    )
    ok = sqlite_db.habilitar_pago_manual_aliado("A0001", "ADMIN001")
    assert ok.get("status") == "success"
    resp = client.get("/api/metodos-pago", headers=session_headers("aliado", "A0001"))
    assert resp.status_code == 200
    metodos = resp.get_json()["metodos"]
    assert metodos["habilitado"] is True
    assert metodos["bizum_num"] == _BIZUM_FAKE
    assert metodos["iban"] == _IBAN_FAKE


def test_habilitar_deshabilitar_sin_admin_es_401(client):
    r1 = client.post("/api/admin/metodos-pago/aliados/A0001/habilitar")
    r2 = client.post("/api/admin/metodos-pago/aliados/A0001/deshabilitar")
    assert r1.status_code == 401
    assert r2.status_code == 401


def test_habilitar_sin_iban_ni_bizum_es_400(client, sqlite_db, session_headers):
    resp = client.post(
        "/api/admin/metodos-pago/aliados/A0001/habilitar",
        headers=_admin_headers(session_headers),
        json={},
    )
    assert resp.status_code == 400
    assert resp.get_json().get("status") == "error"


def test_habilitar_listar_y_deshabilitar_allowlist(client, sqlite_db, session_headers):
    sqlite_db.actualizar_metodos_pago_ruana(
        {"bizum_num": _BIZUM_FAKE, "iban": _IBAN_FAKE},
        admin_codigo="ADMIN001",
    )
    headers = _admin_headers(session_headers)
    hab = client.post(
        "/api/admin/metodos-pago/aliados/A0001/habilitar",
        headers=headers,
        json={},
    )
    assert hab.status_code == 200
    listed = client.get("/api/admin/metodos-pago/aliados", headers=headers)
    assert listed.status_code == 200
    aliados = listed.get_json()["aliados"]
    assert any(a["aliado_codigo"] == "A0001" for a in aliados)

    des = client.post(
        "/api/admin/metodos-pago/aliados/A0001/deshabilitar",
        headers=headers,
        json={},
    )
    assert des.status_code == 200
    listed2 = client.get("/api/admin/metodos-pago/aliados", headers=headers)
    aliados2 = listed2.get_json()["aliados"]
    assert all(a["aliado_codigo"] != "A0001" for a in aliados2)

    resp = client.get("/api/metodos-pago", headers=session_headers("aliado", "A0001"))
    assert resp.get_json()["metodos"]["habilitado"] is False
    assert resp.get_json()["metodos"]["iban"] is None


def test_listar_aliados_incluye_activo_recien_creado(sqlite_db):
    conn = sqlite_db._connect()
    conn.execute(
        "INSERT INTO aliados (codigo, nombre, email, estado) VALUES (?, ?, ?, ?)",
        ("99001", "Aliado Recien Creado", "nuevo@test.com", "activo"),
    )
    conn.commit()
    conn.close()
    codigos = {str(a["codigo"]) for a in sqlite_db.listar_aliados()}
    assert "77357" in codigos
    assert "99001" in codigos


def _count_rows(db, table):
    conn = db._connect()
    try:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    finally:
        conn.close()


def test_habilitar_aliado_activo_numerico_persiste_sin_crear_cargo(
    client, sqlite_db, session_headers
):
    sqlite_db.actualizar_metodos_pago_ruana(
        {"bizum_num": _BIZUM_FAKE, "iban": _IBAN_FAKE},
        admin_codigo="ADMIN001",
    )
    contactos_antes = _count_rows(sqlite_db, "contactos_ruana")
    ingresos_antes = _count_rows(sqlite_db, "ingresos_ruana")
    headers = _admin_headers(session_headers)

    hab = client.post(
        "/api/admin/metodos-pago/aliados/77357/habilitar",
        headers=headers,
        json={},
    )
    assert hab.status_code == 200
    body = hab.get_json()
    assert body.get("status") == "success"
    assert body.get("aliado_codigo") == "77357"

    listed = client.get("/api/admin/metodos-pago/aliados", headers=headers)
    assert listed.status_code == 200
    aliados = listed.get_json()["aliados"]
    assert any(a["aliado_codigo"] == "77357" for a in aliados)

    listed_otra_vez = client.get("/api/admin/metodos-pago/aliados", headers=headers)
    assert any(a["aliado_codigo"] == "77357" for a in listed_otra_vez.get_json()["aliados"])

    visible = client.get("/api/metodos-pago", headers=session_headers("aliado", "77357"))
    assert visible.status_code == 200
    metodos = visible.get_json()["metodos"]
    assert metodos["habilitado"] is True
    assert metodos["iban"] == _IBAN_FAKE
    assert metodos["bizum_num"] == _BIZUM_FAKE

    assert _count_rows(sqlite_db, "contactos_ruana") == contactos_antes
    assert _count_rows(sqlite_db, "ingresos_ruana") == ingresos_antes


def test_habilitar_codigo_inexistente_es_404(client, sqlite_db, session_headers):
    sqlite_db.actualizar_metodos_pago_ruana(
        {"bizum_num": _BIZUM_FAKE, "iban": _IBAN_FAKE},
        admin_codigo="ADMIN001",
    )
    resp = client.post(
        "/api/admin/metodos-pago/aliados/99999/habilitar",
        headers=_admin_headers(session_headers),
        json={},
    )
    assert resp.status_code == 404
    data = resp.get_json()
    assert data.get("status") == "error"
    assert data.get("code") == "aliado_no_encontrado"


def test_deshabilitar_oculta_pago_manual_al_aliado(client, sqlite_db, session_headers):
    sqlite_db.actualizar_metodos_pago_ruana(
        {"bizum_num": _BIZUM_FAKE, "iban": _IBAN_FAKE},
        admin_codigo="ADMIN001",
    )
    headers = _admin_headers(session_headers)
    hab = client.post(
        "/api/admin/metodos-pago/aliados/77357/habilitar",
        headers=headers,
        json={},
    )
    assert hab.status_code == 200
    visible = client.get("/api/metodos-pago", headers=session_headers("aliado", "77357"))
    assert visible.get_json()["metodos"]["habilitado"] is True

    des = client.post(
        "/api/admin/metodos-pago/aliados/77357/deshabilitar",
        headers=headers,
        json={},
    )
    assert des.status_code == 200
    oculto = client.get("/api/metodos-pago", headers=session_headers("aliado", "77357"))
    metodos = oculto.get_json()["metodos"]
    assert metodos["habilitado"] is False
    assert metodos["iban"] is None
    assert metodos["bizum_num"] is None


def test_admin_guardar_metodos_pago_persiste_en_get(client, sqlite_db, session_headers):
    headers = _admin_headers(session_headers)
    post = client.post(
        "/api/admin/metodos-pago",
        headers=headers,
        json={"bizum_num": _BIZUM_FAKE, "iban": _IBAN_FAKE},
    )
    assert post.status_code == 200
    body = post.get_json()
    assert body["status"] == "success"
    assert body["metodos"]["bizum_num"] == _BIZUM_FAKE
    assert body["metodos"]["iban"] == _IBAN_FAKE

    get = client.get("/api/admin/metodos-pago", headers=headers)
    assert get.status_code == 200
    metodos = get.get_json()["metodos"]
    assert metodos["bizum_num"] == _BIZUM_FAKE
    assert metodos["iban"] == _IBAN_FAKE


def test_admin_metodos_pago_iban_invalido_es_400(client, sqlite_db, session_headers):
    headers = _admin_headers(session_headers)
    resp = client.post(
        "/api/admin/metodos-pago",
        headers=headers,
        json={"bizum_num": _BIZUM_FAKE, "iban": "ES12"},
    )
    assert resp.status_code == 400
    assert resp.get_json()["status"] == "error"
    get = client.get("/api/admin/metodos-pago", headers=headers)
    assert get.status_code == 200
    assert get.get_json()["metodos"]["iban"] is None
    assert get.get_json()["metodos"]["bizum_num"] is None


def test_admin_metodos_pago_sin_sesion_es_401(client):
    r_get = client.get("/api/admin/metodos-pago")
    r_post = client.post(
        "/api/admin/metodos-pago",
        json={"bizum_num": _BIZUM_FAKE, "iban": _IBAN_FAKE},
    )
    assert r_get.status_code == 401
    assert r_post.status_code == 401
    assert r_get.get_json()["status"] == "error"
    assert r_post.get_json()["status"] == "error"


def test_admin_metodos_pago_solo_lectura_es_403(client, sqlite_db, session_headers):
    resp = client.post(
        "/api/admin/metodos-pago",
        headers=_admin_headers(session_headers, escritura=False),
        json={"bizum_num": _BIZUM_FAKE, "iban": _IBAN_FAKE},
    )
    assert resp.status_code == 403
    data = resp.get_json()
    assert data["status"] == "error"
    get = client.get("/api/admin/metodos-pago", headers=_admin_headers(session_headers, escritura=False))
    assert get.status_code == 200
    assert get.get_json()["metodos"]["iban"] is None


def test_metodos_pago_persisten_en_nueva_conexion_bd(sqlite_db):
    sqlite_db.actualizar_metodos_pago_ruana(
        {"bizum_num": _BIZUM_FAKE, "iban": _IBAN_FAKE},
        admin_codigo="ADMIN001",
    )
    db2 = db_module.DBManager(sqlite_db.db_path)
    cfg = db2.obtener_config_pago_manual()
    assert cfg["bizum_num"] == _BIZUM_FAKE
    assert cfg["iban"] == _IBAN_FAKE


def test_guardar_metodos_pago_persiste_aunque_falle_evento(sqlite_db, monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("eventos_sistema no disponible")

    monkeypatch.setattr(sqlite_db, "registrar_evento_sistema", boom)
    monkeypatch.setattr(sqlite_db, "_insert_evento_sistema", boom)
    result = sqlite_db.actualizar_metodos_pago_ruana(
        {"bizum_num": _BIZUM_FAKE, "iban": _IBAN_FAKE},
        admin_codigo="ADMIN001",
    )
    assert result["status"] == "success"
    cfg = sqlite_db.obtener_config_pago_manual()
    assert cfg["bizum_num"] == _BIZUM_FAKE
    assert cfg["iban"] == _IBAN_FAKE


def test_get_admin_metodos_pago_error_es_500_visible(client, sqlite_db, session_headers, monkeypatch):
    from core.services import pago_service

    def boom(*_args, **_kwargs):
        raise RuntimeError("tabla rota")

    monkeypatch.setattr(pago_service._repo, "select_metodos_pago_manual", boom)
    resp = client.get("/api/admin/metodos-pago", headers=_admin_headers(session_headers))
    assert resp.status_code == 500
    data = resp.get_json()
    assert data["status"] == "error"
    assert "tabla rota" in (data.get("message") or "")


def test_allowlist_tras_guardar_http_habilita_solo_aliado_incluido(
    client, sqlite_db, session_headers
):
    headers = _admin_headers(session_headers)
    post = client.post(
        "/api/admin/metodos-pago",
        headers=headers,
        json={"bizum_num": _BIZUM_FAKE, "iban": _IBAN_FAKE},
    )
    assert post.status_code == 200
    hab = client.post(
        "/api/admin/metodos-pago/aliados/A0001/habilitar",
        headers=headers,
        json={},
    )
    assert hab.status_code == 200
    visible = client.get("/api/metodos-pago", headers=session_headers("aliado", "A0001"))
    assert visible.status_code == 200
    metodos = visible.get_json()["metodos"]
    assert metodos["habilitado"] is True
    assert metodos["iban"] == _IBAN_FAKE
    assert metodos["bizum_num"] == _BIZUM_FAKE
    oculto = client.get("/api/metodos-pago", headers=session_headers("aliado", "77357"))
    assert oculto.status_code == 200
    metodos_ocultos = oculto.get_json()["metodos"]
    assert metodos_ocultos["habilitado"] is False
    assert metodos_ocultos["iban"] is None
    assert metodos_ocultos["bizum_num"] is None


def test_get_elige_fila_con_datos_aunque_la_primera_este_vacia(sqlite_db):
    conn = sqlite_db._connect()
    conn.execute(
        "INSERT INTO ruana_metodos_pago_manual (bizum_num, iban) VALUES (?, ?)",
        (None, None),
    )
    conn.execute(
        "INSERT INTO ruana_metodos_pago_manual (bizum_num, iban) VALUES (?, ?)",
        (_BIZUM_FAKE, _IBAN_FAKE),
    )
    conn.commit()
    conn.close()
    cfg = sqlite_db.obtener_config_pago_manual()
    assert cfg["bizum_num"] == _BIZUM_FAKE
    assert cfg["iban"] == _IBAN_FAKE


def test_guardar_metodos_pago_actualiza_todas_las_filas(sqlite_db):
    conn = sqlite_db._connect()
    conn.execute(
        "INSERT INTO ruana_metodos_pago_manual (bizum_num, iban) VALUES (?, ?)",
        (None, None),
    )
    conn.execute(
        "INSERT INTO ruana_metodos_pago_manual (bizum_num, iban) VALUES (?, ?)",
        ("600111222", _IBAN_FAKE),
    )
    conn.commit()
    conn.close()
    result = sqlite_db.actualizar_metodos_pago_ruana(
        {"bizum_num": _BIZUM_FAKE, "iban": _IBAN_FAKE},
        admin_codigo="ADMIN001",
    )
    assert result["status"] == "success"
    conn = sqlite_db._connect()
    rows = conn.execute(
        "SELECT bizum_num FROM ruana_metodos_pago_manual ORDER BY id"
    ).fetchall()
    conn.close()
    assert [r[0] for r in rows] == [_BIZUM_FAKE, _BIZUM_FAKE]


def test_guardar_metodos_pago_error_si_relectura_vacia(sqlite_db, monkeypatch):
    from core.services import pago_service

    monkeypatch.setattr(
        pago_service,
        "obtener_config_pago_manual",
        lambda _db: {"bizum_num": None, "iban": None, "qr_revolut_path": None},
    )
    result = sqlite_db.actualizar_metodos_pago_ruana(
        {"bizum_num": _BIZUM_FAKE, "iban": _IBAN_FAKE},
        admin_codigo="ADMIN001",
    )
    assert result["status"] == "error"
    assert result.get("http_status") == 500


def test_fila_metodos_pago_lee_claves_alias():
    from core.postgres_compat import CompatRow
    from core.services import pago_service

    row = CompatRow(
        {"ruana_metodos_pago_manual.bizum_num": _BIZUM_FAKE, "IBAN": _IBAN_FAKE, "qr": None},
        ["ruana_metodos_pago_manual.bizum_num", "IBAN", "qr"],
    )
    datos = pago_service._fila_metodos_pago(row)
    assert datos["bizum_num"] == _BIZUM_FAKE
    assert datos["iban"] == _IBAN_FAKE


def test_admin_guardar_solo_bizum_persiste(client, sqlite_db, session_headers):
    headers = _admin_headers(session_headers)
    post = client.post(
        "/api/admin/metodos-pago",
        headers=headers,
        json={"bizum_num": _BIZUM_FAKE},
    )
    assert post.status_code == 200
    metodos = post.get_json()["metodos"]
    assert metodos["bizum_num"] == _BIZUM_FAKE
    assert metodos["iban"] is None
    get = client.get("/api/admin/metodos-pago", headers=headers)
    assert get.get_json()["metodos"]["bizum_num"] == _BIZUM_FAKE
    assert get.get_json()["metodos"]["iban"] is None


def test_admin_guardar_solo_iban_persiste(client, sqlite_db, session_headers):
    headers = _admin_headers(session_headers)
    post = client.post(
        "/api/admin/metodos-pago",
        headers=headers,
        json={"iban": _IBAN_FAKE},
    )
    assert post.status_code == 200
    metodos = post.get_json()["metodos"]
    assert metodos["iban"] == _IBAN_FAKE
    assert metodos["bizum_num"] is None
    get = client.get("/api/admin/metodos-pago", headers=headers)
    assert get.get_json()["metodos"]["iban"] == _IBAN_FAKE
    assert get.get_json()["metodos"]["bizum_num"] is None


def test_admin_guardar_iban_conserva_bizum_previo(client, sqlite_db, session_headers):
    headers = _admin_headers(session_headers)
    client.post(
        "/api/admin/metodos-pago",
        headers=headers,
        json={"bizum_num": _BIZUM_FAKE},
    )
    post = client.post(
        "/api/admin/metodos-pago",
        headers=headers,
        json={"iban": _IBAN_FAKE},
    )
    assert post.status_code == 200
    metodos = post.get_json()["metodos"]
    assert metodos["bizum_num"] == _BIZUM_FAKE
    assert metodos["iban"] == _IBAN_FAKE


def test_admin_guardar_solo_qr_persiste(sqlite_db):
    result = sqlite_db.actualizar_metodos_pago_ruana(
        {"qr_revolut_path": "https://storage.example/metodos/revolut.png"},
        admin_codigo="ADMIN001",
    )
    assert result["status"] == "success"
    cfg = sqlite_db.obtener_config_pago_manual()
    assert cfg["qr_revolut_path"] == "https://storage.example/metodos/revolut.png"
    assert cfg["bizum_num"] is None
    assert cfg["iban"] is None


def test_habilitar_con_solo_qr(client, sqlite_db, session_headers):
    sqlite_db.actualizar_metodos_pago_ruana(
        {"qr_revolut_path": "https://storage.example/metodos/revolut.png"},
        admin_codigo="ADMIN001",
    )
    resp = client.post(
        "/api/admin/metodos-pago/aliados/A0001/habilitar",
        headers=_admin_headers(session_headers),
        json={},
    )
    assert resp.status_code == 200
    visible = client.get("/api/metodos-pago", headers=session_headers("aliado", "A0001"))
    assert visible.get_json()["metodos"]["habilitado"] is True
    assert visible.get_json()["metodos"]["qr_revolut_path"] == "https://storage.example/metodos/revolut.png"
    assert visible.get_json()["metodos"]["iban"] is None
    assert visible.get_json()["metodos"]["bizum_num"] is None
