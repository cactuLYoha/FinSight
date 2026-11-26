import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { finalize } from 'rxjs';
import { AuthService } from './auth.service';

@Component({
  selector: 'app-password-page',
  imports: [ReactiveFormsModule, RouterLink],
  templateUrl: './password-page.html',
  styleUrl: './password-page.scss',
})
export class PasswordPage {
  protected readonly auth = inject(AuthService);
  private readonly http = inject(HttpClient);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);
  private readonly fb = inject(FormBuilder);
  readonly account = inject(ActivatedRoute).snapshot.data['account'] === true;
  readonly pending = signal(false);
  readonly sent = signal(false);
  readonly error = signal('');
  readonly info = signal('');
  readonly seconds = signal(0);
  private resendAt = 0;
  readonly emailForm = this.fb.nonNullable.group({
    email: ['', [Validators.required, Validators.email, Validators.maxLength(120)]],
  });
  readonly form = this.fb.nonNullable.group({
    current_password: ['', this.account ? [Validators.required] : []],
    code: ['', this.account ? [] : [Validators.required, Validators.pattern(/^[0-9]{6}$/)]],
    new_password: ['', [Validators.required, Validators.minLength(8), Validators.maxLength(35)]],
    confirmation: ['', Validators.required],
  }, { validators: control => control.get('new_password')?.value === control.get('confirmation')?.value ? null : { mismatch: true } });

  constructor() {
    const timer = setInterval(() => this.seconds.set(Math.max(0, Math.ceil((this.resendAt - Date.now()) / 1000))), 1000);
    this.destroyRef.onDestroy(() => clearInterval(timer));
  }

  send(resend = false): void {
    if (this.pending() || (resend && this.seconds() > 0)) return;
    this.emailForm.controls.email.setValue(this.emailForm.controls.email.value.trim().toLowerCase());
    if (!resend && this.emailForm.invalid) { this.emailForm.markAllAsTouched(); return; }
    this.pending.set(true); this.error.set('');
    this.http.post<{ message: string; retry_after: number }>(`/api/auth/password/reset/${resend ? 'resend' : 'request'}`,
      resend ? {} : this.emailForm.getRawValue()).pipe(
      takeUntilDestroyed(this.destroyRef), finalize(() => this.pending.set(false)),
    ).subscribe({
      next: result => {
        this.sent.set(true); this.info.set(result.message);
        this.resendAt = Date.now() + result.retry_after * 1000;
        this.seconds.set(result.retry_after);
      },
      error: err => this.describeError(err),
    });
  }

  restart(): void {
    if (this.pending()) return;
    this.sent.set(false); this.form.reset(); this.error.set(''); this.info.set('');
  }

  submit(): void {
    if (this.pending()) return;
    if (this.form.invalid) { this.form.markAllAsTouched(); return; }
    this.pending.set(true); this.error.set('');
    const value = this.form.getRawValue();
    const body = this.account
      ? { current_password: value.current_password, new_password: value.new_password }
      : { code: value.code, new_password: value.new_password };
    this.http.post<void>(`/api/auth/password/${this.account ? 'change' : 'reset/confirm'}`, body).pipe(
      takeUntilDestroyed(this.destroyRef), finalize(() => this.pending.set(false)),
    ).subscribe({
      next: () => {
        this.form.reset(); this.auth.passwordChanged();
        void this.router.navigateByUrl('/login');
      },
      error: err => this.describeError(err),
    });
  }

  private describeError(error: unknown): void {
    const code = error instanceof HttpErrorResponse ? error.error?.code : '';
    const messages: Record<string, string> = {
      incorrect_current_password: 'Поточний пароль неправильний.',
      invalid_code: 'Код неправильний або вже недійсний. Перевірте його чи почніть відновлення заново.',
      verification_expired: 'Час відновлення минув. Почніть заново.',
      invalid_password_payload: 'Перевірте поля. Новий пароль має містити 8–35 символів.',
    };
    this.error.set(messages[code] ?? 'Не вдалося виконати запит. Перевірте з’єднання та спробуйте ще раз.');
    if (this.account && error instanceof HttpErrorResponse && error.status === 401) {
      this.auth.passwordChanged();
      this.auth.registrationNotice.set('Сесія завершилась. Увійдіть повторно.');
      void this.router.navigateByUrl('/login');
    }
  }
}
