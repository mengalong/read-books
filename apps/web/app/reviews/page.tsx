"use client";

import { Eye, RotateCcw, Search, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { FormEvent } from "react";
import { useEffect, useState } from "react";

import { EmptyState, ErrorState, StatusBadge } from "@/components/ui";
import { ApiError, deleteReview, getReviewHistory, reopenReview } from "@/lib/api";
import { formatDateTime, formatDuration, scorePercentage } from "@/lib/format";
import type { ReviewTaskSummary } from "@/lib/types";

type ReviewStatusFilter = "in_progress" | "submitted";

const statusFilters: { label: string; value?: ReviewStatusFilter }[] = [
  { label: "全部" },
  { label: "已完成", value: "submitted" },
  { label: "进行中", value: "in_progress" },
];

export default function ReviewsPage() {
  const router = useRouter();
  const [reviews, setReviews] = useState<ReviewTaskSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [workingId, setWorkingId] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [appliedSearch, setAppliedSearch] = useState("");
  const [activeStatus, setActiveStatus] = useState<ReviewStatusFilter | undefined>();
  const [hasLoaded, setHasLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getReviewHistory({ search: appliedSearch, status: activeStatus })
      .then((items) => {
        if (!cancelled) {
          setReviews(items);
          setError("");
        }
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof ApiError ? reason.message : "复习记录加载失败");
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
          setHasLoaded(true);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [appliedSearch, activeStatus]);

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

  if (!hasLoaded && loading) return <div className="page-wrap"><div className="loading-state">正在整理全部复习记录……</div></div>;
  if (!hasLoaded && error) return <div className="page-wrap"><ErrorState message={error} /></div>;

  const hasFilters = Boolean(appliedSearch || activeStatus);

  function handleSearchSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAppliedSearch(searchInput.trim());
  }

  return (
    <div className="page-wrap">
      <header className="page-header"><div><div className="eyebrow">Review log</div><h1 className="page-title">复习记录</h1><p className="page-description">所有书籍的答题任务都集中在这里。重新答题会更新原任务，不会额外创建一条记录。</p></div></header>
      {error && <div className="toast-error">{error}</div>}
      <div className="books-toolbar review-filters">
        <div className="review-filter-meta">
          <div className="tag-row">{statusFilters.map((filter) => <button className={`tag ${activeStatus === filter.value ? "active-filter" : ""}`} key={filter.label} onClick={() => setActiveStatus(filter.value)} type="button">{filter.label}</button>)}</div>
          <span>{loading ? "正在筛选……" : `${reviews.length} 条记录`}</span>
        </div>
        <form className="search-box" onSubmit={handleSearchSubmit}><Search size={15} /><input aria-label="按书名或作者搜索复习记录" placeholder="搜索书名或作者，按回车搜索" value={searchInput} onChange={(event) => setSearchInput(event.target.value)} /></form>
      </div>
      {reviews.length === 0 ? <EmptyState title={hasFilters ? "没有匹配的复习记录" : "还没有复习记录"} detail={hasFilters ? "换个书名、作者或状态试试。" : "从书籍详情页选择一套复习试卷，完成第一次复习后记录会出现在这里。"} action={hasFilters ? <button className="button button-secondary" onClick={() => { setSearchInput(""); setAppliedSearch(""); setActiveStatus(undefined); }} type="button">清除筛选</button> : undefined} /> : <div className="history-table-wrap"><table className="history-table"><thead><tr><th>书籍与试卷</th><th>状态</th><th>次数</th><th>得分率</th><th>题量</th><th>用时</th><th>时间</th><th>操作</th></tr></thead><tbody>{reviews.map((review) => {
        const percent = scorePercentage(review.total_score, review.max_score);
        const busy = workingId === review.id;
        return <tr key={review.id}><td><strong>{review.book_title}</strong><span className="table-subtext">{review.title}</span></td><td><StatusBadge status={review.status} /></td><td>第 {review.attempt_number} 次</td><td className={percent !== null && percent >= 60 ? "score-good" : "score-low"}>{percent === null ? "—" : `${percent}%`}</td><td>{review.question_count} 题</td><td>{formatDuration(review.elapsed_seconds)}</td><td>{formatDateTime(review.submitted_at || review.created_at)}</td><td><div className="table-actions">{review.status === "submitted" ? <Link aria-label="查看复习详情" className="button button-quiet" href={`/reviews/${review.id}/result`} title="查看复习详情"><Eye size={15} /></Link> : <Link aria-label="继续复习" className="button button-quiet" href={`/reviews/${review.id}`} title="继续复习"><Eye size={15} /></Link>}{review.status === "submitted" && <button aria-label="重新答题" className="button button-quiet" disabled={busy} onClick={() => void handleReopen(review)} title="重新答题" type="button"><RotateCcw size={15} /></button>}<button aria-label="删除记录" className="button button-quiet danger-action" disabled={busy} onClick={() => void handleDelete(review)} title="删除记录" type="button"><Trash2 size={15} /></button></div></td></tr>;
      })}</tbody></table></div>}
    </div>
  );
}
