# Phase 0 Research: 微信小程序编译跑通

**Date**: 2026-05-21

---

## D1：project.config.json —— 微信小程序项目配置

**Decision**：在 `frontend/` 新建 `project.config.json`，含 AppID `wxb4776856c0d56676`、项目名、`miniprogramRoot` 指向 Taro weapp 产物目录（`dist/weapp/`）、编译设置。

**Rationale**:
- 微信开发者工具靠 `project.config.json` 识别项目（AppID、产物根目录、编译选项）——没有它工具无法打开
- Taro `build:weapp` 默认产物在 `dist/`（config 里 `outputRoot: 'dist'`）；微信开发者工具要指向**编译后的 weapp 产物**
- AppID 写进配置后，开发者工具用它做云端关联

**Alternatives considered**:
- 用微信开发者工具的「测试号」→ 用户已注册真实 AppID，直接用更规范
- 让 Taro 自动生成 → Taro 编译会生成产物内的 project.config，但项目根的配置仍建议显式建，便于版本控制 + 注释

**实施细节**：`project.private.config.json`（本地私有配置，含 `setting.urlCheck` 等开发者本地偏好）应加入 `.gitignore`，不入库。

---

## D2：现有代码的平台守卫情况（关键——决定编译能不能过）

**Decision**：现有前端**已有相当程度的平台守卫**，编译大概率能过，地图运行时也不会崩首页。

**勘察发现**：
- `utils/amap.ts`：`loadAmap()` 有 `typeof window === 'undefined'` 守卫 → 非浏览器环境直接 reject，不会因 `window` 未定义而崩
- `components/MapCanvas.tsx`：`useEffect` 里 `if (process.env.TARO_ENV !== 'h5') return` → 小程序端直接跳过地图初始化
- `api/client.ts`、`utils/place-helpers.ts`：也有 TARO_ENV / window 守卫

**Rationale**:
- 这些守卫意味着：weapp 编译时不会因「`window` 不存在」直接失败；地图组件在小程序运行时是「跳过初始化」而非「崩溃」
- 所以 spec-009 的「首页非白屏」目标，**地基条件本身就具备**——这降低了本 spec 的风险

**Alternatives considered**: 不适用（这是勘察结论，非选型）

**风险点**：守卫不一定覆盖全。仍可能有：① 某些 npm 依赖只支持浏览器、② `document`/`localStorage` 等直接调用没守卫、③ CSS 里 H5 专属单位。这些是编译/运行时才暴露的——正是本 spec 要盘点的。

---

## D3：地图等不兼容组件的「错误隔离」策略

**Decision**：优先依赖**现有的 `TARO_ENV` 条件守卫**（地图在小程序端跳过初始化）；若发现仍有崩溃，用 React 错误边界（Error Boundary）包住地图区域兜底。

**Rationale**:
- 现有 `MapCanvas` 已经 `TARO_ENV !== 'h5'` early-return → 小程序端它本来就不跑地图逻辑，渲染一个空容器
- 「占位/空白可接受」（FR-004）—— 空容器即满足
- 只有当某处守卫漏了、真的抛运行时错误，才需要 Error Boundary

**Alternatives considered**:
- 一上来就全套 Error Boundary → 过度设计；现有守卫够用就不加
- 条件编译彻底剔除地图代码 → 属「地图适配 spec」范围，不在 009

---

## D4：H5 不回归怎么保证

**Decision**：每次改 `config/index.js` / `app.config.ts` / 业务代码后，都跑一次 `build:h5` 验证；改动只允许「补 mini/weapp 配置」「加平台守卫」这类**对 H5 透明**的操作，不允许动 H5 行为。

**Rationale**:
- FR-006 / SC-004 硬约束：H5 零回归
- Taro 的 `mini` 段和 `h5` 段是独立的——改 `mini` 段天然不影响 H5
- 业务代码若要改（修编译错误），用 `process.env.TARO_ENV` 条件分支，H5 分支保持原样

---

## D5：差异清单的产出方式

**Decision**：盘点分两个来源——① **编译期**：`build:weapp` 的报错/警告；② **运行期**：微信开发者工具里控制台报错 + 肉眼看页面哪块没渲染。汇总进 `docs/mvp-backlog/小程序平台差异清单.md`，结构见 `contracts/差异清单模板.md`。

**Rationale**:
- 编译期错误（依赖不兼容、语法）和运行期错误（API 缺失、组件不渲染）是两类，要分别抓
- 运行期那部分需要微信开发者工具——属人工核验环节

**Alternatives considered**:
- 只看编译期 → 漏掉运行时问题（地图、API、定位都是运行时才暴露）

---

## 综合结论

无 NEEDS CLARIFICATION 遗留。关键利好：现有代码已有平台守卫，编译跑通风险较低。可进入 Phase 1。
后续 spec（地图适配 / 信源外链 / 后端网络层 / 导航 / AI 标注）均以本 spec 的差异清单为输入。
