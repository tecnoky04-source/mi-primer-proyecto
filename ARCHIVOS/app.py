import smtplib
from email.message import EmailMessage
def send_error_email(subject, body):
    """Envía un email de alerta en caso de error crítico."""
    EMAIL_ENABLED = os.environ.get('ERROR_EMAIL_ENABLED', 'False').lower() == 'true'
    if not EMAIL_ENABLED:
        return
    EMAIL_TO = os.environ.get('ERROR_EMAIL_TO')
    EMAIL_FROM = os.environ.get('ERROR_EMAIL_FROM')
    EMAIL_HOST = os.environ.get('ERROR_EMAIL_HOST')
    EMAIL_PORT = int(os.environ.get('ERROR_EMAIL_PORT', 587))
    EMAIL_USER = os.environ.get('ERROR_EMAIL_USER')
    EMAIL_PASS = os.environ.get('ERROR_EMAIL_PASS')
    if not all([EMAIL_TO, EMAIL_FROM, EMAIL_HOST, EMAIL_USER, EMAIL_PASS]):
        logging.error("Faltan variables de entorno para email de error.")
        return
    try:
        msg = EmailMessage()
        msg.set_content(body)
        msg['Subject'] = subject
        msg['From'] = EMAIL_FROM
        msg['To'] = EMAIL_TO
        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASS)
            server.send_message(msg)
        logging.info(f"Alerta de error enviada a {EMAIL_TO}")
    except Exception as e:
        logging.error(f"Error enviando email de alerta: {e}")
"""
DocuExpress - Sistema de Gestión de Papelerías
Aplicación Flask principal con configuración mejorada y seguridad reforzada.
"""
from flask import Flask, url_for, session, render_template, jsonify, current_app
import logging
import os
import secrets
from pathlib import Path
from markupsafe import Markup
from flask_login import LoginManager, current_user
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from datetime import datetime
from sqlalchemy import text
from dotenv import load_dotenv
try:
    from flask_caching import Cache
except ImportError:
    # type: ignore[import]
    pass  # Para Pylance: asegúrate de que el entorno es correcto

# Compresión GZIP para reducir transferencia de datos
try:
    from flask_compress import Compress
    FLASK_COMPRESS_AVAILABLE = True
except ImportError:
    FLASK_COMPRESS_AVAILABLE = False

load_dotenv()

# Importamos la clase DB y User
# Se actualiza la importación para usar el nuevo módulo de base de datos.

from ARCHIVOS.models import db, User
from ARCHIVOS.backup_manager import backup_manager

# Importa tus Blueprints
# MEJORA DE ESTRUCTURA: Se actualizan las rutas de importación tras mover los archivos a la carpeta 'routes'.
from ARCHIVOS.routes.config_routes import config_bp
from ARCHIVOS.routes.api_routes import api_bp
from ARCHIVOS.routes.auth_routes import auth_bp
from ARCHIVOS.routes.papeleria_routes import papeleria_bp
from ARCHIVOS.routes.gastos_routes import gastos_bp
from ARCHIVOS.routes.main_routes import main_bp

# ==================== CONFIGURACIÓN ====================

class Config:
    """Configuración centralizada de la aplicación."""
    
    # Configuración básica
    SECRET_KEY = os.environ.get('FLASK_SECRET_KEY') or secrets.token_hex(32)
    DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    
    # Configuración de sesión
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "False").lower() == "true"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = 3600 * 24 * 7  # 7 días
    
    # Configuración de archivos
    BASE_DIR = Path(__file__).resolve().parent
    UPLOAD_FOLDER = BASE_DIR / 'static' / 'uploads'
    RECEIPTS_FOLDER = BASE_DIR / 'static' / 'receipts'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf'}
    
    # Configuración de logging
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    LOG_FILE = os.environ.get('LOG_FILE', 'docuexpress.log')
    LOG_MAX_BYTES = int(os.environ.get('LOG_MAX_BYTES', 2 * 1024 * 1024))  # 2MB
    LOG_BACKUP_COUNT = int(os.environ.get('LOG_BACKUP_COUNT', 5))
    
    # Configuración de base de datos
    DATABASE_PATH = BASE_DIR / 'control_papelerias.db'
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{DATABASE_PATH}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Configuración de seguridad
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None  # No expira el token CSRF
    
    # Configuración de Rate Limiting
    RATELIMIT_ENABLED = os.environ.get('RATELIMIT_ENABLED', 'True').lower() == 'true'
    RATELIMIT_STORAGE_URL = os.environ.get('RATELIMIT_STORAGE_URL', 'redis://localhost:6379')
    RATELIMIT_DEFAULT = os.environ.get('RATELIMIT_DEFAULT', '1000 per day;200 per hour')
    RATELIMIT_API = os.environ.get('RATELIMIT_API', '500 per day;100 per hour')

    # Configuración de caché multicapa (OPTIMIZADO para PythonAnywhere gratis)
    CACHE_REDIS_URL = os.environ.get('CACHE_REDIS_URL', 'redis://localhost:6379/0')
    CACHE_DEFAULT_TIMEOUT = int(os.environ.get('CACHE_DEFAULT_TIMEOUT', '300'))
    CACHE_TYPE = 'SimpleCache'  # Mejor para PythonAnywhere gratis (sin Redis)
    CACHE_THRESHOLD = 500  # Máximo elementos en caché
    
    # Configuración de compresión (reduce transferencia 60-80%)
    COMPRESS_MIMETYPES = [
        'text/html', 'text/css', 'text/xml', 'text/javascript',
        'application/json', 'application/javascript', 'application/xml'
    ]
    COMPRESS_LEVEL = 6  # Balance entre compresión y CPU
    COMPRESS_MIN_SIZE = 500  # Solo comprimir si > 500 bytes
    
    @staticmethod
    def init_app(app):
        """Inicializa la configuración de la aplicación."""
        # Crear directorios necesarios
        Config.UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
        Config.RECEIPTS_FOLDER.mkdir(parents=True, exist_ok=True)

        # Configurar logging con rotación
        from logging.handlers import RotatingFileHandler
        handler = RotatingFileHandler(
            Config.LOG_FILE,
            maxBytes=Config.LOG_MAX_BYTES,
            backupCount=Config.LOG_BACKUP_COUNT
        )
        formatter = logging.Formatter(Config.LOG_FORMAT)
        handler.setFormatter(formatter)
        root_logger = logging.getLogger()
        root_logger.setLevel(getattr(logging, Config.LOG_LEVEL))
        root_logger.addHandler(handler)

        # Advertencia si no hay SECRET_KEY configurado (solo en producción)
        if not os.environ.get('FLASK_SECRET_KEY') and not app.config['DEBUG']:
            logging.warning("\n" + "="*80)
            logging.warning("⚠️  ADVERTENCIA DE SEGURIDAD")
            logging.warning("No se configuró FLASK_SECRET_KEY. Se generó una automáticamente.")
            logging.warning("Para producción, configura FLASK_SECRET_KEY en el archivo .env")
            logging.warning("Genera una clave con: python3 -c 'import secrets; print(secrets.token_hex(32))'")
            logging.warning("="*80 + "\n")
        elif os.environ.get('FLASK_SECRET_KEY'):
            logging.info("✅ SECRET_KEY cargado desde variables de entorno")


# ==================== CREACIÓN DE LA APLICACIÓN ====================

def run_db_migration(app):
    """
    Realiza migraciones de base de datos simples y automáticas al inicio.
    Es idempotente, por lo que es seguro ejecutarlo en cada arranque.
    """
    with app.app_context():
        # La migración de la columna is_active se maneja directamente en el modelo.
        # Para cambios de esquema más complejos, se recomienda usar una herramienta de migración como Alembic.
        # Por ahora, solo se asegura que la tabla se cree con la columna si no existe.
        db.create_all()


def create_app(config_class=Config):

    app = Flask(__name__)
    app.config.from_object(config_class)

    # ✅ 0. Inicializar Compresión GZIP PRIMERO (antes de cualquier ruta)
    if FLASK_COMPRESS_AVAILABLE:
        Compress(app)
        logging.info("✅ Compresión GZIP habilitada")

    # ✅ 1. Inicializar configuración PRIMERO
    config_class.init_app(app)

    # ✅ 2. Inicializar extensiones DESPUÉS
    # Disable CSRF in testing mode to simplify unit tests that POST forms.
    if not app.config.get('TESTING', False):
        CSRFProtect(app)
    db.init_app(app)
    # ✅ 3. Inicializar caché multicapa
    # Intentamos usar el backend indicado en configuración (por defecto Redis).
    # Si falla (p. ej. Redis no está disponible en desarrollo) caemos a SimpleCache.
    try:
        cache = Cache(app)
        app.cache = cache
    except Exception as e:
        logging.warning("Cache init failed, falling back to SimpleCache: %s", e)
        # Forzar tipo SimpleCache y reintentar
        app.config['CACHE_TYPE'] = 'SimpleCache'
        cache = Cache(app)
        app.cache = cache

    # Ruta de prueba para verificar la caché
    @app.route('/cache-test')
    @cache.cached(timeout=60)
    def cache_test():
        from time import time
        return jsonify({
            'cached_time': time(),
            'message': 'Si este valor no cambia en 60 segundos, la caché funciona.'
        })

    # ✅ 4. Inicializar Rate Limiter con Redis
    limiter = None
    if app.config.get('RATELIMIT_ENABLED', True):
        storage_uri = app.config.get('RATELIMIT_STORAGE_URL', 'redis://localhost:6379')
        try:
            limiter = Limiter(
                app=app,
                key_func=get_remote_address,
                default_limits=[app.config.get('RATELIMIT_DEFAULT', '1000 per day')],
                storage_uri=storage_uri,
                strategy='fixed-window'
            )
            logging.info("✅ Rate Limiting habilitado (%s)", storage_uri)
            logging.info(f"   Límites por defecto: {app.config.get('RATELIMIT_DEFAULT')}")
            app.limiter = limiter
        except Exception as e:
            logging.warning("No se pudo inicializar Rate Limiter con %s: %s. Usando almacenamiento en memoria para desarrollo.", storage_uri, e)
            try:
                # Fallback a almacenamiento en memoria para evitar 500s en desarrollo
                limiter = Limiter(
                    app=app,
                    key_func=get_remote_address,
                    default_limits=[app.config.get('RATELIMIT_DEFAULT', '1000 per day')],
                    storage_uri='memory://',
                    strategy='fixed-window'
                )
                app.limiter = limiter
            except Exception as e2:
                logging.error("Error al inicializar Rate Limiter en memoria: %s", e2)
                app.limiter = None
    else:
        logging.info("⚠️ Rate Limiting deshabilitado")
        app.limiter = None

    # ✅ 5. Inicializar Backup Manager
    backup_manager.init_app(app)

    # ✅ 5. Ejecutar migración de BD ANTES de registrar blueprints y contextos
    run_db_migration(app) # Se ejecuta para asegurar que las tablas existan al inicio.

    # Jinja
    app.jinja_env.add_extension('jinja2.ext.do')

    # Login, contextos, errores, blueprints
    setup_login_manager(app)
    register_context_processors(app)
    register_error_handlers(app)
    register_blueprints(app)

    @app.route('/health')
    def health_check():
        try:
            db.session.execute(text('SELECT 1'))
            return jsonify({
                'status': 'healthy',
                'timestamp': datetime.now().isoformat(),
                'database': 'connected'
            }), 200
        except Exception as e:
            return jsonify({
                'status': 'unhealthy',
                'error': str(e)
            }), 500

    return app



# ==================== CONFIGURACIÓN DE LOGIN MANAGER ====================

def setup_login_manager(app):
    """Configura Flask-Login."""
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = "Por favor, inicia sesión para acceder a esta página."
    login_manager.login_message_category = "danger"
    
    @login_manager.user_loader
    def load_user(user_id):
        """Carga un usuario desde la base de datos."""
        return db.session.get(User, int(user_id))


# ==================== CONTEXT PROCESSORS ====================

def register_context_processors(app):
    """Registra context processors para templates."""
    
    @app.context_processor
    def utility_processor():
        def render_field(field, **kwargs):
            """Renderiza un campo de WTForms con clases de Bootstrap y errores."""
            field_id = kwargs.pop('id', field.id)
            field_class = kwargs.pop('class', '')
            
            # Añadir 'is-invalid' si hay errores
            if field.errors:
                field_class += ' is-invalid'
            
            # Renderizar el campo
            rendered_field = field(id=field_id, class_=field_class, **kwargs)
            
            # Construir el HTML del error
            error_html = ''
            if field.errors:
                error_html = f'<div class="invalid-feedback">{" ".join(field.errors)}</div>'
            
            return Markup(f"{rendered_field}{error_html}")
        return dict(render_field=render_field)
    @app.context_processor
    def inject_current_year():
        """Inyecta el año actual en todos los templates."""
        return {'current_year': datetime.now().year}
    
    @app.context_processor
    def inject_logo():
        """Inyecta la ruta del logo del usuario actual."""
        # MEJORA: Usar la sesión para evitar comprobaciones de archivo en cada request.
        # Se asume que 'session["has_logo"]' y 'session["user_id"]' se establecen
        # durante el login o al subir/eliminar el logo.
        logo_path = None
        if session.get('has_logo') and session.get('user_id'):
            logo_filename = f"logo_{session['user_id']}.png"
            logo_path = url_for('static', filename=f'uploads/{logo_filename}')
        return {'logo_path': logo_path}
    
    @app.context_processor
    def inject_impersonation_status():
        """Inyecta el estado de suplantación de identidad en los templates."""
        if 'original_user_id' in session:
            from ARCHIVOS.models import User # Importación local para evitar dependencia circular
            viewing_user_id = session.get('viewing_user_id')
            user = db.session.get(User, viewing_user_id)
            if user:
                return {
                    'is_impersonating': True,
                    'impersonated_user_name': user.username
                }
        return {'is_impersonating': False}


# ==================== ERROR HANDLERS ====================

def register_error_handlers(app):
    """Registra manejadores de errores personalizados."""
    
    @app.errorhandler(404)
    def not_found_error(error):
        """Maneja errores 404 - Página no encontrada."""
        logging.warning(f"404 error: {error}")
        return render_template('errors/404.html'), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        logging.error(f"500 error: {error}")
        # Rollback de la base de datos si hay un error para evitar datos corruptos.
        try:
            db.session.rollback()
        except Exception as e:
            logging.error(f"Error during DB rollback on 500 error: {e}")
        # Enviar alerta por email
        send_error_email(
            subject="DocuExpress - Error 500",
            body=f"Error interno del servidor: {error}"
        )
        return render_template('errors/500.html'), 500
    
    @app.errorhandler(403)
    def forbidden_error(error):
        """Maneja errores 403 - Acceso prohibido."""
        logging.warning(f"403 error: {error}")
        return render_template('errors/403.html'), 403
    
    @app.errorhandler(413)
    def request_entity_too_large(error):
        """Maneja errores 413 - Archivo demasiado grande."""
        logging.warning(f"413 error: {error}")
        return jsonify({
            'error': 'El archivo es demasiado grande. Tamaño máximo: 16MB'
        }), 413


# ==================== REGISTRO DE BLUEPRINTS ====================

def register_blueprints(app):
    blueprints = [
        (auth_bp, 'Autenticación'),
        (papeleria_bp, 'Papelerías'),
        (gastos_bp, 'Gastos'),
        (main_bp, 'Principal'),
        (config_bp, 'Configuración'),
        (api_bp, 'API'),
    ]
    
    for blueprint, name in blueprints:
        app.register_blueprint(blueprint)
        logging.info(f"✓ Blueprint registrado: {name}")


# Para despliegue en PythonAnywhere, no se debe usar app.run().
# El objeto 'app' debe estar disponible para WSGI:
# from ARCHIVOS.app import app
