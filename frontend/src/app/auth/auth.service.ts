import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { inject, Injectable, signal } from '@angular/core';
import { catchError, finalize, map, Observable, of, shareReplay, switchMap, tap, throwError, timeout } from 'rxjs';

export interface User {
  id: number; email: string; created_at: string;
  is_email_verified: boolean; email_verified_at: string | null;
}
export interface Credentials { email: string; password: string; }
interface UserResponse { user: User; }
export interface VerificationContext {
  verification_required: true;
  masked_email: string;
  expires_at: string;
  resend_available_at: string;
  delivery_ready: boolean;
}
export type AuthStatus = 'checking' | 'authenticated' | 'anonymous' | 'error';
export class CookieStorageError extends Error {
  constructor() { super('Browser did not retain the authentication cookie.'); }
}
export class AccountCreatedError extends Error {
  constructor(readonly originalError: unknown) { super('Account created, automatic login failed.'); }
}

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);
  private restoreRequest?: Observable<User | null>;
  readonly user = signal<User | null>(null);
  readonly status = signal<AuthStatus>('checking');
  readonly signingOut = signal(false);
  readonly registrationNotice = signal('');
  readonly verification = signal<VerificationContext | null>(null);
  readonly verificationNotice = signal('');

  restoreSession(): Observable<User | null> {
    if (this.restoreRequest) return this.restoreRequest;
    this.status.set('checking');
    this.restoreRequest = this.http.get<UserResponse>('/api/auth/me').pipe(
      timeout(10000), map((response) => response.user), tap((user) => this.setUser(user)),
      catchError((error: unknown) => {
        if (this.isAuthFailure(error)) { this.setUser(null); return of(null); }
        this.status.set('error'); return throwError(() => error);
      }),
      finalize(() => { this.restoreRequest = undefined; }),
      shareReplay({ bufferSize: 1, refCount: false }),
    );
    return this.restoreRequest;
  }

  login(credentials: Credentials): Observable<User | null> {
    this.verificationNotice.set('');
    return this.http.post<UserResponse | VerificationContext>('/api/auth/session', credentials).pipe(
      timeout(30000),
      switchMap((response) => {
        if ('verification_required' in response) {
          this.verification.set(response); this.setUser(null); return of(null);
        }
        return this.verifyCookie(response.user);
      }),
      catchError((error: unknown) => this.pendingDelivery(error)),
    );
  }

  register(credentials: Credentials): Observable<User | null> {
    this.verificationNotice.set('');
    return this.http.post<VerificationContext>('/api/auth/register', credentials).pipe(
      timeout(30000),
      map((response) => { this.verification.set(response); this.setUser(null); return null; }),
      catchError((error: unknown) => this.pendingDelivery(error)),
    );
  }

  verificationState(): Observable<VerificationContext> {
    return this.http.get<VerificationContext>('/api/auth/verification').pipe(
      timeout(10000), tap((context) => this.verification.set(context)),
    );
  }

  resendVerification(): Observable<VerificationContext> {
    return this.http.post<VerificationContext>('/api/auth/verification/resend', {}).pipe(
      timeout(30000), tap((context) => this.verification.set(context)),
    );
  }

  confirmVerification(code: string, trustDevice: boolean): Observable<User> {
    return this.http.post<UserResponse>('/api/auth/verification/confirm', { code, trust_device: trustDevice }).pipe(
      timeout(10000), switchMap(({ user }) => this.verifyCookie(user)),
      tap(() => { this.verification.set(null); this.verificationNotice.set(''); }),
    );
  }

  logout(): Observable<void> {
    this.signingOut.set(true);
    return this.http.delete<void>('/api/auth/session').pipe(
      timeout(10000), tap(() => { this.setUser(null); this.verification.set(null); }),
      finalize(() => this.signingOut.set(false)),
    );
  }

  passwordChanged(): void {
    this.setUser(null);
    this.verification.set(null);
    this.registrationNotice.set('Пароль змінено. Увійдіть із новим паролем.');
  }

  private verifyCookie(expected: User): Observable<User> {
    return this.http.get<UserResponse>('/api/auth/me').pipe(
      timeout(10000),
      map(({ user }) => { if (user.id !== expected.id) throw new CookieStorageError(); return user; }),
      catchError((error: unknown) => throwError(() => this.isAuthFailure(error) ? new CookieStorageError() : error)),
      tap((user) => this.setUser(user)),
    );
  }

  private pendingDelivery(error: unknown): Observable<null> {
    this.setUser(null);
    if (error instanceof HttpErrorResponse && error.status === 503 && error.error?.verification_required) {
      this.verification.set(error.error as VerificationContext);
      this.verificationNotice.set('Лист не вдалося надіслати. Спробуйте повторне надсилання, коли кнопка стане доступною.');
      return of(null);
    }
    return throwError(() => error);
  }

  private setUser(user: User | null): void {
    this.user.set(user); this.status.set(user ? 'authenticated' : 'anonymous');
  }
  private isAuthFailure(error: unknown): boolean {
    return error instanceof HttpErrorResponse && (
      error.status === 401 || error.status === 422 ||
      (error.status === 403 && error.error?.code === 'verification_required')
    );
  }
}
