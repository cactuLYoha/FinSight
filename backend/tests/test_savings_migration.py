from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from flask_migrate import downgrade, upgrade
from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models.savings_goal import SavingsContribution, SavingsGoal


MIGRATIONS = str(Path(__file__).resolve().parents[1] / 'migrations')
PREVIOUS = 'b72c41d8e903'
CURRENT = 'c83d51e9f204'


def _snapshot(connection, table):
    return [dict(row) for row in connection.execute(sa.select(table).order_by(table.c.id)).mappings()]


def test_savings_migration_and_rollback_preserve_existing_financial_data(migration_app):
    upgrade(directory=MIGRATIONS, revision=PREVIOUS)
    metadata = sa.MetaData()
    users = sa.Table('user', metadata, autoload_with=db.engine)
    accounts = sa.Table('account', metadata, autoload_with=db.engine)
    transactions = sa.Table('transaction', metadata, autoload_with=db.engine)
    categories = sa.Table('category', metadata, autoload_with=db.engine)
    timestamp = datetime(2026, 11, 17, tzinfo=timezone.utc)
    with db.engine.begin() as connection:
        connection.execute(users.insert(), {
            'id': 1, 'email': 'savings-migration@example.com',
            'password_hash': generate_password_hash('StrongPassword123'), 'created_at': timestamp,
        })
        connection.execute(accounts.insert(), {
            'id': 1, 'user_id': 1, 'name': 'Existing', 'account_type': 'bank',
            'currency': 'UAH', 'balance': Decimal('100.01'),
            'created_at': timestamp, 'created_by': timestamp,
        })
        connection.execute(transactions.insert(), {
            'id': 1, 'account_id': 1, 'amount': Decimal('10.01'),
            'transaction_type': 'income', 'description': 'Existing income',
            'category_id': None, 'created_at': timestamp,
        })
        originals = {table.name: _snapshot(connection, table) for table in (users, accounts, transactions, categories)}

    for index, (migrate, revision) in enumerate((
        (upgrade, CURRENT), (downgrade, PREVIOUS), (upgrade, CURRENT),
    )):
        db.session.remove()
        migrate(directory=MIGRATIONS, revision=revision)
        with db.engine.connect() as connection:
            for table in (users, accounts, transactions, categories):
                assert _snapshot(connection, table) == originals[table.name]
            if revision != CURRENT:
                assert not sa.inspect(connection).has_table('savings_goal')
                assert not sa.inspect(connection).has_table('savings_contribution')
            if connection.dialect.name == 'sqlite':
                assert connection.exec_driver_sql('PRAGMA foreign_key_check').all() == []
        if index == 0:
            goal = SavingsGoal(
                user_id=1, name='Нові накопичення', target_amount=Decimal('250.00'),
                currency='UAH', deadline=date(2027, 2, 15),
            )
            db.session.add(goal)
            db.session.flush()
            # Exercise the historical schema without current ORM-only columns.
            db.session.commit()
            historical = sa.Table('savings_contribution', sa.MetaData(), autoload_with=db.engine)
            with db.engine.begin() as connection:
                connection.execute(historical.insert(), dict(goal_id=goal.id, amount=Decimal('25.50'),
                    contributed_on=date(2026, 11, 17), note='Manual contribution', created_at=timestamp))
                assert connection.scalar(sa.select(historical.c.amount)) == Decimal('25.50')
    db.session.remove()
    upgrade(directory=MIGRATIONS)
    with db.engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), db.metadata) == []
