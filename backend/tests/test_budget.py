from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.extensions import db
from app.models.account import Account
from app.models.budget import Budget
from app.models.category import Category
from app.models.transaction import Transaction
from app.models.user import User


NOVEMBER = datetime(2026, 11, 1, tzinfo=timezone.utc)


@pytest.fixture
def account(app):
    user = User(email='budget@example.com')
    user.set_password('StrongPassword123')
    account = Account(
        name='Main', account_type='bank', currency='USD',
        balance=Decimal('9999.99'), user=user,
    )
    db.session.add(account)
    db.session.commit()
    return account


def _record(account, amount, created_at=NOVEMBER, transaction_type='income', category=None):
    transaction = Transaction(
        account=account,
        amount=Decimal(amount),
        transaction_type=transaction_type,
        description='Budget test operation',
        created_at=created_at,
        category=category,
    )
    db.session.add(transaction)
    return transaction


def test_budget_sums_only_user_incomes_in_requested_currency(account):
    user_id = account.user_id
    second_account = Account(
        name='Cash', account_type='cash', currency='USD', user=account.user,
    )
    euro_account = Account(
        name='Euro', account_type='bank', currency='EUR', user=account.user,
    )
    other_user = User(email='other-budget@example.com')
    other_user.set_password('StrongPassword123')
    other_account = Account(
        name='Other user', account_type='bank', currency='USD', user=other_user,
    )
    category = Category(name='Інше')
    _record(account, '0.10')
    _record(account, '0.20', category=category)
    _record(second_account, '2.03')
    _record(euro_account, '1000.00')
    _record(other_account, '2000.00')
    _record(account, '50.00', transaction_type='expense', category=category)
    db.session.commit()

    result = Budget.for_month(user_id, 2026, 11, ' usd ')

    assert isinstance(result, Budget)
    assert (result.user_id, result.year, result.month, result.currency) == (
        user_id, 2026, 11, 'USD',
    )
    assert isinstance(result.income_total, Decimal)
    assert result.income_total == Decimal('2.33')
    assert Budget.for_month(user_id, 2026, 11, 'EUR').income_total == Decimal('1000.00')
    assert Budget.for_month(other_user.id, 2026, 11, 'USD').income_total == Decimal('2000.00')
    assert Budget.for_month(user_id, 2026, 11, 'UAH').income_total == Decimal('0.00')


@pytest.mark.parametrize('has_expense', [False, True])
def test_budget_returns_decimal_zero_without_incomes(account, has_expense):
    if has_expense:
        _record(
            account, '25.00', transaction_type='expense',
            category=Category(name='Продукти'),
        )
        db.session.commit()

    result = Budget.for_month(account.user_id, 2026, 11, 'USD')

    assert isinstance(result.income_total, Decimal)
    assert result.income_total.as_tuple().exponent == -2
    assert result.income_total == Decimal('0.00')


@pytest.mark.parametrize('year, month, start, end', [
    (
        2026, 11,
        datetime(2026, 11, 1, tzinfo=timezone.utc),
        datetime(2026, 12, 1, tzinfo=timezone.utc),
    ),
    (
        2026, 12,
        datetime(2026, 12, 1, tzinfo=timezone.utc),
        datetime(2027, 1, 1, tzinfo=timezone.utc),
    ),
    (
        2024, 2,
        datetime(2024, 2, 1, tzinfo=timezone.utc),
        datetime(2024, 3, 1, tzinfo=timezone.utc),
    ),
])
def test_budget_uses_utc_month_boundaries(account, year, month, start, end):
    _record(account, '1000.00', start - timedelta(microseconds=1))
    _record(account, '1.23', start)
    _record(account, '2.34', end - timedelta(microseconds=1))
    _record(account, '1000.00', end)
    db.session.commit()

    result = Budget.for_month(account.user_id, year, month, 'USD')

    assert result.income_total == Decimal('3.57')


def test_budget_recalculates_after_changes_and_preserves_previous_result(account):
    first_income = _record(account, '10.00')
    db.session.commit()
    original_result = Budget.for_month(account.user_id, 2026, 11, 'USD')
    assert original_result.income_total == Decimal('10.00')

    first_income.amount = Decimal('15.25')
    db.session.commit()
    assert Budget.for_month(account.user_id, 2026, 11, 'USD').income_total == Decimal('15.25')

    second_income = _record(account, '4.75')
    db.session.commit()
    assert Budget.for_month(account.user_id, 2026, 11, 'USD').income_total == Decimal('20.00')

    db.session.delete(first_income)
    db.session.commit()
    assert Budget.for_month(account.user_id, 2026, 11, 'USD').income_total == Decimal('4.75')

    db.session.delete(second_income)
    db.session.commit()
    assert Budget.for_month(account.user_id, 2026, 11, 'USD').income_total == Decimal('0.00')
    assert original_result.income_total == Decimal('10.00')


@pytest.mark.parametrize('overrides', [
    {'user_id': 0},
    {'user_id': -1},
    {'user_id': '1'},
    {'user_id': True},
    {'year': 0},
    {'year': 10000},
    {'year': '2026'},
    {'year': 2026.0},
    {'year': 9999, 'month': 12},
    {'month': 0},
    {'month': 13},
    {'month': True},
    {'month': '11'},
    {'currency': ''},
    {'currency': 'US'},
    {'currency': 'USDT'},
    {'currency': 'U1D'},
    {'currency': 'УКР'},
    {'currency': None},
])
def test_budget_rejects_invalid_parameters(app, overrides):
    arguments = {'user_id': 1, 'year': 2026, 'month': 11, 'currency': 'USD'}
    arguments.update(overrides)

    with pytest.raises(ValueError):
        Budget.for_month(**arguments)
