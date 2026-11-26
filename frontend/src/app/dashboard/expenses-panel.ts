import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { afterNextRender, Component, DestroyRef, effect, ElementRef, inject, Injector, input, output, signal, untracked } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import { finalize, Subscription, timeout } from 'rxjs';

interface Option { id: number; name: string; }
interface Expense { id: number; amount: string; description: string; date: string; category: string; account: string; account_id?: number; category_id?: number; recurring_id?: number | null; recurring_active?: boolean; }
interface RecurringExpense { id: number; description: string; amount: string; category: string; billing_day: number; next_due_on: string; }
interface ExpenseList { expenses: Expense[]; total: number; page: number; accounts: Option[]; categories: Option[]; recurring_expenses?: RecurringExpense[]; }

@Component({
  selector: 'app-expenses-panel', imports: [ReactiveFormsModule],
  templateUrl: './expenses-panel.html', styleUrl: './expenses-panel.scss',
})
export class ExpensesPanel {
  readonly month = input.required<string>();
  readonly currency = input.required<string>();
  readonly saved = output<void>();
  readonly busy = output<boolean>();
  readonly refreshVersion = input(0);
  private readonly http = inject(HttpClient);
  private readonly fb = inject(FormBuilder);
  private readonly destroyRef = inject(DestroyRef);
  private readonly router = inject(Router);
  private readonly element = inject<ElementRef<HTMLElement>>(ElementRef);
  private readonly injector = inject(Injector);
  private request?: Subscription;
  private scope = '';
  readonly data = signal<ExpenseList | null>(null);
  readonly page = signal(1);
  readonly loading = signal(false);
  readonly saving = signal(false);
  readonly error = signal('');
  readonly formError = signal('');
  readonly notice = signal('');
  readonly open = signal(false);
  readonly editing = signal<Expense | null>(null);
  readonly deleteConfirm = signal(false);
  readonly form = this.fb.nonNullable.group({
    amount: ['', [Validators.required, Validators.min(.01), Validators.pattern(/^(?:0|[1-9]\d{0,12})(?:\.\d{1,2})?$/)]],
    category_id: ['', Validators.required], account_id: [''],
    date: ['', Validators.required],
    description: ['', [Validators.required, Validators.maxLength(100), Validators.pattern(/\S/)]],
    recurring: [false],
  });

  constructor() {
    effect(() => {
      const month = this.month(), currency = this.currency(); this.refreshVersion();
      untracked(() => {
        if (this.scope !== month + currency) {
          this.scope = month + currency;
          this.page.set(1); this.notice.set(''); this.formError.set('');
          this.editing.set(null); this.open.set(false); this.deleteConfirm.set(false);
          const today = new Date().toISOString().slice(0, 10);
          this.form.controls.date.setValue(today.startsWith(month) ? today : month + '-01');
          this.form.controls.account_id.setValue('');
        }
        this.load();
      });
    });
  }

  load(): void {
    this.request?.unsubscribe();
    this.loading.set(true); this.error.set(''); this.data.set(null);
    const [year, month] = this.month().split('-');
    this.request = this.http.get<ExpenseList>('/api/expenses', { params: { year, month, currency: this.currency(), page: this.page() } }).pipe(
      timeout(15000), takeUntilDestroyed(this.destroyRef), finalize(() => this.loading.set(false)),
    ).subscribe({ next: data => this.data.set(data), error: error => this.failed(error, this.error) });
  }

  lastDate(): string {
    const [year, month] = this.month().split('-').map(Number);
    return this.month() + '-' + new Date(Date.UTC(year, month, 0)).getUTCDate();
  }
  money(amount: string): string { return new Intl.NumberFormat('uk-UA', { style: 'currency', currency: this.currency() }).format(Number(amount)); }
  dateLabel(date: string): string { return new Intl.DateTimeFormat('uk-UA', { day: 'numeric', month: 'long', timeZone: 'UTC' }).format(new Date(date + 'T12:00:00Z')); }
  turnPage(offset: number): void { if (this.loading()) return; this.page.update(page => page + offset); this.load(); }

  add(): void {
    if (this.saving() || this.loading() || this.deleteConfirm()) return;
    this.form.controls.description.setValue(this.form.controls.description.value.trim());
    this.form.controls.amount.setValue(this.form.controls.amount.value.trim().replace(',', '.'));
    if (this.form.invalid) { this.form.markAllAsTouched(); return; }
    const values = this.form.getRawValue();
    const editing = this.editing();
    if (!editing && values.date.slice(0, 7) !== this.month()) { this.formError.set('Оберіть дату у вибраному місяці.'); return; }
    if (editing && !values.account_id) { this.formError.set('Оберіть рахунок витрати.'); return; }
    this.saving.set(true); this.busy.emit(true); this.formError.set(''); this.notice.set('');
    const payload = { amount: values.amount, category_id: Number(values.category_id), account_id: values.account_id ? Number(values.account_id) : null, date: values.date, description: values.description };
    const request = editing ? this.http.patch(`/api/expenses/${editing.id}`, payload) : this.http.post('/api/expenses', { ...payload, currency: this.currency(), recurring: values.recurring });
    request.pipe(
      timeout(15000), takeUntilDestroyed(this.destroyRef), finalize(() => { this.saving.set(false); this.busy.emit(false); }),
    ).subscribe({
      next: () => {
        this.form.patchValue({ amount: '', description: '', recurring: false }); this.form.markAsUntouched();
        this.open.set(false); this.editing.set(null); this.notice.set(editing ? 'Витрату оновлено. Баланс і аналітику перераховано. Якщо дату змінено на інший місяць, операція відображатиметься в ньому.' : values.recurring ? 'Щомісячну витрату додано. Операції створюються в день оплати.' : 'Витрату додано. Аналітику оновлено.');
        this.page.set(1); this.load(); this.saved.emit();
      }, error: error => this.failed(error, this.formError),
    });
  }
  toggleForm(): void {
    if (this.saving()) return;
    this.deleteConfirm.set(false);
    if (this.open()) { this.open.set(false); this.editing.set(null); return; }
    this.editing.set(null); this.formError.set('');
    const today = new Date().toISOString().slice(0, 10);
    this.form.reset({ amount: '', description: '', category_id: '', account_id: '', date: today.startsWith(this.month()) ? today : this.month() + '-01', recurring: false });
    this.open.set(true); this.focusForm();
  }
  edit(expense: Expense): void {
    if (this.saving() || this.loading()) return;
    this.deleteConfirm.set(false);
    this.editing.set(expense); this.formError.set(''); this.notice.set('');
    this.form.reset({ amount: expense.amount, description: expense.description, date: expense.date,
      account_id: String(expense.account_id ?? this.data()?.accounts.find(item => item.name === expense.account)?.id ?? ''),
      category_id: String(expense.category_id ?? this.data()?.categories.find(item => item.name === expense.category)?.id ?? ''), recurring: false });
    this.open.set(true); this.focusForm();
  }
  private focusForm(): void {
    afterNextRender(() => {
      const input = this.element.nativeElement.querySelector<HTMLInputElement>('#expense-form input');
      input?.focus(); input?.scrollIntoView?.({ block: 'nearest' });
    }, { injector: this.injector });
  }
  deleteExpense(): void {
    const expense = this.editing();
    if (!expense || !this.deleteConfirm() || this.saving() || this.loading()) return;
    this.saving.set(true); this.busy.emit(true); this.formError.set(''); this.notice.set('');
    this.http.delete<void>(`/api/expenses/${expense.id}`).pipe(timeout(15000), takeUntilDestroyed(this.destroyRef),
      finalize(() => { this.saving.set(false); this.busy.emit(false); }),
    ).subscribe({
      next: () => {
        this.deleteConfirm.set(false); this.editing.set(null); this.open.set(false);
        this.notice.set('Витрату видалено. Суму повернуто на рахунок, аналітику оновлено.');
        this.page.set(1); this.load(); this.saved.emit();
      }, error: error => this.failed(error, this.formError),
    });
  }
  repeat(expense: Expense): void {
    if (this.saving() || this.loading()) return;
    this.updateRecurring(this.http.post(`/api/expenses/${expense.id}/repeat`, {}), 'Витрата тепер повторюється щомісяця.');
  }
  stop(rule: RecurringExpense): void {
    this.stopRecurring(rule.id);
  }
  stopRecurring(ruleId: number): void {
    if (this.saving() || this.loading()) return;
    this.updateRecurring(this.http.delete(`/api/expenses/recurring/${ruleId}`), 'Повторення зупинено. Попередні витрати збережено.');
  }
  private updateRecurring(request: import('rxjs').Observable<unknown>, message: string): void {
    this.saving.set(true); this.busy.emit(true); this.formError.set('');
    request.pipe(timeout(15000), takeUntilDestroyed(this.destroyRef), finalize(() => { this.saving.set(false); this.busy.emit(false); })).subscribe({
      next: () => { this.notice.set(message); this.load(); this.saved.emit(); },
      error: error => this.failed(error, this.formError),
    });
  }
  private failed(error: unknown, target: { set(value: string): void }): void {
    if (error instanceof HttpErrorResponse && error.status === 401) { void this.router.navigateByUrl('/login'); return; }
    target.set(error instanceof HttpErrorResponse && error.status === 400 ? 'Перевірте суму, дату, категорію та рахунок.' : 'Не вдалося виконати запит. Спробуйте ще раз.');
  }
}
