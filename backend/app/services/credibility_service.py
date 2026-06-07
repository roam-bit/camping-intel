from __future__ import annotations

from datetime import datetime, timezone


def days_since(value: datetime | None) -> int | None:
    if not value:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return max(0, (datetime.now(timezone.utc) - value).days)


def recommendation_from_score(score: int) -> str:
    if score >= 80:
        return "recommend"
    if score >= 40:
        return "caution"
    return "not_recommend"


def calculate_credibility_score(
    last_verified_days: int | None,
    verification_count: int,
    source_consistency: float,
    risk_feedback_count: int,
    source_quality_score: float,
) -> int:
    if last_verified_days is None:
        time_score = 10
    elif last_verified_days <= 7:
        time_score = 100
    elif last_verified_days <= 30:
        time_score = 70
    elif last_verified_days <= 90:
        time_score = 40
    else:
        time_score = 10

    people_score = min(100, verification_count * 20)
    consistency_score = int(max(0, min(1, source_consistency)) * 100)
    risk_score = max(0, 100 - risk_feedback_count * 25)
    quality_score = int(max(0, min(1, source_quality_score)) * 100)
    total = (
        time_score * 0.30
        + people_score * 0.20
        + consistency_score * 0.20
        + risk_score * 0.15
        + quality_score * 0.15
    )
    return max(0, min(100, int(total)))


def source_quality_from_domains(domains: list[str]) -> float:
    if not domains:
        return 0.15
    score = 0.0
    for domain in domains:
        domain = domain.lower()
        if domain.endswith("gov.cn"):
            score += 0.95
        elif any(item in domain for item in ("amap", "ctrip", "mafengwo", "qyer")):
            score += 0.65
        elif any(item in domain for item in ("xiaohongshu", "douyin", "bilibili", "zhihu")):
            score += 0.55
        else:
            score += 0.35
    return min(1.0, score / len(domains))
