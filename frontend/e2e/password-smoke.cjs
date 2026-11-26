const assert = require('node:assert/strict');
const { randomUUID, createHash } = require('node:crypto');
const { lookup } = require('node:dns/promises');
const { readFile, mkdir } = require('node:fs/promises');
const { chromium } = require('playwright');
if (!process.env.TEST_MAIL_DIR) throw new Error('Run against isolated verification Compose with a test outbox.');
const base = process.env.BASE_URL || 'http://localhost:4201';
const email = 'password-' + randomUUID() + '@example.com';
const oldPassword = 'OldPassword123';
const newPassword = 'NewPassword456';
const resetPassword = 'RecoveredPassword789';
async function code() {
  return JSON.parse(await readFile(process.env.TEST_MAIL_DIR + '/' + createHash('sha256').update(email).digest('hex') + '.json', 'utf8')).code;
}
(async () => {
  const host = await lookup('host.docker.internal', { family: 4 });
  const browser = await chromium.launch({ args: ['--no-sandbox', '--host-resolver-rules=MAP localhost ' + host.address] });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  try {
    await page.goto(base + '/register');
    const notice = page.locator('.notice button');
    if (await notice.first().isVisible()) await notice.first().click();
    await page.locator('#email').fill(email);
    await page.locator('#password').fill(oldPassword);
    await page.locator('#confirmation').fill(oldPassword);
    await page.locator('form button.button-primary').click();
    await page.waitForURL(base + '/verify');
    await page.locator('#verification-code').fill(await code());
    await page.locator('#verification-code').press('Enter');
    await page.waitForURL(base + '/');
    await page.getByRole('link', { name: 'Налаштування акаунту' }).click();
    await page.waitForURL(base + '/account/settings');
    await page.locator('#current-password').fill('wrong-password');
    await page.locator('#new-password').fill(newPassword);
    await page.locator('#repeat-password').fill(newPassword);
    await page.locator('form button.button-primary').click();
    await page.getByRole('alert').filter({ hasText: 'Поточний пароль неправильний.' }).waitFor();
    await page.locator('#current-password').fill(oldPassword);
    const staleCookie = (await context.cookies()).find(c => c.name === 'access_token_cookie');
    await page.locator('form button.button-primary').click();
    await page.waitForURL(base + '/login');
    const staleStatus = await page.evaluate(async token => (await fetch('/api/auth/me', { headers: { Authorization: 'Bearer ' + token } })).status, staleCookie.value);
    assert.equal(staleStatus, 401);
    await page.getByRole('link', { name: 'Забули пароль?' }).click();
    await page.locator('#reset-email').fill(email);
    await page.locator('form button.button-primary').click();
    await page.locator('#reset-code').waitFor();
    await page.locator('#reset-code').fill(await code());
    await page.locator('#new-password').fill(resetPassword);
    await page.locator('#repeat-password').fill(resetPassword);
    for (const width of [375, 768, 1440]) {
      await page.setViewportSize({ width, height: 1000 });
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      await mkdir('/artifacts', { recursive: true });
      await page.screenshot({ path: '/artifacts/password-reset-' + width + '.png', fullPage: true });
    }
    await page.locator('form button.button-primary').click();
    await page.waitForURL(base + '/login');
    await page.locator('#email').fill(email);
    await page.locator('#password').fill(resetPassword);
    await page.locator('form button.button-primary').click();
    await page.waitForURL(base + '/verify');
    await page.locator('#verification-code').fill(await code());
    await page.locator('#verification-code').press('Enter');
    await page.waitForURL(base + '/');
    assert.deepEqual(errors, []);
    console.log('Password browser smoke passed: account link, wrong/current password, revoked JWT, recovery code, new-password login, 375/768/1440px.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
