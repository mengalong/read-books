# 资料理解层设计（轻量方案）

实施状态（2026-09-04）：数据结构与增量摘要生成已完成；向量检索召回、Prompt 背景注入与规则版忠实性校验正在实施中。

## 1. 背景与目标

出题时的“捏造事实”问题主要来自两类原因：

- 使用模型内化知识出题（`model_knowledge` 来源模式）时，模型可能记错细节或混淆版本。
- 使用用户上传的可信资料出题（`material`/`pdf` 来源模式）时，召回逐条台词或原文片段时缺乏对整本书/整部剧上下文的理解，容易断章取义或答案缺乏依据。

本设计只解决第二类问题：**在忠实原文的前提下，让系统对已上传资料有更完整的理解，出题时既能精确引用原文，又能利用整体上下文避免断章取义**。

核心原则不变：摘要、向量检索都只是"理解与召回"的辅助手段，绝不能成为可引用的事实来源。最终题目仍然只能引用 `MaterialSegment` / `QuoteEntry` / `ContentChunk` 的原文 ID，`_validate_questions` 的 ID 存在性校验和台词逐字匹配校验保持不变、不放松。

## 2. 技术选型（已确认，不再讨论新增知识图谱/ES）

评估了引入独立知识库底座、知识图谱、Elasticsearch 等重型架构的方案，结论是：现有资料规模（单本书/单部剧，几千到几万条片段）用不上这些基础设施，复杂度收益比不合理。采用以下轻量方案：

1. **摘要策略：增量更新**。按“集数”（台词资料）或“页码窗口”（PDF，每 20 页一组）分组生成局部摘要，再基于局部摘要合并生成一份全局摘要。新增资料时，只有内容变化的分组会重新生成摘要，通过对比 `content_signature`（分组内片段 ID 排序后取 sha256）判断是否需要重新生成，未变化的分组直接复用旧摘要。
2. **忠实性校验：规则版**。不引入模型二次校验（避免新增一次不确定的模型调用），改为后端关键词/实体级别的规则校验：检查题目的 `explanation`、`correct_answers`、`answer_signature` 中出现的关键实体是否能在题目引用的原文片段（`source_chunk_ids`/`quote_entry_ids`）中找到依据。
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

### 4.2 向量检索召回（规划中）

解析完成后为每条 `MaterialSegment`/`QuoteEntry`/`ContentChunk` 调用 `embedding_client.get_embedding_client()` 生成并存储向量。出题时，`_candidate_chunks`（`quiz_provider.py`）会优先按“与近期已考察事实、专题关键词”的向量相似度排序候选池，替代当前基于 `generation_number` 的随机 shuffle，同时保留“最近使用过的片段降权”的既有去重逻辑。

### 4.3 Prompt 背景注入（规划中）

`_generation_values` 会在 `source_material` 之外新增一个独立字段（如 `background_context`），仅包含 `get_understanding_context()` 返回的摘要文本。Prompt 会明确声明：该背景仅用于理解剧情/内容脉络，不得引用摘要中的具体表述作为答案依据，所有可引用内容仍必须来自 `source_material` 列表。

### 4.4 规则版忠实性校验（规划中）

出题校验通过 `_validate_questions` 之后，新增一轮规则校验：从 `explanation`/`answer_signature`/`correct_answers` 中提取关键词（复用 `question_dedup.question_keywords` 的 n-gram 思路），检查这些关键词是否在引用的原文片段内容中有足够重合度；重合度不足时判定为可能捏造，交由 provider 重试或拒绝该题。

## 5. CSV 台词格式兼容说明

用户提供的《潜伏》台词 CSV 采用“集数,页码,类型,角色,内容”表头，其中`类型`为`环境描写/旁白/台词`等，环境描写和旁白行没有角色。`material_parser.py` 已扩展 `FIELD_ALIASES` 支持 `内容`→`content`、`类型`→`row_type`、`页码`→`page` 别名，并新增 `NON_DIALOGUE_ROW_TYPES` 白名单，允许这类无角色行通过解析（写入 `MaterialSegment` 但不生成 `QuoteEntry`，因为环境描写和旁白不是可引用的逐字台词）。这些行仍会进入资料理解层的摘要输入，有助于生成更完整的剧情背景摘要。

## 6. 不做的事情

- 不引入独立知识库底座、向量数据库或搜索引擎（ES/Milvus 等），现有数据规模不需要。
- 不引入知识图谱抽取和维护，复杂度过高，收益不明确。
- 摘要生成不设人工审核环节。
- 不对已有 `_validate_questions` 的 ID 存在性和逐字匹配校验做任何放松。
