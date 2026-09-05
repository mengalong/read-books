"use client";

import { ArrowLeft, Ban, Check, Save, Search } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { EmptyState, ErrorState, StatusBadge } from "@/components/ui";
import { ApiError, getBook, getMaterials, getPlotEvents, updatePlotEvent } from "@/lib/api";
import { resourceTypeLabel } from "@/lib/format";
import type { BookDetail, PlotEvent, PlotEventList, ResourceMaterial } from "@/lib/types";

const PAGE_SIZE = 50;

type EventDraft = Pick<PlotEvent, "title" | "summary" | "cause" | "action" | "result" | "future_impact">;

export default function PlotEventsPage() {
  const params = useParams<{ bookId: string }>();
  const bookId = params.bookId;
  const [book, setBook] = useState<BookDetail | null>(null);
  const [materials, setMaterials] = useState<ResourceMaterial[]>([]);
  const [events, setEvents] = useState<PlotEventList | null>(null);
  const [materialId, setMaterialId] = useState("");
  const [reviewStatus, setReviewStatus] = useState<"" | PlotEvent["review_status"]>("");
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [drafts, setDrafts] = useState<Record<string, EventDraft>>({});
  const [savingId, setSavingId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const initialMaterialId = new URLSearchParams(window.location.search).get("material_id") || "";
    if (initialMaterialId) setMaterialId(initialMaterialId);
    Promise.all([getBook(bookId), getMaterials(bookId)])
      .then(([bookData, materialData]) => { setBook(bookData); setMaterials(materialData); })
      .catch((reason: unknown) => setError(reason instanceof ApiError ? reason.message : "资源加载失败"));
  }, [bookId]);

  const loadEvents = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const result = await getPlotEvents(bookId, {
        ...(materialId ? { materialId } : {}),
        ...(reviewStatus ? { reviewStatus } : {}),
        ...(search ? { search } : {}),
        page,
        pageSize: PAGE_SIZE,
      });
      setEvents(result);
      setDrafts(Object.fromEntries(result.items.map((event) => [event.id, {
        title: event.title,
        summary: event.summary,
        cause: event.cause,
        action: event.action,
        result: event.result,
        future_impact: event.future_impact,
      }])));
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "剧情事件加载失败");
    } finally {
      setLoading(false);
    }
  }, [bookId, materialId, page, reviewStatus, search]);

  useEffect(() => { void loadEvents(); }, [loadEvents]);

  function updateDraft(eventId: string, field: keyof EventDraft, value: string) {
    setDrafts((current) => ({ ...current, [eventId]: { ...current[eventId], [field]: value } }));
  }

  async function saveEvent(event: PlotEvent, status?: PlotEvent["review_status"]) {
    const draft = drafts[event.id];
    if (!draft) return;
    setSavingId(event.id);
    setError("");
    try {
      await updatePlotEvent(bookId, event.id, { ...draft, ...(status ? { review_status: status } : {}) });
      await loadEvents();
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "剧情事件保存失败");
    } finally {
      setSavingId(null);
    }
  }

  if (!book && loading) return <div className="page-wrap"><div className="loading-state">正在打开剧情梗概……</div></div>;
  if (!book) return <div className="page-wrap"><ErrorState message={error || "未找到这个资源"} /></div>;

  const totalPages = Math.max(1, Math.ceil((events?.total || 0) / PAGE_SIZE));
  return <div className="page-wrap">
    <Link className="back-link" href={`/books/${book.id}`}><ArrowLeft size={14} />返回《{book.title}》</Link>
    {error && <div className="toast-error">{error}</div>}
    <header className="page-header">
      <div><div className="eyebrow">Plot summary review</div><h1 className="page-title">剧情事件校对</h1><p className="page-description">{resourceTypeLabel(book.resource_type)} · {book.title} · 确认后的事件才会用于剧情理解题。</p></div>
    </header>
    <section className="content-panel plot-event-filter-panel">
      <div className="filter-row"><label className="search-field"><Search size={15} /><input onChange={(event) => setSearchInput(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") { setPage(1); setSearch(searchInput.trim()); } }} placeholder="搜索标题、摘要或行动" value={searchInput} /></label><select aria-label="剧情资料" onChange={(event) => { setMaterialId(event.target.value); setPage(1); }} value={materialId}><option value="">全部剧情资料</option>{materials.filter((item) => item.material_type === "plot_summary").map((item) => <option key={item.id} value={item.id}>{item.file_name}</option>)}</select><select aria-label="校对状态" onChange={(event) => { setReviewStatus(event.target.value as "" | PlotEvent["review_status"]); setPage(1); }} value={reviewStatus}><option value="">全部状态</option><option value="pending">待校对</option><option value="confirmed">已确认</option><option value="rejected">已排除</option></select></div>
      <div className="plot-event-counts"><span>共 {events?.total || 0} 条事件</span><span>待校对 {events?.pending_count || 0}</span><span>已确认 {events?.confirmed_count || 0}</span></div>
    </section>
    {loading ? <div className="loading-state">正在读取剧情事件……</div> : !events?.items.length ? <EmptyState title="没有匹配的剧情事件" detail="调整筛选条件，或先在资源主页上传 plot_summary.v1 JSON。" /> : <section className="plot-event-list">{events.items.map((event) => <PlotEventCard drafts={drafts} event={event} saving={savingId === event.id} onSave={saveEvent} onUpdateDraft={updateDraft} key={event.id} />)}</section>}
    {events && totalPages > 1 && <div className="pagination"><button aria-label="上一页" className="button button-secondary" disabled={page <= 1} onClick={() => setPage((current) => current - 1)} type="button">上一页</button><span>第 {page} / {totalPages} 页</span><button aria-label="下一页" className="button button-secondary" disabled={page >= totalPages} onClick={() => setPage((current) => current + 1)} type="button">下一页</button></div>}
  </div>;
}

function PlotEventCard({ event, drafts, saving, onSave, onUpdateDraft }: { event: PlotEvent; drafts: Record<string, EventDraft>; saving: boolean; onSave: (event: PlotEvent, status?: PlotEvent["review_status"]) => Promise<void>; onUpdateDraft: (eventId: string, field: keyof EventDraft, value: string) => void }) {
  const draft = drafts[event.id];
  if (!draft) return null;
  return <article className="plot-event-card"><header><div><span className="question-number">{event.event_id}</span><h2>{event.title || event.summary.slice(0, 60)}</h2></div><StatusBadge status={event.review_status} /></header><div className="plot-event-meta"><span>{event.season_number ? `第 ${event.season_number} 季` : ""}{event.episode_number ? ` · 第 ${event.episode_number} 集` : ""}</span><span>{event.confidence}</span><span>{event.question_usable === "true" ? "可用于出题" : "需要复核"}</span></div><form onSubmit={(formEvent) => { formEvent.preventDefault(); void onSave(event); }}><label>标题<input onChange={(inputEvent) => onUpdateDraft(event.id, "title", inputEvent.target.value)} value={draft.title} /></label><label>剧情概述<textarea onChange={(inputEvent) => onUpdateDraft(event.id, "summary", inputEvent.target.value)} rows={2} value={draft.summary} /></label><div className="form-grid"><label>前因<textarea onChange={(inputEvent) => onUpdateDraft(event.id, "cause", inputEvent.target.value)} rows={2} value={draft.cause} /></label><label>行动<textarea onChange={(inputEvent) => onUpdateDraft(event.id, "action", inputEvent.target.value)} rows={2} value={draft.action} /></label><label>结果<textarea onChange={(inputEvent) => onUpdateDraft(event.id, "result", inputEvent.target.value)} rows={2} value={draft.result} /></label><label>后续影响<textarea onChange={(inputEvent) => onUpdateDraft(event.id, "future_impact", inputEvent.target.value)} rows={2} value={draft.future_impact} /></label></div><div className="plot-event-actions"><button className="button button-primary" disabled={saving || !draft.summary.trim()} type="submit"><Save size={14} />保存调整</button><button className="button button-secondary" disabled={saving} onClick={() => void onSave(event, "confirmed")} type="button"><Check size={14} />确认使用</button><button className="button button-secondary" disabled={saving} onClick={() => void onSave(event, "rejected")} type="button"><Ban size={14} />排除事件</button></div></form></article>;
}
