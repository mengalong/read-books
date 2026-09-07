"use client";

import { Archive, BookOpen, Check, Film, Lightbulb, ListTodo, Pencil, RefreshCw, Save, Trash2, X } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { ErrorState } from "@/components/ui";
import { ApiError, deleteJournalItem, getJournalItems, updateJournalItem } from "@/lib/api";
import type { JournalItem, JournalItemType } from "@/lib/types";

const filters: { value?: JournalItemType; label: string }[] = [
  { label: "全部" },
  { value: "todo", label: "待办" },
  { value: "idea", label: "灵感" },
  { value: "want_read", label: "想读" },
  { value: "want_watch", label: "想看" },
];

const labels: Record<JournalItemType, string> = { todo: "待办", idea: "灵感", want_read: "想读", want_watch: "想看" };
const icons: Record<JournalItemType, typeof ListTodo> = { todo: ListTodo, idea: Lightbulb, want_read: BookOpen, want_watch: Film };

function statusText(item: JournalItem) {
  if (item.status === "needs_review") return "待确认";
  if (item.status === "dismissed") return "已取消";
  if (item.item_type === "todo") return item.status === "done" ? "已完成" : "已确认";
  if (item.status === "archived" || item.status === "dismissed") return "已归档";
  if (item.status === "added") return "已采纳";
  if (item.status === "completed") return "已完成";
  return "已确认";
}

function nextStatus(item: JournalItem) {
  if (item.status === "needs_review") return item.item_type === "todo" ? "open" : "inbox";
  if (item.status === "dismissed" || item.status === "archived" || item.status === "completed") return item.item_type === "todo" ? "open" : "inbox";
  if (item.item_type === "todo") return item.status === "done" ? "open" : "done";
  return item.status;
}

export default function JournalItemsPage() {
  const [activeFilter, setActiveFilter] = useState<JournalItemType | undefined>();
  const [items, setItems] = useState<JournalItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [workingId, setWorkingId] = useState("");
  const [error, setError] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState("");
  const [editingDescription, setEditingDescription] = useState("");
  const [editingType, setEditingType] = useState<JournalItemType>("todo");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setItems(await getJournalItems(activeFilter));
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "日常清单加载失败");
    } finally {
      setLoading(false);
    }
  }, [activeFilter]);

  useEffect(() => { void load(); }, [load]);

  async function changeStatus(item: JournalItem) {
    setWorkingId(item.id);
    try {
      const updated = await updateJournalItem(item.id, { status: nextStatus(item) });
      setItems((current) => current.map((entry) => entry.id === updated.id ? updated : entry));
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "项目状态更新失败");
    } finally {
      setWorkingId("");
    }
  }

  function startEdit(item: JournalItem) {
    setEditingId(item.id);
    setEditingTitle(item.title);
    setEditingDescription(item.description);
    setEditingType(item.item_type);
    setError("");
  }

  function cancelEdit() {
    setEditingId(null);
    setEditingTitle("");
    setEditingDescription("");
  }

  async function saveEdit() {
    if (!editingId || !editingTitle.trim()) return;
    setWorkingId(editingId);
    try {
      const updated = await updateJournalItem(editingId, {
        item_type: editingType,
        title: editingTitle.trim(),
        description: editingDescription.trim(),
      });
      setItems((current) => current.map((entry) => entry.id === updated.id ? updated : entry));
      cancelEdit();
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "项目更新失败");
    } finally {
      setWorkingId("");
    }
  }

  async function removeItem(item: JournalItem) {
    if (!window.confirm(`确定删除“${item.title}”吗？来源记录不会删除。`)) return;
    setWorkingId(item.id);
    try {
      await deleteJournalItem(item.id);
      setItems((current) => current.filter((entry) => entry.id !== item.id));
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "项目删除失败");
    } finally {
      setWorkingId("");
    }
  }

  return (
    <div className="page-wrap journal-page">
      <header className="page-header journal-header">
        <div><div className="eyebrow">Long-lived items</div><h1 className="page-title">日常清单</h1><p className="page-description">从快速记录里归集出的任务、灵感和想读/想看项目，会在这里持续追踪。</p></div>
        <Link className="button button-secondary" href="/journal"><RefreshCw size={15} />回到今天</Link>
      </header>
      {error && <ErrorState message={error} />}
      <div className="journal-list-filters">{filters.map((filter) => <button className={`tag ${activeFilter === filter.value ? "active-filter" : ""}`} key={filter.label} onClick={() => setActiveFilter(filter.value)} type="button">{filter.label}</button>)}</div>
      {!loading && items.some((item) => item.item_type === "want_read" || item.item_type === "want_watch") && <section className="journal-media-table-panel form-panel"><div className="section-title"><h2>媒体候选结构化视图</h2><span>可继续沉淀为表格</span></div><div className="journal-media-table-wrap"><table className="journal-media-table"><thead><tr><th>类型</th><th>书名 / 片名</th><th>原因</th><th>提及时间</th><th>状态</th></tr></thead><tbody>{items.filter((item) => item.item_type === "want_read" || item.item_type === "want_watch").map((item) => <tr key={`media-${item.id}`}><td>{labels[item.item_type]}</td><td><strong>{String(item.metadata.media_title || item.title)}</strong>{Boolean(item.metadata.creator) && <small>{String(item.metadata.creator)}</small>}</td><td>{String(item.metadata.reason || item.description || "-")}</td><td>{item.metadata.mentioned_at ? new Date(String(item.metadata.mentioned_at)).toLocaleDateString("zh-CN") : "-"}</td><td><span className={`journal-item-status ${item.status}`}>{statusText(item)}</span></td></tr>)}</tbody></table></div></section>}
      {loading ? <div className="loading-state">正在整理日常清单……</div> : items.length === 0 ? <div className="journal-empty journal-empty-large"><Archive size={22} /><strong>还没有归集项目</strong><span>在今天的页面记录待办、灵感或想读/想看的内容，整理后会出现在这里。</span></div> : <div className="journal-all-items">{items.map((item) => { const Icon = icons[item.item_type]; const busy = workingId === item.id; if (editingId === item.id) return <article className="journal-all-item journal-all-item-editing" key={item.id}><span className={`journal-item-icon item-${editingType}`}><Icon size={16} /></span><div className="journal-all-item-copy"><div className="journal-edit-actions"><select aria-label="修改项目分类" onChange={(event) => setEditingType(event.target.value as JournalItemType)} value={editingType}>{filters.filter((filter): filter is { value: JournalItemType; label: string } => Boolean(filter.value)).map((filter) => <option key={filter.value} value={filter.value}>{filter.label}</option>)}</select></div><input aria-label="编辑归集标题" className="journal-item-edit-title" onChange={(event) => setEditingTitle(event.target.value)} value={editingTitle} /><textarea aria-label="编辑归集说明" className="journal-item-edit-description" onChange={(event) => setEditingDescription(event.target.value)} rows={3} value={editingDescription} /><div className="journal-edit-actions"><button className="button button-primary" disabled={busy || !editingTitle.trim()} onClick={() => void saveEdit()} type="button"><Save size={14} />保存</button><button aria-label="取消项目编辑" className="button button-quiet" onClick={cancelEdit} title="取消编辑" type="button"><X size={15} /></button></div></div></article>; return <article className={`journal-all-item ${item.status === "done" ? "is-done" : ""}`} key={item.id}><span className={`journal-item-icon item-${item.item_type}`}><Icon size={16} /></span><div className="journal-all-item-copy"><div className="journal-capture-meta"><span>{labels[item.item_type]}</span><span className={`journal-item-status ${item.status}`}>{statusText(item)}</span>{item.confidence !== null && item.status === "needs_review" && <span>模型置信度 {Math.round(item.confidence * 100)}%</span>}</div><strong>{item.title}</strong>{item.description && <p>{item.description}</p>}<small>{item.source_capture_ids.length} 条来源记录 · 更新于 {new Date(item.updated_at).toLocaleDateString("zh-CN")}</small></div><div className="journal-item-actions"><button aria-label="编辑归集项目" className="button button-quiet" disabled={busy} onClick={() => startEdit(item)} title="编辑归集项目" type="button"><Pencil size={14} /></button><button className="button button-secondary" disabled={busy} onClick={() => void changeStatus(item)} type="button">{item.item_type === "todo" && item.status !== "done" ? <><Check size={14} />完成</> : item.status === "needs_review" ? "确认" : item.status === "done" ? "重新打开" : item.status === "archived" || item.status === "completed" ? "重新打开" : "推进"}</button><button aria-label="删除归集项目" className="button button-quiet danger-action" disabled={busy} onClick={() => void removeItem(item)} title="删除归集项目" type="button"><Trash2 size={14} /></button></div></article>; })}</div>}
    </div>
  );
}
