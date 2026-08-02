# 回卷

一个面向个人使用的读书复习网站。上传读过的 PDF 后，系统按原文生成单选题、多选题和问答题，并在提交后给出自动评分、参考答案和可定位到 PDF 页码的原文依据。

当前版本使用 Mock AI Provider，出题和评分链路已经完整保留未来真实大模型需要的数据结构，但不会调用外部模型。

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

当前版本尚未实现具体模型协议，切换到 OpenAI 兼容模式后只会保存参数，出题和评分仍会返回明确的“真实模型 Provider 尚未启用”提示。后续接入协议适配时无需调整书籍、题目和评分的数据结构。

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
