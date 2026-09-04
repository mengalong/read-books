"use client";

import { ArrowLeft, BarChart3, CalendarDays, Check, ChevronLeft, ChevronRight, CircleX, Copy, Download, Eye, LoaderCircle, Monitor, PencilLine, RefreshCw, RotateCcw, Search, ShieldAlert, Smartphone, Tablet, UserRound, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { ExamAttemptReport } from "@/components/exam-attempt-report";
import { EmptyState, ErrorState, EvidenceList } from "@/components/ui";
import { ExamLearningAnalysis } from "@/components/exam-learning-analysis";
import { ApiError, getAdminExamAttempt, getAdminExamShare, getExamAttemptForOwner, getExamShare, retryAdminExamAttemptGrading, retryExamAttemptGrading } from "@/lib/api";
import { copyText } from "@/lib/clipboard";
import { downloadElementAsPng } from "@/lib/export-image";
import { formatDateTime, formatDuration, formatScore } from "@/lib/format";
import type { ExamAttempt, ExamAttemptStatus, ExamAttemptSummary, ExamDeviceType, ExamParticipationGranularity, ExamParticipationPeriod, ExamQuestion, ExamShare, ExamShareStatus } from "@/lib/types";

const ATTEMPTS_PAGE_SIZE = 20;
const ATTEMPTS_PAGE_SIZES = [20, 50, 100, 200] as const;
type AttemptPageSize = (typeof ATTEMPTS_PAGE_SIZES)[number];
type AttemptStatusFilter = "" | ExamAttemptStatus;
type AttemptSort = "latest" | "score_desc" | "score_asc";

function isAttemptStatus(value: string): value is ExamAttemptStatus {
  return ["in_progress", "grading", "completed", "grading_failed"].includes(value);
}

function isAttemptSort(value: string): value is AttemptSort {
  return ["latest", "score_desc", "score_asc"].includes(value);
}

function isAttemptPageSize(value: string): value is `${AttemptPageSize}` {
  return ATTEMPTS_PAGE_SIZES.some((item) => String(item) === value);
}

function isParticipationGranularity(value: string): value is ExamParticipationGranularity {
  return ["month", "year"].includes(value);
}

const statusLabels: Record<ExamShareStatus, string> = {
  active: "分享中",
  stopped: "已停止",
  source_deleted: "原试卷已删除",
  expired: "已过期",
};

const attemptStatusLabels: Record<ExamAttemptSummary["status"], string> = {
  in_progress: "答题中",
  grading: "评分中",
  completed: "已完成",
  grading_failed: "评分失败",
};

const deviceTypeLabels: Record<ExamDeviceType, string> = {
  desktop: "电脑",
  mobile: "手机",
  tablet: "平板",
  unknown: "未知终端",
};

export function ExamShareDetailView({ shareId, admin = false }: { shareId: string; admin?: boolean }) {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const initialPage = Math.max(1, Number(searchParams.get("page") || 1) || 1);
  const initialStatusParam = searchParams.get("status") || "";
  const initialStatus: AttemptStatusFilter = isAttemptStatus(initialStatusParam) ? initialStatusParam : "";
  const initialSortParam = searchParams.get("sort") || "latest";
  const initialSort: AttemptSort = isAttemptSort(initialSortParam) ? initialSortParam : "latest";
  const initialSearch = searchParams.get("search") || "";
  const initialPageSizeParam = searchParams.get("page_size") || String(ATTEMPTS_PAGE_SIZE);
  const initialPageSize: AttemptPageSize = isAttemptPageSize(initialPageSizeParam) ? Number(initialPageSizeParam) as AttemptPageSize : ATTEMPTS_PAGE_SIZE;
  const currentCalendarDate = new Date();
  const initialGranularityParam = searchParams.get("granularity") || "month";
  const initialGranularity: ExamParticipationGranularity = isParticipationGranularity(initialGranularityParam) ? initialGranularityParam : "month";
  const initialYearParam = Number(searchParams.get("participation_year"));
  const initialYear = Number.isInteger(initialYearParam) && initialYearParam >= 1 ? initialYearParam : currentCalendarDate.getFullYear();
  const initialMonthParam = Number(searchParams.get("participation_month"));
  const initialMonth = Number.isInteger(initialMonthParam) && initialMonthParam >= 1 && initialMonthParam <= 12 ? initialMonthParam : currentCalendarDate.getMonth() + 1;
  const [share, setShare] = useState<ExamShare | null>(null);
  const [selectedAttempt, setSelectedAttempt] = useState<ExamAttempt | null>(null);
  const [loading, setLoading] = useState(true);
  const [attemptsLoading, setAttemptsLoading] = useState(false);
  const [attemptLoading, setAttemptLoading] = useState(false);
  const [exportingAttemptId, setExportingAttemptId] = useState<string | null>(null);
  const [reportAttempt, setReportAttempt] = useState<ExamAttempt | null>(null);
  const [retrying, setRetrying] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState("");
  const [attemptPage, setAttemptPage] = useState(initialPage);
  const [attemptStatus, setAttemptStatus] = useState<AttemptStatusFilter>(initialStatus);
  const [attemptSort, setAttemptSort] = useState<AttemptSort>(initialSort);
  const [attemptSearch, setAttemptSearch] = useState(initialSearch);
  const [searchInput, setSearchInput] = useState(initialSearch);
  const [attemptPageSize, setAttemptPageSize] = useState<AttemptPageSize>(initialPageSize);
  const [participationGranularity, setParticipationGranularity] = useState<ExamParticipationGranularity>(initialGranularity);
  const [participationYear, setParticipationYear] = useState(initialYear);
  const [participationMonth, setParticipationMonth] = useState(initialMonth);
  const reportRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const nextPage = Math.max(1, Number(searchParams.get("page") || 1) || 1);
    const nextStatusParam = searchParams.get("status") || "";
    const nextStatus: AttemptStatusFilter = isAttemptStatus(nextStatusParam) ? nextStatusParam : "";
    const nextSortParam = searchParams.get("sort") || "latest";
    const nextSort: AttemptSort = isAttemptSort(nextSortParam) ? nextSortParam : "latest";
    const nextSearch = searchParams.get("search") || "";
    const nextPageSizeParam = searchParams.get("page_size") || String(ATTEMPTS_PAGE_SIZE);
    const nextPageSize: AttemptPageSize = isAttemptPageSize(nextPageSizeParam) ? Number(nextPageSizeParam) as AttemptPageSize : ATTEMPTS_PAGE_SIZE;
    const nextGranularityParam = searchParams.get("granularity") || "month";
    const nextGranularity: ExamParticipationGranularity = isParticipationGranularity(nextGranularityParam) ? nextGranularityParam : "month";
    const nextYearParam = Number(searchParams.get("participation_year"));
    const nextYear = Number.isInteger(nextYearParam) && nextYearParam >= 1 ? nextYearParam : new Date().getFullYear();
    const nextMonthParam = Number(searchParams.get("participation_month"));
    const nextMonth = Number.isInteger(nextMonthParam) && nextMonthParam >= 1 && nextMonthParam <= 12 ? nextMonthParam : new Date().getMonth() + 1;
    setAttemptPage(nextPage);
    setAttemptStatus(nextStatus);
    setAttemptSort(nextSort);
    setAttemptSearch(nextSearch);
    setSearchInput(nextSearch);
    setAttemptPageSize(nextPageSize);
    setParticipationGranularity(nextGranularity);
    setParticipationYear(nextYear);
    setParticipationMonth(nextMonth);
  }, [searchParams]);

  function updateAttemptUrl(
    page: number,
    status: AttemptStatusFilter,
    sort: AttemptSort,
    search: string = attemptSearch,
    pageSize: AttemptPageSize = attemptPageSize,
    granularity: ExamParticipationGranularity = participationGranularity,
    year: number = participationYear,
    month: number = participationMonth,
  ) {
    const params = new URLSearchParams(searchParams.toString());
    if (page > 1) params.set("page", String(page)); else params.delete("page");
    if (status) params.set("status", status); else params.delete("status");
    if (sort !== "latest") params.set("sort", sort); else params.delete("sort");
    if (search) params.set("search", search); else params.delete("search");
    if (pageSize !== ATTEMPTS_PAGE_SIZE) params.set("page_size", String(pageSize)); else params.delete("page_size");
    if (granularity !== "month") params.set("granularity", granularity); else params.delete("granularity");
    params.set("participation_year", String(year));
    if (granularity === "month") params.set("participation_month", String(month)); else params.delete("participation_month");
    const query = params.toString();
    router.replace(`${pathname}${query ? `?${query}` : ""}`, { scroll: false });
  }

  const load = useCallback(async () => {
    setError("");
    setAttemptsLoading(true);
    try {
      const options = {
        ...(attemptPage > 1 ? { page: attemptPage } : {}),
        ...(attemptPageSize !== ATTEMPTS_PAGE_SIZE ? { pageSize: attemptPageSize } : {}),
        ...(attemptStatus ? { status: attemptStatus } : {}),
        ...(attemptSort !== "latest" ? { sort: attemptSort } : {}),
        ...(attemptSearch ? { search: attemptSearch } : {}),
        participationGranularity,
        participationYear,
        ...(participationGranularity === "month" ? { participationMonth } : {}),
      };
      const nextShare = await (admin ? getAdminExamShare(shareId, options) : getExamShare(shareId, options));
      setShare(nextShare);
      if (nextShare.participation_granularity) setParticipationGranularity(nextShare.participation_granularity);
      if (nextShare.participation_year) setParticipationYear(nextShare.participation_year);
      if (nextShare.participation_month) setParticipationMonth(nextShare.participation_month);
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "考试详情加载失败");
    } finally {
      setLoading(false);
      setAttemptsLoading(false);
    }
  }, [admin, attemptPage, attemptPageSize, attemptSearch, attemptSort, attemptStatus, participationGranularity, participationMonth, participationYear, shareId]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    if (!share?.grading_count) return;
    const timer = window.setInterval(() => { void load(); }, 2500);
    return () => window.clearInterval(timer);
  }, [load, share?.grading_count]);
  useEffect(() => {
    if (selectedAttempt?.status !== "grading") return;
    const attemptId = selectedAttempt.id;
    const refresh = async () => {
      try {
        const nextAttempt = await (admin ? getAdminExamAttempt(shareId, attemptId) : getExamAttemptForOwner(shareId, attemptId));
        setSelectedAttempt((currentAttempt) => currentAttempt?.id === attemptId ? nextAttempt : currentAttempt);
      } catch {
        // Keep the current answer visible; the manual refresh action reports request errors.
      }
    };
    const timer = window.setInterval(() => { void refresh(); }, 2500);
    return () => window.clearInterval(timer);
  }, [admin, selectedAttempt?.id, selectedAttempt?.status, shareId]);

  async function copyLink() {
    if (!share) return;
    setError("");
    try {
      await copyText(`${window.location.origin}/exams/${share.share_code}`);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setError("链接复制失败，请手动选择下方分享链接进行复制");
    }
  }

  async function openAttempt(attemptId: string) {
    setAttemptLoading(true);
    setError("");
    try {
      setSelectedAttempt(await (admin ? getAdminExamAttempt(shareId, attemptId) : getExamAttemptForOwner(shareId, attemptId)));
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "答卷详情加载失败");
    } finally {
      setAttemptLoading(false);
    }
  }

  async function retryGrading() {
    if (!selectedAttempt) return;
    setRetrying(true);
    setError("");
    try {
      setSelectedAttempt(await (admin ? retryAdminExamAttemptGrading(shareId, selectedAttempt.id) : retryExamAttemptGrading(shareId, selectedAttempt.id)));
      await load();
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "重新评分失败");
    } finally {
      setRetrying(false);
    }
  }

  async function exportAttempt(attemptId: string) {
    setExportingAttemptId(attemptId);
    setError("");
    try {
      const attempt = selectedAttempt?.id === attemptId
        ? selectedAttempt
        : await (admin ? getAdminExamAttempt(shareId, attemptId) : getExamAttemptForOwner(shareId, attemptId));
      setReportAttempt(attempt);
      await waitForReportRender();
      if (!reportRef.current) throw new Error("报告内容尚未完成渲染");
      await downloadElementAsPng(reportRef.current, `${attempt.exam_name}-${attempt.participant_name}-答题报告`);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "答题报告导出失败");
    } finally {
      setExportingAttemptId(null);
      setReportAttempt(null);
    }
  }

  if (loading) return <div className="page-wrap"><div className="loading-state">正在读取考试详情……</div></div>;
  if (!share) return <div className="page-wrap"><ErrorState message={error || "未找到这个考试活动"} /></div>;

  const attempts = share.attempts || [];
  const attemptsTotal = share.attempts_total ?? share.started_count;
  const attemptsPage = share.attempts_page ?? attemptPage;
  const attemptsPageSize = share.attempts_page_size ?? ATTEMPTS_PAGE_SIZE;
  const totalAttemptPages = Math.max(1, Math.ceil(attemptsTotal / attemptsPageSize));
  const hasAttemptFilter = Boolean(attemptStatus || attemptSearch);

  return (
    <div className="page-wrap">
      <Link className="back-link" href={admin ? "/settings/exams" : "/exam-management"}><ArrowLeft size={14} />返回{admin ? "全平台考试" : "考试管理"}</Link>
      {error && <div className="toast-error">{error}</div>}
      <header className="exam-detail-header">
        <div><div className="eyebrow">Exam detail</div><h1 className="page-title">{share.name}</h1><p className="page-description">{share.book_title} · {share.quiz_title}{admin ? ` · 分享者：${share.owner_display_name}（${share.owner_username}）` : ""}</p></div>
        <div className="header-actions"><span className={`exam-status exam-status-${share.status}`}>{statusLabels[share.status]}</span><Link className="button button-secondary" href={`/exam-management/${share.id}/edit`}><PencilLine size={15} />编辑题目</Link><button className="button button-secondary" onClick={() => void copyLink()} type="button">{copied ? <Check size={15} /> : <Copy size={15} />}{copied ? "已复制" : "复制链接"}</button></div>
      </header>

      <div className="share-link-strip"><span>{`${typeof window === "undefined" ? "" : window.location.origin}/exams/${share.share_code}`}</span><small>创建于 {formatDateTime(share.created_at)} · {share.expires_at ? `截止 ${formatDateTime(share.expires_at)}` : "长期有效"}</small></div>

      <div className="metrics-grid exam-detail-metrics">
        <div className="metric"><div className="metric-label">开始答题</div><div className="metric-value">{share.started_count}<span className="metric-detail">人次</span></div></div>
        <div className="metric"><div className="metric-label">已经交卷</div><div className="metric-value">{share.submitted_count}<span className="metric-detail">份</span></div></div>
        <div className="metric"><div className="metric-label">完成率</div><div className="metric-value">{share.completion_rate}<span className="metric-detail">%</span></div></div>
        <div className="metric"><div className="metric-label">已完成评分</div><div className="metric-value">{share.graded_count ?? 0}<span className="metric-detail">份</span></div></div>
        <div className="metric"><div className="metric-label">平均分</div><div className="metric-value">{share.average_points === null || share.average_points === undefined ? "—" : formatScore(share.average_points)}<span className="metric-detail">/ {formatScore(share.max_score)} 分</span></div></div>
        <div className="metric"><div className="metric-label">中位数分数</div><div className="metric-value">{share.median_points === null || share.median_points === undefined ? "—" : formatScore(share.median_points)}<span className="metric-detail">/ {formatScore(share.max_score)} 分</span></div></div>
      </div>

      <ExamAnalyticsPanel
        distribution={share.score_distribution || []}
        gradedCount={share.graded_count || 0}
        aboveThresholdCount={share.above_threshold_count || 0}
        aboveThresholdRate={share.above_threshold_rate ?? null}
        participationGranularity={participationGranularity}
        participationYear={participationYear}
        participationMonth={participationMonth}
        participationPeriods={share.participation_periods || []}
        onGranularityChange={(next) => {
          setParticipationGranularity(next);
          updateAttemptUrl(1, attemptStatus, attemptSort, attemptSearch, attemptPageSize, next, participationYear, participationMonth);
        }}
        onYearChange={(next) => {
          setParticipationYear(next);
          setAttemptPage(1);
          updateAttemptUrl(1, attemptStatus, attemptSort, attemptSearch, attemptPageSize, participationGranularity, next, participationMonth);
        }}
        onMonthChange={(next) => {
          setParticipationMonth(next);
          setAttemptPage(1);
          updateAttemptUrl(1, attemptStatus, attemptSort, attemptSearch, attemptPageSize, participationGranularity, participationYear, next);
        }}
      />

      <section className="content-panel exam-attempt-panel">
        <div className="section-title attempt-table-heading"><div><h2>答题记录</h2><span>{hasAttemptFilter ? `${attemptsTotal} 份匹配记录` : `${share.graded_count || 0} 份已完成评分 · ${share.grading_count} 份评分中`}</span></div><div className="attempt-table-controls"><form className="attempt-search-form" onSubmit={(event) => { event.preventDefault(); const next = searchInput.trim(); setAttemptSearch(next); setAttemptPage(1); updateAttemptUrl(1, attemptStatus, attemptSort, next, attemptPageSize, participationGranularity); }}><label className="attempt-search-field"><Search aria-hidden="true" size={14} /><span className="visually-hidden">搜索参与者名称或 IP</span><input aria-label="搜索参与者名称或 IP" onChange={(event) => setSearchInput(event.target.value)} placeholder="参与者名称或 IP" value={searchInput} /></label><button aria-label="搜索答题记录" className="button button-secondary" title="搜索答题记录" type="submit"><Search size={15} />搜索</button>{attemptSearch && <button aria-label="清除答题记录搜索" className="button button-quiet" onClick={() => { setSearchInput(""); setAttemptSearch(""); setAttemptPage(1); updateAttemptUrl(1, attemptStatus, attemptSort, "", attemptPageSize, participationGranularity); }} title="清除搜索" type="button"><X size={15} /></button>}</form><label>状态<select aria-label="按答卷状态筛选" onChange={(event) => { const next = event.target.value as AttemptStatusFilter; setAttemptStatus(next); setAttemptPage(1); updateAttemptUrl(1, next, attemptSort, attemptSearch, attemptPageSize, participationGranularity); }} value={attemptStatus}><option value="">全部状态</option><option value="in_progress">答题中</option><option value="grading">评分中</option><option value="completed">已完成</option><option value="grading_failed">评分失败</option></select></label><label>排序<select aria-label="答卷排序" onChange={(event) => { const next = event.target.value as AttemptSort; setAttemptSort(next); setAttemptPage(1); updateAttemptUrl(1, attemptStatus, next, attemptSearch, attemptPageSize, participationGranularity); }} value={attemptSort}><option value="latest">最近提交</option><option value="score_desc">得分从高到低</option><option value="score_asc">得分从低到高</option></select></label><label>每页<select aria-label="每页显示记录数" onChange={(event) => { const next = Number(event.target.value) as AttemptPageSize; setAttemptPageSize(next); setAttemptPage(1); updateAttemptUrl(1, attemptStatus, attemptSort, attemptSearch, next, participationGranularity); }} value={attemptPageSize}>{ATTEMPTS_PAGE_SIZES.map((size) => <option key={size} value={size}>{size} 条</option>)}</select></label></div></div>
        {!attempts.length ? <EmptyState title={hasAttemptFilter ? "没有符合条件的答卷" : "还没有参与者"} detail={hasAttemptFilter ? "调整搜索词或筛选条件后再试。" : "分享链接被打开并开始答题后，记录会出现在这里。"} /> : <div className={`exam-table-wrap${attemptsLoading ? " is-refreshing" : ""}`}><table className="exam-table attempt-table"><thead><tr><th>参与者</th><th>身份</th><th>终端 / IP</th><th>状态</th><th>得分</th><th>用时</th><th>开始时间</th><th>提交时间</th><th className="attempt-actions-cell">操作</th></tr></thead><tbody>{attempts.map((attempt) => <tr key={attempt.id}>
          <td><div className="attempt-participant-cell"><span className="participant-avatar">{attempt.participant_avatar_url ? <img alt="" src={attempt.participant_avatar_url} /> : <UserRound size={14} />}</span><strong>{attempt.participant_name}</strong></div></td>
          <td><span className={`participant-type ${attempt.participant_type === "wechat" ? "wechat" : ""}`}><UserRound size={13} />{attempt.participant_type === "user" ? "平台用户" : attempt.participant_type === "wechat" ? "微信认证" : "匿名参与者"}</span></td>
          <td><div className="attempt-device-cell"><span>{deviceIcon(attempt.device_type)}{attempt.device_type ? deviceTypeLabels[attempt.device_type] : "历史记录未采集"}</span><small>{attempt.started_ip_address || "IP 未采集"}</small>{attempt.ip_changed && <small className="ip-change-warning"><ShieldAlert size={11} />提交 IP 已变化</small>}</div></td>
          <td><div className="exam-cell-stack"><span className={`exam-status attempt-status-${attempt.status}`}>{attemptStatusLabels[attempt.status]}</span>{attempt.grading_error && <small className="score-low" title={attempt.grading_error}>需要重新评分</small>}</div></td>
          <td className={`attempt-score-cell ${attempt.score_percentage !== null && attempt.score_percentage < 60 ? "score-low" : "score-good"}`}>{attempt.total_score === null ? "—" : `${formatScore(attempt.total_score)} / ${formatScore(attempt.max_score)}`}</td>
          <td>{formatDuration(attempt.elapsed_seconds)}</td><td>{formatDateTime(attempt.started_at)}</td><td>{formatDateTime(attempt.submitted_at)}</td>
          <td className="attempt-actions-cell"><div className="attempt-action-buttons"><button aria-label={`查看${attempt.participant_name}的答卷`} className="button button-quiet" disabled={attemptLoading} onClick={() => void openAttempt(attempt.id)} title="查看答卷" type="button"><Eye size={15} /></button>{attempt.status === "completed" && <button aria-label={`下载${attempt.participant_name}的答题报告`} className="button button-quiet" disabled={exportingAttemptId !== null} onClick={() => void exportAttempt(attempt.id)} title="下载报告长图" type="button">{exportingAttemptId === attempt.id ? <LoaderCircle className="spin" size={15} /> : <Download size={15} />}</button>}</div></td>
        </tr>)}</tbody></table></div>}
        {attemptsTotal > 0 && <div className="attempt-pagination"><span aria-live="polite">{attemptsLoading ? "正在刷新…" : `第 ${attemptsPage} / ${totalAttemptPages} 页 · 共 ${attemptsTotal} 份`}</span><div><button aria-label="上一页" className="button button-quiet" disabled={attemptsPage <= 1 || attemptsLoading} onClick={() => { const next = attemptsPage - 1; setAttemptPage(next); updateAttemptUrl(next, attemptStatus, attemptSort, attemptSearch, attemptPageSize, participationGranularity); }} title="上一页" type="button"><ChevronLeft size={16} /></button><button aria-label="下一页" className="button button-quiet" disabled={attemptsPage >= totalAttemptPages || attemptsLoading} onClick={() => { const next = attemptsPage + 1; setAttemptPage(next); updateAttemptUrl(next, attemptStatus, attemptSort, attemptSearch, attemptPageSize, participationGranularity); }} title="下一页" type="button"><ChevronRight size={16} /></button></div></div>}
      </section>

      {selectedAttempt && <div className="modal-backdrop attempt-modal-backdrop" onMouseDown={(event) => { if (event.currentTarget === event.target) setSelectedAttempt(null); }} role="presentation"><section aria-labelledby="attempt-detail-title" aria-modal="true" className="modal-panel attempt-detail-modal" role="dialog">
        <div className="modal-heading"><div><span className="eyebrow">Answer detail</span><h2 id="attempt-detail-title">{selectedAttempt.participant_name}的答卷</h2></div><button aria-label="关闭答卷详情" className="modal-close" onClick={() => setSelectedAttempt(null)} title="关闭" type="button"><X size={18} /></button></div>
        <div className="attempt-summary-strip"><span>{attemptStatusLabels[selectedAttempt.status]}</span><strong>{formatScore(selectedAttempt.total_score)} / {formatScore(selectedAttempt.max_score)} 分</strong><span>用时 {formatDuration(selectedAttempt.elapsed_seconds)}</span></div>
        <div className="attempt-security-strip">
          <div><span>答题终端</span><strong>{deviceIcon(selectedAttempt.device_type)}{selectedAttempt.device_type ? deviceTypeLabels[selectedAttempt.device_type] : "历史记录未采集"}</strong></div>
          <div><span>开始 IP</span><strong>{selectedAttempt.started_ip_address || "未采集"}</strong></div>
          <div><span>提交 IP</span><strong className={selectedAttempt.ip_changed ? "score-low" : ""}>{selectedAttempt.submitted_ip_address || "未采集"}{selectedAttempt.ip_changed && <ShieldAlert size={13} />}</strong></div>
        </div>
        {selectedAttempt.user_agent && <details className="attempt-user-agent"><summary>查看浏览器终端信息</summary><code>{selectedAttempt.user_agent}</code></details>}
        {selectedAttempt.status === "grading_failed" && <div className="toast-error">{selectedAttempt.grading_error || "问答题评分失败。"}<button className="button button-secondary" disabled={retrying} onClick={() => void retryGrading()} type="button"><RotateCcw size={14} />{retrying ? "正在重试……" : "重新评分"}</button></div>}
        {selectedAttempt.status === "grading" && <div className="grading-state"><LoaderCircle className="spin" size={18} />问答题正在评分，结果会自动更新。</div>}
        {selectedAttempt.status === "completed" && <ExamLearningAnalysis recommendedDirection={selectedAttempt.recommended_direction} weakPoints={selectedAttempt.weak_knowledge_points || []} />}
        <div className="attempt-question-list">{selectedAttempt.questions.map((question, index) => <AttemptQuestion key={question.id} question={question} answer={selectedAttempt.answers.find((item) => item.question_id === question.id)} index={index} sourceMode={selectedAttempt.source_mode} />)}</div>
        <div className="modal-actions"><button className="button button-secondary" onClick={() => setSelectedAttempt(null)} type="button">关闭</button>{selectedAttempt.status === "completed" && <button className="button button-secondary" disabled={exportingAttemptId !== null} onClick={() => void exportAttempt(selectedAttempt.id)} type="button">{exportingAttemptId === selectedAttempt.id ? <LoaderCircle className="spin" size={15} /> : <Download size={15} />}导出报告</button>}<button aria-label="刷新答卷" className="button button-primary" onClick={() => void openAttempt(selectedAttempt.id)} type="button"><RefreshCw size={15} />刷新结果</button></div>
      </section></div>}
      {reportAttempt && <ExamAttemptReport attempt={reportAttempt} includeSecurity ref={reportRef} />}
    </div>
  );
}

function waitForReportRender() {
  return new Promise<void>((resolve) => {
    window.requestAnimationFrame(() => window.requestAnimationFrame(() => resolve()));
  });
}

function deviceIcon(deviceType: ExamDeviceType | null) {
  if (deviceType === "mobile") return <Smartphone aria-hidden="true" size={13} />;
  if (deviceType === "tablet") return <Tablet aria-hidden="true" size={13} />;
  return <Monitor aria-hidden="true" size={13} />;
}

function ExamAnalyticsPanel({ distribution, gradedCount, aboveThresholdCount, aboveThresholdRate, participationGranularity, participationYear, participationMonth, participationPeriods, onGranularityChange, onYearChange, onMonthChange }: { distribution: { label: string; min_score: number; max_score: number; count: number; percentage: number }[]; gradedCount: number; aboveThresholdCount: number; aboveThresholdRate: number | null; participationGranularity: ExamParticipationGranularity; participationYear: number; participationMonth: number; participationPeriods: ExamParticipationPeriod[]; onGranularityChange: (value: ExamParticipationGranularity) => void; onYearChange: (value: number) => void; onMonthChange: (value: number) => void }) {
  const participationTotals = participationPeriods.reduce(
    (totals, period) => ({
      participants: totals.participants + period.participant_count,
      completed: totals.completed + period.completed_count,
    }),
    { participants: 0, completed: 0 },
  );
  const calendarCells = buildParticipationCalendar(participationGranularity, participationYear, participationMonth, participationPeriods);
  return (
    <div className="exam-analytics-grid">
      <section className="content-panel exam-analytics-card participation-analytics-card">
        <div className="section-title"><div><h2><CalendarDays size={17} />参与考试人数</h2><span>{participationGranularity === "month" ? `${participationYear} 年 ${participationMonth} 月` : `${participationYear} 年`}</span></div><div className="analytics-filters"><label>统计方式<select aria-label="参与人数统计方式" onChange={(event) => onGranularityChange(event.target.value as ExamParticipationGranularity)} value={participationGranularity}><option value="month">按月</option><option value="year">按年</option></select></label><label>年份<select aria-label="参与人数统计年份" onChange={(event) => onYearChange(Number(event.target.value))} value={participationYear}>{participationYearOptions(participationYear).map((year) => <option key={year} value={year}>{year}</option>)}</select></label>{participationGranularity === "month" && <label>月份<select aria-label="参与人数统计月份" onChange={(event) => onMonthChange(Number(event.target.value))} value={participationMonth}>{Array.from({ length: 12 }, (_, index) => index + 1).map((month) => <option key={month} value={month}>{month} 月</option>)}</select></label>}</div></div>
        <div className={`participation-calendar participation-calendar-${participationGranularity}`} aria-label={`${participationYear} 年${participationGranularity === "month" ? ` ${participationMonth} 月` : ""}参与考试统计`}>
          {participationGranularity === "month" && <div className="participation-calendar-weekdays">{["一", "二", "三", "四", "五", "六", "日"].map((weekday) => <span key={weekday}>{weekday}</span>)}</div>}
          <div className="participation-calendar-grid">{calendarCells.map((cell, index) => cell ? <div className="participation-calendar-cell" key={cell.period.period_key}><strong>{cell.label}</strong><span>参与 {cell.period.participant_count}</span><span>完成 {cell.period.completed_count}</span></div> : <div className="participation-calendar-cell is-empty" key={`empty-${index}`} aria-hidden="true" />)}</div>
        </div>
        <div className="participation-calendar-total"><span>合计参与 {participationTotals.participants} 人次</span><span>完成 {participationTotals.completed} 人次</span></div>
      </section>
      <section className="content-panel exam-analytics-card score-analytics-card">
        <div className="section-title"><div><h2><BarChart3 size={17} />成绩分布</h2><span>按得分区间统计已完成评分的答卷</span></div></div>
        {gradedCount === 0 ? <p className="analytics-empty">暂无可统计成绩</p> : <><div className="score-distribution-summary"><dl><div><dt>已完成评分</dt><dd>{gradedCount} 份</dd></div><div><dt>60 分以上</dt><dd>{aboveThresholdRate === null ? "—" : `${aboveThresholdRate}%`}<small>{aboveThresholdCount} 份</small></dd></div></dl></div><div className="analytics-table-wrap"><table className="score-distribution-table"><caption>成绩区间明细</caption><thead><tr><th>区间</th><th>人数</th><th>占比</th></tr></thead><tbody>{distribution.map((bucket) => <tr key={bucket.label}><th scope="row">{bucket.label}</th><td>{bucket.count}</td><td>{bucket.percentage}%</td></tr>)}</tbody></table></div></>}
      </section>
    </div>
  );
}

function participationYearOptions(selectedYear: number) {
  const currentYear = new Date().getFullYear();
  const latestYear = Math.max(currentYear, selectedYear);
  const firstYear = Math.min(currentYear - 9, selectedYear);
  return Array.from({ length: latestYear - firstYear + 1 }, (_, index) => latestYear - index);
}

function buildParticipationCalendar(granularity: ExamParticipationGranularity, year: number, month: number, periods: ExamParticipationPeriod[]) {
  const periodMap = new Map(periods.map((period) => [period.period_key, period]));
  if (granularity === "year") {
    return Array.from({ length: 12 }, (_, index) => {
      const monthNumber = index + 1;
      const periodKey = `${year}-${String(monthNumber).padStart(2, "0")}`;
      return { label: `${monthNumber} 月`, period: periodMap.get(periodKey) || { period_key: periodKey, period_label: periodKey, participant_count: 0, completed_count: 0 } };
    });
  }
  const firstDate = new Date(year, month - 1, 1);
  const dayOffset = (firstDate.getDay() + 6) % 7;
  const daysInMonth = new Date(year, month, 0).getDate();
  const cells: ({ label: string; period: ExamParticipationPeriod } | null)[] = Array.from({ length: dayOffset }, () => null);
  for (let day = 1; day <= daysInMonth; day += 1) {
    const periodKey = `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
    cells.push({ label: String(day), period: periodMap.get(periodKey) || { period_key: periodKey, period_label: periodKey, participant_count: 0, completed_count: 0 } });
  }
  while (cells.length % 7 !== 0) cells.push(null);
  return cells;
}

function AttemptQuestion({ question, answer, index, sourceMode }: { question: ExamQuestion; answer: ExamAttempt["answers"][number] | undefined; index: number; sourceMode: ExamAttempt["source_mode"] }) {
  const selectedText = answer ? question.question_type === "short" ? answer.text_answer || "未作答" : question.options.filter((option) => answer.selected_answers.includes(option.id)).map((option) => `${option.id}. ${option.text}`).join("；") || "未作答" : "尚未提交";
  const correctText = question.question_type === "short" ? question.reference_answer : question.options.filter((option) => question.correct_answers?.includes(option.id)).map((option) => `${option.id}. ${option.text}`).join("；");
  return <article className={`result-question ${answer?.is_correct ? "correct" : "incorrect"}`}>
    <div className="question-card-header"><span className="question-number">第 {index + 1} 题 · {question.knowledge_point}</span><span className={answer && answer.score / answer.max_score >= 0.6 ? "score-good" : "score-low"}>{answer ? `${formatScore(answer.score)} / ${formatScore(answer.max_score)} 分` : "等待提交"}</span></div>
    <h3>{question.prompt}</h3>
    <div className="result-answer-row"><div><strong>参与者答案：</strong>{selectedText}</div><div><strong>{question.question_type === "short" ? "参考答案" : "正确答案"}：</strong>{correctText || "—"}</div></div>
    {answer && <div className="result-feedback">{answer.is_correct ? <Check size={14} /> : <CircleX size={14} />}{answer.feedback} {question.explanation}</div>}
    {question.grading_rubric.length > 0 && <div className="rubric-list">{question.grading_rubric.map((rubric) => <div className={`rubric-row ${answer?.matched_points.includes(rubric.point) ? "hit" : ""}`} key={rubric.point}>{answer?.matched_points.includes(rubric.point) ? "已覆盖" : "待补充"}：{rubric.point}</div>)}</div>}
    <EvidenceList evidence={question.source_evidence} sourceMode={sourceMode} />
  </article>;
}
