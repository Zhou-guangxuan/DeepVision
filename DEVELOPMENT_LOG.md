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
