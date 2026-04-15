import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { LucideAngularModule } from 'lucide-angular';
import {
  LayoutDashboard,
  Disc3,
  ClipboardList,
  Bot,
  BarChart2,
  Cable,
  Settings2,
  LogOut,
} from 'lucide-angular';
import { AuthService } from '../../core/services/auth.service';

@Component({
  selector: 'app-shell',
  imports: [RouterOutlet, RouterLink, RouterLinkActive, LucideAngularModule],
  templateUrl: './shell.component.html',
  styleUrl: './shell.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ShellComponent {
  readonly auth = inject(AuthService);

  readonly LayoutDashboardIcon = LayoutDashboard;
  readonly Disc3Icon = Disc3;
  readonly ClipboardListIcon = ClipboardList;
  readonly BotIcon = Bot;
  readonly BarChart2Icon = BarChart2;
  readonly CableIcon = Cable;
  readonly Settings2Icon = Settings2;
  readonly LogOutIcon = LogOut;
}
