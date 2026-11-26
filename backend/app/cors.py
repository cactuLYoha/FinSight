from urllib.parse import urlsplit

from flask import request


def configure_cors(app):
    configured = app.config.get('CORS_ORIGINS') or ()
    origins = configured.split(',') if isinstance(configured, str) else configured
    allowed = set()
    for value in origins:
        origin = value.strip().rstrip('/')
        if not origin:
            continue
        parsed = urlsplit(origin)
        if (
            parsed.scheme not in ('http', 'https') or not parsed.netloc
            or parsed.path or parsed.query or parsed.fragment
            or parsed.username is not None or parsed.password is not None
            or '*' in origin
        ):
            raise ValueError('CORS_ORIGINS must contain explicit HTTP(S) origins.')
        allowed.add(origin)
    app.config['CORS_ORIGINS'] = frozenset(allowed)

    @app.after_request
    def cors_headers(response):
        origin = request.headers.get('Origin')
        if request.path.startswith('/api/') and origin in app.config['CORS_ORIGINS']:
            response.headers['Access-Control-Allow-Origin'] = origin
            response.vary.add('Origin')
            if request.method == 'OPTIONS':
                response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PATCH, DELETE, OPTIONS'
                response.headers['Access-Control-Allow-Headers'] = 'Authorization, Content-Type'
        return response
