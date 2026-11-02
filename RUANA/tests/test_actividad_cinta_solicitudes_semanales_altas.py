"""
Cinta RUANA: solicitudes semanales de la zona y altas de aliados (sin nombres).

Reproduce el caso real del 2 nov 2026: un carpintero solo en su grupo (CP 03380)
publica una solicitud semanal. Antes nadie la veía en la cinta, porque solo se
avisaba a los aliados activos del mismo grupo y el grupo no tenía más aliados.
"""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from core import db_manager as db_module
from core.services import actividad_cinta_service as svc
from core.services import solicitud_semanal_service


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    return db_module.DBManager(str(tmp_path / "ruana_cinta_sol_sem.db"))


def _ts(delta_dias=0):
    return (datetime.utcnow() - timedelta(days=delta_dias)).strftime("%Y-%m-%d %H:%M:%S")


def _grupo(cur, nombre, cp):
    cur.execute(
        "INSERT INTO grupos (nombre, codigo_postal, estado, fecha_creacion) VALUES (?, ?, 'activo', ?)",
        (nombre, cp, _ts()),
    )
    return cur.lastrowid


def _aliado(cur, codigo, nombre, oficio, cp, gid, estado="activo", creado=None):
    cur.execute(
        """
        INSERT INTO aliados (codigo, nombre, oficio, codigo_postal, grupo_id, estado, creado_en)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (codigo, nombre, oficio, cp, gid, estado, creado or _ts(10)),
    )


@pytest.fixture
def red(sqlite_db):
    conn = sqlite_db._connect()
    cur = conn.cursor()
    g_alicante = _grupo(cur, "RUANA-09WCE1QN-ENLACE", "03014")
    g_madrid = _grupo(cur, "RUANA-NHGNZ1O1-HOGAR", "28100")
    g_jesus = _grupo(cur, "RUANA-D21ZELQU-RED", "03380")
    _aliado(cur, "81366", "Alexander", "Clases de informática básica", "03014", g_alicante)
    _aliado(cur, "40243", "Daniel", "Electricidad", "28100", g_madrid)
    _aliado(cur, "26053", "Jesus Espinosa", "Carpintería de madera e interior", "03380", g_jesus, creado=_ts(0))
    conn.commit()
    conn.close()
    return {"g_alicante": g_alicante, "g_madrid": g_madrid, "g_jesus": g_jesus}


def _textos(items):
    return [it["texto"] for it in items]


def _publicar_jesus(db, oficio="Electricidad", personalizado=False):
    res = solicitud_semanal_service.crear_solicitud_semanal(
        db, "26053", oficio, "Necesito ayuda con una instalación", personalizado
    )
    assert res["status"] == "success", res
    return res["id"]


def test_solicitud_de_grupo_unipersonal_se_ve_en_la_zona(sqlite_db, red):
    _publicar_jesus(sqlite_db)
    textos = _textos(svc.preparar_actividad_cinta(sqlite_db, "81366"))
    assert "Un carpintero de tu zona busca un electricista esta semana" in textos


def test_solicitud_sin_nombre_del_solicitante(sqlite_db, red):
    _publicar_jesus(sqlite_db)
    joined = " ".join(_textos(svc.preparar_actividad_cinta(sqlite_db, "81366")))
    assert "Jesus" not in joined
    assert "instalación" not in joined  # la descripción no se publica en la cinta


def test_solicitud_no_sale_fuera_de_la_provincia(sqlite_db, red):
    _publicar_jesus(sqlite_db)
    textos = _textos(svc.preparar_actividad_cinta(sqlite_db, "40243"))
    assert not any("busca" in t for t in textos)


def test_solicitante_no_ve_su_propia_solicitud(sqlite_db, red):
    _publicar_jesus(sqlite_db)
    textos = _textos(svc.preparar_actividad_cinta(sqlite_db, "26053"))
    assert not any("busca" in t for t in textos)


def test_solicitud_mismo_grupo_dice_de_tu_grupo_y_no_duplica(sqlite_db, red):
    conn = sqlite_db._connect()
    cur = conn.cursor()
    _aliado(cur, "26999", "Compañero", "Pintura y decoración", "03380", red["g_jesus"])
    conn.commit()
    conn.close()
    sid = _publicar_jesus(sqlite_db)
    items = svc.preparar_actividad_cinta(sqlite_db, "26999")
    # El compañero recibe la notificación de siempre (con nombre, dentro del grupo)
    # y no se le duplica con la lectura de tabla.
    sol_items = [it for it in items if "solicitud" in it["tipo"]]
    assert len(sol_items) == 1, _textos(items)
    assert sol_items[0]["texto"] == "Nueva solicitud publicada por Jesus Espinosa en el grupo"
    assert sid


def test_solicitud_oficio_personalizado(sqlite_db, red):
    _publicar_jesus(sqlite_db, oficio="Persianero", personalizado=True)
    textos = _textos(svc.preparar_actividad_cinta(sqlite_db, "81366"))
    assert "Un carpintero de tu zona busca «Persianero» esta semana" in textos


def test_solicitud_expirada_o_de_otra_semana_no_sale(sqlite_db, red):
    sid = _publicar_jesus(sqlite_db)
    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute("UPDATE solicitudes_semanales SET estado = 'cerrada' WHERE id = ?", (sid,))
    conn.commit()
    conn.close()
    textos = _textos(svc.preparar_actividad_cinta(sqlite_db, "81366"))
    assert not any("busca" in t for t in textos)


def test_alta_aliado_cp_y_oficio_sin_nombre(sqlite_db, red):
    textos = _textos(svc.preparar_actividad_cinta(sqlite_db, "40243"))
    esperado = "En el CP 03380 se acaba de registrar un nuevo aliado de carpintería de madera e interior"
    assert esperado in textos
    assert "Jesus" not in " ".join(textos)


def test_alta_no_incluye_al_propio_aliado_ni_altas_antiguas(sqlite_db, red):
    textos = _textos(svc.preparar_actividad_cinta(sqlite_db, "26053"))
    assert not any("CP 03380 se acaba de registrar" in t for t in textos)
    # Alexander y Daniel se dieron de alta hace 10 días: siguen en la ventana de 14.
    assert any("CP 03014 se acaba de registrar" in t for t in textos)
    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute("UPDATE aliados SET creado_en = ? WHERE codigo IN ('81366', '40243')", (_ts(20),))
    conn.commit()
    conn.close()
    textos = _textos(svc.preparar_actividad_cinta(sqlite_db, "26053"))
    assert not any("se acaba de registrar" in t for t in textos)


def test_alta_excluye_estados_no_reales(sqlite_db, red):
    conn = sqlite_db._connect()
    cur = conn.cursor()
    _aliado(cur, "55001", "Rechazado", "Cerrajería", "41001", None, estado="rechazado", creado=_ts(0))
    _aliado(cur, "55002", "Pendiente", "Cerrajería", "41002", None, estado="pendiente_validacion", creado=_ts(0))
    _aliado(cur, "55003", "Espera", "Cerrajería", "41003", None, estado="en_espera", creado=_ts(0))
    conn.commit()
    conn.close()
    joined = " ".join(_textos(svc.preparar_actividad_cinta(sqlite_db, "40243")))
    assert "CP 41001" not in joined
    assert "CP 41002" not in joined
    assert "CP 41003 se acaba de registrar un nuevo aliado de cerrajería" in joined


def test_alta_mismo_grupo_no_se_duplica(sqlite_db, red):
    conn = sqlite_db._connect()
    cur = conn.cursor()
    _aliado(cur, "28555", "Nuevo", "Fontanería y fontanería-gas", "28100", red["g_madrid"], creado=_ts(0))
    conn.commit()
    conn.close()
    textos = _textos(svc.preparar_actividad_cinta(sqlite_db, "40243"))
    assert "Nuevo acaba de entrar al grupo" in textos
    assert not any("CP 28100 se acaba de registrar" in t for t in textos)


def test_altas_maximo_tres(sqlite_db, red):
    conn = sqlite_db._connect()
    cur = conn.cursor()
    for i in range(6):
        _aliado(cur, f"7700{i}", f"N{i}", "Cerrajería", f"4600{i}", None, creado=_ts(0))
    conn.commit()
    conn.close()
    textos = _textos(svc.preparar_actividad_cinta(sqlite_db, "40243"))
    assert sum("se acaba de registrar" in t for t in textos) == svc.MAX_ALTAS_CINTA


def test_metricas_no_desplazan_eventos_reales(sqlite_db, red):
    _publicar_jesus(sqlite_db)
    items = svc.preparar_actividad_cinta(sqlite_db, "81366")
    fuentes = [it["fuente"] for it in items]
    if "metrica" in fuentes:
        primera_metrica = fuentes.index("metrica")
        assert all(f == "metrica" for f in fuentes[primera_metrica:])
    assert fuentes[0] != "metrica"


@pytest.mark.parametrize(
    "oficio,esperado",
    [
        ("Carpintería de madera e interior", "Un carpintero"),
        ("Electricidad", "Un electricista"),
        ("Mudanzas y portes", "Un profesional de mudanzas y portes"),
        ("", "Un aliado"),
    ],
)
def test_sujeto_oficio(oficio, esperado):
    assert svc._sujeto_oficio(oficio) == esperado


def test_repo_sql_postgres_compatible():
    from unittest.mock import MagicMock

    from core.postgres_compat import PostgresCompatCursor
    from core.repositories.actividad_repo import ActividadRepo

    conn = MagicMock()
    conn._conn = MagicMock()
    inner = MagicMock()
    conn._conn.cursor.return_value = inner
    inner.fetchall.return_value = []
    cur = PostgresCompatCursor(conn)
    ActividadRepo().listar_altas_recientes(cur, "X")
    sql = inner.execute.call_args[0][0]
    assert "interval '14 days'" in sql
    assert "datetime(" not in sql
