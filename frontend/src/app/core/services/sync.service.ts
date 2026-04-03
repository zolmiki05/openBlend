import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { environment } from '../../../environments/environment';

export interface SyncRun {
  id: string;
  status: string;
  triggered_by: string;
  raw_tracks_ingested: number;
  matched_tracks: number;
  manual_review_count: number;
  canonical_tracks_total: number;
  error: string | null;
  metrics: Record<string, unknown> | null;
}

export interface PlatformStatus {
  platform: string;
  connected: boolean;
  token_expiry: string | null;
}

export interface PlaylistStats {
  total: number;
  platform?: string;
  published_at?: string;
  buckets: Record<string, number>;
}

@Injectable({ providedIn: 'root' })
export class SyncService {
  private readonly http = inject(HttpClient);
  private readonly api = environment.apiUrl;

  triggerSync() {
    return this.http.post<SyncRun>(`${this.api}/pipeline/ingest`, {});
  }

  getRuns(limit = 5) {
    return this.http.get<SyncRun[]>(`${this.api}/pipeline/runs?limit=${limit}`);
  }

  getSpotifyStatus() {
    return this.http.get<PlatformStatus>(`${this.api}/auth/spotify/status`);
  }

  getAppleMusicStatus() {
    return this.http.get<PlatformStatus>(`${this.api}/auth/apple-music/status`);
  }

  getPlaylistStats() {
    return this.http.get<PlaylistStats>(`${this.api}/playlist/stats`);
  }
}
