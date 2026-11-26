from datetime import date
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import pytest
from flask_jwt_extended import create_access_token

from app.extensions import db
from app.models.account import Account
from app.models.transaction import Transaction
from app.models.recurring_expense import RecurringExpense
from app.models.user import User
from app.services import recurring_expense_service as recurring
from tests.test_expenses import expense_setup, body


def test_month_end_leap_year_no_duplicates_and_balance(client, expense_setup, monkeypatch):
    user, category, headers = expense_setup
    monkeypatch.setattr(recurring, 'today', lambda: date(2028, 3, 31))
    payload = {**body(category), 'date': '2028-01-31', 'recurring': True}
    response = client.post('/api/expenses', headers=headers, json=payload)
    assert response.status_code == 201
    rule = db.session.get(RecurringExpense, response.json['recurring_expense']['id'])
    assert rule.next_due_on == date(2028, 4, 30)
    rows = list(db.session.scalars(db.select(Transaction).order_by(Transaction.created_at)))
    assert [row.created_at.date() for row in rows] == [date(2028, 1, 31), date(2028, 2, 29), date(2028, 3, 31)]
    recurring.materialize_due(user.id)
    db.session.commit()
    assert db.session.query(Transaction).count() == 3
    assert db.session.scalar(db.select(Account)).balance == Decimal('-376.50')
    monkeypatch.setattr(recurring, 'today', lambda: date(2028, 5, 31))
    client.get('/api/analytics/monthly?year=2028&month=5&currency=UAH', headers=headers)
    assert db.session.query(Transaction).count() == 5
    assert rule.next_due_on == date(2028, 6, 30)


def test_editing_occurrence_preserves_rule_and_does_not_duplicate_charge(client, expense_setup, monkeypatch):
    user, category, headers = expense_setup
    monkeypatch.setattr(recurring, 'today', lambda: date(2028, 1, 5))
    response = client.post('/api/expenses', headers=headers, json={**body(category), 'date': '2028-01-05', 'recurring': True})
    rule = db.session.get(RecurringExpense, response.json['recurring_expense']['id'])
    row = db.session.scalar(db.select(Transaction))
    assert client.patch(f'/api/expenses/{row.id}', headers=headers, json={'amount': '50.00', 'description': 'Edited occurrence', 'date': '2028-01-07'}).status_code == 200
    assert rule.amount == Decimal('125.50')
    assert rule.billing_day == 5
    recurring.materialize_due(user.id); db.session.commit()
    assert db.session.query(Transaction).count() == 1
    assert db.session.scalar(db.select(Account)).balance == Decimal('-50.00')
    monkeypatch.setattr(recurring, 'today', lambda: date(2028, 2, 5))
    recurring.materialize_due(user.id); db.session.commit()
    assert db.session.query(Transaction).count() == 2
    assert db.session.scalar(db.select(Account)).balance == Decimal('-175.50')
    assert client.delete(f'/api/expenses/{row.id}', headers=headers).status_code == 204
    assert db.session.scalar(db.select(Account)).balance == Decimal('-125.50')
    recurring.materialize_due(user.id); db.session.commit()
    assert db.session.query(Transaction).count() == 1
    assert rule.active is True
    assert rule.next_due_on == date(2028, 3, 5)


def test_future_rule_waits_until_due_and_can_be_stopped(client, expense_setup, monkeypatch):
    _, category, headers = expense_setup
    monkeypatch.setattr(recurring, 'today', lambda: date(2028, 1, 1))
    response = client.post('/api/expenses', headers=headers, json={**body(category), 'date': '2028-02-05', 'recurring': True})
    assert response.status_code == 201
    rule_id = response.json['recurring_expense']['id']
    assert db.session.query(Transaction).count() == 0
    monkeypatch.setattr(recurring, 'today', lambda: date(2028, 2, 5))
    result = client.get('/api/expenses?year=2028&month=2&currency=UAH', headers=headers).json
    assert result['total'] == 1
    assert result['expenses'][0]['recurring_id'] == rule_id
    assert len(result['recurring_expenses']) == 1
    assert client.delete(f'/api/expenses/recurring/{rule_id}', headers=headers).status_code == 204
    monkeypatch.setattr(recurring, 'today', lambda: date(2028, 5, 5))
    result = client.get('/api/expenses?year=2028&month=5&currency=UAH', headers=headers).json
    assert result['recurring_expenses'] == []
    assert db.session.query(Transaction).count() == 1
    history = client.get('/api/expenses?year=2028&month=2&currency=UAH', headers=headers).json
    assert history['expenses'][0]['recurring_active'] is False
    expense_id = history['expenses'][0]['id']
    restarted = client.post(f'/api/expenses/{expense_id}/repeat', headers=headers)
    assert restarted.status_code == 201
    assert restarted.json['recurring_expense']['next_due_on'] == '2028-06-05'
    assert db.session.query(Transaction).count() == 1
    history = client.get('/api/expenses?year=2028&month=2&currency=UAH', headers=headers).json
    assert history['expenses'][0]['recurring_active'] is True


def test_convert_existing_expense_does_not_charge_twice(client, expense_setup, monkeypatch):
    _, category, headers = expense_setup
    monkeypatch.setattr(recurring, 'today', lambda: date(2026, 11, 20))
    response = client.post('/api/expenses', headers=headers, json=body(category))
    expense_id = response.json['expense']['id']
    result = client.post(f'/api/expenses/{expense_id}/repeat', headers=headers)
    assert result.status_code == 201
    assert db.session.query(Transaction).count() == 1  # Conversion starts next month; history is unchanged.
    assert result.json['recurring_expense']['next_due_on'] == '2026-12-15'
    assert client.post(f'/api/expenses/{expense_id}/repeat', headers=headers).status_code == 409
    assert db.session.query(Transaction).count() == 1
    assert client.post('/api/expenses/999999/repeat', headers=headers).status_code == 404
    assert client.delete('/api/expenses/recurring/999999', headers=headers).status_code == 404


def test_other_user_cannot_convert_or_stop_rule(client, expense_setup):
    _, category, headers = expense_setup
    expense = client.post('/api/expenses', headers=headers, json=body(category)).json['expense']
    rule = client.post(f"/api/expenses/{expense['id']}/repeat", headers=headers).json['recurring_expense']
    other = User(email='other-recurring@example.com', is_email_verified=True)
    other.set_password('password123')
    db.session.add(other)
    db.session.commit()
    token = create_access_token(identity=str(other.id), additional_claims={'auth_complete': True})
    other_headers = {**headers, 'Authorization': 'Bearer ' + token}
    assert client.post(f"/api/expenses/{expense['id']}/repeat", headers=other_headers).status_code == 404
    assert client.delete(f"/api/expenses/recurring/{rule['id']}", headers=other_headers).status_code == 404
    assert client.get('/api/expenses?year=2026&month=11&currency=UAH', headers=other_headers).json['recurring_expenses'] == []


@pytest.mark.postgresql
def test_concurrent_worker_and_ui_only_charge_once(app, client, expense_setup, monkeypatch):
    user, category, headers = expense_setup
    user_id = user.id
    monkeypatch.setattr(recurring, 'today', lambda: date(2028, 1, 1))
    assert client.post('/api/expenses', headers=headers, json={**body(category), 'date': '2028-01-05', 'recurring': True}).status_code == 201
    db.session.commit()
    monkeypatch.setattr(recurring, 'today', lambda: date(2028, 1, 5))
    barrier = Barrier(2)

    def process():
        with app.app_context():
            barrier.wait(timeout=10)
            recurring.materialize_due(user_id)
            db.session.commit()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(process) for _ in range(2)]
        for future in futures:
            future.result(timeout=20)
    db.session.expire_all()
    assert db.session.query(Transaction).count() == 1
    assert db.session.scalar(db.select(Account)).balance == Decimal('-125.50')
