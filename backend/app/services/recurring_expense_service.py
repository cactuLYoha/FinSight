"""Materialize due monthly expenses, with one occurrence per rule and month."""
from calendar import monthrange
from datetime import date, datetime, time, timezone
from decimal import Decimal

from sqlalchemy import select

from app.extensions import db
from app.models.account import Account
from app.models.user import User
from app.models.transaction import Transaction
from app.models.recurring_expense import RecurringExpense, RecurringExpenseOccurrence


def today():
    return datetime.now(timezone.utc).date()


def following_month(due_on, billing_day):
    year, month = (due_on.year + 1, 1) if due_on.month == 12 else (due_on.year, due_on.month + 1)
    return date(year, month, min(billing_day, monthrange(year, month)[1]))


def materialize_due(user_id):
    """The caller owns commit/rollback. User locks serialize UI and worker runs."""
    db.session.execute(select(User).where(User.id == user_id).with_for_update()).scalar_one()
    rules = db.session.scalars(select(RecurringExpense).where(
        RecurringExpense.user_id == user_id, RecurringExpense.active.is_(True),
        RecurringExpense.next_due_on <= today(),
    ).order_by(RecurringExpense.id).with_for_update().execution_options(populate_existing=True))
    for rule in rules:
        account = db.session.execute(select(Account).where(Account.id == rule.account_id)
            .with_for_update().execution_options(populate_existing=True)).scalar_one()
        # Bound historical catch-up per run; the worker will continue next minute.
        for _ in range(120):
            if rule.next_due_on > today():
                break
            due = rule.next_due_on
            month = due.replace(day=1)
            if db.session.get(RecurringExpenseOccurrence, (rule.id, month)) is None:
                balance = account.balance - rule.amount
                if abs(balance) > Decimal('9999999999999.99'):
                    raise ValueError('Resulting account balance is too large.')
                row = Transaction(account_id=account.id, category_id=rule.category_id,
                    amount=rule.amount, transaction_type='expense', description=rule.description,
                    created_at=datetime.combine(due, time(12), tzinfo=timezone.utc))
                db.session.add(row)
                db.session.flush()
                db.session.add(RecurringExpenseOccurrence(recurring_id=rule.id, month=month, transaction_id=row.id))
                account.balance = balance
            rule.next_due_on = following_month(due, rule.billing_day)
            db.session.flush()
    from app.services.recurring_income_service import materialize_due as materialize_income
    materialize_income(user_id)
