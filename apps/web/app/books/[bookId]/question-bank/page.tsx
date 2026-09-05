"use client";

import { ArrowLeft, Check, CheckCircle2, Edit3, LibraryBig, LoaderCircle, Search, X } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { ErrorState } from "@/components/ui";
import { ApiError, getBook, getQuestionBank, updateQuestionBankEntry } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { BookDetail, QuestionBankEntry } from "@/lib/types";

const questionTypeLabel = (value: QuestionBankEntry["question_type"]) => ({
  single: "单项选择题",
  multiple: "多项选择题",
  short: "问答题",
}[value]);

export default function QuestionBankPage() {
  const params = useParams<{ bookId: string }>();
  const [book, setBook] = useState<BookDetail | null>(null);
  const [entries, setEntries] = useState<QuestionBankEntry[]>([]);
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [unusedOnly, setUnusedOnly] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [total, setTotal] = useState(0);
  const [unusedCount, setUnusedCount] = useState(0);

  async function refresh(nextSearch = search, nextUnusedOnly = unusedOnly) {
    try {
      const result = await getQuestionBank(params.bookId, { search: nextSearch, unusedOnly: nextUnusedOnly, pageSize: 200 });
      setEntries(result.items);
      setTotal(result.total);
      setUnusedCount(result.unused_count);
      setError("");
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "题库加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    Promise.all([getBook(params.bookId), getQuestionBank(params.bookId, { pageSize: 200 })])
      .then(([bookData, result]) => {
        setBook(bookData);
        setEntries(result.items);
        setTotal(result.total);
        setUnusedCount(result.unused_count);
      })
      .catch((reason: unknown) => setError(reason instanceof ApiError ? reason.message : "题库加载失败"))
      .finally(() => setLoading(false));
  }, [params.bookId]);

  function submitSearch(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSearch(searchInput);
    setLoading(true);
    void refresh(searchInput, unusedOnly);
  }

  async function handleSaved(updated: QuestionBankEntry) {
    setEntries((current) => current.map((entry) => entry.id === updated.id ? updated : entry));
  }

  if (loading && !book) return <div className="page-wrap"><div className="loading-state">正在打开题库……</div></div>;
  if (!book) return <div className="page-wrap"><ErrorState message={error || "未找到这个资源"} /></div>;

  return <div className="page-wrap">
    <Link className="back-link" href={`/books/${book.id}`}><ArrowLeft size={14} />返回《{book.title}》</Link>
    {error && <div className="toast-error">{error}</div>}
    <header className="page-header question-bank-header">
      <div><div className="eyebrow"><LibraryBig size={13} />Question bank</div><h1 className="page-title">《{book.title}》题库</h1><p className="page-description">集中管理已经人工确认的题目。题库题目会优先复用未被其他试卷使用过的内容，并保留历史引用关系。</p></div>
      <div className="question-bank-summary"><strong>{total} 道题</strong><span>{unusedCount} 道尚未被试卷复用</span></div>
    </header>
    <form className="question-bank-toolbar" onSubmit={submitSearch}>
      <label className="search-field"><Search size={16} /><input aria-label="搜索题库" onChange={(event) => setSearchInput(event.target.value)} placeholder="搜索题干、知识点或事实" value={searchInput} /></label>
      <label className="question-bank-unused-filter"><input checked={unusedOnly} onChange={(event) => { const next = event.target.checked; setUnusedOnly(next); setLoading(true); void refresh(search, next); }} type="checkbox" />只看未使用</label>
      <button className="button button-secondary" type="submit"><Search size={15} />搜索</button>
    </form>
    {entries.length === 0 ? <div className="empty-state"><LibraryBig size={22} /><strong>{search || unusedOnly ? "没有符合条件的题库题目" : "题库还是空的"}</strong><span>可以从试卷编辑页逐题确认后加入题库。</span></div> : <section className="question-bank-list">{entries.map((entry) => <BankEntryCard entry={entry} key={entry.id} onSaved={handleSaved} />)}</section>}
  </div>;
}

function BankEntryCard({ entry, onSaved }: { entry: QuestionBankEntry; onSaved: (entry: QuestionBankEntry) => Promise<void> }) {
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [prompt, setPrompt] = useState(entry.prompt);
  const [explanation, setExplanation] = useState(entry.explanation);
  const [knowledgePoint, setKnowledgePoint] = useState(entry.knowledge_point);
  const [referenceAnswer, setReferenceAnswer] = useState(entry.reference_answer || "");
  const [options, setOptions] = useState(entry.options.map((option) => option.text));
  const [correctAnswers, setCorrectAnswers] = useState(entry.correct_answers);
  const [entryStatus, setEntryStatus] = useState(entry.status);

  function startEditing() {
    setPrompt(entry.prompt);
    setExplanation(entry.explanation);
    setKnowledgePoint(entry.knowledge_point);
    setReferenceAnswer(entry.reference_answer || "");
    setOptions(["A", "B", "C", "D"].map((id) => entry.options.find((option) => option.id === id)?.text || ""));
    setCorrectAnswers(entry.correct_answers);
    setEntryStatus(entry.status);
    setError("");
    setEditing(true);
  }

  async function save() {
    if (!prompt.trim() || !knowledgePoint.trim()) return;
    setSaving(true);
    setError("");
    try {
      const updated = await updateQuestionBankEntry(entry.book_id, entry.id, {
        prompt: prompt.trim(),
        knowledge_point: knowledgePoint.trim(),
        explanation: explanation.trim(),
        status: entryStatus,
        ...(entry.question_type === "short" ? { reference_answer: referenceAnswer.trim() } : {
          options: ["A", "B", "C", "D"].map((id, index) => ({ id, text: options[index].trim() })),
          correct_answers: correctAnswers,
        }),
      });
      await onSaved(updated);
      setEditing(false);
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "题库题目保存失败");
    } finally {
      setSaving(false);
    }
  }

  function toggleAnswer(id: string) {
    setCorrectAnswers((current) => entry.question_type === "single" ? [id] : current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);
  }

  return <article className={`question-bank-card ${entry.status}`}>
    <div className="question-bank-card-header"><div><span className="question-number">第 {entry.use_count > 0 ? `已复用 ${entry.use_count} 次` : "未使用"}</span><span className="question-type">{questionTypeLabel(entry.question_type)}</span></div><div className="question-bank-card-actions">{entry.status === "active" ? <span className="question-bank-active"><CheckCircle2 size={14} />可复用</span> : <span className="question-bank-disabled">已停用</span>}<button className="button button-quiet" onClick={() => setEditing((current) => !current)} title={editing ? "取消编辑" : "编辑题库题目"} type="button">{editing ? <X size={15} /> : <Edit3 size={15} />}</button></div></div>
    {error && <div className="toast-error">{error}</div>}
    {editing ? <div className="question-bank-edit-form">
      <label className="field field-full"><span>题干</span><textarea onChange={(event) => setPrompt(event.target.value)} value={prompt} /></label>
      <label className="field"><span>知识点</span><input onChange={(event) => setKnowledgePoint(event.target.value)} value={knowledgePoint} /></label>
      <label className="field"><span>题库状态</span><select onChange={(event) => setEntryStatus(event.target.value as QuestionBankEntry["status"])} value={entryStatus}><option value="active">启用，可被新试卷复用</option><option value="disabled">停用，仅保留历史记录</option></select></label>
      <label className="field"><span>解析</span><textarea onChange={(event) => setExplanation(event.target.value)} value={explanation} /></label>
      {entry.question_type === "short" ? <label className="field field-full"><span>参考答案</span><textarea onChange={(event) => setReferenceAnswer(event.target.value)} value={referenceAnswer} /></label> : <><div className="field field-full"><span>选项与答案</span><div className="question-bank-options-edit">{["A", "B", "C", "D"].map((id, index) => <label key={id}><span>{id}</span><input onChange={(event) => setOptions((current) => current.map((value, itemIndex) => itemIndex === index ? event.target.value : value))} value={options[index] || ""} /><input aria-label={`题库正确答案 ${id}`} checked={correctAnswers.includes(id)} onChange={() => toggleAnswer(id)} type={entry.question_type === "single" ? "radio" : "checkbox"} /></label>)}</div></div></>}
      <div className="question-bank-edit-actions"><button className="button button-secondary" onClick={() => setEditing(false)} type="button">取消</button><button className="button button-primary" disabled={saving} onClick={() => void save()} type="button">{saving ? <LoaderCircle className="spin" size={15} /> : <Check size={15} />}保存题库题目</button></div>
    </div> : <>
      <h2>{entry.prompt}</h2>
      {entry.options.length > 0 && <ol className="question-bank-options">{entry.options.map((option) => <li className={entry.correct_answers.includes(option.id) ? "correct" : ""} key={option.id}><span>{option.id}</span>{option.text}{entry.correct_answers.includes(option.id) && <Check size={13} />}</li>)}</ol>}
      <div className="question-bank-answer"><strong>正确答案</strong><span>{entry.question_type === "short" ? entry.reference_answer || "未设置" : entry.correct_answers.join("、")}</span></div>
      <div className="question-bank-meta"><span>知识点：{entry.knowledge_point}</span><span>来源依据：{entry.source_evidence.length} 条</span><span>创建于：{formatDateTime(entry.created_at)}</span></div>
      {entry.explanation && <p className="question-bank-explanation">解析：{entry.explanation}</p>}
      <details className="question-bank-usages"><summary>查看试卷引用（{entry.usages.length}）</summary>{entry.usages.length > 0 ? entry.usages.map((usage) => <div key={usage.id}><span>{usage.quiz_title}{usage.question_position ? ` · 第 ${usage.question_position} 题` : ""}</span><small>{formatDateTime(usage.used_at)}{usage.quiz_id ? "" : " · 试卷已删除"}</small></div>) : <p>这道题还没有被其他试卷使用。</p>}</details>
    </>}
  </article>;
}
