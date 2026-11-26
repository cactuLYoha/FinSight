import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, provideRouter, Router } from '@angular/router';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AuthPage } from './auth-page';
import { AuthService, AuthStatus } from './auth.service';

const user = { id: 5, email: 'person@example.com', created_at: '2026-11-18T12:00:00' };

async function setup(
  mode: 'login' | 'register' = 'login',
  initialStatus: AuthStatus = 'anonymous',
) {
  await TestBed.configureTestingModule({
    imports: [AuthPage],
    providers: [
      provideHttpClient(),
      provideHttpClientTesting(),
      provideRouter([]),
      { provide: ActivatedRoute, useValue: { snapshot: { data: { mode } } } },
    ],
  }).compileComponents();
  const auth = TestBed.inject(AuthService);
  auth.status.set(initialStatus);
  const router = TestBed.inject(Router);
  const navigate = vi.spyOn(router, 'navigateByUrl').mockResolvedValue(true);
  const fixture = TestBed.createComponent(AuthPage);
  fixture.detectChanges();
  return {
    fixture,
    host: fixture.nativeElement as HTMLElement,
    http: TestBed.inject(HttpTestingController),
    auth,
    navigate,
  };
}
function fill(fixture: ComponentFixture<AuthPage>, id: string, value: string): void {
  const input = fixture.nativeElement.querySelector('#' + id) as HTMLInputElement;
  input.value = value;
  input.dispatchEvent(new Event('input', { bubbles: true }));
  fixture.detectChanges();
}
function submit(fixture: ComponentFixture<AuthPage>): void {
  fixture.nativeElement
    .querySelector('form')
    .dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
  fixture.detectChanges();
}

describe('Authentication forms', () => {
  it('does not redirect from a form that was left while startup verification was pending', async () => {
    const { fixture, http, navigate } = await setup('login', 'checking');
    const check = http.expectOne('/api/auth/me');
    fixture.destroy();
    check.flush({ user });
    expect(navigate).not.toHaveBeenCalled();
  });
  afterEach(() => {
    TestBed.inject(HttpTestingController).verify();
  });

  it('validates empty credentials and focuses the first invalid input', async () => {
    const { fixture, host, http } = await setup();
    submit(fixture);
    expect(host.querySelector('#email-error')).not.toBeNull();
    expect(host.querySelector('#password-error')).not.toBeNull();
    expect(document.activeElement).toBe(host.querySelector('#email'));
    http.expectNone('/api/auth/session');
  });

  it('requires matching registration passwords', async () => {
    const { fixture, host, http } = await setup('register');
    fill(fixture, 'email', user.email);
    fill(fixture, 'password', 'strong-password');
    fill(fixture, 'confirmation', 'different-password');
    submit(fixture);
    expect(host.querySelector('#confirmation-error')?.textContent).toContain('збігатися');
    http.expectNone('/api/auth/register');
  });

  it('shows a credential error and prevents duplicate in-flight submits', async () => {
    const { fixture, host, http } = await setup();
    fill(fixture, 'email', user.email);
    fill(fixture, 'password', 'wrong-password');
    submit(fixture);
    submit(fixture);
    expect(host.querySelector<HTMLButtonElement>('button[type="submit"]')!.disabled).toBe(true);
    http.expectOne('/api/auth/session').flush({}, { status: 401, statusText: 'Unauthorized' });
    fixture.detectChanges();
    expect(host.querySelector('[role="alert"]')?.textContent).toContain(
      'Неправильний email або пароль',
    );
    expect(host.querySelector<HTMLButtonElement>('button[type="submit"]')!.disabled).toBe(false);
  });

  it('registers normalized email without altering the password or submitting confirmation', async () => {
    const { fixture, http, navigate } = await setup('register');
    fill(fixture, 'email', 'Person@Example.com');
    fill(fixture, 'password', ' strong-password ');
    fill(fixture, 'confirmation', ' strong-password ');
    submit(fixture);
    const registration = http.expectOne('/api/auth/register');
    expect(registration.request.body).toEqual({ email: user.email, password: ' strong-password ' });
    registration.flush({ user, verification_required: true });
    http.expectNone('/api/auth/session');
    expect(navigate).toHaveBeenCalledWith('/verify');
  });

  it('permits retrying delivery for an already-created account', async () => {
    const { fixture, http, navigate, auth } = await setup('register');
    fill(fixture, 'email', user.email);
    fill(fixture, 'password', 'strong-password');
    fill(fixture, 'confirmation', 'strong-password');
    submit(fixture);
    http.expectOne('/api/auth/register').flush({ verification_required: true, delivery_ready: false }, { status: 503, statusText: 'Unavailable' });
    expect(navigate).toHaveBeenCalledWith('/verify');
    expect(auth.verificationNotice()).toContain('Лист');
  });

  it('explains duplicate email without attempting login', async () => {
    const { fixture, host, http } = await setup('register');
    fill(fixture, 'email', user.email);
    fill(fixture, 'password', 'strong-password');
    fill(fixture, 'confirmation', 'strong-password');
    submit(fixture);
    http.expectOne('/api/auth/register').flush({}, { status: 409, statusText: 'Conflict' });
    fixture.detectChanges();
    expect(host.querySelector('[role="alert"]')?.textContent).toContain('уже зареєстрований');
  });

  it('changes password visibility without submitting credentials', async () => {
    const { fixture, host, http } = await setup();
    host.querySelector<HTMLButtonElement>('.password-toggle')!.click();
    fixture.detectChanges();
    expect(host.querySelector<HTMLInputElement>('#password')!.type).toBe('text');
    expect(host.querySelector('.password-toggle')?.getAttribute('aria-pressed')).toBe('true');
    http.expectNone('/api/auth/session');
  });

  it('explains that cookies must be allowed when verification fails', async () => {
    const { fixture, host, http } = await setup();
    fill(fixture, 'email', user.email);
    fill(fixture, 'password', 'strong-password');
    submit(fixture);
    http.expectOne('/api/auth/session').flush({ user });
    http.expectOne('/api/auth/me').flush({}, { status: 401, statusText: 'Unauthorized' });
    fixture.detectChanges();
    expect(host.querySelector('[role="alert"]')?.textContent).toContain('Дозвольте cookies');
  });
});
