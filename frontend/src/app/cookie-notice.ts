import { Component, inject } from '@angular/core';
import { RouterLink } from '@angular/router';
import { CookieNoticeService } from './cookie-notice.service';
import { Icon } from './icon';

@Component({
  selector: 'app-cookie-notice',
  imports: [RouterLink, Icon],
  template: `
    @if (notice.visible()) {
      <aside class="notice" aria-labelledby="cookie-heading">
        <span class="cookie-icon"><app-icon name="cookie" [size]="25" /></span>
        <div class="copy">
          <h2 id="cookie-heading">Трохи cookies для зручності</h2>
          <p>
            Функціональні cookies запам’ятовують вхід і прочитання цього повідомлення.
            Без рекламних трекерів.
          </p>
        </div>
        <div class="actions">
          <a routerLink="/cookies">Докладніше</a>
          <button type="button" class="button button-primary" (click)="notice.acknowledge()">
            Зрозуміло <app-icon name="check" [size]="16" />
          </button>
        </div>
      </aside>
    }
  `,
  styles: `
    .notice {
      position: fixed;
      bottom: 22px;
      left: 24px;
      right: 24px;
      z-index: 20;
      max-width: 1120px;
      margin-inline: auto;
      display: flex;
      align-items: center;
      gap: 20px;
      padding: 22px 26px;
      border: 1px solid #334257;
      border-radius: 16px;
      background: #172133;
      box-shadow: 0 16px 65px #0007;
    }
    .cookie-icon {
      display: flex;
      padding: 12px;
      border-radius: 12px;
      background: #27d5b010;
      color: var(--mint);
    }
    h2 {
      font-size: 15px;
      margin-bottom: 5px;
      font-weight: 600;
    }
    p {
      color: #b4bfd1;
      font-size: 12px;
      line-height: 1.65;
      max-width: 510px;
    }
    .actions {
      margin-left: auto;
      display: flex;
      align-items: center;
      gap: 24px;
      flex-shrink: 0;
    }
    .actions a {
      font-size: 12px;
      color: #c3cddd;
      text-decoration: underline;
      text-underline-offset: 4px;
    }
    .button {
      font-size: 12px;
      padding: 11px 17px;
    }
    @media (max-width: 900px) {
      .cookie-icon {
        display: none;
      }
      .notice {
        gap: 14px;
        padding: 20px;
      }
    }
    @media (max-width: 600px) {
      .notice {
        bottom: 12px;
        left: 12px;
        right: 12px;
        flex-direction: column;
        align-items: stretch;
        gap: 16px;
        padding: 20px;
      }
      .actions {
        margin-left: 0;
        justify-content: space-between;
      }
      h2 {
        font-size: 14px;
      }
    }
  `,
})
export class CookieNotice {
  protected readonly notice = inject(CookieNoticeService);
}
