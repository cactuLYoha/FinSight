"""Build/start the local Compose stack and verify API + restart persistence."""
import json
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import time
from datetime import date, datetime, timezone
from http.client import HTTPException
from http.cookiejar import CookieJar
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]


def wait_ready(request, timeout=180, retry_interval=2):
    """Poll health through transient restart failures, within the time budget."""
    until = time.monotonic() + timeout
    last_error = None
    while (remaining := until - time.monotonic()) > 0:
        try:
            if request('/api/health', timeout=min(10, remaining))['status'] == 'ok':
                return
        except (URLError, TimeoutError, ConnectionError, HTTPException) as error:
            last_error = error
        remaining = until - time.monotonic()
        if remaining > 0:
            time.sleep(min(retry_interval, remaining))
    raise RuntimeError('API healthcheck did not become ready.') from last_error


def main():
    # Mandatory OTP is exercised in a separate stack, never through a runtime bypass.
    from verification_smoke import main as verification_main
    verification_main()


if __name__ == '__main__':
    main()
