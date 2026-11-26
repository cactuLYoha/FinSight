from app.services.gmail_service import MailDeliveryError

HEADERS = {'Origin': 'http://localhost:4200'}


class FakeMailer:
    def __init__(self):
        self.messages = []
        self.fail = False

    def send_verification(self, recipient, code):
        if self.fail:
            raise MailDeliveryError('Test transport outage.')
        self.messages.append((recipient, code))

    def send_password_reset(self, recipient, code):
        self.send_verification(recipient, code)


def finish_verification(client, trust=False):
    code = client.application.extensions['mail_sender'].messages[-1][1]
    return client.post('/api/auth/verification/confirm', headers=HEADERS, json={'code': code, 'trust_device': trust})
