from pathlib import Path
from tempfile import TemporaryDirectory

from flask import Blueprint, current_app, jsonify, request
from werkzeug.exceptions import RequestEntityTooLarge

from app.auth_security import check_session_origin
from app.routes.auth_helpers import authenticated
from app.services.statement_reader import analyze_statement, StatementError
from app.services.statement_import_service import import_statement
from app.extensions import db

statements_bp = Blueprint('statements', __name__)
MAX_FILE_BYTES = 10 * 1024 * 1024


@statements_bp.after_request
def no_cache(response):
    response.headers['Cache-Control'] = 'no-store'
    return response


@statements_bp.errorhandler(RequestEntityTooLarge)
def oversized(error):
    return jsonify(message='Upload a PDF smaller than 10 MB.'), 413


@statements_bp.post('/analyze')
@statements_bp.post('/import')
@authenticated
def analyze(user_id):
    denied = check_session_origin()
    if denied is not None:
        return denied
    request.max_content_length = MAX_FILE_BYTES + 1024 * 1024
    uploaded = request.files.get('file')
    if uploaded is None or not uploaded.filename:
        return jsonify(message='Select a PDF file.'), 400
    if Path(uploaded.filename).suffix.lower() != '.pdf':
        return jsonify(message='Only PDF files are supported.'), 400
    data = uploaded.stream.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        return oversized(None)
    if not data.startswith(b'%PDF-'):
        return jsonify(message='Invalid PDF file.'), 400
    try:
        with TemporaryDirectory(prefix='finsight-statement-') as directory:
            path = Path(directory) / 'statement.pdf'
            path.write_bytes(data)
            if request.path.endswith('/import'):
                try:
                    account_id = int(request.form.get('account_id', ''))
                except ValueError:
                    return jsonify(message='Select an account.'), 400
                result = import_statement(path, user_id=user_id, account_id=account_id,
                                          model=current_app.config['STATEMENT_MODEL'],
                                          api_base=current_app.config['STATEMENT_API_BASE'])
                db.session.commit()
                return jsonify(result), 200 if result['duplicate'] else 201
            preview = analyze_statement(path, model=current_app.config['STATEMENT_MODEL'],
                                        api_base=current_app.config['STATEMENT_API_BASE'])
        return jsonify(analysis=preview)
    except StatementError as error:
        db.session.rollback()
        return jsonify(message=str(error)), error.status
    except Exception:
        db.session.rollback()
        # Provider diagnostics can contain statement contents; do not expose them.
        return jsonify(message='Statement analysis failed. Try another PDF.'), 502
