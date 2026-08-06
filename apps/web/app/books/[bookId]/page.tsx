"use client";

import { AlertCircle, Archive, ArchiveRestore, ArrowLeft, BookOpen, Check, CheckCircle2, Copy, FileText, History, LoaderCircle, PencilLine, Play, Share2, Sparkles, Trash2, UploadCloud, X } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { BookCover, EmptyState, ErrorState, NextReview, SourceModeNotice, StatusBadge, formatPdfMeta } from "@/components/ui";
import { ApiError, createExamShare, deleteBook, deletePdf, deleteQuiz, getBook, getChunks, restoreBook, unlistBook, uploadPdf } from "@/lib/api";
import { copyText } from "@/lib/clipboard";
import { formatDate, formatDateTime, scorePercentage } from "@/lib/format";
import type { BookDetail, Chunk, ExamShare, PdfDocument, QuizSummary } from "@/lib/types";

const difficultyLabels: Record<string, string> = {
  easy: "基础",
  medium: "适中",
  hard: "深入",
};

export default function BookDetailPage() {
  const params = useParams<{ bookId: string }>();
  const router = useRouter();
  const bookId = params.bookId;
  const [book, setBook] = useState<BookDetail | null>(null);
  const [chunks, setChunks] = useState<Chunk[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [deletingQuizId, setDeletingQuizId] = useState<string | null>(null);
  const [managingBook, setManagingBook] = useState(false);
  const [sharingQuiz, setSharingQuiz] = useState<QuizSummary | null>(null);
  const [shareName, setShareName] = useState("");
  const [shareHasExpiry, setShareHasExpiry] = useState(false);
  const [shareExpiresAt, setShareExpiresAt] = useState("");
  const [createdShare, setCreatedShare] = useState<ExamShare | null>(null);
  const [sharing, setSharing] = useState(false);
  const [copied, setCopied] = useState(false);
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
    if (!book?.pdfs.some((pdf) => pdf.parse_status === "pending" || pdf.parse_status === "processing") && !book?.active_generation_task_id) return;
    const timer = window.setInterval(() => { void refresh(); }, 2200);
    return () => window.clearInterval(timer);
  }, [book]);

  const completed = book?.stats.completed_pdf_count || 0;
  const pending = book?.pdfs.filter((pdf) => pdf.parse_status !== "completed").length || 0;
  const generating = Boolean(book?.active_generation_task_id);
  const noPdf = Boolean(book && book.pdfs.length === 0);
  const isActive = book?.shelf_status === "active";
  const canGenerate = Boolean(book && isActive && (completed > 0 || noPdf) && !generating);
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

  async function handleDeleteQuiz(quiz: QuizSummary) {
    if (!window.confirm(`确定删除“${quiz.title}”吗？该试卷下的复习记录会一并删除；已分享的考试将停止，但历史答卷会继续保留。`)) return;
    setDeletingQuizId(quiz.id);
    setError("");
    try {
      await deleteQuiz(quiz.id);
      await refresh(false);
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "试卷删除失败");
    } finally {
      setDeletingQuizId(null);
    }
  }

  function openShare(quiz: QuizSummary) {
    if (!book) return;
    setSharingQuiz(quiz);
    setShareName(`${book.title} · ${quiz.title}`);
    setShareHasExpiry(false);
    setShareExpiresAt(defaultExpirationValue());
    setCreatedShare(null);
    setCopied(false);
    setError("");
  }

  function closeShare() {
    if (!sharing) {
      setSharingQuiz(null);
      setCreatedShare(null);
    }
  }

  async function handleCreateShare(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!sharingQuiz) return;
    setSharing(true);
    setError("");
    try {
      setCreatedShare(await createExamShare(sharingQuiz.id, {
        name: shareName.trim(),
        expires_at: shareHasExpiry ? new Date(shareExpiresAt).toISOString() : null,
      }));
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "考试链接创建失败");
    } finally {
      setSharing(false);
    }
  }

  async function copyShareLink() {
    if (!createdShare) return;
    setError("");
    try {
      await copyText(`${window.location.origin}/exams/${createdShare.share_code}`);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setError("链接复制失败，请手动选择分享链接进行复制");
    }
  }

  async function handleShelfStatus() {
    if (!book) return;
    const action = book.shelf_status === "active" ? "下架" : "恢复上架";
    if (!window.confirm(`确定${action}《${book.title}》吗？${book.shelf_status === "active" ? "下架后会保留资料和复习记录，但不能继续生成试卷或开始复习。" : ""}`)) return;
    setManagingBook(true);
    setError("");
    try {
      const updated = book.shelf_status === "active"
        ? await unlistBook(book.id)
        : await restoreBook(book.id);
      setBook(updated);
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : `书籍${action}失败`);
    } finally {
      setManagingBook(false);
    }
  }

  async function handleDeleteBook() {
    if (!book || !window.confirm(`确定永久删除《${book.title}》吗？PDF、试卷、复习记录和答案都会一并删除，且无法恢复。`)) return;
    setManagingBook(true);
    setError("");
    try {
      await deleteBook(book.id);
      router.replace("/");
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "书籍删除失败");
      setManagingBook(false);
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
            <div className="tag-row"><StatusBadge status={book.shelf_status} />{book.tags.map((tag) => <span className="tag" key={tag}>{tag}</span>)}</div>
          </div>
        </div>
        <div className="detail-actions">
          <Link className="button button-secondary" href={`/books/${book.id}/edit`}><PencilLine size={15} />编辑信息</Link>
          <Link className="button button-secondary" href={`/books/${book.id}/history`}><History size={15} />复习记录</Link>
          {isActive && <Link className="button button-primary" href={canGenerate ? `/books/${book.id}/quiz/new` : "#"} aria-disabled={!canGenerate} onClick={(event) => { if (!canGenerate) event.preventDefault(); }}><Sparkles size={15} />{generating ? "正在后台出题" : "生成新试卷"}</Link>}
          <button className="button button-secondary" disabled={managingBook} onClick={() => void handleShelfStatus()} type="button">{isActive ? <Archive size={15} /> : <ArchiveRestore size={15} />}{isActive ? "下架书籍" : "恢复上架"}</button>
          <button className="button button-danger" disabled={managingBook} onClick={() => void handleDeleteBook()} type="button"><Trash2 size={15} />删除书籍</button>
        </div>
      </section>

      {!isActive && <div className="shelf-status-banner"><Archive size={18} /><div><strong>这本书已下架</strong><span>PDF、试卷和复习记录均已保留。恢复上架后才能上传 PDF、生成试卷或开始新的复习。</span></div></div>}

      {isActive && noPdf && !generating && <SourceModeNotice sourceMode="model_knowledge" />}

      {book.active_generation_task_id && <div className="generation-progress processing">
        <div className="generation-progress-heading"><div><span className="eyebrow">出题任务</span><strong>{book.active_generation_phase || "正在后台生成题目"}</strong></div><LoaderCircle className="spin" size={21} /></div>
        <div className="progress-track"><div className="progress-fill" style={{ width: `${book.active_generation_total_questions ? book.active_generation_completed_questions / book.active_generation_total_questions * 100 : 0}%` }} /></div>
        <div className="generation-progress-meta"><span>{book.active_generation_completed_questions} / {book.active_generation_total_questions} 道题</span><span>可以离开此页，任务会继续执行</span></div>
      </div>}

      {book.pre_generation_status !== "disabled" && !book.active_generation_task_id && <div className={`pre-generation-banner ${book.pre_generation_status}`}>
        {book.pre_generation_status === "completed" ? <CheckCircle2 size={18} /> : book.pre_generation_status === "failed" ? <AlertCircle size={18} /> : <LoaderCircle className={book.pre_generation_status === "processing" ? "spin" : ""} size={18} />}
        <div>
          <strong>{book.pre_generation_status === "completed" ? "预生成测试已准备好" : book.pre_generation_status === "failed" ? "预生成测试失败" : "正在生成题目中"}</strong>
          <span>{book.pre_generation_error || (book.pre_generation_status === "completed" ? "预生成试卷已保存到下方的复习试卷列表中。" : "系统正在后台生成一套默认复习测试，完成前不能重复触发。")}</span>
        </div>
      </div>}

      <div className="metrics-grid book-detail-metrics" style={{ marginBottom: 25 }}>
        <div className="metric"><div className="metric-label">原文资料</div><div className="metric-value">{completed}<span className="metric-detail">份已完成</span></div></div>
        <div className="metric"><div className="metric-label">已解析片段</div><div className="metric-value">{book.stats.chunk_count}<span className="metric-detail">段</span></div></div>
        <div className="metric"><div className="metric-label">复习试卷</div><div className="metric-value">{book.quizzes.length}<span className="metric-detail">套</span></div></div>
        <div className="metric"><div className="metric-label">下次建议复习</div><div className="metric-value" style={{ fontSize: 18 }}>{formatDate(book.stats.next_review_date)}</div></div>
      </div>

      <section className="content-panel quiz-library">
        <div className="section-title"><h2>复习试卷</h2><span>{book.quizzes.length ? "可重复选择同一套试卷复习" : "等待生成"}</span></div>
        {book.quizzes.length === 0 ? <EmptyState title="还没有复习试卷" detail={isActive ? "生成完成后，试卷会保存在这里，以后可以反复作答。" : "恢复上架后，可以为这本书生成复习试卷。"} action={isActive ? <Link className="button button-primary" href={`/books/${book.id}/quiz/new`}><Sparkles size={15} />生成第一套试卷</Link> : undefined} /> : <div className="quiz-library-list">{book.quizzes.map((quiz) => {
          const latestPercent = scorePercentage(quiz.latest_score, quiz.max_score);
          return <article className="quiz-library-row" key={quiz.id}>
            <div className="quiz-library-main">
              <strong>{quiz.title}</strong>
              <span>难度：{difficultyLabels[quiz.difficulty] || quiz.difficulty} · {quiz.question_count} 道题 · {quiz.duration_minutes} 分钟 · 创建于 {formatDateTime(quiz.created_at)}</span>
              <span>出题依据：{quiz.source_mode === "model_knowledge" ? "模型知识（无 PDF 原文）" : "已解析 PDF 原文"}</span>
              <span>题目构成：单选 {quiz.single_count} · 多选 {quiz.multiple_count} · 问答 {quiz.short_count}</span>
            </div>
            <div className="quiz-library-stats"><span>已复习 {quiz.review_count} 次</span><strong>{latestPercent === null ? "暂无成绩" : `最近得分率 ${latestPercent}%`}</strong></div>
            <div className="quiz-library-actions">
              {isActive && <Link className="button button-secondary" href={`/quizzes/${quiz.id}`}><Play size={15} />选择这套</Link>}
              {isActive && <button className="button button-quiet" onClick={() => openShare(quiz)} title="分享考试" type="button"><Share2 size={16} /></button>}
              <button
                aria-label={`删除${quiz.title}`}
                className="button button-quiet quiz-delete-button"
                disabled={deletingQuizId === quiz.id}
                onClick={() => void handleDeleteQuiz(quiz)}
                title="删除试卷"
                type="button"
              >
                <Trash2 size={16} />
              </button>
            </div>
          </article>;
        })}</div>}
      </section>

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
            {book.pdfs.length === 0 && <EmptyState title="还没有 PDF" detail="可以上传读过的原文以获得页码和逐句依据；当前也可以使用已配置模型的知识生成测试。" />}
          </div>
          {isActive && <div className="upload-zone">
            <UploadCloud size={23} />
            <div className="upload-zone-copy"><strong>{uploading ? "正在上传……" : "补充一份 PDF"}</strong><span>不设置产品层面的大小上限；大文件上传后会在后台解析，请在此页等待状态更新。</span></div>
            <input className="upload-input" accept="application/pdf,.pdf" disabled={uploading} onChange={handleUpload} type="file" />
          </div>}
        </section>

        <section className="content-panel">
          <div className="section-title"><h2>原文片段</h2><span>{chunks.length ? `预览前 ${chunks.length} 段` : "等待解析"}</span></div>
          {previewChunks.length > 0 ? <div className="chunk-list">{previewChunks.map((chunk) => <article className="chunk-item" key={chunk.id}><div className="chunk-heading">第 {chunk.page_number} 页 · {chunk.file_name}</div><p>{chunk.content}</p></article>)}</div> : <EmptyState title="暂时没有片段" detail="PDF 完成解析后，会在这里看到按页保存的原文。" />}
          {chunks.length > 0 && <p className="field-hint" style={{ marginTop: 17 }}><BookOpen size={13} style={{ verticalAlign: "-3px", marginRight: 4 }} />测试中的每道题都会保留同样的页码和原文片段。</p>}
        </section>
      </div>

      {sharingQuiz && <div className="modal-backdrop" onMouseDown={(event) => { if (event.currentTarget === event.target) closeShare(); }} role="presentation">
        <section aria-labelledby="share-exam-title" aria-modal="true" className="modal-panel exam-share-modal" role="dialog">
          <div className="modal-heading"><div><span className="eyebrow">Share exam</span><h2 id="share-exam-title">分享“{sharingQuiz.title}”</h2></div><button aria-label="关闭分享弹窗" className="modal-close" disabled={sharing} onClick={closeShare} title="关闭" type="button"><X size={18} /></button></div>
          {createdShare ? <div className="share-created-panel">
            <div className="share-created-status"><CheckCircle2 size={18} /><div><strong>考试链接已创建</strong><span>{createdShare.expires_at ? `答题截止到 ${formatDateTime(createdShare.expires_at)}` : "考试长期有效，可在考试管理中随时调整。"}</span></div></div>
            <label className="field"><span>分享链接</span><div className="share-link-field"><input readOnly value={`${typeof window === "undefined" ? "" : window.location.origin}/exams/${createdShare.share_code}`} /><button aria-label="复制考试链接" className="button button-secondary" onClick={() => void copyShareLink()} title="复制链接" type="button">{copied ? <Check size={15} /> : <Copy size={15} />}{copied ? "已复制" : "复制"}</button></div></label>
            <div className="modal-actions"><button className="button button-secondary" onClick={closeShare} type="button">关闭</button><Link className="button button-primary" href={`/exam-management/${createdShare.id}`}><Share2 size={15} />查看考试</Link></div>
          </div> : <form onSubmit={handleCreateShare}>
            <div className="share-quiz-summary"><strong>{book.title}</strong><span>难度：{difficultyLabels[sharingQuiz.difficulty] || sharingQuiz.difficulty} · {sharingQuiz.question_count} 道题 · {sharingQuiz.duration_minutes} 分钟</span><span>单选 {sharingQuiz.single_count} · 多选 {sharingQuiz.multiple_count} · 问答 {sharingQuiz.short_count}</span></div>
            <label className="field"><span>考试活动名称</span><input maxLength={200} onChange={(event) => setShareName(event.target.value)} required value={shareName} /></label>
            <div className="share-expiry-setting">
              <div><strong>设置考试有效期</strong><span>{shareHasExpiry ? "到期后不能继续答题，历史结果仍可查看。" : "当前设置为长期有效。"}</span></div>
              <label className="switch-control" htmlFor="share-has-expiry"><input checked={shareHasExpiry} id="share-has-expiry" onChange={(event) => setShareHasExpiry(event.target.checked)} type="checkbox" /><span className="switch-track" aria-hidden="true"><span className="switch-thumb" /></span><span className="switch-label">{shareHasExpiry ? "已开启" : "未开启"}</span></label>
            </div>
            {shareHasExpiry && <label className="field"><span>答题截止时间</span><input min={toDateTimeLocal(new Date())} onChange={(event) => setShareExpiresAt(event.target.value)} required type="datetime-local" value={shareExpiresAt} /><small>按当前设备的本地时间填写，保存后统一按北京时间展示。</small></label>}
            <div className="copy-scope-note">公开答题页不会展示 PDF 文件名、页码或原文摘录。参与者提交后可以查看分数、答案和解析。</div>
            <div className="modal-actions"><button className="button button-secondary" disabled={sharing} onClick={closeShare} type="button">取消</button><button className="button button-primary" disabled={sharing || !shareName.trim()} type="submit"><Share2 size={15} />{sharing ? "正在创建……" : "生成考试链接"}</button></div>
          </form>}
        </section>
      </div>}
    </div>
  );
}

function defaultExpirationValue() {
  return toDateTimeLocal(new Date(Date.now() + 7 * 24 * 60 * 60 * 1000));
}

function toDateTimeLocal(value: Date) {
  const offset = value.getTimezoneOffset() * 60_000;
  return new Date(value.getTime() - offset).toISOString().slice(0, 16);
}
