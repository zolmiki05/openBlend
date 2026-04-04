import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { Router, ActivatedRoute } from '@angular/router';
import { SyncService } from '../../core/services/sync.service';

@Component({
  selector: 'app-spotify-callback',
  templateUrl: './spotify-callback.component.html',
  styleUrl: './spotify-callback.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SpotifyCallbackComponent implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly sync = inject(SyncService);

  readonly status = signal<'loading' | 'error'>('loading');
  readonly errorMessage = signal('');

  ngOnInit(): void {
    const params = this.route.snapshot.queryParamMap;
    const error = params.get('error');
    const code = params.get('code');
    const state = params.get('state');

    if (error) {
      this.status.set('error');
      this.errorMessage.set(`Spotify returned an error: ${error}`);
      return;
    }

    if (!code || !state) {
      this.status.set('error');
      this.errorMessage.set('Missing authorization code or state parameter.');
      return;
    }

    this.sync.exchangeSpotifyCode(code, state).subscribe({
      next: () => {
        this.router.navigate(['/settings'], {
          queryParams: { spotify_connected: 'true' },
          replaceUrl: true,
        });
      },
      error: (err) => {
        this.status.set('error');
        this.errorMessage.set(err?.error?.detail ?? 'Token exchange failed. Please try again.');
      },
    });
  }

  retry(): void {
    this.router.navigate(['/settings'], { replaceUrl: true });
  }
}
