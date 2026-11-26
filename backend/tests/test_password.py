from datetime import timedelta

import pytest
from flask_jwt_extended import create_access_token

from app.extensions import db
from app.models.user import User
from app.models.verification import PasswordResetBudget, VerificationChallenge, TrustedDevice, utcnow
from tests.auth_support import HEADERS, finish_verification

EMAIL = 'password@example.com'
OLD = 'OldPassword123'
NEW = 'NewPassword456'


@pytest.fixture(autouse=True)
def origin(app):
    app.config['AUTH_TRUSTED_ORIGINS'] = frozenset({HEADERS['Origin']})


def register(client):
    assert client.post('/api/auth/register', json={'email': EMAIL, 'password': OLD}).status_code == 201
    assert finish_verification(client, trust=True).status_code == 200


def csrf(client):
    return {**HEADERS, 'X-CSRF-TOKEN': client.get_cookie('csrf_access_token').value}


def request_reset(client, email=EMAIL):
    return client.post('/api/auth/password/reset/request', headers=HEADERS, json={'email': email})


def test_change_revokes_sessions_devices_and_pending_codes(client, app):
    register(client)
    user = db.session.scalar(db.select(User))
    token = create_access_token(identity=str(user.id), additional_claims={'auth_complete': True})
    wrong = client.post('/api/auth/password/change', headers=csrf(client), json={'current_password': 'wrong', 'new_password': NEW})
    assert wrong.status_code == 400
    response = client.post('/api/auth/password/change', headers=csrf(client), json={'current_password': OLD, 'new_password': NEW})
    assert response.status_code == 204
    assert user.check_password(NEW)
    assert user.auth_version == 1
    assert client.get('/api/auth/me', headers={'Authorization': 'Bearer ' + token}).status_code == 401
    assert all(d.revoked_at for d in db.session.scalars(db.select(TrustedDevice)))
    assert all(c.consumed_at for c in db.session.scalars(db.select(VerificationChallenge)))


def test_reset_success_and_no_login_or_reuse(client, app):
    register(client)
    assert request_reset(client).status_code == 202
    code = app.extensions['mail_sender'].messages[-1][1]
    payload = {'code': code, 'new_password': NEW}
    assert client.post('/api/auth/password/reset/confirm', headers=HEADERS, json=payload).status_code == 204
    assert db.session.scalar(db.select(User)).check_password(NEW)
    assert client.get('/api/auth/me').status_code == 401
    assert client.post('/api/auth/password/reset/confirm', headers=HEADERS, json=payload).status_code == 410


def test_unknown_email_and_mail_failure_are_neutral(client, app):
    register(client)
    app.extensions['mail_sender'].fail = True
    known = request_reset(client)
    unknown = request_reset(client, 'unknown@example.com')
    assert known.status_code == unknown.status_code == 202
    assert known.json == unknown.json
    assert db.session.query(PasswordResetBudget).count() == 2


def test_reset_limits_and_wrong_codes(client, app):
    register(client)
    request_reset(client)
    initial = len(app.extensions['mail_sender'].messages)
    for _ in range(7):
        assert client.post('/api/auth/password/reset/resend', headers=HEADERS).status_code == 202
    assert len(app.extensions['mail_sender'].messages) == initial
    good = app.extensions['mail_sender'].messages[-1][1]
    wrong = '000000' if good != '000000' else '111111'
    for _ in range(5):
        assert client.post('/api/auth/password/reset/confirm', headers=HEADERS, json={'code': wrong, 'new_password': NEW}).status_code == 400
    assert client.post('/api/auth/password/reset/confirm', headers=HEADERS, json={'code': good, 'new_password': NEW}).status_code == 400
    assert db.session.scalar(db.select(User)).check_password(OLD)


def test_reset_context_cannot_confirm_login(client, app):
    register(client)
    request_reset(client)
    code = app.extensions['mail_sender'].messages[-1][1]
    from app.routes.password import serializer
    signed = client.get_cookie('finsight_password_reset', path='/api/auth/').value
    raw = serializer().loads(signed)['token']
    client.set_cookie('finsight_verification', raw, path='/api/auth/')
    assert client.post('/api/auth/verification/confirm', headers=HEADERS, json={'code': code}).status_code == 404


def test_expiry_validation_and_origin(client, app):
    register(client)
    request_reset(client)
    challenge = db.session.scalar(db.select(VerificationChallenge).where(VerificationChallenge.purpose == 'password_reset'))
    challenge.expires_at = utcnow() - timedelta(seconds=1)
    db.session.commit()
    code = app.extensions['mail_sender'].messages[-1][1]
    assert client.post('/api/auth/password/reset/confirm', headers=HEADERS, json={'code': code, 'new_password': NEW}).status_code == 400
    assert client.post('/api/auth/password/reset/request', json={'email': EMAIL}).status_code == 403
    assert client.post('/api/auth/password/reset/confirm', headers=HEADERS, json={'code': code, 'new_password': 'short'}).status_code == 400
