import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { ExpensesPanel } from './expenses-panel';

describe('ExpensesPanel', () => {
  let http: HttpTestingController;
  beforeEach(() => {
    TestBed.configureTestingModule({ imports: [ExpensesPanel], providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])] });
    http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => { http.verify(); TestBed.resetTestingModule(); });
  function setup() {
    const fixture = TestBed.createComponent(ExpensesPanel);
    fixture.componentRef.setInput('month', '2026-11');
    fixture.componentRef.setInput('currency', 'UAH');
    fixture.detectChanges();
    http.expectOne(r => r.url === '/api/expenses').flush({ expenses: [], total: 0, page: 1, accounts: [], categories: [{ id: 1, name: 'Продукти' }] });
    return fixture;
  }
  it('submits an expense for the selected month and refreshes the list', () => {
    const fixture = setup(), panel = fixture.componentInstance;
    panel.form.setValue({ amount: '125.50', category_id: '1', account_id: '', date: '2026-11-15', description: 'Продукти', recurring: false });
    let saved = false;
    panel.saved.subscribe(() => saved = true);
    panel.add();
    const request = http.expectOne('/api/expenses');
    expect(request.request.body).toEqual({ amount: '125.50', category_id: 1, account_id: null, date: '2026-11-15', description: 'Продукти', currency: 'UAH', recurring: false });
    request.flush({ expense: { id: 1 } });
    http.expectOne(r => r.url === '/api/expenses').flush({ expenses: [], total: 0, page: 1, accounts: [], categories: [] });
    expect(saved).toBe(true);
    expect(panel.saving()).toBe(false);
    expect(panel.notice()).toContain('Витрату додано');
    fixture.destroy();
  });
  it('rejects a date outside the selected month and invalid amounts', () => {
    const fixture = setup(), panel = fixture.componentInstance;
    panel.form.setValue({ amount: '125.50', category_id: '1', account_id: '', date: '2026-10-15', description: 'Продукти', recurring: false });
    panel.add(); http.expectNone('/api/expenses');
    expect(panel.formError()).toContain('дату');
    panel.form.patchValue({ date: '2026-11-15', amount: '-1' });
    panel.add(); http.expectNone('/api/expenses');
    fixture.destroy();
  });
  it('opens the existing expense from its button and patches all editable fields', () => {
    const fixture = setup(), panel = fixture.componentInstance;
    const expense = { id: 15, amount: '125.50', description: 'Продукти', date: '2026-11-15', category: 'Продукти', account: 'Bank', account_id: 4, category_id: 1, recurring_id: 10, recurring_active: true };
    panel.data.set({ expenses: [expense], total: 1, page: 1, accounts: [{ id: 4, name: 'Bank' }], categories: [{ id: 1, name: 'Продукти' }] });
    fixture.detectChanges();
    fixture.nativeElement.querySelector('[aria-label="Редагувати витрату Продукти"]').click(); fixture.detectChanges();
    expect(panel.form.controls.amount.value).toBe('125.50');
    expect(panel.form.controls.account_id.value).toBe('4');
    expect(fixture.nativeElement.querySelector('.repeat-choice')).toBeNull();
    panel.form.patchValue({ amount: '100,25', description: 'Оновлено', date: '2026-12-01' });
    fixture.nativeElement.querySelector('form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    panel.add();
    const request = http.expectOne('/api/expenses/15');
    expect(request.request.method).toBe('PATCH');
    expect(request.request.body).toEqual({ amount: '100.25', description: 'Оновлено', date: '2026-12-01', category_id: 1, account_id: 4 });
    request.flush({ expense: { ...expense, amount: '100.25' } });
    http.expectOne(r => r.url === '/api/expenses').flush({ expenses: [], total: 0, page: 1, accounts: [], categories: [] });
    expect(panel.editing()).toBeNull(); expect(panel.open()).toBe(false);
    expect(panel.notice()).toContain('Витрату оновлено'); fixture.destroy();
  });
  it('retains edits on API failure and cancels without sending a write', () => {
    const fixture = setup(), panel = fixture.componentInstance;
    const expense = { id: 2, amount: '20.00', description: 'Їжа', date: '2026-11-01', category: 'Продукти', account: 'Bank', account_id: 4, category_id: 1 };
    panel.edit(expense); panel.form.controls.amount.setValue('30.00'); panel.add();
    http.expectOne('/api/expenses/2').flush({}, { status: 400, statusText: 'Bad Request' });
    expect(panel.form.controls.amount.value).toBe('30.00'); expect(panel.formError()).toBeTruthy();
    panel.toggleForm(); expect(panel.editing()).toBeNull(); expect(panel.open()).toBe(false);
    http.expectNone('/api/expenses/2'); fixture.destroy();
  });
  it('deletes from the edit form only after confirmation, prevents duplicate requests and refreshes', () => {
    const fixture = setup(), panel = fixture.componentInstance;
    panel.edit({ id: 2, amount: '20.00', description: 'Їжа', date: '2026-11-01', category: 'Продукти', account: 'Bank', account_id: 4, category_id: 1 });
    fixture.detectChanges();
    const buttons = () => Array.from(fixture.nativeElement.querySelectorAll('button') as NodeListOf<HTMLButtonElement>);
    panel.deleteExpense(); http.expectNone('/api/expenses/2');
    buttons().find(button => button.textContent?.trim() === 'Видалити витрату')!.click(); fixture.detectChanges();
    http.expectNone('/api/expenses/2');
    buttons().find(button => button.textContent?.trim() === 'Залишити витрату')!.click(); fixture.detectChanges();
    expect(panel.deleteConfirm()).toBe(false);
    buttons().find(button => button.textContent?.trim() === 'Видалити витрату')!.click(); fixture.detectChanges();
    buttons().find(button => button.textContent?.trim() === 'Підтвердити видалення')!.click(); panel.deleteExpense();
    const request = http.expectOne('/api/expenses/2'); expect(request.request.method).toBe('DELETE');
    request.flush(null, { status: 204, statusText: 'No Content' });
    http.expectOne(r => r.url === '/api/expenses').flush({ expenses: [], total: 0, page: 1, accounts: [], categories: [] });
    expect(panel.editing()).toBeNull(); expect(panel.open()).toBe(false); expect(panel.notice()).toContain('Витрату видалено'); fixture.destroy();
  });
  it('sends the monthly choice and stops a recurring rule without deleting transactions', () => {
    const fixture = setup(), panel = fixture.componentInstance;
    panel.form.setValue({ amount: '9000', category_id: '1', account_id: '', date: '2026-11-05', description: 'Оренда', recurring: true });
    panel.add();
    const request = http.expectOne('/api/expenses');
    expect(request.request.body.recurring).toBe(true);
    request.flush({ recurring_expense: { id: 10 } });
    const rule = { id: 10, description: 'Оренда', amount: '9000', category: 'Житло', billing_day: 5, next_due_on: '2026-12-05' };
    http.expectOne(r => r.url === '/api/expenses').flush({ expenses: [], total: 0, page: 1, accounts: [], categories: [], recurring_expenses: [rule] });
    panel.stop(rule);
    const stop = http.expectOne('/api/expenses/recurring/10');
    expect(stop.request.method).toBe('DELETE');
    stop.flush(null, { status: 204, statusText: 'No Content' });
    http.expectOne(r => r.url === '/api/expenses').flush({ expenses: [], total: 0, page: 1, accounts: [], categories: [], recurring_expenses: [] });
    expect(panel.notice()).toContain('Попередні витрати збережено');
    fixture.destroy();
  });
  it('shows stopped status on the existing transaction after stopping its rule', () => {
    const fixture = setup(), panel = fixture.componentInstance;
    const expense = { id: 15, amount: '9000', description: 'Оренда', date: '2026-11-05', category: 'Житло', account: 'Готівка', recurring_id: 10, recurring_active: true };
    panel.data.set({ expenses: [expense], total: 1, page: 1, accounts: [], categories: [] });
    fixture.detectChanges();
    const button = fixture.nativeElement.querySelector('[aria-label="Зупинити повторення операції Оренда"]');
    expect(button).toBeTruthy();
    button.click();
    http.expectOne('/api/expenses/recurring/10').flush(null, { status: 204, statusText: 'No Content' });
    http.expectOne(r => r.url === '/api/expenses').flush({ expenses: [{ ...expense, recurring_active: false }], total: 1, page: 1, accounts: [], categories: [], recurring_expenses: [] });
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Повторення зупинено');
    expect(fixture.nativeElement.querySelector('[aria-label="Повторювати щомісяця Оренда"]')).toBeTruthy();
    expect(fixture.nativeElement.querySelector('[aria-label="Зупинити повторення операції Оренда"]')).toBeNull();
    fixture.destroy();
  });
});
