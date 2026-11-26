const assert = require('node:assert/strict');
const { randomBytes, randomUUID, createHash } = require('node:crypto');
const { lookup } = require('node:dns/promises');
const { mkdir, readFile } = require('node:fs/promises');
if (!process.env.TEST_MAIL_DIR) throw new Error('Use the isolated verification Compose and mount its private test outbox.');
const { chromium } = require('playwright');

const base = (process.env.BASE_URL || 'http://localhost:4201').replace(/\/$/, '');
const errors = [];
const email = 'finsight-browser-' + randomUUID() + '@example.com';
const password = 'Test-' + randomBytes(12).toString('hex');
const screenshots = '/artifacts';

function observe(page) {
  page.on('pageerror', (error) => errors.push(error.message));
}
async function acknowledge(page) {
  const notice = page.locator('.notice');
  if (await notice.isVisible()) {
    await notice.getByRole('button', { name: 'Зрозуміло' }).press('Enter');
    await notice.waitFor({ state: 'hidden' });
  }
}
async function enterCredentials(page, value, confirmation = false) {
  await page.getByLabel('Email', { exact: true }).focus();
  await page.keyboard.type(email);
  await page.keyboard.press('Tab');
  assert.ok(await page.locator('#password').evaluate((node) => node === document.activeElement));
  await page.keyboard.type(value);
  if (confirmation) {
    await page.keyboard.press('Tab'); // Password visibility button is keyboard accessible.
    await page.keyboard.press('Tab');
    assert.ok(await page.locator('#confirmation').evaluate((node) => node === document.activeElement));
    await page.keyboard.type(value);
  }
  await page.keyboard.press('Enter');
}
async function otpCode() {
  return JSON.parse(await readFile(process.env.TEST_MAIL_DIR + '/' + createHash('sha256').update(email).digest('hex') + '.json', 'utf8')).code;
}
async function completeOtp(page, trust = false) {
  await page.waitForURL(base + '/verify');
  await page.locator('#verification-code').waitFor();
  await page.screenshot({ path: screenshots + '/verification-1440.png', fullPage: true });
  await page.setViewportSize({ width: 375, height: 1000 });
  await page.screenshot({ path: screenshots + '/verification-375.png', fullPage: true });
  await page.setViewportSize({ width: 1440, height: 1000 });
  if (trust) await page.getByRole('checkbox', { name: 'Довіряти цьому браузеру 90 днів' }).check();
  await page.locator('#verification-code').focus();
  await page.keyboard.type(await otpCode());
  await page.keyboard.press('Enter');
  await page.waitForURL(base + '/');
}
async function fetchResult(page, path, options = {}) {
  return page.evaluate(async ({ path, options }) => {
    const response = await fetch(path, options);
    const text = await response.text();
    return { status: response.status, data: text ? JSON.parse(text) : null };
  }, { path, options });
}

(async () => {
  await mkdir(screenshots, { recursive: true });
  const args = ['--no-sandbox'];
  // Keep the real localhost origin while reaching the host's loopback-published
  // Compose port from Docker Desktop. No Origin headers or API responses are
  // rewritten in the normal login flow.
  if (new URL(base).hostname === 'localhost') {
    const host = await lookup('host.docker.internal', { family: 4 });
    args.push('--host-resolver-rules=MAP localhost ' + host.address);
  }
  const launch = { headless: true, args, viewport: { width: 1440, height: 1000 } };
  let context;
  let blockedContext;
  try {
    context = await chromium.launchPersistentContext('/tmp/finsight-browser-profile', launch);
    let page = await context.newPage();
    observe(page);
    await page.goto(base + '/register', { waitUntil: 'networkidle' });
    await acknowledge(page);

    const registration = page.waitForResponse((response) => response.url().endsWith('/api/auth/register') && response.request().method() === 'POST');
    await enterCredentials(page, password, true);
    assert.equal((await registration).status(), 201);
    await completeOtp(page, true);
    const trusted = (await context.cookies()).find((entry) => entry.name === 'finsight_trusted_device');
    assert.ok(trusted.httpOnly && Math.abs(trusted.expires - Date.now() / 1000 - 90 * 86400) < 30);
    await page.waitForURL(base + '/');
    await page.getByText(email, { exact: true }).waitFor();

    const cookie = (await context.cookies()).find((entry) => entry.name === 'access_token_cookie');
    assert.ok(cookie);
    assert.equal(cookie.httpOnly, true);
    assert.equal(cookie.sameSite, 'Lax');
    assert.equal(cookie.path, '/api/');
    assert.ok(Math.abs(cookie.expires - Date.now() / 1000 - 604800) < 30);
    assert.ok(!await page.evaluate(() => document.cookie.includes('access_token_cookie')));
    assert.deepEqual(await page.evaluate(() => [localStorage.length, sessionStorage.length]), [0, 0]);
    const me = await fetchResult(page, '/api/auth/me');
    const sessionBody = me.data;
    assert.deepEqual(Object.keys(sessionBody), ['user']);
    assert.equal(me.status, 200);
    assert.equal(me.data.user.email, email);

    // Verify real cookie-authenticated writes and CSRF enforcement.
    const deadline = new Date(Date.now() + 90 * 86400000).toISOString().slice(0, 10);
    const goal = { name: 'Browser CSRF smoke', target_amount: '100.00', currency: 'UAH', deadline };
    const denied = await fetchResult(page, '/api/savings/goals', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(goal) });
    assert.equal(denied.status, 401);
    const csrfWrite = await page.evaluate(async (goal) => {
      const nonce = document.cookie.split(';').map((part) => part.trim()).find((part) => part.startsWith('csrf_access_token=')).slice('csrf_access_token='.length);
      const response = await fetch('/api/savings/goals', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-TOKEN': nonce }, body: JSON.stringify(goal) });
      return response.status;
    }, goal);
    assert.equal(csrfWrite, 201);
    await page.screenshot({ path: screenshots + '/account-home.png', fullPage: false });

    // Closing and reopening the persistent profile must retain the seven-day login.
    await context.close();
    context = await chromium.launchPersistentContext('/tmp/finsight-browser-profile', launch);
    page = await context.newPage();
    observe(page);
    await page.goto(base, { waitUntil: 'networkidle' });
    await page.getByText(email, { exact: true }).waitFor();
    await page.goto(base + '/login');
    await page.waitForURL(base + '/');

    // Expiry of the seven-day login still requires the password, but trust skips OTP.
    const previousMail = await otpCode();
    await context.clearCookies({ name: 'access_token_cookie' });
    await page.goto(base + '/login', { waitUntil: 'networkidle' });
    await enterCredentials(page, password);
    await page.waitForURL(base + '/');
    await page.getByText(email, { exact: true }).waitFor();
    assert.equal(await otpCode(), previousMail);
    assert.equal((await context.cookies()).find((entry) => entry.name === 'finsight_trusted_device').expires, trusted.expires);
    // A failed status request must permit retry without discarding valid cookies.
    await page.route('**/api/auth/me', (route) => route.fulfill({ status: 503, contentType: 'application/json', body: '{}' }));
    await page.reload({ waitUntil: 'networkidle' });
    await page.getByRole('button', { name: 'Повторити', exact: true }).waitFor();
    await page.unroute('**/api/auth/me');
    await page.getByRole('button', { name: 'Повторити', exact: true }).click();
    await page.getByText(email, { exact: true }).waitFor();

    // Network failure on logout must not claim the server removed the cookie.
    await page.route('**/api/auth/session', (route) => route.fulfill({ status: 503, contentType: 'application/json', body: '{}' }));
    await page.getByRole('button', { name: 'Вийти', exact: true }).press('Enter');
    await page.getByRole('alert').filter({ hasText: 'Не вдалося вийти' }).waitFor();
    assert.ok((await context.cookies()).some((entry) => entry.name === 'access_token_cookie'));
    await page.unroute('**/api/auth/session');

    const logoutRequest = page.waitForRequest((request) => request.url().endsWith('/api/auth/session') && request.method() === 'DELETE');
    await page.getByRole('button', { name: 'Вийти', exact: true }).press('Enter');
    assert.ok((await logoutRequest).headers()['x-csrf-token']);
    await page.getByRole('navigation').getByRole('link', { name: 'Увійти', exact: true }).waitFor();
    assert.equal((await fetchResult(page, '/api/auth/me')).status, 401);
    assert.ok(!(await context.cookies()).some((entry) => ['access_token_cookie', 'csrf_access_token', 'finsight_trusted_device'].includes(entry.name)));

    // Both routes must work on a direct request and at mobile/tablet/desktop widths.
    for (const width of [375, 768, 1440]) {
      await page.setViewportSize({ width, height: 1000 });
      for (const route of ['login', 'register']) {
        await page.goto(base + '/' + route, { waitUntil: 'networkidle' });
        await page.getByRole('heading', { name: route === 'login' ? 'Увійти у FinSight' : 'Створити акаунт', exact: true }).waitFor();
        assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'Horizontal overflow on ' + route + '/' + width);
        await page.screenshot({ path: screenshots + '/' + route + '-' + width + '.png', fullPage: true });
      }
    }
    await page.goto(base + '/login', { waitUntil: 'networkidle' });
    await enterCredentials(page, 'incorrect-password');
    await page.getByRole('alert').filter({ hasText: 'Неправильний email або пароль' }).waitFor();
    assert.ok(!(await context.cookies()).some((entry) => entry.name === 'access_token_cookie'));
    await page.locator('#password').focus();
    await page.keyboard.press('ControlOrMeta+A');
    await page.keyboard.type(password);
    await page.keyboard.press('Enter');
    await completeOtp(page);
    await page.getByText(email, { exact: true }).waitFor();

    // Simulate a successful response whose Set-Cookie was rejected by the browser.
    // /me remains real and cannot authenticate without a retained cookie.
    blockedContext = await chromium.launchPersistentContext('/tmp/finsight-blocked-profile', launch);
    const blockedPage = await blockedContext.newPage();
    observe(blockedPage);
    await blockedPage.route('**/api/auth/verification/confirm', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(sessionBody) }));
    await blockedPage.goto(base + '/login', { waitUntil: 'networkidle' });
    await acknowledge(blockedPage);
    await enterCredentials(blockedPage, password);
    await blockedPage.waitForURL(base + '/verify');
    await blockedPage.locator('#verification-code').fill(await otpCode());
    await blockedPage.locator('#verification-code').press('Enter');
    await blockedPage.getByRole('alert').filter({ hasText: 'Дозвольте cookies' }).waitFor();
    assert.equal(new URL(blockedPage.url()).pathname, '/verify');
    assert.deepEqual(errors, []);
    console.log('OTP browser smoke passed: keyboard registration/login, email verification, 90-day trust, logout revocation, browser restart, CSRF, retries, blocked cookies, 375/768/1440px.');
  } finally {
    await blockedContext?.close();
    await context?.close();
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
