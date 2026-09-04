# 资料理解层设计（轻量方案）

实施状态（2026-09-04）：数据结构、增量摘要生成、向量检索召回、Prompt 背景注入、规则版忠实性校验均已完成。

## 1. 背景与目标

出题时的“捏造事实”问题主要来自两类原因：

- 使用模型内化知识出题（`model_knowledge` 来源模式）时，模型可能记错细节或混淆版本。
- 使用用户上传的可信资料出题（`material`/`pdf` 来源模式）时，召回逐条台词或原文片段时缺乏对整本书/整部剧上下文的理解，容易断章取义或答案缺乏依据。

本设计只解决第二类问题：**在忠实原文的前提下，让系统对已上传资料有更完整的理解，出题时既能精确引用原文，又能利用整体上下文避免断章取义**。

核心原则不变：摘要、向量检索都只是"理解与召回"的辅助手段，绝不能成为可引用的事实来源。最终题目仍然只能引用 `MaterialSegment` / `QuoteEntry` / `ContentChunk` 的原文 ID，`_validate_questions` 的 ID 存在性校验和台词逐字匹配校验保持不变、不放松。

## 2. 技术选型（已确认，不再讨论新增知识图谱/ES）

评估了引入独立知识库底座、知识图谱、Elasticsearch 等重型架构的方案，结论是：现有资料规模（单本书/单部剧，几千到几万条片段）用不上这些基础设施，复杂度收益比不合理。采用以下轻量方案：

1. **摘要策略：增量更新**。按“集数”（台词资料）或“页码窗口”（PDF，每 20 页一组）分组生成局部摘要，再基于局部摘要合并生成一份全局摘要。新增资料时，只有内容变化的分组会重新生成摘要，通过对比 `content_signature`（分组内片段 ID 排序后取 sha256）判断是否需要重新生成，未变化的分组直接复用旧摘要。
2. **忠实性校验：规则版**。不引入模型二次校验（避免新增一次不确定的模型调用），复用已有的 `question_dedup.token_similarity`（2/3 字 n-gram 的 Jaccard 相似度）计算题目答案文本（`explanation` + `correct_answers` + `answer_signature`）与引用原文片段的词汇重合度，重合度低于阈值时判定为可能捏造。
3. **召回方式：向量检索**。为 `ContentChunk`、`MaterialSegment`、`QuoteEntry` 生成并存储 embedding（`LargeBinary` 存储 `struct.pack` 序列化后的 float 数组，配合纯 Python 余弦相似度计算，不引入 numpy/向量数据库依赖），出题时按语义相似度召回候选片段，替代原来的随机 shuffle。
4. **摘要不需要人工审核**：摘要只作为背景理解注入 Prompt，不直接展示给用户、不作为答案依据展示，因此不需要审核工作流；生成失败时记录 `status=failed` 和 `error_message`，下一次增量刷新会重试。

## 3. 数据设计

### 3.1 `material_understandings`（新表）

| 字段 | 说明 |
| --- | --- |
| `id` | 主键 |
| `book_id` | 归属资源 |
| `scope_type` | `episode`（按集）/ `page_range`（PDF 按页码窗口）/ `material`（无集数无页码兜底）/ `book`（全局） |
| `scope_ref` | 集数、页码区间（如 `1-20`）或空字符串（book 级） |
| `summary_text` | 200 字以内摘要，仅用于理解，不作为引用来源 |
| `key_entities` | JSON，模型抽取的人物/事件等结构化信息，用于未来扩展 |
| `source_segment_ids` / `source_chunk_ids` | 该摘要覆盖的原文片段 ID 列表 |
| `content_signature` | 覆盖片段 ID 排序后的 sha256，用于增量判断是否需要重新生成 |
| `status` | `pending / completed / failed` |
| `error_message` | 失败原因 |

唯一约束 `(book_id, scope_type, scope_ref)`，保证同一分组只有一条记录，重新生成时是更新而不是追加。

### 3.2 向量字段

`ContentChunk`、`MaterialSegment`、`QuoteEntry` 均新增：

- `embedding: LargeBinary`：`struct.pack("<{n}f", ...)` 序列化后的向量字节
- `embedding_model: String(120)`：生成该向量时使用的模型名，模型切换后可用于判断是否需要重新计算

不引入独立向量数据库，直接在 SQLite 中按 book_id 过滤后在应用层做余弦相似度排序；数据规模在可预期范围内（单资源几千至几万条），全量计算的性能可接受。

## 4. 处理流程

### 4.1 增量摘要生成（`app/services/material_understanding.py`）

`refresh_material_understanding(book_id)`：

1. 取出该 `book_id` 下所有 `parse_status` 为 `completed`/`needs_review` 资料对应的 `MaterialSegment`，按 `episode_number`（有则用）或 `page_number` 分组；两者都没有时归入 `material` 兜底分组。
2. 对每个分组计算 `content_signature`；若已有记录且签名一致且状态为 `completed`，跳过，直接复用旧摘要文本用于后续全局摘要拼接。
3. 签名变化或首次出现的分组，调用模型生成局部摘要（`_summarize_text`），写入/更新 `MaterialUnderstanding`。
4. 任一分组发生变化时，重新拼接全部局部摘要生成一份 `scope_type="book"` 的全局摘要。
5. Mock 模式下直接截断原文当作摘要，不调用模型，保证测试环境可用。

触发时机：`parse_material_document` 解析完成后，用后台线程异步调用 `refresh_material_understanding`（不阻塞解析流程本身）；应用启动时（`app/main.py` lifespan）会对所有已有资料的 `book_id` 补跑一次，覆盖服务重启期间漏掉的更新。

PDF 场景（`parse_pdf_document`）同理，按页码窗口分组生成摘要，设计已预留 `scope_type="page_range"`，实现将在后续批次接入。

### 4.2 向量检索召回（已完成，`app/services/embedding_index.py`）

`refresh_book_embeddings(book_id)` 在 PDF/资料解析完成后由后台线程异步调用，为该书所有尚未生成向量或向量模型已过期的 `ContentChunk`/`MaterialSegment`/`QuoteEntry` 批量调用 `embedding_client.get_embedding_client()` 生成并存储向量（未配置 `LLM_EMBEDDING_MODEL` 或 mock 模式下直接跳过，不影响主流程）。

出题时，`HttpQuizAiProvider._candidate_chunks` 新增 `relevance_query` 参数（由专题约束 `theme_requirements` 和重出引导 `regeneration_guidance` 拼接而来），调用 `rank_by_similarity` 按与该查询的余弦相似度对“尚未使用过的候选”重新排序；只有当候选片段存在匹配当前配置模型的向量时才生效，否则回退到原有的按 `generation_number` 随机 shuffle，不影响现有行为。已使用过的候选（`recent_chunk_ids` 命中）仍保持随机 shuffle 降权，不参与相似度排序。

### 4.3 Prompt 背景注入（已完成）

`_generation_values` 新增 `background_context` 字段，取值来自 `material_understanding.get_understanding_context()`：包含全局摘要，以及命中候选台词所属集数的分集摘要。Prompt 中新增独立的“背景理解”段落，明确声明该背景仅用于理解剧情/内容脉络，不得作为可引用来源、不得把其中的具体表述当作答案依据，所有可引用内容仍必须来自 `SOURCE_MATERIAL`。`regenerate_quiz_question`、`regenerate_snapshot_question`、`run_generation_task` 三处出题入口均已接入。

### 4.4 规则版忠实性校验（已完成，`app/services/faithfulness_check.py`）

`_validate_questions` 通过之后，对 `source_mode` 为 `pdf`/`material` 的题目新增一轮规则校验，作为已有 ID 存在性校验和台词逐字匹配校验之外的额外保护层（不替代、不放松原有校验）：

- `source_text_for_question` 拼接题目引用的每一个已验证来源（`ContentChunk.content` / `MaterialSegment.content` / `TrustedQuoteSource.content`）的正文，说话人题（`quote_speaker` 等子类型）额外拼接 `speaker`、`context` 元数据字段，因为说话人姓名和场景说明本身不在 `content` 正文里，只存在于这些元数据字段中，若不纳入会造成误判。
- `check_question_faithfulness` 复用 `question_dedup.token_similarity`，计算 `explanation + correct_answers_text + answer_signature` 拼接文本与来源文本的 2/3 字 n-gram Jaccard 相似度，低于 `MIN_OVERLAP_RATIO`（当前 0.03）判定为不通过。
- 阈值经过对比实测校准：正常的合理复述重合度约 0.07~0.09；完全捏造、与原文无关的内容重合度普遍低于 0.02。取 0.03 只拦截几乎完全不沾边的极端捏造，避免误伤正常复述。
- 校验不通过时在 `quiz_provider.py` 中抛出 `RuntimeError`，附带重合度数值，交由现有的重试/拒绝逻辑处理，不新增额外的重试策略。
- 来源为空（例如 `model_knowledge` 模式或题目未引用任何原文）时直接放行，规则校验只对引用了具体原文片段却答案脱节的场景生效。

## 5. CSV 台词格式兼容说明

用户提供的《潜伏》台词 CSV 采用“集数,页码,类型,角色,内容”表头，其中`类型`为`环境描写/旁白/台词`等，环境描写和旁白行没有角色。`material_parser.py` 已扩展 `FIELD_ALIASES` 支持 `内容`→`content`、`类型`→`row_type`、`页码`→`page`、`集数`→`episode` 别名。带`类型`列的台词表中，任何角色为空的行（不论 `row_type` 是环境描写、旁白，还是台词但确实没有明确说话人，例如画外音、群众对白）都会正常写入 `MaterialSegment`，保留 `speaker=None`、`speaker_origin="unknown"`，不会因为个别行缺角色而整份文件解析失败；只有 `content` 满足可引用长度阈值时才会同时生成 `QuoteEntry`（`review_status="pending"`），进入资料校对流程等待人工补充角色，与字幕/PDF 场景的“无角色台词待校对”策略一致。只有完全没有`类型`列的传统两列台词表（仅“台词,角色”）才要求每行角色必填，因为这种格式的每一行都被视为可直接出题的确定台词。已用完整版《潜伏》台词 CSV（14408 行，30 集，含 60 行无角色台词）验证解析、集数分组均正确，`tests/test_trusted_materials.py::test_qianfu_style_episode_page_csv_is_parsed` 覆盖该格式的回归测试。

## 6. 不做的事情

- 不引入独立知识库底座、向量数据库或搜索引擎（ES/Milvus 等），现有数据规模不需要。
- 不引入知识图谱抽取和维护，复杂度过高，收益不明确。
- 摘要生成不设人工审核环节。
- 不对已有 `_validate_questions` 的 ID 存在性和逐字匹配校验做任何放松。
