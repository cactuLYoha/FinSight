import { HttpClient } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';

export interface SavingsGoal {
  id: number; name: string; target_amount: string; currency: string; deadline: string;
  status: 'active' | 'completed' | 'cancelled'; saved_amount: string;
  remaining_amount: string; progress_percent: string; is_achieved: boolean;
}
export interface GoalInput { name: string; target_amount: string; currency: string; deadline: string; }
export interface ContributionInput { amount: string; contributed_on: string; note: string | null; account_id?: number; }
export interface Contribution extends ContributionInput { id: number; goal_id: number; }
export interface SavingsSummary {
  currency: string; income_total: string; expense_total: string; net_savings: string;
  available_to_save: string; savings_rate_percent: string | null;
}
export interface SavingsPlan {
  goal: SavingsGoal; overdue: boolean; required_monthly_amount: string | null;
  is_feasible: boolean | null; monthly_shortfall: string | null;
  history: { status: string; sample_size: number; available_monthly: string | null; };
  installments: { month: string; due_date: string; amount: string; is_affordable: boolean | null; shortfall: string | null; }[];
}

@Injectable({ providedIn: 'root' })
export class SavingsService {
  private readonly http = inject(HttpClient);
  private readonly base = '/api/savings';
  summary(period: string, currency: string) {
    const [year, month] = period.split('-');
    return this.http.get<{ summary: SavingsSummary }>(`${this.base}/summary`, { params: { year, month, currency } });
  }
  goals() { return this.http.get<{ goals: SavingsGoal[] }>(`${this.base}/goals`); }
  goal(id: number) { return this.http.get<{ goal: SavingsGoal }>(`${this.base}/goals/${id}`); }
  createGoal(data: GoalInput) { return this.http.post<{ goal: SavingsGoal }>(`${this.base}/goals`, data); }
  updateGoal(id: number, data: Omit<GoalInput, 'currency'>) { return this.http.patch<{ goal: SavingsGoal }>(`${this.base}/goals/${id}`, data); }
  plan(id: number) { return this.http.get<{ plan: SavingsPlan }>(`${this.base}/goals/${id}/plan`); }
  contributions(id: number) { return this.http.get<{ contributions: Contribution[]; accounts?: { id: number; name: string }[] }>(`${this.base}/goals/${id}/contributions`); }
  addContribution(id: number, data: ContributionInput) { return this.http.post<{ contribution: Contribution }>(`${this.base}/goals/${id}/contributions`, data); }
  updateContribution(id: number, contributionId: number, data: ContributionInput) { return this.http.patch<{ contribution: Contribution }>(`${this.base}/goals/${id}/contributions/${contributionId}`, data); }
  deleteContribution(id: number, contributionId: number) { return this.http.delete<void>(`${this.base}/goals/${id}/contributions/${contributionId}`); }
  complete(id: number) { return this.http.post<{ goal: SavingsGoal }>(`${this.base}/goals/${id}/complete`, {}); }
  cancel(id: number) { return this.http.post<{ goal: SavingsGoal }>(`${this.base}/goals/${id}/cancel`, {}); }
  reactivate(id: number, deadline: string) { return this.http.post<{ goal: SavingsGoal }>(`${this.base}/goals/${id}/reactivate`, { deadline }); }
  deleteGoal(id: number) { return this.http.delete<void>(`${this.base}/goals/${id}`); }
  transfer(id: number, data: { target_goal_id: number } | { new_goal: GoalInput }) {
    return this.http.post<{ source: SavingsGoal; target: SavingsGoal; transferred_amount: string }>(`${this.base}/goals/${id}/transfer`, data);
  }
}
