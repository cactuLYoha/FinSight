import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { Dashboard } from './dashboard';

describe('Dashboard', () => {
  let http: HttpTestingController;
  beforeEach(() => {
    TestBed.configureTestingModule({ imports: [Dashboard], providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])] });
    http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => { http.verify(); TestBed.resetTestingModule(); });

  function load() {
    const fixture = TestBed.createComponent(Dashboard);
    http.expectOne(r => r.url === '/api/analytics/monthly').flush({ analytics: { income_total: '1000', expense_total: '200', net_total: '800', categories: [{ category_id: 1, name: 'Їжа', expense_total: '200' }] } });
    http.expectOne(r => r.url === '/api/analytics/forecast').flush({ forecast: { status: 'insufficient_history', minimum_history_months: 3, sample_size: 1, starting_savings: '0', scenarios: [] } });
    http.expectOne(r => r.url === '/api/subscriptions').flush({ subscriptions: [] });
    fixture.detectChanges();
    return fixture;
  }

  it('shows real totals, categories and insufficient history without fabricated forecasts', () => {
    const fixture = load();
    expect(fixture.nativeElement.textContent).toContain('Їжа');
    expect(fixture.nativeElement.textContent).toContain('Для прогнозу потрібно трохи історії');
    expect(fixture.nativeElement.querySelector('svg')).toBeNull();
    expect(fixture.componentInstance.share('200')).toBe(100);
    expect(fixture.nativeElement.querySelector('.horizon select').value).toBe('12');
    fixture.destroy();
  });

  it('persists subscriptions and removes them through the API', () => {
    const fixture = load(), page = fixture.componentInstance;
    page.form.setValue({ name: 'Music', amount: '199.99', billing_day: 31 });
    page.add();
    const add = http.expectOne('/api/subscriptions');
    expect(add.request.body.currency).toBe('UAH');
    const row = { id: 1, ...add.request.body };
    add.flush({ subscription: row });
    expect(page.subscriptionTotal()).toBe(199.99);
    page.remove(row);
    http.expectOne('/api/subscriptions/1').flush(null, { status: 204, statusText: 'No Content' });
    expect(page.plans()).toEqual([]);
    fixture.destroy();
  });

  it('clips monthly billing to the last day and prevents invalid entries', () => {
    const fixture = load(), page = fixture.componentInstance;
    page.month.set('2028-02');
    expect(page.billingLabel(31)).toContain('29');
    page.form.setValue({ name: 'Music', amount: '1.001', billing_day: 32 });
    page.add(); http.expectNone('/api/subscriptions');
    fixture.destroy();
  });

  it('keeps subscriptions available when analytics fails', () => {
    const fixture = TestBed.createComponent(Dashboard);
    http.expectOne(r => r.url === '/api/analytics/monthly').flush({}, { status: 503, statusText: 'Unavailable' });
    http.expectOne(r => r.url === '/api/analytics/forecast').flush({}, { status: 503, statusText: 'Unavailable' });
    http.expectOne(r => r.url === '/api/subscriptions').flush({ subscriptions: [{ id: 1, name: 'Music', amount: '100', currency: 'UAH', billing_day: 1 }] });
    fixture.detectChanges();
    expect(fixture.componentInstance.plans().length).toBe(1);
    expect(fixture.nativeElement.querySelector('[role=alert]')).toBeTruthy();
    fixture.destroy();
  });
});
