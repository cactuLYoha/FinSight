import { DOCUMENT } from '@angular/common';
import { inject, Injectable, signal } from '@angular/core';

export const NOTICE_COOKIE = 'finsight_cookie_notice';
export const NOTICE_VERSION = 'v3';
const MAX_AGE = 180 * 24 * 60 * 60;

@Injectable({ providedIn: 'root' })
export class CookieNoticeService {
  private readonly document = inject(DOCUMENT);
  readonly visible = signal(!this.hasAcknowledgement());

  acknowledge(): void {
    try {
      const secure = this.document.location?.protocol === 'https:' ? '; Secure' : '';
      this.document.cookie = `${NOTICE_COOKIE}=${NOTICE_VERSION}; Max-Age=${MAX_AGE}; Path=/; SameSite=Lax${secure}`;
    } catch {
      // A blocked cookie must not prevent dismissal during this visit.
    }
    this.visible.set(false);
  }

  reopen(): void {
    this.visible.set(true);
  }

  private hasAcknowledgement(): boolean {
    try {
      return this.document.cookie
        .split(';')
        .some((part) => part.trim() === `${NOTICE_COOKIE}=${NOTICE_VERSION}`);
    } catch {
      return false;
    }
  }
}
