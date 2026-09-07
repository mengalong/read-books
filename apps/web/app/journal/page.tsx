"use client";

import {
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Check,
  Film,
  Lightbulb,
  ListTodo,
  NotebookPen,
  RefreshCw,
  Save,
  Sparkles,
  Trash2,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { ErrorState } from "@/components/ui";
import {
  ApiError,
  createJournalCapture,
  deleteJournalCapture,
  getJournalDay,
  organizeJournalDay,
  updateJournalDay,
  updateJournalItem,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { JournalCaptureType, JournalDay, JournalItem, JournalItemType } from "@/lib/types";

const captureTypes: { value: JournalCaptureType; label: string; icon: typeof NotebookPen }[] = [
  { value: "note", label: "记录", icon: NotebookPen },
  { value: "todo", label: "待办", icon: ListTodo },
  { value: "idea", label: "灵感", icon: Lightbulb },
  { value: "want_read", label: "想读", icon: BookOpen },
  { value: "want_watch", label: "想看", icon: Film },
];

const itemLabels: Record<JournalItemType, string> = {
  todo: "待办",
  idea: "灵感",
  want_read: "想读",
  want_watch: "想看",
};

const itemIcons: Record<JournalItemType, typeof ListTodo> = {
  todo: ListTodo,
  idea: Lightbulb,
  want_read: BookOpen,
  want_watch: Film,
};

function todayString() {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}

function shiftDate(value: string, amount: number) {
  const current = new Date(`${value}T12:00:00Z`);
  current.setUTCDate(current.getUTCDate() + amount);
  return current.toISOString().slice(0, 10);
}

function dayLabel(value: string) {
  const current = new Date(`${value}T12:00:00`);
  return current.toLocaleDateString("zh-CN", { weekday: "long", month: "long", day: "numeric" });
}

function statusLabel(item: JournalItem) {
  if (item.status === "needs_review") return "待确认";
  if (item.item_type === "todo") return item.status === "done" ? "已完成" : item.status === "cancelled" ? "已取消" : "进行中";
  if (item.status === "archived" || item.status === "dismissed") return "已归档";
  if (item.status === "added") return "已采纳";
  if (item.status === "completed") return "已完成";
  return "收件箱";
}

function nextStatus(item: JournalItem) {
  if (item.item_type === "todo") return item.status === "done" ? "open" : "done";
  if (item.status === "needs_review") return "inbox";
  if (item.item_type === "idea") return item.status === "inbox" ? "archived" : "inbox";
  if (item.status === "inbox") return "added";
  if (item.status === "added") return "completed";
  return "inbox";
}

export default function JournalPage() {
  const [localDate, setLocalDate] = useState(todayString);
  const [day, setDay] = useState<JournalDay | null>(null);
  const [content, setContent] = useState("");
  const [captureType, setCaptureType] = useState<JournalCaptureType>("note");
  const [journalText, setJournalText] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [organizing, setOrganizing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const loadDay = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const result = await getJournalDay(localDate);
      setDay(result);
      setJournalText(result.journal_text);
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "日常记录加载失败");
    } finally {
      setLoading(false);
    }
  }, [localDate]);

  useEffect(() => { void loadDay(); }, [loadDay]);

  useEffect(() => {
    if (!day || !["pending", "processing"].includes(day.organization_status)) return;
    const timer = window.setInterval(() => {
      getJournalDay(localDate).then((result) => {
        setDay(result);
        setJournalText(result.journal_text);
        if (result.organization_status === "completed" || result.organization_status === "failed") setOrganizing(false);
      }).catch(() => undefined);
    }, 1_200);
    return () => window.clearInterval(timer);
  }, [day, localDate]);

  const captureCount = day?.captures.length || 0;
  const pendingItems = useMemo(() => day?.items.filter((item) => item.status === "needs_review").length || 0, [day]);

  async function handleCapture(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!content.trim()) return;
    setSubmitting(true);
    setError("");
    try {
      await createJournalCapture({ content: content.trim(), capture_type: captureType, local_date: localDate });
      setContent("");
      setNotice("已记下");
      await loadDay();
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "快速记录保存失败");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleOrganize() {
    setOrganizing(true);
    setNotice("");
    setError("");
    try {
      const result = await organizeJournalDay(localDate);
      setDay(result);
      setJournalText(result.journal_text);
      setNotice("整理任务已开始");
    } catch (reason: unknown) {
      setOrganizing(false);
      setError(reason instanceof ApiError ? reason.message : "日常整理启动失败");
    }
  }

  async function handleSaveJournal(confirm = false) {
    setSaving(true);
    setError("");
    try {
      const result = await updateJournalDay(localDate, { journal_text: journalText, ...(confirm ? { confirm: !day?.confirmed_at } : {}) });
      setDay(result);
      setJournalText(result.journal_text);
      setNotice(confirm ? (result.confirmed_at ? "日记已确认" : "已取消确认") : "日记草稿已保存");
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "日记保存失败");
    } finally {
      setSaving(false);
    }
  }

  async function handleDeleteCapture(captureId: string) {
    if (!window.confirm("确定删除这条原始记录吗？归集项不会自动删除。")) return;
    try {
      await deleteJournalCapture(captureId);
      await loadDay();
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "原始记录删除失败");
    }
  }

  async function handleItemStatus(item: JournalItem) {
    try {
      const updated = await updateJournalItem(item.id, { status: nextStatus(item) });
      setDay((current) => current ? { ...current, items: current.items.map((entry) => entry.id === updated.id ? updated : entry) } : current);
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "项目状态更新失败");
    }
  }

  if (loading && !day) return <div className="page-wrap"><div className="loading-state">正在打开今天的记录……</div></div>;

  return (
    <div className="page-wrap journal-page">
      <header className="page-header journal-header">
        <div>
          <div className="eyebrow">Daily capture</div>
          <h1 className="page-title">日常记录</h1>
          <p className="page-description">把随时冒出来的事情先记下来，晚些时候再整理成日记和可追踪的项目。</p>
        </div>
        <div className="journal-date-nav">
          <button aria-label="前一天" className="button button-quiet" onClick={() => setLocalDate((value) => shiftDate(value, -1))} title="前一天" type="button"><ArrowLeft size={16} /></button>
          <span><strong>{dayLabel(localDate)}</strong><small>{localDate}</small></span>
          <button aria-label="后一天" className="button button-quiet" onClick={() => setLocalDate((value) => shiftDate(value, 1))} title="后一天"><ArrowRight size={16} /></button>
        </div>
      </header>

      {error && <ErrorState message={error} />}
      {notice && <div className="toast-success">{notice}</div>}

      <section className="journal-capture-panel form-panel">
        <div className="section-title"><h2>快速记录</h2><span>{captureCount} 条</span></div>
        <form onSubmit={(event) => void handleCapture(event)}>
          <textarea aria-label="快速记录内容" className="journal-capture-input" onChange={(event) => setContent(event.target.value)} placeholder="现在想到什么？先记下来……" rows={3} value={content} />
          <div className="journal-capture-actions">
            <div className="journal-type-picker" aria-label="记录类型">
              {captureTypes.map(({ value, label, icon: Icon }) => <button className={`journal-type-button ${captureType === value ? "active" : ""}`} key={value} onClick={() => setCaptureType(value)} type="button"><Icon size={15} />{label}</button>)}
            </div>
            <button className="button button-primary" disabled={submitting || !content.trim()} type="submit"><NotebookPen size={16} />{submitting ? "保存中……" : "记下"}</button>
          </div>
        </form>
      </section>

      <div className="journal-grid">
        <section className="journal-section form-panel">
          <div className="section-title"><h2>原始记录</h2><span>按时间排列</span></div>
          {day?.captures.length ? <div className="journal-capture-list">{day.captures.map((capture) => {
            const type = captureTypes.find((item) => item.value === capture.capture_type) || captureTypes[0];
            const Icon = type.icon;
            return <article className="journal-capture-row" key={capture.id}><div className={`journal-capture-icon type-${capture.capture_type}`}><Icon size={15} /></div><div className="journal-capture-copy"><div className="journal-capture-meta"><span>{type.label}</span><time>{formatDateTime(capture.captured_at)}</time></div><p>{capture.content}</p></div><button aria-label="删除原始记录" className="button button-quiet danger-action" onClick={() => void handleDeleteCapture(capture.id)} title="删除原始记录" type="button"><Trash2 size={14} /></button></article>;
          })}</div> : <div className="journal-empty">还没有记录。先写下一句话，今天的时间线就从这里开始。</div>}
        </section>

        <section className="journal-section form-panel">
          <div className="section-title"><h2>今日整理</h2><span>{day?.organization_status === "completed" ? "已完成" : day?.organization_status === "processing" || day?.organization_status === "pending" ? "整理中" : "尚未整理"}</span></div>
          <textarea aria-label="今日生成的日记" className="journal-draft" onChange={(event) => setJournalText(event.target.value)} placeholder="整理后会在这里生成日记草稿。" rows={12} value={journalText} />
          <div className="journal-draft-footer"><span>{day?.confirmed_at ? <><Check size={14} />已确认</> : "草稿可继续编辑"}</span><div className="table-actions"><button className="button button-secondary" disabled={saving || !journalText.trim()} onClick={() => void handleSaveJournal()} type="button"><Save size={15} />保存</button><button className="button button-primary" disabled={saving || !captureCount} onClick={() => void handleOrganize()} type="button"><Sparkles size={15} />{organizing ? "整理中……" : "重新整理"}</button>{day?.journal_text && <button aria-label={day.confirmed_at ? "取消确认" : "确认日记"} className="button button-quiet" disabled={saving} onClick={() => void handleSaveJournal(true)} title={day.confirmed_at ? "取消确认" : "确认日记"} type="button"><Check size={15} /></button>}</div></div>
          {day?.organization_error && <div className="journal-error">{day.organization_error}</div>}
        </section>
      </div>

      <section className="journal-section form-panel journal-items-panel">
        <div className="section-title"><h2>从今天归集</h2><span>{pendingItems ? `${pendingItems} 项待确认` : `${day?.items.length || 0} 项`}</span><Link className="section-link" href="/journal/items">查看全部清单 →</Link></div>
        {day?.items.length ? <div className="journal-item-grid">{day.items.map((item) => { const Icon = itemIcons[item.item_type]; return <article className={`journal-item-card ${item.status === "done" ? "is-done" : ""}`} key={item.id}><div className="journal-item-card-head"><span className={`journal-item-icon item-${item.item_type}`}><Icon size={15} /></span><span className="journal-item-label">{itemLabels[item.item_type]}</span><span className={`journal-item-status ${item.status}`}>{statusLabel(item)}</span></div><strong>{item.title}</strong>{item.description && <p>{item.description}</p>}<button className="button button-quiet journal-item-action" onClick={() => void handleItemStatus(item)} type="button">{item.item_type === "todo" && item.status !== "done" ? "标记完成" : item.status === "done" ? "重新打开" : item.status === "needs_review" ? "确认归集" : item.status === "archived" || item.status === "completed" ? "重新打开" : "推进状态"}</button></article>; })}</div> : <div className="journal-empty">整理今天后，待办、灵感和想读/想看项目会显示在这里。</div>}
      </section>

      <div className="journal-footer-note"><RefreshCw size={14} />原始记录始终保留，模型只生成可编辑草稿和可追踪项目。</div>
    </div>
  );
}
