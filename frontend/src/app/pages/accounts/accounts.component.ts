import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute } from '@angular/router';
import { AuthService } from '../../core/services/auth.service';
import { PlatformStatus, SyncService } from '../../core/services/sync.service';

declare const MusicKit: any; // Loaded via CDN in index.html

@Component({
  selector: 'app-accounts',
  templateUrl: './accounts.component.html',
  styleUrl: './accounts.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, FormsModule],
})
export class AccountsComponent implements OnInit {
  readonly auth = inject(AuthService);
  private readonly sync = inject(SyncService);
  private readonly route = inject(ActivatedRoute);

  readonly isAppleUser = computed(
    () => this.auth.currentUser()?.platform === 'apple_music',
  );

  // Platform statuses
  readonly appleMusicStatus = signal<PlatformStatus | null>(null);
  readonly lastFmStatus = signal<PlatformStatus | null>(null);
  readonly spotifyStatus = signal<PlatformStatus | null>(null);

  // Loading / action states
  readonly loadingStatuses = signal(true);
  readonly connectingLastFm = signal(false);
  readonly disconnectingLastFm = signal(false);
  readonly scrobbling = signal(false);
  readonly scrobbleResult = signal<number | null>(null);
  readonly error = signal<string | null>(null);
  readonly successMessage = signal<string | null>(null);

  ngOnInit(): void {
    this._checkQueryParams();
    this._loadStatuses();
  }

  // ── Apple Music ────────────────────────────────────────────────────────────

  appleMusicTokenInput = '';
  readonly savingAppleToken = signal(false);

  saveAppleMusicToken(): void {
    const token = this.appleMusicTokenInput.trim();
    if (!token) return;

    this.savingAppleToken.set(true);
    this.error.set(null);

    this.sync.storeAppleMusicUserToken(token).subscribe({
      next: () => {
        this.savingAppleToken.set(false);
        this.appleMusicTokenInput = '';
        this.successMessage.set('Apple Music connected.');
        this._loadAppleMusicStatus();
        setTimeout(() => this.successMessage.set(null), 4000);
      },
      error: (err) => {
        this.savingAppleToken.set(false);
        this.error.set(err?.error?.detail ?? 'Failed to save Apple Music token.');
      },
    });
  }

  // ── Spotify ────────────────────────────────────────────────────────────────

  spotifyTokenInput = '';
  readonly savingSpotifyToken = signal(false);
  readonly spotifyConnectedAs = signal<string | null>(null);

  connectSpotify(): void {
    this.sync.getSpotifyAuthUrl().subscribe({
      next: ({ authorization_url }) => {
        window.location.href = authorization_url;
      },
      error: (err) => {
        this.error.set(err?.error?.detail ?? 'Failed to get Spotify auth URL.');
      },
    });
  }

  saveSpotifyToken(): void {
    const token = this.spotifyTokenInput.trim();
    if (!token) return;

    this.savingSpotifyToken.set(true);
    this.error.set(null);

    this.sync.pasteSpotifyToken(token).subscribe({
      next: ({ display_name }) => {
        this.savingSpotifyToken.set(false);
        this.spotifyTokenInput = '';
        this.spotifyConnectedAs.set(display_name);
        this.successMessage.set(`Spotify connected as ${display_name}.`);
        this._loadSpotifyStatus();
        setTimeout(() => this.successMessage.set(null), 5000);
      },
      error: (err) => {
        this.savingSpotifyToken.set(false);
        this.error.set(err?.error?.detail ?? 'Failed to validate token.');
      },
    });
  }

  // ── Last.fm ────────────────────────────────────────────────────────────────

  lastFmTokenInput = '';
  readonly savingLastFmToken = signal(false);
  readonly lastFmAuthUrl = signal<string | null>(null);
  readonly loadingLastFmUrl = signal(false);

  openLastFmAuth(): void {
    this.loadingLastFmUrl.set(true);
    this.error.set(null);

    this.sync.getLastFmAuthUrl().subscribe({
      next: ({ auth_url }) => {
        this.loadingLastFmUrl.set(false);
        this.lastFmAuthUrl.set(auth_url);
        window.open(auth_url, '_blank', 'noopener');
      },
      error: (err) => {
        this.loadingLastFmUrl.set(false);
        this.error.set(err?.error?.detail ?? 'Failed to get Last.fm auth URL.');
      },
    });
  }

  saveLastFmToken(): void {
    const token = this.lastFmTokenInput.trim();
    if (!token) return;

    this.savingLastFmToken.set(true);
    this.error.set(null);

    this.sync.exchangeLastFmToken(token).subscribe({
      next: ({ username }) => {
        this.savingLastFmToken.set(false);
        this.lastFmTokenInput = '';
        this.successMessage.set(`Last.fm connected as ${username}.`);
        this._loadLastFmStatus();
        setTimeout(() => this.successMessage.set(null), 5000);
      },
      error: (err) => {
        this.savingLastFmToken.set(false);
        this.error.set(err?.error?.detail ?? 'Invalid token. Make sure you authorized and copied the correct value.');
      },
    });
  }

  connectLastFm(): void {
    this.openLastFmAuth();
  }

  disconnectLastFm(): void {
    this.disconnectingLastFm.set(true);
    this.sync.disconnectLastFm().subscribe({
      next: () => {
        this.disconnectingLastFm.set(false);
        this._loadLastFmStatus();
      },
      error: () => {
        this.disconnectingLastFm.set(false);
      },
    });
  }

  triggerScrobble(): void {
    this.scrobbling.set(true);
    this.scrobbleResult.set(null);
    this.sync.triggerLastFmScrobble().subscribe({
      next: ({ scrobbled }) => {
        this.scrobbling.set(false);
        this.scrobbleResult.set(scrobbled);
        setTimeout(() => this.scrobbleResult.set(null), 5000);
      },
      error: (err) => {
        this.scrobbling.set(false);
        this.error.set(err?.error?.detail ?? 'Scrobble failed.');
      },
    });
  }

  // ── Private helpers ────────────────────────────────────────────────────────

  private _checkQueryParams(): void {
    const params = this.route.snapshot.queryParamMap;
    if (params.get('lastfm_connected') === 'true') {
      this.successMessage.set('Last.fm connected successfully.');
      setTimeout(() => this.successMessage.set(null), 5000);
    }
    if (params.get('spotify_connected') === 'true') {
      this.successMessage.set('Spotify connected successfully.');
      setTimeout(() => this.successMessage.set(null), 5000);
    }
  }

  private _loadStatuses(): void {
    this.loadingStatuses.set(true);
    if (this.isAppleUser()) {
      this._loadAppleMusicStatus();
      this._loadLastFmStatus();
    } else {
      this._loadSpotifyStatus();
    }
    this.loadingStatuses.set(false);
  }

  private _loadAppleMusicStatus(): void {
    this.sync.getAppleMusicStatus().subscribe({
      next: (s) => this.appleMusicStatus.set(s),
    });
  }

  private _loadLastFmStatus(): void {
    this.sync.getLastFmStatus().subscribe({
      next: (s) => this.lastFmStatus.set(s),
    });
  }

  private _loadSpotifyStatus(): void {
    this.sync.getSpotifyStatus().subscribe({
      next: (s) => this.spotifyStatus.set(s),
    });
  }
}
