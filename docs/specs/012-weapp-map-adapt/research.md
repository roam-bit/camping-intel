# Research: 微信小程序地图层适配

**Feature**: 012-weapp-map-adapt | **Date**: 2026-05-21

本文件锁定 R2 的关键技术决策。所有 spec 中可能的 NEEDS CLARIFICATION 已在此解决。

---

## D1：MapCanvas 双端怎么拆

**Decision**：用 Taro 的多端文件约定拆分——**新增 `MapCanvas.weapp.tsx`（weapp 端），现有 `MapCanvas.tsx` 完全不动（H5/默认端）**。`MapCanvasProps` 接口抽到独立的 `MapCanvas.types.ts`，两端文件各自 import。

**Rationale**：
- Taro 编译时按平台选文件：weapp 构建解析 `import './MapCanvas'` → 命中 `MapCanvas.weapp.tsx`；H5 构建无 `.h5.tsx` → 回落到 `MapCanvas.tsx`。`index.tsx` 的 import 一字不改。
- H5 的高德逻辑是**命令式**（`new AMap.Map`、`marker.on('click')`、`ref` 持有句柄），weapp 的 `<Map>` 是**声明式**（props 驱动）——两套范式塞进一个文件靠 `TARO_ENV` 分支会很乱，且共享的 `ref`/`useEffect` 容易让改动溢出到 H5。
- 拆文件后 H5 的 `MapCanvas.tsx` **碰都不碰** → US4 零回归从结构上成立，不靠「我小心点」。
- `MapCanvasProps` 抽到 `MapCanvas.types.ts`：weapp 文件不能 `import from './MapCanvas'`（会循环解析到自己），抽出来最干净。`MapCanvas.tsx` 改为从 `./MapCanvas.types` import 该类型——这是唯一对 H5 文件的改动，纯类型、编译期、零运行时风险。

**Alternatives considered**：
- 单文件 + `TARO_ENV` 内部分支：否。命令式/声明式两范式混写，H5 回归风险高。
- 把 `MapCanvasProps` 在 weapp 文件里重新声明一遍：可行（结构化类型兼容），但有漂移风险，不如抽共享文件。

---

## D2：原生 `<map>` 组件的层级——别盖住浮层

**Decision**：依赖微信现代基础库对 `<map>` 的**同层渲染**能力，首页的搜索框/筛选栏/底部列表面板保持普通 `<View>`，不改成 `cover-view`。在微信开发者工具里核验确认浮层不被地图遮挡。

**Rationale**：
- 微信小程序的 `<map>` 是「原生组件」——由系统底层渲染，**老基础库里它层级最高、会盖住所有普通组件**。首页是「地图打底 + 搜索框/筛选栏/底部面板浮层」结构，老办法下浮层会被吞。
- 微信自基础库 2.x 起对 `<map>` 启用**同层渲染**：原生组件被纳入普通渲染层，普通 `<View>` 可以正常覆盖在地图上。当前微信基础库早已是 2.x/3.x。
- spec-010 已处理过基础库兼容、首页浮层已是普通 View → 本 spec 不改浮层结构，只验证。

**风险标注**：同层渲染是「依赖运行环境」的决策——必须在微信开发者工具实测确认（写进 quickstart）。若实测发现遮挡，回退方案是把被盖的浮层局部改 `cover-view`/`cover-image`（代价：`cover-view` 内只能放受限内容）。

**Alternatives considered**：
- 直接用 `cover-view` 包所有浮层：否。`cover-view` 限制多（只能嵌 `cover-view`/`cover-image`，样式受限），现代基础库不需要，是倒退。

---

## D3：marker 怎么显示「信源数」

**Decision**：weapp marker 用 `<map>` 的 `markers` 声明式数组，每个 marker = `iconPath`（点位图标）+ `callout` 或 `label`（显示信源数文字）。

**Rationale**：
- H5 端 marker 是自定义 HTML（`<div class="map-poi-marker">` 含图标 + 信源数 span）——原生 `<map>` 的 marker **不能塞任意 HTML/DOM**。
- 原生 marker 支持的字段：`iconPath`（图标图片）、`width/height`、`callout`（点上方气泡，可带文字）、`label`（marker 旁文字标签）、`customCallout`。
- 显示「信源数」这个数字：用 `callout`（常显气泡）或 `label`。spec FR-003 只要求「用户能看出信源数」，气泡/标签都满足。
- `iconPath` 需要一张真实图片：可新增一个简单的点位图标 PNG 放 `frontend/src/assets/`；或先用 `<map>` 默认 marker 图标 + `label` 显示数字。tasks 阶段二选一，优先简单。

**Alternatives considered**：
- `customCallout` + `cover-view` 自绘：能力更强但更复杂，本 spec 信息量（一个数字）用不上。

---

## D4：地图居中与 fitView

**Decision**：weapp `<Map>` 用**受控的 `longitude`/`latitude`/`scale`** 做「定位居中」和「无点位时居中到搜索中心」；用 **`includePoints`** 做「有点位时自动 fitView 到点位范围」。组件内用 state 响应与 H5 版相同的 props（`places`/`searchCenter`/`locationStatus`/`userCoord`）。

**Rationale**：
- 原生 `<map>` 的视野控制有两条路：① 受控 `longitude`+`latitude`+`scale`（精确指定中心+缩放）；② `includePoints`（传一组点，地图自动调视野把它们全包进来——等价于高德 `setFitView`）。
- 对应 spec US3 三种场景：
  - 定位成功 → 受控 center 设为用户坐标 + 合理 `scale`
  - 搜索有点位 → `includePoints` 设为所有 marker 点
  - 搜索无点位 → 受控 center 设为 `searchCenter`
- H5 版 `MapCanvas` 的三个 `useEffect`（init/setCenter/markers+fitView）逻辑可作为 weapp 版的行为参照，但实现从命令式改写成 state 驱动。

**注意**：`includePoints` 与受控 `longitude/latitude` 同时设会互相干扰——组件内按「有无点位」二选一驱动，避免两者打架（这正是 H5 版注释里踩过的坑：marker 优先 fitView、0 marker 才用 searchCenter）。

**Alternatives considered**：
- 用 `MapContext.moveToLocation` / `includePoints` 命令式 API：可作补充，但声明式 props 已够，优先声明式。

---

## D5：marker 点击 → 打开详情

**Decision**：每个 marker 带一个数字 `id`（= 该 place 在 places 数组的索引，或 place 的稳定数字 id）。`<Map onMarkerTap={e => ...}>` 事件回调拿到 `e.detail.markerId`，反查到对应 `place`，调用与 H5 一致的 `onMarkerClick(place)`。

**Rationale**：
- 原生 `<map>` 的 marker 点击不像高德能 `marker.on('click', ...)` 直接挂闭包——它给的是 `markerId`（必须是数字）。
- 用索引/稳定 id 做 `markerId`，回调里 `places[id]` 或 Map 查表反查 → 复用父组件传入的 `onMarkerClick`，行为与 H5 对齐（FR-004）。

---

## D6：「一键导航」在小程序端

**Decision**：`utils/amap.ts` 的 `openAmapNavigation` 加 `process.env.TARO_ENV` 分支——weapp 端改用 `Taro.openLocation({ latitude, longitude, name, scale })`，H5 端保持现有 `window.open` 高德 URL 不变。

**Rationale**：
- 现状 `openAmapNavigation` 用 `window.open` 打开高德网页导航 URL——小程序无 `window`，点了无反应。
- weapp 标准做法：`Taro.openLocation` 打开微信内置的位置查看页，用户在那里点「到这里去」会唤起系统地图导航。这是小程序里最稳的导航交接方式，无需额外 key/插件。
- 坐标传 `wgs84ToGcj02` 转换后的 GCJ-02（`Taro.openLocation` 要 GCJ-02）。
- H5 分支不动 → 导航在 H5 零回归。

**Alternatives considered**：
- 高德小程序导航 SDK：否，引入额外依赖，`Taro.openLocation` 已够。

---

## D7：坐标系

**Decision**：直接复用现有 `utils/coords.ts` 的 `wgs84ToGcj02`（经 `amap.ts` 的 `toAmapPosition` 暴露），不为小程序改任何坐标逻辑。

**Rationale**：
- `place.longitude/latitude` 是 WGS-84 原始坐标。H5 高德、微信 `<map>`（腾讯底图）、`Taro.openLocation` **都用 GCJ-02 火星坐标**。
- 现有 `wgs84ToGcj02` 转换对三者通用 → weapp marker 位置、地图中心、导航坐标都走同一个转换，零改造。

---

## 小结

| 维度 | 结论 |
|---|---|
| NEEDS CLARIFICATION | 无——7 项决策全部锁定 |
| H5 零回归保证 | 靠「H5 文件不碰」（D1 拆文件）从结构上成立 |
| 最大不确定性 | D2 同层渲染——依赖运行环境，必须微信开发者工具实测 |
| 新增依赖 | 无（`<Map>` 是 Taro 内置、`Taro.openLocation` 是 Taro 内置）|
