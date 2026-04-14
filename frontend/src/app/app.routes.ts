import { Routes } from '@angular/router';
import { authGuard } from './core/guards/auth.guard';
import { passwordChangeGuard } from './core/guards/password-change.guard';

export const routes: Routes = [
  {
    path: '',
    redirectTo: 'dashboard',
    pathMatch: 'full',
  },
  {
    path: 'login',
    loadComponent: () =>
      import('./pages/login/login.component').then((m) => m.LoginComponent),
  },
  {
    path: 'change-password',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./pages/change-password/change-password.component').then(
        (m) => m.ChangePasswordComponent,
      ),
  },
  {
    path: 'auth/spotify/callback',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./pages/spotify-callback/spotify-callback.component').then(
        (m) => m.SpotifyCallbackComponent,
      ),
  },
  {
    path: 'auth/lastfm/callback',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./pages/lastfm-callback/lastfm-callback.component').then(
        (m) => m.LastFmCallbackComponent,
      ),
  },
  {
    path: '',
    canActivate: [authGuard, passwordChangeGuard],
    loadComponent: () =>
      import('./layout/shell/shell.component').then((m) => m.ShellComponent),
    children: [
      {
        path: 'dashboard',
        loadComponent: () =>
          import('./pages/dashboard/dashboard.component').then((m) => m.DashboardComponent),
      },
      {
        path: 'recommendations',
        loadComponent: () =>
          import('./pages/recommendations/recommendations.component').then((m) => m.RecommendationsComponent),
      },
      {
        path: 'accounts',
        loadComponent: () =>
          import('./pages/accounts/accounts.component').then((m) => m.AccountsComponent),
      },
      {
        path: 'settings',
        loadComponent: () =>
          import('./pages/settings/settings.component').then((m) => m.SettingsComponent),
      },
      {
        path: 'validation',
        loadComponent: () =>
          import('./pages/validation/validation.component').then((m) => m.ValidationComponent),
      },
      {
        path: 'llm-audit',
        loadComponent: () =>
          import('./pages/llm-audit/llm-audit.component').then((m) => m.LlmAuditComponent),
      },
      {
        path: 'taste-profile',
        loadComponent: () =>
          import('./pages/taste-profile/taste-profile.component').then((m) => m.TasteProfileComponent),
      },
    ],
  },
  {
    path: '**',
    redirectTo: 'dashboard',
  },
];
