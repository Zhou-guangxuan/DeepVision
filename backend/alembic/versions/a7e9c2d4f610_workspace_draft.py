"""工作台草稿表

Revision ID: a7e9c2d4f610
Revises: 8c4d2e1f7b90
Create Date: 2026-10-22

同一账号在多设备上恢复画布拓扑。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a7e9c2d4f610"
down_revision: str | None = "8c4d2e1f7b90"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workspace_drafts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("graph", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index(
        op.f("ix_workspace_drafts_user_id"),
        "workspace_drafts",
        ["user_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_workspace_drafts_user_id"), table_name="workspace_drafts"
    )
    op.drop_table("workspace_drafts")
