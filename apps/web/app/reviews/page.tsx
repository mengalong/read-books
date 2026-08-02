"use client";

import { Eye, History, RotateCcw, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { EmptyState, ErrorState, StatusBadge } from "@/components/ui";
import { ApiError, deleteReview, getReviewHistory, reopenReview } from "@/lib/api";
import { formatDateTime, formatDuration } from "@/lib/format";
import type { ReviewTaskSummary } from "@/lib/types";

export default function ReviewsPage() {
  const router = useRouter();
  const [reviews, setReviews] = useState<ReviewTaskSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [workingId, setWorkingId] = useState("");

  async function refresh() {
    try {
      setReviews(await getReviewHistory());
      setError("");
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "复习记录加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void refresh(); }, []);

  async function handleReopen(review: ReviewTaskSummary) {
    setWorkingId(review.id);
    setError("");
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
    setError("");
    try {
      await deleteReview(review.id);
      setReviews((current) => current.filter((item) => item.id !== review.id));
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "删除复习记录失败");
    } finally {
      setWorkingId("");
    }
  }

  if (loading) return <div className="page-wrap"><div className="loading-state">正在整理全部复习记录……</div></div>;
  if (error && reviews.length === 0) return <div className="page-wrap"><ErrorState message={error} /></div>;

  return (
    <div className="page-wrap">
      <header className="page-header"><div><div className="eyebrow">Review log</div><h1 className="page-title">复习记录</h1><p className="page-description">所有书籍的答题任务都集中在这里。重新答题会更新原任务，不会额外创建一条记录。</p></div><History size={30} strokeWidth={1.4} style={{ color: "var(--green)" }} /></header>
      {error && <div className="toast-error">{error}</div>}
      {reviews.length === 0 ? <EmptyState title="还没有复习记录" detail="从书籍详情页选择一套复习试卷，完成第一次复习后记录会出现在这里。" /> : <div className="history-table-wrap"><table className="history-table"><thead><tr><th>书籍与试卷</th><th>状态</th><th>次数</th><th>得分</th><th>题量</th><th>用时</th><th>时间</th><th aria-label="操作" /></tr></thead><tbody>{reviews.map((review) => {
        const percent = review.total_score === null ? null : Math.round(review.total_score / review.max_score * 100);
        const busy = workingId === review.id;
        return <tr key={review.id}><td><strong>{review.book_title}</strong><span className="table-subtext">{review.title}</span></td><td><StatusBadge status={review.status} /></td><td>第 {review.attempt_number} 次</td><td className={percent !== null && percent >= 60 ? "score-good" : "score-low"}>{percent === null ? "—" : `${percent} 分`}</td><td>{review.question_count} 题</td><td>{formatDuration(review.elapsed_seconds)}</td><td>{formatDateTime(review.submitted_at || review.created_at)}</td><td><div className="table-actions">{review.status === "submitted" ? <Link aria-label="查看复习详情" className="button button-quiet" href={`/reviews/${review.id}/result`} title="查看复习详情"><Eye size={15} /></Link> : <Link aria-label="继续复习" className="button button-quiet" href={`/reviews/${review.id}`} title="继续复习"><Eye size={15} /></Link>}{review.status === "submitted" && <button aria-label="重新答题" className="button button-quiet" disabled={busy} onClick={() => void handleReopen(review)} title="重新答题" type="button"><RotateCcw size={15} /></button>}<button aria-label="删除记录" className="button button-quiet danger-action" disabled={busy} onClick={() => void handleDelete(review)} title="删除记录" type="button"><Trash2 size={15} /></button></div></td></tr>;
      })}</tbody></table></div>}
    </div>
  );
}
