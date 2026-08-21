#!/usr/bin/env python3
"""Siembra una red de demostración premium para capturas de landing.

Uso previsto: entorno local/CI de capturas. No es un flujo de producción.
Crea aliados, catálogos, negociación, pagos, notificaciones y una competencia.
"""
from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
RUANA_ROOT = ROOT / "RUANA"
LANDING_DIR = Path(__file__).resolve().parent
STATE_PATH = LANDING_DIR / ".demo-state.json"
DB_PATH = Path(os.environ.get("RUANA_LANDING_DB", "/tmp/ruana-landing.db"))
PIN = "2468"

ALIADOS = [
    {
        "key": "elena",
        "nombre": "Elena Navarro",
        "marca": "Navarro Instalaciones",
        "oficio": "Electricidad",
        "codigo_postal": "28001",
        "email": "elena.navarro@navarroinstalaciones.es",
        "telefono": "+34620110401",
        "descripcion": "Instalaciones eléctricas residenciales y de oficinas en el barrio de Salamanca. Cuadros, recargas y certificación.",
        "score": 372,
        "color": (36, 72, 92),
        "catalogo": [
            ("Instalación de cuadro eléctrico residencial hasta 20 circuitos, con certificación.", "280 €"),
            ("Punto de recarga para vehículo eléctrico en garaje comunitario o particular.", "420 €"),
            ("Revisión y legalización de instalación eléctrica de vivienda.", "190 €"),
        ],
    },
    {
        "key": "marcos",
        "nombre": "Marcos Vidal",
        "marca": "Vidal Fontanería",
        "oficio": "Fontanería y fontanería-gas",
        "codigo_postal": "28001",
        "email": "marcos@vidalfontaneria.es",
        "telefono": "+34620110402",
        "descripcion": "Averías urgentes, reformas de baño y calderas en el centro de Madrid.",
        "score": 248,
        "color": (62, 92, 78),
        "catalogo": [
            ("Reparación de fuga en vivienda con localización y sellado.", "95 €"),
            ("Sustitución de sanitarios y grifería en baño completo.", "340 €"),
        ],
        "invited_by": "elena",
    },
    {
        "key": "lucia",
        "nombre": "Lucía Herrera",
        "marca": "Herrera Color",
        "oficio": "Pintura y decoración",
        "codigo_postal": "28001",
        "email": "lucia@herreracolor.es",
        "telefono": "+34620110403",
        "descripcion": "Pintura interior, lacados y acabados decorativos para viviendas y locales.",
        "score": 186,
        "color": (122, 78, 58),
        "catalogo": [
            ("Pintura completa de vivienda (manos de fondo y acabado).", "12 €/m²"),
            ("Lacado de puertas y carpintería interior.", "45 €/ud"),
        ],
        "invited_by": "elena",
    },
    {
        "key": "andres",
        "nombre": "Andrés Molina",
        "marca": "Taller Molina",
        "oficio": "Carpintería de madera e interior",
        "codigo_postal": "28001",
        "email": "andres@tallermolina.es",
        "telefono": "+34620110404",
        "descripcion": "Carpintería a medida: armarios, revestimientos y restauración de puertas.",
        "score": 264,
        "color": (92, 64, 42),
        "catalogo": [
            ("Armario empotrado a medida con frente liso.", "780 €"),
            ("Restauración y ajuste de puerta de paso.", "160 €"),
        ],
    },
    {
        "key": "sofia",
        "nombre": "Sofía Ríos",
        "marca": "Clima Ríos",
        "oficio": "Climatización y calefacción",
        "codigo_postal": "28001",
        "email": "sofia@climarios.es",
        "telefono": "+34620110405",
        "descripcion": "Climatización por conductos, splits y mantenimiento de calderas.",
        "score": 154,
        "color": (48, 88, 118),
        "catalogo": [
            ("Instalación de split 1x1 con carga de gas incluida.", "890 €"),
            ("Revisión anual de caldera y circuito de calefacción.", "120 €"),
        ],
        "invited_by": "elena",
    },
    {
        "key": "javier",
        "nombre": "Javier Ortega",
        "marca": "Ortega Cerrajería",
        "oficio": "Cerrajería",
        "codigo_postal": "28001",
        "email": "javier@ortegacerrageria.es",
        "telefono": "+34620110406",
        "descripcion": "Aperturas, cambios de bombín y refuerzo de accesos en Salamanca y Retiro.",
        "score": 132,
        "color": (78, 78, 88),
        "catalogo": [
            ("Apertura de vivienda sin rotura, 24 horas.", "75 €"),
            ("Cambio de bombín de alta seguridad.", "145 €"),
        ],
    },
    {
        "key": "carmen",
        "nombre": "Carmen Ruiz",
        "marca": "Ruiz Acabados",
        "oficio": "Limpieza y acabados",
        "codigo_postal": "28001",
        "email": "carmen@ruizacabados.es",
        "telefono": "+34620110407",
        "descripcion": "Limpieza de fin de obra y mantenimiento de oficinas y comunidades.",
        "score": 218,
        "color": (86, 58, 92),
        "catalogo": [
            ("Limpieza de fin de obra en vivienda de hasta 90 m².", "260 €"),
            ("Mantenimiento quincenal de oficina (4 horas).", "110 €"),
        ],
    },
    {
        "key": "pablo",
        "nombre": "Pablo Iglesias",
        "marca": "Iglesias Obra",
        "oficio": "Albañilería y obra",
        "codigo_postal": "28001",
        "email": "pablo@iglesiasobra.es",
        "telefono": "+34620110408",
        "descripcion": "Reformas de albañilería, tabiquería y alicatados en el ensanche.",
        "score": 12,
        "color": (98, 52, 48),
        "catalogo": [
            ("Alicatado de baño completo con junta fina.", "38 €/m²"),
        ],
    },
    {
        "key": "hugo",
        "nombre": "Hugo Serrano",
        "marca": "Serrano Reformas",
        "oficio": "Albañilería y obra",
        "codigo_postal": "28001",
        "email": "hugo@serranoreformas.es",
        "telefono": "+34620110409",
        "descripcion": "Obra menor, recrecidos y preparación de superficies para reforma.",
        "score": 88,
        "color": (58, 72, 64),
        "catalogo": [
            ("Tabique de pladur con aislamiento incluido.", "52 €/m²"),
        ],
    },
    {
        "key": "nuria",
        "nombre": "Núria Soler",
        "marca": "Soler Elèctrics",
        "oficio": "Electricidad",
        "codigo_postal": "08001",
        "email": "nuria@solerelectrics.cat",
        "telefono": "+34620110501",
        "descripcion": "Instalaciones eléctricas en Ciutat Vella y el Eixample.",
        "score": 341,
        "color": (42, 82, 96),
        "catalogo": [
            ("Ampliación de circuitos en local comercial.", "310 €"),
        ],
    },
    {
        "key": "jordi",
        "nombre": "Jordi Puig",
        "marca": "Puig Aigua",
        "oficio": "Fontanería y fontanería-gas",
        "codigo_postal": "08001",
        "email": "jordi@puigaigua.cat",
        "telefono": "+34620110502",
        "descripcion": "Fontanería de comunidades y locales en el centro de Barcelona.",
        "score": 201,
        "color": (48, 96, 88),
        "catalogo": [
            ("Sustitución de bajante en tramo comunitario.", "540 €"),
        ],
    },
    {
        "key": "marta",
        "nombre": "Marta Vives",
        "marca": "Vives Estudi",
        "oficio": "Pintura y decoración",
        "codigo_postal": "08001",
        "email": "marta@vivesestudi.cat",
        "telefono": "+34620110503",
        "descripcion": "Color, papel y acabados para viviendas del Eixample.",
        "score": 41,
        "color": (118, 72, 86),
        "catalogo": [
            ("Papel pintado de diseño en salón o dormitorio.", "28 €/m²"),
        ],
    },
]


def configure_env(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    os.environ["RUANA_ENV"] = "dev"
    os.environ["FLASK_SECRET_KEY"] = "landing-screenshots-secret-key-24"
    os.environ["RUANA_DB_PATH"] = str(db_path)
    os.environ["DATABASE_URL"] = ""
    os.environ["SUPABASE_URL"] = ""
    os.environ["SUPABASE_SERVICE_ROLE_KEY"] = ""
    os.environ["RUANA_ADMIN_CREDENTIALS_PATH"] = str(LANDING_DIR / "admin_credentials.landing.json")
    os.environ["RUANA_ALLOW_LOCAL_UPLOADS"] = "1"
    os.environ["RUANA_STRIPE_PAYMENTS_ENABLED"] = "0"
    os.environ["RUANA_STRIPE_MODE"] = ""
    sys.path.insert(0, str(RUANA_ROOT))


def _font(size: int):
    for candidate in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ):
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def make_avatar(nombre: str, color: tuple[int, int, int]) -> bytes:
    size = 512
    img = Image.new("RGB", (size, size), color)
    draw = ImageDraw.Draw(img)
    draw.ellipse((18, 18, size - 18, size - 18), outline=(255, 255, 255), width=10)
    parts = [p[0] for p in nombre.split() if p]
    initials = "".join(parts[:2]).upper()
    font = _font(180)
    bbox = draw.textbbox((0, 0), initials, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((size - tw) / 2, (size - th) / 2 - 12), initials, fill=(250, 250, 247), font=font)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def make_receipt() -> bytes:
    img = Image.new("RGB", (900, 1200), (248, 247, 242))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((48, 48, 852, 1152), radius=24, outline=(40, 48, 56), width=2)
    font_lg = _font(42)
    font_sm = _font(28)
    draw.text((90, 90), "Comprobante de transferencia", fill=(28, 32, 38), font=font_lg)
    draw.text((90, 180), "Apoyo RUANA · 31,20 €", fill=(28, 32, 38), font=font_sm)
    draw.text((90, 240), "Concepto: RUANA-ENC-1842", fill=(90, 94, 100), font=font_sm)
    draw.text((90, 300), "Ordenante: Ruiz Acabados", fill=(90, 94, 100), font=font_sm)
    draw.text((90, 360), "Fecha: 18 ago 2026", fill=(90, 94, 100), font=font_sm)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class Api:
    def __init__(self, client):
        self.client = client

    def _headers(self, session_id: str | None = None, json_body: bool = True) -> dict:
        headers = {}
        if json_body:
            headers["Content-Type"] = "application/json"
        if session_id:
            headers["X-Ruana-Session-Id"] = session_id
        return headers

    def _assert_status(self, resp, expected, label):
        allowed = expected if isinstance(expected, tuple) else (expected,)
        if resp.status_code not in allowed:
            raise RuntimeError(f"{label} -> {resp.status_code}: {resp.get_data(as_text=True)}")
        return resp.get_json() or {}

    def post(self, path, payload=None, session_id=None, expected=200):
        resp = self.client.post(
            path,
            data=json.dumps(payload or {}),
            headers=self._headers(session_id),
        )
        return self._assert_status(resp, expected, f"POST {path}")

    def put(self, path, payload, session_id, expected=200):
        resp = self.client.put(
            path,
            data=json.dumps(payload),
            headers=self._headers(session_id),
        )
        return self._assert_status(resp, expected, f"PUT {path}")

    def post_files(self, path, files: dict, form: dict | None = None, session_id=None, expected=200):
        data = dict(form or {})
        data.update(files)
        resp = self.client.post(path, data=data, headers=self._headers(session_id, json_body=False))
        return self._assert_status(resp, expected, f"POST {path} files")


def login_aliado(api: Api, codigo: str) -> str:
    first = api.post("/api/aliado/login", {"codigo": codigo, "pin": PIN}, expected=(200, 201, 401))
    if first.get("session_id"):
        return first["session_id"]
    if first.get("pin_setup_required"):
        created = api.post(
            "/api/aliado/pin/crear",
            {
                "setup_token": first["setup_token"],
                "pin": PIN,
                "pin_confirmacion": PIN,
            },
            expected=(200, 201),
        )
        if created.get("session_id"):
            return created["session_id"]
    later = api.post("/api/aliado/login", {"codigo": codigo, "pin": PIN}, expected=(200, 201))
    if not later.get("session_id"):
        raise RuntimeError(f"No se pudo crear sesión para {codigo}: {later}")
    return later["session_id"]


def admin_login(api: Api) -> str:
    body = api.post(
        "/api/admin/validar",
        {"codigo": "ADMIN001", "password": "ADMIN001"},
        expected=200,
    )
    if not body.get("session_id"):
        raise RuntimeError(f"Admin login falló: {body}")
    return body["session_id"]


def seed() -> dict:
    configure_env(DB_PATH)
    from web.app import app  # noqa: E402
    from web.limiter import limiter  # noqa: E402
    from core.db_manager import get_db  # noqa: E402
    from core.services import notificacion_service  # noqa: E402

    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    limiter.enabled = False
    client = app.test_client()
    api = Api(client)
    db = get_db()

    admin_sid = admin_login(api)
    campana = api.post(
        "/api/admin/invitacion-campanas",
        {
            "codigo": "RUANA-SALAMANCA",
            "nombre": "Red Salamanca",
            "codigo_postal": "28001",
            "max_usos": 40,
        },
        session_id=admin_sid,
        expected=(200, 201),
    )
    if campana.get("status") not in (None, "success") and not campana.get("campana"):
        print("[landing] aviso campaña:", campana)

    created: dict[str, dict] = {}
    sessions: dict[str, str] = {}

    for spec in ALIADOS:
        payload = {
            "nombre": spec["nombre"],
            "marca": spec["marca"],
            "oficio": spec["oficio"],
            "oficio_principal": spec["oficio"],
            "codigo_postal": spec["codigo_postal"],
            "email": spec["email"],
            "telefono": spec["telefono"],
            "descripcion": spec["descripcion"],
            "acepta_privacidad_y_terminos": True,
        }
        invitador = spec.get("invited_by")
        if invitador and invitador in sessions:
            inv = api.post("/api/invitaciones/crear", {}, session_id=sessions[invitador], expected=(200, 201))
            codigo_inv = inv.get("codigo") or (inv.get("invitacion") or {}).get("codigo")
            if codigo_inv:
                payload["codigo_invitacion"] = codigo_inv
        elif spec["codigo_postal"] == "28001":
            payload["codigo_invitacion"] = "RUANA-SALAMANCA"

        body = api.post("/api/aliados/registrar", payload, expected=(200, 201))
        codigo = body.get("codigo")
        if not codigo:
            raise RuntimeError(f"Registro falló para {spec['nombre']}: {body}")
        created[spec["key"]] = {**spec, "codigo": codigo, "registro": body}
        print(f"[landing] {spec['nombre']} -> {codigo} estado={body.get('estado')}")

        if body.get("estado") == "en_espera":
            continue
        sid = login_aliado(api, codigo)
        sessions[spec["key"]] = sid
        avatar = make_avatar(spec["nombre"], spec["color"])
        api.post_files(
            f"/api/aliados/{codigo}/foto-perfil",
            {"archivo": (io.BytesIO(avatar), "perfil.jpg", "image/jpeg")},
            session_id=sid,
            expected=(200, 201),
        )
        for idx, (descripcion, precio) in enumerate(spec.get("catalogo") or [], start=1):
            api.put(
                f"/api/aliados/{codigo}/catalogo-servicios/{idx}",
                {"descripcion": descripcion, "precio": precio},
                session_id=sid,
            )

    conn = db._connect()
    try:
        for spec in created.values():
            conn.execute(
                "UPDATE aliados SET score = ?, creado_en = ? WHERE codigo = ?",
                (int(spec["score"]), "2025-11-14 10:00:00", spec["codigo"]),
            )
        conn.execute("UPDATE grupos SET nombre = ? WHERE id = 1", ("Salamanca · Plaza Mayor",))
        conn.execute("UPDATE grupos SET nombre = ? WHERE id = 2", ("Salamanca · Recoletos",))
        conn.execute("UPDATE grupos SET nombre = ? WHERE id = 3", ("Ciutat Vella · Hogar",))
        conn.commit()
    finally:
        conn.close()

    elena = created["elena"]
    marcos = created["marcos"]
    carmen = created["carmen"]
    pablo = created["pablo"]

    elena_sid = sessions["elena"]
    marcos_sid = sessions["marcos"]
    carmen_sid = sessions["carmen"]

    contact_neg = api.post(
        "/api/contactos",
        {
            "profesional_codigo": elena["codigo"],
            "servicio": "Cuadro eléctrico y puntos de recarga",
            "motivo_contacto": "Reforma de oficina en Serrano",
        },
        session_id=marcos_sid,
        expected=(200, 201),
    )
    neg_id = contact_neg.get("id") or (contact_neg.get("contacto") or {}).get("id")
    if not neg_id:
        raise RuntimeError(f"No se creó el contacto de negociación: {contact_neg}")
    api.post(f"/api/contactos/{neg_id}/aceptar", {}, session_id=elena_sid, expected=(200, 201))
    api.post(f"/api/contactos/{neg_id}/trabajo-en-progreso", {}, session_id=elena_sid, expected=(200, 201))
    api.post(
        f"/api/contactos/{neg_id}/negociacion/proponer-completa",
        {
            "servicio": "Renovación de cuadro eléctrico y dos puntos de recarga en garaje",
            "fecha": "2026-09-12",
            "hora": "09:30",
            "direccion": "Calle de Serrano 44, 3º izq., 28001 Madrid",
            "observaciones": "Acceso por rampa de vecinos. Coordinar con el administrador de la finca.",
            "precio_catalogo": "1.150 €",
        },
        session_id=marcos_sid,
        expected=(200, 201),
    )
    for campo in ("servicio", "fecha", "hora", "direccion"):
        api.post(
            f"/api/contactos/{neg_id}/negociacion/aceptar",
            {"campo": campo},
            session_id=elena_sid,
            expected=(200, 201),
        )

    contact_pago = api.post(
        "/api/contactos",
        {
            "profesional_codigo": carmen["codigo"],
            "servicio": "Limpieza de fin de obra",
            "motivo_contacto": "Entrega de oficina",
        },
        session_id=elena_sid,
        expected=(200, 201),
    )
    pago_id = contact_pago.get("id") or (contact_pago.get("contacto") or {}).get("id")
    if not pago_id:
        raise RuntimeError(f"No se creó el contacto de pago: {contact_pago}")
    api.post(f"/api/contactos/{pago_id}/aceptar", {}, session_id=carmen_sid, expected=(200, 201))
    api.post(f"/api/contactos/{pago_id}/trabajo-en-progreso", {}, session_id=carmen_sid, expected=(200, 201))
    api.post(
        f"/api/contactos/{pago_id}/negociacion/proponer-completa",
        {
            "servicio": "Limpieza de fin de obra en oficina de 85 m²",
            "fecha": "2026-08-18",
            "hora": "08:00",
            "direccion": "Calle de Serrano 44, Madrid",
            "observaciones": "Incluye cristales y retirada de restos de pintura.",
            "precio_catalogo": "260 €",
        },
        session_id=elena_sid,
        expected=(200, 201),
    )
    for campo in ("servicio", "fecha", "hora", "direccion", "observaciones"):
        api.post(
            f"/api/contactos/{pago_id}/negociacion/aceptar",
            {"campo": campo},
            session_id=carmen_sid,
            expected=(200, 201),
        )
    cierre = api.post(
        f"/api/contactos/{pago_id}/declarar-importe",
        {"parte": "solicitante", "importe": 260, "moneda": "EUR"},
        session_id=elena_sid,
        expected=(200, 201),
    )
    print("[landing] cierre pago:", cierre.get("estado") or cierre)

    api.post(
        "/api/admin/metodos-pago",
        {"bizum_num": "642868261", "iban": "ES12 2100 0418 4502 0005 1332"},
        session_id=admin_sid,
        expected=(200, 201),
    )
    receipt = make_receipt()
    api.post_files(
        f"/api/contactos/{pago_id}/comprobante-apoyo",
        {"archivo": (io.BytesIO(receipt), "comprobante-apoyo.png", "image/png")},
        form={"comentario": "Transferencia realizada el 18 de agosto. Concepto RUANA-ENC-1842."},
        session_id=carmen_sid,
        expected=(200, 201),
    )

    if pablo.get("codigo"):
        result = db._iniciar_competencia_si_procede(pablo["codigo"])
        print("[landing] competencia:", result)

    notificacion_service.crear_notificacion_aliado(
        db,
        elena["codigo"],
        "score_up",
        "Tu Score RUANA ha subido",
        "Has ganado +8 puntos por completar un encargo con Apoyo RUANA validado.",
        {"delta": 8, "motivo": "encargo_completado_apoyo_pagado"},
    )
    notificacion_service.crear_notificacion_aliado(
        db,
        elena["codigo"],
        "red",
        "Nuevo aliado en tu red",
        "Lucía Herrera se ha incorporado a tu grupo de Salamanca a través de tu invitación.",
        {},
    )
    notificacion_service.crear_notificacion_aliado(
        db,
        elena["codigo"],
        "grupo",
        "Tu grupo sigue cubriendo oficios",
        "El grupo de CP 28001 ya representa 8 oficios. Invitar climatización avanzada o jardinería aceleraría el crecimiento.",
        {},
    )
    notificacion_service.crear_notificacion_aliado(
        db,
        elena["codigo"],
        "encargo",
        "Negociación pendiente de precio",
        "Marcos Vidal espera tu confirmación del importe en el encargo de Serrano 44.",
        {"contacto_id": neg_id},
    )

    state = {
        "db_path": str(DB_PATH),
        "pin": PIN,
        "admin": {"codigo": "ADMIN001", "password": "ADMIN001"},
        "hero": {"key": "elena", "codigo": elena["codigo"], "nombre": elena["nombre"]},
        "negociacion_contacto_id": neg_id,
        "pago_contacto_id": pago_id,
        "aliados": {k: {"codigo": v["codigo"], "nombre": v["nombre"], "oficio": v["oficio"]} for k, v in created.items()},
    }
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[landing] estado escrito en {STATE_PATH}")
    return state


if __name__ == "__main__":
    seed()
