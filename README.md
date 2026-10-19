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
│   │   ├── api/             # Axios 封装：auth、records、graph、datasets、train、ai
│   │   ├── components/
│   │   │   ├── ai/          # AI 助教抽屉
│   │   │   ├── canvas/      # 画布、节点、节点库、属性面板、小地图、工具栏
│   │   │   ├── train/       # 训练启动对话框、拓扑流光
│   │   │   └── ui/          # Button / Input / Card / Toast / Skeleton
│   │   ├── composables/     # 画布视口、登录页装饰动画
│   │   ├── router/          # 路由与登录守卫
│   │   ├── stores/          # Pinia：auth、toast、graph
│   │   ├── styles/          # 设计 token 与组件样式
│   │   ├── types/           # 拓扑类型与 model_config 契约
│   │   ├── utils/           # 自研 CSV 解析与列类型推断
│   │   └── views/           # LoginView / WorkspaceView / DataView / TrainView
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

### 独立教学实验室 `/lab`

- **左侧参数面板**：每层神经元滑块、增删隐藏层、激活函数、初始化、优化器、学习率 / 批大小 / 轮数 / L2 / Dropout
- **中间 3D 网络**：按层排布、相邻层全连接、层名跟随投影的浮动标签、左键旋转 / 滚轮缩放 / 右键平移
- **底部仪表盘**：5 张 KPI 卡 + loss 曲线 + 权重分布直方图 + 决策边界（48×48 概率网格 + 数据点）
- **右侧助教**：模型引擎选择、4 个快捷问题、自定义提问、流式解析、实时指标
- 训练使用内置**双螺旋数据集**（1400 / 600），支持**暂停 / 恢复 / 停止**
- 参数恒等：`[8, 8]` 结构参数量为 114，连接数 96

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

## 后续阶段

五个阶段已全部完成。后续可选：DAG 汇合策略扩展（`add` / `multiply`）、历史记录页 `/history`、ECharts 按需引入、接真实 LLM 服务。
详见 [设计文档.md](./设计文档.md) 第 8 章。
