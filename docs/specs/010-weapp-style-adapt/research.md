# Phase 0 Research: 微信小程序样式适配

**Feature**: 010-weapp-style-adapt | **Date**: 2026-05-21

本文件解决 plan.md Technical Context 中的兼容写法选择，给出每项决策的「选什么 / 为什么 / 否决了什么」。

---

## R1. `.page` 全屏高度：`100vh` → 怎么改

- **Decision**：`.page` 改 `height: 100%`，并补齐根节点高度链——确保 `page`（小程序根标签）/ `.taro_router` / `#app` 等祖先节点均有 `height: 100%`，把高度从视口逐级传到 `.page`。`width: 100vw` 改 `width: 100%`。
- **Rationale**：小程序对 `vh` 支持不稳定（不同基础库/机型解释不一），而 `height: 100%` 是双端都成立的最稳写法；H5 端只要根链补齐，`100%` 与原 `100vh` 视觉等价。比起运行时 `Taro.getSystemInfoSync().windowHeight` 动态算，纯 CSS 方案无 JS、无闪烁、无机型分支，维护成本最低。
- **Alternatives rejected**：
  - `Taro.getSystemInfoSync().windowHeight` 内联高度——需改 tsx、引入 JS 计算与首屏闪烁，且 `getSystemInfoSync` 在新版 Taro 已被标记弃用，否决。
  - 保留 `100vh` 仅给小程序加 `TARO_ENV` 分支——违背 plan「优先双端通写」，CSS 双份维护易漂移，否决。

## R2. 根节点高度链具体落点

- **Decision**：在 `index.css`（或 `app.css`，择全局生效处）补 `page, .taro_router, .taro_router > .taro-tabbar__panel, #app { height: 100% }`，确认从小程序 `page` 标签到 `.page` 之间无断链。实施时先在微信开发者工具 wxml 面板逐层核对真实节点名，按实际结构补。
- **Rationale**：`height: 100%` 要求父节点有确定高度，链一断高度就塌陷——这正是首页空白的直接原因。
- **Alternatives rejected**：只改 `.page` 不补链——必然继续塌陷，否决。
- **Open**：实际节点链以微信开发者工具核对为准（tasks 阶段第一步做此勘查）。

## R3. `min(Apx, calc(100vw - Bpx))` → 怎么改

- **Decision**：统一改写为 `width: calc(100% - Bpx); max-width: Apx`。即用 `max-width` 表达「不超过 A」、用 `calc(100% - B)` 表达「留 B 边距」，二者叠加等价于原 `min()`。`100vw` 一并换成 `100%`。
- **Rationale**：`min()` CSS 函数在小程序老基础库不支持，是首页浮层不可见的元凶之一。`width + max-width` 是 CSS2 级别语法，双端 100% 支持，且语义与 `min()` 完全等价（取两者较小值）。
- **涉及行**：`index.css` 第 54 / 150 / 162 / 599 / 705 / 1156 / 1201 / 1863 行（共 8 处 `min()`）。
- **Alternatives rejected**：CSS 自定义属性 + JS 计算——过度工程，否决。

## R4. `inset: 0` → 怎么改

- **Decision**：拆成 `top: 0; right: 0; bottom: 0; left: 0` 四条。
- **Rationale**：`inset` 简写小程序解释不一致；四条独立属性是双端都稳的等价写法。
- **涉及行**：`index.css` 第 24（`.map-wrap`）/ 1191（`.detail-mask`）行。

## R5. 媒体查询里的 `calc(100vw - Npx)` 与 `100vw`

- **Decision**：媒体查询块内的 `100vw` 同样换 `100%`（第 1665 / 1673 / 1746 / 1812 / 2021 / 2077 行）。注意第 2021 行写的是大写 `100VW`/`44PX`——一并规范为小写。`max-height: 76vh / 92vh`（第 1202 / 1813 / 2078 行）的 `vh` 改为：弹层类高度改用 `calc(100% - Npx)` 或固定 `rpx`，按元素实际定位基准定（详见 data-model.md 逐行台账）。
- **Rationale**：媒体查询自身（`@media`）小程序支持；问题只在值里的 `vw/vh`。`max-height` 的父基准是定位祖先而非视口，换 `100%` 即等价。
- **Alternatives rejected**：保留 `vh` 赌新基础库——基础库版本不可控，违背「至少 2 机型不塌陷」SC-002，否决。

## R6. 求证进度存储：`localStorage` → 怎么改

- **Decision**：`place-helpers.ts` 的 `loadViewedSources` / `persistViewedSources` 把 `window.localStorage.getItem/setItem` 换成 `Taro.getStorageSync(key)` / `Taro.setStorageSync(key, value)`。去掉 `typeof window === 'undefined'` 守卫（Taro Storage 双端均可用），保留 `try/catch` 容错。
- **Rationale**：小程序无 `window.localStorage`，调用即 `localStorage is not defined` 报错。`Taro.getStorageSync/setStorageSync` 是 Taro 官方跨端 API——H5 编译为 `localStorage`、小程序编译为 `wx.getStorageSync`，一套代码双端通。同步 API 与原 `localStorage` 同步语义一致，无需改 `useViewedSources` hook 的调用方式。
- **小程序首次无数据**：`Taro.getStorageSync` 对不存在的 key 返回空字符串 `''`，现有 `if (!raw) return new Set()` 已正确兜底（对应 edge case「首次无历史返回空而非报错」）。
- **Alternatives rejected**：
  - 用 `TARO_ENV` 分支分别调 localStorage / wx API——Taro 已封装好跨端 Storage，再分叉是重复造轮子，否决。
  - 异步 `Taro.getStorage`——会把 `loadViewedSources` 变异步、`useViewedSources` 的 `useState` 初值同步读取就失效，需大改 hook，否决。

## R7. 是否需要扣除导航栏/状态栏占位

- **Decision**：小程序 `app.config`（`window.navigationStyle`）走默认带原生导航栏；`page` 标签下的 `.page` 高度链用 `100%` 时，小程序运行时给 `page` 的高度**已是扣除原生导航栏后的可用区**——因此 `height: 100%` 链天然不与导航栏重叠，无需手动扣 `statusBarHeight`。
- **Rationale**：这是小程序原生导航栏模式的既定行为；只有 `custom` 自定义导航栏才需手动扣占位，本 spec 不改导航栏样式。
- **验证**：tasks 阶段在微信开发者工具用 2 种机型核对 `.page` 顶部不被导航栏压盖（SC-002）。

---

## 决策汇总表

| 项 | 原写法 | 改为 | 涉及行 |
|---|---|---|---|
| R1 全屏尺寸 | `width:100vw;height:100vh` | `width:100%;height:100%`+根链 | 3-4 |
| R3 浮层宽度 | `min(Apx,calc(100vw-Bpx))` | `width:calc(100%-Bpx);max-width:Apx` | 54,150,162,599,705,1156,1201,1863 |
| R4 满定位 | `inset:0` | `top/right/bottom/left:0` | 24,1191 |
| R5 媒体查询 | `100vw` / `vh` | `100%` / `calc(100%-N)` 或 rpx | 1202,1665,1673,1746,1812,1813,2021,2077,2078 |
| R6 存储 | `window.localStorage` | `Taro.getStorageSync/setStorageSync` | place-helpers.ts:293-312 |

所有 spec.md 的 NEEDS CLARIFICATION 均已在 clarify 阶段解决，无遗留。
