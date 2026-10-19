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

---

## 2026-10-18 · 完成阶段四开发（训练引擎与实时可视化）

**类型**：功能开发
**对应提交**：
- `feat(backend): 训练引擎与 WebSocket 实时推送（阶段四）`
- `feat(frontend): 训练监控页与实时图表（阶段四）`

### 环境处置

- PyTorch **2.14.1+cpu**、ECharts **6.1.0** 安装成功（torch 经阿里云镜像，约 200MB）。
- 数据集表新增 `feature_columns`；自动生成的迁移在 SQLite 上因「NOT NULL 且无默认值」失败，改为先 `server_default='[]'` 回填再移除默认值。
- 阶段三遗留的「标准化 / 类别编码」缺口在本次一并补齐。

### 后端交付

| 模块 | 职责 |
| --- | --- |
| `services/preprocessing.py` | 缺失值 → 类别独热 → z-score（统计量仅取训练集） → 8:2 划分；类别数上限 50 |
| `services/dag_model.py` | 按执行计划物化 PyTorch 模块，汇合节点按前驱顺序 `concat` |
| `services/training.py` | 任务注册表、后台线程执行、事件广播、历史回放、权重落盘、记录入库 |
| `api/v1/train.py` | `POST /api/train`（校验拓扑与数据集归属）、`POST /api/train/{task_id}/stop` |
| `api/realtime.py` | `WS /ws/train/{task_id}`（独立路径，不走 `/api` 前缀），心跳与重连回放 |

- 训练结束（成功 / 失败 / 中止）都会写入 `training_records`，并保存 `storage/models/{user_id}/{task_id}.pt`。
- 测试：`test_preprocessing.py`（7 个）+ `test_training.py`（7 个），用例如总数 47 → **61**。

### 前端交付

| 文件 | 职责 |
| --- | --- |
| `composables/useTrainingSocket.ts` | WebSocket 客户端 + 指数退避重连（1s→16s，最多 5 次） |
| `views/TrainView.vue` | ECharts 双轴曲线、进度条、拓扑流光、日志流、停止训练 |
| `components/train/StartTrainingDialog.vue` | 数据集选择与超参设置 |
| `components/train/TrainingTopology.vue` | SVG 拓扑与前向流动画（`stroke-dashoffset`） |
| `vite.config.ts` | 新增 `/ws` 代理（`ws: true`），否则开发环境 WS 无法连通 |

### 验证结果

| 项 | 结果 |
| --- | --- |
| 后端测试 | 61 个用例全部通过（含训练端到端与停止） |
| 前端构建 | `vue-tsc --noEmit && vite build` 通过（726 模块） |
| 端到端 | 起前后端 → 上传 CSV 201 → 创建训练 202 → 经 **Vite 的 WS 代理**收到 `started + 5×epoch + completed`；最终 `val_loss=0.707`、`record_id=2`；记录 `status=success` |

### 已知限制

- 「停止训练」有接口测试覆盖，但未在浏览器中实际操作验证。
- 拓扑流光为**视觉表现**（固定节奏），不是逐 batch 的数据驱动；设计文档已注明。
- 输入层特征数需手动与预处理后维度一致：类别特征会做独热编码从而扩展维度，不一致时后端会返回明确错误。
- ECharts 全量引入使 TrainView chunk 达 1.1MB，未做按需引入优化。
- 断线重连的浏览器行为未实测；服务端回放逻辑有实现但只有代码级保证。

---

## 2026-10-18 · 完成阶段五开发（AI 助教与拓扑诊断）

**类型**：功能开发
**对应提交**：
- `feat(backend): AI 助教问答与拓扑诊断（阶段五）`
- `feat(frontend): AI 助教抽屉与一键应用建议（阶段五）`

### 关键前提

用户未提供 LLM API Key。按设计文档验收标准「LLM 不可用时返回友好降级提示」，本阶段做成**双模式**：

- 配置 `LLM_PROVIDER` + `LLM_API_KEY`：调用 OpenAI 兼容流式接口（GLM 改 `LLM_BASE_URL` 即可）；
- 未配置或调用失败：自动降级为**内置知识库**，问答与诊断功能完整可用且可测试。

### 后端交付

| 模块 | 职责 |
| --- | --- |
| `services/knowledge_base.py` | 14 条深度学习知识条目 + 关键词检索打分 |
| `services/llm.py` | 双模式适配：LLM 流式 / 知识库降级，统一产出 `meta` / `delta` / `done` |
| `services/diagnosis.py` | 规则引擎：健康评分、问题列表、可应用建议（仅限已有节点参数） |
| `services/ai_guard.py` | 敏感词拦截与脱敏、滑动窗口限流（20 次/分钟） |
| `api/v1/ai.py` | `POST /api/ai/chat`（SSE 流式）、`POST /api/ai/diagnose` |

- 建议字段白名单：`features` / `units` / `activation` / `task`，保证前端「一键应用」可靠。
- 测试：`tests/test_ai.py` 13 个用例，总数 61 → **74**。

### 前端交付

| 文件 | 职责 |
| --- | --- |
| `api/ai.ts` | SSE 流式解析（`fetch` + `ReadableStream`）与诊断请求 |
| `components/ai/AssistantDrawer.vue` | 全局悬浮入口、问答/诊断双标签、流式渲染、来源脚注、一键应用 |
| `App.vue` | 登录后全局挂载助教入口（登录页不显示） |
| `NetworkCanvas.vue` | 小地图上移，避让右下角悬浮按钮 |

- 「一键应用」调用 `graph.updateParams`，会 `pushHistory`，因此可 `Ctrl+Z` 撤销。

### 验证结果

| 项 | 结果 |
| --- | --- |
| 后端测试 | 74 个用例全部通过（新增 13 个 AI 用例） |
| 前端构建 | `vue-tsc --noEmit && vite build` 通过（729 模块） |
| 端到端问答 | 经 Vite 代理请求 `/api/ai/chat` 返回 200，事件 `meta + 10×delta + done`，`mode=fallback`，来源含「内置知识库 · 梯度消失与梯度爆炸」 |
| 端到端诊断 | 输入 20 维、隐藏层 4 个神经元 → `score=92`，issue「隐藏层 n2 神经元数偏少」，建议 `n2.units 4 → 20` |

### 已知限制

- 未接入真实大模型（无 Key）：LLM 分支代码已实现但**未真实调用验证**；接上 Key 后需重新验证流式解析。
- 知识库为人工编写的 14 条，覆盖面有限；未命中时退回前两条，回答质量一般。
- 诊断建议不含「新增节点」类操作（如自动加隐藏层），只改现有节点参数。
- 限流为进程内实现，多实例部署需替换为 Redis。
- 助教抽屉在浏览器中的实际交互（流式渲染、一键应用后的撤销）未人工验证。

---

## 2026-10-18 · 修复：训练前缺少结构预检

**类型**：缺陷修复
**对应提交**：`fix: 训练前预检输入/输出层数量，报错点名节点`

### 问题

用户在「开始训练」对话框中点击提交后，才看到「存在多个输入层，首版仅支持单输入」；报错未指出具体节点，且对话框打开时没有任何提示。

### 变更

- **后端** `graph_validation.py`：多输入 / 多输出错误改为**点名节点 id**，并提示「请只保留一个」。
- **前端** `StartTrainingDialog.vue`：
  - 新增 `structuralError` 计算属性——打开对话框即校验输入 / 输出层数量，问题立即显示且禁用「开始训练」按钮，不必等提交后才报错；
  - 数据集选项文案改为「N 个特征列」，并补充提示「类别列独热编码后实际维度会变大」。
- **测试**：新增 `test_multiple_inputs_message_lists_node_ids`，用例总数 74 → **75**。

### 验证

- 后端 75 个测试全部通过；前端构建通过。
- 重启后端后实测多输入层请求，返回：`存在多个输入层（i1、i2），请只保留一个输入层`。

### 环境补充

- 为 `backend\.venv`（Python 3.12）补装 torch 2.14.1+cpu。此前该环境缺 torch，若 PyCharm 解释器选成它会直接启动失败；现在**两个虚拟环境都可用于启动后端**。
- 后端已重启（不带 `--reload`），监听 `127.0.0.1:8000`。

---

## 2026-10-18 · 第二大阶段 P1：顶栏视图切换与逐层统计

**类型**：功能开发（第二大阶段起步）
**对应提交**：
- `feat: 第二大阶段 P1——逐层统计与顶栏视图切换`
- `docs: 设计文档升级至 v3.0（纳入第二大阶段）`

### 背景

用户提供《设计文档第二版》，定义**第二大阶段**四个模块（3D 拓扑引擎、左侧控制面板、底部监控仪表盘、AI Agent），并要求在画布顶栏的空白区域接入新功能、同步升级设计文档。

该空白区正对应模块一要求的「顶栏视图模式切换（权重 / 梯度 / 激活）」，因此先落地这条链路，并补齐它所需的数据基础。

### 后端

- `DagNet` 新增 `forward_intermediates()`，按拓扑序返回每个节点的输出张量；`forward()` 复用之。
- 训练每个 epoch 收集**逐层统计**：`weight_norm`（权重绝对值之和）、`grad_norm`（梯度绝对值之和）、`activation_mean`（该层激活绝对值均值），随 `epoch` 事件推送。
- `grad_norm` 汇总值并入 epoch 指标，供后续指标卡使用。
- 最后一轮统计写入 `training_records.result_metrics.layer_stats`，前端可据此渲染历史记录。
- 修复一处调用错误：`nn.ModuleDict` 没有 `.get()`，改为成员判断 + 下标取值。

### 前端

- `graph` store 新增 `viewMode`（weight / gradient / activation）、`layerStats`、`layerStatsLoaded`。
- **顶栏空白区新增「视图：权重 / 梯度 / 激活」分段控件**（即用户标注的红框位置）。
- 画布渲染接入视图模式：连线线宽按目标层指标归一化（激活模式取源节点），节点发光强度按该层指标渲染；未训练过时退化为中性样式，控件 tooltip 提示「完成一次训练后可查看逐层数据」。
- 工作台加载时读取最近一次训练记录的 `layer_stats`。

### 设计文档

- 升级到 **v3.0**：新增 §11「第二大阶段」，含四模块需求与验收标准、与第一大阶段的复用关系、差异决策（Three.js 引入、不用 MySQL、2D 编辑 / 3D 只读、新增暂停信令）、实施批次与进度。
- §3.2 技术选型补充 Three.js 行；目录与变更记录同步。

### 验证结果

| 项 | 结果 |
| --- | --- |
| 后端测试 | 75 个用例全部通过（训练用例新增 `layer_stats` 断言） |
| 前端构建 | `vue-tsc --noEmit && vite build` 通过 |
| 数据链路 | epoch 事件携带 `layer_stats`；`result_metrics.layer_stats` 已持久化（测试覆盖） |

### 已知限制与后续

- **视图切换的视觉差异未在浏览器中人工验证**；切换后需要先完成一次训练，逐层数据才存在。
- 第二大阶段其余模块尚未开始：P2（Three.js 3D 拓扑）、P3（左侧滑块与暂停/恢复信令）、P4（底部仪表盘）、P5（AI 面板升级）。
- 3D 与 2D 的关系已定为「2D 编辑、3D 只读展示」，避免两套编辑逻辑冲突。

---

## 2026-10-19 · 第二大阶段模块一：3D 神经网络拓扑可视化

**类型**：功能开发
**对应提交**：
- `feat(frontend): 3D 神经网络拓扑视图（第二大阶段模块一）`
- `docs: 更新设计文档与 README（3D 视图）`

### 依赖

- `three` 0.186.1 + `@types/three` 0.186（npm 镜像源安装）

### 前端交付

新增 `frontend/src/components/threed/Network3DView.vue`：

| 能力 | 实现 |
| --- | --- |
| 节点 | `MeshStandardMaterial` 球体 + `AdditiveBlending` 光晕 Sprite；半径由该层神经元数决定 |
| 着色 | 输入浅蓝 `#7dd3fc`、隐藏亮青 `#22d3ee`、输出紫 `#a78bfa` |
| 布局 | 按拓扑层级沿 Z 轴分层，层内环形排布（Kahn 拓扑序求层级） |
| 连线 | `TubeGeometry`，半径与不透明度按当前视图模式指标归一化 |
| 交互 | `OrbitControls`：左键旋转、滚轮缩放、右键平移 |
| 悬浮 | 射线拾取节点 / 连线，气泡显示权重、梯度、激活三项数值 |
| 激活模式 | 光晕按 `sin` 呼吸，幅度与激活强度相关 |
| 降级 | WebGL 初始化失败时显示提示，2D 画布不受影响 |

工作台集成：

- 顶栏新增「3D 视图 / 2D 编辑」切换按钮，与「权重 / 梯度 / 激活」视图控件并排。
- `Network3DView` 通过 `defineAsyncComponent` **按需加载**。
- 3D 模式下点击节点库会自动切回 2D 再添加节点，避免操作落空。
- 卸载时完整释放 renderer / geometry / material，并断开 ResizeObserver 与动画帧。

### 构建产物

| 产物 | 变化 |
| --- | --- |
| `WorkspaceView` chunk | 601KB → **30KB**（three.js 拆出） |
| `Network3DView` chunk | **571KB**，仅切到 3D 时下载 |

### 验证结果

| 项 | 结果 |
| --- | --- |
| 前端类型检查 + 构建 | `vue-tsc --noEmit && vite build` 通过（735 模块） |
| 后端 | 本批次未改动后端，无回归风险 |

### 已知限制

- **未在浏览器中验证 WebGL 渲染效果**（沙箱无法驱动图形环境）。以下需人工确认：球体与光晕是否正常显示、旋转/缩放/平移是否顺手、激活呼吸是否明显、悬浮气泡是否正确。
- 3D 布局为自动分层环形排布，不沿用 2D 画布的手工坐标；节点较多时可能拥挤。
- 连线为直线（Tube），未做曲线避让，节点密集时可能穿插。

### 待办

- P3：左侧滑块面板、重建模型、暂停 / 恢复信令
- P4：底部仪表盘（权重直方图、决策边界散点、指标卡）
- P5：AI 面板升级（引擎选择、上下文打包、Markdown 渲染）

---

## 2026-10-19 · 第二大阶段修正：独立教学实验室 `/lab`

**类型**：需求修正 + 功能开发
**对应提交**：
- `feat(backend): 教学实验室训练服务与实时通道`
- `feat(frontend): 独立教学实验室页面 /lab`
- `docs: 修正第二大阶段定位并更新文档`

### 背景（重要修正）

用户指出此前的理解有误：第二大阶段**不是**第一阶段工作台里的一个「3D 视图」开关，而是**独立的教学实验室页面**——左参数、中 3D、下仪表盘、右助教，使用内置双螺旋数据集，支持暂停与实时调参。

### 后端

`app/services/lab.py`：

- **内置双螺旋数据集**：2 维 2 类，共 2000 点，1400 训练 / 600 验证，无需上传。
- 按配置构建 MLP：隐藏层数、每层神经元、激活函数、初始化（He / Xavier / 均匀）、优化器（Adam / SGD）、学习率、批大小、轮数、L2、Dropout。
- 训练在后台线程执行，支持**暂停 / 恢复 / 停止**（`threading.Event`），暂停期间不产生新 epoch。
- 每 epoch 推送 train/val loss、验证准确率、梯度范数；每 3 个 epoch 与首尾推送**权重直方图**（20 箱）与**决策边界**（48×48 概率网格 + 320 个数据点）。

接口：

| 方法 | 路径 |
| --- | --- |
| POST | `/api/lab/train` |
| POST | `/api/lab/{task_id}/pause` · `/resume` · `/stop` |
| WS | `/ws/lab/{task_id}?token=` |

测试 `tests/test_lab.py`：4 个用例，覆盖鉴权、参数量、事件流、暂停/停止。用例总数 75 → **79**。

### 前端

| 文件 | 职责 |
| --- | --- |
| `views/LabView.vue` | 四区布局与全部状态编排 |
| `components/lab/LabNetwork3D.vue` | 分层球体 + 相邻层全连接 + 层名投影标签 + OrbitControls |
| `components/lab/LabDashboard.vue` | 5 张 KPI 卡 + loss 曲线 + 权重直方图 + canvas 决策边界 |
| `composables/useLabSocket.ts` | 实验室 WebSocket 客户端 |
| `api/lab.ts` | 任务创建与控制 |

- 新路由 `/lab`，工作台顶栏新增「教学实验室」入口。
- 左栏滑块改变层数 / 神经元后，3D 网络与参数量实时更新。
- 右栏助教：模型引擎选择、4 个快捷问题、「诊断训练状态」自动附带当前结构与指标上下文、流式输出、实时指标列表。

### 验证结果

| 项 | 结果 |
| --- | --- |
| 后端测试 | 79 个用例全部通过 |
| 前端构建 | `vue-tsc --noEmit && vite build` 通过（743 模块） |
| 端到端 | `POST /api/lab/train` 返回 202、参数量 **114**；WS 收到 `started` + 3×`epoch` + `weights`（96 条连接）+ `boundary`（2304 个网格值 / 320 个点）+ `completed` |

### 已知限制

- **未在浏览器中人工验证** 3D 渲染、图表与滑块交互。
- 顶栏的「前向/反向传播、注意力 3D、降维投影」仅预留入口，未实现。
- AI 面板仍是纯文本流式输出，**Markdown 渲染未做**。
- 实验室训练结果**不写入**第一阶段的 `training_records`，两套体系目前相互独立。
