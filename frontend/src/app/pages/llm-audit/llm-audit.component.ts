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
import { DecimalPipe } from '@angular/common';
import { LLMLog, LLMLogDetail, SyncService } from '../../core/services/sync.service';

@Component({
  selector: 'app-llm-audit',
  templateUrl: './llm-audit.component.html',
  styleUrl: './llm-audit.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DecimalPipe],
})
export class LlmAuditComponent implements OnInit {
  private readonly sync = inject(SyncService);
  private readonly destroyRef = inject(DestroyRef);

  readonly logs = signal<LLMLog[]>([]);
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);
  readonly expandedId = signal<string | null>(null);
  readonly expandedDetail = signal<LLMLogDetail | null>(null);
  readonly detailLoading = signal(false);

  readonly totals = computed(() => {
    const logs = this.logs();
    return {
      prompt: logs.reduce((s, l) => s + l.prompt_tokens, 0),
      completion: logs.reduce((s, l) => s + l.completion_tokens, 0),
      total: logs.reduce((s, l) => s + l.total_tokens, 0),
      calls: logs.length,
    };
  });

  ngOnInit(): void {
    this.sync.getLLMLogs(50)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (logs) => {
          this.logs.set(logs);
          this.loading.set(false);
        },
        error: (err) => {
          this.error.set(err?.error?.detail ?? 'Failed to load logs.');
          this.loading.set(false);
        },
      });
  }

  toggleRow(log: LLMLog): void {
    if (this.expandedId() === log.id) {
      this.expandedId.set(null);
      this.expandedDetail.set(null);
      return;
    }

    this.expandedId.set(log.id);
    this.expandedDetail.set(null);
    this.detailLoading.set(true);

    this.sync.getLLMLogDetail(log.id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (detail) => {
          this.expandedDetail.set(detail);
          this.detailLoading.set(false);
        },
        error: () => {
          this.detailLoading.set(false);
        },
      });
  }

  isExpanded(id: string): boolean {
    return this.expandedId() === id;
  }

  isRepairStage(stage: string): boolean {
    return stage.startsWith('repair_');
  }

  formatDate(iso: string): string {
    return new Date(iso).toLocaleString('en-US', {
      month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit', second: '2-digit',
    });
  }

  formatJson(obj: Record<string, unknown>): string {
    return JSON.stringify(obj, null, 2);
  }

  skeletons = Array.from({ length: 6 });
}
