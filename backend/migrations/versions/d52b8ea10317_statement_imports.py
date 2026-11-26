"""Track PDF imports to prevent importing the same file twice per account."""
from alembic import op
import sqlalchemy as sa

revision = 'd52b8ea10317'
down_revision = 'c41a7ef89206'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'statement_import',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('account_id', sa.Integer(), sa.ForeignKey('account.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('file_hash', sa.String(64), nullable=False),
        sa.Column('row_count', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('account_id', 'file_hash', name='uq_statement_import_account_file'),
    )


def downgrade():
    op.drop_table('statement_import')
