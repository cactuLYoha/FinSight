import decimal
from datetime import datetime , timezone


from app.extensions import db


class Account(db.Model):
    __tablename__ = 'account'

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey('user.id'),
        nullable=False
    )
    name = db.Column(db.String(120), nullable=False)

    account_type = db.Column(
        db.String(30),
        nullable=False
    )

    currency = db.Column(
        db.String(3),
        nullable=False,
        default='USD'
    )
    balance = db.Column(
        db.Numeric(15 , 2),
        nullable=False,
        default= decimal.Decimal("0.00")
    )
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )
    created_by = db.Column(
        db.DateTime(timezone=True),
        default = lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = db.relationship('User', back_populates='accounts')
    transactions = db.relationship(
        'Transaction',
        back_populates='account'
    )
