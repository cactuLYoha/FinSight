# Email verification and trusted browsers

The verification flag belongs to User, not a financial Account.
Migration d94e62fa0315 adds is_email_verified (false initially), email_verified_at,
verification_challenge, verification_send, and trusted_device. Existing users
must sign in again: private routes reject JWTs without auth_complete=true and
users whose email has not been verified.

## Flow

- POST /api/auth/register: email/password. Returns 201 with user and
  verification_required=true; no login token. Sets a pending HttpOnly cookie.
- POST /api/auth/session: email/password, trusted Origin required. Returns 202
  with verification context, or 200 with user + access cookies if this browser
  already has valid trust for that verified user.
- POST /api/auth/login: Bearer clients also receive 202 and must complete OTP.
  This endpoint no longer issues a token using a password alone.
- GET /api/auth/verification: restores pending context after reloading /verify.
- POST /api/auth/verification/confirm: {code: "012345", trust_device: false}.
  A correct code completes exactly one challenge. Cookie login returns user;
  Bearer login returns access_token. The server remembers the original transport.
- POST /api/auth/verification/resend: sends a replacement code after cooldown.
- DELETE /api/auth/session: clears login/pending/trust cookies and revokes the
  current browser's trust, including when the access JWT has expired.

Confirmation, resend and cookie login/logout require an exact trusted Origin.
Use the configured frontend origin in API scripts as well. Auth responses use
Cache-Control: no-store. Modifying private resources still requires the CSRF
header for cookie authentication.

Context fields: verification_required, masked_email, expires_at,
resend_available_at, delivery_ready. No password, raw context secret or OTP
appears in JSON. /verify reads the pending cookie through the backend.

## Limits and storage

The six-digit code expires after 10 minutes, has five wrong attempts, and cannot
be reused. Only its HMAC is stored; raw codes never enter application logs.
Resend cooldown is 60 seconds, with five sends per user per rolling hour across
registration, new logins and resends. A failed provider call consumes the send
budget and cooldown, but retains an older unexpired code if one exists.
Resend does not reset the guess counter. PostgreSQL user/challenge row locks
serialize send budgets and consumption across API workers.

finsight_verification is an opaque HttpOnly, SameSite=Lax cookie with
Path=/api/auth/ and a ten-minute lifetime. Its secret is hashed in the database.
finsight_trusted_device uses the same attributes with a fixed 90-day lifetime.
It is issued only after a correct OTP with explicit opt-in. It skips OTP only
after the password has been checked. Its expiry never slides during login.
Another account cannot use it, and logout revokes it on the server.
Secure is enabled via JWT_COOKIE_SECURE for HTTPS; local Docker uses HTTP.
Access cookies still last seven days. Natural expiry of access cookies does not
revoke trust; clicking Logout does. Copies of full JWTs remain stateless until
their expiry (there is no full JWT blocklist).

## Failures

400: invalid_code, invalid_trust_choice, or verification_closed after the fifth
wrong guess. 404: verification_not_found. 410: verification_expired or a consumed
challenge. 429: cooldown/send budget, with Retry-After. 503:
email_delivery_failed; no access JWT is issued.

If registration created the user but delivery failed, the response includes
account_created=true and pending context. The frontend offers resend. Missing
Gmail configuration never disables verification or logs a fallback code.

## Gmail activation and tests

Complete GMAIL_SETUP.md before upgrading the working Compose stack. OAuth files
stay in the ignored root secrets/ directory and outside build contexts.
Gmail send access is delegated only to the configured sender; recipients can use
any email provider.

Automated integration tests use compose.verification-test.yaml, separate images,
a separate database/volume, port 4201, and an outbox file available only to the
test runner. There is no HTTP endpoint for reading codes and no environment
switch to bypass verification in the working application.

From the repository root:
    .\.venv\Scripts\python.exe backend/docker_smoke.py --browser

This starts the isolated stack, exercises OTP + trusted browsers with Chromium,
checks financial persistence across API/DB restarts, and removes only that test
project's containers and volume. It writes synthetic-code files/screenshots to
ignored artifacts/. It does not send real email or migrate the working DB.

The previous standalone browser command must now run through this isolated
runner, not directly against the working API with example.com recipients.
