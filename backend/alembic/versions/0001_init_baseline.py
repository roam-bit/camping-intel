"""init_places_sources_feedbacks

Revision ID: 0001_init_baseline
Revises:
Create Date: 2026-05-16

POC 完工后的 schema baseline，内容基于 dev 库 pg_dump --schema-only 还原。

- 新部署/CI：alembic upgrade head 从 0 建库
- 老 dev 库（已存在表 + 数据）：alembic stamp 0001_init_baseline 标记已 applied，不实际跑 SQL
"""
from typing import Sequence, Union
from alembic import op


revision: str = "0001_init_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    op.execute("""
        CREATE TABLE IF NOT EXISTS places (
            id uuid NOT NULL,
            name character varying(255) NOT NULL,
            type character varying(50) NOT NULL,
            latitude double precision NOT NULL,
            longitude double precision NOT NULL,
            location geography(Point, 4326),
            address text,
            city character varying(100),
            district character varying(100),
            province character varying(100) NOT NULL,
            location_confidence character varying(20) NOT NULL,
            geo_source character varying(50),
            ai_rating double precision,
            credibility_score integer NOT NULL,
            heat_level character varying(20),
            recommendation character varying(20) NOT NULL,
            source_count integer NOT NULL,
            mention_count integer,
            price_clues character varying[],
            overnight_clues character varying[],
            toilet_status character varying(20),
            water_status character varying(20),
            electricity_status character varying(20),
            height_limit character varying(50),
            vehicle_fit character varying[],
            risk_tags character varying[],
            positive_summary text,
            negative_summary text,
            ai_summary text,
            source_summary text,
            last_verified_at timestamp with time zone,
            cached_from_query text,
            created_at timestamp with time zone NOT NULL,
            updated_at timestamp with time zone NOT NULL,
            data_origin character varying(50),
            status character varying(20) NOT NULL,
            CONSTRAINT places_pkey PRIMARY KEY (id)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS sources (
            id uuid NOT NULL,
            place_id uuid NOT NULL,
            source_type character varying(50) NOT NULL,
            source_url text,
            domain character varying(255),
            title text,
            snippet text,
            source_time timestamp with time zone,
            extracted_info jsonb,
            reliability_score integer NOT NULL,
            created_at timestamp with time zone NOT NULL,
            CONSTRAINT sources_pkey PRIMARY KEY (id),
            CONSTRAINT sources_place_id_fkey FOREIGN KEY (place_id)
                REFERENCES places(id) ON DELETE CASCADE
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS feedbacks (
            id uuid NOT NULL,
            place_id uuid NOT NULL,
            user_id character varying(100),
            can_park_now character varying(20) NOT NULL,
            can_overnight character varying(20) NOT NULL,
            price_status character varying(20) NOT NULL,
            toilet_available character varying(20) NOT NULL,
            was_warned boolean NOT NULL,
            vehicle_type character varying(50),
            comment text,
            created_at timestamp with time zone NOT NULL,
            CONSTRAINT feedbacks_pkey PRIMARY KEY (id),
            CONSTRAINT feedbacks_place_id_fkey FOREIGN KEY (place_id)
                REFERENCES places(id) ON DELETE CASCADE
        )
    """)

    op.execute("CREATE INDEX IF NOT EXISTS idx_places_location ON places USING GIST (location)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS feedbacks CASCADE")
    op.execute("DROP TABLE IF EXISTS sources CASCADE")
    op.execute("DROP TABLE IF EXISTS places CASCADE")
