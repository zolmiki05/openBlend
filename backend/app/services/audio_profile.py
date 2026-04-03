"""
Compute a user's audio feature profile from their top/recently-played raw tracks.
Used to pre-compute style_overlap_a / style_overlap_b for LLM candidates
— so the model never has to hallucinate these values.
"""

import math
import uuid

from sqlalchemy.orm import Session

from app.models.raw_track import RawTrack

# Only use high-signal sources for profile computation
HIGH_SIGNAL_SOURCES = {"top_tracks_short", "top_tracks_medium", "recently_played", "apple_recently_played"}
PROFILE_KEYS = ["tempo", "energy", "valence", "danceability"]
MIN_TRACKS_FOR_PROFILE = 5
OVERLAP_STD_MULTIPLIER = 1.2  # within 1.2 std deviations = overlap


def compute_user_audio_profile(db: Session, user_id: uuid.UUID) -> dict | None:
    """
    Returns {key_mean: float, key_std: float, ...} for each audio feature key,
    or None if not enough data.
    """
    tracks = (
        db.query(RawTrack)
        .filter(
            RawTrack.user_id == user_id,
            RawTrack.audio_features.isnot(None),
            RawTrack.source_type.in_(HIGH_SIGNAL_SOURCES),
        )
        .all()
    )

    if len(tracks) < MIN_TRACKS_FOR_PROFILE:
        return None

    profile: dict = {}
    for key in PROFILE_KEYS:
        vals = [t.audio_features[key] for t in tracks if t.audio_features and t.audio_features.get(key) is not None]
        if len(vals) < MIN_TRACKS_FOR_PROFILE:
            continue
        mean = sum(vals) / len(vals)
        variance = sum((v - mean) ** 2 for v in vals) / len(vals)
        std = math.sqrt(variance)
        profile[f"{key}_mean"] = mean
        profile[f"{key}_std"] = max(std, 0.05)  # floor to avoid zero-width window

    return profile if profile else None


def compute_style_overlap(
    audio_features: dict | None,
    target_profile: dict | None,
) -> bool | None:
    """
    Returns True if the candidate's audio features are within the target user's
    audio profile window (mean ± std * OVERLAP_STD_MULTIPLIER).
    Returns None if data is insufficient.
    """
    if not audio_features or not target_profile:
        return None

    checked = 0
    for key in PROFILE_KEYS:
        mean = target_profile.get(f"{key}_mean")
        std = target_profile.get(f"{key}_std")
        val = audio_features.get(key)
        if mean is None or std is None or val is None:
            continue
        checked += 1
        if abs(val - mean) > std * OVERLAP_STD_MULTIPLIER:
            return False

    return True if checked >= 2 else None
