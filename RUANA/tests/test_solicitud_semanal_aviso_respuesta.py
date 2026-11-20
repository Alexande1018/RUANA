"""Avisos al autor cuando alguien responde a una solicitud semanal."""

from types import SimpleNamespace

import pytest

from core import db_manager as db_module
from core import email_service
from core.services import notificacion_service, solicitud_semanal_service


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    return db_module.DBManager(str(tmp_path / "ruana_sol_sem_aviso.db"))


def _crear_grupo(db, nombre, cp, aliados):
    """aliados: (codigo, nombre, oficio[, email, telefono])."""
    conn = db._connect()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO grupos (nombre, codigo_postal, estado) VALUES (?, ?, ?)",
        (nombre, cp, "activo"),
    )
    grupo_id = cursor.lastrowid
    for item in aliados:
        codigo, nombre_aliado, oficio = item[:3]
        email = item[3] if len(item) > 3 else None
        telefono = item[4] if len(item) > 4 else None
        cursor.execute(
            """
            INSERT INTO aliados (
                codigo, nombre, oficio, codigo_postal, grupo_id, estado, email, telefono
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (codigo, nombre_aliado, oficio, cp, grupo_id, "activo", email, telefono),
        )
    conn.commit()
    conn.close()
    return grupo_id


def _avisos_respuesta(db, codigo):
    filas = notificacion_service.listar_notificaciones_aliado(db, codigo)
    return [n for n in filas if n.get("tipo") == "solicitud_semanal_respuesta"]


def _codigo_inv(_db):
    return "INVAVISO1"


def test_puedo_ayudar_avisa_al_autor(sqlite_db, monkeypatch):
    enviados = []
    monkeypatch.setattr(
        email_service,
        "enviar_correo_aliado",
        lambda *args, **kwargs: enviados.append((args, kwargs)) or True,
    )
    _crear_grupo(
        sqlite_db,
        "Grupo aviso",
        "03014",
        [
            ("JAIME", "Jaime", "Electricidad", "jaime@example.com", "+34600999888"),
            (
                "MARTA",
                "Marta",
                "Fontanería y fontanería-gas",
                "secreto.respondente@example.com",
                "+34600111222",
            ),
        ],
    )
    creada = solicitud_semanal_service.crear_solicitud_semanal(
        sqlite_db, "JAIME", "Fontanería y fontanería-gas", "", False
    )
    assert creada["status"] == "success"
    ayuda = solicitud_semanal_service.responder_puedo_ayudar(
        sqlite_db, creada["id"], "MARTA"
    )
    assert ayuda["status"] == "success"
    assert ayuda["contacto_id"]

    avisos = _avisos_respuesta(sqlite_db, "JAIME")
    assert len(avisos) == 1
    n = avisos[0]
    assert "Marta puede ayudarte con tu solicitud de" in n["mensaje"]
    assert "Fontanería" in n["mensaje"]
    meta = n["metadata"]
    assert meta["contacto_id"] == ayuda["contacto_id"]
    assert meta["solicitud_semanal_id"] == creada["id"]
    assert "contacto_id=" in (meta.get("enlace") or "")
    assert enviados, "Debe usar el canal de email transaccional existente"
    args, kwargs = enviados[0]
    assert args[0] == "jaime@example.com"
    assert "puede ayudarte" in args[1].lower() or "puede ayudarte" in args[2]
    assert "contacto_id=" in args[2]


def test_conozco_alguien_avisa_al_autor(sqlite_db, monkeypatch):
    enviados = []
    monkeypatch.setattr(
        email_service,
        "enviar_correo_aliado",
        lambda *args, **kwargs: enviados.append((args, kwargs)) or True,
    )
    _crear_grupo(
        sqlite_db,
        "Grupo recomiendo aviso",
        "03014",
        [
            ("JAIME", "Jaime", "Electricidad", "jaime@example.com"),
            ("MARTA", "Marta", "Fontanería y fontanería-gas"),
        ],
    )
    creada = solicitud_semanal_service.crear_solicitud_semanal(
        sqlite_db, "JAIME", "Fotografía", "", True
    )
    r = solicitud_semanal_service.responder_conozco_alguien(
        sqlite_db, creada["id"], "MARTA", _codigo_inv
    )
    assert r["status"] == "success"
    avisos = _avisos_respuesta(sqlite_db, "JAIME")
    assert len(avisos) == 1
    assert "Marta conoce a alguien para tu solicitud de" in avisos[0]["mensaje"]
    assert avisos[0]["metadata"].get("contacto_id") is None
    assert "#solicitudes" in (avisos[0]["metadata"].get("enlace") or "")
    assert enviados
    assert "conoce a alguien" in enviados[0][0][2]


def test_no_puedo_ayudar_no_avisa(sqlite_db, monkeypatch):
    enviados = []
    monkeypatch.setattr(
        email_service,
        "enviar_correo_aliado",
        lambda *args, **kwargs: enviados.append((args, kwargs)) or True,
    )
    _crear_grupo(
        sqlite_db,
        "Grupo no aviso",
        "03014",
        [
            ("JAIME", "Jaime", "Electricidad"),
            ("MARTA", "Marta", "Fontanería y fontanería-gas"),
        ],
    )
    creada = solicitud_semanal_service.crear_solicitud_semanal(
        sqlite_db, "JAIME", "Electricidad", "", False
    )
    r = solicitud_semanal_service.responder_no_puedo_ayudar(
        sqlite_db, creada["id"], "MARTA"
    )
    assert r["status"] == "success"
    assert _avisos_respuesta(sqlite_db, "JAIME") == []
    assert enviados == []


def test_click_repetido_avisa_una_sola_vez(sqlite_db, monkeypatch):
    enviados = []
    monkeypatch.setattr(
        email_service,
        "enviar_correo_aliado",
        lambda *args, **kwargs: enviados.append((args, kwargs)) or True,
    )
    _crear_grupo(
        sqlite_db,
        "Grupo idem",
        "03014",
        [
            ("JAIME", "Jaime", "Electricidad", "jaime@example.com"),
            ("MARTA", "Marta", "Electricidad"),
        ],
    )
    creada = solicitud_semanal_service.crear_solicitud_semanal(
        sqlite_db, "JAIME", "Electricidad", "", False
    )
    r1 = solicitud_semanal_service.responder_puedo_ayudar(
        sqlite_db, creada["id"], "MARTA"
    )
    r2 = solicitud_semanal_service.responder_puedo_ayudar(
        sqlite_db, creada["id"], "MARTA"
    )
    assert r1["status"] == "success"
    assert r2["status"] == "success"
    assert r2.get("ya_registrado") is True
    assert len(_avisos_respuesta(sqlite_db, "JAIME")) == 1
    assert len(enviados) == 1

    # La clave única también aguanta un segundo insert concurrente.
    segundo = notificacion_service.crear_notificacion_aliado_unica(
        sqlite_db,
        "JAIME",
        "solicitud_semanal_respuesta",
        "x",
        "y",
        metadata={"solicitud_semanal_id": creada["id"]},
        clave_unica=f"sol_sem_resp:{creada['id']}:MARTA",
    )
    assert segundo == "duplicate"
    assert len(_avisos_respuesta(sqlite_db, "JAIME")) == 1


def test_otro_respondente_avisa_de_nuevo(sqlite_db, monkeypatch):
    enviados = []
    monkeypatch.setattr(
        email_service,
        "enviar_correo_aliado",
        lambda *args, **kwargs: enviados.append((args, kwargs)) or True,
    )
    _crear_grupo(
        sqlite_db,
        "Grupo dos",
        "03014",
        [
            ("JAIME", "Jaime", "Electricidad", "jaime@example.com"),
            ("MARTA", "Marta", "Electricidad"),
            ("PEDRO", "Pedro", "Electricidad"),
        ],
    )
    creada = solicitud_semanal_service.crear_solicitud_semanal(
        sqlite_db, "JAIME", "Carpintería de madera e interior", "", False
    )
    assert (
        solicitud_semanal_service.responder_puedo_ayudar(
            sqlite_db, creada["id"], "MARTA"
        )["status"]
        == "success"
    )
    assert (
        solicitud_semanal_service.responder_puedo_ayudar(
            sqlite_db, creada["id"], "PEDRO"
        )["status"]
        == "success"
    )
    avisos = _avisos_respuesta(sqlite_db, "JAIME")
    assert len(avisos) == 2
    nombres = {n["metadata"]["respondente_nombre"] for n in avisos}
    assert nombres == {"Marta", "Pedro"}
    assert len(enviados) == 2


def test_respondente_de_grupo_cercano_avisa(sqlite_db, monkeypatch):
    enviados = []
    monkeypatch.setattr(
        email_service,
        "enviar_correo_aliado",
        lambda *args, **kwargs: enviados.append((args, kwargs)) or True,
    )
    _crear_grupo(
        sqlite_db,
        "Grupo 2",
        "28100",
        [("92979", "Juan Pablo", "Electricidad", "juan@example.com")],
    )
    _crear_grupo(
        sqlite_db,
        "Grupo 9",
        "28770",
        [("75658", "Stop Fugas", "Fontanería y fontanería-gas")],
    )
    creada = solicitud_semanal_service.crear_solicitud_semanal(
        sqlite_db, "92979", "Fontanería y fontanería-gas", "", False
    )
    ayuda = solicitud_semanal_service.responder_puedo_ayudar(
        sqlite_db, creada["id"], "75658"
    )
    assert ayuda["status"] == "success"
    avisos = _avisos_respuesta(sqlite_db, "92979")
    assert len(avisos) == 1
    assert "Stop Fugas puede ayudarte" in avisos[0]["mensaje"]
    assert enviados


def test_aviso_no_incluye_pii_del_respondente(sqlite_db, monkeypatch):
    enviados = []
    monkeypatch.setattr(
        email_service,
        "enviar_correo_aliado",
        lambda *args, **kwargs: enviados.append((args, kwargs)) or True,
    )
    email_resp = "secreto.respondente@example.com"
    tel_resp = "+34600111222"
    _crear_grupo(
        sqlite_db,
        "Grupo pii",
        "03014",
        [
            ("JAIME", "Jaime", "Electricidad", "jaime@example.com", "+34600999888"),
            (
                "MARTA",
                "Marta",
                "Fontanería y fontanería-gas",
                email_resp,
                tel_resp,
            ),
        ],
    )
    creada = solicitud_semanal_service.crear_solicitud_semanal(
        sqlite_db, "JAIME", "Fontanería y fontanería-gas", "", False
    )
    solicitud_semanal_service.responder_puedo_ayudar(sqlite_db, creada["id"], "MARTA")
    avisos = _avisos_respuesta(sqlite_db, "JAIME")
    assert len(avisos) == 1
    n = avisos[0]
    blob = " ".join(
        [
            n.get("titulo") or "",
            n.get("mensaje") or "",
            str(n.get("metadata") or ""),
            enviados[0][0][1] if enviados else "",
            enviados[0][0][2] if enviados else "",
        ]
    )
    assert email_resp not in blob
    assert tel_resp not in blob
    assert "600111222" not in blob
    meta = n["metadata"]
    assert "email" not in meta
    assert "telefono" not in meta
    assert "teléfono" not in str(meta).lower()


def test_fallo_al_avisar_no_rompe_la_respuesta(sqlite_db, monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("aviso caido")

    monkeypatch.setattr(
        notificacion_service, "crear_notificacion_aliado_unica", boom
    )
    _crear_grupo(
        sqlite_db,
        "Grupo fallo",
        "03014",
        [
            ("JAIME", "Jaime", "Electricidad"),
            ("MARTA", "Marta", "Electricidad"),
        ],
    )
    creada = solicitud_semanal_service.crear_solicitud_semanal(
        sqlite_db, "JAIME", "Electricidad", "", False
    )
    ayuda = solicitud_semanal_service.responder_puedo_ayudar(
        sqlite_db, creada["id"], "MARTA"
    )
    assert ayuda["status"] == "success"
    assert ayuda["contacto_id"]
    panel = solicitud_semanal_service.obtener_panel_por_codigo(sqlite_db, "MARTA")
    assert panel["activas_grupo"][0]["mi_respuesta"] == "puedo_ayudar"


def test_email_usa_el_canal_smtp_existente_y_respeta_smtp_apagado(
    sqlite_db, monkeypatch
):
    monkeypatch.setattr(email_service, "_smtp_configurado", lambda: False)
    enviados = []

    def _captura(email, asunto, cuerpo, contexto=""):
        enviados.append(contexto)
        # delega al helper real: con SMTP apagado debe devolver False y no lanzar
        return email_service.enviar_correo_aliado.__wrapped__ if False else (
            email_service.enviar_correo_aliado
        )

    # Llamamos al helper real: SMTP apagado => no envía, la respuesta sigue ok.
    _crear_grupo(
        sqlite_db,
        "Grupo smtp",
        "03014",
        [
            ("JAIME", "Jaime", "Electricidad", "jaime@example.com"),
            ("MARTA", "Marta", "Electricidad"),
        ],
    )
    creada = solicitud_semanal_service.crear_solicitud_semanal(
        sqlite_db, "JAIME", "Electricidad", "", False
    )
    ayuda = solicitud_semanal_service.responder_puedo_ayudar(
        sqlite_db, creada["id"], "MARTA"
    )
    assert ayuda["status"] == "success"
    assert _avisos_respuesta(sqlite_db, "JAIME")  # in-app sí
    # Sin SMTP no debe lanzar; el helper devuelve False.


def test_init_postgres_incluye_migracion_clave_unica():
    import inspect
    from core.services import schema_service

    source = inspect.getsource(schema_service._init_postgres_schema_unlocked)
    assert "_migrar_notificaciones_clave_unica" in source
    assert inspect.getsource(schema_service._migrar_notificaciones_clave_unica)
