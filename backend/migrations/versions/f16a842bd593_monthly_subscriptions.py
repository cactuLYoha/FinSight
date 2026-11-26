"""User-owned monthly subscription plans."""
from alembic import op
import sqlalchemy as sa

revision = 'f16a842bd593'
down_revision = 'e05f731ac482'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('subscription',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('user.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(120), nullable=False),
        sa.Column('amount', sa.Numeric(15, 2), nullable=False),
        sa.Column('currency', sa.String(3), nullable=False),
        sa.Column('billing_day', sa.Integer(), nullable=False),
        sa.CheckConstraint('amount > 0', name='ck_subscription_amount'),
        sa.CheckConstraint('billing_day >= 1 AND billing_day <= 31', name='ck_subscription_day'),
    )
    op.create_index('ix_subscription_user_id', 'subscription', ['user_id'])


def downgrade():
    op.drop_table('subscription')
