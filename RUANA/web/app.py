#!/usr/bin/env python3
"""
RUANA Dashboard Web Server
Servidor Flask para servir el dashboard y API
"""

from flask import Flask, render_template, jsonify, send_from_directory, request, session, redirect, url_for
import json
from pathlib import Path
from datetime import datetime, timedelta
import sys
import os
import time
import secrets
import threading
import jwt
from functools import wraps
from urllib.parse import quote

try:
    from flask_cors import CORS
except ImportError:
    CORS = None

# Agregar parent directory al path para imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Importar gestor de base de datos (y ruta ?nica de SQLite)
from core.db_manager import get_db, DB_PATH, RUANA_CODIGO_INVITACION_REGEX
from core.settings import get_settings
from core.storage_manager import upload_ruana_file, upload_foto_perfil_file

# Obtener ruta absoluta de la carpeta web
web_dir = Path(__file__).parent.absolute()
settings = get_settings()

app = Flask(__name__, 
            static_folder=str(web_dir / 'static'),
            static_url_path='/static',
            template_folder=str(web_dir))

app.secret_key = settings.flask_secret_key

# Cookie de sesi?n segura (aliado y admin): httpOnly evita acceso desde JS (XSS), SameSite limita CSRF
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# CORS: permite que el frontend en otro puerto/origen llame al backend
if CORS is not None:
    CORS(app)

# Sesi?n admin: expiraci?n en segundos (1 hora)
ADMIN_SESSION_EXPIRES_SECONDS = int(os.environ.get('RUANA_ADMIN_SESSION_EXPIRES', 3600))

# Sesi?n aliado: expiraci?n (misma duraci?n que admin por defecto)
ALIADO_SESSION_EXPIRES_SECONDS = int(os.environ.get('RUANA_ALIADO_SESSION_EXPIRES', 3600))

# ---------- Store de sesiones server-side (evita sesiones cruzadas entre pestañas) ----------
# Cada login genera un session_id (JWT firmado) que el frontend envía en X-Ruana-Session-Id.
# El JWT permite validar sesión en cualquier instancia de Cloud Run sin memoria compartida.
_RUANA_SESSION_STORE = {}
_RUANA_SESSION_REVOKED = set()
_RUANA_SESSION_LOCK = threading.Lock()
RUANA_SESSION_HEADER = 'X-Ruana-Session-Id'


def _ruana_session_from_jwt(token):
    """Decodifica un JWT de sesión RUANA. None si es inválido o expiró."""
    if not token:
        return None
    try:
        payload = jwt.decode(token, app.secret_key, algorithms=['HS256'])
        if float(payload.get('exp', 0)) <= time.time():
            return None
        return {
            'tipo': payload.get('tipo'),
            'codigo': (payload.get('codigo') or '').strip(),
            'expires_at': float(payload.get('exp', 0)),
            'permisos': list(payload.get('permisos') or []),
        }
    except Exception:
        return None


def _get_ruana_session():
    """
    Lee X-Ruana-Session-Id del request y devuelve la sesión si existe y no expiró.
    Acepta JWT firmado (multi-instancia) o entradas legacy en memoria (tests).
    """
    sid = (request.headers.get(RUANA_SESSION_HEADER) or '').strip()
    if not sid:
        return None
    with _RUANA_SESSION_LOCK:
        if sid in _RUANA_SESSION_REVOKED:
            return None
        data = _RUANA_SESSION_STORE.get(sid)
    if data and float(data.get('expires_at', 0)) > time.time():
        return data
    return _ruana_session_from_jwt(sid)


def _ruana_session_create(tipo, codigo, expires_at, permisos=None):
    """Crea una sesión y devuelve un JWT como session_id (nuevo id por login)."""
    payload = {
        'tipo': tipo,
        'codigo': (codigo or '').strip(),
        'exp': int(expires_at),
    }
    if permisos is not None:
        payload['permisos'] = list(permisos)
    token = jwt.encode(payload, app.secret_key, algorithm='HS256')
    if isinstance(token, bytes):
        token = token.decode('utf-8')
    with _RUANA_SESSION_LOCK:
        _RUANA_SESSION_STORE[token] = {
            'tipo': tipo,
            'codigo': (codigo or '').strip(),
            'expires_at': float(expires_at),
            'permisos': list(permisos) if permisos is not None else [],
        }
    return token


def _ruana_session_invalidate(session_id):
    """Invalida una sesión por su id."""
    sid = (session_id or '').strip()
    if not sid:
        return
    with _RUANA_SESSION_LOCK:
        _RUANA_SESSION_STORE.pop(sid, None)
        _RUANA_SESSION_REVOKED.add(sid)


def _admin_session_valid():
    """True si hay sesi?n admin v?lida (store por header o JWT). No se usa cookie para evitar cruce entre pestañas."""
    s = _get_ruana_session()
    if s and s.get('tipo') == 'admin' and s.get('codigo'):
        return True
    payload = _admin_jwt_payload()
    return bool(payload and payload.get('admin_codigo'))

def _admin_permisos():
    """Lista de permisos del admin actual (store por header o JWT). Vac?a si no hay sesi?n."""
    s = _get_ruana_session()
    if s and s.get('tipo') == 'admin' and isinstance(s.get('permisos'), list):
        return s['permisos']
    payload = _admin_jwt_payload()
    if payload and isinstance(payload.get('permisos'), list):
        return payload['permisos']
    return []

def _admin_puede_escribir():
    """True si el admin tiene permiso de escritura o configuraci?n."""
    p = _admin_permisos()
    return 'escribir' in p or 'configurar' in p

def _admin_codigo():
    """Código del admin en sesión (store por header) o JWT. Vacío si no hay sesión."""
    s = _get_ruana_session()
    if s and s.get('tipo') == 'admin':
        return (s.get('codigo') or '').strip()
    payload = _admin_jwt_payload()
    return (payload.get('admin_codigo') or '') if payload else ''

def _admin_jwt_payload():
    """Si hay Authorization: Bearer <jwt> v?lido, devuelve el payload; si no, None."""
    auth = request.headers.get('Authorization')
    if not auth or not auth.startswith('Bearer '):
        return None
    token = auth[7:].strip()
    if not token:
        return None
    try:
        payload = jwt.decode(token, app.secret_key, algorithms=['HS256'])
        if payload.get('exp', 0) <= time.time():
            return None
        return payload
    except Exception:
        return None

def require_admin(f):
    """Decorator: exige sesi?n admin o JWT v?lido. Devuelve 401 si no."""
    @wraps(f)
    def wrapped(*args, **kwargs):
        if _admin_session_valid():
            return f(*args, **kwargs)
        payload = _admin_jwt_payload()
        if payload and payload.get('admin_codigo'):
            return f(*args, **kwargs)
        return jsonify({'status': 'error', 'message': 'Sesi?n admin expirada o no autorizado'}), 401
    return wrapped


def require_admin_escritura(f):
    """Decorator: exige sesi?n admin Y permiso de escritura/configurar. 401 si no admin, 403 si solo lectura."""
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not _admin_session_valid() and not (_admin_jwt_payload() and _admin_jwt_payload().get('admin_codigo')):
            return jsonify({'status': 'error', 'message': 'Sesi?n admin expirada o no autorizado'}), 401
        if not _admin_puede_escribir():
            return jsonify({'status': 'error', 'message': 'Sin permiso de escritura (solo lectura)'}), 403
        return f(*args, **kwargs)
    return wrapped


# ---------- S-04: Middleware de autorizaci?n admin ----------
# Todas las peticiones a /api/admin/* (salvo logout y validar) exigen sesi?n o JWT v?lido.
_ADMIN_PUBLIC_PATHS = ('/api/admin/logout', '/api/admin/validar')

@app.before_request
def admin_auth_middleware():
    """S-04: Middleware de autorizaci?n. Bloquea acceso a /api/admin/* sin sesi?n/JWT v?lido."""
    path = request.path.rstrip('/')
    if not path.startswith('/api/admin/'):
        return None
    for allowed in _ADMIN_PUBLIC_PATHS:
        if path == allowed.rstrip('/') or path.startswith(allowed.rstrip('/') + '/'):
            return None
    if _admin_session_valid():
        return None
    if _admin_jwt_payload() and _admin_jwt_payload().get('admin_codigo'):
        return None
    resp = jsonify({'status': 'error', 'message': 'Sesi?n admin expirada o no autorizado'})
    resp.status_code = 401
    return resp


# ---------- Sesi?n aliado (store por header X-Ruana-Session-Id; evita cruce entre pestañas) ----------
def _aliado_session_valid():
    """True si hay sesi?n de aliado v?lida en el store (header X-Ruana-Session-Id)."""
    s = _get_ruana_session()
    return bool(s and s.get('tipo') == 'aliado' and s.get('codigo'))


def _aliado_codigo():
    """C?digo del aliado autenticado (store por header). None si no hay sesi?n v?lida."""
    s = _get_ruana_session()
    if s and s.get('tipo') == 'aliado':
        return (s.get('codigo') or '').strip()
    return None


def require_aliado(f):
    """Decorator: exige sesi?n de aliado v?lida. 401 si no. La vista debe usar _aliado_codigo() para el c?digo."""
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not _aliado_session_valid():
            return jsonify({'status': 'error', 'message': 'Sesión expirada o no autorizado. Inicia sesión con tu código.'}), 401
        return f(*args, **kwargs)
    return wrapped


def _forbidden_unless_admin_or_aliado_self(codigo):
    """None si admin autenticado o aliado consultando su propio código; si no, (response, status_code)."""
    codigo = (codigo or '').strip()
    if _admin_session_valid() or (_admin_jwt_payload() and _admin_jwt_payload().get('admin_codigo')):
        return None
    aliado = _aliado_codigo()
    if aliado:
        if aliado == codigo:
            return None
        return jsonify({'status': 'error', 'message': 'No autorizado'}), 403
    return jsonify({'status': 'error', 'message': 'Sesión expirada o no autorizado. Inicia sesión con tu código.'}), 401


_ALIADO_SELF_EDITABLE_FIELDS = frozenset({
    'nombre', 'marca', 'oficio', 'codigo_postal', 'email',
    'telefono', 'descripcion_servicio', 'qr_paypal_path', 'bizum_num',
})

# Instrumentaci?n de arranque: confirmar ruta de BD usada por Flask
try:
    from pathlib import Path as _PathCheck
    if settings.postgres_configured:
        print("[RUANA][BOOT] Flask usando backend Postgres/Supabase")
    else:
        _db_exists = _PathCheck(DB_PATH).exists()
        print(f"[RUANA][BOOT] Flask usando base de datos SQLite en: {DB_PATH}")
        print(f"[RUANA][BOOT] ruana.db existe? {'si' if _db_exists else 'NO'}")
except Exception as _e:
    print(f"[RUANA][BOOT] Error comprobando BD: {_e}")

# ================================================
# RUTAS PARA ARCHIVOS EST?TICOS
# ================================================

@app.route('/')
def index():
    """Sirve la pantalla de invitaci?n con c?digo"""
    return send_from_directory(str(web_dir), 'index.html')


@app.route('/register')
@app.route('/register.html')
def register():
    """Sirve la pantalla de registro del aliado"""
    return send_from_directory(str(web_dir), 'register.html')


@app.route('/dashboard')
def dashboard():
    """Sirve el dashboard principal (requiere invitaci?n v?lida)"""
    return send_from_directory(str(web_dir), 'index.html')


@app.route('/panel')
def private_panel():
    """Ruta legacy de panel privado: redirige al panel real de aliado."""
    return send_from_directory(str(web_dir), 'aliado.html')


@app.route('/test-panel')
def test_panel():
    """Sirve la p?gina de test del panel"""
    test_file = Path(__file__).parent.parent / 'test_panel.html'
    return send_from_directory(str(test_file.parent), 'test_panel.html')


@app.route('/diagnostico-panel')
def diagnostico_panel():
    """Sirve el diagn?stico del panel de profesionales"""
    diag_file = Path(__file__).parent.parent / 'diagnostico-panel.html'
    return send_from_directory(str(diag_file.parent), 'diagnostico-panel.html')


@app.route('/test-simple')
def test_simple():
    """Sirve la p?gina de test simple"""
    test_file = Path(__file__).parent.parent / 'test-simple.html'
    return send_from_directory(str(test_file.parent), 'test-simple.html')


@app.route('/panel-test')
def panel_test():
    """Sirve el panel de test"""
    panel_file = Path(__file__).parent.parent / 'panel-test.html'
    return send_from_directory(str(panel_file.parent), 'panel-test.html')


# S-02 / S-03: No existe bypass admin por URL. Acceso solo mediante login (formulario + POST /api/admin/validar).
@app.route('/admin')
def admin_panel():
    """
    Sirve el panel de administrador.
    El parámetro ?bypass= no tiene efecto; se ignora y se redirige sin query para no dejar credencial en URL.
    Autenticación únicamente vía formulario de login y POST /api/admin/validar.
    """
    if request.args.get('bypass') is not None:
        return redirect(url_for('admin_panel'))
    return send_from_directory(str(web_dir), 'admin.html')


@app.route('/aliado')
@app.route('/aliado.html')
def aliado_panel():
    """Sirve el panel del aliado"""
    return send_from_directory(str(web_dir), 'aliado.html')


@app.route('/api/aliado/login', methods=['POST'], strict_slashes=False)
def aliado_login():
    """
    POST /api/aliado/login  body: { codigo: "XXXXX" }
    Valida el código, comprueba estado del aliado y crea sesión en store server-side.
    Retorna { status: 'success', codigo: "...", session_id: "..." }. El frontend debe guardar
    session_id en sessionStorage y enviar header X-Ruana-Session-Id en cada petición (aisla por pestaña).
    """
    data = request.get_json() or {}
    codigo = (data.get('codigo') or '').strip()
    if not codigo:
        return jsonify({'status': 'error', 'message': 'C?digo de aliado requerido'}), 400
    try:
        db = get_db()
        aliado = db.obtener_aliado_por_codigo(codigo)
        if not aliado:
            return jsonify({'status': 'error', 'message': 'C?digo inv?lido o aliado no encontrado'}), 401
        estado = aliado.get('estado')
        if estado == 'expulsado':
            return jsonify({'status': 'error', 'message': 'C?digo desactivado. Se requiere nueva invitaci?n para volver.'}), 403
        if estado == 'pendiente_validacion':
            return jsonify({'status': 'error', 'message': 'Tu cuenta est? pendiente de validaci?n. No puedes acceder al panel hasta que un administrador la active.'}), 403
        if estado == 'rechazado':
            return jsonify({'status': 'error', 'message': 'Tu solicitud de registro no fue aceptada.'}), 403
        if estado == 'suspendido_temporal':
            return jsonify({'status': 'error', 'message': 'Acceso suspendido temporalmente.'}), 403
        expires_at = time.time() + ALIADO_SESSION_EXPIRES_SECONDS
        session_id = _ruana_session_create('aliado', codigo, expires_at)
        # Regla 8: registrar día de login (calendario servidor) y evaluar racha 7 días
        try:
            db.registrar_acceso_login(codigo)
        except Exception:
            pass
        return jsonify({'status': 'success', 'codigo': codigo, 'session_id': session_id})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/aliado/sesion', methods=['GET'], strict_slashes=False)
def aliado_sesion():
    """
    GET /api/aliado/sesion
    Requiere header X-Ruana-Session-Id. Devuelve { status: 'ok', codigo: "XXXXX" } si la sesión es válida; si no, 401.
    """
    if not _aliado_session_valid():
        return jsonify({'status': 'error', 'message': 'Sesi?n expirada o no autorizado'}), 401
    return jsonify({'status': 'ok', 'codigo': _aliado_codigo()})


@app.route('/api/aliado/logout', methods=['POST'])
def aliado_logout():
    """POST /api/aliado/logout  Invalida la sesión indicada por header X-Ruana-Session-Id (o body session_id)."""
    sid = request.headers.get(RUANA_SESSION_HEADER) or (request.get_json() or {}).get('session_id')
    _ruana_session_invalidate(sid)
    return jsonify({'status': 'success'})


@app.route('/api/aliado/datos', methods=['GET', 'POST'], strict_slashes=False)
@require_aliado
def get_aliado_datos():
    """
    GET/POST /api/aliado/datos
    Requiere sesi?n de aliado (cookie). Retorna datos del aliado autenticado.
    El c?digo se toma de la sesi?n; no se conf?a en query/body para autorizaci?n (S-01).
    """
    codigo = _aliado_codigo()
    if not codigo:
        return jsonify({'status': 'error', 'message': 'Sesi?n expirada'}), 401
    
    try:
        db = get_db()
        # Aplicar penalizaciones por contactos abiertos (7d/21d), chat 48h y sin acceso semanal
        db.aplicar_penalizaciones_contactos_abiertos(codigo)
        aliado = db.obtener_aliado_por_codigo(codigo)
        
        if aliado:
            estado = aliado.get('estado')
            if estado == 'expulsado':
                return jsonify({
                    'status': 'error',
                    'message': 'C?digo desactivado. Se requiere nueva invitaci?n para volver.'
                }), 403
            if estado == 'pendiente_validacion':
                return jsonify({
                    'status': 'error',
                    'message': 'Tu cuenta est? pendiente de validaci?n. No puedes acceder al panel hasta que un administrador la active.'
                }), 403
            if estado == 'rechazado':
                return jsonify({
                    'status': 'error',
                    'message': 'Tu solicitud de registro no fue aceptada. Contacta al administrador si crees que es un error.'
                }), 403
            if estado == 'suspendido_temporal':
                return jsonify({
                    'status': 'error',
                    'message': 'Acceso suspendido temporalmente por purga de calidad. Contacte al administrador.'
                }), 403
            solicitudes = []
            if aliado.get('codigo_postal'):
                solicitudes = db.obtener_solicitudes_grupo(aliado['codigo_postal'])
            contar_contestadas = getattr(db, 'contar_solicitudes_enviadas_contestadas', lambda c: 0)
            solicitudes_enviadas_contestadas = contar_contestadas(codigo)
            referidos_count = db.contar_referidos_por_codigo(codigo)
            # Estado RUANA siempre calculado desde el score (PRIORITARIO/ESTABLE/EN RIESGO/COMPETENCIA)
            score = aliado.get('score')
            if score is None:
                score = 0
            estado_ruana = db.score_a_estado(score)
            aliado_dict = dict(aliado)
            # Especializaciones: en BD es JSON string; exponer como lista
            if isinstance(aliado_dict.get('especializaciones'), str):
                try:
                    aliado_dict['especializaciones'] = json.loads(aliado_dict['especializaciones'])
                except Exception:
                    aliado_dict['especializaciones'] = []
            elif aliado_dict.get('especializaciones') is None:
                aliado_dict['especializaciones'] = []
            aliado_dict['solicitudes_enviadas_contestadas'] = solicitudes_enviadas_contestadas
            aliado_dict['referidos_count'] = referidos_count
            aliado_dict['estado_ruana'] = estado_ruana

            grupo_id = aliado_dict.get('grupo_id')
            avisos_grupo = []
            if grupo_id:
                avisos_grupo = db.obtener_avisos_grupo(grupo_id)
                # Info del grupo para el panel: nombre, estado, num oficios, oficios faltantes (cat?logo RUANA). Sin scores ni m?tricas de otros.
                grupo_info = db.info_grupo_para_panel(grupo_id)
                if grupo_info:
                    aliado_dict['grupo_info'] = grupo_info
            aliado_dict['competencia_activa'] = bool(
                grupo_id and db.grupo_tiene_competencia_activa(grupo_id)
            )

            # Notificaciones del aliado (ej. comprobante rechazado con mensaje de admin)
            notificaciones = db.listar_notificaciones_aliado(codigo, limite=50)

            return jsonify({
                'status': 'success',
                'aliado': aliado_dict,
                'solicitudes': solicitudes,
                'avisos_grupo': avisos_grupo,
                'solicitudes_enviadas_contestadas': solicitudes_enviadas_contestadas,
                'referidos_count': referidos_count,
                'notificaciones': notificaciones,
                'timestamp': datetime.now().isoformat()
            })
        
        # Si no existe, retornar error
        return jsonify({
            'status': 'error',
            'message': f'Aliado con c?digo {codigo} no encontrado'
        }), 404
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/aliado/referidos', methods=['GET'])
@require_aliado
def aliado_referidos_arbol():
    """
    GET /api/aliado/referidos
    Árbol de referidos del aliado autenticado (quién invitó a quién, hacia abajo).
    """
    try:
        codigo = _aliado_codigo()
        if not codigo:
            return jsonify({'status': 'error', 'message': 'Sesión no válida'}), 401
        profundidad = request.args.get('profundidad', 8)
        try:
            profundidad_int = int(profundidad)
        except (TypeError, ValueError):
            profundidad_int = 8
        db = get_db()
        arbol = db.obtener_arbol_referidos(codigo, max_depth=profundidad_int)
        if not arbol:
            return jsonify({'status': 'error', 'message': 'Aliado no encontrado'}), 404
        invitador = db.obtener_invitador_de(codigo)
        total_descendientes = _contar_nodos_arbol(arbol) - 1
        return jsonify({
            'status': 'success',
            'arbol': arbol,
            'invitador': invitador,
            'total_descendientes': max(0, total_descendientes),
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/admin/referidos/arbol', methods=['GET'])
@require_admin
def admin_referidos_arbol():
    """
    GET /api/admin/referidos/arbol
    GET /api/admin/referidos/arbol?codigo=XXXXX&profundidad=8
    Árbol de referidos para admin: bosque completo o subárbol desde un aliado.
    """
    try:
        codigo = (request.args.get('codigo') or '').strip()
        profundidad = request.args.get('profundidad', 8)
        try:
            profundidad_int = int(profundidad)
        except (TypeError, ValueError):
            profundidad_int = 8
        db = get_db()
        if codigo:
            arbol = db.obtener_arbol_referidos(codigo, max_depth=profundidad_int)
            if not arbol:
                return jsonify({'status': 'error', 'message': f'Aliado {codigo} no encontrado'}), 404
            invitador = db.obtener_invitador_de(codigo)
            return jsonify({
                'status': 'success',
                'modo': 'subarbol',
                'arbol': arbol,
                'invitador': invitador,
                'total_nodos': _contar_nodos_arbol(arbol),
                'timestamp': datetime.now().isoformat()
            })
        bosques = db.obtener_bosques_referidos(max_depth=profundidad_int)
        total_nodos = sum(_contar_nodos_arbol(b) for b in bosques)
        return jsonify({
            'status': 'success',
            'modo': 'bosque',
            'bosques': bosques,
            'total_nodos': total_nodos,
            'total_raices': len(bosques),
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/admin/referidos/raices', methods=['GET'])
@require_admin
def admin_referidos_raices():
    """GET /api/admin/referidos/raices — Nodos raíz de la red (carga inicial lazy)."""
    try:
        db = get_db()
        raices = db.listar_nodos_raiz_referidos()
        resumen = db.obtener_resumen_referidos_red()
        return jsonify({
            'status': 'success',
            'modo': 'raices',
            'raices': raices,
            'total_nodos': resumen.get('total_nodos', 0),
            'total_raices': len(raices),
            'total_aliados_activos': resumen.get('total_aliados_activos', 0),
            'aliados_fuera_red': resumen.get('aliados_fuera_red', 0),
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/admin/referidos/hijos/<codigo>', methods=['GET'])
@require_admin
def admin_referidos_hijos(codigo):
    """GET /api/admin/referidos/hijos/<codigo> — Referidos directos de un aliado."""
    try:
        codigo = (codigo or '').strip()
        if not codigo:
            return jsonify({'status': 'error', 'message': 'Código requerido'}), 400
        db = get_db()
        nodo = db.obtener_nodo_referidos(codigo)
        if not nodo:
            return jsonify({'status': 'error', 'message': 'Aliado no encontrado'}), 404
        hijos = db.listar_referidos_directos(codigo)
        invitador = db.obtener_invitador_de(codigo)
        return jsonify({
            'status': 'success',
            'nodo': nodo,
            'hijos': hijos,
            'invitador': invitador,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/admin/referidos/ruta/<codigo>', methods=['GET'])
@require_admin
def admin_referidos_ruta(codigo):
    """GET /api/admin/referidos/ruta/<codigo> — Cadena desde raíz hasta el aliado."""
    try:
        codigo = (codigo or '').strip()
        if not codigo:
            return jsonify({'status': 'error', 'message': 'Código requerido'}), 400
        db = get_db()
        ruta = db.obtener_ruta_referidos_hacia_arriba(codigo)
        if not ruta:
            return jsonify({'status': 'error', 'message': 'Aliado no encontrado en la red'}), 404
        return jsonify({
            'status': 'success',
            'ruta': ruta,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/admin/referidos/buscar', methods=['GET'])
@require_admin
def admin_referidos_buscar():
    """GET /api/admin/referidos/buscar?q=texto — Busca aliados en la red."""
    try:
        query = (request.args.get('q') or '').strip()
        if not query:
            return jsonify({'status': 'success', 'resultados': []})
        db = get_db()
        resultados = db.buscar_en_red_referidos(query, limite=25)
        return jsonify({
            'status': 'success',
            'resultados': resultados,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/aliado/referidos/hijos/<codigo>', methods=['GET'])
@require_aliado
def aliado_referidos_hijos(codigo):
    """GET /api/aliado/referidos/hijos/<codigo> — Referidos directos visibles para el aliado."""
    try:
        codigo_sesion = _aliado_codigo()
        codigo = (codigo or '').strip()
        if not codigo_sesion:
            return jsonify({'status': 'error', 'message': 'Sesión no válida'}), 401
        if not codigo:
            return jsonify({'status': 'error', 'message': 'Código requerido'}), 400
        db = get_db()
        if not db.aliado_puede_ver_nodo_referidos(codigo_sesion, codigo):
            return jsonify({'status': 'error', 'message': 'No autorizado'}), 403
        nodo = db.obtener_nodo_referidos(codigo)
        if not nodo:
            return jsonify({'status': 'error', 'message': 'Aliado no encontrado'}), 404
        hijos = db.listar_referidos_directos(codigo)
        invitador = db.obtener_invitador_de(codigo) if codigo != codigo_sesion else db.obtener_invitador_de(codigo)
        return jsonify({
            'status': 'success',
            'nodo': nodo,
            'hijos': hijos,
            'invitador': invitador,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/aliado/referidos/raiz', methods=['GET'])
@require_aliado
def aliado_referidos_raiz():
    """GET /api/aliado/referidos/raiz — Nodo raíz del aliado autenticado."""
    try:
        codigo = _aliado_codigo()
        if not codigo:
            return jsonify({'status': 'error', 'message': 'Sesión no válida'}), 401
        db = get_db()
        nodo = db.obtener_nodo_referidos(codigo)
        if not nodo:
            return jsonify({'status': 'error', 'message': 'Aliado no encontrado'}), 404
        invitador = db.obtener_invitador_de(codigo)
        total_desc = db.contar_referidos_por_codigo(codigo)
        return jsonify({
            'status': 'success',
            'modo': 'raiz',
            'nodo': nodo,
            'invitador': invitador,
            'total_descendientes_directos': total_desc,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/admin/referidos/cambios', methods=['GET'])
@require_admin
def admin_referidos_cambios():
    """GET /api/admin/referidos/cambios?desde=<iso> — Nuevos referidos desde un momento."""
    try:
        desde = (request.args.get('desde') or '').strip()
        db = get_db()
        cambios = db.listar_referidos_desde(desde)
        raices = db.listar_nodos_raiz_referidos()
        resumen = db.obtener_resumen_referidos_red()
        return jsonify({
            'status': 'success',
            'cambios': cambios,
            'raices': raices,
            'total_nodos': resumen.get('total_nodos', 0),
            'total_raices': len(raices),
            'total_aliados_activos': resumen.get('total_aliados_activos', 0),
            'aliados_fuera_red': resumen.get('aliados_fuera_red', 0),
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/aliado/referidos/cambios', methods=['GET'])
@require_aliado
def aliado_referidos_cambios():
    """GET /api/aliado/referidos/cambios?desde=<iso> — Nuevos referidos visibles para el aliado."""
    try:
        codigo_sesion = _aliado_codigo()
        if not codigo_sesion:
            return jsonify({'status': 'error', 'message': 'Sesión no válida'}), 401
        desde = (request.args.get('desde') or '').strip()
        db = get_db()
        todos = db.listar_referidos_desde(desde)
        cambios = [
            c for c in todos
            if db.aliado_puede_ver_nodo_referidos(codigo_sesion, c.get('codigo_referido') or '')
        ]
        nodo_raiz = db.obtener_nodo_referidos(codigo_sesion)
        return jsonify({
            'status': 'success',
            'cambios': cambios,
            'nodo_raiz': nodo_raiz,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/admin/aliados/<codigo>/linaje', methods=['GET'])
@require_admin
def admin_aliado_linaje(codigo):
    """
    GET /api/admin/aliados/<codigo>/linaje
    Linaje para Control de Aliados: padre, hijos directos y ruta.
    """
    try:
        codigo = (codigo or '').strip()
        if not codigo:
            return jsonify({'status': 'error', 'message': 'Código requerido'}), 400
        db = get_db()
        linaje = db.obtener_linaje_aliado(codigo)
        if not linaje:
            return jsonify({'status': 'error', 'message': 'Aliado no encontrado'}), 404
        return jsonify({
            'status': 'success',
            'linaje': linaje,
            'timestamp': datetime.now().isoformat(),
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/aliado/linaje/hijos', methods=['GET'])
@require_aliado
def aliado_linaje_hijos():
    """
    GET /api/aliado/linaje/hijos
    Hijos directos del aliado autenticado (modal panel aliado).
    """
    try:
        codigo = _aliado_codigo()
        if not codigo:
            return jsonify({'status': 'error', 'message': 'Sesión no válida'}), 401
        db = get_db()
        hijos = db.listar_hijos_directos_linaje(codigo)
        return jsonify({
            'status': 'success',
            'codigo': codigo,
            'hijos': hijos,
            'total': len(hijos),
            'timestamp': datetime.now().isoformat(),
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


def _contar_nodos_arbol(nodo: dict) -> int:
    """Cuenta nodos en un árbol de referidos (incluye la raíz)."""
    if not nodo or not isinstance(nodo, dict):
        return 0
    count = 1
    for hijo in nodo.get('referidos') or []:
        count += _contar_nodos_arbol(hijo)
    return count


@app.route('/api/aliados/por-codigo/<codigo>', methods=['GET'])
@require_aliado
def get_aliado_by_codigo(codigo):
    """
    GET /api/aliados/por-codigo/XXXXX
    Retorna datos del aliado. Solo se permite consultar el propio c?digo (sesi?n).
    """
    try:
        codigo = codigo.strip()
        if codigo != _aliado_codigo():
            return jsonify({'status': 'error', 'message': 'No autorizado a consultar otro aliado'}), 403
        db = get_db()
        aliado = db.obtener_aliado_por_codigo(codigo)
        
        if aliado:
            estado = aliado.get('estado')
            if estado == 'expulsado':
                return jsonify({
                    'status': 'error',
                    'message': 'C?digo desactivado. Se requiere nueva invitaci?n para volver.'
                }), 403
            if estado == 'suspendido_temporal':
                return jsonify({
                    'status': 'error',
                    'message': 'Acceso suspendido temporalmente por purga de calidad. Contacte al administrador.'
                }), 403
            aliado_out = dict(aliado)
            grupo_id = aliado_out.get('grupo_id')
            aliado_out['competencia_activa'] = bool(
                grupo_id and db.grupo_tiene_competencia_activa(grupo_id)
            )
            return jsonify({
                'status': 'success',
                'aliado': aliado_out,
                'timestamp': datetime.now().isoformat()
            })
        
        return jsonify({
            'status': 'error',
            'message': f'Aliado {codigo} no encontrado'
        }), 404
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/solicitudes', methods=['GET', 'POST'])
@require_aliado
def api_solicitudes():
    """GET ? lista activas del grupo del aliado en sesi?n. POST body { oficio, descripcion } ? crear."""
    codigo = _aliado_codigo()
    if not codigo:
        return jsonify({'error': 'Sesi?n expirada'}), 401
    if request.method == 'GET':
        try:
            db = get_db()
            entrantes = db.listar_solicitudes_activas_por_codigo(codigo)
            propias = db.listar_solicitudes_propias_por_codigo(codigo)
            historial = db.listar_solicitudes_historial_grupo_por_codigo(codigo, limite=50)
            return jsonify({
                'entrantes': entrantes,
                'propias': propias,
                'historial': historial
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    else:
        data = request.get_json() or {}
        oficio = (data.get('oficio') or '').strip()
        descripcion = (data.get('descripcion') or '').strip()
        if not oficio:
            return jsonify({'error': 'Oficio obligatorio'}), 400
        if not descripcion:
            return jsonify({'error': 'Descripción obligatoria'}), 400
        if len(descripcion) < 5:
            return jsonify({'error': 'La descripción debe tener al menos 5 caracteres'}), 400
        try:
            db = get_db()
            result = db.crear_solicitud_por_codigo(codigo, oficio, descripcion)
            if result.get('status') != 'success':
                return jsonify({'error': result.get('message', 'Error al crear solicitud')}), 400
            return jsonify({'ok': True, 'id': result.get('id')}), 200
        except Exception as e:
            return jsonify({'error': str(e)}), 500


@app.route('/api/solicitudes/<int:solicitud_id>/atender', methods=['POST'])
@require_aliado
def atender_solicitud(solicitud_id):
    """
    POST /api/solicitudes/<id>/atender
    Marca atendida y registra al aliado en sesi?n como quien atendi?.
    """
    codigo = _aliado_codigo()
    if not codigo:
        return jsonify({'error': 'Sesi?n expirada'}), 401
    try:
        db = get_db()
        result = db.atender_solicitud_por_id(solicitud_id, codigo)
        if result.get('status') != 'success':
            return jsonify({'error': result.get('message', 'Error al atender')}), 400
        return jsonify({'ok': True}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/generar-invitacion', methods=['POST'])
@app.route('/api/aliado/generar-invitacion', methods=['POST'])
@require_aliado
def generar_invitacion():
    """
    POST /api/generar-invitacion  o  POST /api/aliado/generar-invitacion
    Body: { oficio: "Alba?iler?a" }. Genera invitaci?n para oficio faltante en el grupo del aliado en sesi?n.
    """
    print("[RUANA] ENDPOINT generar-invitacion llamado")
    codigo = _aliado_codigo()
    if not codigo:
        return jsonify({'status': 'error', 'message': 'Sesi?n expirada'}), 401
    data = request.get_json() or {}
    oficio = (data.get('oficio') or '').strip()
    if not oficio:
        return jsonify({'status': 'error', 'message': 'Oficio requerido'}), 400
    try:
        db = get_db()
        result = db.generar_invitacion_oficio(codigo, oficio)
        if result.get('status') == 'error':
            return jsonify(result), 400
        return jsonify({'status': 'success', 'codigo': result['codigo']})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/invite')
@app.route('/invite.html')
def invite():
    """Sirve la pantalla de invitaci?n (alternativa)"""
    return send_from_directory(str(web_dir), 'invite.html')


@app.route('/private-panel')
@app.route('/private-panel.html')
def private_panel_alt():
    """Ruta alternativa legacy de panel privado: redirige al panel real de aliado."""
    return send_from_directory(str(web_dir), 'aliado.html')


@app.route('/dashboard.html')
def dashboard_alt():
    """Sirve dashboard (alternativa)"""
    return send_from_directory(str(web_dir), 'dashboard.html')


@app.route('/static/<path:path>')
def static_files(path):
    """Sirve archivos est?ticos (CSS, JS, etc)"""
    return send_from_directory(str(web_dir / 'static'), path)


# ================================================
# API ENDPOINTS
# ================================================

@app.route('/api/aliados', methods=['GET'])
@require_admin
def get_aliados():
    """
    GET /api/aliados
    Retorna lista de todos los aliados desde SQLite
    """
    try:
        db = get_db()
        aliados = db.listar_aliados()
        
        return jsonify({
            'status': 'success',
            'total': len(aliados),
            'aliados': aliados,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/aliados/directorio', methods=['GET'])
@require_aliado
def get_aliados_directorio():
    """
    GET /api/aliados/directorio
    Retorna profesionales del mismo grupo que el aliado en sesi?n (directorio). Excluye al propio aliado.
    """
    try:
        codigo = _aliado_codigo()
        if not codigo:
            return jsonify({'status': 'error', 'message': 'Sesi?n expirada'}), 401
        db = get_db()
        aliados = db.listar_aliados_directorio_grupo(codigo)
        print(f"[directorio] codigo={codigo!r} -> {len(aliados)} profesionales")
        return jsonify({
            'status': 'success',
            'total': len(aliados),
            'aliados': aliados,
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/aliados/<int:aliado_id>', methods=['GET'])
@require_admin
def get_aliado(aliado_id):
    """
    GET /api/aliados/<id>
    Retorna detalles de un aliado espec?fico por ID
    """
    try:
        db = get_db()
        aliado = db.obtener_aliado_por_id(aliado_id)
        
        if not aliado:
            return jsonify({
                'status': 'error',
                'message': f'Aliado con ID {aliado_id} no encontrado'
            }), 404
        
        return jsonify({
            'status': 'success',
            'aliado': aliado,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


def _catalogo_oficios_desde_archivo():
    """Lee el catálogo desde config/oficios_ruana.json. Devuelve lista de {nombre, especializaciones} o []."""
    try:
        config_path = Path(__file__).resolve().parent.parent / 'config' / 'oficios_ruana.json'
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            oficios = data.get('oficios', [])
            if isinstance(oficios, list) and oficios:
                out = []
                for o in oficios:
                    if isinstance(o, dict) and o.get('nombre'):
                        esp = o.get('especializaciones') or [o['nombre']]
                        if isinstance(esp, list):
                            esp = [str(e).strip() for e in esp if str(e).strip()]
                        else:
                            esp = [str(o['nombre']).strip()]
                        out.append({'nombre': str(o['nombre']).strip(), 'especializaciones': esp})
                    elif isinstance(o, str) and o.strip():
                        n = str(o).strip()
                        out.append({'nombre': n, 'especializaciones': [n]})
                return out if out else []
    except Exception:
        pass
    return []


@app.route('/api/catalogo/oficios', methods=['GET'])
def get_catalogo_oficios():
    """
    GET /api/catalogo/oficios
    Retorna el catálogo oficial de oficios RUANA en formato jerárquico.
    Cada oficio tiene nombre y lista de especializaciones (una plaza por especialización por grupo).
    """
    try:
        oficios = _catalogo_oficios_desde_archivo()
        if oficios:
            return jsonify({
                'status': 'success',
                'oficios': oficios,
                'timestamp': datetime.now().isoformat()
            })
        db = get_db()
        oficios = db.get_catalogo_oficios_jerarquico()
        return jsonify({
            'status': 'success',
            'oficios': oficios,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/catalogo/oficios-raw', methods=['GET'])
def get_catalogo_oficios_raw():
    """Devuelve el catálogo leyendo solo el archivo config (sin BD). Fallback para el frontend."""
    oficios = _catalogo_oficios_desde_archivo()
    return jsonify({'status': 'success', 'oficios': oficios})


@app.route('/api/grupos/especializaciones-disponibles', methods=['GET'])
def get_especializaciones_disponibles():
    """
    GET /api/grupos/especializaciones-disponibles?codigo_postal=...&oficio_principal=...&grupo_id=...
    Devuelve para cada especialización del oficio si está disponible u ocupada en el grupo destino.
    Si grupo_id viene (invitación), se consulta solo ese grupo; si no, todos los grupos activos del CP.
    """
    try:
        codigo_postal = (request.args.get('codigo_postal') or '').strip()
        oficio_principal = (request.args.get('oficio_principal') or '').strip()
        grupo_id_raw = request.args.get('grupo_id')
        db = get_db()
        catalogo = db.get_catalogo_oficios_jerarquico()
        oficio_info = next((o for o in catalogo if (o.get('nombre') or '').strip() == oficio_principal), None)
        if not oficio_info:
            return jsonify({
                'status': 'success',
                'especializaciones': [],
                'grupos': [],
                'timestamp': datetime.now().isoformat()
            })
        especializaciones_nombres = list(oficio_info.get('especializaciones') or [oficio_principal])
        resultado = []
        grupos_a_consultar = []
        if grupo_id_raw and str(grupo_id_raw).isdigit():
            grupos_a_consultar = [{'id': int(grupo_id_raw)}]
        elif codigo_postal:
            grupos_a_consultar = db.obtener_grupos_activos_por_cp(codigo_postal)
        for esp in especializaciones_nombres:
            esp = str(esp).strip()
            if not esp:
                continue
            # Disponible si al menos un grupo del CP (o el grupo de invitación) tiene la plaza libre
            disponible = False
            for g in grupos_a_consultar:
                gid = g.get('id') if isinstance(g, dict) else g
                ocupadas = db.obtener_especializaciones_ocupadas(gid, oficio_principal)
                if esp not in ocupadas:
                    disponible = True
                    break
            resultado.append({'nombre': esp, 'disponible': disponible})
        return jsonify({
            'status': 'success',
            'especializaciones': resultado,
            'grupos': [g.get('id') if isinstance(g, dict) else g for g in grupos_a_consultar],
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/filtros', methods=['GET'])
def get_filtros():
    """
    GET /api/filtros
    Retorna opciones disponibles para filtros (extra?das de SQLite)
    """
    try:
        db = get_db()
        aliados = db.listar_aliados()
        
        zonas = sorted(list(set(a.get('codigo_postal', '') for a in aliados if a.get('codigo_postal'))))
        oficios = sorted(list(set(a.get('oficio', '') for a in aliados if a.get('oficio'))))
        
        return jsonify({
            'status': 'success',
            'zonas': zonas,
            'oficios': oficios,
            'estados': ['activo', 'inactivo'],
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/stats', methods=['GET'])
@require_admin
def get_stats():
    """
    GET /api/stats
    Retorna estad?sticas generales del dashboard desde SQLite
    """
    try:
        db = get_db()
        stats = db.obtener_estadisticas_evaluaciones()

        aliados = db.listar_aliados()
        total = len(aliados)
        activos = len([a for a in aliados if a.get('estado') == 'activo'])

        suplentes = db.contar_suplentes_activos()
        en_riesgo = db.contar_aliados_en_riesgo()
        solicitudes_activas = db.contar_solicitudes_activas()
        oficios_ocupados = db.contar_oficios_ocupados()
        grupos_counts = db.contar_grupos()
        if not isinstance(grupos_counts, dict):
            grupos_counts = {'total': 0, 'activos': 0, 'en_competencia': 0, 'disueltos': 0}
        total_grupos = int(grupos_counts.get('total', 0) or 0)
        grupos_activos = int(grupos_counts.get('activos', 0) or 0)
        grupos_en_competencia = int(grupos_counts.get('en_competencia', 0) or 0)
        grupos_disueltos = int(grupos_counts.get('disueltos', 0) or 0)

        # M?tricas de contactos RUANA (contactos abiertos, disputas, etc.)
        contactos_metricas = db.obtener_metricas_contactos()
        if isinstance(contactos_metricas, dict) and contactos_metricas.get('status') == 'success':
            contactos_payload = {
                k: v for k, v in contactos_metricas.items()
                if k != 'status'
            }
        else:
            contactos_payload = {}

        # Estado del sistema (Estable / Alerta / Cr?tico) basado en m?tricas reales
        contactos_disputa = contactos_payload.get('contactos_en_disputa', 0) or 0
        contactos_disputa_prolongada = contactos_payload.get('contactos_en_disputa_prolongada', 0) or 0
        pct_riesgo = (en_riesgo / activos * 100) if activos else 0
        if pct_riesgo <= 10 and contactos_disputa <= 2 and contactos_disputa_prolongada == 0:
            estado_sistema = 'Estable'
        elif pct_riesgo <= 25 and contactos_disputa <= 5:
            estado_sistema = 'Alerta'
        else:
            estado_sistema = 'Cr?tico'

        permisos = _admin_permisos()
        if not permisos and _admin_codigo():
            permisos = ['leer', 'escribir', 'eliminar', 'configurar']
        return jsonify({
            'status': 'success',
            'permisos': permisos or [],
            'total_aliados': total,
            'aliados_activos': activos,
            'suplentes': suplentes,
            'en_riesgo': en_riesgo,
            'solicitudes_activas': solicitudes_activas,
            'oficios_ocupados': oficios_ocupados,
            'total_grupos': total_grupos,
            'grupos_activos': grupos_activos,
            'grupos_en_competencia': grupos_en_competencia,
            'grupos_disueltos': grupos_disueltos,
            'estado_sistema': estado_sistema,
            'evaluaciones': stats,
            'contactos': contactos_payload,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/movimiento-24h', methods=['GET'])
@require_admin
def get_movimiento_24h():
    """
    GET /api/movimiento-24h
    Movimiento del sistema en las ?ltimas 24h: solicitudes, invitaciones, contactos, top invitadores.
    Requiere sesi?n admin o JWT.
    """
    try:
        db = get_db()
        movimiento = db.obtener_movimiento_24h()
        return jsonify({
            'status': 'success',
            'movimiento': movimiento,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/movimiento-24h-horas', methods=['GET'])
@require_admin
def get_movimiento_24h_horas():
    """
    GET /api/movimiento-24h-horas
    Movimiento en las ?ltimas 24h agrupado por hora (00-23). Siempre devuelve 24 claves con valores num?ricos.
    """
    try:
        db = get_db()
        por_hora = db.obtener_movimiento_24h_por_hora()
        return jsonify({
            'status': 'success',
            'por_hora': por_hora,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/metricas-salud', methods=['GET'])
@require_admin
def get_metricas_salud():
    """
    GET /api/metricas-salud
    Cruce aliados, contactos, evaluaciones, invitaciones: ratio solicitud?invitaci?n,
    ratio invitaci?n?registro, oficios saturados/disponibles, zona mayor demanda, tasa retenci?n.
    Requiere sesi?n admin o JWT.
    """
    try:
        db = get_db()
        metricas = db.obtener_metricas_salud()
        return jsonify({
            'status': 'success',
            'metricas': metricas,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/eventos-recientes', methods=['GET'])
@require_admin
def get_eventos_recientes():
    """
    GET /api/eventos-recientes
    Devuelve las ?ltimas acciones relevantes registradas en el sistema (trazabilidad).
    Requiere sesi?n admin o JWT.
    """
    try:
        limite_raw = (request.args.get('limit') or '').strip()
        try:
            limite = int(limite_raw) if limite_raw else 10
        except Exception:
            limite = 10

        db = get_db()
        eventos = db.obtener_eventos_recientes(limite)
        return jsonify({
            'status': 'success',
            'eventos': eventos,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/health', methods=['GET'])
def health():
    """
    GET /api/health
    Verifica estado del servidor
    """
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat()
    })


# ========== Chat RUANA (path de un solo segmento para evitar 404) ==========
def _chat_payload_from_messages(mensajes, estado):
    """Construye una respuesta de chat coherente entre lista visible y contador."""
    mensajes_list = mensajes if isinstance(mensajes, list) else []
    chat_max = int(estado.get('chat_max_mensajes') or 30)
    chat_expirado = bool(estado.get('chat_expirado', False))
    mensajes_restantes = 0 if chat_expirado else max(0, chat_max - len(mensajes_list))
    return {
        'status': 'success',
        'mensajes': mensajes_list,
        'chat_expirado': chat_expirado,
        'mensajes_restantes': mensajes_restantes,
        'chat_referencia_en': estado.get('chat_referencia_en'),
        'chat_expira_en': estado.get('chat_expira_en'),
        'chat_horas_restantes': 0 if chat_expirado else estado.get('chat_horas_restantes'),
        'chat_horas_vigencia': estado.get('chat_horas_vigencia'),
        'chat_max_mensajes': chat_max,
    }


def _priorizar_contactos_con_mensajes(contactos):
    """Evita que un contacto abierto vacío tape una conversación activa en el banner."""
    def tiene_mensajes(contacto):
        try:
            return int(contacto.get('num_mensajes') or 0) > 0
        except (TypeError, ValueError):
            return False

    return sorted(contactos or [], key=lambda c: 0 if tiene_mensajes(c) else 1)


@app.route('/api/chat_mensajes', methods=['GET'])
@require_aliado
def chat_mensajes_get():
    """GET /api/chat_mensajes?contacto_id=1  ? lista mensajes (codigo desde sesi?n)."""
    try:
        contacto_id = request.args.get('contacto_id', type=int)
        codigo = _aliado_codigo()
        if not contacto_id or not codigo:
            return jsonify({'status': 'error', 'message': 'contacto_id obligatorio y sesi?n v?lida'}), 400
        db = get_db()
        contacto = db.obtener_contacto_resumen(contacto_id)
        if not contacto:
            return jsonify({'status': 'error', 'message': 'Contacto no encontrado'}), 404
        sol = str(contacto.get('solicitante_codigo') or '').strip()
        pro = str(contacto.get('profesional_codigo') or '').strip()
        if codigo not in (sol, pro):
            return jsonify({'status': 'error', 'message': 'No tienes permiso para ver este chat'}), 403
        mensajes = db.listar_mensajes_contacto(contacto_id)
        estado = db.estado_chat_contacto(contacto_id, codigo)
        return jsonify(_chat_payload_from_messages(mensajes, estado))
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/chat_enviar', methods=['POST', 'OPTIONS'])
def chat_enviar_post():
    """POST /api/chat_enviar  body: { contacto_id, texto }. emisor = aliado en sesi?n."""
    if request.method == 'OPTIONS':
        return '', 200
    if not _aliado_session_valid():
        return jsonify({'status': 'error', 'message': 'Sesi?n expirada o no autorizado'}), 401
    emisor_codigo = _aliado_codigo()
    try:
        data = request.get_json() or {}
        contacto_id = data.get('contacto_id')
        if contacto_id is not None:
            try:
                contacto_id = int(contacto_id)
            except (TypeError, ValueError):
                contacto_id = None
        texto = data.get('texto')
        if not contacto_id:
            return jsonify({'status': 'error', 'message': 'contacto_id es obligatorio'}), 400
        if not emisor_codigo:
            return jsonify({'status': 'error', 'message': 'Sesi?n expirada'}), 401
        db = get_db()
        result = db.enviar_mensaje_chat(contacto_id, emisor_codigo, texto or '')
        if result.get('status') != 'success':
            return jsonify(result), 400
        return jsonify(result), 201
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ================================================
# NEW SQLite ENDPOINTS
# ================================================

@app.route('/api/contactos', methods=['POST'])
@require_aliado
def crear_contacto():
    """
    POST /api/contactos
    Crea un contacto RUANA. solicitante_codigo debe ser el aliado en sesi?n (no se conf?a en body).
        Body JSON: profesional_codigo, servicio, motivo_contacto, es_urgente (opcional).
    """
    try:
        solicitante_codigo = _aliado_codigo()
        if not solicitante_codigo:
            return jsonify({'status': 'error', 'message': 'Sesi?n expirada'}), 401
        data = request.get_json() or {}
        profesional_codigo = (data.get('profesional_codigo') or '').strip()
        servicio = (data.get('servicio') or '').strip()
        motivo_contacto = (data.get('motivo_contacto') or '').strip()
        es_urgente_raw = data.get('es_urgente', False)
        es_urgente = es_urgente_raw in (True, 1, '1', 'true', 'True', 'yes', 'on')

        if not profesional_codigo:
            return jsonify({
                'status': 'error',
                'message': 'profesional_codigo es obligatorio'
            }), 400
        if not motivo_contacto:
            return jsonify({
                'status': 'error',
                'message': 'Debes elegir un motivo de contacto antes de iniciar la conversaci?n'
            }), 400

        db = get_db()
        result = db.crear_contacto_ruana(
            solicitante_codigo=solicitante_codigo,
            profesional_codigo=profesional_codigo,
            servicio=servicio,
            motivo_contacto=motivo_contacto,
            es_urgente=es_urgente,
        )

        status_code = 201 if result.get('status') == 'success' else 400
        return jsonify(result), status_code

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


# Finalizar chat: registrar antes que otras rutas /api/contactos/<id>/... para que coincidan correctamente
def _finalizar_chat_contacto_impl(contacto_id):
    """Implementación compartida para finalizar-chat (ocultar contacto del panel del aliado)."""
    usuario = _aliado_codigo()
    if not usuario:
        return jsonify({'status': 'error', 'message': 'Sesión expirada'}), 401
    db = get_db()
    result = db.ocultar_contacto_del_panel(contacto_id, codigo_aliado=usuario)
    status_code = 200 if result.get('status') == 'success' else 400
    return jsonify(result), status_code


@app.route('/api/contactos/<int:contacto_id>/finalizar-chat', methods=['POST'])
@require_aliado
def finalizar_chat_contacto(contacto_id):
    """POST /api/contactos/<id>/finalizar-chat - Oculta el contacto del panel del aliado."""
    try:
        return _finalizar_chat_contacto_impl(contacto_id)
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/contactos/<int:contacto_id>/finalizar_chat', methods=['POST'])
@require_aliado
def finalizar_chat_contacto_alias(contacto_id):
    """Alias: POST /api/contactos/<id>/finalizar_chat"""
    try:
        return _finalizar_chat_contacto_impl(contacto_id)
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/contactos/<int:contacto_id>/aceptar', methods=['POST'])
@require_aliado
def aceptar_contacto(contacto_id):
    """
    POST /api/contactos/<id>/aceptar
    El profesional (aliado en sesi?n) acepta el contacto.
    """
    try:
        profesional_codigo = _aliado_codigo()
        if not profesional_codigo:
            return jsonify({'status': 'error', 'message': 'Sesi?n expirada'}), 401

        db = get_db()
        if db.tiene_pagos_ruana_pendientes(profesional_codigo):
            return jsonify({
                'status': 'error',
                'message': 'Tienes pagos pendientes con RUANA. No puedes aceptar nuevos trabajos hasta regularizar la situaci?n.'
            }), 403
        result = db.aceptar_contacto_ruana(contacto_id, profesional_codigo)
        status_code = 200 if result.get('status') == 'success' else 400
        return jsonify(result), status_code

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/contactos/<int:contacto_id>/trabajo-en-progreso', methods=['POST'])
@require_aliado
def marcar_trabajo_en_progreso(contacto_id):
    """
    POST /api/contactos/<id>/trabajo-en-progreso
    Marca el contacto como trabajo_en_progreso. Solo un participante (sesi?n) puede hacerlo.
    """
    try:
        codigo = _aliado_codigo()
        if not codigo:
            return jsonify({'status': 'error', 'message': 'Sesi?n expirada'}), 401
        db = get_db()
        contacto = db.obtener_contacto_resumen(contacto_id)
        if not contacto:
            return jsonify({'status': 'error', 'message': 'Contacto no encontrado'}), 404
        sol = str(contacto.get('solicitante_codigo') or '').strip()
        pro = str(contacto.get('profesional_codigo') or '').strip()
        if codigo not in (sol, pro):
            return jsonify({'status': 'error', 'message': 'No autorizado'}), 403
        result = db.marcar_trabajo_en_progreso(contacto_id)
        status_code = 200 if result.get('status') == 'success' else 400
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/contactos/<int:contacto_id>/no-concretado', methods=['POST'])
@require_aliado
def marcar_contacto_no_concretado(contacto_id):
    """
    POST /api/contactos/<id>/no-concretado
    Cierra el contacto como no concretado. actor = aliado en sesi?n.
    """
    try:
        data = request.get_json() or {}
        motivo = (data.get('motivo') or '').strip()
        usuario = _aliado_codigo() or (data.get('usuario') or '').strip()

        db = get_db()
        result = db.marcar_cerrado_no_concretado(contacto_id, motivo=motivo, actor_codigo=usuario)
        status_code = 200 if result.get('status') == 'success' else 400
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/contactos/<int:contacto_id>/en-conversacion', methods=['POST'])
@require_aliado
def marcar_contacto_en_conversacion(contacto_id):
    """
    POST /api/contactos/<id>/en-conversacion
    Marca el contacto como en_conversacion. actor = aliado en sesi?n.
    """
    try:
        usuario = _aliado_codigo() or (request.get_json() or {}).get('usuario') or ''

        db = get_db()
        result = db.marcar_en_conversacion(contacto_id, actor_codigo=usuario)
        status_code = 200 if result.get('status') == 'success' else 400
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/contactos/<int:contacto_id>/mensajes', methods=['GET', 'POST'])
@require_aliado
def api_contactos_mensajes(contacto_id):
    """
    GET /api/contactos/<id>/mensajes  ? lista mensajes (codigo desde sesi?n).
    POST /api/contactos/<id>/mensajes  ? body: { texto }  ? env?a mensaje (emisor = sesi?n).
    """
    codigo = _aliado_codigo()
    if not codigo:
        return jsonify({'status': 'error', 'message': 'Sesi?n expirada'}), 401
    if request.method == 'GET':
        try:
            db = get_db()
            contacto = db.obtener_contacto_resumen(contacto_id)
            if not contacto:
                return jsonify({'status': 'error', 'message': 'Contacto no encontrado'}), 404
            sol = str(contacto.get('solicitante_codigo') or '').strip()
            pro = str(contacto.get('profesional_codigo') or '').strip()
            if codigo not in (sol, pro):
                return jsonify({'status': 'error', 'message': 'No tienes permiso para ver este chat'}), 403
            mensajes = db.listar_mensajes_contacto(contacto_id)
            estado = db.estado_chat_contacto(contacto_id, codigo)
            return jsonify(_chat_payload_from_messages(mensajes, estado))
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500

    # POST
    try:
        data = request.get_json() or {}
        texto = data.get('texto')
        db = get_db()
        result = db.enviar_mensaje_chat(contacto_id, codigo, texto or '')
        if result.get('status') != 'success':
            return jsonify(result), 400
        return jsonify(result), 201
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ========== Chat RUANA (rutas simples: Aliado y Profesional) ==========
@app.route('/api/chat/mensajes', methods=['GET'])
@require_aliado
def chat_get_mensajes():
    """GET /api/chat/mensajes?contacto_id=1  ? lista mensajes del chat (codigo desde sesi?n)."""
    try:
        contacto_id = request.args.get('contacto_id', type=int)
        codigo = _aliado_codigo()
        if not contacto_id or not codigo:
            return jsonify({'status': 'error', 'message': 'contacto_id es obligatorio'}), 400
        db = get_db()
        contacto = db.obtener_contacto_resumen(contacto_id)
        if not contacto:
            return jsonify({'status': 'error', 'message': 'Contacto no encontrado'}), 404
        sol = str(contacto.get('solicitante_codigo') or '').strip()
        pro = str(contacto.get('profesional_codigo') or '').strip()
        if codigo not in (sol, pro):
            return jsonify({'status': 'error', 'message': 'No tienes permiso para ver este chat'}), 403
        mensajes = db.listar_mensajes_contacto(contacto_id)
        estado = db.estado_chat_contacto(contacto_id, codigo)
        return jsonify(_chat_payload_from_messages(mensajes, estado))
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/chat/enviar', methods=['POST'])
@require_aliado
def chat_enviar():
    """POST /api/chat/enviar  body: { contacto_id, texto }  ? env?a mensaje (emisor = sesi?n)."""
    try:
        data = request.get_json() or {}
        contacto_id = data.get('contacto_id')
        if contacto_id is not None:
            try:
                contacto_id = int(contacto_id)
            except (TypeError, ValueError):
                contacto_id = None
        emisor_codigo = _aliado_codigo()
        texto = data.get('texto')
        if not contacto_id:
            return jsonify({'status': 'error', 'message': 'contacto_id es obligatorio'}), 400
        if not emisor_codigo:
            return jsonify({'status': 'error', 'message': 'Sesi?n expirada'}), 401
        db = get_db()
        result = db.enviar_mensaje_chat(contacto_id, emisor_codigo, texto or '')
        if result.get('status') != 'success':
            return jsonify(result), 400
        return jsonify(result), 201
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/contactos/<int:contacto_id>/declarar-importe', methods=['POST'])
@require_aliado
def declarar_importe_contacto(contacto_id):
    """
    POST /api/contactos/<id>/declarar-importe
    Declaraci?n de importe. usuario = aliado en sesi?n (no se conf?a en body).
    Body: parte, importe, moneda (opcional).
    """
    try:
        usuario = _aliado_codigo()
        if not usuario:
            return jsonify({'status': 'error', 'message': 'Sesi?n expirada'}), 401
        data = request.get_json() or {}
        parte = data.get('parte')
        importe = data.get('importe')
        moneda = (data.get('moneda') or 'EUR').strip()

        db = get_db()
        result = db.registrar_importe_contacto(
            contacto_id=contacto_id,
            parte=parte,
            importe=importe,
            moneda=moneda,
            usuario=usuario
        )
        if result.get('status') != 'success':
            print(f"[RUANA] declarar-importe 400: contacto_id={contacto_id} message={result.get('message')}")
        # Score por encargo (+2) al marcar Apoyo pagado (Regla 2). Sin penalización por disputa.
        status_code = 200 if result.get('status') == 'success' else 400

        safe_response = {
            'status': result.get('status'),
            'message': result.get('message'),
            'id': result.get('id'),
            'estado': result.get('estado')
        }

        return jsonify(safe_response), status_code
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/contactos/metricas', methods=['GET'])
def metricas_contactos():
    """
    GET /api/contactos/metricas
    
    Devuelve m?tricas agregadas de contactos RUANA:
    - contactos_abiertos
    - contactos_no_resueltos
    - contactos_en_disputa
    - contactos_en_disputa_prolongada
    """
    try:
        db = get_db()
        metricas = db.obtener_metricas_contactos()
        status_code = 200 if metricas.get('status') == 'success' else 500
        return jsonify(metricas), status_code
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/contactos/abiertos/<codigo_aliado>', methods=['GET'])
@require_aliado
def contactos_abiertos_por_codigo(codigo_aliado):
    """
    GET /api/contactos/abiertos/<codigo_aliado>
    Devuelve contactos abiertos del aliado. Solo se permite el c?digo de la sesi?n.
    """
    try:
        codigo_aliado = codigo_aliado.strip()
        if codigo_aliado != _aliado_codigo():
            return jsonify({'status': 'error', 'message': 'No autorizado'}), 403

        db = get_db()
        contactos = db.obtener_contactos_abiertos_por_codigo(codigo_aliado)
        contactos = _priorizar_contactos_con_mensajes(contactos)

        return jsonify({
            'status': 'success',
            'total': len(contactos),
            'contactos': contactos,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/aliado/contactos-pago-pendiente', methods=['GET'])
@require_aliado
def aliado_contactos_pago_pendiente():
    """
    GET /api/aliado/contactos-pago-pendiente
    Lista contactos donde el aliado en sesi?n es profesional y estado_pago = pendiente_pago.
    """
    try:
        codigo = _aliado_codigo()
        if not codigo:
            return jsonify({'status': 'error', 'message': 'Sesi?n expirada'}), 401
        db = get_db()
        lista = db.listar_contactos_pago_pendiente_profesional(codigo)
        return jsonify({'status': 'success', 'contactos': lista})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/contactos/<int:contacto_id>', methods=['GET'])
@require_aliado
def obtener_contacto_resumen(contacto_id):
    """
    GET /api/contactos/<id>
    Devuelve resumen del contacto solo si el aliado en sesi?n es solicitante o profesional.
    """
    try:
        codigo = _aliado_codigo()
        if not codigo:
            return jsonify({'status': 'error', 'message': 'Sesi?n expirada'}), 401
        db = get_db()
        contacto = db.obtener_contacto_resumen(contacto_id)
        if not contacto:
            return jsonify({
                'status': 'error',
                'message': f'Contacto {contacto_id} no encontrado'
            }), 404
        sol = str(contacto.get('solicitante_codigo') or '').strip()
        pro = str(contacto.get('profesional_codigo') or '').strip()
        if codigo not in (sol, pro):
            return jsonify({'status': 'error', 'message': 'No autorizado a ver este contacto'}), 403

        return jsonify({
            'status': 'success',
            'contacto': contacto,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/contactos/<int:contacto_id>/comprobante-apoyo', methods=['POST'])
@require_aliado
def subir_comprobante_apoyo(contacto_id):
    """
    POST /api/contactos/<id>/comprobante-apoyo
    El profesional (aliado en sesi?n) sube comprobante de pago del Apoyo RUANA.
    Form: archivo (o file), comentario (opcional).
    """
    try:
        codigo = _aliado_codigo()
        if not codigo:
            return jsonify({'status': 'error', 'message': 'Sesi?n expirada'}), 401
        if 'archivo' not in request.files and 'file' not in request.files:
            return jsonify({'status': 'error', 'message': 'Falta el archivo (archivo o file)'}), 400
        file = request.files.get('archivo') or request.files.get('file')
        if not file or not file.filename:
            return jsonify({'status': 'error', 'message': 'Archivo vac?o'}), 400
        comentario = (request.form.get('comentario') or '').strip()[:500]
        ext = (Path(file.filename).suffix or '.bin').lower()
        if ext not in ('.pdf', '.jpg', '.jpeg', '.png', '.gif', '.webp'):
            return jsonify({'status': 'error', 'message': 'Formato no permitido. Usa imagen (jpg, png, gif, webp) o PDF.'}), 400
        storage_result = upload_ruana_file(
            file_obj=file.stream,
            original_filename=file.filename,
            bucket='ruana-comprobantes',
            folder='pagos_ruana',
            prefix=str(contacto_id),
            content_type=file.mimetype,
        )
        comprobante_ruta = storage_result['url']
        db = get_db()
        result = db.subir_comprobante_apoyo_ruana(contacto_id, codigo, comprobante_ruta, comentario or None)
        if result.get('status') != 'success':
            return jsonify(result), 400
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/metodos-pago', methods=['GET'])
@require_aliado
def metodos_pago_ruana():
    """Devuelve los metodos de pago RUANA visibles para aliados autenticados."""
    try:
        db = get_db()
        return jsonify({'status': 'success', 'metodos': db.obtener_metodos_pago_ruana()}), 200
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/admin/metodos-pago', methods=['GET'])
@require_admin
def admin_obtener_metodos_pago():
    """Admin lee la configuracion actual de metodos de pago."""
    try:
        db = get_db()
        return jsonify({'status': 'success', 'metodos': db.obtener_metodos_pago_ruana()}), 200
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/admin/metodos-pago', methods=['POST'])
@require_admin_escritura
def admin_actualizar_metodos_pago():
    """Admin actualiza Bizum e IBAN de cobro RUANA."""
    try:
        data = request.get_json() or {}
        valores = {}
        for clave in ('bizum_num', 'iban'):
            if clave in data:
                valores[clave] = (data.get(clave) or '').strip()
        if 'iban' in valores and valores['iban']:
            iban_limpio = valores['iban'].replace(' ', '').upper()
            if not iban_limpio.startswith('ES') or len(iban_limpio) != 24:
                return jsonify({'status': 'error', 'message': 'IBAN espanol no valido'}), 400
            valores['iban'] = iban_limpio
        db = get_db()
        result = db.actualizar_metodos_pago_ruana(valores, admin_codigo=_admin_codigo() or None)
        status_code = 200 if result.get('status') == 'success' else 400
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/admin/metodos-pago/qr-revolut', methods=['POST'])
@require_admin_escritura
def admin_subir_qr_revolut():
    """Admin sube el QR Revolut a Supabase Storage y actualiza la configuracion."""
    try:
        if 'archivo' not in request.files and 'file' not in request.files:
            return jsonify({'status': 'error', 'message': 'Falta el archivo (archivo o file)'}), 400
        file = request.files.get('archivo') or request.files.get('file')
        if not file or not file.filename:
            return jsonify({'status': 'error', 'message': 'Archivo vacio'}), 400
        ext = (Path(file.filename).suffix or '.bin').lower()
        if ext not in ('.jpg', '.jpeg', '.png', '.webp'):
            return jsonify({'status': 'error', 'message': 'Formato no permitido. Usa jpg, png o webp.'}), 400
        storage_result = upload_ruana_file(
            file_obj=file.stream,
            original_filename=file.filename,
            bucket='ruana-public',
            folder='metodos_pago',
            prefix='revolut',
            content_type=file.mimetype,
        )
        db = get_db()
        result = db.actualizar_metodos_pago_ruana(
            {'qr_revolut_path': storage_result['url']},
            admin_codigo=_admin_codigo() or None,
        )
        status_code = 200 if result.get('status') == 'success' else 400
        return jsonify(result), status_code
    except ValueError as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/contactos/<int:contacto_id>/impugnar-apoyo', methods=['POST'])
@require_aliado
def impugnar_apoyo(contacto_id):
    """
    POST /api/contactos/<id>/impugnar-apoyo
    El profesional impugna el importe declarado por el contratante.
    """
    try:
        codigo = _aliado_codigo()
        if not codigo:
            return jsonify({'status': 'error', 'message': 'Sesi?n expirada'}), 401
        data = request.get_json(silent=True) or {}
        motivo = (data.get('motivo') or '').strip()
        db = get_db()
        result = db.impugnar_apoyo_ruana(contacto_id, codigo, motivo)
        status_code = 200 if result.get('status') == 'success' else 400
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/aliados/registrar', methods=['POST'])
def registrar_aliado():
    """
    POST /api/aliados/registrar
    
    Registra un nuevo aliado en SQLite
    
    Body JSON:
    {
        "nombre": "Juan P?rez",
        "marca": "JP Construcci?n",
        "oficio": "Constructor",
        "codigo_postal": "080001",
        "email": "juan@example.com",
        "telefono": "+57 3001234567"
    }
    """
    try:
        data = request.get_json() or {}
        db = get_db()
        
        # Validar campos requeridos
        # F07: Validaci?n coherente - Opci?n A: Email y tel?fono OBLIGATORIOS
        # Una ?nica fuente de verdad: frontend debe cumplir esto, backend lo valida
        required = ['nombre', 'email', 'telefono']
        for field in required:
            if not data.get(field, '').strip():
                return jsonify({
                    'status': 'error',
                    'message': f'Campo requerido: {field}'
                }), 400
        
        # F07: Validaci?n de formato ANTES de DB (una ?nica fuente de verdad en app.py)
        nombre = data.get('nombre', '').strip()
        email = data.get('email', '').strip()
        telefono = data.get('telefono', '').strip()
        
        # Validar nombre
        if len(nombre) < 3:
            return jsonify({
                'status': 'error',
                'message': 'El nombre debe tener al menos 3 caracteres'
            }), 400
        
        # F07: Validar email
        if '@' not in email or '.' not in email.split('@')[1]:
            return jsonify({
                'status': 'error',
                'message': 'Email inv?lido (debe contener @ y dominio v?lido)'
            }), 400
        
        # F07: Validar tel?fono (solo d?gitos, al menos 7; se ignoran espacios y s?mbolos)
        import re
        digitos = re.sub(r'\D', '', telefono)
        if len(digitos) < 7:
            return jsonify({
                'status': 'error',
                'message': 'Tel?fono inv?lido (debe tener al menos 7 d?gitos)'
            }), 400
        
        # Oficio principal obligatorio (catálogo oficial)
        oficio = (data.get('oficio') or data.get('oficio_principal') or '').strip()
        if not oficio:
            return jsonify({
                'status': 'error',
                'message': 'El oficio principal es obligatorio. Elige uno del catálogo.'
            }), 400

        # Especialización que ocupa plaza (una por grupo). Obligatoria si el catálogo es jerárquico; si no se envía, se usa el oficio.
        especializacion_plaza = (data.get('especializacion') or '').strip() or oficio

        # Especializaciones adicionales (solo del mismo oficio; máx. 3 en total: 1 plaza + 2 más)
        especializaciones = data.get('especializaciones')
        if isinstance(especializaciones, list):
            especializaciones = [str(e).strip() for e in especializaciones if str(e).strip()][:2]
        else:
            especializaciones = []


        # Si viene con código de invitación "Conozco a alguien", intentar asignar al grupo del invitador si cumple reglas
        grupo_id_invitacion = None
        codigo_postal = (data.get('codigo_postal') or '').strip()
        codigo_invitacion_raw = (data.get('codigo_invitacion') or '').strip()
        codigo_placeholder = None
        codigo_campana_invitacion = None
        if codigo_invitacion_raw and not re.match(RUANA_CODIGO_INVITACION_REGEX, codigo_invitacion_raw.upper()):
            campana = db.validar_campana_invitacion(codigo_invitacion_raw.upper()) if hasattr(db, 'validar_campana_invitacion') else None
            if campana:
                codigo_campana_invitacion = (campana.get('codigo') or codigo_invitacion_raw).strip().upper()
                if not codigo_postal and campana.get('codigo_postal'):
                    codigo_postal = (campana.get('codigo_postal') or '').strip()
            else:
                aliado_invitacion = db.obtener_aliado_por_codigo(codigo_invitacion_raw)
                if not aliado_invitacion or (aliado_invitacion.get('estado') or '').strip() != 'pendiente_completar':
                    return jsonify({
                        'status': 'error',
                        'message': f'Codigo de invitacion {codigo_invitacion_raw} no encontrado o ya usado.'
                    }), 404
                codigo_placeholder = (aliado_invitacion.get('codigo') or codigo_invitacion_raw).strip()
                grupo_inv = db.obtener_grupo_invitador_por_codigo_invitacion(codigo_invitacion_raw)
                if grupo_inv and grupo_inv.get('grupo_id'):
                    grupo_id_invitacion = grupo_inv['grupo_id']

        # Validar disponibilidad de la plaza antes de confirmar (evitar condición de carrera)
        if grupo_id_invitacion:
            if db.plaza_ocupada_en_grupo(grupo_id_invitacion, oficio, especializacion_plaza):
                return jsonify({
                    'status': 'error',
                    'message': 'La especialización elegida ya no está disponible en este grupo. Elige otra.',
                    'code': 'plaza_ocupada'
                }), 409
        elif codigo_postal:
            grupo_libre = db.buscar_grupo_sin_oficio(codigo_postal, oficio, especializacion_plaza)
            if not grupo_libre and db.contar_grupos_activos_por_cp(codigo_postal) >= 5:
                return jsonify({
                    'status': 'error',
                    'message': 'No hay plaza libre para esta especialización en tu código postal. Límite de grupos alcanzado.',
                    'code': 'sin_plaza'
                }), 409

        # Crear aliado: si oficio no está en catálogo → estado pendiente_validacion (validación manual)
        descripcion_servicio = (data.get('descripcion') or data.get('descripcion_servicio') or '').strip() or None
        if codigo_placeholder:
            result = db.completar_aliado_pendiente(
                codigo=codigo_placeholder,
                nombre=nombre,
                marca=data.get('marca', '').strip(),
                oficio=oficio,
                codigo_postal=codigo_postal,
                email=email,
                telefono=telefono,
                estado='activo',
                score=50,
                especializaciones=especializaciones,
                especializacion=especializacion_plaza,
                descripcion_servicio=descripcion_servicio,
                grupo_id_invitacion=grupo_id_invitacion
            )
        else:
            # Generar codigo unico (5 digitos) solo si no estamos completando un placeholder.
            codigo = _generar_codigo_unico()
            result = db.crear_aliado(
                codigo=codigo,
                nombre=nombre,
                marca=data.get('marca', '').strip(),
                oficio=oficio,
                codigo_postal=codigo_postal,
                email=email,
                telefono=telefono,
                estado='activo',
                score=50,
                especializaciones=especializaciones,
                especializacion=especializacion_plaza,
                descripcion_servicio=descripcion_servicio,
                grupo_id_invitacion=grupo_id_invitacion
            )
        
        if result['status'] == 'error':
            return jsonify(result), 400

        # Oficio o suboficio fuera de catálogo → pendiente_validacion (validación manual por admin)
        if result.get('estado') == 'pendiente_validacion':
            result['mensaje_pendiente_validacion'] = (
                'Tu oficio o suboficio no está en el catálogo oficial. Tu cuenta queda pendiente de validación. '
                'Guarda tu código personal. Tus datos se han enviado al panel de administración en "Aliados pendientes de validación", '
                'donde un administrador podrá aceptarte o rechazarte. Cuando te activen, podrás entrar con este mismo código.'
            )

        # Si registr? con c?digo de invitaci?n v?lido
        codigo_invitacion = (data.get('codigo_invitacion') or '').strip()
        if codigo_invitacion:
            codigo_inv_upper = codigo_invitacion.upper()
            # C?digo RUANA-XXX-OFICIO-XXXX: invitaci?n por oficio (una sola vez)
            if re.match(RUANA_CODIGO_INVITACION_REGEX, codigo_inv_upper):
                db.consumir_invitacion_oficio(codigo_inv_upper, result['codigo'])
            elif codigo_campana_invitacion:
                db.consumir_campana_invitacion(codigo_campana_invitacion, result['codigo'])
            else:
                if not db.consumir_invitacion_y_recompensar(codigo_invitacion, result['codigo']):
                    db.asegurar_referido_desde_invitacion(codigo_invitacion, result['codigo'])

        # Asegurar red completa: invitaciones pendientes de sync y huérfanos bajo admin
        db.sincronizar_referidos_completo()

        return jsonify(result), 201
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/aliados/obtener-por-codigo/<codigo>', methods=['GET'])
def obtener_aliado_codigo(codigo):
    """
    GET /api/aliados/obtener-por-codigo/XXXXX
    
    Obtiene aliado por su c?digo (5 d?gitos o legacy alfanum?rico)
    F08: Aceptar c?digos num?ricos (12345) y legacy (A0001)
    Retorna todos sus datos para renderizar el panel din?mico
    """
    try:
        codigo = codigo.strip()
        auth_err = _forbidden_unless_admin_or_aliado_self(codigo)
        if auth_err:
            return auth_err
        
        # F08: Validaci?n de formato para compatibilidad legacy
        # Aceptar:
        #   - d?gitos num?ricos (^\d{5}$)  ? ej: 47604
        #   - legacy 1 letra + 4 d?gitos (^[A-Z]\d{4}$) ? ej: A0001
        #   - legacy 4 letras + 2 d?gitos (^[A-Z]{4}\d{2}$) ? ej: ALFA01/BETA02
        import re
        if not codigo:
            return jsonify({
                'status': 'error',
                'message': 'C?digo requerido'
            }), 400
        
        # Validar formato: 5 d?gitos OR 1 letra + 4 d?gitos OR 4 letras + 2 d?gitos (legacy)
        if not (
            re.match(r'^\d{5}$', codigo) or
            re.match(r'^[A-Z]\d{4}$', codigo) or
            re.match(r'^[A-Z]{4}\d{2}$', codigo)
        ):
            return jsonify({
                'status': 'error',
                'message': 'C?digo inv?lido (debe ser 5 d?gitos o formato legacy como A0001)'
            }), 400
        
        db = get_db()
        aliado = db.obtener_aliado_por_codigo(codigo)
        
        if not aliado:
            return jsonify({
                'status': 'error',
                'message': f'Aliado con c?digo {codigo} no encontrado'
            }), 404

        # Cuenta pendiente de validaci?n: se avisa al usuario y sus datos est?n en el panel admin para aceptar/rechazar
        if aliado.get('estado') == 'pendiente_validacion':
            return jsonify({
                'status': 'error',
                'message': 'Tu cuenta est? pendiente de validaci?n. Tus datos est?n en el panel de administraci?n en la secci?n "Pendientes de validaci?n", donde un administrador puede aceptarte o rechazarte. Cuando te activen, podr?s entrar con este mismo c?digo.'
            }), 403
        if aliado.get('estado') == 'rechazado':
            return jsonify({
                'status': 'error',
                'message': 'Tu solicitud de registro no fue aceptada. Contacta al administrador si crees que es un error.'
            }), 403
        
        # Obtener solicitudes del grupo si tiene c?digo postal
        solicitudes = []
        if aliado.get('codigo_postal'):
            solicitudes = db.obtener_solicitudes_grupo(aliado['codigo_postal'])
        
        aliado_dict = dict(aliado)
        aliado_dict['estado_ruana'] = db.score_a_estado(aliado.get('score'))
        aliado_dict['referidos_count'] = db.contar_referidos_por_codigo(codigo)
        contar_contestadas = getattr(db, 'contar_solicitudes_enviadas_contestadas', lambda c: 0)
        aliado_dict['solicitudes_enviadas_contestadas'] = contar_contestadas(codigo)
        
        return jsonify({
            'status': 'success',
            'aliado': aliado_dict,
            'solicitudes': solicitudes,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/aliados/verificar-codigo/<codigo>', methods=['GET'])
@require_admin
def verificar_codigo_existe(codigo):
    """
    GET /api/aliados/verificar-codigo/XXXXX
    
    Verifica si un c?digo ya existe en la BD
    Usado por el frontend para validaci?n de unicidad
    """
    try:
        codigo = codigo.strip()
        db = get_db()
        
        existe = db.codigo_existe(codigo)
        
        return jsonify({
            'status': 'success',
            'existe': existe,
            'codigo': codigo
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/aliados/listar', methods=['GET'])
@require_admin
def listar_aliados_db():
    """
    GET /api/aliados/listar
    GET /api/aliados/listar?codigo_postal=080001
    
    Lista todos los aliados o filtra por c?digo postal
    """
    try:
        codigo_postal = request.args.get('codigo_postal', '').strip() or None
        
        db = get_db()
        aliados = db.listar_aliados(codigo_postal)

        return jsonify({
            'status': 'success',
            'total': len(aliados),
            'aliados': aliados,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/aliado/pausar', methods=['POST'])
@require_admin_escritura
def pausar_aliado():
    """
    POST /api/aliado/pausar

    Body JSON:
    {
        "codigo": "12345",
        "razon": "Motivo opcional de la pausa"
    }
    """
    try:
        data = request.get_json() or {}
        codigo = (data.get('codigo') or '').strip()
        razon = (data.get('razon') or '').strip() or None

        if not codigo:
            return jsonify({'status': 'error', 'message': 'C?digo de aliado obligatorio'}), 400

        db = get_db()
        admin_codigo = _admin_codigo() or ''
        result = db.pausar_aliado(codigo, razon, admin_codigo=admin_codigo or None)

        status_code = 200 if result.get('status') == 'success' else 400
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/aliados/<codigo>/foto-perfil', methods=['POST'])
@require_aliado
def subir_foto_perfil_aliado(codigo):
    """
    POST /api/aliados/<codigo>/foto-perfil
    Sube o reemplaza la foto de perfil del aliado. Solo el propio aliado en sesión.
    Form: archivo (o file). Formatos: jpg, png, gif, webp, heic, heif. Máx. 15 MB.
    """
    try:
        codigo = (codigo or '').strip()
        if codigo != _aliado_codigo():
            return jsonify({'status': 'error', 'message': 'No autorizado a actualizar otro aliado'}), 403
        if 'archivo' not in request.files and 'file' not in request.files:
            return jsonify({'status': 'error', 'message': 'Falta el archivo (archivo o file)'}), 400
        file = request.files.get('archivo') or request.files.get('file')
        if not file or not file.filename:
            return jsonify({'status': 'error', 'message': 'Archivo vacío'}), 400
        ext = (Path(file.filename).suffix or '.bin').lower()
        if ext not in ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.heic', '.heif'):
            return jsonify({'status': 'error', 'message': 'Formato no permitido. Usa una imagen (jpg, png, gif, webp o heic).'}), 400
        storage_result = upload_foto_perfil_file(
            file_obj=file.stream,
            original_filename=file.filename,
            prefix=codigo,
        )
        db = get_db()
        result = db.actualizar_aliado(codigo, foto_perfil_url=storage_result['url'])
        if result.get('status') != 'success':
            return jsonify(result), 400
        return jsonify({
            'status': 'success',
            'message': 'Foto de perfil actualizada',
            'foto_perfil_url': storage_result['url'],
        }), 200
    except ValueError as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400
    except Exception as e:
        msg = str(e)
        if '413' in msg or 'Payload too large' in msg or 'maximum allowed size' in msg:
            return jsonify({
                'status': 'error',
                'message': 'La imagen es demasiado pesada para almacenarla. Prueba con otra foto.',
            }), 400
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/aliados/<codigo>/foto-perfil', methods=['DELETE'])
@require_aliado
def eliminar_foto_perfil_aliado(codigo):
    """DELETE /api/aliados/<codigo>/foto-perfil — quita la foto y vuelve a mostrar iniciales."""
    try:
        codigo = (codigo or '').strip()
        if codigo != _aliado_codigo():
            return jsonify({'status': 'error', 'message': 'No autorizado a actualizar otro aliado'}), 403
        db = get_db()
        result = db.actualizar_aliado(codigo, foto_perfil_url=None)
        if result.get('status') != 'success':
            return jsonify(result), 400
        return jsonify({'status': 'success', 'message': 'Foto de perfil eliminada'}), 200
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/aliados/<codigo>', methods=['PUT'])
@require_aliado
def actualizar_aliado_db(codigo):
    """
    PUT /api/aliados/XXXXX
    Actualiza datos del aliado. Solo se permite actualizar el propio c?digo (sesi?n).
    """
    try:
        codigo = codigo.strip()
        if codigo != _aliado_codigo():
            return jsonify({'status': 'error', 'message': 'No autorizado a actualizar otro aliado'}), 403
        data = request.get_json() or {}
        data = {k: v for k, v in data.items() if k in _ALIADO_SELF_EDITABLE_FIELDS}
        db = get_db()
        result = db.actualizar_aliado(codigo, **data)
        
        if result['status'] == 'error':
            return jsonify(result), 400
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/aliados/<codigo>/notificaciones', methods=['GET'])
@require_aliado
def get_notificaciones_aliado(codigo):
    """
    GET /api/aliados/XXXXX/notificaciones
    Lista notificaciones del aliado. Solo se permite el c?digo de la sesi?n.
    """
    try:
        codigo = (codigo or "").strip()
        if codigo != _aliado_codigo():
            return jsonify({'status': 'error', 'message': 'No autorizado'}), 403
        limite = request.args.get('limite', 50, type=int)
        db = get_db()
        notificaciones = db.listar_notificaciones_aliado(codigo, limite=limite)
        return jsonify({'status': 'success', 'notificaciones': notificaciones})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/aliados/<codigo>/notificaciones/marcar-todas-leidas', methods=['POST'])
@require_aliado
def marcar_todas_notificaciones_leidas_api(codigo):
    """
    POST /api/aliados/<codigo>/notificaciones/marcar-todas-leidas
    Marca todas las notificaciones del aliado como le?das. Solo c?digo de sesi?n.
    """
    try:
        codigo = (codigo or "").strip()
        if codigo != _aliado_codigo():
            return jsonify({'status': 'error', 'message': 'No autorizado'}), 403
        db = get_db()
        result = db.marcar_todas_notificaciones_leidas(codigo)
        if result.get('status') == 'error':
            return jsonify(result), 400
        return jsonify(result)
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/aliados/<codigo>/notificaciones/<int:notif_id>/leida', methods=['POST'])
@require_aliado
def marcar_notificacion_leida_api(codigo, notif_id):
    """
    POST /api/aliados/XXXXX/notificaciones/<id>/leida
    Marca una notificaci?n como le?da. Solo c?digo de sesi?n.
    """
    try:
        codigo = (codigo or "").strip()
        if codigo != _aliado_codigo():
            return jsonify({'status': 'error', 'message': 'No autorizado'}), 403
        db = get_db()
        result = db.marcar_notificacion_leida(notif_id, codigo)
        if result.get('status') == 'error':
            return jsonify(result), 400
        return jsonify(result)
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ================================================
# EVALUACIONES (Motor RUANA)
# ================================================

@app.route('/api/evaluaciones/<codigo_aliado>', methods=['GET'])
@require_aliado
def obtener_evaluacion(codigo_aliado):
    """
    GET /api/evaluaciones/XXXXX
    Obtiene la evaluaci?n m?s reciente del aliado. Solo se permite el c?digo de la sesi?n.
    """
    try:
        codigo_aliado = codigo_aliado.strip()
        if codigo_aliado != _aliado_codigo():
            return jsonify({'status': 'error', 'message': 'No autorizado'}), 403
        db = get_db()
        evaluacion = db.obtener_evaluacion(codigo_aliado)
        
        if not evaluacion:
            return jsonify({
                'status': 'error',
                'message': f'No hay evaluaci?n para {codigo_aliado}'
            }), 404
        
        return jsonify({
            'status': 'success',
            'evaluacion': evaluacion,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/evaluaciones', methods=['GET'])
@require_admin
def listar_evaluaciones():
    """
    GET /api/evaluaciones
    GET /api/evaluaciones?estado=verde
    
    Lista todas las evaluaciones o filtra por estado
    """
    try:
        estado = request.args.get('estado', '').strip() or None
        db = get_db()
        
        evaluaciones = db.listar_evaluaciones(estado)
        
        return jsonify({
            'status': 'success',
            'total': len(evaluaciones),
            'evaluaciones': evaluaciones,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/evaluaciones/<codigo_aliado>/historico', methods=['GET'])
def obtener_historico_evaluacion(codigo_aliado):
    """
    GET /api/evaluaciones/XXXXX/historico
    
    Obtiene el hist?rico de cambios de evaluaci?n de un aliado
    """
    try:
        codigo_aliado = codigo_aliado.strip()
        auth_err = _forbidden_unless_admin_or_aliado_self(codigo_aliado)
        if auth_err:
            return auth_err
        db = get_db()
        
        historico = db.obtener_historico_evaluaciones(codigo_aliado)
        
        return jsonify({
            'status': 'success',
            'historico': historico,
            'total': len(historico),
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/evaluaciones/estadisticas', methods=['GET'])
@require_admin
def estadisticas_evaluaciones():
    """
    GET /api/evaluaciones/estadisticas
    
    Retorna estad?sticas generales de las evaluaciones
    """
    try:
        db = get_db()
        stats = db.obtener_estadisticas_evaluaciones()
        
        return jsonify({
            'status': 'success',
            'estadisticas': stats,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/admin/evaluaciones/<codigo_aliado>', methods=['GET'])
@require_admin
def admin_obtener_evaluacion(codigo_aliado):
    """
    GET /api/admin/evaluaciones/XXXXX
    Obtiene la evaluaci?n de un aliado para el panel admin (VER DETALLE).
    Si no existe en BD, calcula m?tricas e intenci?n/severidad/razones con el motor.
    """
    try:
        codigo_aliado = (codigo_aliado or '').strip()
        if not codigo_aliado:
            return jsonify({'status': 'error', 'message': 'Código de aliado requerido'}), 400
        db = get_db()
        evaluacion = db.obtener_evaluacion(codigo_aliado)
        if evaluacion:
            # Asegurar razones como lista para el frontend
            r = evaluacion.get('razones')
            if r is not None and not isinstance(r, list):
                try:
                    evaluacion = dict(evaluacion)
                    evaluacion['razones'] = json.loads(r) if isinstance(r, str) else (r if isinstance(r, list) else [])
                except Exception:
                    evaluacion = dict(evaluacion)
                    evaluacion['razones'] = []
            return jsonify({'status': 'success', 'evaluacion': evaluacion, 'timestamp': datetime.now().isoformat()})
        # Sin fila en evaluaciones: calcular m?tricas y decisión del motor (sin persistir)
        metrics = db.obtener_metricas_motor_por_aliado(codigo_aliado)
        from engines.motor_evaluacion import MotorEvaluacion
        motor = MotorEvaluacion()
        decision = motor._evaluar_aliado(codigo_aliado, metrics)
        decision = motor._incorporar_persistencia(codigo_aliado, decision)
        evaluacion = {
            'intencion': decision.get('intencion', ''),
            'tasa_respuesta': metrics.get('tasa_respuesta'),
            'tasa_confirmacion': metrics.get('tasa_confirmacion'),
            'meses_sin_trabajo': metrics.get('meses_sin_trabajo'),
            'severidad': decision.get('severidad', 'normal'),
            'razones': decision.get('razones', []),
            'estado': decision.get('estado'),
            'score': decision.get('score'),
            'actualizado_en': datetime.now().isoformat(),
        }
        return jsonify({'status': 'success', 'evaluacion': evaluacion, 'timestamp': datetime.now().isoformat()})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/validar-invitacion', methods=['GET'])
def validar_invitacion_query():
    """
    GET /api/validar-invitacion?codigo=XXXXX
    Valida c?digo de invitaci?n (query param). Endpoint dedicado para evitar problemas de routing.
    """
    print("[RUANA] ENDPOINT validar-invitacion (query) llamado path=%s" % request.path)
    codigo_raw = request.args.get('codigo') or ''
    return _validar_invitacion_impl(codigo_raw)


def _validar_invitacion_impl(codigo_raw):
    """L?gica com?n de validaci?n de invitaci?n."""
    try:
        codigo = ''.join(c for c in str(codigo_raw or '').strip() if c.isprintable() and c != '\x00').strip()
        if not codigo:
            return jsonify({
                'status': 'error',
                'message': 'C?digo de invitaci?n requerido'
            }), 400

        db = get_db()

        # Formato RUANA-{grupo_id}-{OFICIO}-{4chars}: invitaci?n por oficio (Oficios faltantes)
        import re
        codigo_upper = codigo.strip().upper()
        if re.match(RUANA_CODIGO_INVITACION_REGEX, codigo_upper):
            inv = db.validar_invitacion_oficio(codigo_upper)
            if not inv:
                return jsonify({
                    'status': 'error',
                    'message': 'C?digo no encontrado o ya utilizado. Cada c?digo de invitaci?n solo puede usarse una vez.'
                }), 404
            return jsonify({
                'status': 'success',
                'message': 'C?digo v?lido',
                'invitacion': {
                    'codigo': inv['codigo'],
                    'zona': inv.get('zona', ''),
                    'grupo': inv.get('grupo', ''),
                    'oficio': inv.get('oficio', ''),
                    'codigo_postal': inv.get('codigo_postal', ''),
                }
            }), 200

        campana = None
        if hasattr(db, 'validar_campana_invitacion'):
            campana = db.validar_campana_invitacion(codigo_upper)
        if campana:
            return jsonify({
                'status': 'success',
                'message': 'Codigo valido',
                'invitacion': {
                    'tipo': 'campana',
                    'codigo': campana.get('codigo'),
                    'zona': campana.get('codigo_postal') or '',
                    'grupo': None,
                    'aliado_id': None,
                    'fecha_expiracion': None,
                    'max_usos': campana.get('max_usos'),
                    'usos_actuales': campana.get('usos_actuales'),
                    'usos_restantes': campana.get('usos_restantes'),
                }
            }), 200
        if hasattr(db, 'obtener_campana_invitacion') and db.obtener_campana_invitacion(codigo_upper):
            return jsonify({
                'status': 'error',
                'message': 'Codigo de invitacion agotado o desactivado.'
            }), 404

        # Formato aliado: 5 d?gitos, A0001, ALFA01
        if not (
            re.match(r'^\d{5}$', codigo) or
            re.match(r'^[A-Z]\d{4}$', codigo) or
            re.match(r'^[A-Z]{4}\d{2}$', codigo)
        ):
            return jsonify({
                'status': 'error',
                'message': 'Formato de c?digo inv?lido'
            }), 400
        aliado = db.obtener_aliado_por_codigo(codigo)

        # LOG TEMPORAL: traza completa para depuraci?n de invitaciones
        try:
            print(f"[RUANA][INVITACION] validar_invitacion codigo={codigo} db_path={db.db_path}")
            print(f"[RUANA][INVITACION] aliado_encontrado={bool(aliado)} datos={dict(aliado) if aliado else None}")
        except Exception as _log_err:
            print(f"[RUANA][INVITACION] Error log interno: {_log_err}")

        # C?digo expulsado: desactivado, requiere nueva invitaci?n para volver
        if aliado and aliado.get('estado') == 'expulsado':
            return jsonify({
                'status': 'error',
                'message': 'C?digo desactivado. Se requiere nueva invitaci?n para volver.'
            }), 403
        # Solo c?digos "placeholder" (pendiente_completar) son invitaci?n ? registro.
        # Si el c?digo es de un aliado activo o pendiente_validacion, es c?digo de ingreso (no invitaci?n).
        if not aliado or aliado.get('estado') != 'pendiente_completar':
            if aliado and aliado.get('estado') in ('activo', 'pendiente_validacion'):
                return jsonify({
                    'status': 'error',
                    'message': 'Este c?digo es de ingreso personal. Usa la opci?n "Tengo c?digo de ingreso".'
                }), 404
            return jsonify({
                'status': 'error',
                'message': f'C?digo de invitaci?n {codigo} no encontrado o ya usado.'
            }), 404

        invitacion_payload = {
            'codigo': codigo,
            'zona': aliado.get('codigo_postal') or '',
            'grupo': None,
            'aliado_id': aliado.get('id'),
            'fecha_expiracion': None
        }

        return jsonify({
            'status': 'success',
            'message': 'C?digo v?lido',
            'invitacion': invitacion_payload
        }), 200

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Error al validar invitaci?n: {str(e)}'
        }), 500


@app.route('/api/invitaciones/validar', methods=['GET'])
def validar_invitacion_legacy():
    """GET /api/invitaciones/validar?codigo=XXXXX - alias para compatibilidad."""
    codigo_raw = request.args.get('codigo') or ''
    return _validar_invitacion_impl(codigo_raw)


@app.route('/api/invitaciones/validar/<path:codigo>', methods=['GET'])
def validar_invitacion_path(codigo):
    """GET /api/invitaciones/validar/XXXXX - c?digo en path."""
    return _validar_invitacion_impl(codigo)


def _crear_aliado_placeholder_para_invitacion(db, zona=""):
    """Crea un aliado temporal que el invitado completara al usar el codigo."""
    import random

    for _ in range(100):
        codigo = str(random.randint(10000, 99999))
        if not db.codigo_existe(codigo):
            break
    else:
        raise RuntimeError("No se pudo generar codigo unico despues de 100 intentos")

    result = db.crear_aliado(
        codigo=codigo,
        nombre=f"Nuevo Aliado - {codigo}",
        marca="",
        oficio="Pendiente",
        codigo_postal=(zona or "").strip(),
        email=f"placeholder-{codigo}@ruana.local",
        telefono=f"+34 600 {codigo}",
        estado="pendiente_completar",
        score=50,
    )
    return codigo, result


@app.route('/api/invitaciones/crear', methods=['POST'])
@require_aliado
def crear_invitacion():
    """
    POST /api/invitaciones/crear
    
    Crea un c?digo de invitaci?n para un nuevo aliado
    
    FLUJO CORREGIDO:
    - Genera un c?digo de 5 d?gitos num?ricos ?nicos
    - Crea un "aliado placeholder" en la BD con ese c?digo
    - El nuevo usuario ingresa el c?digo en index.html y accede al sistema
    - El c?digo DEBE ser aceptado por la validaci?n en /api/aliados/obtener-por-codigo/
    
    Body JSON:
    {
        "zona": "080001",
        "solicitud_id": 456
    }
    """
    try:
        data = request.get_json() or {}
        
        db = get_db()

        # La identidad del invitador sale siempre de la sesion de aliado.
        codigo_sesion = _aliado_codigo()
        aliado_sesion = db.obtener_aliado_por_codigo(codigo_sesion) if codigo_sesion else None
        if not aliado_sesion:
            return jsonify({'status': 'error', 'message': 'Aliado invitador no encontrado'}), 403
        estado_aliado = (aliado_sesion.get('estado') or '').strip().lower()
        if estado_aliado != 'activo':
            return jsonify({'status': 'error', 'message': 'Aliado no autorizado para crear invitaciones'}), 403

        aliado_invitador_id = aliado_sesion.get('id')
        zona = data.get('zona', '').strip()
        solicitud_id = data.get('solicitud_id')

        codigo, result = _crear_aliado_placeholder_para_invitacion(db, zona)
        
        if result['status'] != 'success':
            return jsonify(result), 400

        # Registrar quién invitó (para recompensa +3 y métrica de referidos al completar)
        if aliado_invitador_id is None:
            return jsonify({'status': 'error', 'message': 'No se pudo identificar al invitador'}), 500
        try:
            db._registrar_invitacion(codigo, int(aliado_invitador_id))
        except Exception as e:
            print(f"[RUANA] Error registrando invitacion {codigo}: {e}")
            return jsonify({
                'status': 'error',
                'message': 'No se pudo registrar la invitacion. Intenta de nuevo.',
            }), 500

        # Si esta invitaci?n viene de "Conozco a alguien", marcar la solicitud como contestada
        if solicitud_id is not None:
            try:
                db.atender_solicitud_por_id(int(solicitud_id), codigo_sesion)
            except (TypeError, ValueError):
                pass
        
        return jsonify({
            'status': 'success',
            'message': f'C?digo de invitaci?n creado',
            'codigo': codigo,
            'tipo': 'invitacion',
            'timestamp': datetime.now().isoformat()
        }), 201
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/admin/invitaciones/crear', methods=['POST'])
@require_admin_escritura
def admin_crear_invitacion():
    """
    POST /api/admin/invitaciones/crear
    Crea un codigo de aliado placeholder desde el panel admin.
    """
    try:
        data = request.get_json() or {}
        zona = (data.get('zona') or data.get('codigo_postal') or '').strip()
        db = get_db()
        codigo, result = _crear_aliado_placeholder_para_invitacion(db, zona)

        if result['status'] != 'success':
            return jsonify(result), 400

        # Vincular al admin como invitador para que el registro aparezca en la red de referidos.
        admin_codigo = _admin_codigo() or 'RUANA-ADMIN'
        db.obtener_o_crear_invitador_admin(admin_codigo)
        admin_aliado = db.obtener_aliado_por_codigo(admin_codigo)
        admin_id = admin_aliado.get('id') if admin_aliado else None
        if admin_id is None:
            return jsonify({'status': 'error', 'message': 'No se pudo vincular invitacion al admin'}), 500
        try:
            db._registrar_invitacion(codigo, int(admin_id))
        except Exception as e:
            print(f"[RUANA] Error registrando invitacion admin {codigo}: {e}")
            return jsonify({
                'status': 'error',
                'message': 'No se pudo registrar la invitacion admin. Intenta de nuevo.',
            }), 500

        return jsonify({
            'status': 'success',
            'message': 'Codigo de aliado creado desde admin',
            'codigo': codigo,
            'tipo': 'invitacion_admin',
            'timestamp': datetime.now().isoformat()
        }), 201
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


def _registro_url_para_invitacion(codigo):
    base = (getattr(settings, 'public_app_url', '') or request.host_url).rstrip('/')
    return f"{base}/invite.html?codigo={codigo}"


@app.route('/api/admin/invitacion-campanas', methods=['GET'])
@require_admin
def admin_listar_campanas_invitacion():
    """GET /api/admin/invitacion-campanas - Lista codigos multiuso de invitacion."""
    try:
        limite = request.args.get('limite', type=int) or 50
        db = get_db()
        campanas = db.listar_campanas_invitacion(limite=limite)
        for campana in campanas:
            campana['registro_url'] = _registro_url_para_invitacion(campana.get('codigo', ''))
        return jsonify({'status': 'success', 'campanas': campanas})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/admin/invitacion-campanas', methods=['POST'])
@require_admin_escritura
def admin_crear_campana_invitacion():
    """POST /api/admin/invitacion-campanas - Crea un codigo multiuso para QR/registro."""
    try:
        data = request.get_json() or {}
        db = get_db()
        result = db.crear_campana_invitacion(
            codigo=(data.get('codigo') or '').strip(),
            nombre=(data.get('nombre') or '').strip(),
            codigo_postal=(data.get('codigo_postal') or data.get('zona') or '').strip(),
            max_usos=data.get('max_usos') or 100,
            creado_por_admin_codigo=_admin_codigo() or ''
        )
        if result.get('status') != 'success':
            return jsonify(result), 400
        campana = result.get('campana') or {}
        registro_url = _registro_url_para_invitacion(campana.get('codigo', ''))
        return jsonify({
            'status': 'success',
            'campana': campana,
            'registro_url': registro_url,
            'qr_url': 'https://api.qrserver.com/v1/create-qr-code/?size=220x220&data=' + quote(registro_url, safe=''),
            'timestamp': datetime.now().isoformat()
        }), 201
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/admin/invitacion-campanas/<path:codigo>/desactivar', methods=['POST'])
@require_admin_escritura
def admin_desactivar_campana_invitacion(codigo):
    """POST /api/admin/invitacion-campanas/<codigo>/desactivar - Da de baja un codigo multiuso."""
    try:
        db = get_db()
        result = db.desactivar_campana_invitacion(codigo)
        if result.get('status') != 'success':
            return jsonify(result), 404
        return jsonify(result), 200
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/competencia/finalizar-vencidas', methods=['POST'])
@require_admin_escritura
def finalizar_competencia_vencidas():
    """
    POST /api/competencia/finalizar-vencidas
    Finaliza competencias cuya fecha_fin_prevista ha pasado. Mayor score permanece, el otro sale.
    Pensado para cron o ejecuci?n peri?dica.
    """
    try:
        db = get_db()
        resultados = db.finalizar_competencia_activas_vencidas()
        return jsonify({
            'status': 'success',
            'finalizadas': len(resultados),
            'resultados': resultados,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/purga/mensual', methods=['POST'])
@require_admin_escritura
def purga_mensual():
    """
    POST /api/purga/mensual
    Ejecuta la purga mensual de calidad: finaliza competencias vencidas y aplica reglas de pool.
    Aliados en pool (1 derrota) que no ganan competencia en N meses o mantienen score bajo
    ? expulsi?n temporal (suspendido_temporal). No permite acumulaci?n indefinida.
    Pensado para cron mensual.
    """
    try:
        db = get_db()
        resultado = db.purga_mensual()
        return jsonify({
            **resultado,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/admin/validar', methods=['POST'])
def validar_admin():
    """
    POST /api/admin/validar
    Valida si el c?digo proporcionado es un c?digo de administrador
    Lee desde archivo persistente de configuraci?n
    """
    data = request.get_json() or {}
    codigo = data.get('codigo', '').strip().upper()
    
    if not codigo:
        return jsonify({
            'status': 'error',
            'message': 'C?digo requerido'
        }), 400
    
    try:
        # Cargar c?digos desde archivo de configuraci?n
        config_path = Path(__file__).parent.parent / 'config' / 'admin_codes.json'
        
        if not config_path.exists():
            return jsonify({
                'status': 'error',
                'message': 'Configuraci?n de administrador no encontrada'
            }), 500
        
        with open(config_path, 'r', encoding='utf-8') as f:
            admin_config = json.load(f)
        
        admin_codes = admin_config.get('admin_codes', {})
        
        if codigo in admin_codes:
            admin_info = admin_codes[codigo]
            
            # Verificar si est? activo
            if not admin_info.get('activo', True):
                return jsonify({
                    'status': 'error',
                    'message': 'Este c?digo de administrador est? desactivado'
                }), 401

            expires_at = time.time() + ADMIN_SESSION_EXPIRES_SECONDS
            permisos = admin_info.get('permisos', [])
            session_id = _ruana_session_create('admin', codigo, expires_at, permisos=permisos)

            payload = {
                'admin_codigo': codigo,
                'permisos': permisos,
                'exp': expires_at,
                'iat': time.time()
            }
            token = jwt.encode(payload, app.secret_key, algorithm='HS256')
            if hasattr(token, 'decode'):
                token = token.decode('utf-8')

            return jsonify({
                'status': 'success',
                'message': f'Acceso concedido como {admin_info.get("nombre")}',
                'role': admin_info.get('nombre'),
                'permisos': admin_info.get('permisos', []),
                'expires_at': expires_at,
                'session_id': session_id,
                'token': token
            })
        
        return jsonify({
            'status': 'error',
            'message': 'C?digo de administrador no v?lido'
        }), 401

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Error al validar: {str(e)}'
        }), 500


@app.route('/api/admin/logout', methods=['POST'])
def logout_admin():
    """
    POST /api/admin/logout
    Invalida la sesión indicada por header X-Ruana-Session-Id (o body session_id). El cliente debe
    eliminar session_id de sessionStorage y esperar esta respuesta.
    """
    sid = request.headers.get(RUANA_SESSION_HEADER) or (request.get_json() or {}).get('session_id')
    _ruana_session_invalidate(sid)
    return jsonify({'status': 'success', 'message': 'Sesi\u00f3n cerrada'})


@app.route('/api/admin/me', methods=['GET'])
@require_admin
def admin_me():
    """
    GET /api/admin/me
    Devuelve permisos del admin actual (store por header o JWT).
    """
    permisos = _admin_permisos()
    if not permisos and _admin_codigo():
        permisos = ['leer', 'escribir', 'eliminar', 'configurar']
    return jsonify({'permisos': permisos or []})


@app.route('/api/admin/health-metrics', methods=['GET'])
@require_admin
def admin_health_metrics():
    """
    GET /api/admin/health-metrics
    M?tricas de salud del sistema:
    - ratio_solicitud_invitacion
    - ratio_invitacion_registro
    - oficios_saturados (m?s de X suplentes en competencia)
    - oficios_disponibles (sin titular)
    - zona_mayor_demanda
    - tasa_retencion (activos / total)
    """
    try:
        db = get_db()
        umbral = request.args.get('umbral_suplentes', 1, type=int)
        umbral = max(0, min(umbral, 10))
        metrics = db.obtener_health_metrics_admin(umbral_suplentes=umbral)
        return jsonify(metrics)
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/admin/stats-24h', methods=['GET'])
@require_admin
def admin_stats_24h():
    """
    GET /api/admin/stats-24h
    Endpoint ?nico: todas las m?tricas de movimiento en las ?ltimas 24h en una respuesta.
    Respuesta: solicitudes (nuevas, atendidas, sin_respuesta), invitaciones (generadas, usadas, expiradas),
    top_invitadores [{ nombre, total }].
    """
    try:
        db = get_db()
        data = db.obtener_stats_24h_panel()
        return jsonify({'status': 'success', **data})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/admin/invitaciones-recientes', methods=['GET'])
@require_admin
def admin_invitaciones_recientes():
    """GET /api/admin/invitaciones-recientes?limite=20 - Lista ?ltimas invitaciones generadas (registro en panel)."""
    try:
        limite = request.args.get('limite', type=int) or 20
        limite = min(max(1, limite), 100)
        db = get_db()
        lista = db.listar_invitaciones_recientes(limite=limite)
        return jsonify({'status': 'success', 'invitaciones': lista})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/admin/dashboard-summary', methods=['GET'])
@require_admin
def admin_dashboard_summary():
    """
    GET /api/admin/dashboard-summary
    Resumen del dashboard global para el panel admin.
    Conecta indicadores a consultas reales:
    - total_users: COUNT users (aliados)
    - active_users: WHERE status = active
    - suplentes: WHERE role = suplente (en competencia activa)
    - en_riesgo: WHERE score < umbral o en rango EN RIESGO (35 <= score < 60)
    - solicitudes_activas: WHERE estado = pendiente (open)
    - oficios_ocupados: COUNT oficios con titular activo
    - grupos: COUNT grupos reales
    """
    try:
        db = get_db()
        aliados = db.listar_aliados()
        total_users = len(aliados)
        active_users = len([a for a in aliados if a.get('estado') == 'activo'])
        suplentes = db.contar_suplentes_activos()
        en_riesgo = db.contar_aliados_en_riesgo()
        solicitudes_activas = db.contar_solicitudes_activas()
        oficios_ocupados = db.contar_oficios_ocupados()
        grupos_data = db.contar_grupos()
        grupos = int(grupos_data.get('total', 0) or 0)

        # Estado del sistema (Estable / Alerta / Cr?tico) para la UI
        contactos_metricas = db.obtener_metricas_contactos()
        contactos_disputa = contactos_metricas.get('contactos_en_disputa', 0) or 0
        contactos_disputa_prolongada = contactos_metricas.get('contactos_en_disputa_prolongada', 0) or 0
        pct_riesgo = (en_riesgo / active_users * 100) if active_users else 0
        if pct_riesgo <= 10 and contactos_disputa <= 2 and contactos_disputa_prolongada == 0:
            estado_sistema = 'Estable'
        elif pct_riesgo <= 25 and contactos_disputa <= 5:
            estado_sistema = 'Alerta'
        else:
            estado_sistema = 'Cr?tico'

        return jsonify({
            'total_users': total_users,
            'active_users': active_users,
            'suplentes': suplentes,
            'en_riesgo': en_riesgo,
            'solicitudes_activas': solicitudes_activas,
            'oficios_ocupados': oficios_ocupados,
            'grupos': grupos,
            'grupos_activos': int(grupos_data.get('activos', 0) or 0),
            'grupos_en_competencia': int(grupos_data.get('en_competencia', 0) or 0),
            'grupos_disueltos': int(grupos_data.get('disueltos', 0) or 0),
            'estado_sistema': estado_sistema,
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/admin/forzar-suplencia', methods=['POST'])
@require_admin
def admin_forzar_suplencia():
    """
    POST /api/admin/forzar-suplencia
    Body: { "grupo_id": int, "oficio": str, "aliado_original_codigo": str, "suplente_codigo": str }
    """
    try:
        data = request.get_json() or {}
        grupo_id = data.get('grupo_id')
        oficio = (data.get('oficio') or '').strip()
        aliado_original_codigo = (data.get('aliado_original_codigo') or '').strip()
        suplente_codigo = (data.get('suplente_codigo') or '').strip()
        if grupo_id is None or not oficio or not aliado_original_codigo or not suplente_codigo:
            return jsonify({'status': 'error', 'message': 'Faltan grupo_id, oficio, aliado_original_codigo o suplente_codigo'}), 400
        db = get_db()
        admin_codigo = _admin_codigo() or None
        result = db.forzar_suplencia(int(grupo_id), oficio, aliado_original_codigo, suplente_codigo, admin_codigo=admin_codigo)
        status_code = 200 if result.get('status') == 'success' else 400
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/admin/pending-users', methods=['GET'])
@app.route('/api/admin/aliados-pendientes', methods=['GET'])
@require_admin
def admin_pending_users():
    """
    GET /api/admin/aliados-pendientes
    Lista aliados con estado pendiente_validacion (oficio fuera de cat?logo, requieren activaci?n manual).
    """
    try:
        db = get_db()
        aliados = db.listar_aliados_pendiente_validacion()
        return jsonify({'status': 'success', 'aliados': aliados, 'total': len(aliados)})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/admin/rechazar-aliado', methods=['POST'])
@require_admin_escritura
def admin_rechazar_aliado():
    """
    POST /api/admin/rechazar-aliado
    Body: { "codigo": "12345" }
    Rechaza un aliado pendiente de validaci?n. Pasa a estado rechazado y no podr? entrar al panel.
    """
    try:
        data = request.get_json() or {}
        codigo = (data.get('codigo') or '').strip()
        if not codigo:
            return jsonify({'status': 'error', 'message': 'C?digo de aliado obligatorio'}), 400
        db = get_db()
        result = db.rechazar_aliado_pendiente(codigo)
        status_code = 200 if result.get('status') == 'success' else 400
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/admin/users/<int:user_id>/activate', methods=['PATCH'])
@require_admin_escritura
def admin_users_activate(user_id):
    """
    PATCH /api/admin/users/{id}/activate
    Activa un aliado pendiente de validaci?n por ID. Actualizaci?n en tiempo real.
    """
    try:
        db = get_db()
        result = db.activar_aliado_por_id(user_id)
        status_code = 200 if result.get('status') == 'success' else 400
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/admin/activar-aliado', methods=['POST'])
@require_admin_escritura
def admin_activar_aliado():
    """
    POST /api/admin/activar-aliado
    Body: { "codigo": "12345" }
    Activa un aliado pendiente de validaci?n (cambia estado a activo).
    """
    try:
        data = request.get_json() or {}
        codigo = (data.get('codigo') or '').strip()
        if not codigo:
            return jsonify({'status': 'error', 'message': 'C?digo de aliado obligatorio'}), 400
        db = get_db()
        result = db.activar_aliado_pendiente(codigo)
        status_code = 200 if result.get('status') == 'success' else 400
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/admin/cerrar-oficio', methods=['POST'])
@require_admin_escritura
def admin_cerrar_oficio():
    """
    POST /api/admin/cerrar-oficio
    Body: { "grupo_id": int, "oficio": str }
    """
    try:
        data = request.get_json() or {}
        grupo_id = data.get('grupo_id')
        oficio = (data.get('oficio') or '').strip()
        if grupo_id is None or not oficio:
            return jsonify({'status': 'error', 'message': 'Faltan grupo_id u oficio'}), 400
        db = get_db()
        admin_codigo = _admin_codigo() or None
        result = db.cerrar_oficio_grupo(int(grupo_id), oficio, admin_codigo=admin_codigo)
        status_code = 200 if result.get('status') == 'success' else 400
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/admin/grupos/<int:grupo_id>/oficios-cerrados', methods=['GET'])
@require_admin
def admin_grupo_oficios_cerrados(grupo_id):
    """
    GET /api/admin/grupos/<grupo_id>/oficios-cerrados
    Lista oficios cerrados en ese grupo (para modal Abrir plaza → Reabrir plaza cerrada).
    """
    try:
        db = get_db()
        oficios = db.listar_oficios_cerrados_grupo(grupo_id)
        return jsonify({'status': 'success', 'oficios': oficios})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/admin/abrir-plaza', methods=['POST'])
@require_admin
def admin_abrir_plaza():
    """
    POST /api/admin/abrir-plaza
    Body: { "grupo_id": int, "oficio": str }
    Abre plaza: nueva profesión o reabrir plaza cerrada en el grupo.
    """
    try:
        data = request.get_json() or {}
        grupo_id = data.get('grupo_id')
        oficio = (data.get('oficio') or '').strip()
        if grupo_id is None or not oficio:
            return jsonify({'status': 'error', 'message': 'Faltan grupo_id u oficio'}), 400
        db = get_db()
        admin_codigo = _admin_codigo() or None
        result = db.abrir_plaza_grupo(int(grupo_id), oficio, admin_codigo=admin_codigo)
        status_code = 200 if result.get('status') == 'success' else 400
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/admin/generar-reporte', methods=['POST'])
@require_admin
def admin_generar_reporte():
    """
    POST /api/admin/generar-reporte
    Devuelve resumen de aliados, contactos, grupos, competencias, plazas cerradas.
    """
    try:
        db = get_db()
        result = db.generar_reporte()
        return jsonify(result)
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/admin/cambiar-reglas', methods=['POST'])
@require_admin_escritura
def admin_cambiar_reglas():
    """
    POST /api/admin/cambiar-reglas
    Body: { "clave": str, "valor": int }
    Claves: umbral_competencia, duracion_competencia_dias, purga_mensual_meses_sin_ganar, purga_score_bajo_umbral
    """
    try:
        data = request.get_json() or {}
        clave = (data.get('clave') or '').strip()
        valor = data.get('valor')
        if not clave or valor is None:
            return jsonify({'status': 'error', 'message': 'Faltan clave o valor'}), 400
        db = get_db()
        admin_codigo = _admin_codigo() or None
        result = db.cambiar_regla(clave, valor, admin_codigo=admin_codigo)
        status_code = 200 if result.get('status') == 'success' else 400
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/admin/solicitudes', methods=['GET'])
@require_admin
def admin_solicitudes():
    """
    GET /api/admin/solicitudes
    Todas las solicitudes (pendientes y atendidas). Orden created_at DESC.
    """
    try:
        db = get_db()
        lista = db.listar_solicitudes_admin_todas()
        return jsonify(lista)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/admin/solicitudes/<int:solicitud_id>/atender', methods=['POST'])
@require_admin_escritura
def admin_solicitud_atender(solicitud_id):
    """
    POST /api/admin/solicitudes/<id>/atender
    Marca la solicitud como atendida y registra al admin en sesión como "Atendido por" y "Atendido at".
    Sirve para rellenar columnas vacías o marcar pendientes como atendidas desde admin.
    """
    try:
        admin_codigo = _admin_codigo()
        db = get_db()
        result = db.marcar_solicitud_atendida_por_admin(solicitud_id, admin_codigo or '')
        if result.get('status') != 'success':
            return jsonify({'status': 'error', 'message': result.get('message', 'Error')}), 400
        return jsonify({'status': 'success', 'ok': True}), 200
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/admin/payment-conflicts', methods=['GET'])
@app.route('/api/admin/conflictos-pago', methods=['GET'])
@require_admin
def admin_payment_conflicts():
    """
    GET /api/admin/payment-conflicts
    Lista conflictos desde payment_conflicts (orden created_at DESC).
    Campos: id, trabajo_id, contratante_nombre, profesional_nombre, importes, estado, prueba_url, created_at.
    """
    try:
        db = get_db()
        lista = db.listar_payment_conflicts_admin()
        return jsonify({'status': 'success', 'conflictos': lista, 'total': len(lista)})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/admin/payment-conflicts/<int:conflict_id>', methods=['GET'])
@require_admin
def admin_payment_conflict_detail(conflict_id):
    """
    GET /api/admin/payment-conflicts/<id>
    Detalle de un conflicto para el panel admin (datos completos + prueba_url).
    """
    try:
        db = get_db()
        c = db.obtener_payment_conflict(conflict_id)
        if not c:
            return jsonify({'status': 'error', 'message': 'Conflicto no encontrado'}), 404
        return jsonify({'status': 'success', 'conflicto': c})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/admin/payment-conflicts/<int:conflict_id>/resolver', methods=['POST'])
@require_admin_escritura
def admin_resolver_payment_conflict(conflict_id):
    """
    POST /api/admin/payment-conflicts/<id>/resolver
    Body: { "decision": "contratante" | "profesional" | "rechazado", "comentario": "texto obligatorio" }
    Marca estado RESUELTO/RECHAZADO, guarda comentario_admin; si resuelve a favor, cierra trabajo e importe.
    """
    try:
        data = request.get_json() or {}
        decision = data.get('decision')
        comentario = data.get('comentario')
        if not decision:
            return jsonify({'status': 'error', 'message': 'Falta decision'}), 400
        if not (comentario or '').strip():
            return jsonify({'status': 'error', 'message': 'El comentario es obligatorio'}), 400
        admin_codigo = _admin_codigo() or ''
        db = get_db()
        result = db.resolver_payment_conflict_admin(conflict_id, decision, comentario, admin_codigo)
        status_code = 200 if result.get('status') == 'success' else 400
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/conflictos/por-trabajo/<int:trabajo_id>', methods=['GET'])
@require_aliado
def get_conflicto_por_trabajo(trabajo_id):
    """
    GET /api/conflictos/por-trabajo/<trabajo_id>
    Devuelve el conflicto de pago para ese trabajo si el aliado en sesi?n es contratante o profesional.
    """
    try:
        codigo = _aliado_codigo()
        if not codigo:
            return jsonify({'status': 'error', 'message': 'Sesi?n expirada'}), 401
        db = get_db()
        c = db.obtener_payment_conflict_por_trabajo(trabajo_id, codigo)
        if not c:
            return jsonify({'status': 'error', 'message': 'No hay conflicto o no autorizado'}), 404
        return jsonify({'status': 'success', 'conflicto': c})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/conflictos/<int:conflict_id>/subir-prueba', methods=['POST'])
@require_aliado
def subir_prueba_conflicto(conflict_id):
    """
    POST /api/conflictos/<id>/subir-prueba
    Solo el contratante (aliado en sesi?n). Form: archivo (file).
    """
    try:
        codigo = _aliado_codigo()
        if not codigo:
            return jsonify({'status': 'error', 'message': 'Sesi?n expirada'}), 401
        if 'archivo' not in request.files and 'file' not in request.files:
            return jsonify({'status': 'error', 'message': 'Falta el archivo (archivo o file)'}), 400
        file = request.files.get('archivo') or request.files.get('file')
        if not file or not file.filename:
            return jsonify({'status': 'error', 'message': 'Archivo vac?o'}), 400
        ext = (Path(file.filename).suffix or '.bin').lower()
        if ext not in ('.pdf', '.jpg', '.jpeg', '.png', '.gif', '.webp'):
            return jsonify({'status': 'error', 'message': 'Formato no permitido. Usa imagen (jpg, png, gif, webp) o PDF.'}), 400
        storage_result = upload_ruana_file(
            file_obj=file.stream,
            original_filename=file.filename,
            bucket='ruana-comprobantes',
            folder='conflictos',
            prefix=str(conflict_id),
            content_type=file.mimetype,
        )
        prueba_url = storage_result['url']
        db = get_db()
        result = db.subir_prueba_conflicto(conflict_id, codigo, prueba_url)
        if result.get('status') != 'success':
            return jsonify(result), 400
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/admin/conversations', methods=['GET'])
@app.route('/api/admin/contactos-conversaciones', methods=['GET'])
@require_admin
def admin_conversations():
    """
    GET /api/admin/conversations
    Lista contactos con: id, solicitante, profesional, servicio, estado, importe,
    total_mensajes, ultimo_mensaje, fecha_inicio, fecha_cierre.
    """
    try:
        db = get_db()
        limite = request.args.get('limite', 10000, type=int)
        limite = min(max(1, limite), 50000)
        raw = db.listar_contactos_recientes_con_chat(limite=limite)
        lista = []
        for c in raw:
            lista.append({
                'id': c.get('id'),
                'solicitante': c.get('solicitante_codigo'),
                'profesional': c.get('profesional_codigo'),
                'servicio': c.get('servicio'),
                'estado': c.get('estado'),
                'importe': c.get('importe_final'),
                'total_mensajes': c.get('num_mensajes', 0),
                'ultimo_mensaje': c.get('ultimo_mensaje_en'),
                'fecha_inicio': c.get('creado_en'),
                'fecha_cierre': c.get('fecha_cierre') or c.get('fecha_no_concretado'),
                # Compatibilidad con renderConversaciones
                'solicitante_codigo': c.get('solicitante_codigo'),
                'profesional_codigo': c.get('profesional_codigo'),
                'motivo_contacto': c.get('motivo_contacto'),
                'es_urgente': bool(c.get('es_urgente')),
                'urgente_marcado_en': c.get('urgente_marcado_en'),
                'importe_final': c.get('importe_final'),
                'comision': c.get('comision'),
                'num_mensajes': c.get('num_mensajes'),
                'ultimo_mensaje_en': c.get('ultimo_mensaje_en'),
                'creado_en': c.get('creado_en'),
            })
        return jsonify({'status': 'success', 'contactos': lista})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/admin/competencias-activas', methods=['GET'])
@require_admin
def admin_competencias_activas():
    """
    GET /api/admin/competencias-activas
    Lista competencias activas: titular, suplente, grupo origen, scores, tiempo en competencia.
    Ordenado por fecha_inicio ascendente (m?s antiguas arriba).
    """
    try:
        db = get_db()
        lista = db.listar_competencias_activas_admin()
        return jsonify({'status': 'success', 'competencias': lista})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/admin/chat-messages', methods=['GET'])
@require_admin
def admin_chat_messages():
    """
    GET /api/admin/chat-messages?limit=50&page=1
    Registro bruto: Fecha, Emisor, Receptor, Mensaje. Paginaci?n real.
    Acepta page (1-based) o offset. page=1 ? primeras 50, page=2 ? siguientes 50.
    """
    try:
        limit = request.args.get('limit', 50, type=int)
        limit = min(max(1, limit), 100)
        page = request.args.get('page', type=int)
        offset = request.args.get('offset', type=int)
        if page is not None and page >= 1:
            offset = (page - 1) * limit
        elif offset is None:
            offset = 0
        offset = max(0, offset)
        db = get_db()
        lista = db.listar_chat_messages(limit=limit, offset=offset)
        has_more = len(lista) == limit
        return jsonify({
            'status': 'success',
            'messages': lista,
            'page': (offset // limit) + 1 if limit else 1,
            'limit': limit,
            'has_more': has_more,
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/admin/chats', methods=['GET'])
@require_admin
def admin_chats():
    """
    GET /api/admin/chats?limite=10&offset=0
    Contactos con mensajes (paginado). Orden: más reciente primero.
    """
    try:
        limite = request.args.get('limite', 10, type=int)
        limite = min(max(1, limite), 100)
        offset = request.args.get('offset', 0, type=int)
        offset = max(0, offset)
        db = get_db()
        raw = db.listar_conversaciones_admin(limite=limite, offset=offset)
        conversaciones = []
        for c in raw:
            conversaciones.append({
                'contacto_id': c.get('contacto_id'),
                'solicitante': c.get('solicitante') or '',
                'profesional': c.get('profesional') or '',
                'ultimo_mensaje': (c.get('ultimo_mensaje') or '')[:200],
                'fecha_ultimo': c.get('fecha_ultimo'),
                'num_mensajes': c.get('num_mensajes', 0),
                'mensajes': c.get('mensajes') or [],
            })
        if len(conversaciones) == 0:
            print("ADMIN_CHATS_EMPTY")
        return jsonify({'status': 'success', 'conversaciones': conversaciones})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/admin/contactos/<int:contacto_id>/mensajes', methods=['GET'])
@require_admin
def admin_get_mensajes_chat(contacto_id):
    """
    GET /api/admin/contactos/<id>/mensajes
    Admin puede ver todos los mensajes del chat de un contacto.
    Incluye remitente: 'solicitante' | 'profesional' para cada mensaje.
    """
    try:
        db = get_db()
        mensajes = db.listar_mensajes_contacto(contacto_id)
        contacto = db.obtener_contacto_resumen(contacto_id)
        sol = (contacto or {}).get('solicitante_codigo') or ''
        prof = (contacto or {}).get('profesional_codigo') or ''
        out = []
        for m in mensajes:
            emisor = m.get('emisor_codigo') or ''
            remitente = 'solicitante' if emisor == sol else ('profesional' if emisor == prof else 'aliado')
            out.append({
                'id': m.get('id'),
                'emisor_codigo': emisor,
                'texto': m.get('texto'),
                'creado_en': m.get('creado_en'),
                'remitente': remitente,
            })
        return jsonify({
            'status': 'success',
            'mensajes': out,
            'contacto': contacto
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/admin/conflictos-pago/<int:contacto_id>/resolver', methods=['POST'])
@require_admin_escritura
def admin_resolver_conflicto_pago(contacto_id):
    """
    PATCH /api/admin/payment/<id>/resolve  o  POST /api/admin/conflictos-pago/<id>/resolver
    Body: { "importe_valido": float }
        Admin define importe valido, se calcula apoyo_pct, se cierra contacto (Apoyo pendiente).
        El score +2 se aplica al confirmar el pago Apoyo como pagado (Regla 2).
    """
    try:
        data = request.get_json() or {}
        importe_valido = data.get('importe_valido')
        if importe_valido is None:
            return jsonify({'status': 'error', 'message': 'Falta importe_valido'}), 400
        admin_codigo = _admin_codigo() or ''
        db = get_db()
        result = db.resolver_conflicto_pago(contacto_id, float(importe_valido), admin_codigo)
        status_code = 200 if result.get('status') == 'success' else 400
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/admin/pagos-apoyo', methods=['GET'])
@require_admin
def admin_pagos_apoyo():
    """
    GET /api/admin/pagos-apoyo
    Lista contactos con trabajo_cerrado e importe_final (Apoyo RUANA) para confirmar pagos manuales.
    """
    try:
        db = get_db()
        lista = db.listar_contactos_pagos_apoyo()
        return jsonify({'status': 'success', 'pagos': lista})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/admin/pagos-en-revision', methods=['GET'])
@require_admin
def admin_pagos_en_revision():
    """
    GET /api/admin/pagos-en-revision
    Lista contactos con estado_pago = en_revision (comprobante subido, pendiente de aprobar/rechazar).
    """
    try:
        db = get_db()
        lista = db.listar_contactos_pagos_en_revision()
        return jsonify({'status': 'success', 'pagos': lista})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/admin/contactos/<int:contacto_id>/estado-pago', methods=['POST'])
@require_admin_escritura
def admin_estado_pago_contacto(contacto_id):
    """
    POST /api/admin/contactos/<id>/estado-pago
    Body: { "estado_pago": "en_revision" | "pagado" | "rechazado", "motivo": "..." }
    Motivo obligatorio si estado_pago es rechazado (vuelve a pendiente_pago y notifica al profesional).
    """
    try:
        data = request.get_json() or {}
        estado_pago = data.get('estado_pago')
        if not estado_pago:
            return jsonify({'status': 'error', 'message': 'Falta estado_pago'}), 400
        if (estado_pago or '').strip().lower() == 'rechazado':
            motivo = (data.get('motivo') or '').strip()
            if not motivo:
                return jsonify({'status': 'error', 'message': 'El motivo de rechazo es obligatorio'}), 400
        else:
            motivo = None
        admin_codigo = _admin_codigo() or ''
        db = get_db()
        result = db.actualizar_estado_pago_contacto(contacto_id, estado_pago, admin_codigo, motivo_rechazo=motivo)
        status_code = 200 if result.get('status') == 'success' else 400
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ================================================
# HELPER FUNCTIONS
# ================================================

def _generar_codigo_unico() -> str:
    """
    Genera un c?digo ?nico de 5 d?gitos
    Verifica contra BD para garantizar unicidad
    """
    import random
    db = get_db()
    
    max_intentos = 100
    for _ in range(max_intentos):
        codigo = str(random.randint(10000, 99999))
        if not db.codigo_existe(codigo):
            return codigo
    
    raise Exception("No se pudo generar c?digo ?nico despu?s de 100 intentos")


# ================================================
# ERROR HANDLERS
# ================================================

@app.errorhandler(404)
def not_found(error):
    """Maneja rutas no encontradas"""
    return jsonify({
        'status': 'error',
        'message': 'Recurso no encontrado',
        'path': request.path
    }), 404


@app.errorhandler(500)
def server_error(error):
    """Maneja errores del servidor"""
    return jsonify({
        'status': 'error',
        'message': 'Error interno del servidor'
    }), 500


# ================================================
# CONFIGURACI?N Y EJECUCI?N
# ================================================

if __name__ == '__main__':
    print("=" * 60)
    print("RUANA Dashboard Server")
    print("=" * 60)
    print("Iniciando servidor en http://localhost:5000")
    print("Presione Ctrl+C para detener")
    print("=" * 60)
    
    # Configuraci?n para desarrollo
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True,
        use_reloader=True
    )
