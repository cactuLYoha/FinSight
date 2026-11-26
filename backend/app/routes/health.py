from flask import Blueprint, jsonify
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db


health_bp = Blueprint('health', __name__)


@health_bp.get('/health')
def health():
    try:
        with db.engine.connect() as connection:
            ready = connection.execute(text('SELECT 1')).scalar_one() == 1
    except SQLAlchemyError:
        ready = False
    return jsonify(status='ok' if ready else 'unavailable'), 200 if ready else 503
