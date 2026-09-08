"use client";

import {
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Copy,
  Film,
  History,
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
import { createElement, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ErrorState } from "@/components/ui";
import {
  ApiError,
  createJournalCapture,
  deleteJournalCapture,
  getJournalDay,
  getJournalDayVersions,
  organizeJournalDay,
  restoreJournalDayVersion,
  updateJournalCapture,
  updateJournalDay,
  updateJournalItem,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { JournalCaptureType, JournalDay, JournalDayVersion, JournalItem, JournalItemType, JournalWritingStyle } from "@/lib/types";

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
  if (item.review_status === "pending") return "待确认";
  if (item.review_status === "completed") return "已完成";
  if (item.review_status === "cancelled") return "已取消";
  if (item.review_status === "deleted") return "已删除";
  return "已确认";
}

function nextReviewStatus(item: JournalItem): JournalItem["review_status"] {
  if (item.review_status === "pending") return "confirmed";
  if (item.review_status === "cancelled" || item.review_status === "deleted") return "confirmed";
  if (item.item_type === "todo") return item.review_status === "completed" ? "confirmed" : "completed";
  return "cancelled";
}

function primaryItemAction(item: JournalItem) {
  if (item.review_status === "pending") return "确认";
  if (item.review_status === "cancelled" || item.review_status === "deleted") return "恢复";
  if (item.item_type === "todo" && item.review_status === "completed") return "重新打开";
  if (item.item_type === "todo" && item.review_status === "confirmed") return "完成";
  return null;
}

function markdownInline(text: string, keyPrefix: string) {
  return text.split(/(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*)/g).map((part, index) => {
    const key = `${keyPrefix}-${index}`;
    if (part.startsWith("`") && part.endsWith("`")) return <code key={key}>{part.slice(1, -1)}</code>;
    if (part.startsWith("**") && part.endsWith("**")) return <strong key={key}>{part.slice(2, -2)}</strong>;
    if (part.startsWith("*") && part.endsWith("*")) return <em key={key}>{part.slice(1, -1)}</em>;
    return <span key={key}>{part}</span>;
  });
}

function MarkdownPreview({ value }: { value: string }) {
  return <div className="journal-markdown-preview">{value.split(/\r?\n/).map((line, index) => {
    const key = `markdown-${index}`;
    if (!line.trim()) return <div className="markdown-spacer" key={key} />;
    if (/^---+$/.test(line.trim())) return <hr key={key} />;
    const heading = line.match(/^(#{1,6})\s+(.+)$/);
    if (heading) return createElement(`h${heading[1].length}`, { key }, markdownInline(heading[2], key));
    const unordered = line.match(/^\s*[-*]\s+(.+)$/);
    if (unordered) return <div className="markdown-list-item" key={key}><span>•</span><span>{markdownInline(unordered[1], key)}</span></div>;
    const ordered = line.match(/^\s*(\d+)\.\s+(.+)$/);
    if (ordered) return <div className="markdown-list-item" key={key}><span>{ordered[1]}.</span><span>{markdownInline(ordered[2], key)}</span></div>;
    if (/^>\s?/.test(line)) return <blockquote key={key}>{markdownInline(line.replace(/^>\s?/, ""), key)}</blockquote>;
    return <p key={key}>{markdownInline(line, key)}</p>;
  })}</div>;
}

function DayItemCard({
  item,
  onStatus,
  onTypeChange,
  onReject,
}: {
  item: JournalItem;
  onStatus: (item: JournalItem) => void;
  onTypeChange: (item: JournalItem, itemType: JournalItemType) => void;
  onReject: (item: JournalItem) => void;
}) {
  const Icon = itemIcons[item.item_type];
  const rejected = item.review_status === "cancelled" || item.review_status === "deleted";
  const primaryAction = primaryItemAction(item);
  return <article className={`journal-item-card ${item.review_status === "completed" ? "is-done" : ""}`}>
    <div className="journal-item-card-head"><span className={`journal-item-icon item-${item.item_type}`}><Icon size={15} /></span><select aria-label={`修改${itemLabels[item.item_type]}归集类型`} className="journal-item-type-select" onChange={(event) => onTypeChange(item, event.target.value as JournalItemType)} value={item.item_type}>{Object.entries(itemLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select><span className={`journal-item-status ${item.review_status}`}>{statusLabel(item)}</span></div>
    <strong>{item.title}</strong>{item.description && <p>{item.description}</p>}
    <div className="journal-item-card-actions">{primaryAction && <button className="button button-quiet journal-item-action" onClick={() => onStatus(item)} type="button">{primaryAction}</button>}{!rejected && item.review_status !== "completed" && <button className="button button-quiet journal-item-action journal-item-reject" onClick={() => onReject(item)} type="button">取消归集</button>}</div>
  </article>;
}

export default function JournalPage() {
  const [localDate, setLocalDate] = useState(todayString);
  const [day, setDay] = useState<JournalDay | null>(null);
  const [content, setContent] = useState("");
  const [captureType, setCaptureType] = useState<JournalCaptureType>("note");
  const [journalText, setJournalText] = useState("");
  const [writingStyle, setWritingStyle] = useState<JournalWritingStyle>("natural");
  const [previewMode, setPreviewMode] = useState<"edit" | "preview">("edit");
  const [autoSaving, setAutoSaving] = useState(false);
  const [lastAutosavedAt, setLastAutosavedAt] = useState<string | null>(null);
  const [versions, setVersions] = useState<JournalDayVersion[]>([]);
  const editorRevision = useRef(0);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [organizing, setOrganizing] = useState(false);
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
      setLastAutosavedAt(result.updated_at);
      setVersions(await getJournalDayVersions(localDate));
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "日常记录加载失败");
    } finally {
      setLoading(false);
    }
  }, [localDate]);

  useEffect(() => { void loadDay(); }, [loadDay]);

  useEffect(() => {
    const requestedDate = new URLSearchParams(window.location.search).get("date");
    if (requestedDate && /^\d{4}-\d{2}-\d{2}$/.test(requestedDate)) setLocalDate(requestedDate);
  }, []);

  useEffect(() => {
    if (window.location.hash === "#quick-capture") {
      window.setTimeout(() => document.querySelector<HTMLTextAreaElement>("[aria-label='快速记录内容']")?.focus(), 0);
    }
  }, []);

  useEffect(() => {
    const handleShortcut = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "j") {
        event.preventDefault();
        document.querySelector<HTMLTextAreaElement>("[aria-label='快速记录内容']")?.focus();
      }
    };
    window.addEventListener("keydown", handleShortcut);
    return () => window.removeEventListener("keydown", handleShortcut);
  }, []);

  useEffect(() => {
    if (!day || loading || (journalText === day.journal_text && writingStyle === day.writing_style)) return;
    const timer = window.setTimeout(() => {
      const revisionAtSave = editorRevision.current;
      setAutoSaving(true);
      updateJournalDay(localDate, { journal_text: journalText, writing_style: writingStyle })
        .then(async (result) => {
          if (revisionAtSave !== editorRevision.current) return;
          setDay(result);
          setJournalText(result.journal_text);
          setWritingStyle(result.writing_style);
          setLastAutosavedAt(result.updated_at);
          setVersions(await getJournalDayVersions(localDate));
          setError("");
        })
        .catch((reason: unknown) => setError(reason instanceof ApiError ? reason.message : "草稿自动保存失败"))
        .finally(() => setAutoSaving(false));
    }, 700);
    return () => window.clearTimeout(timer);
  }, [day, journalText, localDate, loading, writingStyle]);

  useEffect(() => {
    if (!day || !["pending", "processing"].includes(day.organization_status)) return;
    const timer = window.setInterval(() => {
      getJournalDay(localDate).then((result) => {
        setDay(result);
        setJournalText(result.journal_text);
        setWritingStyle(result.writing_style);
        setLastAutosavedAt(result.updated_at);
        if (result.organization_status === "completed" || result.organization_status === "failed") setOrganizing(false);
      }).catch(() => undefined);
    }, 1_200);
    return () => window.clearInterval(timer);
  }, [day, localDate]);

  const captureCount = day?.captures.length || 0;
  const pendingItems = useMemo(() => day?.items.filter((item) => item.review_status === "pending").length || 0, [day]);

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
      setLastAutosavedAt(result.updated_at);
      setNotice("整理任务已开始");
    } catch (reason: unknown) {
      setOrganizing(false);
      setError(reason instanceof ApiError ? reason.message : "日常整理启动失败");
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

  async function handleRestoreVersion(version: JournalDayVersion) {
    if (!window.confirm(`恢复第 ${version.version_number} 版日记？当前内容会先保存为一个新版本。`)) return;
    try {
      const result = await restoreJournalDayVersion(localDate, version.version_number);
      setDay(result);
      setJournalText(result.journal_text);
      setWritingStyle(result.writing_style);
      setLastAutosavedAt(result.updated_at);
      setVersions(await getJournalDayVersions(localDate));
      setPreviewMode("edit");
      setNotice(`已恢复第 ${version.version_number} 版日记`);
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "日记版本恢复失败");
    }
  }

  async function updateReflection(payload: { model_consent?: boolean; mood_score?: number | null; energy_score?: number | null; meaning_score?: number | null }) {
    try {
      const result = await updateJournalDay(localDate, payload);
      setDay(result);
      setLastAutosavedAt(result.updated_at);
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "日常偏好保存失败");
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
      const updated = await updateJournalItem(item.id, { review_status: nextReviewStatus(item) });
      setDay((current) => current ? { ...current, items: current.items.map((entry) => entry.id === updated.id ? updated : entry) } : current);
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "项目状态更新失败");
    }
  }

  async function handleItemTypeChange(item: JournalItem, itemType: JournalItemType) {
    if (item.item_type === itemType) return;
    try {
      const updated = await updateJournalItem(item.id, { item_type: itemType });
      setDay((current) => current ? { ...current, items: current.items.map((entry) => entry.id === updated.id ? updated : entry) } : current);
      setNotice("归集类型已修改");
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "归集类型修改失败");
    }
  }

  async function handleRejectItem(item: JournalItem) {
    try {
      const updated = await updateJournalItem(item.id, { review_status: "cancelled" });
      setDay((current) => current ? { ...current, items: current.items.map((entry) => entry.id === updated.id ? updated : entry) } : current);
      setNotice("已打回这条归集，不会删除原始记录");
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "归集打回失败");
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
          <textarea aria-label="快速记录内容" className="journal-capture-input" id="quick-capture" onChange={(event) => setContent(event.target.value)} placeholder="现在想到什么？先记下来……" rows={6} value={content} />
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
          <div className="section-title journal-draft-heading"><div><h2>今日整理</h2><span>{day?.organization_status === "completed" ? "已完成" : day?.organization_status === "processing" || day?.organization_status === "pending" ? "整理中" : "尚未整理"}</span></div><button className="button button-primary journal-organize-button" disabled={organizing || !captureCount} onClick={() => void handleOrganize()} type="button"><Sparkles size={15} />{organizing ? "整理中" : "整理今天"}</button></div>
          <div className="journal-draft-hint">Markdown 草稿，可直接复制到支持 Markdown 的编辑器发布</div>
          <div className="journal-editor-toolbar"><div className="journal-editor-tabs" role="tablist" aria-label="日记查看模式"><button aria-selected={previewMode === "edit"} className={previewMode === "edit" ? "active" : ""} onClick={() => setPreviewMode("edit")} role="tab" type="button">编辑</button><button aria-selected={previewMode === "preview"} className={previewMode === "preview" ? "active" : ""} onClick={() => setPreviewMode("preview")} role="tab" type="button">预览</button></div><button aria-label="复制 Markdown 日记" className="journal-copy-button" disabled={!journalText.trim()} onClick={() => void handleCopyJournal()} title="复制 Markdown 日记" type="button"><Copy size={16} /></button></div>
          {previewMode === "edit" ? <textarea aria-label="今日生成的日记" className="journal-draft" onChange={(event) => { editorRevision.current += 1; setJournalText(event.target.value); }} placeholder="整理后会在这里生成结构化 Markdown 日记草稿。" rows={16} value={journalText} /> : <MarkdownPreview value={journalText || "还没有日记草稿，先整理今天的记录。"} />}
          <div className="journal-autosave-meta"><span>{autoSaving ? "正在自动保存……" : lastAutosavedAt ? `已自动保存 ${formatDateTime(lastAutosavedAt)}` : "编辑后会自动保存"}</span><label className="journal-style-picker"><span>写作风格</span><select aria-label="日记写作风格" onChange={(event) => { editorRevision.current += 1; setWritingStyle(event.target.value as JournalWritingStyle); }} value={writingStyle}>{writingStyles.map((style) => <option key={style.value} value={style.value}>{style.label}</option>)}</select></label></div>
          <div className="journal-reflection-row"><label className="journal-consent-control"><input checked={day?.model_consent ?? true} onChange={(event) => void updateReflection({ model_consent: event.target.checked })} type="checkbox" /><span>允许今天的原始记录发送给模型整理</span></label><div className="journal-score-controls"><label>心情 <select aria-label="心情评分" onChange={(event) => void updateReflection({ mood_score: event.target.value ? Number(event.target.value) : null })} value={day?.mood_score ?? ""}><option value="">未评分</option>{Array.from({ length: 10 }, (_, index) => <option key={index + 1} value={index + 1}>{index + 1} / 10</option>)}</select></label><label>精力 <select aria-label="精力评分" onChange={(event) => void updateReflection({ energy_score: event.target.value ? Number(event.target.value) : null })} value={day?.energy_score ?? ""}><option value="">未评分</option>{Array.from({ length: 10 }, (_, index) => <option key={index + 1} value={index + 1}>{index + 1} / 10</option>)}</select></label><label>意义 <select aria-label="意义评分" onChange={(event) => void updateReflection({ meaning_score: event.target.value ? Number(event.target.value) : null })} value={day?.meaning_score ?? ""}><option value="">未评分</option>{Array.from({ length: 10 }, (_, index) => <option key={index + 1} value={index + 1}>{index + 1} / 10</option>)}</select></label></div></div>
          {versions.length > 0 && <details className="journal-version-history"><summary><History size={14} />历史版本（{versions.length}）</summary><div className="journal-version-list">{versions.map((version) => <div className="journal-version-row" key={version.id}><span><strong>第 {version.version_number} 版</strong><small>{version.source} · {formatDateTime(version.created_at)}</small></span><button className="button button-quiet" onClick={() => void handleRestoreVersion(version)} type="button">恢复</button></div>)}</div></details>}
          {day?.organization_error && <div className="journal-error">{day.organization_error}</div>}
        </section>
      </div>

      <section className="journal-section form-panel journal-items-panel">
        <div className="section-title"><h2>从今天归集</h2><span>{pendingItems ? `${pendingItems} 项待确认` : `${day?.items.length || 0} 项`}</span><Link className="section-link" href="/journal/items">查看全部清单 →</Link></div>
        {day?.items.length ? <div className="journal-item-grid">{day.items.map((item) => { const Icon = itemIcons[item.item_type]; return <article className={`journal-item-card ${item.status === "done" ? "is-done" : ""}`} key={item.id}><div className="journal-item-card-head"><span className={`journal-item-icon item-${item.item_type}`}><Icon size={15} /></span><select aria-label={`修改${itemLabels[item.item_type]}归集类型`} className="journal-item-type-select" onChange={(event) => void handleItemTypeChange(item, event.target.value as JournalItemType)} value={item.item_type}>{Object.entries(itemLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select><span className={`journal-item-status ${item.status}`}>{statusLabel(item)}</span></div><strong>{item.title}</strong>{item.description && <p>{item.description}</p>}<div className="journal-item-card-actions">{item.status === "needs_review" ? <><button className="button button-quiet journal-item-action" onClick={() => void handleItemStatus(item)} type="button">确认</button><button className="button button-quiet journal-item-action journal-item-reject" onClick={() => void handleRejectItem(item)} type="button">打回</button></> : <button className="button button-quiet journal-item-action" onClick={() => void handleItemStatus(item)} type="button">{item.item_type === "todo" && item.status !== "done" ? "标记完成" : item.status === "done" ? "重新打开" : item.status === "dismissed" ? "恢复" : item.status === "archived" || item.status === "completed" ? "重新打开" : "推进状态"}</button>}</div></article>; })}</div> : <div className="journal-empty">整理今天后，待办、灵感和想读/想看项目会显示在这里。</div>}
      </section>

      <div className="journal-footer-note"><RefreshCw size={14} />原始记录始终保留，模型只生成可编辑草稿和可追踪项目。</div>
    </div>
  );
}
