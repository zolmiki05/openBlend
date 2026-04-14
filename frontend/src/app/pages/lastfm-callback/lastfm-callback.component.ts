import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  inject,
  signal,
} from '@angular/core';
import { Router, ActivatedRoute } from '@angular/router';

@Component({
  selector: 'app-lastfm-callback',
  templateUrl: './lastfm-callback.component.html',
  styleUrl: './lastfm-callback.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class LastFmCallbackComponent implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);

  readonly token = signal<string | null>(null);
  readonly copied = signal(false);
  readonly hasError = signal(false);

  ngOnInit(): void {
    const t = this.route.snapshot.queryParamMap.get('token');
    if (!t) {
      this.hasError.set(true);
    } else {
      this.token.set(t);
    }
  }

  copyToken(): void {
    const t = this.token();
    if (!t) return;
    navigator.clipboard.writeText(t).then(() => {
      this.copied.set(true);
      setTimeout(() => this.copied.set(false), 2500);
    });
  }

  goToAccounts(): void {
    this.router.navigate(['/accounts'], { replaceUrl: true });
  }
}
