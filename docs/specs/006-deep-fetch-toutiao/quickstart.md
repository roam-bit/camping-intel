# Quickstart: spec-006 本地跑通

**Date**: 2026-05-20
**Audience**: 实现完成后，验证一次跑通的步骤（含人工抽查）

---

## 前置依赖

- ✅ Docker 容器 `camping_ai_postgres` + `camping_ai_redis` 已 Up（既有）
- ✅ Python venv 在 `/Users/yihan_guo/Desktop/旅居产品_副本/.venv/`（既有）
- ✅ Ark API key 在 `backend/.env`（既有）

---

## 1. 安装新依赖（首次）

```bash
cd backend
/Users/yihan_guo/Desktop/旅居产品_副本/.venv/bin/pip install "playwright>=1.40"
/Users/yihan_guo/Desktop/旅居产品_副本/.venv/bin/playwright install chromium
```

预计 200-300MB 下载，3-5 分钟。

---

## 2. 跑 migration（新增 places.topic_url_original 列）

```bash
cd backend
/Users/yihan_guo/Desktop/旅居产品_副本/.venv/bin/alembic upgrade head
```

预期：`006_add_topic_url_original` 应用成功。

---

## 3. 跑 pytest（验证 2 条新测试）

```bash
cd backend
/Users/yihan_guo/Desktop/旅居产品_副本/.venv/bin/python -m pytest tests/test_deep_fetch_service.py -v
```

预期：
- `test_deep_fetch_happy_path` ✅ —— FakeFetcher 返回 5 条 mock 帖，「莫干山」关键词匹配中 3 条相关 → 返回 score 最高的那一条
- `test_deep_fetch_timeout_fallback` ✅ —— FakeFetcher 抛 TimeoutError → 返回 match_status=timeout，无异常上抛

全套 pytest 通过：
```bash
/Users/yihan_guo/Desktop/旅居产品_副本/.venv/bin/python -m pytest
# 应该 ≥51 passed（既有 49 + 2 条新）
```

---

## 4. 启动后端 + 人工冒烟

```bash
# 终端 A
cd backend
/Users/yihan_guo/Desktop/旅居产品_副本/.venv/bin/uvicorn app.main:app --port 8000 --reload
```

```bash
# 终端 B：触发一次包含话题页的搜索
curl -X POST http://localhost:8000/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{"query": "莫干山免费露营"}' | jq .
```

**期望检查项**（人工）：
- [ ] 响应里的 `sources[]` **不含** `weitoutiao.zjurl.cn/topic/...` 这类 URL
  - 命中场景：原话题页位置被替换成 `weitoutiao.zjurl.cn/article/{帖子ID}` 这类单帖 URL
  - 未命中场景：原话题页被整体剔除，sources 数量比之前少 1-2 条
- [ ] 后端 stdout 里能看到 `{"event": "deep_fetch.completed", ...}` 结构化日志，含 `match_status / duration_ms / cache_hit` 字段
- [ ] DB 里命中场景的 places 记录 `topic_url_original` 字段非空：
  ```sql
  SELECT name, source_url, topic_url_original FROM places ORDER BY id DESC LIMIT 5;
  ```

---

## 5. 缓存命中验证

```bash
# 立即再跑一次完全相同的搜索
curl -X POST http://localhost:8000/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{"query": "莫干山免费露营"}' | jq .
```

**期望**：
- [ ] 后端日志里 `cache_hit=true`
- [ ] 整体搜索延迟比第一次快显著（深抓部分接近 0）

---

## 6. SC-001 抽查（演示前）

准备 10 条真实「微头条话题页 URL + 搜索关键词」样本，逐个跑过一遍 `/api/v1/search`，人工评分：

| # | URL | keyword | 返回的单帖是否真相关？(Y/N) |
|---|---|---|---|
| 1 | ... | 莫干山 | |
| 2 | ... | 长白山 | |
| ... | | | |

合计 Y 的占比 ≥ 70% → SC-001 达标。

---

## 已知潜在踩坑

| 现象 | 排查 |
|---|---|
| `playwright install` 卡在 90% | 切换镜像：`PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright playwright install chromium` |
| Redis 连不上 | `docker ps` 看 `camping_ai_redis` 是否 healthy；env 里 `REDIS_URL` 应为 `redis://localhost:6379/0` |
| 深抓全 timeout | (a) 排查代理（CLAUDE.md 提到 FlClash 7890，需要 `export HTTP_PROXY=http://127.0.0.1:7890`）(b) 微头条改版了？人工开浏览器看话题页能不能渲出帖子列表 |
| LLM 评分全返回 keyword_only | Ark API key 失效 / Ark 服务 5xx —— 看 ark provider 日志 |
