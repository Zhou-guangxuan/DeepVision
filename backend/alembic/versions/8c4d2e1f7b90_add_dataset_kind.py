"""给数据集增加 kind 字段（tabular / image）

Revision ID: 8c4d2e1f7b90
Revises: 3f1c9d7a2b64
Create Date: 2026-10-22

图像实验线使用内置合成数据集，需要区分它与 CSV 表格数据集。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8c4d2e1f7b90"
down_revision: str | None = "3f1c9d7a2b64"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "datasets",
        sa.Column(
            "kind",
            sa.String(length=16),
            nullable=False,
            server_default="tabular",
        ),
    )


def downgrade() -> None:
    op.drop_column("datasets", "kind")
