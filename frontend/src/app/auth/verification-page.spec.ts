import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { VerificationPage } from './verification-page';

const context = { verification_required: true, masked_email: 'a***@example.com', expires_at: new Date(Date.now() + 600000).toISOString(), resend_available_at: new Date(0).toISOString(), delivery_ready: true };
const user = { id: 1, email: 'a@example.com', created_at: '2026-11-19', is_email_verified: true, email_verified_at: '2026-11-19' };

async function setup() {
  await TestBed.configureTestingModule({
    imports: [VerificationPage], providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
  }).compileComponents();
  const navigate = vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);
  const fixture = TestBed.createComponent(VerificationPage);
  fixture.detectChanges();
  const http = TestBed.inject(HttpTestingController);
  http.expectOne('/api/auth/verification').flush(context);
  fixture.detectChanges();
  const host = fixture.nativeElement as HTMLElement;
  const fill = (value: string) => {
    const input = host.querySelector<HTMLInputElement>('#verification-code')!;
    input.value = value; input.dispatchEvent(new Event('input', { bubbles: true })); fixture.detectChanges();
  };
  const submit = () => { host.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })); fixture.detectChanges(); };
  return { fixture, host, http, fill, submit, navigate };
}
describe('Verification page', () => {
  afterEach(() => TestBed.inject(HttpTestingController).verify());
  it('restores pending context after a reload and defaults trust to off', async () => {
    const { host } = await setup();
    expect(host.textContent).toContain('a***@example.com');
    expect(host.querySelector<HTMLInputElement>('[type="checkbox"]')!.checked).toBe(false);
    expect(host.querySelector('input')!.getAttribute('autocomplete')).toBe('one-time-code');
  });
  it('validates six digits without making a request', async () => {
    const { host, fill, submit, http } = await setup();
    fill('12'); submit();
    expect(host.querySelector('[role="alert"]')?.textContent).toContain('6 цифр');
    http.expectNone('/api/auth/verification/confirm');
  });
  it('preserves leading zeros, submits trust choice, and verifies the final cookie', async () => {
    const { host, fill, submit, http, navigate } = await setup();
    fill('012345');
    host.querySelector<HTMLInputElement>('[type="checkbox"]')!.click();
    submit();
    const request = http.expectOne('/api/auth/verification/confirm');
    expect(request.request.body).toEqual({ code: '012345', trust_device: true });
    request.flush({ user });
    http.expectOne('/api/auth/me').flush({ user });
    expect(navigate).toHaveBeenCalledWith('/');
  });
  it('shows a wrong-code error and allows another try', async () => {
    const { fixture, host, fill, submit, http } = await setup();
    fill('123456'); submit();
    http.expectOne('/api/auth/verification/confirm').flush({ code: 'invalid_code' }, { status: 400, statusText: 'Bad Request' });
    fixture.detectChanges();
    expect(host.querySelector('[role="alert"]')?.textContent).toContain('Неправильний код');
    expect(host.querySelector<HTMLButtonElement>('[type="submit"]')!.disabled).toBe(false);
  });
  it('closes a consumed challenge rather than retrying it', async () => {
    const { fixture, host, fill, submit, http } = await setup();
    fill('123456'); submit();
    http.expectOne('/api/auth/verification/confirm').flush({ code: 'verification_closed' }, { status: 410, statusText: 'Gone' });
    fixture.detectChanges();
    expect(host.querySelector('form')).toBeNull();
    expect(host.textContent).toContain('Почніть вхід заново');
  });
  it('resends and refreshes the countdown from server timestamps', async () => {
    const { fixture, host, http } = await setup();
    host.querySelector<HTMLButtonElement>('.resend')!.click();
    http.expectOne('/api/auth/verification/resend').flush({ ...context, resend_available_at: new Date(Date.now() + 60000).toISOString() });
    fixture.detectChanges();
    expect(host.querySelector<HTMLButtonElement>('.resend')!.disabled).toBe(true);
    expect(host.textContent).toContain('Новий код надіслано');
  });
});
