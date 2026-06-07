"""add_indexes_for_p1_3

Revision ID: 0002_add_indexes
Revises: 0001_init_baseline
Create Date: 2026-05-16

P1-3 关键索引：覆盖列表查询、去重查重、关联表 join。

注：idx_places_location_gist 在 baseline 里已以 idx_places_location 存在
（PostGIS GIST 索引），不重复建。
"""
from typing import Sequence, Union
from alembic import op


revision: str = "0002_add_indexes"
down_revision: Union[str, None] = "0001_init_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_places_status_credibility
        ON places (status, credibility_score DESC)
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_places_type ON places (type)")
    # 文档原本要求 uq_places_geo_source UNIQUE，但当前数据里 geo_source 是混合标签
    # （amap:村庄 / approximate_area / source_coord 等），存在天然重复，无法 UNIQUE。
    # 降级为普通索引保留 join/过滤的提速能力。
    # TODO(P2-1/P2-3): 去重逻辑整改后 geo_source 改为真正的原始 record id，再回收 UNIQUE。
    op.execute("CREATE INDEX IF NOT EXISTS idx_places_geo_source ON places (geo_source) WHERE geo_source IS NOT NULL")
    op.execute("CREATE INDEX IF NOT EXISTS idx_places_name ON places (name)")

    op.execute("CREATE INDEX IF NOT EXISTS idx_sources_place_id ON sources (place_id)")
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_sources_place_url
        ON sources (place_id, source_url) WHERE source_url IS NOT NULL
    """)

    op.execute("CREATE INDEX IF NOT EXISTS idx_feedbacks_place_id ON feedbacks (place_id)")
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_feedbacks_created_at
        ON feedbacks (created_at DESC)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_feedbacks_created_at")
    op.execute("DROP INDEX IF EXISTS idx_feedbacks_place_id")
    op.execute("DROP INDEX IF EXISTS uq_sources_place_url")
    op.execute("DROP INDEX IF EXISTS idx_sources_place_id")
    op.execute("DROP INDEX IF EXISTS idx_places_name")
    op.execute("DROP INDEX IF EXISTS idx_places_geo_source")
    op.execute("DROP INDEX IF EXISTS idx_places_type")
    op.execute("DROP INDEX IF EXISTS idx_places_status_credibility")
