from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy.exc import DataError, IntegrityError

from app.extensions import db
from app.models.account import Account
from app.models.transaction import Transaction
from app.models.user import User


@pytest.fixture
def saved_account(app):
    user = User(email='integrity@example.com')
    user.set_password('StrongPassword123')
    account = Account(name='Main', account_type='bank', user=user)
    db.session.add(account)
    db.session.commit()
    return account


def test_password_change_survives_reload(saved_account):
    user = saved_account.user
    user_id = user.id
    user.set_password('ReplacementPassword123')
    db.session.commit()
    db.session.expunge_all()

    saved_user = db.session.get(User, user_id)
    assert saved_user.password_hash != 'ReplacementPassword123'
    assert saved_user.check_password('ReplacementPassword123')
    assert not saved_user.check_password('StrongPassword123')
    assert not saved_user.check_password('wrong-password')


def test_duplicate_email_keeps_existing_user_and_allows_recovery(saved_account):
    original_id = saved_account.user_id
    email = saved_account.user.email
    duplicate = User(email=email)
    duplicate.set_password('AnotherPassword123')
    db.session.add(duplicate)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

    assert db.session.get(User, original_id).check_password('StrongPassword123')
    valid_user = User(email='different@example.com')
    valid_user.set_password('AnotherPassword123')
    db.session.add(valid_user)
    db.session.commit()
    assert db.session.get(User, valid_user.id).email == 'different@example.com'


@pytest.mark.parametrize('user_id', [None, 999999])
def test_account_requires_existing_owner(app, user_id):
    db.session.add(Account(name='Invalid owner', account_type='cash', user_id=user_id))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


@pytest.mark.parametrize('account_id', [None, 999999])
def test_transaction_requires_existing_account(app, account_id):
    db.session.add(Transaction(
        account_id=account_id, amount=Decimal('1.00'),
        transaction_type='income', description='Invalid account',
    ))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


@pytest.mark.parametrize('amount, transaction_type', [
    ('0.00', 'income'),
    ('-0.01', 'income'),
    ('1.00', 'transfer'),
    ('1.00', ''),
])
def test_invalid_transaction_rolls_back_without_losing_account(saved_account, amount, transaction_type):
    account_id = saved_account.id
    db.session.add(Transaction(
        account_id=account_id, amount=Decimal(amount),
        transaction_type=transaction_type, description='Invalid transaction',
    ))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

    assert db.session.get(Account, account_id) is not None
    assert db.session.get(Account, account_id).transactions == []
    valid = Transaction(
        account_id=account_id, amount=Decimal('0.01'),
        transaction_type='income', description='Valid after rollback',
    )
    db.session.add(valid)
    db.session.commit()
    assert db.session.get(Transaction, valid.id).amount == Decimal('0.01')


@pytest.mark.parametrize('parent_type', ['user', 'account'])
@pytest.mark.parametrize('load_children', [False, True])
def test_parent_with_financial_records_cannot_be_deleted(saved_account, parent_type, load_children):
    operation = Transaction(
        account=saved_account, amount=Decimal('12.34'),
        transaction_type='income', description='Keep this record',
    )
    db.session.add(operation)
    db.session.commit()
    user_id, account_id, transaction_id = saved_account.user_id, saved_account.id, operation.id
    db.session.expunge_all()
    if parent_type == 'user':
        parent = db.session.get(User, user_id)
        if load_children:
            assert len(parent.accounts) == 1
    else:
        parent = db.session.get(Account, account_id)
        if load_children:
            assert len(parent.transactions) == 1
    db.session.delete(parent)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

    assert db.session.get(User, user_id) is not None
    assert db.session.get(Account, account_id).user_id == user_id
    assert db.session.get(Transaction, transaction_id).account_id == account_id


@pytest.mark.postgresql
@pytest.mark.parametrize('field', ['balance', 'amount'])
def test_postgresql_preserves_maximum_numeric_cents(saved_account, field):
    value = Decimal('9999999999999.99')
    if field == 'balance':
        record = saved_account
    else:
        record = Transaction(
            account=saved_account, amount=Decimal('1.00'),
            transaction_type='income', description='Exact numeric',
        )
        db.session.add(record)
    setattr(record, field, value)
    db.session.commit()
    db.session.refresh(record)
    assert getattr(record, field) == value


@pytest.mark.postgresql
@pytest.mark.parametrize('field', ['balance', 'amount'])
def test_postgresql_rejects_numeric_overflow(saved_account, field):
    if field == 'balance':
        record = saved_account
    else:
        record = Transaction(
            account=saved_account, amount=Decimal('1.00'),
            transaction_type='income', description='Numeric overflow',
        )
        db.session.add(record)
    setattr(record, field, Decimal('10000000000000.00'))
    with pytest.raises(DataError):
        db.session.commit()
    db.session.rollback()


@pytest.mark.postgresql
def test_postgresql_preserves_timestamp_instant(saved_account):
    operation = Transaction(
        account=saved_account, amount=Decimal('1.00'),
        transaction_type='income', description='Offset timestamp',
        created_at=datetime(2026, 12, 1, 1, 0, tzinfo=timezone(timedelta(hours=2))),
    )
    db.session.add(operation)
    db.session.commit()
    db.session.refresh(operation)
    assert operation.created_at.tzinfo is not None
    assert operation.created_at.astimezone(timezone.utc) == datetime(
        2026, 11, 30, 23, 0, tzinfo=timezone.utc,
    )
