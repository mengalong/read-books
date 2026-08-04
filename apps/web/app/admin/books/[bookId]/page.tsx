"use client";

import { Archive, ArchiveRestore, ArrowLeft, BookOpen, FileText, ShieldCheck, Trash2, UserRound } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { BookCover, EmptyState, ErrorState, StatusBadge, formatPdfMeta } from "@/components/ui";
import { ApiError, deleteAdminBook, getAdminBook, getAdminBookChunks, restoreAdminBook, unlistAdminBook } from "@/lib/api";
import { formatDate, formatDateTime, scorePercentage } from "@/lib/format";
import type { BookDetail, Chunk } from "@/lib/types";

const difficultyLabels: Record<string, string> = { easy: "基础", medium: "适中", hard: "深入" };

export default function AdminBookDetailPage() {
  const params = useParams<{ bookId: string }>();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [book, setBook] = useState<BookDetail | null>(null);
  const [chunks, setChunks] = useState<Chunk[]>([]);
  const [loading, setLoading] = useState(true);
  const [managing, setManaging] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    getAdminBook(params.bookId)
      .then(async (item) => {
        const content = item.stats.chunk_count ? await getAdminBookChunks(params.bookId) : [];
        if (!cancelled) { setBook(item); setChunks(content); }
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof ApiError ? reason.message : "书籍详情加载失败");
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [params.bookId]);

  const previewChunks = useMemo(() => chunks.slice(0, 4), [chunks]);

  if (loading) return <div className="page-wrap"><div className="loading-state">正在打开管理视图……</div></div>;
  if (!book) return <div className="page-wrap"><ErrorState message={error || "未找到这本书"} /></div>;

  const currentBook = book;
  const fromWorkspace = searchParams.get("source") === "workspace" && book.owner_user_id;
  const returnHref = fromWorkspace ? `/admin/users/${book.owner_user_id}/space` : "/settings/books";
  const returnLabel = fromWorkspace ? `返回${book.owner_display_name || "用户"}的空间` : "返回书籍管理";

  async function handleShelfStatus() {
    const action = currentBook.shelf_status === "active" ? "下架" : "恢复上架";
    if (!window.confirm(`确定${action}《${currentBook.title}》吗？${currentBook.shelf_status === "active" ? "下架后会保留全部资料和历史记录。" : ""}`)) return;
    setManaging(true);
    setError("");
    try {
      const updated = currentBook.shelf_status === "active"
        ? await unlistAdminBook(currentBook.id)
        : await restoreAdminBook(currentBook.id);
      setBook(updated);
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : `书籍${action}失败`);
    } finally {
      setManaging(false);
    }
  }

  async function handleDelete() {
    if (!window.confirm(`确定永久删除《${currentBook.title}》吗？该用户的 PDF、试卷、复习记录和答案都会一并删除，且无法恢复。`)) return;
    setManaging(true);
    setError("");
    try {
      await deleteAdminBook(currentBook.id);
      router.replace(returnHref);
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "书籍删除失败");
      setManaging(false);
    }
  }

  return (
    <div className="page-wrap">
      <Link className="back-link" href={returnHref}><ArrowLeft size={14} />{returnLabel}</Link>
      {error && <div className="toast-error">{error}</div>}
      <div className="workspace-context-banner">
        <ShieldCheck size={18} />
        <div><strong>管理员书籍管理视图</strong><span>归属：{book.owner_display_name || "历史未归属用户"}。管理员可管理上下架和删除，但不能代用户编辑、出题或答题。</span></div>
      </div>

      <section className="detail-hero">
        <div className="detail-info">
          <BookCover book={book} large />
          <div className="detail-info-text">
            <div className="eyebrow">Managed book detail</div>
            <h1>{book.title}</h1>
            <p className="book-author">{book.author || "作者未填写"} · {book.language}</p>
            <p className="book-description">{book.description || "还没有写下这本书的简介。"}</p>
            <div className="tag-row"><StatusBadge status={book.shelf_status} /><span className="tag book-owner-tag"><UserRound size={12} />归属：{book.owner_display_name || "历史数据"}</span>{book.tags.map((tag) => <span className="tag" key={tag}>{tag}</span>)}</div>
          </div>
        </div>
        <div className="detail-actions">
          {book.owner_user_id && <Link className="button button-secondary" href={`/admin/users/${book.owner_user_id}/space`}><UserRound size={15} />查看所属空间</Link>}
          <button className="button button-secondary" disabled={managing} onClick={() => void handleShelfStatus()} type="button">{book.shelf_status === "active" ? <Archive size={15} /> : <ArchiveRestore size={15} />}{book.shelf_status === "active" ? "下架书籍" : "恢复上架"}</button>
          <button className="button button-danger" disabled={managing} onClick={() => void handleDelete()} type="button"><Trash2 size={15} />删除书籍</button>
        </div>
      </section>

      <div className="metrics-grid book-detail-metrics" style={{ marginBottom: 25 }}>
        <div className="metric"><div className="metric-label">原文资料</div><div className="metric-value">{book.stats.completed_pdf_count}<span className="metric-detail">份已完成</span></div></div>
        <div className="metric"><div className="metric-label">已解析片段</div><div className="metric-value">{book.stats.chunk_count}<span className="metric-detail">段</span></div></div>
        <div className="metric"><div className="metric-label">复习试卷</div><div className="metric-value">{book.quizzes.length}<span className="metric-detail">套</span></div></div>
        <div className="metric"><div className="metric-label">下次建议复习</div><div className="metric-value" style={{ fontSize: 18 }}>{formatDate(book.stats.next_review_date)}</div></div>
      </div>

      <section className="content-panel quiz-library">
        <div className="section-title"><h2>复习试卷</h2><span>只读查看题量与历史成绩</span></div>
        {book.quizzes.length === 0 ? <EmptyState title="还没有复习试卷" detail="该用户尚未为这本书生成试卷。" /> : <div className="quiz-library-list">{book.quizzes.map((quiz) => {
          const latestPercent = scorePercentage(quiz.latest_score, quiz.max_score);
          return <article className="quiz-library-row admin-quiz-row" key={quiz.id}><div className="quiz-library-main"><strong>{quiz.title}</strong><span>难度：{difficultyLabels[quiz.difficulty] || quiz.difficulty} · {quiz.question_count} 道题 · {quiz.duration_minutes} 分钟 · 创建于 {formatDateTime(quiz.created_at)}</span><span>题目构成：单选 {quiz.single_count} · 多选 {quiz.multiple_count} · 问答 {quiz.short_count}</span></div><div className="quiz-library-stats"><span>已复习 {quiz.review_count} 次</span><strong>{latestPercent === null ? "暂无成绩" : `最近得分率 ${latestPercent}%`}</strong></div></article>;
        })}</div>}
      </section>

      <div className="detail-columns">
        <section className="content-panel">
          <div className="section-title"><h2>原文资料</h2><span>{book.pdfs.length} 份 PDF 记录</span></div>
          <div className="file-list">{book.pdfs.map((pdf) => <div className="file-row" key={pdf.id}><div className="file-icon"><FileText size={16} /></div><div className="file-main"><div className="file-name" title={pdf.file_name}>{pdf.file_name}</div><div className="file-meta">{formatPdfMeta(pdf.file_size, pdf.page_count, pdf.chunk_count)}{pdf.error_message ? ` · ${pdf.error_message}` : ""}</div></div><StatusBadge status={pdf.parse_status} /></div>)}{book.pdfs.length === 0 && <EmptyState title="没有 PDF" detail="这本书当前依赖模型知识兜底出题。" />}</div>
        </section>
        <section className="content-panel">
          <div className="section-title"><h2>原文片段</h2><span>{previewChunks.length ? `预览前 ${previewChunks.length} 段` : "暂无片段"}</span></div>
          {previewChunks.length > 0 ? <div className="chunk-list">{previewChunks.map((chunk) => <article className="chunk-item" key={chunk.id}><div className="chunk-heading">第 {chunk.page_number} 页 · {chunk.file_name}</div><p>{chunk.content}</p></article>)}</div> : <EmptyState title="暂时没有片段" detail="PDF 完成解析并保留原文后，会在这里显示。" />}
          {previewChunks.length > 0 && <p className="field-hint" style={{ marginTop: 17 }}><BookOpen size={13} style={{ verticalAlign: "-3px", marginRight: 4 }} />这里仅用于管理员核查原文，不提供编辑操作。</p>}
        </section>
      </div>
    </div>
  );
}
