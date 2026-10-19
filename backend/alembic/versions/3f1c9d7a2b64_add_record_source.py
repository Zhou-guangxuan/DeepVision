"""给训练记录增加来源字段

Revision ID: 3f1c9d7a2b64
Revises: 776eaa382327
Create Date: 2026-10-19

第一阶段工作台产生的记录 source = platform；
第三阶段教学实验室的训练记录 source = lab。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3f1c9d7a2b64"
down_revision: str | None = "776eaa382327"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "training_records",
        sa.Column(
            "source",
            sa.String(length=16),
            nullable=False,
            server_default="platform",
        ),
    )
    op.create_index(
        op.f("ix_training_records_source"),
        "training_records",
        ["source"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_training_records_source"), table_name="training_records"
    )
    op.drop_column("training_records", "source")
