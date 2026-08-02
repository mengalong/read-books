# 回卷

一个面向个人使用的读书复习网站。上传读过的 PDF 后，系统按原文生成单选题、多选题和问答题，并在提交后给出自动评分、参考答案和可定位到 PDF 页码的原文依据。系统会保存生成好的复习试卷；同一套试卷可以反复作答，每次作答单独记录为一个复习任务。

当前版本默认使用 Mock AI Provider，也可以在“模型设置”页面切换到 OpenAI 兼容模型。真实模式支持基于 PDF 原文生成题目和自动评分问答题；客观题仍由后端按标准答案确定性评分。

## 技术栈

- 网页端：Next.js、React、TypeScript、Tailwind CSS
- 后端：FastAPI、Python 3.12、SQLAlchemy、Alembic
- 数据：SQLite、本地文件存储、PyMuPDF
- 测试：pytest、Playwright

## 本地开发

项目使用 Conda 环境 `read-books`。首次安装：

```bash
conda env create -f environment.yml
npm --prefix apps/web install
conda run -n read-books alembic -c apps/api/alembic.ini upgrade head
```

如果环境已经存在，可以使用：

```bash
make setup
```

同时启动前后端：

```bash
make dev
```

- 网页端：<http://localhost:3000>
- API：<http://localhost:8000>
- OpenAPI：<http://localhost:8000/docs>

也可以分别运行 `make dev-web` 和 `make dev-api`。

## 配置

复制根目录 `.env.example` 为 `.env` 后按需修改。开发阶段默认：

```env
MOCK_MODE=true
SEED_DEMO_DATA=true
```

当项目根目录存在 PDF 时，开发启动会自动建立对应书籍并后台解析；如果 PDF 原生文字是乱码或受到复制权限限制，会在 macOS 上自动调用 Vision OCR 兜底。原文片段仍然保留 PDF 页码。本地 PDF、SQLite 数据库和上传目录均不会提交到 Git。

网页端的“模型设置”页面（`/settings/model`）已经支持保存接口地址、模型名称、API Key、请求超时和温度，并通过一个开关选择已配置模型或内部模拟接口。配置保存在本地 SQLite 中，API Key 只在保存时写入，读取接口不会返回明文；页面以固定 16 位掩码显示已配置状态，输入新值并保存即可覆盖更新。页面还可以发送最小 OpenAI 兼容请求测试连接，并展示脱敏后的等价 `curl` 命令和模型实际返回文本。环境变量 `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL`、`LLM_TIMEOUT_MS` 和 `LLM_TEMPERATURE` 仍作为尚未在网页端保存配置时的默认值。

切换到 OpenAI 兼容模式后，新测试会调用配置地址的 `/chat/completions` 生成题目，提交测试时的问答题也会调用同一模型评分。模型只能引用后端提供的原文片段 ID，PDF 文件名、页码和原文摘录由后端从数据库重建；题量、题型、选项、答案、参考答案和评分要点均会经过结构校验。接口不可用或返回内容不合规时，页面会显示明确错误且不会保存不可靠题目。

出题采用持久化后台任务：创建接口立即返回，网页端显示已完成题数和当前阶段，用户可以在生成期间访问其他页面。同一套试卷的多道题按顺序逐题请求模型，每次只要求生成一道题，并缩小候选原文范围，以降低长响应超时和无效 Token 消耗。任务失败会保留已完成题数和错误信息；服务重启后会恢复未完成任务。

“系统管理”下的“提示词管理”页面（`/settings/prompts`）支持调整出题和问答评分两套模板；“Token 用量”页面（`/settings/token-usage`）支持按任务和阶段查看模型调用的输入、输出 Token、耗时和失败信息。模板使用受限变量并保存版本，后端会校验必需变量，真实 Provider 会读取当前启用版本；管理员修改提示词不能绕过题目结构和原文来源校验。书籍详情页支持开启一套后台预生成测试，任务期间页面显示生成状态并禁止重复触发；没有完成解析的 PDF 时不会启动预生成。

预生成的开启状态和运行状态属于具体书籍：用户只会为需要复习的书准备题目，书籍详情页也能清楚展示进度。默认题型、题量、目标时长、并发上限等属于系统策略，后续开放多租户时建议采用“平台默认值 -> 租户覆盖 -> 书籍局部覆盖”的配置层级；任务记录则独立保存，便于管理员按租户查看用量和失败情况。当前本地版使用进程内后台线程，公网部署前应替换为独立任务队列和 Worker。

系统不会在没有 PDF 的情况下让模型凭记忆生成所谓“原文依据”。模型记忆不能保证版本、章节和引文准确，无法满足本系统的原文可追溯要求；需要可靠出题时请先上传并完成解析 PDF。

OCR 配置为 `OCR_ENABLED` 和 `OCR_COMMAND`。当前 OCR 脚本使用 macOS Vision，适合本地开发；其他操作系统若没有对应命令，解析会失败并阻止无依据出题。

## 测试

```bash
make test
```

后端单独测试：

```bash
make test-api
```

## 文档

- [需求设计](docs/reading-review-system-requirements.md)
- [技术选型](docs/technical-selection.md)
- [开发状态](docs/development-status.md)
