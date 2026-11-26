import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { AccountsPage } from './accounts-page';

const account = { id: 1, name: 'Bank', account_type: 'bank', currency: 'UAH', balance: '100.00' };
describe('AccountsPage', () => {
  let http: HttpTestingController;
  beforeEach(() => { TestBed.configureTestingModule({ imports: [AccountsPage], providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])] }); http = TestBed.inject(HttpTestingController); });
  afterEach(() => { http.verify(); TestBed.resetTestingModule(); });
  function setup() {
    const fixture = TestBed.createComponent(AccountsPage);
    http.expectOne('/api/accounts').flush({ accounts: [account, { ...account, id: 2, balance: '20.25' }, { ...account, id: 3, currency: 'USD', balance: '10' }] });
    fixture.detectChanges(); return fixture;
  }
  function history() { http.expectOne(r => r.url === '/api/accounts/1/incomes').flush({ incomes: [], total: 0, page: 1 }); }
  it('uploads a PDF into the opened account and refreshes balances after import', () => {
    const fixture = setup(), page = fixture.componentInstance;
    expect(fixture.nativeElement.querySelector('app-statement-upload')).toBeNull();
    fixture.nativeElement.querySelector('.account-card').click(); history(); fixture.detectChanges();
    const uploader = fixture.nativeElement.querySelector('app-statement-upload');
    expect(uploader.textContent).toContain('Bank');
    expect(uploader.querySelector('select')).toBeNull();
    const input = uploader.querySelector('input[type=file]');
    Object.defineProperty(input, 'files', { value: [new File(['%PDF-test'], 'bank.pdf', { type: 'application/pdf' })] });
    input.dispatchEvent(new Event('change')); fixture.detectChanges();
    const button = Array.from(uploader.querySelectorAll('button')).find((item: any) => item.textContent.includes('Імпортувати PDF')) as HTMLButtonElement;
    button.click(); fixture.detectChanges();
    page.select({ ...account, id: 2 });
    expect(page.selected()?.id).toBe(1);
    const request = http.expectOne('/api/statements/import');
    expect(request.request.body.get('account_id')).toBe('1');
    expect(request.request.body.get('file').name).toBe('bank.pdf');
    request.flush({ imported_count: 1, duplicate: false });
    http.expectOne('/api/accounts').flush({ accounts: [{ ...account, balance: '150.00' }] });
    history(); fixture.detectChanges();
    expect(page.selected()?.balance).toBe('150.00');
    expect(page.statementBusy()).toBe(false);
    expect(uploader.textContent).toContain('Збережено операцій: 1');
    fixture.destroy();
  });
  it('groups balances by currency and opens account history', () => {
    const fixture = setup(), page = fixture.componentInstance;
    expect(page.totals()).toEqual([{ currency: 'UAH', amount: 120.25 }, { currency: 'USD', amount: 10 }]);
    fixture.nativeElement.querySelector('.account-card').click(); history(); fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Історія надходжень'); fixture.destroy();
  });
  it('creates and edits accounts without changing currency or balance', () => {
    const fixture = setup(), page = fixture.componentInstance;
    page.open('create'); page.accountForm.setValue({ name: ' New bank ', account_type: 'bank', currency: 'UAH' }); page.saveAccount(); page.saveAccount();
    const create = http.expectOne('/api/accounts'); expect(create.request.method).toBe('POST'); expect(create.request.body.name).toBe('New bank'); create.flush({ account }); history();
    page.open('edit'); page.accountForm.controls.name.setValue('Renamed'); page.saveAccount();
    const update = http.expectOne('/api/accounts/1'); expect(update.request.method).toBe('PATCH'); expect(update.request.body).toEqual({ name: 'Renamed', account_type: 'bank' }); update.flush({ account: { ...account, name: 'Renamed' } }); history();
    expect(page.selected()?.name).toBe('Renamed'); fixture.destroy();
  });
  it('posts comma decimals and immediately updates the balance and history', () => {
    const fixture = setup(), page = fixture.componentInstance;
    page.select(account); history(); page.open('income');
    page.incomeForm.patchValue({ amount: '250,50', description: ' Salary ' }); page.saveIncome(); page.saveIncome();
    const request = http.expectOne('/api/accounts/1/incomes'); expect(request.request.method).toBe('POST'); expect(request.request.body.amount).toBe('250.50'); expect(request.request.body.description).toBe('Salary');
    request.flush({ account: { ...account, balance: '350.50' }, income: { id: 1 } }); history();
    expect(page.selected()?.balance).toBe('350.50'); expect(page.editor()).toBeNull(); fixture.destroy();
  });
  it('rejects future incomes and preserves form input after an API error', () => {
    const fixture = setup(), page = fixture.componentInstance;
    page.select(account); history(); page.open('income');
    page.incomeForm.setValue({ amount: '10', description: 'Income', date: '9999-12-31', recurring: false }); page.saveIncome(); http.expectNone('/api/accounts/1/incomes');
    page.incomeForm.controls.date.setValue(page.today()); page.saveIncome();
    http.expectOne('/api/accounts/1/incomes').flush({}, { status: 400, statusText: 'Bad Request' });
    expect(page.incomeForm.controls.amount.value).toBe('10'); expect(page.formError()).toBeTruthy(); expect(page.selected()?.balance).toBe('100.00'); fixture.destroy();
  });
  it('schedules future monthly income and supports stopping and converting income', () => {
    const fixture = setup(), page = fixture.componentInstance;
    page.select(account); history(); page.open('income');
    const future = new Date(); future.setUTCMonth(future.getUTCMonth() + 1, 5);
    page.incomeForm.setValue({ amount: '100', date: future.toISOString().slice(0, 10), description: 'Salary', recurring: true });
    page.saveIncome();
    const request = http.expectOne('/api/accounts/1/incomes'); expect(request.request.body.recurring).toBe(true);
    request.flush({ account }); history();
    page.stopIncome(3); const stop = http.expectOne('/api/accounts/1/recurring-incomes/3'); expect(stop.request.method).toBe('DELETE'); stop.flush(null, { status: 204, statusText: 'No Content' }); history();
    page.repeatIncome({ id: 4, account_id: 1, amount: '100', date: page.today(), description: 'Salary' });
    const repeat = http.expectOne('/api/accounts/1/incomes/4/repeat'); expect(repeat.request.method).toBe('POST'); repeat.flush({ account }); history(); fixture.destroy();
  });
});
