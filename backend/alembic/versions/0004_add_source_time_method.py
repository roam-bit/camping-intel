"""add_source_time_method_for_spec_007

Revision ID: 0004_add_source_time_method
Revises: 0003_add_topic_url_original
Create Date: 2026-05-20

spec-007 信源时间 HTML meta fallback：
- sources 表加 source_time_method 列，记录 source_time 是哪种途径解析的
- 枚举值：url_path / meta_og / meta_article_published / meta_publishdate /
          meta_pubdate / meta_itemprop_date / citation / snippet / NULL
- NULL = spec-007 之前的历史数据；回灌脚本据此识别要重跑的行
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_add_source_time_method"
down_revision: Union[str, None] = "0003_add_topic_url_original"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sources",
        sa.Column("source_time_method", sa.String(length=40), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sources", "source_time_method")
