import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, inject, input, output, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { finalize, timeout } from 'rxjs';

@Component({
  selector: 'app-statement-upload',
  template: `
    <section class="statement" aria-labelledby="statement-title" [attr.aria-busy]="pending()">
      <h3 id="statement-title">PDF-виписка для «{{ account().name }}»</h3>
      <p>Завантажте цифрову виписку до 10 МБ та 20 сторінок у {{ account().currency }}. Операції буде збережено до цього рахунку, а баланс оновлено.</p>
      <p>Виписка обробляється локально. Скановані та захищені паролем PDF поки не підтримуються.</p>
      <input #pdfInput hidden type="file" accept=".pdf,application/pdf" [disabled]="pending()" (change)="choose($event)" />
      <button type="button" class="button" [disabled]="pending()" (click)="pdfInput.value = ''; pdfInput.click()">Завантажити PDF-виписку</button>
      @if (file(); as selectedFile) { <p class="filename">Обрано: {{ selectedFile.name }}</p> }
      <button type="button" class="button button-primary" [disabled]="!file() || pending()" (click)="analyze()">
        {{ pending() ? 'Імпортуємо…' : 'Імпортувати PDF' }}
      </button>
      @if (pending()) { <p role="status">Аналіз може тривати кілька хвилин, особливо під час першого запуску.</p> }
      @if (error()) { <p class="error" role="alert">{{ error() }}</p> }
      @if (notice()) { <p role="status">{{ notice() }}</p> }
    </section>
  `,
  styles: `
    .statement { margin-block: 24px; padding: 24px; background: var(--surface); border: 1px solid var(--line); border-radius: 16px; }
    h3 { font-size: 18px; } p { margin-block: 12px; color: var(--muted); line-height: 1.6; }
    label { display: block; margin-bottom: 8px; } input { max-width: 100%; margin: 0 16px 16px 0; }
    .filename { overflow-wrap: anywhere; } button { margin: 8px 12px 8px 0; } .error { color: #ffadb3; }
    @media(max-width: 600px) { .statement { padding: 16px; } }
  `,
})
export class StatementUpload {
  readonly account = input.required<{ id: number; name: string; currency: string }>();
  readonly imported = output<void>();
  readonly busy = output<boolean>();
  readonly notice = signal('');
  private readonly http = inject(HttpClient);
  private readonly destroyRef = inject(DestroyRef);
  readonly file = signal<File | null>(null);
  readonly pending = signal(false);
  readonly error = signal('');

  choose(event: Event): void {
    this.error.set(''); this.notice.set(''); this.file.set(null);
    const file = (event.target as HTMLInputElement).files?.[0];
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.pdf') || !file.size || file.size > 10 * 1024 * 1024) {
      this.error.set('Оберіть непорожній PDF-файл до 10 МБ.'); return;
    }
    this.file.set(file);
  }

  analyze(): void {
    const file = this.file(); if (!file || this.pending()) return;
    this.pending.set(true); this.busy.emit(true); this.error.set(''); this.notice.set('');
    const body = new FormData(); body.append('file', file); body.append('account_id', String(this.account().id));
    this.http.post<{ imported_count: number; duplicate: boolean }>('/api/statements/import', body).pipe(
      timeout(205000), takeUntilDestroyed(this.destroyRef), finalize(() => { this.pending.set(false); this.busy.emit(false); }),
    ).subscribe({
      next: response => {
        this.notice.set(response.duplicate ? 'Цю виписку вже імпортовано до цього рахунку.' : `Збережено операцій: ${response.imported_count}. Баланс оновлено.`);
        this.imported.emit();
      },
      error: (error: unknown) => {
        const status = error instanceof HttpErrorResponse ? error.status : 0;
        this.error.set(status === 401 || status === 403 ? 'Увійдіть до акаунта повторно.' :
          status === 503 ? 'Аналіз недоступний. Перевірте, чи запущено локальний сервіс аналізу.' :
          status === 413 ? 'Файл завеликий. Максимальний розмір — 10 МБ.' :
          status === 404 ? 'Рахунок не знайдено. Оновіть сторінку.' :
          status === 422 ? 'Імпорт відхилено. Перевірте валюту рахунку, дати, суми, описи та баланс виписки. Операції не збережено.' :
          'Не вдалося проаналізувати PDF. Спробуйте ще раз або оберіть іншу виписку.');
      },
    });
  }

}
