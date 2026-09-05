# 读书复习测试系统技术选型 v0.7

## 1. 选型结论

第一版采用前端 TypeScript + 后端 Python、桌面网页优先、本地单用户部署的方案：

- 前端：Next.js App Router + React + TypeScript
- UI：Tailwind CSS + lucide-react
- 后端：FastAPI + Python 3.12+
- 文件上传：FastAPI `UploadFile` + `python-multipart`，流式写入本地磁盘
- 数据库：SQLite + SQLAlchemy 2.0 + Alembic
- PDF 解析：PyMuPDF，按页抽取文本并保留页码；对乱码、扫描版或受复制权限限制的 PDF，使用 macOS Vision OCR 兜底
- 可信资料解析：标准库解析 TXT、SRT、VTT、ASS、CSV，openpyxl 以只读模式解析 XLSX 台词表
- 出题与评分：使用统一 Provider 接口，同时支持 Mock LLM Provider 和 OpenAI 兼容 HTTP Provider
- 检索：MVP 使用关键词/覆盖权重检索，后续替换为向量检索
- Python 虚拟环境：Conda 环境 `read-books`，Python 3.12+
- 配置：`.env` + Pydantic Settings
- 时间：后端统一保存 UTC；前端展示固定使用 `Asia/Shanghai`，并统一格式化为 `YYYY-MM-DD HH:MM:SS`，避免运行环境时区影响用户看到的任务时间
- 测试：pytest + Playwright
- 包管理：前端用 npm/pnpm；后端在 conda 环境内使用 uv 或 pip 安装依赖

这个方案的核心取舍是：前端保持开发效率，后端单独承担大 PDF 上传、解析任务、资源真实内容检查和未来模型调用，避免把大文件能力绑死在前端框架的请求处理模型上。

## 2. 架构形态

采用一个仓库，两个应用，少量共享契约和配置：

```text
read-books/
  apps/
    web/                 # Next.js 前端
    api/                 # FastAPI 后端
  data/
    uploads/             # PDF、字幕、剧本和台词表原始文件
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

- 适合构建多页面应用：书架、资源详情、测试页、结果页、历史页。
- 路由和页面结构清晰，便于后续扩展。
- 可以使用 React Server Components 和客户端组件组合，但第一版保持简单。
- 自托管能力成熟，适合本地单用户部署。

第一版页面建议：

- `/`：书架
- `/books/new`：新增书籍
- `/books/[bookId]`：资源详情、PDF/可信资料上传与解析状态
- `/books/[bookId]/quotes`：台词筛选、角色与上下文修正、确认和排除
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
- `UploadFile` 支持流式文件上传，适合处理 PDF、字幕、剧本和结构化台词表。
- 持久化任务表配合后台线程，可以让 PDF 解析和逐题出题在请求返回后继续执行，并在服务重启时恢复未完成任务。
- Python 生态在 PDF 解析、文本处理和后续 AI 调用上更顺手。

后端主要职责：

- 书籍、PDF、出题任务、试卷和复习任务的 API。
- PDF 与可信资料的上传、存储、解析状态管理。
- PDF 文本抽取和分块，以及字幕、剧本和台词表结构化解析。
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
- `Quiz` 和 `QuizGenerationTask` 保存 `source_mode`，明确区分 `pdf`（可追溯 PDF 原文）、`material`（用户上传并确认的可信台词资料）、`plot`（用户上传并确认的剧情事件）、`combined`（可用 PDF、剧情事件和可信台词的综合来源）与 `model_knowledge`（无逐句原文依据）。即使没有 PDF，只要剧情事件和可信台词同时可用，也必须使用 `combined`。
- `ResourceMaterial`、`MaterialSegment` 和 `QuoteEntry` 分别保存上传文件、可定位内容片段和校对后的台词；`generation_theme/theme_config` 保存专题、资料、角色和考察角度，题目保存实际引用的台词与片段 ID。
- `Question` 额外保存 `fact_key`、`fact_claim` 和 `semantic_signature`。生成任务逐题把已生成事实摘要传给模型，后端使用本地归一化和字段/字符 n-gram 相似度拦截同一事实的不同问法；旧题没有事实字段时回退到题干、知识点、选项答案和来源 ID 的兼容规则。
- `Book` 保存 `resource_type`、`model_knowledge_supported` 和 `model_knowledge_checked_at`，用于区分书籍、电影和电视剧，并记录模型真实内容检查结果。

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
  verifyResourceContent(input: VerifyResourceContentInput): Promise<ResourceContentCheckResult>;
  generateQuiz(input: GenerateQuizInput): Promise<GeneratedQuiz>;
  gradeAnswer(input: GradeAnswerInput): Promise<GradedAnswer>;
}
```

第一版实现两个 Provider：

- `MockQuizAiProvider`：默认启用，用固定规则和样例数据生成题目/评分。
- `HttpQuizAiProvider`：调用 OpenAI 兼容的 `/chat/completions`，负责真实模型出题和问答题语义评分。
- 资源真实内容检查也走同一层 Provider，返回是否支持模型知识出题、检查时间和提示信息。

业务代码只依赖 `QuizAiProvider`，不直接依赖具体模型。

真实出题分为三种来源模式。PDF 模式下，后端先选择候选 `ContentChunk`，向模型提供片段 ID、页码和原文内容；模型返回后必须通过题量、题型、选项、正确答案、参考答案、评分要点和来源片段 ID 校验，PDF 文件名、页码与原文摘录由后端根据数据库记录重建。可信资料模式下，后端只检索已确认并启用的 `QuoteEntry`，模型必须返回实际使用的台词 ID；台词题允许逐字引用或自然转述，后端检查来源 ID、说话人、专题范围和精确出处禁问，并从资料记录重建文件、季集、时间或页码。模型知识模式下不发送资料片段，只发送资源名称、主创信息、资源类型和来源模式约束，所有来源 ID 必须为空。三种模式都不采信模型生成的文件名、位置或摘录。客观题继续由后端确定性评分，只有问答题提交时调用模型。

真实模型长响应的默认请求超时为 180 秒。整套试卷不再使用一次长请求，而是按题型逐题调用模型；每次调用只要求一道题，候选片段数量控制为 `max(本次题目数 + 2, 4)`，实际出题和问答评分请求不主动设置 `max_tokens`。Provider 同时兼容字符串和文本片段数组形式的 `message.content`；每题完成后提交任务进度，全部成功后再保存完整试卷；请求读取超时、模型服务自身输出达到上限或只返回推理内容时会记录失败阶段和具体错误，不会保存半成品试卷。

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

提示词模板保存在 SQLite 的 `prompt_templates` 表中，出题和问答评分分别维护版本。模板只能使用后端提供的白名单变量，例如 `{{book_title}}`、`{{author}}`、`{{resource_type_label}}`、`{{resource_type_scope}}`、`{{source_mode}}`、`{{source_material}}`、`{{generation_theme}}`、`{{theme_requirements}}`、`{{difficulty}}`、`{{user_answer}}` 和 `{{grading_rubric}}`。版本切换只影响模型表达和任务约束，后端仍强制校验题目结构、分数范围和来源模式；旧版模板继续兼容，可信资料模式会额外追加不能伪造台词和来源的系统边界。

### 8.4 模型 Token 用量记录

真实 Provider 每次发起模型请求都会写入 `model_usage_records`，记录任务 ID、任务类型、阶段、题目位置、调用序号、模型名称、耗时、成功状态、输入消息、模型原始回复和接口返回的 `prompt_tokens`/`completion_tokens`（兼容 `input_tokens`/`output_tokens`）等调试信息。提示词中用于历史去重的内容是按相关性筛选的紧凑事实摘要（最多 10 条并受字符预算约束），服务端仍保留全量历史题目做最终硬判重。记录不保存 API Key；调试页支持按题复制全部调用信息，便于问题定位。

出题任务支持实时人工控制：`POST /api/quiz-generation-tasks/{task_id}/cancel` 将 pending/processing/awaiting_intervention 任务标记为 cancelled，后台线程在模型调用返回前后检查该状态，不再写入后续题目或创建试卷；`DELETE /api/quiz-generation-tasks/{task_id}` 删除已终止或失败的任务及其 `model_usage_records`。进行中的任务必须先终止再删除，待人工处理的未完成任务同样显示“终止出题”而不是直接删除。任务页面可复制整套当前任务或单题的 Prompt、模型回复、草稿和 Token；任何已生成题目在任务完成前都可人工调整，结构/来源校验失败时会从最近一次模型原始回复回填可编辑草稿。

已完成试卷提供 `GET /api/quizzes/{quiz_id}/export` 导出接口，返回 `read-books-quiz-validation-v1` 结构，包含完整试卷答案、解析、评分要点和来源依据，并附带给其他模型的校验用途说明。资源详情页的“选择这套”直接进入只读预览页；预览页的“管理题库题目”通过 `return_to=preview` 进入编辑页，编辑页返回时恢复预览上下文，不创建复习记录。“导出题目与答案”将同一结构下载为 JSON 文件。

试卷预览页和概览页都提供模型合理性审查。`POST /api/quizzes/{quiz_id}/quality-review` 创建整套后台审查任务，`GET /api/quizzes/{quiz_id}/quality-review` 查询状态和结果；编辑页通过 `POST /api/quizzes/{quiz_id}/questions/{question_id}/quality-review` 只复审指定题目。状态为 `not_started / pending / processing / completed / failed`。审查请求只发送紧凑的题目字段和有限的来源摘录，结果保存于试卷的 `quality_review_*` 字段，格式为 `quiz_quality_review.v2`，包含整套 `score`、逐题 `question_reviews`（分数、结论、优点、问题）和详细修改稿（建议题干、完整选项、答案、解析、知识点及问答评分要点），并记录本次 `reviewed_question_positions`。选择题审查区分正确选项与干扰项：只有 `correct_answers` 标记的选项要求来源支持，未标记选项可以故意错误；干扰项只检查是否造成多解、误导或完全失去迷惑性。模型只给建议，不直接写入题目；用户确认建议后仍通过原有试卷编辑接口修改。真实 Provider 的调用计入 `model_usage_records`，服务重启会恢复未完成的整套或单题审查任务。模拟 Provider 提供结构检查兜底，便于本地联调。

剧情梗概资料使用 `plot_summary.v1` JSON。资源主页生成的提示词要求模型输出 `source_registry`、分季/分集概览、人物/关系/主线索引、经典金句候选和按集覆盖的原子化 `events`；提示词明确区分“理解上下文”和“可出题事件”，要求事件分别记录因果、行动、结果和后续影响，不能把精确出处位置作为考点。上传接口以 `plot_summary` 资料类型接收 JSON，解析后写入 `plot_events`，同时保存其他结构化内容作为受限的剧情背景，事件经过可信度和 `question_usable` 检查，确认启用后才能进入剧情题来源池；旧资料在生成时也会按需从原 JSON 文件读取这些背景字段。上传弹窗在选择该类型时支持一次选择多个 JSON 文件，前端按顺序分别创建资料记录并显示进度。管理接口为 `GET/PATCH /api/books/{book_id}/plot-events`，支持按资料、集数、状态和关键词筛选及逐条编辑确认。剧情事件与 QuoteEntry、PDF 片段保持独立来源 ID，后续综合出题按来源方向分别召回。资源详情页的后台出题卡片始终提供“查看出题进度”入口，离开进度页后可从资源主页重新进入任务详情。

综合内容任务在 `run_generation_task` 中为每道题生成来源方向计划：默认 70% `content`、20% `dialogue`、10% `integrated`。`HttpQuizAiProvider` 和 Mock Provider 按方向过滤候选：`content` 只使用 PDF/剧情事件，`dialogue` 只使用可信台词，`integrated` 强制同时提供两类来源。模型返回后 `_validate_questions` 校验对应 ID 是否齐全，题目仍禁止把集数、时间码或资料位置作为考点。

一次手动出题或后台预出题是一个任务，各道题的首次生成和结构修正重试分别按调用序号记录；一次提交中的多个问答题评分共享提交任务 ID，并按调用序号展开。连接测试也作为独立任务记录，便于排查模型连通性。接口没有返回 usage 时对应 Token 为空，统计页面显示“未报告”，不将未知值假定为零。

预生成采用分层配置边界：书籍实体维护是否开启、当前状态、失败信息和结果题目 ID；平台或未来租户设置维护默认题量、题型、目标时长、并发和资源预算；书籍级参数可以覆盖租户默认值。未来增加 `tenant_id` 后，任务和用量记录沿用租户维度查询，避免把书籍运行状态塞进全局模型配置表。

### 8.5 管理员访问统计

访问统计只对平台管理员开放，当前统计对象是用户访问会话，而不是页面浏览量。访问定义和聚合规则如下：

- 登录成功创建一条访问会话；同一会话连续活动期间只计一次访问，连续 30 分钟无活动后再次活动计为新访问。
- 页面处于可见状态时，前端最多每 60 秒发送一次心跳；心跳只延长当前会话，不新增访问次数。主动退出或会话撤销会关闭会话，异常退出按最后活动时间后 2 分钟估算结束。
- 数据库存储 UTC 时间；聚合边界和页面展示使用 `Asia/Shanghai`（北京时间）。跨午夜的访问次数归开始日期，访问时长按实际涉及的日期拆分。
- 页面 `/settings/access-statistics` 提供按天、按月、按年三个连续时间段汇总表；默认从首条真实访问记录所在的天、月或年开始，数据积累后分别保留最近 30 天、12 个月和 5 年的滚动范围，避免展示采集功能启用前的大量零值时间段；支持日期范围和用户筛选。
- 汇总表展示访问次数、登录次数、活跃用户数、总访问时长和平均访问时长，并提供用户维度汇总及首次/最近访问时间。

后端接口为 `GET /api/settings/access-statistics?granularity=day|month|year`，可附带 `start_date`、`end_date` 和 `user_id`；前端心跳接口为 `POST /api/auth/activity`。访问会话保留用户、工作空间、登录会话、进入类型、开始时间、最后活动时间、结束时间和结束原因，后续迁移 PostgreSQL 时沿用同一统计契约。

### 8.6 考试答卷分析与风控元数据

考试答卷的薄弱知识点不通过额外模型调用生成。后端以试卷快照中的 `knowledge_point` 为分组键，汇总逐题实际得分和满分，低于 60% 的分组按得分率升序输出；问答题缺失要点和客观题漏选项转换为可阅读的重点补充内容，再按题型生成确定性学习建议。这样历史答卷无需回填即可获得相同分析，且结果可复现、可测试、没有额外 Token 成本。

`ExamAttempt` 保存 `device_type`、`user_agent`、`started_ip_address` 和 `submitted_ip_address`。终端类型由 User-Agent 在服务端归类，IP 优先读取 Nginx 传递的首个 `X-Forwarded-For`，字段长度受限；仅授权管理响应返回这些字段，公开参与响应固定隐藏。开始和提交 IP 不同只生成辅助风险标记，不参与身份唯一性、自动封禁或作弊判定。

考试有效期沿用 `ExamShare.expires_at` UTC 字段。创建和更新接口拒绝早于当前时间的截止时间，读取时通过 `effective_share_status` 动态计算 `expired`，不批量改写活动状态。过期活动拒绝新建答卷，并拒绝加载或提交仍为 `in_progress` 的答卷；已提交、评分中、评分失败和已完成答卷不受有效期限制，保证历史结果可追溯。

答题报告使用前端共享的 `ExamAttemptReport` 组件生成固定宽度、完整展开的报告 DOM，再通过 `html2canvas` 转为 PNG 下载。报告只在用户触发导出时临时挂载，下载完成立即卸载，不在服务器保存派生图片。渲染时根据内容高度和总像素数动态降低缩放比例，避免长答卷超过浏览器 Canvas 尺寸限制。管理端报告使用授权答卷响应并可展示终端/IP；公开结果报告使用已脱敏响应，不能通过前端参数补回风控或 PDF 来源字段。

### 8.7 微信公开考试身份

微信参与者使用微信开放平台网站应用的 QR OAuth（`snsapi_login`），不复用平台 `User`，避免给外部考试参与者意外授予书架和后台权限。`WechatUser` 保存 `openid`、可选 `unionid`、昵称和头像；`WechatSession` 只保存随机会话令牌哈希；`WechatOAuthState` 保存一次性状态哈希、浏览器 nonce 哈希、考试代码和短有效期。公开接口的身份优先级为平台会话、微信会话、匿名答卷凭据。

AppID、AppSecret、站点地址、启用开关和强制认证策略保存在平台级 `wechat_login_configurations`；网页读取只返回 `app_secret_configured`。OAuth 状态消费时同时校验有效期、未消费状态和浏览器 nonce，回调成功后使用 `HttpOnly` Cookie 建立微信会话。同一微信用户与同一考试活动由数据库唯一约束保证只有一份答卷。微信登录证明账号控制权而非实名，昵称重复不影响身份判定。

正式启用依赖审核通过的微信开放平台网站应用、正确授权回调域和 HTTPS。当前生产仍为 HTTP，后端在 `APP_ENV=production` 时拒绝保存 HTTP 回调地址，防止误启用不安全配置。

后台还提供独立的微信登录自检页 `/settings/wechat/test`，它会按配置读取、诊断登录、回调落库、当前会话查询和退出会话的顺序调用同一套 OAuth 起始与回调链路，但不依赖考试链接，也不依赖正式开关；自检页会展示每一步对应的请求 URL、预期返回和可复制的 `curl` 命令，并通过 `GET /api/public/wechat/me` 读取当前浏览器里的微信会话，便于单独验证扫码、回调、Cookie 写入和身份读取是否正常。

### 8.8 Mock 数据原则

Mock 不是随便造页面假数据，而是要模拟真实链路的数据结构：

- PDF 模式题目必须有关联 `sourceChunkIds` 和 `sourceEvidence`；模型知识模式两者必须为空，并记录 `sourceMode`。
- 问答题必须有 `referenceAnswer` 和 `gradingRubric`。
- 评分结果必须有 `matchedPoints` 和 `missingPoints`。
- 试卷总分固定为 100；出题完成后由后端按单选、多选、问答 `6:10:20` 的相对权重和实际题量统一分配单题满分，并同步归一化问答题评分要点。分值分配不依赖模型输出。

因此切换 Mock/真实 Provider 时，页面、题目和数据库结构不需要变化；来源模式则单独记录并在前端展示。

### 8.9 图书元数据 Provider 预留

未来对接豆瓣或其他图书服务时，增加独立的 `BookMetadataProvider`，输入书名、作者等检索条件，输出候选版本、ISBN、出版社、出版时间和封面等元数据。版本检索与 `QuizAiProvider` 保持解耦：元数据 Provider 不提供正文、不生成题目，也不能把简介或模型知识冒充为 PDF 原文。后续多租户部署时，第三方接口凭据应进入租户或平台配置，不写入书籍记录。

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
- 考试答卷按知识点聚合得分、生成缺失要点和推荐深入方向，并隔离公开响应中的终端/IP 风控字段。
- 任意题型和题量组合的单题分值之和严格等于 100，问答题评分要点之和严格等于对应单题满分。
- 配置读取与 mock/real provider 切换。
- 异步出题任务创建、逐题生成、进度完成和失败恢复。
- 同一试卷创建多次复习任务。
- 复习任务保存实际得分和实际满分；结果页同时展示两者及换算后的得分率，跨试卷汇总和列表比较统一使用得分率，避免不同试卷满分不同时直接比较原始分数。
- 历史任务重答复用原任务 ID，删除任务不删除试卷。
- 试卷摘要按题目类型统计单选、多选和问答数量；删除试卷时级联删除题目、复习任务和答案。
- 删除试卷时解除 `QuizGenerationTask.quiz_id` 与 `Book.pre_generation_quiz_id` 引用，并将 `QuestionBankUsage.quiz_id/question_id` 置空保留试卷名称快照；不删除题库条目和 `ModelUsageRecord` 审计数据。

题库使用独立的 `question_bank_entries` 快照表和 `question_bank_usages` 引用表。已完成试卷的预览页通过 `POST /api/quizzes/{quiz_id}/questions/{question_id}/question-bank` 逐题回流，并按剩余题目逐个调用同一接口实现带进度的“一键回流”；试卷列表不直接提供回流入口。资源题库页面通过 `GET/PATCH /api/books/{book_id}/question-bank` 查询和编辑。条目按 `book_id + fact_key` 去重，保存完整题干、选项、答案、解析、评分依据、事实签名和来源证据；每次进入新试卷都会写入使用关系并增加 `use_count`，按使用次数和最近使用时间优先选择低频条目。综合出题的题库候选仍按来源方向过滤，已多次被其他试卷使用的重复事实会让位给模型生成或其他候选，避免整套试卷大量重复。

### 10.2 端到端测试

使用 Playwright：

- 创建书籍。
- 上传 PDF 并看到解析状态。
- 生成测试。
- 在生成期间离开页面，并从资源详情查看任务进度。
- 从试卷列表选择同一套试卷创建多次复习任务。
- 查看试卷难度和题型构成，并删除历史试卷。
- 完成单选、多选、问答。
- 查看结果页、原文依据和全局复习记录。
- 验证考试列表和答题记录表格列对齐、固定操作列、答卷详情入口、已完成参与者得分柱状图、个人学习方向、管理端终端/IP 信息，以及管理端和参与者端 PNG 报告下载。

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
