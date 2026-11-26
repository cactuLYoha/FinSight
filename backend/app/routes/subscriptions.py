from flask import Blueprint, jsonify, request
from marshmallow import Schema, fields, validate, ValidationError
from sqlalchemy import select

from app.auth_security import check_session_origin
from app.extensions import db
from app.models.subscription import Subscription
from app.routes.auth_helpers import authenticated
from app.schemas.savings_schema import Currency, Money, GoalName

subscriptions_bp = Blueprint('subscriptions', __name__)


class SubscriptionSchema(Schema):
    name = GoalName(required=True)
    amount = Money(required=True)
    currency = Currency(required=True)
    billing_day = fields.Integer(required=True, strict=True, validate=validate.Range(min=1, max=31))


@subscriptions_bp.after_request
def no_cache(response):
    response.headers['Cache-Control'] = 'no-store'
    return response


@subscriptions_bp.errorhandler(ValidationError)
def invalid(error):
    return jsonify(message=error.messages), 400


@subscriptions_bp.get('')
@authenticated
def list_subscriptions(user_id):
    query = select(Subscription).where(Subscription.user_id == user_id)
    if request.args.get('currency'):
        currency = Currency().deserialize(request.args['currency'])
        query = query.where(Subscription.currency == currency)
    rows = db.session.scalars(query.order_by(Subscription.billing_day, Subscription.id))
    return jsonify(subscriptions=[row.to_dict() for row in rows])


@subscriptions_bp.post('')
@authenticated
def add_subscription(user_id):
    denied = check_session_origin()
    if denied is not None:
        return denied
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValidationError('Expected an object.')
    row = Subscription(user_id=user_id, **SubscriptionSchema().load(data))
    db.session.add(row)
    db.session.commit()
    return jsonify(subscription=row.to_dict()), 201


@subscriptions_bp.delete('/<int:subscription_id>')
@authenticated
def delete_subscription(user_id, subscription_id):
    denied = check_session_origin()
    if denied is not None:
        return denied
    row = db.session.scalar(select(Subscription).where(Subscription.id == subscription_id, Subscription.user_id == user_id))
    if row is None:
        return jsonify(message='Subscription not found'), 404
    db.session.delete(row)
    db.session.commit()
    return '', 204
