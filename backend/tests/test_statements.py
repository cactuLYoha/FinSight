from io import BytesIO
from pathlib import Path
from unittest.mock import Mock

import pytest
from flask_jwt_extended import create_access_token

from app.extensions import db
from app.models.user import User
from app.models.transaction import Transaction
from app.routes import statements
from app.services import statement_reader
from app.services import statement_import_service
from app.models.account import Account
from app.models.statement_import import StatementImport
from decimal import Decimal


@pytest.fixture
def headers(app):
    user = User(email='statement@example.com', is_email_verified=True)
    user.set_password('StrongPassword123')
    db.session.add(user); db.session.commit()
    app.config['AUTH_TRUSTED_ORIGINS'] = frozenset({'http://localhost:4200'})
    token = create_access_token(identity=str(user.id), additional_claims={'auth_complete': True})
    return {'Origin': 'http://localhost:4200', 'Authorization': 'Bearer ' + token}


def upload(client, headers, data=b'%PDF-test', name='statement.pdf'):
    return client.post('/api/statements/analyze', headers=headers,
                       data={'file': (BytesIO(data), name)})


def test_upload_authentication_and_origin(client, headers):
    assert upload(client, {}).status_code == 401
    assert upload(client, {**headers, 'Origin': 'https://other.example'}).status_code == 403


@pytest.mark.parametrize('data,name,status', [
    (b'hello', 'file.pdf', 400), (b'%PDF-test', 'file.csv', 400),
    (b'%PDF-' + b'x' * statements.MAX_FILE_BYTES, 'file.pdf', 413),
])
def test_upload_validation(client, headers, data, name, status):
    assert upload(client, headers, data, name).status_code == status


def test_missing_file(client, headers):
    assert client.post('/api/statements/analyze', headers=headers).status_code == 400


@pytest.mark.parametrize('failure', [False, True])
def test_temporary_file_cleanup_and_read_only_preview(client, headers, monkeypatch, failure):
    paths = []
    def analyze(path, **kwargs):
        paths.append(Path(path))
        assert path.name == 'statement.pdf' and path.read_bytes() == b'%PDF-test'
        if failure:
            raise statement_reader.StatementError('Model unavailable', 503)
        return {'transactions': [], 'verification': None, 'source_method': 'llm'}
    monkeypatch.setattr(statements, 'analyze_statement', analyze)
    response = upload(client, headers, name='../../private.pdf')
    assert response.status_code == (503 if failure else 200)
    assert response.headers['Cache-Control'] == 'no-store'
    assert not paths[0].exists() and not paths[0].parent.exists()
    assert db.session.query(Transaction).count() == 0


def test_unexpected_error_does_not_expose_statement(client, headers, monkeypatch):
    monkeypatch.setattr(statements, 'analyze_statement', Mock(side_effect=RuntimeError('private details')))
    response = upload(client, headers)
    assert response.status_code == 502
    assert b'private details' not in response.data


def test_service_serializes_actual_library_result(monkeypatch):
    from datetime import date
    from decimal import Decimal
    from bankstatementparser.hybrid.orchestrator import IngestResult
    from bankstatementparser.transaction_models import Transaction as ParsedTransaction
    reader = Mock(is_encrypted=False, pages=[Mock(extract_text=lambda: 'Bank statement text ' * 10)])
    monkeypatch.setattr(statement_reader, 'PdfReader', Mock(return_value=reader))
    result = IngestResult(source_method='llm', source_format='pdf', transactions=(
        ParsedTransaction(amount=Decimal('-12.34'), currency='UAH', booking_date=date(2026, 11, 1),
                          description='Groceries', raw_source_text='private source', source_method='llm'),))
    ingest = Mock(return_value=result)
    monkeypatch.setattr(statement_reader, 'smart_ingest', ingest)
    preview = statement_reader.analyze_statement('file.pdf')
    assert preview['transactions'][0]['amount'] == '-12.34'
    assert preview['transactions'][0]['booking_date'] == '2026-11-01'
    assert 'raw_source_text' not in preview['transactions'][0]


@pytest.mark.parametrize('encrypted,pages', [(True, []), (False, []), (False, [Mock(extract_text=lambda: '')]),
                                           (False, [Mock()] * 21)])
def test_service_rejects_unsupported_pdf(monkeypatch, encrypted, pages):
    monkeypatch.setattr(statement_reader, 'PdfReader', Mock(return_value=Mock(is_encrypted=encrypted, pages=pages)))
    with pytest.raises(statement_reader.StatementError):
        statement_reader.analyze_statement('file.pdf')


def test_real_pdf_pipeline_with_mocked_model(tmp_path, monkeypatch):
    import json
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'),
                            NameObject('/Subtype'): NameObject('/Type1'),
                            NameObject('/BaseFont'): NameObject('/Helvetica')})
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): font})})
    stream = DecodedStreamObject()
    stream.set_data(b'BT /F1 12 Tf 40 700 Td (Bank statement November 2026 opening 100.00 closing 87.66 Groceries debit 12.34 UAH) Tj ET')
    page[NameObject('/Contents')] = writer._add_object(stream)
    path = tmp_path / 'statement.pdf'
    writer.write(path)
    completion = Mock(return_value={'choices': [{'message': {'content': json.dumps({
        'currency': 'UAH', 'opening_balance': '100.00', 'closing_balance': '87.66',
        'transactions': [{'amount': '-12.34', 'booking_date': '2026-11-01', 'description': 'Groceries', 'confidence': .95}],
    })}}]})
    monkeypatch.setattr(statement_reader, 'ollama_direct_completion', completion)
    preview = statement_reader.analyze_statement(path)
    assert preview['transactions'][0]['amount'] == '-12.34'
    assert preview['verification']['status'] == 'verified'
    assert completion.call_args.kwargs['timeout'] == 180


@pytest.fixture
def import_account(headers):
    user = db.session.scalar(db.select(User).where(User.email == 'statement@example.com'))
    account = Account(user_id=user.id, name='Statement bank', account_type='bank', currency='UAH', balance=Decimal('50.00'))
    db.session.add(account); db.session.commit()
    return account


def parsed_rows():
    return {'source_method': 'llm', 'verification': {'status': 'verified'}, 'transactions': [
        {'amount': '100.00', 'currency': 'UAH', 'booking_date': '2026-11-01', 'description': 'Salary'},
        {'amount': '-12.34', 'currency': 'UAH', 'booking_date': '2026-11-02', 'description': 'Groceries'},
    ]}


def import_upload(client, headers, account_id, content=b'%PDF-import'):
    return client.post('/api/statements/import', headers=headers, data={
        'account_id': str(account_id), 'file': (BytesIO(content), 'statement.pdf')})


def test_import_saves_ledger_balance_analytics_and_skips_same_file(client, headers, import_account, monkeypatch):
    parser = Mock(return_value=parsed_rows())
    monkeypatch.setattr(statement_import_service, 'analyze_statement', parser)
    response = import_upload(client, headers, import_account.id)
    assert response.status_code == 201 and response.json['imported_count'] == 2
    rows = db.session.scalars(db.select(Transaction).order_by(Transaction.created_at)).all()
    assert [(row.transaction_type, row.amount) for row in rows] == [('income', Decimal('100.00')), ('expense', Decimal('12.34'))]
    assert rows[1].category.name == 'Без категорії'
    assert import_account.balance == Decimal('137.66')
    report = client.get('/api/analytics/monthly?year=2026&month=11&currency=UAH', headers=headers).json['analytics']
    assert report['income_total'] == '100.00' and report['expense_total'] == '12.34'
    duplicate = import_upload(client, headers, import_account.id)
    assert duplicate.status_code == 200 and duplicate.json['duplicate'] is True
    assert duplicate.json['imported_count'] == 0 and parser.call_count == 1
    assert db.session.query(Transaction).count() == 2
    assert db.session.query(StatementImport).count() == 1
    assert import_account.balance == Decimal('137.66')


@pytest.mark.parametrize('change', [
    {'currency': 'EUR'}, {'amount': 'NaN'}, {'amount': '0.001'}, {'amount': '0'},
    {'booking_date': 'invalid'}, {'booking_date': '9999-01-01'}, {'description': ''},
])
def test_import_rejects_entire_statement_on_invalid_row(client, headers, import_account, monkeypatch, change):
    result = parsed_rows(); result['transactions'][1].update(change)
    monkeypatch.setattr(statement_import_service, 'analyze_statement', Mock(return_value=result))
    assert import_upload(client, headers, import_account.id).status_code == 422
    assert db.session.query(Transaction).count() == db.session.query(StatementImport).count() == 0
    assert import_account.balance == Decimal('50.00')


def test_import_checks_account_ownership_before_parsing(client, headers, import_account, monkeypatch):
    other = User(email='other-statement@example.com'); other.set_password('Password123')
    db.session.add(other); db.session.flush()
    foreign = Account(user_id=other.id, name='Foreign', account_type='bank', currency='UAH')
    db.session.add(foreign); db.session.commit()
    parser = Mock(); monkeypatch.setattr(statement_import_service, 'analyze_statement', parser)
    assert import_upload(client, headers, foreign.id).status_code == 404
    assert import_upload(client, headers, 'invalid').status_code == 400
    parser.assert_not_called()


def test_import_rolls_back_if_database_write_fails(client, headers, import_account, monkeypatch):
    monkeypatch.setattr(statement_import_service, 'analyze_statement', Mock(return_value=parsed_rows()))
    monkeypatch.setattr(db.session, 'commit', Mock(side_effect=RuntimeError('simulated write failure')))
    assert import_upload(client, headers, import_account.id).status_code == 502
    assert db.session.query(Transaction).count() == db.session.query(StatementImport).count() == 0
    assert import_account.balance == Decimal('50.00')


def test_import_rejects_balance_discrepancy(client, headers, import_account, monkeypatch):
    result = parsed_rows(); result['verification']['status'] = 'discrepancy'
    monkeypatch.setattr(statement_import_service, 'analyze_statement', Mock(return_value=result))
    assert import_upload(client, headers, import_account.id).status_code == 422
    assert db.session.query(Transaction).count() == 0
