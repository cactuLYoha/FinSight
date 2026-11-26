import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter, Router } from '@angular/router';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { App } from './app';
import { routes } from './app.routes';

describe('Public app interactions', () => {
  beforeEach(async () => {
    document.cookie = 'finsight_cookie_notice=; Max-Age=0; Path=/';
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [provideRouter(routes), provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();
  });

  afterEach(() => {
    TestBed.inject(HttpTestingController).verify();
    document.cookie = 'finsight_cookie_notice=; Max-Age=0; Path=/';
  });

  it('dismisses the banner and reopens it from the footer', async () => {
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();
    TestBed.inject(HttpTestingController)
      .expectOne('/api/auth/me')
      .flush({}, { status: 401, statusText: 'Unauthorized' });
    fixture.detectChanges();
    const host = fixture.nativeElement as HTMLElement;
    host.querySelector<HTMLButtonElement>('.notice button')!.click();
    fixture.detectChanges();
    expect(host.querySelector('.notice')).toBeNull();
    expect(document.cookie).toContain('finsight_cookie_notice=v3');
    host.querySelector<HTMLButtonElement>('.footer-links button')!.click();
    fixture.detectChanges();
    expect(host.querySelector('.notice')).not.toBeNull();
    await fixture.whenStable();
  });

  it('opens the cookies page through the public router', async () => {
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();
    TestBed.inject(HttpTestingController)
      .expectOne('/api/auth/me')
      .flush({}, { status: 401, statusText: 'Unauthorized' });
    fixture.detectChanges();
    await TestBed.inject(Router).navigateByUrl('/cookies');
    await fixture.whenStable();
    fixture.detectChanges();
    const host = fixture.nativeElement as HTMLElement;
    expect(host.querySelector('main h1')?.textContent).toBe('Про cookies');
    expect(host.querySelector('main code')?.textContent).toBe('finsight_cookie_notice');
  });
});
