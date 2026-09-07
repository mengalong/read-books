"use client";

import {
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Check,
  Copy,
  Film,
  Lightbulb,
  ListTodo,
  NotebookPen,
  Pencil,
  RefreshCw,
  Save,
  Sparkles,
  Trash2,
  X,
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
  updateJournalCapture,
  updateJournalDay,
  updateJournalItem,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { JournalCaptureType, JournalDay, JournalItem, JournalItemType, JournalWritingStyle } from "@/lib/types";

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

const writingStyles: { value: JournalWritingStyle; label: string; description: string }[] = [
  { value: "natural", label: "自然纪实", description: "清楚、克制地记录当天" },
  { value: "lu_xun", label: "鲁迅式冷峻讽刺", description: "冷静观察，带一点锋利的讽刺" },
  { value: "hu_shi", label: "胡适式平实自省", description: "平实清晰，保留思考和自省" },
  { value: "minimal", label: "清简随笔", description: "短句和留白为主" },
];

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
  const [writingStyle, setWritingStyle] = useState<JournalWritingStyle>("natural");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [organizing, setOrganizing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [editingCaptureId, setEditingCaptureId] = useState<string | null>(null);
  const [editingContent, setEditingContent] = useState("");
  const [editingType, setEditingType] = useState<JournalCaptureType>("note");
  const [editingDate, setEditingDate] = useState(localDate);

  const loadDay = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const result = await getJournalDay(localDate);
      setDay(result);
      setJournalText(result.journal_text);
      setWritingStyle(result.writing_style);
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
        setWritingStyle(result.writing_style);
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
      const result = await organizeJournalDay(localDate, writingStyle);
      setDay(result);
      setJournalText(result.journal_text);
      setWritingStyle(result.writing_style);
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
      const result = await updateJournalDay(localDate, { journal_text: journalText, writing_style: writingStyle, ...(confirm ? { confirm: !day?.confirmed_at } : {}) });
      setDay(result);
      setJournalText(result.journal_text);
      setWritingStyle(result.writing_style);
      setNotice(confirm ? (result.confirmed_at ? "日记已确认" : "已取消确认") : "日记草稿已保存");
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "日记保存失败");
    } finally {
      setSaving(false);
    }
  }

  async function handleCopyJournal() {
    if (!journalText.trim()) return;
    try {
      await navigator.clipboard.writeText(journalText);
      setNotice("Markdown 日记已复制");
    } catch {
      setError("浏览器拒绝了复制，请手动选中文本复制");
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

  function startEditingCapture(capture: JournalDay["captures"][number]) {
    setEditingCaptureId(capture.id);
    setEditingContent(capture.content);
    setEditingType(capture.capture_type);
    setEditingDate(capture.local_date);
    setError("");
  }

  function cancelEditingCapture() {
    setEditingCaptureId(null);
    setEditingContent("");
    setEditingType("note");
    setEditingDate(localDate);
  }

  async function handleUpdateCapture() {
    if (!editingCaptureId || !editingContent.trim()) return;
    setSubmitting(true);
    setError("");
    try {
      await updateJournalCapture(editingCaptureId, {
        content: editingContent.trim(),
        capture_type: editingType,
        local_date: editingDate,
      });
      cancelEditingCapture();
      setNotice("原始记录已更新");
      await loadDay();
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "原始记录更新失败");
    } finally {
      setSubmitting(false);
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
          <label className="journal-date-picker"><span>选择日期</span><input aria-label="选择日期" onChange={(event) => event.target.value && setLocalDate(event.target.value)} type="date" value={localDate} /></label>
          <button aria-label="后一天" className="button button-quiet" onClick={() => setLocalDate((value) => shiftDate(value, 1))} title="后一天"><ArrowRight size={16} /></button>
        </div>
      </header>

      {error && <ErrorState message={error} />}
      {notice && <div className="toast-success">{notice}</div>}

      <section className="journal-capture-panel form-panel">
        <div className="section-title"><h2>快速记录</h2><span>{captureCount} 条</span></div>
        <form onSubmit={(event) => void handleCapture(event)}>
          <textarea aria-label="快速记录内容" className="journal-capture-input" onChange={(event) => setContent(event.target.value)} placeholder="现在想到什么？先记下来……" rows={6} value={content} />
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
            if (editingCaptureId === capture.id) {
              return <article className="journal-capture-row journal-capture-row-editing" key={capture.id}>
                <div className={`journal-capture-icon type-${editingType}`}><Icon size={15} /></div>
                <div className="journal-capture-copy journal-capture-edit-copy">
                  <textarea aria-label="编辑原始记录" className="journal-edit-input" onChange={(event) => setEditingContent(event.target.value)} rows={4} value={editingContent} />
                  <div className="journal-edit-actions"><select aria-label="修改记录类型" onChange={(event) => setEditingType(event.target.value as JournalCaptureType)} value={editingType}>{captureTypes.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select><input aria-label="修改记录日期" onChange={(event) => setEditingDate(event.target.value)} type="date" value={editingDate} /><button className="button button-primary" disabled={submitting || !editingContent.trim() || !editingDate} onClick={() => void handleUpdateCapture()} type="button"><Save size={14} />保存</button><button aria-label="取消编辑" className="button button-quiet" onClick={cancelEditingCapture} title="取消编辑" type="button"><X size={15} /></button></div>
                </div>
              </article>;
            }
            return <article className="journal-capture-row" key={capture.id}><div className={`journal-capture-icon type-${capture.capture_type}`}><Icon size={15} /></div><div className="journal-capture-copy"><div className="journal-capture-meta"><span>{type.label}</span><time>{formatDateTime(capture.captured_at)}</time></div><p>{capture.content}</p></div><div className="journal-capture-row-actions"><button aria-label="编辑原始记录" className="button button-quiet" onClick={() => startEditingCapture(capture)} title="编辑原始记录" type="button"><Pencil size={14} /></button><button aria-label="删除原始记录" className="button button-quiet danger-action" onClick={() => void handleDeleteCapture(capture.id)} title="删除原始记录" type="button"><Trash2 size={14} /></button></div></article>;
          })}</div> : <div className="journal-empty">还没有记录。先写下一句话，今天的时间线就从这里开始。</div>}
        </section>

        <section className="journal-section form-panel">
          <div className="section-title"><h2>今日整理</h2><span>{day?.organization_status === "completed" ? "已完成" : day?.organization_status === "processing" || day?.organization_status === "pending" ? "整理中" : "尚未整理"}</span></div>
          <div className="journal-draft-hint">Markdown 草稿，可直接复制到支持 Markdown 的编辑器发布</div><textarea aria-label="今日生成的日记" className="journal-draft" onChange={(event) => setJournalText(event.target.value)} placeholder="整理后会在这里生成结构化 Markdown 日记草稿。" rows={16} value={journalText} />
          <div className="journal-draft-footer"><div className="journal-draft-meta"><span>{day?.confirmed_at ? <><Check size={14} />已确认</> : "草稿可继续编辑"}</span><label className="journal-style-picker"><span>写作风格</span><select aria-label="日记写作风格" onChange={(event) => setWritingStyle(event.target.value as JournalWritingStyle)} value={writingStyle}>{writingStyles.map((style) => <option key={style.value} value={style.value}>{style.label}</option>)}</select></label></div><div className="table-actions"><button className="button button-secondary" disabled={saving || !journalText.trim()} onClick={() => void handleSaveJournal()} type="button"><Save size={15} />保存</button><button className="button button-secondary" disabled={!journalText.trim()} onClick={() => void handleCopyJournal()} type="button"><Copy size={15} />复制 Markdown</button><button className="button button-primary" disabled={saving || !captureCount} onClick={() => void handleOrganize()} type="button"><Sparkles size={15} />{organizing ? "整理中……" : "重新整理"}</button>{day?.journal_text && <button aria-label={day.confirmed_at ? "取消确认" : "确认日记"} className="button button-quiet" disabled={saving} onClick={() => void handleSaveJournal(true)} title={day.confirmed_at ? "取消确认" : "确认日记"} type="button"><Check size={15} /></button>}</div></div>
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
