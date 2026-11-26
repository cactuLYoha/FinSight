import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { SavingsPage } from './savings-page';
import { SavingsGoal } from './savings.service';

const goal: SavingsGoal = { id: 7, name: 'Подушка', currency: 'UAH', target_amount: '10000.00', deadline: '2028-12-31', status: 'active', saved_amount: '0.00', remaining_amount: '10000.00', progress_percent: '0.00', is_achieved: false };
describe('SavingsPage', () => {
  let http: HttpTestingController;
  beforeEach(() => {
    TestBed.configureTestingModule({ imports: [SavingsPage], providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])] });
    http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => { http.verify(); TestBed.resetTestingModule(); });
  function summary() {
    const request = http.expectOne(r => r.url === '/api/savings/summary');
    expect(request.request.params.get('year')).toBeTruthy();
    expect(request.request.params.get('month')).toBeTruthy();
    request.flush({ summary: { currency: 'UAH', income_total: '1000', expense_total: '100', net_savings: '900', available_to_save: '900', savings_rate_percent: '90' } });
  }
  function load() {
    const fixture = TestBed.createComponent(SavingsPage);
    summary(); http.expectOne('/api/savings/goals').flush({ goals: [goal, { ...goal, id: 8, currency: 'USD' }] });
    fixture.detectChanges(); return fixture;
  }
  function details(updated = goal) {
    http.expectOne('/api/savings/goals/7/plan').flush({ plan: { goal: updated, overdue: false, required_monthly_amount: '1000', is_feasible: null, history: { sample_size: 0 }, installments: [] } });
    http.expectOne('/api/savings/goals/7/contributions').flush({ contributions: [] });
  }
  it('shows only selected currency goals and renders missing history honestly', () => {
    const fixture = load(), page = fixture.componentInstance;
    expect(page.visibleGoals().length).toBe(1);
    page.selectGoal(goal); details(); fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Недостатньо історії');
    expect(fixture.nativeElement.textContent).toContain('90%');
    fixture.destroy();
  });
  it('opens the contribution form by clicking the rendered button and posts comma decimals', () => {
    const fixture = load(), page = fixture.componentInstance;
    fixture.nativeElement.querySelector('.goal-card').click(); details(); fixture.detectChanges();
    const button = Array.from(fixture.nativeElement.querySelectorAll('button') as NodeListOf<HTMLButtonElement>).find(item => item.textContent?.includes('+ Додати внесок'))!;
    button.click(); fixture.detectChanges();
    const input = fixture.nativeElement.querySelector('.contribution-editor input') as HTMLInputElement;
    expect(input).toBeTruthy(); expect(input.value).toBe('1000');
    input.value = '250,50'; input.dispatchEvent(new Event('input'));
    fixture.nativeElement.querySelector('.contribution-editor').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    const request = http.expectOne('/api/savings/goals/7/contributions');
    expect(request.request.method).toBe('POST'); expect(request.request.body.amount).toBe('250.50');
    request.flush({ contribution: { id: 1 } }); details(); summary(); fixture.destroy();
  });
  it('archives cancelled goals after the rendered confirmation button is clicked', () => {
    const fixture = load(), page = fixture.componentInstance;
    page.selectGoal(goal); details(); fixture.detectChanges();
    const click = (label: string) => {
      const button = Array.from(fixture.nativeElement.querySelectorAll('button') as NodeListOf<HTMLButtonElement>).find(item => item.textContent?.trim() === label)!;
      button.click(); fixture.detectChanges();
    };
    click('Скасувати ціль'); expect(fixture.nativeElement.querySelector('.confirmation')).toBeTruthy();
    http.expectNone('/api/savings/goals/7/cancel'); click('Підтвердити');
    const request = http.expectOne('/api/savings/goals/7/cancel'); expect(request.request.method).toBe('POST');
    request.flush({ goal: { ...goal, status: 'cancelled' } }); details({ ...goal, status: 'cancelled' }); summary();
    expect(page.visibleGoals()).toHaveLength(0);
    click('Показати завершені та скасовані'); expect(page.visibleGoals()).toHaveLength(1); fixture.destroy();
  });
  it('saves a new goal, fetches its plan and prevents duplicate writes', () => {
    const fixture = load(), page = fixture.componentInstance;
    page.openGoal();
    page.goalForm.setValue({ name: ' Подушка ', target_amount: '10000.00', deadline: page.minimumDeadline() });
    page.saveGoal(); page.saveGoal();
    const request = http.expectOne('/api/savings/goals');
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({ name: 'Подушка', target_amount: '10000.00', deadline: page.minimumDeadline(), currency: 'UAH' });
    request.flush({ goal }); details(); summary();
    expect(page.goalFormOpen()).toBe(false); expect(page.selected()?.id).toBe(7);
    fixture.destroy();
  });
  it('validates amount precision and future contribution dates before sending', () => {
    const fixture = load(), page = fixture.componentInstance;
    page.selectGoal(goal); details(); page.openContribution();
    page.contributionForm.patchValue({ amount: '1.001' }); page.saveContribution();
    page.contributionForm.patchValue({ amount: '10', contributed_on: '9999-12-31' }); page.saveContribution();
    http.expectNone('/api/savings/goals/7/contributions');
    expect(page.formError()).toBeTruthy(); fixture.destroy();
  });
  it('refreshes progress after a contribution and supports completing an achieved goal', () => {
    const fixture = load(), page = fixture.componentInstance;
    page.selectGoal(goal); details(); page.openContribution();
    page.contributionForm.patchValue({ amount: '10000.00', note: 'Перший внесок' }); page.saveContribution();
    const request = http.expectOne('/api/savings/goals/7/contributions');
    expect(request.request.body.contributed_on).toBe(page.today()); request.flush({ contribution: { id: 1 } });
    const achieved = { ...goal, saved_amount: '10000.00', remaining_amount: '0.00', progress_percent: '100.00', is_achieved: true };
    details(achieved); summary(); expect(page.selected()?.is_achieved).toBe(true);
    page.completeGoal(); http.expectOne('/api/savings/goals/7/complete').flush({ goal: { ...achieved, status: 'completed' } });
    details({ ...achieved, status: 'completed' }); summary(); fixture.detectChanges();
    expect(fixture.nativeElement.textContent).not.toContain('+ Додати внесок'); fixture.destroy();
  });
  it('requires confirmation for deletion and retains form input on conflict', () => {
    const fixture = load(), page = fixture.componentInstance;
    page.selectGoal(goal); details();
    page.confirmation.set({ kind: 'delete', id: 3 }); page.confirmAction();
    const request = http.expectOne('/api/savings/goals/7/contributions/3'); expect(request.request.method).toBe('DELETE');
    request.flush(null, { status: 204, statusText: 'No Content' }); details(); summary();
    page.openContribution(); page.contributionForm.patchValue({ amount: '50' }); page.saveContribution();
    http.expectOne('/api/savings/goals/7/contributions').flush({}, { status: 409, statusText: 'Conflict' });
    expect(page.contributionForm.controls.amount.value).toBe('50'); expect(page.formError()).toContain('Зміна недоступна');
    fixture.destroy();
  });
  it('patches goals without changing currency, edits contributions and cancels a goal', () => {
    const fixture = load(), page = fixture.componentInstance;
    page.openGoal(goal); page.goalForm.controls.deadline.setValue(page.minimumDeadline()); page.saveGoal();
    const update = http.expectOne('/api/savings/goals/7');
    expect(update.request.method).toBe('PATCH'); expect(update.request.body.currency).toBeUndefined();
    update.flush({ goal }); details(); summary();
    page.openContribution({ id: 4, goal_id: 7, amount: '20', contributed_on: page.today(), note: null });
    page.contributionForm.controls.amount.setValue('30'); page.saveContribution();
    const contribution = http.expectOne('/api/savings/goals/7/contributions/4');
    expect(contribution.request.method).toBe('PATCH'); expect(contribution.request.body.amount).toBe('30');
    contribution.flush({ contribution: { id: 4 } }); details(); summary();
    page.confirmation.set({ kind: 'cancel', id: 7 }); page.confirmAction();
    http.expectOne('/api/savings/goals/7/cancel').flush({ goal: { ...goal, status: 'cancelled' } });
    details({ ...goal, status: 'cancelled' }); summary();
    expect(page.selected()?.status).toBe('cancelled'); fixture.destroy();
  });
  it('keeps goals usable when the summary fails and redirects expired sessions', () => {
    const fixture = TestBed.createComponent(SavingsPage), page = fixture.componentInstance;
    http.expectOne(r => r.url === '/api/savings/summary').flush({}, { status: 503, statusText: 'Unavailable' });
    http.expectOne('/api/savings/goals').flush({ goals: [goal] });
    expect(page.visibleGoals().length).toBe(1); expect(page.summaryError()).toBeTruthy();
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    page.selectGoal(goal);
    http.expectOne('/api/savings/goals/7/plan').flush({}, { status: 401, statusText: 'Unauthorized' });
    http.expectOne('/api/savings/goals/7/contributions').flush({ contributions: [] });
    expect(navigate).toHaveBeenCalledWith(['/login'], { queryParams: { returnUrl: '/savings' } }); fixture.destroy();
  });
  it('deletes an empty goal only after confirmation', () => {
    const fixture = load(), page = fixture.componentInstance;
    page.selectGoal(goal); details(); page.requestConfirmation('deleteGoal', goal.id);
    http.expectNone('/api/savings/goals/7'); page.confirmAction();
    const request = http.expectOne('/api/savings/goals/7'); expect(request.request.method).toBe('DELETE');
    request.flush(null, { status: 204, statusText: 'No Content' }); summary();
    expect(page.selected()).toBeNull(); expect(page.visibleGoals()).toHaveLength(0); fixture.destroy();
  });
  it('reactivates an archived goal with a new deadline and loads the new plan', () => {
    const fixture = load(), page = fixture.componentInstance;
    const archived = { ...goal, status: 'cancelled' as const };
    page.selectGoal(archived); details(archived); fixture.detectChanges();
    const button = Array.from(fixture.nativeElement.querySelectorAll('button') as NodeListOf<HTMLButtonElement>).find(item => item.textContent?.trim() === 'Зробити ціль активною')!;
    button.click(); fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.restore-editor')).toBeTruthy();
    page.restoreForm.controls.deadline.setValue('2020-01-01'); page.restoreGoal(); http.expectNone('/api/savings/goals/7/reactivate');
    const deadline = page.minimumDeadline(); page.restoreForm.controls.deadline.setValue(deadline); page.restoreGoal(); page.restoreGoal();
    const request = http.expectOne('/api/savings/goals/7/reactivate'); expect(request.request.method).toBe('POST'); expect(request.request.body).toEqual({ deadline });
    request.flush({ goal: { ...goal, deadline } }); details({ ...goal, deadline }); summary();
    expect(page.restoreOpen()).toBe(false); expect(page.selected()?.status).toBe('active'); fixture.destroy();
  });
  it('transfers all contributions to a new goal and refreshes both goal balances', () => {
    const fixture = load(), page = fixture.componentInstance;
    const funded = { ...goal, saved_amount: '250.50' };
    page.selectGoal(funded); details(funded); page.openTransfer();
    page.transferForm.setValue({ target: 'new', name: 'Нова ціль', target_amount: '500,00', deadline: page.minimumDeadline() });
    page.transferSavings();
    const request = http.expectOne('/api/savings/goals/7/transfer');
    expect(request.request.method).toBe('POST'); expect(request.request.body.new_goal.target_amount).toBe('500.00');
    const target = { ...funded, id: 9, name: 'Нова ціль' };
    request.flush({ source: { ...goal, status: 'cancelled' }, target, transferred_amount: '250.50' });
    http.expectOne('/api/savings/goals/9/plan').flush({ plan: { goal: target, history: { sample_size: 0 }, installments: [] } });
    http.expectOne('/api/savings/goals/9/contributions').flush({ contributions: [] }); summary();
    expect(page.selected()?.id).toBe(9); expect(page.visibleGoals()).toHaveLength(1); fixture.destroy();
  });
});
