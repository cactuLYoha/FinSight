import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.extensions import db
from app.models.account import Account
from app.models.budget import Budget
from app.models.category import Category
from app.models.transaction import Transaction
from app.models.user import User
from app.services.analytics_service import get_monthly_analytics, get_monthly_totals


def _record(account, amount, transaction_type, day, category=None):
    operation = Transaction(
        account=account, amount=Decimal(amount), transaction_type=transaction_type,
        description='Analytics test', created_at=day, category=category,
    )
    db.session.add(operation)
    return operation


def _user(email):
    user = User(email=email)
    user.set_password('StrongPassword123')
    return user


@pytest.fixture
def ledger(app):
    user = _user('analytics@example.com')
    other_user = _user('other-analytics@example.com')
    first = Account(name='Bank', account_type='bank', currency='UAH', balance=Decimal('5000.00'), user=user)
    second = Account(name='Cash', account_type='cash', currency='UAH', user=user)
    unused = Account(name='Unused', account_type='bank', currency='UAH', balance=Decimal('999.00'), user=user)
    euro = Account(name='Euro', account_type='bank', currency='EUR', user=user)
    foreign = Account(name='Other user', account_type='bank', currency='UAH', user=other_user)
    food, transport, small_a, small_b, income_label = [
        Category(name=name) for name in ('Продукти', 'Транспорт', 'Дозвілля', 'Освіта', 'Підпис доходу')
    ]
    db.session.add_all([first, second, unused, euro, foreign, food, transport, small_a, small_b, income_label])
    first_day = datetime(2026, 11, 1, tzinfo=timezone.utc)
    middle_day = datetime(2026, 11, 15, tzinfo=timezone.utc)
    later_day = datetime(2026, 11, 20, tzinfo=timezone.utc)
    income = _record(first, '100.00', 'income', first_day)
    expense = _record(first, '20.00', 'expense', first_day, food)
    _record(second, '50.00', 'income', middle_day, income_label)
    _record(second, '10.00', 'expense', middle_day, transport)
    _record(second, '10.00', 'expense', later_day, food)
    _record(first, '5.00', 'expense', later_day, small_a)
    _record(second, '5.00', 'expense', later_day, small_b)
    _record(euro, '1000.00', 'income', first_day)
    _record(euro, '900.00', 'expense', first_day, food)
    _record(foreign, '9999.00', 'income', first_day)
    _record(foreign, '1000.00', 'expense', first_day, food)
    for outside in (first_day - timedelta(microseconds=1), datetime(2026, 12, 1, tzinfo=timezone.utc)):
        _record(first, '7777.00', 'income', outside)
        _record(first, '6666.00', 'expense', outside, food)
    db.session.commit()
    return {
        'user_id': user.id, 'accounts': (first.id, second.id),
        'categories': (food.id, transport.id, small_a.id, small_b.id),
        'income_id': income.id, 'expense_id': expense.id,
    }


def test_monthly_report_is_scoped_sorted_and_reconciled(ledger):
    report = get_monthly_analytics(ledger['user_id'], 2026, 11, ' uah ')
    totals = get_monthly_totals(ledger['user_id'], 2026, 11, 'UAH')
    assert (report.user_id, report.year, report.month, report.currency) == (
        ledger['user_id'], 2026, 11, 'UAH',
    )
    assert report.income_total == totals.income_total == Decimal('150.00')
    assert report.expense_total == totals.expense_total == Decimal('50.00')
    assert report.net_total == totals.net_total == Decimal('100.00')
    assert report.expense_to_income_percent == Decimal('33.33')
    assert Budget.for_month(ledger['user_id'], 2026, 11, 'UAH').income_total == report.income_total
    assert tuple(row.category_id for row in report.categories) == ledger['categories']
    assert [row.expense_total for row in report.categories] == [
        Decimal('30.00'), Decimal('10.00'), Decimal('5.00'), Decimal('5.00'),
    ]
    assert tuple(row.account_id for row in report.accounts) == ledger['accounts']
    assert [(row.income_total, row.expense_total, row.net_total) for row in report.accounts] == [
        (Decimal('100.00'), Decimal('25.00'), Decimal('75.00')),
        (Decimal('50.00'), Decimal('25.00'), Decimal('25.00')),
    ]
    assert [row.date for row in report.daily] == [date(2026, 11, 1) + timedelta(days=i) for i in range(30)]
    assert report.daily[0].income_total == Decimal('100.00')
    assert report.daily[0].expense_total == Decimal('20.00')
    assert report.daily[1].income_total == report.daily[1].expense_total == Decimal('0.00')
    assert report.daily[14].income_total == Decimal('50.00')
    assert report.daily[19].net_total == Decimal('-20.00')
    for field in ('income_total', 'expense_total', 'net_total'):
        assert sum(getattr(row, field) for row in report.daily) == getattr(report, field)
        assert sum(getattr(row, field) for row in report.accounts) == getattr(report, field)
    assert sum(row.expense_total for row in report.categories) == report.expense_total


def test_report_serializes_money_dates_and_chart_arrays(ledger):
    payload = get_monthly_analytics(ledger['user_id'], 2026, 11, 'UAH').to_dict()
    assert set(payload) == {
        'user_id', 'year', 'month', 'currency', 'income_total', 'expense_total',
        'net_total', 'expense_to_income_percent', 'daily', 'categories', 'accounts',
    }
    assert payload['income_total'] == '150.00'
    assert payload['expense_total'] == '50.00'
    assert payload['net_total'] == '100.00'
    assert payload['expense_to_income_percent'] == '33.33'
    assert payload['daily'][0] == {
        'date': '2026-11-01', 'income_total': '100.00',
        'expense_total': '20.00', 'net_total': '80.00',
    }
    assert payload['categories'][0] == {
        'category_id': ledger['categories'][0], 'name': 'Продукти', 'expense_total': '30.00',
    }
    assert payload['accounts'][0] == {
        'account_id': ledger['accounts'][0], 'name': 'Bank',
        'income_total': '100.00', 'expense_total': '25.00', 'net_total': '75.00',
    }
    assert json.loads(json.dumps(payload, ensure_ascii=False)) == payload


@pytest.mark.parametrize('year, month, day_count', [
    (2024, 2, 29), (2026, 2, 28), (2026, 11, 30), (2026, 12, 31),
])
def test_empty_month_has_complete_zero_series(app, year, month, day_count):
    report = get_monthly_analytics(1, year, month, 'USD')
    assert report.income_total == report.expense_total == report.net_total == Decimal('0.00')
    assert report.expense_to_income_percent is None
    assert report.categories == report.accounts == ()
    assert len(report.daily) == day_count
    assert report.daily[0].date == date(year, month, 1)
    assert report.daily[-1].date == date(year, month, day_count)
    assert all(row.income_total == row.expense_total == row.net_total == Decimal('0.00') for row in report.daily)
    assert report.to_dict()['expense_to_income_percent'] is None


@pytest.mark.parametrize('income, expense, expected_percent, expected_net', [
    ('0.00', '7.00', None, '-7.00'),
    ('10.00', '0.00', '0.00', '10.00'),
    ('10.00', '15.00', '150.00', '-5.00'),
    ('32.00', '1.80', '5.63', '30.20'),
])
def test_spending_percentage_handles_zero_overspending_and_half_up(
    app, income, expense, expected_percent, expected_net,
):
    account = Account(name='Main', account_type='bank', currency='USD', user=_user('ratio@example.com'))
    db.session.add(account)
    day = datetime(2026, 11, 1, tzinfo=timezone.utc)
    if Decimal(income):
        _record(account, income, 'income', day)
    if Decimal(expense):
        _record(account, expense, 'expense', day, Category(name='Інше'))
    db.session.commit()
    report = get_monthly_analytics(account.user_id, 2026, 11, 'USD')
    assert report.net_total == Decimal(expected_net)
    assert report.expense_to_income_percent == (
        Decimal(expected_percent) if expected_percent is not None else None
    )


def test_report_recalculates_all_breakdowns_after_edits(ledger):
    user_id = ledger['user_id']
    original = get_monthly_analytics(user_id, 2026, 11, 'UAH')
    income = db.session.get(Transaction, ledger['income_id'])
    income.amount = Decimal('200.00')
    expense = db.session.get(Transaction, ledger['expense_id'])
    expense.category_id = ledger['categories'][1]
    db.session.commit()

    changed = get_monthly_analytics(user_id, 2026, 11, 'UAH')
    assert changed.income_total == Decimal('250.00')
    assert changed.net_total == Decimal('200.00')
    assert changed.expense_to_income_percent == Decimal('20.00')
    assert changed.daily[0].income_total == Decimal('200.00')
    assert changed.accounts[0].income_total == Decimal('200.00')
    assert changed.categories[0].category_id == ledger['categories'][1]
    assert changed.categories[0].expense_total == Decimal('30.00')

    db.session.delete(expense)
    db.session.commit()
    final = get_monthly_analytics(user_id, 2026, 11, 'UAH')
    assert final.expense_total == Decimal('30.00')
    assert final.daily[0].expense_total == Decimal('0.00')
    assert sum(row.expense_total for row in final.categories) == final.expense_total
    assert original.income_total == Decimal('150.00')
    assert original.categories[0].expense_total == Decimal('30.00')


def test_services_do_not_commit_or_change_account_balance(app):
    account = Account(
        name='Main', account_type='bank', currency='USD',
        balance=Decimal('123.45'), user=_user('readonly@example.com'),
    )
    db.session.add(account)
    db.session.commit()
    account_id, user_id = account.id, account.user_id
    _record(account, '10.00', 'income', datetime(2026, 11, 1, tzinfo=timezone.utc))
    assert get_monthly_totals(user_id, 2026, 11, 'USD').income_total == Decimal('10.00')
    assert get_monthly_analytics(user_id, 2026, 11, 'USD').income_total == Decimal('10.00')
    db.session.rollback()
    assert get_monthly_totals(user_id, 2026, 11, 'USD').income_total == Decimal('0.00')
    assert db.session.get(Account, account_id).balance == Decimal('123.45')


@pytest.mark.parametrize('service', [get_monthly_totals, get_monthly_analytics])
@pytest.mark.parametrize('overrides', [
    {'user_id': 0}, {'month': 13}, {'currency': None},
])
def test_services_validate_month_requests(app, service, overrides):
    arguments = {'user_id': 1, 'year': 2026, 'month': 11, 'currency': 'USD'}
    arguments.update(overrides)
    with pytest.raises(ValueError):
        service(**arguments)


@pytest.mark.postgresql
def test_postgresql_daily_chart_uses_utc_even_in_another_session_timezone(app):
    account = Account(name='Main', account_type='bank', currency='USD', user=_user('utc@example.com'))
    _record(
        account, '12.34', 'income',
        datetime(2026, 12, 1, 1, 0, tzinfo=timezone(timedelta(hours=2))),
    )
    _record(account, '1000.00', 'income', datetime(2026, 12, 1, 1, 0, tzinfo=timezone.utc))
    db.session.commit()
    user_id = account.user_id
    db.session.execute(text("SET LOCAL TIME ZONE 'Pacific/Kiritimati'"))
    report = get_monthly_analytics(user_id, 2026, 11, 'USD')

    assert report.income_total == Decimal('12.34')
    assert report.daily[-1].date == date(2026, 11, 30)
    assert report.daily[-1].income_total == report.income_total
    assert sum(row.income_total for row in report.daily[:-1]) == Decimal('0.00')
    assert db.session.scalar(text('SHOW TIME ZONE')) == 'Pacific/Kiritimati'


@pytest.mark.postgresql
def test_postgresql_aggregates_cents_beyond_single_column_capacity(app):
    account = Account(name='Main', account_type='bank', currency='USD', user=_user('precise@example.com'))
    day = datetime(2026, 11, 1, tzinfo=timezone.utc)
    _record(account, '9999999999999.99', 'income', day)
    _record(account, '0.01', 'income', day)
    _record(account, '0.02', 'expense', day, Category(name='Інше'))
    db.session.commit()
    report = get_monthly_analytics(account.user_id, 2026, 11, 'USD')
    assert report.income_total == Decimal('10000000000000.00')
    assert report.net_total == Decimal('9999999999999.98')
    assert report.daily[0].income_total == report.income_total
    assert report.accounts[0].net_total == report.net_total
    assert report.to_dict()['income_total'] == '10000000000000.00'
