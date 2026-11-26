"""Exercise mandatory OTP only in the separate, disposable verification stack."""
import hashlib
import argparse
from datetime import datetime, timedelta, timezone
from http.cookiejar import CookieJar
import json
from pathlib import Path
import secrets
import shutil
import subprocess
from urllib.error import HTTPError
from urllib.request import Request, HTTPCookieProcessor, build_opener
from uuid import uuid4

from docker_smoke import wait_ready

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--browser', action='store_true')
    args = parser.parse_args()
    if shutil.which('docker') is None:
        raise SystemExit('Docker CLI is required.')
    outbox = ROOT / 'artifacts' / 'verification-mail'
    outbox.mkdir(parents=True, exist_ok=True)
    compose = ['docker', 'compose', '-p', 'finsight-verification-test', '-f', str(ROOT / 'compose.verification-test.yaml')]
    def run(*args):
        subprocess.run(compose + list(args), cwd=ROOT, check=True)
    try:
        run('up', '--build', '-d', '--wait')
        base = 'http://127.0.0.1:4201'
        jar = CookieJar()
        browser = build_opener(HTTPCookieProcessor(jar))
        credentials = {'email': 'verification-smoke-' + uuid4().hex + '@example.com', 'password': secrets.token_hex(12)}
        def request(path, data=None, *, method=None, timeout=10, token=None):
            body = None if data is None else json.dumps(data).encode()
            headers = {'Content-Type': 'application/json', 'Origin': base}
            csrf = next((cookie.value for cookie in jar if cookie.name == 'csrf_access_token'), None)
            if csrf: headers['X-CSRF-TOKEN'] = csrf
            if token: headers['Authorization'] = 'Bearer ' + token
            with browser.open(Request(base + path, data=body, headers=headers, method=method), timeout=timeout) as response:
                return None if response.status == 204 else json.load(response)
        def confirm():
            file = outbox / (hashlib.sha256(credentials['email'].encode()).hexdigest() + '.json')
            code = json.loads(file.read_text(encoding='utf-8'))['code']
            return request('/api/auth/verification/confirm', {'code': code, 'trust_device': True})
        wait_ready(request)
        assert request('/api/auth/register', credentials)['verification_required']
        confirm()
        assert request('/api/auth/me')['user']['is_email_verified']
        assert request('/api/analytics/forecast?currency=UAH')['forecast']['status'] == 'insufficient_history'
        goal = request('/api/savings/goals', {
            'name': 'OTP persistence smoke', 'target_amount': '100.00', 'currency': 'UAH',
            'deadline': (datetime.now(timezone.utc).date() + timedelta(days=90)).isoformat(),
        })['goal']
        request(f"/api/savings/goals/{goal['id']}/contributions", {'amount': '10.00'})
        run('restart', 'db', 'api')
        wait_ready(request)
        assert request('/api/auth/me')['user']['email'] == credentials['email']
        assert request(f"/api/savings/goals/{goal['id']}")['goal']['saved_amount'] == '10.00'
        request('/api/auth/session', method='DELETE')
        try: request('/api/auth/me')
        except HTTPError as error: assert error.code == 401
        else: raise RuntimeError('Logout failed.')
        assert request('/api/auth/login', credentials)['verification_required']
        token = confirm()['access_token']
        assert request('/api/auth/me', token=token)['user']['email'] == credentials['email']
        if args.browser:
            subprocess.run(['docker', 'build', '-f', str(ROOT / 'frontend/Dockerfile.e2e'), '-t', 'finsight-browser:verification-test', str(ROOT / 'frontend')], check=True)
            subprocess.run([
                'docker', 'run', '--rm', '--init',
                '-e', 'BASE_URL=http://localhost:4201', '-e', 'TEST_MAIL_DIR=/test-mail',
                '--mount', f'type=bind,source={outbox},target=/test-mail,readonly',
                '--mount', f'type=bind,source={ROOT / "artifacts"},target=/artifacts',
                'finsight-browser:verification-test',
            ], check=True)
        print('Verification Compose smoke passed: OTP, cookie, Bearer, savings, analytics, logout, restart persistence.')
    finally:
        run('down', '-v')


if __name__ == '__main__':
    main()
