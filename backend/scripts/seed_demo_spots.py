"""演示数据种子脚本：为面试演示场景预置杭州周边点位（秒出结果、不等 AI）。

背景：DB-first 召回策略要求关键词命中 ≥ ceil(limit×0.5)=6 条才跳过 AI 兜底直接返回。
线上演示时 DB 是空的 → 每次搜索都走 AI 联网（30-90 秒）且可能 0 结果，现场风险极高。
本脚本给三个演示 query 各种 ≥6 个点位，保证点开示例芯片秒出地图 marker：
  - 「杭州周边免费露营地」 → 杭州近郊簇 + 莫干山簇（文案都含「杭州周边」）
  - 「莫干山附近营地」     → 莫干山簇（文案含「莫干山」）
  - 「千岛湖驻车点」       → 千岛湖簇（文案含「千岛湖」）

数据特征：
  - data_origin='demo_seed'，一条 SQL 可干净删除（与正式数据可插拔隔离）
  - 信源 URL 用平台「真实搜索结果页」链接（小红书/知乎/马蜂窝搜索页）——
    面试演示点击可真实跳转到相关内容，不是 404 假链接
  - source_time 在最近 60 天内随机 → 不会被前端「近一年」时间筛选剔除
  - location_confidence='high' → 不会被 API 层脏数据过滤剔除

用法：
    cd backend
    <venv>/bin/python scripts/seed_demo_spots.py            # 写入（幂等：先删旧 demo_seed 再插）
    <venv>/bin/python scripts/seed_demo_spots.py --remove   # 只删除全部 demo_seed 数据
"""
from __future__ import annotations

import argparse
import asyncio
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from geoalchemy2 import WKTElement  # noqa: E402
from sqlalchemy import delete, select  # noqa: E402

from app.database import async_session  # noqa: E402
from app.models.place import Place  # noqa: E402
from app.models.source import Source  # noqa: E402

DATA_ORIGIN = "demo_seed"
RNG = random.Random(20260612)  # 固定种子：每次跑出的数据一致，便于截图对比/回归


def _search_url(platform: str, keyword: str) -> tuple[str, str, str]:
    """返回 (url, domain, source_type)。用平台真实搜索页，演示点击可跳转到真实相关内容。"""
    k = quote(keyword)
    if platform == "xhs":
        return (f"https://www.xiaohongshu.com/search_result?keyword={k}", "xiaohongshu.com", "小红书")
    if platform == "zhihu":
        return (f"https://www.zhihu.com/search?type=content&q={k}", "zhihu.com", "知乎")
    if platform == "mafengwo":
        return (f"https://www.mafengwo.cn/search/q.php?q={k}", "mafengwo.cn", "马蜂窝")
    return (f"https://www.bing.com/search?q={k}", "bing.com", "网页")


# (name, type, lat, lon, district, summary, toilet, water, elec, rating)
# summary 必须含演示 query 的地名 token（杭州周边 / 莫干山 / 千岛湖）——DB 关键词召回靠它
CLUSTERS: dict[str, list[tuple]] = {
    "hangzhou": [
        ("青山湖环湖驻车点", "驻车点", 30.2490, 119.7360, "临安区",
         "杭州周边热门免费驻车点：环湖北线多处平整碎石带，夜间安静可过夜，距公厕约 300 米，适合床车短住。",
         "有", "有", "无", 4.3),
        ("径山寺停车场过夜点", "驻车点", 30.3740, 119.8680, "余杭区",
         "杭州周边驻车选择：寺院外围停车场夜间不清场，海拔较高夏季凉快，免费停放，早课钟声较早。",
         "有", "无", "无", 4.0),
        ("富春江畔滩地营地", "营地", 29.9940, 119.6720, "富阳区",
         "杭州周边免费露营地：富春江边卵石滩可搭帐篷天幕，傍晚江景视野极佳，丰水期注意水位变化。",
         "无", "有", "无", 4.5),
        ("西径山森林公园草坪营位", "营地", 30.2010, 119.8520, "临安区",
         "杭州周边露营草坪：公园外围开放草坪可免费搭帐，树荫多适合亲子，周末需早到占位。",
         "有", "有", "无", 4.2),
        ("湘湖越王城山停车场", "驻车点", 30.1410, 120.1850, "萧山区",
         "杭州周边市区近郊驻车点：景区停车场夜间免费时段可停，湖边步道晨跑方便，节假日人多。",
         "有", "有", "有", 3.9),
        ("良渚水库坝下野营点", "野外露营", 30.3960, 119.9620, "余杭区",
         "杭州周边野外露营点：水库坝下平地可扎营，无人管理设施简陋，适合有经验的轻量化露营者。",
         "无", "有", "无", 3.8),
    ],
    "moganshan": [
        ("莫干山·劳岭村露营基地", "营地", 30.6020, 119.8710, "德清县",
         "莫干山人气免费营地：村委开放草坪营位，可搭天幕帐篷，杭州周边自驾 1 小时直达，周末人多需早到。",
         "有", "有", "有", 4.6),
        ("莫干山庾村文创园停车场", "驻车点", 30.5820, 119.8640, "德清县",
         "莫干山驻车过夜点：文创园公共停车场夜间可停床车，步行可达咖啡街区，补给方便。",
         "有", "有", "无", 4.1),
        ("莫干山仙潭村溪边营位", "营地", 30.6350, 119.8330, "德清县",
         "莫干山溪边露营：仙潭村溪流边平整草地，夏季玩水纳凉佳选，杭州周边亲子露营热门。",
         "无", "有", "无", 4.4),
        ("对河口水库观景驻车带", "驻车点", 30.5430, 119.7910, "德清县",
         "莫干山对河口水库边观景驻车带，日落湖景一流，路肩较窄注意会车，免费无设施。",
         "无", "无", "无", 4.0),
        ("下渚湖湿地外围营地", "营地", 30.5050, 120.0260, "德清县",
         "莫干山下渚湖湿地外围免费草坪，观鸟胜地，杭州周边小众露营选择，蚊虫多备好防护。",
         "有", "有", "无", 3.9),
        ("安吉小杭坑生态营地外围", "野外露营", 30.6380, 119.6160, "安吉县",
         "莫干山以西的小杭坑外围野营区，溪谷地形风景好，正式营区收费、外围可免费扎营。",
         "无", "有", "无", 4.2),
    ],
    "qiandaohu": [
        ("千岛湖东南湖区野营点", "野外露营", 29.5770, 119.0620, "淳安县",
         "千岛湖半岛野营点：三面环水视野开阔，无补给设施，适合有经验的轻量化露营老手。",
         "无", "无", "无", 4.3),
        ("千岛湖上江埠大桥观景驻车区", "驻车点", 29.6210, 119.1430, "淳安县",
         "千岛湖驻车点：大桥旁观景停车区夜间可停床车，看日出方便，大车位充足。",
         "有", "无", "无", 4.1),
        ("千岛湖骑龙巷夜泊停车场", "驻车点", 29.6080, 119.0250, "淳安县",
         "千岛湖县城驻车点：骑龙巷商业街旁停车场，夜间收费低，吃饭补给洗漱都方便。",
         "有", "有", "有", 4.0),
        ("千岛湖金峰半岛露营地", "营地", 29.6630, 119.0150, "淳安县",
         "千岛湖湖湾草坪营地：金峰半岛湖湾免费草坪，可湖边垂钓，节假日帐篷密度高。",
         "有", "有", "无", 4.4),
        ("千岛湖汾口农田营位", "营地", 29.4720, 118.8580, "淳安县",
         "千岛湖西南汾口镇农田边开放营位，村民友好，星空通透度高，光污染少。",
         "无", "有", "无", 3.8),
        ("千岛湖界首乡环湖绿道驻车带", "驻车点", 29.5460, 118.9480, "淳安县",
         "千岛湖环湖绿道旁驻车带，骑行+露营组合玩法热门，免费停放注意不挡绿道入口。",
         "无", "无", "无", 3.9),
    ],
}


def _build_sources(name: str, district: str, now: datetime) -> list[dict]:
    """每个点位 2-3 条信源，URL 是平台真实搜索页（可点击跳转），时间在最近 60 天内。"""
    keyword = f"{name.split('·')[-1].replace('（', ' ').split('外围')[0]}"
    keyword_short = keyword[:10]
    platforms = RNG.sample(["xhs", "zhihu", "mafengwo"], k=RNG.choice([2, 3]))
    sources = []
    for idx, platform in enumerate(platforms):
        url, domain, source_type = _search_url(platform, f"{keyword_short} 露营")
        days_ago = RNG.randint(3, 60) + idx * 7
        sources.append({
            "source_type": source_type,
            "source_url": url,
            "domain": domain,
            "title": f"{keyword_short}实测分享（{source_type}搜索）",
            "snippet": f"网友近期实测{district}{keyword_short}的露营/驻车体验，含到达路线与设施情况。",
            "source_time": now - timedelta(days=days_ago),
            "source_time_method": "demo_seed",
            "reliability_score": RNG.randint(55, 80),
        })
    return sources


async def remove_demo_seed() -> int:
    async with async_session() as db:
        rows = (await db.execute(select(Place.id).where(Place.data_origin == DATA_ORIGIN))).scalars().all()
        if rows:
            # sources/feedbacks 都是 ondelete=CASCADE，删 places 即可
            await db.execute(delete(Place).where(Place.data_origin == DATA_ORIGIN))
            await db.commit()
        return len(rows)


async def seed() -> tuple[int, int]:
    removed = await remove_demo_seed()  # 幂等：先清旧 demo 数据再插
    now = datetime.now(timezone.utc)
    inserted = 0
    async with async_session() as db:
        for cluster in CLUSTERS.values():
            for (name, ptype, lat, lon, district, summary, toilet, water, elec, rating) in cluster:
                sources = _build_sources(name, district, now)
                place = Place(
                    name=name,
                    type=ptype,
                    latitude=lat,
                    longitude=lon,
                    location=WKTElement(f"POINT({lon} {lat})", srid=4326),
                    address=f"浙江省{district}{name}",
                    city="杭州市" if district in {"临安区", "余杭区", "富阳区", "萧山区", "淳安县"} else "湖州市",
                    district=district,
                    province="浙江省",
                    location_confidence="high",   # 过 API 层脏数据过滤（仅 high/medium 可见）
                    geo_source=DATA_ORIGIN,
                    ai_rating=rating,
                    credibility_score=RNG.randint(60, 85),
                    recommendation="recommend" if rating >= 4.2 else "caution",
                    source_count=len(sources),
                    price_clues=["免费"],
                    overnight_clues=["可过夜"] if ptype != "野外露营" else ["无人管理"],
                    toilet_status=toilet,
                    water_status=water,
                    electricity_status=elec,
                    vehicle_fit=["轿车", "SUV"] if ptype != "野外露营" else ["SUV"],
                    risk_tags=[],
                    ai_summary=summary,
                    positive_summary=summary,
                    last_verified_at=now - timedelta(days=RNG.randint(1, 14)),
                    data_origin=DATA_ORIGIN,
                    status="active",
                )
                db.add(place)
                await db.flush()
                for s in sources:
                    db.add(Source(place_id=place.id, **s))
                inserted += 1
        await db.commit()
    return removed, inserted


def main() -> None:
    parser = argparse.ArgumentParser(description="面试演示数据种子（data_origin=demo_seed，可插拔）")
    parser.add_argument("--remove", action="store_true", help="只删除全部 demo_seed 数据")
    args = parser.parse_args()
    if args.remove:
        removed = asyncio.run(remove_demo_seed())
        print(f"已删除 demo_seed 点位 {removed} 个（信源级联删除）")
        return
    removed, inserted = asyncio.run(seed())
    print(f"重置完成：删旧 {removed} 个 → 插入 {inserted} 个演示点位（data_origin={DATA_ORIGIN}）")


if __name__ == "__main__":
    main()
