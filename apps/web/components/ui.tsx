import { AlertCircle, ChevronRight, FileText, FileX2, UserRound } from "lucide-react";
import Link from "next/link";

import type { BookSummary, SourceEvidence, SourceMode } from "@/lib/types";
import {
  formatDate,
  formatFileSize,
  resourceAuthorLabel,
  resourceTypeLabel,
  resourceTypeShortLabel,
  statusLabel,
} from "@/lib/format";

export function BookCover({ book, large = false }: { book: Pick<BookSummary, "title" | "author" | "cover_color"> & { resource_type?: BookSummary["resource_type"] }; large?: boolean }) {
  return (
    <div className={`book-cover${large ? " detail-cover" : ""}`} style={{ background: book.cover_color }}>
      <span className="book-cover-kicker">{resourceTypeShortLabel(book.resource_type)} / REVIEW</span>
      <span className="book-cover-title">{book.title.slice(0, 8)}</span>
      <span className="book-cover-author">{book.author || `${resourceAuthorLabel(book.resource_type)}未署名`}</span>
    </div>
  );
}

export function StatusBadge({ status }: { status: string }) {
  return <span className={`status-badge status-${status}`}>{statusLabel(status)}</span>;
}

export function BookCard({ book, href }: { book: BookSummary; href?: string }) {
  const hasPdf = book.stats.pdf_count > 0;
  const hasTrustedMaterial = (book.stats.material_count || 0) > 0;

  return (
    <Link className="book-card" href={href || `/books/${book.id}`}>
      <div className="book-card-top">
        <BookCover book={book} />
        <div className="book-card-heading">
          <h3>{book.title}</h3>
          <p className="book-author">{book.author || `${resourceAuthorLabel(book.resource_type)}未填写`}</p>
        </div>
        <StatusBadge status={book.reading_status} />
      </div>
      <p className="book-description">{book.description || "还没有写下这本书的简介。"}</p>
      <div className="tag-row">
        {book.shelf_status === "unlisted" && <StatusBadge status="unlisted" />}
        <span className="tag">{resourceTypeLabel(book.resource_type)}</span>
        <span className={`tag pdf-status-tag ${hasPdf || hasTrustedMaterial ? "has-pdf" : "no-pdf"}`}>
          {hasPdf || hasTrustedMaterial ? <FileText size={12} /> : <FileX2 size={12} />}
          {hasPdf ? "已上传 PDF" : hasTrustedMaterial ? "已有可信资料" : "暂无可信资料"}
        </span>
        {book.owner_display_name && <span className="tag book-owner-tag"><UserRound size={12} />归属：{book.owner_display_name}</span>}
        {book.tags.slice(0, 3).map((tag) => <span className="tag" key={tag}>{tag}</span>)}
      </div>
      <div className="book-card-bottom">
        <div className="book-stats">
          <span>{book.stats.completed_pdf_count + (book.stats.ready_material_count || 0)} 份资料</span>
          <span>{book.stats.quiz_count} 次测试</span>
          <span>{book.stats.average_score === null ? "未测试" : `平均 ${book.stats.average_score}%`}</span>
        </div>
        <ChevronRight className="book-card-arrow" size={16} />
      </div>
    </Link>
  );
}

export function SourceModeNotice({ sourceMode, compact = false }: { sourceMode: SourceMode; compact?: boolean }) {
  if (sourceMode === "combined") return <div className={`source-mode-warning combined-source${compact ? " compact" : ""}`}>
    <FileText size={17} />
    <div>
      <strong>本次综合使用可信剧情、PDF 与台词</strong>
      <span>题目只能依据已解析 PDF、已确认剧情梗概事件和用户确认的台词资料生成，系统会保留实际引用来源用于校验。</span>
    </div>
  </div>;
  if (sourceMode === "plot") return <div className={`source-mode-warning material-source${compact ? " compact" : ""}`}>
    <FileText size={17} />
    <div>
      <strong>本次使用可信剧情梗概</strong>
      <span>题目依据已确认并启用的剧情事件生成，系统会保留对应事件和来源信息用于校验。</span>
    </div>
  </div>;
  if (sourceMode === "material") return <div className={`source-mode-warning material-source${compact ? " compact" : ""}`}>
    <FileText size={17} />
    <div>
      <strong>本次使用可信资料出题</strong>
      <span>题目中的台词、角色和场景来自用户上传并确认的资料，系统保留对应文件及位置用于校验。</span>
    </div>
  </div>;
  if (sourceMode !== "model_knowledge") return null;
  return <div className={`source-mode-warning${compact ? " compact" : ""}`}>
    <AlertCircle size={17} />
    <div>
      <strong>本次使用模型知识兜底出题</strong>
      <span>未上传 PDF，题目基于资源名称、类型和模型内化知识生成，不提供可靠的 PDF 页码、章节、集数或逐句原文依据；不同版本和模型记忆可能造成偏差，请将结果作为复习线索。</span>
    </div>
  </div>;
}

export function EvidenceList({ evidence, open = false, sourceMode = "pdf" }: { evidence: SourceEvidence[]; open?: boolean; sourceMode?: SourceMode }) {
  function evidenceLocation(item: SourceEvidence) {
    if (sourceMode === "material" || sourceMode === "plot" || (sourceMode === "combined" && item.material_id)) {
      const parts = [
        item.speaker || null,
        item.season_number ? `第 ${item.season_number} 季` : null,
        item.episode_number ? `第 ${item.episode_number} 集` : null,
        item.page_number ? `第 ${item.page_number} 页` : null,
      ].filter(Boolean);
      return [item.file_name, ...parts].join(" · ");
    }
    return `${item.file_name}${item.page_number ? ` · 第 ${item.page_number} 页` : ""}`;
  }

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
      <summary>{sourceMode === "material" ? "可信台词依据" : sourceMode === "plot" ? "剧情梗概依据" : sourceMode === "combined" ? "综合可信来源依据" : "原文依据"}（{evidence.length} 处，答题时默认折叠）</summary>
      <div className="evidence-body">
        {evidence.map((item) => (
          <div key={item.chunk_id} style={{ marginBottom: 14 }}>
            <div className="evidence-meta"><FileText size={13} style={{ verticalAlign: "-2px", marginRight: 4 }} />{evidenceLocation(item)}</div>
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
