FinSight is a full-stack personal finance pet project for managing accounts, tracking income and expenses, planning savings, and viewing financial analytics and forecasts. It supports recurring payments, PDF bank statement imports using a local AI model, and email verification through Gmail.
Architecture: Angular frontend → REST API → Flask routes → business services → SQLAlchemy models → PostgreSQL. The backend uses Flask’s application factory and Blueprints, with separate folders for routes, services, models, and validation schemas. Docker Compose runs the frontend through Nginx, the API, PostgreSQL, database migrations, and a separate recurring transaction worker.
Libraries and tools declared in the project:
•
Frontend: Angular 22.2 (common, compiler, core, forms, platform-browser, router), RxJS, tslib; TypeScript 6, Angular CLI, Angular Build, and Angular Compiler CLI.
•
Backend: Python 3.13, Flask, Flask-SQLAlchemy / SQLAlchemy, Flask-Migrate / Alembic, Flask-JWT-Extended, Marshmallow, python-dotenv, psycopg2-binary, psycopg with binary support, and Gunicorn. Werkzeug handles password hashing.
•
Integrations: google-api-python-client, google-auth-httplib2, google-auth-oauthlib, and bankstatementparser with hybrid support; Ollama runs the local Qwen2.5 3B model for statement extraction.
•
Testing and formatting: pytest, Vitest, jsdom, and Prettier.
•
Infrastructure: PostgreSQL 18, Docker, Docker Compose, Nginx, Node.js 24, and npm.
