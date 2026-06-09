from io import BytesIO


class UploadFakeDB:
    def __init__(self):
        self.calls = []

    def subir_comprobante_apoyo_ruana(self, contacto_id, codigo, comprobante_ruta, comentario=None):
        self.calls.append(("subir_comprobante_apoyo_ruana", contacto_id, codigo, comprobante_ruta, comentario))
        return {"status": "success", "contacto_id": contacto_id, "estado_pago": "en_revision"}

    def subir_prueba_conflicto(self, conflict_id, codigo, prueba_url):
        self.calls.append(("subir_prueba_conflicto", conflict_id, codigo, prueba_url))
        return {"status": "success", "conflict_id": conflict_id}


def test_comprobante_apoyo_upload_uses_storage_adapter(client, monkeypatch, session_headers):
    from RUANA.web import app as app_module

    db = UploadFakeDB()
    uploads = []
    monkeypatch.setattr(app_module, "get_db", lambda: db)
    monkeypatch.setattr(
        app_module,
        "upload_ruana_file",
        lambda **kwargs: uploads.append(kwargs) or {
            "url": "https://storage.example/pagos/1.png",
            "bucket": kwargs["bucket"],
            "path": "pagos/1.png",
        },
    )

    response = client.post(
        "/api/contactos/33/comprobante-apoyo",
        headers=session_headers("aliado", "A0001"),
        data={
            "comentario": "pagado",
            "archivo": (BytesIO(b"ok"), "comprobante.png"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert uploads[0]["bucket"] == "ruana-comprobantes"
    assert uploads[0]["folder"] == "pagos_ruana"
    assert uploads[0]["prefix"] == "33"
    assert db.calls == [
        ("subir_comprobante_apoyo_ruana", 33, "A0001", "https://storage.example/pagos/1.png", "pagado")
    ]


def test_comprobante_apoyo_upload_rejects_files_over_2mb(client, monkeypatch, session_headers):
    from RUANA.core.storage_manager import MAX_UPLOAD_BYTES
    from RUANA.web import app as app_module

    db = UploadFakeDB()
    monkeypatch.setattr(app_module, "get_db", lambda: db)

    response = client.post(
        "/api/contactos/33/comprobante-apoyo",
        headers=session_headers("aliado", "A0001"),
        data={"archivo": (BytesIO(b"x" * (MAX_UPLOAD_BYTES + 1)), "grande.png")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    assert "2 MB" in response.get_json()["message"]
    assert db.calls == []


def test_conflict_proof_upload_uses_storage_adapter(client, monkeypatch, session_headers):
    from RUANA.web import app as app_module

    db = UploadFakeDB()
    uploads = []
    monkeypatch.setattr(app_module, "get_db", lambda: db)
    monkeypatch.setattr(
        app_module,
        "upload_ruana_file",
        lambda **kwargs: uploads.append(kwargs) or {
            "url": "https://storage.example/conflictos/9.pdf",
            "bucket": kwargs["bucket"],
            "path": "conflictos/9.pdf",
        },
    )

    response = client.post(
        "/api/conflictos/9/subir-prueba",
        headers=session_headers("aliado", "A0001"),
        data={"archivo": (BytesIO(b"pdf"), "prueba.pdf")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert uploads[0]["bucket"] == "ruana-comprobantes"
    assert uploads[0]["folder"] == "conflictos"
    assert uploads[0]["prefix"] == "9"
    assert db.calls == [("subir_prueba_conflicto", 9, "A0001", "https://storage.example/conflictos/9.pdf")]
