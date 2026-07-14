# 课程学习助手

面向课程资料管理与持续学习的本地桌面应用。项目由 React/Vite/Electron 前端与 FastAPI 后端组成，使用 MySQL 保存结构化数据，ChromaDB 保存本地向量索引。课程、资料检索、Agent 多轮问答、任务、学习计划、学习记录、笔记、Notion/Obsidian 同步和运行审计均在同一工作台中完成。

## 仓库结构

```text
course-agent-backend/   FastAPI、Agent、MySQL 模型、文件解析与向量检索
course-agent-frontend/  React/Vite 页面、Electron 宿主与桌面打包配置
README.md               本说明
.gitignore              统一忽略本机依赖、数据、密钥与构建产物
```

以下目录会保留在开发电脑上，但不会上传 GitHub：`.venv`、`node_modules`、`build`、`dist`、`release`、`uploads`、`chroma_db`。删除 `.venv` 或 `node_modules` 后可以重新安装，但并不是提交代码前必须删除；`.gitignore` 已足够阻止它们被提交。`uploads`、`chroma_db` 和 `.env` 是本机数据/配置，更不应提交。

## 环境要求

- Windows 10/11
- MySQL 8.0+
- Python 3.13（当前项目已验证 3.13.9）
- Node.js 24（当前项目已验证 24.15.0）
- 可选：Tesseract OCR，用于没有可用文本层的扫描 PDF

## 安全配置 MySQL

不要让应用使用 MySQL `root` 账号。先登录 MySQL，创建独立数据库和最小权限账号；下面的强密码仅是占位符，必须替换：

```sql
CREATE DATABASE course_agent
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

CREATE USER 'course_agent'@'localhost'
  IDENTIFIED BY '请替换为至少16位的随机强密码';

GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, REFERENCES
  ON course_agent.* TO 'course_agent'@'localhost';
FLUSH PRIVILEGES;
```

如果程序和 MySQL 不在同一台电脑，应限制数据库防火墙来源、启用 TLS，并把 `'localhost'` 替换成明确的客户端主机；不要把 3306 端口直接暴露到公网。

## 开发运行

### 1. 后端

```powershell
cd course-agent-backend
Copy-Item .env.example .env
```

编辑 `.env`，至少填写 `DATABASE_URL`、随机 `SECRET_KEY` 和所用模型的 API Key。真实 `.env` 已被 Git 忽略。

首次安装依赖：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

已有 `.venv` 时不需要重复安装。启动后端：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

首次启动会在已创建的 MySQL 数据库中建立所需数据表。健康检查地址为 `http://127.0.0.1:8000/health`。

### 2. 前端

另开一个 PowerShell：

```powershell
cd course-agent-frontend
npm install
npm run dev
```

访问 Vite 输出的本地地址。开发环境通过 Vite 代理连接 `127.0.0.1:8000`。

## 构建桌面程序

```powershell
cd course-agent-frontend
npm run dist
```

该命令会先通过 PyInstaller 构建内嵌 FastAPI 后端，再构建前端并生成 Electron 安装版与便携版。产物位于 `course-agent-frontend/release/`，属于可再生成文件，因此不提交 Git；需要对外发布时请上传到 GitHub Releases。

桌面包不再携带源码目录中的真实 `.env`。用户第一次打开程序时会看到 MySQL 配置页；数据库密码与程序生成的 JWT 密钥通过 Electron `safeStorage` 使用当前 Windows 登录凭据加密，配置文件保存在当前系统用户的应用数据目录。密钥不会写入安装目录，也不会通过 Git 分发。

> 桌面程序包含 Python 运行环境和必要依赖，但 MySQL 服务仍需用户自行安装、启动并创建数据库。向量模型第一次使用时可能需要联网下载，之后使用本地缓存。

## 文件上传与后台处理

上传接口收到文件并创建资料记录后立即返回，解析、分块和向量化在后端继续执行。前端提供上传进度与后台处理状态；在课程、任务等页面之间切换不会取消当前上传队列。大文件仍受后端大小限制，扫描 PDF 的 OCR 耗时取决于页数和电脑性能。

## 数据备份与迁移

登录后打开“设置 → 数据备份与迁移”：

1. 输入当前登录密码导出 ZIP；
2. 在新电脑配置新的 MySQL 后，创建并登录目标账号；
3. 导入 ZIP，程序会重新映射主键、复制资料并重建向量索引。

备份包含课程、资料、任务、计划、笔记、对话、学习记录和 Agent 长期记忆，不包含登录密码、外部大模型 API Key、Notion Token、Obsidian 路径或第三方同步状态。归档文件会校验大小、路径和 SHA-256；备份仍可能含私人课程资料，请加密保管，不要提交到 GitHub。

如需数据库管理员级灾备，可另外使用 MySQL 官方工具：

```powershell
mysqldump --single-transaction --routines --triggers -u course_agent -p course_agent > course_agent.sql
mysql -u course_agent -p course_agent < course_agent.sql
```

应用内备份适合账号迁移；`mysqldump` 适合整库运维，两者用途不同。

## GitHub 提交检查

初始化根仓库后，提交前执行：

```powershell
git status --short --ignored
git check-ignore -v course-agent-backend/.env
git check-ignore -v course-agent-backend/.venv/Scripts/python.exe
git check-ignore -v course-agent-frontend/node_modules
git check-ignore -v course-agent-frontend/release
```

然后确认待提交列表中没有 `.env`、数据库密码、API Key、上传文件、向量库、虚拟环境、依赖目录或 EXE。若真实密钥曾经进入 Git 历史，仅添加 `.gitignore` 并不能消除泄漏，必须立即轮换密钥，并使用历史清理工具处理远程仓库。

建议将源码推送到私有仓库完成首次安全审查，再根据需要公开。安装程序使用 GitHub Releases 分发，不要混入源码提交。

## 常用验证

```powershell
# 后端语法与导入检查
cd course-agent-backend
.\.venv\Scripts\python.exe -m compileall -q app
.\.venv\Scripts\python.exe -c "from app.main import app; print(len(app.routes))"

# 前端类型检查与生产构建
cd ..\course-agent-frontend
npm run build
```

## 故障定位

- MySQL 连接失败：确认服务已启动、数据库已创建、账号主机范围和密码正确。
- 上传后一直“处理中”：查看资料状态与桌面应用数据目录中的 `backend.log`。
- 首次检索较慢：本地嵌入模型可能正在下载或加载。
- 扫描 PDF 内容不完整：安装 Tesseract OCR；若原文件字体映射已损坏，程序会提示文本层质量问题，但不能凭空恢复丢失字符。
- 打包空间不足：`.venv`、PyInstaller `build/dist` 和 Electron `release` 会同时占用较多空间，可在确认不需要旧产物后手动清理；清理前不影响源码提交。
