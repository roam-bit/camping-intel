"""P2-3 字段投票一致性公式单测。

测覆盖 3 个文档定义的 case + 几个边界情况:
- 5 个反馈全说「能」 → 1.0
- 3 个「能」+ 2 个「不能」 → 0.6
- 全是「不确定」 → 0.4
- 0 个反馈 → 0.4
- 跨字段不同一致性的平均值
"""
from __future__ import annotations

from types import SimpleNamespace

from app.routers.places import consistency_from_feedbacks


def _fb(**kwargs):
    """构造一个轻量 Feedback 替身（不用真创建 ORM 实例，单元测试用 SimpleNamespace）"""
    defaults = {
        "can_park_now": "不确定",
        "can_overnight": "不确定",
        "price_status": "不确定",
        "toilet_available": "不确定",
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_no_feedback_returns_neutral():
    """无反馈 → 0.4 中性值"""
    assert consistency_from_feedbacks([]) == 0.4


def test_all_uncertain_returns_neutral():
    """所有反馈都是「不确定」 → 0.4（无有效投票）"""
    fbs = [_fb() for _ in range(5)]
    assert consistency_from_feedbacks(fbs) == 0.4


def test_all_consistent_returns_1():
    """5 个反馈全说「能」 → 1.0"""
    fbs = [_fb(can_park_now="能", can_overnight="能", price_status="免费", toilet_available="有") for _ in range(5)]
    assert consistency_from_feedbacks(fbs) == 1.0


def test_majority_3_vs_2():
    """3 个「能」+ 2 个「不能」（同一字段）→ 该字段 0.6；其他字段无投票 → 平均仍 0.6"""
    fbs = [_fb(can_park_now="能") for _ in range(3)] + [_fb(can_park_now="不能") for _ in range(2)]
    result = consistency_from_feedbacks(fbs)
    assert abs(result - 0.6) < 0.001, f"期望 0.6 实际 {result}"


def test_average_across_fields():
    """跨字段平均：can_park_now 一致(1.0) + price_status 4:1(0.8) → (1.0+0.8)/2=0.9"""
    fbs = [
        _fb(can_park_now="能", price_status="免费"),
        _fb(can_park_now="能", price_status="免费"),
        _fb(can_park_now="能", price_status="免费"),
        _fb(can_park_now="能", price_status="免费"),
        _fb(can_park_now="能", price_status="收费"),
    ]
    result = consistency_from_feedbacks(fbs)
    # can_park_now: 全"能" → 5/5=1.0; price_status: 4 免费 + 1 收费 → 4/5=0.8
    # 平均 = (1.0 + 0.8) / 2 = 0.9
    assert abs(result - 0.9) < 0.001, f"期望 0.9 实际 {result}"


def test_ignores_unrecognized_field_values():
    """空字符串 / None 也应被排除（与「不确定」同等对待）"""
    fbs = [
        _fb(can_park_now="能"),
        _fb(can_park_now=""),  # 空字符串：被 filter 排除
        _fb(can_park_now=None),  # None：被 filter 排除
    ]
    # 有效投票只剩 1 个「能」 → 1/1 = 1.0
    result = consistency_from_feedbacks(fbs)
    assert result == 1.0
