import { provideHttpClient, withXsrfConfiguration, HttpErrorResponse } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { AuthService, CookieStorageError, User, VerificationContext } from './auth.service';

const user: User = { id: 7, email: 'person@example.com', created_at: '2026-11-18T12:00:00', is_email_verified: true, email_verified_at: '2026-11-19T12:00:00' };
const credentials = { email: user.email, password: 'strong-password' };
const context: VerificationContext = { verification_required: true, masked_email: 'p***@example.com', expires_at: '2027-01-01T12:00:00Z', resend_available_at: '2027-01-01T11:51:00Z', delivery_ready: true };

describe('AuthService', () => {
  let auth: AuthService;
  let http: HttpTestingController;
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [
      provideHttpClient(withXsrfConfiguration({ cookieName: 'csrf_access_token', headerName: 'X-CSRF-TOKEN' })),
      provideHttpClientTesting(),
    ] });
    auth = TestBed.inject(AuthService); http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => { http.verify(); document.cookie = 'csrf_access_token=; Max-Age=0; Path=/'; });

  it('coalesces startup checks and restores verified identity', () => {
    auth.restoreSession().subscribe(); auth.restoreSession().subscribe();
    http.expectOne('/api/auth/me').flush({ user });
    expect(auth.user()).toEqual(user);
  });
  it.each([401, 422, 403])('treats invalid or pre-verification credentials as anonymous (%s)', (status) => {
    auth.restoreSession().subscribe((result) => expect(result).toBeNull());
    http.expectOne('/api/auth/me').flush({ code: 'verification_required' }, { status, statusText: 'Unauthorized' });
    expect(auth.status()).toBe('anonymous');
  });
  it('permits retry after a server outage', () => {
    auth.restoreSession().subscribe({ error: () => {} });
    http.expectOne('/api/auth/me').flush({}, { status: 503, statusText: 'Unavailable' });
    expect(auth.status()).toBe('error');
    auth.restoreSession().subscribe(); http.expectOne('/api/auth/me').flush({ user });
    expect(auth.status()).toBe('authenticated');
  });
  it('keeps login pending instead of calling me before OTP', () => {
    auth.login(credentials).subscribe((result) => expect(result).toBeNull());
    const login = http.expectOne('/api/auth/session');
    expect(login.request.body).toEqual(credentials);
    login.flush(context, { status: 202, statusText: 'Accepted' });
    expect(auth.verification()).toEqual(context); expect(auth.user()).toBeNull();
    http.expectNone('/api/auth/me');
  });
  it('verifies the cookie after a trusted-device shortcut', () => {
    let result: User | null | undefined;
    auth.login(credentials).subscribe((value) => { result = value; });
    http.expectOne('/api/auth/session').flush({ user });
    expect(result).toBeUndefined();
    http.expectOne('/api/auth/me').flush({ user });
    expect(result).toEqual(user);
  });
  it('registers without immediately making another login request', () => {
    auth.register(credentials).subscribe((result) => expect(result).toBeNull());
    http.expectOne('/api/auth/register').flush({ user, ...context });
    expect(auth.verification()).toEqual({ user, ...context });
    http.expectNone('/api/auth/session');
  });
  it('keeps a failed delivery context available for resend', () => {
    auth.register(credentials).subscribe((result) => expect(result).toBeNull());
    http.expectOne('/api/auth/register').flush({ ...context, delivery_ready: false, code: 'email_delivery_failed', account_created: true }, { status: 503, statusText: 'Unavailable' });
    expect(auth.verification()?.delivery_ready).toBe(false);
    expect(auth.verificationNotice()).toContain('Лист');
    expect(auth.user()).toBeNull();
  });
  it('confirms OTP and the trust choice before restoring cookie identity', () => {
    auth.confirmVerification('012345', true).subscribe();
    const request = http.expectOne('/api/auth/verification/confirm');
    expect(request.request.body).toEqual({ code: '012345', trust_device: true });
    request.flush({ user });
    expect(auth.user()).toBeNull();
    http.expectOne('/api/auth/me').flush({ user });
    expect(auth.user()).toEqual(user); expect(auth.verification()).toBeNull();
  });
  it.each([401, 403])('detects a rejected final cookie (%s)', (status) => {
    let result: unknown;
    auth.confirmVerification('012345', false).subscribe({ error: (error) => { result = error; } });
    http.expectOne('/api/auth/verification/confirm').flush({ user });
    http.expectOne('/api/auth/me').flush({ code: 'verification_required' }, { status, statusText: 'Unauthorized' });
    expect(result).toBeInstanceOf(CookieStorageError);
    expect(auth.user()).toBeNull();
  });
  it('rejects a retained cookie for another account', () => {
    let result: unknown;
    auth.login(credentials).subscribe({ error: (error) => { result = error; } });
    http.expectOne('/api/auth/session').flush({ user });
    http.expectOne('/api/auth/me').flush({ user: { ...user, id: 99 } });
    expect(result).toBeInstanceOf(CookieStorageError);
  });
  it('does not mistake an outage for cookie blocking', () => {
    let result: unknown;
    auth.login(credentials).subscribe({ error: (error) => { result = error; } });
    http.expectOne('/api/auth/session').flush({ user });
    http.expectOne('/api/auth/me').flush({}, { status: 503, statusText: 'Unavailable' });
    expect(result).toBeInstanceOf(HttpErrorResponse);
  });
  it('passes duplicate-registration errors through', () => {
    auth.register(credentials).subscribe({ error: (error) => expect(error.status).toBe(409) });
    http.expectOne('/api/auth/register').flush({}, { status: 409, statusText: 'Conflict' });
  });
  it('clears identity only after successful logout', () => {
    auth.user.set(user); auth.status.set('authenticated');
    auth.logout().subscribe();
    expect(auth.user()).toEqual(user); expect(auth.signingOut()).toBe(true);
    http.expectOne('/api/auth/session').flush(null, { status: 204, statusText: 'No Content' });
    expect(auth.user()).toBeNull(); expect(auth.signingOut()).toBe(false);
  });
  it('retains identity after failed logout', () => {
    auth.user.set(user); auth.status.set('authenticated');
    auth.logout().subscribe({ error: () => {} });
    http.expectOne('/api/auth/session').error(new ProgressEvent('error'));
    expect(auth.user()).toEqual(user);
  });
  it('forwards only the readable CSRF nonce', () => {
    document.cookie = 'csrf_access_token=nonce; Path=/';
    auth.logout().subscribe();
    const request = http.expectOne('/api/auth/session');
    expect(request.request.headers.get('X-CSRF-TOKEN')).toBe('nonce');
    expect(request.request.headers.has('Authorization')).toBe(false);
    request.flush(null, { status: 204, statusText: 'No Content' });
  });
});
