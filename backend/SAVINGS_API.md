# Savings API

All endpoints require an Authorization: Bearer token. The owner always comes
from the JWT. Money is returned as two-decimal strings and dates as ISO dates.

## Create a goal

POST /api/savings/goals

```json
{"name":"Laptop","target_amount":"1200.00","currency":"UAH","deadline":"2027-06-15"}
```

Only one active goal is allowed per user, across all currencies. The deadline
must be in the next month or later. Initial savings are entered as the first
manual contribution. GET /api/savings/goals lists the current goal and history;
GET/PATCH /api/savings/goals/<id> reads or updates name, target_amount, deadline.
Currency cannot change. Mutations are allowed only while a goal is active.

## Manual contributions

GET/POST /api/savings/goals/<id>/contributions

```json
{"amount":"100.00","contributed_on":"2026-11-17","note":"Initial savings"}
```

contributed_on defaults to today in UTC and cannot be in the future.
PATCH/DELETE /api/savings/goals/<id>/contributions/<contribution_id> corrects
records. Contributions do not create income or expense transactions and do not
update account balances.

POST /api/savings/goals/<id>/complete closes a funded goal.
POST /api/savings/goals/<id>/cancel cancels it while preserving its records.
Closed goals are read-only and a new active goal can be created.

## Summary and plan

GET /api/savings/summary?year=2026&month=11&currency=UAH returns analytics income,
expense, net_savings (which may be negative), available_to_save (at least zero),
and savings_rate_percent (null when income is zero).

GET /api/savings/goals/<id>/plan returns goal progress, installment_count,
months_until_deadline, required_monthly_amount, history, is_feasible,
monthly_shortfall, and installments (month, due_date, amount, is_affordable,
shortfall). The schedule is recalculated from the remaining goal amount,
starting next month through the deadline month. It distributes whole cents
exactly; remaining cents go to the first installments. A deadline in the current
month has one final payment; an elapsed deadline is marked overdue.

Affordability uses the previous three complete UTC calendar months in the goal
currency. Only months with transactions are averaged; sample_size reports their
count. With no history the assessment and shortfall are null, but the schedule
is available. Negative average cashflow is included in the shortfall.

Responses use goal, goals, contribution, contributions, summary, or plan
envelopes. Validation errors return 400, missing or foreign resources 404, and
lifecycle/active-goal conflicts 409. JWT errors follow existing auth behavior.

## Migration and tests

From backend, apply the new schema:

```powershell
..\.venv\Scripts\python.exe -m flask --app run db upgrade
..\.venv\Scripts\python.exe -m pytest tests -q --db-backend=sqlite
..\.venv\Scripts\python.exe -m pytest tests -q --db-backend=postgresql
```

PostgreSQL tests allocate disposable finsight_test_<uuid> databases and remove
them at teardown. They do not use application tables in the configured live DB.
Forecast scenarios and allocation across multiple goals are a later stage.
