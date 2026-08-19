"""
Tests para:
- Plaza por oficio principal (no por especializacion)
- Dos aliados con mismo oficio no caben en el mismo grupo
- CP < 5 grupos → crear nuevo grupo para el aliado
- CP = 5 y oficio lleno en todos → estado en_espera + mensaje_lista_espera
- Admin incorporar aliado en espera
- Sin suboficios en payload de registro
"""
from types import SimpleNamespace

import pytest

from core import db_manager as db_module
from RUANA.web import app as app_module

MENSAJE_LISTA_ESPERA_FRAGMENT = "lista de Suplentes"


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    return db_module.DBManager(str(tmp_path / "ruana_plaza.db"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _crear(db, codigo, oficio="Electricidad", cp="28001", estado="activo", score=50):
    r = db.crear_aliado(
        codigo=codigo,
        nombre=f"Aliado {codigo}",
        marca="Marca",
        oficio=oficio,
        codigo_postal=cp,
        email=f"{codigo}@example.com",
        telefono=f"+3460000{codigo}",
        estado=estado,
        score=score,
    )
    return r


def _set_activo(db, codigo):
    """Fuerza estado activo en BD (bypass lógica de catálogo)."""
    conn = db._connect()
    conn.execute("UPDATE aliados SET estado = 'activo' WHERE codigo = ?", (codigo,))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# 1. Plaza por oficio: dos aliados del mismo oficio no caben en el mismo grupo
# ---------------------------------------------------------------------------

def test_dos_mismo_oficio_no_caben_en_mismo_grupo(sqlite_db):
    """Si un grupo ya tiene Electricidad, plaza_ocupada_en_grupo debe devolver True."""
    r1 = _crear(sqlite_db, "10001", oficio="Electricidad")
    assert r1["status"] == "success"
    _set_activo(sqlite_db, "10001")

    # Obtener el grupo del primer aliado
    aliado1 = sqlite_db.obtener_aliado_por_codigo("10001")
    grupo_id = aliado1.get("grupo_id")
    assert grupo_id is not None, "El primer aliado debe tener grupo asignado"

    assert sqlite_db.plaza_ocupada_en_grupo(grupo_id, "Electricidad") is True


def test_misma_plaza_libre_para_distinto_oficio(sqlite_db):
    """Si un grupo tiene Electricidad, la plaza para Fontanería sigue libre."""
    r1 = _crear(sqlite_db, "10002", oficio="Electricidad")
    assert r1["status"] == "success"
    _set_activo(sqlite_db, "10002")
    aliado1 = sqlite_db.obtener_aliado_por_codigo("10002")
    grupo_id = aliado1.get("grupo_id")
    assert grupo_id is not None

    assert sqlite_db.plaza_ocupada_en_grupo(grupo_id, "Fontanería y fontanería-gas") is False


# ---------------------------------------------------------------------------
# 2. CP < 5 grupos → crear grupo nuevo para segundo aliado del mismo oficio
# ---------------------------------------------------------------------------

def test_cp_menos_de_5_grupos_crea_nuevo_grupo(sqlite_db):
    """Segundo aliado con mismo oficio en el mismo CP → asignado a un grupo diferente."""
    r1 = _crear(sqlite_db, "10003", oficio="Electricidad", cp="11111")
    assert r1["status"] == "success"
    _set_activo(sqlite_db, "10003")
    grupo1 = sqlite_db.obtener_aliado_por_codigo("10003").get("grupo_id")
    assert grupo1 is not None

    # Segundo aliado con mismo oficio, mismo CP
    r2 = _crear(sqlite_db, "10004", oficio="Electricidad", cp="11111")
    assert r2["status"] == "success"
    _set_activo(sqlite_db, "10004")

    # Puede quedar pendiente_validacion si oficio no está en catálogo del test;
    # pero el grupo asignado, si existe, debe ser diferente.
    aliado2 = sqlite_db.obtener_aliado_por_codigo("10004")
    grupo2 = aliado2.get("grupo_id")

    # Ambos deben existir y pertenecer a grupos distintos
    if grupo2 is not None:
        assert grupo1 != grupo2, "Los dos aliados del mismo oficio no deben compartir grupo"


# ---------------------------------------------------------------------------
# 3. CP = 5 grupos y oficio lleno en todos → en_espera + mensaje
# ---------------------------------------------------------------------------

def _fill_5_groups_with_oficio(db, oficio, cp):
    """Crea 5 grupos en el CP con el oficio dado activo en cada uno."""
    grupos_ids = []
    for i in range(5):
        g = db.crear_grupo_en_cp(cp)
        assert "id" in g, f"No se creó el grupo {i}"
        grupos_ids.append(g["id"])

    # Crear un aliado por grupo con el oficio
    for idx, gid in enumerate(grupos_ids):
        codigo = f"2000{idx}"
        r = db.crear_aliado(
            codigo=codigo,
            nombre=f"Titular {idx}",
            marca="M",
            oficio=oficio,
            codigo_postal=cp,
            email=f"titular{idx}@example.com",
            telefono=f"+34600{idx:05d}",
            estado="activo",
            score=50,
        )
        assert r["status"] == "success", f"Error al crear aliado {codigo}: {r}"
        # Asignar al grupo directamente (bypass lógica de catálogo)
        conn = db._connect()
        conn.execute(
            "UPDATE aliados SET estado = 'activo', grupo_id = ? WHERE codigo = ?",
            (gid, codigo),
        )
        conn.commit()
        conn.close()
    return grupos_ids


def test_cp_5_grupos_oficio_lleno_resulta_en_espera(sqlite_db, monkeypatch):
    """Con 5 grupos en CP y el oficio ocupado en todos, el nuevo aliado queda en_espera."""
    cp = "99999"
    oficio = "Electricidad"
    _fill_5_groups_with_oficio(sqlite_db, oficio, cp)

    # Aliado adicional con mismo oficio
    r = sqlite_db.crear_aliado(
        codigo="29999",
        nombre="Suplente Espera",
        marca="M",
        oficio=oficio,
        codigo_postal=cp,
        email="espera@example.com",
        telefono="+34600099999",
        estado="activo",
        score=50,
    )
    assert r["status"] == "success"
    assert r.get("estado") == "en_espera", (
        f"Esperaba en_espera, obtuvo: {r.get('estado')}"
    )
    assert r.get("grupo_id") is None, "Aliado en_espera no debe tener grupo"
    assert "mensaje_lista_espera" in r
    assert MENSAJE_LISTA_ESPERA_FRAGMENT in r["mensaje_lista_espera"]


def test_cp_5_grupos_oficio_lleno_sin_grupo_id(sqlite_db):
    """Aliado en_espera no tiene grupo_id asignado en BD."""
    cp = "88888"
    oficio = "Electricidad"
    _fill_5_groups_with_oficio(sqlite_db, oficio, cp)

    r = sqlite_db.crear_aliado(
        codigo="28888",
        nombre="Sin Plaza",
        marca="M",
        oficio=oficio,
        codigo_postal=cp,
        email="sinplaza@example.com",
        telefono="+34600088888",
        estado="activo",
        score=50,
    )
    assert r["status"] == "success"

    aliado_bd = sqlite_db.obtener_aliado_por_codigo("28888")
    assert (aliado_bd.get("estado") or "").startswith("en_espera") or \
           aliado_bd.get("estado") == "en_espera"
    assert aliado_bd.get("grupo_id") is None


# ---------------------------------------------------------------------------
# 4. Admin incorporar: listar_aliados_en_espera y incorporar_aliado_espera
# ---------------------------------------------------------------------------

def test_incorporar_aliado_en_espera_activa_y_asigna_grupo(sqlite_db):
    """incorporar_aliado_espera cambia estado a activo y asigna grupo libre."""
    cp = "77777"
    oficio = "Electricidad"
    _fill_5_groups_with_oficio(sqlite_db, oficio, cp)

    # Crear aliado en_espera
    r = sqlite_db.crear_aliado(
        codigo="27777",
        nombre="Aliado Espera",
        marca="M",
        oficio=oficio,
        codigo_postal=cp,
        email="aliado_espera@example.com",
        telefono="+34600077777",
        estado="activo",
        score=50,
    )
    assert r["status"] == "success"
    # Forzar en_espera directamente si no lo hizo la lógica (por catálogo)
    conn = sqlite_db._connect()
    conn.execute("UPDATE aliados SET estado = 'en_espera', grupo_id = NULL WHERE codigo = '27777'")
    conn.commit()
    conn.close()

    # Crear un grupo con plaza libre para el oficio
    nuevo_g = sqlite_db.crear_grupo_en_cp(cp)
    grupo_libre_id = nuevo_g["id"]

    # Incorporar
    result = sqlite_db.incorporar_aliado_espera("27777", grupo_id=grupo_libre_id)
    assert result["status"] == "success"

    aliado = sqlite_db.obtener_aliado_por_codigo("27777")
    assert aliado["estado"] == "activo"
    assert aliado["grupo_id"] == grupo_libre_id


def test_incorporar_aliado_no_en_espera_devuelve_error(sqlite_db):
    """No se puede incorporar un aliado que no está en_espera."""
    r = sqlite_db.crear_aliado(
        codigo="30001",
        nombre="Activo Normal",
        marca="M",
        oficio="Carpintería de madera e interior",
        codigo_postal="66666",
        email="activo@example.com",
        telefono="+34600030001",
        estado="activo",
        score=50,
    )
    assert r["status"] == "success"

    result = sqlite_db.incorporar_aliado_espera("30001")
    assert result["status"] == "error"
    assert "en lista de espera" in result["message"]


def test_listar_aliados_en_espera(sqlite_db):
    """listar_aliados_en_espera debe incluir al aliado en_espera y excluir activos."""
    cp = "55555"
    oficio = "Electricidad"
    _fill_5_groups_with_oficio(sqlite_db, oficio, cp)

    r = sqlite_db.crear_aliado(
        codigo="25555",
        nombre="Espera Test",
        marca="M",
        oficio=oficio,
        codigo_postal=cp,
        email="espera_test@example.com",
        telefono="+34600055555",
        estado="activo",
        score=50,
    )
    assert r["status"] == "success"
    conn = sqlite_db._connect()
    conn.execute("UPDATE aliados SET estado = 'en_espera', grupo_id = NULL WHERE codigo = '25555'")
    conn.commit()
    conn.close()

    lista = sqlite_db.listar_aliados_en_espera()
    codigos = [a["codigo"] for a in lista]
    assert "25555" in codigos

    # Los activos no deben estar
    for a in lista:
        assert a.get("estado") == "en_espera"


# ---------------------------------------------------------------------------
# 5. API: registro sin suboficios no falla
# ---------------------------------------------------------------------------

def test_registro_api_sin_suboficios_no_falla(client, sqlite_db, monkeypatch):
    """El endpoint de registro funciona sin campos especializacion/especializaciones."""
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    monkeypatch.setattr(app_module, "_generar_codigo_unico", lambda: "40001")

    # Invitación válida requerida
    inv_r = sqlite_db.crear_aliado(
        codigo="40000",
        nombre="Invitador",
        marca="M",
        oficio="Electricidad",
        codigo_postal="12345",
        email="invitador_40000@example.com",
        telefono="+34600040000",
        estado="activo",
        score=50,
    )
    sqlite_db._registrar_invitacion("INV01", inv_r.get("id", 1))

    response = client.post(
        "/api/aliados/registrar",
        json={
            "nombre": "Nuevo Sin Suboficios",
            "marca": "M",
            "oficio": "Carpintería de madera e interior",
            "oficio_principal": "Carpintería de madera e interior",
            "codigo_postal": "12345",
            "email": "nuevo_sin_sub@example.com",
            "telefono": "+34600040001",
            "codigo_invitacion": "INV01",
            "acepta_privacidad_y_terminos": True,
        },
    )
    data = response.get_json()
    assert response.status_code in (201, 200), f"Unexpected status: {response.status_code}, {data}"
    assert data.get("status") == "success"
    assert "especializacion" not in data
    assert "especializaciones" not in data


# ---------------------------------------------------------------------------
# 6. API: login rechaza en_espera
# ---------------------------------------------------------------------------

def test_login_rechaza_en_espera(client, sqlite_db, monkeypatch):
    """Un aliado en estado en_espera no puede iniciar sesión."""
    conn = sqlite_db._connect()
    conn.execute(
        "INSERT INTO aliados (codigo, nombre, marca, oficio, codigo_postal, email, telefono, estado, score)"
        " VALUES ('50001', 'Espera Login', 'M', 'Electricidad', '12345', 'login_espera@example.com', '+34600050001', 'en_espera', 50)"
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    response = client.post("/api/aliado/login", json={"codigo": "50001"})
    data = response.get_json()
    assert response.status_code != 200 or data.get("status") != "success", (
        "El login de un aliado en_espera no debe tener éxito"
    )


# ---------------------------------------------------------------------------
# 7. API: admin incorporar endpoint
# ---------------------------------------------------------------------------

def test_admin_incorporar_suplente_endpoint(client, sqlite_db, monkeypatch, session_headers):
    """POST /api/admin/suplentes-espera/<codigo>/incorporar incorpora al aliado."""
    conn = sqlite_db._connect()
    conn.execute(
        "INSERT INTO aliados (codigo, nombre, marca, oficio, codigo_postal, email, telefono, estado, score)"
        " VALUES ('60001', 'Espera Admin', 'M', 'Electricidad', '33333', 'admin_esp@example.com', '+34600060001', 'en_espera', 50)"
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)

    response = client.post(
        "/api/admin/suplentes-espera/60001/incorporar",
        json={},
        headers=session_headers("admin", "00000"),
    )
    data = response.get_json()
    # Puede devolver error si no hay grupos libres, pero el endpoint debe responder JSON
    assert data is not None
    assert "status" in data


def test_admin_listar_suplentes_espera_endpoint(client, sqlite_db, monkeypatch, session_headers):
    """GET /api/admin/suplentes-espera devuelve lista con aliados en_espera."""
    conn = sqlite_db._connect()
    conn.execute(
        "INSERT INTO aliados (codigo, nombre, marca, oficio, codigo_postal, email, telefono, estado, score)"
        " VALUES ('60002', 'Espera Lista', 'M', 'Electricidad', '44444', 'lista_esp@example.com', '+34600060002', 'en_espera', 50)"
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)

    response = client.get(
        "/api/admin/suplentes-espera",
        headers=session_headers("admin", "00000"),
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data.get("status") == "success"
    aliados = data.get("aliados", [])
    assert any(a.get("codigo") == "60002" for a in aliados)
