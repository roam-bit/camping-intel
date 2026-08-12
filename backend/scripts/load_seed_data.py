#!/usr/bin/env python3
"""把随仓库分发的种子数据导入数据库（幂等）。

配套 export_seed_data.py。容器启动时自动跑，也可以手动跑。

幂等靠 `ON CONFLICT (id) DO NOTHING`：
    重复执行不会插重复数据，也不会覆盖你本地已经改过的点位。
    想强制重来：先 `--purge` 再跑一次。

用法：
    PYTHONPATH=backend python backend/scripts/load_seed_data.py
    PYTHONPATH=backend python backend/scripts/load_seed_data.py --purge   # 先删掉本种子集再导

设计上的一个刻意选择：任何一步失败都只打印警告并返回 0，不让整个进程挂掉。
    这个脚本跑在容器启动链路里（alembic → load_seed → uvicorn）。
    对新人来说「后端起不来」远比「点位少一点」严重得多，
    所以种子导入失败绝不能连累服务启动。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import warnings
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import MetaData, Table, text  # noqa: E402
from sqlalchemy.exc import SAWarning  # noqa: E402

# 反射时 SQLAlchemy 不认识 PostGIS 的 geography 类型，会打一条警告。
# 我们本来就不从反射结果里读这一列（下面用原生 SQL 重算），警告纯属噪音——
# 而这个脚本的输出是新人第一次启动时会盯着看的东西，不该出现看不懂的红字。
warnings.filterwarnings("ignore", category=SAWarning, message=".*geography.*")
from sqlalchemy.dialects.postgresql import insert as pg_insert  # noqa: E402

from app.database import engine  # noqa: E402

SEED_PATH = Path(__file__).resolve().parents[1] / "seed_data" / "places_seed.json"


def coerce_datetimes(row: dict, table: Table) -> dict:
    """JSON 里时间是 ISO 字符串，数据库要 datetime 对象。"""
    out = {}
    for k, v in row.items():
        col = table.columns.get(k)
        if col is None:
            continue  # 导出时的列在当前 schema 里没有了 —— 跳过，别让整批失败
        if isinstance(v, str) and str(col.type).upper().startswith("TIMESTAMP"):
            try:
                out[k] = datetime.fromisoformat(v)
                continue
            except ValueError:
                pass
        out[k] = v
    return out


async def main(purge: bool) -> int:
    if not SEED_PATH.exists():
        print(f"⚠ 没找到种子文件 {SEED_PATH}，跳过（不影响服务启动）")
        return 0

    payload = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    places = payload.get("places", [])
    sources = payload.get("sources", [])
    if not places:
        print("⚠ 种子文件里没有点位，跳过")
        return 0

    meta = MetaData()
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: meta.reflect(bind=c, only=["places", "sources"]))
        places_t = meta.tables["places"]
        sources_t = meta.tables["sources"]

        if purge:
            ids = [p["id"] for p in places]
            await conn.execute(text("DELETE FROM places WHERE id = ANY(:ids)"), {"ids": ids})
            print(f"  已清除 {len(ids)} 个种子点位（信源随外键级联删除）")

        place_rows = [coerce_datetimes(p, places_t) for p in places]
        source_rows = [coerce_datetimes(s, sources_t) for s in sources]

        before = (await conn.execute(text("SELECT count(*) FROM places"))).scalar()

        # 分批插入：单条 INSERT 塞 500+ 行会撞 asyncpg 的参数上限。
        for i in range(0, len(place_rows), 200):
            await conn.execute(
                pg_insert(places_t).values(place_rows[i : i + 200]).on_conflict_do_nothing(
                    index_elements=["id"]
                )
            )
        for i in range(0, len(source_rows), 200):
            await conn.execute(
                pg_insert(sources_t).values(source_rows[i : i + 200]).on_conflict_do_nothing(
                    index_elements=["id"]
                )
            )

        # location 是 PostGIS geography 列，导出时刻意跳过了（不好序列化且可推导），
        # 这里用经纬度重新算出来。没有它，按地理范围检索的查询会漏掉这些点。
        filled = await conn.execute(
            text(
                "UPDATE places SET location = ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography "
                "WHERE location IS NULL AND longitude IS NOT NULL AND latitude IS NOT NULL"
            )
        )
        after = (await conn.execute(text("SELECT count(*) FROM places"))).scalar()

    print(
        f"✓ 种子数据就绪：新增 {after - before} 个点位（文件内共 {len(places)} 个，"
        f"已存在的跳过）；补算坐标 {filled.rowcount} 个；当前库内共 {after} 个点位"
    )
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="导入随仓库分发的点位种子数据（幂等）")
    ap.add_argument("--purge", action="store_true", help="先删掉本种子集里的点位再导入")
    args = ap.parse_args()
    try:
        sys.exit(asyncio.run(main(args.purge)))
    except Exception as exc:  # noqa: BLE001
        # 见文件头说明：种子导入失败绝不能拖垮后端启动。
        print(f"⚠ 种子数据导入失败（{type(exc).__name__}: {exc}）——服务照常启动，只是点位会少一些")
        sys.exit(0)
