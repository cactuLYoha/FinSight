import { Routes } from '@angular/router';
import { accountGuard } from './auth/account-guard';

export const routes: Routes = [
  {
    path: '',
    pathMatch: 'full',
    title: 'FinSight — фінанси з перспективою',
    loadComponent: () => import('./home/home').then((m) => m.Home),
  },
  {
    path: 'cookies',
    title: 'Про cookies — FinSight',
    loadComponent: () => import('./cookies/cookies').then((m) => m.Cookies),
  },
  {
    path: 'login',
    title: 'Увійти — FinSight',
    data: { mode: 'login' },
    loadComponent: () => import('./auth/auth-page').then((m) => m.AuthPage),
  },
  {
    path: 'register',
    title: 'Створити акаунт — FinSight',
    data: { mode: 'register' },
    loadComponent: () => import('./auth/auth-page').then((m) => m.AuthPage),
  },
  { path: 'verify', title: 'Підтвердження пошти — FinSight', loadComponent: () => import('./auth/verification-page').then((m) => m.VerificationPage) },
  { path: 'account/settings', title: 'Налаштування акаунту — FinSight', canActivate: [accountGuard], data: { account: true }, loadComponent: () => import('./auth/password-page').then(m => m.PasswordPage) },
  { path: 'forgot-password', title: 'Відновлення пароля — FinSight', loadComponent: () => import('./auth/password-page').then(m => m.PasswordPage) },
  { path: 'dashboard', title: 'Особистий кабінет — FinSight', canActivate: [accountGuard], loadComponent: () => import('./dashboard/dashboard').then(m => m.Dashboard) },
  { path: 'savings', title: 'Заощадження — FinSight', canActivate: [accountGuard], loadComponent: () => import('./savings/savings-page').then(m => m.SavingsPage) },
  { path: 'accounts', title: 'Рахунки — FinSight', canActivate: [accountGuard], loadComponent: () => import('./accounts/accounts-page').then(m => m.AccountsPage) },
  { path: '**', redirectTo: '' },
];
