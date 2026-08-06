"use client";

import { Check, Copy, Eye, PauseCircle, PlayCircle, Search, Share2 } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";

import { EmptyState, ErrorState } from "@/components/ui";
import { ApiError, getExamShares, updateExamShare } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { ExamShare, ExamShareStatus } from "@/lib/types";

const filters: { label: string; value?: ExamShareStatus }[] = [
  { label: "全部" },
  { label: "分享中", value: "active" },
  { label: "已停止", value: "stopped" },
  { label: "已失效", value: "source_deleted" },
];

const statusLabels: Record<ExamShareStatus, string> = {
  active: "分享中",
  stopped: "已停止",
  source_deleted: "原试卷已删除",
  expired: "已过期",
};

export default function ExamManagementPage() {
  const [shares, setShares] = useState<ExamShare[]>([]);
  const [searchInput, setSearchInput] = useState("");
  const [appliedSearch, setAppliedSearch] = useState("");
  const [activeStatus, setActiveStatus] = useState<ExamShareStatus | undefined>();
  const [createdFrom, setCreatedFrom] = useState("");
  const [createdTo, setCreatedTo] = useState("");
  const [loading, setLoading] = useState(true);
  const [workingId, setWorkingId] = useState("");
  const [copiedId, setCopiedId] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setShares(await getExamShares({ search: appliedSearch, status: activeStatus, createdFrom, createdTo }));
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "考试活动加载失败");
    } finally {
      setLoading(false);
    }
  }, [activeStatus, appliedSearch, createdFrom, createdTo]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    if (!shares.some((share) => share.grading_count > 0)) return;
    const timer = window.setInterval(() => { void load(); }, 3000);
    return () => window.clearInterval(timer);
  }, [load, shares]);

  const totals = useMemo(() => ({
    active: shares.filter((share) => share.status === "active").length,
    started: shares.reduce((sum, share) => sum + share.started_count, 0),
    submitted: shares.reduce((sum, share) => sum + share.submitted_count, 0),
    grading: shares.reduce((sum, share) => sum + share.grading_count, 0),
  }), [shares]);

  function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAppliedSearch(searchInput.trim());
  }

  async function copyLink(share: ExamShare) {
    await navigator.clipboard.writeText(`${window.location.origin}/exams/${share.share_code}`);
    setCopiedId(share.id);
    window.setTimeout(() => setCopiedId(""), 1500);
  }

  async function toggleShare(share: ExamShare) {
    const nextStatus = share.status === "active" ? "stopped" : "active";
    if (nextStatus === "stopped" && !window.confirm(`停止“${share.name}”后，新的参与者将无法开始答题。确认停止吗？`)) return;
    setWorkingId(share.id);
    setError("");
    try {
      await updateExamShare(share.id, { status: nextStatus });
      await load();
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "考试状态更新失败");
    } finally {
      setWorkingId("");
    }
  }

  if (loading && shares.length === 0 && !error) return <div className="page-wrap"><div className="loading-state">正在读取考试活动……</div></div>;
  if (error && shares.length === 0) return <div className="page-wrap"><ErrorState message={error} /></div>;

  return (
    <div className="page-wrap">
      <header className="page-header"><div><div className="eyebrow">Exam management</div><h1 className="page-title">考试管理</h1><p className="page-description">管理分享出去的考试链接，查看参与进度和每份答卷的评分结果。</p></div></header>
      {error && <div className="toast-error">{error}</div>}

      <div className="metrics-grid exam-metrics">
        <div className="metric"><div className="metric-label">分享中的考试</div><div className="metric-value">{totals.active}<span className="metric-detail">场</span></div></div>
        <div className="metric"><div className="metric-label">开始答题</div><div className="metric-value">{totals.started}<span className="metric-detail">人次</span></div></div>
        <div className="metric"><div className="metric-label">已经交卷</div><div className="metric-value">{totals.submitted}<span className="metric-detail">份</span></div></div>
        <div className="metric"><div className="metric-label">正在评分</div><div className="metric-value">{totals.grading}<span className="metric-detail">份</span></div></div>
      </div>

      <div className="books-toolbar review-filters">
        <div className="review-filter-meta"><div className="tag-row">{filters.map((filter) => <button className={`tag ${activeStatus === filter.value ? "active-filter" : ""}`} key={filter.label} onClick={() => setActiveStatus(filter.value)} type="button">{filter.label}</button>)}</div><span>{loading ? "正在刷新……" : `${shares.length} 场考试`}</span></div>
        <div className="exam-list-filters"><label>开始日期<input aria-label="考试创建开始日期" max={createdTo || undefined} onChange={(event) => setCreatedFrom(event.target.value)} type="date" value={createdFrom} /></label><label>结束日期<input aria-label="考试创建结束日期" min={createdFrom || undefined} onChange={(event) => setCreatedTo(event.target.value)} type="date" value={createdTo} /></label><form className="search-box" onSubmit={handleSearch}><Search size={15} /><input aria-label="搜索考试、书籍或试卷" onChange={(event) => setSearchInput(event.target.value)} placeholder="搜索考试或书名，按回车搜索" value={searchInput} /></form></div>
      </div>

      {shares.length === 0 ? <EmptyState title="还没有分享考试" detail="从书籍详情页选择一套复习试卷，点击分享按钮即可创建考试链接。" /> : <div className="exam-table-wrap"><table className="exam-table exam-management-table"><thead><tr><th>考试活动</th><th>状态</th><th>答题进度</th><th>成绩</th><th>最近提交</th><th>操作</th></tr></thead><tbody>{shares.map((share) => <tr key={share.id}>
        <td><div className="exam-cell-stack"><strong>{share.name}</strong><span>{share.book_title} · {share.quiz_title}</span><small>单选 {share.single_count} · 多选 {share.multiple_count} · 问答 {share.short_count}</small></div></td>
        <td><div className="exam-cell-stack"><span className={`exam-status exam-status-${share.status}`}>{statusLabels[share.status]}</span>{share.grading_failed_count > 0 && <small className="score-low">{share.grading_failed_count} 份评分失败</small>}</div></td>
        <td><div className="exam-cell-stack"><strong>{share.submitted_count} / {share.started_count}</strong><span>完成率 {share.completion_rate}%</span></div></td>
        <td><div className="exam-cell-stack"><strong>{share.average_score === null ? "暂无" : `${share.average_score}%`}</strong><span>最高 {share.highest_score === null ? "暂无" : `${share.highest_score}%`}</span></div></td>
        <td>{formatDateTime(share.last_attempt_at)}</td>
        <td><div className="table-actions"><button aria-label="复制考试链接" className="button button-quiet" onClick={() => void copyLink(share)} title="复制链接" type="button">{copiedId === share.id ? <Check size={15} /> : <Copy size={15} />}</button><Link aria-label="查看考试详情" className="button button-quiet" href={`/exam-management/${share.id}`} title="查看详情"><Eye size={15} /></Link>{share.status === "active" || share.status === "stopped" ? <button aria-label={share.status === "active" ? "停止分享" : "恢复分享"} className="button button-quiet" disabled={workingId === share.id} onClick={() => void toggleShare(share)} title={share.status === "active" ? "停止分享" : "恢复分享"} type="button">{share.status === "active" ? <PauseCircle size={15} /> : <PlayCircle size={15} />}</button> : <Share2 size={15} className="exam-disabled-icon" />}</div></td>
      </tr>)}</tbody></table></div>}
    </div>
  );
}
