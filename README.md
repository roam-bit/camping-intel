# 🏕️ Camping Intel · AI 驻车露营情报助手

> 搜索驱动的 AI 露营 / 驻车点位地图。
> **用户自然语言查询 → AI 联网整理公开信源 → 用户一键求证 → 跳转导航。**

一个开源的「AI 整理 + 人工求证」式露营情报工具：你说「景德镇周边免费露营地」，AI 联网搜索公开网页、抽取出带**真实来源链接**的候选点位铺在地图上，每个结论都能点开原始信源自己核验，确认后一键跳高德导航。

> ⚠️ **信息仅供参考**：AI 整理的内容可能有误或过时，**前往任何点位前请通过信源链接自行核验**，并遵守当地法律法规。

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Frontend](https://img.shields.io/badge/frontend-Taro%204%20%2B%20React%2018-61dafb.svg)
![Backend](https://img.shields.io/badge/backend-FastAPI%20%2B%20PostGIS-009688.svg)

---

## ✨ 核心理念

市面上的露营 App 多是「平台自己堆 POI 库」。本项目走另一条路——**AI 不负责凭空生成点位，只负责联网核验和解释**：

- **来源可追溯**：每个点位必须绑定真实的网络信源 URL，没有来源的点直接丢弃，杜绝 AI 编造
- **坐标可信**：AI 给坐标用 AI 坐标；没给则走高德地理编码兜底；定位不可信的点不入图，不用城市中心伪坐标凑数
- **求证闭环**：用户点开信源链接自行核验 → 确认后导航按钮变「已求证」态，把「信不信」的决定权交还用户

> AI 约束设计的完整思路见 [docs/AI搜索约束设计.md](docs/AI搜索约束设计.md)。

---

## 🧱 技术栈

| 层 | 技术 |
|---|---|
| 前端 | Taro 4 + React 18（一套代码编 H5 / 微信小程序双端）+ 高德地图 JS API |
| 后端 | FastAPI + SQLAlchemy(async) + Alembic |
| 数据库 | PostgreSQL + PostGIS（地理空间查询）|
| 缓存 | Redis |
| AI | 火山方舟 Ark / 豆包大模型（联网搜索 + 结构化抽取）|
| 地图 | 高德地图（渲染 / 地理编码 / 导航跳转）|

---

## 🗺️ 数据流

```
用户输入「景德镇露营地」
        │
        ▼
[前端 Taro] ──POST /api/v1/ai/search──▶ [后端 FastAPI]
                                            │
                          ┌─────────────────┼─────────────────┐
                          ▼                 ▼                 ▼
                  ① Ark 联网搜索      ② Ark 结构化抽取    ③ 高德地理编码
                  （带引用的回答）     （抽成候选点 JSON）   （地名→坐标兜底）
                          │                 │                 │
                          └─────────────────┴─────────────────┘
                                            ▼
                              过滤：无来源 / 泛标题 / 坐标偏离 → 丢弃
                                            ▼
                              入库 places(PostGIS) + 缓存 Redis(6h)
                                            ▼
[前端地图] ◀── 候选点 + 信源卡片 + AI 摘要 ── 用户点信源求证 ── 一键导航
```

---

## 🚀 快速开始

> 唯一前置：装一个 [Docker Desktop](https://www.docker.com/products/docker-desktop/)。
> Node、Python、PostgreSQL 全在容器里，**你一个都不用装**。

```bash
git clone https://github.com/roam-bit/camping-intel.git
cd camping-intel
docker compose up
```

浏览器打开 **<http://localhost:10086>**。Windows 用 PowerShell/CMD 同样这条命令。

首次 8-20 分钟（下载依赖），之后 30 秒。建表、导入数据都在容器启动时自动完成。

### 不填任何 API key 也能玩

仓库自带 **551 个真实点位 + 594 条信源**（`backend/seed_data/`），覆盖杭州、上海、北京、拉萨、新疆等地，全部由 AI 联网抓取沉淀而来，每个点位都能点开原始信源自行核验。

| 功能 | 不填 key | 说明 |
|---|---|---|
| 点位列表 / 详情 / 信源求证 / 导航跳转 | ✅ 完整可用 | 开箱即用 |
| 关键词搜索（查本地库） | ✅ 秒回 | 试试搜「杭州」「莫干山」 |
| 地图底图 | ❌ | 自动切到「列表」视图，内容一样全 |
| AI 联网搜**新**地点 | ❌ | 只查本地库，**不会崩** |

想要地图和 AI 搜索，编辑首次启动自动生成的 `.env` 填入真实 key（见下节），然后 `docker compose restart`。

> 🆘 遇到问题看 **[docs/学生快速启动.md](docs/学生快速启动.md)** —— 完整排错对照表、端口冲突处理、推倒重来的兜底方案。

---

## 🔑 API key 申请

**一个都不填也能跑**（见上节），下面这些是解锁地图和 AI 联网搜索用的：

| key | 用途 | 申请地址 | 不填会怎样 |
|---|---|---|---|
| `ARK_API_KEY` | AI 联网搜索 + 内容整理 | <https://console.volcengine.com/ark/> | 只查本地 551 个点位，不崩 |
| `AMAP_JS_KEY` + `AMAP_JS_SECURITY_CODE` | 前端地图渲染 | <https://console.amap.com/> 建「Web端 JS API」类型 key | 自动切列表视图，内容一样全 |
| `AMAP_WEB_KEY` | 后端地理编码（地名→坐标） | 同上，建「Web服务」类型 key | 生僻地名识别不出，常见地名走本地字典正常 |
| `DEEPSEEK_API_KEY` | 多模型对比评测 | <https://platform.deepseek.com/> | 无影响（评测脚手架才用） |

> 高德 key 通过**域名白名单**保护，前端 key 暴露在浏览器是正常的——记得在高德控制台绑定你的部署域名。

---

## 🛠️ 手动开发（不用 Docker）

<details>
<summary>展开本地分别启动前后端</summary>

⚠️ **Python 必须是 3.9–3.12，不能用 3.13+** —— `asyncpg` / `pydantic` 还没有对应的预编译包，
pip 会退化成现场编译并抛出几百行看不懂的 C 错误。走 Docker 完全不受这个影响（镜像自带 3.12）。

**后端**（需本机有 PostgreSQL+PostGIS 与 Redis，或用 `docker compose up postgres redis`）：

```bash
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# 可选：信源深度抓取需要 Chromium（约 200MB）
python -m playwright install chromium
alembic upgrade head
python scripts/load_seed_data.py    # 导入仓库自带的 551 个点位
uvicorn app.main:app --reload --port 8000
```

**前端**（Node 18+，安装需加 `--legacy-peer-deps`）：

```bash
cd frontend
npm install --legacy-peer-deps
npm run dev:h5      # H5 开发服务器，默认 http://localhost:10086
# npm run build:h5  # 构建生产 H5 产物到 dist-h5/
# npm run dev:weapp # 编译微信小程序（产物用微信开发者工具打开）
```

</details>

---

## 📁 项目结构

```
camping-intel/
├── frontend/              # Taro 4 + React 18（H5 + 小程序双端）
│   └── src/
│       ├── pages/         # 页面（首页地图 / 搜索 / 详情抽屉）
│       ├── components/    # 组件
│       ├── api/           # 后端接口封装
│       └── utils/         # 高德地图、坐标转换等工具
├── backend/               # FastAPI
│   ├── app/
│   │   ├── routers/       # 路由（ai 搜索 / places / 地理编码 / 二维码）
│   │   ├── services/      # AI 服务、高德服务、可信度评分、缓存、信源抓取
│   │   ├── models/        # SQLAlchemy 模型（place / source / feedback）
│   │   └── schemas/       # Pydantic 模型
│   ├── alembic/           # 数据库迁移
│   ├── seed_data/         # ⭐ 随仓库分发的 551 个点位 + 594 条信源
│   ├── scripts/           # 种子数据导入/导出、演示数据
│   └── tests/             # pytest（105 条）
├── docs/                  # 设计文档 + 上手指南（见下）
├── docker-compose.yml     # postgres + redis + api + frontend 一键编排
└── .env.example           # 环境变量模板（key 可留空）
```

前端另有 `e2e/`（12 条 Playwright 端到端回归测试，每条对应一个真实修过的 UI bug）。

---

## 📚 设计文档

### 上手 & 改造

- [docs/学生快速启动.md](docs/学生快速启动.md) —— 第一次跑先看这份：一条命令、没 key 能玩什么、完整排错对照表
- [docs/技术方案.md](docs/技术方案.md) —— 架构图、一次搜索请求的完整旅程、**5 个关键技术决策及其原因**、模块地图（标注哪些文件适合新手改、哪些是雷区）
- [docs/学生练手任务.md](docs/学生练手任务.md) —— 6 个难度递增的改造任务，具体到文件和验证方法

### 设计过程

本项目用 [Spec-Driven Development](https://github.com/github/spec-kit) 流程开发，`docs/specs/` 下保留了 **16 个功能规格**的完整留痕（spec → plan → tasks → contracts）：

- [docs/AI搜索约束设计.md](docs/AI搜索约束设计.md) —— AI 链路如何约束 LLM 保证「来源可信 + 坐标可信」（核心设计思路）
- [docs/specs/017-amap-geo-fallback/](docs/specs/017-amap-geo-fallback/) —— **推荐先读这个**。它记录了一次真实事故：用户搜「莫干山」，本地字典没有，调地图 API 返回了福建一个同名地点，搜索中心飞到 500 公里外，等 34 秒返回 0 结果。看一句用户抱怨如何变成带优先级的用户故事 + 可验收场景 + 性能护栏
- [docs/specs/009~016](docs/specs/) —— 一条完整的「H5 → 微信小程序移植」叙事线
- [docs/PRIVACY-TEMPLATE.md](docs/PRIVACY-TEMPLATE.md) —— 隐私政策模板（部署上线前替换占位符）

> 部分早期设计文档引用的代号 / 文件名可能与当前代码不完全一致，仅供理解设计思路。

---

## 🛣️ Roadmap

- [ ] POI 候选池 + AI 批量核验（让地图天然有更多点位）
- [ ] 本地缓存沉淀为产品资产（越用点位越多）
- [ ] UGC 链路（用户提交 + 内容审核）
- [ ] 微信小程序上线（ICP 备案 + AIGC 合规）

---

## 🤝 贡献

欢迎 Issue / PR。本项目处于早期迭代阶段，接口和数据结构可能变动。

## 📄 License

[MIT](LICENSE) © 2026 roam-bit

---

> 本项目整理的露营 / 驻车信息来自公开网络信源，**不对信源真实性作担保**，使用者需自行核验并对自己的出行行为负责。
