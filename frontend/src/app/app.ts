import { Component, inject, OnInit, signal } from '@angular/core';
import { RouterLink, RouterOutlet } from '@angular/router';
import { CookieNotice } from './cookie-notice';
import { CookieNoticeService } from './cookie-notice.service';
import { Icon } from './icon';
import { AuthService } from './auth/auth.service';
import { AuthNavigation } from './auth/auth-navigation';

@Component({
  selector: 'app-root',
  imports: [RouterLink, RouterOutlet, CookieNotice, Icon, AuthNavigation],
  styleUrl: './app.scss',
  templateUrl: './app.html',
})
export class App implements OnInit {
  private readonly auth = inject(AuthService);
  protected readonly notice = inject(CookieNoticeService);
  protected readonly menuOpen = signal(false);

  ngOnInit(): void {
    this.auth.restoreSession().subscribe({ error: () => {} });
  }

  closeMenu(): void {
    this.menuOpen.set(false);
  }

  reopenNotice(): void {
    this.notice.reopen();
    // Let the conditional banner render before moving keyboard focus.
    setTimeout(() => document.querySelector<HTMLElement>('.notice button')?.focus());
  }
}
