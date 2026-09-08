"use client";

import { Archive, Pencil, RefreshCw, Save, Trash2, X } from "lucide-react";
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

function statusText(item: JournalItem) {
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

function actionText(item: JournalItem) {
  if (item.review_status === "pending") return "确认";
  if (item.review_status === "cancelled" || item.review_status === "deleted") return "恢复";
  if (item.item_type === "todo" && item.review_status === "confirmed") return "完成";
  if (item.item_type === "todo" && item.review_status === "completed") return "重新打开";
  return "取消";
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
      const updated = await updateJournalItem(item.id, { review_status: nextReviewStatus(item) });
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
      const updated = await updateJournalItem(editingId, { item_type: editingType, title: editingTitle.trim(), description: editingDescription.trim() });
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
        <div><div className="eyebrow">Long-lived items</div><h1 className="page-title">日常清单</h1><p className="page-description">所有从快速记录中沉淀的项目，都在这张表里继续追踪。</p></div>
        <Link className="button button-secondary" href="/journal"><RefreshCw size={15} />回到今天</Link>
      </header>
      {error && <ErrorState message={error} />}
      <div className="journal-list-filters">{filters.map((filter) => <button className={`tag ${activeFilter === filter.value ? "active-filter" : ""}`} key={filter.label} onClick={() => setActiveFilter(filter.value)} type="button">{filter.label}</button>)}</div>
      {loading ? <div className="loading-state">正在整理日常清单……</div> : items.length === 0 ? <div className="journal-empty journal-empty-large"><Archive size={22} /><strong>还没有归集项目</strong><span>在今天的页面记录待办、灵感或想读/想看的内容，整理后会出现在这里。</span></div> : <div className="journal-unified-table-wrap"><table className="journal-unified-table"><thead><tr><th>类型</th><th>内容</th><th>原因 / 说明</th><th>提及时间</th><th>状态</th><th>操作</th></tr></thead><tbody>{items.map((item) => {
        const busy = workingId === item.id;
        if (editingId === item.id) return <tr className="journal-table-edit-row" key={item.id}><td colSpan={6}><div className="journal-table-edit-fields"><select aria-label="修改项目分类" onChange={(event) => setEditingType(event.target.value as JournalItemType)} value={editingType}>{filters.filter((filter): filter is { value: JournalItemType; label: string } => Boolean(filter.value)).map((filter) => <option key={filter.value} value={filter.value}>{filter.label}</option>)}</select><input aria-label="编辑归集标题" onChange={(event) => setEditingTitle(event.target.value)} value={editingTitle} /><textarea aria-label="编辑归集说明" onChange={(event) => setEditingDescription(event.target.value)} rows={2} value={editingDescription} /><div className="journal-table-edit-actions"><button className="button button-primary" disabled={busy || !editingTitle.trim()} onClick={() => void saveEdit()} type="button"><Save size={14} />保存</button><button className="button button-quiet" onClick={cancelEdit} type="button"><X size={14} />取消</button></div></div></td></tr>;
        const mediaTitle = item.metadata.media_title ? String(item.metadata.media_title) : item.title;
        const reason = item.metadata.reason ? String(item.metadata.reason) : item.description || "-";
        const mentionedAt = item.metadata.mentioned_at ? new Date(String(item.metadata.mentioned_at)).toLocaleDateString("zh-CN") : "-";
        return <tr key={item.id}><td><select aria-label="修改项目类型" className="journal-table-type-select" onChange={(event) => void updateJournalItem(item.id, { item_type: event.target.value as JournalItemType }).then((updated) => setItems((current) => current.map((entry) => entry.id === updated.id ? updated : entry))).catch((reason: unknown) => setError(reason instanceof ApiError ? reason.message : "项目类型修改失败"))} value={item.item_type}>{filters.filter((filter): filter is { value: JournalItemType; label: string } => Boolean(filter.value)).map((filter) => <option key={filter.value} value={filter.value}>{filter.label}</option>)}</select></td><td><strong>{mediaTitle}</strong><small>{item.source_capture_ids.length} 条来源记录</small></td><td>{reason}</td><td>{mentionedAt}</td><td><span className={`journal-item-status ${item.review_status}`}>{statusText(item)}</span></td><td><div className="journal-table-actions"><button className="button button-quiet" disabled={busy} onClick={() => startEdit(item)} title="编辑项目" type="button"><Pencil size={14} /></button><button className="button button-quiet" disabled={busy} onClick={() => void changeStatus(item)} type="button">{actionText(item)}</button><button className="button button-quiet danger-action" disabled={busy} onClick={() => void removeItem(item)} title="删除项目" type="button"><Trash2 size={14} /></button></div></td></tr>;
      })}</tbody></table></div>}
    </div>
  );
}
