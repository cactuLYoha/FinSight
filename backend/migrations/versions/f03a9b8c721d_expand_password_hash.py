"""Expand password hash storage for Werkzeug hashes."""
from alembic import op
import sqlalchemy as sa

revision = 'f03a9b8c721d'
down_revision = 'e4c3fa900e2c'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('user') as batch_op:
        batch_op.alter_column('pasword_hash', existing_type=sa.String(120),
                              type_=sa.String(255), existing_nullable=False)


def downgrade():
    with op.batch_alter_table('user') as batch_op:
        batch_op.alter_column('pasword_hash', existing_type=sa.String(255),
                              type_=sa.String(120), existing_nullable=False)
