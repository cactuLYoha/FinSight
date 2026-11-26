from pathlib import Path
from decimal import Decimal

import sqlalchemy as sa
from flask_migrate import upgrade, downgrade

from app.extensions import db
from app.models.account import Account
from app.models.user import User
from app.models.transaction import Transaction


def test_import_migration_round_trip_preserves_ledger(migration_app):
    directory = str(Path(__file__).resolve().parents[1] / 'migrations')
    upgrade(directory=directory, revision='c41a7ef89206')
    user = User(email='import-migration@example.com'); user.set_password('Password123')
    account = Account(user=user, name='Existing bank', account_type='bank', currency='UAH', balance=Decimal('10.00'))
    db.session.add(Transaction(account=account, amount=Decimal('10.00'), transaction_type='income', description='Existing'))
    db.session.commit()
    for direction, revision in ((upgrade, 'd52b8ea10317'), (downgrade, 'c41a7ef89206'), (upgrade, 'd52b8ea10317')):
        db.session.remove()
        direction(directory=directory, revision=revision)
        tables = sa.inspect(db.engine).get_table_names()
        assert ('statement_import' in tables) == (direction is upgrade)
        assert db.session.query(Transaction).one().amount == Decimal('10.00')
        assert db.session.query(Account).one().balance == Decimal('10.00')
