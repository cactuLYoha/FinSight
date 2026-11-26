import { HttpClient } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';

export interface Account { id: number; name: string; account_type: string; currency: string; balance: string; income_total?: string; expense_total?: string; savings_total?: string; }
export interface Income { id: number; account_id: number; amount: string; date: string; description: string; recurring_id?: number | null; recurring_active?: boolean; }
export interface RecurringIncome { id: number; amount: string; description: string; billing_day: number; next_due_on: string; }
export interface IncomeList { incomes: Income[]; total: number; page: number; recurring_incomes?: RecurringIncome[]; }
export interface AccountInput { name: string; account_type: string; currency: string; }
@Injectable({ providedIn: 'root' })
export class AccountsService {
  private readonly http = inject(HttpClient);
  list() { return this.http.get<{ accounts: Account[] }>('/api/accounts'); }
  create(data: AccountInput) { return this.http.post<{ account: Account }>('/api/accounts', data); }
  update(id: number, data: Omit<AccountInput, 'currency'>) { return this.http.patch<{ account: Account }>(`/api/accounts/${id}`, data); }
  incomes(id: number, page: number) { return this.http.get<IncomeList>(`/api/accounts/${id}/incomes`, { params: { page } }); }
  addIncome(id: number, data: { amount: string; date: string; description: string; recurring?: boolean }) { return this.http.post<{ account: Account }>(`/api/accounts/${id}/incomes`, data); }
  repeatIncome(id: number, incomeId: number) { return this.http.post<{ account: Account }>(`/api/accounts/${id}/incomes/${incomeId}/repeat`, {}); }
  stopIncome(id: number, ruleId: number) { return this.http.delete<void>(`/api/accounts/${id}/recurring-incomes/${ruleId}`); }
}
