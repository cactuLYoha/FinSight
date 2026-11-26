from datetime import datetime, time, timezone
from decimal import Decimal

from flask import Blueprint, jsonify, request
from marshmallow import Schema, fields, validate, ValidationError
from sqlalchemy import select, func

from app.auth_security import check_session_origin
from app.extensions import db
from app.models.account import Account
from app.models.transaction import Transaction
from app.models.user import User
from app.models.savings_goal import SavingsContribution
from app.models.recurring_income import RecurringIncome, RecurringIncomeOccurrence
from app.services import recurring_income_service as recurring_income
from app.services.recurring_expense_service import following_month
from app.routes.auth_helpers import authenticated
from app.schemas.savings_schema import Currency, GoalName, Money
from app.services.recurring_expense_service import materialize_due

accounts_bp = Blueprint('accounts', __name__)
ACCOUNT_TYPES = ('bank', 'card', 'cash', 'savings')


class AccountCreate(Schema):
    name = GoalName(required=True)
    account_type = fields.String(required=True, validate=validate.OneOf(ACCOUNT_TYPES))
    currency = Currency(required=True)


class AccountPatch(Schema):
    name = GoalName()
    account_type = fields.String(validate=validate.OneOf(ACCOUNT_TYPES))


class IncomeCreate(Schema):
    recurring = fields.Boolean(load_default=False)
    amount = Money(required=True)
    date = fields.Date(required=True)
    description = fields.String(required=True, validate=validate.Length(min=1, max=100))


class IncomeQuery(Schema):
    page = fields.Integer(load_default=1, validate=validate.Range(min=1, max=1000000))


@accounts_bp.after_request
def no_cache(response):
    response.headers['Cache-Control'] = 'no-store'
    return response


@accounts_bp.errorhandler(ValidationError)
def invalid(error):
    db.session.rollback()
    return jsonify(message=error.messages), 400


def body(schema):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ValidationError('Expected an object.')
    return schema.load(payload)


def account_dict(row):
    income = db.session.scalar(select(func.coalesce(func.sum(Transaction.amount), 0)).where(
        Transaction.account_id == row.id, Transaction.transaction_type == 'income'))
    expense = db.session.scalar(select(func.coalesce(func.sum(Transaction.amount), 0)).where(
        Transaction.account_id == row.id, Transaction.transaction_type == 'expense'))
    reserved = db.session.scalar(select(func.coalesce(func.sum(SavingsContribution.amount), 0)).where(
        SavingsContribution.account_id == row.id))
    return dict(id=row.id, name=row.name, account_type=row.account_type,
                currency=row.currency, balance=format(income - expense - reserved, '.2f'),
                income_total=format(income, '.2f'), expense_total=format(expense, '.2f'), savings_total=format(reserved, '.2f'))


def income_dict(row):
    timestamp = row.created_at
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return dict(id=row.id, account_id=row.account_id, amount=format(row.amount, '.2f'),
                description=row.description, date=timestamp.astimezone(timezone.utc).date().isoformat(),
                recurring_id=row.recurring_income_occurrence.recurring_id if row.recurring_income_occurrence else None,
                recurring_active=bool(row.recurring_income_occurrence and row.recurring_income_occurrence.rule.active))


def rule_dict(rule):
    return dict(id=rule.id, amount=format(rule.amount, '.2f'), description=rule.description,
                billing_day=rule.billing_day, starts_on=rule.starts_on.isoformat(), next_due_on=rule.next_due_on.isoformat())


def sync_income(user_id):
    try:
        recurring_income.materialize_due(user_id)
        db.session.commit()
    except ValueError as error:
        raise ValidationError(str(error)) from None


def lock_user(user_id):
    db.session.execute(select(User).where(User.id == user_id).with_for_update()).scalar_one()


def owned(user_id, account_id, lock=False):
    query = select(Account).where(Account.id == account_id, Account.user_id == user_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    return db.session.scalar(query)


@accounts_bp.get('')
@authenticated
def list_accounts(user_id):
    try:
        materialize_due(user_id)
        db.session.commit()
    except ValueError as error:
        raise ValidationError(str(error)) from None
    rows = db.session.scalars(select(Account).where(Account.user_id == user_id).order_by(Account.id))
    return jsonify(accounts=[account_dict(row) for row in rows])


@accounts_bp.post('')
@authenticated
def create_account(user_id):
    denied = check_session_origin()
    if denied is not None:
        return denied
    values = body(AccountCreate())
    lock_user(user_id)
    row = Account(user_id=user_id, balance=Decimal('0.00'), **values)
    db.session.add(row)
    db.session.commit()
    return jsonify(account=account_dict(row)), 201


@accounts_bp.patch('/<int:account_id>')
@authenticated
def update_account(user_id, account_id):
    denied = check_session_origin()
    if denied is not None:
        return denied
    values = body(AccountPatch())
    if not values:
        raise ValidationError('At least one editable field is required.')
    lock_user(user_id)
    row = owned(user_id, account_id, lock=True)
    if row is None:
        return jsonify(message='Account not found'), 404
    for key, value in values.items():
        setattr(row, key, value)
    db.session.commit()
    return jsonify(account=account_dict(row))


@accounts_bp.get('/<int:account_id>/incomes')
@authenticated
def list_incomes(user_id, account_id):
    values = IncomeQuery().load(request.args.to_dict())
    if owned(user_id, account_id) is None:
        return jsonify(message='Account not found'), 404
    sync_income(user_id)
    query = select(Transaction).where(Transaction.account_id == account_id, Transaction.transaction_type == 'income')
    total = db.session.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.session.scalars(query.order_by(Transaction.created_at.desc(), Transaction.id.desc())
                              .offset((values['page'] - 1) * 50).limit(50))
    rules = db.session.scalars(select(RecurringIncome).where(RecurringIncome.user_id == user_id,
        RecurringIncome.account_id == account_id, RecurringIncome.active.is_(True)).order_by(RecurringIncome.billing_day, RecurringIncome.id))
    return jsonify(incomes=[income_dict(row) for row in rows], total=total, page=values['page'], recurring_incomes=[rule_dict(rule) for rule in rules])


@accounts_bp.post('/<int:account_id>/incomes')
@authenticated
def add_income(user_id, account_id):
    denied = check_session_origin()
    if denied is not None:
        return denied
    values = body(IncomeCreate())
    values['description'] = values['description'].strip()
    if not values['description']:
        raise ValidationError({'description': ['Description is required.']})
    if 'recurring' in request.json and type(request.json['recurring']) is not bool:
        raise ValidationError({'recurring': ['A boolean is required.']})
    if not values['recurring'] and values['date'] > recurring_income.today():
        raise ValidationError({'date': ['Income cannot be in the future.']})
    lock_user(user_id)
    account = owned(user_id, account_id, lock=True)
    if account is None:
        return jsonify(message='Account not found'), 404
    if values['recurring']:
        rule = RecurringIncome(user_id=user_id, account_id=account.id, amount=values['amount'],
            description=values['description'], billing_day=values['date'].day,
            starts_on=values['date'], next_due_on=values['date'])
        db.session.add(rule)
        db.session.flush()
        sync_income(user_id)
        return jsonify(recurring_income=rule_dict(rule), account=account_dict(account)), 201
    balance = account.balance + values['amount']
    if abs(balance) > Decimal('9999999999999.99'):
        raise ValidationError({'amount': ['Resulting balance is too large.']})
    row = Transaction(account_id=account.id, transaction_type='income', amount=values['amount'],
                      description=values['description'], created_at=datetime.combine(values['date'], time(12), tzinfo=timezone.utc))
    account.balance = balance
    db.session.add(row)
    db.session.commit()
    return jsonify(income=income_dict(row), account=account_dict(account)), 201


@accounts_bp.post('/<int:account_id>/incomes/<int:income_id>/repeat')
@authenticated
def repeat_income(user_id, account_id, income_id):
    denied = check_session_origin()
    if denied is not None:
        return denied
    lock_user(user_id)
    account = owned(user_id, account_id, lock=True)
    if account is None:
        return jsonify(message='Account not found'), 404
    row = db.session.scalar(select(Transaction).where(Transaction.id == income_id,
        Transaction.account_id == account_id, Transaction.transaction_type == 'income'))
    if row is None:
        return jsonify(message='Income not found'), 404
    if row.recurring_income_occurrence and row.recurring_income_occurrence.rule.active:
        return jsonify(message='Income is already recurring'), 409
    timestamp = row.created_at if row.created_at.tzinfo else row.created_at.replace(tzinfo=timezone.utc)
    day = timestamp.astimezone(timezone.utc).date()
    if row.recurring_income_occurrence:
        rule = row.recurring_income_occurrence.rule
        rule.active = True
        rule.next_due_on = following_month(max(day, recurring_income.today()), rule.billing_day)
    else:
        rule = RecurringIncome(user_id=user_id, account_id=account_id, amount=row.amount,
            description=row.description, billing_day=day.day, starts_on=day,
            next_due_on=following_month(max(day, recurring_income.today()), day.day))
        db.session.add(rule)
        db.session.flush()
        db.session.add(RecurringIncomeOccurrence(recurring_id=rule.id, month=day.replace(day=1), transaction_id=row.id))
    db.session.commit()
    return jsonify(recurring_income=rule_dict(rule), account=account_dict(account)), 201


@accounts_bp.delete('/<int:account_id>/recurring-incomes/<int:rule_id>')
@authenticated
def stop_recurring_income(user_id, account_id, rule_id):
    denied = check_session_origin()
    if denied is not None:
        return denied
    lock_user(user_id)
    if owned(user_id, account_id) is None:
        return jsonify(message='Account not found'), 404
    rule = db.session.scalar(select(RecurringIncome).where(RecurringIncome.id == rule_id,
        RecurringIncome.user_id == user_id, RecurringIncome.account_id == account_id).with_for_update())
    if rule is None:
        return jsonify(message='Recurring income not found'), 404
    rule.active = False
    db.session.commit()
    return '', 204
