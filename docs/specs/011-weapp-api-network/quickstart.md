# Quickstart: spec-011 验证清单

实现完成后，按下面顺序逐项核验。任何一项不过即视为未完工。

## 前置

- 本地后端已起：`backend` 目录 venv 跑 `uvicorn app.main:app --reload`
- 微信开发者工具已装，能打开本项目

## 1. H5 零回归（US3，最优先验）

```bash
cd frontend && npm run build:h5
```

- [ ] 构建成功，无报错
- [ ] 浏览器打开 H5，发起一次 AI 搜索 → 答案仍是**逐字蹦出**的流式效果
- [ ] 点位列表、统一搜索、信源 chip、反馈提交 → 功能与改动前一致
- [ ] 控制台无新增报错

## 2. 小程序连可配置域名（US1）

```bash
cd frontend && TARO_APP_API_BASE=http://<本机局域网IP>:8000 npm run build:weapp
```

> 用本机局域网 IP（非 localhost）模拟「域名」，因为微信开发者工具里小程序连 localhost 也受限。

- [ ] 构建成功
- [ ] 微信开发者工具打开 `dist/`，详情面板勾选「不校验合法域名」
- [ ] 首页加载 → Network 面板里 API 请求指向所配地址，**无 `localhost`/`127.0.0.1`**
- [ ] 不带 `TARO_APP_API_BASE` 跑 `build:weapp` → 构建日志出现「⚠️ 仍指向 localhost」提示

## 3. 小程序 AI 搜索降级（US2）

- [ ] 微信开发者工具里发起一次 AI 搜索
- [ ] 结果完整返回并展示（答案文本 + 点位 + 信源）
- [ ] 控制台**无** `fetch` / `ReadableStream` / 流式相关报错
- [ ] 答案为一次性出现（无逐字动效）—— 属预期，不是 bug

## 4. 后端 CORS（US4）

```bash
cd backend && /Users/yihan_guo/Desktop/异想天开/旅居产品_副本/.venv/bin/python -m pytest tests/test_cors_config.py -v
```

- [ ] `test_cors_config.py` 全过
- [ ] 全量 `pytest` 无回归

## 5. 全库无写死地址（SC-001）

```bash
grep -rn "127.0.0.1:8000\|localhost:8000" frontend/src
```

- [ ] `frontend/src` 下无「无法被配置覆盖」的硬编码后端地址（`config/index.js` 里作为本地开发默认值的那一处可保留）

## 完工标准

5 节全部勾满 → spec-011 代码侧完成。真实世界线（域名/备案/HTTPS/微信后台配域名）不在本 spec，另行处理。
