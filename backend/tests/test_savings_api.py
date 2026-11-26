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
from app.services import savings_service as savings


BASE = '/api/savings/goals'
GOAL = {
    'name': 'Подорож', 'target_amount': '100.00',
    'currency': ' uah ', 'deadline': '2027-02-15',
}


@pytest.fixture
def actors(app, monkeypatch):
    monkeypatch.setattr(savings, 'utc_today', lambda: date(2026, 11, 17))
    users = []
    for email in ('saver@example.com', 'other-saver@example.com'):
        user = User(is_email_verified=True, email=email)
        user.set_password('StrongPassword123')
        db.session.add(user)
        users.append(user)
    db.session.commit()
    return [
        {'id': user.id, 'headers': {'Authorization': 'Bearer ' + create_access_token(additional_claims={'auth_complete': True}, identity=str(user.id))}}
        for user in users
    ]


def create_goal(client, actor, **changes):
    response = client.post(BASE, headers=actor['headers'], json={**GOAL, **changes})
    assert response.status_code == 201, response.get_json()
    return response.get_json()['goal']


def contribute(client, actor, goal_id, amount='10.00', **changes):
    response = client.post(
        f'{BASE}/{goal_id}/contributions', headers=actor['headers'],
        json={'amount': amount, **changes},
    )
    assert response.status_code == 201, response.get_json()
    return response.get_json()['contribution']


@pytest.mark.parametrize('method, path', [
    ('get', '/api/savings/summary?year=2026&month=11&currency=UAH'),
    ('get', BASE), ('post', BASE),
    ('get', BASE + '/1'), ('patch', BASE + '/1'),
    ('get', BASE + '/1/plan'),
    ('get', BASE + '/1/contributions'), ('post', BASE + '/1/contributions'),
    ('patch', BASE + '/1/contributions/1'), ('delete', BASE + '/1/contributions/1'),
    ('post', BASE + '/1/complete'), ('post', BASE + '/1/cancel'),
    ('delete', BASE + '/1'), ('post', BASE + '/1/transfer'), ('post', BASE + '/1/reactivate'),
])
def test_savings_routes_require_jwt(client, method, path):
    assert getattr(client, method)(path).status_code == 401


def test_reactivate_cancelled_goal_with_new_deadline_preserves_money(client, actors, monkeypatch):
    owner = actors[0]
    goal = create_goal(client, owner)
    row = contribute(client, owner, goal['id'], amount='25.00')
    url = f"{BASE}/{goal['id']}"
    client.post(url + '/cancel', headers=owner['headers'])
    account = db.session.get(Account, row['account_id'])
    before = account.balance
    monkeypatch.setattr(savings, 'utc_today', lambda: date(2028, 1, 10))
    result = client.post(url + '/reactivate', headers=owner['headers'], json={'deadline': '2028-06-30'})
    assert result.status_code == 200
    assert result.json['goal']['status'] == 'active'
    assert result.json['goal']['deadline'] == '2028-06-30'
    assert result.json['goal']['saved_amount'] == '25.00'
    assert account.balance == before
    assert client.get(url + '/contributions', headers=owner['headers']).json['contributions'][0]['id'] == row['id']
    plan = client.get(url + '/plan', headers=owner['headers']).json['plan']
    assert plan['overdue'] is False and len(plan['installments']) == 5
    assert sum(Decimal(item['amount']) for item in plan['installments']) == Decimal('75.00')


def test_reactivation_validation_ownership_and_single_active_goal(client, actors):
    owner, other = actors
    goal = create_goal(client, owner)
    url = f"{BASE}/{goal['id']}"
    assert client.post(url + '/reactivate', headers=owner['headers'], json={'deadline': '2027-06-30'}).status_code == 409
    client.post(url + '/cancel', headers=owner['headers'])
    for payload in ({}, {'deadline': '2026-11-20'}, {'deadline': '2027-02-30'}, {'deadline': '2027-06-30', 'amount': 1}):
        assert client.post(url + '/reactivate', headers=owner['headers'], json=payload).status_code == 400
    assert client.post(url + '/reactivate', headers=other['headers'], json={'deadline': '2027-06-30'}).status_code == 404
    active = create_goal(client, owner)
    assert client.post(url + '/reactivate', headers=owner['headers'], json={'deadline': '2027-06-30'}).status_code == 409
    unchanged = client.get(url, headers=owner['headers']).json['goal']
    assert unchanged['status'] == 'cancelled' and unchanged['deadline'] == goal['deadline']
    contribute(client, owner, active['id'], amount='100')
    client.post(f"{BASE}/{active['id']}/complete", headers=owner['headers'])
    assert client.post(f"{BASE}/{active['id']}/reactivate", headers=owner['headers'], json={'deadline': '2027-06-30'}).status_code == 409


def test_empty_goal_deletion_and_ownership(client, actors):
    owner, other = actors
    goal = create_goal(client, owner)
    url = f"{BASE}/{goal['id']}"
    assert client.delete(url, headers=other['headers']).status_code == 404
    row = contribute(client, owner, goal['id'])
    assert client.delete(url, headers=owner['headers']).status_code == 409
    assert client.delete(f"{url}/contributions/{row['id']}", headers=owner['headers']).status_code == 204
    assert client.delete(url, headers=owner['headers']).status_code == 204
    assert client.get(url, headers=owner['headers']).status_code == 404


def test_transfer_to_new_goal_preserves_contributions_and_total(client, actors):
    owner = actors[0]
    source = create_goal(client, owner)
    row = contribute(client, owner, source['id'], amount='12.34', note='Original note', contributed_on='2026-11-01')
    url = f"{BASE}/{source['id']}"
    response = client.post(url + '/transfer', headers=owner['headers'], json={'new_goal': {**GOAL, 'name': 'New goal'}})
    assert response.status_code == 200, response.get_json()
    payload = response.get_json()
    assert payload['source']['saved_amount'] == '0.00'
    assert payload['source']['status'] == 'cancelled'
    assert payload['target']['saved_amount'] == '12.34'
    assert payload['transferred_amount'] == '12.34'
    target_url = f"{BASE}/{payload['target']['id']}"
    moved = client.get(target_url + '/contributions', headers=owner['headers']).get_json()['contributions'][0]
    assert (moved['id'], moved['note'], moved['contributed_on']) == (row['id'], 'Original note', '2026-11-01')
    assert client.post(url + '/transfer', headers=owner['headers'], json={'target_goal_id': payload['target']['id']}).status_code == 409
    assert client.delete(url, headers=owner['headers']).status_code == 204


def test_transfer_checks_currency_ownership_and_rolls_back(client, actors):
    owner, other = actors
    source = create_goal(client, owner)
    contribute(client, owner, source['id'], amount='25.00')
    url = f"{BASE}/{source['id']}"
    assert client.post(url + '/cancel', headers=owner['headers']).status_code == 200
    target = create_goal(client, owner, currency='USD')
    foreign = create_goal(client, other)
    for target_id, status in [(foreign['id'], 404), (target['id'], 409), (source['id'], 400), (True, 400)]:
        assert client.post(url + '/transfer', headers=owner['headers'], json={'target_goal_id': target_id}).status_code == status
    # New target conflicts with the owner's other active goal; cancellation/moves must roll back.
    assert client.post(url + '/transfer', headers=owner['headers'], json={'new_goal': GOAL}).status_code == 409
    assert client.get(url, headers=owner['headers']).get_json()['goal']['saved_amount'] == '25.00'
    client.post(f"{BASE}/{target['id']}/cancel", headers=owner['headers'])
    target = create_goal(client, owner)
    response = client.post(url + '/transfer', headers=owner['headers'], json={'target_goal_id': target['id']})
    assert response.status_code == 200
    assert response.get_json()['target']['saved_amount'] == '25.00'


def test_goal_creation_conflict_recovery_and_history(client, actors):
    owner, other = actors
    goal = create_goal(client, owner)
    assert goal['name'] == 'Подорож'
    assert goal['currency'] == 'UAH'
    assert goal['status'] == 'active'
    assert goal['saved_amount'] == '0.00'
    assert goal['remaining_amount'] == '100.00'
    assert goal['progress_percent'] == '0.00'
    assert not goal['is_achieved']
    assert client.post(BASE, headers=owner['headers'], json=GOAL).status_code == 409
    assert db.session.scalar(db.select(db.func.count()).select_from(SavingsGoal)) == 1

    changed = client.patch(f"{BASE}/{goal['id']}", headers=owner['headers'], json={'name': '  Ноутбук  '})
    assert changed.status_code == 200
    assert changed.get_json()['goal']['name'] == 'Ноутбук'
    assert client.get(BASE, headers=other['headers']).get_json() == {'goals': []}
    assert client.post(f"{BASE}/{goal['id']}/cancel", headers=owner['headers']).status_code == 200
    new_goal = create_goal(client, owner, name='Нова ціль')
    history = client.get(BASE, headers=owner['headers']).get_json()['goals']
    assert [row['id'] for row in history] == [new_goal['id'], goal['id']]
    assert [row['status'] for row in history] == ['active', 'cancelled']


def test_contribution_edit_delete_and_goal_patch(client, actors):
    owner = actors[0]
    goal = create_goal(client, owner)
    item = contribute(client, owner, goal['id'], contributed_on='2026-11-01', note='Початок')
    path = f"{BASE}/{goal['id']}/contributions/{item['id']}"
    changed = client.patch(path, headers=owner['headers'], json={
        'amount': '25.50', 'contributed_on': '2026-11-10', 'note': None,
    })
    assert changed.status_code == 200
    assert changed.get_json()['contribution']['amount'] == '25.50'
    assert changed.get_json()['contribution']['note'] is None
    saved = client.get(f"{BASE}/{goal['id']}", headers=owner['headers']).get_json()['goal']
    assert saved['saved_amount'] == '25.50'
    assert saved['remaining_amount'] == '74.50'
    assert client.patch(f"{BASE}/{goal['id']}", headers=owner['headers'], json={'currency': 'USD'}).status_code == 400

    changed_goal = client.patch(f"{BASE}/{goal['id']}", headers=owner['headers'], json={
        'target_amount': '120.00', 'deadline': '2027-01-07',
    })
    assert changed_goal.status_code == 200
    plan = client.get(f"{BASE}/{goal['id']}/plan", headers=owner['headers']).get_json()['plan']
    assert [row['amount'] for row in plan['installments']] == ['47.25', '47.25']
    assert client.get(f"{BASE}/{goal['id']}/contributions", headers=owner['headers']).get_json()['contributions'][0]['id'] == item['id']
    assert client.delete(path, headers=owner['headers']).status_code == 204
    assert client.get(f"{BASE}/{goal['id']}", headers=owner['headers']).get_json()['goal']['saved_amount'] == '0.00'
    assert client.get(f"{BASE}/{goal['id']}/contributions", headers=owner['headers']).get_json()['contributions'] == []


def test_manual_completion_and_closed_goal_immutability(client, actors):
    owner = actors[0]
    goal = create_goal(client, owner)
    path = f"{BASE}/{goal['id']}"
    assert client.post(path + '/complete', headers=owner['headers']).status_code == 409
    item = contribute(client, owner, goal['id'], amount='110.00')
    saved = client.get(path, headers=owner['headers']).get_json()['goal']
    assert saved['saved_amount'] == '110.00'
    assert saved['progress_percent'] == '100.00'
    assert saved['remaining_amount'] == '0.00'
    assert saved['status'] == 'active'
    plan = client.get(path + '/plan', headers=owner['headers']).get_json()['plan']
    assert plan['installments'] == []
    assert plan['is_feasible'] is True
    assert client.post(path + '/complete', headers=owner['headers']).get_json()['goal']['status'] == 'completed'
    for method, suffix, body in [
        ('patch', '', {'name': 'Changed'}),
        ('post', '/contributions', {'amount': '1.00'}),
        ('patch', f"/contributions/{item['id']}", {'amount': '1.00'}),
        ('delete', f"/contributions/{item['id']}", None),
        ('post', '/cancel', None),
    ]:
        assert getattr(client, method)(path + suffix, headers=owner['headers'], json=body).status_code == 409
    assert db.session.get(SavingsContribution, item['id']).amount == Decimal('110.00')
    create_goal(client, owner, name='Наступна ціль')


def test_other_users_cannot_access_goals_or_contributions(client, actors):
    owner, other = actors
    goal = create_goal(client, owner)
    item = contribute(client, owner, goal['id'])
    path = f"{BASE}/{goal['id']}"
    for method, suffix, body in [
        ('get', '', None), ('patch', '', {'name': 'Changed'}), ('get', '/plan', None),
        ('get', '/contributions', None), ('post', '/contributions', {'amount': '1.00'}),
        ('patch', f"/contributions/{item['id']}", {'amount': '1.00'}),
        ('delete', f"/contributions/{item['id']}", None),
        ('post', '/complete', None), ('post', '/cancel', None),
    ]:
        assert getattr(client, method)(path + suffix, headers=other['headers'], json=body).status_code == 404
    other_goal = create_goal(client, other)
    assert client.patch(
        f"{BASE}/{other_goal['id']}/contributions/{item['id']}",
        headers=other['headers'], json={'amount': '50.00'},
    ).status_code == 404
    assert db.session.get(SavingsContribution, item['id']).amount == Decimal('10.00')


@pytest.mark.parametrize('changes', [
    {'name': ' '}, {'target_amount': '0'}, {'target_amount': '-1'},
    {'target_amount': '1.001'}, {'target_amount': 'NaN'}, {'target_amount': 'Infinity'},
    {'target_amount': True}, {'target_amount': '10000000000000.00'},
    {'currency': 'UA'}, {'currency': 'U1D'}, {'deadline': '2026-11-30'},
    {'deadline': 'not-a-date'}, {'status': 'completed'}, {'user_id': 999},
])
def test_goal_input_validation_is_atomic(client, actors, changes):
    response = client.post(BASE, headers=actors[0]['headers'], json={**GOAL, **changes})
    assert response.status_code == 400
    assert db.session.scalar(db.select(db.func.count()).select_from(SavingsGoal)) == 0


@pytest.mark.parametrize('changes', [
    {'amount': '0'}, {'amount': '-1'}, {'amount': '1.001'}, {'amount': 'NaN'},
    {'amount': 'Infinity'}, {'amount': True}, {'contributed_on': '2026-11-18'},
    {'note': 'x' * 501}, {'goal_id': 999},
])
def test_invalid_contribution_does_not_change_progress(client, actors, changes):
    owner = actors[0]
    goal = create_goal(client, owner)
    response = client.post(
        f"{BASE}/{goal['id']}/contributions", headers=owner['headers'],
        json={'amount': '10.00', **changes},
    )
    assert response.status_code == 400
    assert client.get(f"{BASE}/{goal['id']}", headers=owner['headers']).get_json()['goal']['saved_amount'] == '0.00'
    contribute(client, owner, goal['id'], amount='0.01')


def test_invalid_json_empty_patch_missing_resources_and_deleted_user(client, actors):
    owner, other = actors
    assert client.post(BASE, headers=owner['headers'], data='{', content_type='application/json').status_code == 400
    assert client.post(BASE, headers=owner['headers'], json=[]).status_code == 400
    goal = create_goal(client, owner)
    assert client.patch(f"{BASE}/{goal['id']}", headers=owner['headers'], json={}).status_code == 400
    assert client.get(BASE + '/999999', headers=owner['headers']).status_code == 404
    db.session.delete(db.session.get(User, other['id']))
    db.session.commit()
    assert client.get(BASE, headers=other['headers']).status_code == 401


@pytest.mark.parametrize('income, expense, net, available, rate', [
    ('100.00', '30.00', '70.00', '70.00', '70.00'),
    ('100.00', '150.00', '-50.00', '0.00', '-50.00'),
    ('0.00', '50.00', '-50.00', '0.00', None),
])
def test_savings_summary_uses_analytics_without_counting_contributions(
    client, actors, income, expense, net, available, rate,
):
    owner = actors[0]
    account = Account(name='Main', account_type='bank', user_id=owner['id'], currency='UAH', balance=Decimal('5000.00'))
    db.session.add(account)
    day = datetime(2026, 11, 1, tzinfo=timezone.utc)
    if Decimal(income):
        db.session.add(Transaction(account=account, amount=Decimal(income), transaction_type='income', description='Income', created_at=day))
    db.session.add(Transaction(
        account=account, amount=Decimal(expense), transaction_type='expense',
        description='Expense', category=Category(name='Продукти'), created_at=day,
    ))
    db.session.commit()
    url = '/api/savings/summary?year=2026&month=11&currency=uah'
    response = client.get(url, headers=owner['headers'])
    assert response.status_code == 200
    before = response.get_json()['summary']
    assert before['net_savings'] == net
    assert before['available_to_save'] == available
    assert before['savings_rate_percent'] == rate
    goal = create_goal(client, owner)
    contribute(client, owner, goal['id'], amount='20.00')
    assert client.get(url, headers=owner['headers']).get_json()['summary'] == before
    assert db.session.get(Account, account.id).balance == Decimal('5000.00')
    assert client.get(url + '&user_id=999', headers=owner['headers']).status_code == 400
    assert client.get('/api/savings/summary?year=2026&month=13&currency=UAH', headers=owner['headers']).status_code == 400


@pytest.mark.postgresql
def test_concurrent_goal_creations_leave_only_one_active(app, actors):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    owner = actors[0]
    db.session.remove()
    barrier = Barrier(2)
    def submit():
        client = app.test_client()
        barrier.wait(timeout=10)
        return client.post(BASE, headers=owner['headers'], json=GOAL).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: submit(), range(2)))
    assert sorted(responses) == [201, 409]
    db.session.remove()
    assert db.session.scalar(db.select(db.func.count()).select_from(SavingsGoal).where(
        SavingsGoal.user_id == owner['id'], SavingsGoal.status == 'active',
    )) == 1
