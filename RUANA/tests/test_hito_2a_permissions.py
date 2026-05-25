from RUANA.tests.conftest import make_session_headers


def test_crear_invitacion_rejects_anonymous_request_without_touching_db(client, fake_db):
    response = client.post(
        "/api/invitaciones/crear",
        json={"zona": "08001", "aliado_id": 999},
    )

    assert response.status_code == 401
    assert fake_db.calls == []


def test_finalizar_competencia_rejects_anonymous_request_without_touching_db(client, fake_db):
    response = client.post("/api/competencia/finalizar-vencidas")

    assert response.status_code == 401
    assert fake_db.calls == []


def test_purga_mensual_rejects_anonymous_request_without_touching_db(client, fake_db):
    response = client.post("/api/purga/mensual")

    assert response.status_code == 401
    assert fake_db.calls == []


def test_finalizar_competencia_rejects_read_only_admin_without_touching_db(client, fake_db):
    headers = make_session_headers("admin", "0000", permisos=["leer"])

    response = client.post("/api/competencia/finalizar-vencidas", headers=headers)

    assert response.status_code == 403
    assert fake_db.calls == []


def test_purga_mensual_rejects_read_only_admin_without_touching_db(client, fake_db):
    headers = make_session_headers("admin", "0000", permisos=["leer"])

    response = client.post("/api/purga/mensual", headers=headers)

    assert response.status_code == 403
    assert fake_db.calls == []


def test_crear_invitacion_authenticated_aliado_uses_session_inviter(client, fake_db):
    headers = make_session_headers("aliado", "A0001")

    response = client.post(
        "/api/invitaciones/crear",
        json={"zona": "08001", "aliado_id": 999},
        headers=headers,
    )

    assert response.status_code == 201
    data = response.get_json()
    assert data["status"] == "success"
    assert data["tipo"] == "invitacion"
    assert ("obtener_aliado_por_codigo", "A0001") in fake_db.calls
    assert any(call[0] == "_registrar_invitacion" and call[2] == 42 for call in fake_db.calls)


def test_finalizar_competencia_allows_write_admin(client, fake_db):
    headers = make_session_headers("admin", "ADMIN001", permisos=["leer", "escribir"])

    response = client.post("/api/competencia/finalizar-vencidas", headers=headers)

    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "success"
    assert data["finalizadas"] == 1
    assert ("finalizar_competencia_activas_vencidas",) in fake_db.calls


def test_purga_mensual_allows_write_admin(client, fake_db):
    headers = make_session_headers("admin", "ADMIN001", permisos=["leer", "escribir"])

    response = client.post("/api/purga/mensual", headers=headers)

    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "success"
    assert data["procesados"] == 1
    assert ("purga_mensual",) in fake_db.calls
