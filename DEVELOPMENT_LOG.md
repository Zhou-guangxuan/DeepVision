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
