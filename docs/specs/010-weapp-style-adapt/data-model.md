# Phase 1 Data Model: 微信小程序样式适配

**Feature**: 010-weapp-style-adapt | **Date**: 2026-05-21

本 spec 无业务数据实体。这里的「data model」= **改动台账**：逐行列出 `index.css` 与 `place-helpers.ts` 的改点，作为 /speckit-tasks 与 /speckit-implement 的施工依据。

---

## 实体 1：CSS 改点台账（`frontend/src/pages/index/index.css`）

> 行号以当前文件为准；实施时若行号漂移，按选择器名定位。

### A 组 — 全屏根尺寸（R1）

| 行 | 选择器 | 原 | 改为 |
|---|---|---|---|
| 3 | `.page` | `width: 100vw` | `width: 100%` |
| 4 | `.page` | `height: 100vh` | `height: 100%` |

### A' 组 — 根节点高度链（R1/R2，新增）

| 位置 | 动作 |
|---|---|
| `index.css` 顶部或 `app.css` | 新增 `page, .taro_router, #app { height: 100%; }`（实际节点链以微信开发者工具 wxml 面板核对，按真实结构补全断链） |

### B 组 — `inset` 简写拆分（R4）

| 行 | 选择器 | 原 | 改为 |
|---|---|---|---|
| 24 | `.map-wrap` | `inset: 0` | `top: 0; right: 0; bottom: 0; left: 0` |
| 1191 | `.detail-mask` | `inset: 0` | `top: 0; right: 0; bottom: 0; left: 0` |

### C 组 — `min()` 函数拆解（R3）

| 行 | 选择器 | 原 `width` | 改为 |
|---|---|---|---|
| 54 | （搜索框区） | `min(540px, calc(100vw - 80px))` | `width: calc(100% - 80px); max-width: 540px` |
| 150 | | `min(760px, calc(100vw - 280px))` | `width: calc(100% - 280px); max-width: 760px` |
| 162 | | `min(560px, calc(100vw - 280px))` | `width: calc(100% - 280px); max-width: 560px` |
| 599 | | `min(440px, calc(100vw - 112px))` | `width: calc(100% - 112px); max-width: 440px` |
| 705 | | `min(1060px, calc(100vw - 96px))` | `width: calc(100% - 96px); max-width: 1060px` |
| 1156 | | `min(980px, calc(100vw - 96px))` | `width: calc(100% - 96px); max-width: 980px` |
| 1201 | `.detail-drawer` | `min(1080px, calc(100vw - 80px))` | `width: calc(100% - 80px); max-width: 1080px` |
| 1863 | （媒体查询内） | `min(1180px, calc(100vw - 140px))` | `width: calc(100% - 140px); max-width: 1180px` |

### D 组 — 媒体查询内 `vw/vh`（R5）

| 行 | 原 | 改为 | 备注 |
|---|---|---|---|
| 1202 | `max-height: 76vh` | `max-height: calc(100% - Npx)` 或固定 `rpx` | `.detail-drawer` 高度，按定位基准定 |
| 1665 | `width: calc(100vw - 20px)` | `width: calc(100% - 20px)` | |
| 1673 | `max-width: calc(100vw - 24px)` | `max-width: calc(100% - 24px)` | |
| 1746 | `width: calc(100vw - 44px)` | `width: calc(100% - 44px)` | |
| 1812 | `width: 100vw` | `width: 100%` | |
| 1813 | `max-height: 92vh` | `max-height: calc(100% - Npx)` 或固定 `rpx` | |
| 2021 | `width: calc(100VW - 44PX)` | `width: calc(100% - 44px)` | 注意原文大写，规范为小写 |
| 2077 | `width: 100vw` | `width: 100%` | |
| 2078 | `max-height: 92vh` | `max-height: calc(100% - Npx)` 或固定 `rpx` | |

> D 组 `vh` 改写时，`Npx` 取值需结合该弹层的定位祖先与上下边距，实施时逐个核对——目标是「视觉与 H5 改前一致」（SC-004）。

**改点合计**：A 组 2 + A' 组 1（新增链）+ B 组 2 + C 组 8 + D 组 9 ≈ 22 处。

## 实体 2：存储改点台账（`frontend/src/utils/place-helpers.ts`）

| 函数 | 行 | 原 | 改为 |
|---|---|---|---|
| `loadViewedSources` | 293-303 | `window.localStorage.getItem(KEY)` + `typeof window` 守卫 | `Taro.getStorageSync(KEY)`；去掉 window 守卫，保留 `try/catch` 与 `if(!raw) return new Set()` |
| `persistViewedSources` | 305-312 | `window.localStorage.setItem(KEY, ...)` + `typeof window` 守卫 | `Taro.setStorageSync(KEY, ...)`；去掉 window 守卫，保留 `try/catch` |
| 文件头 | — | （无 Taro import） | 新增 `import Taro from '@tarojs/taro'` |

**不改**：`useViewedSources.ts`（同步 API 语义不变，hook 透明受益）、`index.tsx`（仅消费 hook）。

## 关系与约束

- **双端通写**：所有 CSS 改点产物在 H5 与小程序编译下都成立——不引入 `TARO_ENV` 分支 CSS。
- **存储键不变**：`VIEWED_SOURCES_KEY` 常量不动，H5 端已有用户数据键名兼容（Taro Storage 在 H5 仍落 localStorage 同名 key）。
- **零回归约束**：每个 CSS 改点的 H5 渲染结果须与改动前肉眼一致（SC-004）。

## 状态流转

无状态机。求证进度仅「未看过 → 看过」单向追加，由 `markSourceViewed` 驱动，存储介质切换不改变这一行为。
