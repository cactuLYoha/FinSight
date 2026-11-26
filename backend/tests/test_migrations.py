from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import sqlalchemy as sa
from flask_migrate import downgrade, upgrade
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.models.user import User


def test_password_column_migration_preserves_data_and_login(migration_app):
    app = migration_app
    migrations = str(Path(__file__).resolve().parents[1] / 'migrations')
    legacy_revision = 'f03a9b8c721d'
    password = 'MigrationPassword123'
    password_hash = generate_password_hash(password)
    timestamp = datetime(2026, 11, 17, tzinfo=timezone.utc)

    upgrade(directory=migrations, revision=legacy_revision)
    metadata = sa.MetaData()
    users = sa.Table('user', metadata, autoload_with=db.engine)
    accounts = sa.Table('account', metadata, autoload_with=db.engine)
    transactions = sa.Table('transaction', metadata, autoload_with=db.engine)
    with db.engine.begin() as connection:
        connection.execute(users.insert(), {
            'id': 1,
            'email': 'migration@example.com',
            'pasword_hash': password_hash,
            'created_at': timestamp,
        })
        connection.execute(accounts.insert(), {
            'id': 1,
            'user_id': 1,
            'name': 'Existing account',
            'account_type': 'bank',
            'currency': 'UAH',
            'balance': Decimal('123.45'),
            'created_at': timestamp,
            'created_by': timestamp,
        })
        connection.execute(transactions.insert(), {
            'id': 1,
            'account_id': 1,
            'amount': Decimal('10.25'),
            'transaction_type': 'expense',
            'description': 'Existing transaction',
            'category': 'Food',
            'created_at': timestamp,
        })
        original_account = dict(connection.execute(sa.select(accounts)).mappings().one())
        original_transaction = dict(connection.execute(sa.select(transactions)).mappings().one())

    for migrate, revision, hash_column in (
        (upgrade, 'a18e2c7d9b04', 'password_hash'),
        (downgrade, legacy_revision, 'pasword_hash'),
        (upgrade, 'a18e2c7d9b04', 'password_hash'),
    ):
        db.session.remove()
        migrate(directory=migrations, revision=revision)
        migrated_users = sa.Table('user', sa.MetaData(), autoload_with=db.engine)
        with db.engine.connect() as connection:
            assert set(migrated_users.c.keys()) == {'id', 'email', hash_column, 'created_at'}
            saved_user = connection.execute(sa.select(migrated_users)).mappings().one()
            assert saved_user['id'] == 1
            assert saved_user['email'] == 'migration@example.com'
            assert saved_user[hash_column] == password_hash
            assert check_password_hash(saved_user[hash_column], password)
            assert dict(connection.execute(sa.select(accounts)).mappings().one()) == original_account
            assert dict(connection.execute(sa.select(transactions)).mappings().one()) == original_transaction
            if connection.dialect.name == 'sqlite':
                assert connection.exec_driver_sql('PRAGMA foreign_keys').scalar_one() == 1
                assert connection.exec_driver_sql('PRAGMA foreign_key_check').all() == []

    db.session.remove()
    upgrade(directory=migrations)
    user = db.session.get(User, 1)
    assert user.password_hash == password_hash
    assert user.check_password(password)
    assert user.is_email_verified is False
