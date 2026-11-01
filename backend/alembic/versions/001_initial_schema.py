"""Initial schema for package integrity persistence.

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-11-01 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. packages
    op.create_table(
        "packages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ecosystem", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ecosystem", "name", name="uq_packages_ecosystem_name"),
    )
    op.create_index("ix_packages_ecosystem_name", "packages", ["ecosystem", "name"])

    # 2. package_versions
    op.create_table(
        "package_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("package_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.String(length=256), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("manifest", sa.JSON(), nullable=True),
        sa.Column("source_repo_url", sa.String(length=512), nullable=True),
        sa.Column("source_commit", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["package_id"], ["packages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("package_id", "version", name="uq_package_versions_package_version"),
    )
    op.create_index("ix_package_versions_version", "package_versions", ["package_id", "version"])

    # 3. scans
    op.create_table(
        "scans",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("package_version_id", sa.Integer(), nullable=True),
        sa.Column("ecosystem", sa.String(length=16), nullable=False),
        sa.Column("package_name", sa.String(length=256), nullable=False),
        sa.Column("version", sa.String(length=256), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("stage", sa.String(length=64), nullable=False),
        sa.Column("progress_percent", sa.Integer(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["package_version_id"], ["package_versions.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scans_pkg_ver", "scans", ["ecosystem", "package_name", "version"])
    op.create_index("ix_scans_created_at", "scans", ["created_at"])

    # 4. scan_reports
    op.create_table(
        "scan_reports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("scan_id", sa.UUID(), nullable=False),
        sa.Column("risk_score", sa.Integer(), nullable=True),
        sa.Column("risk_level", sa.String(length=32), nullable=True),
        sa.Column("confidence", sa.String(length=32), nullable=True),
        sa.Column("completeness", sa.String(length=32), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("source_match_json", sa.JSON(), nullable=True),
        sa.Column("report_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["scan_id"], ["scans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scan_id"),
    )

    # 5. file_comparisons
    op.create_table(
        "file_comparisons",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("scan_id", sa.UUID(), nullable=False),
        sa.Column("path", sa.String(length=1024), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("diff_status", sa.String(length=32), nullable=False),
        sa.Column("classification", sa.String(length=64), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("added_lines", sa.Integer(), nullable=True),
        sa.Column("removed_lines", sa.Integer(), nullable=True),
        sa.Column("unified_diff", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["scan_id"], ["scans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_file_comparisons_scan_id", "file_comparisons", ["scan_id"])
    op.create_index("ix_file_comparisons_scan_path", "file_comparisons", ["scan_id", "path"])

    # 6. security_findings
    op.create_table(
        "security_findings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("scan_id", sa.UUID(), nullable=False),
        sa.Column("rule_id", sa.String(length=64), nullable=False),
        sa.Column("path", sa.String(length=1024), nullable=False),
        sa.Column("line", sa.Integer(), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.String(length=32), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("recommended_action", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["scan_id"], ["scans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_security_findings_scan_id", "security_findings", ["scan_id"])
    op.create_index("ix_security_findings_rule_id", "security_findings", ["rule_id"])

    # 7. provenance_results
    op.create_table(
        "provenance_results",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("scan_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("sigstore_verified", sa.Boolean(), nullable=False),
        sa.Column("build_signer", sa.String(length=512), nullable=True),
        sa.Column("build_runner", sa.String(length=512), nullable=True),
        sa.Column("commit_matched", sa.Boolean(), nullable=False),
        sa.Column("repository_matched", sa.Boolean(), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=True),
        sa.Column("claims", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["scan_id"], ["scans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scan_id"),
    )

    # 8. ai_explanations
    op.create_table(
        "ai_explanations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("scan_id", sa.UUID(), nullable=False),
        sa.Column("finding_rule_id", sa.String(length=64), nullable=True),
        sa.Column("file_path", sa.String(length=1024), nullable=True),
        sa.Column("assessment", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("false_positive_likelihood", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["scan_id"], ["scans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_explanations_scan_id", "ai_explanations", ["scan_id"])

    # 9. watchlist_entries
    op.create_table(
        "watchlist_entries",
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("ecosystem", sa.String(length=16), nullable=False),
        sa.Column("package_name", sa.String(length=256), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("last_scanned_version", sa.String(length=256), nullable=True),
        sa.Column("last_risk_score", sa.Integer(), nullable=True),
        sa.Column("last_risk_level", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ecosystem", "package_name", name="uq_watchlist_ecosystem_package"),
    )
    op.create_index(
        "ix_watchlist_ecosystem_package",
        "watchlist_entries",
        ["ecosystem", "package_name"],
    )


def downgrade() -> None:
    op.drop_table("watchlist_entries")
    op.drop_table("ai_explanations")
    op.drop_table("provenance_results")
    op.drop_table("security_findings")
    op.drop_table("file_comparisons")
    op.drop_table("scan_reports")
    op.drop_table("scans")
    op.drop_table("package_versions")
    op.drop_table("packages")
