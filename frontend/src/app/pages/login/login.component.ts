import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import { LucideAngularModule, Eye, EyeOff, AlertCircle } from 'lucide-angular';
import { InputTextModule } from 'primeng/inputtext';
import { AuthService } from '../../core/services/auth.service';

@Component({
  selector: 'app-login',
  imports: [ReactiveFormsModule, LucideAngularModule, InputTextModule],
  templateUrl: './login.component.html',
  styleUrl: './login.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class LoginComponent {
  private readonly fb = inject(FormBuilder);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  readonly loading = signal(false);
  readonly error = signal('');
  readonly showPassword = signal(false);
  readonly showForgotForm = signal(false);
  readonly forgotSent = signal(false);
  readonly forgotUsername = signal('');

  readonly EyeIcon = Eye;
  readonly EyeOffIcon = EyeOff;
  readonly AlertCircleIcon = AlertCircle;

  readonly form = this.fb.nonNullable.group({
    username: ['', Validators.required],
    password: ['', Validators.required],
  });

  submit(): void {
    if (this.form.invalid || this.loading()) return;
    this.error.set('');
    this.loading.set(true);

    const { username, password } = this.form.getRawValue();
    this.auth.login(username, password).subscribe({
      next: (res) => {
        this.loading.set(false);
        if (res.is_temp_password) {
          this.router.navigate(['/change-password']);
        } else {
          this.router.navigate(['/dashboard']);
        }
      },
      error: (err) => {
        this.loading.set(false);
        this.error.set(
          err.status === 401 ? 'Invalid username or password.' : 'Something went wrong.',
        );
      },
    });
  }

  submitForgot(): void {
    const username = this.forgotUsername();
    if (!username.trim()) return;
    this.auth.forgotPassword(username).subscribe({
      next: () => this.forgotSent.set(true),
      error: () => this.forgotSent.set(true),
    });
  }

  togglePassword(): void {
    this.showPassword.update((v) => !v);
  }
}
