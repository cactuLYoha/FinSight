from datetime import date
from decimal import Decimal

from app.extensions import db
from app.models.account import Account
from app.models.transaction import Transaction
from app.models.recurring_income import RecurringIncome
from app.services import recurring_income_service as recurring
from tests.test_expenses import expense_setup


def account(client, headers):
    return client.post('/api/accounts', headers=headers, json={'name': 'Salary', 'currency': 'UAH', 'account_type': 'bank'}).json['account']['id']


def test_month_end_catchup_leap_year_and_no_duplicates(client, expense_setup, monkeypatch):
    user, _, headers = expense_setup
    monkeypatch.setattr(recurring, 'today', lambda: date(2028, 3, 31))
    identifier = account(client, headers)
    response = client.post(f'/api/accounts/{identifier}/incomes', headers=headers,
        json={'amount': '100.25', 'date': '2028-01-31', 'description': 'Salary', 'recurring': True})
    assert response.status_code == 201
    rule = db.session.get(RecurringIncome, response.json['recurring_income']['id'])
    assert rule.next_due_on == date(2028, 4, 30)
    rows = list(db.session.scalars(db.select(Transaction).order_by(Transaction.created_at)))
    assert [row.created_at.date() for row in rows] == [date(2028, 1, 31), date(2028, 2, 29), date(2028, 3, 31)]
    recurring.materialize_due(user.id); db.session.commit()
    assert db.session.query(Transaction).count() == 3
    assert db.session.get(Account, identifier).balance == Decimal('300.75')
    history = client.get(f'/api/accounts/{identifier}/incomes', headers=headers).json
    assert len(history['recurring_incomes']) == 1
    assert all(row['recurring_active'] for row in history['incomes'])


def test_future_rule_waits_and_stop_keeps_income_history(client, expense_setup, monkeypatch):
    user, _, headers = expense_setup
    monkeypatch.setattr(recurring, 'today', lambda: date(2028, 1, 1))
    identifier = account(client, headers)
    url = f'/api/accounts/{identifier}'
    response = client.post(url + '/incomes', headers=headers, json={'amount': '50', 'date': '2028-02-05', 'description': 'Salary', 'recurring': True})
    assert response.status_code == 201
    rule_id = response.json['recurring_income']['id']
    assert response.json['account']['balance'] == '0.00'
    monkeypatch.setattr(recurring, 'today', lambda: date(2028, 2, 5))
    assert client.get(url + '/incomes', headers=headers).json['total'] == 1
    assert client.delete(url + f'/recurring-incomes/{rule_id}', headers=headers).status_code == 204
    monkeypatch.setattr(recurring, 'today', lambda: date(2028, 4, 5))
    recurring.materialize_due(user.id); db.session.commit()
    assert db.session.query(Transaction).count() == 1
    assert db.session.get(Account, identifier).balance == Decimal('50.00')


def test_convert_existing_income_does_not_credit_again_and_checks_ownership(client, expense_setup, monkeypatch):
    _, _, headers = expense_setup
    monkeypatch.setattr(recurring, 'today', lambda: date(2028, 1, 10))
    identifier = account(client, headers)
    url = f'/api/accounts/{identifier}'
    row = client.post(url + '/incomes', headers=headers, json={'amount': '75', 'date': '2028-01-05', 'description': 'Salary'}).json['income']
    response = client.post(url + f"/incomes/{row['id']}/repeat", headers=headers)
    assert response.status_code == 201
    assert response.json['account']['balance'] == '75.00'
    assert client.post(url + f"/incomes/{row['id']}/repeat", headers=headers).status_code == 409
    assert client.post(url + f"/incomes/{row['id']}/repeat").status_code == 401
    assert client.delete(url + f"/recurring-incomes/{response.json['recurring_income']['id']}").status_code == 401
    assert client.post('/api/accounts/999/incomes/1/repeat', headers=headers).status_code == 404
    assert client.delete(url + '/recurring-incomes/999', headers=headers).status_code == 404
    assert client.post(url + '/incomes', headers=headers, json={'amount': '10', 'date': '2028-01-05', 'description': 'Bad', 'recurring': 'true'}).status_code == 400
    assert db.session.get(Account, identifier).balance == Decimal('75.00')
