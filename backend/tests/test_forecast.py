import json
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from flask_jwt_extended import create_access_token

from app.extensions import db
from app.models.account import Account
from app.models.category import Category
from app.models.savings_goal import SavingsContribution, SavingsGoal
from app.models.transaction import Transaction
from app.models.user import User
from app.services import analytics_service as analytics


@pytest.fixture
def ledger_factory(app, monkeypatch):
    monkeypatch.setattr(analytics, '_forecast_today', lambda: date(2026, 11, 18))

    def seed(pairs=(('100.00', '50.00'), ('200.00', '100.00'), ('300.00', '150.00'))):
        user = User(is_email_verified=True, email='forecast@example.com')
        other = User(is_email_verified=True, email='other-forecast@example.com')
        user.set_password('StrongPassword123')
        other.set_password('StrongPassword123')
        main = Account(name='Main', account_type='bank', currency='UAH', user=user, balance=Decimal('999999.99'))
        usd = Account(name='USD', account_type='bank', currency='USD', user=user)
        foreign = Account(name='Other', account_type='bank', currency='UAH', user=other)
        category = Category(name='Forecast expenses')
        db.session.add_all([main, usd, foreign, category])
        for index, (income, expense) in enumerate(pairs):
            month = 11 - len(pairs) + index
            _record(main, income, 'income', month)
            _record(main, expense, 'expense', month, category)
        _record(main, '99999.00', 'income', 4)
        _record(main, '88888.00', 'income', 11)
        _record(usd, '77777.00', 'income', 8)
        _record(foreign, '66666.00', 'income', 8)
        db.session.commit()
        return {
            'user_id': user.id, 'account_id': main.id, 'other_id': other.id,
            'headers': {'Authorization': 'Bearer ' + create_access_token(additional_claims={'auth_complete': True}, identity=str(user.id))},
        }
    return seed


def _record(account, amount, kind, month, category=None):
    if Decimal(amount):
        db.session.add(Transaction(
            account=account, amount=Decimal(amount), transaction_type=kind,
            description='Forecast input', category=category,
            created_at=datetime(2026, month, 15, tzinfo=timezone.utc),
        ))


def _goal(data, saved='20.00', target='250.00', deadline=date(2027, 2, 15), currency='UAH', status='active'):
    goal = SavingsGoal(
        user_id=data['user_id'], name='Future goal', target_amount=Decimal(target),
        currency=currency, deadline=deadline, status=status,
    )
    db.session.add(goal)
    db.session.flush()
    if Decimal(saved):
        db.session.add(SavingsContribution(
            goal_id=goal.id, amount=Decimal(saved), contributed_on=date(2026, 11, 17),
        ))
    db.session.commit()
    return goal


def test_quartile_scenarios_scope_history_and_relative_cashflow(ledger_factory):
    data = ledger_factory()
    report = analytics.get_financial_forecast(data['user_id'], ' uah ', 3)
    assert report.status == 'ready'
    assert report.currency == 'UAH'
    assert report.sample_size == 3
    assert report.history_window == ('2026-05', '2026-06', '2026-07', '2026-08', '2026-09', '2026-10')
    assert report.used_months == ('2026-08', '2026-09', '2026-10')
    assert report.missing_months == ('2026-05', '2026-06', '2026-07')
    assert report.starting_savings == Decimal('0.00')
    assert report.starting_savings_basis == 'relative_change'
    assert report.goal is None
    assert [(row.name, row.monthly_income, row.monthly_expense, row.monthly_net) for row in report.scenarios] == [
        ('pessimistic', Decimal('150.00'), Decimal('125.00'), Decimal('25.00')),
        ('realistic', Decimal('200.00'), Decimal('100.00'), Decimal('100.00')),
        ('optimistic', Decimal('250.00'), Decimal('75.00'), Decimal('175.00')),
    ]
    for scenario in report.scenarios:
        assert [point.month for point in scenario.points] == ['2026-12', '2027-01', '2027-02']
        assert scenario.points[-1].cumulative_net_change == scenario.monthly_net * 3
        assert scenario.points[-1].projected_savings == scenario.monthly_net * 3
        assert scenario.goal_projection is None
    payload = report.to_dict()
    assert payload['as_of'] == '2026-11-18'
    assert payload['scenarios'][0]['points'][0]['income_total'] == '150.00'
    assert json.loads(json.dumps(payload)) == payload


@pytest.mark.parametrize('count', [0, 1, 2])
def test_forecast_requires_three_closed_months(ledger_factory, count):
    data = ledger_factory([('100.00', '50.00')] * count)
    report = analytics.get_financial_forecast(data['user_id'], 'UAH')
    assert report.status == 'insufficient_history'
    assert report.sample_size == count
    assert report.minimum_history_months == 3
    assert report.horizon_months == 12
    assert report.scenarios == ()


@pytest.mark.parametrize('pairs, expected', [
    ([('1.00', '0.00'), ('1.01', '0.00'), ('1.02', '0.00')], ('1.01', '1.01', '1.02')),
    ([(str(value), '0.00') for value in range(1, 7)], ('2.25', '3.50', '4.75')),
])
def test_percentile_interpolation_and_half_up(ledger_factory, pairs, expected):
    data = ledger_factory(pairs)
    report = analytics.get_financial_forecast(data['user_id'], 'UAH', 1)
    assert [row.monthly_income for row in report.scenarios] == [Decimal(value) for value in expected]


def test_goal_projection_uses_manual_savings_and_deadline_month(ledger_factory):
    data = ledger_factory()
    goal = _goal(data)
    report = analytics.get_financial_forecast(data['user_id'], 'UAH', 3)
    assert report.starting_savings == Decimal('20.00')
    assert report.starting_savings_basis == 'active_goal'
    assert report.goal.id == goal.id
    pessimistic, realistic, optimistic = report.scenarios
    assert pessimistic.points[0].projected_savings == Decimal('45.00')
    assert pessimistic.goal_projection.estimated_goal_month is None
    assert pessimistic.goal_projection.goal_reachable_by_deadline is False
    assert realistic.goal_projection.estimated_goal_month == '2027-02'
    assert realistic.goal_projection.goal_reachable_by_deadline is True
    assert optimistic.goal_projection.estimated_goal_month == '2027-01'
    assert optimistic.goal_projection.assessment_granularity == 'month'
    assert db.session.get(SavingsGoal, goal.id).status == 'active'
    assert db.session.scalar(db.select(db.func.sum(SavingsContribution.amount))) == Decimal('20.00')


def test_deadline_outside_horizon_is_not_rejected_without_evidence(ledger_factory):
    data = ledger_factory()
    _goal(data, target='10000.00', deadline=date(2028, 1, 1))
    report = analytics.get_financial_forecast(data['user_id'], 'UAH', 1)
    assert all(item.goal_projection.goal_reachable_by_deadline is None for item in report.scenarios)


@pytest.mark.parametrize('currency,status', [('USD', 'active'), ('UAH', 'cancelled'), ('UAH', 'completed')])
def test_forecast_ignores_unrelated_or_closed_goals(ledger_factory, currency, status):
    data = ledger_factory()
    _goal(data, currency=currency, status=status)
    report = analytics.get_financial_forecast(data['user_id'], 'UAH', 1)
    assert report.goal is None
    assert report.starting_savings == Decimal('0.00')


def test_already_achieved_goal_uses_actual_contribution_dates(ledger_factory):
    data = ledger_factory()
    goal = _goal(data, saved='0.00', deadline=date(2026, 10, 10))
    db.session.add_all([
        SavingsContribution(goal_id=goal.id, amount=Decimal('100.00'), contributed_on=date(2026, 10, 5)),
        SavingsContribution(goal_id=goal.id, amount=Decimal('150.00'), contributed_on=date(2026, 10, 15)),
    ])
    db.session.commit()
    report = analytics.get_financial_forecast(data['user_id'], 'UAH', 1)
    assert report.goal.actual_achievement_date == date(2026, 10, 15)
    for scenario in report.scenarios:
        assert scenario.goal_projection.already_achieved is True
        assert scenario.goal_projection.estimated_goal_month == '2026-10'
        assert scenario.goal_projection.goal_reachable_by_deadline is False


def test_negative_forecast_keeps_deficits(ledger_factory):
    data = ledger_factory([('10.00', '100.00')] * 3)
    _goal(data)
    report = analytics.get_financial_forecast(data['user_id'], 'UAH', 1)
    assert all(item.monthly_net == Decimal('-90.00') for item in report.scenarios)
    assert all(item.points[0].projected_savings == Decimal('-70.00') for item in report.scenarios)


def test_forecast_does_not_commit_pending_transactions(ledger_factory):
    data = ledger_factory()
    account = db.session.get(Account, data['account_id'])
    _record(account, '1000.00', 'income', 9)
    changed = analytics.get_financial_forecast(data['user_id'], 'UAH', 1)
    assert changed.scenarios[1].monthly_income == Decimal('300.00')
    db.session.rollback()
    original = analytics.get_financial_forecast(data['user_id'], 'UAH', 1)
    assert original.scenarios[1].monthly_income == Decimal('200.00')
    assert db.session.get(Account, data['account_id']).balance == Decimal('999999.99')


@pytest.mark.parametrize('overrides', [
    {'user_id': 0}, {'currency': 'UA'}, {'currency': None},
    {'horizon_months': 0}, {'horizon_months': 61}, {'horizon_months': True},
    {'horizon_months': '12'},
])
def test_forecast_validates_arguments(ledger_factory, overrides):
    data = ledger_factory()
    arguments = {'user_id': data['user_id'], 'currency': 'UAH', 'horizon_months': 12}
    arguments.update(overrides)
    with pytest.raises(ValueError):
        analytics.get_financial_forecast(**arguments)


def test_analytics_http_endpoints_and_jwt_scope(client, ledger_factory):
    data = ledger_factory()
    assert client.get('/api/analytics/monthly?year=2026&month=11&currency=UAH').status_code == 401
    assert client.get('/api/analytics/forecast?currency=UAH').status_code == 401
    monthly = client.get('/api/analytics/monthly?year=2026&month=11&currency=UAH', headers=data['headers'])
    assert monthly.status_code == 200
    assert monthly.get_json()['analytics']['income_total'] == '88888.00'
    result = client.get('/api/analytics/forecast?currency=uah', headers=data['headers'])
    assert result.status_code == 200
    assert result.get_json()['forecast']['horizon_months'] == 12
    assert len(result.get_json()['forecast']['scenarios'][0]['points']) == 12
    other_headers = {'Authorization': 'Bearer ' + create_access_token(additional_claims={'auth_complete': True}, identity=str(data['other_id']))}
    other = client.get('/api/analytics/forecast?currency=UAH', headers=other_headers)
    assert other.get_json()['forecast']['status'] == 'insufficient_history'
    for url in (
        '/api/analytics/forecast?currency=UAH&horizon_months=0',
        '/api/analytics/forecast?currency=UAH&horizon_months=61',
        '/api/analytics/forecast?currency=UAH&horizon_months=1.5',
        '/api/analytics/forecast?currency=UAH&user_id=999',
        '/api/analytics/monthly?year=2026&month=13&currency=UAH',
        '/api/analytics/monthly?year=9999&month=12&currency=UAH',
    ):
        assert client.get(url, headers=data['headers']).status_code == 400

    empty = User(is_email_verified=True, email='deleted-forecast@example.com')
    empty.set_password('StrongPassword123')
    db.session.add(empty)
    db.session.commit()
    token = create_access_token(additional_claims={'auth_complete': True}, identity=str(empty.id))
    db.session.delete(empty)
    db.session.commit()
    assert client.get('/api/analytics/forecast?currency=UAH', headers={'Authorization': 'Bearer ' + token}).status_code == 401
