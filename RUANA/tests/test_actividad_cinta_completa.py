"""
Tests completos de la cinta de actividad RUANA (actividad_cinta_service).
Cubre eventos de negocio, red, score/competencia, métricas, privacidad y límites.
"""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from core import db_manager as db_module
from core.services import actividad_cinta_service, notificacion_service


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    return db_module.DBManager(str(tmp_path / "ruana_actividad_completa.db"))


def _ahora():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def _setup_red(db, cp="28001"):
    """Grupo A (viewer) + Grupo B (otro CP) para pruebas de privacidad."""
    conn = db._connect()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO grupos (nombre, codigo_postal, estado, fecha_creacion) VALUES (?, ?, ?, ?)",
        ("Grupo A", cp, "activo", _ahora()),
    )
    g1 = cur.lastrowid
    cur.execute(
        "INSERT INTO grupos (nombre, codigo_postal, estado, fecha_creacion) VALUES (?, ?, ?, ?)",
        ("Grupo B", "41001", "activo", _ahora()),
    )
    g2 = cur.lastrowid
    aliados = [
        ("V001", "Violeta", "Electricidad", cp, g1, "activo"),
        ("V002", "Pablo", "Fontaneria", cp, g1, "activo"),
        ("V003", "Lucia", "Carpinteria", cp, g1, "activo"),
        ("X001", "Externo", "Pintura", "41001", g2, "activo"),
    ]
    for cod, nom, ofi, postal, gid, est in aliados:
        cur.execute(
            """
            INSERT INTO aliados (codigo, nombre, oficio, codigo_postal, grupo_id, estado, creado_en)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (cod, nom, ofi, postal, gid, est, _ahora()),
        )
    conn.commit()
    conn.close()
    return {"g1": g1, "g2": g2, "cp": cp}


def _textos(items):
    return [it["texto"] for it in items]


def _insert_notif(db, codigo, tipo, metadata=None, creado_en=None):
    db._crear_notificacion_aliado(
        codigo, tipo, "T", "M", metadata=metadata or {}
    )
    if creado_en:
        conn = db._connect()
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE notificaciones_aliado SET creado_en = ?
            WHERE id = (SELECT MAX(id) FROM notificaciones_aliado WHERE aliado_codigo = ?)
            """,
            (creado_en, codigo),
        )
        conn.commit()
        conn.close()


# --- Formateo vía notificaciones ---

@pytest.mark.parametrize(
    "tipo,meta,esperado",
    [
        ("solicitud_nueva", {"solicitante_nombre": "Ana"}, "Ana ha publicado una nueva solicitud"),
        ("solicitud_actualizada", {"solicitante_nombre": "Ana"}, "Ana acaba de actualizar una solicitud"),
        ("solicitud_asignada", {}, "Una solicitud acaba de ser asignada"),
        ("solicitud_semanal_respuesta", {"respondiente_nombre": "Luis"}, "Luis ya ha respondido a la solicitud semanal"),
        ("propuesta", {"proponente_nombre": "A", "propuesto_nombre": "B"}, "A ha propuesto a B"),
        ("recomendacion", {"origen_nombre": "A", "destino_nombre": "B"}, "A acaba de recomendar a B"),
        (
            "recomendacion_oficio",
            {"origen_nombre": "A", "destino_nombre": "B", "oficio": "Fontanero"},
            "A recomienda a B para Fontanero",
        ),
        ("recomendacion_encargo", {}, "Una recomendación acaba de convertirse en un encargo"),
        (
            "acuerdo_cerrado",
            {
                "solicitante_nombre": "Ana",
                "profesional_nombre": "Luis",
                "solicitante_codigo": "V001",
                "profesional_codigo": "V002",
                "importe": 250,
            },
            "Ana y Luis han alcanzado un acuerdo de 250 €",
        ),
        ("aliado_nuevo_grupo", {"nombre": "Nuevo"}, "Nuevo acaba de entrar al grupo"),
        ("invitacion", {"invitador_nombre": "A", "invitado_nombre": "B"}, "A ha invitado a B a RUANA"),
        ("invitacion_oficio", {"invitador_nombre": "A", "oficio": "Electricista"}, "A ha generado una invitación para Electricista"),
        ("catalogo_actualizado", {"nombre": "Marta"}, "Marta acaba de actualizar sus servicios"),
        ("foto_actualizada", {"nombre": "Marta"}, "Marta acaba de actualizar su foto"),
        ("grupo_nuevo_cp", {}, "Nuevo grupo creado en tu código postal"),
        ("plaza_disponible", {"oficio": "Pintor"}, "Nueva plaza de Pintor disponible en tu zona"),
        ("competencia_cp", {"nombre": "Juan"}, "Juan, aliado de tu CP, ha pasado a competencia"),
        ("score_change", {"nombre": "Pedro", "codigo": "X999"}, "El score de Pedro acaba de cambiar"),
        ("competencia_reto", {"retador_nombre": "A", "titular_nombre": "B"}, "A ha retado a B"),
    ],
)
def test_formateo_notificaciones_cinta(sqlite_db, tipo, meta, esperado):
    _setup_red(sqlite_db)
    _insert_notif(sqlite_db, "V001", tipo, metadata=meta)
    items = actividad_cinta_service.preparar_actividad_cinta(sqlite_db, "V001")
    assert any(it["texto"] == esperado for it in items), f"tipo={tipo} textos={_textos(items)}"


# --- Lectura desde tablas reales ---

def test_solicitud_nueva_desde_tabla(sqlite_db):
    ctx = _setup_red(sqlite_db)
    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO solicitudes (grupo_id, solicitante_codigo, solicitante_nombre, oficio, descripcion, estado, created_at)
        VALUES (?, ?, ?, ?, ?, 'pendiente', ?)
        """,
        (ctx["g1"], "V002", "Pablo", "Fontaneria", "Necesito ayuda", _ahora()),
    )
    conn.commit()
    conn.close()
    items = actividad_cinta_service.preparar_actividad_cinta(sqlite_db, "V001")
    assert "Pablo ha publicado una nueva solicitud" in _textos(items)


def test_solicitud_asignada_desde_tabla(sqlite_db):
    ctx = _setup_red(sqlite_db)
    conn = sqlite_db._connect()
    cur = conn.cursor()
    sqlite_db._migrar_solicitudes_candidato(conn, cur)
    cur.execute(
        """
        INSERT INTO solicitudes (
            grupo_id, solicitante_codigo, solicitante_nombre, oficio, descripcion,
            estado, asignada_a_codigo, asignada_a_nombre, candidato_at, created_at
        ) VALUES (?, ?, ?, ?, ?, 'pendiente', ?, ?, ?, ?)
        """,
        (ctx["g1"], "V001", "Violeta", "Electricidad", "x", "V003", "Lucia", _ahora(), _ahora()),
    )
    conn.commit()
    conn.close()
    items = actividad_cinta_service.preparar_actividad_cinta(sqlite_db, "V002")
    assert "Una solicitud acaba de ser asignada" in _textos(items)


def test_respuesta_semanal_desde_tabla(sqlite_db):
    ctx = _setup_red(sqlite_db)
    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO solicitudes (
            grupo_id, solicitante_codigo, solicitante_nombre, oficio, descripcion,
            estado, atendido_por_codigo, atendido_por_nombre, atendido_at, created_at
        ) VALUES (?, ?, ?, ?, ?, 'atendida', ?, ?, ?, ?)
        """,
        (ctx["g1"], "V001", "Violeta", "Electricidad", "x", "V002", "Pablo", _ahora(), _ahora()),
    )
    conn.commit()
    conn.close()
    items = actividad_cinta_service.preparar_actividad_cinta(sqlite_db, "V001")
    assert "Pablo ya ha respondido a la solicitud semanal" in _textos(items)


def test_propuesta_desde_tabla(sqlite_db):
    ctx = _setup_red(sqlite_db)
    conn = sqlite_db._connect()
    cur = conn.cursor()
    sqlite_db._migrar_solicitudes_candidato(conn, cur)
    cur.execute(
        """
        INSERT INTO solicitudes (
            grupo_id, solicitante_codigo, solicitante_nombre, oficio, descripcion,
            estado, candidato_por_codigo, candidato_por_nombre, candidato_at, created_at
        ) VALUES (?, ?, ?, ?, ?, 'candidato_pendiente', ?, ?, ?, ?)
        """,
        (ctx["g1"], "V001", "Violeta", "Electricidad", "x", "V002", "Pablo", _ahora(), _ahora()),
    )
    conn.commit()
    conn.close()
    items = actividad_cinta_service.preparar_actividad_cinta(sqlite_db, "V003")
    assert "Violeta ha propuesto a Pablo" in _textos(items)


def test_recomendacion_desde_contacto(sqlite_db):
    ctx = _setup_red(sqlite_db)
    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO contactos_ruana (solicitante_codigo, profesional_codigo, servicio, estado, creado_en)
        VALUES (?, ?, ?, 'nuevo', ?)
        """,
        ("V001", "V002", "", _ahora()),
    )
    conn.commit()
    conn.close()
    items = actividad_cinta_service.preparar_actividad_cinta(sqlite_db, "V003")
    assert "Violeta acaba de recomendar a Pablo" in _textos(items)


def test_recomendacion_oficio_desde_contacto(sqlite_db):
    ctx = _setup_red(sqlite_db)
    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO contactos_ruana (solicitante_codigo, profesional_codigo, servicio, estado, creado_en)
        VALUES (?, ?, ?, 'nuevo', ?)
        """,
        ("V001", "V002", "Fontaneria", _ahora()),
    )
    conn.commit()
    conn.close()
    items = actividad_cinta_service.preparar_actividad_cinta(sqlite_db, "V003")
    assert "Violeta recomienda a Pablo para Fontaneria" in _textos(items)


def test_encargo_desde_contacto(sqlite_db):
    ctx = _setup_red(sqlite_db)
    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO contactos_ruana (
            solicitante_codigo, profesional_codigo, servicio, estado, fecha_cierre, creado_en
        ) VALUES (?, ?, ?, 'trabajo_cerrado', ?, ?)
        """,
        ("V001", "V002", "Servicio", _ahora(), _ahora()),
    )
    conn.commit()
    conn.close()
    items = actividad_cinta_service.preparar_actividad_cinta(sqlite_db, "V003")
    assert "Una recomendación acaba de convertirse en un encargo" in _textos(items)


def test_acuerdo_cerrado_privacidad_participante(sqlite_db):
    ctx = _setup_red(sqlite_db)
    conn = sqlite_db._connect()
    cur = conn.cursor()
    sqlite_db._migrar_importe_acordado(conn, cur)
    cur.execute(
        """
        INSERT INTO contactos_ruana (
            solicitante_codigo, profesional_codigo, servicio, estado,
            importe_acordado, acuerdo_alcanzado_en, creado_en
        ) VALUES (?, ?, ?, 'acuerdo_alcanzado', ?, ?, ?)
        """,
        ("V001", "V002", "Servicio", 300, _ahora(), _ahora()),
    )
    conn.commit()
    conn.close()
    items_parte = actividad_cinta_service.preparar_actividad_cinta(sqlite_db, "V001")
    items_tercero = actividad_cinta_service.preparar_actividad_cinta(sqlite_db, "V003")
    assert "Violeta y Pablo han alcanzado un acuerdo de 300 €" in _textos(items_parte)
    assert "Se ha cerrado un acuerdo en tu grupo" in _textos(items_tercero)
    assert "300 €" not in " ".join(_textos(items_tercero))


def test_nuevo_aliado_desde_tabla(sqlite_db):
    ctx = _setup_red(sqlite_db)
    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO aliados (codigo, nombre, oficio, codigo_postal, grupo_id, estado, creado_en)
        VALUES (?, ?, ?, ?, ?, 'activo', ?)
        """,
        ("V099", "Recien", "Jardineria", ctx["cp"], ctx["g1"], _ahora()),
    )
    conn.commit()
    conn.close()
    items = actividad_cinta_service.preparar_actividad_cinta(sqlite_db, "V001")
    assert "Recien acaba de entrar al grupo" in _textos(items)


def test_invitacion_desde_referidos(sqlite_db):
    ctx = _setup_red(sqlite_db)
    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO aliados (codigo, nombre, oficio, codigo_postal, grupo_id, estado, creado_en)
        VALUES (?, ?, ?, ?, ?, 'activo', ?)
        """,
        ("V050", "Invitado", "Pintura", ctx["cp"], ctx["g1"], _ahora()),
    )
    cur.execute(
        "INSERT INTO referidos (codigo_referido, codigo_invitador, creado_en) VALUES (?, ?, ?)",
        ("V050", "V001", _ahora()),
    )
    conn.commit()
    conn.close()
    items = actividad_cinta_service.preparar_actividad_cinta(sqlite_db, "V002")
    assert "Violeta ha invitado a Invitado a RUANA" in _textos(items)


def test_catalogo_desde_tabla(sqlite_db):
    ctx = _setup_red(sqlite_db)
    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO catalogo_servicios_aliado (aliado_codigo, posicion, descripcion, actualizado_en)
        VALUES (?, 1, 'Servicio nuevo', ?)
        """,
        ("V002", _ahora()),
    )
    conn.commit()
    conn.close()
    items = actividad_cinta_service.preparar_actividad_cinta(sqlite_db, "V001")
    assert "Pablo acaba de actualizar sus servicios" in _textos(items)


def test_foto_desde_tabla(sqlite_db):
    ctx = _setup_red(sqlite_db)
    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE aliados SET foto_perfil_url = ?, actualizado_en = ? WHERE codigo = ?
        """,
        ("https://example.com/f.jpg", _ahora(), "V002"),
    )
    conn.commit()
    conn.close()
    items = actividad_cinta_service.preparar_actividad_cinta(sqlite_db, "V001")
    assert "Pablo acaba de actualizar su foto" in _textos(items)


def test_grupo_nuevo_cp(sqlite_db):
    ctx = _setup_red(sqlite_db)
    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO grupos (nombre, codigo_postal, estado, fecha_creacion)
        VALUES (?, ?, 'activo', ?)
        """,
        ("Grupo nuevo CP", ctx["cp"], _ahora()),
    )
    conn.commit()
    conn.close()
    items = actividad_cinta_service.preparar_actividad_cinta(sqlite_db, "V001")
    assert "Nuevo grupo creado en tu código postal" in _textos(items)


def test_plaza_disponible_cp(sqlite_db):
    ctx = _setup_red(sqlite_db)
    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE aliados SET estado = 'en_competencia', actualizado_en = ? WHERE codigo = ?
        """,
        (_ahora(), "V002"),
    )
    conn.commit()
    conn.close()
    items = actividad_cinta_service.preparar_actividad_cinta(sqlite_db, "V001")
    assert any("Nueva plaza de Fontaneria disponible en tu zona" == t for t in _textos(items))


def test_competencia_desde_tabla(sqlite_db):
    ctx = _setup_red(sqlite_db)
    conn = sqlite_db._connect()
    cur = conn.cursor()
    fin = (datetime.utcnow() + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    cur.execute(
        """
        INSERT INTO competencia (
            grupo_id, oficio, aliado_original_codigo, retador_codigo,
            fecha_inicio, fecha_fin_prevista, estado, ganador_codigo
        ) VALUES (?, ?, ?, ?, ?, ?, 'finalizada', ?)
        """,
        (ctx["g1"], "Electricidad", "V001", "V002", _ahora(), fin, "V002"),
    )
    conn.commit()
    conn.close()
    items = actividad_cinta_service.preparar_actividad_cinta(sqlite_db, "V003")
    textos = _textos(items)
    assert "Nueva competencia iniciada en tu grupo" in textos
    assert "Pablo ha retado a Violeta" in textos
    assert "Pablo acaba de ganar una competencia" in textos
    assert "Violeta ha perdido una competencia" in textos


def test_score_desde_tabla(sqlite_db):
    ctx = _setup_red(sqlite_db)
    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO score_movimientos (codigo_aliado, delta, motivo, creado_en) VALUES (?, ?, ?, ?)",
        ("V002", 5, "test", _ahora()),
    )
    conn.commit()
    conn.close()
    items = actividad_cinta_service.preparar_actividad_cinta(sqlite_db, "V001")
    assert "El score de Pablo acaba de cambiar" in _textos(items)


def test_metricas_cp_via_grupo_sin_postal_aliado(sqlite_db):
    """Aliados sin codigo_postal propio deben contarse vía CP del grupo."""
    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO grupos (nombre, codigo_postal, estado, fecha_creacion) VALUES (?, ?, ?, ?)",
        ("Grupo CP", "28001", "activo", _ahora()),
    )
    g1 = cur.lastrowid
    for cod, nom in [("G001", "Ana"), ("G002", "Luis"), ("G003", "Marta")]:
        cur.execute(
            """
            INSERT INTO aliados (codigo, nombre, oficio, codigo_postal, grupo_id, estado, creado_en)
            VALUES (?, ?, ?, '', ?, 'activo', ?)
            """,
            (cod, nom, "Electricidad", g1, _ahora()),
        )
    conn.commit()
    conn.close()
    items = actividad_cinta_service.preparar_actividad_cinta(sqlite_db, "G001")
    textos = _textos(items)
    assert any("3 aliados activos en tu código postal" in t for t in textos)


def test_metricas_agregadas(sqlite_db):
    ctx = _setup_red(sqlite_db)
    conn = sqlite_db._connect()
    cur = conn.cursor()
    anio_mes = datetime.utcnow().strftime("%Y-%m")
    cur.execute(
        """
        INSERT INTO contactos_ruana (
            solicitante_codigo, profesional_codigo, servicio, estado, fecha_cierre, creado_en
        ) VALUES (?, ?, ?, 'trabajo_cerrado', ?, ?)
        """,
        ("V001", "V002", "S", f"{anio_mes}-15 12:00:00", f"{anio_mes}-10 10:00:00"),
    )
    cur.execute(
        """
        INSERT INTO solicitudes (
            grupo_id, solicitante_codigo, solicitante_nombre, oficio, descripcion,
            estado, atendido_por_codigo, atendido_por_nombre, atendido_at, created_at
        ) VALUES (?, ?, ?, ?, ?, 'atendida', ?, ?, ?, ?)
        """,
        (
            ctx["g1"], "V001", "Violeta", "E", "d", "V002", "Pablo",
            f"{anio_mes}-12 10:00:00", f"{anio_mes}-12 09:00:00",
        ),
    )
    conn.commit()
    conn.close()
    items = actividad_cinta_service.preparar_actividad_cinta(sqlite_db, "V001")
    textos = " ".join(_textos(items))
    assert "encargos este mes" in textos
    assert "aliados activos en tu código postal" in textos
    assert "recomendaciones ya se han convertido" in textos or "contactos reales" in textos
    assert "ha atendido" in textos and "solicitudes este mes" in textos


def test_privacidad_otro_grupo(sqlite_db):
    ctx = _setup_red(sqlite_db)
    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO solicitudes (grupo_id, solicitante_codigo, solicitante_nombre, oficio, descripcion, estado, created_at)
        VALUES (?, ?, ?, ?, ?, 'pendiente', ?)
        """,
        (ctx["g2"], "X001", "Externo", "Pintura", "privado", _ahora()),
    )
    conn.commit()
    conn.close()
    items = actividad_cinta_service.preparar_actividad_cinta(sqlite_db, "V001")
    assert "Externo ha publicado" not in " ".join(_textos(items))


def test_maximo_diez_elimina_antigua(sqlite_db):
    _setup_red(sqlite_db)
    base = datetime.utcnow()
    for i in range(12):
        _insert_notif(
            sqlite_db,
            "V001",
            "solicitud_nueva",
            metadata={"solicitante_nombre": f"Aliado{i}", "solicitud_id": i},
            creado_en=(base + timedelta(minutes=i)).strftime("%Y-%m-%d %H:%M:%S"),
        )
    items = actividad_cinta_service.preparar_actividad_cinta(sqlite_db, "V001")
    assert len(items) == 10
    assert "Aliado11 ha publicado" in _textos(items)[0]
    assert not any("Aliado0 ha publicado" in t for t in _textos(items))


def test_notificacion_service_fachada(sqlite_db):
    _setup_red(sqlite_db)
    _insert_notif(
        sqlite_db, "V001", "recomendacion",
        metadata={"origen_nombre": "A", "destino_nombre": "B"},
    )
    items = notificacion_service.preparar_actividad_cinta(sqlite_db, "V001")
    assert any("A acaba de recomendar a B" in it["texto"] for it in items)


def test_endpoint_datos_incluye_actividad_cinta(client, sqlite_db, monkeypatch, session_headers):
    from RUANA.web import app as app_module

    _setup_red(sqlite_db)
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    resp = client.get("/api/aliado/datos", headers=session_headers("aliado", "V001"))
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "success"
    assert isinstance(data.get("actividad_cinta"), list)
    assert len(data["actividad_cinta"]) > 0
    assert len(data["actividad_cinta"]) <= 10


def test_endpoint_notificaciones_incluye_actividad_cinta(client, sqlite_db, monkeypatch, session_headers):
    from RUANA.web import app as app_module

    _setup_red(sqlite_db)
    _insert_notif(
        sqlite_db, "V001", "recomendacion",
        metadata={"origen_nombre": "Violeta", "destino_nombre": "Pablo", "contacto_id": 1},
    )
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    resp = client.get("/api/aliados/V001/notificaciones", headers=session_headers("aliado", "V001"))
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "success"
    assert isinstance(data.get("actividad_cinta"), list)
    assert len(data["actividad_cinta"]) <= 10
    assert any(
        "recomendar" in (it.get("texto") or "")
        for it in data["actividad_cinta"]
    )
