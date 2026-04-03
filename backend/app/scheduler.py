"""
APScheduler background jobs.

Jobs:
  - check_scheduled_syncs   every 60 min — trigger pipeline for users whose schedule is due
  - refresh_expiring_tokens every 30 min — proactively refresh Spotify tokens near expiry
"""

import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler

log = logging.getLogger(__name__)

scheduler = BackgroundScheduler(timezone="UTC")

# How many hours between runs for each schedule label
_SCHEDULE_HOURS: dict[str, int] = {
    "daily": 24,
    "every_two_days": 48,
    "weekly": 168,
}


def _check_scheduled_syncs() -> None:
    """Trigger ingestion for every user whose scheduled interval has elapsed."""
    from app.database import SessionLocal
    from app.models.sync_run import SyncRun
    from app.models.user import User
    from app.models.user_settings import UserSettings
    from app.services.pipeline import run_ingestion_pipeline

    db = SessionLocal()
    try:
        users = db.query(User).all()
        now = datetime.now(timezone.utc)

        # Find the last completed run (any user — we run all or none for MVP)
        last_run: SyncRun | None = (
            db.query(SyncRun)
            .filter(SyncRun.status == "completed", SyncRun.completed_at.isnot(None))
            .order_by(SyncRun.completed_at.desc())
            .first()
        )

        due_users: list[User] = []
        for user in users:
            settings = (
                db.query(UserSettings)
                .filter(UserSettings.user_id == user.id)
                .first()
            )
            if not settings or settings.sync_schedule not in _SCHEDULE_HOURS:
                continue  # manual or unknown schedule

            interval = timedelta(hours=_SCHEDULE_HOURS[settings.sync_schedule])

            if last_run and last_run.completed_at:
                completed_at = last_run.completed_at
                if completed_at.tzinfo is None:
                    completed_at = completed_at.replace(tzinfo=timezone.utc)
                if now < completed_at + interval:
                    continue  # not yet due

            due_users.append(user)

        if not due_users:
            return

        log.info("Scheduler: running sync for %d user(s)", len(due_users))
        for user in due_users:
            try:
                run_ingestion_pipeline(db, user, triggered_by="scheduler")
                log.info("Scheduler: completed sync for user %s", user.username)
            except Exception:
                log.exception("Scheduler: sync failed for user %s", user.username)

    finally:
        db.close()


def _refresh_expiring_tokens() -> None:
    """Refresh Spotify tokens that expire within the next hour."""
    from app.database import SessionLocal
    from app.models.platform_token import PlatformToken
    from app.services.spotify import refresh_spotify_token

    db = SessionLocal()
    try:
        soon = datetime.now(timezone.utc) + timedelta(hours=1)
        expiring = (
            db.query(PlatformToken)
            .filter(
                PlatformToken.platform == "spotify",
                PlatformToken.token_expiry.isnot(None),
                PlatformToken.token_expiry < soon,
            )
            .all()
        )

        for token in expiring:
            try:
                refreshed = refresh_spotify_token(db, token)
                if refreshed:
                    log.info("Scheduler: refreshed Spotify token for user %s", token.user_id)
                else:
                    log.warning("Scheduler: failed to refresh Spotify token for user %s", token.user_id)
            except Exception:
                log.exception("Scheduler: error refreshing token for user %s", token.user_id)

    finally:
        db.close()


def start_scheduler() -> None:
    scheduler.add_job(
        _check_scheduled_syncs,
        trigger="interval",
        minutes=60,
        id="scheduled_syncs",
        replace_existing=True,
        misfire_grace_time=300,
    )
    scheduler.add_job(
        _refresh_expiring_tokens,
        trigger="interval",
        minutes=30,
        id="token_refresh",
        replace_existing=True,
        misfire_grace_time=120,
    )
    scheduler.start()
    log.info("APScheduler started (sync check: 60 min, token refresh: 30 min)")


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
        log.info("APScheduler stopped")
