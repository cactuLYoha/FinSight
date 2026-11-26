import { DOCUMENT } from '@angular/common';
import { TestBed } from '@angular/core/testing';
import { describe, beforeEach, expect, it } from 'vitest';
import { CookieNoticeService } from './cookie-notice.service';

class CookieDocument {
  value = '';
  written = '';
  blocked = false;
  location = { protocol: 'http:' };
  get cookie(): string {
    if (this.blocked) throw new Error('Cookies blocked');
    return this.value;
  }
  set cookie(value: string) {
    if (this.blocked) throw new Error('Cookies blocked');
    this.written = value;
    this.value = value.split(';')[0];
  }
}

describe('CookieNoticeService', () => {
  let doc: CookieDocument;

  beforeEach(() => {
    doc = new CookieDocument();
    TestBed.configureTestingModule({ providers: [{ provide: DOCUMENT, useValue: doc }] });
  });

  const service = () => TestBed.inject(CookieNoticeService);

  it('shows a notice on the first visit', () => {
    expect(service().visible()).toBe(true);
  });

  it('recognizes the exact version alongside other cookies', () => {
    doc.value = 'other=1; finsight_cookie_notice=v3; preference=dark';
    expect(service().visible()).toBe(false);
  });

  it.each(['v0', 'v1', '', '%invalid', 'v3extra'])(
    'shows the notice for an unrecognized value: %s',
    (value) => {
      doc.value = 'finsight_cookie_notice=' + value;
      expect(service().visible()).toBe(true);
    },
  );

  it('does not mistake another cookie for acknowledgement', () => {
    doc.value = 'other_finsight_cookie_notice=v3';
    expect(service().visible()).toBe(true);
  });

  it('persists acknowledgement for 180 days and hides the notice', () => {
    service().acknowledge();
    expect(doc.written).toBe('finsight_cookie_notice=v3; Max-Age=15552000; Path=/; SameSite=Lax');
    expect(service().visible()).toBe(false);
  });

  it('restores acknowledgement when the service is recreated', () => {
    service().acknowledge();
    const recreated = TestBed.runInInjectionContext(() => new CookieNoticeService());
    expect(recreated.visible()).toBe(false);
  });

  it('adds Secure when served over HTTPS', () => {
    doc.location.protocol = 'https:';
    service().acknowledge();
    expect(doc.written).toMatch(/; Secure$/);
  });

  it('can reopen without deleting the existing preference', () => {
    service().acknowledge();
    service().reopen();
    expect(service().visible()).toBe(true);
    expect(doc.value).toBe('finsight_cookie_notice=v3');
  });

  it('supports dismissal for this visit when reading and writing cookies are blocked', () => {
    doc.blocked = true;
    expect(service().visible()).toBe(true);
    expect(() => service().acknowledge()).not.toThrow();
    expect(service().visible()).toBe(false);
    const recreated = TestBed.runInInjectionContext(() => new CookieNoticeService());
    expect(recreated.visible()).toBe(true);
  });
});
