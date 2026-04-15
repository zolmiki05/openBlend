import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { LucideAngularModule, Save, Check, AlertCircle, TriangleAlert } from 'lucide-angular';
import { InputTextModule } from 'primeng/inputtext';
import { SyncService } from '../../core/services/sync.service';

@Component({
  selector: 'app-settings',
  templateUrl: './settings.component.html',
  styleUrl: './settings.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, LucideAngularModule, InputTextModule],
})
export class SettingsComponent implements OnInit {
  private readonly sync = inject(SyncService);
  private readonly fb = inject(FormBuilder);
  private readonly destroyRef = inject(DestroyRef);

  readonly loading = signal(true);
  readonly saving = signal(false);
  readonly saveStatus = signal<'idle' | 'success' | 'error'>('idle');
  readonly errorMessage = signal<string | null>(null);

  readonly SaveIcon = Save;
  readonly CheckIcon = Check;
  readonly AlertCircleIcon = AlertCircle;
  readonly TriangleAlertIcon = TriangleAlert;

  readonly scheduleOptions = [
    { value: 'daily', label: 'Daily' },
    { value: 'every_two_days', label: 'Every 2 days' },
    { value: 'weekly', label: 'Weekly' },
    { value: 'manual', label: 'Manual' },
  ];

  readonly form = this.fb.group({
    target_playlist_name: ['', [Validators.required, Validators.maxLength(256)]],
    sync_schedule: ['weekly', Validators.required],
    playlist_size: [40, [Validators.required, Validators.min(10), Validators.max(100)]],
    allow_explicit: [true],
    ratio_common: [30, [Validators.required, Validators.min(0), Validators.max(100)]],
    ratio_bridge_a_to_b: [25, [Validators.required, Validators.min(0), Validators.max(100)]],
    ratio_bridge_b_to_a: [25, [Validators.required, Validators.min(0), Validators.max(100)]],
    ratio_experimental: [20, [Validators.required, Validators.min(0), Validators.max(100)]],
    max_repair_loops: [3, [Validators.required, Validators.min(0), Validators.max(10)]],
  });

  readonly ratioSum = computed(() => {
    const v = this.form.value;
    return (v.ratio_common ?? 0) + (v.ratio_bridge_a_to_b ?? 0) +
           (v.ratio_bridge_b_to_a ?? 0) + (v.ratio_experimental ?? 0);
  });

  readonly ratioValid = computed(() => this.ratioSum() === 100);
  readonly canSave = computed(() => this.form.valid && this.ratioValid() && !this.saving());

  ngOnInit(): void {
    this.sync.getSettings()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (s) => {
          this.form.patchValue(s);
          this.loading.set(false);
        },
        error: () => {
          this.errorMessage.set('Failed to load settings.');
          this.loading.set(false);
        },
      });

    this.form.valueChanges
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe();
  }

  save(): void {
    if (!this.canSave()) return;
    this.saving.set(true);
    this.saveStatus.set('idle');

    const value = this.form.value as Record<string, unknown>;
    this.sync.updateSettings(value as Parameters<typeof this.sync.updateSettings>[0])
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.saving.set(false);
          this.saveStatus.set('success');
          setTimeout(() => this.saveStatus.set('idle'), 3000);
        },
        error: (err) => {
          this.saving.set(false);
          this.saveStatus.set('error');
          this.errorMessage.set(err?.error?.detail ?? 'Failed to save settings.');
        },
      });
  }
}
