from datetime import datetime, timezone

from sqlalchemy import text

from app.extensions import db


class SavingsGoal(db.Model):
    __tablename__ = 'savings_goal'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey('user.id', ondelete='RESTRICT'),
        nullable=False, index=True,
    )
    name = db.Column(db.String(120), nullable=False)
    target_amount = db.Column(db.Numeric(15, 2), nullable=False)
    currency = db.Column(db.String(3), nullable=False)
    deadline = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(10), nullable=False, default='active')
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    user = db.relationship('User', back_populates='savings_goals')
    contributions = db.relationship(
        'SavingsContribution', back_populates='goal', passive_deletes='all',
    )
    __table_args__ = (
        db.CheckConstraint('target_amount > 0', name='check_savings_goal_target_positive'),
        db.CheckConstraint(
            "status IN ('active', 'completed', 'cancelled')",
            name='check_savings_goal_status',
        ),
        db.Index(
            'uq_savings_goal_one_active', 'user_id', unique=True,
            sqlite_where=text("status = 'active'"),
            postgresql_where=text("status = 'active'"),
        ),
    )


class SavingsContribution(db.Model):
    __tablename__ = 'savings_contribution'

    id = db.Column(db.Integer, primary_key=True)
    goal_id = db.Column(
        db.Integer, db.ForeignKey('savings_goal.id', ondelete='RESTRICT'),
        nullable=False, index=True,
    )
    amount = db.Column(db.Numeric(15, 2), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey('account.id', ondelete='RESTRICT'), nullable=True, index=True)
    account = db.relationship('Account')
    contributed_on = db.Column(db.Date, nullable=False)
    note = db.Column(db.String(500), nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    goal = db.relationship('SavingsGoal', back_populates='contributions')
    __table_args__ = (
        db.CheckConstraint('amount > 0', name='check_savings_contribution_positive'),
    )
