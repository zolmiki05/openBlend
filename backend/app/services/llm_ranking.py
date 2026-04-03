"""
LLM ranking service (Stage 6).

Sends the candidate pool to GLM-5 via the Z.ai OpenAI-compatible endpoint.
The model selects and ranks tracks from the provided list only — no new suggestions.
Returns structured JSON with selected track IDs, assigned buckets, and explanations.

Falls back to deterministic score-based ranking if the LLM call fails.
"""

import json
import time
import uuid
from dataclasses import dataclass

from openai import OpenAI
from sqlalchemy.orm import Session

from app.config import settings
from app.models.llm_log import LLMLog
from app.models.raw_track import RawTrack
from app.services.audio_profile import compute_style_overlap, compute_user_audio_profile
from app.services.candidate_pool import Candidate

SYSTEM_PROMPT = """You are a music curator selecting tracks for a shared cross-platform playlist.

RULES (strictly enforced):
1. Select ONLY tracks from the provided candidate list. Do NOT invent or suggest any track not in the list.
2. Return valid JSON only — no preamble, no markdown, no extra text.
3. Assign each selected track to exactly one bucket from the input.
4. Write explanations in English, 1–2 sentences, focused on why this track fits the shared playlist.

SELECTION GUIDELINES:
- "common": both users have strong taste signals — prioritize by combined_score descending.
- "bridge_a_to_b": Spotify user's tracks for the Apple Music user to discover. Prefer tracks where style_overlap_b is true.
- "bridge_b_to_a": Apple Music user's tracks for the Spotify user to discover. Prefer tracks where style_overlap_a is true.
- "experimental": low signal from both users — pick the most musically interesting or cohesive picks.
- Fill the requested slot counts per bucket as closely as possible.
- If a bucket has fewer candidates than requested slots, fill what is available."""

RESPONSE_SCHEMA = """{
  "selected_tracks": [
    {
      "id": "<uuid string from the candidate list>",
      "bucket": "<common|bridge_a_to_b|bridge_b_to_a|experimental>",
      "explanation": "<1-2 sentence explanation in English>"
    }
  ]
}"""


@dataclass
class RankedTrack:
    canonical_track_id: uuid.UUID
    bucket: str
    explanation: str
    score_a: float
    score_b: float


def _build_candidate_payload(
    candidates: list[Candidate],
    db: Session,
    user_a_id: uuid.UUID,
    user_b_id: uuid.UUID,
    excluded_ids: set[uuid.UUID] | None = None,
) -> list[dict]:
    profile_a = compute_user_audio_profile(db, user_a_id)
    profile_b = compute_user_audio_profile(db, user_b_id)

    payload = []
    for c in candidates:
        if excluded_ids and c.canonical_track_id in excluded_ids:
            continue

        # Get audio features from any raw track for this canonical
        raw = (
            db.query(RawTrack)
            .filter(
                RawTrack.audio_features.isnot(None),
            )
            .join(
                __import__("app.models.track_match", fromlist=["TrackMatch"]).TrackMatch,
                __import__("app.models.track_match", fromlist=["TrackMatch"]).TrackMatch.raw_track_id == RawTrack.id,
            )
            .filter(
                __import__("app.models.track_match", fromlist=["TrackMatch"]).TrackMatch.canonical_track_id == c.canonical_track_id
            )
            .first()
        )
        audio_features = raw.audio_features if raw else None

        overlap_b = compute_style_overlap(audio_features, profile_b)
        overlap_a = compute_style_overlap(audio_features, profile_a)

        payload.append({
            "id": str(c.canonical_track_id),
            "bucket": c.bucket,
            "score_a": round(c.score_a, 3),
            "score_b": round(c.score_b, 3),
            "combined_score": round(c.combined_score, 3),
            "style_overlap_b": overlap_b,
            "style_overlap_a": overlap_a,
        })

    return payload


def _call_llm(
    db: Session,
    sync_run_id: uuid.UUID | None,
    stage: str,
    messages: list[dict],
) -> dict | None:
    """Call GLM-5, log the result, return parsed JSON or None on failure."""
    client = OpenAI(
        api_key=settings.zai_api_key,
        base_url=settings.zai_base_url,
    )

    request_payload = {
        "model": settings.llm_model,
        "messages": messages,
        "thinking": {"type": "disabled"},
        "response_format": {"type": "json_object"},
        "temperature": 0.3,
        "max_tokens": 4096,
    }

    start = time.time()
    try:
        resp = client.chat.completions.create(**request_payload)
        duration_ms = int((time.time() - start) * 1000)

        content = resp.choices[0].message.content or "{}"
        usage = resp.usage

        log = LLMLog(
            sync_run_id=sync_run_id,
            model=settings.llm_model,
            stage=stage,
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            total_tokens=usage.total_tokens if usage else 0,
            duration_ms=duration_ms,
            request={"messages": messages},
            response={"content": content, "finish_reason": resp.choices[0].finish_reason},
        )
        db.add(log)
        db.commit()

        return json.loads(content)

    except Exception as exc:
        duration_ms = int((time.time() - start) * 1000)
        db.add(LLMLog(
            sync_run_id=sync_run_id,
            model=settings.llm_model,
            stage=stage,
            duration_ms=duration_ms,
            request={"messages": messages},
            response={"error": str(exc)},
        ))
        db.commit()
        return None


def _deterministic_fallback(
    candidates: list[Candidate],
    target_counts: dict[str, int],
    excluded_ids: set[uuid.UUID] | None = None,
) -> list[RankedTrack]:
    """Score-based selection used when LLM is unavailable."""
    by_bucket: dict[str, list[Candidate]] = {}
    for c in candidates:
        if excluded_ids and c.canonical_track_id in excluded_ids:
            continue
        by_bucket.setdefault(c.bucket, []).append(c)

    result: list[RankedTrack] = []
    for bucket, count in target_counts.items():
        bucket_candidates = sorted(
            by_bucket.get(bucket, []),
            key=lambda c: c.combined_score,
            reverse=True,
        )
        for c in bucket_candidates[:count]:
            result.append(RankedTrack(
                canonical_track_id=c.canonical_track_id,
                bucket=c.bucket,
                explanation="Selected by taste score (LLM unavailable).",
                score_a=c.score_a,
                score_b=c.score_b,
            ))
    return result


def rank_candidates(
    db: Session,
    candidates: list[Candidate],
    target_counts: dict[str, int],
    user_a_id: uuid.UUID,
    user_b_id: uuid.UUID,
    sync_run_id: uuid.UUID | None = None,
    stage: str = "ranking",
    excluded_ids: set[uuid.UUID] | None = None,
) -> list[RankedTrack]:
    """
    Ask GLM-5 to select and rank from the candidate pool.
    Falls back to deterministic ranking on any LLM failure.
    """
    # Build enriched candidate payload
    payload_items = _build_candidate_payload(
        candidates, db, user_a_id, user_b_id, excluded_ids
    )

    if not payload_items:
        return []

    user_message = json.dumps({
        "target_counts": target_counts,
        "response_format_schema": RESPONSE_SCHEMA,
        "candidates": payload_items,
    }, ensure_ascii=False)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    result_json = _call_llm(db, sync_run_id, stage, messages)

    if not result_json:
        return _deterministic_fallback(candidates, target_counts, excluded_ids)

    # Map IDs to Candidate objects for fast lookup
    id_to_candidate: dict[str, Candidate] = {
        str(c.canonical_track_id): c for c in candidates
    }

    ranked: list[RankedTrack] = []
    for item in result_json.get("selected_tracks", []):
        track_id = item.get("id")
        if not track_id or track_id not in id_to_candidate:
            continue  # model referenced a non-existent track — skip
        c = id_to_candidate[track_id]
        ranked.append(RankedTrack(
            canonical_track_id=c.canonical_track_id,
            bucket=item.get("bucket", c.bucket),
            explanation=item.get("explanation", ""),
            score_a=c.score_a,
            score_b=c.score_b,
        ))

    # If LLM returned too few tracks, pad with deterministic fallback
    selected_ids = {r.canonical_track_id for r in ranked}
    all_excluded = (excluded_ids or set()) | selected_ids
    total_selected = len(ranked)
    total_target = sum(target_counts.values())

    if total_selected < total_target * 0.7:
        # Less than 70% filled — use fallback for remaining
        remaining_counts = {
            bucket: max(0, count - sum(1 for r in ranked if r.bucket == bucket))
            for bucket, count in target_counts.items()
        }
        fallback = _deterministic_fallback(candidates, remaining_counts, all_excluded)
        ranked.extend(fallback)

    return ranked
