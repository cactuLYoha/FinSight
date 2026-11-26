"""Add email verification, OTP challenges, and trusted browsers."""
from alembic import op
import sqlalchemy as sa

revision = 'd94e62fa0315'
down_revision = 'c83d51e9f204'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('user', sa.Column('is_email_verified', sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column('user', sa.Column('email_verified_at', sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        'verification_challenge',
        sa.Column('token_hash', sa.String(64), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('user.id', ondelete='CASCADE'), nullable=False),
        sa.Column('purpose', sa.String(16), nullable=False),
        sa.Column('transport', sa.String(8), nullable=False),
        sa.Column('code_hash', sa.String(64)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('resend_after', sa.DateTime(timezone=True), nullable=False),
        sa.Column('sending_until', sa.DateTime(timezone=True)),
        sa.Column('generation', sa.Integer(), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('consumed_at', sa.DateTime(timezone=True)),
        sa.CheckConstraint('attempts >= 0 AND attempts <= 5', name='ck_verification_attempts'),
        sa.CheckConstraint("transport IN ('cookie', 'bearer')", name='ck_verification_transport'),
        sa.CheckConstraint("purpose IN ('register', 'login')", name='ck_verification_purpose'),
    )
    op.create_index('ix_verification_challenge_user_id', 'verification_challenge', ['user_id'])
    op.create_table(
        'verification_send',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('user.id', ondelete='CASCADE'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_verification_send_user_created', 'verification_send', ['user_id', 'created_at'])
    op.create_table(
        'trusted_device',
        sa.Column('token_hash', sa.String(64), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('user.id', ondelete='CASCADE'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True)),
    )
    op.create_index('ix_trusted_device_user_id', 'trusted_device', ['user_id'])


def downgrade():
    op.drop_table('trusted_device')
    op.drop_table('verification_send')
    op.drop_table('verification_challenge')
    # Modern SQLite supports DROP COLUMN without rebuilding the referenced user
    # table, so existing account foreign keys remain intact during rollback.
    op.drop_column('user', 'email_verified_at')
    op.drop_column('user', 'is_email_verified')
