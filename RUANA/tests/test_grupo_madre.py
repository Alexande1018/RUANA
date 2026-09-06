"""
Tests Grupo Madre por ciudad: incubación, madurez, directorio y compatibilidad territorial.
"""
from types import SimpleNamespace

import pytest

from core import db_manager as db_module
from core.db_constants import ESTADOS_ENCARGO_VALIDO_MADUREZ, TIPO_GRUPO_MADRE
from core.repositories.grupo_madre_repo import GrupoMadreRepo
from core.services import grupo_madre_service
from RUANA.web import app as app_module


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    return db_module.DBManager(str(tmp_path / "ruana_grupo_madre.db"))


def _crear(db, codigo, oficio="Electricidad", cp="03001", estado="activo"):
    r = db.crear_aliado(
        codigo=codigo,
        nombre=f"Aliado {codigo}",
        marca="Marca",
        oficio=oficio,
        codigo_postal=cp,
        email=f"{codigo}@example.com",
        telefono=f"+34600{codigo}",
        estado=estado,
        score=50,
    )
    return r


def _set_activo(db, codigo):
    conn = db._connect()
    conn.execute("UPDATE aliados SET estado = 'activo' WHERE codigo = ?", (codigo,))
    conn.commit()
    conn.close()


def _grupo_tipo(db, grupo_id):
    g = db.obtener_grupo_por_id(grupo_id)
    return (g or {}).get("tipo")


def test_cp_sin_territorial_entra_en_grupo_madre(sqlite_db):
    """CP incubación (03001 Alicante) asigna grupo tipo madre."""
    r = _crear(sqlite_db, "50001", cp="03001")
    assert r["status"] == "success"
    _set_activo(sqlite_db, "50001")
    aliado = sqlite_db.obtener_aliado_por_codigo("50001")
    assert aliado.get("grupo_id") is not None
    assert _grupo_tipo(sqlite_db, aliado["grupo_id"]) == TIPO_GRUPO_MADRE


def test_cp_con_territorial_mantiene_flujo_actual(sqlite_db):
    """CP con grupo territorial existente no usa madre."""
    gid = sqlite_db.crear_grupo_en_cp("28001", "Madrid", "Madrid")
    assert isinstance(gid, dict) and gid.get("id")
    r = _crear(sqlite_db, "50002", cp="28001")
    assert r["status"] == "success"
    _set_activo(sqlite_db, "50002")
    aliado = sqlite_db.obtener_aliado_por_codigo("50002")
    assert aliado.get("grupo_id") is not None
    assert _grupo_tipo(sqlite_db, aliado["grupo_id"]) == "territorial"


def test_encargo_iniciado_no_cuenta_madurez_aceptado_si(sqlite_db):
    """Solo encargos desde aceptado cuentan para madurez."""
    _crear(sqlite_db, "51001", cp="03002")
    _crear(sqlite_db, "51002", oficio="Fontanería", cp="03002")
    _set_activo(sqlite_db, "51001")
    _set_activo(sqlite_db, "51002")

    creado = sqlite_db.crear_contacto_ruana("51001", "51002", servicio="Avería", motivo_contacto="Test")
    assert creado["status"] == "success"
    assert creado["estado"] == "iniciado"

    conn = sqlite_db._connect()
    cur = conn.cursor()
    repo = GrupoMadreRepo()
    assert repo.contar_encargos_validos_cp_profesional(cur, "03002") == 0
    conn.close()

    aceptado = sqlite_db.aceptar_contacto_ruana(creado["id"], "51002")
    assert aceptado["status"] == "success"
    assert aceptado["estado"] == "aceptado"

    conn = sqlite_db._connect()
    cur = conn.cursor()
    assert repo.contar_encargos_validos_cp_profesional(cur, "03002") == 1
    conn.close()


def test_estados_encargo_valido_madurez_excluyen_conversacion_previa():
    """La constante no incluye estados previos a aceptado."""
    assert "iniciado" not in ESTADOS_ENCARGO_VALIDO_MADUREZ
    assert "en_conversacion" not in ESTADOS_ENCARGO_VALIDO_MADUREZ
    assert "aceptado" in ESTADOS_ENCARGO_VALIDO_MADUREZ
    assert "trabajo_en_progreso" in ESTADOS_ENCARGO_VALIDO_MADUREZ


def test_directorio_incubacion_incluye_otro_cp_misma_ciudad(sqlite_db):
    """En incubación el directorio muestra aliados del madre aunque tengan otro CP."""
    _crear(sqlite_db, "52001", cp="03001")
    _crear(sqlite_db, "52002", oficio="Fontanería y fontanería-gas", cp="03003")
    _set_activo(sqlite_db, "52001")
    _set_activo(sqlite_db, "52002")

    directorio = sqlite_db.listar_aliados_directorio_grupo("52001")
    codigos = {a["codigo"] for a in directorio}
    assert "52002" in codigos


def test_directorio_territorial_sigue_filtrando_por_cp(sqlite_db):
    """CP territorial mantiene filtro estricto por CP."""
    gid = sqlite_db.crear_grupo_en_cp("28001", "Madrid", "Madrid")
    assert isinstance(gid, dict) and gid.get("id")
    grupo_id = gid["id"]
    _crear(sqlite_db, "53001", cp="28001")
    _crear(sqlite_db, "53002", oficio="Fontanería", cp="28002")
    _set_activo(sqlite_db, "53001")
    _set_activo(sqlite_db, "53002")

    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute("UPDATE aliados SET grupo_id = ? WHERE codigo = '53002'", (grupo_id,))
    conn.commit()
    conn.close()

    directorio = sqlite_db.listar_aliados_directorio_grupo("53001")
    codigos = {a["codigo"] for a in directorio}
    assert "53002" not in codigos


def test_sexto_oficio_mismo_cp_en_madre_va_a_espera(sqlite_db):
    """Máx. 5 CP distintos con el mismo oficio en el madre → en_espera."""
    oficios_cp = [
        ("54001", "03001"),
        ("54002", "03002"),
        ("54003", "03003"),
        ("54004", "03004"),
        ("54005", "03005"),
    ]
    for codigo, cp in oficios_cp:
        r = _crear(sqlite_db, codigo, oficio="Electricidad", cp=cp)
        assert r["status"] == "success"
        _set_activo(sqlite_db, codigo)

    r6 = _crear(sqlite_db, "54006", oficio="Electricidad", cp="03001")
    assert r6["status"] == "success"
    aliado6 = sqlite_db.obtener_aliado_por_codigo("54006")
    assert aliado6["estado"] == "en_espera"


def test_cp_en_modo_territorial_no_cambia_por_madre(sqlite_db):
    """Grupos territoriales existentes no migran al madre."""
    gid = sqlite_db.crear_grupo_en_cp("11111", "Ciudad", "Prov")
    assert isinstance(gid, dict)
    assert grupo_madre_service.cp_en_modo_territorial(sqlite_db, "11111") is True

    r = _crear(sqlite_db, "55001", cp="11111")
    assert r["status"] == "success"
    _set_activo(sqlite_db, "55001")
    aliado = sqlite_db.obtener_aliado_por_codigo("55001")
    assert _grupo_tipo(sqlite_db, aliado["grupo_id"]) == "territorial"


def test_resolver_cp_api(client):
  resp = client.get("/api/territorio/resolver-cp?cp=03001")
  assert resp.status_code == 200
  data = resp.get_json()
  assert data["status"] == "success"
  assert data["resuelto"] is True
  assert data["ciudad"] == "Alicante"


def test_aviso_visto_endpoint(client, sqlite_db, monkeypatch):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    r = _crear(sqlite_db, "56001", cp="03001")
    assert r["status"] == "success"
    _set_activo(sqlite_db, "56001")

    session_id = app_module._ruana_session_create(
        tipo="aliado",
        codigo="56001",
        expires_at=9999999999,
    )
    headers = {app_module.RUANA_SESSION_HEADER: session_id}

    resp = client.post(
        "/api/aliado/grupo-madre/aviso-visto",
        json={"aviso_tipo": "grupo_madre_bienvenida"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.get_json().get("status") == "success"
    assert sqlite_db.debe_mostrar_aviso_madre("56001", r.get("grupo_id")) is False
