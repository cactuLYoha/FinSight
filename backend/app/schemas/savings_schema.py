from decimal import Decimal, InvalidOperation

from marshmallow import Schema, ValidationError, fields, validate


class Money(fields.Field):
    def _deserialize(self, value, attr, data, **kwargs):
        if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
            raise ValidationError('A positive decimal amount is required.')
        try:
            amount = Decimal(str(value))
            if not amount.is_finite() or not 0 < amount <= Decimal('9999999999999.99'):
                raise ValidationError('Amount must be positive and fit Numeric(15, 2).')
            rounded = amount.quantize(Decimal('0.01'))
            if amount != rounded:
                raise ValidationError('Amount must have at most two decimal places.')
            return rounded
        except (InvalidOperation, ValueError):
            raise ValidationError('A valid decimal amount is required.') from None


class Currency(fields.String):
    def _deserialize(self, value, attr, data, **kwargs):
        value = super()._deserialize(value, attr, data, **kwargs).strip()
        if len(value) != 3 or not value.isascii() or not value.isalpha():
            raise ValidationError('A three-letter currency code is required.')
        return value.upper()


class GoalName(fields.String):
    def _deserialize(self, value, attr, data, **kwargs):
        value = super()._deserialize(value, attr, data, **kwargs).strip()
        if not value or len(value) > 120:
            raise ValidationError('Name must contain between 1 and 120 characters.')
        return value


class GoalCreateSchema(Schema):
    name = GoalName(required=True)
    target_amount = Money(required=True)
    currency = Currency(required=True)
    deadline = fields.Date(required=True)


class GoalPatchSchema(Schema):
    name = GoalName()
    target_amount = Money()
    deadline = fields.Date()


class GoalReactivateSchema(Schema):
    deadline = fields.Date(required=True)


class ContributionCreateSchema(Schema):
    account_id = fields.Integer(strict=True, validate=validate.Range(min=1))
    amount = Money(required=True)
    contributed_on = fields.Date()
    note = fields.String(allow_none=True, validate=validate.Length(max=500))


class ContributionPatchSchema(Schema):
    account_id = fields.Integer(strict=True, validate=validate.Range(min=1))
    amount = Money()
    contributed_on = fields.Date()
    note = fields.String(allow_none=True, validate=validate.Length(max=500))


class SavingsSummaryQuerySchema(Schema):
    year = fields.Integer(required=True, validate=validate.Range(min=1, max=9999))
    month = fields.Integer(required=True, validate=validate.Range(min=1, max=12))
    currency = Currency(required=True)
