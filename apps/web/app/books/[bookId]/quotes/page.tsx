"use client";

import { ArrowLeft, Ban, Check, ChevronLeft, ChevronRight, Save, Search } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { EmptyState, ErrorState } from "@/components/ui";
import { ApiError, bulkReviewQuotes, getBook, getMaterials, getQuotes, updateQuote } from "@/lib/api";
import { formatMediaTime, resourceTypeLabel } from "@/lib/format";
import type { BookDetail, QuoteEntry, QuoteEntryList, ResourceMaterial } from "@/lib/types";

type QuoteDraft = { speaker: string; context: string };

const PAGE_SIZE = 50;

export default function QuoteReviewPage() {
  const params = useParams<{ bookId: string }>();
  const bookId = params.bookId;
  const [book, setBook] = useState<BookDetail | null>(null);
  const [materials, setMaterials] = useState<ResourceMaterial[]>([]);
  const [quotes, setQuotes] = useState<QuoteEntryList | null>(null);
  const [reviewStatus, setReviewStatus] = useState<"" | QuoteEntry["review_status"]>("pending");
  const [speaker, setSpeaker] = useState("");
  const [materialId, setMaterialId] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [drafts, setDrafts] = useState<Record<string, QuoteDraft>>({});
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [savingId, setSavingId] = useState<string | null>(null);
  const [bulkSaving, setBulkSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const initialMaterialId = new URLSearchParams(window.location.search).get("material_id") || "";
    if (initialMaterialId) setMaterialId(initialMaterialId);
    Promise.all([getBook(bookId), getMaterials(bookId)])
      .then(([bookData, materialData]) => { setBook(bookData); setMaterials(materialData); })
      .catch((reason: unknown) => setError(reason instanceof ApiError ? reason.message : "资源加载失败"));
  }, [bookId]);

  const loadQuotes = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const result = await getQuotes(bookId, {
        ...(materialId ? { material_id: materialId } : {}),
        ...(speaker ? { speaker } : {}),
        ...(reviewStatus ? { review_status: reviewStatus } : {}),
        ...(search ? { search } : {}),
        page,
        page_size: PAGE_SIZE,
      });
      setQuotes(result);
      setDrafts(Object.fromEntries(result.items.map((item) => [item.id, {
        speaker: item.speaker || "",
        context: item.context || "",
      }])));
      setSelected(new Set());
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "台词加载失败");
    } finally {
      setLoading(false);
    }
  }, [bookId, materialId, page, reviewStatus, search, speaker]);

  useEffect(() => { void loadQuotes(); }, [loadQuotes]);

  const totalPages = Math.max(1, Math.ceil((quotes?.total || 0) / PAGE_SIZE));
  const allVisibleSelected = Boolean(quotes?.items.length) && quotes!.items.every((item) => selected.has(item.id));

  function updateDraft(quoteId: string, key: keyof QuoteDraft, value: string) {
    setDrafts((current) => ({
      ...current,
      [quoteId]: { ...(current[quoteId] || { speaker: "", context: "" }), [key]: value },
    }));
  }

  function toggleSelected(quoteId: string) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(quoteId)) next.delete(quoteId);
      else next.add(quoteId);
      return next;
    });
  }

  function toggleAllVisible() {
    setSelected(allVisibleSelected ? new Set() : new Set(quotes?.items.map((item) => item.id) || []));
  }

  async function saveQuote(quote: QuoteEntry, status?: QuoteEntry["review_status"]) {
    const draft = drafts[quote.id] || { speaker: quote.speaker || "", context: quote.context || "" };
    setSavingId(quote.id);
    setError("");
    try {
      await updateQuote(bookId, quote.id, {
        speaker: draft.speaker.trim() || null,
        context: draft.context.trim() || null,
        ...(status ? { review_status: status } : {}),
      });
      await loadQuotes();
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "台词保存失败");
    } finally {
      setSavingId(null);
    }
  }

  async function toggleGeneration(quote: QuoteEntry) {
    setSavingId(quote.id);
    setError("");
    try {
      await updateQuote(bookId, quote.id, {
        enabled_for_generation: !quote.enabled_for_generation,
      });
      await loadQuotes();
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "出题状态更新失败");
    } finally {
      setSavingId(null);
    }
  }

  async function reviewSelected(action: "confirm" | "reject") {
    if (!selected.size) return;
    setBulkSaving(true);
    setError("");
    try {
      await bulkReviewQuotes(bookId, Array.from(selected), action);
      await loadQuotes();
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "批量校对失败");
    } finally {
      setBulkSaving(false);
    }
  }

  if (!book && !loading && error) return <div className="page-wrap"><ErrorState message={error} /></div>;

  return (
    <div className="page-wrap quote-review-page">
      <Link className="back-link" href={`/books/${bookId}`}><ArrowLeft size={14} />返回资源详情</Link>
      <header className="page-header">
        <div><h1 className="page-title">台词校对</h1><p className="page-description">{book ? `${resourceTypeLabel(book.resource_type)} · ${book.title}` : "正在读取资源"}</p></div>
        <div className="quote-review-summary"><span>待校对 <strong>{quotes?.pending_count || 0}</strong></span><span>已确认 <strong>{quotes?.confirmed_count || 0}</strong></span></div>
      </header>
      {error && <div className="toast-error">{error}</div>}

      <section className="quote-toolbar" aria-label="台词筛选">
        <form className="search-box quote-search" onSubmit={(event) => { event.preventDefault(); setPage(1); setSearch(searchInput.trim()); }}><Search size={15} /><input aria-label="搜索台词" onChange={(event) => setSearchInput(event.target.value)} placeholder="搜索台词内容" value={searchInput} /></form>
        <select aria-label="校对状态" onChange={(event) => { setPage(1); setReviewStatus(event.target.value as typeof reviewStatus); }} value={reviewStatus}><option value="">全部状态</option><option value="pending">待校对</option><option value="confirmed">已确认</option><option value="rejected">已排除</option></select>
        <select aria-label="角色" onChange={(event) => { setPage(1); setSpeaker(event.target.value); }} value={speaker}><option value="">全部角色</option>{quotes?.speakers.map((item) => <option key={item} value={item}>{item}</option>)}</select>
        {materials.length > 1 && <select aria-label="资料" onChange={(event) => { setPage(1); setMaterialId(event.target.value); }} value={materialId}><option value="">全部资料</option>{materials.map((item) => <option key={item.id} value={item.id}>{item.file_name}</option>)}</select>}
      </section>

      <section className="content-panel quote-review-panel">
        <div className="quote-bulk-bar">
          <label><input checked={allVisibleSelected} onChange={toggleAllVisible} type="checkbox" />选择本页</label>
          <span>已选 {selected.size} 条</span>
          <div className="quote-bulk-actions"><button className="button button-secondary" disabled={!selected.size || bulkSaving} onClick={() => void reviewSelected("reject")} type="button"><Ban size={15} />排除</button><button className="button button-primary" disabled={!selected.size || bulkSaving} onClick={() => void reviewSelected("confirm")} type="button"><Check size={15} />确认可用</button></div>
        </div>

        {loading ? <div className="loading-state">正在读取台词……</div> : quotes?.items.length ? <div className="quote-review-list">{quotes.items.map((quote) => {
          const draft = drafts[quote.id] || { speaker: quote.speaker || "", context: quote.context || "" };
          return <article className={`quote-review-row${selected.has(quote.id) ? " selected" : ""}`} key={quote.id}>
            <div className="quote-select"><input aria-label={`选择台词${quote.quote_text}`} checked={selected.has(quote.id)} onChange={() => toggleSelected(quote.id)} type="checkbox" /></div>
            <div className="quote-review-content">
              <div className="quote-review-heading"><blockquote>{quote.quote_text}</blockquote><QuoteStatus status={quote.review_status} /></div>
              <div className="quote-location">{quoteLocation(quote)} · {quote.material_file_name} · {speakerOriginLabel(quote.speaker_origin)}</div>
              <div className="quote-fields"><label><span>角色</span><input maxLength={120} onChange={(event) => updateDraft(quote.id, "speaker", event.target.value)} placeholder="未确认" value={draft.speaker} /></label><label><span>上下文</span><input maxLength={2000} onChange={(event) => updateDraft(quote.id, "context", event.target.value)} placeholder="未填写" value={draft.context} /></label></div>
            </div>
            <div className="quote-row-actions">
              <label className="quote-generation-toggle" title={quote.review_status === "confirmed" ? "控制这条台词是否进入出题候选" : "确认后才能用于出题"}><input checked={quote.enabled_for_generation} disabled={quote.review_status !== "confirmed" || savingId === quote.id} onChange={() => void toggleGeneration(quote)} type="checkbox" /><span>用于出题</span></label>
              <button aria-label="保存台词修改" className="button button-quiet" disabled={savingId === quote.id} onClick={() => void saveQuote(quote)} title="保存修改" type="button"><Save size={15} /></button>
              <button aria-label="排除台词" className="button button-quiet" disabled={savingId === quote.id} onClick={() => void saveQuote(quote, "rejected")} title="排除" type="button"><Ban size={15} /></button>
              <button aria-label="确认台词" className="button button-quiet" disabled={savingId === quote.id} onClick={() => void saveQuote(quote, "confirmed")} title="确认可用" type="button"><Check size={15} /></button>
            </div>
          </article>;
        })}</div> : <EmptyState title="没有符合条件的台词" detail={search || speaker || reviewStatus ? "调整筛选条件后重试。" : "上传并解析可信资料后，台词会出现在这里。"} />}

        {quotes && quotes.total > PAGE_SIZE && <div className="pagination quote-pagination"><button aria-label="上一页" className="button button-quiet" disabled={page <= 1} onClick={() => setPage((current) => current - 1)} title="上一页" type="button"><ChevronLeft size={16} /></button><span>{page} / {totalPages}</span><button aria-label="下一页" className="button button-quiet" disabled={page >= totalPages} onClick={() => setPage((current) => current + 1)} title="下一页" type="button"><ChevronRight size={16} /></button></div>}
      </section>
    </div>
  );
}

function quoteLocation(quote: QuoteEntry) {
  const time = formatMediaTime(quote.start_ms);
  return [
    quote.season_number ? `第 ${quote.season_number} 季` : null,
    quote.episode_number ? `第 ${quote.episode_number} 集` : null,
    quote.page_number ? `第 ${quote.page_number} 页` : null,
    time,
  ].filter(Boolean).join(" · ") || "未提供位置";
}

function speakerOriginLabel(origin: QuoteEntry["speaker_origin"]) {
  return {
    provided: "资料已标注角色",
    inferred: "模型推断角色",
    confirmed: "人工确认角色",
    unknown: "角色未确认",
  }[origin];
}

function QuoteStatus({ status }: { status: QuoteEntry["review_status"] }) {
  const labels = { pending: "待校对", confirmed: "已确认", rejected: "已排除" };
  const statusClass = status === "pending" ? "needs_review" : status;
  return <span className={`status-badge status-${statusClass}`}>{labels[status]}</span>;
}
