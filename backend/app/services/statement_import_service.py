"""Validate and atomically import parsed statements into the existing ledger."""
from datetime import date, datetime, time, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.account import Account
from app.models.category import Category
from app.models.statement_import import StatementImport
from app.models.transaction import Transaction
from app.models.user import User
from app.services.statement_reader import analyze_statement, StatementError

LIMIT = Decimal('9999999999999.99')


def _owned(user_id, account_id, lock=False):
    query = select(Account).where(Account.id == account_id, Account.user_id == user_id)
    account = db.session.scalar(query.with_for_update() if lock else query)
    if account is None:
        raise StatementError('Account not found.', 404)
    return account


def _receipt(account_id, file_hash):
    return db.session.scalar(select(StatementImport).where(
        StatementImport.account_id == account_id, StatementImport.file_hash == file_hash))


def _summary(receipt, duplicate):
    return {'import_id': receipt.id, 'imported_count': 0 if duplicate else receipt.row_count,
            'duplicate': duplicate}


def _normalize(rows, currency):
    if not rows:
        raise StatementError('No transactions were found in the statement.')
    normalized = []
    for index, row in enumerate(rows, 1):
        try:
            amount = Decimal(str(row.get('amount')))
            if not amount.is_finite() or not amount or abs(amount) > LIMIT or amount != amount.quantize(Decimal('.01')):
                raise ValueError('Invalid amount')
            if (row.get('currency') or '').strip().upper() != currency:
                raise ValueError('Currency must match the selected account')
            day = date.fromisoformat(row.get('booking_date') or row.get('value_date') or '')
            if day > datetime.now(timezone.utc).date():
                raise ValueError('Future transaction date')
            description = (row.get('description') or '').strip()
            if not description or len(description) > 100:
                raise ValueError('Description must contain 1–100 characters')
        except (InvalidOperation, ValueError, TypeError, AttributeError) as error:
            raise StatementError(f'Transaction {index}: invalid amount, currency, date or description. Nothing was imported.') from error
        normalized.append(dict(amount=abs(amount), transaction_type='income' if amount > 0 else 'expense',
                               description=description, created_at=datetime.combine(day, time(12), tzinfo=timezone.utc)))
    return normalized


def _uncategorized():
    name = 'Без категорії'
    category = db.session.scalar(select(Category).where(Category.name == name))
    if category is None:
        # Different users can reach this at once; the unique category name is shared.
        try:
            with db.session.begin_nested():
                category = Category(name=name)
                db.session.add(category)
                db.session.flush()
        except IntegrityError:
            category = db.session.scalar(select(Category).where(Category.name == name))
    return category


def import_statement(path, *, user_id, account_id, model, api_base):
    """Caller commits or rolls back the entire import; parsing holds no row locks."""
    account = _owned(user_id, account_id)
    file_hash = sha256(path.read_bytes()).hexdigest()
    receipt = _receipt(account.id, file_hash)
    if receipt:
        return _summary(receipt, True)
    analysis = analyze_statement(path, model=model, api_base=api_base)
    status = (analysis.get('verification') or {}).get('status')
    if status in ('discrepancy', 'failed'):
        raise StatementError('Statement balance verification failed. Nothing was imported.')
    rows = _normalize(analysis['transactions'], account.currency)
    # Same user-lock order as manual income/expense routes prevents lost balances.
    db.session.execute(select(User).where(User.id == user_id).with_for_update()).scalar_one()
    account = _owned(user_id, account_id, lock=True)
    receipt = _receipt(account.id, file_hash)
    if receipt:
        return _summary(receipt, True)
    # Refresh attributes read before a concurrent account write while parsing.
    db.session.refresh(account)
    delta = sum((row['amount'] if row['transaction_type'] == 'income' else -row['amount'] for row in rows), Decimal('0.00'))
    if abs(account.balance + delta) > LIMIT:
        raise StatementError('Import would exceed the account balance limit.')
    category = _uncategorized() if any(row['transaction_type'] == 'expense' for row in rows) else None
    for row in rows:
        db.session.add(Transaction(account_id=account.id,
                                   category_id=category.id if row['transaction_type'] == 'expense' else None, **row))
    account.balance += delta
    receipt = StatementImport(account_id=account.id, file_hash=file_hash, row_count=len(rows))
    db.session.add(receipt)
    db.session.flush()
    return _summary(receipt, False)
