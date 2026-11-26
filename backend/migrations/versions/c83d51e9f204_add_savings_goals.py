"""Add manual savings goals and contributions."""
from alembic import op
import sqlalchemy as sa


revision = 'c83d51e9f204'
down_revision = 'b72c41d8e903'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'savings_goal',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(120), nullable=False),
        sa.Column('target_amount', sa.Numeric(15, 2), nullable=False),
        sa.Column('currency', sa.String(3), nullable=False),
        sa.Column('deadline', sa.Date(), nullable=False),
        sa.Column('status', sa.String(10), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='RESTRICT'),
        sa.CheckConstraint('target_amount > 0', name='check_savings_goal_target_positive'),
        sa.CheckConstraint(
            "status IN ('active', 'completed', 'cancelled')",
            name='check_savings_goal_status',
        ),
    )
    op.create_index('ix_savings_goal_user_id', 'savings_goal', ['user_id'])
    op.create_index(
        'uq_savings_goal_one_active', 'savings_goal', ['user_id'], unique=True,
        sqlite_where=sa.text("status = 'active'"),
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_table(
        'savings_contribution',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('goal_id', sa.Integer(), nullable=False),
        sa.Column('amount', sa.Numeric(15, 2), nullable=False),
        sa.Column('contributed_on', sa.Date(), nullable=False),
        sa.Column('note', sa.String(500), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['goal_id'], ['savings_goal.id'], ondelete='RESTRICT'),
        sa.CheckConstraint('amount > 0', name='check_savings_contribution_positive'),
    )
    op.create_index('ix_savings_contribution_goal_id', 'savings_contribution', ['goal_id'])


def downgrade():
    op.drop_index('ix_savings_contribution_goal_id', table_name='savings_contribution')
    op.drop_table('savings_contribution')
    op.drop_index('uq_savings_goal_one_active', table_name='savings_goal')
    op.drop_index('ix_savings_goal_user_id', table_name='savings_goal')
    op.drop_table('savings_goal')
