#!/usr/bin/env python3
"""把库里「可展示」的点位 + 信源导出成随仓库分发的种子数据。

为什么要有这个脚本：
    这个项目的数据资产是一点点跑 AI 搜索沉淀下来的（每个点位都带公开信源）。
    只把代码给别人，对方 clone 下来是一个空库，产品等于没有内容。
    把这批数据打包进仓库，别人 `docker compose up` 就能看到真实的全国露营点位。

导出范围（刻意不是「全部」）：
    只导 status IN ('active', 'pending_review') 的点位。
    hidden 的那两千多条绝大多数是早期 OSM 批量导入的低质量数据，早已不展示，
    带上只会让仓库变大、让读数据的人以为产品有两千个能看的点。

用法：
    PYTHONPATH=backend backend/.venv/bin/python backend/scripts/export_seed_data.py
输出：
    backend/seed_data/places_seed.json
"""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from app.database import engine  # noqa: E402

OUT_PATH = Path(__file__).resolve().parents[1] / "seed_data" / "places_seed.json"
EXPORT_STATUSES = ("active", "pending_review")

# location 是 PostGIS geography 列，导出没意义也不好序列化——
# 导入时由 latitude/longitude 重新算出来，见 load_seed_data.py。
SKIP_COLUMNS = {"location"}


def to_jsonable(v):
    if isinstance(v, UUID):
        return str(v)
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v)
    return v


async def columns_of(conn, table: str) -> list[str]:
    rows = await conn.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name=:t ORDER BY ordinal_position"
        ),
        {"t": table},
    )
    # 反射列名而不是硬编码：以后加字段不用回来改这个脚本，也不会悄悄漏字段。
    return [r[0] for r in rows if r[0] not in SKIP_COLUMNS]


def render(payload: dict) -> str:
    """每条记录占一行的 JSON。

    为什么不用 `json.dumps(indent=1)`：那样 1141 条记录会摊成 4 万行，文件 1.1MB，
    撞上仓库的 large-file 护栏（1000KB）。
    为什么也不用完全紧凑的一行流：那样整个文件是一行，`git diff` 完全没法看——
    而「导出自己搜到的点位、看 diff」正是给学生设计的练习之一。

    折中成每条记录一行：体积接近最紧凑（~945KB），新增一个点位在 diff 里就是新增一行。
    仍然是合法 JSON，json.load() 直接读得了。
    """
    c = json.dumps
    opts = {"ensure_ascii": False, "separators": (",", ":")}
    lines = ["{"]
    for key in ("_comment", "exported_statuses", "place_count", "source_count"):
        lines.append(f" {c(key, **opts)}:{c(payload[key], **opts)},")
    for key in ("places", "sources"):
        lines.append(f" {c(key, **opts)}:[")
        items = payload[key]
        for i, item in enumerate(items):
            comma = "," if i < len(items) - 1 else ""
            lines.append(f"  {c(item, **opts)}{comma}")
        lines.append(" ]," if key == "places" else " ]")
    lines.append("}")
    return "\n".join(lines) + "\n"


async def main() -> None:
    async with engine.connect() as conn:
        place_cols = await columns_of(conn, "places")
        source_cols = await columns_of(conn, "sources")

        place_rows = (
            await conn.execute(
                text(
                    f"SELECT {', '.join(place_cols)} FROM places "
                    "WHERE status = ANY(:st) ORDER BY created_at"
                ),
                {"st": list(EXPORT_STATUSES)},
            )
        ).fetchall()

        place_ids = [r[place_cols.index("id")] for r in place_rows]

        source_rows = (
            await conn.execute(
                text(
                    f"SELECT {', '.join(source_cols)} FROM sources "
                    "WHERE place_id = ANY(:ids) ORDER BY created_at"
                ),
                {"ids": place_ids},
            )
        ).fetchall()

    places = [{c: to_jsonable(v) for c, v in zip(place_cols, row)} for row in place_rows]
    sources = [{c: to_jsonable(v) for c, v in zip(source_cols, row)} for row in source_rows]

    payload = {
        "_comment": (
            "随仓库分发的露营点位种子数据。由 backend/scripts/export_seed_data.py 生成，"
            "由 backend/scripts/load_seed_data.py 幂等导入。全部为公开网络信源整理所得。"
        ),
        "exported_statuses": list(EXPORT_STATUSES),
        "place_count": len(places),
        "source_count": len(sources),
        "places": places,
        "sources": sources,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(render(payload), encoding="utf-8")
    size_mb = OUT_PATH.stat().st_size / 1024 / 1024
    print(f"✓ 导出 {len(places)} 个点位 / {len(sources)} 条信源 → {OUT_PATH} （{size_mb:.1f} MB）")


if __name__ == "__main__":
    asyncio.run(main())
