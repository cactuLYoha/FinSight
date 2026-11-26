import os
import re
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url

from app import create_app
from app.config import Config
from app.extensions import db
from tests.auth_support import FakeMailer


def pytest_addoption(parser):
    parser.addoption(
        '--db-backend', choices=('sqlite', 'postgresql'), default='sqlite',
        help='Database used by model, service, authentication, and migration tests.',
    )


def pytest_configure(config):
    config.addinivalue_line('markers', 'postgresql: requires PostgreSQL type semantics')


def pytest_collection_modifyitems(config, items):
    if config.getoption('--db-backend') != 'postgresql':
        skip = pytest.mark.skip(reason='Requires --db-backend=postgresql')
        for item in items:
            if 'postgresql' in item.keywords:
                item.add_marker(skip)


@pytest.fixture(scope='session')
def db_backend(pytestconfig):
    return pytestconfig.getoption('--db-backend')


@pytest.fixture(scope='session')
def postgres_database_factory(db_backend):
    """Allocate only disposable databases, never tables in the configured app DB."""
    if db_backend != 'postgresql':
        yield None
        return

    configured_url = os.getenv('TEST_DATABASE_URL') or Config.SQLALCHEMY_DATABASE_URI
    if not configured_url:
        raise pytest.UsageError('PostgreSQL tests require TEST_DATABASE_URL or DATABASE_URL.')
    server_url = make_url(configured_url)
    if server_url.get_backend_name() != 'postgresql':
        raise pytest.UsageError('PostgreSQL tests require a PostgreSQL connection URL.')
    admin = create_engine(
        server_url.set(database='postgres'), isolation_level='AUTOCOMMIT',
        connect_args={'connect_timeout': 5},
    )
    allocated = []

    def allocate():
        name = 'finsight_test_' + uuid4().hex
        quoted_name = admin.dialect.identifier_preparer.quote(name)
        with admin.connect() as connection:
            connection.exec_driver_sql('CREATE DATABASE ' + quoted_name)
        allocated.append(name)
        return server_url.set(database=name).render_as_string(hide_password=False)

    try:
        yield allocate
    finally:
        try:
            with admin.connect() as connection:
                for name in reversed(allocated):
                    if not re.fullmatch(r'finsight_test_[0-9a-f]{32}', name):
                        raise RuntimeError('Refusing to remove an unexpected database name.')
                    quoted_name = admin.dialect.identifier_preparer.quote(name)
                    connection.exec_driver_sql('DROP DATABASE ' + quoted_name)
        finally:
            admin.dispose()


@pytest.fixture(scope='session')
def model_database_url(db_backend, postgres_database_factory):
    if db_backend == 'sqlite':
        return 'sqlite://'
    return postgres_database_factory()


@pytest.fixture
def migration_database_url(db_backend, postgres_database_factory, tmp_path):
    if db_backend == 'sqlite':
        return f"sqlite:///{(tmp_path / 'migration.sqlite').as_posix()}"
    return postgres_database_factory()


def _test_app(database_url):
    settings = {
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': database_url,
        'JWT_SECRET_KEY': 'test-only-secret-key-at-least-32-bytes',
        'SECRET_KEY': 'test-only-otp-secret-key-at-least-32-bytes',
        'MAIL_SENDER': FakeMailer(),
    }
    if make_url(database_url).get_backend_name() == 'postgresql':
        settings['SQLALCHEMY_ENGINE_OPTIONS'] = {
            'connect_args': {'options': '-c timezone=UTC', 'connect_timeout': 5},
        }
    app = create_app(settings)
    with app.app_context():
        if db.engine.dialect.name == 'sqlite':
            @event.listens_for(db.engine, 'connect')
            def enable_foreign_keys(connection, _):
                cursor = connection.cursor()
                cursor.execute('PRAGMA foreign_keys = ON')
                cursor.close()
    return app


@pytest.fixture
def app(model_database_url):
    app = _test_app(model_database_url)
    with app.app_context():
        try:
            db.create_all()
            yield app
        finally:
            db.session.remove()
            try:
                db.drop_all()
            finally:
                db.engine.dispose()


@pytest.fixture
def migration_app(migration_database_url):
    app = _test_app(migration_database_url)
    with app.app_context():
        try:
            yield app
        finally:
            db.session.remove()
            db.engine.dispose()


@pytest.fixture
def client(app):
    return app.test_client()
