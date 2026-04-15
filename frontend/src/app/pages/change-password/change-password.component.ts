import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import { LucideAngularModule, Lock, Eye, EyeOff, AlertCircle } from 'lucide-angular';
import { AuthService } from '../../core/services/auth.service';

@Component({
  selector: 'app-change-password',
  imports: [ReactiveFormsModule, LucideAngularModule],
  templateUrl: './change-password.component.html',
  styleUrl: './change-password.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ChangePasswordComponent {
  private readonly fb = inject(FormBuilder);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  readonly loading = signal(false);
  readonly error = signal('');
  readonly showCurrent = signal(false);
  readonly showNew = signal(false);
  readonly showConfirm = signal(false);

  readonly LockIcon = Lock;
  readonly EyeIcon = Eye;
  readonly EyeOffIcon = EyeOff;
  readonly AlertCircleIcon = AlertCircle;

  readonly form = this.fb.nonNullable.group({
    currentPassword: ['', Validators.required],
    newPassword: ['', [Validators.required, Validators.minLength(8)]],
    confirmPassword: ['', Validators.required],
  });

  readonly passwordStrength = computed(() => {
    const p = this.form.get('newPassword')?.value ?? '';
    if (p.length === 0) return 0;
    let score = 0;
    if (p.length >= 8) score++;
    if (p.length >= 12) score++;
    if (/[A-Z]/.test(p)) score++;
    if (/[0-9]/.test(p)) score++;
    if (/[^A-Za-z0-9]/.test(p)) score++;
    return score;
  });

  readonly strengthLabel = computed(() => {
    const s = this.passwordStrength();
    if (s <= 1) return 'Weak';
    if (s <= 3) return 'Fair';
    if (s === 4) return 'Good';
    return 'Strong';
  });

  readonly strengthClass = computed(() => {
    const s = this.passwordStrength();
    if (s <= 1) return 'weak';
    if (s <= 3) return 'fair';
    if (s === 4) return 'good';
    return 'strong';
  });

  submit(): void {
    if (this.form.invalid || this.loading()) return;

    const { currentPassword, newPassword, confirmPassword } = this.form.getRawValue();
    if (newPassword !== confirmPassword) {
      this.error.set('New passwords do not match.');
      return;
    }
    this.error.set('');
    this.loading.set(true);

    this.auth.changePassword(currentPassword, newPassword).subscribe({
      next: () => {
        this.loading.set(false);
        this.router.navigate(['/dashboard']);
      },
      error: (err) => {
        this.loading.set(false);
        const msg = err.error?.detail ?? 'Something went wrong.';
        this.error.set(msg);
      },
    });
  }
}
