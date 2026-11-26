from decimal import Decimal

import pytest
from flask_jwt_extended import create_access_token

from app.extensions import db
from app.models.user import User
from app.models.category import Category
from app.models.account import Account
from app.models.transaction import Transaction

ORIGIN = {'Origin': 'http://localhost:4200'}


@pytest.fixture
def expense_setup(app):
    app.config['AUTH_TRUSTED_ORIGINS'] = frozenset({ORIGIN['Origin']})
    user = User(email='expenses@example.com', is_email_verified=True)
    user.set_password('password123')
    category = Category(name='Test expenses')
    db.session.add_all([user, category])
    db.session.commit()
    token = create_access_token(identity=str(user.id), additional_claims={'auth_complete': True})
    return user, category, {**ORIGIN, 'Authorization': 'Bearer ' + token}


def body(category):
    return dict(amount='125.50', currency='UAH', category_id=category.id, description=' Groceries ', date='2026-10-15')


def test_expense_persists_updates_balance_and_analytics(client, expense_setup):
    user, category, headers = expense_setup
    result = client.post('/api/expenses', headers=headers, json=body(category))
    assert result.status_code == 201
    assert result.json['expense']['description'] == 'Groceries'
    account = db.session.scalar(db.select(Account).where(Account.user_id == user.id))
    assert account.balance == Decimal('-125.50')
    assert client.post('/api/expenses', headers=headers, json=body(category)).status_code == 201
    assert db.session.query(Account).count() == 1
    response = client.get('/api/expenses?year=2026&month=10&currency=UAH', headers=headers)
    assert response.json['total'] == 2
    assert len(response.json['expenses']) == 2
    totals = client.get('/api/analytics/monthly?year=2026&month=10&currency=UAH', headers=headers).json['analytics']
    assert totals['expense_total'] == '251.00'
    assert client.get('/api/expenses?year=2026&month=11&currency=UAH', headers=headers).json['total'] == 0
    assert client.get('/api/expenses?year=2026&month=10&currency=USD', headers=headers).json['total'] == 0


def test_expense_ownership(client, expense_setup):
    user, category, headers = expense_setup
    other = User(email='other-expenses@example.com', is_email_verified=True)
    other.set_password('password123')
    db.session.add(other)
    db.session.flush()
    account = Account(user_id=other.id, name='Other account', currency='UAH', account_type='bank', balance=1000)
    db.session.add(account)
    db.session.commit()
    assert client.post('/api/expenses', headers=headers, json={**body(category), 'account_id': account.id}).status_code == 400
    response = client.get('/api/expenses?year=2026&month=10&currency=UAH', headers=headers).json
    assert response['accounts'] == []
    assert account.balance == Decimal('1000')
    assert client.get('/api/expenses?year=2026&month=10&currency=UAH').status_code == 401


@pytest.mark.parametrize('change', [
    {'amount': '-1'}, {'amount': '0'}, {'amount': '1.001'}, {'amount': 'NaN'},
    {'date': '2026-02-30'}, {'category_id': 99999}, {'description': '   '},
    {'description': 'x' * 101}, {'user_id': 5}, {'account_id': 0},
])
def test_expense_validation(client, expense_setup, change):
    _, category, headers = expense_setup
    assert client.post('/api/expenses', headers=headers, json={**body(category), **change}).status_code == 400
    assert db.session.query(Transaction).count() == 0


def test_expense_own_account_and_origin(client, expense_setup):
    user, category, headers = expense_setup
    account = Account(user_id=user.id, name='Bank', currency='UAH', account_type='bank', balance=1000)
    db.session.add(account)
    db.session.commit()
    payload = {**body(category), 'account_id': account.id}
    assert client.post('/api/expenses', headers={**headers, 'Origin': 'https://wrong.example'}, json=payload).status_code == 403
    assert client.post('/api/expenses', headers=headers, json={**payload, 'currency': 'USD'}).status_code == 400
    assert client.post('/api/expenses', headers=headers, json=payload).status_code == 201
    assert account.balance == Decimal('874.50')


def test_delete_expense_restores_balance_updates_totals_and_does_not_refund_twice(client, expense_setup):
    _, category, headers = expense_setup
    expense = client.post('/api/expenses', headers=headers, json=body(category)).json['expense']
    url = f"/api/expenses/{expense['id']}"
    account = db.session.get(Account, expense['account_id'])
    assert client.delete(url).status_code == 401
    assert client.delete(url, headers={**headers, 'Origin': 'https://wrong.example'}).status_code == 403
    assert account.balance == Decimal('-125.50')
    assert client.delete(url, headers=headers).status_code == 204
    assert account.balance == Decimal('0.00')
    assert db.session.get(Transaction, expense['id']) is None
    assert client.delete(url, headers=headers).status_code == 404
    assert account.balance == Decimal('0.00')
    assert client.get('/api/analytics/monthly?year=2026&month=10&currency=UAH', headers=headers).json['analytics']['expense_total'] == '0.00'


def test_delete_rejects_other_users_income_and_balance_overflow(client, expense_setup):
    user, category, headers = expense_setup
    expense = client.post('/api/expenses', headers=headers, json=body(category)).json['expense']
    other = User(email='delete-other@example.com', is_email_verified=True)
    other.set_password('password123'); db.session.add(other); db.session.flush()
    foreign_headers = {**ORIGIN, 'Authorization': 'Bearer ' + create_access_token(identity=str(other.id), additional_claims={'auth_complete': True})}
    assert client.delete(f"/api/expenses/{expense['id']}", headers=foreign_headers).status_code == 404
    account = db.session.get(Account, expense['account_id'])
    income = Transaction(account_id=account.id, transaction_type='income', amount=10, description='Income')
    db.session.add(income); db.session.commit()
    assert client.delete(f'/api/expenses/{income.id}', headers=headers).status_code == 404
    account.balance = Decimal('9999999999999.99'); db.session.commit()
    assert client.delete(f"/api/expenses/{expense['id']}", headers=headers).status_code == 400
    assert db.session.get(Transaction, expense['id']) is not None
    assert account.balance == Decimal('9999999999999.99')


def test_edit_expense_rebalances_accounts_and_monthly_totals(client, expense_setup):
    user, category, headers = expense_setup
    expense = client.post('/api/expenses', headers=headers, json=body(category)).json['expense']
    original = db.session.get(Account, expense['account_id'])
    target = Account(user_id=user.id, name='Bank', currency='UAH', account_type='bank', balance=1000)
    second = Category(name='Transport')
    db.session.add_all([target, second])
    db.session.commit()
    url = f"/api/expenses/{expense['id']}"
    response = client.patch(url, headers=headers, json={'amount': '50.25', 'description': ' Edited ', 'category_id': second.id, 'account_id': target.id, 'date': '2026-11-05'})
    assert response.status_code == 200
    assert response.json['expense']['description'] == 'Edited'
    assert response.json['expense']['account_id'] == target.id
    assert original.balance == Decimal('0.00')
    assert target.balance == Decimal('949.75')
    for month, total in [(10, '0.00'), (11, '50.25')]:
        assert client.get(f'/api/analytics/monthly?year=2026&month={month}&currency=UAH', headers=headers).json['analytics']['expense_total'] == total
    assert client.patch(url, headers=headers, json={'amount': '40.00'}).status_code == 200
    assert target.balance == Decimal('960.00')
    assert client.patch(url, headers=headers, json={'description': 'Only description'}).status_code == 200
    assert target.balance == Decimal('960.00')


@pytest.mark.parametrize('changes', [{}, {'amount': '0'}, {'amount': '1.001'}, {'description': '  '}, {'date': '2026-02-30'}, {'category_id': 99999}, {'account_id': 99999}, {'currency': 'USD'}, {'recurring': True}])
def test_invalid_edits_leave_balance_and_expense_unchanged(client, expense_setup, changes):
    _, category, headers = expense_setup
    expense = client.post('/api/expenses', headers=headers, json=body(category)).json['expense']
    assert client.patch(f"/api/expenses/{expense['id']}", headers=headers, json=changes).status_code == 400
    row = db.session.get(Transaction, expense['id'])
    assert row.amount == Decimal('125.50')
    assert row.account.balance == Decimal('-125.50')


def test_edit_requires_auth_owner_currency_and_trusted_origin(client, expense_setup):
    user, category, headers = expense_setup
    expense = client.post('/api/expenses', headers=headers, json=body(category)).json['expense']
    url = f"/api/expenses/{expense['id']}"
    assert client.patch(url, json={'amount': '10'}).status_code == 401
    assert client.patch(url, headers={**headers, 'Origin': 'https://wrong.example'}, json={'amount': '10'}).status_code == 403
    other = User(email='expense-editor@example.com', is_email_verified=True)
    other.set_password('password123')
    db.session.add(other)
    db.session.flush()
    foreign = Account(user_id=other.id, name='Foreign', currency='UAH', account_type='bank', balance=1000)
    usd = Account(user_id=user.id, name='USD', currency='USD', account_type='bank', balance=1000)
    db.session.add_all([foreign, usd]); db.session.commit()
    for target in (foreign, usd):
        assert client.patch(url, headers=headers, json={'account_id': target.id}).status_code == 400
        assert target.balance == Decimal('1000.00')
    other_headers = {**ORIGIN, 'Authorization': 'Bearer ' + create_access_token(identity=str(other.id), additional_claims={'auth_complete': True})}
    assert client.patch(url, headers=other_headers, json={'amount': '10'}).status_code == 404
    assert client.patch('/api/expenses/999999', headers=headers, json={'amount': '10'}).status_code == 404
