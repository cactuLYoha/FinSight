import { HttpErrorResponse } from '@angular/common/http';
import { afterNextRender, Component, computed, DestroyRef, ElementRef, inject, Injector, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { finalize, Observable, Subscription, timeout } from 'rxjs';
import { Account, AccountsService, Income, IncomeList } from './accounts.service';
import { StatementUpload } from './statement-upload';

@Component({ selector: 'app-accounts-page', imports: [RouterLink, ReactiveFormsModule, StatementUpload], templateUrl: './accounts-page.html', styleUrl: './accounts-page.scss' })
export class AccountsPage {
  private readonly api = inject(AccountsService);
  private readonly fb = inject(FormBuilder);
  private readonly destroyRef = inject(DestroyRef);
  private readonly router = inject(Router);
  private readonly element = inject<ElementRef<HTMLElement>>(ElementRef);
  private readonly injector = inject(Injector);
  private listRequest?: Subscription;
  private historyRequest?: Subscription;
  readonly accounts = signal<Account[]>([]);
  readonly selected = signal<Account | null>(null);
  readonly loading = signal(false);
  readonly saving = signal(false);
  readonly statementBusy = signal(false);
  readonly historyLoading = signal(false);
  readonly history = signal<IncomeList | null>(null);
  readonly page = signal(1);
  readonly error = signal('');
  readonly formError = signal('');
  readonly historyError = signal('');
  readonly notice = signal('');
  readonly editor = signal<'create' | 'edit' | 'income' | null>(null);
  readonly types: Record<string, string> = { bank: 'Банківський рахунок', card: 'Картка', cash: 'Готівка', savings: 'Ощадний рахунок' };
  readonly totals = computed(() => {
    const sums = new Map<string, number>();
    for (const account of this.accounts()) sums.set(account.currency, (sums.get(account.currency) ?? 0) + Math.round(Number(account.balance) * 100));
    return Array.from(sums, ([currency, cents]) => ({ currency, amount: cents / 100 }));
  });
  readonly accountForm = this.fb.nonNullable.group({ name: ['', [Validators.required, Validators.maxLength(120), Validators.pattern(/\S/)]], account_type: ['bank', Validators.required], currency: ['UAH', Validators.required] });
  readonly incomeForm = this.fb.nonNullable.group({ amount: ['', [Validators.required, Validators.min(.01), Validators.pattern(/^(?:0|[1-9]\d{0,12})(?:\.\d{1,2})?$/)]], date: [this.today(), Validators.required], description: ['', [Validators.required, Validators.maxLength(100), Validators.pattern(/\S/)]], recurring: [false] });
  constructor() { this.load(); }
  load(): void {
    if (this.saving()) return;
    this.listRequest?.unsubscribe(); this.loading.set(true); this.error.set('');
    this.listRequest = this.api.list().pipe(timeout(15000), takeUntilDestroyed(this.destroyRef), finalize(() => this.loading.set(false))).subscribe({
      next: ({ accounts }) => {
        this.accounts.set(accounts);
        if (this.selected()) {
          const account = accounts.find(item => item.id === this.selected()?.id);
          if (account) { this.selected.set(account); this.loadHistory(); }
          else { this.selected.set(null); this.editor.set(null); this.history.set(null); }
        }
      }, error: error => this.failed(error, this.error),
    });
  }
  select(account: Account): void {
    if (this.saving() || this.loading() || this.statementBusy()) return;
    this.selected.set(account); this.page.set(1); this.editor.set(null); this.formError.set(''); this.loadHistory();
  }
  loadHistory(): void {
    const account = this.selected(); if (!account) return;
    this.historyRequest?.unsubscribe(); this.historyLoading.set(true); this.historyError.set(''); this.history.set(null);
    this.historyRequest = this.api.incomes(account.id, this.page()).pipe(timeout(15000), takeUntilDestroyed(this.destroyRef), finalize(() => this.historyLoading.set(false))).subscribe({ next: result => this.history.set(result), error: error => this.failed(error, this.historyError) });
  }
  turnPage(offset: number): void { if (this.historyLoading() || this.saving()) return; this.page.update(page => page + offset); this.loadHistory(); }
  open(mode: 'create' | 'edit' | 'income'): void {
    if (this.saving() || this.loading()) return;
    const account = this.selected(); if (mode !== 'create' && !account) return;
    this.editor.set(mode); this.formError.set(''); this.notice.set('');
    if (mode === 'income') this.incomeForm.reset({ amount: '', date: this.today(), description: '', recurring: false });
    else this.accountForm.reset({ name: mode === 'edit' ? account!.name : '', account_type: mode === 'edit' ? account!.account_type : 'bank', currency: mode === 'edit' ? account!.currency : 'UAH' });
    afterNextRender(() => { const input = this.element.nativeElement.querySelector<HTMLInputElement>('.editor input'); input?.focus(); input?.scrollIntoView?.({ block: 'nearest' }); }, { injector: this.injector });
  }
  saveAccount(): void {
    const mode = this.editor(); if (mode !== 'create' && mode !== 'edit') return;
    this.accountForm.controls.name.setValue(this.accountForm.controls.name.value.trim());
    if (this.accountForm.invalid) { this.accountForm.markAllAsTouched(); this.formError.set('Вкажіть назву до 120 символів, тип і валюту рахунку.'); return; }
    const values = this.accountForm.getRawValue(), account = this.selected();
    if (mode === 'edit' && !account) return;
    this.mutate(mode === 'create' ? this.api.create(values) : this.api.update(account!.id, { name: values.name, account_type: values.account_type }), 'Рахунок збережено.');
  }
  saveIncome(): void {
    const account = this.selected(); if (!account || this.editor() !== 'income') return;
    this.incomeForm.controls.amount.setValue(this.incomeForm.controls.amount.value.trim().replace(',', '.'));
    this.incomeForm.controls.description.setValue(this.incomeForm.controls.description.value.trim());
    const values = this.incomeForm.getRawValue(), parsed = new Date(values.date + 'T00:00:00Z');
    if (this.incomeForm.invalid || !/^\d{4}-\d{2}-\d{2}$/.test(values.date) || values.date < '0001-01-01' || (!values.recurring && values.date > this.today()) || isNaN(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== values.date) {
      this.incomeForm.markAllAsTouched(); this.formError.set('Вкажіть додатну суму до двох десяткових знаків, дату не пізніше сьогодні й опис до 100 символів.'); return;
    }
    this.mutate(this.api.addIncome(account.id, values), values.recurring ? 'Щомісячне надходження заплановано. Кошти додаються в день надходження.' : 'Дохід додано. Баланс і фінансову аналітику оновлено.');
  }
  repeatIncome(income: Income): void {
    const account = this.selected(); if (!account) return;
    this.mutate(this.api.repeatIncome(account.id, income.id), 'Дохід повторюватиметься з наступного місяця.');
  }
  stopIncome(ruleId: number): void {
    const account = this.selected(); if (!account || this.saving() || this.loading()) return;
    this.saving.set(true); this.formError.set('');
    this.api.stopIncome(account.id, ruleId).pipe(timeout(15000), takeUntilDestroyed(this.destroyRef), finalize(() => this.saving.set(false))).subscribe({
      next: () => { this.notice.set('Повторення надходження зупинено. Попередні доходи збережено.'); this.loadHistory(); },
      error: error => this.failed(error, this.historyError),
    });
  }
  private mutate(request: Observable<{ account: Account }>, message: string): void {
    if (this.saving() || this.loading()) return;
    this.saving.set(true); this.formError.set('');
    request.pipe(timeout(15000), takeUntilDestroyed(this.destroyRef), finalize(() => this.saving.set(false))).subscribe({ next: ({ account }) => {
      this.accounts.update(accounts => accounts.some(item => item.id === account.id) ? accounts.map(item => item.id === account.id ? account : item) : [...accounts, account]);
      this.selected.set(account); this.editor.set(null); this.notice.set(message); this.page.set(1); this.loadHistory();
    }, error: error => this.failed(error, this.formError) });
  }
  today(): string { return new Date().toISOString().slice(0, 10); }
  money(value: string | number, currency: string): string { return new Intl.NumberFormat('uk-UA', { style: 'currency', currency }).format(Number(value)); }
  dateLabel(value: string): string { return new Intl.DateTimeFormat('uk-UA', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' }).format(new Date(value + 'T00:00:00Z')); }
  private failed(error: unknown, target: { set(value: string): void }): void {
    if (error instanceof HttpErrorResponse && error.status === 401) { void this.router.navigateByUrl('/login'); return; }
    target.set(error instanceof HttpErrorResponse && error.status === 400 ? 'Перевірте введені значення. Сума має бути додатною, дата доходу — не пізніше сьогодні.' : 'Не вдалося виконати запит. Оновіть дані перед повторним збереженням.');
  }
}
