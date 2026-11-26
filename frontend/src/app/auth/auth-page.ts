import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, ElementRef, inject, OnInit, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import {
  AbstractControl,
  FormBuilder,
  ReactiveFormsModule,
  ValidationErrors,
  Validators,
} from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { finalize } from 'rxjs';
import { AccountCreatedError, AuthService, CookieStorageError } from './auth.service';
import { Icon } from '../icon';

function passwordsMatch(control: AbstractControl): ValidationErrors | null {
  return control.get('password')?.value === control.get('confirmation')?.value
    ? null
    : { passwordMismatch: true };
}

@Component({
  selector: 'app-auth-page',
  imports: [ReactiveFormsModule, RouterLink, Icon],
  templateUrl: './auth-page.html',
  styleUrl: './auth-page.scss',
})
export class AuthPage implements OnInit {
  protected readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);
  private readonly fb = inject(FormBuilder);
  private readonly destroyRef = inject(DestroyRef);
  protected readonly isRegister = this.route.snapshot.data['mode'] === 'register';
  protected readonly pending = signal(false);
  protected readonly submitted = signal(false);
  protected readonly showPassword = signal(false);
  protected readonly error = signal('');
  protected readonly info = signal('');
  protected readonly form = this.fb.nonNullable.group(
    {
      email: ['', [Validators.required, Validators.email, Validators.maxLength(120)]],
      password: [
        '',
        this.isRegister
          ? [Validators.required, Validators.minLength(8), Validators.maxLength(35)]
          : [Validators.required],
      ],
      confirmation: ['', this.isRegister ? [Validators.required] : []],
    },
    { validators: this.isRegister ? passwordsMatch : null },
  );

  ngOnInit(): void {
    if (!this.isRegister) {
      this.info.set(this.auth.registrationNotice());
      this.auth.registrationNotice.set('');
    }
    if (this.auth.status() === 'authenticated') {
      void this.router.navigateByUrl('/');
    } else if (this.auth.status() === 'checking') {
      this.auth
        .restoreSession()
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe({
          next: (user) => {
            if (user) void this.router.navigateByUrl('/');
          },
          error: () => {},
        });
    }
  }

  invalid(name: 'email' | 'password' | 'confirmation'): boolean {
    const field = this.form.controls[name];
    return field.invalid && (field.touched || this.submitted());
  }

  mismatch(): boolean {
    return (
      this.form.hasError('passwordMismatch') &&
      (this.form.controls.confirmation.touched || this.submitted())
    );
  }

  submit(): void {
    if (this.pending() || this.auth.status() === 'checking') return;
    this.submitted.set(true);
    this.error.set('');
    this.info.set('');
    this.form.controls.email.setValue(this.form.controls.email.value.trim());
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      const field =
        this.host.nativeElement.querySelector<HTMLInputElement>('input.ng-invalid') ??
        this.host.nativeElement.querySelector<HTMLInputElement>('#confirmation');
      field?.focus();
      return;
    }
    const credentials = {
      email: this.form.controls.email.value.toLowerCase(),
      password: this.form.controls.password.value,
    };
    this.pending.set(true);
    const request = this.isRegister
      ? this.auth.register(credentials)
      : this.auth.login(credentials);
    request
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.pending.set(false)),
      )
      .subscribe({
      next: (user) => {
          this.form.reset();
        void this.router.navigateByUrl(user ? '/' : '/verify');
        },
        error: (error: unknown) => {
          if (error instanceof AccountCreatedError) {
            this.auth.registrationNotice.set(
              error.originalError instanceof CookieStorageError
                ? 'Акаунт створено. Дозвольте cookies у браузері та увійдіть.'
                : 'Акаунт створено, але автоматичний вхід не завершився. Спробуйте увійти.',
            );
            void this.router.navigateByUrl('/login');
            return;
          }
          this.error.set(this.describeError(error));
        },
      });
  }

  private describeError(error: unknown): string {
    if (error instanceof CookieStorageError)
      return 'Не вдалося зберегти вхід. Дозвольте cookies для FinSight і спробуйте ще раз.';
    if (error instanceof HttpErrorResponse) {
      if (error.status === 401) return 'Неправильний email або пароль.';
      if (error.status === 409 && this.isRegister)
        return 'Цей email уже зареєстрований. Перейдіть до входу.';
      if (error.status === 400) return 'Перевірте email і пароль та спробуйте ще раз.';
      if (error.status === 429) return 'Досягнуто ліміту листів. Спробуйте пізніше.';
      if (error.status === 403)
        return 'Вхід із цієї адреси сайту недоступний. Перевірте адресу FinSight.';
    }
    return 'Не вдалося з’єднатися із сервером. Спробуйте ще раз трохи пізніше.';
  }
}
