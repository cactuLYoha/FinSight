from urllib.parse import urlsplit

from flask import current_app, jsonify, request


COOKIE_LOGIN_SECONDS = 7 * 24 * 60 * 60


def configure_auth_security(app):
    """Trust only configured frontend origins, independently of CORS settings."""
    configured = app.config.get('AUTH_TRUSTED_ORIGINS') or ()
    origins = configured.split(',') if isinstance(configured, str) else configured
    allowed = set()
    for value in origins:
        origin = value.strip().rstrip('/')
        if not origin:
            continue
        parsed = urlsplit(origin)
        try:
            port = parsed.port
        except ValueError:
            raise ValueError('AUTH_TRUSTED_ORIGINS contains an invalid port.') from None
        if (
            parsed.scheme not in ('http', 'https') or not parsed.hostname
            or parsed.path or parsed.query or parsed.fragment
            or parsed.username is not None or parsed.password is not None
            or '*' in origin or (port is not None and not 1 <= port <= 65535)
        ):
            raise ValueError('AUTH_TRUSTED_ORIGINS must contain explicit HTTP(S) origins.')
        allowed.add(origin)
    app.config['AUTH_TRUSTED_ORIGINS'] = frozenset(allowed)


def check_session_origin():
    """Protect session creation/deletion even without a valid JWT (login CSRF)."""
    if request.headers.get('Origin') not in current_app.config['AUTH_TRUSTED_ORIGINS']:
        return jsonify(message='Untrusted request origin'), 403
    return None
