from app.extensions import db


class RecurringExpense(db.Model):
    __tablename__ = 'recurring_expense'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
    account_id = db.Column(db.Integer, db.ForeignKey('account.id', ondelete='RESTRICT'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id', ondelete='RESTRICT'), nullable=False)
    amount = db.Column(db.Numeric(15, 2), nullable=False)
    description = db.Column(db.String(100), nullable=False)
    billing_day = db.Column(db.Integer, nullable=False)
    starts_on = db.Column(db.Date, nullable=False)
    next_due_on = db.Column(db.Date, nullable=False)
    active = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true())
    account = db.relationship('Account')
    category = db.relationship('Category')
    __table_args__ = (
        db.CheckConstraint('amount > 0', name='ck_recurring_expense_amount'),
        db.CheckConstraint('billing_day BETWEEN 1 AND 31', name='ck_recurring_expense_day'),
    )


class RecurringExpenseOccurrence(db.Model):
    __tablename__ = 'recurring_expense_occurrence'
    recurring_id = db.Column(db.Integer, db.ForeignKey('recurring_expense.id', ondelete='CASCADE'), primary_key=True)
    month = db.Column(db.Date, primary_key=True)
    transaction_id = db.Column(db.Integer, db.ForeignKey('transaction.id', ondelete='CASCADE'), nullable=False, unique=True)
    rule = db.relationship('RecurringExpense')
    transaction = db.relationship('Transaction', backref=db.backref('recurring_occurrence', uselist=False))
