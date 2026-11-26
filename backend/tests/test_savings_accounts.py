from datetime import datetime, timezone
from decimal import Decimal

from app.extensions import db
from app.models.account import Account
from app.models.transaction import Transaction
from tests.test_savings_api import actors, create_goal, contribute, BASE


def funded(owner, currency='UAH'):
    account = Account(user_id=owner['id'], name='Source', currency=currency, account_type='bank', balance=1000)
    db.session.add(account); db.session.flush()
    db.session.add(Transaction(account_id=account.id, transaction_type='income', amount=1000,
        description='Funding', created_at=datetime(2026, 11, 1, tzinfo=timezone.utc)))
    db.session.commit()
    return account


def test_contribution_edit_move_delete_and_displayed_balance(client, actors):
    owner = actors[0]
    first, second = funded(owner), funded(owner)
    goal = create_goal(client, owner)
    row = contribute(client, owner, goal['id'], amount='250', account_id=first.id)
    url = f"{BASE}/{goal['id']}/contributions/{row['id']}"
    assert first.balance == Decimal('750.00')
    accounts = client.get('/api/accounts', headers=owner['headers']).json['accounts']
    assert accounts[0]['balance'] == '750.00'
    assert accounts[0]['savings_total'] == '250.00'
    assert client.patch(url, headers=owner['headers'], json={'amount': '200'}).status_code == 200
    assert first.balance == Decimal('800.00')
    assert client.patch(url, headers=owner['headers'], json={'account_id': second.id}).status_code == 200
    assert first.balance == Decimal('1000.00') and second.balance == Decimal('800.00')
    assert client.delete(url, headers=owner['headers']).status_code == 204
    assert second.balance == Decimal('1000.00')


def test_transfer_between_goals_does_not_debit_twice_and_rejects_other_sources(client, actors):
    owner, other = actors
    account, foreign, usd = funded(owner), funded(other), funded(owner, 'USD')
    goal = create_goal(client, owner)
    for invalid in (foreign, usd):
        assert client.post(f"{BASE}/{goal['id']}/contributions", headers=owner['headers'], json={'amount': '10', 'account_id': invalid.id}).status_code == 400
        assert invalid.balance == Decimal('1000.00')
    contribute(client, owner, goal['id'], amount='100', account_id=account.id)
    response = client.post(f"{BASE}/{goal['id']}/transfer", headers=owner['headers'], json={'new_goal': {'name': 'New', 'target_amount': '500', 'currency': 'UAH', 'deadline': '2027-02-15'}})
    assert response.status_code == 200
    assert account.balance == Decimal('900.00')
    moved = client.get(f"{BASE}/{response.json['target']['id']}/contributions", headers=owner['headers']).json['contributions'][0]
    assert moved['account_id'] == account.id
