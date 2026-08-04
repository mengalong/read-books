import { AlertCircle, ChevronRight, FileText, FileX2, UserRound } from "lucide-react";
import Link from "next/link";

import type { BookSummary, SourceEvidence, SourceMode } from "@/lib/types";
import { formatDate, formatFileSize, statusLabel } from "@/lib/format";

export function BookCover({ book, large = false }: { book: Pick<BookSummary, "title" | "author" | "cover_color">; large?: boolean }) {
  return (
    <div className={`book-cover${large ? " detail-cover" : ""}`} style={{ background: book.cover_color }}>
      <span className="book-cover-kicker">READ / REVIEW</span>
      <span className="book-cover-title">{book.title.slice(0, 8)}</span>
      <span className="book-cover-author">{book.author || "未署名"}</span>
    </div>
  );
}

export function StatusBadge({ status }: { status: string }) {
  return <span className={`status-badge status-${status}`}>{statusLabel(status)}</span>;
}

export function BookCard({ book, href }: { book: BookSummary; href?: string }) {
  const hasPdf = book.stats.pdf_count > 0;

  return (
    <Link className="book-card" href={href || `/books/${book.id}`}>
      <div className="book-card-top">
        <BookCover book={book} />
        <div className="book-card-heading">
          <h3>{book.title}</h3>
          <p className="book-author">{book.author || "作者未填写"}</p>
        </div>
        <StatusBadge status={book.reading_status} />
      </div>
      <p className="book-description">{book.description || "还没有写下这本书的简介。"}</p>
      <div className="tag-row">
        {book.shelf_status === "unlisted" && <StatusBadge status="unlisted" />}
        <span className={`tag pdf-status-tag ${hasPdf ? "has-pdf" : "no-pdf"}`}>
          {hasPdf ? <FileText size={12} /> : <FileX2 size={12} />}
          {hasPdf ? "已上传 PDF" : "未上传 PDF"}
        </span>
        {book.owner_display_name && <span className="tag book-owner-tag"><UserRound size={12} />归属：{book.owner_display_name}</span>}
        {book.tags.slice(0, 3).map((tag) => <span className="tag" key={tag}>{tag}</span>)}
      </div>
      <div className="book-card-bottom">
        <div className="book-stats">
          <span>{book.stats.completed_pdf_count} 份原文</span>
          <span>{book.stats.quiz_count} 次测试</span>
          <span>{book.stats.average_score === null ? "未测试" : `平均 ${book.stats.average_score}%`}</span>
        </div>
        <ChevronRight className="book-card-arrow" size={16} />
      </div>
    </Link>
  );
}

export function SourceModeNotice({ sourceMode, compact = false }: { sourceMode: SourceMode; compact?: boolean }) {
  if (sourceMode !== "model_knowledge") return null;
  return <div className={`source-mode-warning${compact ? " compact" : ""}`}>
    <AlertCircle size={17} />
    <div>
      <strong>本次使用模型知识兜底出题</strong>
      <span>未上传 PDF，题目基于书名、作者和模型内化知识生成，不提供可靠的 PDF 页码或逐句原文依据；不同版本和模型记忆可能造成偏差，请将结果作为复习线索。</span>
    </div>
  </div>;
}

export function EvidenceList({ evidence, open = false, sourceMode = "pdf" }: { evidence: SourceEvidence[]; open?: boolean; sourceMode?: SourceMode }) {
  function renderExcerpt(item: SourceEvidence) {
    const fallback = item.excerpt.match(/[^。！？；\n]+(?:[。！？；]|$)/)?.[0]?.trim();
    const highlight = (item.highlight || fallback || "").trim();
    const start = highlight ? item.excerpt.indexOf(highlight) : -1;
    if (start < 0) return <>“{item.excerpt}”</>;
    return <>“{item.excerpt.slice(0, start)}<mark className="evidence-highlight">{highlight}</mark>{item.excerpt.slice(start + highlight.length)}”</>;
  }

  if (sourceMode === "model_knowledge") return <details className="evidence model-knowledge-evidence" open={open}>
    <summary>来源说明（模型知识模式，答题时默认折叠）</summary>
    <div className="evidence-body"><p className="evidence-support">本题没有对应的 PDF 原文依据。题目、参考答案和问答评分要点基于书名、作者及模型内化知识生成，不能据此确认具体版本的页码或逐句引文。</p></div>
  </details>;

  return (
    <details className="evidence" open={open}>
      <summary>原文依据（{evidence.length} 处，答题时默认折叠）</summary>
      <div className="evidence-body">
        {evidence.map((item) => (
          <div key={item.chunk_id} style={{ marginBottom: 14 }}>
            <div className="evidence-meta"><FileText size={13} style={{ verticalAlign: "-2px", marginRight: 4 }} />{item.file_name} · 第 {item.page_number} 页</div>
            <p className="evidence-excerpt">{renderExcerpt(item)}</p>
            <p className="evidence-support">依据说明：{item.support}</p>
          </div>
        ))}
      </div>
    </details>
  );
}

export function EmptyState({ title, detail, action }: { title: string; detail: string; action?: React.ReactNode }) {
  return <div className="empty-state"><strong>{title}</strong><p style={{ marginTop: 8 }}>{detail}</p>{action && <div style={{ marginTop: 18 }}>{action}</div>}</div>;
}

export function ErrorState({ message }: { message: string }) {
  return <div className="error-state">{message}</div>;
}

export function formatPdfMeta(size: number, pages: number, chunks: number) {
  const details = [`${formatFileSize(size)}`];
  if (pages) details.push(`${pages} 页`);
  if (chunks) details.push(`${chunks} 个原文片段`);
  return details.join(" · ");
}

export function NextReview({ date }: { date: string | null }) {
  return <span className="meta-text">下次建议：{formatDate(date)}</span>;
}
