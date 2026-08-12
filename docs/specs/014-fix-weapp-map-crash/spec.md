# Feature Specification: 彻查并修复微信小程序地图 marker 渲染崩溃

**Feature Branch**: `014-fix-weapp-map-crash`

**Created**: 2026-05-22

**Status**: Draft

**Input**: User description: "微信小程序首页地图 `<map>` 渲染层崩溃 `Cannot read property 'lat' of undefined`（栈在腾讯地图 SDK fitBounds ← pointsChanged），导致点位 marker 显示不出来。空 includePoints、includePoints 本身、灰度基础库 均已排除。根因未知，本 spec 须做真正的根因调查后再修；若原生 <map> 走不通可转为重新评估地图方案。"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 小程序地图正常显示点位 marker（Priority: P1）

用户在微信小程序首页，希望地图上能看到代表露营/驻车点位的 marker——而现在地图组件一加载点位就**渲染层崩溃**（`Cannot read property 'lat' of undefined`），marker 显示不出来。点位数据其实已经成功加载（spec-013 打通了），但用户在地图上看不到任何点。

**Why this priority**：P1，这是「小程序地图能不能用」的最后一道坎。数据通了、地图底图也有了，就差 marker——marker 崩溃，等于地图功能在小程序端依然废着。

**Independent Test**：微信开发者工具打开小程序首页（当前位置有点位数据），地图上出现点位 marker，Console 无 `Cannot read property 'lat'` 渲染层崩溃。

**Acceptance Scenarios**:

1. **Given** 小程序首页加载、当前区域有点位数据，**When** 地图渲染，**Then** 点位 marker 正常显示在地图上，无渲染层崩溃
2. **Given** 地图上有 marker，**When** 用户点击某 marker，**Then** 打开该点位详情（与 spec-012 设计一致）
3. **Given** 当前区域 0 个点位 / 仅 1 个点位 / 多个点位，**When** 地图渲染，**Then** 三种情况都不崩溃（崩溃疑与点位数量相关，须都覆盖）

---

### User Story 2 - H5 端零回归（Priority: P1）

开发者希望本次为修小程序地图崩溃所做的改动**不破坏 H5 端**——H5 用高德 JS API、与小程序 `<map>` 是两套实现，理论上不受影响，但须确认。

**Why this priority**：P1，H5 是已上线形态，零回归是硬约束。

**Independent Test**：`build:h5` 成功；H5 首页地图、marker、交互与改动前一致。

**Acceptance Scenarios**:

1. **Given** 本 spec 完成，**When** 跑 H5 构建并打开首页，**Then** H5 地图与 marker 与改动前一致

---

### Edge Cases

- 点位数量边界：0 / 1 / 多个——崩溃疑与「点位很少时算视野/边界」相关，三种数量都须验证不崩
- marker 数据字段异常（坐标缺失/越界/格式不符地图组件预期）——单个坏数据不应拖垮整张地图
- 若调查证明原生 `<map>` 组件在本项目用法下根本无法稳定显示 marker：本 spec 须能转向「换地图方案」，而不是无限期卡在原生 `<map>` 上
- 地图组件 / 地图 SDK 的报错栈里没有应用代码——根因须靠调试工具定位，不能靠猜

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 微信小程序地图 MUST 能正常渲染点位 marker，且 MUST NOT 出现 `Cannot read property 'lat'` 渲染层崩溃
- **FR-002**: 本次修复 MUST 建立在**查清并验证过的根因**之上——根因结论须标「已验证」，不接受推测当定论（前两次定位 includePoints / 灰度基础库 均已被证伪，不可再凭猜测改）
- **FR-003**: 若根因调查证明微信原生 `<map>` 组件在本项目用法下无法稳定承载点位 marker，系统 MUST 改用可行的替代地图方案达成 marker 显示——由调查结论驱动该决策，不预设一定能在原生 `<map>` 上修好
- **FR-004**: 点击 marker MUST 能打开点位详情，行为与 spec-012 设计一致
- **FR-005**: 系统 MUST 在 0 个 / 1 个 / 多个点位三种数量下都不崩溃
- **FR-006**: 系统 MUST 保持 H5 端零回归——H5 地图、marker、交互与改动前一致；`build:h5` 正常
- **FR-007**: 系统 MUST NOT 改动后端、spec-013 已完成的数据加载链路、AI 搜索的后端出网问题

### Key Entities

- **地图 marker**：点位在小程序地图上的可视标记；本 spec 要让它能渲染出来、不崩溃
- **崩溃根因**：`<map>` 组件 / 地图 SDK 内部 `fitBounds` 读 `undefined.lat` 的确切触发条件——本 spec 的首要产出是「查清它」
- **地图方案**：当前为微信原生 `<map>`（腾讯底图）；若被证不可行，可能切换为其它方案

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 微信开发者工具小程序首页（区域有点位），地图显示点位 marker——人工核验，可见
- **SC-002**: 微信开发者工具 Console 无 `Cannot read property 'lat'` 渲染层崩溃——0 次
- **SC-003**: 0 / 1 / 多个点位 三种场景下，小程序地图均不崩溃——三场景人工核验均通过
- **SC-004**: 点击地图 marker 能打开对应点位详情——人工核验
- **SC-005**: H5 端地图与 marker 与改动前肉眼一致；`build:h5` 成功
- **SC-006**: 崩溃根因有一份「已验证」的结论记录（research.md），不是推测

## Assumptions

- spec-009/010/011/012/013 已完成：小程序能编译、首页框架与地图底图可见、网络层就绪、点位数据能加载
- 后端正常、点位数据能加载——本 spec 只解决「marker 渲染崩溃」，不碰数据链路
- 微信开发者工具基础库保持稳定版（非灰度版）——灰度版 3.16.1 已知会带来无关的 `Error: timeout`
- 根因调查须用微信开发者工具的断点调试 / Sources 面板 / 二分法（逐步增减 marker 字段或数量）定位——属 plan/research 阶段的核心工作
- 验证靠 `build:weapp` + 微信开发者工具人工核验 / `build:h5` + H5 人工核验；前端无单测设施
- 本 spec 不预设修法——是「先查清、再决定怎么修」，可能的结局包含「换地图方案」
