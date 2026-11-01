"""Add release monitoring columns to watchlist_entries.

Revision ID: 002_watchlist_monitoring
Revises: 001_initial_schema
Create Date: 2026-11-01 13:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002_watchlist_monitoring"
down_revision: str | None = "001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "watchlist_entries",
        sa.Column("latest_version", sa.String(length=256), nullable=True),
    )
    op.add_column(
        "watchlist_entries",
        sa.Column("has_update", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "watchlist_entries",
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "watchlist_entries",
        sa.Column("diff_summary_json", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("watchlist_entries", "diff_summary_json")
    op.drop_column("watchlist_entries", "last_checked_at")
    op.drop_column("watchlist_entries", "has_update")
    op.drop_column("watchlist_entries", "latest_version")
