"""Tests del Copiloto RUANA (motor determinista + endpoints)."""

import pytest

from RUANA.core.services import (
    copiloto_conocimiento as conocimiento,
    copiloto_jugadas,
    copiloto_service,
)
from RUANA.core.services.copiloto_llm import disponible as llm_disponible
from RUANA.web import app as app_module


# ---------------------------------------------------------------------------
# Bandas de score
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "score,banda",
    [
        (0, "COMPETENCIA"),
        (14, "COMPETENCIA"),
        (15, "EN RIESGO"),
        (48, "EN RIESGO"),
        (49, "EN RIESGO"),
        (50, "ESTABLE"),
        (199, "ESTABLE"),
        (200, "DESTACADO"),
        (349, "DESTACADO"),
        (350, "ÉLITE"),
        (500, "ÉLITE"),
    ],
)
def test_banda_de_score(score, banda):
    assert conocimiento.banda_de_score(score)["banda"] == banda


def test_banda_calcula_salto_al_siguiente_estado():
    datos = conocimiento.banda_de_score(48)
    assert datos["siguiente_banda"] == "ESTABLE"
    assert datos["puntos_al_siguiente"] == 2


def test_banda_tolera_valores_raros():
    assert conocimiento.banda_de_score(None)["banda"] == "COMPETENCIA"
    assert conocimiento.banda_de_score("no-es-un-numero")["banda"] == "COMPETENCIA"


# ---------------------------------------------------------------------------
# Clasificación de intención
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "texto,intencion",
    [
        ("hola", "saludo"),
        ("Hola, buenos días", "saludo"),
        ("¿cuánto cobra RUANA?", "apoyo_economico"),
        ("como invito a un fontanero", "invitar"),
        ("quiero subir mi score", "subir_score"),
        ("¿por qué me han quitado puntos?", "por_que_baje"),
        ("como voy este mes", "mi_estado"),
        ("como cierro un encargo", "encargo_cerrar"),
        ("necesito hacer una contraoferta", "negociacion"),
        ("en mi zona no hay nadie", "grupo_zona"),
        ("me van a retar por el score", "competencia"),
        ("como pago con bizum", "pagos"),
        ("mi perfil esta vacio", "perfil_catalogo"),
        ("¿qué es RUANA?", "que_es_ruana"),
        ("quiero hablar con una persona", "soporte_humano"),
        ("escríbeme un mensaje para invitar", "redactar_invitacion"),
        ("gracias", "gracias"),
    ],
)
def test_clasificar_intencion(texto, intencion):
    assert conocimiento.clasificar(texto) == intencion


def test_clasificar_texto_vacio_es_saludo():
    assert conocimiento.clasificar("") == "saludo"
    assert conocimiento.clasificar("   ") == "saludo"


def test_clasificar_fuera_de_catalogo_es_general():
    assert conocimiento.clasificar("ajsdkajsd qweqwe") == "general"


# ---------------------------------------------------------------------------
# Validador de cifras
# ---------------------------------------------------------------------------

def test_validador_acepta_cifras_del_contexto():
    permitido = copiloto_service.cifras_permitidas(
        '{"score": 48, "puntos": 5}', "+3 por responder rápido"
    )
    assert copiloto_service.validar_cifras("Estás en 48 y te faltan 5.", permitido) is True


def test_validador_rechaza_cifra_inventada():
    permitido = copiloto_service.cifras_permitidas('{"score": 48}')
    assert copiloto_service.validar_cifras("Te voy a dar 120 puntos.", permitido) is False


def test_validador_no_confunde_decimales():
    permitido = copiloto_service.cifras_permitidas("apoyo del 5 %")
    assert copiloto_service.validar_cifras("Se aporta un 5 %", permitido) is True
    assert copiloto_service.validar_cifras("Se aporta un 7,5 %", permitido) is False


# ---------------------------------------------------------------------------
# Motor de jugadas
# ---------------------------------------------------------------------------

def _contexto(**cambios):
    base = {
        "ok": True,
        "codigo": "A0001",
        "nombre": "Alex Acero",
        "oficio": "pintor",
        "codigo_postal": "03001",
        "estado": "activo",
        "estado_ruana": "EN RIESGO",
        "score": {
            "score": 48,
            "banda": "EN RIESGO",
            "puntos_al_siguiente": 2,
            "siguiente_banda": "ESTABLE",
            "delta_hoy": 0,
            "motivos_recientes": [],
        },
        "grupo": {
            "tiene_grupo": True,
            "nombre": "RUANA-03001",
            "num_aliados": 2,
            "num_oficios": 2,
            "oficios_faltantes": ["Electricista", "Fontanero", "Cerrajero"],
            "en_creacion": True,
            "recompensas_usadas": 3,
            "recompensas_max": 10,
        },
        "contactos": {
            "total": 0,
            "sin_importe": 0,
            "negociacion_a_medias": 0,
            "antiguos": [],
            "detalle": [],
        },
        "red": {"referidos": 1},
        "perfil": {"tiene_descripcion": True, "num_servicios": 2, "servicios": ["Pintura"]},
        "demanda": [],
        "competencia_activa": False,
        "limite_diario": 10,
    }
    for clave, valor in cambios.items():
        if isinstance(valor, dict) and isinstance(base.get(clave), dict):
            base[clave] = {**base[clave], **valor}
        else:
            base[clave] = valor
    return base


def test_jugada_de_invitar_cuando_la_zona_pide_el_oficio():
    contexto = _contexto(demanda=[{"oficio": "electricista", "peticiones": 3}])
    jugadas = copiloto_jugadas.calcular_jugadas(contexto)
    assert jugadas, "debe proponer al menos una jugada"
    invitar = [j for j in jugadas if j["id"] == "invitar_demanda"]
    assert invitar, "la demanda de la zona debe priorizar la invitación"
    assert invitar[0]["accion"]["oficio"] == "Electricista"
    assert "+5" in invitar[0]["impacto"]


def test_jugada_de_invitar_sin_demanda_usa_el_primer_oficio_faltante():
    jugadas = copiloto_jugadas.calcular_jugadas(_contexto())
    invitar = [j for j in jugadas if j["id"] in {"invitar_demanda", "invitar_oficio"}]
    assert invitar
    assert invitar[0]["accion"]["tipo"] == "invitar"


def test_sin_recompensas_no_propone_invitar():
    contexto = _contexto(grupo={"recompensas_usadas": 10, "recompensas_max": 10})
    jugadas = copiloto_jugadas.calcular_jugadas(contexto)
    assert not [j for j in jugadas if j["id"].startswith("invitar")]


def test_contacto_antiguo_sale_como_urgente():
    contexto = _contexto(
        contactos={
            "total": 1,
            "detalle": [
                {
                    "contacto_id": 7,
                    "rol": "profesional",
                    "estado": "iniciado",
                    "dias_abierto": 9,
                    "negociacion_completa": True,
                    "paso_pendiente": None,
                    "declaro_importe": True,
                    "es_urgente": False,
                }
            ],
        }
    )
    jugadas = copiloto_jugadas.calcular_jugadas(contexto)
    assert jugadas[0]["id"] == "contacto_abierto"
    assert jugadas[0]["urgencia"] == "alta"


def test_negociacion_a_medias_desbloquea_el_encargo():
    contexto = _contexto(
        contactos={
            "total": 1,
            "sin_importe": 1,
            "negociacion_a_medias": 1,
            "detalle": [
                {
                    "contacto_id": 9,
                    "rol": "profesional",
                    "estado": "iniciado",
                    "dias_abierto": 1,
                    "negociacion_completa": False,
                    "paso_pendiente": "Precio final",
                    "declaro_importe": False,
                    "es_urgente": False,
                }
            ],
        }
    )
    jugadas = copiloto_jugadas.calcular_jugadas(contexto)
    ids = [j["id"] for j in jugadas]
    assert "negociacion_paso" in ids
    assert "declarar_importe" in ids


def test_perfil_incompleto_es_una_jugada():
    contexto = _contexto(
        perfil={"tiene_descripcion": False, "num_servicios": 0, "servicios": []}
    )
    jugadas = copiloto_jugadas.calcular_jugadas(contexto)
    assert "completar_perfil" in [j["id"] for j in jugadas]


def test_sin_nada_pendiente_propone_la_jugada_del_dia():
    contexto = _contexto(
        grupo={"recompensas_usadas": 10, "recompensas_max": 10, "num_aliados": 7},
        perfil={"tiene_descripcion": True, "num_servicios": 1, "servicios": ["Pintura"]},
    )
    jugadas = copiloto_jugadas.calcular_jugadas(contexto)
    assert jugadas
    assert jugadas[0]["id"] == "visita_diaria"


def test_jugadas_nunca_devuelve_mas_de_tres():
    contexto = _contexto(
        demanda=[{"oficio": "electricista", "peticiones": 2}],
        perfil={"tiene_descripcion": False, "num_servicios": 0, "servicios": []},
        competencia_activa=True,
        contactos={
            "total": 1,
            "sin_importe": 1,
            "negociacion_a_medias": 1,
            "detalle": [
                {
                    "contacto_id": 1,
                    "rol": "profesional",
                    "estado": "iniciado",
                    "dias_abierto": 30,
                    "negociacion_completa": False,
                    "paso_pendiente": "Precio final",
                    "declaro_importe": False,
                    "es_urgente": False,
                }
            ],
        },
    )
    assert len(copiloto_jugadas.calcular_jugadas(contexto)) == 3


def test_jugadas_con_contexto_vacio_no_lanza():
    assert copiloto_jugadas.calcular_jugadas({}) == []
    assert copiloto_jugadas.calcular_jugadas(None) == []
    assert copiloto_jugadas.calcular_jugadas({"ok": False}) == []


# ---------------------------------------------------------------------------
# Redacción de invitación
# ---------------------------------------------------------------------------

def test_invitacion_menciona_la_demanda_real_de_la_zona():
    contexto = _contexto(demanda=[{"oficio": "electricista", "peticiones": 3}])
    texto = copiloto_service.redactar_invitacion(contexto, "Electricista")
    assert "3" in texto
    assert "electricista" in texto.lower()
    assert "5" in texto  # el Apoyo RUANA


def test_invitacion_no_inventa_peticiones_si_no_hay_demanda():
    contexto = _contexto()
    texto = copiloto_service.redactar_invitacion(contexto, "Fontanero")
    assert "fontanero" in texto.lower()
    assert "persona(s) pidiendo" not in texto


# ---------------------------------------------------------------------------
# Respuestas deterministas
# ---------------------------------------------------------------------------

def test_respuesta_de_score_cita_las_reglas_reales():
    texto, _ = copiloto_service._respuesta_determinista(_contexto(), "subir_score", "")
    assert "48" in texto
    assert "+3" in texto or "+5" in texto


def test_respuesta_de_soporte_ofrece_abrir_el_centro_de_comunicacion():
    _, accion = copiloto_service._respuesta_determinista(
        _contexto(), "soporte_humano", "quiero hablar con alguien"
    )
    assert accion["tipo"] == "soporte"


def test_respuesta_de_invitar_da_accion_con_oficio():
    contexto = _contexto(demanda=[{"oficio": "electricista", "peticiones": 2}])
    _, accion = copiloto_service._respuesta_determinista(contexto, "invitar", "")
    assert accion["tipo"] == "invitar"
    assert accion["oficio"]


# ---------------------------------------------------------------------------
# LLM: apagado por defecto y sin fugas de clave
# ---------------------------------------------------------------------------

def test_llm_apagado_por_defecto(monkeypatch):
    monkeypatch.delenv("RUANA_AI_ENABLED", raising=False)
    monkeypatch.delenv("RUANA_AI_API_KEY", raising=False)
    assert llm_disponible() is False


def test_llm_requiere_clave(monkeypatch):
    monkeypatch.setenv("RUANA_AI_ENABLED", "1")
    monkeypatch.delenv("RUANA_AI_API_KEY", raising=False)
    assert llm_disponible() is False


def test_llm_estado_publico_no_expone_la_clave(monkeypatch):
    monkeypatch.setenv("RUANA_AI_ENABLED", "1")
    monkeypatch.setenv("RUANA_AI_API_KEY", "sk-secreto-que-no-debe-salir")
    monkeypatch.setenv("RUANA_AI_PROVIDER", "deepseek")
    monkeypatch.setenv("RUANA_AI_MODEL", "deepseek-chat")
    estado = copiloto_service.copiloto_llm.estado_publico()
    assert estado["activa"] is True
    assert "sk-secreto" not in str(estado)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

class _FakeDB:
    """BD mínima para el contexto del copiloto."""

    backend = "sqlite"

    def __init__(self):
        class _Lock:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        self._lock = _Lock()
        self._aliado = {
            "codigo": "A0001",
            "nombre": "Alex Acero",
            "oficio": "pintor",
            "codigo_postal": "03001",
            "estado": "activo",
            "score": 48,
            "grupo_id": 1,
            "descripcion_servicio": "Pinto pisos",
            "competencia_activa": False,
        }

    def _connect(self):
        raise RuntimeError("sin BD en este test")

    def obtener_aliado_por_codigo(self, codigo):
        return dict(self._aliado) if codigo == "A0001" else None

    def score_a_estado(self, score):
        return "EN RIESGO"

    def contar_referidos_por_codigo(self, codigo):
        return 2

    def info_grupo_para_panel(self, grupo_id, codigo):
        return {
            "nombre": "RUANA-03001",
            "num_aliados": 2,
            "num_oficios": 2,
            "oficios_faltantes": ["Electricista", "Fontanero"],
            "en_creacion": True,
            "crecimiento": {"recompensas_obtenidas": 4, "recompensas_max": 10},
        }

    def obtener_contactos_abiertos_por_codigo(self, codigo):
        return []

    def listar_catalogo_servicios_aliado(self, codigo):
        return [{"nombre": "Pintura interior"}]


@pytest.fixture
def copiloto_client(monkeypatch):
    db = _FakeDB()
    monkeypatch.setattr(app_module, "get_db", lambda: db)
    return app_module.app.test_client()


def test_endpoint_estado_sin_sesion_da_401(copiloto_client):
    respuesta = copiloto_client.get("/api/aliado/copiloto/estado")
    assert respuesta.status_code == 401


def test_endpoint_estado_devuelve_jugadas(copiloto_client, session_headers):
    cabeceras = session_headers("aliado", "A0001")
    respuesta = copiloto_client.get("/api/aliado/copiloto/estado", headers=cabeceras)
    assert respuesta.status_code == 200
    datos = respuesta.get_json()
    assert datos["status"] == "success"
    assert isinstance(datos["jugadas"], list)
    assert datos["saludo"]
    assert datos["ia"]["activa"] is False


def test_endpoint_mensaje_responde_en_modo_determinista(copiloto_client, session_headers):
    cabeceras = session_headers("aliado", "A0001")
    respuesta = copiloto_client.post(
        "/api/aliado/copiloto/mensaje",
        json={"mensaje": "¿cuánto cobra RUANA?"},
        headers=cabeceras,
    )
    assert respuesta.status_code == 200
    datos = respuesta.get_json()
    assert datos["fuente"] == "reglas"
    assert "5" in datos["texto"]
    assert datos["intencion"] == "apoyo_economico"


def test_endpoint_mensaje_vacio_devuelve_400(copiloto_client, session_headers):
    cabeceras = session_headers("aliado", "A0001")
    respuesta = copiloto_client.post(
        "/api/aliado/copiloto/mensaje", json={"mensaje": ""}, headers=cabeceras
    )
    assert respuesta.status_code == 400


def test_endpoint_redactar_invitacion(copiloto_client, session_headers):
    cabeceras = session_headers("aliado", "A0001")
    respuesta = copiloto_client.post(
        "/api/aliado/copiloto/redactar",
        json={"tipo": "invitacion", "oficio": "Electricista"},
        headers=cabeceras,
    )
    assert respuesta.status_code == 200
    datos = respuesta.get_json()
    assert datos["status"] == "success"
    assert "electricista" in datos["texto"].lower()


# ---------------------------------------------------------------------------
# Ficha del producto: hechos que el copiloto sí puede afirmar
# ---------------------------------------------------------------------------

def test_ficha_producto_incluye_el_apoyo_y_las_bandas():
    ficha = conocimiento.ficha_producto()
    assert "5 %" in ficha
    assert "ÉLITE" in ficha
    assert "Recibir un contacto no cuesta nada" in ficha


def test_el_apoyo_del_5_pasa_el_validador_de_cifras():
    """Regresión: el modelo debe poder decir «5 %» sin que se descarte."""
    permitido = copiloto_service.cifras_permitidas(
        conocimiento.tabla_puntos_texto(), conocimiento.ficha_producto()
    )
    assert copiloto_service.validar_cifras(
        "Solo al cerrar el encargo se aporta el 5 % del importe.", permitido
    ) is True


def test_el_prompt_del_modelo_lleva_los_datos_del_aliado_y_la_ficha():
    prompt = copiloto_service._prompt_usuario(_contexto(), "¿cómo voy?", "mi_estado")
    assert "DATOS DEL ALIADO" in prompt
    assert "FICHA DEL PRODUCTO" in prompt
    assert "48" in prompt  # el score real del aliado


def test_los_numeros_pequenos_no_invalidan_una_respuesta():
    """Regresión: «1 encargo» o «2 o 3 profesionales» no son cifras de cuenta."""
    permitido = copiloto_service.cifras_permitidas(conocimiento.ficha_producto())
    assert copiloto_service.validar_cifras(
        "Si tienes 1 encargo abierto, responde en menos de 1 hora a 2 o 3 clientes.",
        permitido,
    ) is True


def test_una_cifra_grande_inventada_sigue_bloqueada():
    permitido = copiloto_service.cifras_permitidas(conocimiento.ficha_producto())
    fuera = copiloto_service.cifras_no_permitidas("Vas a ganar 180 puntos.", permitido)
    assert fuera == ["180"]
