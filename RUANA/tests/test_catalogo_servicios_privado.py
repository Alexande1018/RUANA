from RUANA.web import app as app_module
from tests.service_forwarders import install_service_db_forwarders


class CatalogoFakeDB:
    def __init__(self):
        self.calls = []

    def guardar_catalogo_servicio_aliado(self, codigo, posicion, descripcion, precio):
        self.calls.append(("guardar", codigo, posicion, descripcion, precio))
        return {
            "status": "success",
            "servicio": {
                "posicion": posicion,
                "descripcion": descripcion,
                "precio": precio,
                "configurado": bool(descripcion and precio),
            },
        }

    def obtener_aliado_por_codigo(self, codigo):
        self.calls.append(("obtener", codigo))
        if codigo == "A0001":
            return {"codigo": "A0001", "nombre": "Aliado Uno"}
        return None

    def listar_catalogo_servicios_aliado(self, codigo):
        self.calls.append(("listar", codigo))
        return [
            {"posicion": i, "descripcion": None, "precio": None, "configurado": False}
            for i in range(1, 11)
        ]


def test_guardar_catalogo_servicio_aliado_ok(client, monkeypatch, session_headers):
    fake_db = CatalogoFakeDB()
    monkeypatch.setattr(app_module, "get_db", lambda: fake_db)
    install_service_db_forwarders(monkeypatch)
    headers = session_headers("aliado", "A0001")

    resp = client.put(
        "/api/aliados/A0001/catalogo-servicios/1",
        headers=headers,
        json={"descripcion": "Instalación eléctrica", "precio": "120 EUR"},
    )

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "success"
    assert data["servicio"]["posicion"] == 1
    assert ("guardar", "A0001", 1, "Instalación eléctrica", "120 EUR") in fake_db.calls


def test_guardar_catalogo_servicio_aliado_forbidden_otro_codigo(client, monkeypatch, session_headers):
    fake_db = CatalogoFakeDB()
    monkeypatch.setattr(app_module, "get_db", lambda: fake_db)
    install_service_db_forwarders(monkeypatch)
    headers = session_headers("aliado", "A0001")

    resp = client.put(
        "/api/aliados/B0002/catalogo-servicios/1",
        headers=headers,
        json={"descripcion": "X", "precio": "Y"},
    )

    assert resp.status_code == 403
    data = resp.get_json()
    assert data["status"] == "error"
    assert "No autorizado" in data["message"]


def test_admin_ver_catalogo_servicios_aliado(client, monkeypatch, session_headers):
    fake_db = CatalogoFakeDB()
    monkeypatch.setattr(app_module, "get_db", lambda: fake_db)
    install_service_db_forwarders(monkeypatch)
    headers = session_headers("admin", "ADMIN001", permisos=["escribir"])

    resp = client.get(
        "/api/admin/aliados/A0001/catalogo-servicios",
        headers=headers,
    )

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "success"
    assert data["codigo"] == "A0001"
    assert isinstance(data["catalogo_servicios"], list)
    assert len(data["catalogo_servicios"]) == 10
