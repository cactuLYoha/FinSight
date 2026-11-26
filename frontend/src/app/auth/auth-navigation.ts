import { Component, inject, output, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { AuthService } from './auth.service';
import { Icon } from '../icon';

@Component({
  selector: 'app-auth-navigation',
  imports: [RouterLink, Icon],
  template: `
    <div class="controls">
      @if (auth.status() === 'checking') {
        <span class="checking" role="status">Перевіряємо вхід…</span>
      } @else if (auth.user(); as user) {
        <a class="account" routerLink="/account/settings" (click)="navigated.emit()" aria-label="Налаштування акаунту"
          ><span class="account-dot"></span
          ><span class="email" [title]="user.email">{{ user.email }}</span></a
        >
        <a class="cabinet" routerLink="/dashboard" (click)="navigated.emit()">Особистий кабінет</a>
        <button class="logout" type="button" [disabled]="auth.signingOut()" (click)="logout()">
          {{ auth.signingOut() ? 'Виходимо…' : 'Вийти' }}
        </button>
      } @else {
        <a class="login" routerLink="/login" (click)="navigated.emit()">Увійти</a>
        <a class="register" routerLink="/register" (click)="navigated.emit()"
          >Створити акаунт <app-icon name="arrow" [size]="15"
        /></a>
      }
    </div>
    @if (auth.status() === 'error') {
      <p class="connection" role="status">
        Вхід не перевірено. <button type="button" (click)="retry()">Повторити</button>
      </p>
    }
    @if (error()) {
      <p class="error" role="alert">{{ error() }}</p>
    }
  `,
  styles: `
    :host {
      display: block;
      position: relative;
    }
    .controls {
      display: flex;
      align-items: center;
      gap: 18px;
      flex-wrap: wrap;
    }
    .cabinet { color: var(--mint); white-space: nowrap; }
    .cabinet:hover { text-decoration: underline; }
    a,
    button {
      font-size: 12px;
    }
    .login {
      color: #c1ccdd;
    }
    .login:hover {
      color: var(--mint);
    }
    .register,
    .logout {
      display: inline-flex;
      gap: 9px;
      align-items: center;
      padding: 10px 14px;
      border-radius: 8px;
      border: 1px solid #ffffff25;
      background: transparent;
      white-space: nowrap;
    }
    .register:hover,
    .logout:hover {
      border-color: var(--mint);
    }
    .account {
      display: flex;
      align-items: center;
      gap: 8px;
      min-width: 0;
    }
    .email {
      max-width: 190px;
      text-overflow: ellipsis;
      white-space: nowrap;
      overflow: hidden;
      color: #bfcddd;
      font-size: 12px;
    }
    .account:hover .email { color: var(--mint); }
    .account:focus-visible { outline: 2px solid var(--mint); outline-offset: 5px; }
    .account-dot {
      background: var(--mint);
      width: 6px;
      height: 6px;
      border-radius: 50%;
      flex-shrink: 0;
    }
    .checking {
      font-size: 11px;
      color: var(--muted);
    }
    .error,
    .connection {
      position: absolute;
      right: 0;
      top: calc(100% + 12px);
      z-index: 15;
      border: 1px solid #344156;
      background: #172133;
      border-radius: 8px;
      padding: 12px 15px;
      width: 280px;
      max-width: calc(100vw - 40px);
      font-size: 11px;
      line-height: 1.7;
    }
    .error {
      color: #ffb9b9;
    }
    .connection {
      color: var(--muted);
    }
    .connection button {
      color: var(--mint);
      background: none;
      border: 0;
      text-decoration: underline;
      font-size: 11px;
    }
    @media (max-width: 1000px) {
      :host {
        padding-block: 16px 4px;
        border-top: 1px solid #ffffff14;
        margin-top: 10px;
      }
      .email {
        max-width: min(230px, 53vw);
      }
      .error,
      .connection {
        position: static;
        margin-top: 12px;
        width: auto;
      }
    }
  `,
})
export class AuthNavigation {
  protected readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  readonly navigated = output<void>();
  protected readonly error = signal('');

  logout(): void {
    if (this.auth.signingOut()) return;
    this.error.set('');
    this.auth.logout().subscribe({
      next: () => {
        this.navigated.emit();
        void this.router.navigateByUrl('/');
      },
      error: () => this.error.set('Не вдалося вийти. Перевірте з’єднання та спробуйте ще раз.'),
    });
  }

  retry(): void {
    this.auth.restoreSession().subscribe({ error: () => {} });
  }
}
