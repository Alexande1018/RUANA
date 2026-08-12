from io import BytesIO

from tests.service_forwarders import install_service_db_forwarders


class PaymentMethodsFakeDB:
    def __init__(self):
        self.metodos = {
            "bizum_num": "642868261",
            "iban": "ES8915830001119028625152",
            "qr_revolut_path": "https://storage.example/qr/revolut.png",
        }
        self.calls = []

    def obtener_metodos_pago_ruana(self):
        self.calls.append(("obtener_metodos_pago_ruana",))
        return dict(self.metodos)

    def actualizar_metodos_pago_ruana(self, valores, admin_codigo=None):
        self.calls.append(("actualizar_metodos_pago_ruana", valores, admin_codigo))
        self.metodos.update(valores)
        return {"status": "success", "metodos": dict(self.metodos)}


def test_aliado_can_read_payment_methods(client, fake_db, monkeypatch, session_headers):
    from RUANA.web import app as app_module

    db = PaymentMethodsFakeDB()
    monkeypatch.setattr(app_module, "get_db", lambda: db)
    install_service_db_forwarders(monkeypatch)

    response = client.get("/api/metodos-pago", headers=session_headers("aliado", "A0001"))

    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "success"
    assert data["metodos"]["iban"] == "ES8915830001119028625152"
    assert data["metodos"]["qr_revolut_path"] == "https://storage.example/qr/revolut.png"


def test_admin_can_update_payment_methods(client, monkeypatch, session_headers):
    from RUANA.web import app as app_module

    db = PaymentMethodsFakeDB()
    monkeypatch.setattr(app_module, "get_db", lambda: db)
    install_service_db_forwarders(monkeypatch)

    response = client.post(
        "/api/admin/metodos-pago",
        headers=session_headers("admin", "ADMIN001", permisos=["leer", "configurar"]),
        json={
            "bizum_num": "600111222",
            "iban": "ES8915830001119028625152",
        },
    )

    assert response.status_code == 200
    assert db.calls[-1] == (
        "actualizar_metodos_pago_ruana",
        {"bizum_num": "600111222", "iban": "ES8915830001119028625152"},
        "ADMIN001",
    )


def test_admin_qr_upload_updates_revolut_qr_path(client, monkeypatch, session_headers):
    from RUANA.web import app as app_module

    db = PaymentMethodsFakeDB()
    uploads = []
    monkeypatch.setattr(app_module, "get_db", lambda: db)
    install_service_db_forwarders(monkeypatch)
    monkeypatch.setattr(
        app_module,
        "upload_ruana_file",
        lambda **kwargs: uploads.append(kwargs) or {
            "url": "https://storage.example/metodos/revolut.png",
            "bucket": kwargs["bucket"],
            "path": "metodos/revolut.png",
        },
    )

    response = client.post(
        "/api/admin/metodos-pago/qr-revolut",
        headers=session_headers("admin", "ADMIN001", permisos=["leer", "configurar"]),
        data={"archivo": (BytesIO(b"png"), "revolut.png")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert uploads[0]["bucket"] == "ruana-public"
    assert uploads[0]["folder"] == "metodos_pago"
    assert db.calls[-1] == (
        "actualizar_metodos_pago_ruana",
        {"qr_revolut_path": "https://storage.example/metodos/revolut.png"},
        "ADMIN001",
    )
