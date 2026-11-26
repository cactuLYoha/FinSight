"""Isolated integration-test server. This module is excluded from the runtime image."""
import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

from flask_migrate import upgrade

from app import create_app


class DiskMailer:
    def send_password_reset(self, recipient, code):
        self.send_verification(recipient, code)

    def send_verification(self, recipient, code):
        folder = Path('/test-mail')
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / (hashlib.sha256(recipient.encode()).hexdigest() + '.json')
        temporary = folder / (uuid4().hex + '.tmp')
        temporary.write_text(json.dumps({'code': code}), encoding='utf-8')
        os.replace(temporary, target)


app = create_app({'TESTING': True, 'MAIL_SENDER': DiskMailer()})
with app.app_context():
    upgrade(directory='/app/migrations')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
