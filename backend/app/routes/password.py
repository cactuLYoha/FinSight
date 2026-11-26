"""Password changes and email recovery never grant a login session."""
from datetime import timedelta
import hashlib
import hmac
import secrets

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt, jwt_required, unset_access_cookies
from itsdangerous import BadSignature, URLSafeTimedSerializer
from marshmallow import Schema, fields, validate, ValidationError
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.auth_security import check_session_origin
from app.extensions import db
from app.models.user import User
from app.models.verification import PasswordResetBudget, TrustedDevice, VerificationChallenge, utcnow
from app.routes.auth import clear_private_cookie, set_private_cookie, verification_error
from app.routes.auth_helpers import current_verified_user
from app.services import verification_service as verification

password_bp = Blueprint('password', __name__)
password_bp.register_error_handler(verification.VerificationError, verification_error)
RESET_COOKIE = 'finsight_password_reset'


class ChangeSchema(Schema):
    current_password = fields.Str(required=True, validate=validate.Length(min=1))
    new_password = fields.Str(required=True, validate=validate.Length(min=8, max=35))


class ResetSchema(Schema):
    code = fields.Str(required=True, validate=validate.Regexp(r'^[0-9]{6}$'))
    new_password = fields.Str(required=True, validate=validate.Length(min=8, max=35))


class EmailSchema(Schema):
    email = fields.Email(required=True, validate=validate.Length(max=120))


@password_bp.after_request
def no_cache(response):
    response.headers['Cache-Control'] = 'no-store'
    return response


@password_bp.before_request
def trusted_origin():
    return check_session_origin()


@password_bp.errorhandler(ValidationError)
def invalid_payload(error):
    db.session.rollback()
    return jsonify(code='invalid_password_payload', message=error.messages), 400


def load(schema):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValidationError('Expected an object.')
    return schema.load(data)


def replace_password(user, password):
    """Caller holds the user lock; all access is revoked in this transaction."""
    user.set_password(password)
    user.auth_version += 1
    now = utcnow()
    db.session.execute(update(TrustedDevice).where(
        TrustedDevice.user_id == user.id, TrustedDevice.revoked_at.is_(None),
    ).values(revoked_at=now))
    db.session.execute(update(VerificationChallenge).where(
        VerificationChallenge.user_id == user.id, VerificationChallenge.consumed_at.is_(None),
    ).values(consumed_at=now))
    db.session.commit()


def completed():
    response = jsonify()
    unset_access_cookies(response)
    for name in (RESET_COOKIE, verification.PENDING_COOKIE, verification.TRUST_COOKIE):
        clear_private_cookie(response, name)
    return response, 204


@password_bp.post('/change')
@jwt_required()
def change():
    data = load(ChangeSchema())
    user, error = current_verified_user()
    if error is not None:
        return error
    user = verification._lock_user(user.id)
    if get_jwt().get('auth_version', 0) != user.auth_version:
        db.session.rollback()
        return jsonify(code='session_revoked'), 401
    if not user.check_password(data['current_password']):
        db.session.rollback()
        return jsonify(code='incorrect_current_password'), 400
    replace_password(user, data['new_password'])
    return completed()


def serializer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'], salt='password-reset-context')


def context():
    try:
        return serializer().loads(request.cookies.get(RESET_COOKIE, ''), max_age=verification.OTP_SECONDS)
    except BadSignature:
        raise verification.VerificationError('verification_expired', 410) from None


def reserve_send(email):
    """Persist limits for unknown addresses too; serialize concurrent requests."""
    now = utcnow()
    key = hmac.new(str(current_app.config['SECRET_KEY']).encode(), email.encode(), hashlib.sha256).hexdigest()
    if db.session.get(PasswordResetBudget, key) is None:
        try:
            with db.session.begin_nested():
                db.session.add(PasswordResetBudget(email_key=key, window_start=now, resend_after=now, count=0))
                db.session.flush()
        except IntegrityError:
            pass  # Another request created this address's budget first.
    budget = db.session.execute(select(PasswordResetBudget).where(
        PasswordResetBudget.email_key == key,
    ).with_for_update().execution_options(populate_existing=True)).scalar_one()
    if verification.aware(budget.window_start) + timedelta(hours=1) <= now:
        budget.window_start, budget.count = now, 0
    allowed = budget.count < 5 and verification.aware(budget.resend_after) <= now
    if allowed:
        budget.count += 1
        budget.resend_after = now + timedelta(seconds=60)
    db.session.commit()
    return allowed


def deliver(email, token=None):
    allowed = reserve_send(email)
    raw = token or secrets.token_urlsafe(32)
    if allowed:
        user = db.session.scalar(select(User).where(User.email == email))
        if user is not None:
            try:
                if token is None:
                    raw = verification.begin(user, 'password_reset', 'cookie')
                verification.send_code(raw, purpose='password_reset')
            except verification.VerificationError:
                # Delivery outages and per-user limits must not disclose accounts.
                db.session.rollback()
    response = jsonify(message='Якщо акаунт існує, лист із кодом буде надіслано.', retry_after=60)
    signed = serializer().dumps({'email': email, 'token': raw})
    set_private_cookie(response, RESET_COOKIE, signed, verification.OTP_SECONDS)
    return response, 202


@password_bp.post('/reset/request')
def request_reset():
    data = load(EmailSchema())
    email = data['email'].strip().lower()
    try:
        pending = context()
    except verification.VerificationError:
        pending = {}
    return deliver(email, pending.get('token') if pending.get('email') == email else None)


@password_bp.post('/reset/resend')
def resend_reset():
    data = context()
    return deliver(data['email'], data['token'])


@password_bp.post('/reset/confirm')
def confirm_reset():
    data = load(ResetSchema())
    pending = context()
    try:
        challenge = verification._challenge(pending['token'], lock=True, purpose='password_reset')
    except verification.VerificationError:
        raise verification.VerificationError('invalid_code') from None
    if not challenge.code_hash or not hmac.compare_digest(
        challenge.code_hash, verification.code_digest(challenge, data['code']),
    ):
        challenge.attempts += 1
        if challenge.attempts >= 5:
            challenge.consumed_at = utcnow()
        db.session.commit()
        raise verification.VerificationError('invalid_code')
    user = db.session.get(User, challenge.user_id)
    replace_password(user, data['new_password'])
    return completed()
