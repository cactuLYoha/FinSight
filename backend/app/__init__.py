from flask import Flask
from app.config import Config
from app.extensions import db, migrate, jwt
from app.models import transaction
from app.models.user import User
from app.models.account import Account
from app.models.category import Category
from app.models.transaction import Transaction
from app.models.statement_import import StatementImport
from app.models.savings_goal import SavingsGoal, SavingsContribution
from app.models.verification import VerificationChallenge, VerificationSend, TrustedDevice
from app.models.subscription import Subscription
from app.models.recurring_expense import RecurringExpense, RecurringExpenseOccurrence
from app.models.recurring_income import RecurringIncome, RecurringIncomeOccurrence
def create_app(test_config=None):

    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config is not None:
        app.config.update(test_config)
    from app.auth_security import configure_auth_security
    configure_auth_security(app)
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    from app.services.aut_service import get_user_by_identity

    @jwt.token_in_blocklist_loader
    def session_revoked(header, payload):
        user = get_user_by_identity(payload['sub'])
        return user is None or payload.get('auth_version', 0) != user.auth_version
    from app.services.gmail_service import GmailSender
    sender = app.config.get('MAIL_SENDER')
    if sender is not None and not app.testing:
        raise ValueError('Injected mail senders are only allowed in tests.')
    app.extensions['mail_sender'] = sender or GmailSender(
        app.config['GMAIL_TOKEN_FILE'], app.config['GMAIL_SENDER'],
    )

    from app.routes.auth import auth_bp
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    from app.routes.password import password_bp
    app.register_blueprint(password_bp, url_prefix='/api/auth/password')
    from app.routes.savings import savings_bp
    app.register_blueprint(savings_bp, url_prefix='/api/savings')
    from app.routes.analytics import analytics_bp
    app.register_blueprint(analytics_bp, url_prefix='/api/analytics')
    from app.routes.subscriptions import subscriptions_bp
    app.register_blueprint(subscriptions_bp, url_prefix='/api/subscriptions')
    from app.routes.expenses import expenses_bp
    app.register_blueprint(expenses_bp, url_prefix='/api/expenses')
    from app.routes.accounts import accounts_bp
    app.register_blueprint(accounts_bp, url_prefix='/api/accounts')
    from app.routes.statements import statements_bp
    app.register_blueprint(statements_bp, url_prefix='/api/statements')
    from app.routes.health import health_bp
    app.register_blueprint(health_bp, url_prefix='/api')
    from app.cors import configure_cors
    configure_cors(app)

    return app
