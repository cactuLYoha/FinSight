from marshmallow import Schema, fields, validate

from app.schemas.savings_schema import Currency


class MonthlyAnalyticsQuerySchema(Schema):
    year = fields.Integer(required=True, validate=validate.Range(min=1, max=9999))
    month = fields.Integer(required=True, validate=validate.Range(min=1, max=12))
    currency = Currency(required=True)


class ForecastQuerySchema(Schema):
    currency = Currency(required=True)
    horizon_months = fields.Integer(load_default=12, validate=validate.Range(min=1, max=60))
