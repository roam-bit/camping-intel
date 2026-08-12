# Research: 修复微信小程序端点位数据加载不出来

**Feature**: 013-fix-weapp-data-load | **Date**: 2026-05-22

---

## 根因分析（已查证 vs 假设）

### ✅ 已查证（读码确认）——主问题：点位永不加载

- `frontend/src/pages/index/index.tsx` 约 99-109 行 useEffect（依赖 `[locationStatus]`）：
  - `locationStatus === 'denied'` → 弹 toast，**不加载**
  - `locationStatus === 'error'` → 弹 toast，**不加载**
  - `locationStatus === 'ok'` → `loadPlaces()`
- `frontend/src/hooks/useUserLocation.ts`：`Taro.getLocation` 失败时 `.catch` 把 status 设为 `denied`/`error`，但 `coord` 仍是杭州默认（`HANGZHOU_FALLBACK`）——**兜底坐标一直在，只是没人用**。
- `frontend/src/hooks/usePlaces.ts`：`loadPlaces` 直接用传入的 `userCoord` 调 `getPlaces`——它**不挑**坐标是真实还是默认，给什么用什么。
- 结论链：小程序定位失败（见下）→ `locationStatus` 到 `error`/`denied`，永不 `ok` → useEffect 永不调 `loadPlaces()` → 点位永不加载 → Network 无请求、地图无 marker。

### ✅ 已查证——小程序定位为什么必失败

- `frontend/src/app.config.ts` 当前内容只有 `pages` + `window`，**无 `permission`、无 `requiredPrivateInfos`**。
- 现代微信小程序：调 `wx.getLocation` 前必须在 app 配置里声明 `requiredPrivateInfos: ['getLocation']`，并在 `permission` 里声明 `scope.userLocation`。未声明 → `wx.getLocation` 无法正常工作。

### 🤔 假设（未证实）——`Error: timeout`

- Console 那条**未被捕获**的 `Error: timeout`（栈在 `WAServiceMainContext`）——`useUserLocation` 的 `.catch` 能接住 promise 拒绝，所以它不是被接住的那条。
- 假设：`wx.getLocation` 因缺权限声明而**挂起**（既不回调成功也不回调失败）→ 微信运行时对挂起的 API 调用做超时 → 抛出未被业务代码接住的 `Error: timeout`。
- 该假设**未证实**。本 spec 的处理方式：① D1 补权限声明让 `getLocation` 正常；② D3 加超时保护让挂起也能收尾。预期二者合力消除它；实现后在微信开发者工具核验确认（若仍在，再查）。

---

## D1：补微信定位权限声明

**Decision**：`app.config.ts` 的 `defineAppConfig` 里加：
- `permission: { 'scope.userLocation': { desc: '用于在地图上显示你附近的露营/驻车点位' } }`
- `requiredPrivateInfos: ['getLocation']`

**Rationale**：这是微信小程序调用 `wx.getLocation` 的硬性前置。`desc` 是授权弹窗里给用户看的用途说明。两项都是 **weapp-only 配置**——H5 构建忽略它们，对 H5 零影响。

**Alternatives considered**：不声明、只靠 D2 兜底——否。那样小程序用户永远拿不到真实定位、连授权弹窗都见不到（US3 不达成）。声明是正路。

---

## D2：解耦「加载点位」与「定位成功」（修复主体）

**Decision**：改 `index.tsx` 的定位 useEffect——`ok`/`denied`/`error` **三种终态都调 `loadPlaces()`**。`denied`/`error` 的 toast 提示保留。`loadPlaces()` 用的 `userCoord` 来自 `useUserLocation`：定位成功是真实坐标，失败则是杭州默认——两种都能加载点位。

**Rationale**：
- 当前「只有 `ok` 才加载」把数据加载和定位成功死绑，是这个 bug 的本质。
- `useUserLocation` 早就有杭州兜底坐标，`usePlaces.loadPlaces` 也照单全收任意坐标——基础设施都在，只差「在失败分支也调一次」。
- 改动极小、风险低：失败分支只是多调一个已有函数。

**Alternatives considered**：
- 组件 mount 时立即用默认坐标 `loadPlaces()`、定位回来再 reload：也可行，但会产生一次「默认→真实」的双加载；且代码里有「初始不再 loadPlaces」的历史注释，按终态触发更贴合现有设计。
- 把判断塞进 `usePlaces`：否——加载时机是页面级编排逻辑，属 `index.tsx`。

---

## D3：`useUserLocation` 加定位超时保护

**Decision**：`useUserLocation` 里给 `Taro.getLocation` 包一层超时——用 `Promise.race([Taro.getLocation(...), 超时Promise])`，超时（如 8 秒）则按失败处理（status → `error`，coord 保持杭州默认）。

**Rationale**：
- 防御 `Taro.getLocation` 挂起（既不 resolve 也不 reject）导致 `locationStatus` 永远卡在 `pending` → 即使 D2 改好了，终态都到不了、`loadPlaces` 仍不触发。
- 这也是对假设 D4 的兜底：就算 `wx.getLocation` 真的挂起，超时保护会主动收尾到 `error`，应用照常走兜底加载，不会干等、不会留一个挂起的调用。
- 对 H5 同样有意义——浏览器 geolocation 也可能迟迟不返回。

**Alternatives considered**：只靠浏览器/微信自带的定位超时——否。两端自带超时行为不一、且不可控；自己用 `Promise.race` 兜一个确定的上限最稳。

---

## D4：`Error: timeout` 怎么处理

**Decision**：不预设修法。D1（权限声明）+ D3（超时保护）落地后，在微信开发者工具核验 Console 是否还有未被捕获的 `Error: timeout`：
- 若消失 → 假设成立，完成。
- 若仍在 → 再查（用 Network/Sources 面板定位抛出点），按 spec FR-005「消除或妥善捕获」处理。

**Rationale**：根因未证实（research 开头已标）。不在根因坐实前预设「改哪一行」——避免重蹈 spec-010「建在未验证根因上」的覆辙（见错题本）。spec FR-005 是结果导向（无未捕获报错），给了处理这条假设的空间。

---

## D5：H5 零回归

**Decision**：
- D1 的 `permission`/`requiredPrivateInfos` 是 weapp-only，H5 构建忽略 → H5 无影响。
- D2：H5 定位成功（`ok`）路径——仍是 `loadPlaces()`，**行为完全不变**；H5 定位失败（`denied`/`error`）——现在也会 `loadPlaces()`，这是**修复**（H5 同样有「定位失败就空白」的隐患），不是回归。
- D3 超时保护对 H5 一致生效，行为更稳健、不改变定位成功时的结果。

**Rationale**：H5 定位成功路径一行不动 = 零回归硬约束满足；失败路径的改善是正向的。

---

## 小结

| 维度 | 结论 |
|---|---|
| 主根因 | 已查证：`loadPlaces` 只在定位 `ok` 时触发 + 小程序定位因缺权限声明必失败 |
| 修复主体 | D2 解耦——失败终态也加载点位（用杭州兜底坐标）|
| 最大不确定性 | D4 `Error: timeout` 根因未证实——D1+D3 预期消除，实现后微信开发者工具核验 |
| H5 零回归 | D2 让 H5 定位成功路径一行不动；其余改动对 H5 无害或正向 |
| 新增依赖 | 无 |
