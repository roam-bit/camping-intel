# Phase 1 Data Model: 微信小程序编译跑通

**Date**: 2026-05-21

本 spec 是构建配置 + 盘点，**无数据库实体**。这里描述的是配置文件 + 盘点清单两个「文档型实体」。

---

## 实体 1：微信小程序项目配置（`frontend/project.config.json`）

| 字段 | 取值 | 说明 |
|---|---|---|
| `appid` | `wxb4776856c0d56676` | 用户已注册的微信小程序 AppID |
| `projectname` | `camping-ai`（或沿用 `camping-ai-taro`）| 项目名 |
| `miniprogramRoot` | `dist/weapp/`（Taro weapp 产物目录）| 微信开发者工具识别的小程序根 |
| `compileType` | `miniprogram` | 编译类型 |
| `setting` | `{ urlCheck, es6, postcss, ... }` | 编译/校验选项 |

**配套**：`project.private.config.json`（本地私有，含 `setting.urlCheck=false` 等开发者偏好）→ 加入 `.gitignore`，不入库。

---

## 实体 2：平台差异清单（`docs/mvp-backlog/小程序平台差异清单.md`）

本 spec 的核心交付物。每条差异记录的字段：

| 字段 | 说明 | 取值示例 |
|---|---|---|
| 名称 | 不兼容点简述 | 「高德地图 JS API 不可用」 |
| 类别 | 分类 | 地图 / 外链 web-view / 浏览器 API / 定位 / 网络层 / 依赖 / 样式 / 其它 |
| 现象 | 编译期或运行期表现 | 「小程序端 MapCanvas 渲染空容器，无地图」 |
| 来源 | 编译期 / 运行期 | 运行期 |
| 严重度 | 三级 | 阻断首页 / 功能缺失 / 体验降级 |
| 建议归属 spec | 后续哪个 spec 解决 | spec-010 地图适配 |

**严重度定义**：
- **阻断首页**：导致整页白屏/崩溃，必须本 spec 内隔离掉（FR-004）
- **功能缺失**：某功能完全不可用（如地图不显示、外链打不开），留后续 spec
- **体验降级**：能用但体验差（如样式偏移），留后续 spec 或 backlog

---

## 预期会进清单的差异（基于 Phase 0 勘察的预判，实测为准）

| 预判差异 | 类别 | 预估严重度 | 预估归属 |
|---|---|---|---|
| 高德地图 JS API 不可用（`amap.ts`/`MapCanvas`）| 地图 | 功能缺失 | spec-010 地图适配 |
| 信源「查看原文」外链（`PlaceDetailDrawer`）| 外链 web-view | 功能缺失 | 信源外链 spec |
| 后端 API 调 localhost/IP 被微信拦 | 网络层 | 功能缺失 | 后端网络层 spec |
| 浏览器定位 API（geolocation）| 定位 | 功能缺失 | 地图适配 spec 或独立 |
| 可能的 `window`/`document` 漏守卫处 | 浏览器 API | 视情况 | 本 spec 隔离（若阻断）/ 后续 |
| AI 生成内容合规标注未做 | 合规 | 体验降级 | AI 标注 spec |

> 以上是 Phase 0 勘察的**预判**，真实清单以 spec-009 实施时 `build:weapp` + 开发者工具实测为准。

---

## 实体关系

```text
build:weapp ──编译期问题──┐
                          ├──► 平台差异清单（汇总分类 + 严重度）
微信开发者工具 ──运行期问题─┘            │
                                        ▼
                          spec-010 地图适配 / 信源外链 spec / 后端网络层 spec ...
                          （各自从清单圈定范围）
```
