import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  inject,
  signal,
} from '@angular/core';
import { Router, ActivatedRoute } from '@angular/router';
import { LucideAngularModule, AlertCircle, Check, Copy } from 'lucide-angular';

@Component({
  selector: 'app-lastfm-callback',
  templateUrl: './lastfm-callback.component.html',
  styleUrl: './lastfm-callback.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [LucideAngularModule],
})
export class LastFmCallbackComponent implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);

  readonly token = signal<string | null>(null);
  readonly copied = signal(false);
  readonly hasError = signal(false);

  readonly AlertCircleIcon = AlertCircle;
  readonly CheckIcon = Check;
  readonly CopyIcon = Copy;

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
