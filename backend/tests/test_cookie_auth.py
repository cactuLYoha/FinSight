from datetime import datetime, timedelta, timezone

import pytest
from flask_jwt_extended import create_access_token, decode_token

from app import create_app
from app.auth_security import COOKIE_LOGIN_SECONDS
from app.extensions import db
from app.models.user import User
from tests.auth_support import finish_verification


ORIGIN = 'http://localhost:4200'
HEADERS = {'Origin': ORIGIN}
CREDENTIALS = {'email': 'cookie-user@example.com', 'password': 'StrongPassword123'}


@pytest.fixture(autouse=True)
def trusted_origin(app):
    app.config['AUTH_TRUSTED_ORIGINS'] = frozenset({ORIGIN})


def sign_in(client):
    registered = client.post('/api/auth/register', json=CREDENTIALS)
    assert registered.status_code == 201
    response = client.post('/api/auth/session', json=CREDENTIALS, headers=HEADERS)
    assert response.status_code == 202
    response = finish_verification(client)
    assert response.status_code == 200
    return response.get_json()['user'], response


def goal_body():
    return {
        'name': 'Cookie goal', 'target_amount': '100.00', 'currency': 'UAH',
        'deadline': (datetime.now(timezone.utc).date() + timedelta(days=90)).isoformat(),
    }


def test_cookie_login_attributes_lifetime_and_identity(client):
    user, response = sign_in(client)
    assert response.get_json() == {'user': user}
    assert response.headers['Cache-Control'] == 'no-store'
    access = client.get_cookie('access_token_cookie', path='/api/')
    csrf = client.get_cookie('csrf_access_token')
    assert access.http_only is True
    assert access.same_site == csrf.same_site == 'Lax'
    assert access.secure is False
    assert access.path == '/api/'
    assert csrf.path == '/'
    assert csrf.http_only is False
    assert access.max_age == csrf.max_age == COOKIE_LOGIN_SECONDS == 604800
    assert access.expires is not None
    token = decode_token(access.value)
    assert token['exp'] - token['iat'] == COOKIE_LOGIN_SECONDS
    assert token['csrf'] == csrf.value
    me = client.get('/api/auth/me')
    assert me.status_code == 200
    assert me.get_json() == {'user': user}
    assert me.headers['Cache-Control'] == 'no-store'
    assert client.get('/api/analytics/forecast?currency=UAH').status_code == 200


@pytest.mark.parametrize('credentials', [
    {'email': CREDENTIALS['email'], 'password': 'incorrect'},
    {'email': 'unknown@example.com', 'password': CREDENTIALS['password']},
])
def test_cookie_login_wrong_credentials_do_not_set_cookies(client, credentials):
    client.post('/api/auth/register', json=CREDENTIALS)
    response = client.post('/api/auth/session', json=credentials, headers=HEADERS)
    assert response.status_code == 401
    assert response.get_json() == {'message': 'Invalid email or password'}
    assert not response.headers.getlist('Set-Cookie')


@pytest.mark.parametrize('payload', [{}, {'email': 'bad', 'password': 'pass'}, {'email': 'valid@example.com'}])
def test_cookie_login_validates_credentials(client, payload):
    response = client.post('/api/auth/session', json=payload, headers=HEADERS)
    assert response.status_code == 400
    assert not response.headers.getlist('Set-Cookie')


@pytest.mark.parametrize('method', ['post', 'delete'])
@pytest.mark.parametrize('origin', [None, 'null', 'https://evil.example', 'http://localhost:4201', 'http://localhost:4200.evil.example'])
def test_session_changes_reject_untrusted_origins(client, method, origin):
    sign_in(client)
    headers = {} if origin is None else {'Origin': origin}
    response = getattr(client, method)('/api/auth/session', json=CREDENTIALS, headers=headers)
    assert response.status_code == 403
    assert not response.headers.getlist('Set-Cookie')
    assert client.get('/api/auth/me').status_code == 200


def test_cookie_writes_require_matching_csrf(client):
    sign_in(client)
    assert client.post('/api/savings/goals', json=goal_body()).status_code == 401
    assert client.post('/api/savings/goals', json=goal_body(), headers={'X-CSRF-TOKEN': 'wrong'}).status_code == 401
    csrf = client.get_cookie('csrf_access_token').value
    response = client.post('/api/savings/goals', json=goal_body(), headers={'X-CSRF-TOKEN': csrf})
    assert response.status_code == 201


def test_bearer_contract_precedence_and_writes_without_csrf(client):
    sign_in(client)
    credentials = {**CREDENTIALS, 'email': 'bearer-user@example.com'}
    user = client.post('/api/auth/register', json=credentials).get_json()['user']
    response = client.post('/api/auth/login', json=credentials)
    assert response.status_code == 202
    response = finish_verification(client)
    assert set(response.get_json()) == {'access_token'}
    assert not any(value.startswith('access_token_cookie=') for value in response.headers.getlist('Set-Cookie'))
    headers = {'Authorization': 'Bearer ' + response.get_json()['access_token']}
    actual = client.get('/api/auth/me', headers=headers).get_json()['user']
    assert actual['id'] == user['id']
    assert actual['email'] == user['email']
    assert actual['is_email_verified'] is True
    assert client.post('/api/savings/goals', json=goal_body(), headers=headers).status_code == 201
    assert client.get('/api/auth/me', headers={'Authorization': 'Bearer invalid'}).status_code == 422


@pytest.mark.parametrize('bad_cookie', ['expired', 'corrupt', 'absent'])
def test_logout_also_clears_invalid_or_missing_tokens(client, bad_cookie):
    user, _ = sign_in(client)
    if bad_cookie == 'expired':
        token = create_access_token(identity=str(user['id']), expires_delta=timedelta(seconds=-60))
        client.set_cookie('access_token_cookie', token, path='/api/')
        assert client.get('/api/auth/me').status_code == 401
    elif bad_cookie == 'corrupt':
        client.set_cookie('access_token_cookie', 'corrupt', path='/api/')
        assert client.get('/api/auth/me').status_code == 422
    else:
        client.delete_cookie('access_token_cookie', path='/api/')
    response = client.delete('/api/auth/session', headers=HEADERS)
    assert response.status_code == 204
    assert response.headers['Cache-Control'] == 'no-store'
    assert client.get_cookie('access_token_cookie', path='/api/') is None
    assert client.get_cookie('csrf_access_token') is None
    assert client.get('/api/auth/me').status_code == 401
    assert client.delete('/api/auth/session', headers=HEADERS).status_code == 204


def test_cookie_cannot_authenticate_a_deleted_user(client):
    user, _ = sign_in(client)
    db.session.delete(db.session.get(User, user['id']))
    db.session.commit()
    assert client.get('/api/auth/me').status_code == 401
    assert client.get('/api/analytics/forecast').status_code == 401


def test_https_configuration_marks_both_cookies_secure(client, app):
    app.config['JWT_COOKIE_SECURE'] = True
    sign_in(client)
    assert client.get_cookie('access_token_cookie', path='/api/').secure is True
    assert client.get_cookie('csrf_access_token').secure is True


@pytest.mark.parametrize('origin', ['*', 'https://*.example.com', 'https://example.com/path', 'https://user:pass@example.com', 'http://localhost:99999'])
def test_invalid_trusted_origins_fail_at_startup(origin):
    with pytest.raises(ValueError):
        create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://', 'AUTH_TRUSTED_ORIGINS': origin})
