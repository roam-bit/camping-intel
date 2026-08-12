# Research: 彻查并修复微信小程序地图 marker 渲染崩溃

**Feature**: 014-fix-weapp-map-crash | **Date**: 2026-05-22

---

## 根因（FR-002 / SC-006：须「已验证」结论，不接受推测当定论）

### 崩溃链条

1. 微信原生 `<map>` 有 `include-points` 属性：传一组坐标点，地图自动缩放视野把它们全包进画面。
2. `include-points` 变化 → 触发原生组件内部观察器 `pointsChanged` → 调 `fitBounds` 算包围框。
3. `fitBounds` 对**空数组无防护**：无点位时仍访问「首个点的 `.lat`」，首个点是 `undefined` → `Cannot read property 'lat' of undefined`。
4. 本项目 React 代码 `frontend/src/components/MapCanvas.weapp.tsx` 自 spec-013 起已**不传** `includePoints` prop。
5. 但 Taro 4 的 `<Map>` 组件在 `@tarojs/shared` 把 `include-points` 的默认值硬编码为 `DEFAULT_EMPTY_ARRAY`（值即 `'[]'`）。模板生成器 `createMiniComponents` 对「带默认值的属性」产出的 WXML 绑定，在 React 层未传时（运行时数据 `i.includePoints` 为 `undefined`）会**代入 `[]`**。
6. → 编译出的小程序原生 `<map>` **永远收到 `include-points=[]`** → 每次渲染触发 `pointsChanged` → `fitBounds([])` → 崩溃。

### 证据分级（区分「已验证」与「推断」）

| 环节 | 等级 | 依据 |
|---|---|---|
| Taro 给 `include-points` 默认值 `[]` 并在编译期强制注入 | ✅ 已验证 | 直读 Taro 源码：`@tarojs/shared/dist/components.js`（`'include-points': DEFAULT_EMPTY_ARRAY`，`DEFAULT_EMPTY_ARRAY = '[]'`）+ `template.js` 的 `createMiniComponents`——该默认值经其 3 条可能分支（对象字面量 / 数字 / 兜底）产出的绑定，在 `i.includePoints === undefined` 时**都**代入 `[]` |
| 崩溃栈为 `fitBounds ← pointsChanged` | ✅ 已验证 | 上次会话微信开发者工具实测记录 |
| 空 `include-points` 致腾讯地图 SDK 崩 | ✅ 已验证 | spec-012 实施期实测踩坑记录 |
| 上述三者合龙 = 本 bug 根因 | 🔵 强推断 | 三条独立证据互相吻合，且能解释所有此前失败的修复尝试；最终因果留待实现后微信开发者工具核验（SC-002）|

### 为什么 spec-012 / spec-013 / 换基础库都没修好（两次被证伪的定位）

- spec-012「无点位时改传 `undefined`」、spec-013「移除 `includePoints` prop」——都在 **React 层**动手；但 Taro 在**编译层**用默认值把 `[]` 重新注入，React 层做什么都被覆盖、根本到不了原生 `<map>`。
- 换稳定基础库无效——这不是基础库 bug，是「空数组喂给 `fitBounds`」的输入问题，与基础库版本无关。
- 教训：根因要查到「能解释所有反例」才算坐实（见错题本 2026-05-22 条）。本 spec 的根因已能解释三次失败尝试，故 FR-002 满足。

---

## D1：修复方案——始终给 `include-points` 喂非空有效点

**Decision**：既然 Taro 必然向原生 `<map>` 传 `include-points`、React 层无法阻止——反向解决：让 `MapCanvas.weapp.tsx` **显式传 `includePoints`，并保证它永远是 ≥2 个有效坐标点的非空数组**。
- 有 marker → `includePoints` = 各 marker 的坐标。
- marker 数 < 2（0 或 1 个）→ 用「围绕当前中心点的 2 个合成点」补齐到 ≥2。中心按优先级取：搜索中心 → 用户定位 → 杭州默认。
- 合成点 = 中心 ± δ；δ 按场景取值（初始 / 定位成功 / 搜索），借此控制缩放粗细——替代原 `DEFAULT/LOCATED/SEARCH_SCALE` 三档。

**Rationale**：
- `include-points` 非空 → `fitBounds` 不再读到 `undefined` → 崩溃从源头消除。
- 这正是 `<map>` `include-points` 的设计用途（自动 fitView）——把工具用对，而非绕开。

**为什么 ≥2 而非 ≥1**：spec-013 注释称「点位 ≤1 时崩」。该说法未经独立验证（spec-013 的其它判断已被证伪），本方案**不赌它真假**：统一补齐到 ≥2，则无论「≤1 崩」是真是假都安全。运行时核验会顺带确认 1 点行为（见 quickstart B）。

**Alternatives considered**：见 D3。

---

## D2：移除 spec-013 手写的 `viewForMarkers` + 受控 `view` state

**Decision**：删除 `MapCanvas.weapp.tsx` 里的 `viewForMarkers()` 函数和 `useState` 的 `view`（受控 longitude/latitude/scale）。地图视野改由 `include-points` 单一驱动；`<Map>` 的 `longitude/latitude` 仅保留一个初始中心值（`<map>` 必填项）。

**Rationale**：
- `viewForMarkers` 是 spec-013 基于「`include-points` 坏了、点位 ≤1 必崩」这一**错误判断**手写的替代品。根因查清后该前提已不成立。
- 非空 `include-points` 必然触发 fitView；若再并存一套受控 `view`，就是 spec-012 D4 明确警告过的「两套视野控制互相打架」。须二选一——选 `include-points`（原生、设计如此、代码更少）。
- 留着 `viewForMarkers` = 死代码 / 误导后来者。删除它属于「清理被本次修复变得过时的代码」，不是额外重构。

**Alternatives considered**：
- 保留 `view` + 另加非空 `includePoints`：否——两套机制并存，最终视野由谁定不可预测，且 `view` 沦为 vestigial 死代码。

---

## D3：被否决的替代方案

| 方案 | 否决理由 |
|---|---|
| 改 Taro 组件配置、去掉 `include-points` 的默认值 | 需改 Taro 编译层内部约定，随 Taro 版本漂移；影响全局所有 `<map>`；且「绑定成 `undefined` 是否也崩」未验证。脆弱、不适合编程小白长期维护 |
| 换地图方案（spec FR-003 兜底）| 根因证明原生 `<map>` 可修——崩溃是「输入空数组」问题，非组件能力缺陷 → FR-003 的「换方案」兜底**不触发** |

---

## D4：H5 零回归

**Decision**：本 spec 仅改 `frontend/src/components/MapCanvas.weapp.tsx` 一个文件。H5 端走 `MapCanvas.tsx`（高德 JS API，spec-012 D1 拆成的独立平台文件），一字不动。

**Rationale**：Taro 分平台文件机制下，weapp 构建只取 `.weapp.tsx`、H5 构建只取 `.tsx`——改 weapp 文件结构上不可能影响 H5。零回归从结构上成立，不靠「我小心点」。

---

## 小结

| 维度 | 结论 |
|---|---|
| 根因 | Taro 编译层给原生 `<map>` 强制注入 `include-points=[]` → `fitBounds([])` 崩（机制已验证，因果为强推断）|
| 修复 | D1 始终喂 ≥2 个有效点；D2 删 `viewForMarkers`、视野改由 `include-points` 单一驱动 |
| FR-003 兜底 | 不触发——原生 `<map>` 可修 |
| H5 零回归 | 只改 weapp 文件，H5 文件不碰 |
| 改动面 | 1 个前端文件 |
| 最大不确定性 | `fitBounds([≥2 点])` 确不崩 + `include-points` 单一驱动视野的实际表现——实现后微信开发者工具核验（quickstart / SC-002/003）|

---

## 实现期实测补充（2026-05-22 收尾）

> 上面 D1/D2 是 plan 阶段的设想；实现 + 微信开发者工具实测后有重大修正，记录如下。

### 实测发现根因 2：声明式 include-points 会「锁死」视野

微信原生 `<map>` 一旦挂载，**声明式 `include-points` 属性会把视野锁死**——之后 `include-points` 改值、命令式 `MapContext.includePoints`（返回 ok 但无视觉效果）、受控 `longitude/latitude` 全都压不动它（命令式诊断日志实测确认）。

→ D2「视野由 `includePoints` 单一驱动」不可行；中途试过的「命令式 `includePoints` 更新」也无效。

### 最终修法（受控视野）

- `include-points` 降级为**固定不变的非空常量 `CRASH_GUARD_POINTS`**——仅作崩溃护栏（顶掉 Taro 注入的空数组），不参与视野控制。
- 地图视野改由**受控 `longitude/latitude/scale`** 驱动，恢复 `viewForMarkers` 包围盒算法。`<map>` 对受控经纬度/缩放的更新可靠响应（前提：`include-points` 不再变）。

### 验证结果（微信开发者工具 + 真机）

| 项 | 结果 |
|---|---|
| 崩溃（`fitBounds` 读 undefined.lat）| ✅ 已消除——实测无 `Cannot read property 'lat'` |
| 视野跟随定位更新 | ✅ 实测通过——定位回来地图正确缩放到用户位置 |
| 真机定位准确 | ✅ 用户真机验证正确（模拟器偏差 = 微信开发者工具的 IP 模拟定位，非 bug）|
| marker 渲染 | 代码无误（沿用 spec-012、与 H5 同款）；未「实测看见」——DB 临平 80km 内唯一点位信源是 2023 年、被前端「近一年」时间筛选 `inTimeRange` 正确剔除，属测试数据陈旧、非代码缺陷 |
