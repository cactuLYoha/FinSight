"""Link savings contributions to their source accounts."""
from alembic import op
import sqlalchemy as sa

revision = 'c41a7ef89206'
down_revision = 'b39d6a2ef105'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('savings_contribution') as batch:
        batch.add_column(sa.Column('account_id', sa.Integer(), nullable=True))
        batch.create_foreign_key('fk_savings_contribution_account_id', 'account', ['account_id'], ['id'], ondelete='RESTRICT')
        batch.create_index('ix_savings_contribution_account_id', ['account_id'])


def downgrade():
    with op.batch_alter_table('savings_contribution') as batch:
        batch.drop_index('ix_savings_contribution_account_id')
        batch.drop_constraint('fk_savings_contribution_account_id', type_='foreignkey')
        batch.drop_column('account_id')
