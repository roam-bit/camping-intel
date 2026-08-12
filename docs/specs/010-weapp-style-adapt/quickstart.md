# Quickstart: 微信小程序样式适配验证

**Feature**: 010-weapp-style-adapt | **Date**: 2026-05-21

本 spec 无单元测试（纯样式 + 存储 API）。验证 = 双端构建 + 人工核验。下面是改完后跑一遍的步骤。

---

## 前置

- spec-009 已完成：`frontend/project.config.json` 有 AppID、`config/index.js` 已按 `TARO_ENV` 分 `dist/`（weapp）与 `dist-h5/`（h5）
- 微信开发者工具已安装、能导入 worktree 下的 `frontend/` 目录

## 步骤 1：小程序构建 + 首页核验（验 US1 / SC-001 / SC-002 / SC-005）

```bash
cd frontend && npm run build:weapp
```

- 构建成功、0 报错
- 微信开发者工具打开 `frontend/`（确认选「不使用云服务」），模拟器加载首页
- **肉眼核验**首页框架元素全部可见、不塌陷不重叠：
  - [ ] 搜索框
  - [ ] 地图/列表模式切换
  - [ ] 结果分类 tab
  - [ ] 筛选栏
  - [ ] 底部列表/sheet 面板
- [ ] 地图区域为空白/占位——可接受，但不遮挡/挤占其它元素（SC-005）
- [ ] 切换「地图/列表」模式，对应视图正常显隐、不错乱
- [ ] 至少 2 种机型模拟器（如 iPhone 13 + 一款小屏机型）下都不塌陷、不与导航栏重叠（SC-002）

## 步骤 2：小程序控制台核验（验 US2 / SC-003）

- 微信开发者工具 Console 面板：
  - [ ] 无 `localStorage is not defined` 类报错
  - [ ] 无视口单位（`vh`/`vw`/`min()`）相关报错
- 在首页触发求证进度打点（点开信源详情），再重进首页：
  - [ ] 控制台无存储相关报错
  - [ ] 之前看过的信源进度能正确读回

## 步骤 3：H5 零回归核验（验 US3 / SC-004）

```bash
cd frontend && npm run build:h5
```

- [ ] `build:h5` 构建成功
- [ ] H5 首页布局/视觉与改动前肉眼一致——无错位、无塌陷
- [ ] H5 端求证进度功能与改动前行为一致（看过的信源高亮、计数正常）

## 通过标准

US1+US2+US3 三组 checklist 全勾 → spec-010 验收通过，可合并 main。

## 注意

- `build:h5` 与 `build:weapp` 输出已分目录（`dist-h5/` vs `dist/`），互不覆盖——但若曾误跑混，重跑对应命令即可。
- 微信开发者工具会实时回写 `project.config.json` 的部分字段，commit 前 `git add` 一下即可。
