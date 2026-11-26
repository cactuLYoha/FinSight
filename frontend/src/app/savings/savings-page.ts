import { HttpErrorResponse } from '@angular/common/http';
import { afterNextRender, Component, computed, DestroyRef, ElementRef, inject, Injector, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { catchError, finalize, forkJoin, Observable, of, Subscription, timeout } from 'rxjs';
import { Contribution, SavingsGoal, SavingsPlan, SavingsService, SavingsSummary } from './savings.service';

const amountValidators = [Validators.required, Validators.min(.01), Validators.pattern(/^(?:0|[1-9]\d{0,12})(?:\.\d{1,2})?$/)];

@Component({
  selector: 'app-savings-page', imports: [ReactiveFormsModule, RouterLink],
  templateUrl: './savings-page.html', styleUrl: './savings-page.scss',
})
export class SavingsPage {
  private readonly api = inject(SavingsService);
  private readonly fb = inject(FormBuilder);
  private readonly destroyRef = inject(DestroyRef);
  private readonly router = inject(Router);
  private readonly element = inject<ElementRef<HTMLElement>>(ElementRef);
  private readonly injector = inject(Injector);
  private summaryRequest?: Subscription;
  private goalsRequest?: Subscription;
  private detailRequest?: Subscription;
  readonly currency = signal('UAH');
  readonly month = signal(new Date().toISOString().slice(0, 7));
  readonly summary = signal<SavingsSummary | null>(null);
  readonly goals = signal<SavingsGoal[]>([]);
  readonly selected = signal<SavingsGoal | null>(null);
  readonly plan = signal<SavingsPlan | null>(null);
  readonly contributions = signal<Contribution[]>([]);
  readonly sourceAccounts = signal<{ id: number; name: string }[]>([]);
  readonly sourceAccount = signal('');
  readonly loading = signal(false);
  readonly summaryLoading = signal(false);
  readonly detailLoading = signal(false);
  readonly saving = signal(false);
  readonly error = signal('');
  readonly summaryError = signal('');
  readonly detailError = signal('');
  readonly planError = signal('');
  readonly formError = signal('');
  readonly notice = signal('');
  readonly goalFormOpen = signal(false);
  readonly editingGoal = signal<number | null>(null);
  readonly contributionFormOpen = signal(false);
  readonly editingContribution = signal<number | null>(null);
  readonly confirmation = signal<{ kind: 'cancel' | 'delete' | 'deleteGoal'; id: number } | null>(null);
  readonly transferOpen = signal(false);
  readonly restoreOpen = signal(false);
  readonly restoreForm = this.fb.nonNullable.group({ deadline: ['', Validators.required] });
  readonly transferTargets = computed(() => this.goals().filter(goal => goal.id !== this.selected()?.id && goal.status === 'active' && goal.currency === this.selected()?.currency));
  readonly transferForm = this.fb.nonNullable.group({
    target: ['new', Validators.required], name: ['', [Validators.maxLength(120)]],
    target_amount: [''], deadline: [''],
  });
  readonly showArchived = signal(false);
  readonly visibleGoals = computed(() => this.goals().filter(goal => goal.currency === this.currency() && (this.showArchived() || goal.status === 'active')));
  readonly activeCount = computed(() => this.goals().filter(goal => goal.currency === this.currency() && goal.status === 'active').length);
  readonly statusNames = { active: 'Активна', completed: 'Завершена', cancelled: 'Скасована' };
  readonly goalForm = this.fb.nonNullable.group({
    name: ['', [Validators.required, Validators.maxLength(120), Validators.pattern(/\S/)]],
    target_amount: ['', amountValidators], deadline: ['', Validators.required],
  });
  readonly contributionForm = this.fb.nonNullable.group({
    amount: ['', amountValidators], contributed_on: [this.today(), Validators.required],
    note: ['', Validators.maxLength(500)],
  });

  constructor() { this.load(); }

  load(): void {
    this.loadSummary();
    this.goalsRequest?.unsubscribe(); this.loading.set(true); this.error.set('');
    this.goalsRequest = this.api.goals().pipe(timeout(15000), takeUntilDestroyed(this.destroyRef), finalize(() => this.loading.set(false))).subscribe({
      next: ({ goals }) => {
        this.goals.set(goals);
        const selected = goals.find(goal => goal.id === this.selected()?.id);
        if (selected) this.selectGoal(selected);
        else if (this.selected()) this.clearDetail();
      }, error: error => this.failed(error, this.error),
    });
  }
  loadSummary(): void {
    this.summaryRequest?.unsubscribe(); this.summaryLoading.set(true); this.summary.set(null); this.summaryError.set('');
    this.summaryRequest = this.api.summary(this.month(), this.currency()).pipe(timeout(15000), takeUntilDestroyed(this.destroyRef), finalize(() => this.summaryLoading.set(false))).subscribe({
      next: ({ summary }) => this.summary.set(summary), error: error => this.failed(error, this.summaryError),
    });
  }
  selectGoal(goal: SavingsGoal): void {
    if (this.saving()) return;
    this.detailRequest?.unsubscribe(); this.selected.set(goal); this.plan.set(null); this.contributions.set([]);
    this.sourceAccounts.set([]); this.sourceAccount.set('');
    this.detailError.set(''); this.planError.set(''); this.formError.set(''); this.confirmation.set(null);
    this.transferOpen.set(false);
    this.restoreOpen.set(false);
    this.contributionFormOpen.set(false); this.detailLoading.set(true);
    this.detailRequest = forkJoin({
      plan: this.api.plan(goal.id).pipe(timeout(15000), catchError(error => { this.failed(error, this.planError); return of(null); })),
      contributions: this.api.contributions(goal.id).pipe(timeout(15000), catchError(error => { this.failed(error, this.detailError); return of(null); })),
    }).pipe(takeUntilDestroyed(this.destroyRef), finalize(() => this.detailLoading.set(false))).subscribe(result => {
      this.plan.set(result.plan?.plan ?? null); this.contributions.set(result.contributions?.contributions ?? []);
      this.sourceAccounts.set(result.contributions?.accounts ?? []);
      if (result.plan) this.replaceGoal(result.plan.plan.goal);
    });
  }
  private clearDetail(): void {
    this.detailRequest?.unsubscribe(); this.selected.set(null); this.plan.set(null); this.contributions.set([]);
    this.confirmation.set(null); this.contributionFormOpen.set(false);
    this.transferOpen.set(false);
  }
  changeCurrency(event: Event): void {
    if (this.saving()) return;
    this.currency.set((event.target as HTMLSelectElement).value); this.clearDetail();
    this.goalFormOpen.set(false); this.notice.set(''); this.loadSummary();
  }
  changeMonth(event: Event): void {
    const value = (event.target as HTMLInputElement).value;
    if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(value) || value < '0001-01' || value > '9998-12') return;
    this.month.set(value); this.loadSummary();
  }
  openGoal(goal?: SavingsGoal): void {
    if (this.saving()) return;
    this.editingGoal.set(goal?.id ?? null);
    this.goalForm.reset({ name: goal?.name ?? '', target_amount: goal?.target_amount ?? '', deadline: goal?.deadline ?? this.minimumDeadline() });
    this.formError.set(''); this.goalFormOpen.set(true);
    this.focus('.editor input');
  }
  saveGoal(): void {
    if (this.saving()) return;
    this.goalForm.controls.name.setValue(this.goalForm.controls.name.value.trim());
    this.goalForm.controls.target_amount.setValue(this.normalizeAmount(this.goalForm.controls.target_amount.value));
    const values = this.goalForm.getRawValue();
    if (this.goalForm.invalid || !this.validDate(values.deadline) || values.deadline < this.minimumDeadline()) {
      this.goalForm.markAllAsTouched(); this.formError.set('Вкажіть назву, додатну суму до двох десяткових знаків і дату з наступного місяця.'); return;
    }
    const id = this.editingGoal();
    this.mutate(id === null ? this.api.createGoal({ ...values, currency: this.currency() }) : this.api.updateGoal(id, values), 'Ціль збережено.', result => {
      this.replaceGoal(result.goal); this.goalFormOpen.set(false); this.selectGoal(result.goal);
    });
  }
  openContribution(item?: Contribution): void {
    if (this.saving() || this.selected()?.status !== 'active') return;
    this.confirmation.set(null);
    this.editingContribution.set(item?.id ?? null);
    this.sourceAccount.set(item?.account_id?.toString() ?? this.sourceAccounts()[0]?.id.toString() ?? '');
    this.contributionForm.reset({ amount: item?.amount ?? this.plan()?.required_monthly_amount ?? '', contributed_on: item?.contributed_on ?? this.today(), note: item?.note ?? '' });
    this.formError.set(''); this.contributionFormOpen.set(true);
    this.focus('.contribution-editor input');
  }
  requestConfirmation(kind: 'cancel' | 'delete' | 'deleteGoal', id: number): void {
    if (this.saving()) return;
    this.contributionFormOpen.set(false); this.formError.set('');
    this.transferOpen.set(false);
    this.confirmation.set({ kind, id }); this.focus('.confirmation button');
  }
  private focus(selector: string): void {
    afterNextRender(() => {
      const target = this.element.nativeElement.querySelector<HTMLElement>(selector);
      target?.focus(); target?.scrollIntoView?.({ block: 'nearest' });
    }, { injector: this.injector });
  }
  private normalizeAmount(value: string): string { return value.trim().replace(',', '.'); }
  saveContribution(): void {
    const goal = this.selected();
    if (!goal || goal.status !== 'active' || this.saving()) return;
    this.contributionForm.controls.amount.setValue(this.normalizeAmount(this.contributionForm.controls.amount.value));
    const values = this.contributionForm.getRawValue();
    if (this.contributionForm.invalid || !this.validDate(values.contributed_on) || values.contributed_on > this.today()) {
      this.contributionForm.markAllAsTouched(); this.formError.set('Вкажіть додатну суму до двох десяткових знаків, дату не пізніше сьогодні та примітку до 500 символів.'); return;
    }
    const id = this.editingContribution();
    const payload = { ...values, ...(this.sourceAccount() ? { account_id: Number(this.sourceAccount()) } : {}) };
    this.mutate(id === null ? this.api.addContribution(goal.id, payload) : this.api.updateContribution(goal.id, id, payload), 'Внесок збережено. Баланс рахунку оновлено.', () => this.selectGoal(goal));
  }
  completeGoal(): void {
    const goal = this.selected();
    if (!goal || goal.status !== 'active' || !goal.is_achieved) return;
    this.mutate(this.api.complete(goal.id), 'Ціль завершено. Вітаємо!', result => { this.replaceGoal(result.goal); this.selectGoal(result.goal); });
  }
  openRestore(): void {
    if (this.saving() || this.selected()?.status !== 'cancelled') return;
    this.transferOpen.set(false); this.confirmation.set(null); this.formError.set('');
    this.restoreForm.reset({ deadline: this.minimumDeadline() });
    this.restoreOpen.set(true); this.focus('.restore-editor input');
  }
  restoreGoal(): void {
    const goal = this.selected(), deadline = this.restoreForm.controls.deadline.value;
    if (!goal || goal.status !== 'cancelled' || this.saving()) return;
    if (!this.validDate(deadline) || deadline < this.minimumDeadline()) {
      this.formError.set('Оберіть новий строк із наступного місяця або пізніше.'); return;
    }
    this.mutate(this.api.reactivate(goal.id, deadline), 'Ціль знову активна. Строк і план накопичення оновлено.', result => {
      this.restoreOpen.set(false); this.replaceGoal(result.goal); this.selectGoal(result.goal);
    });
  }
  confirmAction(): void {
    const action = this.confirmation(), goal = this.selected();
    if (!action || !goal) return;
    if (action.kind === 'deleteGoal') {
      this.mutate(this.api.deleteGoal(goal.id), 'Порожню ціль видалено.', () => {
        this.clearDetail(); this.goals.update(goals => goals.filter(item => item.id !== goal.id));
      });
      return;
    }
    if (goal.status !== 'active') return;
    if (action.kind === 'cancel') this.mutate(this.api.cancel(goal.id), 'Ціль скасовано.', result => { this.replaceGoal(result.goal); this.selectGoal(result.goal); });
    else this.mutate(this.api.deleteContribution(goal.id, action.id), 'Внесок видалено.', () => this.selectGoal(goal));
  }
  openTransfer(): void {
    const goal = this.selected();
    if (!goal || this.saving()) return;
    this.contributionFormOpen.set(false); this.confirmation.set(null); this.formError.set('');
    this.transferForm.reset({ target: this.transferTargets()[0]?.id.toString() ?? 'new', name: '', target_amount: goal.target_amount, deadline: this.minimumDeadline() });
    this.transferOpen.set(true); this.focus('.transfer-editor select');
  }
  transferSavings(): void {
    const goal = this.selected();
    if (!goal || this.saving()) return;
    const values = this.transferForm.getRawValue();
    const amount = this.normalizeAmount(values.target_amount);
    const newGoal = values.target === 'new';
    if (newGoal && (!values.name.trim() || values.name.trim().length > 120 || !/^(?:0|[1-9]\d{0,12})(?:\.\d{1,2})?$/.test(amount) || Number(amount) <= 0 || !this.validDate(values.deadline) || values.deadline < this.minimumDeadline())) {
      this.formError.set('Вкажіть назву нової цілі, додатну суму до двох десяткових знаків і строк із наступного місяця.'); return;
    }
    this.mutate(this.api.transfer(goal.id, newGoal ? { new_goal: { name: values.name.trim(), target_amount: amount, deadline: values.deadline, currency: goal.currency } } : { target_goal_id: Number(values.target) }), 'Усі внески перенесено. Загальна сума заощаджень збережена.', result => {
      this.replaceGoal(result.source); this.replaceGoal(result.target); this.selectGoal(result.target);
    });
  }
  private mutate<T>(request: Observable<T>, message: string, done: (result: T) => void): void {
    if (this.saving()) return;
    this.saving.set(true); this.formError.set(''); this.notice.set('');
    request.pipe(timeout(15000), takeUntilDestroyed(this.destroyRef), finalize(() => this.saving.set(false))).subscribe({
      next: result => { this.saving.set(false); this.confirmation.set(null); this.notice.set(message); done(result); this.loadSummary(); },
      error: error => this.failed(error, this.formError),
    });
  }
  private replaceGoal(goal: SavingsGoal): void {
    this.goals.update(goals => goals.some(item => item.id === goal.id) ? goals.map(item => item.id === goal.id ? goal : item) : [goal, ...goals]);
    if (this.selected()?.id === goal.id) this.selected.set(goal);
  }
  today(): string { return new Date().toISOString().slice(0, 10); }
  minimumDeadline(): string {
    const date = new Date(this.today() + 'T00:00:00Z'); date.setUTCMonth(date.getUTCMonth() + 1, 1);
    return date.toISOString().slice(0, 10);
  }
  private validDate(value: string): boolean {
    const date = new Date(value + 'T00:00:00Z');
    return /^\d{4}-\d{2}-\d{2}$/.test(value) && value >= '0001-01-01' && !isNaN(date.getTime()) && date.toISOString().slice(0, 10) === value;
  }
  money(value: string | number, currency = this.currency()): string { return new Intl.NumberFormat('uk-UA', { style: 'currency', currency }).format(Number(value)); }
  dateLabel(value: string): string { return new Intl.DateTimeFormat('uk-UA', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' }).format(new Date(value + 'T00:00:00Z')); }
  private failed(error: unknown, target: { set(value: string): void }): void {
    if (error instanceof HttpErrorResponse) {
      if (error.status === 409 && error.error?.message === 'Another active savings goal already exists.') { target.set('У вас уже є активна ціль. Спочатку завершіть або скасуйте її, а потім відновіть цю.'); return; }
      if (error.status === 401) { void this.router.navigate(['/login'], { queryParams: { returnUrl: '/savings' } }); return; }
      if (error.status === 400) { target.set('Перевірте суму й дати. Строк цілі — з наступного місяця, дата внеску — не пізніше сьогодні.'); return; }
      if (error.status === 409) { target.set('Зміна недоступна. Видаляти можна лише порожню ціль; переносити кошти — до активної цілі в тій самій валюті. Одночасно може бути лише одна активна ціль. Оновіть дані.'); return; }
      if (error.status === 404) { target.set('Ціль або внесок більше не існує. Оновіть дані.'); return; }
    }
    target.set('Не вдалося виконати запит. Перевірте з’єднання й оновіть дані перед повторним збереженням.');
  }
}
