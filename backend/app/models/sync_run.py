import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
    )  # pending | running | completed | failed | partial
    triggered_by: Mapped[str] = mapped_column(
        String(32), nullable=False, default="manual"
    )  # manual | scheduler
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    raw_tracks_ingested: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    canonical_tracks_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    matched_tracks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    manual_review_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
