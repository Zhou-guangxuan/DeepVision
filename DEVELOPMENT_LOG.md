# 开发日志

本文件按「一次与 AI 的核心对话 / 一个功能模块的落地」逐条记录开发过程，与 git 提交历史一一对应。

---

## 2026-10-16 · 创建 GitHub 项目库

**类型**：项目初始化
**对应提交**：`chore: 初始化仓库骨架（README、.gitignore）`

### 本次对话完成的工作

1. 在空目录 `D:\AI-web` 中执行 `git init -b main`，初始化本地仓库，默认分支 `main`。
2. 检查本机 GitHub 认证环境，发现 `gh` CLI、SSH 密钥、`.git-credentials`、Windows 凭据管理器、`GITHUB_TOKEN` 环境变量均为空。
3. 通过 winget 安装 GitHub CLI `2.102.0`，并用浏览器设备码流程完成授权登录，账号 `Zhou-guangxuan`；token 存储于 Windows 凭据管理器（keyring），非明文文件。
4. 新建 `README.md`、Python 版 `.gitignore`，作为首次提交内容。
5. 添加远程 `origin` → `https://github.com/Zhou-guangxuan/DeepVision.git`，推送 `main` 分支并设置上游跟踪。

### 结果

- 仓库地址：https://github.com/Zhou-guangxuan/DeepVision
- 首次提交 `chore: 初始化仓库骨架（README、.gitignore）`
- 远端文件：`.gitignore`、`README.md`

### 事项与决定

- 仓库可见性为 **Public**（GitHub 上原已存在的空仓库）。此后提交的代码对外公开可见。
- `.gitignore` 默认忽略模型权重文件（`*.pth`、`*.pt`、`*.onnx`、`*.safetensors` 等）。如需将权重纳入版本管理，应改用 Git LFS，而非直接移除忽略规则。
- 本机沙箱化 shell 无法启动（`pwsh` 报 `0xC0000142`，DLL 初始化失败），所有命令需在放宽沙箱权限后执行。

### 提交规范

- 必须保留完整、细粒度的 git 提交历史。
- **禁止**一次性提交（如一条 `initial commit` 即包含全部功能）。
- 每次提交对应一次与 AI 的核心对话，或一个功能模块的落地。

---

## 2026-10-17 · 重构设计文档为 v2.0

**类型**：文档重构
**对应提交**：`docs: 重构设计文档为 v2.0（设计系统、页面规格、接口契约、任务书）`

### 本次对话完成的工作

1. 阅读原型 `设计文档.md`（158 行，五阶段 Prompt 模板）。
2. 重构为正式设计文档 v2.0（882 行、11 章）：
   - 新增「视觉设计系统」：深色科技风的色彩、字体、间距、动效 token 与组件规范，替代形容词式描述。
   - 新增「页面规格」：7 个页面逐页定义布局、状态（加载/空/错误/禁用）与交互。
   - 新增「数据模型」：ER 图、3 张表、3 个核心 JSON 契约。
   - 新增「接口契约」：13 个 REST 接口与 WebSocket 协议（含心跳）。
   - 原型 Prompt 模板重构为「开发任务书」：每阶段含交付物、接口契约、可勾选验收标准与依赖。
   - 新增「非功能需求」与「风险与对策」。
3. 原型备份为 `设计文档.original.md`，随后移至桌面（`C:\Users\zgx\Desktop`），不进入版本库。
4. 对文档做技术可行性评审，识别出 5 处开工前必须决策的缺口。

### 结果

- 仓库内：设计文档 v2.0，882 行。
- 仓库外：`设计文档.original.md` 保留在桌面作为原型备份。

### 待决事项

评审识别出的 5 处缺口，尚未写入文档：

1. **结构矛盾**：画布允许任意 DAG（§5.3），但后端仅支持 MLP（§2.2），无法表达分叉与汇合。
2. **动画数据源缺失**：动画要求传播级数据（§5.5），WebSocket 协议仅有 epoch 级事件（§7.3）。
3. **预处理缺口**：缺少数值标准化、类别编码、训练/验证集划分与预处理参数持久化。
4. **RAG 语料未定义**：知识库内容来源、规模、embedding 与向量库选型均未说明。
5. **LLM 输出约束缺失**：结构化诊断缺少 JSON 模式、重试校验与建议字段白名单。

其他待定：

- 认证 token 存储方式（`Authorization: Bearer` vs httpOnly Cookie + CSRF）未定。
- `README.md` 与设计文档不一致：README 仍写「Python 计算机视觉项目」，实际为全栈 Web 应用。

---

## 2026-10-17 · 完成阶段一开发（认证与记录读写）

**类型**：功能开发
**对应提交**：
- `feat(backend): 实现用户认证与训练记录 CRUD（阶段一）`
- `feat(frontend): 实现登录页、路由守卫与鉴权拦截器（阶段一）`

### 环境处置

- 沙箱化 shell 仍无法启动（`0xC0000142`），全部命令在放宽权限后执行。
- Python 3.14 缺少依赖的预编译 wheel（`from versions: none`），改用系统内 Python 3.12 重建虚拟环境。
- `npm` / `pnpm` 受 PowerShell 执行策略限制，改用 `npm.cmd` 调用。
- PyPI 官方源不可达，改用清华镜像；npm 使用 npmmirror。

### 后端交付

1. 应用骨架：`pydantic-settings` 配置、SQLAlchemy 引擎与会话、统一错误体 `{code, message, detail}`。
2. 模型：`User`、`Dataset`、`TrainingRecord`（列名 `model_config`）、任务状态机常量。
3. 认证：argon2id 密码哈希、JWT 签发与校验、`get_current_user` 依赖、401 细分错误码（`NOT_AUTHENTICATED` / `TOKEN_EXPIRED` / `TOKEN_INVALID`）。
4. 接口：注册、登录、`/me`；训练记录 CRUD（分页、时间倒序、归属校验）。
5. Alembic 迁移：由 autogenerate 生成 `c5ffc10eb3be_initial_schema.py`。

### 前端交付

1. Vite + Vue3 + TS + Tailwind + Pinia + Vue Router 脚手架。
2. 设计系统落地：`styles/tokens.css`（色彩 / 动效 token）+ `styles/main.css`（按钮、输入框、卡片、Toast、骨架屏、徽标）。
3. 基础组件：`AppButton`、`AppInput`（浮动标签）、`AppCard`（实心 / 玻璃）、`AppToastHost`、`AppSkeleton`。
4. 登录页：品牌区 Canvas 拓扑动画、浮动标签、密码强度条、字段校验与服务端错误两种错误态、抖动反馈。
5. 路由守卫（未登录重定向 `/login` 并记录 redirect）、Axios 拦截器（自动携带 Bearer、401 清理凭证并跳转、失败统一 Toast）。
6. 工作台占位页：展示当前用户并拉取 `/api/records`，用于验证鉴权链路。

### 验证结果

| 项 | 结果 |
| --- | --- |
| 后端测试 | 21 个用例全部通过 |
| 前端类型检查 + 构建 | `vue-tsc --noEmit && vite build` 通过 |
| 真实 HTTP 冒烟 | 注册 → 登录 → `/me` → 创建记录 → 列表 → 无 token 401，全部符合预期 |
| 迁移执行 | `alembic upgrade head` 成功，表：`users`、`datasets`、`training_records`、`alembic_version` |

### 决定与偏离

- **`datasets` 表提前到阶段一**：`training_records.dataset_id` 为外键，必须先存在被引用表。阶段三只需补上传、解析与统计逻辑。
- **`model_config` 命名处理**：Pydantic v2 保留 `model_config` 作为配置属性，无法作字段名。数据库列名仍为 `model_config`，ORM 属性与 schema 字段用 `network_config` + alias，对外 JSON 契约保持不变（已有测试覆盖）。
- **注册不返回 token**：注册返回 201 用户信息，前端再调用登录，保持接口语义单一。
- **认证端点错误静默**：登录 / 注册的错误在表单内联展示，不触发全局 Toast 与 401 跳转；其余接口失败统一 Toast，不存在静默失败。
- **`.gitignore` 补充**：新增 `node_modules/`、`*.db` 等，避免依赖与本地数据库进入版本库。

### 已知限制

- Token 存于 localStorage（Bearer 头），存在 XSS 风险；httpOnly Cookie + CSRF 方案仍待决策。
- 登录页视觉仅通过构建与代码评审验证，尚未做浏览器截图核对。
- 沙箱 shell 故障未修复，后续每次执行命令仍需授权。

---

## 2026-10-17 · 测试账号与密码策略调整

**类型**：配置调整
**对应提交**：`feat: 密码最小长度调整为 6 位，新增测试账号种子脚本`

### 本次对话完成的工作

1. 新增 `backend/scripts/seed_test_user.py`：创建或重置测试账号，可重复执行（幂等），密码以 argon2id 哈希入库。
2. 创建测试账号 `admin` / `123456`（数据库 id=2，位于 `backend/deepvision.db`）。
3. 密码最小长度由 8 位调整为 6 位，前后端同步：
   - 后端 `RegisterRequest`（`backend/app/schemas/auth.py`）
   - 前端登录/注册页校验（`frontend/src/views/LoginView.vue`）
4. 补充测试 `test_six_char_password_accepted`，用例总数 21 → 22。
5. README 新增「测试账号」章节；修正 Python 版本说明（3.12 与 3.14 均验证通过）。

### 验证结果

| 项 | 结果 |
| --- | --- |
| 后端测试 | 22 个用例全部通过 |
| 前端构建 | `vue-tsc --noEmit && vite build` 通过 |
| 真实登录 | `admin/123456` 返回 200；`/api/auth/me` 返回 admin；错误密码返回 401 |

### 决定与风险

- 密码最小长度从 8 降到 6，安全性随之下降（OWASP 建议 8 位以上）。此处为满足本地测试账号的便利性，属于有意识的取舍。
- `admin/123456` 为弱口令，仅限本地开发。仓库为 Public，公网部署前必须删除该账号或更换密码；脚本与 README 均已注明。

---

## 2026-10-17 · 阶段一完成状态确认与本地环境处置

**类型**：里程碑确认
**对应提交**：`docs: 补记阶段一完成状态与本地环境处置`

### 阶段一验收标准逐项确认

| 设计文档验收项 | 结果 | 依据 |
| --- | --- | --- |
| 密码为 argon2 哈希，无明文 | 通过 | `test_password_is_argon2_hashed`；库中值为 `$argon2id$v=19$...` |
| 登录返回 JWT，可访问 `/api/records` | 通过 | 真实冒烟：`token_len=141`，`/api/records` 返回 200 |
| 无 token / 过期返回 401 | 通过 | `test_me_requires_token`、`test_expired_token_returns_401` |
| 未登录访问 `/workspace` 重定向 `/login` | 通过 | `frontend/src/router/index.ts` 全局守卫 |
| 1440×900 无横向滚动；两种错误态可复现 | 已实现 | `body { overflow-x: hidden }`；字段校验与表单底部错误各一 |
| 请求失败均有 Toast，无静默失败 | 通过 | Axios 拦截器统一提示（认证端点走内联展示） |

### 本地环境处置

1. PyCharm 项目 SDK 指向 `D:\AI-web\.venv`（Python 3.14.6，PyCharm 自动创建），与依赖所在的 `backend\.venv`（3.12）不一致，导致编辑器大面积报「无法解析导入」。
   - 已向 `D:\AI-web\.venv` 补齐 15 个依赖：uvicorn、PyJWT、argon2-cffi、argon2-cffi-bindings、pydantic-settings、httpx、httpcore、httptools、websockets、watchfiles、pyyaml、python-dotenv、click、h11、certifi。
   - 用该 3.14 解释器运行测试：22 个用例全部通过；`pip check` 无损坏依赖。
   - **更正先前结论**：Python 3.14 可以安装本项目后端依赖（此前「3.14 缺 wheel 装不上」的判断有误，实际是镜像或 pip 的偶发问题）。
2. IDE 导入解析：`app.*` 位于 `backend/` 下，需在 PyCharm 中把 `backend` 标记为 Sources Root，否则 `backend/alembic/env.py` 等文件显示无法解析。**此提示仅影响 IDE 索引，不影响运行**——`alembic.ini` 的 `prepend_sys_path = .` 与 `pytest.ini` 的 `pythonpath = .` 已保证运行时导入正确。
3. 现存两个虚拟环境：根 `.venv`（Python 3.14）与 `backend\.venv`（Python 3.12），均含完整依赖，尚未统一。

### 仓库状态

- `main` 与 `origin/main` 同步，当前提交 `52122d5`。
- 工作区干净，无未跟踪文件；`.venv`、`node_modules`、`*.db`、`dist` 均已被 `.gitignore` 正确忽略。
- 阶段一相关提交：

| 提交 | 内容 |
| --- | --- |
| `f09258b` | 后端：认证与训练记录 CRUD |
| `7a3d362` | 前端：登录页、路由守卫、鉴权拦截器 |
| `cc64a35` | README、gitignore 与阶段一日志 |
| `5854ab5` | 密码最小长度改为 6 位、测试账号种子脚本 |
| `52122d5` | README 补充测试账号说明 |

### 待办

- 统一虚拟环境（根 `.venv` 或 `backend\.venv` 二选一），避免后续混淆。
- `admin/123456` 为弱口令，公网部署前必须删除或改密。
- 阶段二开工前需先决策：画布是否限制为链式结构（设计文档 §2.2 与 §5.3 的 DAG 冲突）。

---

## 2026-10-18 · 完成阶段二开发（拖拽式拓扑编辑器）

**类型**：功能开发
**对应提交**：
- `feat(backend): 新增拓扑校验接口（阶段二）`
- `feat(frontend): 拖拽式网络拓扑编辑器（阶段二）`

### 开工决策

1. **图可视化采用自研 SVG，不引入 G6**。设计文档 §8 允许二选一；G6 v5 的 API 变动大，且无法在浏览器中实时调试，自研可完全控制交互且能用构建验证。已同步修改设计文档 §3.2 的技术选型表。
2. **画布允许任意 DAG，但训练仅支持链式结构**。分支 / 汇合在结构上合法，后端校验返回 warning，训练入口据此拦截。用于消解设计文档 §2.2（仅 MLP）与 §5.3（任意 DAG）的矛盾；已作为「实现决策」写入 §8 阶段二。

### 后端交付

- `POST /api/graph/validate`（需登录），返回 `{ valid, errors, warnings }`。
- `app/services/graph_validation.py`：节点 id 唯一性、连线端点存在性、自连、重复连线、输入层不可作为终点、输出层不可作为起点、成环检测（迭代 DFS，避免深层递归）、单输入 / 单输出校验、分支与孤立节点告警。
- `app/schemas/graph.py`：`ModelConfigIn` / `GraphValidationResult`，与 §6.3 契约一致。
- `backend/tests/test_graph.py`：10 个用例覆盖上述规则。

### 前端交付

| 文件 | 职责 |
| --- | --- |
| `types/graph.ts` | 节点 / 边 / `model_config` 契约、节点默认参数、节点摘要 |
| `stores/graph.ts` | 拓扑状态、连线校验（成环 / 自连 / 重复）、撤销重做（50 步）、快速模板、草稿读写 |
| `composables/useCanvasViewport.ts` | 视口缩放（25%–400%，以光标为锚点）与平移 |
| `components/canvas/NetworkCanvas.vue` | 画布主体：网格、贝塞尔连线、拖拽、连线交互、键盘快捷键 |
| `components/canvas/GraphNode.vue` | 节点渲染与端口 |
| `components/canvas/NodeLibrary.vue` | 节点库，支持拖拽入画布与点击添加 |
| `components/canvas/PropertyPanel.vue` | 三类节点的参数编辑 |
| `components/canvas/CanvasMinimap.vue` | 小地图与视口框，点击可导航 |
| `components/canvas/CanvasToolbar.vue` | 撤销 / 重做、缩放、模板、清空、校验、保存状态 |
| `views/WorkspaceView.vue` | 三栏工作台：节点库 + 画布 + 属性面板 |
| `api/graph.ts` | 调用后端拓扑校验 |

同时新增 `.dv-input-plain` / `.dv-select` 两个通用表单样式类。

### 验证结果

| 项 | 结果 |
| --- | --- |
| 后端测试 | 32 个用例全部通过（阶段一 22 + 阶段二 10） |
| 前端构建 | `vue-tsc --noEmit && vite build` 通过（120 个模块） |
| 集成验证 | 同时启动前后端后：Vite 代理下 `admin/123456` 登录成功；链式拓扑返回 `valid=true`；分支拓扑返回 `valid=true` 且 warnings 含「分支或汇合」 |

### 未验证 / 已知限制

- 画布的**实际交互**（拖拽、连线、缩放、撤销重做）**未在浏览器中操作验证**，目前只有类型检查、构建与接口层面的证据。建议按 §8 阶段二验收清单人工过一遍。
- 「100 节点下拖动帧率不低于 50fps」未实测。
- 阶段一工作台的训练记录列表已移除，按设计文档 §5.6 归入后续 `/history` 页面；训练记录相关 API 保持不变。
- 属性面板连续修改参数会各占一步撤销记录。

---

## 2026-10-18 · 支持分支与汇合（DAG 训练语义）

**类型**：能力扩展
**对应提交**：
- `feat(backend): 支持分支与汇合的 DAG 执行计划`
- `feat(frontend): 移除链式结构限制提示`

### 背景

阶段二上线后，画布对含分支 / 汇合的拓扑会显示「训练仅支持链式结构」的黄色警告。用户要求解决该限制，而不是把它留到后续版本。

### 变更内容

**后端**

- 新增 `app/services/dag.py`：Kahn 拓扑排序 + 执行计划生成（`merge` / `order` / `steps[].inputs`）。阶段四的训练引擎将直接消费该计划物化 PyTorch 模块。
- `GraphValidationResult` 增加 `execution_plan` 字段，校验通过时一并返回。
- 校验规则调整：
  - 分支 / 汇合不再产生告警；
  - 「无法从输入层到达」由 warning 升级为 **error**（这类节点无法参与计算）；
  - 「输出不会影响最终结果」保留为 warning（死分支，不影响训练）；
  - 多输入 / 多输出改为 error；
  - 成环检测独立执行，与其他校验同时报出，避免只看到一个错误。
- 测试：移除 2 个旧用例（分支告警、孤立节点告警），新增 3 个（分支合法且生成计划、汇合 `concat`、不可达报错），用例总数 32 → **33**。

**前端**

- 移除画布顶部「当前拓扑存在分支或汇合，训练仅支持链式结构」提示——同时消除了该提示与右上角工具栏**视觉重叠**的问题。
- `graph` store 移除 `hasBranch`。
- 节点库底部说明改为「支持分支与汇合，汇合按特征维 concat 合并」。

**文档**

- §2.2 范围：由「仅 MLP」改为「全连接层 + 任意前馈 DAG」。
- §7.2 接口表补上 `/api/graph/validate`（此前遗漏）。
- §8 阶段二实现决策更新；阶段四交付物与验收标准补充 DAG 训练要求。

### 汇合语义约定

汇合节点（多前驱）在**特征维**按前驱声明顺序 `concat`。
例：两个隐藏层各输出 64 维 → 汇合后为 128 维 → 送入后续层。

### 验证结果

| 项 | 结果 |
| --- | --- |
| 后端测试 | 33 个用例全部通过 |
| 前端构建 | `vue-tsc --noEmit && vite build` 通过 |
| 汇合计划 | 测试断言 `n4` 的 `inputs == ["n2", "n3"]`，且 `order` 首尾为输入 / 输出节点 |

### 遗留

- 实际训练尚未实现（阶段四），`execution_plan` 目前只被校验接口消费。
- `concat` 之外的汇合方式（`add` / `multiply`）未实现，`merge` 字段已预留扩展位。

---

## 2026-10-18 · 完成阶段三开发（CSV 上传与预处理）

**类型**：功能开发
**对应提交**：
- `feat(backend): CSV 数据集上传解析与统计（阶段三）`
- `feat(frontend): 数据集上传页与 CSV 解析（阶段三）`

### 环境处置与偏离

1. pandas 3.0.6 / numpy 2.5.4 / python-multipart 0.0.32 经**阿里云镜像**装入两个虚拟环境（清华镜像当时 SSL 握手失败）。
2. **PapaParse 未能安装**：npm 持续报 `Invalid Version`。定位过程：清空 `node_modules` 后 `npm ci` 仍失败 → 说明损坏在 `package-lock.json`；备份并删除 lock 后 `npm install` 恢复正常。前端因此改为**自研 CSV 解析器**。
3. 清理 `node_modules` 时曾删到一半被运行中的 vite / esbuild 进程锁住，导致构建报 `vue-tsc is not recognized`；终止残留进程后完整重装（153 个包）。
4. 集成验证时 httpx 默认走系统代理（Clash），访问 localhost 返回 502；改用 `trust_env=False` 绕过。

### 后端交付

- `app/services/csv_service.py`：UTF-8 / GBK 解码、列类型推断、四种缺失值策略、均值 / 方差 / 目标分布统计、文件落盘。
- 接口：`POST /api/datasets`（multipart）、`GET /api/datasets`、`GET /api/datasets/{id}`。
- 数据集表新增 `target_column`、`missing_strategy`、`stats` 三列，迁移 `2b11c1dd2f2c`。
- `requirements.txt` 增加 pandas、python-multipart。
- 测试 `tests/test_datasets.py`：14 个用例。

### 前端交付

| 文件 | 职责 |
| --- | --- |
| `utils/csv.ts` | 自研 CSV 解析器（引号 / 转义 / 字段内换行 / CRLF / BOM）、列类型推断、处理后样本数估算 |
| `views/DataView.vue` | 拖拽上传、预览表、列角色、缺失值策略、处理后样本数、提交、结果统计 |
| `api/datasets.ts` | 上传与列表接口封装 |
| `router/index.ts` | 新增 `/data` 路由 |
| `views/WorkspaceView.vue` | 顶栏「数据集」入口启用 |

### 验证结果

| 项 | 结果 |
| --- | --- |
| 后端测试 | 47 个用例全部通过（阶段二 33 + 阶段三 14） |
| 前端构建 | `vue-tsc --noEmit && vite build` 通过（124 个模块） |
| 集成验证 | 起前后端 → `admin/123456` 登录 → 经 Vite 代理上传 CSV 返回 **201**；`sample_count=4`、`feature_count=2`、`f1 mean=2.5`、`variance=1.666667`、目标分布 `{0:2, 1:2}`、列表 total=1 |

### 验收对照

- 非 CSV、空文件、超限、解析失败四类异常均有明确错误码与中文提示，测试覆盖。
- 统计与 Pandas 直接计算结果一致（测试用 `df.var(ddof=1)` 对齐）。
- 前端「处理后样本数」与后端 `dropna` 语义一致。

### 遗留与风险

- 前端解析器替代 PapaParse 属环境所迫的偏离；依赖树已修复，后续可直接换回。
- `package-lock.json` 已重新生成，部分依赖版本可能小幅上浮。
- 「10MB 文件 3s 内完成预览」未实测（浏览器交互仍未验证）。
- 缺失值策略仅对所选列生效；**标准化与类别编码尚未实现**，这是阶段四训练前的必要前置。
