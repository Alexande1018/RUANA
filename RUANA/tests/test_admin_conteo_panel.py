"""El resumen admin y /api/stats cuentan el mismo conjunto de aliados."""

from types import SimpleNamespace

from core import db_manager as db_module
from RUANA.web import app as app_module


def _sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    return db_module.DBManager(str(tmp_path / "ruana_conteo_panel.db"))


def _alta(db, codigo, nombre, estado):
    result = db.crear_aliado(
        codigo=codigo,
        nombre=nombre,
        marca="Marca",
        oficio="Electricidad",
        codigo_postal="28001",
        email=f"{codigo}@example.com",
        telefono=f"+34611{codigo}",
        estado=estado,
        score=50,
    )
    assert result["status"] == "success", result
    return result


def test_resumen_y_stats_cuentan_los_mismos_aliados(
    client, tmp_path, monkeypatch, session_headers
):
    """Un aliado real cuenta. La raíz sistema, el placeholder y el eliminado no.

    Antes el resumen hacía len(listar_aliados()) y, si esa SQL fallaba, devolvía
    0. Otras pantallas hacían COUNT(*) FROM aliados sin filtro y veían 1.
    """
    sqlite_db = _sqlite_db(tmp_path, monkeypatch)
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)

    _alta(sqlite_db, "82001", "Aliado Visible", "activo")
    _alta(sqlite_db, "82002", "Placeholder", "pendiente_completar")
    _alta(sqlite_db, "82003", "Para Borrar", "activo")
    assert sqlite_db.eliminar_perfil_aliado_admin("82003")["status"] == "success"
    assert sqlite_db.obtener_o_crear_invitador_admin("RUANA-ADMIN")

    headers = session_headers("admin", "ADMIN001", permisos=["leer"])

    summary = client.get("/api/admin/dashboard-summary", headers=headers).get_json()
    stats = client.get("/api/stats", headers=headers).get_json()

    assert summary["total_users"] == 1
    assert summary["active_users"] == 1
    assert stats["status"] == "success"
    assert stats["total_aliados"] == summary["total_users"]
    assert stats["aliados_activos"] == summary["active_users"]

    _alta(sqlite_db, "82004", "Pendiente Validacion", "pendiente_validacion")
    summary2 = client.get("/api/admin/dashboard-summary", headers=headers).get_json()
    stats2 = client.get("/api/stats", headers=headers).get_json()
    assert summary2["total_users"] == 2
    assert summary2["active_users"] == 1
    assert stats2["total_aliados"] == 2
    assert stats2["aliados_activos"] == 1
