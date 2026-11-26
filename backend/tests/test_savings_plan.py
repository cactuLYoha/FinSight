from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.account import Account
from app.models.category import Category
from app.models.savings_goal import SavingsContribution
from app.models.transaction import Transaction
from app.models.user import User
from app.services import savings_service as savings


@pytest.fixture
def owner(app, monkeypatch):
    monkeypatch.setattr(savings, 'utc_today', lambda: date(2026, 11, 17))
    user = User(email='plan@example.com')
    user.set_password('StrongPassword123')
    db.session.add(user)
    db.session.commit()
    return user.id


def _goal(owner, amount='100.00', deadline='2027-02-15'):
    return savings.create_goal(owner, {
        'name': 'План', 'target_amount': amount, 'currency': 'UAH', 'deadline': deadline,
    })


def _month(owner, year, month, income, expense, currency='UAH'):
    account = Account(name='History', account_type='bank', user_id=owner, currency=currency)
    db.session.add(account)
    day = datetime(year, month, 15, tzinfo=timezone.utc)
    if Decimal(income):
        db.session.add(Transaction(
            account=account, amount=Decimal(income), transaction_type='income',
            description='Historical income', created_at=day,
        ))
    if Decimal(expense):
        category = db.session.scalar(db.select(Category).where(Category.name == 'History expense'))
        if category is None:
            category = Category(name='History expense')
        db.session.add(Transaction(
            account=account, amount=Decimal(expense), transaction_type='expense',
            description='Historical expense', category=category, created_at=day,
        ))
    db.session.commit()


def test_plan_rounding_exact_sum_and_missing_history(owner):
    goal = _goal(owner)
    plan = savings.get_plan(owner, goal.id)
    assert [item['month'] for item in plan['installments']] == ['2026-12', '2027-01', '2027-02']
    assert [item['due_date'] for item in plan['installments']] == ['2026-12-31', '2027-01-31', '2027-02-15']
    assert [item['amount'] for item in plan['installments']] == ['33.34', '33.33', '33.33']
    assert sum(Decimal(item['amount']) for item in plan['installments']) == Decimal('100.00')
    assert plan['months_until_deadline'] == plan['installment_count'] == 3
    assert plan['required_monthly_amount'] == '33.34'
    assert plan['history']['sample_size'] == 0
    assert plan['history']['status'] == 'insufficient_history'
    assert plan['is_feasible'] is None
    assert plan['monthly_shortfall'] is None
    assert all(row['is_affordable'] is None and row['shortfall'] is None for row in plan['installments'])

    savings.add_contribution(owner, goal.id, {'amount': '10.00'})
    changed = savings.get_plan(owner, goal.id)
    assert changed['goal']['saved_amount'] == '10.00'
    assert [item['amount'] for item in changed['installments']] == ['30.00'] * 3


def test_small_target_does_not_generate_negative_payments(owner):
    plan = savings.get_plan(owner, _goal(owner, amount='0.01').id)
    assert [item['amount'] for item in plan['installments']] == ['0.01', '0.00', '0.00']
    assert plan['installment_count'] == 1
    assert plan['months_until_deadline'] == 3


def test_plan_handles_month_changes_deadline_and_extension(owner, monkeypatch):
    goal = _goal(owner)
    savings.add_contribution(owner, goal.id, {'amount': '10.00'})
    monkeypatch.setattr(savings, 'utc_today', lambda: date(2026, 12, 20))
    assert [item['amount'] for item in savings.get_plan(owner, goal.id)['installments']] == ['45.00', '45.00']
    monkeypatch.setattr(savings, 'utc_today', lambda: date(2027, 2, 1))
    plan = savings.get_plan(owner, goal.id)
    assert plan['installments'][0]['amount'] == '90.00'
    assert plan['installments'][0]['due_date'] == '2027-02-15'
    monkeypatch.setattr(savings, 'utc_today', lambda: date(2027, 2, 16))
    overdue = savings.get_plan(owner, goal.id)
    assert overdue['overdue'] is True
    assert overdue['is_feasible'] is False
    assert overdue['required_monthly_amount'] is None
    assert overdue['installments'] == []
    assert overdue['goal']['remaining_amount'] == '90.00'
    savings.update_goal(owner, goal.id, {'deadline': '2027-03-15'})
    assert not savings.get_plan(owner, goal.id)['overdue']


def test_plan_handles_leap_year(owner, monkeypatch):
    monkeypatch.setattr(savings, 'utc_today', lambda: date(2023, 12, 17))
    plan = savings.get_plan(owner, _goal(owner, amount='1.01', deadline='2024-02-29').id)
    assert [row['due_date'] for row in plan['installments']] == ['2024-01-31', '2024-02-29']
    assert [row['amount'] for row in plan['installments']] == ['0.51', '0.50']


def test_capacity_uses_only_previous_three_closed_months_and_goal_currency(owner):
    goal = _goal(owner, amount='600.00')
    _month(owner, 2026, 8, '300.00', '100.00')
    _month(owner, 2026, 9, '100.00', '300.00')
    _month(owner, 2026, 10, '400.00', '100.00')
    _month(owner, 2026, 11, '9000.00', '1.00')
    _month(owner, 2026, 7, '99999.00', '0.00')
    _month(owner, 2026, 8, '99999.00', '0.00', currency='USD')
    other = User(email='other-history@example.com')
    other.set_password('StrongPassword123')
    db.session.add(other)
    db.session.commit()
    _month(other.id, 2026, 10, '99999.00', '0.00')
    plan = savings.get_plan(owner, goal.id)
    assert plan['history']['sample_size'] == 3
    assert [row['month'] for row in plan['history']['months']] == [8, 9, 10]
    assert plan['history']['average_net'] == plan['history']['available_monthly'] == '100.00'
    assert plan['required_monthly_amount'] == '200.00'
    assert plan['monthly_shortfall'] == '100.00'
    assert plan['is_feasible'] is False


def test_negative_cashflow_counts_existing_deficit(owner):
    goal = _goal(owner, amount='30.00')
    _month(owner, 2026, 10, '10.00', '20.00')
    plan = savings.get_plan(owner, goal.id)
    assert plan['history']['sample_size'] == 1
    assert plan['history']['average_net'] == '-10.00'
    assert plan['history']['available_monthly'] == '0.00'
    assert plan['required_monthly_amount'] == '10.00'
    assert plan['monthly_shortfall'] == '20.00'


def test_partial_history_can_show_affordable_plan(owner):
    goal = _goal(owner, amount='60.00')
    _month(owner, 2026, 10, '50.00', '20.00')
    plan = savings.get_plan(owner, goal.id)
    assert plan['history']['sample_size'] == 1
    assert plan['is_feasible'] is True
    assert plan['monthly_shortfall'] == '0.00'


def test_cancelled_goal_keeps_contributions_and_restricts_user_deletion(owner):
    goal = _goal(owner)
    contribution = savings.add_contribution(owner, goal.id, {'amount': '5.00'})
    contribution_id = contribution.id
    savings.cancel_goal(owner, goal.id)
    assert savings.list_goals(owner)[0]['saved_amount'] == '5.00'
    assert savings.get_plan(owner, goal.id)['installments'] == []
    assert db.session.get(SavingsContribution, contribution_id) is not None
    db.session.delete(db.session.get(User, owner))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()
    assert db.session.get(SavingsContribution, contribution_id).amount == Decimal('5.00')
