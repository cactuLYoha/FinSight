from flask import Blueprint , jsonify
main_dp = Blueprint('main_db',__name__)
@main_dp.route('/' , methods=['GET'])
def home():
    return jsonify("hello")