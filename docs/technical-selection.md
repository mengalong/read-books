# 读书复习测试系统技术选型 v0.6

## 1. 选型结论

第一版采用前端 TypeScript + 后端 Python、桌面网页优先、本地单用户部署的方案：

- 前端：Next.js App Router + React + TypeScript
- UI：Tailwind CSS + lucide-react
- 后端：FastAPI + Python 3.12+
- 文件上传：FastAPI `UploadFile` + `python-multipart`，流式写入本地磁盘
- 数据库：SQLite + SQLAlchemy 2.0 + Alembic
- PDF 解析：PyMuPDF，按页抽取文本并保留页码；对乱码、扫描版或受复制权限限制的 PDF，使用 macOS Vision OCR 兜底
- 出题与评分：使用统一 Provider 接口，同时支持 Mock LLM Provider 和 OpenAI 兼容 HTTP Provider
- 检索：MVP 使用关键词/覆盖权重检索，后续替换为向量检索
- Python 虚拟环境：Conda 环境 `read-books`，Python 3.12+
- 配置：`.env` + Pydantic Settings
- 时间：后端统一保存 UTC；前端展示固定使用 `Asia/Shanghai`，避免运行环境时区影响用户看到的任务时间
- 测试：pytest + Playwright
- 包管理：前端用 npm/pnpm；后端在 conda 环境内使用 uv 或 pip 安装依赖

这个方案的核心取舍是：前端保持开发效率，后端单独承担大 PDF 上传、解析任务和未来模型调用，避免把大文件能力绑死在前端框架的请求处理模型上。

## 2. 架构形态

采用一个仓库，两个应用，少量共享契约和配置：

```text
read-books/
  apps/
    web/                 # Next.js 前端
    api/                 # FastAPI 后端
  data/
    uploads/             # PDF 原始文件
    parsed/              # 可选：解析中间产物
    app.db               # SQLite 数据库
  docs/
```

开发时通过根目录任务脚本同时启动前后端：

```bash
dev
```

生产或本地长期使用时仍然以自托管服务为主，不以 serverless 部署为第一目标。

## 3. 本地 Python 环境

后端开发使用 conda 虚拟环境：

```bash
conda activate read-books
```

当前环境：

- 环境名：`read-books`
- Python：`3.12`
- 复现文件：`environment.yml`

后续创建项目依赖后，可以在该环境内使用 uv 或 pip 安装 FastAPI、SQLAlchemy、PyMuPDF、pytest 等依赖。

## 4. 前端选型

### 4.1 Next.js App Router

选择 Next.js App Router 的原因：

- 适合构建多页面应用：书架、书籍详情、测试页、结果页、历史页。
- 路由和页面结构清晰，便于后续扩展。
- 可以使用 React Server Components 和客户端组件组合，但第一版保持简单。
- 自托管能力成熟，适合本地单用户部署。

第一版页面建议：

- `/`：书架
- `/books/new`：新增书籍
- `/books/[bookId]`：书籍详情、PDF 上传与解析状态
- `/books/[bookId]/quiz/new`：创建并查看异步出题任务
- `/quizzes/[quizId]`：试卷概览与开始复习
- `/reviews/[reviewId]`：一次复习任务的答题页
- `/reviews/[reviewId]/result`：一次复习任务的结果页
- `/reviews`：全局复习记录
- `/books/[bookId]/history`：单本书复习记录

### 4.2 Tailwind CSS + lucide-react

选择 Tailwind CSS 的原因：

- 快速构建桌面网页 UI。
- 适合做偏工具型、信息密度适中的页面。
- 无运行时样式负担。

选择 lucide-react 的原因：

- 图标覆盖常见按钮和状态。
- 和 React/Tailwind 组合成本低。

第一版不引入重型组件库。需要表单、弹窗、折叠面板等控件时，先实现少量本地组件；如果后续复杂度上升，再考虑 Radix UI 或 shadcn/ui。

## 5. 后端选型

### 5.1 FastAPI + Python

选择 FastAPI + Python 的原因：

- 路由、依赖注入、请求校验和 OpenAPI 生成都很适合做这种工具型产品。
- `UploadFile` 支持文件上传，适合处理 PDF。
- 持久化任务表配合后台线程，可以让 PDF 解析和逐题出题在请求返回后继续执行，并在服务重启时恢复未完成任务。
- Python 生态在 PDF 解析、文本处理和后续 AI 调用上更顺手。

后端主要职责：

- 书籍、PDF、出题任务、试卷和复习任务的 API。
- PDF 上传、存储、解析状态管理。
- PDF 文本抽取和分块。
- 测试生成、提交评分、结果汇总。
- Mock LLM 与未来真实 LLM 的统一适配层。

### 5.2 REST API

第一版使用 REST API，不引入 GraphQL/tRPC。原因是接口边界清晰，FastAPI 会自动生成 OpenAPI，后续替换前端、移动端或真实 AI 服务时更直接。

核心接口草案：

- `GET /books`
- `POST /books`
- `GET /books/:bookId`
- `PATCH /books/:bookId`
- `POST /books/:bookId/pdfs`
- `GET /books/:bookId/pdfs`
- `GET /books/:bookId/chunks`
- `POST /books/:bookId/quizzes`
- `GET /quiz-generation-tasks/:taskId`
- `GET /books/:bookId/quizzes`
- `GET /quizzes/:quizId`
- `POST /quizzes/:quizId/reviews`
- `GET /reviews`
- `GET /reviews/:reviewId`
- `POST /reviews/:reviewId/submit`
- `GET /reviews/:reviewId/result`
- `POST /reviews/:reviewId/reopen`
- `DELETE /reviews/:reviewId`
- `GET /books/:bookId/history`

前端可以直接消费 FastAPI 的 OpenAPI 文档，必要时再生成 TypeScript 客户端或类型定义。

## 6. 数据库选型

### 6.1 SQLite

第一版选择 SQLite：

- 单用户场景足够。
- 本地部署简单，不需要额外数据库服务。
- 数据文件便于备份。
- 后续可迁移到 PostgreSQL。

数据库文件建议放在：

```text
data/app.db
```

### 6.2 SQLAlchemy 2.0 + Alembic

选择 SQLAlchemy 2.0 + Alembic 的原因：

- SQLAlchemy 2.0 是当前 Python ORM 的主流方案之一。
- Alembic 是 SQLAlchemy 官方生态里的迁移工具。
- 支持 SQLite，也给未来 PostgreSQL 迁移留下空间。
- 模型、迁移和复杂查询都比较稳。

注意点：

- JSON 字段用于保存题目选项、评分要点、原文依据等结构化数据。
- PDF 原文片段需要独立表存储，不能只存在题目 JSON 中，否则后续检索和去重会困难。
- 大文本字段只保存必要原文片段；PDF 原文件保存在文件系统。

## 7. PDF 处理选型

### 7.1 PyMuPDF 与文本质量检测

第一版使用 PyMuPDF 进行服务端 PDF 文本抽取：

- 按页处理，天然支持保存页码。
- 可以直接得到页面文本项，便于构建来源片段。
- 先使用 PyMuPDF 读取原生文字，并按页检查中文/拉丁文字可读比例。
- 对《红楼梦》这类页面可视文字正常、但字体没有 ToUnicode 映射的 PDF，原生结果会是乱码；系统不会把乱码直接送入出题流程。
- 当原生文字质量不足时，开发环境默认调用 `scripts/pdf_ocr.swift` 使用 macOS Vision 按页识别中文。
- OCR 结果仍不足时，解析状态为失败，前端不允许生成题目。

PDF 处理流程：

1. 上传接口流式保存 PDF 文件。
2. 创建 `PdfDocument` 记录，状态为 `pending`。
3. 后端启动解析任务，状态改为 `processing`。
4. 使用 PyMuPDF 按页抽取文本并检查可读性。
5. 如果原生文字质量不足，转入本地 OCR，并继续保留 PDF 页码。
6. 清洗文本并按页/段落/长度切分为 `ContentChunk`。
7. 更新页数、片段数和解析状态。
8. 解析失败时保存错误信息，并在前端展示。

### 7.2 大 PDF 策略

产品层面不限制 PDF 大小，但实现上需要避免阻塞：

- 上传使用流式写盘。
- 解析使用异步任务，不在上传请求中同步解析完整 PDF。
- 前端轮询解析状态。
- 解析失败必须显示可理解的失败原因。
- 文本解析和 OCR 解析均需经过最低质量检查，不能把乱码当作有效原文。
- 后续如遇超大 PDF 性能问题，再加入任务队列、断点解析或后台 worker。

## 8. AI 与 Mock 策略

### 8.1 Provider 接口

出题和评分统一通过 Provider 接口调用：

```ts
interface QuizAiProvider {
  generateQuiz(input: GenerateQuizInput): Promise<GeneratedQuiz>;
  gradeAnswer(input: GradeAnswerInput): Promise<GradedAnswer>;
}
```

第一版实现两个 Provider：

- `MockQuizAiProvider`：默认启用，用固定规则和样例数据生成题目/评分。
- `HttpQuizAiProvider`：调用 OpenAI 兼容的 `/chat/completions`，负责真实模型出题和问答题语义评分。

业务代码只依赖 `QuizAiProvider`，不直接依赖具体模型。

真实出题时，后端先选择本次候选 `ContentChunk`，只向模型提供片段 ID、页码和原文内容。模型返回后必须通过题量、题型、选项、正确答案、参考答案、评分要点和来源片段 ID 校验；PDF 文件名、页码与原文摘录由后端根据数据库记录重新构造，不采信模型生成的来源信息。客观题继续由后端确定性评分，只有问答题提交时调用模型。

真实模型长响应的默认请求超时为 180 秒。整套试卷不再使用一次长请求，而是按题型逐题调用模型；每次调用只要求一道题，候选片段数量控制为 `max(本次题目数 + 2, 4)`，单题默认输出预算为 4000 Token。Provider 同时兼容字符串和文本片段数组形式的 `message.content`；每题完成后提交任务进度，全部成功后再保存完整试卷；请求读取超时、输出达到上限或只返回推理内容时会记录失败阶段和具体错误，不会保存半成品试卷。

### 8.2 配置项

网页端模型设置页面对应后端接口：

- `GET /api/settings/model`：读取当前生效配置，但只返回 `api_key_configured`，不返回 API Key 明文。
- `PUT /api/settings/model`：保存连接参数和是否使用已配置模型的开关；未修改的固定长度掩码不作为密钥提交，输入新 API Key 后覆盖后台原值。
- `POST /api/settings/model/test`：使用当前表单参数调用 OpenAI 兼容的 `/chat/completions`，校验 HTTP 状态和响应结构，并返回耗时、测试时间和 `choices[0].message.content` 文本；成功/失败结果持久化到 `model_configurations`，前端另外展示脱敏后的等价 `curl` 命令。
- `GET /api/settings/prompts`：读取出题和问答评分当前启用的提示词模板及可用变量。
- `PUT /api/settings/prompts/{prompt_type}`：校验变量后保存新版本并启用。
- `POST /api/settings/prompts/{prompt_type}/preview`：使用示例数据渲染模板，供保存前检查。
- `POST /api/settings/prompts/{prompt_type}/reset`：以系统默认模板保存一个新版本。
- `GET /api/settings/token-usage`：按任务类型读取模型调用汇总，并展开每个任务的出题、格式修正、问答评分或连接测试阶段。

已保存的单用户配置存放在 SQLite 的 `model_configurations` 表中，并优先于环境变量。尚未保存网页配置时，后端回退到 `.env` 的默认值。读取接口不返回 API Key 明文，前端只根据 `api_key_configured` 显示固定 16 位掩码。页面开关启用已配置模型后，新生成的测试和问答题评分会使用该配置；关闭后立即回到 Mock Provider。

配置文件和环境变量预留：

```env
MOCK_MODE=true
LLM_BASE_URL=
LLM_API_KEY=
LLM_MODEL=
LLM_TIMEOUT_MS=180000
LLM_TEMPERATURE=0.2
```

建议配置模块输出统一对象：

```ts
export type AppConfig = {
  mockMode: boolean;
  llm: {
    baseUrl?: string;
    apiKey?: string;
    model?: string;
    timeoutMs: number;
    temperature: number;
  };
  storage: {
    uploadDir: string;
    databaseUrl: string;
  };
};
```

### 8.3 提示词模板原则

提示词模板保存在 SQLite 的 `prompt_templates` 表中，出题和问答评分分别维护版本。模板只能使用后端提供的白名单变量，例如 `{{source_material}}`、`{{difficulty}}`、`{{user_answer}}` 和 `{{grading_rubric}}`。版本切换只影响模型表达和任务约束，后端仍强制校验题目结构、分数范围和原文来源。

### 8.4 模型 Token 用量记录

真实 Provider 每次发起模型请求都会写入 `model_usage_records`，记录任务 ID、任务类型、阶段、调用序号、模型名称、耗时、成功状态和接口返回的 `prompt_tokens`/`completion_tokens`（兼容 `input_tokens`/`output_tokens`）等元数据。记录不保存提示词、PDF 原文、用户答案或 API Key。

一次手动出题或后台预出题是一个任务，各道题的首次生成和结构修正重试分别按调用序号记录；一次提交中的多个问答题评分共享提交任务 ID，并按调用序号展开。连接测试也作为独立任务记录，便于排查模型连通性。接口没有返回 usage 时对应 Token 为空，统计页面显示“未报告”，不将未知值假定为零。

预生成采用分层配置边界：书籍实体维护是否开启、当前状态、失败信息和结果题目 ID；平台或未来租户设置维护默认题量、题型、目标时长、并发和资源预算；书籍级参数可以覆盖租户默认值。未来增加 `tenant_id` 后，任务和用量记录沿用租户维度查询，避免把书籍运行状态塞进全局模型配置表。

### 8.5 Mock 数据原则

Mock 不是随便造页面假数据，而是要模拟真实链路的数据结构：

- 题目必须有关联 `sourceChunkIds`。
- 每道题必须有 `sourceEvidence`。
- 问答题必须有 `referenceAnswer` 和 `gradingRubric`。
- 评分结果必须有 `matchedPoints` 和 `missingPoints`。

因此切换模型模式时，页面、题目和数据库结构不需要变化。

## 9. 检索与出题策略

第一版不急着上向量数据库，先使用可解释的本地策略：

- 按书籍选择候选 `ContentChunk`。
- 根据历史测试记录降低近期片段权重。
- 根据错题和低分知识点提高权重。
- 使用关键词、标题、页码范围和片段长度做基础筛选。
- 生成题目时强制携带来源片段。

后续升级路径：

- SQLite FTS：提高文本搜索体验。
- Embedding + 向量检索：提高语义召回。
- PostgreSQL + pgvector：当多用户或数据规模变大时迁移。

## 10. 测试与质量

### 10.1 单元测试

使用 pytest：

- 分块逻辑。
- 题目去重逻辑。
- 客观题评分。
- 问答题评分结果归一化。
- 配置读取与 mock/real provider 切换。
- 异步出题任务创建、逐题生成、进度完成和失败恢复。
- 同一试卷创建多次复习任务。
- 历史任务重答复用原任务 ID，删除任务不删除试卷。
- 试卷摘要按题目类型统计单选、多选和问答数量；删除试卷时级联删除题目、复习任务和答案。
- 删除试卷时解除 `QuizGenerationTask.quiz_id` 与 `Book.pre_generation_quiz_id` 引用，但不删除 `ModelUsageRecord` 审计数据。

### 10.2 端到端测试

使用 Playwright：

- 创建书籍。
- 上传 PDF 并看到解析状态。
- 生成测试。
- 在生成期间离开页面，并从书籍详情查看任务进度。
- 从试卷列表选择同一套试卷创建多次复习任务。
- 查看试卷难度和题型构成，并删除历史试卷。
- 完成单选、多选、问答。
- 查看结果页、原文依据和全局复习记录。

## 11. 部署与运行

第一版面向本地或个人服务器自托管：

- Web：Next.js Node server
- API：FastAPI + Uvicorn
- DB：本地 SQLite 文件
- 文件：本地 `data/uploads`

后续如果要公开访问，至少需要补充：

- 访问保护，例如登录或反向代理 basic auth。
- HTTPS。
- 备份策略。
- 文件存储迁移到对象存储。
- SQLite 迁移到 PostgreSQL。
- 将进程内后台线程替换为支持租户隔离、并发上限、重试和超时控制的任务队列与独立 Worker。

## 12. 暂不选择的方案

- 不用纯前端应用：PDF 解析、文件保存和未来模型调用都需要后端。
- 不用 serverless 作为第一目标：大文件上传、本地文件和 SQLite 不适合直接放在 serverless 里。
- 不用 PostgreSQL 起步：单用户阶段 SQLite 更简单。
- 不直接接真实 LLM 起步：先用 Mock 跑通产品闭环，降低早期开发和调试成本。
- 不提供 OCR 编辑校对工作台：PDF 原生文字质量不足时，仅自动调用本地 Vision OCR 兜底。

## 13. 参考资料

- Next.js App Router：https://nextjs.org/docs/app
- Next.js self-hosting：https://nextjs.org/docs/app/guides/self-hosting
- Tailwind CSS installation：https://tailwindcss.com/docs/installation
- FastAPI request files：https://fastapi.tiangolo.com/tutorial/request-files/
- FastAPI background tasks：https://fastapi.tiangolo.com/tutorial/background-tasks/
- FastAPI upload file reference：https://fastapi.tiangolo.com/reference/uploadfile/
- SQLAlchemy 2.0 docs：https://docs.sqlalchemy.org/en/20/
- Alembic docs：https://alembic.sqlalchemy.org/en/latest/
- PyMuPDF docs：https://pymupdf.readthedocs.io/en/latest/
- uv docs：https://docs.astral.sh/uv/
