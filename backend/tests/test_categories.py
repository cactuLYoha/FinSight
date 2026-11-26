from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.account import Account
from app.models.category import Category
from app.models.transaction import Transaction
from app.models.user import User


@pytest.fixture
def account(app):
    user = User(email='categories@example.com')
    user.set_password('StrongPassword123')
    account = Account(name='Daily expenses', account_type='cash', user=user)
    db.session.add(account)
    db.session.commit()
    return account


def test_category_is_shared_between_users(app):
    category = Category(name='Продукти')
    for index in range(2):
        user = User(email=f'category-user-{index}@example.com')
        user.set_password('StrongPassword123')
        account = Account(name='Cash', account_type='cash', user=user)
        db.session.add(Transaction(
            account=account,
            amount=Decimal('20.00'),
            transaction_type='expense',
            description='Groceries',
            category=category,
        ))
    db.session.commit()
    db.session.expunge_all()

    saved_category = db.session.scalars(db.select(Category)).one()
    assert saved_category.name == 'Продукти'
    assert len(saved_category.transactions) == 2
    assert len({transaction.account.user_id for transaction in saved_category.transactions}) == 2
    assert all(transaction.category is saved_category for transaction in saved_category.transactions)


def test_category_names_are_unique(app):
    db.session.add_all([Category(name='Транспорт'), Category(name='Транспорт')])
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


@pytest.mark.parametrize('transaction_type, category_id, allowed', [
    ('expense', None, False),
    ('income', None, True),
    ('expense', 999, False),
    ('income', 999, False),
])
def test_transaction_category_rules(account, transaction_type, category_id, allowed):
    transaction = Transaction(
        account_id=account.id,
        amount=Decimal('10.00'),
        transaction_type=transaction_type,
        description='Category rules',
        category_id=category_id,
    )
    db.session.add(transaction)
    if allowed:
        db.session.commit()
        db.session.refresh(transaction)
        assert transaction.category is None
    else:
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


@pytest.mark.parametrize('transaction_type', ['income', 'expense'])
@pytest.mark.parametrize('load_transactions', [False, True])
def test_referenced_category_cannot_be_deleted(account, transaction_type, load_transactions):
    category = Category(name='Інше')
    transaction = Transaction(
        account=account,
        amount=Decimal('10.00'),
        transaction_type=transaction_type,
        description='Keep this operation',
        category=category,
    )
    db.session.add(transaction)
    db.session.commit()
    category_id, transaction_id = category.id, transaction.id
    db.session.expunge_all()

    category = db.session.get(Category, category_id)
    if load_transactions:
        assert len(category.transactions) == 1
    db.session.delete(category)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

    assert db.session.get(Category, category_id) is not None
    assert db.session.get(Transaction, transaction_id).category_id == category_id


def test_unused_category_can_be_deleted(app):
    category = Category(name='Unused')
    db.session.add(category)
    db.session.commit()
    category_id = category.id

    db.session.delete(category)
    db.session.commit()

    assert db.session.get(Category, category_id) is None
