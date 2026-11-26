from datetime import timedelta
import hashlib
import hmac
import math
import re
import secrets

from flask import current_app
from sqlalchemy import func, select, update

from app.extensions import db
from app.models.user import User
from app.models.verification import VerificationChallenge, VerificationSend, TrustedDevice, utcnow
from app.services.gmail_service import MailDeliveryError


OTP_SECONDS = 600
TRUST_SECONDS = 90 * 24 * 60 * 60
PENDING_COOKIE = 'finsight_verification'
TRUST_COOKIE = 'finsight_trusted_device'
AUTH_COOKIE_PATH = '/api/auth/'


class VerificationError(ValueError):
    def __init__(self, code, status=400, retry_after=None):
        self.code = code
        self.status = status
        self.retry_after = retry_after
        super().__init__(code)


def aware(value):
    return value.replace(tzinfo=utcnow().tzinfo) if value.tzinfo is None else value


def digest(token):
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def code_digest(challenge, code):
    key = current_app.config.get('SECRET_KEY')
    if not key:
        raise RuntimeError('SECRET_KEY is required for verification.')
    return hmac.new(
        key.encode() if isinstance(key, str) else key,
        f'email-otp:{challenge.token_hash}:{challenge.purpose}:{code}'.encode(),
        hashlib.sha256,
    ).hexdigest()


def _lock_user(user_id):
    return db.session.execute(
        select(User).where(User.id == user_id).with_for_update().execution_options(populate_existing=True),
    ).scalar_one()


def _challenge(token, lock=False, purpose=None):
    if not token or len(token) > 128:
        raise VerificationError('verification_not_found', 404)
    challenge = db.session.get(VerificationChallenge, digest(token))
    if challenge is None:
        raise VerificationError('verification_not_found', 404)
    if (purpose is not None and challenge.purpose != purpose) or (purpose is None and challenge.purpose not in ('login', 'register')):
        raise VerificationError('verification_not_found', 404)
    if lock:
        _lock_user(challenge.user_id)
        challenge = db.session.execute(
            select(VerificationChallenge).where(VerificationChallenge.token_hash == challenge.token_hash)
            .with_for_update().execution_options(populate_existing=True),
        ).scalar_one()
    if challenge.consumed_at is not None:
        raise VerificationError('verification_closed', 410)
    if aware(challenge.expires_at) <= utcnow():
        raise VerificationError('verification_expired', 410)
    return challenge


def _check_budget(user_id, now):
    oldest = db.session.scalar(select(func.min(VerificationSend.created_at)).where(
        VerificationSend.user_id == user_id, VerificationSend.created_at > now - timedelta(hours=1),
    ))
    count = db.session.scalar(select(func.count()).select_from(VerificationSend).where(
        VerificationSend.user_id == user_id, VerificationSend.created_at > now - timedelta(hours=1),
    ))
    if count >= 5:
        seconds = max(1, math.ceil((aware(oldest) + timedelta(hours=1) - now).total_seconds()))
        raise VerificationError('verification_rate_limited', 429, seconds)


def begin(user, purpose, transport):
    now = utcnow()
    _lock_user(user.id)
    _check_budget(user.id, now)
    token = secrets.token_urlsafe(32)
    challenge = VerificationChallenge(
        token_hash=digest(token), user_id=user.id, purpose=purpose, transport=transport,
        expires_at=now + timedelta(seconds=OTP_SECONDS), resend_after=now,
    )
    db.session.add(challenge)
    db.session.commit()
    return token


def state(token, purpose=None):
    challenge = _challenge(token, purpose=purpose)
    user = db.session.get(User, challenge.user_id)
    local, domain = user.email.rsplit('@', 1)
    return {
        'verification_required': True,
        'masked_email': local[:1] + '***@' + domain,
        'expires_at': aware(challenge.expires_at).isoformat(),
        'resend_available_at': aware(challenge.resend_after).isoformat(),
        'delivery_ready': challenge.code_hash is not None,
    }


def send_code(token, purpose=None):
    now = utcnow()
    challenge = _challenge(token, lock=True, purpose=purpose)
    if aware(challenge.resend_after) > now:
        raise VerificationError('verification_cooldown', 429, max(1, math.ceil((aware(challenge.resend_after) - now).total_seconds())))
    if challenge.sending_until and aware(challenge.sending_until) > now:
        raise VerificationError('verification_sending', 429, 30)
    _check_budget(challenge.user_id, now)
    user = db.session.get(User, challenge.user_id)
    recipient = user.email
    code = f'{secrets.randbelow(1_000_000):06d}'
    hashed_code = code_digest(challenge, code)
    challenge.generation += 1
    generation = challenge.generation
    challenge.resend_after = now + timedelta(seconds=60)
    challenge.sending_until = now + timedelta(seconds=30)
    db.session.add(VerificationSend(user_id=user.id, created_at=now))
    db.session.commit()

    # Do not hold a user-row lock while calling Google.
    try:
        sender = current_app.extensions['mail_sender']
        if purpose == 'password_reset':
            sender.send_password_reset(recipient, code)
        else:
            sender.send_verification(recipient, code)
    except MailDeliveryError:
        db.session.execute(update(VerificationChallenge).where(
            VerificationChallenge.token_hash == digest(token),
            VerificationChallenge.generation == generation,
        ).values(sending_until=None))
        db.session.commit()
        raise VerificationError('email_delivery_failed', 503) from None

    challenge = _challenge(token, lock=True, purpose=purpose)
    if challenge.generation != generation:
        raise VerificationError('verification_closed', 410)
    challenge.code_hash = hashed_code
    challenge.expires_at = utcnow() + timedelta(seconds=OTP_SECONDS)
    challenge.sending_until = None
    db.session.commit()
    return state(token, purpose=purpose)


def confirm(token, code, trust_device):
    if not isinstance(code, str) or re.fullmatch(r'[0-9]{6}', code) is None:
        raise VerificationError('invalid_code')
    if not isinstance(trust_device, bool):
        raise VerificationError('invalid_trust_choice')
    challenge = _challenge(token, lock=True)
    if not challenge.code_hash:
        raise VerificationError('email_delivery_failed', 503)
    if not hmac.compare_digest(challenge.code_hash, code_digest(challenge, code)):
        challenge.attempts += 1
        if challenge.attempts >= 5:
            challenge.consumed_at = utcnow()
        db.session.commit()
        raise VerificationError('verification_closed' if challenge.attempts >= 5 else 'invalid_code')
    now = utcnow()
    challenge.consumed_at = now
    user = db.session.get(User, challenge.user_id)
    if not user.is_email_verified:
        user.is_email_verified = True
        user.email_verified_at = now
    trusted_token = None
    if trust_device:
        trusted_token = secrets.token_urlsafe(32)
        db.session.add(TrustedDevice(
            token_hash=digest(trusted_token), user_id=user.id,
            expires_at=now + timedelta(seconds=TRUST_SECONDS),
        ))
    transport = challenge.transport
    db.session.commit()
    return user, transport, trusted_token


def is_trusted(user, token):
    if not user.is_email_verified or not token or len(token) > 128:
        return False
    device = db.session.get(TrustedDevice, digest(token))
    return bool(device and device.user_id == user.id and device.revoked_at is None and aware(device.expires_at) > utcnow())


def revoke_trust(token):
    if token and len(token) <= 128:
        db.session.execute(update(TrustedDevice).where(
            TrustedDevice.token_hash == digest(token), TrustedDevice.revoked_at.is_(None),
        ).values(revoked_at=utcnow()))
        db.session.commit()
