import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# Source weights as defined in the spec
SOURCE_WEIGHTS: dict[str, float] = {
    # Spotify
    "top_tracks_short": 1.0,
    "top_tracks_medium": 0.8,
    "top_tracks_long": 0.6,
    "recently_played": 0.9,
    "saved_songs": 0.7,
    "playlist": 0.5,
    # Apple Music
    "library_playlist": 0.5,
    "apple_recently_played": 0.9,
    "apple_recommendations": 0.3,
    # Last.fm
    "lastfm_loved": 0.9,        # Loved/hearted — treated as "saved" in scoring
    "lastfm_top_short": 1.0,    # Top tracks, 1-month window
    "lastfm_top_medium": 0.7,   # Top tracks, 6-month window
    "lastfm_top_long": 0.5,     # Top tracks, all-time
    "lastfm_recent": 0.6,       # Recently played on Last.fm
}


class RawTrack(Base):
    __tablename__ = "raw_tracks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sync_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sync_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    platform: Mapped[str] = mapped_column(String(32), nullable=False)  # spotify | apple_music
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_weight: Mapped[float] = mapped_column(Float, nullable=False)
    platform_id: Mapped[str] = mapped_column(String(128), nullable=False)  # platform's own track ID
    isrc: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    artists: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    album: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Spotify audio features (tempo, energy, valence, danceability, etc.)
    # Null for Apple Music tracks (no public audio features API)
    audio_features: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    raw_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    canonical_match: Mapped["TrackMatch | None"] = relationship(
        "TrackMatch", back_populates="raw_track", uselist=False
    )
