# Quickstart: spec-009 验证步骤

**Date**: 2026-05-21

---

## 前置依赖

- ✅ 前端工具链（Taro 4 + node，`frontend/` 已 `npm install`）
- ✅ 微信小程序 AppID `wxb4776856c0d56676`
- ⏳ 微信开发者工具（macOS 版，[官网](https://developers.weixin.qq.com/miniprogram/dev/devtools/download.html) 下载）—— US2 运行验证需要，由开发者本地装

---

## 1. 编译微信小程序产物

```bash
cd frontend
<node> npm run build:weapp
```

预期：`dist/weapp/`（或对应产物目录）生成，构建进程成功结束，无致命错误。
编译期的报错/警告 → 抓进平台差异清单。

---

## 2. H5 不回归验证

```bash
cd frontend
npm run build:h5
```

预期：H5 构建仍成功。本 spec 任何改动都不能让这步坏掉（SC-004）。

---

## 3. 微信开发者工具打开（人工核验 US2）

1. 打开微信开发者工具 → 导入项目 → 选 `frontend/` 目录
2. AppID 填 `wxb4776856c0d56676`（或 project.config.json 已带）
3. 工具编译预览

**核验项**：
- [ ] 小程序能启动，**首页非白屏**——能看到搜索框、列表区、导航栏等框架元素
- [ ] 地图区域空白/占位**可以接受**，但不能导致整页崩溃
- [ ] 控制台报错 → 抓进平台差异清单

---

## 4. 检查平台差异清单产出

```bash
cat docs/mvp-backlog/小程序平台差异清单.md
```

**核验项**：
- [ ] 文档存在，结构符合 `contracts/差异清单模板.md`
- [ ] 编译期 + 运行期问题都有
- [ ] 每条差异有：现象 / 严重度（阻断首页·功能缺失·体验降级）/ 建议归属 spec
- [ ] 「按后续 spec 归类汇总」覆盖所有非「已隔离」条目
- [ ] 含「小程序↔后端 API 网络层」一项（clarify Q1 要求）

---

## 已知潜在踩坑

| 现象 | 排查 |
|---|---|
| `build:weapp` 报某 npm 依赖不支持小程序 | 记入差异清单（依赖类）；本 spec 不强行替换 |
| 开发者工具打开白屏 | 看控制台——多半是某处 `window`/`document` 漏了 TARO_ENV 守卫；若阻断首页则本 spec 内隔离 |
| 主包体积 > 2MB | 记入清单，分包优化留后续 spec |
| 开发者工具提示 AppID 无效 | 确认 AppID 拼写；或用工具的测试号临时验证 |
