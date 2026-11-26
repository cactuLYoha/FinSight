"""Interactive, one-time sender authorization. Never run inside the API container."""
import argparse
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description='Connect the FinSight Gmail sender (gmail.send only).')
    parser.add_argument('--client-secret', type=Path, required=True)
    parser.add_argument('--token-output', type=Path, default=Path(__file__).resolve().parents[1] / 'secrets' / 'gmail_token.json')
    parser.add_argument('--replace', action='store_true')
    args = parser.parse_args()
    if args.token_output.exists() and not args.replace:
        raise SystemExit('Token file exists. Use --replace only to reconnect this sender.')
    from google_auth_oauthlib.flow import InstalledAppFlow
    flow = InstalledAppFlow.from_client_secrets_file(
        str(args.client_secret), scopes=['https://www.googleapis.com/auth/gmail.send'],
        autogenerate_code_verifier=True,
    )
    credentials = flow.run_local_server(port=0, access_type='offline', prompt='consent')
    if not credentials.refresh_token:
        raise SystemExit('Offline access was not granted; reconnect with consent.')
    args.token_output.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | (os.O_TRUNC if args.replace else os.O_EXCL)
    with os.fdopen(os.open(args.token_output, flags, 0o600), 'w', encoding='utf-8') as stream:
        stream.write(credentials.to_json())
    print('Gmail sender connected. Token saved locally; do not share or commit it.')


if __name__ == '__main__':
    main()
