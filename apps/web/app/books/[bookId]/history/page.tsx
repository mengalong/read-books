"use client";

import { ArrowLeft, Eye, Plus, RotateCcw, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { EmptyState, ErrorState, StatusBadge } from "@/components/ui";
import { ApiError, deleteReview, getBook, getHistory, reopenReview } from "@/lib/api";
import { formatDateTime, formatDuration, scorePercentage } from "@/lib/format";
import type { BookDetail, ReviewTaskSummary } from "@/lib/types";

export default function BookHistoryPage() {
  const params = useParams<{ bookId: string }>();
  const router = useRouter();
  const [book, setBook] = useState<BookDetail | null>(null);
  const [history, setHistory] = useState<ReviewTaskSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [workingId, setWorkingId] = useState("");

  useEffect(() => {
    Promise.all([getBook(params.bookId), getHistory(params.bookId)])
      .then(([bookData, historyData]) => { setBook(bookData); setHistory(historyData); })
      .catch((reason: unknown) => setError(reason instanceof ApiError ? reason.message : "历史记录加载失败"))
      .finally(() => setLoading(false));
  }, [params.bookId]);

  async function handleReopen(review: ReviewTaskSummary) {
    setWorkingId(review.id);
    try {
      await reopenReview(review.id);
      router.push(`/reviews/${review.id}`);
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "重新答题失败");
      setWorkingId("");
    }
  }

  async function handleDelete(review: ReviewTaskSummary) {
    if (!window.confirm(`确定删除“${review.title}”第 ${review.attempt_number} 次复习记录吗？`)) return;
    setWorkingId(review.id);
    try {
      await deleteReview(review.id);
      setHistory((current) => current.filter((item) => item.id !== review.id));
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "删除复习记录失败");
    } finally {
      setWorkingId("");
    }
  }

  if (loading) return <div className="page-wrap"><div className="loading-state">正在整理复习记录……</div></div>;
  if (!book) return <div className="page-wrap"><ErrorState message={error || "未找到这本书"} /></div>;

  return (
    <div className="page-wrap">
      <Link className="back-link" href={`/books/${book.id}`}><ArrowLeft size={14} />返回《{book.title}》</Link>
      <header className="page-header"><div><div className="eyebrow">Book review log</div><h1 className="page-title">{book.title} 的复习记录</h1><p className="page-description">同一套试卷可以多次复习，每次答题都会记录为独立任务。</p></div><Link className="button button-primary" href={`/books/${book.id}/quiz/new`}><Plus size={15} />生成新试卷</Link></header>
      {error && <div className="toast-error">{error}</div>}
      {history.length === 0 ? <EmptyState title="还没有复习记录" detail="完成一次复习后，得分、用时和复习建议会保存在这里。" action={<Link className="button button-primary" href={`/books/${book.id}/quiz/new`}>生成第一套试卷</Link>} /> : <div className="history-table-wrap"><table className="history-table"><thead><tr><th>试卷</th><th>状态</th><th>次数</th><th>得分率</th><th>题量</th><th>实际用时</th><th>时间</th><th aria-label="操作" /></tr></thead><tbody>{history.map((item) => {
        const percent = scorePercentage(item.total_score, item.max_score);
        const busy = workingId === item.id;
        return <tr key={item.id}><td><strong>{item.title}</strong></td><td><StatusBadge status={item.status} /></td><td>第 {item.attempt_number} 次</td><td className={percent !== null && percent >= 60 ? "score-good" : "score-low"}>{percent === null ? "—" : `${percent}%`}</td><td>{item.question_count} 题</td><td>{formatDuration(item.elapsed_seconds)}</td><td>{formatDateTime(item.submitted_at || item.created_at)}</td><td><div className="table-actions">{item.status === "submitted" ? <Link aria-label="查看复习详情" className="button button-quiet" href={`/reviews/${item.id}/result`} title="查看复习详情"><Eye size={15} /></Link> : <Link aria-label="继续复习" className="button button-quiet" href={`/reviews/${item.id}`} title="继续复习"><Eye size={15} /></Link>}{item.status === "submitted" && <button aria-label="重新答题" className="button button-quiet" disabled={busy} onClick={() => void handleReopen(item)} title="重新答题" type="button"><RotateCcw size={15} /></button>}<button aria-label="删除记录" className="button button-quiet danger-action" disabled={busy} onClick={() => void handleDelete(item)} title="删除记录" type="button"><Trash2 size={15} /></button></div></td></tr>;
      })}</tbody></table></div>}
    </div>
  );
}
