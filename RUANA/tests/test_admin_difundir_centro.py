"""Difusión de avisos admin por el centro de comunicación."""
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from core import db_manager as db_module
from core.services import chat_service, difusion_soporte_service as ds
from RUANA.web import app as app_module

TEXTO = "Aviso de prueba del equipo RUANA para la red."


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    return db_module.DBManager(str(tmp_path / "ruana_difusion.db"))


def _crear(db, codigo, oficio="Electricidad", cp="28001", estado="activo", grupo_id=None):
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
    assert r.get("status") == "success", r
    conn = db._connect()
    conn.execute("UPDATE aliados SET estado = ? WHERE codigo = ?", (estado, codigo))
    if grupo_id is not None:
        conn.execute("UPDATE aliados SET grupo_id = ? WHERE codigo = ?", (grupo_id, codigo))
    conn.commit()
    conn.close()


def _poblar(db):
    _crear(db, "10001", "Electricidad", "28001")
    _crear(db, "10002", "Fontanería", "28002")
    _crear(db, "22001", "Albañilería", "22200")
    _crear(db, "22002", "Pintura", "22260")
    _crear(db, "30001", "Carpintería", "50001", estado="expulsado")
    _crear(db, "30002", "Riego", "28003", estado="pendiente_validacion")
    _crear(db, "30003", "Climatización", "28004", estado="en_espera")
    _crear(db, "30004", "Estética", "28005", estado="sistema")
    g1 = _grupo(db, "10001")
    g2 = _grupo(db, "22001")
    return g1, g2


def _grupo(db, codigo):
    conn = db._connect()
    row = conn.execute("SELECT grupo_id FROM aliados WHERE codigo = ?", (codigo,)).fetchone()
    conn.close()
    return row[0] if row else None


def _dump(db, tablas):
    conn = db._connect()
    out = {}
    try:
        for t in tablas:
            rows = conn.execute(f'SELECT * FROM "{t}"').fetchall()
            out[t] = sorted(json.dumps(list(r), default=str) for r in rows)
        return out
    finally:
        conn.close()


def _api(client, sqlite_db, monkeypatch, session_headers, body, permisos=None):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    headers = session_headers(
        "admin", "ADMIN001", permisos=permisos or ["leer", "escribir"]
    )
    return client.post("/api/admin/centro-comunicacion/difundir", json=body, headers=headers)


# --- Auth / validación -----------------------------------------------------------------

def test_exige_sesion_admin(client):
    r = client.post("/api/admin/centro-comunicacion/difundir", json={"texto": TEXTO, "dry_run": True})
    assert r.status_code in (401, 403)


def test_exige_permiso_escritura(client, sqlite_db, monkeypatch, session_headers):
    _poblar(sqlite_db)
    r = _api(client, sqlite_db, monkeypatch, session_headers, {"texto": TEXTO}, permisos=["leer"])
    assert r.status_code == 403


def test_texto_obligatorio_y_tope(client, sqlite_db, monkeypatch, session_headers):
    _poblar(sqlite_db)
    assert _api(client, sqlite_db, monkeypatch, session_headers, {"texto": "   "}).status_code == 400
    largo = "x" * (ds.TEXTO_MAX + 1)
    r = _api(client, sqlite_db, monkeypatch, session_headers, {"texto": largo, "dry_run": True})
    assert r.status_code == 400
    r = _api(client, sqlite_db, monkeypatch, session_headers, {"texto": "ok", "codigos": [], "dry_run": True})
    assert r.status_code == 400


def test_filtros_mutuamente_excluyentes(client, sqlite_db, monkeypatch, session_headers):
    _poblar(sqlite_db)
    r = _api(
        client, sqlite_db, monkeypatch, session_headers,
        {"texto": TEXTO, "codigos": ["10001"], "prefijo_cp": "28", "dry_run": True},
    )
    assert r.status_code == 400
    r = _api(
        client, sqlite_db, monkeypatch, session_headers,
        {"texto": TEXTO, "filtro": {"grupo_id": 1, "prefijo_cp": "28"}, "dry_run": True},
    )
    assert r.status_code == 400


# --- Filtros y exclusión de no activos -------------------------------------------------

def test_sin_filtro_solo_aliados_activos(client, sqlite_db, monkeypatch, session_headers):
    _poblar(sqlite_db)
    r = _api(client, sqlite_db, monkeypatch, session_headers, {"texto": TEXTO, "dry_run": True})
    assert r.status_code == 200, r.get_json()
    data = r.get_json()
    assert data["dry_run"] is True
    assert set(data["codigos"]) == {"10001", "10002", "22001", "22002"}
    assert data["destinatarios"] == 4
    for fuera in ("30001", "30002", "30003", "30004"):
        assert fuera not in data["codigos"]


def test_filtro_codigos(client, sqlite_db, monkeypatch, session_headers):
    _poblar(sqlite_db)
    r = _api(
        client, sqlite_db, monkeypatch, session_headers,
        {"texto": TEXTO, "codigos": ["10001", "30001", "99999", "10001"], "dry_run": True},
    )
    data = r.get_json()
    assert r.status_code == 200
    assert data["codigos"] == ["10001"]
    motivos = {o["codigo"]: o["motivo"] for o in data["omitidos"]}
    assert motivos["30001"] == "no_activo"
    assert motivos["99999"] == "inexistente"


def test_filtro_grupo_id(client, sqlite_db, monkeypatch, session_headers):
    _poblar(sqlite_db)
    gid = _grupo(sqlite_db, "10001")
    r = _api(
        client, sqlite_db, monkeypatch, session_headers,
        {"texto": TEXTO, "grupo_id": gid, "dry_run": True},
    )
    assert r.status_code == 200
    assert "10001" in r.get_json()["codigos"]
    # 22001 está en otro CP/grupo
    assert "22001" not in r.get_json()["codigos"]


def test_filtro_prefijo_cp(client, sqlite_db, monkeypatch, session_headers):
    _poblar(sqlite_db)
    r = _api(
        client, sqlite_db, monkeypatch, session_headers,
        {"texto": TEXTO, "prefijo_cp": "22", "dry_run": True},
    )
    assert set(r.get_json()["codigos"]) == {"22001", "22002"}
    r2 = _api(
        client, sqlite_db, monkeypatch, session_headers,
        {"texto": TEXTO, "filtro": {"prefijo_cp": "22260"}, "dry_run": True},
    )
    assert r2.get_json()["codigos"] == ["22002"]


# --- dry_run no escribe ----------------------------------------------------------------

def test_dry_run_no_escribe_nada(client, sqlite_db, monkeypatch, session_headers):
    _poblar(sqlite_db)
    tablas = (
        "ruana_soporte_conversaciones",
        "ruana_soporte_mensajes",
        "notificaciones_aliado",
        "eventos_sistema",
    )
    antes = _dump(sqlite_db, tablas)
    r = _api(client, sqlite_db, monkeypatch, session_headers, {"texto": TEXTO, "dry_run": True})
    assert r.status_code == 200
    assert r.get_json()["destinatarios"] == 4
    assert _dump(sqlite_db, tablas) == antes


# --- Envío: conversación, no leído, log ------------------------------------------------

def test_envio_crea_conversacion_y_queda_no_leido(client, sqlite_db, monkeypatch, session_headers):
    _poblar(sqlite_db)
    r = _api(
        client, sqlite_db, monkeypatch, session_headers,
        {"texto": TEXTO, "codigos": ["10001"]},
    )
    assert r.status_code == 200, r.get_json()
    data = r.get_json()
    assert data["dry_run"] is False
    assert data["destinatarios"] == 1
    assert data["creadas"] == 1 and data["reutilizadas"] == 0

    convs = chat_service.listar_conversaciones_soporte_aliado(sqlite_db, "10001")
    avisos = [c for c in convs if c.get("categoria") == "aviso" or c.get("tipo") == "aviso"]
    assert len(avisos) == 1
    conv = avisos[0]
    assert int(conv["tiene_no_leido_aliado"]) == 1
    assert conv["asunto"] == ds.ASUNTO_AVISO

    msgs = chat_service.listar_mensajes_soporte_aliado(sqlite_db, conv["id"], "10001")
    admin_msgs = [m for m in msgs if m["emisor_tipo"] == "admin"]
    assert len(admin_msgs) == 1
    assert admin_msgs[0]["mensaje"] == TEXTO
    assert int(admin_msgs[0]["leido_por_aliado"] or 0) == 0

    # La notificación in-app ya existía en las respuestas manuales; se reutiliza, sin email/push.
    conn = sqlite_db._connect()
    notif = conn.execute(
        "SELECT tipo, leida, titulo FROM notificaciones_aliado WHERE aliado_codigo='10001'"
    ).fetchall()
    conn.close()
    assert any(n[0] == "ruana_soporte" and int(n[1] or 0) == 0 for n in notif)

    chat_service.marcar_soporte_leido_aliado(sqlite_db, conv["id"], "10001")
    convs2 = chat_service.listar_conversaciones_soporte_aliado(sqlite_db, "10001")
    aviso2 = [c for c in convs2 if int(c["id"]) == int(conv["id"])][0]
    assert int(aviso2["tiene_no_leido_aliado"]) == 0


def test_reutiliza_conversacion_de_aviso_y_no_mezcla_otras(client, sqlite_db, monkeypatch, session_headers):
    _poblar(sqlite_db)
    # Conversación previa de consulta (no se reutiliza) y de activación.
    chat_service.crear_conversacion_soporte_aliado(
        sqlite_db, "10001", "Consulta previa", "Hola, una duda", categoria="consulta"
    )
    r1 = _api(client, sqlite_db, monkeypatch, session_headers, {"texto": "Primer aviso", "codigos": ["10001"]})
    assert r1.status_code == 200
    convs = chat_service.listar_conversaciones_soporte_aliado(sqlite_db, "10001")
    avisos = [c for c in convs if (c.get("tipo") or "") == "aviso"]
    assert len(avisos) == 1
    aviso_id = avisos[0]["id"]
    n_conv = len(convs)

    r2 = _api(client, sqlite_db, monkeypatch, session_headers, {"texto": "Segundo aviso", "codigos": ["10001"]})
    # El segundo choca con el límite de 1/hora salvo que movamos el evento atrás.
    assert r2.status_code == 429

    conn = sqlite_db._connect()
    conn.execute(
        "UPDATE eventos_sistema SET creado_en = ? WHERE tipo = ?",
        ((datetime.now(timezone.utc) - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S"), ds.TIPO_EVENTO),
    )
    conn.commit()
    conn.close()

    r3 = _api(client, sqlite_db, monkeypatch, session_headers, {"texto": "Segundo aviso", "codigos": ["10001"]})
    assert r3.status_code == 200, r3.get_json()
    assert r3.get_json()["reutilizadas"] == 1 and r3.get_json()["creadas"] == 0
    convs2 = chat_service.listar_conversaciones_soporte_aliado(sqlite_db, "10001")
    avisos2 = [c for c in convs2 if (c.get("tipo") or "") == "aviso"]
    assert len(avisos2) == 1
    assert avisos2[0]["id"] == aviso_id
    assert len(convs2) == n_conv
    msgs = chat_service.listar_mensajes_soporte_aliado(sqlite_db, aviso_id, "10001")
    textos = [m["mensaje"] for m in msgs if m["emisor_tipo"] == "admin"]
    assert textos == ["Primer aviso", "Segundo aviso"]
    assert int(avisos2[0]["tiene_no_leido_aliado"]) == 1


def test_envio_sin_destinatarios_no_escribe_ni_cuenta_cuota(client, sqlite_db, monkeypatch, session_headers):
    _poblar(sqlite_db)
    tablas = ("ruana_soporte_conversaciones", "ruana_soporte_mensajes", "eventos_sistema", "notificaciones_aliado")
    antes = _dump(sqlite_db, tablas)
    r = _api(
        client, sqlite_db, monkeypatch, session_headers,
        {"texto": TEXTO, "codigos": ["30001"]},
    )
    assert r.status_code == 400
    assert _dump(sqlite_db, tablas) == antes
    # Sigue pudiendo enviarse uno real después.
    ok = _api(client, sqlite_db, monkeypatch, session_headers, {"texto": TEXTO, "codigos": ["10001"]})
    assert ok.status_code == 200


def test_log_admin_sin_pii_extra(client, sqlite_db, monkeypatch, session_headers):
    _poblar(sqlite_db)
    r = _api(
        client, sqlite_db, monkeypatch, session_headers,
        {"texto": TEXTO, "prefijo_cp": "22"},
    )
    assert r.status_code == 200
    conn = sqlite_db._connect()
    row = conn.execute(
        "SELECT tipo, descripcion, actor_tipo, actor_codigo, metadata FROM eventos_sistema WHERE tipo = ?",
        (ds.TIPO_EVENTO,),
    ).fetchone()
    conn.close()
    assert row is not None
    tipo, desc, actor_tipo, actor_codigo, meta = row
    assert tipo == ds.TIPO_EVENTO
    assert actor_tipo == "admin"
    assert actor_codigo == "ADMIN001"
    assert "2 aliados" in desc
    assert "prefijo_cp" in desc
    payload = json.loads(meta)
    assert payload["destinatarios"] == 2
    assert payload["filtro"]["tipo"] == "prefijo_cp"
    assert payload["filtro"]["valor"] == "22"
    assert "excerpt" in payload
    # No guarda emails, teléfonos ni nombres.
    blob = desc + meta
    assert "@example.com" not in blob
    assert "+34600" not in blob
    assert "Aliado 22001" not in blob


def test_rate_limit_un_envio_real_por_hora(client, sqlite_db, monkeypatch, session_headers):
    _poblar(sqlite_db)
    r1 = _api(client, sqlite_db, monkeypatch, session_headers, {"texto": "Uno", "codigos": ["10001"]})
    assert r1.status_code == 200
    # dry_run no cuenta y sigue permitido.
    prev = _api(
        client, sqlite_db, monkeypatch, session_headers,
        {"texto": "Dos", "codigos": ["10002"], "dry_run": True},
    )
    assert prev.status_code == 200
    r2 = _api(client, sqlite_db, monkeypatch, session_headers, {"texto": "Dos", "codigos": ["10002"]})
    assert r2.status_code == 429
    body = r2.get_json()
    assert body["reintentar_en_segundos"] > 0
    assert "hora" in body["message"].lower()
    # El segundo aliado no recibió nada.
    assert chat_service.listar_conversaciones_soporte_aliado(sqlite_db, "10002") == [] or all(
        (c.get("tipo") or "") != "aviso" for c in chat_service.listar_conversaciones_soporte_aliado(sqlite_db, "10002")
    )


def test_frontend_tiene_formulario_de_aviso():
    from pathlib import Path
    web = Path(__file__).resolve().parents[1] / "web"
    html = (web / "admin.html").read_text(encoding="utf-8")
    js = (web / "static/js/admin-operaciones-module.js").read_text(encoding="utf-8")
    assert 'id="cc-admin-difundir-texto"' in html
    assert 'id="cc-admin-difundir-preview"' in html
    assert 'id="cc-admin-difundir-enviar"' in html
    assert "/api/admin/centro-comunicacion/difundir" in js
    assert "dry_run" in js
    assert "window.confirm" in js
    assert "admin-operaciones-module.js?v=20261120a" in html
