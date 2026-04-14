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
  username?: string;
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

export interface TasteScoreItem {
  canonical_track_id: string;
  display_title: string;
  display_artists: string[];
  album: string | null;
  album_art_url: string | null;
  score: number;
  max_source_weight: number;
  frequency: number;
  is_saved: boolean;
  playlist_count: number;
  lastfm_playcount_bonus: number;
  platforms: string[];
  source_types: string[];
  computed_at: string;
}

export interface TasteProfileSummary {
  total_scored_tracks: number;
  avg_score: number;
  max_score: number;
  saved_tracks: number;
  lastfm_boosted_tracks: number;
  platform_breakdown: Record<string, number>;
  source_type_breakdown: Record<string, number>;
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

  rejectTrack(canonicalTrackId: string, reason = 'user_rejected') {
    return this.http.post(`${this.api}/rejected-tracks`, { canonical_track_id: canonicalTrackId, reason });
  }

  exchangeSpotifyCode(code: string, state: string) {
    return this.http.post<{ connected: boolean }>(`${this.api}/auth/spotify/exchange`, { code, state });
  }

  getSpotifyAuthUrl() {
    return this.http.get<{ authorization_url: string }>(`${this.api}/auth/spotify/authorize`);
  }

  pasteSpotifyToken(access_token: string) {
    return this.http.post<{ connected: boolean; display_name: string }>(
      `${this.api}/auth/spotify/paste-token`,
      { access_token },
    );
  }

  // ── Taste Profile ──────────────────────────────────────────────────────────

  getTasteScores(limit = 100, sortBy: 'score' | 'frequency' | 'lastfm' = 'score') {
    return this.http.get<TasteScoreItem[]>(
      `${this.api}/taste-profile/scores?limit=${limit}&sort_by=${sortBy}`,
    );
  }

  refreshTasteScores() {
    return this.http.post<{ recomputed: number }>(`${this.api}/taste-profile/refresh`, {});
  }

  getTasteProfileSummary() {
    return this.http.get<TasteProfileSummary>(`${this.api}/taste-profile/summary`);
  }

  // ── Apple Music ────────────────────────────────────────────────────────────

  getAppleMusicDeveloperToken() {
    return this.http.get<{ developer_token: string }>(`${this.api}/auth/apple-music/developer-token`);
  }

  storeAppleMusicUserToken(music_user_token: string) {
    return this.http.post(`${this.api}/auth/apple-music/user-token`, { music_user_token });
  }

  // ── Last.fm ────────────────────────────────────────────────────────────────

  getLastFmAuthUrl() {
    return this.http.get<{ auth_url: string }>(`${this.api}/auth/lastfm/auth-url`);
  }

  exchangeLastFmToken(token: string) {
    return this.http.post<{ message: string; username: string }>(
      `${this.api}/auth/lastfm/callback`,
      { token },
    );
  }

  getLastFmStatus() {
    return this.http.get<PlatformStatus>(`${this.api}/auth/lastfm/status`);
  }

  disconnectLastFm() {
    return this.http.delete(`${this.api}/auth/lastfm/disconnect`);
  }

  triggerLastFmScrobble() {
    return this.http.post<{ scrobbled: number }>(`${this.api}/auth/lastfm/scrobble`, {});
  }
}
