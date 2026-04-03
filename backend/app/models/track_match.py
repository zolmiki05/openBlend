import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TrackMatch(Base):
    __tablename__ = "track_matches"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    raw_track_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("raw_tracks.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    canonical_track_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("canonical_tracks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    match_type: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # isrc | exact | fuzzy | manual
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    raw_track: Mapped["RawTrack"] = relationship("RawTrack", back_populates="canonical_match")
    canonical_track: Mapped["CanonicalTrack"] = relationship(
        "CanonicalTrack", back_populates="matches"
    )
