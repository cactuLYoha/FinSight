# FinSight frontend

Ukrainian Angular SPA with home, login, registration, email-code verification and
cookie information. Financial figures on the public home page are demo data.
The personal dashboard and sessionStorage handling are a later stage.

## Working Docker

Complete ../GMAIL_SETUP.md before deploying mandatory OTP. Then from repo root:
    docker compose --env-file .env.docker up --build -d

Open http://localhost:4200. Nginx proxies relative /api URLs to Flask.
Existing database credentials and JWT keys must be preserved.
The current working stack is not upgraded automatically until Gmail is connected.

## Authentication

Register or enter a password at /login, then complete /verify with the six-digit
email code. Inputs support Tab, Enter, paste and one-time-code autofill. Reloading
/verify restores the pending request from an HttpOnly cookie.

Optional trust lasts 90 days and skips the code on subsequent password logins.
It does not extend the seven-day login cookie. Logout forgets browser trust.
JavaScript never receives the cookie access token; no password or access token
is saved in localStorage/sessionStorage. Cookie notice v3 lasts 180 days.
See ../VERIFICATION_API.md for endpoints, limits and errors.

## Tests without Gmail

From repo root:
    docker build --target test -t finsight-frontend:test ./frontend
    docker run --rm finsight-frontend:test
    .\.venv\Scripts\python.exe backend/docker_smoke.py --browser

The last command builds a separate test stack on 4201, records fake mail in a
private test outbox, runs Chromium, then removes only that stack. It never adds a
test-code-reading endpoint to the application or sends real messages.

## Optional local Angular development

Use Node.js 24.15+ (24.x), then:
    cd frontend
    npm ci
    npm start

The dev proxy targets localhost:5000; update proxy.conf.json if API_PORT differs.
Stop the working frontend before using port 4200 for ng serve.
Use npm test -- --watch=false and npm run build for local checks.
Run npm audit when updating dependencies.
