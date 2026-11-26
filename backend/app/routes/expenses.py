from datetime import datetime, time, timezone
from decimal import Decimal

from flask import Blueprint, jsonify, request
from marshmallow import Schema, fields, validate, ValidationError
from sqlalchemy import select, func

from app.auth_security import check_session_origin
from app.extensions import db
from app.models.account import Account
from app.models.category import Category
from app.models.transaction import Transaction
from app.models.user import User
from app.models.recurring_expense import RecurringExpense, RecurringExpenseOccurrence
from app.services.recurring_expense_service import materialize_due, following_month
from app.services import recurring_expense_service as recurring_service
from app.routes.auth_helpers import authenticated
from app.schemas.analytics_schema import MonthlyAnalyticsQuerySchema
from app.schemas.savings_schema import Currency, Money
from app.services.analytics_service import _month_scope

expenses_bp = Blueprint('expenses', __name__)


class ExpenseSchema(Schema):
    recurring = fields.Boolean(load_default=False)
    account_id = fields.Integer(allow_none=True, load_default=None, strict=True, validate=validate.Range(min=1))
    category_id = fields.Integer(required=True, strict=True, validate=validate.Range(min=1))
    currency = Currency(required=True)
    amount = Money(required=True)
    date = fields.Date(required=True)
    description = fields.String(required=True, validate=validate.Length(min=1, max=100))


class ExpenseQuery(MonthlyAnalyticsQuerySchema):
    page = fields.Integer(load_default=1, validate=validate.Range(min=1, max=1000000))


class ExpensePatchSchema(Schema):
    account_id = fields.Integer(strict=True, validate=validate.Range(min=1))
    category_id = fields.Integer(strict=True, validate=validate.Range(min=1))
    amount = Money()
    date = fields.Date()
    description = fields.String(validate=validate.Length(min=1, max=100))


@expenses_bp.after_request
def no_cache(response):
    response.headers['Cache-Control'] = 'no-store'
    return response


@expenses_bp.errorhandler(ValidationError)
def invalid(error):
    db.session.rollback()
    return jsonify(message=error.messages), 400


def expense_dict(row):
    timestamp = row.created_at
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return dict(id=row.id, amount=str(row.amount), description=row.description,
                date=timestamp.astimezone(timezone.utc).date().isoformat(), category=row.category.name,
                account=row.account.name, account_id=row.account_id, category_id=row.category_id,
                recurring_active=bool(row.recurring_occurrence and row.recurring_occurrence.rule.active),
                recurring_id=row.recurring_occurrence.recurring_id if row.recurring_occurrence else None)


def recurring_dict(rule):
    return dict(id=rule.id, description=rule.description, amount=str(rule.amount),
                category=rule.category.name, account=rule.account.name, billing_day=rule.billing_day,
                starts_on=rule.starts_on.isoformat(), next_due_on=rule.next_due_on.isoformat())


def sync_recurring(user_id):
    try:
        materialize_due(user_id)
        db.session.commit()
    except ValueError as error:
        raise ValidationError(str(error)) from None


@expenses_bp.get('')
@authenticated
def list_expenses(user_id):
    data = ExpenseQuery().load(request.args.to_dict())
    try:
        scope = _month_scope(user_id, data['year'], data['month'], data['currency'])
    except ValueError as error:
        raise ValidationError(str(error)) from None
    sync_recurring(user_id)
    query = select(Transaction).join(Account).where(
        Account.user_id == user_id, Account.currency == scope.currency,
        Transaction.transaction_type == 'expense',
        Transaction.created_at >= scope.start, Transaction.created_at < scope.end,
    )
    total = db.session.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.session.scalars(query.order_by(Transaction.created_at.desc(), Transaction.id.desc())
                              .offset((data['page'] - 1) * 50).limit(50))
    accounts = db.session.scalars(select(Account).where(Account.user_id == user_id, Account.currency == scope.currency).order_by(Account.id))
    categories = db.session.scalars(select(Category).order_by(Category.name))
    recurring = db.session.scalars(select(RecurringExpense).join(Account).where(
        RecurringExpense.user_id == user_id, RecurringExpense.active.is_(True), Account.currency == scope.currency,
    ).order_by(RecurringExpense.billing_day, RecurringExpense.id))
    return jsonify(expenses=[expense_dict(row) for row in rows], total=total, page=data['page'],
                   recurring_expenses=[recurring_dict(rule) for rule in recurring],
                   accounts=[dict(id=row.id, name=row.name) for row in accounts],
                   categories=[dict(id=row.id, name=row.name) for row in categories])


@expenses_bp.post('')
@authenticated
def add_expense(user_id):
    denied = check_session_origin()
    if denied is not None:
        return denied
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ValidationError('Expected an object.')
    data = ExpenseSchema().load(payload)
    if 'recurring' in payload and not isinstance(payload['recurring'], bool):
        raise ValidationError({'recurring': ['A boolean is required.']})
    description = data['description'].strip()
    if not description:
        raise ValidationError({'description': ['Description is required.']})
    # Serialize automatic cash-account creation and balance updates for this user.
    db.session.execute(select(User).where(User.id == user_id).with_for_update()).scalar_one()
    category = db.session.get(Category, data['category_id'])
    if category is None:
        raise ValidationError({'category_id': ['Category not found.']})
    if data['account_id'] is not None:
        account = db.session.scalar(select(Account).where(Account.id == data['account_id'], Account.user_id == user_id).with_for_update())
        if account is None or account.currency != data['currency']:
            raise ValidationError({'account_id': ['Account not found in this currency.']})
    else:
        account = db.session.scalar(select(Account).where(Account.user_id == user_id, Account.currency == data['currency'], Account.name == 'Ручний облік', Account.account_type == 'cash').with_for_update())
        if account is None:
            account = Account(user_id=user_id, name='Ручний облік', account_type='cash', currency=data['currency'], balance=0)
            db.session.add(account)
            db.session.flush()
    if data['recurring']:
        rule = RecurringExpense(user_id=user_id, account_id=account.id, category_id=category.id,
            amount=data['amount'], description=description, billing_day=data['date'].day,
            starts_on=data['date'], next_due_on=data['date'])
        db.session.add(rule)
        db.session.flush()
        sync_recurring(user_id)
        return jsonify(recurring_expense=recurring_dict(rule)), 201
    row = Transaction(account_id=account.id, category_id=category.id, amount=data['amount'],
                      transaction_type='expense', description=description,
                      created_at=datetime.combine(data['date'], time(12), tzinfo=timezone.utc))
    new_balance = account.balance - data['amount']
    if abs(new_balance) > Decimal('9999999999999.99'):
        raise ValidationError({'amount': ['Resulting balance is too large.']})
    account.balance = new_balance
    db.session.add(row)
    db.session.commit()
    return jsonify(expense=expense_dict(row)), 201


@expenses_bp.patch('/<int:expense_id>')
@authenticated
def update_expense(user_id, expense_id):
    denied = check_session_origin()
    if denied is not None:
        return denied
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ValidationError('Expected an object.')
    data = ExpensePatchSchema().load(payload)
    if not data:
        raise ValidationError('At least one editable field is required.')
    if 'description' in data:
        data['description'] = data['description'].strip()
        if not data['description']:
            raise ValidationError({'description': ['Description is required.']})
    # Share the same user lock as creation and the recurring worker.
    db.session.execute(select(User).where(User.id == user_id).with_for_update()).scalar_one()
    row = db.session.scalar(select(Transaction).join(Account).where(
        Transaction.id == expense_id, Account.user_id == user_id,
        Transaction.transaction_type == 'expense',
    ))
    if row is None:
        return jsonify(message='Expense not found'), 404
    target_id = data.get('account_id', row.account_id)
    accounts = {account.id: account for account in db.session.scalars(select(Account).where(
        Account.user_id == user_id, Account.id.in_(sorted({row.account_id, target_id})),
    ).order_by(Account.id).with_for_update().execution_options(populate_existing=True))}
    original, target = accounts[row.account_id], accounts.get(target_id)
    if target is None or target.currency != original.currency:
        raise ValidationError({'account_id': ['Account not found in this currency.']})
    category = db.session.get(Category, data.get('category_id', row.category_id))
    if category is None:
        raise ValidationError({'category_id': ['Category not found.']})
    amount = data.get('amount', row.amount)
    balances = {key: account.balance for key, account in accounts.items()}
    balances[original.id] += row.amount
    balances[target.id] -= amount
    if any(abs(balance) > Decimal('9999999999999.99') for balance in balances.values()):
        raise ValidationError({'amount': ['Resulting balance is too large.']})
    for key, balance in balances.items():
        accounts[key].balance = balance
    row.amount = amount
    row.account = target
    row.category = category
    if 'description' in data:
        row.description = data['description']
    if 'date' in data:
        row.created_at = datetime.combine(data['date'], time(12), tzinfo=timezone.utc)
    db.session.commit()
    return jsonify(expense=expense_dict(row))


@expenses_bp.delete('/<int:expense_id>')
@authenticated
def delete_expense(user_id, expense_id):
    denied = check_session_origin()
    if denied is not None:
        return denied
    db.session.execute(select(User).where(User.id == user_id).with_for_update()).scalar_one()
    row = db.session.scalar(select(Transaction).join(Account).where(
        Transaction.id == expense_id, Account.user_id == user_id,
        Transaction.transaction_type == 'expense',
    ))
    if row is None:
        return jsonify(message='Expense not found'), 404
    account = db.session.scalar(select(Account).where(Account.id == row.account_id)
        .with_for_update().execution_options(populate_existing=True))
    balance = account.balance + row.amount
    if abs(balance) > Decimal('9999999999999.99'):
        raise ValidationError({'amount': ['Resulting balance is too large.']})
    # The rule's next_due_on already points past this occurrence; future repeats
    # stay active while this particular charge is removed permanently.
    occurrence = row.recurring_occurrence
    if occurrence is not None:
        db.session.delete(occurrence)
        db.session.flush()
    account.balance = balance
    db.session.delete(row)
    db.session.commit()
    return '', 204


@expenses_bp.post('/<int:expense_id>/repeat')
@authenticated
def repeat_expense(user_id, expense_id):
    denied = check_session_origin()
    if denied is not None:
        return denied
    db.session.execute(select(User).where(User.id == user_id).with_for_update()).scalar_one()
    row = db.session.scalar(select(Transaction).join(Account).where(
        Transaction.id == expense_id, Account.user_id == user_id, Transaction.transaction_type == 'expense',
    ))
    if row is None:
        return jsonify(message='Expense not found'), 404
    if row.recurring_occurrence and row.recurring_occurrence.rule.active:
        return jsonify(message='Expense is already recurring'), 409
    timestamp = row.created_at.replace(tzinfo=timezone.utc) if row.created_at.tzinfo is None else row.created_at
    date = timestamp.astimezone(timezone.utc).date()
    if row.recurring_occurrence:
        rule = row.recurring_occurrence.rule
        rule.active = True
        rule.next_due_on = following_month(max(date, recurring_service.today()), rule.billing_day)
        db.session.commit()
        return jsonify(recurring_expense=recurring_dict(rule)), 201
    rule = RecurringExpense(user_id=user_id, account_id=row.account_id, category_id=row.category_id,
        amount=row.amount, description=row.description, billing_day=date.day, starts_on=date,
        next_due_on=following_month(max(date, recurring_service.today()), date.day))
    db.session.add(rule)
    db.session.flush()
    db.session.add(RecurringExpenseOccurrence(recurring_id=rule.id, month=date.replace(day=1), transaction_id=row.id))
    sync_recurring(user_id)
    return jsonify(recurring_expense=recurring_dict(rule)), 201


@expenses_bp.delete('/recurring/<int:rule_id>')
@authenticated
def stop_recurring(user_id, rule_id):
    denied = check_session_origin()
    if denied is not None:
        return denied
    db.session.execute(select(User).where(User.id == user_id).with_for_update()).scalar_one()
    rule = db.session.scalar(select(RecurringExpense).where(RecurringExpense.id == rule_id, RecurringExpense.user_id == user_id).with_for_update())
    if rule is None:
        return jsonify(message='Recurring expense not found'), 404
    rule.active = False
    db.session.commit()
    return '', 204
