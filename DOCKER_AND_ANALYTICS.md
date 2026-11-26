# Analytics, forecasts, and local Docker

## Python runtime

The backend targets Python 3.13 in both Dockerfiles and `.python-version`.
Install dependencies with `python -m pip install -r backend/requirements.txt`
using a Python 3.13 virtual environment.

On this Windows checkout, the Python 3.13 runtime is in `.python313/` and
the project interpreter remains `.venv/Scripts/python.exe`. The previous
Python 3.14 environment is preserved in `.venv-py314-backup/`, with its package
snapshot in `artifacts/python313/requirements-py314-backup.txt`.
Restart PyCharm if its interpreter label still shows the cached Python 3.14
version; `.venv/Scripts/python.exe --version` reports the actual runtime.

Run backend tests from `backend/` with
`../.venv/Scripts/python.exe -m pytest -q`. PostgreSQL-specific tests require
`--db-backend=postgresql` and a running test database. Rebuild Docker images
to apply the Python change to containers.

Mandatory email verification is now implemented. Read GMAIL_SETUP.md before rebuilding the working stack; it requires sender OAuth credentials. See VERIFICATION_API.md for the new two-step login contract and isolated tests.

## Analytics API

### PDF statement import

The Accounts page includes PDF upload and automatic import into a selected account. The authenticated
`POST /api/statements/analyze` endpoint accepts multipart form field `file`, with
the existing CSRF and trusted-origin protections. Limits: 10 MiB per file,
20 pages, digital PDFs only; encrypted and scanned PDFs are rejected. Temporary
files are removed after processing. `/analyze` remains read-only for API callers.
`POST /api/statements/import` accepts the same `file` plus `account_id` and saves
all validated rows atomically to the existing `transaction` table. Income and
expenses update the account balance; expenses use the shared category
`Без категорії`. Currency must match the account, dates cannot be in the future,
amounts must be nonzero with at most two decimal places, and descriptions must
contain 1–100 characters. Invalid rows or failed/discrepant balance verification
reject the whole import. Unverifiable statements can still be imported.

Migration `d52b8ea10317` adds `statement_import` receipts with a unique
account/file SHA-256 pair. Reuploading identical PDF bytes to the same account
returns `duplicate: true`, even if imported operations were later edited/deleted.
Different or overlapping PDFs are not deduplicated against each other or manual
transactions. Use non-overlapping exports. Apply migrations before running the
new API: from `backend/`, run `../.venv/Scripts/python.exe -m flask --app run db upgrade`.

Install `backend/requirements.txt`, then install and start Ollama separately.
Run `ollama pull qwen2.5:3b` once to download the default model and ensure Ollama is
listening on port 11434. Local Flask defaults to `http://localhost:11434`;
Compose uses `http://host.docker.internal:11434`. Docker must be able to reach
that host service. Override `BSP_HYBRID_MODEL` (an `ollama/` model identifier)
and `BSP_HYBRID_API_BASE` in the environment if needed. These variables are
passed through Compose. Rebuild the API and frontend containers after this change.

Model requests have a 180-second timeout to allow local model startup. Failed extraction returns a readable
error. The Accounts page reports the imported count and refreshes balances and
income history. Imported expenses and incomes also feed the existing analytics.
No model-based categorization is performed.

The local Windows installation uses Ollama 0.40.18 and `qwen2.5:3b` on the
GTX 1650 Ti (4 GiB VRAM, 16 GiB system RAM). Cloud features are disabled via
Ollama's `disable_ollama_cloud` setting and user-level `OLLAMA_NO_CLOUD=1`.
No account or API key is required. Run `ollama ps` to inspect GPU offload;
open a new terminal if the newly installed command is not on PATH yet.
The synthetic two-transaction PDF test completed in 5.3 seconds with the model
already loaded; cold starts and longer statements take longer. Re-run
`artifacts/check-local-ollama.py` with the project interpreter for a read-only
live-model smoke check. It generates synthetic data and does not write ledger rows.

Use Authorization: Bearer <token> with:

- GET /api/analytics/monthly?year=2026&month=11&currency=UAH
- GET /api/analytics/forecast?currency=UAH&horizon_months=12

Responses use analytics and forecast envelopes. The user comes from the JWT;
user_id is not accepted as a request parameter. horizon_months defaults to 12
and supports 1-60. Amounts are two-decimal strings and months are YYYY-MM.
Malformed parameters return 400; missing/invalid JWTs follow existing auth rules.

Forecasting reads six closed UTC calendar months and needs at least three
months with transactions. The current month and empty months are excluded from
the sample. history_window, used_months, missing_months and sample_size explain
the inputs. With insufficient history the API returns 200 with
status=insufficient_history and an empty scenarios array.

Scenarios use linearly interpolated historical quartiles:
pessimistic = income P25 / expense P75; realistic = P50 / P50;
optimistic = income P75 / expense P25. Each scenario keeps those monthly levels
constant and returns points containing income_total, expense_total, net_total,
cumulative_net_change, and projected_savings. Decimal ROUND_HALF_UP is used.

An active savings goal in the requested currency supplies starting_savings.
Otherwise the zero base represents relative cashflow change, not account wealth.
All net cashflow is assumed available for potential saving; negative projected
savings represents a deficit. Actual contributions, balances, and goal status
are never changed by a forecast. There is no currency conversion.

goal_projection reports estimated_goal_month and goal_reachable_by_deadline.
Future assessments have month-level precision. Already achieved goals use
actual contribution dates. A deadline outside the horizon is unknown (null)
unless the goal is already shown as reachable inside that horizon.

## Docker setup

Docker Engine with Docker Compose is required. The local Docker DB starts
clean; it does not use or import the existing local PostgreSQL database.

From the repository root on Windows:

```powershell
.\.venv\Scripts\python.exe backend/docker_env.py
docker compose --env-file .env.docker config --quiet
docker compose --env-file .env.docker up --build -d
docker compose --env-file .env.docker ps
```

docker_env.py creates .env.docker with random local credentials only when it
does not exist. It never overwrites an existing file. The file is ignored by
Git and is not copied into the image. .env.docker.example documents its fields.

The API is served at http://localhost:5000. API_PORT changes the host port.
Gunicorn runs the API; db uses PostgreSQL 18 with a named persistent volume;
migrate runs flask db upgrade after the DB is healthy, before the API starts.
GET /api/health returns 200/ok when the database is reachable, otherwise 503.
PostgreSQL is also available to local pgAdmin at 127.0.0.1:5433 (container port 5432).
Register a separate server using POSTGRES_DB, POSTGRES_USER, and POSTGRES_PASSWORD
from .env.docker, then inspect Schemas > public > Tables > user. The existing
local PostgreSQL on port 5432 is a separate database.

## Angular frontend

Open http://localhost:4200 after the Compose startup above. FRONTEND_PORT in
.env.docker optionally changes the published port; its default is 4200.
Existing environment files do not need to be regenerated.

The frontend image builds Angular 22 with Node.js 24, then serves the SPA with
Nginx. You do not need a local Node.js installation for Docker builds or tests.
The frontend container waits for API health. Nginx forwards /api/ to api:5000;
the browser uses relative /api URLs on the same origin, so CORS_ORIGINS is not
needed for the Compose frontend. The API remains available on localhost:5000.

The public routes are /, /cookies, /login, /register, and /verify.
Reloading an Angular route is supported.
The dark Ukrainian homepage introduces monthly analytics, savings goals, and
forecast scenarios; all financial figures on it are labelled as demo data.
Login and registration are connected; the personal dashboard is the next stage.

The informational notice stores only finsight_cookie_notice=v3 for 180 days
(Path=/, SameSite=Lax, Secure over HTTPS). The footer can reopen it. It stores
no email, password, access token, or financial data and adds no third-party
tracking. Browser authentication uses a separate backend-set HttpOnly cookie.

Rebuild just the frontend after editing its source:

```powershell
docker compose --env-file .env.docker up --build -d frontend
```

Run frontend unit tests without installing Node.js locally:

```powershell
docker build --target test -t finsight-frontend:test ./frontend
docker run --rm finsight-frontend:test
```

For optional local development, use Node.js 24.15+ (24.x):

```powershell
cd frontend
npm ci
npm start
```

The Angular dev server also runs on localhost:4200 and proxies /api/ to
localhost:5000. Stop the Docker frontend before using that port for ng serve.
If API_PORT differs, update frontend/proxy.conf.json for local development.

Check the same-origin API proxy and SPA route from PowerShell:

```powershell
Invoke-RestMethod http://localhost:4200/api/health
Invoke-WebRequest http://localhost:4200/cookies -UseBasicParsing
```

CORS_ORIGINS is only needed for clients that access the API from a different
origin directly. It accepts a comma-separated allowlist and rejects wildcards;
those clients use Authorization and Content-Type headers with the current API.


## Browser authentication API

See VERIFICATION_API.md: registration/login first returns a pending verification, then OTP completion issues the session or Bearer token. No password-only endpoint bypasses OTP. Trusted browsers may skip only the code for 90 days; Logout forgets trust.

## Verification and persistence

```powershell
.\.venv\Scripts\python.exe backend/docker_smoke.py
```

The smoke script uses only the isolated verification-test Compose project,
creates a unique synthetic user and savings goal, checks OTP and analytics
endpoints, establishes a cookie session through the frontend proxy, restarts
db/api, and verifies that the existing cookie, login and savings persist.
It also checks cookie logout. It leaves
screenshots and fake-mail files in ignored artifacts/ and removes only the test project.

```powershell
docker compose --env-file .env.docker logs api migrate db
docker compose --env-file .env.docker down
```

Normal down preserves the named database volume. Keep .env.docker so the same
database credentials and JWT keys are used on later starts.

Run the full test suite from backend:
```powershell
..\.venv\Scripts\python.exe -m pytest tests -q --db-backend=sqlite
..\.venv\Scripts\python.exe -m pytest tests -q --db-backend=postgresql
```
