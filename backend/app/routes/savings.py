
from flask import Blueprint, jsonify, request

from marshmallow import ValidationError

from app.services import savings_service as savings
from app.routes.auth_helpers import authenticated


savings_bp = Blueprint('savings', __name__)



def _body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValidationError({'_schema': ['A JSON object is required.']})
    return data


@savings_bp.errorhandler(ValidationError)
def validation_error(error):
    return jsonify(message=error.messages), 400


@savings_bp.errorhandler(savings.SavingsError)
def savings_error(error):
    return jsonify(message=str(error)), error.status_code


@savings_bp.get('/summary')
@authenticated
def summary(user_id):
    return jsonify(summary=savings.get_summary(user_id, request.args.to_dict()))


@savings_bp.get('/goals')
@authenticated
def goals(user_id):
    return jsonify(goals=savings.list_goals(user_id))


@savings_bp.post('/goals')
@authenticated
def create_goal(user_id):
    goal = savings.create_goal(user_id, _body())
    return jsonify(goal=savings.serialize_goal(goal)), 201


@savings_bp.get('/goals/<int:goal_id>')
@authenticated
def get_goal(user_id, goal_id):
    return jsonify(goal=savings.get_goal(user_id, goal_id))


@savings_bp.patch('/goals/<int:goal_id>')
@authenticated
def update_goal(user_id, goal_id):
    goal = savings.update_goal(user_id, goal_id, _body())
    return jsonify(goal=savings.serialize_goal(goal))


@savings_bp.get('/goals/<int:goal_id>/plan')
@authenticated
def plan(user_id, goal_id):
    return jsonify(plan=savings.get_plan(user_id, goal_id))


@savings_bp.get('/goals/<int:goal_id>/contributions')
@authenticated
def contributions(user_id, goal_id):
    rows = savings.list_contributions(user_id, goal_id)
    goal = savings.get_goal(user_id, goal_id)
    from sqlalchemy import select
    from app.extensions import db
    from app.models.account import Account
    accounts = db.session.scalars(select(Account).where(Account.user_id == user_id,
        Account.currency == goal['currency']).order_by(Account.id))
    return jsonify(contributions=rows, accounts=[dict(id=account.id, name=account.name) for account in accounts])


@savings_bp.post('/goals/<int:goal_id>/contributions')
@authenticated
def add_contribution(user_id, goal_id):
    contribution = savings.add_contribution(user_id, goal_id, _body())
    return jsonify(contribution=savings.serialize_contribution(contribution)), 201


@savings_bp.patch('/goals/<int:goal_id>/contributions/<int:contribution_id>')
@authenticated
def update_contribution(user_id, goal_id, contribution_id):
    contribution = savings.update_contribution(user_id, goal_id, contribution_id, _body())
    return jsonify(contribution=savings.serialize_contribution(contribution))


@savings_bp.delete('/goals/<int:goal_id>/contributions/<int:contribution_id>')
@authenticated
def delete_contribution(user_id, goal_id, contribution_id):
    savings.delete_contribution(user_id, goal_id, contribution_id)
    return '', 204


@savings_bp.post('/goals/<int:goal_id>/complete')
@authenticated
def complete_goal(user_id, goal_id):
    return jsonify(goal=savings.serialize_goal(savings.complete_goal(user_id, goal_id)))


@savings_bp.post('/goals/<int:goal_id>/cancel')
@authenticated
def cancel_goal(user_id, goal_id):
    return jsonify(goal=savings.serialize_goal(savings.cancel_goal(user_id, goal_id)))


@savings_bp.post('/goals/<int:goal_id>/reactivate')
@authenticated
def reactivate_goal(user_id, goal_id):
    goal = savings.reactivate_goal(user_id, goal_id, _body())
    return jsonify(goal=savings.serialize_goal(goal))


@savings_bp.delete('/goals/<int:goal_id>')
@authenticated
def delete_goal(user_id, goal_id):
    savings.delete_goal(user_id, goal_id)
    return '', 204


@savings_bp.post('/goals/<int:goal_id>/transfer')
@authenticated
def transfer_goal(user_id, goal_id):
    return jsonify(**savings.transfer_goal(user_id, goal_id, _body()))
