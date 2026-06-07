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

## 🚀 快速开始（Docker，推荐）

> 前置：已安装 [Docker](https://www.docker.com/) 与 Docker Compose。

**1. 克隆并配置环境变量**

```bash
git clone https://github.com/roam-bit/camping-intel.git
cd camping-intel
cp .env.example .env
```

**2. 填入你自己的 API key**

编辑 `.env`，至少填 `ARK_API_KEY`（火山方舟）和 `AMAP_WEB_KEY`（高德）。
申请入口见 [`.env.example`](.env.example) 顶部注释，或下方 [API key 申请](#-api-key-申请)。

**3. 启动全部服务**（postgres + redis + 后端 + 前端）

```bash
docker compose -p camping_ai up -d
```

**4. 初始化数据库表**（首次必做，否则查询会报表不存在）

```bash
docker compose -p camping_ai exec api alembic upgrade head
```

**5. 访问**

- 前端 H5：<http://localhost:10086>
- 后端健康检查：<http://127.0.0.1:8000/api/v1/health>

> 💡 填占位 key 也能启动，但 AI 搜索链路会降级/报错——要真正出结果，必须填真实 key。

---

## 🔑 API key 申请

| key | 用途 | 申请地址 | 是否必填 |
|---|---|---|---|
| `ARK_API_KEY` | AI 联网搜索 + 内容整理 | <https://console.volcengine.com/ark/> | ✅ 必填 |
| `AMAP_WEB_KEY` | 后端地理编码（地名→坐标） | <https://console.amap.com/> | ✅ 必填 |
| `AMAP_JS_KEY` + `AMAP_JS_SECURITY_CODE` | 前端地图渲染 | 同上（高德控制台建「Web端 JS API」类型 key） | ✅ 必填 |
| `DEEPSEEK_API_KEY` | 多模型对比评测 | <https://platform.deepseek.com/> | ⬜ 可选 |

> 高德 key 通过**域名白名单**保护，前端 key 暴露在浏览器是正常的——记得在高德控制台绑定你的部署域名。

---

## 🛠️ 手动开发（不用 Docker）

<details>
<summary>展开本地分别启动前后端</summary>

**后端**（需本机有 PostgreSQL+PostGIS 与 Redis，或用 `docker compose up postgres redis`）：

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# 可选：信源深度抓取需要 Chromium（约 200MB）
python -m playwright install chromium
alembic upgrade head
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
│   └── tests/             # pytest
├── docs/                  # 设计文档（见下）
├── docker-compose.yml     # postgres + redis + api + frontend 一键编排
└── .env.example           # 环境变量模板
```

---

## 📚 设计文档

本项目用 [Spec-Driven Development](https://github.com/github/spec-kit) 流程开发，保留了部分设计文档作为参考：

- [docs/AI搜索约束设计.md](docs/AI搜索约束设计.md) —— AI 链路如何约束 LLM 保证「来源可信 + 坐标可信」（核心设计思路）
- [docs/specs/005-precise-geocoding/](docs/specs/005-precise-geocoding/) —— 精确地理编码 spec
- [docs/specs/017-amap-geo-fallback/](docs/specs/017-amap-geo-fallback/) —— 地名识别高德兜底 spec（完整的 spec → plan → tasks → contracts 范例）
- [docs/PRIVACY-TEMPLATE.md](docs/PRIVACY-TEMPLATE.md) —— 隐私政策模板（部署上线前替换占位符）

> 部分设计文档为产品早期记录，引用的代号 / 文件名可能与当前代码不完全一致，仅供理解设计思路。

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
