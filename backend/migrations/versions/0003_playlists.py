"""Taste scores, rejected tracks, user settings, playlists

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "taste_scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("canonical_track_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("max_source_weight", sa.Float(), nullable=False),
        sa.Column("frequency", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_saved", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("playlist_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["canonical_track_id"], ["canonical_tracks.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "canonical_track_id", name="uq_taste_score_user_track"),
    )
    op.create_index("ix_taste_scores_user_id", "taste_scores", ["user_id"])
    op.create_index("ix_taste_scores_canonical_track_id", "taste_scores", ["canonical_track_id"])

    op.create_table(
        "rejected_tracks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("canonical_track_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rejected_by", sa.String(32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("rejected_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["canonical_track_id"], ["canonical_tracks.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_rejected_tracks_canonical_track_id", "rejected_tracks", ["canonical_track_id"])

    op.create_table(
        "user_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_playlist_id", sa.String(256), nullable=True),
        sa.Column("target_playlist_name", sa.String(256), nullable=False, server_default="OpenBlend"),
        sa.Column("sync_schedule", sa.String(32), nullable=False, server_default="weekly"),
        sa.Column("playlist_size", sa.Integer(), nullable=False, server_default="40"),
        sa.Column("allow_explicit", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("ratio_common", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("ratio_bridge_a_to_b", sa.Integer(), nullable=False, server_default="25"),
        sa.Column("ratio_bridge_b_to_a", sa.Integer(), nullable=False, server_default="25"),
        sa.Column("ratio_experimental", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("max_repair_loops", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", name="uq_user_settings_user_id"),
    )
    op.create_index("ix_user_settings_user_id", "user_settings", ["user_id"])

    op.create_table(
        "playlists",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("sync_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("platform_playlist_id", sa.String(256), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("track_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("publish_status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["sync_run_id"], ["sync_runs.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_playlists_sync_run_id", "playlists", ["sync_run_id"])

    op.create_table(
        "playlist_tracks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("playlist_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("canonical_track_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("platform_track_id", sa.String(256), nullable=False),
        sa.Column("bucket", sa.String(32), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("score_a", sa.Float(), nullable=False, server_default="0"),
        sa.Column("score_b", sa.Float(), nullable=False, server_default="0"),
        sa.Column("added_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["playlist_id"], ["playlists.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["canonical_track_id"], ["canonical_tracks.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_playlist_tracks_playlist_id", "playlist_tracks", ["playlist_id"])
    op.create_index("ix_playlist_tracks_canonical_track_id", "playlist_tracks", ["canonical_track_id"])


def downgrade() -> None:
    op.drop_table("playlist_tracks")
    op.drop_table("playlists")
    op.drop_table("user_settings")
    op.drop_table("rejected_tracks")
    op.drop_table("taste_scores")
