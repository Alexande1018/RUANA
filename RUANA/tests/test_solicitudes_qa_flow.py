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
    return db_module.DBManager(str(tmp_path / "ruana.db"))


def _crear_grupo_con_aliados(db):
    conn = db._connect()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO grupos (nombre, codigo_postal, estado) VALUES (?, ?, ?)",
        ("Grupo QA Solicitudes", "03014", "activo"),
    )
    grupo_id = cursor.lastrowid
    cursor.execute(
        "INSERT INTO aliados (codigo, nombre, oficio, codigo_postal, grupo_id, estado) VALUES (?, ?, ?, ?, ?, ?)",
        ("QA001", "Aliado que solicita", "Electricidad", "03014", grupo_id, "activo"),
    )
    cursor.execute(
        "INSERT INTO aliados (codigo, nombre, oficio, codigo_postal, grupo_id, estado) VALUES (?, ?, ?, ?, ?, ?)",
        ("QA002", "Aliado que atiende", "Fontaneria", "03014", grupo_id, "activo"),
    )
    conn.commit()
    conn.close()
    return grupo_id


def _get_solicitudes(client, headers):
    response = client.get("/api/solicitudes", headers=headers)
    assert response.status_code == 200
    return response.get_json()


def test_qa_solicitudes_crear_entrantes_propias_e_historial(
    client, sqlite_db, monkeypatch, session_headers
):
    from RUANA.web import app as app_module

    _crear_grupo_con_aliados(sqlite_db)
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    headers_a = session_headers("aliado", "QA001")
    headers_b = session_headers("aliado", "QA002")

    create_response = client.post(
        "/api/solicitudes",
        json={
            "oficio": "Carpinteria",
            "descripcion": "Necesito a alguien para reparar una puerta de cocina",
        },
        headers=headers_a,
    )

    assert create_response.status_code == 200
    solicitud_id = create_response.get_json()["id"]

    vista_a = _get_solicitudes(client, headers_a)
    assert vista_a["entrantes"] == []
    assert [s["id"] for s in vista_a["propias"]] == [solicitud_id]
    assert vista_a["propias"][0]["estado"] == "pendiente"
    assert vista_a["propias"][0]["oficio"] == "Carpinteria"
    assert vista_a["historial"] == []

    vista_b = _get_solicitudes(client, headers_b)
    assert [s["id"] for s in vista_b["entrantes"]] == [solicitud_id]
    assert vista_b["entrantes"][0]["solicitante_codigo"] == "QA001"
    assert vista_b["propias"] == []
    assert vista_b["historial"] == []

    atender_response = client.post(
        f"/api/solicitudes/{solicitud_id}/atender",
        headers=headers_b,
    )
    assert atender_response.status_code == 200

    vista_a_atendida = _get_solicitudes(client, headers_a)
    assert vista_a_atendida["entrantes"] == []
    assert vista_a_atendida["propias"][0]["estado"] == "atendida"
    assert vista_a_atendida["propias"][0]["atendido_por_codigo"] == "QA002"
    assert vista_a_atendida["historial"][0]["estado"] == "atendida"
    assert vista_a_atendida["historial"][0]["atendido_por_nombre"] == "Aliado que atiende"

    vista_b_atendida = _get_solicitudes(client, headers_b)
    assert vista_b_atendida["entrantes"] == []
    assert vista_b_atendida["historial"][0]["estado"] == "atendida"
    assert vista_b_atendida["historial"][0]["atendido_por_codigo"] == "QA002"
