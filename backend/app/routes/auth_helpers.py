from functools import wraps

from flask import jsonify
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required

from app.services.aut_service import get_user_by_identity


def current_verified_user():
    user = get_user_by_identity(get_jwt_identity())
    if user is None:
        return None, (jsonify(message='User not found'), 401)
    if not user.is_email_verified or get_jwt().get('auth_complete') is not True:
        return None, (jsonify(code='verification_required'), 403)
    return user, None


def authenticated(view):
    """Pass only an existing, verified, fully authenticated user's ID."""
    @wraps(view)
    def guarded(*args, **kwargs):
        user, error = current_verified_user()
        return error if error is not None else view(user.id, *args, **kwargs)
    return jwt_required()(guarded)
