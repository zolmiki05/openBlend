import { ChangeDetectionStrategy, Component, OnInit, inject } from '@angular/core';
import { Router } from '@angular/router';

@Component({
  selector: 'app-spotify-callback',
  templateUrl: './spotify-callback.component.html',
  styleUrl: './spotify-callback.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SpotifyCallbackComponent implements OnInit {
  private readonly router = inject(Router);

  ngOnInit(): void {
    this.router.navigate(['/accounts'], { replaceUrl: true });
  }

  retry(): void {
    this.router.navigate(['/accounts'], { replaceUrl: true });
  }
}
