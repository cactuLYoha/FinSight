from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from threading import Barrier

import pytest
import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from flask_jwt_extended import create_access_token
from flask_migrate import upgrade, downgrade
from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models.user import User
from app.models.verification import VerificationChallenge, VerificationSend, TrustedDevice
from app.services import verification_service as service
from app.services.gmail_service import GmailSender, MailDeliveryError
from tests.auth_support import HEADERS, finish_verification

CREDS = {'email': 'otp@example.com', 'password': 'StrongPassword123'}


def register(client):
    response = client.post('/api/auth/register', json=CREDS)
    assert response.status_code == 201
    return response


@pytest.fixture
def clock(monkeypatch):
    now = [service.utcnow()]
    monkeypatch.setattr(service, 'utcnow', lambda: now[0])
    return now


def test_registration_is_pending_and_hides_code_and_context_secret(client, app, monkeypatch):
    monkeypatch.setattr(service.secrets, 'randbelow', lambda _: 0)
    response = register(client)
    assert response.get_json()['verification_required'] is True
    assert response.get_json()['user']['is_email_verified'] is False
    assert client.get_cookie('access_token_cookie', path='/api/') is None
    pending = client.get_cookie(service.PENDING_COOKIE, path=service.AUTH_COOKIE_PATH)
    assert pending.http_only and pending.same_site == 'Lax' and pending.max_age == 600
    challenge = db.session.get(VerificationChallenge, service.digest(pending.value))
    assert challenge is not None and challenge.code_hash != '000000'
    assert challenge.token_hash != pending.value
    assert app.extensions['mail_sender'].messages[-1][1] == '000000'
    assert client.get('/api/auth/me').status_code == 401
    assert '000000' not in response.get_data(as_text=True)
    confirmed = finish_verification(client)
    assert confirmed.status_code == 200
    assert confirmed.get_json()['user']['is_email_verified'] is True
    assert confirmed.get_json()['user']['email_verified_at']
    client.set_cookie(service.PENDING_COOKIE, pending.value, path=service.AUTH_COOKIE_PATH)
    assert client.post('/api/auth/verification/confirm', headers=HEADERS, json={'code': '000000'}).status_code == 410


def test_five_wrong_codes_close_challenge_even_after_resend(client, app, clock, monkeypatch):
    monkeypatch.setattr(service.secrets, 'randbelow', lambda _: 123456)
    register(client)
    for _ in range(2):
        assert client.post('/api/auth/verification/confirm', headers=HEADERS, json={'code': '654321'}).status_code == 400
    clock[0] += timedelta(seconds=61)
    assert client.post('/api/auth/verification/resend', headers=HEADERS).status_code == 200
    for _ in range(3):
        assert client.post('/api/auth/verification/confirm', headers=HEADERS, json={'code': '654321'}).status_code == 400
    assert finish_verification(client).status_code == 410
    assert client.post('/api/auth/verification/resend', headers=HEADERS).status_code == 410
    assert db.session.scalar(sa.select(User)).is_email_verified is False


def test_expired_context_cannot_confirm_or_resend(client, clock):
    register(client)
    clock[0] += timedelta(minutes=11)
    assert client.get('/api/auth/verification').status_code == 410
    assert finish_verification(client).status_code == 410
    assert client.post('/api/auth/verification/resend', headers=HEADERS).status_code == 410


def test_resend_replaces_old_code_and_enforces_cooldown(client, clock, monkeypatch):
    codes = iter((111111, 222222))
    monkeypatch.setattr(service.secrets, 'randbelow', lambda _: next(codes))
    register(client)
    response = client.post('/api/auth/verification/resend', headers=HEADERS)
    assert response.status_code == 429 and int(response.headers['Retry-After']) > 0
    clock[0] += timedelta(seconds=61)
    assert client.post('/api/auth/verification/resend', headers=HEADERS).status_code == 200
    assert client.post('/api/auth/verification/confirm', headers=HEADERS, json={'code': '111111'}).status_code == 400
    assert finish_verification(client).status_code == 200


def test_sending_budget_covers_new_logins_and_survives_context_replacement(client):
    register(client)
    for _ in range(4):
        assert client.post('/api/auth/session', json=CREDS, headers=HEADERS).status_code == 202
    assert client.post('/api/auth/session', json=CREDS, headers=HEADERS).status_code == 429
    assert db.session.scalar(sa.select(sa.func.count()).select_from(VerificationSend)) == 5
    assert client.get_cookie('access_token_cookie', path='/api/') is None


def test_failed_initial_delivery_keeps_user_pending_and_allows_later_retry(client, app, clock):
    mail = app.extensions['mail_sender']
    mail.fail = True
    response = client.post('/api/auth/register', json=CREDS)
    assert response.status_code == 503
    assert response.get_json()['account_created'] is True
    assert response.get_json()['delivery_ready'] is False
    assert db.session.scalar(sa.select(User)).is_email_verified is False
    assert client.get_cookie('access_token_cookie', path='/api/') is None
    mail.fail = False
    clock[0] += timedelta(seconds=61)
    assert client.post('/api/auth/verification/resend', headers=HEADERS).status_code == 200
    assert finish_verification(client).status_code == 200


def test_failed_resend_preserves_previous_unexpired_code(client, app, clock):
    register(client)
    app.extensions['mail_sender'].fail = True
    clock[0] += timedelta(seconds=61)
    assert client.post('/api/auth/verification/resend', headers=HEADERS).status_code == 503
    assert finish_verification(client).status_code == 200


def test_trusted_browser_requires_password_does_not_extend_expiry_and_logout_revokes(client, app):
    register(client)
    assert finish_verification(client, trust=True).status_code == 200
    trusted = client.get_cookie(service.TRUST_COOKIE, path=service.AUTH_COOKIE_PATH)
    assert trusted.http_only and trusted.max_age == 90 * 86400
    record = db.session.get(TrustedDevice, service.digest(trusted.value))
    expiry = record.expires_at
    sent = len(app.extensions['mail_sender'].messages)
    client.delete_cookie('access_token_cookie', path='/api/')
    assert client.post('/api/auth/session', headers=HEADERS, json={**CREDS, 'password': 'wrong'}).status_code == 401
    assert client.post('/api/auth/session', headers=HEADERS, json=CREDS).status_code == 200
    assert len(app.extensions['mail_sender'].messages) == sent
    db.session.refresh(record)
    assert record.expires_at == expiry
    assert client.delete('/api/auth/session', headers=HEADERS).status_code == 204
    assert client.get_cookie(service.TRUST_COOKIE, path=service.AUTH_COOKIE_PATH) is None
    db.session.refresh(record)
    assert record.revoked_at is not None
    client.set_cookie(service.TRUST_COOKIE, trusted.value, path=service.AUTH_COOKIE_PATH)
    assert client.post('/api/auth/session', headers=HEADERS, json=CREDS).status_code == 202


@pytest.mark.parametrize('case', ['expired', 'foreign', 'unverified', 'tampered'])
def test_invalid_trust_never_bypasses_code(client, app, case):
    register(client)
    finish_verification(client, trust=True)
    trusted = client.get_cookie(service.TRUST_COOKIE, path=service.AUTH_COOKIE_PATH)
    device = db.session.get(TrustedDevice, service.digest(trusted.value))
    if case == 'expired':
        device.expires_at = service.utcnow() - timedelta(seconds=1)
    elif case == 'foreign':
        other = User(email='other-otp@example.com', password_hash='not-used')
        db.session.add(other)
        db.session.flush()
        device.user_id = other.id
    elif case == 'unverified':
        db.session.get(User, device.user_id).is_email_verified = False
    else:
        client.set_cookie(service.TRUST_COOKIE, 'tampered', path=service.AUTH_COOKIE_PATH)
    db.session.commit()
    client.delete_cookie('access_token_cookie', path='/api/')
    assert client.post('/api/auth/session', headers=HEADERS, json=CREDS).status_code == 202


@pytest.mark.parametrize('verified,complete', [(False, False), (False, True), (True, False)])
def test_old_or_incomplete_tokens_cannot_access_private_apis(client, verified, complete):
    user = User(email='old@example.com', password_hash='unused', is_email_verified=verified)
    db.session.add(user); db.session.commit()
    token = create_access_token(identity=str(user.id), additional_claims={'auth_complete': complete})
    headers = {'Authorization': 'Bearer ' + token}
    assert client.get('/api/auth/me', headers=headers).status_code == 403
    assert client.get('/api/analytics/forecast', headers=headers).status_code == 403
    assert client.get('/api/savings/goals', headers=headers).status_code == 403


@pytest.mark.parametrize('path', ['confirm', 'resend'])
def test_verification_operations_require_trusted_origin(client, path):
    register(client)
    response = client.post('/api/auth/verification/' + path, json={'code': '000000'}, headers={'Origin': 'https://evil.example'})
    assert response.status_code == 403


@pytest.mark.postgresql
def test_concurrent_consumption_can_issue_only_one_session(app, client):
    register(client)
    token = client.get_cookie(service.PENDING_COOKIE, path=service.AUTH_COOKIE_PATH).value
    code = app.extensions['mail_sender'].messages[-1][1]
    db.session.remove()
    barrier = Barrier(2)
    def verify(_):
        browser = app.test_client()
        browser.set_cookie(service.PENDING_COOKIE, token, path=service.AUTH_COOKIE_PATH)
        barrier.wait(timeout=10)
        return browser.post('/api/auth/verification/confirm', headers=HEADERS, json={'code': code, 'trust_device': True}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(verify, range(2))) == [200, 410]
    assert db.session.scalar(sa.select(sa.func.count()).select_from(TrustedDevice)) == 1


def test_gmail_formats_mime_and_sanitizes_failures(monkeypatch):
    import base64
    from email import message_from_bytes
    sent = {}
    class Service:
        def users(self): return self
        def messages(self): return self
        def send(self, **kwargs): sent.update(kwargs); return self
        def execute(self, **kwargs): return {'id': 'fake'}
        def close(self): pass
    sender = GmailSender('private-token-path', 'sender@example.com')
    monkeypatch.setattr(sender, '_service', lambda: Service())
    sender.send_verification('recipient@example.com', '012345')
    message = message_from_bytes(base64.urlsafe_b64decode(sent['body']['raw']))
    assert message['To'] == 'recipient@example.com'
    assert sent['userId'] == 'me'
    def unavailable(): raise RuntimeError('private Google credential')
    monkeypatch.setattr(sender, '_service', unavailable)
    with pytest.raises(MailDeliveryError, match='Unable to deliver') as error:
        sender.send_verification('recipient@example.com', '012345')
    assert 'private' not in str(error.value)


def test_verification_migration_backfill_rollback_and_model_parity(migration_app):
    migrations = str(Path(__file__).resolve().parents[1] / 'migrations')
    upgrade(directory=migrations, revision='c83d51e9f204')
    users = sa.Table('user', sa.MetaData(), autoload_with=db.engine)
    accounts = sa.Table('account', sa.MetaData(), autoload_with=db.engine)
    password_hash = generate_password_hash('StrongPassword123')
    with db.engine.begin() as connection:
        connection.execute(users.insert(), {'id': 1, 'email': 'legacy@example.com', 'password_hash': password_hash, 'created_at': service.utcnow()})
        connection.execute(accounts.insert(), {
            'id': 1, 'user_id': 1, 'name': 'Preserved', 'account_type': 'bank',
            'currency': 'UAH', 'balance': Decimal('42.50'),
            'created_at': service.utcnow(), 'created_by': service.utcnow(),
        })
    upgrade(directory=migrations)
    user = db.session.get(User, 1)
    assert user.password_hash == password_hash and user.is_email_verified is False
    with db.engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), db.metadata) == []
    db.session.remove()
    downgrade(directory=migrations, revision='c83d51e9f204')
    assert 'is_email_verified' not in {col['name'] for col in sa.inspect(db.engine).get_columns('user')}
    with db.engine.connect() as connection:
        assert connection.scalar(sa.select(accounts.c.balance)) == Decimal('42.50')
    upgrade(directory=migrations)
    assert db.session.get(User, 1).password_hash == password_hash
