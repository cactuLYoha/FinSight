"""Manual savings goals and on-demand monthly plans."""
from calendar import monthrange
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from functools import wraps

from marshmallow import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.savings_goal import SavingsContribution, SavingsGoal
from app.models.account import Account
from app.models.user import User
from app.schemas.savings_schema import (
    ContributionCreateSchema, ContributionPatchSchema,
    GoalCreateSchema, GoalPatchSchema, GoalReactivateSchema, SavingsSummaryQuerySchema,
)
from app.services.analytics_service import get_monthly_totals


CENT = Decimal('0.01')
ZERO = Decimal('0.00')


class SavingsError(Exception):
    status_code = 409


class SavingsNotFound(SavingsError):
    status_code = 404


class SavingsConflict(SavingsError):
    pass


def utc_today():
    return datetime.now(timezone.utc).date()


def _shift_month(value, offset):
    year, month = divmod(value.year * 12 + value.month - 1 + offset, 12)
    return date(year, month + 1, 1)


def _write(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            user_id = args[0] if args else kwargs.get('user_id')
            if user_id is not None:
                db.session.execute(select(User).where(User.id == user_id).with_for_update()).scalar_one()
            result = function(*args, **kwargs)
            db.session.commit()
            return result
        except IntegrityError:
            db.session.rollback()
            raise SavingsConflict('Savings change conflicts with existing data.') from None
        except Exception:
            db.session.rollback()
            raise
    return wrapped


def _owned_goal(user_id, goal_id, lock=False):
    statement = select(SavingsGoal).where(
        SavingsGoal.id == goal_id, SavingsGoal.user_id == user_id,
    )
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    goal = db.session.scalar(statement)
    if goal is None:
        raise SavingsNotFound('Savings goal not found.')
    return goal


def _active(goal):
    if goal.status != 'active':
        raise SavingsConflict('Only active goals can be changed.')


def _validate_deadline(deadline):
    if deadline < _shift_month(utc_today(), 1):
        raise ValidationError({'deadline': ['Deadline must be in the next month or later.']})


def _validate_contribution_date(contributed_on):
    if contributed_on > utc_today():
        raise ValidationError({'contributed_on': ['A contribution cannot be in the future.']})


def _patch(schema, data):
    values = schema.load(data)
    if not values:
        raise ValidationError({'_schema': ['At least one editable field is required.']})
    return values


def _saved_amount(goal_id):
    return db.session.scalar(
        select(func.coalesce(func.sum(SavingsContribution.amount), ZERO))
        .where(SavingsContribution.goal_id == goal_id)
    ).quantize(CENT)


def _timestamp(value):
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def serialize_goal(goal, saved=None):
    saved = _saved_amount(goal.id) if saved is None else saved
    remaining = max(goal.target_amount - saved, ZERO)
    progress = min(saved / goal.target_amount * Decimal('100'), Decimal('100'))
    return {
        'id': goal.id, 'user_id': goal.user_id, 'name': goal.name,
        'target_amount': format(goal.target_amount, '.2f'),
        'currency': goal.currency, 'deadline': goal.deadline.isoformat(),
        'status': goal.status, 'created_at': _timestamp(goal.created_at),
        'saved_amount': format(saved, '.2f'),
        'remaining_amount': format(remaining, '.2f'),
        'progress_percent': format(progress.quantize(CENT, rounding=ROUND_HALF_UP), '.2f'),
        'is_achieved': saved >= goal.target_amount,
    }


def serialize_contribution(contribution):
    return {
        'id': contribution.id, 'goal_id': contribution.goal_id,
        'amount': format(contribution.amount, '.2f'),
        'account_id': contribution.account_id,
        'account_name': contribution.account.name if contribution.account else None,
        'contributed_on': contribution.contributed_on.isoformat(),
        'note': contribution.note, 'created_at': _timestamp(contribution.created_at),
    }


@_write
def create_goal(user_id, data):
    values = GoalCreateSchema().load(data)
    _validate_deadline(values['deadline'])
    goal = SavingsGoal(user_id=user_id, **values)
    db.session.add(goal)
    return goal


def get_goal(user_id, goal_id):
    return serialize_goal(_owned_goal(user_id, goal_id))


def list_goals(user_id):
    goals = db.session.scalars(
        select(SavingsGoal).where(SavingsGoal.user_id == user_id)
        .order_by(SavingsGoal.created_at.desc(), SavingsGoal.id.desc())
    ).all()
    if not goals:
        return []
    saved = dict(db.session.execute(
        select(SavingsContribution.goal_id, func.sum(SavingsContribution.amount))
        .where(SavingsContribution.goal_id.in_([goal.id for goal in goals]))
        .group_by(SavingsContribution.goal_id)
    ).all())
    return [serialize_goal(goal, saved.get(goal.id, ZERO)) for goal in goals]


@_write
def update_goal(user_id, goal_id, data):
    goal = _owned_goal(user_id, goal_id, lock=True)
    _active(goal)
    values = _patch(GoalPatchSchema(), data)
    if 'deadline' in values:
        _validate_deadline(values['deadline'])
    for key, value in values.items():
        setattr(goal, key, value)
    return goal


def _owned_contribution(goal_id, contribution_id):
    contribution = db.session.scalar(select(SavingsContribution).where(
        SavingsContribution.id == contribution_id,
        SavingsContribution.goal_id == goal_id,
    ))
    if contribution is None:
        raise SavingsNotFound('Savings contribution not found.')
    return contribution


@_write
def add_contribution(user_id, goal_id, data):
    goal = _owned_goal(user_id, goal_id, lock=True)
    _active(goal)
    values = ContributionCreateSchema().load(data)
    values.setdefault('contributed_on', utc_today())
    _validate_contribution_date(values['contributed_on'])
    account = _contribution_account(user_id, goal.currency, values.pop('account_id', None))
    _change_account_balance(account, -values['amount'])
    contribution = SavingsContribution(goal_id=goal.id, **values)
    contribution.account = account
    db.session.add(contribution)
    return contribution


def list_contributions(user_id, goal_id):
    _owned_goal(user_id, goal_id)
    contributions = db.session.scalars(
        select(SavingsContribution).where(SavingsContribution.goal_id == goal_id)
        .order_by(SavingsContribution.contributed_on.desc(), SavingsContribution.id.desc())
    ).all()
    return [serialize_contribution(item) for item in contributions]


@_write
def update_contribution(user_id, goal_id, contribution_id, data):
    goal = _owned_goal(user_id, goal_id, lock=True)
    _active(goal)
    contribution = _owned_contribution(goal.id, contribution_id)
    values = _patch(ContributionPatchSchema(), data)
    if 'contributed_on' in values:
        _validate_contribution_date(values['contributed_on'])
    if 'amount' in values or 'account_id' in values:
        target = _contribution_account(user_id, goal.currency, values.pop('account_id', contribution.account_id))
        if contribution.account_id is not None:
            original = db.session.scalar(select(Account).where(Account.id == contribution.account_id).with_for_update())
            _change_account_balance(original, contribution.amount)
        _change_account_balance(target, -values.get('amount', contribution.amount))
        contribution.account = target
    for key, value in values.items():
        setattr(contribution, key, value)
    return contribution


@_write
def delete_contribution(user_id, goal_id, contribution_id):
    goal = _owned_goal(user_id, goal_id, lock=True)
    _active(goal)
    contribution = _owned_contribution(goal.id, contribution_id)
    if contribution.account_id is not None:
        account = db.session.scalar(select(Account).where(Account.id == contribution.account_id).with_for_update())
        _change_account_balance(account, contribution.amount)
    db.session.delete(contribution)


def _contribution_account(user_id, currency, account_id):
    if account_id is None:
        # Backward-compatible manual bookkeeping for API clients without a source.
        account = db.session.scalar(select(Account).where(Account.user_id == user_id,
            Account.currency == currency, Account.name == 'Ручний облік', Account.account_type == 'cash').order_by(Account.id).with_for_update())
        if account is None:
            account = Account(user_id=user_id, currency=currency, name='Ручний облік', account_type='cash', balance=ZERO)
            db.session.add(account)
            db.session.flush()
    else:
        account = db.session.scalar(select(Account).where(Account.id == account_id, Account.user_id == user_id,
            Account.currency == currency).with_for_update().execution_options(populate_existing=True))
        if account is None:
            raise ValidationError({'account_id': ['Account not found in this currency.']})
    return account


def _change_account_balance(account, delta):
    balance = account.balance + delta
    if abs(balance) > Decimal('9999999999999.99'):
        raise ValidationError({'amount': ['Resulting account balance is too large.']})
    account.balance = balance


@_write
def complete_goal(user_id, goal_id):
    goal = _owned_goal(user_id, goal_id, lock=True)
    _active(goal)
    if _saved_amount(goal.id) < goal.target_amount:
        raise SavingsConflict('The goal has not reached its target.')
    goal.status = 'completed'
    return goal


@_write
def cancel_goal(user_id, goal_id):
    goal = _owned_goal(user_id, goal_id, lock=True)
    _active(goal)
    goal.status = 'cancelled'
    return goal


@_write
def reactivate_goal(user_id, goal_id, data):
    goal = _owned_goal(user_id, goal_id, lock=True)
    if goal.status != 'cancelled':
        raise SavingsConflict('Only cancelled goals can be reactivated.')
    values = GoalReactivateSchema().load(data)
    _validate_deadline(values['deadline'])
    if db.session.scalar(select(SavingsGoal.id).where(
        SavingsGoal.user_id == user_id, SavingsGoal.status == 'active',
    ).limit(1)) is not None:
        raise SavingsConflict('Another active savings goal already exists.')
    goal.deadline = values['deadline']
    goal.status = 'active'
    return goal


@_write
def delete_goal(user_id, goal_id):
    goal = _owned_goal(user_id, goal_id, lock=True)
    if db.session.scalar(select(SavingsContribution.id).where(
        SavingsContribution.goal_id == goal.id,
    ).limit(1)) is not None:
        raise SavingsConflict('Transfer savings before deleting this goal.')
    db.session.delete(goal)


@_write
def transfer_goal(user_id, goal_id, data):
    if not isinstance(data, dict) or set(data) not in ({'target_goal_id'}, {'new_goal'}):
        raise ValidationError({'transfer': ['Choose an existing goal or provide a new goal.']})
    target_id = data.get('target_goal_id')
    if 'target_goal_id' in data and (type(target_id) is not int or target_id <= 0 or target_id == goal_id):
        raise ValidationError({'target_goal_id': ['Choose a different goal.']})
    # Every operation on contributions locks its goal. Lock both in stable order
    # so transfers cannot race with contributions, deletion, or reverse transfers.
    locked = {identifier: _owned_goal(user_id, identifier, lock=True)
              for identifier in sorted({goal_id, target_id} if target_id else {goal_id})}
    source = locked[goal_id]
    rows = db.session.scalars(select(SavingsContribution).where(
        SavingsContribution.goal_id == source.id,
    ).order_by(SavingsContribution.id)).all()
    if not rows:
        raise SavingsConflict('This goal has no savings to transfer.')
    if target_id:
        target = locked[target_id]
        _active(target)
        if target.currency != source.currency:
            raise SavingsConflict('Goals must use the same currency.')
    else:
        values = GoalCreateSchema().load(data['new_goal'])
        _validate_deadline(values['deadline'])
        if values['currency'] != source.currency:
            raise SavingsConflict('Goals must use the same currency.')
        source.status = 'cancelled'
        db.session.flush()  # Release the one-active-goal index before insertion.
        target = SavingsGoal(user_id=user_id, **values)
        db.session.add(target)
        db.session.flush()
    source.status = 'cancelled'
    amount = sum((row.amount for row in rows), ZERO)
    for row in rows:
        row.goal_id = target.id
    db.session.flush()
    return {'source': serialize_goal(source), 'target': serialize_goal(target),
            'transferred_amount': format(amount, '.2f'), 'contribution_count': len(rows)}


def get_summary(user_id, query):
    values = SavingsSummaryQuerySchema().load(query)
    try:
        totals = get_monthly_totals(user_id=user_id, **values)
    except ValueError as error:
        raise ValidationError({'_schema': [str(error)]}) from None
    payload = totals.to_dict()
    payload['net_savings'] = payload.pop('net_total')
    payload['available_to_save'] = format(max(totals.net_total, ZERO), '.2f')
    rate = (
        (totals.net_total / totals.income_total * Decimal('100')).quantize(
            CENT, rounding=ROUND_HALF_UP,
        ) if totals.income_total else None
    )
    payload['savings_rate_percent'] = format(rate, '.2f') if rate is not None else None
    return payload


def _history(user_id, currency, today):
    periods = []
    month = today.replace(day=1)
    for offset in (-3, -2, -1):
        past = _shift_month(month, offset)
        totals = get_monthly_totals(user_id, past.year, past.month, currency)
        if totals.income_total or totals.expense_total:
            periods.append(totals)
    count = len(periods)
    average_net = (
        (sum((item.net_total for item in periods), ZERO) / count).quantize(
            CENT, rounding=ROUND_HALF_UP,
        ) if count else None
    )
    def average(field):
        if not count:
            return None
        value = sum((getattr(item, field) for item in periods), ZERO) / count
        return format(value.quantize(CENT, rounding=ROUND_HALF_UP), '.2f')
    return {
        'lookback_months': 3, 'sample_size': count,
        'status': 'available' if count else 'insufficient_history',
        'months': [item.to_dict() for item in periods],
        'average_income': average('income_total'),
        'average_expense': average('expense_total'),
        'average_net': format(average_net, '.2f') if average_net is not None else None,
        'available_monthly': format(max(average_net, ZERO), '.2f') if count else None,
    }, average_net


def get_plan(user_id, goal_id):
    goal = _owned_goal(user_id, goal_id)
    saved = _saved_amount(goal.id)
    remaining = max(goal.target_amount - saved, ZERO)
    today = utc_today()
    overdue = goal.status == 'active' and remaining > ZERO and goal.deadline < today
    history, average_net = _history(user_id, goal.currency, today)
    installments = []
    if goal.status == 'active' and remaining > ZERO and not overdue:
        months = (goal.deadline.year - today.year) * 12 + goal.deadline.month - today.month
        count = max(months, 1)
        cents, extra = divmod(int(remaining * 100), count)
        for index in range(count):
            month = _shift_month(today, index + 1) if months else today.replace(day=1)
            due = min(
                date(month.year, month.month, monthrange(month.year, month.month)[1]),
                goal.deadline,
            )
            amount = (Decimal(cents + (index < extra)) / 100).quantize(CENT)
            shortfall = max(amount - average_net, ZERO) if average_net is not None else None
            installments.append({
                'month': month.strftime('%Y-%m'), 'due_date': due.isoformat(),
                'amount': format(amount, '.2f'),
                'is_affordable': amount <= average_net if average_net is not None else None,
                'shortfall': format(shortfall, '.2f') if shortfall is not None else None,
            })

    required = max((Decimal(item['amount']) for item in installments), default=None)
    if remaining == ZERO:
        required = ZERO
    feasible = (
        True if remaining == ZERO else False if overdue else
        required <= average_net if required is not None and average_net is not None else None
    )
    shortfall = (
        max(required - average_net, ZERO)
        if required is not None and average_net is not None else None
    )
    if remaining == ZERO:
        shortfall = ZERO
    return {
        'goal': serialize_goal(goal, saved), 'as_of': today.isoformat(),
        'overdue': overdue, 'months_until_deadline': len(installments),
        'installment_count': sum(Decimal(item['amount']) > ZERO for item in installments),
        'required_monthly_amount': format(required, '.2f') if required is not None else None,
        'is_feasible': feasible,
        'monthly_shortfall': format(shortfall, '.2f') if shortfall is not None else None,
        'history': history, 'installments': installments,
    }
