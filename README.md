# DeepVision

可视化深度学习实验平台 —— 拖拽搭建神经网络、上传 CSV 数据、实时观察训练过程，并由 LLM 助教给出结构与超参建议。

- 设计文档：[设计文档.md](./设计文档.md)
- 开发日志：[DEVELOPMENT_LOG.md](./DEVELOPMENT_LOG.md)

## 技术栈

| 层 | 技术 |
| --- | --- |
| 前端 | Vue 3 + TypeScript + Vite + Pinia + Vue Router + TailwindCSS + Axios |
| 3D 可视化 | Three.js 0.186（按需加载） |
| 后端 | FastAPI + SQLAlchemy 2 + Alembic + Pydantic v2 |
| 认证 | JWT（PyJWT）+ argon2id 密码哈希 |
| 数据库 | SQLite（开发）/ PostgreSQL（生产） |

## 系统架构

```
浏览器（Vue 3 SPA）
   │  REST  /api/*          WebSocket  /ws/train/*  ·  /ws/lab/*
   ▼
FastAPI（uvicorn）
   ├── 认证      JWT + argon2id
   ├── 业务      拓扑校验 · 数据集预处理 · 训练调度 · AI 助教
   ├── 训练      后台线程 + PyTorch；事件经 asyncio.Queue 广播给 WebSocket
   └── 持久化    SQLAlchemy → SQLite / PostgreSQL；模型与数据集 → storage/
```

三条关键数据流：

1. **训练流**：前端 `POST /api/train` 建任务 → 建立 WebSocket → 后端训练线程逐 epoch 推送指标 → 结束写入 `training_records` 与 `.pt` 权重。
2. **可视化流**：epoch 事件携带逐层 `layer_stats`（权重 / 梯度 / 激活）→ 前端 2D 画布与 3D 视图按当前视图模式渲染。
3. **助教流**：前端 `POST /api/ai/chat`（SSE）→ 后端优先走 OpenAI 兼容大模型，失败或无 Key 时降级到内置知识库。

## 项目结构

```
DeepVision/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── v1/            # auth / records / graph / datasets / train / ai / lab
│   │   │   ├── realtime.py    # WS /ws/train/{task_id}
│   │   │   ├── lab_ws.py      # WS /ws/lab/{task_id}
│   │   │   └── errors.py      # 统一错误体 {code, message, detail}
│   │   ├── core/              # 配置、安全（argon2 + JWT）、当前用户依赖
│   │   ├── db/                # 引擎、会话、声明式基类
│   │   ├── models/            # User / Dataset / TrainingRecord
│   │   ├── schemas/           # Pydantic 请求与响应模型
│   │   ├── services/          # 拓扑校验、DAG、预处理、训练、AI、实验室
│   │   └── main.py            # 应用入口
│   ├── alembic/               # 数据库迁移（versions/ 下按时间排列）
│   ├── scripts/               # 种子账号等运维脚本
│   ├── tests/                 # pytest 接口与 WebSocket 测试（84 用例）
│   ├── pyproject.toml         # ruff 规则与格式配置
│   ├── requirements.txt       # 后端依赖清单
│   └── .env.example           # 环境变量模板
├── frontend/
│   ├── src/
│   │   ├── api/               # Axios 封装：auth / records / graph / datasets / train / ai / lab
│   │   ├── components/
│   │   │   ├── ai/            # AI 助教抽屉
│   │   │   ├── canvas/        # 画布、节点、节点库、属性面板、小地图、工具栏
│   │   │   ├── train/         # 训练启动对话框、拓扑流光
│   │   │   ├── threed/        # 工作台 3D 只读拓扑
│   │   │   ├── lab/           # 教学实验室：3D 网络、仪表盘、观察弹窗
│   │   │   └── ui/            # Button / Input / Card / Toast / Skeleton
│   │   ├── composables/       # 视口、训练 WebSocket、实验室 WebSocket
│   │   ├── router/            # 路由与登录守卫
│   │   ├── stores/            # Pinia：auth、toast、graph
│   │   ├── styles/            # 设计 token 与组件样式
│   │   ├── types/             # 拓扑类型与 model_config 契约
│   │   ├── utils/             # 自研 CSV 解析与列类型推断
│   │   └── views/             # Login / Workspace / Data / Train / Lab
│   ├── package.json           # 前端依赖与脚本
│   ├── .prettierrc.json       # 前端格式化配置
│   └── vite.config.ts         # 开发代理：/api、/ws → 127.0.0.1:8000
├── samples/                   # 示例数据集（验证用）
├── 设计文档.md                 # 三大阶段的设计与验收标准
├── DEVELOPMENT_LOG.md         # 按对话记录的开发日志
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

## 环境配置

### 后端 `backend/.env`

复制模板：`copy .env.example .env`（macOS/Linux 用 `cp`）。全部可用变量：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `APP_NAME` | `DeepVision API` | 应用名 |
| `DEBUG` | `false` | 调试模式 |
| `SECRET_KEY` | `dev-secret-change-me-in-production` | JWT 签名密钥，**生产必须更换** |
| `ALGORITHM` | `HS256` | JWT 算法 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `120` | Token 有效期 |
| `DATABASE_URL` | `sqlite:///./deepvision.db` | 相对路径基于工作目录，**须在 `backend` 下启动** |
| `CORS_ORIGINS` | `["http://localhost:5173","http://127.0.0.1:5173"]` | 允许的前端来源（JSON 数组） |
| `STORAGE_DIR` | `./storage` | 数据集与模型权重目录 |
| `MAX_UPLOAD_BYTES` | `52428800` | 单次上传上限（50MB） |
| `LLM_PROVIDER` | `none` | `none` / `openai`（任意 OpenAI 兼容服务） |
| `LLM_API_KEY` | 空 | 留空即走内置知识库 |
| `LLM_BASE_URL` | `https://api.openai.com/v1` | 需带版本路径 |
| `LLM_MODEL` | `gpt-4o-mini` | 模型名 |
| `LLM_TIMEOUT_SECONDS` | `30` | 单次请求超时 |
| `LLM_VERIFY_SSL` | `true` | 用系统证书库校验 TLS |
| `AI_RATE_LIMIT_PER_MINUTE` | `20` | 每用户每分钟问答上限 |

### 前端 `frontend/.env.local`（可选）

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `VITE_API_BASE_URL` | 空 | 留空走 Vite 代理（`/api`、`/ws` → 127.0.0.1:8000）；前后端分离部署时填完整地址 |

### 依赖清单

- 后端：[`backend/requirements.txt`](backend/requirements.txt)（Python 3.12+；PyTorch 安装 CPU 版即可）
- 前端：[`frontend/package.json`](frontend/package.json) + `package-lock.json`（Node 18+，`npm ci` 可复现安装）

## AI 助教接入大模型（可选）

不配置时使用内置知识库（14 条），功能完整、完全离线。要接大模型，在 `backend/.env` 中填：

```env
LLM_PROVIDER=openai                    # 任何兼容 OpenAI /chat/completions 的服务
LLM_API_KEY=sk-xxx
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
LLM_TIMEOUT_SECONDS=60
LLM_VERIFY_SSL=true
AI_RATE_LIMIT_PER_MINUTE=20
```

- 改完需**重启后端**（配置有进程内缓存）。
- 验证：`POST /api/ai/chat` 的第一条 SSE 事件应为 `{"type":"meta","mode":"llm"}`；若是 `fallback`，说明调用失败已降级。
- **TLS 说明**：默认用**系统证书库**校验。企业代理或安全软件注入自签根证书时，certifi 会报 `CERTIFICATE_VERIFY_FAILED`，系统证书库通常可通过；实在不行可设 `LLM_VERIFY_SSL=false`（降低安全性）。
- 请求使用 `trust_env=False`，**不经过系统代理**，所以直连不通的服务需要换可达的 `LLM_BASE_URL`。


## 测试

```bash
cd backend
.venv\Scripts\python.exe -m pytest    # 74 个用例
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

## 已实现（阶段三）

- `/data` 页面：拖拽上传 CSV、50MB 限制、四类异常明确提示（非 CSV / 空文件 / 超限 / 解析失败）
- 自研 CSV 解析器：引号、转义双引号、字段内换行、CRLF、BOM
- 前 10 行预览表，空值高亮
- 列类型推断（数值 / 类别 / 日期）与手动纠正（勾选特征列、单选目标列）
- 缺失值处理：均值 / 中位数 / 众数 / 删除，处理后样本数实时更新
- 后端 Pandas 解析：复用同一套规则，返回样本数、特征数、均值、方差与目标分布
- 数据集落库与原始文件存储（`storage/datasets/`），列表与详情接口含归属校验

## 已实现（阶段四）

- 训练引擎：按执行计划物化 PyTorch 模块，支持任意前馈 DAG（汇合按 `concat`）
- 预处理管线：z-score 标准化（仅用训练集统计量）、类别特征独热编码、8:2 训练/验证划分
- 训练任务：后台线程执行、逐 epoch 指标、可随时停止、权重落盘 `storage/models/`
- WebSocket 实时推送（`/ws/train/{token}`）：`started` / `epoch` / `completed` / `failed` / `stopped`，心跳 ping-pong
- 断线重连：指数退避 1s→16s，最多 5 次；重连后服务端回放历史事件，前端按 epoch 去重
- 训练监控页：ECharts 双轴实时曲线（训练损失 / 验证损失 / 准确率）、进度条、拓扑流光、日志流、停止按钮
- 训练结束（含失败与中止）自动写入 `training_records`
- **计算图剖析**：训练开始时推送 `graph_profile`，逐层展示形状 / dtype / 参数量 / 前向耗时，并持久化到记录
- **点击节点看代码**：计算图表格任意一行可打开等效 PyTorch 代码，高亮该节点的定义行与前向计算行
- 逐层曲线支持「范数 ‖W‖₁ / 标准差 σ(W)」切换，观察权重分布演化

## 已实现（阶段五）

- AI 助教抽屉（全局悬浮入口，登录后所有页面可用）
- 流式问答（SSE）：`meta` / `delta` / `done`，回答附带知识来源
- **双模式**：配置 LLM Key 时走 OpenAI 兼容流式接口；未配置或调用失败时自动降级为内置知识库（离线可用）
- 内置知识库 14 条（梯度消失、过拟合、学习率、激活函数、标准化等），关键词检索
- 网络诊断：健康评分 + 问题列表 + 可应用建议（`units` / `features` / `activation` / `task`）
- 「一键应用」直接修改画布节点参数，并进入撤销栈（可 `Ctrl+Z` 回退）
- 输入敏感词拦截、输出脱敏、单用户限流 20 次/分钟

## 已实现（第二大阶段）

- 顶栏视图切换：权重 / 梯度 / 激活三态，2D 画布与 3D 视图同步响应
- 训练时产出逐层统计（权重绝对值之和、梯度范数、激活均值），随 epoch 推送并持久化到 `result_metrics.layer_stats`
- **3D 只读拓扑视图**（Three.js）：发光球体按层着色、权重驱动连线粗细、激活呼吸动画、悬浮查看逐层数值
- 3D 视图按需加载（独立 chunk），不影响 2D 编辑首屏
- 3D 布局沿用 2D 手工坐标（重合时回退环形布局），右上角显示实时 FPS，可导出 PNG
- 视图模式与 2D / 3D 偏好持久化（`localStorage`）
- 训练页新增「逐层权重范数」曲线，按层分色
- 已知限制：逐层统计只保存最后一轮，无法回放中间 epoch 的权重分布

## 已实现（第三大阶段：独立教学实验室 `/lab`）

> 教学实验室是**独立页面**，与第一阶段的画布 / 数据集 / 训练记录互不影响。

- **左侧参数面板**：每层神经元滑块、增删隐藏层、激活函数、初始化、优化器、学习率 / 批大小 / 轮数 / L2 / Dropout
- **中间 3D 网络**：按层排布、相邻层全连接、层名跟随投影的浮动标签、左键旋转 / 滚轮缩放 / 右键平移
- **底部仪表盘**：5 张 KPI 卡 + loss 曲线 + 权重分布直方图 + 决策边界（48×48 概率网格 + 数据点）
- **右侧助教**：模型引擎选择、4 个快捷问题、自定义提问、流式解析、实时指标
- **输入神经元数（1–8）与输出类别数（2–6）可调**，数据集按配置生成（>2 维补噪声，3 类以上为环形分布）
- 训练支持**暂停 / 恢复 / 停止**，默认 1400 / 600 切分
- 参数恒等：`[8, 8]` 结构参数量为 114，连接数 96
- **观察弹窗**（顶栏导航）：前向 / 反向逐层单步、输入特征注意力（条形图 + 3D 输入节点高亮）、逐 epoch 注意力曲线、指定层 **PCA / t-SNE** 降维散点
- 弹窗内可**一键导出 PNG**（`html2canvas` 按需加载，不拖慢首屏）
- **实验任务**：3 个内置任务（双螺旋达标 / 学习率过大 / 隐藏层过窄），一键应用参数，训练后自动判定达标并给出检查点问答与解释
- **自动调参**：随机搜索学习率 / 结构 / 激活 / l2 / dropout / batch，连续 4 轮未提升即早停，结果表可一键回填最佳参数
- **对比实验**：任务结果弹窗可「再跑一组对比」，并排显示两组的准确率与 loss（曲线级对比在 `/history`）
- 助教回答支持 **Markdown 渲染**，引擎可选择 自动 / 强制大模型 / 离线规则
- 实验室训练结果写入 `training_records`（`source = lab`），与第一阶段历史共用一张表

## 主要接口

| 方法 | 路径 | 说明 | 认证 |
| --- | --- | --- | --- |
| POST | `/api/auth/register` | 注册 | 否 |
| POST | `/api/auth/login` | 登录，返回 JWT | 否 |
| GET | `/api/auth/me` | 当前用户 | 是 |
| GET | `/api/records` | 训练记录列表（分页） | 是 |
| POST | `/api/records` | 保存训练记录 | 是 |
| GET | `/api/records/{id}` | 记录详情 | 是 |
| GET | `/api/records/{id}/diagnosis` | 训练曲线诊断（过拟合 / 欠拟合 / 学习率） | 是 |
| POST | `/api/records/{id}/rerun` | 按原配置一键重跑 | 是 |
| GET | `/api/records/compare?ids=` | 多实验曲线对比（2–4 条） | 是 |
| GET | `/api/records/{id}/code` | 生成等效 PyTorch 代码与行号映射 | 是 |
| GET | `/api/train/{task_id}/code` | 按训练任务生成等效代码 | 是 |
| POST | `/api/lab/tune` | 启动自动调参（随机搜索 + 早停） | 是 |
| GET | `/api/lab/tune/{tune_id}` | 查询自动调参进度 | 是 |
| DELETE | `/api/records/{id}` | 删除记录 | 是 |
| POST | `/api/graph/validate` | 校验网络拓扑结构 | 是 |
| POST | `/api/datasets` | 上传并解析 CSV 数据集 | 是 |
| GET | `/api/datasets` | 数据集列表（分页） | 是 |
| GET | `/api/datasets/{id}` | 数据集详情与统计 | 是 |
| POST | `/api/train` | 创建训练任务 | 是 |
| POST | `/api/train/{task_id}/stop` | 停止训练 | 是 |
| WS | `/ws/train/{task_id}?token=` | 训练指标实时推送 | 是 |
| POST | `/api/ai/chat` | AI 助教问答（SSE 流式） | 是 |
| POST | `/api/ai/diagnose` | 拓扑诊断与调参建议 | 是 |
| POST | `/api/lab/train` | 创建教学实验室训练任务 | 是 |
| POST | `/api/lab/{task_id}/pause` \| `/resume` \| `/stop` | 实验室训练控制 | 是 |
| WS | `/ws/lab/{task_id}?token=` | 实验室指标 / 权重分布 / 决策边界推送 | 是 |
| GET | `/api/lab/{task_id}/inspect?index=` | 逐层激活 / 梯度与输入注意力 | 是 |
| GET | `/api/lab/{task_id}/projection?layer=` | 指定层 PCA 二维投影 | 是 |

## 阶段总览

| 阶段 | 定位 | 入口 |
| --- | --- | --- |
| 第一大阶段 | 用户训练自己的数据（认证 / 画布 / 数据集 / 训练 / AI 助教） | `/workspace`、`/data`、`/train/:id` |
| 第二大阶段 | 3D 观察结构与逐层指标 | `/workspace` 内切换 3D |
| 第三大阶段 | 教学实验室：滑块调参 + 实时可视化 | `/lab` |

## 开发规范

### 代码风格

| 端 | 规范 |
| --- | --- |
| 后端 | ruff（规则 E / F / I / UP / B / SIM），行宽 88，`ruff format` 统一格式；函数带类型注解，模块与关键函数用中文 docstring 说明意图与边界 |
| 前端 | TypeScript + `<script setup>`，Prettier（无分号、单引号、行宽 80）；组件 PascalCase，工具函数 camelCase |
| 通用 | UTF-8 / LF（见 `.gitattributes`、`.editorconfig`） |

### 常用命令

```bash
# 后端
cd backend
.venv\Scripts\python.exe -m ruff check app tests
.venv\Scripts\python.exe -m ruff format app tests
.venv\Scripts\python.exe -m pytest -q

# 前端
cd frontend
npm run typecheck
npm run format
npm run build
```

### 提交信息

`<type>(<scope>): <subject>`，`type` 取 `feat` / `fix` / `docs` / `refactor` / `test` / `chore` / `style`。

一次提交只做一件事，按「对话 / 功能模块」拆分，禁止把多个功能压成一次提交。

### 分支与合并

- `main` 始终保持可运行；
- 新功能用 `feature/<简述>`，修复用 `fix/<简述>`；
- 合并前必须通过后端 `pytest` 与前端 `npm run build`。

## 团队信息

| 角色 | 成员 | 负责内容 |
| --- | --- | --- |
| 项目负责人 / 全栈开发 | 小广漩 | 需求与设计、后端 API 与训练引擎、前端画布与 3D、文档与部署 |
| 代码仓库 | Zhou-guangxuan | https://github.com/Zhou-guangxuan/DeepVision |

> 如有其他成员，请按「角色 / 成员 / 负责模块」三列在此表追加。

## 相关文档

- [设计文档.md](./设计文档.md)：三大阶段的架构、页面规格、数据模型、接口契约与验收标准；**§13 教学价值论证**（痛点 / 方案 / 效果 / 六项需求评估）
- [设计文档第二版.md](./设计文档第二版.md)：第三大阶段（教学实验室）的需求原文，保留用于追溯
- [DEVELOPMENT_LOG.md](./DEVELOPMENT_LOG.md)：按对话记录的开发过程与决策
- 运行后可在 `http://127.0.0.1:8000/docs` 查看 Swagger 接口文档

## 后续可选

- 历史记录页 `/history`（当前记录只能通过接口或数据库查看）
- 第三大阶段：注意力热力图的逐层版本、t-SNE 困惑度可调、导出矢量图
- 第二大阶段：DAG 汇合策略扩展（`add` / `multiply`）
- 工程优化：ECharts / three 按需引入、接真实 LLM 服务

详见 [设计文档.md](./设计文档.md) 第 12 章。
