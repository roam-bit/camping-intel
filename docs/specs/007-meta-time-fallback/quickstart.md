# Quickstart: spec-007 本地跑通 + 回灌

**Date**: 2026-05-20

---

## 前置依赖

- ✅ Docker `camping_ai-postgres-1` + `camping_ai-redis-1` 已 Up
- ✅ venv 在 `/Users/yihan_guo/Desktop/异想天开/旅居产品_副本/.venv/`
- ✅ httpx 已装（spec-006 已引入）

---

## 1. 跑 migration（加 source_time_method 列）

```bash
cd backend
/Users/yihan_guo/Desktop/异想天开/旅居产品_副本/.venv/bin/python -m alembic upgrade head
```

预期 `0004_add_source_time_method` 应用成功；用 `psql` 确认：
```sql
\d sources
-- 应该看到 source_time_method | character varying(40)
```

---

## 2. 跑 pytest

```bash
/Users/yihan_guo/Desktop/异想天开/旅居产品_副本/.venv/bin/python -m pytest backend/tests/test_meta_time_service.py -v
```

预期：4 条新测试 + 既有 64 条全过 = **68 passed**
- `test_meta_smzdm_happy_path`（fixture HTML 含 og:published_time → matched）
- `test_meta_no_tag_fallback`（无 meta tag → status=no_meta）
- `test_meta_timeout_fallback`（mock HTTP 超时 → status=timeout）
- `test_meta_invalid_time_rejected`（meta 标签内是 2099 年 → 拒绝接受）

---

## 3. 启动后端 + 真实搜索冒烟

```bash
# 终端 A
cd backend && /Users/yihan_guo/Desktop/异想天开/旅居产品_副本/.venv/bin/python -m uvicorn app.main:app --port 8000
```

```bash
# 终端 B
curl -X POST http://localhost:8000/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{"q":"深圳坪山免费露营","lat":22.69,"lon":114.35,"radius_km":30,"limit":12}' \
  | python3 -m json.tool
```

**期望检查**（人工）：
- [ ] 后端 stdout 出现 `meta_time.resolved` 结构化日志
- [ ] 命中 smzdm 信源时，response 里 `sources[N].published_at` 显示真实日期（非 2026-01-31 这类错值）

---

## 4. 跑回灌脚本（修历史 232 条）

```bash
cd backend
/Users/yihan_guo/Desktop/异想天开/旅居产品_副本/.venv/bin/python scripts/backfill_meta_time.py
```

预计运行时间：**5-10 分钟**（按 5 并发 × 平均 2s/条 × dedupe 后约 ~100 unique URL）

输出报告示例：
```
[扫描] 232 candidate rows / 98 unique urls
[处理] 98/98 done
[结果]
  matched: 76
  no_meta: 15
  http_error: 4
  timeout: 3
[域名 top 5 成功率]
  post.m.smzdm.com  42/42 (100%)
  zhuanlan.zhihu.com  8/10 (80%)
  jianshu.com  5/6 (83%)
  ...
[DB UPDATE] 共更新 76 条 sources.source_time + source_time_method
```

**验证回灌效果**：
```sql
-- 看 smzdm 当前状态
SELECT source_url, source_time::date, source_time_method
FROM sources
WHERE source_url LIKE '%smzdm%'
ORDER BY updated_at DESC LIMIT 10;
-- 期望: source_time_method='meta_article_published' 或 'meta_og'
```

随机抽 3 条与 Chrome 实测 og:published_time 对比，误差 ≤ 1 天即达标 SC-004。

---

## 5. 缓存命中验证

```bash
# 立即再跑一次同搜索
curl -X POST http://localhost:8000/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{"q":"深圳坪山免费露营","lat":22.69,"lon":114.35,"radius_km":30,"limit":12}'
```

**期望**：
- [ ] 后端日志里 `cache_hit=true`
- [ ] 整体搜索延迟比第一次快显著（meta_time 部分接近 0）

```bash
# 查 Redis
docker exec camping_ai-redis-1 redis-cli --scan --pattern 'meta_time:v1:*' | head -5
```

---

## 已知潜在踩坑

| 现象 | 排查 |
|---|---|
| 回灌脚本 99% URL 都返回 timeout | 后端机器没设代理；export HTTP_PROXY=http://127.0.0.1:7890 再跑（如果目标站需要） |
| smzdm 命中率低于预期 | smzdm 改版了 meta 标签格式？随机开一篇 view-source 看 head 里实际标签 |
| 跑完后 source_time_method 还有大量 NULL | 这些是回灌脚本跳过的（matched 没成功的保留原值），下次新搜该 URL 时仍会走 fallback 链 |
