import { HttpClient } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { tap } from 'rxjs';
import { environment } from '../../../environments/environment';
import { User } from '../models/user.model';

interface LoginResponse {
  access_token: string;
  token_type: string;
  is_temp_password: boolean;
  username: string;
  platform: string;
}

const TOKEN_KEY = 'ob_access_token';
const USER_KEY = 'ob_user';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);
  private readonly router = inject(Router);

  private readonly _token = signal<string | null>(localStorage.getItem(TOKEN_KEY));
  private readonly _user = signal<User | null>(this._loadUser());

  readonly token = this._token.asReadonly();
  readonly currentUser = this._user.asReadonly();
  readonly isAuthenticated = computed(() => this._token() !== null);
  readonly requiresPasswordChange = computed(() => this._user()?.is_temp_password ?? false);

  login(username: string, password: string) {
    return this.http
      .post<LoginResponse>(`${environment.apiUrl}/auth/login`, { username, password })
      .pipe(
        tap((res) => {
          const user: User = {
            username: res.username,
            platform: res.platform as User['platform'],
            is_temp_password: res.is_temp_password,
          };
          localStorage.setItem(TOKEN_KEY, res.access_token);
          localStorage.setItem(USER_KEY, JSON.stringify(user));
          this._token.set(res.access_token);
          this._user.set(user);
        }),
      );
  }

  changePassword(currentPassword: string, newPassword: string) {
    return this.http
      .post(`${environment.apiUrl}/auth/change-password`, {
        current_password: currentPassword,
        new_password: newPassword,
      })
      .pipe(
        tap(() => {
          const user = this._user();
          if (user) {
            const updated = { ...user, is_temp_password: false };
            localStorage.setItem(USER_KEY, JSON.stringify(updated));
            this._user.set(updated);
          }
        }),
      );
  }

  forgotPassword(username: string) {
    return this.http.post(`${environment.apiUrl}/auth/forgot-password`, { username });
  }

  logout(): void {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    this._token.set(null);
    this._user.set(null);
    this.router.navigate(['/login']);
  }

  private _loadUser(): User | null {
    const raw = localStorage.getItem(USER_KEY);
    if (!raw) return null;
    try {
      return JSON.parse(raw) as User;
    } catch {
      return null;
    }
  }
}
