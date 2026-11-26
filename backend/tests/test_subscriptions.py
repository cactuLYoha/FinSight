import pytest
from flask_jwt_extended import create_access_token

from app.extensions import db
from app.models.user import User

ORIGIN = {'Origin': 'http://localhost:4200'}
BODY = {'name': ' Music ', 'amount': '199.99', 'currency': 'uah', 'billing_day': 31}


@pytest.fixture
def headers(app):
    app.config['AUTH_TRUSTED_ORIGINS'] = frozenset({ORIGIN['Origin']})
    user = User(email='subscriptions@example.com', is_email_verified=True)
    user.set_password('password123')
    db.session.add(user)
    db.session.commit()
    token = create_access_token(identity=str(user.id), additional_claims={'auth_complete': True})
    return {**ORIGIN, 'Authorization': 'Bearer ' + token}


def test_subscription_create_list_filter_delete(client, headers):
    response = client.post('/api/subscriptions', headers=headers, json=BODY)
    assert response.status_code == 201
    row = response.json['subscription']
    assert row == dict(id=row['id'], name='Music', amount='199.99', currency='UAH', billing_day=31)
    assert client.get('/api/subscriptions?currency=UAH', headers=headers).json['subscriptions'] == [row]
    assert client.get('/api/subscriptions?currency=USD', headers=headers).json['subscriptions'] == []
    assert client.delete(f"/api/subscriptions/{row['id']}", headers=headers).status_code == 204
    assert client.get('/api/subscriptions', headers=headers).json['subscriptions'] == []


@pytest.mark.parametrize('changes', [
    {'amount': '0'}, {'amount': '-1'}, {'amount': 'NaN'}, {'amount': '1.001'},
    {'billing_day': 0}, {'billing_day': 32}, {'billing_day': 1.5},
    {'name': '  '}, {'currency': '123'}, {'user_id': 999},
])
def test_subscription_validation(client, headers, changes):
    assert client.post('/api/subscriptions', headers=headers, json={**BODY, **changes}).status_code == 400


def test_subscription_ownership_and_authentication(client, headers):
    row = client.post('/api/subscriptions', headers=headers, json=BODY).json['subscription']
    other = User(email='other-subscriptions@example.com', is_email_verified=True)
    other.set_password('password123')
    db.session.add(other)
    db.session.commit()
    token = create_access_token(identity=str(other.id), additional_claims={'auth_complete': True})
    other_headers = {**ORIGIN, 'Authorization': 'Bearer ' + token}
    assert client.get('/api/subscriptions', headers=other_headers).json['subscriptions'] == []
    assert client.delete(f"/api/subscriptions/{row['id']}", headers=other_headers).status_code == 404
    assert client.get('/api/subscriptions').status_code == 401
    assert client.post('/api/subscriptions', headers={**headers, 'Origin': 'https://untrusted.example'}, json=BODY).status_code == 403
