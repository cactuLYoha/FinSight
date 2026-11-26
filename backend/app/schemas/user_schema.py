from marshmallow import Schema, fields , validate

class RegisterSchema(Schema):
    email = fields.Email(required=True, validate=validate.Length(max=120))

    password = fields.Str(
        required=True,
        validate = validate.Length(min=8 , max=35),
        load_only=True,
    )


class LoginSchema(Schema):
    email = fields.Email(required=True, validate=validate.Length(max=120))
    password = fields.Str(required=True, load_only=True, validate=validate.Length(min=1))


class UserSchema(Schema):
    id = fields.Int(dump_only=True)
    email = fields.Email(dump_only=True)
    created_at = fields.DateTime(dump_only=True)
    is_email_verified = fields.Boolean(dump_only=True)
    email_verified_at = fields.DateTime(dump_only=True)
