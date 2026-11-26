from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from flask_migrate import downgrade, upgrade
from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models.category import Category


MIGRATIONS = str(Path(__file__).resolve().parents[1] / 'migrations')
PREVIOUS_REVISION = 'a18e2c7d9b04'
CATEGORY_REVISION = 'b72c41d8e903'
EXPECTED_CATEGORIES = {
    'Продукти', 'Кафе та ресторани', 'Житло та комунальні послуги',
    'Побут і товари для дому', 'Транспорт', 'Здоров’я', 'Особистий догляд',
    'Одяг та взуття', 'Зв’язок та інтернет', 'Підписки та цифрові сервіси',
    'Освіта', 'Дозвілля та спорт', 'Подорожі', 'Сім’я та діти',
    'Домашні тварини', 'Подарунки та благодійність',
    'Податки та банківські комісії', 'Інше',
}


def _snapshot(connection, table):
    return {
        row['id']: dict(row)
        for row in connection.execute(sa.select(table)).mappings()
    }


def test_empty_database_gets_catalog_and_matching_schema(migration_app):
    upgrade(directory=MIGRATIONS, revision='head')

    categories = db.session.scalars(db.select(Category)).all()
    assert len(categories) == 18
    assert {category.name for category in categories} == EXPECTED_CATEGORIES
    db.session.remove()
    with db.engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), db.metadata) == []
        if connection.dialect.name == 'sqlite':
            assert connection.exec_driver_sql('PRAGMA foreign_key_check').all() == []


def test_category_migration_preserves_data_through_roundtrip(migration_app):
    upgrade(directory=MIGRATIONS, revision=PREVIOUS_REVISION)
    metadata = sa.MetaData()
    users = sa.Table('user', metadata, autoload_with=db.engine)
    accounts = sa.Table('account', metadata, autoload_with=db.engine)
    transactions = sa.Table('transaction', metadata, autoload_with=db.engine)
    timestamp = datetime(2026, 11, 17, tzinfo=timezone.utc)
    labels = {
        1: 'Продукти',
        2: 'Стара категорія',
        3: 'Зарплата',
        4: '',
        5: '   ',
        6: 'Стара категорія',
        7: '  Рідкісний підпис  ',
    }
    with db.engine.begin() as connection:
        connection.execute(users.insert(), {
            'id': 1,
            'email': 'legacy-category@example.com',
            'password_hash': generate_password_hash('LegacyPassword123'),
            'created_at': timestamp,
        })
        connection.execute(accounts.insert(), {
            'id': 1, 'user_id': 1, 'name': 'Existing account',
            'account_type': 'bank', 'currency': 'UAH',
            'balance': Decimal('500.00'),
            'created_at': timestamp, 'created_by': timestamp,
        })
        connection.execute(transactions.insert(), [
            {
                'id': transaction_id, 'account_id': 1,
                'amount': Decimal('10.25') * transaction_id,
                'transaction_type': 'income' if transaction_id == 3 else 'expense',
                'description': f'Legacy transaction {transaction_id}',
                'category': label, 'created_at': timestamp,
            }
            for transaction_id, label in labels.items()
        ])
        original_users = _snapshot(connection, users)
        original_accounts = _snapshot(connection, accounts)
        expected_transactions = _snapshot(connection, transactions)
        for row in expected_transactions.values():
            if not row['category'].strip():
                row['category'] = 'Інше'

    for step, (migrate, revision) in enumerate((
        (upgrade, CATEGORY_REVISION),
        (downgrade, PREVIOUS_REVISION),
        (upgrade, CATEGORY_REVISION),
    )):
        db.session.remove()
        migrate(directory=MIGRATIONS, revision=revision)
        current_transactions = sa.Table('transaction', sa.MetaData(), autoload_with=db.engine)

        if step == 0:
            # A new income may have no category; downgrade must restore a non-null label.
            with db.engine.begin() as connection:
                connection.execute(current_transactions.insert(), {
                    'id': 8, 'account_id': 1, 'amount': Decimal('100.00'),
                    'transaction_type': 'income', 'description': 'New uncategorized income',
                    'category_id': None, 'created_at': timestamp,
                })
                saved_income = dict(connection.execute(
                    sa.select(current_transactions).where(current_transactions.c.id == 8)
                ).mappings().one())
                assert saved_income.pop('category_id') is None
                saved_income['category'] = 'Інше'
                expected_transactions[8] = saved_income

        with db.engine.connect() as connection:
            assert _snapshot(connection, users) == original_users
            assert _snapshot(connection, accounts) == original_accounts
            if revision == CATEGORY_REVISION:
                assert 'category' not in current_transactions.c
                categories = sa.Table('category', sa.MetaData(), autoload_with=connection)
                names = connection.execute(sa.select(categories.c.name)).scalars().all()
                assert len(names) == len(set(names))
                assert set(names) == EXPECTED_CATEGORIES | {
                    'Стара категорія', 'Зарплата', '  Рідкісний підпис  ',
                }
                statement = sa.select(
                    *[column for column in current_transactions.c if column.name != 'category_id'],
                    sa.func.coalesce(categories.c.name, 'Інше').label('category'),
                ).select_from(current_transactions.outerjoin(
                    categories, current_transactions.c.category_id == categories.c.id
                ))
                saved_transactions = {
                    row['id']: dict(row)
                    for row in connection.execute(statement).mappings()
                }
            else:
                assert not sa.inspect(connection).has_table('category')
                saved_transactions = _snapshot(connection, current_transactions)

            assert saved_transactions == expected_transactions
            if connection.dialect.name == 'sqlite':
                assert connection.exec_driver_sql('PRAGMA foreign_keys').scalar_one() == 1
                assert connection.exec_driver_sql('PRAGMA foreign_key_check').all() == []
