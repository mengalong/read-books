"use client";

import { BookPlus, Search, Sparkles } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";

import { BookCard, EmptyState, ErrorState } from "@/components/ui";
import { ApiError, getBooks } from "@/lib/api";
import type { BookSummary, ReadingStatus, ShelfStatus } from "@/lib/types";

const filters: { label: string; value?: ReadingStatus }[] = [
  { label: "全部" },
  { label: "复习中", value: "reviewing" },
  { label: "已读", value: "finished" },
  { label: "在读", value: "reading" },
];

export default function BookshelfPage() {
  const [books, setBooks] = useState<BookSummary[]>([]);
  const [searchInput, setSearchInput] = useState("");
  const [appliedSearch, setAppliedSearch] = useState("");
  const [activeStatus, setActiveStatus] = useState<ReadingStatus | undefined>();
  const [shelfStatus, setShelfStatus] = useState<ShelfStatus>("active");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getBooks(appliedSearch, activeStatus, shelfStatus)
      .then((items) => { if (!cancelled) { setBooks(items); setError(""); } })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof ApiError ? reason.message : "内容库加载失败");
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [appliedSearch, activeStatus, shelfStatus]);

  function handleSearchSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAppliedSearch(searchInput.trim());
  }

  const metrics = useMemo(() => {
    const readyResources = books.filter((book) => book.stats.completed_pdf_count > 0 || book.model_knowledge_supported === true).length;
    const tested = books.filter((book) => book.stats.quiz_count > 0);
    const average = tested.length
      ? Math.round(tested.reduce((sum, book) => sum + (book.stats.average_score || 0), 0) / tested.length)
      : null;
    return { readyResources, average };
  }, [books]);

  return (
    <div className="page-wrap">
      <header className="page-header">
        <div>
          <div className="eyebrow">Personal reading review</div>
          <h1 className="page-title">我的内容库</h1>
          <p className="page-description">把读过、看过的内容变成一次次主动回忆。选择一个资源，开始一套约 15 分钟的复习测试。</p>
        </div>
        <Link className="button button-primary" href="/books/new"><BookPlus size={16} />添加资源</Link>
      </header>

      <section className="metrics-grid" aria-label="内容库概览">
        <div className="metric"><div className="metric-label">资源总数</div><div className="metric-value">{books.length}<span className="metric-detail">条</span></div></div>
        <div className="metric"><div className="metric-label">可出题资源</div><div className="metric-value">{metrics.readyResources}<span className="metric-detail">条</span></div></div>
        <div className="metric"><div className="metric-label">平均得分率</div><div className="metric-value">{metrics.average === null ? "—" : metrics.average}<span className="metric-detail">%</span></div></div>
      </section>

      <div className="books-toolbar">
        <div className="section-title" style={{ marginBottom: 0 }}><h2>全部资源</h2><span>{books.length} 条</span></div>
        <form className="search-box" onSubmit={handleSearchSubmit}>
          <Search size={15} />
          <input aria-label="搜索资源名称或主创" value={searchInput} onChange={(event) => setSearchInput(event.target.value)} placeholder="搜索资源名称或主创，按回车搜索" />
        </form>
      </div>
      <div className="tag-row" style={{ marginBottom: 19, marginTop: 0 }}>
        {filters.map((filter) => <button className={`tag ${shelfStatus === "active" && activeStatus === filter.value ? "active-filter" : ""}`} key={filter.label} onClick={() => { setShelfStatus("active"); setActiveStatus(filter.value); }} type="button">{filter.label}</button>)}
        <button className={`tag ${shelfStatus === "unlisted" ? "active-filter unlisted-filter" : ""}`} onClick={() => { setShelfStatus("unlisted"); setActiveStatus(undefined); }} type="button">已下架</button>
      </div>

      {loading && <div className="loading-state">正在整理内容库……</div>}
      {!loading && error && <ErrorState message={error} />}
      {!loading && !error && books.length === 0 && <EmptyState title={shelfStatus === "unlisted" ? "没有已下架的资源" : "内容库还是空的"} detail={shelfStatus === "unlisted" ? "下架的资源会保留资料和历史记录，并显示在这里。" : "添加一个资源并上传 PDF，或者等待模型真实内容检查通过，开始建立属于你的复习资料。"} action={shelfStatus === "active" ? <Link className="button button-primary" href="/books/new"><BookPlus size={16} />添加第一条资源</Link> : undefined} />}
      {!loading && !error && books.length > 0 && <div className="book-grid">{books.map((book) => <BookCard book={book} key={book.id} />)}</div>}

      <div style={{ alignItems: "center", color: "var(--muted)", display: "flex", fontSize: 12, gap: 7, marginTop: 32 }}><Sparkles size={14} color="var(--yellow)" />开发阶段使用模拟出题与评分；没有 PDF 时需启用真实模型进行资源知识兜底。</div>
    </div>
  );
}
