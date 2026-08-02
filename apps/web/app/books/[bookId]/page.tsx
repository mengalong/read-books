"use client";

import { ArrowLeft, BookOpen, Clock3, FileText, History, Play, Trash2, UploadCloud } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { BookCover, EmptyState, ErrorState, NextReview, StatusBadge, formatPdfMeta } from "@/components/ui";
import { ApiError, deletePdf, getBook, getChunks, uploadPdf } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { BookDetail, Chunk, PdfDocument } from "@/lib/types";

export default function BookDetailPage() {
  const params = useParams<{ bookId: string }>();
  const bookId = params.bookId;
  const [book, setBook] = useState<BookDetail | null>(null);
  const [chunks, setChunks] = useState<Chunk[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");

  async function refresh(loadChunks = true) {
    try {
      const nextBook = await getBook(bookId);
      setBook(nextBook);
      if (loadChunks && nextBook.stats.chunk_count > 0) setChunks(await getChunks(bookId));
      setError("");
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "书籍详情加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void refresh(); }, [bookId]);

  useEffect(() => {
    if (!book?.pdfs.some((pdf) => pdf.parse_status === "pending" || pdf.parse_status === "processing")) return;
    const timer = window.setInterval(() => { void refresh(); }, 2200);
    return () => window.clearInterval(timer);
  }, [book]);

  const completed = book?.stats.completed_pdf_count || 0;
  const pending = book?.pdfs.filter((pdf) => pdf.parse_status !== "completed").length || 0;
  const previewChunks = useMemo(() => chunks.slice(0, 4), [chunks]);

  async function handleUpload(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setUploading(true);
    setError("");
    try {
      await uploadPdf(bookId, file);
      await refresh(false);
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "PDF 上传失败");
    } finally {
      setUploading(false);
    }
  }

  async function handleDelete(pdf: PdfDocument) {
    if (!window.confirm(`确定删除“${pdf.file_name}”吗？`)) return;
    try {
      await deletePdf(bookId, pdf.id);
      await refresh();
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "PDF 删除失败");
    }
  }

  if (loading) return <div className="page-wrap"><div className="loading-state">正在打开书籍……</div></div>;
  if (!book || error && !book) return <div className="page-wrap"><ErrorState message={error || "未找到这本书"} /></div>;

  return (
    <div className="page-wrap">
      <Link className="back-link" href="/"><ArrowLeft size={14} />返回书架</Link>
      {error && <div className="toast-error">{error}</div>}
      <section className="detail-hero">
        <div className="detail-info">
          <BookCover book={book} large />
          <div className="detail-info-text">
            <div className="eyebrow">Book detail</div>
            <h1>{book.title}</h1>
            <p className="book-author">{book.author || "作者未填写"} · {book.language}</p>
            <p className="book-description">{book.description || "还没有写下这本书的简介。"}</p>
            <div className="tag-row">{book.tags.map((tag) => <span className="tag" key={tag}>{tag}</span>)}</div>
          </div>
        </div>
        <div className="detail-actions">
          <Link className="button button-secondary" href={`/books/${book.id}/history`}><History size={15} />测试历史</Link>
          <Link className="button button-primary" href={completed ? `/books/${book.id}/quiz/new` : "#"} aria-disabled={!completed} onClick={(event) => { if (!completed) event.preventDefault(); }}><Play size={15} />开始测试</Link>
        </div>
      </section>

      <div className="metrics-grid" style={{ marginBottom: 25 }}>
        <div className="metric"><div className="metric-label">原文资料</div><div className="metric-value">{completed}<span className="metric-detail">份已完成</span></div></div>
        <div className="metric"><div className="metric-label">已解析片段</div><div className="metric-value">{book.stats.chunk_count}<span className="metric-detail">段</span></div></div>
        <div className="metric"><div className="metric-label">下次建议复习</div><div className="metric-value" style={{ fontSize: 18 }}>{formatDate(book.stats.next_review_date)}</div></div>
      </div>

      <div className="detail-columns">
        <section className="content-panel">
          <div className="section-title"><h2>原文资料</h2><span>{pending ? `${pending} 个文件处理中` : "默认按页保留依据"}</span></div>
          <div className="file-list">
            {book.pdfs.map((pdf) => <div className="file-row" key={pdf.id}>
              <div className="file-icon"><FileText size={16} /></div>
              <div className="file-main"><div className="file-name" title={pdf.file_name}>{pdf.file_name}</div><div className="file-meta">{formatPdfMeta(pdf.file_size, pdf.page_count, pdf.chunk_count)}{pdf.error_message ? ` · ${pdf.error_message}` : ""}</div></div>
              <StatusBadge status={pdf.parse_status} />
              <button aria-label={`删除${pdf.file_name}`} className="button button-quiet" onClick={() => void handleDelete(pdf)} title="删除 PDF" type="button"><Trash2 size={15} /></button>
            </div>)}
            {book.pdfs.length === 0 && <EmptyState title="还没有 PDF" detail="上传读过的原文后，系统才能基于内容生成测试。" />}
          </div>
          <div className="upload-zone">
            <UploadCloud size={23} />
            <div className="upload-zone-copy"><strong>{uploading ? "正在上传……" : "补充一份 PDF"}</strong><span>不设置产品层面的大小上限；大文件上传后会在后台解析，请在此页等待状态更新。</span></div>
            <input className="upload-input" accept="application/pdf,.pdf" disabled={uploading} onChange={handleUpload} type="file" />
          </div>
        </section>

        <section className="content-panel">
          <div className="section-title"><h2>原文片段</h2><span>{chunks.length ? `预览前 ${chunks.length} 段` : "等待解析"}</span></div>
          {previewChunks.length > 0 ? <div className="chunk-list">{previewChunks.map((chunk) => <article className="chunk-item" key={chunk.id}><div className="chunk-heading">第 {chunk.page_number} 页 · {chunk.file_name}</div><p>{chunk.content}</p></article>)}</div> : <EmptyState title="暂时没有片段" detail="PDF 完成解析后，会在这里看到按页保存的原文。" />}
          {chunks.length > 0 && <p className="field-hint" style={{ marginTop: 17 }}><BookOpen size={13} style={{ verticalAlign: "-3px", marginRight: 4 }} />测试中的每道题都会保留同样的页码和原文片段。</p>}
        </section>
      </div>
    </div>
  );
}
