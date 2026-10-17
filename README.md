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
│   │   ├── api/v1/          # 路由：auth、records
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
│   │   ├── api/             # Axios 实例与接口封装
│   │   ├── components/ui/   # Button / Input / Card / Toast / Skeleton
│   │   ├── composables/     # 登录页拓扑装饰动画
│   │   ├── router/          # 路由与登录守卫
│   │   ├── stores/          # Pinia：auth、toast
│   │   ├── styles/          # 设计 token 与组件样式
│   │   └── views/           # LoginView / WorkspaceView
│   ├── package.json
│   └── vite.config.ts
├── 设计文档.md
├── DEVELOPMENT_LOG.md
└── README.md
```

## 环境要求

- Python **3.12**（3.13 / 3.14 部分依赖尚无预编译 wheel，安装会失败）
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

## 测试

```bash
cd backend
.venv\Scripts\python.exe -m pytest    # 21 个用例
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

## 后续阶段

拖拽式拓扑编辑器 → CSV 上传与预处理 → 训练实时可视化 → LLM 助教与 Agent 调参。
详见 [设计文档.md](./设计文档.md) 第 8 章。
