"use client";

import { ArrowLeft, Eye, Plus } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { EmptyState, ErrorState, StatusBadge } from "@/components/ui";
import { ApiError, getBook, getHistory } from "@/lib/api";
import { formatDate, formatDateTime, formatDuration } from "@/lib/format";
import type { BookDetail, HistoryItem } from "@/lib/types";

export default function HistoryPage() {
  const params = useParams<{ bookId: string }>();
  const [book, setBook] = useState<BookDetail | null>(null);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([getBook(params.bookId), getHistory(params.bookId)])
      .then(([bookData, historyData]) => { setBook(bookData); setHistory(historyData); })
      .catch((reason: unknown) => setError(reason instanceof ApiError ? reason.message : "历史记录加载失败"))
      .finally(() => setLoading(false));
  }, [params.bookId]);

  if (loading) return <div className="page-wrap"><div className="loading-state">正在整理复习记录……</div></div>;
  if (!book) return <div className="page-wrap"><ErrorState message={error || "未找到这本书"} /></div>;

  return (
    <div className="page-wrap">
      <Link className="back-link" href={`/books/${book.id}`}><ArrowLeft size={14} />返回《{book.title}》</Link>
      <header className="page-header"><div><div className="eyebrow">Review history</div><h1 className="page-title">复习记录</h1><p className="page-description">{book.title} · 共完成 {book.stats.quiz_count} 次复习</p></div><Link className="button button-primary" href={`/books/${book.id}/quiz/new`}><Plus size={15} />创建复习题</Link></header>
      {error && <div className="toast-error">{error}</div>}
      {history.length === 0 ? <EmptyState title="还没有复习记录" detail="完成第一套复习后，得分、用时和复习建议会保存在这里。" action={<Link className="button button-primary" href={`/books/${book.id}/quiz/new`}>开始第一次复习</Link>} /> : <div className="history-table-wrap"><table className="history-table"><thead><tr><th>复习</th><th>状态</th><th>得分</th><th>题量</th><th>实际用时</th><th>完成时间</th><th>下次复习</th><th aria-label="操作" /></tr></thead><tbody>{history.map((item) => {
        const percent = item.total_score === null ? null : Math.round(item.total_score / item.max_score * 100);
        return <tr key={item.id}><td><strong>{item.title}</strong></td><td><StatusBadge status={item.status} /></td><td className={percent !== null && percent >= 60 ? "score-good" : "score-low"}>{percent === null ? "—" : `${percent} 分`}</td><td>{item.question_count} 题</td><td>{formatDuration(item.elapsed_seconds)}</td><td>{formatDateTime(item.submitted_at || item.created_at)}</td><td>{formatDate(item.next_review_date)}</td><td>{item.status === "submitted" && <Link aria-label="查看结果" className="button button-quiet" href={`/quizzes/${item.id}/result`} title="查看结果"><Eye size={15} /></Link>}</td></tr>;
      })}</tbody></table></div>}
    </div>
  );
}
