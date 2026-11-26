from app.extensions import db


class RecurringIncome(db.Model):
    __tablename__ = 'recurring_income'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
    account_id = db.Column(db.Integer, db.ForeignKey('account.id', ondelete='RESTRICT'), nullable=False)
    amount = db.Column(db.Numeric(15, 2), nullable=False)
    description = db.Column(db.String(100), nullable=False)
    billing_day = db.Column(db.Integer, nullable=False)
    starts_on = db.Column(db.Date, nullable=False)
    next_due_on = db.Column(db.Date, nullable=False)
    active = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true())
    __table_args__ = (
        db.CheckConstraint('amount > 0', name='ck_recurring_income_amount'),
        db.CheckConstraint('billing_day BETWEEN 1 AND 31', name='ck_recurring_income_day'),
    )


class RecurringIncomeOccurrence(db.Model):
    __tablename__ = 'recurring_income_occurrence'
    recurring_id = db.Column(db.Integer, db.ForeignKey('recurring_income.id', ondelete='CASCADE'), primary_key=True)
    month = db.Column(db.Date, primary_key=True)
    transaction_id = db.Column(db.Integer, db.ForeignKey('transaction.id', ondelete='CASCADE'), nullable=False, unique=True)
    rule = db.relationship('RecurringIncome')
    transaction = db.relationship('Transaction', backref=db.backref('recurring_income_occurrence', uselist=False))
