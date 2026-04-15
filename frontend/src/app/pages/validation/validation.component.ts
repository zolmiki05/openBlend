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
import { LucideAngularModule, Check, X, CheckCircle2, AlertCircle } from 'lucide-angular';
import { ReviewItem, SyncService } from '../../core/services/sync.service';

type FilterTab = 'all' | 'pending' | 'approved' | 'rejected';

@Component({
  selector: 'app-validation',
  templateUrl: './validation.component.html',
  styleUrl: './validation.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [LucideAngularModule],
})
export class ValidationComponent implements OnInit {
  private readonly sync = inject(SyncService);
  private readonly destroyRef = inject(DestroyRef);

  readonly items = signal<ReviewItem[]>([]);
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);
  readonly activeTab = signal<FilterTab>('all');
  readonly actioning = signal<Set<string>>(new Set());

  readonly CheckIcon = Check;
  readonly XIcon = X;
  readonly CheckCircle2Icon = CheckCircle2;
  readonly AlertCircleIcon = AlertCircle;

  readonly tabs: { key: FilterTab; label: string }[] = [
    { key: 'all', label: 'All' },
    { key: 'pending', label: 'Pending' },
    { key: 'approved', label: 'Approved' },
    { key: 'rejected', label: 'Rejected' },
  ];

  readonly filteredItems = computed(() => {
    const tab = this.activeTab();
    const all = this.items();
    return tab === 'all' ? all : all.filter(i => i.status === tab);
  });

  readonly counts = computed(() => {
    const all = this.items();
    return {
      all: all.length,
      pending: all.filter(i => i.status === 'pending').length,
      approved: all.filter(i => i.status === 'approved').length,
      rejected: all.filter(i => i.status === 'rejected').length,
    };
  });

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.sync.getValidationQueue()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (items) => {
          this.items.set(items);
          this.loading.set(false);
        },
        error: (err) => {
          this.error.set(err?.error?.detail ?? 'Failed to load validation queue.');
          this.loading.set(false);
        },
      });
  }

  setTab(tab: FilterTab): void {
    this.activeTab.set(tab);
  }

  review(item: ReviewItem, action: 'approved' | 'rejected'): void {
    // Optimistic update
    this.actioning.update(s => new Set([...s, item.id]));
    this.items.update(list =>
      list.map(i => i.id === item.id ? { ...i, status: action } : i)
    );

    this.sync.reviewQueueItem(item.id, action)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.actioning.update(s => { const n = new Set(s); n.delete(item.id); return n; });
        },
        error: () => {
          // Revert on error
          this.items.update(list =>
            list.map(i => i.id === item.id ? { ...i, status: 'pending' } : i)
          );
          this.actioning.update(s => { const n = new Set(s); n.delete(item.id); return n; });
        },
      });
  }

  isActioning(id: string): boolean {
    return this.actioning().has(id);
  }

  confidencePct(c: number | null): string {
    return c != null ? `${Math.round(c * 100)}%` : '';
  }

  platformLabel(p: string | null): string {
    if (p === 'spotify') return 'Spotify';
    if (p === 'apple_music') return 'Apple Music';
    return 'Unknown';
  }

  formatDate(iso: string): string {
    return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  }
}
