import { Component, inject } from '@angular/core';
import { RouterLink } from '@angular/router';
import { CookieNoticeService } from '../cookie-notice.service';
import { Icon } from '../icon';

@Component({
  selector: 'app-cookies',
  imports: [RouterLink, Icon],
  template: `
    <article class="container policy">
      <a class="back" routerLink="/"><app-icon name="arrow" [size]="16" /> На головну</a>
      <p class="eyebrow">ПРОЗОРО ПРО ВАШІ ДАНІ</p>
      <h1>Про cookies</h1>
      <p class="intro">Невеликий файл, який допомагає сайту запам’ятати ваш вибір.</p>
      <section>
        <h2>Що ми зберігаємо зараз</h2>
        <p>
          Коли ви натискаєте «Зрозуміло», FinSight зберігає факт прочитання повідомлення. Так ми не
          показуємо його знову під час кожного відвідування.
        </p>
        <dl>
          <div>
            <dt>Назва</dt>
            <dd><code>finsight_cookie_notice</code></dd>
          </div>
          <div>
            <dt>Значення</dt>
            <dd><code>v3</code> — версія повідомлення</dd>
          </div>
          <div>
            <dt>Строк</dt>
            <dd>180 днів</dd>
          </div>
          <div>
            <dt>Призначення</dt>
            <dd>Запам’ятати прочитання повідомлення</dd>
          </div>
        </dl>
        <p>
          Ця cookie не містить пароля, email, токена входу або фінансових даних. На цих сторінках
          немає сторонніх рекламних чи аналітичних трекерів.
        </p>
      </section>
      <section>
        <h2>Cookies для входу</h2>
        <p>
          Після входу ми зберігаємо авторизацію на 7 днів. Вона потрібна, щоб упізнати ваш акаунт
          після перезавантаження сторінки або повторного відкриття браузера.
        </p>
        <dl>
          <div>
            <dt>Авторизація</dt>
            <dd>
              <code>access_token_cookie</code> — токен входу, 7 днів, шлях <code>/api/</code>.
              Захищений атрибутом HttpOnly: JavaScript сторінки не може його прочитати.
            </dd>
          </div>
          <div>
            <dt>Захист запитів</dt>
            <dd>
              <code>csrf_access_token</code> — допоміжний код перевірки запитів, 7 днів, шлях
              <code>/</code>. Доступний застосунку для захисту дій з акаунтом.
            </dd>
          </div>
          <div>
            <dt>Передавання</dt>
            <dd>
              SameSite=Lax. За HTTPS cookies позначаються Secure; локальний Docker працює через
              HTTP.
            </dd>
          </div>
        </dl>
        <p>
          Кнопка «Вийти» видаляє обидві cookies входу з цього браузера. Повідомлення «Зрозуміло»
          лише запам’ятовує прочитання пояснення й не керує авторизацією. Пароль не зберігається в
          cookies.
        </p>
      </section>
      <section>
        <h2>Як керувати cookie</h2>
        <p>Короткочасна HttpOnly cookie <code>finsight_verification</code> зберігає запит перевірки до 10 хвилин. Після правильного поштового коду її видаляємо.</p>
        <p>Якщо ви обираєте «Довіряти цьому браузеру», HttpOnly cookie <code>finsight_trusted_device</code> дозволяє пропускати поштовий код під час входу з правильним паролем протягом 90 днів. «Вийти» скасовує довіру та видаляє cookie. Обидві cookies мають шлях /api/auth/ та SameSite=Lax.</p>
        <p>
          Ви можете видалити або заблокувати cookies в налаштуваннях браузера. Головна сторінка
          залишиться доступною, але повідомлення може з’явитися знову після перезавантаження. Якщо
          призначення cookie зміниться, ми оновимо пояснення.
        </p>
        <button class="button button-secondary" type="button" (click)="reopen()">
          Показати повідомлення ще раз <app-icon name="cookie" [size]="18" />
        </button>
      </section>
    </article>
  `,
  styles: `
    .policy {
      max-width: 850px;
      padding-block: 46px 80px;
    }
    .back {
      display: inline-flex;
      gap: 9px;
      align-items: center;
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 50px;
    }
    .back app-icon {
      transform: rotate(180deg);
    }
    h1 {
      margin-top: 17px;
      font-size: 48px;
      letter-spacing: -1.6px;
      font-weight: 600;
    }
    .intro {
      color: var(--muted);
      font-size: 17px;
      margin-top: 15px;
      line-height: 1.7;
    }
    section {
      margin-top: 42px;
    }
    h2 {
      font-size: 22px;
      font-weight: 550;
      margin-bottom: 15px;
    }
    section p {
      font-size: 14px;
      line-height: 1.9;
      color: #aebbd0;
    }
    dl {
      margin-block: 25px;
      border: 1px solid #ffffff14;
      border-radius: 12px;
      overflow: hidden;
    }
    dl > div {
      display: grid;
      grid-template-columns: 130px 1fr;
      gap: 20px;
      padding: 16px 22px;
      font-size: 13px;
      background: #121a2b;
    }
    dl > div + div {
      border-top: 1px solid #ffffff0a;
    }
    dt {
      color: var(--muted);
    }
    dd {
      margin: 0;
      overflow-wrap: anywhere;
    }
    code {
      color: var(--mint);
      font-size: 12px;
    }
    .button {
      margin-top: 23px;
      font-size: 12px;
    }
    @media (max-width: 600px) {
      h1 {
        font-size: 38px;
      }
      .intro {
        font-size: 15px;
      }
      .policy {
        padding-top: 30px;
      }
      dl > div {
        grid-template-columns: 1fr;
        gap: 9px;
        padding: 16px;
      }
      .back {
        margin-bottom: 35px;
      }
    }
  `,
})
export class Cookies {
  private readonly notice = inject(CookieNoticeService);
  reopen(): void {
    this.notice.reopen();
    setTimeout(() => document.querySelector<HTMLElement>('.notice button')?.focus());
  }
}
