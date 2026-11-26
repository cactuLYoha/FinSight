from datetime import datetime , timezone
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db




class User(db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False , index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    auth_version = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    is_email_verified = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    email_verified_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc) ,
        nullable=False)
    accounts = db.relationship('Account', back_populates='user')
    savings_goals = db.relationship(
        'SavingsGoal', back_populates='user', passive_deletes='all',
    )


    def set_password(self, password):
        self.password_hash = generate_password_hash(password)


    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
