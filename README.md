# DeepVision

> 可视化深度学习实验平台：拖拽搭建神经网络、上传 CSV 数据、实时观察训练过程，并由 LLM 助教给出结构与超参建议；同时提供**教学实验室**与**图像实验**两条独立实验线。

---

## 一、项目介绍

### 1.1 这个项目解决什么问题

传统深度学习实验教学里，学生通常只能看到一条 loss 曲线：

- 环境配置耗时，一节课可能卡在装依赖上
- 网络结构不可见，层宽、连线、激活全靠想象
- 调参靠猜，改完要等训练结束才知道效果
- 训练过程不可回放，无法回答「什么时候开始过拟合」
- 结果不可复现，换台机器就跑不出同样的数

DeepVision 把这五件事变成**可看、可问、可验证**：浏览器里搭网络、训练时逐层可观测、训练后用规则诊断曲线、实验配置完整落库可复现。

### 1.2 三条实验线

| 实验线 | 入口 | 适合谁 | 能做什么 |
| --- | --- | --- | --- |
| **表格实验** | `/workspace` | 想训练自己数据的同学 | 拖拽搭任意前馈 DAG、上传 CSV、训练、对比、诊断 |
| **教学实验室** | `/lab` | 课堂 / 自学 | 滑块调参、3D 网络、逐层观察、教学任务、快照回放、归因 |
| **图像实验** | `/images` | 想看卷积怎么工作 | 内置图形数据集、固定小 CNN、混淆矩阵与样本网格 |

三条线共用同一套训练、记录与 AI 助教体系，但**不做跨模态融合**（边界见设计文档 §13.10）。

### 1.3 核心能力

**可视化**

- 自研 SVG 画布：拖拽节点、贝塞尔连线、成环/自连/重复连线前置拦截
- 3D 只读拓扑（Three.js）：发光球体、权重驱动连线、激活呼吸动画
- 训练页实时曲线 + 拓扑流光（可切前向 / 反向）+ 日志流

**可观测**

- 逐层统计：权重范数、梯度范数、激活均值与 P50/P95
- **计算图剖析**：每层形状 / dtype / 参数量 / 内存 / 前向耗时
- **拓扑热力**：节点颜色深浅 = 耗时占比，悬停看详情
- **等效代码**：点计算图某行，高亮该层对应的 PyTorch 代码行

**会判断**

- 规则诊断：发散、过拟合、学习率过大 / 过小、欠拟合，每条给证据与建议
- 多实验对比：2–4 条记录，按 **epoch / 进度 / 实际耗时** 三种对齐
- 一键重跑：按原配置与随机种子重跑，验证结论是否稳定

**会教**

- 3 个内置教学任务（达标 + 两个错误示范），参数一键填好
- 训练后自动判定是否达标，并给检查点问答与解释
- 快照回放：回到任意 epoch 看决策边界
- Integrated Gradients 归因：每个输入特征推了多少

**工程**

- 密码 argon2id、JWT、资源归属校验、上传大小/类型校验
- WebSocket 断线重连 + 历史事件回放，训练数据不丢
- 画布草稿服务端同步，同账号换设备可恢复

### 1.4 与同类工具的区别

| 工具 | 定位 | 与 DeepVision 的差异 |
| --- | --- | --- |
| TensorBoard | 看训练指标 | 不做结构编辑、不做诊断、不面向教学 |
| Netron | 看静态模型结构 | 不训练、不可编辑 |
| AutoML 平台 | 自动找最好模型 | 目标是「替人做」，本平台目标是「让人懂」 |

一句话：**别的工具给你结果，DeepVision 给你过程。**

### 1.5 项目状态

| 项 | 当前 |
| --- | --- |
| 提交 | **127** 次，按功能模块拆分 |
| 后端测试 | **113 passed** |
| 端到端自测 | **29 / 29** 通过 |
| 前端构建 | 通过（`vue-tsc --noEmit`） |
| 数据库迁移 | 6 个版本，当前 `a7e9c2d4f610` |
| 文档 | 设计文档 v6.5、演示答辩脚本 |

> 教学效果**尚未实测**，不预填任何效果数字；论证结构见设计文档 §13。

---

## 二、技术架构

### 2.1 技术栈

| 层 | 技术 | 说明 |
| --- | --- | --- |
| 前端框架 | Vue 3.5 + TypeScript + Vite 5 | `<script setup>` 单文件组件 |
| 状态 / 路由 | Pinia + Vue Router | 画布 store、鉴权守卫 |
| 样式 | TailwindCSS 3.4 + CSS 变量 | 深色主题，设计令牌集中管理 |
| 图表 / 3D | ECharts 6 + Three.js + OrbitControls | 3D 按需加载，独立 chunk |
| 网络 / 渲染 | Axios + WebSocket + marked + DOMPurify | SSE 流式问答，Markdown 安全渲染 |
| 后端框架 | FastAPI 0.14 + Pydantic v2 + pydantic-settings | 统一错误体、依赖注入 |
| 数据层 | SQLAlchemy 2 + Alembic + SQLite | 6 个迁移版本 |
| 训练 | PyTorch 2.14（CPU） | 后台线程执行，事件经 asyncio.Queue 广播 |
| 认证 | PyJWT + argon2id | Token 2 小时 |
| 数据处理 | pandas + numpy | CSV 解析、预处理、统计 |
| 质量 | pytest + ruff + Prettier | 113 个测试用例 |

### 2.2 架构分层

```
┌────────────────────────────────────────────────────────────┐
│ 浏览器（Vue 3）                                            │
│  工作台画布 / 训练页 / 历史 / 教学实验室 / 图像实验 / AI 抽屉 │
└───────────────┬────────────────────────────────────────────┘
                │ HTTP (REST) + WebSocket
┌───────────────▼────────────────────────────────────────────┐
│ FastAPI                                                    │
│  api/v1/*  路由与鉴权（JWT、资源归属校验）                   │
│  services  训练、诊断、codegen、调参、压缩、快照、图像数据    │
└───────┬───────────────────────────────┬────────────────────┘
        │ 线程池 / 后台线程               │ SQLAlchemy
┌───────▼──────────────┐        ┌───────▼────────────────────┐
│ 训练运行时            │        │ SQLite + 文件存储           │
│ DagNet / ImageCNN     │        │ storage/datasets、models    │
│ 事件 → asyncio.Queue  │        │ training_records / datasets │
└──────────────────────┘        └────────────────────────────┘
```

**一次训练的完整链路**

1. 画布导出 `model_config`（节点 + 连线）
2. `POST /api/graph/validate` 校验并生成执行计划（拓扑序 + 前驱）
3. `POST /api/train` 创建 pending 任务
4. 前端建立 `WS /ws/train/{task_id}`，服务端此时才启动训练线程
5. 每个 epoch 推送事件；断线重连时先回放历史再续推
6. 结束（成功 / 失败 / 停止）写入 `training_records`，权重落盘

### 2.3 关键设计决策

| 主题 | 决策 | 原因 |
| --- | --- | --- |
| 画布 | 自研 SVG，不引入 G6 | 交互与样式完全可控，规避第三方 API 变动 |
| 拓扑 | 支持任意前馈 DAG，汇合按 `concat` | 分支/汇合都能训练，比链式更接近真实网络 |
| 训练执行 | 后台线程 + `asyncio.Queue` | 不阻塞事件循环，事件可广播给多个客户端 |
| 诊断 | 规则引擎，不用 LLM | 判定要稳定可复现；LLM 只负责解释 |
| 代码行映射 | 配置驱动生成等效代码 | 平台没有「源码行」，用 codegen + 行号映射替代 |
| 图像线 | 固定小 CNN，不进画布 | 通用多模态需重写引擎，投入产出不成立 |
| 随机种子 | 训练固定 `seed=42` | 重跑与教学任务判定可复现 |

### 2.4 目录结构

```
AI-web/
├── backend/
│   ├── app/
│   │   ├── api/v1/          # auth / datasets / graph / train / records / ai / lab / workspace
│   │   ├── core/            # 配置、JWT、依赖
│   │   ├── db/              # 会话与 Base
│   │   ├── models/          # user / dataset / record / workspace
│   │   ├── schemas/         # Pydantic 请求响应
│   │   └── services/        # training / dag_model / preprocessing / diagnosis / codegen /
│   │                        # tuning / compression / lab / image_dataset / llm ...
│   ├── alembic/versions/    # 6 个迁移
│   ├── scripts/seed_test_user.py
│   ├── tests/               # 113 个用例
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── api/             # Axios 封装
│   │   ├── components/      # canvas / train / lab / ai / ui
│   │   ├── composables/     # WebSocket 训练通道
│   │   ├── data/            # 教学任务定义
│   │   ├── router/ stores/  types/ utils/
│   │   └── views/           # 8 个页面
│   ├── package.json
│   └── vite.config.ts
├── 设计文档.md               # 架构 / 页面 / 数据模型 / 接口 / 验收
├── 演示答辩脚本.md
├── multi_io_rings.csv        # 示例数据集：2+2 输入 / 3×32 隐藏 / 2 输出二分类
├── DEVELOPMENT_LOG.md
└── README.md
```

### 2.5 主要接口

完整契约见 [设计文档 §7](./设计文档.md) 与运行后的 `http://127.0.0.1:8000/docs`。

| 分组 | 代表接口 |
| --- | --- |
| 认证 | `POST /api/auth/register`、`POST /api/auth/login`、`GET /api/auth/me` |
| 数据集 | `POST /api/datasets`、`GET /api/datasets`、`GET /api/datasets/{id}`、`POST /api/datasets/image`、`GET /api/datasets/{id}/preview` |
| 拓扑 | `POST /api/graph/validate` |
| 表格训练 | `POST /api/train`、`POST /api/train/{id}/stop`、`WS /ws/train/{id}`、`GET /api/train/{id}/code` |
| 记录 | `GET /api/records`、`GET /api/records/{id}`、`DELETE /api/records/{id}`、`GET /api/records/{id}/model`（下载权重） |
| 诊断 / 对比 | `GET /api/records/{id}/diagnosis`、`GET /api/records/compare?ids=`、`POST /api/records/{id}/rerun`、`GET /api/records/{id}/code` |
| 实验室 | `POST /api/lab/train`、`WS /ws/lab/{id}`、`pause/resume/stop`、`GET /api/lab/{id}/inspect`、`projection`、`attention`、`diagnosis`、`compression`、`snapshots`、`snapshot`、`attribution`、`POST /api/lab/tune` |
| 图像 | `POST /api/train/image`、`GET /api/records/{id}/image-eval` |
| 草稿 | `GET /api/workspace/draft`、`PUT /api/workspace/draft` |
| AI | `POST /api/ai/chat`（SSE）、`POST /api/ai/diagnose` |

---

## 三、安装运行指南

### 3.1 环境要求

- Python 3.12+（3.12 与 3.14 均验证通过，推荐 3.12）
- Node.js 18+
- 不需要 GPU：训练在 CPU 上完成

### 3.2 快速启动（环境已配置好）

开**两个** PowerShell 窗口，普通权限即可。

```powershell
# 窗口 1：后端
cd D:\AI-web\backend
D:\AI-web\.venv\Scripts\python.exe -m alembic upgrade head
D:\AI-web\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```powershell
# 窗口 2：前端
cd D:\AI-web\frontend
npm.cmd run dev
```

| 检查 | 地址 | 预期 |
| --- | --- | --- |
| 后端健康 | http://127.0.0.1:8000/health | `{"status":"ok"}` |
| 接口文档 | http://127.0.0.1:8000/docs | Swagger 页面 |
| 前端 | http://localhost:5173 | 登录页 |

- `alembic upgrade head` 只在第一次启动或拉到新代码后需要执行
- 演示时建议不加 `--reload`，避免训练中途被重启打断
- Windows 上必须写 `npm.cmd`，直接写 `npm` 可能被执行策略拦住

**停止**：两个窗口各按一次 `Ctrl + C`。

**端口被占用**

```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen
Stop-Process -Id <上面查到的进程号> -Force
```

前端 5173 被占用时：`npm.cmd run dev -- --port 5174`。

### 3.3 从零安装（新机器）

**后端**

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

> 数据库路径是相对路径，**必须在 `backend` 目录下启动**，否则会新建一个空库。

**前端**

```bash
cd frontend
npm install
npm run dev                   # http://localhost:5173
```

开发期 Vite 已把 `/api`、`/ws` 代理到 `http://127.0.0.1:8000`，无需额外配置跨域。

### 3.4 测试账号

```bash
cd backend
.venv\Scripts\python.exe scripts/seed_test_user.py                        # 默认 admin / 123456
.venv\Scripts\python.exe scripts/seed_test_user.py --username demo --password demo123456
```

| 用户名 | 密码 |
| --- | --- |
| `admin` | `123456` |

脚本可重复执行（已存在则重置密码），密码始终以 argon2id 哈希入库。

> 弱口令仅用于本地开发。公开仓库部署到公网前请删除该账号或更换密码。

### 3.5 配置项

> 完整的变量说明、依赖清单与环境检查表见 [环境配置.md](./环境配置.md)。

复制模板：`copy .env.example .env`（macOS/Linux 用 `cp`）。

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `APP_NAME` | `DeepVision API` | 应用名 |
| `DEBUG` | `false` | 调试模式 |
| `SECRET_KEY` | `dev-secret-change-me-in-production` | JWT 签名密钥，**生产必须更换** |
| `ALGORITHM` | `HS256` | JWT 算法 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `120` | Token 有效期 |
| `DATABASE_URL` | `sqlite:///./deepvision.db` | 相对路径基于工作目录 |
| `CORS_ORIGINS` | `["http://localhost:5173","http://127.0.0.1:5173"]` | 允许的前端来源 |
| `STORAGE_DIR` | `./storage` | 数据集与模型权重目录 |
| `MAX_UPLOAD_BYTES` | `52428800` | 单次上传上限（50MB） |
| `LLM_PROVIDER` | `none` | `none` / `openai`（任意兼容服务） |
| `LLM_API_KEY` | 空 | 留空走内置知识库 |
| `LLM_BASE_URL` | `https://api.openai.com/v1` | 需带版本路径 |
| `LLM_MODEL` | `gpt-4o-mini` | 模型名 |
| `LLM_TIMEOUT_SECONDS` | `30` | 单次请求超时 |
| `LLM_VERIFY_SSL` | `true` | 用系统证书库校验 TLS |
| `AI_RATE_LIMIT_PER_MINUTE` | `20` | 每用户每分钟问答上限 |

前端可选：`frontend/.env.local` 里的 `VITE_API_BASE_URL`（留空走 Vite 代理，前后端分离部署时填完整地址）。

依赖清单：[`backend/requirements.txt`](backend/requirements.txt)、[`frontend/package.json`](frontend/package.json)。

### 3.6 接入大模型（可选，以 DeepSeek 为例）

不配置时使用内置知识库（14 条），功能完整、完全离线。下面是把 AI 助教切到 DeepSeek 的完整步骤。

#### 第 1 步：获取 API Key

登录 DeepSeek 开放平台 → 「API keys」→ 创建 → 复制 `sk-...`（只显示一次，注意不要带空格）。

#### 第 2 步：写入 `backend/.env`

```env
LLM_PROVIDER=openai
LLM_API_KEY=sk-你的key
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-flash
LLM_TIMEOUT_SECONDS=60
LLM_VERIFY_SSL=true
AI_RATE_LIMIT_PER_MINUTE=20
```

#### 第 3 步：确认模型名

DeepSeek 接口会校验模型名，**填错直接返回 400，并在错误里列出支持的名称**。

| 模型 id | 状态 | 说明 |
| --- | --- | --- |
| `deepseek-flash` | ✅ 实测可用 | 通用对话，当前默认 |
| `deepseek-v4-pro` | ✅ 接口列为支持 | 更强的版本，按账号额度使用 |
| `deepseek-chat` | ✅ 可用（别名） | 请求会转发到 `deepseek-flash`，返回的 `model` 字段是 flash |
| `deepseek-v4.1-flash` | ❌ 返回 400 | 接口提示「supported names are deepseek-flash, deepseek-v4-pro」 |

> 模型列表由服务商控制，平台不硬编码。换模型只改 `LLM_MODEL`；
> 不确定时先跑第 5 步的脚本，400 的响应体会直接告诉你可用名称。

#### 第 4 步：重启后端

配置有进程内缓存，**改完必须重启**，否则仍按旧配置运行。

#### 第 5 步：验证

```bash
cd backend
.venv\Scripts\python.exe scripts/check_llm.py
```

成功时输出类似：

```
LLM_PROVIDER = openai
LLM_BASE_URL = https://api.deepseek.com/v1
LLM_MODEL    = deepseek-chat
LLM_API_KEY  = sk-a…z9
HTTP 200
模型返回：deepseek-chat / 'pong'
接入成功。
```

也可以直接看业务接口：`POST /api/ai/chat` 的第一条 SSE 事件应为
`{"type":"meta","mode":"llm"}`；若是 `fallback`，说明调用失败已自动降级（功能仍可用）。

#### 常见错误

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `HTTP 400` | 模型名不被支持 | 看响应体里的 `supported API model names`，改成其中之一 |
| `HTTP 401` | Key 无效 / 过期 / 多了空格 | 重新生成，检查引号与空格 |
| `HTTP 402` | 余额不足 | 充值 |
| `HTTP 403` | 账号无权调用该模型 | 控制台确认已开通 |
| `HTTP 404` | 模型名或地址不对 | 核对 `LLM_MODEL` 与 `LLM_BASE_URL`（要带 `/v1`） |
| `HTTP 429` | 触发限流 | 稍后重试，或调低 `AI_RATE_LIMIT_PER_MINUTE` |
| 连接超时 | 网络不通 / 需要代理 | 脚本与后端都**不走系统代理**（`trust_env=False`），需能直连 |
| TLS 证书错误 | 企业代理注入自签根证书 | 默认用系统证书库；仍失败可临时 `LLM_VERIFY_SSL=false`（降低安全性） |
| 首条事件是 `fallback` | 调用失败已降级 | 看后端日志中的 warning，按上表排查 |

#### 安全与设计说明

- Key 只存在 `backend/.env`（已在 `.gitignore`），**前端永远拿不到**
- 所有调用在后端完成，前端只接收流式文本
- 未配置或调用失败会**自动降级**到内置知识库，不影响其他功能
- 输出经敏感词脱敏、输入被拦截，单用户限流 20 次/分钟

### 3.7 验证与测试

```bash
# 后端
cd backend
.venv\Scripts\python.exe -m pytest -q

# 前端
cd frontend
npm run build      # 含 vue-tsc --noEmit
npx prettier --check src
```

| 检查 | 结果 |
| --- | --- |
| pytest | **113 passed** |
| ruff check / format | 通过 |
| prettier | 通过 |
| 前端构建 | 通过 |
| `alembic upgrade head` | 当前 `a7e9c2d4f610`（head） |

### 3.8 常见问题

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 页面能开但报「网络异常」 | 后端没启动 | 访问 `/health` 确认 |
| `Address already in use` | 8000 被占 | 见 §3.2 端口排查 |
| 前端报 `EADDRINUSE` | 5173 被占 | 换端口或关旧进程 |
| `npm` 无法运行 | 执行策略 | 用 `npm.cmd` |
| `ModuleNotFoundError` | 用错解释器 | 用 `.venv\Scripts\python.exe` |
| 训练报「拓扑结构非法」 | 结构不合法 | 点「校验拓扑」看具体原因 |
| 准确率上不去 | 欠拟合 / 过拟合 / 学习率 | 看历史页「诊断」结论 |

---

## 四、团队信息

| 角色 | 成员 | 负责内容 |
| --- | --- | --- |
| 项目负责人 / 全栈开发 | 小广漩 | 需求与设计、后端 API 与训练引擎、前端画布与 3D、文档与部署 |
| 代码仓库 | Zhou-guangxuan | https://github.com/Zhou-guangxuan/DeepVision |

> 如有其他成员，请按「角色 / 成员 / 负责模块」三列在此表追加。

---

## 附录

### A. 功能清单（按阶段）

| 阶段 | 主要内容 |
| --- | --- |
| 阶段一 | 注册登录、JWT、argon2、记录 CRUD、统一错误体、登录页、路由守卫、基础组件 |
| 阶段二 | SVG 画布、节点库、属性面板、连线校验、缩放平移、小地图、撤销重做、草稿、DAG 校验 |
| 阶段三 | CSV 上传、自研解析器、列类型推断、缺失值处理、统计、数据集落库 |
| 阶段四 | DAG 训练引擎、预处理、WebSocket 实时指标、断线重连、训练页、记录落库、计算图剖析、代码映射、多实验对比 |
| 阶段五 | AI 助教（流式 + 降级）、知识库、结构诊断、一键应用、限流与敏感词 |
| 第二大阶段 | 3D 拓扑、逐层统计、视图切换、FPS 与导出 |
| 第三大阶段 | 教学实验室：滑块调参、3D 网络、仪表盘、观察弹窗（传播/注意力/曲线/归因/投影）、教学任务、自动调参、剪枝量化、快照回放 |
| 图像线 | 合成图形数据集、固定小 CNN、混淆矩阵与样本网格、重跑 |
| 协作最小集 | 画布草稿服务端同步（同账号多设备） |

### B. 开发规范

| 端 | 规范 |
| --- | --- |
| 后端 | ruff（E / F / I / UP / B / SIM），行宽 88，`ruff format`；类型注解 + 中文 docstring |
| 前端 | TypeScript + `<script setup>`；Prettier（无分号、单引号、行宽 80）；组件 PascalCase |
| 通用 | UTF-8 / LF（`.gitattributes`、`.editorconfig`） |
| 提交 | `<type>(<scope>): <subject>`，一次提交只做一件事 |

### C. 相关文档

- [设计文档.md](./设计文档.md)：架构、页面规格、数据模型、接口契约、验收标准；**§13 教学价值论证**（痛点 / 方案 / 效果 / 六项需求对照）
- [演示答辩脚本.md](./演示答辩脚本.md)：演示动线、逐场景台词、12 个常见提问、应急方案
- [环境配置.md](./环境配置.md)：环境变量模板、变量说明、依赖清单、检查清单与多环境配置建议
- [DEVELOPMENT_LOG.md](./DEVELOPMENT_LOG.md)：按对话记录的开发过程与决策
- 运行后在 `http://127.0.0.1:8000/docs` 查看 Swagger

### D. 范围说明

功能范围以当前实现为准，未实现的能力（算子融合、跨用户协作、多模态融合等）已在
[设计文档 §13](./设计文档.md) 的「限制」与「完整版范围」中列明，不在此另列计划。

已知边界见 [设计文档 §13](./设计文档.md)，尤其是 §13.4「完整版范围」与各节「限制」。
