import os

from dotenv import load_dotenv
from sqlalchemy.engine import URL


load_dotenv()


def env_bool(name, default=False):
    value = os.getenv(name, str(default)).strip().lower()
    if value not in ('true', 'false', '1', '0'):
        raise ValueError(f'{name} must be true or false.')
    return value in ('true', '1')


def database_uri(environ=None):
    """Keep local DATABASE_URL support and safely assemble container credentials."""
    environ = os.environ if environ is None else environ
    if environ.get('DATABASE_URL'):
        return environ['DATABASE_URL']
    if not environ.get('DB_HOST'):
        return None
    required = ('DB_NAME', 'DB_USER', 'DB_PASSWORD')
    if any(not environ.get(key) for key in required):
        raise ValueError('DB_NAME, DB_USER, and DB_PASSWORD are required with DB_HOST.')
    port = int(environ.get('DB_PORT', '5432'))
    if not 1 <= port <= 65535:
        raise ValueError('DB_PORT must be between 1 and 65535.')
    return URL.create(
        'postgresql+psycopg2', username=environ['DB_USER'],
        password=environ['DB_PASSWORD'], host=environ['DB_HOST'],
        port=port, database=environ['DB_NAME'],
    )


class Config:
    STATEMENT_MODEL = os.getenv('BSP_HYBRID_MODEL', 'ollama/qwen2.5:3b')
    STATEMENT_API_BASE = os.getenv('BSP_HYBRID_API_BASE', 'http://localhost:11434')
    SECRET_KEY = os.getenv('SECRET_KEY')
    SQLALCHEMY_DATABASE_URI = database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {'pool_pre_ping': True}
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY')
    JWT_TOKEN_LOCATION = ['headers', 'cookies']
    JWT_ACCESS_COOKIE_PATH = '/api/'
    JWT_ACCESS_CSRF_COOKIE_PATH = '/'
    JWT_COOKIE_SAMESITE = 'Lax'
    JWT_COOKIE_SECURE = env_bool('JWT_COOKIE_SECURE')
    JWT_COOKIE_CSRF_PROTECT = True
    JWT_SESSION_COOKIE = False
    AUTH_TRUSTED_ORIGINS = os.getenv(
        'AUTH_TRUSTED_ORIGINS',
        f"http://localhost:{os.getenv('FRONTEND_PORT', '4200')},"
        f"http://127.0.0.1:{os.getenv('FRONTEND_PORT', '4200')}",
    )
    CORS_ORIGINS = os.getenv('CORS_ORIGINS', '')
    GMAIL_TOKEN_FILE = os.getenv('GMAIL_TOKEN_FILE', '')
    GMAIL_SENDER = os.getenv('GMAIL_SENDER', '')
