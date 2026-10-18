# DeepVision

可视化深度学习实验平台 —— 拖拽搭建神经网络、上传 CSV 数据、实时观察训练过程，并由 LLM 助教给出结构与超参建议。

- 设计文档：[设计文档.md](./设计文档.md)
- 开发日志：[DEVELOPMENT_LOG.md](./DEVELOPMENT_LOG.md)

## 技术栈

| 层 | 技术 |
| --- | --- |
| 前端 | Vue 3 + TypeScript + Vite + Pinia + Vue Router + TailwindCSS + Axios |
| 后端 | FastAPI + SQLAlchemy 2 + Alembic + Pydantic v2 |
| 认证 | JWT（PyJWT）+ argon2id 密码哈希 |
| 数据库 | SQLite（开发）/ PostgreSQL（生产） |

## 项目结构

```
DeepVision/
├── backend/
│   ├── app/
│   │   ├── api/v1/          # 路由：auth、records、graph
│   │   ├── core/            # 配置、安全（argon2 + JWT）、当前用户依赖
│   │   ├── db/              # 引擎、会话、声明式基类
│   │   ├── models/          # User / Dataset / TrainingRecord
│   │   ├── schemas/         # Pydantic 请求与响应模型
│   │   └── main.py          # 应用入口
│   ├── alembic/             # 数据库迁移
│   ├── tests/               # 接口测试
│   ├── alembic.ini
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── api/             # Axios 封装：auth、records、graph
│   │   ├── components/
│   │   │   ├── canvas/      # 画布、节点、节点库、属性面板、小地图、工具栏
│   │   │   └── ui/          # Button / Input / Card / Toast / Skeleton
│   │   ├── composables/     # 画布视口、登录页装饰动画
│   │   ├── router/          # 路由与登录守卫
│   │   ├── stores/          # Pinia：auth、toast、graph
│   │   ├── styles/          # 设计 token 与组件样式
│   │   ├── types/           # 拓扑类型与 model_config 契约
│   │   └── views/           # LoginView / WorkspaceView
│   ├── package.json
│   └── vite.config.ts
├── 设计文档.md
├── DEVELOPMENT_LOG.md
└── README.md
```

## 环境要求

- Python 3.12+（后端已在 3.12 与 3.14 上验证通过；后续 PyTorch 等依赖对 3.14 支持可能滞后，推荐 3.12）
- Node.js 18+

## 后端

```bash
cd backend

python -m venv .venv
# Windows (PowerShell)
.venv\Scripts\Activate.ps1
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env          # Windows: copy .env.example .env
alembic upgrade head          # 建表
uvicorn app.main:app --reload # http://127.0.0.1:8000
```

接口文档：http://127.0.0.1:8000/docs

## 前端

```bash
cd frontend
npm install
npm run dev                   # http://localhost:5173
```

开发期 Vite 已把 `/api` 代理到 `http://127.0.0.1:8000`，无需额外配置跨域。

## 测试账号（本地开发）

执行 `alembic upgrade head` 建表后，用种子脚本创建或重置测试账号：

```bash
cd backend
.venv\Scripts\python.exe scripts/seed_test_user.py                          # 默认 admin / 123456
.venv\Scripts\python.exe scripts/seed_test_user.py --username demo --password demo123456
```

| 用户名 | 密码 |
| --- | --- |
| `admin` | `123456` |

脚本可重复执行（账号已存在则重置密码），密码始终以 argon2id 哈希入库、不存明文。

> 弱口令仅用于本地开发。本仓库为公开仓库，部署到公网前请删除该账号或更换密码。

## 测试

```bash
cd backend
.venv\Scripts\python.exe -m pytest    # 32 个用例
```

## 已实现（阶段一）

- 用户注册、登录、`/api/auth/me`
- JWT 签发与校验；密码 argon2id 哈希，绝不落明文
- 训练记录 CRUD、分页、按时间倒序、归属校验（越权返回 403）
- 统一错误体 `{ code, message, detail }` 与 401 / 403 / 404 / 409 / 422 语义
- 登录页：深色科技风、浮动标签、密码强度、字段校验与服务端错误两种错误态
- 路由守卫：未登录访问 `/workspace` 自动重定向 `/login`
- Axios 拦截器：自动携带 Token，401 自动清理凭证并跳转登录，失败统一 Toast
- 基础组件库：Button / Input / Card / Toast / Skeleton

## 已实现（阶段二）

- 画布编辑器：SVG 渲染、点阵网格、贝塞尔连线
- 节点库拖拽入画布（也可点击添加到中央）
- 节点拖动、属性面板实时编辑（输入 / 隐藏 / 输出三类参数）
- 连线交互：从输出端口拖出，成环、自连、重复连线被拒绝并给出提示
- 缩放 25%–400%（以光标为锚点）、空格或中键平移、小地图导航
- 撤销 / 重做 50 步；Delete 删除；Ctrl+Z / Ctrl+Y / Ctrl+S
- 空状态引导与「三层 MLP 快速模板」
- 草稿 2s 防抖自动保存到 localStorage，刷新后可恢复
- 支持分支与汇合（任意前馈 DAG），汇合节点按特征维 `concat` 合并
- 后端 `POST /api/graph/validate`：成环、自连、重复连线、悬空引用校验，并返回执行计划（拓扑序 + 前驱）

## 主要接口

| 方法 | 路径 | 说明 | 认证 |
| --- | --- | --- | --- |
| POST | `/api/auth/register` | 注册 | 否 |
| POST | `/api/auth/login` | 登录，返回 JWT | 否 |
| GET | `/api/auth/me` | 当前用户 | 是 |
| GET | `/api/records` | 训练记录列表（分页） | 是 |
| POST | `/api/records` | 保存训练记录 | 是 |
| GET | `/api/records/{id}` | 记录详情 | 是 |
| DELETE | `/api/records/{id}` | 删除记录 | 是 |
| POST | `/api/graph/validate` | 校验网络拓扑结构 | 是 |

## 后续阶段

拖拽式拓扑编辑器已完成。后续：CSV 上传与预处理 → 训练实时可视化 → LLM 助教与 Agent 调参。
详见 [设计文档.md](./设计文档.md) 第 8 章。
