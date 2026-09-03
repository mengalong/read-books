"use client";

import { AlertCircle, ArrowLeft, Check, CheckCircle2, Clock3, FileQuestion, LoaderCircle, MessageSquareQuote, Minus, Plus, Sparkles } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { ErrorState, SourceModeNotice } from "@/components/ui";
import { ApiError, generateQuiz, getBook, getGenerationTask, getMaterials, getQuotes } from "@/lib/api";
import { materialTypeLabel, resourceTypeLabel } from "@/lib/format";
import type { BookDetail, GenerationTheme, QuestionSubtype, QuizGenerationTask, QuoteEntryList, ResourceMaterial } from "@/lib/types";

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
  const [counts, setCounts] = useState<Record<CountKey, number>>({ single_count: 5, multiple_count: 3, short_count: 2 });
  const [pageStart, setPageStart] = useState("");
  const [pageEnd, setPageEnd] = useState("");
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [generationTask, setGenerationTask] = useState<QuizGenerationTask | null>(null);
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
        if (bookData.active_generation_task_id) setGenerationTask(await getGenerationTask(bookData.active_generation_task_id));
      })
      .catch((reason: unknown) => setError(reason instanceof ApiError ? reason.message : "出题设置加载失败"))
      .finally(() => setLoading(false));
  }, [bookId]);

  useEffect(() => {
    if (!generationTask || !["pending", "processing"].includes(generationTask.status)) return;
    const poll = async () => {
      try {
        setGenerationTask(await getGenerationTask(generationTask.id));
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
  const generalReady = hasPdfSource || canUseModelKnowledge;
  const themedReady = selectedMaterialIds.length > 0
    && selectedSubtypes.length > 0
    && (theme !== "character" || selectedCharacters.length > 0)
    && availableQuotes.length >= totalQuestions
    && !(selectedSubtypes.length === 1 && selectedSubtypes[0] === "quote_speaker" && (counts.multiple_count > 0 || counts.short_count > 0));
  const canGenerate = totalQuestions > 0 && (theme === "general" ? generalReady : themedReady);
  const sourceMode = theme === "general" ? (hasPdfSource ? "pdf" : "model_knowledge") : "material";

  return (
    <div className="page-wrap">
      <Link className="back-link" href={`/books/${book.id}`}><ArrowLeft size={14} />返回《{book.title}》</Link>
      <header className="page-header" style={{ marginBottom: 25 }}>
        <div><h1 className="page-title">生成一套复习测试</h1><p className="page-description">{resourceTypeLabel(book.resource_type)} · {book.title}</p></div>
      </header>
      {error && <div className="toast-error">{error}</div>}
      {book.model_knowledge_message && theme === "general" && <div className={`shelf-status-banner${book.model_knowledge_supported === false ? " warning" : ""}`}><AlertCircle size={18} /><div><strong>{book.model_knowledge_supported === true ? "模型真实内容检查通过" : book.model_knowledge_supported === false ? "模型真实内容检查未通过" : "模型真实内容检查未执行"}</strong><span>{book.model_knowledge_message}</span></div></div>}
      {(canGenerate || sourceMode === "material") && <SourceModeNotice sourceMode={sourceMode} />}

      {generationTask && <section className={`generation-progress ${generationTask.status}`}>
        <div className="generation-progress-heading"><div><strong>{generationTask.status === "completed" ? "复习试卷已经准备好" : generationTask.status === "failed" ? "本次出题未完成" : generationTask.current_phase}</strong></div>{generationTask.status === "completed" ? <CheckCircle2 size={21} /> : <LoaderCircle className={["pending", "processing"].includes(generationTask.status) ? "spin" : ""} size={21} />}</div>
        <div className="progress-track"><div className="progress-fill" style={{ width: `${generationTask.total_questions ? generationTask.completed_questions / generationTask.total_questions * 100 : 0}%` }} /></div>
        <div className="generation-progress-meta"><span>{generationTask.completed_questions} / {generationTask.total_questions} 道题</span><span>{generationTask.error_message || generationTask.current_phase}</span></div>
        {generationTask.status === "completed" && generationTask.quiz_id && <div className="generation-progress-actions"><Link className="button button-primary" href={`/quizzes/${generationTask.quiz_id}`}><CheckCircle2 size={15} />查看并开始复习</Link></div>}
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
          <div className="settings-block"><label htmlFor="duration"><Clock3 size={14} style={{ verticalAlign: "-3px", marginRight: 5 }} />目标时长</label><select id="duration" value={duration} onChange={(event) => setDuration(Number(event.target.value))}><option value={10}>10 分钟</option><option value={15}>15 分钟</option><option value={20}>20 分钟</option><option value={30}>30 分钟</option></select></div>
          {theme === "general" && hasPdfSource && <div className="settings-block"><label>页码范围（可选）</label><div className="page-range"><input min={1} onChange={(event) => setPageStart(event.target.value)} placeholder="起始页" type="number" value={pageStart} /><span>至</span><input min={1} onChange={(event) => setPageEnd(event.target.value)} placeholder="结束页" type="number" value={pageEnd} /></div></div>}

          <div className="form-actions"><Link className="button button-secondary" href={`/books/${book.id}`}>返回资源</Link><button className="button button-primary" disabled={generating || ["pending", "processing"].includes(generationTask?.status || "") || !canGenerate} onClick={() => void handleGenerate()} type="button"><Sparkles size={15} />{generating ? "正在创建任务……" : ["pending", "processing"].includes(generationTask?.status || "") ? "正在后台出题" : "生成复习试卷"}</button></div>
        </section>

        <aside className="quiz-settings-summary">
          <MessageSquareQuote size={18} />
          <strong>{totalQuestions} 道题</strong>
          <p>{theme === "general" ? (hasPdfSource ? "基于已解析 PDF 原文生成，并保留页码依据。" : "基于模型知识生成，不提供逐句原文依据。") : `基于 ${availableQuotes.length} 条已确认台词生成，题目会保留可信资料定位。`}</p>
          <dl><div><dt>主题</dt><dd>{themes.find((item) => item.value === theme)?.label}</dd></div><div><dt>目标时长</dt><dd>{duration} 分钟</dd></div><div><dt>预计用时</dt><dd>{estimatedMinutes} 分钟</dd></div><div><dt>评分方式</dt><dd>自动评分</dd></div></dl>
        </aside>
      </div>
    </div>
  );
}
