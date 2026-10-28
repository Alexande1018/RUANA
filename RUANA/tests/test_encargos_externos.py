"""Encargos externos («Encargo de RUANA»): permisos, transiciones, sin cobro ni puntos."""

from types import SimpleNamespace

import pytest

from core import db_manager as db_module
from core.services import encargo_externo_service as svc
from RUANA.web import app as app_module

ADMIN_W = ["leer", "escribir"]


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    db = db_module.DBManager(str(tmp_path / "ruana_encargos_ext.db"))
    conn = db._connect()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO grupos (nombre, codigo_postal, estado) VALUES (?, ?, ?)",
        ("Grupo Alcobendas", "28100", "activo"),
    )
    gid = cur.lastrowid
    for codigo, nombre, estado in (
        ("40243", "Daniel", "activo"),
        ("50001", "Otra", "activo"),
        ("60001", "Baja", "inactivo"),
    ):
        cur.execute(
            """
            INSERT INTO aliados (codigo, nombre, oficio, codigo_postal, grupo_id, estado, email, score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (codigo, nombre, "Electricidad", "28100", gid, estado, f"{codigo}@example.com", 100),
        )
    conn.commit()
    conn.close()
    monkeypatch.setattr(app_module, "get_db", lambda: db)
    return db


@pytest.fixture
def sin_email(monkeypatch):
    enviados = []
    monkeypatch.setattr(
        svc, "_enviar_email_aliado", lambda email, nombre, enc: enviados.append((email, enc["id"])) or True
    )
    return enviados


@pytest.fixture
def client():
    return app_module.app.test_client()


def _payload(**extra):
    base = {
        "aliado_codigo": "40243",
        "cliente_nombre": "Lucía Pérez",
        "cliente_telefono": "+34 612 345 678",
        "codigo_postal": "28100",
        "descripcion": "Cambiar enchufes del salón",
        "origen_anuncio": "Meta Alcobendas oct",
        "precio_orientativo": "80",
    }
    base.update(extra)
    return base


def _crear(client, session_headers, **extra):
    return client.post(
        "/api/admin/encargos-externos",
        json=_payload(**extra),
        headers=session_headers("admin", "ADMIN", ADMIN_W),
    )


def _score(db, codigo):
    conn = db._connect()
    cur = conn.cursor()
    cur.execute("SELECT score FROM aliados WHERE codigo = ?", (codigo,))
    v = cur.fetchone()[0]
    conn.close()
    return v


# --- Permisos -----------------------------------------------------------------

def test_crear_requiere_admin(client, sqlite_db, session_headers, sin_email):
    r = client.post("/api/admin/encargos-externos", json=_payload())
    assert r.status_code == 401
    r = client.post(
        "/api/admin/encargos-externos", json=_payload(), headers=session_headers("aliado", "40243")
    )
    assert r.status_code == 401
    assert sin_email == []


def test_crear_requiere_permiso_escritura(client, sqlite_db, session_headers, sin_email):
    r = client.post(
        "/api/admin/encargos-externos",
        json=_payload(),
        headers=session_headers("admin", "LECTOR", ["leer"]),
    )
    assert r.status_code == 403


def test_listado_admin_requiere_admin(client, sqlite_db, session_headers):
    assert client.get("/api/admin/encargos-externos").status_code == 401
    r = client.get("/api/admin/encargos-externos", headers=session_headers("aliado", "40243"))
    assert r.status_code == 401


def test_aliado_requiere_sesion(client, sqlite_db):
    assert client.get("/api/encargos-externos").status_code == 401
    assert client.post("/api/encargos-externos/1/aceptar").status_code == 401


# --- Alta y validación ---------------------------------------------------------

def test_admin_crea_encargo_y_avisa(client, sqlite_db, session_headers, sin_email):
    r = _crear(client, session_headers)
    assert r.status_code == 201, r.get_json()
    data = r.get_json()
    enc = data["encargo"]
    assert enc["estado"] == "creado"
    assert enc["aliado_codigo"] == "40243"
    assert enc["comision_activada"] == 0
    assert float(enc["comision_pct"]) == 5.0
    assert enc["creado_por"] == "ADMIN"
    assert data["notificacion"] == {"app": True, "email": True}
    assert sin_email == [("40243@example.com", enc["id"])]
    from core.services import notificacion_service

    notifs = notificacion_service.listar_notificaciones_aliado(sqlite_db, "40243")
    assert any(n.get("tipo") == svc.TIPO_NOTIFICACION for n in notifs)


@pytest.mark.parametrize(
    "extra,mensaje",
    [
        ({"cliente_telefono": "", "cliente_email": ""}, "teléfono o un email"),
        ({"cliente_nombre": ""}, "nombre"),
        ({"codigo_postal": "281"}, "código postal"),
        ({"descripcion": " "}, "Describe"),
        ({"cliente_email": "malo", "cliente_telefono": ""}, "email"),
        ({"precio_orientativo": "abc"}, "precio"),
    ],
)
def test_validacion(client, sqlite_db, session_headers, sin_email, extra, mensaje):
    r = _crear(client, session_headers, **extra)
    assert r.status_code == 400
    assert mensaje in r.get_json()["error"]
    assert sin_email == []


def test_solo_email_vale(client, sqlite_db, session_headers, sin_email):
    r = _crear(client, session_headers, cliente_telefono="", cliente_email="lucia@example.com",
               precio_orientativo="")
    assert r.status_code == 201
    assert r.get_json()["encargo"]["precio_orientativo"] is None


def test_aliado_inexistente_o_inactivo(client, sqlite_db, session_headers, sin_email):
    assert _crear(client, session_headers, aliado_codigo="99999").status_code == 404
    assert _crear(client, session_headers, aliado_codigo="60001").status_code == 400
    assert sin_email == []


def test_fallo_de_aviso_no_rompe_el_alta(client, sqlite_db, session_headers, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("smtp caído")

    monkeypatch.setattr(svc, "_enviar_email_aliado", boom)
    from core.services import notificacion_service

    monkeypatch.setattr(notificacion_service, "crear_notificacion_aliado", boom)
    r = _crear(client, session_headers)
    assert r.status_code == 201
    assert r.get_json()["notificacion"] == {"app": False, "email": False}


def test_email_sin_smtp_no_falla(sqlite_db, monkeypatch):
    from core import email_service

    monkeypatch.setattr(email_service, "_smtp_configurado", lambda: False)
    assert svc._enviar_email_aliado("a@b.com", "Daniel", {"id": 1}) is False


# --- Vista del aliado y transiciones -----------------------------------------

def test_aliado_ve_solo_los_suyos(client, sqlite_db, session_headers, sin_email):
    _crear(client, session_headers)
    _crear(client, session_headers, aliado_codigo="50001")
    r = client.get("/api/encargos-externos", headers=session_headers("aliado", "40243"))
    assert r.status_code == 200
    encargos = r.get_json()["encargos"]
    assert len(encargos) == 1
    e = encargos[0]
    assert e["cliente_nombre"] == "Lucía Pérez"
    assert e["cliente_telefono"] == "+34612345678"
    assert "creado_por" not in e and "comision_pct" not in e


def test_transiciones_validas(client, sqlite_db, session_headers, sin_email):
    eid = _crear(client, session_headers).get_json()["encargo"]["id"]
    h = session_headers("aliado", "40243")
    # No se puede marcar hecho sin aceptar.
    assert client.post(f"/api/encargos-externos/{eid}/hecho", headers=h).status_code == 409
    r = client.post(f"/api/encargos-externos/{eid}/aceptar", headers=h)
    assert r.status_code == 200 and r.get_json()["encargo"]["estado"] == "aceptado"
    assert r.get_json()["encargo"]["aceptado_at"]
    # Ya aceptado: no se puede rechazar ni volver a aceptar.
    assert client.post(f"/api/encargos-externos/{eid}/rechazar", headers=h).status_code == 409
    assert client.post(f"/api/encargos-externos/{eid}/aceptar", headers=h).status_code == 409
    r = client.post(f"/api/encargos-externos/{eid}/hecho", headers=h)
    assert r.status_code == 200 and r.get_json()["encargo"]["estado"] == "hecho"
    assert client.post(f"/api/encargos-externos/{eid}/aceptar", headers=h).status_code == 409


def test_rechazo_con_motivo_y_final(client, sqlite_db, session_headers, sin_email):
    eid = _crear(client, session_headers).get_json()["encargo"]["id"]
    h = session_headers("aliado", "40243")
    r = client.post(f"/api/encargos-externos/{eid}/rechazar", json={"motivo": "Estoy lleno"}, headers=h)
    assert r.status_code == 200
    enc = r.get_json()["encargo"]
    assert enc["estado"] == "rechazado" and enc["motivo_rechazo"] == "Estoy lleno"
    assert client.post(f"/api/encargos-externos/{eid}/aceptar", headers=h).status_code == 409
    assert client.post(f"/api/encargos-externos/{eid}/hecho", headers=h).status_code == 409


def test_solo_el_aliado_asignado(client, sqlite_db, session_headers, sin_email):
    eid = _crear(client, session_headers).get_json()["encargo"]["id"]
    otro = session_headers("aliado", "50001")
    assert client.post(f"/api/encargos-externos/{eid}/aceptar", headers=otro).status_code == 403
    assert client.post("/api/encargos-externos/9999/aceptar", headers=otro).status_code == 404
    h = session_headers("aliado", "40243")
    assert client.post(f"/api/encargos-externos/{eid}/borrar", headers=h).status_code == 400


# --- Admin: listado y conteos ---------------------------------------------------

def test_admin_lista_con_conteos(client, sqlite_db, session_headers, sin_email):
    ids = [_crear(client, session_headers).get_json()["encargo"]["id"] for _ in range(4)]
    h = session_headers("aliado", "40243")
    client.post(f"/api/encargos-externos/{ids[0]}/aceptar", headers=h)
    client.post(f"/api/encargos-externos/{ids[1]}/aceptar", headers=h)
    client.post(f"/api/encargos-externos/{ids[1]}/hecho", headers=h)
    client.post(f"/api/encargos-externos/{ids[2]}/rechazar", headers=h)
    r = client.get("/api/admin/encargos-externos", headers=session_headers("admin", "ADMIN", ["leer"]))
    assert r.status_code == 200
    data = r.get_json()
    assert data["conteos"] == {"creado": 1, "aceptado": 1, "hecho": 1, "rechazado": 1}
    assert data["total"] == 4
    assert data["comision_activada"] is False
    assert data["encargos"][0]["aliado_nombre"] == "Daniel"
    assert data["encargos"][0]["origen_anuncio"] == "Meta Alcobendas oct"
    r = client.get("/api/admin/encargos-externos?estado=hecho", headers=session_headers("admin", "ADMIN", ["leer"]))
    assert [e["id"] for e in r.get_json()["encargos"]] == [ids[1]]
    r = client.get("/api/admin/encargos-externos?estado=xx", headers=session_headers("admin", "ADMIN", ["leer"]))
    assert r.status_code == 400


# --- Sin puntos, sin Stripe, comisión apagada --------------------------------

def test_no_suma_puntos_ni_llama_a_stripe(client, sqlite_db, session_headers, sin_email, monkeypatch):
    from core.services import score_service
    import stripe

    def prohibido(*a, **k):
        raise AssertionError("no debe llamarse")

    for nombre in dir(score_service):
        if nombre.startswith(("aplicar", "registrar", "sumar", "ajustar")) and callable(getattr(score_service, nombre)):
            monkeypatch.setattr(score_service, nombre, prohibido)
    for recurso in ("PaymentIntent", "Transfer", "Charge", "checkout"):
        obj = getattr(stripe, recurso, None)
        if obj is not None and hasattr(obj, "create"):
            monkeypatch.setattr(obj, "create", prohibido)

    antes = _score(sqlite_db, "40243")
    eid = _crear(client, session_headers).get_json()["encargo"]["id"]
    h = session_headers("aliado", "40243")
    assert client.post(f"/api/encargos-externos/{eid}/aceptar", headers=h).status_code == 200
    assert client.post(f"/api/encargos-externos/{eid}/hecho", headers=h).status_code == 200
    assert _score(sqlite_db, "40243") == antes

    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ruana_score_movimientos'")
    if cur.fetchone():
        cur.execute("SELECT COUNT(*) FROM ruana_score_movimientos WHERE aliado_codigo = ?", ("40243",))
        assert cur.fetchone()[0] == 0
    conn.close()


def test_servicio_no_importa_stripe_ni_score():
    import inspect

    src = inspect.getsource(svc)
    assert "import stripe" not in src
    assert "stripe_client" not in src
    assert "score_service" not in src


def test_comision_desactivada_por_defecto(monkeypatch):
    enc = {"comision_activada": 1, "comision_pct": 5, "precio_orientativo": 100}
    assert svc.comision_activada() is False
    assert svc.calcular_comision(enc) == 0.0
    monkeypatch.setattr(svc, "COMISION_ENCARGOS_EXTERNOS_ACTIVADA", True)
    assert svc.calcular_comision(enc) == 5.0
    assert svc.calcular_comision({**enc, "comision_activada": 0}) == 0.0


def test_migracion_supabase_existe():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    files = list((root / "supabase" / "migrations").glob("*_encargos_externos.sql"))
    assert files
    sql = files[0].read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS encargos_externos" in sql
    assert "ENABLE ROW LEVEL SECURITY" in sql
    assert "FORCE ROW LEVEL" not in sql
