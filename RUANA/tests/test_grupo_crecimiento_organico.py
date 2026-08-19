"""Tests de crecimiento orgánico de grupos profesionales."""

from types import SimpleNamespace

import pytest

from core import db_manager as db_module
from core.db_constants import (
    CRECIMIENTO_GRUPO_SCORE_DELTA,
    INVITACION_TIPO_CRECIMIENTO_GRUPO,
    SCORE_MOTIVO_ALIADO_INVITADO_REGISTRADO,
)
from core.services import grupo_crecimiento_service
from RUANA.web import app as app_module

OFICIOS_TEST = [
    "Electricidad",
    "Fontanería y fontanería-gas",
    "Carpintería",
    "Pintura",
    "Albañilería",
    "Cerrajería",
    "Climatización",
    "Jardinería",
    "Limpieza",
    "Cristalería",
    "Persianas",
    "Reformas integrales",
]


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    return db_module.DBManager(str(tmp_path / "grupo_crecimiento.db"))


@pytest.fixture
def client():
    return app_module.app.test_client()


def _session_headers(codigo):
    session_id = app_module._ruana_session_create(
        tipo="aliado",
        codigo=codigo,
        expires_at=9999999999,
    )
    return {app_module.RUANA_SESSION_HEADER: session_id}


def _crear_grupo(db, cp="28001"):
    g = db.crear_grupo_en_cp(cp, "Ciudad", "Provincia")
    assert g.get("id")
    return g["id"]


def _insertar_aliado_en_grupo(db, codigo, cp, grupo_id, oficio_idx=0):
    oficio = OFICIOS_TEST[oficio_idx % len(OFICIOS_TEST)]
    conn = db._connect()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO aliados (
            codigo, nombre, marca, oficio, codigo_postal, grupo_id,
            estado, score, email, telefono
        ) VALUES (?, ?, ?, ?, ?, ?, 'activo', 50, ?, ?)
        """,
        (
            codigo,
            f"Aliado {codigo}",
            "M",
            oficio,
            cp,
            grupo_id,
            f"{codigo}@example.com",
            f"+34600{codigo}",
        ),
    )
    conn.commit()
    conn.close()


def _poblar_grupo(db, grupo_id, n_aliados, cp="28001", codigo_base="700"):
    codigos = []
    for i in range(n_aliados):
        codigo = f"{int(codigo_base) + i:05d}"
        _insertar_aliado_en_grupo(db, codigo, cp, grupo_id, oficio_idx=i)
        codigos.append(codigo)
    return codigos


def _reset_movimientos_score_dia(db, codigo):
    """Evita el tope diario ±10 en tests con múltiples recompensas."""
    conn = db._connect()
    cur = conn.cursor()
    cur.execute(
        "UPDATE score_movimientos SET creado_en = datetime('now', '-2 day') "
        "WHERE codigo_aliado = ?",
        (codigo,),
    )
    conn.commit()
    conn.close()


def _crear_invitacion_crecimiento(client, invitador_codigo):
    return client.post(
        "/api/invitaciones/crear",
        headers=_session_headers(invitador_codigo),
        json={"crecimiento_grupo": True},
    )


def _registrar_invitado(client, codigo_inv, codigo_suffix, oficio_idx=0):
    oficio = OFICIOS_TEST[oficio_idx % len(OFICIOS_TEST)]
    return client.post(
        "/api/aliados/registrar",
        json={
            "nombre": f"Invitado {codigo_suffix}",
            "marca": "I",
            "oficio": oficio,
            "oficio_principal": oficio,
            "especializacion": "Servicio invitado",
            "codigo_postal": "28001",
            "email": f"inv{codigo_suffix}@example.com",
            "telefono": f"+34601{codigo_suffix}",
            "codigo_invitacion": codigo_inv,
        },
    )


def _score_invitador(db, codigo):
    aliado = db.obtener_aliado_por_codigo(codigo)
    return int(aliado.get("score") or 0)


def _info_grupo_panel(client, codigo):
    r = client.get("/api/aliado/datos", headers=_session_headers(codigo))
    assert r.status_code == 200
    aliado = r.get_json()["aliado"]
    return aliado.get("grupo_info")


@pytest.mark.parametrize("n_aliados,debe_mostrar", [(5, True), (10, True), (11, False)])
def test_aviso_segun_tamano_grupo(client, sqlite_db, monkeypatch, n_aliados, debe_mostrar):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    sqlite_db.obtener_o_crear_invitador_admin("RUANA-ADMIN")
    grupo_id = _crear_grupo(sqlite_db)
    codigos = _poblar_grupo(sqlite_db, grupo_id, n_aliados)
    info = _info_grupo_panel(client, codigos[0])
    assert info is not None
    assert info.get("en_creacion") is debe_mostrar
    assert info.get("num_aliados") == n_aliados


def test_enviar_invitacion_no_genera_score(client, sqlite_db, monkeypatch):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    sqlite_db.obtener_o_crear_invitador_admin("RUANA-ADMIN")
    grupo_id = _crear_grupo(sqlite_db)
    codigos = _poblar_grupo(sqlite_db, grupo_id, 3, codigo_base="710")
    invitador = codigos[0]
    score_antes = _score_invitador(sqlite_db, invitador)
    r = _crear_invitacion_crecimiento(client, invitador)
    assert r.status_code == 201
    assert r.get_json().get("tipo") == INVITACION_TIPO_CRECIMIENTO_GRUPO
    assert _score_invitador(sqlite_db, invitador) == score_antes


def test_invitado_registrado_otorga_mas5_score(client, sqlite_db, monkeypatch):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    sqlite_db.obtener_o_crear_invitador_admin("RUANA-ADMIN")
    grupo_id = _crear_grupo(sqlite_db)
    codigos = _poblar_grupo(sqlite_db, grupo_id, 4, codigo_base="720")
    invitador = codigos[0]
    score_antes = _score_invitador(sqlite_db, invitador)
    inv = _crear_invitacion_crecimiento(client, invitador)
    codigo_inv = inv.get_json()["codigo"]
    reg = _registrar_invitado(client, codigo_inv, "00001", oficio_idx=5)
    assert reg.status_code == 201
    assert _score_invitador(sqlite_db, invitador) == score_antes + CRECIMIENTO_GRUPO_SCORE_DELTA


def test_segundo_invitado_registrado_suma_otros_5(client, sqlite_db, monkeypatch):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    sqlite_db.obtener_o_crear_invitador_admin("RUANA-ADMIN")
    grupo_id = _crear_grupo(sqlite_db)
    codigos = _poblar_grupo(sqlite_db, grupo_id, 3, codigo_base="730")
    invitador = codigos[0]
    score_antes = _score_invitador(sqlite_db, invitador)

    inv1 = _crear_invitacion_crecimiento(client, invitador).get_json()["codigo"]
    _registrar_invitado(client, inv1, "00002", oficio_idx=6)
    inv2 = _crear_invitacion_crecimiento(client, invitador).get_json()["codigo"]
    _registrar_invitado(client, inv2, "00003", oficio_idx=7)

    assert _score_invitador(sqlite_db, invitador) == score_antes + (2 * CRECIMIENTO_GRUPO_SCORE_DELTA)


def test_diez_invitados_acumulan_50_score(client, sqlite_db, monkeypatch):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    sqlite_db.obtener_o_crear_invitador_admin("RUANA-ADMIN")
    grupo_id = _crear_grupo(sqlite_db)
    codigos = _poblar_grupo(sqlite_db, grupo_id, 2, codigo_base="740")
    invitador = codigos[0]
    score_antes = _score_invitador(sqlite_db, invitador)

    for i in range(10):
        inv = _crear_invitacion_crecimiento(client, invitador).get_json()["codigo"]
        reg = _registrar_invitado(client, inv, f"1{i:04d}", oficio_idx=i + 2)
        assert reg.status_code == 201
        _reset_movimientos_score_dia(sqlite_db, invitador)

    assert _score_invitador(sqlite_db, invitador) == score_antes + 50


def test_undecimo_invitado_no_suma_mas_score(client, sqlite_db, monkeypatch):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    sqlite_db.obtener_o_crear_invitador_admin("RUANA-ADMIN")
    grupo_id = _crear_grupo(sqlite_db)
    codigos = _poblar_grupo(sqlite_db, grupo_id, 2, codigo_base="750")
    invitador = codigos[0]

    for i in range(10):
        inv = _crear_invitacion_crecimiento(client, invitador).get_json()["codigo"]
        _registrar_invitado(client, inv, f"2{i:04d}", oficio_idx=i + 1)
        _reset_movimientos_score_dia(sqlite_db, invitador)

    score_con_10 = _score_invitador(sqlite_db, invitador)
    inv11 = _crear_invitacion_crecimiento(client, invitador).get_json()["codigo"]
    _registrar_invitado(client, inv11, "29999", oficio_idx=0)
    assert _score_invitador(sqlite_db, invitador) == score_con_10


def test_mismo_invitado_procesado_dos_veces_solo_una_recompensa(client, sqlite_db, monkeypatch):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    sqlite_db.obtener_o_crear_invitador_admin("RUANA-ADMIN")
    grupo_id = _crear_grupo(sqlite_db)
    codigos = _poblar_grupo(sqlite_db, grupo_id, 3, codigo_base="760")
    invitador = codigos[0]
    inv = _crear_invitacion_crecimiento(client, invitador).get_json()["codigo"]
    reg = _registrar_invitado(client, inv, "30001", oficio_idx=4)
    nuevo_codigo = reg.get_json()["codigo"]
    score_tras_registro = _score_invitador(sqlite_db, invitador)

    sqlite_db.consumir_invitacion_y_recompensar(inv, nuevo_codigo)
    assert _score_invitador(sqlite_db, invitador) == score_tras_registro
    assert grupo_crecimiento_service.contar_recompensas_invitador(sqlite_db, invitador) == 1


def test_auto_invitacion_cero_puntos(sqlite_db):
    sqlite_db.obtener_o_crear_invitador_admin("RUANA-ADMIN")
    grupo_id = _crear_grupo(sqlite_db)
    codigos = _poblar_grupo(sqlite_db, grupo_id, 2, codigo_base="770")
    invitador = codigos[0]
    score_antes = _score_invitador(sqlite_db, invitador)
    resultado = grupo_crecimiento_service.otorgar_recompensa_registro(
        sqlite_db, invitador, invitador, "99999", grupo_id
    )
    assert resultado["otorgada"] is False
    assert _score_invitador(sqlite_db, invitador) == score_antes


def test_usuario_con_10_recompensas_no_recibe_mas_puntos(sqlite_db):
    sqlite_db.obtener_o_crear_invitador_admin("RUANA-ADMIN")
    grupo_id = _crear_grupo(sqlite_db)
    _insertar_aliado_en_grupo(sqlite_db, "78000", "28001", grupo_id, oficio_idx=0)
    invitador = "78000"
    for i in range(10):
        invitado = f"88{i:03d}"
        _insertar_aliado_en_grupo(sqlite_db, invitado, "28001", grupo_id, oficio_idx=i + 1)
        grupo_crecimiento_service.otorgar_recompensa_registro(
            sqlite_db, invitador, invitado, f"INV{i}", grupo_id
        )
        _reset_movimientos_score_dia(sqlite_db, invitador)
    score_con_limite = _score_invitador(sqlite_db, invitador)
    resultado = grupo_crecimiento_service.otorgar_recompensa_registro(
        sqlite_db, invitador, "88999", "INVEXTRA", grupo_id
    )
    assert resultado["otorgada"] is False
    assert _score_invitador(sqlite_db, invitador) == score_con_limite


def test_recompensa_queda_registrada_auditable(client, sqlite_db, monkeypatch):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    sqlite_db.obtener_o_crear_invitador_admin("RUANA-ADMIN")
    grupo_id = _crear_grupo(sqlite_db)
    codigos = _poblar_grupo(sqlite_db, grupo_id, 3, codigo_base="790")
    invitador = codigos[0]
    inv = _crear_invitacion_crecimiento(client, invitador).get_json()["codigo"]
    reg = _registrar_invitado(client, inv, "40001", oficio_idx=3)
    invitado = reg.get_json()["codigo"]

    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT invitador_codigo, invitado_codigo, invitacion_codigo, grupo_id, score_delta "
        "FROM grupo_crecimiento_recompensas WHERE invitador_codigo = ?",
        (invitador,),
    )
    row = cur.fetchone()
    conn.close()
    assert row is not None
    assert row[0] == invitador
    assert row[1] == invitado
    assert row[2] == inv
    assert row[3] == grupo_id
    assert row[4] == CRECIMIENTO_GRUPO_SCORE_DELTA

    motivo = f"{SCORE_MOTIVO_ALIADO_INVITADO_REGISTRADO}_{invitado}"
    assert sqlite_db._ya_aplicado_motivo_score(invitador, motivo) is True


def test_recargar_panel_no_vuelve_a_conceder_puntos(client, sqlite_db, monkeypatch):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    sqlite_db.obtener_o_crear_invitador_admin("RUANA-ADMIN")
    grupo_id = _crear_grupo(sqlite_db)
    codigos = _poblar_grupo(sqlite_db, grupo_id, 3, codigo_base="800")
    invitador = codigos[0]
    inv = _crear_invitacion_crecimiento(client, invitador).get_json()["codigo"]
    _registrar_invitado(client, inv, "50001", oficio_idx=2)
    score_tras = _score_invitador(sqlite_db, invitador)

    for _ in range(3):
        r = client.get("/api/aliado/datos", headers=_session_headers(invitador))
        assert r.status_code == 200
    assert _score_invitador(sqlite_db, invitador) == score_tras


def test_repetir_evento_registro_no_duplica_recompensa(client, sqlite_db, monkeypatch):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    sqlite_db.obtener_o_crear_invitador_admin("RUANA-ADMIN")
    grupo_id = _crear_grupo(sqlite_db)
    codigos = _poblar_grupo(sqlite_db, grupo_id, 2, codigo_base="810")
    invitador = codigos[0]
    inv = _crear_invitacion_crecimiento(client, invitador).get_json()["codigo"]
    reg = _registrar_invitado(client, inv, "60001", oficio_idx=1)
    nuevo = reg.get_json()["codigo"]
    score_una = _score_invitador(sqlite_db, invitador)

    sqlite_db.consumir_invitacion_y_recompensar(inv, nuevo)
    sqlite_db.consumir_invitacion_y_recompensar(inv, nuevo)
    assert _score_invitador(sqlite_db, invitador) == score_una
    assert grupo_crecimiento_service.contar_recompensas_invitador(sqlite_db, invitador) == 1


def test_invitacion_ampliar_red_sigue_dando_mas3(client, sqlite_db, monkeypatch):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    sqlite_db.obtener_o_crear_invitador_admin("RUANA-ADMIN")
    grupo_id = _crear_grupo(sqlite_db)
    codigos = _poblar_grupo(sqlite_db, grupo_id, 3, codigo_base="820")
    invitador = codigos[0]
    score_antes = _score_invitador(sqlite_db, invitador)
    inv = client.post(
        "/api/invitaciones/crear",
        headers=_session_headers(invitador),
        json={"zona": "28001"},
    )
    codigo_inv = inv.get_json()["codigo"]
    _registrar_invitado(client, codigo_inv, "70001", oficio_idx=4)
    assert _score_invitador(sqlite_db, invitador) == score_antes + 3


def test_progreso_en_panel_muestra_recompensas(client, sqlite_db, monkeypatch):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    sqlite_db.obtener_o_crear_invitador_admin("RUANA-ADMIN")
    grupo_id = _crear_grupo(sqlite_db)
    codigos = _poblar_grupo(sqlite_db, grupo_id, 4, codigo_base="830")
    invitador = codigos[0]

    for i in range(3):
        inv = _crear_invitacion_crecimiento(client, invitador).get_json()["codigo"]
        _registrar_invitado(client, inv, f"8{i:04d}", oficio_idx=i + 5)
        _reset_movimientos_score_dia(sqlite_db, invitador)

    info = _info_grupo_panel(client, invitador)
    crec = info.get("crecimiento") or {}
    assert crec.get("recompensas_obtenidas") == 3
    assert crec.get("score_obtenido") == 15
    assert crec.get("limite_alcanzado") is False


def test_aliado_nuevo_en_grupo_pequeno_ve_aviso_crecimiento(client, sqlite_db, monkeypatch):
    """Un aliado que entra a un grupo con ≤10 miembros recibe en_creacion en sus datos."""
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    sqlite_db.obtener_o_crear_invitador_admin("RUANA-ADMIN")
    grupo_id = _crear_grupo(sqlite_db)
    codigos = _poblar_grupo(sqlite_db, grupo_id, 4, codigo_base="850")
    invitador = codigos[0]

    inv = _crear_invitacion_crecimiento(client, invitador).get_json()["codigo"]
    reg = _registrar_invitado(client, inv, "85099", oficio_idx=5)
    assert reg.status_code == 201
    nuevo_codigo = reg.get_json()["codigo"]

    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute(
        "UPDATE aliados SET grupo_id = ? WHERE codigo = ?",
        (grupo_id, nuevo_codigo),
    )
    conn.commit()
    conn.close()

    datos = client.get("/api/aliado/datos", headers=_session_headers(nuevo_codigo))
    assert datos.status_code == 200
    grupo_info = datos.get_json()["aliado"].get("grupo_info") or {}
    assert grupo_info.get("en_creacion") is True
    assert grupo_info.get("num_aliados") == 5
    assert "crecimiento" in grupo_info


def test_no_permite_invitacion_crecimiento_si_grupo_consolidado(client, sqlite_db, monkeypatch):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    sqlite_db.obtener_o_crear_invitador_admin("RUANA-ADMIN")
    grupo_id = _crear_grupo(sqlite_db)
    codigos = _poblar_grupo(sqlite_db, grupo_id, 11, codigo_base="840")
    r = _crear_invitacion_crecimiento(client, codigos[0])
    assert r.status_code == 400
