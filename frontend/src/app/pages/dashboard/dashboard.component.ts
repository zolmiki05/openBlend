import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  inject,
  signal,
} from '@angular/core';
import { AuthService } from '../../core/services/auth.service';
import {
  PlaylistStats,
  PlatformStatus,
  SyncRun,
  SyncService,
} from '../../core/services/sync.service';

@Component({
  selector: 'app-dashboard',
  templateUrl: './dashboard.component.html',
  styleUrl: './dashboard.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class DashboardComponent implements OnInit {
  readonly auth = inject(AuthService);
  private readonly sync = inject(SyncService);

  readonly lastRun = signal<SyncRun | null>(null);
  readonly syncing = signal(false);
  readonly syncError = signal('');
  readonly spotifyStatus = signal<PlatformStatus | null>(null);
  readonly appleMusicStatus = signal<PlatformStatus | null>(null);
  readonly playlistStats = signal<PlaylistStats | null>(null);

  ngOnInit(): void {
    this._loadData();
  }

  triggerSync(): void {
    if (this.syncing()) return;
    this.syncing.set(true);
    this.syncError.set('');

    this.sync.triggerSync().subscribe({
      next: (run) => {
        this.lastRun.set(run);
        this.syncing.set(false);
        this._loadPlaylistStats();
      },
      error: (err) => {
        this.syncing.set(false);
        this.syncError.set(err.error?.detail ?? 'Sync failed.');
      },
    });
  }

  private _loadData(): void {
    this.sync.getRuns(1).subscribe({
      next: (runs) => this.lastRun.set(runs[0] ?? null),
    });

    const user = this.auth.currentUser();
    if (user?.platform === 'spotify') {
      this.sync.getSpotifyStatus().subscribe({
        next: (s) => this.spotifyStatus.set(s),
      });
    } else {
      this.sync.getAppleMusicStatus().subscribe({
        next: (s) => this.appleMusicStatus.set(s),
      });
    }

    this._loadPlaylistStats();
  }

  private _loadPlaylistStats(): void {
    this.sync.getPlaylistStats().subscribe({
      next: (s) => this.playlistStats.set(s),
    });
  }

  statusClass(status: string): string {
    if (status === 'completed') return 'status--ok';
    if (status === 'failed') return 'status--error';
    if (status === 'running') return 'status--running';
    return 'status--pending';
  }

  bucketEntries(buckets: Record<string, number>): { key: string; value: number }[] {
    return Object.entries(buckets).map(([key, value]) => ({ key, value }));
  }
}
