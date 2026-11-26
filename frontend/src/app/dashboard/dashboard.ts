import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { ExpensesPanel } from './expenses-panel';
import { HttpErrorResponse } from '@angular/common/http';
import { catchError, finalize, forkJoin, of, Subscription, timeout } from 'rxjs';
import { DashboardService, Forecast, ForecastScenario, MonthlyAnalytics, SubscriptionPlan } from './dashboard.service';

@Component({
  selector: 'app-dashboard', imports: [ReactiveFormsModule, RouterLink, ExpensesPanel],
  templateUrl: './dashboard.html', styleUrl: './dashboard.scss',
})
export class Dashboard {
  private readonly api = inject(DashboardService);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);
  private readonly fb = inject(FormBuilder);
  private readonly route = inject(ActivatedRoute);
  readonly expensesTab = signal(false);
  readonly expenseSaving = signal(false);
  readonly refreshVersion = signal(0);
  private request?: Subscription;
  readonly currency = signal('UAH');
  readonly month = signal(new Date().toISOString().slice(0, 7));
  readonly horizon = signal(12);
  readonly selectedScenario = signal('all');
  readonly loading = signal(false);
  readonly monthly = signal<MonthlyAnalytics | null>(null);
  readonly forecast = signal<Forecast | null>(null);
  readonly plans = signal<SubscriptionPlan[]>([]);
  readonly monthlyError = signal('');
  readonly forecastError = signal('');
  readonly plansError = signal('');
  readonly saving = signal(false);
  readonly deleting = signal<number | null>(null);
  readonly formOpen = signal(false);
  readonly formError = signal('');
  readonly notice = signal('');
  readonly form = this.fb.nonNullable.group({
    name: ['', [Validators.required, Validators.maxLength(120), Validators.pattern(/\S/)]],
    amount: ['', [Validators.required, Validators.pattern(/^(?:0|[1-9]\d{0,12})(?:\.\d{1,2})?$/), Validators.min(.01)]],
    billing_day: [1, [Validators.required, Validators.min(1), Validators.max(31), Validators.pattern(/^\d+$/)]],
  });
  readonly scenarioNames: Record<string, string> = { optimistic: 'Оптимістичний', realistic: 'Реалістичний', pessimistic: 'Песимістичний' };
  readonly colors: Record<string, string> = { optimistic: '#27d5b0', realistic: '#82aaff', pessimistic: '#f4b078' };

  constructor() {
    this.route.queryParamMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(params => this.expensesTab.set(params.get('tab') === 'expenses'));
    this.load();
  }

  load(): void {
    this.refreshVersion.update(version => version + 1);
    this.request?.unsubscribe();
    this.loading.set(true);
    this.monthly.set(null); this.forecast.set(null); this.plans.set([]);
    this.monthlyError.set(''); this.forecastError.set(''); this.plansError.set('');
    this.request = forkJoin({
      monthly: this.api.monthly(this.month(), this.currency()).pipe(timeout(15000), catchError(error => { this.failed(error, this.monthlyError); return of(null); })),
      forecast: this.api.forecast(this.currency(), this.horizon()).pipe(timeout(15000), catchError(error => { this.failed(error, this.forecastError); return of(null); })),
      plans: this.api.subscriptions(this.currency()).pipe(timeout(15000), catchError(error => { this.failed(error, this.plansError); return of(null); })),
    }).pipe(takeUntilDestroyed(this.destroyRef), finalize(() => this.loading.set(false))).subscribe(result => {
      this.monthly.set(result.monthly?.analytics ?? null);
      this.forecast.set(result.forecast?.forecast ?? null);
      this.plans.set(result.plans?.subscriptions ?? []);
    });
  }

  changeCurrency(event: Event): void { this.currency.set((event.target as HTMLSelectElement).value); this.notice.set(''); this.load(); }
  changeMonth(event: Event): void {
    const month = (event.target as HTMLInputElement).value;
    if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(month) || month < '0001-01' || month > '9998-12') return;
    this.month.set(month); this.load();
  }
  changeHorizon(event: Event): void { this.horizon.set(Number((event.target as HTMLSelectElement).value)); this.load(); }
  money(value: string | number): string {
    return new Intl.NumberFormat('uk-UA', { style: 'currency', currency: this.currency(), maximumFractionDigits: 2 }).format(Number(value));
  }
  monthLabel(month: string): string {
    return new Intl.DateTimeFormat('uk-UA', { month: 'short', year: '2-digit', timeZone: 'UTC' }).format(new Date(month + '-01T00:00:00Z'));
  }
  subscriptionTotal(): number { return this.plans().reduce((sum, plan) => sum + Number(plan.amount), 0); }
  share(value: string): number {
    const total = Number(this.monthly()?.expense_total ?? 0);
    return total ? Number(value) / total * 100 : 0;
  }
  visibleScenarios(): ForecastScenario[] {
    return (this.forecast()?.scenarios ?? []).filter(scenario => this.selectedScenario() === 'all' || this.selectedScenario() === scenario.name);
  }
  private bounds(): [number, number] {
    const forecast = this.forecast();
    const values = [0, Number(forecast?.starting_savings ?? 0), ...(forecast?.scenarios ?? []).flatMap(s => s.points.map(p => Number(p.projected_savings)))];
    const min = Math.min(...values), max = Math.max(...values);
    const padding = Math.max((max - min) * .12, 1);
    return [min - padding, max + padding];
  }
  y(value: number): number { const [min, max] = this.bounds(); return 265 - (value - min) / (max - min) * 230; }
  x(index: number): number { return 105 + index / this.horizon() * 745; }
  ticks(): number[] { const [min, max] = this.bounds(); return Array.from({ length: 5 }, (_, index) => min + (max - min) * index / 4); }
  path(scenario: ForecastScenario): string {
    return [Number(this.forecast()?.starting_savings ?? 0), ...scenario.points.map(point => Number(point.projected_savings))]
      .map((value, index) => `${index === 0 ? 'M' : 'L'} ${this.x(index)} ${this.y(value)}`).join(' ');
  }
  lastValue(scenario: ForecastScenario): string { return scenario.points.at(-1)?.projected_savings ?? '0'; }
  billingLabel(day: number): string {
    const [year, month] = this.month().split('-').map(Number);
    const lastDay = new Date(Date.UTC(year, month, 0)).getUTCDate();
    const date = new Date(this.month() + '-01T00:00:00Z');
    date.setUTCDate(Math.min(day, lastDay));
    return new Intl.DateTimeFormat('uk-UA', { day: 'numeric', month: 'long', timeZone: 'UTC' }).format(date);
  }
  add(): void {
    if (this.saving() || this.loading()) return;
    this.form.controls.name.setValue(this.form.controls.name.value.trim());
    if (this.form.invalid) { this.form.markAllAsTouched(); return; }
    this.saving.set(true); this.formError.set('');
    this.api.add({ ...this.form.getRawValue(), currency: this.currency() }).pipe(timeout(15000), takeUntilDestroyed(this.destroyRef), finalize(() => this.saving.set(false))).subscribe({
      next: result => {
        if (result.subscription.currency === this.currency()) this.plans.update(plans => [...plans, result.subscription].sort((a, b) => a.billing_day - b.billing_day || a.id - b.id));
        this.form.reset({ name: '', amount: '', billing_day: 1 }); this.formOpen.set(false);
        this.notice.set('Підписку додано.');
      }, error: error => this.failed(error, this.formError),
    });
  }
  remove(plan: SubscriptionPlan): void {
    if (this.deleting() !== null || this.loading()) return;
    this.deleting.set(plan.id); this.formError.set('');
    this.api.remove(plan.id).pipe(timeout(15000), takeUntilDestroyed(this.destroyRef), finalize(() => this.deleting.set(null))).subscribe({
      next: () => { this.plans.update(plans => plans.filter(item => item.id !== plan.id)); this.notice.set('Підписку видалено.'); },
      error: error => this.failed(error, this.formError),
    });
  }
  private failed(error: unknown, target: { set(value: string): void }): void {
    if (error instanceof HttpErrorResponse && error.status === 401) { void this.router.navigateByUrl('/login'); return; }
    target.set(error instanceof HttpErrorResponse && error.status === 400 ? 'Перевірте введені значення.' : 'Не вдалося отримати дані. Спробуйте ще раз.');
  }
}
