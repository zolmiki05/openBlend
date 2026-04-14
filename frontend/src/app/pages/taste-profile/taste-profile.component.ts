import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  inject,
  signal,
} from '@angular/core';
import { DecimalPipe } from '@angular/common';
import {
  TasteProfileSummary,
  TasteScoreItem,
  SyncService,
} from '../../core/services/sync.service';

@Component({
  selector: 'app-taste-profile',
  templateUrl: './taste-profile.component.html',
  styleUrl: './taste-profile.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DecimalPipe],
})
export class TasteProfileComponent implements OnInit {
  private readonly sync = inject(SyncService);

  readonly scores = signal<TasteScoreItem[]>([]);
  readonly summary = signal<TasteProfileSummary | null>(null);
  readonly loading = signal(true);
  readonly refreshing = signal(false);
  readonly refreshResult = signal<number | null>(null);
  readonly error = signal<string | null>(null);
  readonly sortBy = signal<'score' | 'frequency' | 'lastfm'>('score');
  readonly sortOptions: { value: 'score' | 'frequency' | 'lastfm'; label: string }[] = [
    { value: 'score',     label: 'Score' },
    { value: 'frequency', label: 'Frequency' },
    { value: 'lastfm',    label: 'Last.fm boost' },
  ];
  readonly limit = signal(100);

  ngOnInit(): void {
    this._load();
  }

  changeSort(sort: 'score' | 'frequency' | 'lastfm'): void {
    this.sortBy.set(sort);
    this._loadScores();
  }

  refresh(): void {
    this.refreshing.set(true);
    this.refreshResult.set(null);
    this.error.set(null);

    this.sync.refreshTasteScores().subscribe({
      next: ({ recomputed }) => {
        this.refreshing.set(false);
        this.refreshResult.set(recomputed);
        this._load();
        setTimeout(() => this.refreshResult.set(null), 5000);
      },
      error: (err) => {
        this.refreshing.set(false);
        this.error.set(err?.error?.detail ?? 'Refresh failed.');
      },
    });
  }

  platformLabel(platform: string): string {
    const map: Record<string, string> = {
      spotify: 'Spotify',
      apple_music: 'Apple Music',
      lastfm: 'Last.fm',
    };
    return map[platform] ?? platform;
  }

  sourceLabel(source: string): string {
    const map: Record<string, string> = {
      top_tracks_short: 'Top (1mo)',
      top_tracks_medium: 'Top (6mo)',
      top_tracks_long: 'Top (all-time)',
      recently_played: 'Recently played',
      saved_songs: 'Saved',
      playlist: 'Playlist',
      library_playlist: 'Library playlist',
      apple_recently_played: 'Recently played',
      apple_recommendations: 'Recommendations',
      lastfm_loved: 'Loved',
      lastfm_top_short: 'LFM top (1mo)',
      lastfm_top_medium: 'LFM top (6mo)',
      lastfm_top_long: 'LFM top (all)',
      lastfm_recent: 'LFM recent',
    };
    return map[source] ?? source;
  }

  scoreBarWidth(score: number): string {
    const max = this.summary()?.max_score ?? 1;
    return `${Math.min((score / max) * 100, 100).toFixed(1)}%`;
  }

  private _load(): void {
    this.loading.set(true);
    this._loadScores();
    this.sync.getTasteProfileSummary().subscribe({
      next: (s) => this.summary.set(s),
    });
  }

  private _loadScores(): void {
    this.sync.getTasteScores(this.limit(), this.sortBy()).subscribe({
      next: (s) => {
        this.scores.set(s);
        this.loading.set(false);
      },
      error: (err) => {
        this.error.set(err?.error?.detail ?? 'Failed to load taste profile.');
        this.loading.set(false);
      },
    });
  }

  summaryEntries(obj: Record<string, number>): { key: string; value: number }[] {
    return Object.entries(obj)
      .map(([key, value]) => ({ key, value }))
      .sort((a, b) => b.value - a.value);
  }
}
