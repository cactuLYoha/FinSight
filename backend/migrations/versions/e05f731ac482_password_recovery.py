"""Add password recovery and revocable authentication versions."""
from alembic import op
import sqlalchemy as sa

revision = 'e05f731ac482'
down_revision = 'd94e62fa0315'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('user', sa.Column('auth_version', sa.Integer(), nullable=False, server_default='0'))
    with op.batch_alter_table('verification_challenge') as batch:
        batch.drop_constraint('ck_verification_purpose', type_='check')
        batch.create_check_constraint('ck_verification_purpose', "purpose IN ('register', 'login', 'password_reset')")
    op.create_table('password_reset_budget',
        sa.Column('email_key', sa.String(64), primary_key=True),
        sa.Column('window_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('resend_after', sa.DateTime(timezone=True), nullable=False),
        sa.Column('count', sa.Integer(), nullable=False),
    )


def downgrade():
    op.drop_table('password_reset_budget')
    op.execute("DELETE FROM verification_challenge WHERE purpose = 'password_reset'")
    with op.batch_alter_table('verification_challenge') as batch:
        batch.drop_constraint('ck_verification_purpose', type_='check')
        batch.create_check_constraint('ck_verification_purpose', "purpose IN ('register', 'login')")
    op.drop_column('user', 'auth_version')
