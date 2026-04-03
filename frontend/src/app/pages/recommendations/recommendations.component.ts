import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { SyncService, Track } from '../../core/services/sync.service';

@Component({
  selector: 'app-recommendations',
  templateUrl: './recommendations.component.html',
  styleUrl: './recommendations.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class RecommendationsComponent implements OnInit {
  private readonly syncService = inject(SyncService);
  private readonly destroyRef = inject(DestroyRef);

  readonly tracks = signal<Track[]>([]);
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);
  readonly activeFilter = signal<string>('all');

  readonly filteredTracks = computed(() => {
    const filter = this.activeFilter();
    const all = this.tracks();
    if (filter === 'all') return all;
    if (filter === 'bridge') {
      return all.filter(t => t.bucket === 'bridge_a_to_b' || t.bucket === 'bridge_b_to_a');
    }
    return all.filter(t => t.bucket === filter);
  });

  readonly filters = [
    { key: 'all', label: 'All' },
    { key: 'common', label: 'Common' },
    { key: 'bridge', label: 'Bridge' },
    { key: 'experimental', label: 'Experimental' },
  ];

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.error.set(null);

    this.syncService.getPlaylist()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (playlists) => {
          const seen = new Set<string>();
          const deduped: Track[] = [];
          for (const playlist of playlists) {
            for (const track of playlist.tracks) {
              if (!seen.has(track.canonical_track_id)) {
                seen.add(track.canonical_track_id);
                deduped.push(track);
              }
            }
          }
          deduped.sort((a, b) => a.position - b.position);
          this.tracks.set(deduped);
          this.loading.set(false);
        },
        error: (err) => {
          this.error.set(err?.error?.detail ?? 'Failed to load recommendations.');
          this.loading.set(false);
        },
      });
  }

  setFilter(key: string): void {
    this.activeFilter.set(key);
  }

  bucketLabel(bucket: string): string {
    const labels: Record<string, string> = {
      common: 'Common',
      bridge_a_to_b: 'Bridge',
      bridge_b_to_a: 'Bridge',
      experimental: 'Exp',
    };
    return labels[bucket] ?? bucket;
  }

  scoreBarWidths(track: Track): { a: string; b: string } {
    const total = track.score_a + track.score_b;
    if (total === 0) return { a: '50%', b: '50%' };
    return {
      a: `${(track.score_a / total) * 100}%`,
      b: `${(track.score_b / total) * 100}%`,
    };
  }

  skeletons = Array.from({ length: 8 });
}
