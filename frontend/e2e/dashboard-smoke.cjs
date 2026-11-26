const assert = require('node:assert/strict');
const { randomUUID, createHash } = require('node:crypto');
const { lookup } = require('node:dns/promises');
const { readFile } = require('node:fs/promises');
const { chromium } = require('playwright');
if (!process.env.TEST_MAIL_DIR) throw new Error('Use isolated verification Compose with a test outbox.');
const base = process.env.BASE_URL || 'http://localhost:4201';
const email = 'dashboard-' + randomUUID() + '@example.com';

(async () => {
  const host = await lookup('host.docker.internal', { family: 4 });
  const browser = await chromium.launch({ args: ['--no-sandbox', '--host-resolver-rules=MAP localhost ' + host.address] });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  try {
    await page.goto(base + '/dashboard');
    await page.waitForURL(base + '/login');
    await page.goto(base + '/register');
    const notice = page.locator('.notice button');
    if (await notice.first().isVisible()) await notice.first().click();
    await page.locator('#email').fill(email);
    await page.locator('#password').fill('DashboardPassword123');
    await page.locator('#confirmation').fill('DashboardPassword123');
    await page.locator('button[type=submit]').click();
    await page.waitForURL(base + '/verify');
    const mail = JSON.parse(await readFile(process.env.TEST_MAIL_DIR + '/' + createHash('sha256').update(email).digest('hex') + '.json', 'utf8'));
    await page.locator('#verification-code').fill(mail.code);
    await page.locator('#verification-code').press('Enter');
    await page.waitForURL(base + '/');
    await page.getByRole('link', { name: 'Особистий кабінет', exact: true }).click();
    await page.waitForURL(base + '/dashboard');
    await page.getByText('Для прогнозу потрібно трохи історії', { exact: true }).waitFor();
    assert.equal(await page.getByRole('heading', { name: 'Щомісячні підписки', exact: true }).count(), 0);
    await page.getByRole('link', { name: 'Витрати та підписки', exact: true }).click();
    await page.getByRole('button', { name: '+ Додати', exact: true }).click();
    await page.getByLabel('Назва', { exact: true }).fill('Music');
    await page.getByLabel('Сума, UAH', { exact: true }).fill('199.99');
    await page.getByLabel('День оплати', { exact: true }).fill('31');
    await page.getByRole('button', { name: 'Зберегти підписку', exact: true }).click();
    await page.getByText('Підписку додано.', { exact: true }).waitFor();
    await page.reload();
    await page.getByRole('heading', { name: 'Music', exact: true }).waitFor();
    await page.locator('.filters select').selectOption('USD');
    await page.getByText('Підписок поки немає', { exact: true }).waitFor();
    await page.locator('.filters select').selectOption('UAH');
    await page.getByRole('heading', { name: 'Music', exact: true }).waitFor();
    await page.getByRole('button', { name: '+ Додати витрату', exact: true }).click();
    await page.locator('#expense-form input[formcontrolname=amount]').fill('125.50');
    const categoryId = await page.locator('#expense-form select[formcontrolname=category_id] option').nth(1).getAttribute('value');
    await page.locator('#expense-form select[formcontrolname=category_id]').selectOption(categoryId);
    await page.getByLabel('Опис витрати', { exact: true }).fill('Browser test groceries');
    await page.getByRole('button', { name: 'Зберегти витрату', exact: true }).click();
    await page.getByText('Витрату додано. Аналітику оновлено.', { exact: true }).waitFor();
    await page.reload();
    await page.getByText('Browser test groceries', { exact: true }).waitFor();
    const totals = await page.evaluate(async () => {
      const month = new Date().toISOString().slice(0, 7).split('-');
      return (await (await fetch(`/api/analytics/monthly?year=${month[0]}&month=${month[1]}&currency=UAH`)).json()).analytics;
    });
    assert.equal(totals.expense_total, '125.50');
    await page.getByRole('button', { name: 'Редагувати витрату Browser test groceries', exact: true }).click();
    assert.equal(await page.locator('#expense-form input[formcontrolname=amount]').inputValue(), '125.50');
    await page.locator('#expense-form input[formcontrolname=amount]').fill('250,75');
    const editedResponse = page.waitForResponse(response => response.request().method() === 'PATCH' && response.url().includes('/api/expenses/'));
    await page.getByRole('button', { name: 'Зберегти зміни', exact: true }).click();
    assert.equal((await editedResponse).status(), 200);
    await page.locator('.expense-panel .notice').filter({ hasText: 'Витрату оновлено' }).waitFor();
    await page.reload();
    await page.getByRole('button', { name: 'Редагувати витрату Browser test groceries', exact: true }).click();
    assert.equal(await page.locator('#expense-form input[formcontrolname=amount]').inputValue(), '250.75');
    const editedTotals = await page.evaluate(async () => {
      const month = new Date().toISOString().slice(0, 7).split('-');
      return (await (await fetch(`/api/analytics/monthly?year=${month[0]}&month=${month[1]}&currency=UAH`)).json()).analytics;
    });
    assert.equal(editedTotals.expense_total, '250.75');
    await page.locator('#expense-form input[formcontrolname=amount]').fill('125.50');
    await page.getByRole('button', { name: 'Зберегти зміни', exact: true }).click();
    await page.locator('.expense-panel .notice').filter({ hasText: 'Витрату оновлено' }).waitFor();
    await page.getByRole('button', { name: 'Повторювати щомісяця Browser test groceries', exact: true }).click();
    await page.getByRole('region', { name: 'Щомісячні витрати', exact: true }).waitFor();
    await page.reload();
    await page.getByRole('button', { name: 'Зупинити повторення Browser test groceries', exact: true }).waitFor();
    await page.getByRole('button', { name: 'Зупинити повторення Browser test groceries', exact: true }).click();
    await page.getByText('Повторення зупинено. Попередні витрати збережено.', { exact: true }).waitFor();
    await page.getByText('Browser test groceries', { exact: true }).waitFor();
    await page.getByRole('button', { name: 'Повторювати щомісяця Browser test groceries', exact: true }).waitFor();
    await page.reload();
    await page.getByRole('button', { name: 'Повторювати щомісяця Browser test groceries', exact: true }).waitFor();
    await page.getByRole('button', { name: 'Повторювати щомісяця Browser test groceries', exact: true }).click();
    await page.getByRole('button', { name: 'Зупинити повторення операції Browser test groceries', exact: true }).waitFor();
    await page.getByRole('button', { name: 'Зупинити повторення операції Browser test groceries', exact: true }).click();
    await page.getByRole('button', { name: 'Повторювати щомісяця Browser test groceries', exact: true }).waitFor();
    await page.getByRole('button', { name: '+ Додати витрату', exact: true }).click();
    await page.locator('#expense-form input[formcontrolname=amount]').fill('9000');
    await page.locator('#expense-form select[formcontrolname=category_id]').selectOption(categoryId);
    await page.getByLabel('Опис витрати', { exact: true }).fill('Browser test rent');
    await page.getByLabel('Повторювати щомісяця', { exact: true }).check();
    await page.getByRole('button', { name: 'Зберегти витрату', exact: true }).click();
    await page.getByRole('button', { name: 'Зупинити повторення Browser test rent', exact: true }).waitFor();
    for (const width of [375, 1440]) {
      await page.setViewportSize({ width, height: 1100 });
      await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      await page.screenshot({ path: '/artifacts/expense-tab-' + width + '.png', fullPage: true });
    }
    await page.getByRole('link', { name: 'Огляд', exact: true }).click();

    // Fixture analytics exercise the chart with populated data; subscriptions stay real.
    await page.route('**/api/analytics/monthly?*', route => route.fulfill({ json: { analytics: {
      income_total: '45000', expense_total: '19500', net_total: '25500', categories: [
        { category_id: 1, name: 'Продукти', expense_total: '8500' },
        { category_id: 2, name: 'Житло', expense_total: '6000' },
        { category_id: 3, name: 'Транспорт', expense_total: '3000' },
        { category_id: 4, name: 'Дозвілля', expense_total: '2000' },
      ],
    } } }));
    await page.route('**/api/analytics/forecast?*', route => {
      const horizon = Number(new URL(route.request().url()).searchParams.get('horizon_months'));
      return route.fulfill({ json: { forecast: {
        status: 'ready', sample_size: 6, minimum_history_months: 3, starting_savings: '0', starting_savings_basis: 'relative_change',
        scenarios: [['optimistic', 28000], ['realistic', 22000], ['pessimistic', 16000]].map(([name, net]) => ({
          name, monthly_net: String(net), points: Array.from({ length: horizon }, (_, i) => ({ month: new Date(Date.UTC(2026, 11 + i, 1)).toISOString().slice(0, 7), projected_savings: String(net * (i + 1)) })),
        })),
      } } });
    });
    await page.getByRole('button', { name: 'Оновити дані', exact: true }).click();
    await page.locator('svg[role=img]').waitFor();
    await page.getByRole('button', { name: 'Реалістичний', exact: true }).click();
    await page.waitForFunction(() => document.querySelectorAll('.forecast-panel svg path').length === 1);
    assert.equal(await page.locator('.forecast-panel svg path').count(), 1);
    await page.getByRole('button', { name: 'Усі сценарії', exact: true }).click();
    await page.waitForFunction(() => document.querySelectorAll('.forecast-panel svg path').length === 3);
    assert.equal(await page.locator('.forecast-panel svg path').count(), 3);
    await page.getByText('Значення за місяцями', { exact: true }).click();
    assert.equal(await page.locator('tbody tr').count(), 12);
    await page.getByText('Значення за місяцями', { exact: true }).click();
    await page.getByLabel('Горизонт прогнозу', { exact: true }).selectOption('6');
    await page.waitForFunction(() => document.querySelectorAll('.forecast-panel svg circle').length === 18);
    await page.getByLabel('Горизонт прогнозу', { exact: true }).selectOption('12');
    await page.waitForFunction(() => document.querySelectorAll('.forecast-panel svg circle').length === 36);
    for (const width of [375, 768, 1440]) {
      await page.setViewportSize({ width, height: 1100 });
      await page.evaluate(() => window.scrollTo(0, 0));
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'Page overflow at ' + width);
      await page.screenshot({ path: '/artifacts/dashboard-' + width + '.png', fullPage: true });
    }
    await page.getByRole('link', { name: 'Витрати та підписки', exact: true }).click();
    await page.getByRole('button', { name: 'Редагувати витрату Browser test groceries', exact: true }).click();
    await page.getByRole('button', { name: 'Видалити витрату', exact: true }).click();
    await page.getByRole('button', { name: 'Залишити витрату', exact: true }).click();
    await page.getByRole('button', { name: 'Підтвердити видалення', exact: true }).waitFor({ state: 'hidden' });
    await page.getByRole('button', { name: 'Видалити витрату', exact: true }).click();
    const deleteResponse = page.waitForResponse(response => response.request().method() === 'DELETE' && /\/api\/expenses\/\d+$/.test(response.url()));
    await page.getByRole('button', { name: 'Підтвердити видалення', exact: true }).click();
    assert.equal((await deleteResponse).status(), 204);
    await page.locator('.expense-panel .notice').filter({ hasText: 'Витрату видалено' }).waitFor();
    const expensesAfterReload = page.waitForResponse(response => response.url().includes('/api/expenses?') && response.request().method() === 'GET');
    await page.reload();
    assert.ok((await (await expensesAfterReload).json()).expenses.every(expense => expense.description !== 'Browser test groceries'));
    await page.getByRole('heading', { name: 'Music', exact: true }).waitFor();
    assert.equal(await page.getByRole('button', { name: 'Редагувати витрату Browser test groceries', exact: true }).count(), 0);
    await page.getByRole('button', { name: 'Видалити підписку Music', exact: true }).click();
    await page.getByText('Підписок поки немає', { exact: true }).waitFor();
    assert.deepEqual(errors, []);
    console.log('Dashboard browser smoke passed: expenses, recurring checkbox/conversion/stop/persistence, subscriptions, charts, categories, responsive layouts.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
