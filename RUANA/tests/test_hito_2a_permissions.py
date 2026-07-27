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


def test_crear_invitacion_rejects_admin_session_without_touching_db(client, fake_db, session_headers):
    headers = session_headers("admin", "ADMIN001", permisos=["leer", "escribir"])

    response = client.post(
        "/api/invitaciones/crear",
        json={"zona": "08001", "aliado_id": 999},
        headers=headers,
    )

    assert response.status_code == 401
    assert fake_db.calls == []


def test_finalizar_competencia_rejects_read_only_admin_without_touching_db(client, fake_db, session_headers):
    headers = session_headers("admin", "0000", permisos=["leer"])

    response = client.post("/api/competencia/finalizar-vencidas", headers=headers)

    assert response.status_code == 403
    assert fake_db.calls == []


def test_purga_mensual_rejects_read_only_admin_without_touching_db(client, fake_db, session_headers):
    headers = session_headers("admin", "0000", permisos=["leer"])

    response = client.post("/api/purga/mensual", headers=headers)

    assert response.status_code == 403
    assert fake_db.calls == []


def test_finalizar_competencia_rejects_aliado_session_without_touching_db(client, fake_db, session_headers):
    headers = session_headers("aliado", "A0001")

    response = client.post("/api/competencia/finalizar-vencidas", headers=headers)

    assert response.status_code == 401
    assert fake_db.calls == []


def test_purga_mensual_rejects_aliado_session_without_touching_db(client, fake_db, session_headers):
    headers = session_headers("aliado", "A0001")

    response = client.post("/api/purga/mensual", headers=headers)

    assert response.status_code == 401
    assert fake_db.calls == []


def test_crear_invitacion_authenticated_aliado_uses_session_inviter(client, fake_db, session_headers):
    headers = session_headers("aliado", "A0001")

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
    registrar_calls = [call for call in fake_db.calls if call[0] == "_registrar_invitacion"]
    assert len(registrar_calls) == 1
    assert registrar_calls[0][2] == 42


def test_crear_invitacion_with_solicitud_uses_session_scoped_attendance(client, fake_db, session_headers):
    headers = session_headers("aliado", "A0001")

    response = client.post(
        "/api/invitaciones/crear",
        json={"zona": "08001", "solicitud_id": 456},
        headers=headers,
    )

    assert response.status_code == 201
    assert ("atender_solicitud_por_id", 456, "A0001") in fake_db.calls
    assert all(call[0] != "marcar_solicitud_contestada" for call in fake_db.calls)


def test_crear_invitacion_rejects_pending_aliado_without_writes(client, fake_db, session_headers):
    fake_db.aliado_estado = "pendiente_completar"
    headers = session_headers("aliado", "A0001")

    response = client.post(
        "/api/invitaciones/crear",
        json={"zona": "08001"},
        headers=headers,
    )

    assert response.status_code == 403
    data = response.get_json()
    assert data["status"] == "error"
    assert data["message"] == "Aliado no autorizado para crear invitaciones"
    assert ("obtener_aliado_por_codigo", "A0001") in fake_db.calls
    assert all(call[0] != "crear_aliado" for call in fake_db.calls)
    assert all(call[0] != "_registrar_invitacion" for call in fake_db.calls)


def test_admin_crear_invitacion_rejects_read_only_admin_without_writes(client, fake_db, session_headers):
    headers = session_headers("admin", "0000", permisos=["leer"])

    response = client.post(
        "/api/admin/invitaciones/crear",
        json={"zona": "08001"},
        headers=headers,
    )

    assert response.status_code == 403
    assert fake_db.calls == []


def test_admin_crear_invitacion_creates_invitation_without_placeholder(client, fake_db, session_headers):
    headers = session_headers("admin", "ADMIN001", permisos=["leer", "escribir"])

    response = client.post(
        "/api/admin/invitaciones/crear",
        json={"zona": "08001"},
        headers=headers,
    )

    assert response.status_code == 201
    data = response.get_json()
    assert data["status"] == "success"
    assert data["tipo"] == "invitacion_admin"
    assert data["codigo"].isdigit()
    assert len(data["codigo"]) == 5

    crear_calls = [call for call in fake_db.calls if call[0] == "crear_aliado"]
    assert crear_calls == []
    registrar_calls = [call for call in fake_db.calls if call[0] == "_registrar_invitacion"]
    assert len(registrar_calls) == 1
    assert registrar_calls[0][1] == data["codigo"]
    assert registrar_calls[0][2] == 42


def test_finalizar_competencia_allows_write_admin(client, fake_db, session_headers):
    headers = session_headers("admin", "ADMIN001", permisos=["leer", "escribir"])

    response = client.post("/api/competencia/finalizar-vencidas", headers=headers)

    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "success"
    assert data["finalizadas"] == 1
    assert ("finalizar_competencia_activas_vencidas",) in fake_db.calls


def test_purga_mensual_allows_write_admin(client, fake_db, session_headers):
    headers = session_headers("admin", "ADMIN001", permisos=["leer", "escribir"])

    response = client.post("/api/purga/mensual", headers=headers)

    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "success"
    assert data["procesados"] == 1
    assert ("purga_mensual",) in fake_db.calls
