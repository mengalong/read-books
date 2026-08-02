"use client";

import { ArrowLeft, Check, CheckCircle2, Clock3, FileQuestion, LoaderCircle, Minus, Plus, Sparkles } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { ErrorState } from "@/components/ui";
import { ApiError, generateQuiz, getBook, getGenerationTask } from "@/lib/api";
import type { BookDetail, QuizGenerationTask } from "@/lib/types";

type CountKey = "single_count" | "multiple_count" | "short_count";

const questionTypes: { key: CountKey; label: string; detail: string; seconds: number }[] = [
  { key: "single_count", label: "单项选择题", detail: "概念边界与事实辨认", seconds: 45 },
  { key: "multiple_count", label: "多项选择题", detail: "多条信息的综合判断", seconds: 90 },
  { key: "short_count", label: "问答题", detail: "主动组织语言，由 AI 自动评分", seconds: 180 },
];

export default function NewQuizPage() {
  const params = useParams<{ bookId: string }>();
  const bookId = params.bookId;
  const [book, setBook] = useState<BookDetail | null>(null);
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
    getBook(bookId)
      .then(async (data) => {
        setBook(data);
        if (data.active_generation_task_id) {
          setGenerationTask(await getGenerationTask(data.active_generation_task_id));
        }
      })
      .catch((reason: unknown) => setError(reason instanceof ApiError ? reason.message : "书籍加载失败"))
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

  function adjust(key: CountKey, delta: number) {
    setCounts((current) => ({ ...current, [key]: Math.max(0, Math.min(15, current[key] + delta)) }));
  }

  async function handleGenerate() {
    setGenerating(true);
    setError("");
    try {
      const quiz = await generateQuiz(bookId, {
        duration_minutes: duration,
        difficulty,
        ...counts,
        ...(pageStart ? { page_start: Number(pageStart) } : {}),
        ...(pageEnd ? { page_end: Number(pageEnd) } : {}),
      });
      setGenerationTask(quiz);
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "测试生成失败");
    } finally {
      setGenerating(false);
    }
  }

  if (loading) return <div className="page-wrap"><div className="loading-state">正在准备测试设置……</div></div>;
  if (!book) return <div className="page-wrap"><ErrorState message={error || "未找到这本书"} /></div>;

  return (
    <div className="page-wrap">
      <Link className="back-link" href={`/books/${book.id}`}><ArrowLeft size={14} />返回《{book.title}》</Link>
      <header className="page-header" style={{ marginBottom: 25 }}>
        <div><div className="eyebrow">Create review</div><h1 className="page-title">生成一套复习测试</h1><p className="page-description">{book.title} · 已有 {book.stats.chunk_count} 个原文片段可用于出题</p></div>
      </header>
      {error && <div className="toast-error">{error}</div>}
      {generationTask && <section className={`generation-progress ${generationTask.status}`}>
        <div className="generation-progress-heading">
          <div>
            <span className="eyebrow">出题任务</span>
            <strong>{generationTask.status === "completed" ? "复习试卷已经准备好" : generationTask.status === "failed" ? "本次出题未完成" : generationTask.current_phase}</strong>
          </div>
          {generationTask.status === "completed" ? <CheckCircle2 size={21} /> : <LoaderCircle className={["pending", "processing"].includes(generationTask.status) ? "spin" : ""} size={21} />}
        </div>
        <div className="progress-track"><div className="progress-fill" style={{ width: `${generationTask.total_questions ? generationTask.completed_questions / generationTask.total_questions * 100 : 0}%` }} /></div>
        <div className="generation-progress-meta"><span>{generationTask.completed_questions} / {generationTask.total_questions} 道题</span><span>{generationTask.error_message || generationTask.current_phase}</span></div>
        {generationTask.status === "completed" && generationTask.quiz_id && <div className="generation-progress-actions"><Link className="button button-primary" href={`/quizzes/${generationTask.quiz_id}`}><CheckCircle2 size={15} />查看并开始复习</Link></div>}
      </section>}
      <div className="quiz-settings-grid">
        <section className="form-panel" style={{ maxWidth: "none" }}>
          <div className="section-title"><h2>题目组成</h2><span>预计 {estimatedMinutes} 分钟</span></div>
          <div className="count-list">
            {questionTypes.map((type) => <div className="count-row" key={type.key}>
              <div className="count-icon"><FileQuestion size={17} /></div>
              <div className="count-copy"><strong>{type.label}</strong><span>{type.detail}</span></div>
              <div className="stepper"><button aria-label={`减少${type.label}`} onClick={() => adjust(type.key, -1)} type="button"><Minus size={14} /></button><span>{counts[type.key]}</span><button aria-label={`增加${type.label}`} onClick={() => adjust(type.key, 1)} type="button"><Plus size={14} /></button></div>
            </div>)}
          </div>

          <div className="settings-block"><label>难度</label><div className="segmented-control">{[{ value: "easy", label: "基础" }, { value: "medium", label: "适中" }, { value: "hard", label: "深入" }].map((item) => <button className={difficulty === item.value ? "active" : ""} key={item.value} onClick={() => setDifficulty(item.value)} type="button">{difficulty === item.value && <Check size={13} />}{item.label}</button>)}</div></div>

          <div className="settings-block"><label htmlFor="duration"><Clock3 size={14} style={{ verticalAlign: "-3px", marginRight: 5 }} />目标时长</label><select id="duration" value={duration} onChange={(event) => setDuration(Number(event.target.value))}><option value={10}>10 分钟</option><option value={15}>15 分钟</option><option value={20}>20 分钟</option><option value={30}>30 分钟</option></select></div>

          <div className="settings-block"><label>页码范围（可选）</label><div className="page-range"><input min={1} onChange={(event) => setPageStart(event.target.value)} placeholder="起始页" type="number" value={pageStart} /><span>至</span><input min={1} onChange={(event) => setPageEnd(event.target.value)} placeholder="结束页" type="number" value={pageEnd} /></div></div>

          <div className="form-actions"><Link className="button button-secondary" href={`/books/${book.id}`}>返回书籍</Link><button className="button button-primary" disabled={generating || ["pending", "processing"].includes(generationTask?.status || "") || Object.values(counts).every((count) => count === 0)} onClick={() => void handleGenerate()} type="button"><Sparkles size={15} />{generating ? "正在创建任务……" : ["pending", "processing"].includes(generationTask?.status || "") ? "正在后台出题" : "生成复习试卷"}</button></div>
        </section>
        <aside className="quiz-settings-summary">
          <div className="eyebrow">本次测试</div>
          <strong>{Object.values(counts).reduce((sum, count) => sum + count, 0)} 道题</strong>
          <p>系统会优先选择近期没有考过的原文片段。每道题都附带页码依据，答题时默认折叠。</p>
          <dl><div><dt>目标时长</dt><dd>{duration} 分钟</dd></div><div><dt>预计用时</dt><dd>{estimatedMinutes} 分钟</dd></div><div><dt>评分方式</dt><dd>自动评分</dd></div></dl>
        </aside>
      </div>
    </div>
  );
}
