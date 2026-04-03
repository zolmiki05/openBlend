import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Playlist(Base):
    __tablename__ = "playlists"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sync_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sync_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    platform: Mapped[str] = mapped_column(String(32), nullable=False)  # spotify | apple_music
    platform_playlist_id: Mapped[str] = mapped_column(String(256), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    track_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    publish_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
    )  # pending | published | failed
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    tracks: Mapped[list["PlaylistTrack"]] = relationship(
        "PlaylistTrack", back_populates="playlist", order_by="PlaylistTrack.position"
    )


class PlaylistTrack(Base):
    __tablename__ = "playlist_tracks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    playlist_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("playlists.id", ondelete="CASCADE"), nullable=False, index=True
    )
    canonical_track_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("canonical_tracks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    platform_track_id: Mapped[str] = mapped_column(String(256), nullable=False)
    bucket: Mapped[str] = mapped_column(String(32), nullable=False)  # common | bridge_a_to_b | bridge_b_to_a | experimental
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    score_a: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    score_b: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    llm_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    validation_status: Mapped[str | None] = mapped_column(String(32), nullable=True)  # valid_both | valid_spotify_only | valid_apple_only | not_found
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    playlist: Mapped["Playlist"] = relationship("Playlist", back_populates="tracks")
