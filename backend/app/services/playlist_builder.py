"""
Score-based playlist composer (Phase 3 — no LLM).

Selects tracks from the candidate pool, composes them according to bucket ratios,
and interleaves buckets for natural listening flow.
"""

from dataclasses import dataclass

from app.models.user_settings import UserSettings
from app.services.candidate_pool import Candidate

BUCKET_ORDER = ["common", "bridge_a_to_b", "bridge_b_to_a", "experimental"]


@dataclass
class PlaylistEntry:
    canonical_track_id: object  # uuid.UUID
    bucket: str
    position: int
    score_a: float
    score_b: float


def compose_playlist(
    candidates: list[Candidate],
    settings: UserSettings,
) -> list[PlaylistEntry]:
    """
    Select tracks from the candidate pool and interleave them across buckets.
    Returns an ordered list of PlaylistEntry objects.
    """
    size = settings.playlist_size
    ratios = {
        "common": settings.ratio_common / 100,
        "bridge_a_to_b": settings.ratio_bridge_a_to_b / 100,
        "bridge_b_to_a": settings.ratio_bridge_b_to_a / 100,
        "experimental": settings.ratio_experimental / 100,
    }

    # Target count per bucket
    targets: dict[str, int] = {
        bucket: max(1, round(size * ratio))
        for bucket, ratio in ratios.items()
    }
    # Adjust rounding so total == size
    diff = size - sum(targets.values())
    if diff != 0:
        targets["common"] += diff

    # Bucket the candidates
    by_bucket: dict[str, list[Candidate]] = {b: [] for b in BUCKET_ORDER}
    for c in candidates:
        if c.bucket in by_bucket:
            by_bucket[c.bucket].append(c)

    # Take top N per bucket (already sorted by combined_score desc from pool builder)
    selected: dict[str, list[Candidate]] = {
        bucket: by_bucket[bucket][: targets[bucket]]
        for bucket in BUCKET_ORDER
    }

    # Interleave: round-robin across buckets that still have tracks
    interleaved: list[Candidate] = []
    queues = {b: list(selected[b]) for b in BUCKET_ORDER}
    while any(queues[b] for b in BUCKET_ORDER):
        for bucket in BUCKET_ORDER:
            if queues[bucket]:
                interleaved.append(queues[bucket].pop(0))

    return [
        PlaylistEntry(
            canonical_track_id=c.canonical_track_id,
            bucket=c.bucket,
            position=i,
            score_a=c.score_a,
            score_b=c.score_b,
        )
        for i, c in enumerate(interleaved)
    ]
