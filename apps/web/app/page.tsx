"use client";

import { BookPlus, Search, Sparkles } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { BookCard, EmptyState, ErrorState } from "@/components/ui";
import { ApiError, getBooks } from "@/lib/api";
import type { BookSummary, ReadingStatus } from "@/lib/types";

const filters: { label: string; value?: ReadingStatus }[] = [
  { label: "全部" },
  { label: "复习中", value: "reviewing" },
  { label: "已读", value: "finished" },
  { label: "在读", value: "reading" },
];

export default function BookshelfPage() {
  const [books, setBooks] = useState<BookSummary[]>([]);
  const [search, setSearch] = useState("");
  const [activeStatus, setActiveStatus] = useState<ReadingStatus | undefined>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getBooks(search, activeStatus)
      .then((items) => { if (!cancelled) { setBooks(items); setError(""); } })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof ApiError ? reason.message : "书架加载失败");
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [search, activeStatus]);

  const metrics = useMemo(() => {
    const sourceBooks = books.filter((book) => book.stats.completed_pdf_count > 0).length;
    const tested = books.filter((book) => book.stats.quiz_count > 0);
    const average = tested.length
      ? Math.round(tested.reduce((sum, book) => sum + (book.stats.average_score || 0), 0) / tested.length)
      : null;
    return { sourceBooks, average };
  }, [books]);

  return (
    <div className="page-wrap">
      <header className="page-header">
        <div>
          <div className="eyebrow">Personal reading review</div>
          <h1 className="page-title">我的书架</h1>
          <p className="page-description">把读过的内容变成一次次主动回忆。选择一本书，开始一套约 15 分钟的复习测试。</p>
        </div>
        <Link className="button button-primary" href="/books/new"><BookPlus size={16} />添加书籍</Link>
      </header>

      <section className="metrics-grid" aria-label="书架概览">
        <div className="metric"><div className="metric-label">书架总数</div><div className="metric-value">{books.length}<span className="metric-detail">本书</span></div></div>
        <div className="metric"><div className="metric-label">已建立原文</div><div className="metric-value">{metrics.sourceBooks}<span className="metric-detail">本书</span></div></div>
        <div className="metric"><div className="metric-label">平均得分率</div><div className="metric-value">{metrics.average === null ? "—" : metrics.average}<span className="metric-detail">%</span></div></div>
      </section>

      <div className="books-toolbar">
        <div className="section-title" style={{ marginBottom: 0 }}><h2>全部书籍</h2><span>{books.length} 本</span></div>
        <label className="search-box">
          <Search size={15} />
          <input aria-label="搜索书名或作者" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索书名或作者" />
        </label>
      </div>
      <div className="tag-row" style={{ marginBottom: 19, marginTop: 0 }}>
        {filters.map((filter) => <button className={`tag ${activeStatus === filter.value ? "active-filter" : ""}`} key={filter.label} onClick={() => setActiveStatus(filter.value)} type="button">{filter.label}</button>)}
      </div>

      {loading && <div className="loading-state">正在整理书架……</div>}
      {!loading && error && <ErrorState message={error} />}
      {!loading && !error && books.length === 0 && <EmptyState title="书架还是空的" detail="添加一本书并上传 PDF，开始建立属于你的复习资料。" action={<Link className="button button-primary" href="/books/new"><BookPlus size={16} />添加第一本书</Link>} />}
      {!loading && !error && books.length > 0 && <div className="book-grid">{books.map((book) => <BookCard book={book} key={book.id} />)}</div>}

      <div style={{ alignItems: "center", color: "var(--muted)", display: "flex", fontSize: 12, gap: 7, marginTop: 32 }}><Sparkles size={14} color="var(--yellow)" />开发阶段使用模拟出题与评分；没有 PDF 时需启用真实模型进行知识兜底。</div>
    </div>
  );
}
