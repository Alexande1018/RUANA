from types import SimpleNamespace

import pytest

from core import db_manager as db_module
from RUANA.web import app as app_module


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    return db_module.DBManager(str(tmp_path / "ruana_metric_estado.db"))


def _session_headers(codigo):
    session_id = app_module._ruana_session_create(
        tipo="aliado",
        codigo=codigo,
        expires_at=9999999999,
    )
    return {app_module.RUANA_SESSION_HEADER: session_id}


def test_registro_con_codigo_suma_referidos_y_queda_activo(client, sqlite_db, monkeypatch):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    sqlite_db.obtener_o_crear_invitador_admin("RUANA-ADMIN")
    invitador = sqlite_db.crear_aliado(
        codigo="11111",
        nombre="Invitador",
        marca="M",
        oficio="Electricidad",
        codigo_postal="28013",
        email="inv@example.com",
        telefono="+34600111111",
        estado="activo",
        score=50,
        especializacion="Averías y reparaciones eléctricas",
    )
    assert invitador["status"] == "success"

    create_inv = client.post(
        "/api/invitaciones/crear",
        headers=_session_headers("11111"),
        json={"zona": "28013"},
    )
    assert create_inv.status_code == 201
    codigo_inv = create_inv.get_json()["codigo"]

    # Especialización sin acentos debe resolverse al catálogo y quedar activo
    register = client.post(
        "/api/aliados/registrar",
        json={
            "nombre": "Ricardo Perez",
            "marca": "RP",
            "oficio": "Fontanería y fontanería-gas",
            "oficio_principal": "Fontanería y fontanería-gas",
            "especializacion": "Reparacion de fugas y grifos",
            "codigo_postal": "28013",
            "email": "ricardo@example.com",
            "telefono": "+34600999888",
            "codigo_invitacion": codigo_inv,
            "acepta_privacidad_y_terminos": True,
        },
    )
    assert register.status_code == 201, register.get_json()
    data = register.get_json()
    assert data["codigo"] != codigo_inv
    assert data.get("estado") == "activo"
    assert len(data["codigo"]) == 5
    assert data["codigo"].isdigit()

    assert sqlite_db.contar_referidos_por_codigo("11111") == 1
    hijos = sqlite_db.listar_hijos_directos_linaje("11111")
    assert len(hijos) == 1
    assert hijos[0]["nombre"] == "Ricardo Perez"

    datos = client.get("/api/aliado/datos", headers=_session_headers("11111"))
    assert datos.status_code == 200
    payload = datos.get_json()
    assert payload["referidos_count"] == 1
    assert payload["aliado"]["referidos_count"] == 1

    listado = sqlite_db.listar_aliados()
    ricardo = next(a for a in listado if a.get("nombre") == "Ricardo Perez")
    assert ricardo["estado"] == "activo"
    assert ricardo["estado_panel"] == "activos"
    assert ricardo["invitado_por_codigo"] == "11111"


def test_oficio_fuera_catalogo_va_a_pendiente_validacion_no_observacion(sqlite_db):
    sqlite_db.obtener_o_crear_invitador_admin("RUANA-ADMIN")
    result = sqlite_db.crear_aliado(
        codigo="22222",
        nombre="Oficio Raro",
        marca="OR",
        oficio="Alienigena espacial",
        codigo_postal="28013",
        email="raro@example.com",
        telefono="+34600222222",
        estado="activo",
        score=50,
    )
    assert result["status"] == "success"
    assert result.get("estado") == "pendiente_validacion"

    item = next(a for a in sqlite_db.listar_aliados() if a["codigo"] == "22222")
    assert item["estado"] == "pendiente_validacion"
    assert item["estado_panel"] == "pendientes"


def test_registrar_invitacion_no_falla_en_silencio(sqlite_db):
    invitador = sqlite_db.crear_aliado(
        codigo="33333",
        nombre="Inv",
        marca="I",
        oficio="Electricidad",
        codigo_postal="28013",
        email="i3@example.com",
        telefono="+34600333333",
        estado="activo",
        score=70,
        especializacion="Averías y reparaciones eléctricas",
    )
    assert invitador["status"] == "success"
    sqlite_db._registrar_invitacion("55555", invitador["id"])
    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT invitador_aliado_id, usado FROM invitaciones WHERE codigo = ?",
        ("55555",),
    )
    row = cur.fetchone()
    conn.close()
    assert row is not None
    assert int(row[0]) == int(invitador["id"])
    assert int(row[1]) == 0
