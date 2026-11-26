"""Small scheduler for local Compose; restart-safe through persisted due dates."""
import time

from sqlalchemy import select
from app import create_app
from app.extensions import db
from app.models.recurring_expense import RecurringExpense
from app.models.recurring_income import RecurringIncome
from app.services.recurring_expense_service import materialize_due, today


def main():
    app = create_app()
    while True:
        with app.app_context():
            try:
                users = list(db.session.scalars(select(RecurringExpense.user_id).where(
                    RecurringExpense.active.is_(True), RecurringExpense.next_due_on <= today(),
                ).distinct()))
                users = sorted(set(users) | set(db.session.scalars(select(RecurringIncome.user_id).where(
                    RecurringIncome.active.is_(True), RecurringIncome.next_due_on <= today(),
                ).distinct())))
                db.session.rollback()
                for user_id in users:
                    try:
                        materialize_due(user_id)
                        db.session.commit()
                    except Exception:
                        db.session.rollback()
                        app.logger.exception('Unable to process recurring expenses for user %s', user_id)
            except Exception:
                db.session.rollback()
                app.logger.exception('Recurring expense scheduler failed')
        time.sleep(60)


if __name__ == '__main__':
    main()
