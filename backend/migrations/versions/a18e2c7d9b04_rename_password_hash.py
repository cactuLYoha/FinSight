"""Correct the password hash column name without changing stored hashes."""
from alembic import op
import sqlalchemy as sa


revision = 'a18e2c7d9b04'
down_revision = 'f03a9b8c721d'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        'user',
        'pasword_hash',
        new_column_name='password_hash',
        existing_type=sa.String(255),
        existing_nullable=False,
    )


def downgrade():
    op.alter_column(
        'user',
        'password_hash',
        new_column_name='pasword_hash',
        existing_type=sa.String(255),
        existing_nullable=False,
    )
