from app.extensions import db
from app.models.user import User
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash, check_password_hash


class EmailAlreadyRegistered(ValueError):
    pass


_DUMMY_HASH = generate_password_hash('unused-login-password')


def register_user(email, password):
    email = email.strip().lower()

    existing_user = User.query.filter_by(email=email).first()

    if existing_user:
        raise EmailAlreadyRegistered('Email already registered.')
    user = User(email=email)
    user.set_password(password)

    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        if User.query.filter_by(email=email).first() is not None:
            raise EmailAlreadyRegistered('Email already registered.') from None
        raise

    return user


def authenticate_user(email, password):
    user = User.query.filter_by(email=email.strip().lower()).first()
    if user is None:
        check_password_hash(_DUMMY_HASH, password)
        return None
    return user if user.check_password(password) else None


def get_user_by_identity(identity):
    try:
        user_id = int(identity)
    except (TypeError, ValueError):
        return None
    if not 0 < user_id <= 2147483647:
        return None
    return db.session.get(User, user_id)
