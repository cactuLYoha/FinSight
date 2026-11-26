from datetime import datetime, time, timezone
from decimal import Decimal

from sqlalchemy import select

from app.extensions import db
from app.models.account import Account
from app.models.user import User
from app.models.transaction import Transaction
from app.models.recurring_income import RecurringIncome, RecurringIncomeOccurrence
from app.services.recurring_expense_service import following_month


def today():
    return datetime.now(timezone.utc).date()


def materialize_due(user_id):
    """Caller commits; the shared user lock serializes worker and UI writes."""
    db.session.execute(select(User).where(User.id == user_id).with_for_update()).scalar_one()
    rules = db.session.scalars(select(RecurringIncome).where(
        RecurringIncome.user_id == user_id, RecurringIncome.active.is_(True),
        RecurringIncome.next_due_on <= today(),
    ).order_by(RecurringIncome.id).with_for_update().execution_options(populate_existing=True))
    for rule in rules:
        account = db.session.scalar(select(Account).where(Account.id == rule.account_id)
            .with_for_update().execution_options(populate_existing=True))
        for _ in range(120):
            if rule.next_due_on > today():
                break
            due = rule.next_due_on
            month = due.replace(day=1)
            if db.session.get(RecurringIncomeOccurrence, (rule.id, month)) is None:
                balance = account.balance + rule.amount
                if abs(balance) > Decimal('9999999999999.99'):
                    raise ValueError('Resulting account balance is too large.')
                row = Transaction(account_id=account.id, transaction_type='income',
                    amount=rule.amount, description=rule.description,
                    created_at=datetime.combine(due, time(12), tzinfo=timezone.utc))
                db.session.add(row)
                db.session.flush()
                db.session.add(RecurringIncomeOccurrence(recurring_id=rule.id, month=month, transaction_id=row.id))
                account.balance = balance
            rule.next_due_on = following_month(due, rule.billing_day)
            db.session.flush()
