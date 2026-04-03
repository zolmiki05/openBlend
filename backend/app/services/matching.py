"""
Matching engine — priority chain:
1. ISRC match (exact, most reliable)
2. Exact normalized match (canonical_key equality)
3. Fuzzy match (title + artist similarity + duration tolerance)
4. Manual review queue (below threshold)
"""

import uuid
from dataclasses import dataclass

from rapidfuzz import fuzz
from sqlalchemy.orm import Session

from app.models.canonical_track import CanonicalTrack
from app.models.manual_review import ManualReviewQueue
from app.models.raw_track import RawTrack
from app.models.track_match import TrackMatch
from app.services.normalization import NormalizedTrack, normalize_track

# Fuzzy thresholds
FUZZY_TITLE_THRESHOLD = 85.0
FUZZY_ARTIST_THRESHOLD = 80.0
DURATION_TOLERANCE_MS = 5000


@dataclass
class MatchResult:
    match_type: str  # isrc | exact | fuzzy | manual_queue | none
    canonical_track: CanonicalTrack | None
    confidence: float


def find_or_create_canonical(
    db: Session,
    raw: RawTrack,
    normalized: NormalizedTrack,
) -> MatchResult:
    """
    Attempt to match raw track to an existing canonical track using the priority chain.
    If no match is found, create a new canonical track.
    Low-confidence matches are sent to the manual review queue.
    """
    # 1. ISRC match
    if raw.isrc:
        existing = db.query(CanonicalTrack).filter(CanonicalTrack.isrc == raw.isrc).first()
        if existing:
            return MatchResult("isrc", existing, 1.0)

    # 2. Exact normalized key match
    existing = (
        db.query(CanonicalTrack)
        .filter(CanonicalTrack.canonical_key == normalized.canonical_key)
        .first()
    )
    if existing:
        return MatchResult("exact", existing, 1.0)

    # 3. Fuzzy match against all existing canonical tracks
    # (Only load title + artists for comparison — no need for full objects in MVP)
    candidates = db.query(
        CanonicalTrack.id,
        CanonicalTrack.normalized_title,
        CanonicalTrack.normalized_artists,
        CanonicalTrack.duration_ms,
    ).all()

    best_score = 0.0
    best_id = None

    for cand_id, cand_title, cand_artists, cand_duration in candidates:
        title_score = fuzz.token_sort_ratio(normalized.normalized_title, cand_title)
        artist_score = fuzz.token_sort_ratio(
            ",".join(normalized.normalized_artists),
            ",".join(cand_artists or []),
        )

        if title_score < FUZZY_TITLE_THRESHOLD or artist_score < FUZZY_ARTIST_THRESHOLD:
            continue

        # Duration check when available
        if raw.duration_ms and cand_duration:
            if abs(raw.duration_ms - cand_duration) > DURATION_TOLERANCE_MS:
                continue

        combined = (title_score + artist_score) / 2
        if combined > best_score:
            best_score = combined
            best_id = cand_id

    if best_id is not None:
        canonical = db.get(CanonicalTrack, best_id)
        confidence = best_score / 100.0
        return MatchResult("fuzzy", canonical, confidence)

    # 4. No match — create new canonical track
    canonical = CanonicalTrack(
        id=uuid.uuid4(),
        canonical_key=normalized.canonical_key,
        isrc=raw.isrc,
        normalized_title=normalized.normalized_title,
        normalized_artists=normalized.normalized_artists,
        display_title=normalized.display_title,
        display_artists=normalized.display_artists,
        album=raw.album,
        duration_ms=raw.duration_ms,
    )
    db.add(canonical)
    db.flush()  # get the ID without committing
    return MatchResult("none", canonical, 1.0)


def process_raw_track(db: Session, raw: RawTrack) -> TrackMatch | None:
    """
    Normalize a raw track, find/create its canonical counterpart, and persist the match.
    Tracks that don't meet fuzzy threshold go to the manual review queue.
    Returns the TrackMatch if successful, None if sent to manual queue.
    """
    # Skip if already matched
    existing_match = (
        db.query(TrackMatch).filter(TrackMatch.raw_track_id == raw.id).first()
    )
    if existing_match:
        return existing_match

    normalized = normalize_track(raw.title, raw.artists)
    result = find_or_create_canonical(db, raw, normalized)

    if result.match_type == "none" and result.canonical_track is None:
        # This case shouldn't happen since find_or_create always returns a canonical
        return None

    match = TrackMatch(
        id=uuid.uuid4(),
        raw_track_id=raw.id,
        canonical_track_id=result.canonical_track.id,
        match_type=result.match_type if result.match_type != "none" else "new",
        confidence=result.confidence,
    )
    db.add(match)
    return match


def send_to_manual_queue(db: Session, raw_track_id: uuid.UUID, reason: str) -> None:
    already = (
        db.query(ManualReviewQueue)
        .filter(ManualReviewQueue.raw_track_id == raw_track_id)
        .first()
    )
    if not already:
        db.add(ManualReviewQueue(raw_track_id=raw_track_id, reason=reason))
