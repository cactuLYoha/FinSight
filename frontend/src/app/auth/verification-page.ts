import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, inject, OnInit, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { finalize } from 'rxjs';
import { AuthService, CookieStorageError } from './auth.service';
import { Icon } from '../icon';

@Component({
  selector: 'app-verification-page',
  imports: [ReactiveFormsModule, RouterLink, Icon],
  templateUrl: './verification-page.html',
  styleUrls: ['./auth-page.scss', './verification-page.scss'],
})
export class VerificationPage implements OnInit {
  protected readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);
  private readonly fb = inject(FormBuilder);
  protected readonly pending = signal(false);
  protected readonly loading = signal(true);
  protected readonly closed = signal(false);
  protected readonly error = signal('');
  protected readonly info = signal('');
  protected readonly now = signal(Date.now());
  protected readonly form = this.fb.nonNullable.group({
    code: ['', [Validators.required, Validators.pattern(/^[0-9]{6}$/)]],
    trust: [false],
  });

  constructor() {
    const timer = setInterval(() => this.now.set(Date.now()), 1000);
    this.destroyRef.onDestroy(() => clearInterval(timer));
  }
  ngOnInit(): void {
    this.info.set(this.auth.verificationNotice());
    this.auth.verificationState().pipe(takeUntilDestroyed(this.destroyRef), finalize(() => this.loading.set(false))).subscribe({
      error: (error: unknown) => this.handleError(error),
    });
  }
  remaining(): number {
    return Math.max(0, Math.ceil((Date.parse(this.auth.verification()?.expires_at ?? '') - this.now()) / 1000) || 0);
  }
  cooldown(): number {
    return Math.max(0, Math.ceil((Date.parse(this.auth.verification()?.resend_available_at ?? '') - this.now()) / 1000) || 0);
  }
  submit(): void {
    if (this.pending() || this.closed() || !this.remaining()) return;
    this.error.set('');
    if (this.form.invalid) { this.form.markAllAsTouched(); this.error.set('Введіть 6 цифр із листа.'); return; }
    this.pending.set(true);
    this.auth.confirmVerification(this.form.controls.code.value, this.form.controls.trust.value).pipe(
      takeUntilDestroyed(this.destroyRef), finalize(() => this.pending.set(false)),
    ).subscribe({
      next: () => { this.form.reset(); void this.router.navigateByUrl('/'); },
      error: (error: unknown) => this.handleError(error),
    });
  }
  resend(): void {
    if (this.pending() || this.cooldown() || this.closed() || !this.remaining()) return;
    this.pending.set(true); this.error.set(''); this.info.set('');
    this.auth.resendVerification().pipe(
      takeUntilDestroyed(this.destroyRef), finalize(() => this.pending.set(false)),
    ).subscribe({
      next: () => { this.info.set('Новий код надіслано. Використайте його замість попереднього.'); this.form.controls.code.reset(); },
      error: (error: unknown) => {
        this.handleError(error);
        if (!this.closed()) this.auth.verificationState().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({ error: () => {} });
      },
    });
  }
  private handleError(error: unknown): void {
    if (error instanceof CookieStorageError) { this.closed.set(true); this.error.set('Не вдалося зберегти вхід. Дозвольте cookies та увійдіть знову.'); return; }
    if (error instanceof HttpErrorResponse) {
      const code = error.error?.code;
      if (error.status === 404 || error.status === 410 || code === 'verification_closed') {
        this.closed.set(true); this.error.set('Перевірка завершена або прострочена. Почніть вхід заново.'); return;
      }
      if (code === 'invalid_code') { this.error.set('Неправильний код. Перевірте цифри з останнього листа.'); return; }
      if (error.status === 429) { this.error.set('Досягнуто ліміту. Зачекайте перед наступною спробою.'); return; }
      if (code === 'email_delivery_failed') { this.error.set('Не вдалося надіслати лист. Спробуйте повторити пізніше.'); return; }
    }
    this.error.set('Сервер тимчасово недоступний. Спробуйте ще раз.');
  }
}
