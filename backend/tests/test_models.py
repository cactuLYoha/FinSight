import datetime
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.extensions import db
from app.models import account as account_model
from app.models.account import Account
from app.models.category import Category
from app.models.transaction import Transaction
from app.models.user import User


def test_user_account_transaction_relationships(app):
    user = User(email='relationships@example.com')
    user.set_password('StrongPassword123')
    user.accounts = [
        Account(
            name='Cash',
            account_type='cash',
            transactions=[
                Transaction(
                    amount=Decimal('12.34'),
                    transaction_type='expense',
                    description='Groceries',
                    category=Category(name='Продукти'),
                ),
            ],
        ),
        Account(name='Bank', account_type='bank'),
    ]
    db.session.add(user)
    db.session.commit()
    user_id = user.id
    db.session.expunge_all()

    saved_user = db.session.get(User, user_id)
    accounts = {account.name: account for account in saved_user.accounts}
    assert set(accounts) == {'Cash', 'Bank'}
    assert accounts['Cash'].user is saved_user
    assert accounts['Bank'].transactions == []

    transaction, = accounts['Cash'].transactions
    assert transaction.account is accounts['Cash']
    assert transaction.account_id == accounts['Cash'].id
    assert transaction.amount == Decimal('12.34')
    assert transaction.category.name == 'Продукти'
    assert transaction in transaction.category.transactions


def test_account_timestamps_use_each_insertion_time(app, monkeypatch):
    first_time = datetime(2026, 11, 17, 10, 0, tzinfo=timezone.utc)
    second_time = first_time + timedelta(hours=1)

    class Clock:
        current = first_time

        @classmethod
        def now(cls, tz):
            return cls.current.astimezone(tz)

    monkeypatch.setattr(account_model, 'datetime', Clock)
    user = User(email='timestamps@example.com')
    user.set_password('StrongPassword123')
    first = Account(name='First', account_type='cash', user=user)
    db.session.add(first)
    db.session.flush()
    Clock.current = second_time
    second = Account(name='Second', account_type='bank', user=user)
    db.session.add(second)
    db.session.commit()

    # SQLite returns naive datetimes; these stored values represent UTC.
    assert first.created_at.replace(tzinfo=timezone.utc) == first_time
    assert first.created_by.replace(tzinfo=timezone.utc) == first_time
    assert second.created_at.replace(tzinfo=timezone.utc) == second_time
    assert second.created_by.replace(tzinfo=timezone.utc) == second_time
