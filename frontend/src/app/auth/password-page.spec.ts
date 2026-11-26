import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, provideRouter, Router } from '@angular/router';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { PasswordPage } from './password-page';
import { AuthService } from './auth.service';

describe('PasswordPage', () => {
  afterEach(() => TestBed.resetTestingModule());

  function setup(account = false) {
    TestBed.configureTestingModule({ imports: [PasswordPage], providers: [
      provideHttpClient(), provideHttpClientTesting(), provideRouter([]),
      { provide: ActivatedRoute, useValue: { snapshot: { data: { account } } } },
    ] });
    const fixture = TestBed.createComponent(PasswordPage);
    fixture.detectChanges();
    const http = TestBed.inject(HttpTestingController);
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);
    return { fixture, page: fixture.componentInstance, http, navigate };
  }

  it('requests recovery and observes resend cooldown', () => {
    const { page, http, fixture } = setup();
    page.emailForm.setValue({ email: 'person@example.com' });
    page.send();
    http.expectOne('/api/auth/password/reset/request').flush({ message: 'Лист надіслано', retry_after: 60 });
    expect(page.sent()).toBe(true);
    page.send(true);
    http.expectNone('/api/auth/password/reset/resend');
    expect(page.seconds()).toBe(60);
    http.verify(); fixture.destroy();
  });

  it('validates confirmation before changing the password and signs out on success', () => {
    const { page, http, fixture, navigate } = setup(true);
    page.form.setValue({ current_password: 'old-password', new_password: 'new-password', confirmation: 'different', code: '' });
    page.submit(); http.expectNone('/api/auth/password/change');
    page.form.controls.confirmation.setValue('new-password');
    page.submit();
    const request = http.expectOne('/api/auth/password/change');
    expect(request.request.body).toEqual({ current_password: 'old-password', new_password: 'new-password' });
    request.flush(null, { status: 204, statusText: 'No Content' });
    expect(TestBed.inject(AuthService).status()).toBe('anonymous');
    expect(navigate).toHaveBeenCalledWith('/login');
    http.verify(); fixture.destroy();
  });

  it('submits reset code and password without requesting login', () => {
    const { page, http, fixture } = setup();
    page.form.setValue({ current_password: '', code: '012345', new_password: 'new-password', confirmation: 'new-password' });
    page.submit();
    const request = http.expectOne('/api/auth/password/reset/confirm');
    expect(request.request.body).toEqual({ code: '012345', new_password: 'new-password' });
    request.flush(null, { status: 204, statusText: 'No Content' });
    http.expectNone('/api/auth/session'); http.verify(); fixture.destroy();
  });
});
