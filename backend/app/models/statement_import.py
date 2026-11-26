from datetime import datetime, timezone

from app.extensions import db


class StatementImport(db.Model):
    """Receipt for an imported file, retained even if its transactions are edited."""
    __tablename__ = 'statement_import'
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('account.id', ondelete='RESTRICT'), nullable=False)
    file_hash = db.Column(db.String(64), nullable=False)
    row_count = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    __table_args__ = (db.UniqueConstraint('account_id', 'file_hash', name='uq_statement_import_account_file'),)
