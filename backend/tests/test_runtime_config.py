from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
import pytest

from app import create_app
from app.config import database_uri
from app.extensions import db
from docker_env import write_env_file


def test_database_url_preserves_existing_local_configuration():
    assert database_uri({'DATABASE_URL': 'sqlite://', 'DB_HOST': 'db'}) == 'sqlite://'
    assert database_uri({}) is None


def test_container_database_url_roundtrips_special_password_characters():
    password = 'p@ss:/#% with spaces'
    uri = database_uri({
        'DB_HOST': 'db', 'DB_NAME': 'finsight', 'DB_USER': 'finsight',
        'DB_PASSWORD': password, 'DB_PORT': '5432',
    })
    rebuilt = make_url(uri.render_as_string(hide_password=False))
    assert rebuilt.password == password
    assert rebuilt.host == 'db'
    assert rebuilt.database == 'finsight'
    assert rebuilt.port == 5432


@pytest.mark.parametrize('overrides', [
    {'DB_PASSWORD': ''}, {'DB_USER': ''}, {'DB_NAME': ''},
    {'DB_PORT': '0'}, {'DB_PORT': '65536'}, {'DB_PORT': 'not-a-port'},
])
def test_invalid_container_database_configuration_fails_early(overrides):
    values = {'DB_HOST': 'db', 'DB_NAME': 'finsight', 'DB_USER': 'finsight', 'DB_PASSWORD': 'test'}
    values.update(overrides)
    with pytest.raises(ValueError):
        database_uri(values)


def test_health_reports_readiness_and_hides_connection_errors(client, app, monkeypatch):
    assert client.get('/api/health').get_json() == {'status': 'ok'}
    def unavailable(*args, **kwargs):
        raise OperationalError('private statement', {}, RuntimeError('private database details'))
    with monkeypatch.context() as patch:
        patch.setattr(db.engine, 'connect', unavailable)
        response = client.get('/api/health')
    assert response.status_code == 503
    assert response.get_json() == {'status': 'unavailable'}
    assert b'private' not in response.data


def test_cors_preflight_requires_explicit_origin_and_keeps_jwt(client, app):
    app.config['CORS_ORIGINS'] = frozenset({'http://localhost:5173'})
    headers = {
        'Origin': 'http://localhost:5173', 'Access-Control-Request-Method': 'GET',
        'Access-Control-Request-Headers': 'Authorization, Content-Type',
    }
    response = client.options('/api/analytics/forecast?currency=UAH', headers=headers)
    assert response.status_code == 200
    assert response.headers['Access-Control-Allow-Origin'] == 'http://localhost:5173'
    assert 'Authorization' in response.headers['Access-Control-Allow-Headers']
    assert 'Origin' in response.vary
    assert 'Access-Control-Allow-Credentials' not in response.headers
    denied = client.options('/api/analytics/forecast', headers={**headers, 'Origin': 'https://untrusted.example'})
    assert 'Access-Control-Allow-Origin' not in denied.headers
    protected = client.get('/api/analytics/forecast?currency=UAH', headers={'Origin': headers['Origin']})
    assert protected.status_code == 401
    assert protected.headers['Access-Control-Allow-Origin'] == headers['Origin']
    app.config['CORS_ORIGINS'] = frozenset()
    assert 'Access-Control-Allow-Origin' not in client.get('/api/health', headers=headers).headers


@pytest.mark.parametrize('origin', ['*', 'https://*.example.com', 'file://local', 'https://example.com/path', 'https://user:password@example.com'])
def test_invalid_cors_origins_are_rejected(origin):
    with pytest.raises(ValueError):
        create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://', 'CORS_ORIGINS': origin})


def test_docker_env_generation_does_not_overwrite_credentials(tmp_path):
    path = tmp_path / '.env.docker'
    assert write_env_file(path) is True
    original = path.read_text(encoding='utf-8')
    values = dict(line.split('=', 1) for line in original.splitlines())
    for key in ('POSTGRES_PASSWORD', 'SECRET_KEY', 'JWT_SECRET_KEY'):
        assert len(values[key]) == 64
        assert int(values[key], 16) >= 0
    assert len({values[key] for key in ('POSTGRES_PASSWORD', 'SECRET_KEY', 'JWT_SECRET_KEY')}) == 3
    assert write_env_file(path) is False
    assert path.read_text(encoding='utf-8') == original
