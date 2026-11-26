from flask import Blueprint, jsonify, request
from marshmallow import ValidationError

from app.routes.auth_helpers import authenticated
from app.schemas.analytics_schema import ForecastQuerySchema, MonthlyAnalyticsQuerySchema
from app.services.analytics_service import get_financial_forecast, get_monthly_analytics
from app.extensions import db
from app.services.recurring_expense_service import materialize_due


analytics_bp = Blueprint('analytics', __name__)


@analytics_bp.errorhandler(ValidationError)
def validation_error(error):
    return jsonify(message=error.messages), 400


def _calculate(schema, operation, user_id):
    values = schema.load(request.args.to_dict())
    try:
        materialize_due(user_id)
        db.session.commit()
        return operation(user_id=user_id, **values).to_dict()
    except ValueError as error:
        db.session.rollback()
        raise ValidationError({'_schema': [str(error)]}) from None


@analytics_bp.get('/monthly')
@authenticated
def monthly(user_id):
    return jsonify(analytics=_calculate(
        MonthlyAnalyticsQuerySchema(), get_monthly_analytics, user_id,
    ))


@analytics_bp.get('/forecast')
@authenticated
def forecast(user_id):
    return jsonify(forecast=_calculate(
        ForecastQuerySchema(), get_financial_forecast, user_id,
    ))
