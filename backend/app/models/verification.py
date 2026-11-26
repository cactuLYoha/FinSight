from datetime import datetime, timezone

from app.extensions import db


def utcnow():
    return datetime.now(timezone.utc)


class VerificationChallenge(db.Model):
    __tablename__ = 'verification_challenge'
    token_hash = db.Column(db.String(64), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
    purpose = db.Column(db.String(16), nullable=False)
    transport = db.Column(db.String(8), nullable=False)
    code_hash = db.Column(db.String(64), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    resend_after = db.Column(db.DateTime(timezone=True), nullable=False)
    sending_until = db.Column(db.DateTime(timezone=True), nullable=True)
    generation = db.Column(db.Integer, nullable=False, default=0)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    consumed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    __table_args__ = (
        db.CheckConstraint('attempts >= 0 AND attempts <= 5', name='ck_verification_attempts'),
        db.CheckConstraint("transport IN ('cookie', 'bearer')", name='ck_verification_transport'),
        db.CheckConstraint("purpose IN ('register', 'login', 'password_reset')", name='ck_verification_purpose'),
    )


class VerificationSend(db.Model):
    __tablename__ = 'verification_send'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    __table_args__ = (db.Index('ix_verification_send_user_created', 'user_id', 'created_at'),)


class TrustedDevice(db.Model):
    __tablename__ = 'trusted_device'
    token_hash = db.Column(db.String(64), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    revoked_at = db.Column(db.DateTime(timezone=True), nullable=True)


class PasswordResetBudget(db.Model):
    __tablename__ = 'password_reset_budget'
    email_key = db.Column(db.String(64), primary_key=True)
    window_start = db.Column(db.DateTime(timezone=True), nullable=False)
    resend_after = db.Column(db.DateTime(timezone=True), nullable=False)
    count = db.Column(db.Integer, nullable=False, default=0)
