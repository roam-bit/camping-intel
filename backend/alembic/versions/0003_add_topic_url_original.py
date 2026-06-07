"""add_topic_url_original_for_spec_006

Revision ID: 0003_add_topic_url_original
Revises: 0002_add_indexes
Create Date: 2026-05-20

spec-006 微头条话题页深抓 Phase 1：
- 命中场景：source_url 存单帖 permalink、topic_url_original 保留原话题页 URL（用于溯源）
- 未命中场景：topic_url_original 留 NULL
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003_add_topic_url_original"
down_revision: Union[str, None] = "0002_add_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "places",
        sa.Column("topic_url_original", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("places", "topic_url_original")
