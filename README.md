# FinSight

FinSight is a full-stack personal finance pet project for managing accounts, tracking income and expenses, planning savings, and viewing financial analytics and forecasts. It supports recurring payments, PDF bank statement imports using a local AI model, and email verification through Gmail.

## Architecture

```text
Angular frontend
    → REST API
    → Flask routes
    → Business services
    → SQLAlchemy models
    → PostgreSQL
```

The backend uses Flask’s application factory and Blueprints, with separate folders for routes, services, models, and validation schemas. Docker Compose runs the frontend through Nginx, the API, PostgreSQL, database migrations, and a separate recurring transaction worker.

## Libraries and tools

The following covers declared direct dependencies and the supporting technologies used by the project.

| Area | Libraries and tools |
| --- | --- |
| Frontend | Angular 22.2 (`@angular/common`, `@angular/compiler`, `@angular/core`, `@angular/forms`, `@angular/platform-browser`, `@angular/router`), RxJS, tslib |
| Frontend development | TypeScript 6, `@angular/cli`, `@angular/build`, `@angular/compiler-cli` |
| Backend | Python 3.13, Flask, Flask-SQLAlchemy / SQLAlchemy, Flask-Migrate / Alembic, Flask-JWT-Extended, Marshmallow, python-dotenv, psycopg2-binary, psycopg with binary support, Gunicorn |
| Password security | Werkzeug password hashing |
| Integrations | google-api-python-client, google-auth-httplib2, google-auth-oauthlib, bankstatementparser with hybrid support |
| Local AI | Ollama with Qwen2.5 3B for bank statement extraction |
| Testing and formatting | pytest, Vitest, jsdom, Prettier |
| Infrastructure | PostgreSQL 18, Docker, Docker Compose, Nginx, Node.js 24, npm |

## Recurring income processing

[`recurring_income_service.py`](backend/app/services/recurring_income_service.py) automatically creates income transactions when monthly rules become due, updates account balances, and advances payment dates. It uses decimal arithmetic, database row locks, and monthly occurrence records to prevent duplicate income entries during concurrent processing.

## Bank statement imports

The project supports PDF statement analysis and importing validated transactions into a selected account. Imported income and expenses update account balances and feed the existing analytics. Import receipts prevent identical PDF files from being imported repeatedly into the same account.

The import service is located in [`statement_import_service.py`](backend/app/services/statement_import_service.py).

