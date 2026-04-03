"""
Candidate pool builder.

Assembles 80–150 candidate tracks from three origin buckets:
  - common:        both users have a positive score
  - bridge_a_to_b: Spotify user (A) has score > threshold; Apple Music user (B) score == 0
  - bridge_b_to_a: Apple Music user (B) has score > threshold; Spotify user (A) score == 0
  - experimental:  both users have low (but non-zero) scores — used as filler

Tracks in the RejectedTrack table are excluded.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.rejected_track import RejectedTrack
from app.models.taste_score import TasteScore
from app.models.user import User

BRIDGE_THRESHOLD = 0.30   # minimum score for a bridge track
COMMON_THRESHOLD = 0.01   # any positive score counts as "heard"
EXPERIMENTAL_MAX = 0.30   # both users below this → experimental
POOL_TARGET = 120          # target pool size
POOL_MIN = 80


@dataclass
class Candidate:
    canonical_track_id: uuid.UUID
    score_a: float
    score_b: float
    bucket: str  # common | bridge_a_to_b | bridge_b_to_a | experimental
    combined_score: float


def build_candidate_pool(
    db: Session,
    user_a: User,  # Spotify user
    user_b: User,  # Apple Music user
) -> list[Candidate]:
    """Return a list of Candidate objects sorted by combined_score descending."""

    # Rejected canonical IDs — exclude from pool
    rejected_ids: set[uuid.UUID] = {
        row.canonical_track_id
        for row in db.query(RejectedTrack.canonical_track_id).all()
    }

    # Load all scores for both users
    scores_a: dict[uuid.UUID, float] = {
        row.canonical_track_id: row.score
        for row in db.query(TasteScore).filter(TasteScore.user_id == user_a.id).all()
    }
    scores_b: dict[uuid.UUID, float] = {
        row.canonical_track_id: row.score
        for row in db.query(TasteScore).filter(TasteScore.user_id == user_b.id).all()
    }

    all_ids = set(scores_a) | set(scores_b)
    candidates: list[Candidate] = []

    for cid in all_ids:
        if cid in rejected_ids:
            continue

        sa = scores_a.get(cid, 0.0)
        sb = scores_b.get(cid, 0.0)

        if sa > COMMON_THRESHOLD and sb > COMMON_THRESHOLD:
            bucket = "common"
            combined = sa + sb
        elif sa >= BRIDGE_THRESHOLD and sb == 0.0:
            bucket = "bridge_a_to_b"
            combined = sa
        elif sb >= BRIDGE_THRESHOLD and sa == 0.0:
            bucket = "bridge_b_to_a"
            combined = sb
        elif sa > 0.0 and sb > 0.0 and sa < EXPERIMENTAL_MAX and sb < EXPERIMENTAL_MAX:
            bucket = "experimental"
            combined = (sa + sb) / 2
        else:
            continue  # doesn't qualify for any bucket

        candidates.append(Candidate(
            canonical_track_id=cid,
            score_a=sa,
            score_b=sb,
            bucket=bucket,
            combined_score=combined,
        ))

    # Sort each bucket by combined_score descending, then cap per bucket
    by_bucket: dict[str, list[Candidate]] = {
        "common": [],
        "bridge_a_to_b": [],
        "bridge_b_to_a": [],
        "experimental": [],
    }
    for c in candidates:
        by_bucket[c.bucket].append(c)

    for bucket_list in by_bucket.values():
        bucket_list.sort(key=lambda c: c.combined_score, reverse=True)

    # Take top candidates per bucket — proportional to POOL_TARGET
    pool: list[Candidate] = []
    caps = {
        "common": 40,
        "bridge_a_to_b": 30,
        "bridge_b_to_a": 30,
        "experimental": 20,
    }
    for bucket, cap in caps.items():
        pool.extend(by_bucket[bucket][:cap])

    return sorted(pool, key=lambda c: c.combined_score, reverse=True)
