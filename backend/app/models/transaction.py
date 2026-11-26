from datetime import datetime , timezone

from app.extensions import db


class Transaction(db.Model):
    __tablename__ = 'transaction'
    id = db.Column(
        db.Integer,
        primary_key = True,
    )
    account_id = db.Column(
        db.Integer,
        db.ForeignKey('account.id'),
        nullable = False,
        index = True,
    )
    amount = db.Column(
        db.Numeric(15, 2),
        nullable=False
    )
    transaction_type = db.Column(
        db.String(10),
        nullable = False,
    )
    description = db.Column(
        db.String(100),
        nullable = False,

    )
    category_id = db.Column(
        db.Integer,
        db.ForeignKey(
            'category.id',
            name='fk_transaction_category_id_category',
            ondelete='RESTRICT',
        ),
        nullable=True,
        index=True,
    )
    category = db.relationship('Category', back_populates='transactions')
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable = False,
        default=lambda: datetime.now(timezone.utc),
    )
    account = db.relationship(
        "Account",
        back_populates = "transactions",
    )
    __table_args__ = (
        db.CheckConstraint(
            "transaction_type IN ('income' , 'expense')",
            name = "check_transaction_type",
        ),
        db.CheckConstraint(
            "amount > 0",
            name = "check_transaction_amount_positive",
        ),
        db.CheckConstraint(
            "transaction_type != 'expense' OR category_id IS NOT NULL",
            name='check_transaction_expense_category_required',
        )
    )
    def __repr__(self):
        return (f"<Transaction {self.id} "
                f"amount:{self.amount} "
                f"transaction type : {self.transaction_type} "
                )
