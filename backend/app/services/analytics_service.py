"""Read-only monthly reporting in UTC, with exact monetary values."""
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import case, func, select

from app.extensions import db
from app.models.account import Account
from app.models.category import Category
from app.models.transaction import Transaction
from app.models.savings_goal import SavingsContribution, SavingsGoal


CENT = Decimal('0.01')
ZERO = Decimal('0.00')


def _json_value(value):
    if isinstance(value, Decimal):
        return format(value, '.2f')
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    return value


@dataclass(frozen=True)
class MonthlyTotals:
    user_id: int
    year: int
    month: int
    currency: str
    income_total: Decimal
    expense_total: Decimal
    net_total: Decimal
    expense_to_income_percent: Decimal | None

    def to_dict(self) -> dict:
        """Return JSON-ready dates and decimal strings, including nested rows."""
        return _json_value(asdict(self))


@dataclass(frozen=True)
class DailyTotals:
    date: date
    income_total: Decimal
    expense_total: Decimal
    net_total: Decimal


@dataclass(frozen=True)
class CategoryExpense:
    category_id: int
    name: str
    expense_total: Decimal


@dataclass(frozen=True)
class AccountTotals:
    account_id: int
    name: str
    income_total: Decimal
    expense_total: Decimal
    net_total: Decimal


@dataclass(frozen=True)
class MonthlyAnalytics(MonthlyTotals):
    daily: tuple[DailyTotals, ...]
    categories: tuple[CategoryExpense, ...]
    accounts: tuple[AccountTotals, ...]


@dataclass(frozen=True)
class _MonthScope:
    user_id: int
    year: int
    month: int
    currency: str
    start: datetime
    end: datetime


def _month_scope(user_id, year, month, currency):
    if type(user_id) is not int or user_id <= 0:
        raise ValueError('user_id must be a positive integer.')
    if type(year) is not int or type(month) is not int:
        raise ValueError('year and month must be integers.')
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    end = (
        datetime(year + 1, 1, 1, tzinfo=timezone.utc)
        if month == 12 else datetime(year, month + 1, 1, tzinfo=timezone.utc)
    )
    if not isinstance(currency, str):
        raise ValueError('currency must be a three-letter code.')
    currency = currency.strip()
    if len(currency) != 3 or not currency.isascii() or not currency.isalpha():
        raise ValueError('currency must be a three-letter code.')
    return _MonthScope(user_id, year, month, currency.upper(), start, end)


def _query(scope, *columns):
    return (
        select(*columns)
        .select_from(Transaction)
        .join(Account, Transaction.account_id == Account.id)
        .where(
            Account.user_id == scope.user_id,
            Account.currency == scope.currency,
            Transaction.created_at >= scope.start,
            Transaction.created_at < scope.end,
        )
    )


def _sum_type(transaction_type):
    return func.coalesce(func.sum(case(
        (Transaction.transaction_type == transaction_type, Transaction.amount),
        else_=ZERO,
    )), ZERO)


def _money(value):
    return value.quantize(CENT)


def _monthly_totals(scope):
    row = db.session.execute(_query(
        scope,
        _sum_type('income').label('income_total'),
        _sum_type('expense').label('expense_total'),
    )).one()
    income = _money(row.income_total)
    expense = _money(row.expense_total)
    percent = (
        (expense / income * Decimal('100')).quantize(CENT, rounding=ROUND_HALF_UP)
        if income else None
    )
    return MonthlyTotals(
        user_id=scope.user_id, year=scope.year, month=scope.month,
        currency=scope.currency, income_total=income, expense_total=expense,
        net_total=income - expense, expense_to_income_percent=percent,
    )


def get_monthly_totals(
    user_id: int, year: int, month: int, currency: str
) -> MonthlyTotals:
    """Calculate current income, expense, net, and spending percentage.

    Invalid arguments raise ValueError. A valid user ID with no matching
    records returns zero totals. A period must have a representable next month.
    """
    return _monthly_totals(_month_scope(user_id, year, month, currency))


def _daily_totals(scope):
    # PostgreSQL must not group timestamptz values in the session's local zone.
    timestamp = Transaction.created_at
    if db.session.get_bind().dialect.name == 'postgresql':
        timestamp = func.timezone('UTC', timestamp)
    day = func.date(timestamp).label('day')
    rows = db.session.execute(_query(
        scope, day, _sum_type('income').label('income_total'),
        _sum_type('expense').label('expense_total'),
    ).group_by(day))
    by_day = {}
    for row in rows:
        day_value = row.day if isinstance(row.day, date) else date.fromisoformat(row.day)
        by_day[day_value] = (_money(row.income_total), _money(row.expense_total))

    daily = []
    current = scope.start.date()
    while current < scope.end.date():
        income, expense = by_day.get(current, (ZERO, ZERO))
        daily.append(DailyTotals(current, income, expense, income - expense))
        current += timedelta(days=1)
    return tuple(daily)


def _category_expenses(scope):
    expense = func.sum(Transaction.amount).label('expense_total')
    rows = db.session.execute(
        _query(scope, Category.id.label('category_id'), Category.name, expense)
        .join(Category, Transaction.category_id == Category.id)
        .where(Transaction.transaction_type == 'expense')
        .group_by(Category.id, Category.name)
        .order_by(expense.desc(), Category.id)
    )
    return tuple(
        CategoryExpense(row.category_id, row.name, _money(row.expense_total))
        for row in rows
    )


def _account_totals(scope):
    rows = db.session.execute(_query(
        scope, Account.id.label('account_id'), Account.name,
        _sum_type('income').label('income_total'),
        _sum_type('expense').label('expense_total'),
    ).group_by(Account.id, Account.name).order_by(Account.id))
    accounts = []
    for row in rows:
        income, expense = _money(row.income_total), _money(row.expense_total)
        accounts.append(AccountTotals(
            row.account_id, row.name, income, expense, income - expense,
        ))
    return tuple(accounts)


def get_monthly_analytics(
    user_id: int, year: int, month: int, currency: str
) -> MonthlyAnalytics:
    """Return monthly totals and chart rows without committing or updating balances.

    Daily rows include every UTC day. Category rows contain expenses only,
    ordered by amount descending then ID; account rows include accounts with
    operations, ordered by ID. Each call calculates a new result.
    """
    scope = _month_scope(user_id, year, month, currency)
    totals = _monthly_totals(scope)
    return MonthlyAnalytics(
        user_id=totals.user_id, year=totals.year, month=totals.month,
        currency=totals.currency, income_total=totals.income_total,
        expense_total=totals.expense_total, net_total=totals.net_total,
        expense_to_income_percent=totals.expense_to_income_percent,
        daily=_daily_totals(scope),
        categories=_category_expenses(scope),
        accounts=_account_totals(scope),
    )


@dataclass(frozen=True)
class ForecastPoint:
    month: str
    income_total: Decimal
    expense_total: Decimal
    net_total: Decimal
    cumulative_net_change: Decimal
    projected_savings: Decimal


@dataclass(frozen=True)
class ForecastGoal:
    id: int
    name: str
    currency: str
    target_amount: Decimal
    saved_amount: Decimal
    deadline: date
    actual_achievement_date: date | None


@dataclass(frozen=True)
class GoalProjection:
    estimated_goal_month: str | None
    goal_reachable_by_deadline: bool | None
    already_achieved: bool
    assessment_granularity: str


@dataclass(frozen=True)
class ForecastScenario:
    name: str
    monthly_income: Decimal
    monthly_expense: Decimal
    monthly_net: Decimal
    points: tuple[ForecastPoint, ...]
    goal_projection: GoalProjection | None


@dataclass(frozen=True)
class FinancialForecast:
    user_id: int
    currency: str
    as_of: date
    horizon_months: int
    status: str
    method: str
    minimum_history_months: int
    sample_size: int
    history_window: tuple[str, ...]
    used_months: tuple[str, ...]
    missing_months: tuple[str, ...]
    history: tuple[MonthlyTotals, ...]
    starting_savings: Decimal
    starting_savings_basis: str
    goal: ForecastGoal | None
    scenarios: tuple[ForecastScenario, ...]

    def to_dict(self) -> dict:
        return _json_value(asdict(self))


def _forecast_today():
    return datetime.now(timezone.utc).date()


def _forecast_month(value, offset):
    year, month = divmod(value.year * 12 + value.month - 1 + offset, 12)
    return date(year, month + 1, 1)


def _percentile(values, percentile):
    ordered = sorted(values)
    position = Decimal(len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    value = ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _forecast_goal(user_id, currency, today):
    goal = db.session.scalar(select(SavingsGoal).where(
        SavingsGoal.user_id == user_id, SavingsGoal.currency == currency,
        SavingsGoal.status == 'active',
    ))
    if goal is None:
        return None
    rows = db.session.execute(
        select(SavingsContribution.amount, SavingsContribution.contributed_on)
        .where(
            SavingsContribution.goal_id == goal.id,
            SavingsContribution.contributed_on <= today,
        )
        .order_by(SavingsContribution.contributed_on, SavingsContribution.id)
    )
    saved = ZERO
    achieved = None
    for amount, contributed_on in rows:
        saved += amount
        if achieved is None and saved >= goal.target_amount:
            achieved = contributed_on
    return ForecastGoal(
        goal.id, goal.name, goal.currency, goal.target_amount,
        saved.quantize(CENT), goal.deadline, achieved,
    )


def _goal_projection(goal, today, points):
    if goal is None:
        return None
    if goal.actual_achievement_date is not None:
        return GoalProjection(
            goal.actual_achievement_date.isoformat()[:7],
            goal.actual_achievement_date <= goal.deadline, True, 'actual_date',
        )
    estimated = next(
        (point.month for point in points if point.projected_savings >= goal.target_amount),
        None,
    )
    deadline_month = goal.deadline.isoformat()[:7]
    if goal.deadline < today:
        reachable = False
    elif deadline_month < points[0].month:
        reachable = None
    elif estimated is not None and estimated <= deadline_month:
        reachable = True
    elif deadline_month <= points[-1].month:
        reachable = False
    else:
        reachable = None
    return GoalProjection(estimated, reachable, False, 'month')


def get_financial_forecast(
    user_id: int, currency: str, horizon_months: int = 12,
) -> FinancialForecast:
    """Project fixed monthly income/expense quartiles over the next 1-60 months.

    Use six closed UTC months, requiring at least three with transactions.
    Projected savings assumes all net cashflow is available for saving, including
    deficits. It never changes actual contributions, balances, or goal status.
    """
    if type(horizon_months) is not int or not 1 <= horizon_months <= 60:
        raise ValueError('horizon_months must be an integer between 1 and 60.')
    today = _forecast_today()
    scope = _month_scope(user_id, today.year, today.month, currency)
    future = tuple(_forecast_month(today, index) for index in range(1, horizon_months + 1))
    window = tuple(_forecast_month(today, offset) for offset in range(-6, 0))
    history, used, missing = [], [], []
    for month in window:
        totals = get_monthly_totals(user_id, month.year, month.month, scope.currency)
        label = month.isoformat()[:7]
        if totals.income_total or totals.expense_total:
            history.append(totals)
            used.append(label)
        else:
            missing.append(label)
    goal = _forecast_goal(user_id, scope.currency, today)
    starting = goal.saved_amount if goal is not None else ZERO
    scenarios = []
    if len(history) >= 3:
        incomes = [item.income_total for item in history]
        expenses = [item.expense_total for item in history]
        for name, income_quantile, expense_quantile in (
            ('pessimistic', Decimal('0.25'), Decimal('0.75')),
            ('realistic', Decimal('0.50'), Decimal('0.50')),
            ('optimistic', Decimal('0.75'), Decimal('0.25')),
        ):
            income = _percentile(incomes, income_quantile)
            expense = _percentile(expenses, expense_quantile)
            net = income - expense
            cumulative = ZERO
            points = []
            for month in future:
                cumulative += net
                points.append(ForecastPoint(
                    month.isoformat()[:7], income, expense, net,
                    cumulative, starting + cumulative,
                ))
            scenarios.append(ForecastScenario(
                name, income, expense, net, tuple(points),
                _goal_projection(goal, today, points),
            ))
    return FinancialForecast(
        user_id=user_id, currency=scope.currency, as_of=today,
        horizon_months=horizon_months,
        status='ready' if len(history) >= 3 else 'insufficient_history',
        method='historical_quartiles_v1', minimum_history_months=3,
        sample_size=len(history),
        history_window=tuple(month.isoformat()[:7] for month in window),
        used_months=tuple(used), missing_months=tuple(missing), history=tuple(history),
        starting_savings=starting,
        starting_savings_basis='active_goal' if goal is not None else 'relative_change',
        goal=goal, scenarios=tuple(scenarios),
    )
