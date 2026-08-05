# 回卷

一个面向个人使用的读书复习网站。上传读过的 PDF 后，系统按原文生成单选题、多选题和问答题，并在提交后给出自动评分、参考答案和可定位到 PDF 页码的原文依据；没有电子版时，也可以只填写书名和作者，使用真实模型的内化知识兜底出题。系统会保存生成好的复习试卷；同一套试卷可以反复作答，每次作答单独记录为一个复习任务。

当前版本默认使用 Mock AI Provider，也可以在“模型设置”页面切换到 OpenAI 兼容模型。真实模式支持 PDF 原文和模型知识两种出题来源，并自动评分问答题；Mock 模式只支持已有 PDF 原文，客观题始终由后端按标准答案确定性评分。

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

切换到 OpenAI 兼容模式后，新测试会调用配置地址的 `/chat/completions` 生成题目，提交测试时的问答题也会调用同一模型评分。PDF 模式下模型只能引用后端提供的原文片段 ID，文件名、页码和原文摘录由后端从数据库重建；模型知识模式下来源片段 ID 和原文依据必须为空，系统不会采信或保存模型伪造的页码、文件名和引文。题量、题型、选项、答案、参考答案和评分要点均会经过结构校验，接口不可用或返回内容不合规时不会保存不可靠题目。

出题采用持久化后台任务：创建接口立即返回，网页端显示已完成题数和当前阶段，用户可以在生成期间访问其他页面。同一套试卷的多道题按顺序逐题请求模型，每次只要求生成一道题，并缩小候选原文范围，以降低长响应超时和无效 Token 消耗。实际出题和问答评分请求不主动设置 `max_tokens`，由模型服务按自身能力和上下文窗口决定输出；同时兼容文本片段数组形式的响应。如果模型只返回推理过程或触发模型服务自身输出上限，任务会保留明确失败原因。任务失败会保留已完成题数和错误信息；服务重启后会恢复未完成任务。

“系统管理”下的“提示词管理”页面（`/settings/prompts`）支持调整出题和问答评分两套模板；“Token 用量”页面（`/settings/token-usage`）支持按任务和阶段查看模型调用的输入、输出 Token、耗时和失败信息。出题模板支持书名、作者和来源模式变量，管理员修改提示词不能绕过后端的题目结构与来源校验。书籍详情页展示后台预生成测试的任务状态，生成完成的试卷会进入下方试卷列表；无 PDF 时需要先启用已配置的真实模型，已有但尚未解析完成的 PDF 不会自动降级为模型知识模式。

预生成的运行状态属于具体书籍：后台策略只为符合条件的书准备题目，书籍详情页展示进度和结果，完成后统一从试卷列表进入。默认题型、题量、目标时长、并发上限等属于系统策略，后续开放多租户时建议采用“平台默认值 -> 租户覆盖 -> 书籍局部覆盖”的配置层级；任务记录则独立保存，便于管理员按租户查看用量和失败情况。当前本地版使用进程内后台线程，公网部署前应替换为独立任务队列和 Worker。

书籍详情页的试卷列表会展示难度（基础、适中、深入）、总题数、单选/多选/问答题数量、复习次数和最近成绩。删除试卷前页面会二次确认；删除会级联清理该试卷的题目、复习任务和答案，同时解除预生成及出题任务的结果引用，但保留模型 Token 用量记录用于审计。

全局“复习记录”页面支持按书名或作者搜索（输入完成后按回车提交），也支持按任务状态筛选，并提供查看、继续、重新答题和删除操作。

书架页面的书名和作者搜索同样在输入完成并按下回车后才更新列表，输入过程中不会重复请求后端。

网页展示的任务、试卷、复习、模型测试、提示词版本和 Token 调用时间统一使用北京时间（`Asia/Shanghai`），格式为 `YYYY-MM-DD HH:MM:SS`；后端内部仍统一按 UTC 记录，便于未来多时区部署。

没有 PDF 时，系统会将试卷标记为“模型知识模式”，并在书籍、出题、试卷、答题和结果页面持续提示：题目不具备可靠的 PDF 页码或逐句原文依据，可能受版本差异和模型记忆偏差影响。需要可追溯复习时仍应上传并完成解析 PDF；PDF 模式的原文依据会高亮与当前题目最相关的关键句。未来可通过独立的图书元数据 Provider 对接豆瓣等服务进行版本检索，但版本元数据不能替代正文依据。

OCR 配置为 `OCR_ENABLED` 和 `OCR_COMMAND`。当前 OCR 脚本使用 macOS Vision，适合本地开发；其他操作系统若没有对应命令，解析会失败并阻止无依据出题。

## 测试

```bash
make test
```

后端单独测试：

```bash
make test-api
```

## 远程部署

项目已提供统一的生产服务脚本和远程部署脚本。部署到当前服务器：

```bash
scripts/deploy.sh
```

远端服务统一通过以下命令管理：

```bash
cd /home/mengalong/website/read-books
scripts/server.sh start
scripts/server.sh stop
scripts/server.sh restart
scripts/server.sh status
scripts/server.sh logs
```

完整端口、Nginx、生产配置和 HTTPS 注意事项见 [远程部署文档](docs/deployment.md)。

## 文档

- [需求设计](docs/reading-review-system-requirements.md)
- [技术选型](docs/technical-selection.md)
- [开发状态](docs/development-status.md)
- [多用户模式改造计划](docs/multi-user-mode-plan.md)
- [远程部署](docs/deployment.md)
