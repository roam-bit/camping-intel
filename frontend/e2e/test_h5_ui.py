"""H5 UI 端到端回归测试（Playwright 真浏览器）。

每条测试都对应一个「修过的 bug」或「演示关键路径」——防止它们再回归。
跑法见 conftest.py 顶部注释。
"""
from __future__ import annotations


# ─────────────── 回归 1：开屏引导卡必须在首屏可见 ───────────────
# bug 史（2026-06-12 修）：EmptyHero 根节点内联 style position:'relative' 覆盖了
# CSS 的 position:absolute → 卡片被排到地图下方 y≈1193（视口才 900 高），
# 用户从未见过引导卡。这里断言卡片完整落在视口内。

def _assert_hero_in_viewport(page, viewport_h, viewport_w):
    page.wait_for_selector(".empty-hero", timeout=10000)
    box = page.locator(".empty-hero").bounding_box()
    assert box is not None, "引导卡 .empty-hero 不在 DOM"
    assert box["y"] >= 0 and box["y"] + box["height"] <= viewport_h, (
        f"引导卡纵向跑出视口：y={box['y']:.0f} h={box['height']:.0f}（视口高 {viewport_h}）"
        "——疑似 position:absolute 又被覆盖（见 EmptyHero.tsx 注释）"
    )
    assert box["x"] >= 0 and box["x"] + box["width"] <= viewport_w, (
        f"引导卡横向跑出视口：x={box['x']:.0f} w={box['width']:.0f}（视口宽 {viewport_w}）"
    )


def test_hero_visible_desktop(desktop_page):
    _assert_hero_in_viewport(desktop_page, 900, 1440)
    # 3 个示例芯片都在
    assert desktop_page.locator(".hero-chip").count() == 3


def test_hero_visible_mobile(mobile_page):
    _assert_hero_in_viewport(mobile_page, 844, 390)


# ─────────────── 回归 2：宽屏下基准字号不爆炸 ───────────────
# bug 史（2026-06-12 修）：Taro H5 根字号宽屏被撑到 40px + pxtransform 缩放，
# 未显式设字号的元素（如空状态卡）继承出巨大文字。修法 = H5 关 pxtransform +
# index.h5.css 给 .page 设 14px 基准。这里断言继承链正常。

def test_base_font_size_sane_on_desktop(desktop_page):
    desktop_page.wait_for_selector(".page", timeout=10000)
    size = desktop_page.locator(".page").evaluate("el => getComputedStyle(el).fontSize")
    assert size == "14px", f".page 基准字号应为 14px，实际 {size}——pxtransform/index.h5.css 配置疑似回退"


def test_authored_px_not_scaled_on_mobile(mobile_page):
    """pxtransform 关闭后，写 22px 就该渲染 22px（此前手机端被压到 52% ≈ 11.4px）。"""
    mobile_page.wait_for_selector(".empty-hero-title", timeout=10000)
    size = mobile_page.locator(".empty-hero-title").evaluate("el => getComputedStyle(el).fontSize")
    assert size == "22px", f"标题字号应 22px（所写即所得），实际 {size}——pxtransform 疑似又被打开"


# ─────────────── 演示关键路径：示例芯片 → 秒出结果 → 详情可点信源 ───────────────
# 面试演示主链路。依赖 demo 种子数据（backend/scripts/seed_demo_spots.py）：
# DB-first 命中 ≥6 条 → 不调 AI、秒回。若此测试超时，先确认种子数据在库。

def test_demo_search_instant_results(desktop_page):
    page = desktop_page
    page.wait_for_selector(".hero-chip", timeout=10000)
    page.locator(".hero-chip").first.click()  # 「杭州周边免费露营地」
    # DB-first 秒回：8 秒内底部 sheet 必须出现且点位数 > 0（AI 兜底要 30s+，超时即演示链路破了）
    page.wait_for_selector(".bottom-sheet .sheet-title", timeout=8000)
    title = page.locator(".bottom-sheet .sheet-title").inner_text()
    count = int("".join(ch for ch in title if ch.isdigit()) or 0)
    assert count > 0, f"示例搜索应秒出点位，实际 sheet 标题={title!r}——demo 种子数据可能没在库"

    # 点首张点位卡 → 详情抽屉打开，信源链接可点（H5 演示卖点：直接跳转信源）
    page.locator(".place-card").first.click()
    page.wait_for_selector(".detail-drawer, .drawer-actions", timeout=5000)


def test_moganshan_chip_instant(desktop_page):
    """回归（2026-06-12 修）：「莫干山」曾掉进 amap 同名陷阱（福建安溪）→ 0 结果 + 白等 30s。
    字典补条目后必须秒回。"""
    page = desktop_page
    page.wait_for_selector(".hero-chip", timeout=10000)
    page.locator(".hero-chip", has_text="莫干山").click()
    page.wait_for_selector(".bottom-sheet .sheet-title", timeout=8000)
    title = page.locator(".bottom-sheet .sheet-title").inner_text()
    count = int("".join(ch for ch in title if ch.isdigit()) or 0)
    assert count > 0, f"莫干山示例搜索应秒出点位，实际 {title!r}"


# ─────────────── 回归 3：进度文案全局只出现一处 ───────────────
# bug 史（2026-06-12 修）：搜索进度同时显示在顶部 SearchBar 进度卡和底部 sheet，
# 信息重复。修后底部 sheet/list 只显示 warning。结构性断言：结果出来后
# 底部不存在 .sheet-status 进度残留（warning 为空时不渲染）。

def test_progress_not_duplicated_after_search(desktop_page):
    page = desktop_page
    page.wait_for_selector(".hero-chip", timeout=10000)
    page.locator(".hero-chip").first.click()
    page.wait_for_selector(".bottom-sheet", timeout=8000)
    page.wait_for_timeout(1500)  # 等 DB-first 流程完全收尾
    stale = page.locator(".sheet-status", has_text="正在").count()
    assert stale == 0, "底部 sheet 不该再显示进度文案（进度只归顶部 SearchBar 进度卡）"


# ─────────────── 桌面分栏布局（2026-06-12 方案A-2 落地）回归 ───────────────
# 设计稿 /tmp/h5_demos/demo2_v1b.html（用户选定）。断言桌面端是"左 dock 列 +
# 右地图卡"分栏，而不是手机版拉宽：点位面板贴左、宽约 404px；地图从其右侧开始。

def test_desktop_split_layout(desktop_page):
    page = desktop_page
    page.wait_for_selector(".hero-chip", timeout=10000)
    # 顶栏品牌区只在桌面显示
    assert page.locator(".brand").is_visible(), "桌面顶栏应显示品牌区（.brand）"
    page.locator(".hero-chip").first.click()
    page.wait_for_selector(".bottom-sheet .sheet-title", timeout=8000)
    sheet = page.locator(".bottom-sheet").bounding_box()
    assert sheet is not None
    assert sheet["x"] < 60, f"点位面板应贴左侧（dock 列），实际 x={sheet['x']:.0f}"
    assert 320 <= sheet["width"] <= 460, f"dock 列宽应≈404px，实际 {sheet['width']:.0f}"
    map_box = page.locator(".map-wrap").bounding_box()
    assert map_box is not None
    assert map_box["x"] > 400, f"地图应在 dock 右侧开始，实际 x={map_box['x']:.0f}"


def test_mobile_layout_not_split(mobile_page):
    """手机宽度保持原版式（只换色不分栏）：点位面板仍是全宽底部 sheet。"""
    page = mobile_page
    page.wait_for_selector(".hero-chip", timeout=10000)
    assert not page.locator(".brand").is_visible(), "手机宽度不应显示品牌区"
    page.locator(".hero-chip").first.click()
    page.wait_for_selector(".bottom-sheet .sheet-title", timeout=8000)
    sheet = page.locator(".bottom-sheet").bounding_box()
    assert sheet is not None
    assert sheet["width"] > 300, f"手机端 sheet 应接近全宽，实际 {sheet['width']:.0f}"


# ─────────────── demo2 小组件搬运（2026-06-12 用户圈选确认）回归 ───────────────
# 圆形 emoji 地图 pin / 类型徽章 / 设施 emoji 圆点 / 地图图例 / 地名标题。

def test_desktop_demo_widgets(desktop_page):
    page = desktop_page
    page.wait_for_selector(".hero-chip", timeout=10000)
    page.locator(".hero-chip").first.click()
    page.wait_for_selector(".bottom-sheet .sheet-title", timeout=8000)
    # marker 入图时机受 DB 查询 + AMap 渲染影响；且「DB 点位→AI 补齐」阶段 marker 会
    # 整批移除重建，单次采样可能撞上重建间隙读到 0——用重试采样（≤20s）防 flake
    pins = 0
    for _ in range(40):
        pins = page.locator(".map-pin").count()
        if pins > 0:
            break
        page.wait_for_timeout(500)
    assert pins > 0, "地图应渲染圆形 emoji pin（.map-pin）"
    assert page.locator(".map-type-legend").count() == 1, "地图右下应有类型图例"
    assert page.locator(".type-badge").count() > 0, "点位卡应有类型徽章"
    title = page.locator(".sheet-title").inner_text()
    assert "处点位" in title, f"桌面标题应为『地名 · N 处点位』格式，实际 {title!r}"


# ─────────────── 开发者面板（2026-06-12 用户需求：调控搜索/显示数量） ───────────────
# 齿轮入口（仅桌面）→ 抽屉：limit/半径旋钮（写进请求 + localStorage 持久化）、
# 召回诊断、prompt 只读预览（limit 旋钮要真实反映到提示词文本）。

def test_dev_panel_controls_search_limit(desktop_page):
    page = desktop_page
    page.wait_for_selector(".dev-gear", timeout=10000)
    page.locator(".dev-gear").click()
    page.wait_for_selector(".dev-drawer", timeout=5000)

    # prompt 预览加载（接口往返，要等），且默认 limit=12 写在提示词里
    page.wait_for_selector(".dev-prompt", timeout=8000)
    prompt0 = ""
    for _ in range(20):
        prompt0 = page.locator(".dev-prompt").inner_text()
        if "最多列出" in prompt0:
            break
        page.wait_for_timeout(400)
    assert "最多列出 12 个候选" in prompt0, f"默认 prompt 预览应含 limit=12，实际开头：{prompt0[:80]!r}"

    # 调 limit=24 → prompt 预览跟着变
    page.locator(".dev-chip", has_text="24").first.click()
    for _ in range(20):
        if "最多列出 24 个候选" in page.locator(".dev-prompt").inner_text():
            break
        page.wait_for_timeout(400)
    assert "最多列出 24 个候选" in page.locator(".dev-prompt").inner_text(), "limit 旋钮没反映到 prompt 预览"

    # 关抽屉 → 搜索：请求体里必须带 limit=24
    page.locator(".dev-close").click()
    payloads = []
    page.on("request", lambda r: payloads.append(r.post_data or "") if "/api/v1/search" in r.url and r.method == "POST" else None)
    page.locator(".hero-chip").first.click()
    page.wait_for_selector(".bottom-sheet .sheet-title", timeout=8000)
    page.wait_for_timeout(1000)
    assert any('"limit":24' in (p or "").replace(" ", "") for p in payloads), f"搜索请求应带 limit=24，实际载荷：{payloads[:2]}"

    # 召回诊断有数据（搜索发起即有初始快照；complete 事件晚到时策略显示"检索中…"）
    page.locator(".dev-gear").click()
    page.wait_for_selector(".dev-kv-list", timeout=8000)
    diag = page.locator(".dev-kv-list").inner_text()
    assert "策略" in diag and "杭州" in diag, f"诊断面板应含策略行和 query，实际：{diag[:120]!r}"

    # localStorage 持久化（Taro setStorageSync 会包一层 {"data": ...}）
    stored = page.evaluate("() => localStorage.getItem('dev_search_limit')")
    assert stored and "24" in stored, f"limit 应持久化为 24，实际 {stored!r}"


def test_dev_gear_hidden_on_mobile(mobile_page):
    """开发者面板定位是桌面演示工具：手机宽度不显示齿轮入口。"""
    mobile_page.wait_for_selector(".hero-chip", timeout=10000)
    assert not mobile_page.locator(".dev-gear").is_visible(), "手机宽度不该显示开发者齿轮"
