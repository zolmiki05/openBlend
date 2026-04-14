"""Last.fm: scrobble_log table + lastfm_playcount_bonus on taste_scores

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-04
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Track which Apple Music raw_tracks have already been scrobbled to Last.fm
    op.create_table(
        "lastfm_scrobble_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "raw_track_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("raw_tracks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "scrobbled_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_lastfm_scrobble_log_user_id", "lastfm_scrobble_log", ["user_id"])
    op.create_unique_constraint(
        "uq_lastfm_scrobble_raw_track", "lastfm_scrobble_log", ["raw_track_id"]
    )

    # Auditability: store the Last.fm play-count bonus that was applied to each taste score
    op.add_column(
        "taste_scores",
        sa.Column("lastfm_playcount_bonus", sa.Float(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("taste_scores", "lastfm_playcount_bonus")
    op.drop_table("lastfm_scrobble_log")
