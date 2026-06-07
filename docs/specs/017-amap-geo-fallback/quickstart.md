# Quickstart: spec-017 验证流程

5 分钟跑通 spec-017 全链路验证。

## 前置条件

- Docker `camping_ai` postgres/redis 在跑（`docker compose -p camping_ai ps`）
- 后端 uvicorn 在跑（venv Python，PID 通过 `ps aux | grep uvicorn` 查）
- 前端微信开发者工具打开 `/Users/yihan_guo/Desktop/旅居产品/frontend/`
- 真机与开发机同 WiFi、LAN IP（`ipconfig getifaddr en0`）

## Step 1: 重启后端使 spec-017 代码生效

```bash
# kill 旧
kill -TERM $(pgrep -f "uvicorn app.main:app")
sleep 2

# 起新（venv Python）
cd /Users/yihan_guo/Desktop/旅居产品/backend
nohup /Users/yihan_guo/Desktop/异想天开/旅居产品_副本/.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/uvicorn.log 2>&1 &
disown

# 验证
sleep 5
curl -s -o /dev/null -w "health → %{http_code}\n" http://127.0.0.1:8000/api/v1/health
```

## Step 2: curl 验证 3 种场景

### Case 1: 字典命中（应该 < 50ms、不调 amap）

```bash
curl -s -X POST "http://127.0.0.1:8000/api/v1/search" \
  -H "Content-Type: application/json" \
  -d '{"q":"南昌露营地","limit":12,"radius_km":80,"lat":30.27,"lon":120.15}' \
  | jq '.source_breakdown | {detected_place, search_center, search_center_source}'
```

**预期输出**：
```json
{
  "detected_place": "南昌",
  "search_center": {"lat": 28.68, "lon": 115.86},
  "search_center_source": "dict"
}
```

**反向验证**：
```bash
grep 'geo_resolve' /tmp/uvicorn.log | tail -1 | grep '"source": "dict"'
```

### Case 2: amap 命中（字典 miss、amap 救场）

```bash
curl -s -X POST "http://127.0.0.1:8000/api/v1/search" \
  -H "Content-Type: application/json" \
  -d '{"q":"景德镇露营地","limit":12,"radius_km":80,"lat":30.27,"lon":120.15}' \
  | jq '.source_breakdown | {detected_place, search_center, search_center_source}'
```

**预期输出**（坐标可能略不同、amap 返回为准）：
```json
{
  "detected_place": "江西省景德镇市",
  "search_center": {"lat": 29.27, "lon": 117.18},
  "search_center_source": "amap"
}
```

**第二次重复同 query**（应该 cache 命中、< 30ms）：
```bash
time curl -s -X POST "http://127.0.0.1:8000/api/v1/search" \
  -H "Content-Type: application/json" \
  -d '{"q":"景德镇露营地","limit":12,"radius_km":80,"lat":30.27,"lon":120.15}' \
  | jq '.source_breakdown.search_center_source'
# 期望：real time < 1s（含 AI 联网时间）；amap 部分应该 < 30ms
```

### Case 3: amap 也识别不到（unrecognized_location）

```bash
curl -s -X POST "http://127.0.0.1:8000/api/v1/search" \
  -H "Content-Type: application/json" \
  -d '{"q":"火星二号营地","limit":12,"radius_km":80,"lat":30.27,"lon":120.15}' \
  | jq '{warning_code, warning, source_breakdown: .source_breakdown | {detected_place, search_center, search_center_source}, spots_count: (.spots | length)}'
```

**预期输出**：
```json
{
  "warning_code": "unrecognized_location",
  "warning": "无法识别您输入的地名「火星二号营地」，请尝试更明确的地名（如「南昌露营地」「莫干山民宿」）",
  "source_breakdown": {
    "detected_place": null,
    "search_center": null,
    "search_center_source": "none"
  },
  "spots_count": 0
}
```

**第二次重复同 query**（应该命中 negative cache、不调 amap）：
```bash
time curl -s -X POST "http://127.0.0.1:8000/api/v1/search" \
  -H "Content-Type: application/json" \
  -d '{"q":"火星二号营地","limit":12,"radius_km":80,"lat":30.27,"lon":120.15}' \
  | jq '.warning_code'
# 期望：real time < 100ms（cache 命中、不调 amap）
```

## Step 3: 跑 pytest 防回归

```bash
cd /Users/yihan_guo/Desktop/旅居产品/backend
/Users/yihan_guo/Desktop/异想天开/旅居产品_副本/.venv/bin/python -m pytest tests/ -x -v
```

**预期**：97 passed（94 现有 + 3 个新 spec-017 case）

**特别关注**：
- `test_q_unknown_city_amap_fallback`（places.py 的 amap fallback）必须通过——证明 spec-005 行为没回归
- `test_q_no_geo_intent_keeps_user_location`（places.py 的 user loc fallback）必须通过

## Step 4: 前端重新构建 + 真机测

```bash
cd /Users/yihan_guo/Desktop/旅居产品/frontend
TARO_APP_API_BASE=http://$(ipconfig getifaddr en0):8000 npm run build:weapp
```

微信开发者工具 → 编译 → 真机预览扫码。

## Step 5: 真机验证 SC-006（3 条 query）

### Query A: 「景德镇露营地」（amap 命中）

**预期**：
- ✓ 地图视野跳到江西景德镇市（不是杭州）
- ✓ AI 整理结果出现景德镇相关内容（来源 dqdaily.com 之类不会出现、应该是江西本地媒体/小红书）
- ✓ 等 15-30 秒后 marker 落到景德镇周围
- ✓ 底部 sheet「来源点位 N · 80km」N > 0

### Query B: 「莫干山民宿」（字典命中、快路径）

**预期**：
- ✓ 视野跳到莫干山（浙江湖州）
- ✓ 后端日志 `grep "geo_resolve.*莫干山" | grep "source.*dict"` 命中（不是 amap）
- ✓ AI 整理莫干山相关内容、marker 落到莫干山周围

### Query C: 「火星二号营地」（unrecognized）

**预期**：
- ✗ 地图视野**保持当前位置不变**（不跳杭州）
- ✓ 显示明确报错文案「无法识别您输入的地名「火星二号营地」...」
- ✓ 底部 sheet 不展示底库杂数据（0 个 marker、无来源点位卡片）
- ✓ 用户能继续修改搜索词重搜

## Step 6: 验收 + commit

3 个真机 case 全过 → 标记 task #5 完成 → 进 task #6 commit + merge main。

## 故障排查

| 症状 | 可能原因 | 修法 |
|------|---------|------|
| Case 2 返回 search_center_source=='none' | amap key 未配 / 网络不通 | `grep AMAP_WEB_KEY backend/.env` 确认；curl amap 测试连通性 |
| Case 3 返回 fallback 杭州 | 实施有 bug、未走 unrecognized 分支 | 看后端 log `grep geo_resolve.*"source": "none"` 是否真触发；前端是否正确读 search_center=null |
| Case 2 第二次仍调 amap（无 cache） | geocode_query cache 失效 / Redis 挂了 | `docker compose -p camping_ai ps redis`；`redis-cli KEYS 'geocode_query:*'` |
| pytest 失败 `test_q_unknown_city_amap_fallback` | spec-017 改动影响了 places.py | 回退 places.py 改动、确保只动 search.py |
| 真机视野不跳 amap 命中的地名 | 前端没读 search_center_source、或 search_center 字段名 | 看 index.tsx complete handler、确认读取的是 `data.source_breakdown.search_center` |
