"""Persist recurring income schedules and unique occurrences."""
from alembic import op
import sqlalchemy as sa

revision = 'b39d6a2ef105'
down_revision = 'a27b953ce604'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('recurring_income',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('user.id', ondelete='CASCADE'), nullable=False),
        sa.Column('account_id', sa.Integer(), sa.ForeignKey('account.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('amount', sa.Numeric(15, 2), nullable=False),
        sa.Column('description', sa.String(100), nullable=False),
        sa.Column('billing_day', sa.Integer(), nullable=False),
        sa.Column('starts_on', sa.Date(), nullable=False),
        sa.Column('next_due_on', sa.Date(), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.CheckConstraint('amount > 0', name='ck_recurring_income_amount'),
        sa.CheckConstraint('billing_day BETWEEN 1 AND 31', name='ck_recurring_income_day'),
    )
    op.create_index('ix_recurring_income_user_id', 'recurring_income', ['user_id'])
    op.create_table('recurring_income_occurrence',
        sa.Column('recurring_id', sa.Integer(), sa.ForeignKey('recurring_income.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('month', sa.Date(), primary_key=True),
        sa.Column('transaction_id', sa.Integer(), sa.ForeignKey('transaction.id', ondelete='CASCADE'), nullable=False, unique=True),
    )


def downgrade():
    op.drop_table('recurring_income_occurrence')
    op.drop_table('recurring_income')
