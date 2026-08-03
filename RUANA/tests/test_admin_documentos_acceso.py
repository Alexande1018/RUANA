from RUANA.core import storage_manager


def test_parse_storage_location_from_supabase_public_url():
    url = (
        "https://example.supabase.co/storage/v1/object/public/"
        "ruana-comprobantes/pagos_ruana/12_abc_comprobante.png"
    )
    location = storage_manager.parse_storage_location(url)
    assert location == {
        "kind": "supabase",
        "bucket": "ruana-comprobantes",
        "path": "pagos_ruana/12_abc_comprobante.png",
    }


def test_parse_storage_location_from_legacy_static_upload():
    location = storage_manager.parse_storage_location("/static/uploads/pagos_ruana/1.png")
    assert location == {"kind": "local", "bucket": "", "path": "static/uploads/pagos_ruana/1.png"}


def test_parse_storage_location_rejects_unknown_bucket():
    url = "https://example.supabase.co/storage/v1/object/public/other-bucket/file.png"
    assert storage_manager.parse_storage_location(url) is None


def test_resolve_admin_document_access_url_for_local_file():
    url = storage_manager.resolve_admin_document_access_url("/static/uploads/pagos_ruana/1.png")
    assert url == "/static/uploads/pagos_ruana/1.png"


def test_resolve_admin_document_access_url_uses_signed_url(monkeypatch):
    calls = []

    def fake_signed_url(*, bucket, object_path, expires_in=3600):
        calls.append((bucket, object_path, expires_in))
        return "https://signed.example/doc"

    monkeypatch.setattr(storage_manager, "create_ruana_signed_url", fake_signed_url)

    stored = (
        "https://example.supabase.co/storage/v1/object/public/"
        "ruana-comprobantes/conflictos/9_xyz_prueba.pdf"
    )
    url = storage_manager.resolve_admin_document_access_url(stored)
    assert url == "https://signed.example/doc"
    assert calls == [("ruana-comprobantes", "conflictos/9_xyz_prueba.pdf", 3600)]


def test_admin_documento_acceso_requires_auth(client):
    response = client.get(
        "/api/admin/documentos/acceso",
        query_string={"url": "/static/uploads/pagos_ruana/1.png"},
    )
    assert response.status_code == 401


def test_admin_documento_acceso_returns_signed_url(client, monkeypatch, session_headers):
    from RUANA.web import app as app_module

    monkeypatch.setattr(
        app_module,
        "resolve_admin_document_access_url",
        lambda stored_url: "https://signed.example/comprobante",
    )

    response = client.get(
        "/api/admin/documentos/acceso",
        headers=session_headers("admin", "ADMIN001"),
        query_string={"url": "https://example.supabase.co/storage/v1/object/public/ruana-comprobantes/pagos_ruana/1.png"},
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "success"
    assert data["url"] == "https://signed.example/comprobante"


def test_admin_documento_acceso_rejects_invalid_reference(client, monkeypatch, session_headers):
    from RUANA.web import app as app_module

    monkeypatch.setattr(
        app_module,
        "resolve_admin_document_access_url",
        lambda stored_url: (_ for _ in ()).throw(ValueError("La referencia del documento no es válida.")),
    )

    response = client.get(
        "/api/admin/documentos/acceso",
        headers=session_headers("admin", "ADMIN001"),
        query_string={"url": "https://evil.example/file.png"},
    )

    assert response.status_code == 400
    assert "no es válida" in response.get_json()["message"]
