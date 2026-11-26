import base64
from email.message import EmailMessage
from email.utils import formataddr


class MailDeliveryError(RuntimeError):
    pass


class GmailSender:
    """Only gmail.send is needed; tokens are read from a mounted private file."""
    def __init__(self, token_file, sender):
        self.token_file = token_file
        self.sender = sender

    def _service(self):
        import httplib2
        from google.oauth2.credentials import Credentials
        from google_auth_httplib2 import AuthorizedHttp
        from googleapiclient.discovery import build

        if not self.token_file or not self.sender:
            raise MailDeliveryError('Gmail is not configured.')
        credentials = Credentials.from_authorized_user_file(
            self.token_file, ['https://www.googleapis.com/auth/gmail.send'],
        )
        transport = AuthorizedHttp(credentials, http=httplib2.Http(timeout=10))
        return build('gmail', 'v1', http=transport, cache_discovery=False)

    def send_verification(self, recipient, code):
        self._send_code(recipient, code, False)

    def send_password_reset(self, recipient, code):
        self._send_code(recipient, code, True)

    def _send_code(self, recipient, code, reset):
        try:
            message = EmailMessage()
            message['To'] = recipient
            message['From'] = formataddr(('FinSight', self.sender))
            message['Subject'] = 'Відновлення пароля FinSight' if reset else 'Код підтвердження FinSight'
            message.set_content(
                f'Ваш одноразовий код FinSight: {code}\n\n'
                'Код діє 10 хвилин. Нікому його не повідомляйте.\n'
                + ('Якщо ви не запитували відновлення пароля, проігноруйте цей лист.\n' if reset else
                   'Якщо ви не намагалися увійти або зареєструватися, проігноруйте цей лист.\n'),
            )
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode('ascii')
            service = self._service()
            try:
                service.users().messages().send(userId='me', body={'raw': raw}).execute(num_retries=0)
            finally:
                service.close()
        except Exception:
            # Provider errors may contain addresses, headers, or OAuth details.
            raise MailDeliveryError('Unable to deliver verification email.') from None
