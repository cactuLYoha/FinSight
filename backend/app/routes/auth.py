from datetime import timedelta

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import create_access_token, jwt_required, set_access_cookies, unset_access_cookies
from marshmallow import ValidationError

from app.auth_security import COOKIE_LOGIN_SECONDS, check_session_origin
from app.extensions import db
from app.routes.auth_helpers import current_verified_user
from app.schemas.user_schema import RegisterSchema, UserSchema, LoginSchema
from app.services.aut_service import register_user, EmailAlreadyRegistered, authenticate_user
from app.services import verification_service as verification

auth_bp = Blueprint('auth', __name__)
register_schema = RegisterSchema()
login_schema = LoginSchema()
user_schema = UserSchema()


@auth_bp.after_request
def prevent_auth_caching(response):
    response.headers['Cache-Control'] = 'no-store'
    return response


def set_private_cookie(response, name, value, seconds):
    response.set_cookie(
        name, value, max_age=seconds, httponly=True, samesite='Lax',
        secure=current_app.config['JWT_COOKIE_SECURE'], path=verification.AUTH_COOKIE_PATH,
    )


def clear_private_cookie(response, name):
    response.delete_cookie(
        name, path=verification.AUTH_COOKIE_PATH, httponly=True,
        samesite='Lax', secure=current_app.config['JWT_COOKIE_SECURE'],
    )


def complete_login(user, transport, trusted_token=None, preserve_trust=False):
    kwargs = {'expires_delta': timedelta(seconds=COOKIE_LOGIN_SECONDS)} if transport == 'cookie' else {}
    token = create_access_token(identity=str(user.id), additional_claims={'auth_complete': True, 'auth_version': user.auth_version}, **kwargs)
    if transport == 'cookie':
        response = jsonify(user=user_schema.dump(user))
        set_access_cookies(response, token, max_age=COOKIE_LOGIN_SECONDS)
    else:
        response = jsonify(access_token=token)
    clear_private_cookie(response, verification.PENDING_COOKIE)
    if not preserve_trust:
        verification.revoke_trust(request.cookies.get(verification.TRUST_COOKIE))
        if trusted_token:
            set_private_cookie(response, verification.TRUST_COOKIE, trusted_token, verification.TRUST_SECONDS)
        else:
            clear_private_cookie(response, verification.TRUST_COOKIE)
    return response


def pending_login(user, purpose, transport, status):
    raw = verification.begin(user, purpose, transport)
    try:
        metadata = verification.send_code(raw)
        response = jsonify(user=user_schema.dump(user), **metadata) if purpose == 'register' else jsonify(**metadata)
        response.status_code = status
    except verification.VerificationError as error:
        db.session.rollback()
        response = jsonify(
            code=error.code, account_created=purpose == 'register',
            **verification.state(raw),
        )
        response.status_code = error.status
        if error.retry_after:
            response.headers['Retry-After'] = str(error.retry_after)
    # Pending context is not a login token. It also allows retry after a delivery outage.
    set_private_cookie(response, verification.PENDING_COOKIE, raw, verification.OTP_SECONDS)
    return response


@auth_bp.errorhandler(verification.VerificationError)
def verification_error(error):
    db.session.rollback()
    response = jsonify(code=error.code)
    response.status_code = error.status
    if error.retry_after:
        response.headers['Retry-After'] = str(error.retry_after)
    return response


@auth_bp.post('/register')
def register():
    try:
        data = register_schema.load(request.get_json())
    except ValidationError as error:
        return jsonify(message=error.messages), 400
    try:
        user = register_user(email=data['email'], password=data['password'])
    except EmailAlreadyRegistered as error:
        return jsonify(message=str(error)), 409
    return pending_login(user, 'register', 'cookie', 201)


def login_response(transport):
    try:
        data = login_schema.load(request.get_json())
    except ValidationError as error:
        return jsonify(message=error.messages), 400
    user = authenticate_user(email=data['email'], password=data['password'])
    if user is None:
        return jsonify(message='Invalid email or password'), 401
    if verification.is_trusted(user, request.cookies.get(verification.TRUST_COOKIE)):
        return complete_login(user, transport, preserve_trust=True)
    return pending_login(user, 'login', transport, 202)


@auth_bp.post('/login')
def login():
    # Bearer clients must also complete OTP; the transport cannot be changed at confirmation.
    return login_response('bearer')


@auth_bp.post('/session')
def create_session():
    denied = check_session_origin()
    return denied if denied is not None else login_response('cookie')


@auth_bp.get('/verification')
def verification_state():
    return jsonify(**verification.state(request.cookies.get(verification.PENDING_COOKIE)))


@auth_bp.post('/verification/resend')
def resend_verification():
    denied = check_session_origin()
    if denied is not None:
        return denied
    raw = request.cookies.get(verification.PENDING_COOKIE)
    response = jsonify(**verification.send_code(raw))
    set_private_cookie(response, verification.PENDING_COOKIE, raw, verification.OTP_SECONDS)
    return response


@auth_bp.post('/verification/confirm')
def confirm_verification():
    denied = check_session_origin()
    if denied is not None:
        return denied
    data = request.get_json()
    if not isinstance(data, dict) or set(data) - {'code', 'trust_device'}:
        return jsonify(code='invalid_verification_payload'), 400
    user, transport, trusted = verification.confirm(
        request.cookies.get(verification.PENDING_COOKIE), data.get('code'), data.get('trust_device', False),
    )
    return complete_login(user, transport, trusted)


@auth_bp.delete('/session')
def delete_session():
    denied = check_session_origin()
    if denied is not None:
        return denied
    verification.revoke_trust(request.cookies.get(verification.TRUST_COOKIE))
    response = jsonify()
    unset_access_cookies(response)
    clear_private_cookie(response, verification.TRUST_COOKIE)
    clear_private_cookie(response, verification.PENDING_COOKIE)
    return response, 204


@auth_bp.get('/me')
@jwt_required()
def me():
    user, error = current_verified_user()
    return error if error is not None else jsonify(user=user_schema.dump(user))
