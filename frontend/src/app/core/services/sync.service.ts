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

export interface Track {
  canonical_track_id: string;
  display_title: string;
  display_artists: string[];
  album_art_url: string | null;
  bucket: string;
  position: number;
  score_a: number;
  score_b: number;
  platform_track_id: string;
  llm_explanation: string | null;
  validation_status: string | null;
}

export interface PlaylistData {
  id: string;
  platform: string;
  platform_playlist_id: string;
  name: string;
  track_count: number;
  publish_status: string;
  tracks: Track[];
}

export interface UserSettings {
  target_playlist_name: string;
  sync_schedule: string;
  playlist_size: number;
  allow_explicit: boolean;
  ratio_common: number;
  ratio_bridge_a_to_b: number;
  ratio_bridge_b_to_a: number;
  ratio_experimental: number;
  max_repair_loops: number;
  updated_at: string;
}

export interface ReviewItem {
  id: string;
  raw_track_id: string;
  title: string | null;
  artists: string[];
  platform: string | null;
  reason: string;
  status: string;
  confidence: number | null;
  created_at: string;
  reviewed_at: string | null;
}

export interface LLMLog {
  id: string;
  sync_run_id: string | null;
  model: string;
  stage: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  duration_ms: number;
  created_at: string;
}

export interface LLMLogDetail extends LLMLog {
  request: Record<string, unknown>;
  response: Record<string, unknown>;
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

  getPlaylist() {
    return this.http.get<PlaylistData[]>(`${this.api}/playlist/current`);
  }

  getSettings() {
    return this.http.get<UserSettings>(`${this.api}/settings`);
  }

  updateSettings(body: Partial<Omit<UserSettings, 'updated_at'>>) {
    return this.http.put<UserSettings>(`${this.api}/settings`, body);
  }

  getValidationQueue(status?: string) {
    const params = status ? `?status=${status}` : '';
    return this.http.get<ReviewItem[]>(`${this.api}/validation/queue${params}`);
  }

  reviewQueueItem(id: string, action: 'approved' | 'rejected') {
    return this.http.patch(`${this.api}/validation/queue/${id}?action=${action}`, {});
  }

  getLLMLogs(limit = 50) {
    return this.http.get<LLMLog[]>(`${this.api}/llm-audit/logs?limit=${limit}`);
  }

  getLLMLogDetail(id: string) {
    return this.http.get<LLMLogDetail>(`${this.api}/llm-audit/logs/${id}`);
  }
}
