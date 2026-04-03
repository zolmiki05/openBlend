"""Data pipeline: sync_runs, raw_tracks, canonical_tracks, track_matches, manual_review_queue

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sync_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("triggered_by", sa.String(32), nullable=False, server_default="manual"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("metrics", postgresql.JSON(), nullable=True),
        sa.Column("raw_tracks_ingested", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("canonical_tracks_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("matched_tracks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("manual_review_count", sa.Integer(), nullable=False, server_default="0"),
    )

    op.create_table(
        "raw_tracks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sync_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("source_type", sa.String(64), nullable=False),
        sa.Column("source_weight", sa.Float(), nullable=False),
        sa.Column("platform_id", sa.String(128), nullable=False),
        sa.Column("isrc", sa.String(32), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("artists", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("album", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("audio_features", postgresql.JSON(), nullable=True),
        sa.Column("raw_data", postgresql.JSON(), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sync_run_id"], ["sync_runs.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_raw_tracks_user_id", "raw_tracks", ["user_id"])
    op.create_index("ix_raw_tracks_sync_run_id", "raw_tracks", ["sync_run_id"])
    op.create_index("ix_raw_tracks_isrc", "raw_tracks", ["isrc"])

    op.create_table(
        "canonical_tracks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("canonical_key", sa.Text(), nullable=False),
        sa.Column("isrc", sa.String(32), nullable=True),
        sa.Column("normalized_title", sa.Text(), nullable=False),
        sa.Column("normalized_artists", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("display_title", sa.Text(), nullable=False),
        sa.Column("display_artists", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("album", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_canonical_tracks_canonical_key", "canonical_tracks", ["canonical_key"])
    op.create_index("ix_canonical_tracks_isrc", "canonical_tracks", ["isrc"], unique=True)

    op.create_table(
        "track_matches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("raw_track_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("canonical_track_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("match_type", sa.String(32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["raw_track_id"], ["raw_tracks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["canonical_track_id"], ["canonical_tracks.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_track_matches_raw_track_id", "track_matches", ["raw_track_id"], unique=True)
    op.create_index("ix_track_matches_canonical_track_id", "track_matches", ["canonical_track_id"])

    op.create_table(
        "manual_review_queue",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("raw_track_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.String(64), nullable=True),
        sa.ForeignKeyConstraint(["raw_track_id"], ["raw_tracks.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_manual_review_queue_raw_track_id", "manual_review_queue", ["raw_track_id"])


def downgrade() -> None:
    op.drop_table("manual_review_queue")
    op.drop_table("track_matches")
    op.drop_table("canonical_tracks")
    op.drop_table("raw_tracks")
    op.drop_table("sync_runs")
