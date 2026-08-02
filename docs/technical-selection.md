# 读书复习测试系统技术选型 v0.4

## 1. 选型结论

第一版采用前端 TypeScript + 后端 Python、桌面网页优先、本地单用户部署的方案：

- 前端：Next.js App Router + React + TypeScript
- UI：Tailwind CSS + lucide-react
- 后端：FastAPI + Python 3.12+
- 文件上传：FastAPI `UploadFile` + `python-multipart`，流式写入本地磁盘
- 数据库：SQLite + SQLAlchemy 2.0 + Alembic
- PDF 解析：PyMuPDF，按页抽取文本并保留页码
- 出题与评分：先使用 Mock LLM Provider，预留真实 LLM Provider
- 检索：MVP 使用关键词/覆盖权重检索，后续替换为向量检索
- Python 虚拟环境：Conda 环境 `read-books`，Python 3.12+
- 配置：`.env` + Pydantic Settings
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
- `/books/[bookId]/quiz/new`：生成测试
- `/quizzes/[quizId]`：答题页
- `/quizzes/[quizId]/result`：结果页
- `/books/[bookId]/history`：测试历史

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
- `BackgroundTasks` 可以把上传后解析、索引生成这类工作放到响应之后执行。
- Python 生态在 PDF 解析、文本处理和后续 AI 调用上更顺手。

后端主要职责：

- 书籍、PDF、题目、答题记录的 API。
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
- `GET /quizzes/:quizId`
- `POST /quizzes/:quizId/submit`
- `GET /quizzes/:quizId/result`
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

### 7.1 PyMuPDF

第一版使用 PyMuPDF 进行服务端 PDF 文本抽取：

- 按页处理，天然支持保存页码。
- 可以直接得到页面文本项，便于构建来源片段。
- 不处理扫描版 OCR，扫描 PDF 在第一版显示“暂不支持 OCR”。

PDF 处理流程：

1. 上传接口流式保存 PDF 文件。
2. 创建 `PdfDocument` 记录，状态为 `pending`。
3. 后端启动解析任务，状态改为 `processing`。
4. 使用 PyMuPDF 按页抽取文本。
5. 清洗文本并按页/段落/长度切分为 `ContentChunk`。
6. 更新页数、片段数和解析状态。
7. 解析失败时保存错误信息，并在前端展示。

### 7.2 大 PDF 策略

产品层面不限制 PDF 大小，但实现上需要避免阻塞：

- 上传使用流式写盘。
- 解析使用异步任务，不在上传请求中同步解析完整 PDF。
- 前端轮询解析状态。
- 解析失败必须显示可理解的失败原因。
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
- `HttpQuizAiProvider`：先保留接口和配置读取，后续接真实大模型。

业务代码只依赖 `QuizAiProvider`，不直接依赖具体模型。

### 8.2 配置项

配置文件和环境变量预留：

```env
MOCK_MODE=true
LLM_BASE_URL=
LLM_API_KEY=
LLM_MODEL=
LLM_TIMEOUT_MS=60000
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

### 8.3 Mock 数据原则

Mock 不是随便造页面假数据，而是要模拟真实链路的数据结构：

- 题目必须有关联 `sourceChunkIds`。
- 每道题必须有 `sourceEvidence`。
- 问答题必须有 `referenceAnswer` 和 `gradingRubric`。
- 评分结果必须有 `matchedPoints` 和 `missingPoints`。

这样后续切换真实模型时，页面和数据库结构不需要重做。

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

### 10.2 端到端测试

使用 Playwright：

- 创建书籍。
- 上传 PDF 并看到解析状态。
- 生成测试。
- 完成单选、多选、问答。
- 查看结果页和原文依据。

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

## 12. 暂不选择的方案

- 不用纯前端应用：PDF 解析、文件保存和未来模型调用都需要后端。
- 不用 serverless 作为第一目标：大文件上传、本地文件和 SQLite 不适合直接放在 serverless 里。
- 不用 PostgreSQL 起步：单用户阶段 SQLite 更简单。
- 不直接接真实 LLM 起步：先用 Mock 跑通产品闭环，降低早期开发和调试成本。
- 不做 OCR：扫描版 PDF 复杂度高，第一版先明确提示不支持。

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
