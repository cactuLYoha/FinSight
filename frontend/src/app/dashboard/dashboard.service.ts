import { HttpClient } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';

export interface CategoryExpense { category_id: number; name: string; expense_total: string; }
export interface MonthlyAnalytics {
  income_total: string; expense_total: string; net_total: string; categories: CategoryExpense[];
}
export interface ForecastPoint { month: string; projected_savings: string; }
export interface ForecastScenario { name: string; monthly_net: string; points: ForecastPoint[]; }
export interface Forecast {
  status: string; sample_size: number; minimum_history_months: number;
  starting_savings: string; starting_savings_basis: string; scenarios: ForecastScenario[];
}
export interface SubscriptionPlan { id: number; name: string; amount: string; currency: string; billing_day: number; }
export type NewSubscription = Omit<SubscriptionPlan, 'id'>;

@Injectable({ providedIn: 'root' })
export class DashboardService {
  private readonly http = inject(HttpClient);
  monthly(month: string, currency: string) {
    const [year, number] = month.split('-');
    return this.http.get<{ analytics: MonthlyAnalytics }>('/api/analytics/monthly', { params: { year, month: number, currency } });
  }
  forecast(currency: string, horizon: number) {
    return this.http.get<{ forecast: Forecast }>('/api/analytics/forecast', { params: { currency, horizon_months: horizon } });
  }
  subscriptions(currency: string) {
    return this.http.get<{ subscriptions: SubscriptionPlan[] }>('/api/subscriptions', { params: { currency } });
  }
  add(plan: NewSubscription) { return this.http.post<{ subscription: SubscriptionPlan }>('/api/subscriptions', plan); }
  remove(id: number) { return this.http.delete<void>(`/api/subscriptions/${id}`); }
}
