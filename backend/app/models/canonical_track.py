import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CanonicalTrack(Base):
    __tablename__ = "canonical_tracks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Deduplication key: normalized_title + "||" + sorted_artists_joined
    canonical_key: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    isrc: Mapped[str | None] = mapped_column(String(32), nullable=True, unique=True, index=True)
    normalized_title: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_artists: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    display_title: Mapped[str] = mapped_column(Text, nullable=False)
    display_artists: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    album: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    album_art_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    matches: Mapped[list["TrackMatch"]] = relationship(
        "TrackMatch", back_populates="canonical_track"
    )
