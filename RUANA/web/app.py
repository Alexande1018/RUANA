#!/usr/bin/env python3
"""
RUANA Dashboard Web Server
Servidor Flask para servir el dashboard y API.

Rutas de negocio viven en blueprints (web/blueprints/*).
Aquí: setup Flask, middleware, páginas HTML, auth admin frágil.
"""

from flask import Flask, jsonify, send_from_directory, request, redirect, url_for, make_response
from pathlib import Path
import sys
import os
import time
import jwt

try:
    from flask_cors import CORS
except ImportError:
    CORS = None

try:
    from flask_compress import Compress
except ImportError:
    Compress = None

# Agregar parent directory al path para imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.db_manager import get_db, DB_PATH
from core.settings import get_settings
from core.storage_manager import upload_ruana_file, upload_foto_perfil_file, resolve_admin_document_access_url
from core.admin_auth import verify_admin_login, change_admin_password
from core.email_service import enviar_correo_bienvenida_aliado
from core.auth_session import (
    configure_session_secret,
    _RUANA_SESSION_STORE,
    _RUANA_SESSION_REVOKED,
    _RUANA_SESSION_LOCK,
    RUANA_SESSION_HEADER,
    _ruana_session_from_jwt,
    _get_ruana_session,
    _ruana_session_create,
    _ruana_session_invalidate,
    _ruana_session_invalidate_for_codigo,
)
from web.blueprints.catalogo_bp import catalogo_bp
from web.blueprints.negociacion_bp import negociacion_bp, priorizar_contactos_negociacion
from web.blueprints.referidos_bp import referidos_bp
from web.blueprints.admin_bp import admin_bp, _registro_url_para_invitacion
from web.blueprints.contactos_bp import contactos_bp
from web.blueprints.auth_bp import auth_bp
from web.blueprints.pagos_bp import pagos_bp
from web.blueprints.stripe_webhook_bp import stripe_webhook_bp
from web.blueprints.solicitudes_bp import solicitudes_bp
from web.blueprints.aliado_bp import (
    aliado_bp,
    _generar_codigo_unico_impl as _generar_codigo_unico,
    _ALIADO_SELF_EDITABLE_FIELDS,
)
from web.blueprints.invitacion_bp import (
    invitacion_bp,
    _generar_codigo_invitacion_impl as _generar_codigo_invitacion,
)
from web.blueprints.evaluacion_bp import evaluacion_bp
from web.blueprints.soporte_bp import soporte_bp
from web.blueprints.financial_conflicts_bp import financial_conflicts_bp
from web.blueprints.financial_refunds_bp import financial_refunds_bp
from web.blueprints.financial_disputes_bp import financial_disputes_bp
from web.auth_decorators import (
    require_admin,
    require_admin_escritura,
    require_aliado,
    _admin_session_valid,
    _admin_jwt_payload,
    _admin_permisos,
    _admin_puede_escribir,
    _admin_codigo,
    _aliado_session_valid,
    _aliado_codigo,
    _forbidden_unless_admin_or_aliado_self,
)
from web.limiter import init_limiter
from web.limiter import limiter

# Obtener ruta absoluta de la carpeta web
web_dir = Path(__file__).parent.absolute()
settings = get_settings()

app = Flask(__name__,
            static_folder=str(web_dir / 'static'),
            static_url_path='/static',
            template_folder=str(web_dir))

app.secret_key = settings.flask_secret_key
configure_session_secret(app.secret_key)
if Compress is not None:
    Compress(app)
app.register_blueprint(catalogo_bp)
app.register_blueprint(negociacion_bp)
app.register_blueprint(referidos_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(contactos_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(pagos_bp)
app.register_blueprint(stripe_webhook_bp)
app.register_blueprint(solicitudes_bp)
app.register_blueprint(aliado_bp)
app.register_blueprint(invitacion_bp)
app.register_blueprint(evaluacion_bp)
app.register_blueprint(soporte_bp)
app.register_blueprint(financial_conflicts_bp)
app.register_blueprint(financial_refunds_bp)
app.register_blueprint(financial_disputes_bp)

# Cookie de sesión segura (aliado y admin)
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

if CORS is not None:
    CORS(app)

init_limiter(app)

ADMIN_SESSION_EXPIRES_SECONDS = int(os.environ.get('RUANA_ADMIN_SESSION_EXPIRES', 3600))
ALIADO_SESSION_EXPIRES_SECONDS = int(os.environ.get('RUANA_ALIADO_SESSION_EXPIRES', 3600))

_ADMIN_PUBLIC_PATHS = ('/api/admin/logout', '/api/admin/validar', '/api/admin/bp-health')

@app.before_request
def admin_auth_middleware():
    """S-04: Middleware de autorización. Bloquea acceso a /api/admin/* sin sesión/JWT válido."""
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
    resp = jsonify({'status': 'error', 'message': 'Sesión admin expirada o no autorizado'})
    resp.status_code = 401
    return resp


# Instrumentación de arranque
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

# Reexport catálogo utils (compat tests/legacy)
from web.catalogo_utils import _catalogo_oficios_desde_archivo  # noqa: F401


def _priorizar_contactos_negociacion(contactos):
    """Fachada → blueprints.negociacion_bp."""
    return priorizar_contactos_negociacion(contactos)


# ================================================
# RUTAS HTML / ESTÁTICAS
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


@app.route('/feedback-preview')
@app.route('/feedback-preview.html')
def feedback_preview():
    """Preview del sistema unificado de comunicación visual"""
    return send_from_directory(str(web_dir), 'feedback-preview.html')


@app.route('/aliado-shell-preview')
@app.route('/aliado-shell-preview.html')
def aliado_shell_preview():
    """Preview estático del shell de aliado"""
    return send_from_directory(str(web_dir), 'aliado-shell-preview.html')


@app.route('/alert-hub-preview')
@app.route('/alert-hub-preview.html')
def alert_hub_preview():
    """Preview del hub de alertas compactas"""
    return send_from_directory(str(web_dir), 'alert-hub-preview.html')


@app.route('/static/<path:path>')
def static_files(path):
    """Sirve archivos estáticos (CSS, JS, etc) con cache-control conservador."""
    response = make_response(send_from_directory(str(web_dir / 'static'), path))
    if path.endswith(('.js', '.css', '.woff', '.woff2', '.png', '.jpg', '.jpeg', '.webp', '.svg', '.ico')):
        response.cache_control.public = True
        response.cache_control.max_age = 3600
        response.cache_control.must_revalidate = True
    return response


# ================================================
# AUTH ADMIN (frágil: validar / logout / cambiar-contraseña)
# ================================================

@app.route('/api/admin/validar', methods=['POST'])
@limiter.limit("10 per hour")
@limiter.limit("5 per minute")
def validar_admin():
    """
    POST /api/admin/validar
    Valida las credenciales de administrador (identificador + contraseña).
    Las contraseñas se almacenan con hash fuera del repositorio.
    """
    data = request.get_json() or {}
    admin_id = (data.get('codigo') or data.get('admin_id') or '').strip().upper()
    password = (
        data.get('password')
        or data.get('contraseña')
        or data.get('contrasena')
        or ''
    ).strip()

    # Compatibilidad: un solo campo "codigo" actúa como identificador y contraseña.
    if admin_id and not password:
        password = admin_id
    elif password and not admin_id:
        admin_id = password.upper()

    if not admin_id or not password:
        return jsonify({
            'status': 'error',
            'message': 'Identificador y contraseña requeridos'
        }), 400

    try:
        admin_info = verify_admin_login(admin_id, password)
        if not admin_info:
            return jsonify({
                'status': 'error',
                'message': 'Credenciales de administrador no válidas'
            }), 401

        codigo = admin_info['codigo']
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
            'permisos': permisos,
            'expires_at': expires_at,
            'session_id': session_id,
            'token': token
        })

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



@app.route('/api/admin/cambiar-contraseña', methods=['POST'])
@limiter.limit("10 per hour")
@limiter.limit("5 per minute")
@require_admin
def admin_cambiar_contraseña():
    """
    POST /api/admin/cambiar-contraseña
    Cambia la contraseña del administrador autenticado.
    Requiere permiso de escritura o configuración.
    """
    if not _admin_puede_escribir():
        return jsonify({
            'status': 'error',
            'message': 'No tienes permiso para cambiar la contraseña'
        }), 403

    data = request.get_json() or {}
    current_password = (
        data.get('contraseña_actual')
        or data.get('contrasena_actual')
        or data.get('password_actual')
        or ''
    ).strip()
    new_password = (
        data.get('contraseña_nueva')
        or data.get('contrasena_nueva')
        or data.get('password_nueva')
        or ''
    ).strip()
    confirm_password = (
        data.get('contraseña_confirmacion')
        or data.get('contrasena_confirmacion')
        or data.get('password_confirmacion')
        or ''
    ).strip()

    if confirm_password and new_password != confirm_password:
        return jsonify({
            'status': 'error',
            'message': 'La confirmación de la nueva contraseña no coincide'
        }), 400

    admin_codigo = _admin_codigo()
    result = change_admin_password(admin_codigo, current_password, new_password)
    status_code = 200 if result.get('status') == 'success' else 400
    return jsonify(result), status_code





# ================================================
# ERROR HANDLERS
# ================================================

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


@app.errorhandler(429)
def ratelimit_error(error):
    """Demasiados intentos (Flask-Limiter)."""
    return jsonify({
        'status': 'error',
        'message': 'Demasiados intentos. Inténtalo más tarde.',
    }), 429


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
