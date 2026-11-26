from decimal import Decimal

import pytest
from flask_jwt_extended import create_access_token

from app.extensions import db
from app.models.account import Account
from app.models.transaction import Transaction
from app.models.user import User
from tests.test_expenses import expense_setup

BASE = '/api/accounts'
NEW = {'name': ' Main card ', 'account_type': 'card', 'currency': 'uah'}
INCOME = {'amount': '1250.50', 'date': '2026-10-15', 'description': ' Salary '}


def create(client, headers):
    response = client.post(BASE, headers=headers, json=NEW)
    assert response.status_code == 201
    return response.json['account']


@pytest.mark.parametrize('method,path', [('get', ''), ('post', ''), ('patch', '/1'), ('get', '/1/incomes'), ('post', '/1/incomes')])
def test_accounts_require_auth(client, method, path):
    assert getattr(client, method)(BASE + path).status_code == 401


def test_create_edit_and_income_updates_balance_and_analytics(client, expense_setup):
    _, _, headers = expense_setup
    account = create(client, headers)
    assert (account['name'], account['currency'], account['balance']) == ('Main card', 'UAH', '0.00')
    url = f"{BASE}/{account['id']}"
    edited = client.patch(url, headers=headers, json={'name': 'Savings card', 'account_type': 'bank'})
    assert edited.status_code == 200
    assert edited.json['account']['balance'] == '0.00'
    response = client.post(url + '/incomes', headers=headers, json=INCOME)
    assert response.status_code == 201
    assert response.json['account']['balance'] == '1250.50'
    assert response.json['income']['description'] == 'Salary'
    assert client.get(BASE, headers=headers).json['accounts'][0]['name'] == 'Savings card'
    assert client.get(url + '/incomes', headers=headers).json['total'] == 1
    assert client.get('/api/analytics/monthly?year=2026&month=10&currency=UAH', headers=headers).json['analytics']['income_total'] == '1250.50'
    assert client.get('/api/analytics/monthly?year=2026&month=11&currency=UAH', headers=headers).json['analytics']['income_total'] == '0.00'
    assert client.get('/api/expenses?year=2026&month=10&currency=UAH', headers=headers).json['accounts'][0]['id'] == account['id']


@pytest.mark.parametrize('changes', [{'amount': '0'}, {'amount': '1.001'}, {'date': '9999-12-31'}, {'date': '2026-02-30'}, {'description': '  '}, {'description': 'x' * 101}, {'currency': 'USD'}])
def test_invalid_income_has_no_balance_effect(client, expense_setup, changes):
    _, _, headers = expense_setup
    account = create(client, headers)
    assert client.post(f"{BASE}/{account['id']}/incomes", headers=headers, json={**INCOME, **changes}).status_code == 400
    assert db.session.get(Account, account['id']).balance == Decimal('0.00')
    assert db.session.query(Transaction).count() == 0


def test_ownership_origin_immutable_currency_balance_and_limits(client, expense_setup):
    _, _, headers = expense_setup
    account = create(client, headers)
    url = f"{BASE}/{account['id']}"
    for values in ({'currency': 'USD'}, {'balance': 100}, {}, {'name': '   '}, {'account_type': 'wrong'}):
        assert client.patch(url, headers=headers, json=values).status_code == 400
    other = User(email='other-accounts@example.com', is_email_verified=True)
    other.set_password('password123'); db.session.add(other); db.session.commit()
    other_headers = {**headers, 'Authorization': 'Bearer ' + create_access_token(identity=str(other.id), additional_claims={'auth_complete': True})}
    assert client.get(BASE, headers=other_headers).json['accounts'] == []
    assert client.patch(url, headers=other_headers, json={'name': 'Stolen'}).status_code == 404
    assert client.get(url + '/incomes', headers=other_headers).status_code == 404
    assert client.post(url + '/incomes', headers=other_headers, json=INCOME).status_code == 404
    assert client.post(url + '/incomes', headers={**headers, 'Origin': 'https://wrong.example'}, json=INCOME).status_code == 403
    row = db.session.get(Account, account['id']); row.balance = Decimal('9999999999999.99'); db.session.commit()
    assert client.post(url + '/incomes', headers=headers, json=INCOME).status_code == 400
    assert row.balance == Decimal('9999999999999.99')
    assert db.session.query(Transaction).count() == 0


def test_income_history_pagination(client, expense_setup):
    _, _, headers = expense_setup
    account = create(client, headers)
    from datetime import datetime, timezone
    db.session.add_all([Transaction(account_id=account['id'], amount=1, description=f'Income {index}', transaction_type='income', created_at=datetime(2026, 10, 1, tzinfo=timezone.utc)) for index in range(51)])
    db.session.commit()
    url = f"{BASE}/{account['id']}/incomes"
    first = client.get(url, headers=headers).json
    second = client.get(url + '?page=2', headers=headers).json
    assert first['total'] == second['total'] == 51
    assert len(first['incomes']) == 50 and len(second['incomes']) == 1
    assert first['incomes'][0]['id'] > second['incomes'][0]['id']
    assert client.get(url + '?page=0', headers=headers).status_code == 400
