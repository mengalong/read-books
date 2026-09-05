"use client";

import { AlertCircle, ArrowLeft, Check, CheckCircle2, ChevronUp, Clock3, Copy, Edit3, FileQuestion, LibraryBig, LoaderCircle, MessageSquareQuote, Minus, Plus, RefreshCcw, RotateCcw, Save, Sparkles, Square, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { ErrorState, SourceModeNotice } from "@/components/ui";
import { ApiError, cancelGenerationTask, deleteGenerationTask, generateQuiz, getBook, getGenerationTask, getGenerationTaskDebug, getMaterials, getQuotes, interveneGenerationTask } from "@/lib/api";
import { copyText } from "@/lib/clipboard";
import { materialTypeLabel, resourceTypeLabel } from "@/lib/format";
import type { BookDetail, GenerationTheme, Question, QuestionSubtype, QuizGenerationCall, QuizGenerationQuestionState, QuizGenerationTask, QuoteEntryList, ResourceMaterial } from "@/lib/types";

type CountKey = "single_count" | "multiple_count" | "short_count";

const questionTypes: { key: CountKey; label: string; detail: string; seconds: number }[] = [
  { key: "single_count", label: "单项选择题", detail: "事实、角色与场景辨认", seconds: 45 },
  { key: "multiple_count", label: "多项选择题", detail: "多条信息的综合判断", seconds: 90 },
  { key: "short_count", label: "问答题", detail: "主动组织语言，由 AI 自动评分", seconds: 180 },
];

const themes: { value: GenerationTheme; label: string }[] = [
  { value: "general", label: "综合内容" },
  { value: "classic_quotes", label: "经典台词" },
  { value: "character", label: "角色专题" },
];

const subtypeOptions: Record<Exclude<GenerationTheme, "general">, { value: QuestionSubtype; label: string }[]> = {
  classic_quotes: [
    { value: "quote_speaker", label: "说话人" },
    { value: "quote_context", label: "对话场景" },
    { value: "quote_meaning", label: "台词含义" },
  ],
  character: [
    { value: "quote_speaker", label: "说话人" },
    { value: "quote_context", label: "对话场景" },
    { value: "quote_meaning", label: "台词含义" },
    { value: "character_relation", label: "人物关系" },
    { value: "character_trait", label: "人物特征" },
  ],
};

export default function NewQuizPage() {
  const params = useParams<{ bookId: string }>();
  const bookId = params.bookId;
  const [book, setBook] = useState<BookDetail | null>(null);
  const [materials, setMaterials] = useState<ResourceMaterial[]>([]);
  const [quotes, setQuotes] = useState<QuoteEntryList | null>(null);
  const [theme, setTheme] = useState<GenerationTheme>("general");
  const [selectedMaterialIds, setSelectedMaterialIds] = useState<string[]>([]);
  const [selectedCharacters, setSelectedCharacters] = useState<string[]>([]);
  const [selectedSubtypes, setSelectedSubtypes] = useState<QuestionSubtype[]>([
    "quote_speaker",
    "quote_context",
    "quote_meaning",
  ]);
  const [difficulty, setDifficulty] = useState("medium");
  const [duration, setDuration] = useState(15);
  const [useQuestionBank, setUseQuestionBank] = useState(true);
  const [counts, setCounts] = useState<Record<CountKey, number>>({ single_count: 5, multiple_count: 3, short_count: 2 });
  const [pageStart, setPageStart] = useState("");
  const [pageEnd, setPageEnd] = useState("");
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [generationTask, setGenerationTask] = useState<QuizGenerationTask | null>(null);
  const [generationCalls, setGenerationCalls] = useState<QuizGenerationCall[]>([]);
  const [taskCopyState, setTaskCopyState] = useState<"idle" | "copied">("idle");
  const [taskActionBusy, setTaskActionBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([
      getBook(bookId),
      getMaterials(bookId),
      getQuotes(bookId, { review_status: "confirmed", page_size: 200 }),
    ])
      .then(async ([bookData, materialData, quoteData]) => {
        setBook(bookData);
        setMaterials(materialData);
        setQuotes(quoteData);
        const usableMaterialIds = new Set(quoteData.items.filter((item) => item.enabled_for_generation).map((item) => item.material_id));
        setSelectedMaterialIds(materialData.filter((item) => usableMaterialIds.has(item.id)).map((item) => item.id));
        if (bookData.active_generation_task_id) {
          const task = await getGenerationTask(bookData.active_generation_task_id);
          setGenerationTask(task);
          setUseQuestionBank(task.use_question_bank ?? true);
          setGenerationCalls((await getGenerationTaskDebug(task.id)).calls);
        }
      })
      .catch((reason: unknown) => setError(reason instanceof ApiError ? reason.message : "出题设置加载失败"))
      .finally(() => setLoading(false));
  }, [bookId]);

  useEffect(() => {
    if (!generationTask || !["pending", "processing"].includes(generationTask.status)) return;
    const poll = async () => {
      try {
        const [task, debug] = await Promise.all([
          getGenerationTask(generationTask.id),
          getGenerationTaskDebug(generationTask.id),
        ]);
        setGenerationTask(task);
        setGenerationCalls(debug.calls);
      } catch (reason: unknown) {
        setError(reason instanceof ApiError ? reason.message : "出题进度加载失败");
      }
    };
    const timer = window.setInterval(() => void poll(), 1500);
    return () => window.clearInterval(timer);
  }, [generationTask]);

  const estimatedMinutes = useMemo(() => Math.ceil(questionTypes.reduce((sum, type) => sum + counts[type.key] * type.seconds, 0) / 60), [counts]);
  const totalQuestions = Object.values(counts).reduce((sum, count) => sum + count, 0);
  const usableMaterials = materials.filter((material) => material.quote_count > 0 && ["needs_review", "completed"].includes(material.parse_status));
  const availableQuotes = useMemo(() => (quotes?.items || []).filter((quote) => (
    quote.enabled_for_generation
    && selectedMaterialIds.includes(quote.material_id)
    && (!selectedCharacters.length || Boolean(quote.speaker && selectedCharacters.includes(quote.speaker)))
  )), [quotes, selectedCharacters, selectedMaterialIds]);
  const availableSpeakers = quotes?.speakers || [];

  function adjust(key: CountKey, delta: number) {
    setCounts((current) => ({ ...current, [key]: Math.max(0, Math.min(15, current[key] + delta)) }));
  }

  function changeTheme(nextTheme: GenerationTheme) {
    setTheme(nextTheme);
    setSelectedCharacters([]);
    if (nextTheme === "classic_quotes") setSelectedSubtypes(["quote_speaker", "quote_context", "quote_meaning"]);
    if (nextTheme === "character") setSelectedSubtypes(["quote_context", "quote_meaning", "character_trait"]);
  }

  function toggleValue<T extends string>(values: T[], value: T, setter: (next: T[]) => void) {
    setter(values.includes(value) ? values.filter((item) => item !== value) : [...values, value]);
  }

  async function handleGenerate() {
    setGenerating(true);
    setError("");
    try {
      const task = await generateQuiz(bookId, {
        duration_minutes: duration,
        difficulty,
        ...counts,
        use_question_bank: useQuestionBank,
        ...(theme === "general" && pageStart ? { page_start: Number(pageStart) } : {}),
        ...(theme === "general" && pageEnd ? { page_end: Number(pageEnd) } : {}),
        generation_theme: theme,
        theme_config: {
          material_ids: theme === "general" ? [] : selectedMaterialIds,
          character_names: theme === "general" ? [] : selectedCharacters,
          question_subtypes: theme === "general" ? [] : selectedSubtypes,
        },
      });
      setGenerationTask(task);
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "测试生成失败");
    } finally {
      setGenerating(false);
    }
  }

  if (loading) return <div className="page-wrap"><div className="loading-state">正在准备测试设置……</div></div>;
  if (!book) return <div className="page-wrap"><ErrorState message={error || "未找到这个资源"} /></div>;

  const hasPdfSource = book.stats.completed_pdf_count > 0;
  const canUseModelKnowledge = Boolean(book.model_knowledge_supported === true || (book.resource_type === "book" && book.model_knowledge_supported !== false));
  const hasTrustedQuotes = Boolean(book.stats.confirmed_quote_count);
  const hasPlotSource = materials.some((material) => material.material_type === "plot_summary" && material.segment_count > 0 && ["needs_review", "completed"].includes(material.parse_status));
  const generalReady = hasPdfSource || hasTrustedQuotes || hasPlotSource || canUseModelKnowledge;
  const themedReady = selectedMaterialIds.length > 0
    && selectedSubtypes.length > 0
    && (theme !== "character" || selectedCharacters.length > 0)
    && availableQuotes.length >= totalQuestions
    && !(selectedSubtypes.length === 1 && selectedSubtypes[0] === "quote_speaker" && (counts.multiple_count > 0 || counts.short_count > 0));
  const canGenerate = totalQuestions > 0 && (theme === "general" ? generalReady : themedReady);
  const sourceMode = theme === "general"
    ? (hasPdfSource && (hasTrustedQuotes || hasPlotSource) || hasTrustedQuotes && hasPlotSource ? "combined" : hasPdfSource ? "pdf" : hasTrustedQuotes ? "material" : hasPlotSource ? "plot" : "model_knowledge")
    : "material";

  async function handleIntervention(
    position: number,
    action: "retry" | "accept" | "replace" | "edit",
    question?: Record<string, unknown>,
  ) {
    if (!generationTask) return;
    setError("");
    try {
      setGenerationTask(await interveneGenerationTask(generationTask.id, position, { action, ...(question ? { question } : {}) }));
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "人工介入操作失败");
    }
  }

  async function handleCopyGeneration() {
    if (!generationTask || !book) return;
    setError("");
    try {
      await copyText(formatGenerationTaskTrace(book.title, generationTask, generationCalls));
      setTaskCopyState("copied");
      window.setTimeout(() => setTaskCopyState("idle"), 1500);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "复制出题内容失败");
    }
  }

  async function handleCancelGeneration() {
    if (!generationTask || !["pending", "processing", "awaiting_intervention"].includes(generationTask.status)) return;
    if (!window.confirm("确定要终止当前出题任务吗？已生成的中间结果和调试记录会保留。")) return;
    setTaskActionBusy(true);
    setError("");
    try {
      setGenerationTask(await cancelGenerationTask(generationTask.id));
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "终止出题任务失败");
    } finally {
      setTaskActionBusy(false);
    }
  }

  async function handleDeleteGeneration() {
    if (!generationTask || ["pending", "processing", "completed"].includes(generationTask.status)) return;
    if (!window.confirm("确定删除这次出题任务及其调试记录吗？此操作不可撤销。")) return;
    setTaskActionBusy(true);
    setError("");
    try {
      await deleteGenerationTask(generationTask.id);
      setGenerationTask(null);
      setGenerationCalls([]);
      setTaskCopyState("idle");
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "删除出题任务失败");
    } finally {
      setTaskActionBusy(false);
    }
  }

  return (
    <div className="page-wrap">
      <Link className="back-link" href={`/books/${book.id}`}><ArrowLeft size={14} />返回《{book.title}》</Link>
      <header className="page-header" style={{ marginBottom: 25 }}>
        <div><h1 className="page-title">生成一套复习测试</h1><p className="page-description">{resourceTypeLabel(book.resource_type)} · {book.title}</p></div>
      </header>
      {error && <div className="toast-error">{error}</div>}
      {book.model_knowledge_message && sourceMode === "model_knowledge" && <div className={`shelf-status-banner${book.model_knowledge_supported === false ? " warning" : ""}`}><AlertCircle size={18} /><div><strong>{book.model_knowledge_supported === true ? "模型真实内容检查通过" : book.model_knowledge_supported === false ? "模型真实内容检查未通过" : "模型真实内容检查未执行"}</strong><span>{book.model_knowledge_message}</span></div></div>}
      {(canGenerate || sourceMode === "material") && <SourceModeNotice sourceMode={sourceMode} />}

      {generationTask && <section className={`generation-progress ${generationTask.status}`}>
        <div className="generation-progress-heading"><div><strong>{generationTask.status === "completed" ? "复习试卷已经准备好" : generationTask.status === "awaiting_intervention" ? "本次出题需要人工处理" : generationTask.status === "failed" ? "本次出题未完成" : generationTask.status === "cancelled" ? "本次出题已手动终止" : generationTask.current_phase}</strong></div>{generationTask.status === "completed" ? <CheckCircle2 size={21} /> : generationTask.status === "awaiting_intervention" || generationTask.status === "failed" || generationTask.status === "cancelled" ? <AlertCircle size={21} /> : <LoaderCircle className={["pending", "processing"].includes(generationTask.status) ? "spin" : ""} size={21} />}</div>
        <div className="progress-track"><div className="progress-fill" style={{ width: `${generationTask.total_questions ? generationTask.completed_questions / generationTask.total_questions * 100 : 0}%` }} /></div>
        <div className="generation-progress-meta"><span>{generationTask.completed_questions} / {generationTask.total_questions} 道题</span><span>{generationTask.error_message || generationTask.current_phase}</span></div>
        <GenerationQuestionStates task={generationTask} calls={generationCalls} onIntervention={handleIntervention} />
        <div className="generation-progress-actions"><button className="button button-secondary" disabled={taskActionBusy} onClick={() => void handleCopyGeneration()} type="button"><Copy size={15} />{taskCopyState === "copied" ? "已复制出题内容" : "复制当前出题内容"}</button>{["pending", "processing", "awaiting_intervention"].includes(generationTask.status) && <button className="button button-secondary" disabled={taskActionBusy} onClick={() => void handleCancelGeneration()} type="button"><Square size={14} />终止出题</button>}{["cancelled", "failed"].includes(generationTask.status) && <button className="button button-danger" disabled={taskActionBusy} onClick={() => void handleDeleteGeneration()} type="button"><Trash2 size={14} />删除任务</button>}{generationTask.status === "completed" && generationTask.quiz_id && <Link className="button button-primary" href={`/quizzes/${generationTask.quiz_id}`}><CheckCircle2 size={15} />查看并开始复习</Link>}</div>
      </section>}

      <div className="quiz-settings-grid">
        <section className="form-panel" style={{ maxWidth: "none" }}>
          <div className="settings-block theme-settings"><label>出题主题</label><div className="segmented-control">{themes.map((item) => <button className={theme === item.value ? "active" : ""} disabled={item.value !== "general" && !quotes?.confirmed_count} key={item.value} onClick={() => changeTheme(item.value)} type="button">{theme === item.value && <Check size={13} />}{item.label}</button>)}</div>{!quotes?.confirmed_count && <span className="field-hint">经典台词和角色专题需要先上传并确认可信台词。</span>}</div>

          {theme !== "general" && <div className="topic-settings">
            <div className="settings-block"><label>可信资料</label><div className="choice-list">{usableMaterials.map((material) => <label key={material.id}><input checked={selectedMaterialIds.includes(material.id)} onChange={() => toggleValue(selectedMaterialIds, material.id, setSelectedMaterialIds)} type="checkbox" /><span><strong>{material.file_name}</strong><small>{materialTypeLabel(material.material_type)} · {material.quote_count} 条台词</small></span></label>)}</div>{!usableMaterials.length && <Link className="inline-link" href={`/books/${book.id}`}>返回资源详情上传资料</Link>}</div>

            <div className="settings-block"><label>{theme === "character" ? "角色（必选）" : "角色范围（可选）"}</label><div className="choice-chip-list">{availableSpeakers.map((name) => <label key={name}><input checked={selectedCharacters.includes(name)} onChange={() => toggleValue(selectedCharacters, name, setSelectedCharacters)} type="checkbox" /><span>{name}</span></label>)}</div>{!availableSpeakers.length && <Link className="inline-link" href={`/books/${book.id}/quotes`}>前往台词校对</Link>}</div>

            <div className="settings-block"><label>考察角度</label><div className="choice-chip-list">{subtypeOptions[theme].map((item) => <label key={item.value}><input checked={selectedSubtypes.includes(item.value)} onChange={() => toggleValue(selectedSubtypes, item.value, setSelectedSubtypes)} type="checkbox" /><span>{item.label}</span></label>)}</div></div>

            {availableQuotes.length < totalQuestions && <div className="inline-warning"><AlertCircle size={16} /><span>当前范围有 {availableQuotes.length} 条可用台词，本套试卷需要至少 {totalQuestions} 条。</span><Link href={`/books/${book.id}/quotes`}>调整校对结果</Link></div>}
          </div>}

          <div className="section-title"><h2>题目组成</h2><span>预计 {estimatedMinutes} 分钟</span></div>
          <div className="count-list">{questionTypes.map((type) => <div className="count-row" key={type.key}><div className="count-icon"><FileQuestion size={17} /></div><div className="count-copy"><strong>{type.label}</strong><span>{type.detail}</span></div><div className="stepper"><button aria-label={`减少${type.label}`} onClick={() => adjust(type.key, -1)} type="button"><Minus size={14} /></button><span>{counts[type.key]}</span><button aria-label={`增加${type.label}`} onClick={() => adjust(type.key, 1)} type="button"><Plus size={14} /></button></div></div>)}</div>

          <div className="settings-block"><label>难度</label><div className="segmented-control">{[{ value: "easy", label: "基础" }, { value: "medium", label: "适中" }, { value: "hard", label: "深入" }].map((item) => <button className={difficulty === item.value ? "active" : ""} key={item.value} onClick={() => setDifficulty(item.value)} type="button">{difficulty === item.value && <Check size={13} />}{item.label}</button>)}</div></div>
          <div className="settings-block question-bank-setting"><label className="switch-control" htmlFor="use-question-bank"><input checked={useQuestionBank} id="use-question-bank" onChange={(event) => setUseQuestionBank(event.target.checked)} type="checkbox" /><span className="switch-track" aria-hidden="true"><span className="switch-thumb" /></span><span><strong><LibraryBig size={14} />优先复用题库题目</strong><small>优先选择使用次数少且未被本资源其他试卷使用过的题目，再由模型补充不足部分。</small></span></label></div>
          <div className="settings-block"><label htmlFor="duration"><Clock3 size={14} style={{ verticalAlign: "-3px", marginRight: 5 }} />目标时长</label><select id="duration" value={duration} onChange={(event) => setDuration(Number(event.target.value))}><option value={10}>10 分钟</option><option value={15}>15 分钟</option><option value={20}>20 分钟</option><option value={30}>30 分钟</option></select></div>
          {theme === "general" && hasPdfSource && <div className="settings-block"><label>页码范围（可选）</label><div className="page-range"><input min={1} onChange={(event) => setPageStart(event.target.value)} placeholder="起始页" type="number" value={pageStart} /><span>至</span><input min={1} onChange={(event) => setPageEnd(event.target.value)} placeholder="结束页" type="number" value={pageEnd} /></div></div>}

          <div className="form-actions"><Link className="button button-secondary" href={`/books/${book.id}`}>返回资源</Link><button className="button button-primary" disabled={generating || ["pending", "processing", "awaiting_intervention"].includes(generationTask?.status || "") || !canGenerate} onClick={() => void handleGenerate()} type="button"><Sparkles size={15} />{generating ? "正在创建任务……" : generationTask?.status === "awaiting_intervention" ? "请先处理出题任务" : ["pending", "processing"].includes(generationTask?.status || "") ? "正在后台出题" : "生成复习试卷"}</button></div>
        </section>

        <aside className="quiz-settings-summary">
          <MessageSquareQuote size={18} />
          <strong>{totalQuestions} 道题</strong>
          <p>{theme === "general"
            ? sourceMode === "combined"
              ? "综合已解析 PDF、已确认剧情梗概和台词，题目必须保留真实来源依据。"
              : sourceMode === "pdf"
                ? "基于已解析 PDF 原文生成，并保留页码依据。"
                : sourceMode === "material"
                  ? `基于 ${book.stats.confirmed_quote_count} 条已确认台词生成，题目会保留可信资料定位。`
                  : sourceMode === "plot"
                    ? "基于已确认剧情梗概事件生成，题目会保留剧情来源定位。"
                  : "基于模型知识生成，不提供逐句原文依据。"
            : `基于 ${availableQuotes.length} 条已确认台词生成，题目会保留可信资料定位。`}</p>
          <dl><div><dt>主题</dt><dd>{themes.find((item) => item.value === theme)?.label}</dd></div><div><dt>目标时长</dt><dd>{duration} 分钟</dd></div><div><dt>预计用时</dt><dd>{estimatedMinutes} 分钟</dd></div><div><dt>评分方式</dt><dd>自动评分</dd></div></dl>
        </aside>
      </div>
    </div>
  );
}

const generationQuestionStatusLabels: Record<QuizGenerationQuestionState["status"], string> = {
  pending: "等待生成",
  generating: "生成中",
  ready: "已生成",
  awaiting_intervention: "待人工处理",
  confirmed: "已确认",
};

const sourceFocusLabels = { content: "剧情内容", dialogue: "台词理解", integrated: "剧情与台词关联" } as const;

function GenerationQuestionStates({ task, calls, onIntervention }: { task: QuizGenerationTask; calls: QuizGenerationCall[]; onIntervention: (position: number, action: "retry" | "accept" | "replace" | "edit", question?: Record<string, unknown>) => Promise<void> }) {
  if (!task.question_states?.length) return null;
  return <div className="generation-question-states"><div className="generation-question-states-heading"><strong>逐题出题过程</strong><span>可实时查看单题调用、完整草稿，失败题目可以人工介入</span></div>{task.question_states.map((state) => { const questionCalls = calls.filter((call) => call.question_position === state.position); const editable = !["completed", "cancelled"].includes(task.status) && (Boolean(state.question) || state.status === "awaiting_intervention"); return <article className={`generation-question-state ${state.status}`} key={state.position}><div className="generation-question-state-heading"><div><strong>第 {state.position} 题</strong><span>{state.question_type === "single" ? "单选题" : state.question_type === "multiple" ? "多选题" : "问答题"}{state.source_focus ? ` · ${sourceFocusLabels[state.source_focus]}` : ""} · 第 {state.attempts} 次调用</span></div><span className="generation-question-state-status">{generationQuestionStatusLabels[state.status]}</span></div>{state.error_message && <div className="generation-question-state-error"><AlertCircle size={14} />{state.error_message}</div>}<GenerationQuestionCalls calls={questionCalls} /><QuestionDraftPreview question={state.question} />{editable && <GenerationInterventionEditor state={state} taskStatus={task.status} onIntervention={onIntervention} />}</article>; })}</div>;
}

function GenerationQuestionCalls({ calls }: { calls: QuizGenerationCall[] }) {
  const [copied, setCopied] = useState(false);
  if (!calls.length) return null;
  const latest = calls[calls.length - 1];
  async function copyCalls(event: React.MouseEvent<HTMLButtonElement>) {
    event.preventDefault();
    await copyText(formatGenerationCalls(calls));
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  }
  return <details className="generation-question-call-preview"><summary>查看本题模型信息（{calls.length} 次调用 · {calls.reduce((sum, call) => sum + (call.total_tokens || 0), 0).toLocaleString()} token）</summary><div className="generation-question-call-actions"><button className="button button-quiet" onClick={(event) => void copyCalls(event)} type="button"><Copy size={13} />{copied ? "已复制" : "复制本题出题内容"}</button></div><div className="generation-question-call-meta"><span>{latest.phase}</span><span>输入 {latest.input_tokens === null ? "—" : latest.input_tokens.toLocaleString()}</span><span>输出 {latest.output_tokens === null ? "—" : latest.output_tokens.toLocaleString()}</span><span>总计 {latest.total_tokens === null ? "—" : latest.total_tokens.toLocaleString()}</span></div><div className="generation-question-call-messages">{latest.request_messages.map((message, index) => <div key={`${latest.id}-${index}`}><strong>{message.role}</strong><pre>{message.content}</pre></div>)}</div><div className="generation-question-call-response"><strong>模型回复</strong><pre>{latest.model_response || "模型尚未返回文本"}</pre></div>{latest.error_message && <div className="generation-question-state-error">{latest.error_message}</div>}</details>;
}

function formatGenerationCalls(calls: QuizGenerationCall[]): string {
  const lines: string[] = [];
  calls.forEach((call, index) => {
    lines.push(
      `===== 第 ${index + 1} 次模型调用 =====`,
      `阶段：${call.phase}`,
      `时间：${call.created_at}`,
      `模型：${call.model_name || "未记录"}`,
      `状态：${call.status === "success" ? "成功" : "失败"}`,
      `输入 token：${call.input_tokens === null ? "未返回" : call.input_tokens.toLocaleString()}`,
      `输出 token：${call.output_tokens === null ? "未返回" : call.output_tokens.toLocaleString()}`,
      `总 token：${call.total_tokens === null ? "未返回" : call.total_tokens.toLocaleString()}`,
      "",
      "--- 输入 Prompt ---",
    );
    call.request_messages.forEach((message) => lines.push(`[${message.role}]`, message.content));
    lines.push("", "--- 模型回复 ---", call.model_response || "模型尚未返回文本");
    if (call.error_message) lines.push("", "--- 错误 ---", call.error_message);
    lines.push("");
  });
  return lines.join("\n");
}

function formatGenerationTaskTrace(bookTitle: string, task: QuizGenerationTask, calls: QuizGenerationCall[]): string {
  const lines = [
    `资源：${bookTitle}`,
    `任务 ID：${task.id}`,
    `任务状态：${task.status}`,
    `当前阶段：${task.current_phase}`,
    `进度：${task.completed_questions} / ${task.total_questions} 道题`,
  ];
  task.question_states.forEach((state) => {
    lines.push("", `===== 第 ${state.position} 题 =====`, `状态：${generationQuestionStatusLabels[state.status]}`, `调用次数：${state.attempts}`);
    if (state.error_message) lines.push(`错误：${state.error_message}`);
    if (state.question) lines.push("", "--- 题目草稿 ---", JSON.stringify(state.question, null, 2));
    const questionCalls = calls.filter((call) => call.question_position === state.position);
    if (questionCalls.length) lines.push("", formatGenerationCalls(questionCalls));
  });
  const unassigned = calls.filter((call) => call.question_position === null);
  if (unassigned.length) lines.push("", "===== 未关联题目调用 =====", formatGenerationCalls(unassigned));
  return lines.join("\n");
}

function QuestionDraftPreview({ question }: { question: Partial<Question> | null }) {
  if (!question) return null;
  const draft = question as Record<string, unknown>;
  const options = Array.isArray(draft.options) ? draft.options as { id?: string; text?: string }[] : [];
  const correctAnswers = Array.isArray(draft.correct_answers) ? draft.correct_answers.map(String) : [];
  const rubric = Array.isArray(draft.grading_rubric) ? draft.grading_rubric as Record<string, unknown>[] : [];
  const sourceChunks = Array.isArray(draft.source_chunk_ids) ? draft.source_chunk_ids.map(String) : [];
  const quoteEntries = Array.isArray(draft.quote_entry_ids) ? draft.quote_entry_ids.map(String) : [];
  return <details className="generation-question-preview"><summary>查看完整题目草稿</summary><div className="generation-question-draft"><strong>题干</strong><p>{String(draft.prompt || "尚未生成题干")}</p>{options.length > 0 && <><strong>选项</strong><ol>{options.map((option) => <li key={String(option.id)}>{String(option.id || "")}. {String(option.text || "")}{option.id && correctAnswers.includes(option.id) ? "（正确答案）" : ""}</li>)}</ol></>}{<><strong>正确答案</strong><p>{correctAnswers.length ? correctAnswers.join("、") : "无（问答题）"}</p></>}{typeof draft.explanation === "string" && draft.explanation && <><strong>解析</strong><p>{draft.explanation}</p></>}{typeof draft.knowledge_point === "string" && draft.knowledge_point && <><strong>知识点</strong><p>{draft.knowledge_point}</p></>}{typeof draft.reference_answer === "string" && draft.reference_answer && <><strong>参考答案</strong><p>{draft.reference_answer}</p></>}{rubric.length > 0 && <><strong>评分要点</strong><ul>{rubric.map((item, index) => <li key={index}>{String(item.point || "评分要点")}{item.score !== undefined ? `（${String(item.score)}分）` : ""}</li>)}</ul></>}{(sourceChunks.length > 0 || quoteEntries.length > 0) && <><strong>来源 ID</strong><p>{sourceChunks.length > 0 ? `PDF：${sourceChunks.join("、")}` : ""}{sourceChunks.length > 0 && quoteEntries.length > 0 ? "；" : ""}{quoteEntries.length > 0 ? `台词：${quoteEntries.join("、")}` : ""}</p></>}</div></details>;
}

function GenerationInterventionEditor({ state, taskStatus, onIntervention }: { state: QuizGenerationQuestionState; taskStatus: QuizGenerationTask["status"]; onIntervention: (position: number, action: "retry" | "accept" | "replace" | "edit", question?: Record<string, unknown>) => Promise<void> }) {
  const draft = state.question || {};
  const [prompt, setPrompt] = useState(String(draft.prompt || ""));
  const [optionsText, setOptionsText] = useState((draft.options || []).map((option) => `${option.id}. ${option.text}`).join("\n"));
  const [correctAnswers, setCorrectAnswers] = useState((draft.correct_answers || []).join(","));
  const [explanation, setExplanation] = useState(String(draft.explanation || ""));
  const [knowledgePoint, setKnowledgePoint] = useState(String(draft.knowledge_point || ""));
  const [referenceAnswer, setReferenceAnswer] = useState(String(draft.reference_answer || ""));
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(state.status === "awaiting_intervention");

  useEffect(() => {
    setPrompt(String(draft.prompt || ""));
    setOptionsText((draft.options || []).map((option) => `${option.id}. ${option.text}`).join("\n"));
    setCorrectAnswers((draft.correct_answers || []).join(","));
    setExplanation(String(draft.explanation || ""));
    setKnowledgePoint(String(draft.knowledge_point || ""));
    setReferenceAnswer(String(draft.reference_answer || ""));
  }, [state.position, state.updated_at]);

  useEffect(() => {
    if (state.status === "awaiting_intervention") setEditing(true);
  }, [state.status]);

  async function run(action: "retry" | "accept" | "replace" | "edit", question?: Record<string, unknown>) {
    setBusy(true);
    try {
      await onIntervention(state.position, action, question);
    } finally {
      setBusy(false);
    }
  }

  function parseOptions() {
    return optionsText.split("\n").map((line, index) => {
      const value = line.trim();
      if (!value) return null;
      const match = value.match(/^([A-Z])(?:[.、:：]|\s)+(.+)$/);
      return { id: match?.[1] || String.fromCharCode(65 + index), text: match?.[2]?.trim() || value };
    }).filter((value): value is { id: string; text: string } => Boolean(value));
  }

  async function saveEdit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await run("edit", {
      prompt: prompt.trim(),
      options: state.question_type === "short" ? [] : parseOptions(),
      correct_answers: correctAnswers.split(",").map((value) => value.trim()).filter(Boolean),
      explanation: explanation.trim(),
      knowledge_point: knowledgePoint.trim() || "人工调整",
      reference_answer: state.question_type === "short" ? referenceAnswer.trim() || null : null,
    });
  }

  if (!editing && state.question) return <button className="button button-quiet generation-question-edit-trigger" onClick={() => setEditing(true)} type="button"><Edit3 size={14} />人工调整本题</button>;
  return <form className="generation-intervention-editor" onSubmit={(event) => void saveEdit(event)}><div className="generation-intervention-editor-heading"><Edit3 size={14} /><strong>人工处理第 {state.position} 题</strong></div><label>题干<textarea aria-label={`第${state.position}题人工题干`} onChange={(event) => setPrompt(event.target.value)} rows={2} value={prompt} /></label>{state.question_type !== "short" && <><label>选项（每行一个，例如 A. 选项内容）<textarea aria-label={`第${state.position}题选项`} onChange={(event) => setOptionsText(event.target.value)} rows={4} value={optionsText} /></label><label>正确答案（用逗号分隔）<input aria-label={`第${state.position}题正确答案`} onChange={(event) => setCorrectAnswers(event.target.value)} value={correctAnswers} /></label></>}{state.question_type === "short" && <label>参考答案<textarea aria-label={`第${state.position}题人工参考答案`} onChange={(event) => setReferenceAnswer(event.target.value)} rows={3} value={referenceAnswer} /></label>}<label>解析<textarea aria-label={`第${state.position}题解析`} onChange={(event) => setExplanation(event.target.value)} rows={2} value={explanation} /></label><label>知识点<input aria-label={`第${state.position}题知识点`} onChange={(event) => setKnowledgePoint(event.target.value)} value={knowledgePoint} /></label><div className="generation-intervention-actions"><button className="button button-primary" disabled={busy || !prompt.trim()} type="submit"><Save size={14} />保存调整并继续</button>{state.question && <button className="button button-secondary" disabled={busy} onClick={() => void run("accept")} type="button"><Check size={14} />确认题目可用</button>}{state.question && <button className="button button-quiet" disabled={busy} onClick={() => setEditing(false)} type="button"><ChevronUp size={14} />收起编辑</button>}{["awaiting_intervention", "failed"].includes(taskStatus) && <><button className="button button-secondary" disabled={busy} onClick={() => void run("retry")} type="button"><RotateCcw size={14} />重试本题</button><button className="button button-secondary" disabled={busy} onClick={() => void run("replace")} type="button"><RefreshCcw size={14} />换题重出</button></>}</div></form>;
}
