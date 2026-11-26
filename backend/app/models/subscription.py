from app.extensions import db


class Subscription(db.Model):
    __tablename__ = 'subscription'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    amount = db.Column(db.Numeric(15, 2), nullable=False)
    currency = db.Column(db.String(3), nullable=False)
    billing_day = db.Column(db.Integer, nullable=False)
    __table_args__ = (
        db.CheckConstraint('amount > 0', name='ck_subscription_amount'),
        db.CheckConstraint('billing_day >= 1 AND billing_day <= 31', name='ck_subscription_day'),
    )

    def to_dict(self):
        return dict(id=self.id, name=self.name, amount=str(self.amount), currency=self.currency, billing_day=self.billing_day)
