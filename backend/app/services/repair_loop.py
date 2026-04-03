"""
Repair loop (Stage 8).

If the count of fully validated tracks falls below the target playlist size,
triggers additional LLM passes with the gap info until the target is met
or max_repair_loops is exhausted.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.services.candidate_pool import Candidate
from app.services.llm_ranking import RankedTrack, rank_candidates


@dataclass
class RepairResult:
    ranked_tracks: list[RankedTrack]
    loops_used: int


def run_repair_loop(
    db: Session,
    candidates: list[Candidate],
    initial_ranked: list[RankedTrack],
    valid_ids: set[uuid.UUID],          # canonical IDs confirmed valid on both platforms
    invalid_ids: set[uuid.UUID],         # canonical IDs that failed validation
    target_counts: dict[str, int],
    user_a_id: uuid.UUID,
    user_b_id: uuid.UUID,
    max_loops: int,
    sync_run_id: uuid.UUID | None = None,
) -> RepairResult:
    """
    Iteratively request more tracks from the LLM to fill gaps left by validation failures.
    Returns the best set of RankedTrack objects after repair.
    """
    # Tracks already used (selected + invalid — never retry invalid ones)
    excluded: set[uuid.UUID] = {r.canonical_track_id for r in initial_ranked} | invalid_ids
    current_valid: list[RankedTrack] = [r for r in initial_ranked if r.canonical_track_id in valid_ids]
    loops_used = 0

    for loop_num in range(1, max_loops + 1):
        # Check per-bucket gap
        bucket_gap: dict[str, int] = {}
        for bucket, target in target_counts.items():
            filled = sum(1 for r in current_valid if r.bucket == bucket)
            gap = target - filled
            if gap > 0:
                bucket_gap[bucket] = gap

        if not bucket_gap:
            break  # target met

        # Request additional tracks for the gaps only
        additional = rank_candidates(
            db=db,
            candidates=candidates,
            target_counts=bucket_gap,
            user_a_id=user_a_id,
            user_b_id=user_b_id,
            sync_run_id=sync_run_id,
            stage=f"repair_{loop_num}",
            excluded_ids=excluded,
        )

        loops_used += 1

        if not additional:
            break  # nothing more available

        # The caller is responsible for validating `additional` and updating valid_ids
        # Here we just return the augmented ranked list for the caller to validate
        current_valid.extend(additional)
        excluded |= {r.canonical_track_id for r in additional}

        # Stop if we've reached the total target (caller validates after each loop)
        total_target = sum(target_counts.values())
        if len(current_valid) >= total_target:
            break

    return RepairResult(ranked_tracks=current_valid, loops_used=loops_used)
