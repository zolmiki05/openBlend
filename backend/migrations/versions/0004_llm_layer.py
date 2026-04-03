"""LLM layer: llm_logs, album_art_url on canonical_tracks, llm_explanation on playlist_tracks

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "llm_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("sync_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column("stage", sa.String(64), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("request", postgresql.JSON(), nullable=False),
        sa.Column("response", postgresql.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["sync_run_id"], ["sync_runs.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_llm_logs_sync_run_id", "llm_logs", ["sync_run_id"])

    op.add_column("canonical_tracks", sa.Column("album_art_url", sa.Text(), nullable=True))
    op.add_column("playlist_tracks", sa.Column("llm_explanation", sa.Text(), nullable=True))
    op.add_column("playlist_tracks", sa.Column("validation_status", sa.String(32), nullable=True))


def downgrade() -> None:
    op.drop_column("playlist_tracks", "validation_status")
    op.drop_column("playlist_tracks", "llm_explanation")
    op.drop_column("canonical_tracks", "album_art_url")
    op.drop_table("llm_logs")
