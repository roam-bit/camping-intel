# Tasks: 微信小程序样式适配

**Feature**: 010-weapp-style-adapt | **Date**: 2026-05-21
**Input**: plan.md / spec.md / research.md / data-model.md / quickstart.md（均在 `specs/010-weapp-style-adapt/`）

**Tests**: 本 spec 为纯样式 + 存储 API 适配，无单元测试（符合 CLAUDE.md「纯样式无测试」例外）。验证靠双端构建 + 人工核验。

**改动文件**：`frontend/src/pages/index/index.css`、`frontend/src/utils/place-helpers.ts`（+ 可能 `app.css` 补根链）。

---

## Phase 1: Setup（环境与勘查）

- [X] T001 跑 `cd frontend && npm run build:weapp` 确认改前基线能编译；在微信开发者工具打开 `frontend/` 复现首页空白现象，截图留底
- [X] T002 在微信开发者工具 wxml 面板逐层查看小程序根节点链（`page` → `.taro_router` → … → `.page`），记录真实节点名与缺高度的断链层，作为 T003 补链依据

---

## Phase 2: Foundational

无独立 Foundational 任务——根节点高度链勘查已并入 T002，其修复（T003）归属 US1。

---

## Phase 3: User Story 1 - 小程序首页框架元素可见（P1）

**Goal**：把 `index.css` 的 `vh/vw`、`inset`、`min()` 改为双端兼容写法，让小程序首页搜索框/模式切换/分类 tab/筛选栏/底部 sheet 可见、不塌陷。

**Independent Test**：微信开发者工具首页框架元素全部可见、布局不塌陷不重叠（quickstart 步骤 1）。

> 以下 T003-T007 同改 `frontend/src/pages/index/index.css`（T003 可能改 `app.css`），同文件不可并行，按序执行。

- [X] T003 [US1] 按 T002 勘查结果，在 `frontend/src/pages/index/index.css` 顶部（或 `frontend/src/app.css` 全局处）补根节点高度链：`page, .taro_router, #app { height: 100%; }`，补齐所有断链层
- [X] T004 [US1] 改 `frontend/src/pages/index/index.css` 第 3-4 行 `.page`：`width:100vw`→`width:100%`、`height:100vh`→`height:100%`
- [X] T005 [US1] 改 `frontend/src/pages/index/index.css` 第 24 行 `.map-wrap` 与第 1191 行 `.detail-mask`：`inset:0`→`top:0;right:0;bottom:0;left:0`
- [X] T006 [US1] 改 `frontend/src/pages/index/index.css` 第 54/150/162/599/705/1156/1201/1863 行共 8 处 `min(Apx,calc(100vw-Bpx))`→`width:calc(100%-Bpx);max-width:Apx`（逐行取值见 data-model.md C 组台账）
- [X] T007 [US1] 改 `frontend/src/pages/index/index.css` 媒体查询内 9 处 `vw/vh`（第 1202/1665/1673/1746/1812/1813/2021/2077/2078 行）：`100vw`→`100%`、`calc(100vw-N)`→`calc(100%-N)`、`max-height:Nvh`→`calc(100%-Npx)` 或固定 `rpx`，并把第 2021 行大写 `100VW/44PX` 规范为小写（见 data-model.md D 组台账）
- [X] T008 [US1] 跑 `npm run build:weapp`，微信开发者工具核验首页框架元素全部可见、≥2 机型不塌陷不与导航栏重叠、地图区空白但不遮挡其它元素、模式切换正常显隐（quickstart 步骤 1）

**Checkpoint**：US1 完成——小程序首页骨架可见（SC-001/002/005）。

---

## Phase 4: User Story 2 - 求证进度存储在小程序端不报错（P2）

**Goal**：把求证进度存储从 `localStorage` 换成双端兼容的 Taro Storage，小程序端不报 `localStorage is not defined`。

**Independent Test**：小程序端浏览信源、触发打点，控制台无存储报错，进度能存取（quickstart 步骤 2）。

> US2 改 `frontend/src/utils/place-helpers.ts`，与 US1 的 `index.css` 不同文件——**整个 US2 可与 US1 并行**。T009-T011 同文件按序。

- [X] T009 [US2] 在 `frontend/src/utils/place-helpers.ts` 文件头新增 `import Taro from '@tarojs/taro'`
- [X] T010 [US2] 改 `frontend/src/utils/place-helpers.ts` `loadViewedSources`（第 293-303 行）：`window.localStorage.getItem(KEY)`→`Taro.getStorageSync(VIEWED_SOURCES_KEY)`，去掉 `typeof window` 守卫，保留 `try/catch` 与 `if(!raw) return new Set()` 空值兜底
- [X] T011 [US2] 改 `frontend/src/utils/place-helpers.ts` `persistViewedSources`（第 305-312 行）：`window.localStorage.setItem(KEY,...)`→`Taro.setStorageSync(VIEWED_SOURCES_KEY,...)`，去掉 `typeof window` 守卫，保留 `try/catch`
- [X] T012 [US2] 跑 `npm run build:weapp`，微信开发者工具触发求证进度打点 + 重进首页，核验控制台无 `localStorage`/视口单位报错、进度能读回（quickstart 步骤 2）

**Checkpoint**：US2 完成——小程序求证进度无报错（SC-003）。

---

## Phase 5: User Story 3 - H5 端零回归（P1）

**Goal**：确认所有 CSS/存储改动在 H5 端零回归。

**Independent Test**：`build:h5` 成功、H5 首页布局视觉与改前肉眼一致、H5 求证进度功能正常（quickstart 步骤 3）。

> 依赖 US1 + US2 完成（验证它们的改动）。

- [X] T013 [US3] 跑 `cd frontend && npm run build:h5`，确认构建成功、0 报错
- [X] T014 [US3] 打开 H5 首页，肉眼对比改动前——首页布局/视觉一致，无错位、无塌陷（SC-004）
- [X] T015 [US3] H5 端触发求证进度打点，核验看过的信源高亮/计数与改动前行为一致

**Checkpoint**：US3 完成——H5 零回归（SC-004）。

---

## Phase 6: Polish & 收尾

- [X] T016 按 quickstart.md 三步走一遍完整双端核验，确认 SC-001~SC-005 全达标
- [X] T017 `git add` 改动文件 + commit（spec-010 完成），更新 `current_progress.md` 记录 spec-010 收尾

---

## Dependencies

```
Phase 1 (T001-T002)  ── Setup，最先
       │
       ├─→ Phase 3 US1 (T003-T008)  ┐
       │      T003→T004→T005→T006→T007→T008（同文件串行）
       │                            ├─→ Phase 5 US3 (T013-T015)
       └─→ Phase 4 US2 (T009-T012)  ┘         │
              T009→T010→T011→T012             │
                                              └─→ Phase 6 (T016-T017)
```

- **US1 与 US2 可并行**：改不同文件（`index.css` vs `place-helpers.ts`），互不依赖。
- **US3 依赖 US1+US2**：它验证前两者的改动。
- 同一文件内任务串行（不可并行）。

## Parallel Execution

- US1（T003-T008）与 US2（T009-T012）两条线可同时推进。
- 各线内部串行（同文件）。
- 单人开发顺序推荐：US1 → US2 → US3，简单稳妥。

## Implementation Strategy

- **MVP scope**：US1（首页可见）——这是「小程序看起来像个产品」的最低门槛，单独完成即有可见价值。
- **增量交付**：US1 done 可单独核验 → US2 done 补存储 → US3 统一验 H5 零回归。
- 每个 Checkpoint 都是一个可独立核验的增量。
