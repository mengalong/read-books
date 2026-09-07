"use client";

import { Archive, BookOpen, Check, Film, Lightbulb, ListTodo, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { ErrorState } from "@/components/ui";
import { ApiError, getJournalItems, updateJournalItem } from "@/lib/api";
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
  if (item.item_type === "todo") return item.status === "done" ? "已完成" : "进行中";
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

export default function JournalItemsPage() {
  const [activeFilter, setActiveFilter] = useState<JournalItemType | undefined>();
  const [items, setItems] = useState<JournalItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [workingId, setWorkingId] = useState("");
  const [error, setError] = useState("");

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

  return (
    <div className="page-wrap journal-page">
      <header className="page-header journal-header">
        <div><div className="eyebrow">Long-lived items</div><h1 className="page-title">日常清单</h1><p className="page-description">从快速记录里归集出的任务、灵感和想读/想看项目，会在这里持续追踪。</p></div>
        <Link className="button button-secondary" href="/journal"><RefreshCw size={15} />回到今天</Link>
      </header>
      {error && <ErrorState message={error} />}
      <div className="journal-list-filters">{filters.map((filter) => <button className={`tag ${activeFilter === filter.value ? "active-filter" : ""}`} key={filter.label} onClick={() => setActiveFilter(filter.value)} type="button">{filter.label}</button>)}</div>
      {loading ? <div className="loading-state">正在整理日常清单……</div> : items.length === 0 ? <div className="journal-empty journal-empty-large"><Archive size={22} /><strong>还没有归集项目</strong><span>在今天的页面记录待办、灵感或想读/想看的内容，整理后会出现在这里。</span></div> : <div className="journal-all-items">{items.map((item) => { const Icon = icons[item.item_type]; const busy = workingId === item.id; return <article className={`journal-all-item ${item.status === "done" ? "is-done" : ""}`} key={item.id}><span className={`journal-item-icon item-${item.item_type}`}><Icon size={16} /></span><div className="journal-all-item-copy"><div className="journal-capture-meta"><span>{labels[item.item_type]}</span><span className={`journal-item-status ${item.status}`}>{statusText(item)}</span>{item.confidence !== null && item.status === "needs_review" && <span>模型置信度 {Math.round(item.confidence * 100)}%</span>}</div><strong>{item.title}</strong>{item.description && <p>{item.description}</p>}<small>{item.source_capture_ids.length} 条来源记录 · 更新于 {new Date(item.updated_at).toLocaleDateString("zh-CN")}</small></div><button className="button button-secondary" disabled={busy} onClick={() => void changeStatus(item)} type="button">{item.item_type === "todo" && item.status !== "done" ? <><Check size={14} />完成</> : item.status === "needs_review" ? "确认" : item.status === "done" ? "重新打开" : item.status === "archived" || item.status === "completed" ? "重新打开" : "推进"}</button></article>; })}</div>}
    </div>
  );
}
