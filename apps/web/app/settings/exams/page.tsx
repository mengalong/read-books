"use client";

import { Eye, Search, UserRound } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";

import { EmptyState, ErrorState } from "@/components/ui";
import { ApiError, getAdminExamShares, getAdminUsers } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { AdminUser, ExamShare, ExamShareStatus } from "@/lib/types";

const statusLabels: Record<ExamShareStatus, string> = {
  active: "分享中",
  stopped: "已停止",
  source_deleted: "原试卷已删除",
  expired: "已过期",
};

export default function AdminExamManagementPage() {
  const [shares, setShares] = useState<ExamShare[]>([]);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [searchInput, setSearchInput] = useState("");
  const [appliedSearch, setAppliedSearch] = useState("");
  const [ownerId, setOwnerId] = useState("");
  const [shareStatus, setShareStatus] = useState<"" | ExamShareStatus>("");
  const [createdFrom, setCreatedFrom] = useState("");
  const [createdTo, setCreatedTo] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [shareItems, userItems] = await Promise.all([
        getAdminExamShares({ search: appliedSearch, ownerId: ownerId || undefined, status: shareStatus || undefined, createdFrom, createdTo }),
        getAdminUsers(),
      ]);
      setShares(shareItems);
      setUsers(userItems);
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "全平台考试数据加载失败");
    } finally {
      setLoading(false);
    }
  }, [appliedSearch, createdFrom, createdTo, ownerId, shareStatus]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    if (!shares.some((share) => share.grading_count > 0)) return;
    const timer = window.setInterval(() => { void load(); }, 3500);
    return () => window.clearInterval(timer);
  }, [load, shares]);

  const totals = useMemo(() => ({
    owners: new Set(shares.map((share) => share.owner_user_id)).size,
    started: shares.reduce((sum, share) => sum + share.started_count, 0),
    submitted: shares.reduce((sum, share) => sum + share.submitted_count, 0),
    failed: shares.reduce((sum, share) => sum + share.grading_failed_count, 0),
  }), [shares]);

  function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAppliedSearch(searchInput.trim());
  }

  if (loading && shares.length === 0 && !error) return <div className="page-wrap"><div className="loading-state">正在读取全平台考试……</div></div>;
  if (error && shares.length === 0) return <div className="page-wrap"><ErrorState message={error} /></div>;

  return <div className="page-wrap">
    <header className="page-header"><div><div className="eyebrow">System management</div><h1 className="page-title">考试管理</h1><p className="page-description">查看所有用户创建的分享考试及参与结果。管理员跨用户访问会写入审计记录。</p></div></header>
    {error && <div className="toast-error">{error}</div>}
    <div className="metrics-grid exam-metrics"><div className="metric"><div className="metric-label">考试活动</div><div className="metric-value">{shares.length}<span className="metric-detail">场</span></div></div><div className="metric"><div className="metric-label">分享用户</div><div className="metric-value">{totals.owners}<span className="metric-detail">人</span></div></div><div className="metric"><div className="metric-label">已交答卷</div><div className="metric-value">{totals.submitted}<span className="metric-detail">份</span></div></div><div className="metric"><div className="metric-label">评分失败</div><div className={`metric-value ${totals.failed ? "score-low" : ""}`}>{totals.failed}<span className="metric-detail">份</span></div></div></div>
    <div className="admin-book-toolbar"><form className="search-box" onSubmit={handleSearch}><Search size={15} /><input aria-label="搜索考试、书籍或试卷" onChange={(event) => setSearchInput(event.target.value)} placeholder="搜索考试或书名，按回车搜索" value={searchInput} /></form><div className="admin-book-filters"><label className="admin-owner-filter">开始日期<input max={createdTo || undefined} onChange={(event) => setCreatedFrom(event.target.value)} type="date" value={createdFrom} /></label><label className="admin-owner-filter">结束日期<input min={createdFrom || undefined} onChange={(event) => setCreatedTo(event.target.value)} type="date" value={createdTo} /></label><label className="admin-owner-filter">活动状态<select onChange={(event) => setShareStatus(event.target.value as "" | ExamShareStatus)} value={shareStatus}><option value="">全部状态</option><option value="active">分享中</option><option value="stopped">已停止</option><option value="source_deleted">原试卷已删除</option><option value="expired">已过期</option></select></label><label className="admin-owner-filter">分享用户<select onChange={(event) => setOwnerId(event.target.value)} value={ownerId}><option value="">全部用户</option>{users.map((user) => <option key={user.id} value={user.id}>{user.display_name}（{user.username}）</option>)}</select></label></div></div>
    {shares.length === 0 ? <EmptyState title="没有匹配的考试" detail="调整搜索词、活动状态或分享用户后再试。" /> : <div className="exam-table-wrap"><table className="exam-table admin-exam-table"><thead><tr><th>考试活动</th><th>分享用户</th><th>状态</th><th>答题情况</th><th>平均得分率</th><th>最近提交</th><th>操作</th></tr></thead><tbody>{shares.map((share) => <tr key={share.id}><td><div className="exam-cell-stack"><strong>{share.name}</strong><span>{share.book_title} · {share.quiz_title}</span></div></td><td><div className="exam-cell-stack"><span className="participant-type"><UserRound size={13} />{share.owner_display_name}</span><small>{share.owner_username}</small></div></td><td><div className="exam-cell-stack"><span className={`exam-status exam-status-${share.status}`}>{statusLabels[share.status]}</span>{share.grading_failed_count > 0 && <small className="score-low">{share.grading_failed_count} 份评分失败</small>}</div></td><td><div className="exam-cell-stack"><strong>{share.submitted_count} / {share.started_count}</strong><span>完成率 {share.completion_rate}%</span></div></td><td>{share.average_score === null ? "—" : `${share.average_score}%`}</td><td>{formatDateTime(share.last_attempt_at)}</td><td><Link aria-label="查看考试详情" className="button button-quiet" href={`/settings/exams/${share.id}`} title="查看详情"><Eye size={15} /></Link></td></tr>)}</tbody></table></div>}
  </div>;
}
